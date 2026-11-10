"""Resources mixin (§10): shared-resource quotas, capacity
allocation and reclamation for the single-machine deployment.

Enforced mechanically:
* capacity is finite and owner-configured (settings) — allocations
  can never exceed it (APPROVED and ACTIVE allocations both count
  against capacity, so approval cannot over-commit);
* anti-monopolization: one business may hold at most the configured
  share of any resource kind;
* a business cannot allocate beyond its quota;
* portfolio survival mode blocks new discretionary allocations
  (essential ones must be declared as such);
* releasing/revoking an allocation frees capacity immediately.
"""
from __future__ import annotations

from ..core.exceptions import (
    InvalidStateTransitionError, NotFoundError, ValidationError,
)
from ..database.models.portfolio import ResourceAllocation, ResourceQuota
from ..database.repositories.portfolio import (
    MembershipRepository, QuotaRepository, ResourceAllocationRepository,
)
from ..permissions.models import Principal
from . import constants as C
from .constants import actor_of

COUNTED_STATUSES = ("APPROVED", "ACTIVE")


def quota_dict(row: ResourceQuota) -> dict:
    return {
        "id": row.id, "portfolio_id": row.portfolio_id,
        "business_id": row.business_id, "resource_kind": row.resource_kind,
        "max_units": row.quota_units, "quota_units": row.quota_units,
        "created_by": row.created_by,
    }


def resource_allocation_dict(row: ResourceAllocation) -> dict:
    return {
        "id": row.id, "portfolio_id": row.portfolio_id,
        "business_id": row.business_id, "resource_kind": row.resource_kind,
        "units": row.units, "purpose": row.rationale,
        "rationale": row.rationale,
        "essential": not row.discretionary,
        "discretionary": row.discretionary,
        "status": row.status, "created_by": row.created_by,
        "decided_by": row.decided_by,
        "released_reason": row.released_reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class ResourcesMixin:
    def _allocated_units(self, session, portfolio_id: str,
                         resource_kind: str,
                         business_id: str | None = None) -> int:
        repo = ResourceAllocationRepository(session)
        total = 0
        for status in COUNTED_STATUSES:
            rows, _t = repo.list(limit=500, portfolio_id=portfolio_id,
                                 resource_kind=resource_kind,
                                 status=status, business_id=business_id)
            total += sum(r.units for r in rows)
        return total

    def resource_view(self, principal: Principal, portfolio_id: str) -> dict:
        self._require_portfolio_reader(principal, "portfolio.resources")
        self._portfolio_or_404(portfolio_id)
        settings = self.get_settings()
        session = self._session_factory()
        try:
            kinds = {}
            for kind, capacity in settings["capacities"].items():
                used = self._allocated_units(session, portfolio_id, kind)
                per_business: dict[str, int] = {}
                repo = ResourceAllocationRepository(session)
                for status in COUNTED_STATUSES:
                    rows, _t = repo.list(
                        limit=500, portfolio_id=portfolio_id,
                        resource_kind=kind, status=status)
                    for row in rows:
                        per_business[row.business_id] = \
                            per_business.get(row.business_id, 0) + row.units
                kinds[kind] = {
                    "capacity_units": capacity,
                    "allocated_units": used,
                    "available_units": max(0, capacity - used),
                    "per_business": per_business,
                    "business_share_cap_bps":
                        settings["business_share_cap_bps"],
                }
            quotas, _t = QuotaRepository(session).list(
                limit=200, portfolio_id=portfolio_id)
            quota_items = [quota_dict(q) for q in quotas]
        finally:
            session.close()
        return {
            "portfolio_id": portfolio_id, "kinds": kinds,
            "quotas": quota_items,
            "capacity_source": "owner-configured settings (declared "
                               "capacities for the single-machine "
                               "deployment, not live telemetry)",
        }

    def set_quota(self, principal: Principal, portfolio_id: str,
                  data: dict) -> dict:
        self._require_owner(principal, "portfolio.quota_set")
        self._portfolio_or_404(portfolio_id)
        business_id = data.get("business_id")
        kind = str(data.get("resource_kind") or "")
        if kind not in C.RESOURCE_KINDS:
            raise ValidationError(f"unknown resource kind: {kind}")
        if business_id not in self._member_business_ids(portfolio_id):
            raise ValidationError(
                "quotas apply to portfolio member businesses only")
        max_units = int(data.get("max_units",
                                 data.get("quota_units", 0)))
        if max_units < 0:
            raise ValidationError("max_units must be >= 0")
        session = self._session_factory()
        try:
            repo = QuotaRepository(session)
            row = repo.get_quota(portfolio_id, business_id, kind)
            if row is not None:
                row.quota_units = max_units
                repo.save(row)
            else:
                row = repo.add(ResourceQuota(
                    portfolio_id=portfolio_id, business_id=business_id,
                    resource_kind=kind, quota_units=max_units,
                    created_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.quota_set", "portfolio",
                    portfolio_id, "allow", "resource quota set",
                    {"business_id": business_id, "resource_kind": kind,
                     "max_units": max_units})
        return quota_dict(row)

    def propose_resource_allocation(self, principal: Principal,
                                    portfolio_id: str, data: dict) -> dict:
        self._require_owner(principal, "portfolio.resource_propose")
        portfolio = self._portfolio_or_404(portfolio_id)
        business_id = data.get("business_id")
        kind = str(data.get("resource_kind") or "")
        if kind not in C.RESOURCE_KINDS:
            raise ValidationError(f"unknown resource kind: {kind}")
        if business_id not in self._member_business_ids(portfolio_id):
            raise ValidationError(
                "resource allocations apply to portfolio members only")
        units = int(data.get("units", 0))
        if units <= 0:
            raise ValidationError("units must be positive")
        essential = bool(data.get("essential", False))
        discretionary = not essential
        if portfolio.survival_mode and discretionary:
            raise ValidationError(
                "portfolio survival mode is active: discretionary "
                "resource allocations are blocked; declare the "
                "allocation essential or clear survival mode (§12)")
        settings = self.get_settings()
        capacity = settings["capacities"].get(kind, 0)
        session = self._session_factory()
        try:
            repo = ResourceAllocationRepository(session)
            quota = QuotaRepository(session).get_quota(
                portfolio_id, business_id, kind)
            if quota is None:
                raise ValidationError(
                    "no quota exists for this business and resource "
                    "kind; set a quota first (§10)")
            business_used = self._allocated_units(
                session, portfolio_id, kind, business_id)
            if business_used + units > quota.quota_units:
                raise ValidationError(
                    f"allocation exceeds the business quota "
                    f"({business_used} + {units} > {quota.quota_units})")
            total_used = self._allocated_units(session, portfolio_id, kind)
            if total_used + units > capacity:
                raise ValidationError(
                    f"allocation exceeds configured capacity "
                    f"({total_used} + {units} > {capacity})")
            cap_units = capacity * settings["business_share_cap_bps"] \
                // 10000
            if business_used + units > cap_units:
                raise ValidationError(
                    "anti-monopolization cap: one business may hold at "
                    f"most {settings['business_share_cap_bps'] / 100:.0f}% "
                    f"of {kind} capacity ({cap_units} units)")
            row = repo.add(ResourceAllocation(
                portfolio_id=portfolio_id, business_id=business_id,
                resource_kind=kind, units=units,
                rationale=str(data.get("purpose")
                              or data.get("rationale") or ""),
                discretionary=discretionary,
                created_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.resource_proposed", "portfolio",
                    portfolio_id, "allow", "resource allocation proposed",
                    {"business_id": business_id, "resource_kind": kind,
                     "units": units})
        return resource_allocation_dict(row)

    def decide_resource_allocation(self, principal: Principal,
                                   allocation_id: str,
                                   approve: bool) -> dict:
        self._require_owner(principal, "portfolio.resource_decide")
        session = self._session_factory()
        try:
            repo = ResourceAllocationRepository(session)
            row = repo.get(allocation_id)
            if row is None:
                raise NotFoundError(
                    f"resource allocation {allocation_id} not found")
            if row.status != "PROPOSED":
                raise InvalidStateTransitionError(
                    f"allocation is already {row.status}")
            row.status = "APPROVED" if approve else "DENIED"
            row.decided_by = actor_of(principal)
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        return resource_allocation_dict(row)

    def activate_resource_allocation(self, principal: Principal,
                                     allocation_id: str) -> dict:
        self._require_owner(principal, "portfolio.resource_activate")
        session = self._session_factory()
        try:
            repo = ResourceAllocationRepository(session)
            row = repo.get(allocation_id)
            if row is None:
                raise NotFoundError(
                    f"resource allocation {allocation_id} not found")
            if row.status != "APPROVED":
                raise InvalidStateTransitionError(
                    f"allocation is {row.status}; only APPROVED activates")
            row.status = "ACTIVE"
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        return resource_allocation_dict(row)

    def release_resource_allocation(self, principal: Principal,
                                    allocation_id: str,
                                    reason: str = "") -> dict:
        self._require_owner(principal, "portfolio.resource_release")
        session = self._session_factory()
        try:
            repo = ResourceAllocationRepository(session)
            row = repo.get(allocation_id)
            if row is None:
                raise NotFoundError(
                    f"resource allocation {allocation_id} not found")
            if row.status not in COUNTED_STATUSES:
                raise InvalidStateTransitionError(
                    f"allocation is {row.status}; nothing to release")
            row.status = "RELEASED"
            row.released_reason = str(reason or "")[:200]
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.resource_released",
                    "resource_allocation", allocation_id, "allow",
                    f"resource allocation released: {reason}", {})
        return resource_allocation_dict(row)

    def reclaim_idle(self, principal: Principal, portfolio_id: str) -> dict:
        """§10 reclamation: counted allocations held by businesses
        that are no longer active members are revoked, freeing
        capacity. Nothing else is touched."""
        self._require_owner(principal, "portfolio.resource_reclaim")
        self._portfolio_or_404(portfolio_id)
        active_members = set(self._member_business_ids(portfolio_id))
        session = self._session_factory()
        actions = []
        try:
            repo = ResourceAllocationRepository(session)
            members_repo = MembershipRepository(session)
            rows, _t = repo.list(limit=500, portfolio_id=portfolio_id)
            for row in rows:
                if row.status not in COUNTED_STATUSES:
                    continue
                member = members_repo.get_membership(portfolio_id,
                                                     row.business_id)
                if member is None or member.status != "ACTIVE" or \
                        row.business_id not in active_members:
                    row.status = "REVOKED"
                    repo.save(row)
                    actions.append({
                        "allocation_id": row.id,
                        "business_id": row.business_id,
                        "resource_kind": row.resource_kind,
                        "units_freed": row.units,
                        "reason": "business is no longer an active "
                                  "portfolio member"})
        finally:
            session.close()
        self._audit(principal, "portfolio.resource_reclaimed", "portfolio",
                    portfolio_id, "allow",
                    "idle/orphaned resource allocations reclaimed",
                    {"actions": len(actions)})
        return {"portfolio_id": portfolio_id, "actions": actions}
