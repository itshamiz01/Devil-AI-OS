"""Registry mixin (§4/§5): portfolios, business membership,
analytical grouping, portfolio objectives, survival mode and the
business registry view.

The registry NEVER duplicates a business record: a membership row
points at the P-06 business and adds portfolio-side metadata only.
Removing a membership deletes nothing outside P-13. Lifecycle truth
is read live from P-06 (+ the P-08 overlay reading) and presented
through the §4 derivation in constants.portfolio_stage.
"""
from __future__ import annotations

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.base import utcnow
from ..database.models.portfolio import (
    BusinessPortfolio, PortfolioBusinessMembership, PortfolioObjective,
)
from ..database.repositories.portfolio import (
    MembershipRepository, ObjectiveRepository, PortfolioRepository,
)
from ..permissions.models import Principal
from . import constants as C
from .constants import actor_of


def portfolio_dict(row: BusinessPortfolio) -> dict:
    return {
        "id": row.id, "name": row.name, "description": row.description,
        "mission": row.mission, "status": row.status,
        "survival_mode": row.survival_mode,
        "survival_activated_by": row.survival_activated_by,
        "survival_activated_at": row.survival_activated_at,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def membership_dict(row: PortfolioBusinessMembership) -> dict:
    return {
        "id": row.id, "portfolio_id": row.portfolio_id,
        "business_id": row.business_id, "status": row.status,
        "strategic_priority": row.strategic_priority,
        "group_labels": row.group_labels, "notes": row.notes,
        "registered_by": row.registered_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def objective_dict(row: PortfolioObjective) -> dict:
    return {
        "id": row.id, "portfolio_id": row.portfolio_id,
        "title": row.title, "description": row.description,
        "horizon": row.horizon, "targets": row.targets,
        "status": row.status, "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class RegistryMixin:
    # ------------------------------------------------------ portfolios
    def create_portfolio(self, principal: Principal, data: dict) -> dict:
        self._require_owner(principal, "portfolio.create")
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValidationError("a portfolio requires a name")
        session = self._session_factory()
        try:
            row = PortfolioRepository(session).add(BusinessPortfolio(
                name=name[:200],
                description=str(data.get("description") or ""),
                mission=str(data.get("mission") or ""),
                created_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.created", "portfolio", row.id,
                    "allow", "portfolio created", {"name": name})
        return portfolio_dict(row)

    def list_portfolios(self, principal: Principal) -> dict:
        self._require_portfolio_reader(principal, "portfolio.list")
        session = self._session_factory()
        try:
            rows, total = PortfolioRepository(session).list(limit=200)
            items = [portfolio_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": total}

    def get_portfolio(self, principal: Principal, portfolio_id: str) -> dict:
        self._require_portfolio_reader(principal, "portfolio.get")
        return portfolio_dict(self._portfolio_or_404(portfolio_id))

    def archive_portfolio(self, principal: Principal,
                          portfolio_id: str) -> dict:
        self._require_owner(principal, "portfolio.archive")
        session = self._session_factory()
        try:
            repo = PortfolioRepository(session)
            row = repo.get(portfolio_id)
            if row is None:
                raise NotFoundError(f"portfolio {portfolio_id} not found")
            row.status = "ARCHIVED"
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.archived", "portfolio",
                    portfolio_id, "allow", "portfolio archived", {})
        return portfolio_dict(row)

    def set_survival_mode(self, principal: Principal, portfolio_id: str,
                          enabled: bool) -> dict:
        """§12 portfolio survival mode: an advisory state. It flags
        endangered businesses (in intelligence/risk views) and blocks
        new discretionary P-13 resource allocations. It does NOT
        pause businesses, redirect funds or shut anything down —
        those remain P-08/P-10/P-07 owner paths."""
        self._require_owner(principal, "portfolio.survival_mode")
        session = self._session_factory()
        try:
            repo = PortfolioRepository(session)
            row = repo.get(portfolio_id)
            if row is None:
                raise NotFoundError(f"portfolio {portfolio_id} not found")
            row.survival_mode = bool(enabled)
            row.survival_activated_by = actor_of(principal) if enabled else None
            row.survival_activated_at = (
                utcnow().isoformat() if enabled else None)
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.survival_mode", "portfolio",
                    portfolio_id, "allow",
                    f"survival mode {'activated' if enabled else 'cleared'}",
                    {"enabled": bool(enabled)})
        return portfolio_dict(row)

    # ----------------------------------------------------- memberships
    def register_business(self, principal: Principal, portfolio_id: str,
                          data: dict) -> dict:
        self._require_owner(principal, "portfolio.register_business")
        self._portfolio_or_404(portfolio_id)
        business_id = data.get("business_id")
        if not business_id:
            raise ValidationError("business_id is required")
        self._business_or_404(business_id)  # must exist in P-06
        priority = int(data.get("strategic_priority", 50))
        if not 0 <= priority <= 100:
            raise ValidationError("strategic_priority must be 0..100")
        session = self._session_factory()
        try:
            repo = MembershipRepository(session)
            existing = repo.get_membership(portfolio_id, business_id)
            if existing is not None and existing.status != "REMOVED":
                raise ValidationError(
                    "business is already registered in this portfolio")
            if existing is not None:  # re-register a removed membership
                existing.status = "ACTIVE"
                existing.strategic_priority = priority
                existing.group_labels = list(data.get("group_labels") or [])
                existing.notes = str(data.get("notes") or "")
                repo.save(existing)
                row = existing
            else:
                row = repo.add(PortfolioBusinessMembership(
                    portfolio_id=portfolio_id, business_id=business_id,
                    strategic_priority=priority,
                    group_labels=list(data.get("group_labels") or []),
                    notes=str(data.get("notes") or ""),
                    registered_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.business_registered",
                    "portfolio", portfolio_id, "allow",
                    "business registered in portfolio",
                    {"business_id": business_id})
        return membership_dict(row)

    def set_membership_status(self, principal: Principal,
                              portfolio_id: str, business_id: str,
                              status: str) -> dict:
        """Activate / pause / remove a membership. Removal ends
        portfolio management of the business; the business record
        itself is never touched (§4)."""
        self._require_owner(principal, "portfolio.membership_status")
        if status not in C.MEMBERSHIP_STATUSES:
            raise ValidationError(f"unknown membership status: {status}")
        session = self._session_factory()
        try:
            repo = MembershipRepository(session)
            row = repo.get_membership(portfolio_id, business_id)
            if row is None:
                raise NotFoundError("membership not found")
            row.status = status
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.membership_status", "portfolio",
                    portfolio_id, "allow",
                    f"membership set to {status}", {"business_id": business_id})
        return membership_dict(row)

    def update_membership(self, principal: Principal, portfolio_id: str,
                          business_id: str, data: dict) -> dict:
        self._require_owner(principal, "portfolio.membership_update")
        session = self._session_factory()
        try:
            repo = MembershipRepository(session)
            row = repo.get_membership(portfolio_id, business_id)
            if row is None:
                raise NotFoundError("membership not found")
            if "strategic_priority" in data:
                priority = int(data["strategic_priority"])
                if not 0 <= priority <= 100:
                    raise ValidationError("strategic_priority must be 0..100")
                row.strategic_priority = priority
            if "group_labels" in data:
                row.group_labels = list(data["group_labels"] or [])
            if "notes" in data:
                row.notes = str(data["notes"] or "")
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        return membership_dict(row)

    def list_members(self, principal: Principal, portfolio_id: str) -> dict:
        self._require_portfolio_reader(principal, "portfolio.members")
        self._portfolio_or_404(portfolio_id)
        session = self._session_factory()
        try:
            rows = MembershipRepository(session).for_portfolio(portfolio_id)
            items = []
            for row in rows:
                item = membership_dict(row)
                item["business"] = self._business_summary(row.business_id)
                items.append(item)
        finally:
            session.close()
        return {"items": items, "total": len(items)}

    # ------------------------------------------------------- objectives
    def create_objective(self, principal: Principal, portfolio_id: str,
                         data: dict) -> dict:
        self._require_owner(principal, "portfolio.objective_create")
        self._portfolio_or_404(portfolio_id)
        horizon = str(data.get("horizon") or "90_DAY")
        if horizon not in C.OBJECTIVE_HORIZONS:
            raise ValidationError(f"unknown planning horizon: {horizon}")
        title = str(data.get("title") or "").strip()
        if not title:
            raise ValidationError("an objective requires a title")
        session = self._session_factory()
        try:
            row = ObjectiveRepository(session).add(PortfolioObjective(
                portfolio_id=portfolio_id, title=title[:300],
                description=str(data.get("description") or ""),
                horizon=horizon,
                targets=dict(data.get("targets") or {}),
                created_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.objective_created", "portfolio",
                    portfolio_id, "allow", "portfolio objective created",
                    {"objective_id": row.id})
        return objective_dict(row)

    def list_objectives(self, principal: Principal, portfolio_id: str) -> dict:
        self._require_portfolio_reader(principal, "portfolio.objectives")
        session = self._session_factory()
        try:
            rows, total = ObjectiveRepository(session).list(
                portfolio_id=portfolio_id)
            items = [objective_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": total}

    # ------------------------------------------------- business views
    def _business_summary(self, business_id: str) -> dict:
        """Registry view of one business: P-06 identity + P-08
        lifecycle reading + the derived §4 portfolio stage. Read
        live through the owning services — nothing is copied."""
        business = self._business_or_404(business_id)
        lifecycle = self._survival.lifecycle(business_id) \
            if self._survival is not None else {
                "p06_state": business["status"], "overlay_state": None}
        return {
            "business_id": business_id,
            "name": business["name"],
            "category": business["category"],
            "template": business.get("template_name")
                        or business.get("template_id"),
            "risk_classification": business.get("risk_classification"),
            "is_fixture": bool(business.get("is_fixture")),
            "p06_state": lifecycle["p06_state"],
            "p08_overlay_state": lifecycle.get("overlay_state"),
            "portfolio_stage": C.portfolio_stage(
                lifecycle["p06_state"], lifecycle.get("overlay_state")),
            "paused": bool(lifecycle.get("paused")),
        }

    def business_profile(self, principal: Principal,
                         business_id: str) -> dict:
        """§5 business profile: authoritative identity from P-06,
        lifecycle from P-06/P-08, assignments and relationships from
        P-13 — assembled per request, stored nowhere."""
        self._assert_business_read(principal, business_id)
        business = self._business_or_404(business_id)
        profile = self._business_summary(business_id)
        profile["business"] = business
        return profile

    def portfolio_overview(self, principal: Principal,
                           portfolio_id: str, currency: str = "INR") -> dict:
        """§18A portfolio overview: membership + stage counts from
        live P-06/P-08 readings. Financial figures are attached by
        the finance mixin; this view fabricates none."""
        self._require_portfolio_reader(principal, "portfolio.overview")
        portfolio = self._portfolio_or_404(portfolio_id)
        members = self.list_members(principal, portfolio_id)["items"]
        stages: dict[str, int] = {}
        at_risk = 0
        active = 0
        for item in members:
            if item["status"] == "REMOVED":
                continue
            summary = item["business"]
            stages[summary["portfolio_stage"]] = \
                stages.get(summary["portfolio_stage"], 0) + 1
            if summary["portfolio_stage"] == "AT_RISK":
                at_risk += 1
            if item["status"] == "ACTIVE":
                active += 1
        return {
            "portfolio": portfolio_dict(portfolio),
            "total_businesses": len([m for m in members
                                     if m["status"] != "REMOVED"]),
            "active_businesses": active,
            "businesses_at_risk": at_risk,
            "stage_counts": stages,
            "members": members,
            "survival_mode": bool(portfolio.survival_mode),
            "currency": currency,
        }
