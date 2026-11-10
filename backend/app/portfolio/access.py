"""Access mixin (§8/§20): cross-business permission grants and
scoped agent assignments, plus the two checked access surfaces.

This is the isolation core of P-13:

* a cross-business grant names ONE agent, ONE source business (the
  data owner), a target business context, an explicit category list
  and a mandatory expiry. Categories come from a closed grantable
  set; credentials, customer records, financial records, business
  memory, secrets and platform accounts are NEVER grantable —
  naming one is a validation error, not a silent no-op;
* agent assignments are scoped (one business, or a portfolio with
  aggregate-only categories), carry allowed tools and an expiry,
  and are revocable with immediate effect;
* ``check_agent_access`` / ``check_service_access`` are the only
  agent-facing read surfaces. They fail closed, and every denial is
  written to the P-01 audit log as an isolation event.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.portfolio import (
    CrossBusinessPermission, PortfolioAgentAssignment,
)
from ..database.repositories.portfolio import (
    AgentAssignmentRepository, GrantRepository, MembershipRepository,
    ServiceAccessRepository,
)
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from .constants import actor_of


def grant_dict(row: CrossBusinessPermission) -> dict:
    return {
        "id": row.id, "portfolio_id": row.portfolio_id,
        "grantee_agent_id": row.grantee_agent_id,
        "business_id": row.source_business_id,
        "source_business_id": row.source_business_id,
        "target_business_id": row.target_business_id,
        "categories": row.authorized_data,
        "authorized_data": row.authorized_data,
        "permitted_actions": row.permitted_actions,
        "purpose": row.purpose, "rationale": row.purpose,
        "status": row.status, "granted_by": row.granted_by,
        "expires_at": row.expires_at.isoformat()
        if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def assignment_dict(row: PortfolioAgentAssignment) -> dict:
    return {
        "id": row.id, "agent_id": row.agent_id,
        "scope_type": row.scope_type, "business_id": row.business_id,
        "portfolio_id": row.portfolio_id,
        "categories": row.allowed_data, "allowed_data": row.allowed_data,
        "allowed_tools": row.allowed_tools,
        "budget_ref": (row.budget_scope or {}).get("budget_ref"),
        "budget_scope": row.budget_scope,
        "status": row.status, "assigned_by": row.assigned_by,
        "expires_at": row.expires_at.isoformat()
        if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _validate_categories(categories, allowed: set[str], context: str) -> list[str]:
    cats = [str(c) for c in (categories or [])]
    if not cats:
        raise ValidationError(f"{context}: at least one data category "
                              "is required (access is never implicit)")
    for cat in cats:
        if cat in C.NEVER_GRANTABLE:
            raise ValidationError(
                f"category {cat!r} can never be granted across "
                "businesses: credentials, customer records, financial "
                "records, business memory, secrets and platform "
                "accounts never leave their business (§20)")
        if cat not in allowed:
            raise ValidationError(
                f"category {cat!r} is not grantable in {context}; "
                f"allowed: {sorted(allowed)}")
    return cats


def _parse_expiry(expires_at) -> datetime:
    """Expiry is mandatory and must be in the future (§8/§20)."""
    if not expires_at:
        raise ValidationError(
            "expires_at is required: cross-business access is always "
            "time-limited (§8/§20)")
    if isinstance(expires_at, datetime):
        moment = expires_at
    else:
        try:
            moment = datetime.fromisoformat(str(expires_at))
        except ValueError as exc:
            raise ValidationError(
                "expires_at must be an ISO timestamp") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    if moment <= datetime.now(timezone.utc):
        raise ValidationError("expires_at must be in the future")
    return moment


def _validate_expiry(expires_at) -> str:
    return _parse_expiry(expires_at).isoformat()


def _expired(expires_at) -> bool:
    if expires_at is None:
        return True
    if isinstance(expires_at, datetime):
        moment = expires_at
    else:
        try:
            moment = datetime.fromisoformat(str(expires_at))
        except ValueError:
            return True
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment <= datetime.now(timezone.utc)


class AccessMixin:
    # ---------------------------------------------------------- grants
    def grant_access(self, principal: Principal, data: dict) -> dict:
        self._require_owner(principal, "portfolio.grant_access")
        agent_id = data.get("grantee_agent_id")
        business_id = data.get("business_id") or \
            data.get("source_business_id")
        portfolio_id = data.get("portfolio_id")
        if not agent_id or not business_id:
            raise ValidationError(
                "grantee_agent_id and business_id are required: a "
                "grant is scoped to one agent and one business")
        if not portfolio_id:
            raise ValidationError(
                "portfolio_id is required: cross-business grants are "
                "issued within a portfolio's governance context")
        self._portfolio_or_404(portfolio_id)
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            from ..database.models.core import Agent as AgentRow
            agent = session.get(AgentRow, agent_id)
            if agent is None:
                raise ValidationError(f"agent {agent_id} is not registered")
            categories = _validate_categories(
                data.get("categories") or data.get("authorized_data"),
                C.GRANTABLE_CATEGORIES, "grant")
            expires_at = _parse_expiry(data.get("expires_at"))
            rationale = str(data.get("rationale") or "").strip()
            if not rationale:
                raise ValidationError(
                    "a rationale is required for cross-business access")
            target = data.get("target_business_id") or \
                agent.business_ref or business_id
            row = GrantRepository(session).add(CrossBusinessPermission(
                portfolio_id=portfolio_id,
                source_business_id=business_id,
                target_business_id=target,
                grantee_agent_id=agent_id,
                purpose=str(data.get("purpose") or rationale),
                authorized_data=categories,
                permitted_actions=list(
                    data.get("permitted_actions") or ["read"]),
                expires_at=expires_at,
                granted_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.access_granted", "business",
                    business_id, "allow",
                    "cross-business access granted (scoped, expiring)",
                    {"agent_id": agent_id, "categories": categories,
                     "expires_at": expires_at.isoformat()})
        return grant_dict(row)

    def revoke_grant(self, principal: Principal, grant_id: str) -> dict:
        self._require_owner(principal, "portfolio.grant_revoke")
        session = self._session_factory()
        try:
            repo = GrantRepository(session)
            row = repo.get(grant_id)
            if row is None:
                raise NotFoundError(f"grant {grant_id} not found")
            row.status = "REVOKED"
            row.revoked_by = actor_of(principal)
            from ..database.models.base import utcnow
            row.revoked_at = utcnow().isoformat()
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.access_revoked", "business",
                    row.source_business_id, "allow",
                    "cross-business grant revoked; access ends "
                    "immediately", {"grant_id": grant_id})
        return grant_dict(row)

    def list_grants(self, principal: Principal, *, agent_id: str | None = None,
                    business_id: str | None = None) -> dict:
        self._require_portfolio_reader(principal, "portfolio.grants")
        session = self._session_factory()
        try:
            rows, _t = GrantRepository(session).list(
                limit=200, grantee_agent_id=agent_id,
                source_business_id=business_id)
            items = [grant_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": len(items)}

    # ----------------------------------------------------- assignments
    def assign_agent(self, principal: Principal, data: dict) -> dict:
        self._require_owner(principal, "portfolio.agent_assign")
        agent_id = data.get("agent_id")
        scope_type = str(data.get("scope_type") or "")
        if scope_type not in ("BUSINESS", "PORTFOLIO"):
            raise ValidationError(
                "scope_type must be BUSINESS or PORTFOLIO — there is "
                "no unrestricted portfolio scope (§8)")
        business_id = data.get("business_id")
        portfolio_id = data.get("portfolio_id")
        if not portfolio_id:
            raise ValidationError(
                "portfolio_id is required: assignments are issued "
                "within a portfolio's governance context")
        self._portfolio_or_404(portfolio_id)
        if scope_type == "BUSINESS":
            if not business_id:
                raise ValidationError(
                    "a BUSINESS-scope assignment requires business_id")
            self._business_or_404(business_id)
            allowed = C.GRANTABLE_CATEGORIES
        else:
            allowed = C.PORTFOLIO_SCOPE_CATEGORIES
        session = self._session_factory()
        try:
            from ..database.models.core import Agent as AgentRow
            if session.get(AgentRow, agent_id) is None:
                raise ValidationError(f"agent {agent_id} is not registered")
            categories = _validate_categories(
                data.get("categories") or data.get("allowed_data"),
                allowed, f"{scope_type.lower()}-scope assignment")
            expires_at = _parse_expiry(data.get("expires_at"))
            budget_scope = dict(data.get("budget_scope") or {})
            if data.get("budget_ref"):
                budget_scope["budget_ref"] = data["budget_ref"]
            row = AgentAssignmentRepository(session).add(
                PortfolioAgentAssignment(
                    agent_id=agent_id, scope_type=scope_type,
                    portfolio_id=portfolio_id,
                    business_id=business_id if scope_type == "BUSINESS"
                    else None,
                    allowed_data=categories,
                    allowed_tools=list(data.get("allowed_tools") or []),
                    required_capabilities=list(
                        data.get("required_capabilities") or []),
                    budget_scope=budget_scope,
                    expires_at=expires_at,
                    assigned_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.agent_assigned", "agent",
                    agent_id, "allow",
                    f"agent assigned with {scope_type} scope",
                    {"categories": categories,
                     "expires_at": expires_at.isoformat()})
        return assignment_dict(row)

    def revoke_assignment(self, principal: Principal,
                          assignment_id: str) -> dict:
        self._require_owner(principal, "portfolio.agent_revoke")
        session = self._session_factory()
        try:
            repo = AgentAssignmentRepository(session)
            row = repo.get(assignment_id)
            if row is None:
                raise NotFoundError(f"assignment {assignment_id} not found")
            row.status = "REVOKED"
            row.revoked_by = actor_of(principal)
            from ..database.models.base import utcnow
            row.revoked_at = utcnow().isoformat()
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.agent_assignment_revoked",
                    "agent", row.agent_id, "allow",
                    "agent assignment revoked; scoped access ends "
                    "immediately", {"assignment_id": assignment_id})
        return assignment_dict(row)

    def list_assignments(self, principal: Principal, *,
                         agent_id: str | None = None) -> dict:
        self._require_portfolio_reader(principal, "portfolio.assignments")
        session = self._session_factory()
        try:
            rows, _t = AgentAssignmentRepository(session).list(
                limit=200, agent_id=agent_id)
            items = [assignment_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": len(items)}

    # ------------------------------------------- checked agent surfaces
    def check_agent_access(self, principal: Principal, *,
                           business_id: str, category: str) -> dict:
        """The §20 checked surface. Fail-closed; denials audited."""
        def deny(reason: str) -> dict:
            self._audit(principal, "portfolio.isolation_violation",
                        "business", business_id, "deny", reason,
                        {"category": category,
                         "principal": actor_of(principal)})
            return {"allowed": False, "business_id": business_id,
                    "category": category, "reason": reason,
                    "via": None}

        if principal.type != PrincipalType.AGENT:
            return deny("only agent principals use the checked "
                        "cross-business surface")
        if category in C.NEVER_GRANTABLE:
            return deny(f"category {category!r} never crosses business "
                        "boundaries (§20)")
        if category not in C.GRANTABLE_CATEGORIES:
            return deny(f"unknown data category {category!r}")
        session = self._session_factory()
        try:
            from ..database.models.core import Agent as AgentRow
            agent = session.get(AgentRow, principal.id)
            home = agent.business_ref if agent is not None else None
            if home is not None and home == business_id:
                return {"allowed": True, "business_id": business_id,
                        "category": category,
                        "reason": "the agent's own registered business",
                        "via": "home_business"}
            grants = GrantRepository(session)
            candidates, _t = grants.list(
                limit=200, grantee_agent_id=principal.id,
                source_business_id=business_id, status="ACTIVE")
            for grant in candidates:
                if grant.target_business_id not in (home, business_id):
                    continue
                if category in (grant.authorized_data or []) and \
                        not _expired(grant.expires_at):
                    return {"allowed": True, "business_id": business_id,
                            "category": category,
                            "reason": "active scoped cross-business grant",
                            "via": f"grant:{grant.id}"}
            assignments = AgentAssignmentRepository(session)
            for row in assignments.active_for_agent(principal.id):
                if _expired(row.expires_at):
                    continue
                if category not in (row.allowed_data or []):
                    continue
                if row.scope_type == "BUSINESS" and \
                        row.business_id == business_id:
                    return {"allowed": True, "business_id": business_id,
                            "category": category,
                            "reason": "active business-scope assignment",
                            "via": f"assignment:{row.id}"}
                if row.scope_type == "PORTFOLIO" and row.portfolio_id:
                    member = MembershipRepository(session).get_membership(
                        row.portfolio_id, business_id)
                    if member is not None and member.status == "ACTIVE":
                        return {"allowed": True,
                                "business_id": business_id,
                                "category": category,
                                "reason": "active portfolio-scope "
                                          "assignment (aggregate "
                                          "categories only)",
                                "via": f"assignment:{row.id}"}
        finally:
            session.close()
        return deny("no active grant or scoped assignment covers this "
                    "agent, business and category")

    def check_service_access(self, principal: Principal, *,
                             service_id: str) -> dict:
        """An agent may use a shared service only through its home
        business's ACTIVE access record (§9/§20)."""
        def deny(reason: str) -> dict:
            self._audit(principal, "portfolio.isolation_violation",
                        "shared_service", service_id, "deny", reason,
                        {"principal": actor_of(principal)})
            return {"allowed": False, "service_id": service_id,
                    "reason": reason}

        if principal.type == PrincipalType.OWNER:
            return {"allowed": True, "service_id": service_id,
                    "reason": "owner"}
        if principal.type != PrincipalType.AGENT:
            return deny("principal type cannot use shared services")
        session = self._session_factory()
        try:
            from ..database.models.core import Agent as AgentRow
            agent = session.get(AgentRow, principal.id)
            if agent is None or not agent.business_ref:
                return deny("agent has no registered home business")
            access = ServiceAccessRepository(session).get_access(
                service_id, agent.business_ref)
            if access is not None and access.status == "ACTIVE":
                return {"allowed": True, "service_id": service_id,
                        "business_id": agent.business_ref,
                        "reason": "home business holds ACTIVE service "
                                  "access"}
            return deny("the agent's business holds no ACTIVE access "
                        "to this shared service")
        finally:
            session.close()
