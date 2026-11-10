"""Shared services mixin (§9): the shared-service registry,
governed per-business access, usage accounting and internal cost
allocation.

Rules enforced here:
* a business uses a shared service only after owner-approved access
  (REQUESTED → APPROVED → ACTIVE; revocable at any time);
* usage is recorded only against ACTIVE access — an unapproved or
  revoked business cannot consume the service (§21 Scenario 8);
* cost allocation is INTERNAL management accounting: one row per
  charged business, `kind` permanently INTERNAL_ALLOCATION. It never
  enters P-07, never moves money and is never presented as an
  external payment (§11). A computation writes a batch of rows
  (linked by a batch token in the note) that is decided as a unit.
"""
from __future__ import annotations

import uuid

from ..core.exceptions import (
    InvalidStateTransitionError, NotFoundError, PermissionDeniedError,
    ValidationError,
)
from ..database.models.base import utcnow
from ..database.models.portfolio import (
    InternalCostAllocation, SharedService, SharedServiceAccess,
    SharedServiceUsage,
)
from ..database.repositories.portfolio import (
    AllocationRepository, MembershipRepository, ServiceAccessRepository,
    ServiceUsageRepository, SharedServiceRepository,
)
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from .constants import actor_of

ALLOCATION_METHODS = {"equal", "usage_based", "fixed",
                      "priority_weighted"}
PRESENTATION = ("internal management allocation — not an external "
                "cash payment; recorded in no ledger (P-07 is "
                "unaffected)")


def service_dict(row: SharedService) -> dict:
    return {
        "id": row.id, "name": row.name, "kind": row.service_kind,
        "service_kind": row.service_kind,
        "description": row.description, "provider": row.provider,
        "supported_categories": row.supported_categories,
        "status": row.status,
        "capacity_units": row.capacity_units,
        "cost_model": row.cost_model,
        "security_classification": row.security_classification,
        "access_policy": row.access_policy, "sla": row.sla,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def access_dict(row: SharedServiceAccess) -> dict:
    return {
        "id": row.id, "service_id": row.service_id,
        "business_id": row.business_id, "status": row.status,
        "scope": row.scope, "units_reserved": row.units_reserved,
        "requested_by": row.requested_by, "decided_by": row.granted_by,
        "granted_by": row.granted_by,
        "expires_at": row.expires_at.isoformat()
        if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _method_of(note: str) -> str | None:
    for part in (note or "").split():
        if part.startswith("method:"):
            return part.split(":", 1)[1]
    return None


def _batch_of(note: str) -> str | None:
    for part in (note or "").split():
        if part.startswith("batch:"):
            return part.split(":", 1)[1]
    return None


def allocation_dict(row: InternalCostAllocation) -> dict:
    return {
        "id": row.id, "service_id": row.service_id,
        "portfolio_id": row.portfolio_id,
        # The honesty label is part of the record itself (§11/§21
        # Scenario 12): this is internal management accounting.
        "kind": "INTERNAL_ALLOCATION",
        "is_external_payment": False,
        "presentation": PRESENTATION,
        "method": _method_of(row.note),
        "business_id": row.charged_business_id,
        "charged_business_id": row.charged_business_id,
        "providing_business_id": row.providing_business_id,
        "amount_minor": row.amount_minor,
        "period_label": row.period, "period": row.period,
        "currency": row.currency, "status": row.status,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class SharedServicesMixin:
    # -------------------------------------------------------- services
    def create_service(self, principal: Principal, data: dict) -> dict:
        self._require_owner(principal, "portfolio.service_create")
        kind = str(data.get("kind") or data.get("service_kind") or "")
        if kind not in C.SERVICE_KINDS:
            raise ValidationError(f"unknown shared service kind: {kind}")
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValidationError("a shared service requires a name")
        session = self._session_factory()
        try:
            row = SharedServiceRepository(session).add(SharedService(
                name=name[:200], service_kind=kind,
                description=str(data.get("description") or ""),
                provider=str(data.get("provider") or ""),
                supported_categories=list(
                    data.get("supported_categories") or []),
                capacity_units=int(data.get("capacity_units", 0)),
                cost_model=dict(data.get("cost_model") or {}),
                security_classification=str(
                    data.get("security_classification") or "internal"),
                access_policy=str(data.get("access_policy")
                                  or "owner_approval"),
                sla=str(data.get("sla") or ""),
                created_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.service_created",
                    "shared_service", row.id, "allow",
                    "shared service registered", {"kind": kind})
        return service_dict(row)

    def list_services(self, principal: Principal) -> dict:
        self._require_portfolio_reader(principal, "portfolio.services")
        session = self._session_factory()
        try:
            rows, total = SharedServiceRepository(session).list(limit=200)
            items = [service_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": total}

    def set_service_status(self, principal: Principal, service_id: str,
                           status: str) -> dict:
        self._require_owner(principal, "portfolio.service_status")
        if status not in C.SERVICE_STATUSES:
            raise ValidationError(f"unknown service status: {status}")
        session = self._session_factory()
        try:
            repo = SharedServiceRepository(session)
            row = repo.get(service_id)
            if row is None:
                raise NotFoundError(f"shared service {service_id} not found")
            row.status = status
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.service_status", "shared_service",
                    service_id, "allow", f"service status -> {status}", {})
        return service_dict(row)

    # ---------------------------------------------------------- access
    def request_access(self, principal: Principal, service_id: str,
                       data: dict) -> dict:
        self._require_owner(principal, "portfolio.service_access_request")
        business_id = data.get("business_id")
        if not business_id:
            raise ValidationError("business_id is required")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            repo = ServiceAccessRepository(session)
            service = SharedServiceRepository(session).get(service_id)
            if service is None:
                raise NotFoundError(f"shared service {service_id} not found")
            existing = repo.get_access(service_id, business_id)
            if existing is not None and existing.status in (
                    "REQUESTED", "APPROVED", "ACTIVE"):
                raise ValidationError(
                    "an access record already exists for this business "
                    f"({existing.status})")
            if existing is not None:  # re-request after denial/revocation
                existing.status = "REQUESTED"
                existing.scope = dict(data.get("scope") or {})
                existing.units_reserved = int(
                    data.get("units_reserved", 0))
                existing.requested_by = actor_of(principal)
                existing.revoked_by = None
                existing.revoked_at = None
                repo.save(existing)
                row = existing
            else:
                row = repo.add(SharedServiceAccess(
                    service_id=service_id, business_id=business_id,
                    scope=dict(data.get("scope") or {}),
                    units_reserved=int(data.get("units_reserved", 0)),
                    requested_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.service_access_requested",
                    "shared_service", service_id, "allow",
                    "service access requested", {"business_id": business_id})
        return access_dict(row)

    def decide_access(self, principal: Principal, access_id: str,
                      approve: bool) -> dict:
        self._require_owner(principal, "portfolio.service_access_decide")
        session = self._session_factory()
        try:
            repo = ServiceAccessRepository(session)
            row = repo.get(access_id)
            if row is None:
                raise NotFoundError(f"service access {access_id} not found")
            if row.status != "REQUESTED":
                raise InvalidStateTransitionError(
                    f"access is {row.status}; only REQUESTED can be decided")
            row.status = "APPROVED" if approve else "DENIED"
            row.granted_by = actor_of(principal)
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.service_access_decided",
                    "shared_service_access", access_id, "allow",
                    f"access {'approved' if approve else 'denied'}", {})
        return access_dict(row)

    def activate_access(self, principal: Principal, access_id: str) -> dict:
        self._require_owner(principal, "portfolio.service_access_activate")
        session = self._session_factory()
        try:
            repo = ServiceAccessRepository(session)
            row = repo.get(access_id)
            if row is None:
                raise NotFoundError(f"service access {access_id} not found")
            if row.status != "APPROVED":
                raise InvalidStateTransitionError(
                    f"access is {row.status}; only APPROVED can activate")
            row.status = "ACTIVE"
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        return access_dict(row)

    def revoke_access(self, principal: Principal, access_id: str) -> dict:
        self._require_owner(principal, "portfolio.service_access_revoke")
        session = self._session_factory()
        try:
            repo = ServiceAccessRepository(session)
            row = repo.get(access_id)
            if row is None:
                raise NotFoundError(f"service access {access_id} not found")
            if row.status in ("REVOKED", "DENIED", "EXPIRED"):
                raise InvalidStateTransitionError(
                    f"access is already {row.status}")
            row.status = "REVOKED"
            row.revoked_by = actor_of(principal)
            row.revoked_at = utcnow().isoformat()
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.service_access_revoked",
                    "shared_service_access", access_id, "allow",
                    "service access revoked; further usage is refused", {})
        return access_dict(row)

    def list_access(self, principal: Principal, service_id: str) -> dict:
        self._require_portfolio_reader(principal, "portfolio.service_access")
        session = self._session_factory()
        try:
            rows = ServiceAccessRepository(session).for_service(service_id)
            items = [access_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": len(items)}

    # ----------------------------------------------------------- usage
    def record_usage(self, principal: Principal, service_id: str,
                     data: dict) -> dict:
        """Usage is the consumption record the cost allocation reads.
        It is accepted only for a business with ACTIVE access —
        anything else is an isolation breach, audited and refused."""
        business_id = data.get("business_id")
        if not business_id:
            raise ValidationError("business_id is required")
        if principal.type not in (PrincipalType.OWNER,
                                  PrincipalType.SYSTEM):
            self._assert_business_read(principal, business_id)
        units = int(data.get("units", 0))
        if units <= 0:
            raise ValidationError("usage units must be positive")
        session = self._session_factory()
        try:
            access = ServiceAccessRepository(session).get_access(
                service_id, business_id)
            if access is None or access.status != "ACTIVE":
                self._audit(principal, "portfolio.isolation_violation",
                            "shared_service", service_id, "deny",
                            "usage attempted without ACTIVE service "
                            "access", {"business_id": business_id})
                raise PermissionDeniedError(
                    "this business has no ACTIVE access to the shared "
                    "service; usage is refused (§9/§20)")
            row = ServiceUsageRepository(session).add(SharedServiceUsage(
                access_id=access.id, service_id=service_id,
                business_id=business_id, units=units,
                note=str(data.get("note") or ""),
                recorded_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        return {"id": row.id, "service_id": service_id,
                "business_id": business_id, "units": units,
                "recorded_by": row.recorded_by}

    def usage_view(self, principal: Principal, service_id: str) -> dict:
        self._require_portfolio_reader(principal, "portfolio.service_usage")
        session = self._session_factory()
        try:
            rows = ServiceUsageRepository(session).for_service(service_id)
            per_business: dict[str, int] = {}
            for r in rows:
                per_business[r.business_id] = \
                    per_business.get(r.business_id, 0) + r.units
            service = SharedServiceRepository(session).get(service_id)
            if service is None:
                raise NotFoundError(f"shared service {service_id} not found")
        finally:
            session.close()
        return {"service": service_dict(service),
                "per_business_units": per_business,
                "total_units": sum(per_business.values())}

    # ----------------------------------------------------- allocations
    def create_allocation(self, principal: Principal, data: dict) -> dict:
        """Compute an internal cost allocation (§9/§11). The total
        is an owner-declared internal service cost (management
        accounting input), split by the chosen method into one row
        per charged business. The batch is stored as
        INTERNAL_ALLOCATION forever — P-07 never sees it and no
        money moves."""
        self._require_owner(principal, "portfolio.allocation_create")
        service_id = data.get("service_id")
        portfolio_id = data.get("portfolio_id")
        if not portfolio_id:
            raise ValidationError(
                "portfolio_id is required: internal allocations are "
                "recorded within a portfolio's governance context")
        self._portfolio_or_404(portfolio_id)
        method = str(data.get("method") or "")
        if method not in ALLOCATION_METHODS:
            raise ValidationError(f"unknown allocation method: {method}")
        total = int(data.get("total_cost_minor", 0))
        if total < 0:
            raise ValidationError("total_cost_minor must be >= 0")
        business_ids = list(data.get("business_ids") or [])
        if len(business_ids) < 2:
            raise ValidationError(
                "an internal allocation spans at least two businesses")
        session = self._session_factory()
        try:
            service = SharedServiceRepository(session).get(service_id)
            if service is None:
                raise NotFoundError(f"shared service {service_id} not found")
            usage_repo = ServiceUsageRepository(session)
            shares: dict[str, int] = {}
            if method == "equal":
                base = total // len(business_ids)
                shares = {bid: base for bid in business_ids}
                shares[business_ids[0]] += total - base * len(business_ids)
            elif method == "usage_based":
                units = {}
                for bid in business_ids:
                    access = ServiceAccessRepository(session).get_access(
                        service_id, bid)
                    units[bid] = usage_repo.total_units(access.id) \
                        if access is not None else 0
                total_units = sum(units.values())
                if total_units <= 0:
                    raise ValidationError(
                        "usage_based allocation requires recorded usage")
                allocated = 0
                for bid in business_ids[:-1]:
                    shares[bid] = total * units[bid] // total_units
                    allocated += shares[bid]
                shares[business_ids[-1]] = total - allocated
            elif method == "fixed":
                given = {a["business_id"]: int(a["share_bps"])
                         for a in data.get("allocations") or []}
                if set(given) != set(business_ids) or \
                        sum(given.values()) != 10000:
                    raise ValidationError(
                        "fixed allocation requires share_bps for every "
                        "business summing to 10000")
                allocated = 0
                for bid in business_ids[:-1]:
                    shares[bid] = total * given[bid] // 10000
                    allocated += shares[bid]
                shares[business_ids[-1]] = total - allocated
            else:  # priority_weighted — strategic priority from P-13
                weights = {}
                for bid in business_ids:
                    member = MembershipRepository(session).get_membership(
                        portfolio_id, bid)
                    if member is None:
                        raise ValidationError(
                            f"business {bid} is not a member of the "
                            "portfolio")
                    weights[bid] = max(1, member.strategic_priority)
                total_weight = sum(weights.values())
                allocated = 0
                for bid in business_ids[:-1]:
                    shares[bid] = total * weights[bid] // total_weight
                    allocated += shares[bid]
                shares[business_ids[-1]] = total - allocated
            batch = uuid.uuid4().hex[:12]
            note = (f"batch:{batch} method:{method} internal management "
                    "allocation (not a payment)")
            repo = AllocationRepository(session)
            rows = []
            for bid, amount in shares.items():
                rows.append(repo.add(InternalCostAllocation(
                    portfolio_id=portfolio_id, service_id=service_id,
                    charged_business_id=bid, amount_minor=amount,
                    currency=str(data.get("currency") or "INR"),
                    period=str(data.get("period_label")
                               or data.get("period") or ""),
                    note=note, created_by=actor_of(principal))))
            first = rows[0]
            result = {
                "id": first.id,
                "allocation_ids": [r.id for r in rows],
                "service_id": service_id, "portfolio_id": portfolio_id,
                "kind": "INTERNAL_ALLOCATION",
                "is_external_payment": False,
                "presentation": PRESENTATION,
                "method": method,
                "period_label": first.period,
                "currency": first.currency,
                "total_cost_minor": total,
                "allocations": [
                    {"business_id": r.charged_business_id,
                     "amount_minor": r.amount_minor, "id": r.id}
                    for r in rows],
                "status": first.status,
                "created_by": first.created_by,
            }
        finally:
            session.close()
        self._audit(principal, "portfolio.allocation_created",
                    "internal_cost_allocation", result["id"], "allow",
                    "internal cost allocation computed (not a payment)",
                    {"method": method, "total_cost_minor": total})
        return result

    def decide_allocation(self, principal: Principal, allocation_id: str,
                          approve: bool) -> dict:
        """Decide a whole computation batch (the rows written by one
        create call) — approving one row approves its batch."""
        self._require_owner(principal, "portfolio.allocation_decide")
        session = self._session_factory()
        try:
            repo = AllocationRepository(session)
            row = repo.get(allocation_id)
            if row is None:
                raise NotFoundError(
                    f"internal allocation {allocation_id} not found")
            if row.status != "RECORDED":
                raise InvalidStateTransitionError(
                    f"allocation is already {row.status}")
            batch = _batch_of(row.note)
            rows, _t = repo.list(limit=500, portfolio_id=row.portfolio_id,
                                 service_id=row.service_id)
            decided = []
            for candidate in rows:
                if _batch_of(candidate.note) == batch and \
                        candidate.status == "RECORDED":
                    candidate.status = "APPROVED" if approve else "REJECTED"
                    repo.save(candidate)
                    decided.append(allocation_dict(candidate))
            result = allocation_dict(row)
            result["allocations"] = decided
            result["status"] = "APPROVED" if approve else "REJECTED"
        finally:
            session.close()
        return result

    def list_allocations(self, principal: Principal, *,
                         service_id: str | None = None,
                         portfolio_id: str | None = None) -> dict:
        self._require_portfolio_reader(principal, "portfolio.allocations")
        session = self._session_factory()
        try:
            rows, _t = AllocationRepository(session).list(
                limit=500, service_id=service_id,
                portfolio_id=portfolio_id)
            items = [allocation_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": len(items)}
