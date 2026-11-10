"""Capability registry + per-agent grant service (§8).

Design (audit §5): the grant LEDGER is ``agent_permissions`` (approval
reference, expiry, revocation, status). The ENFORCEMENT artefact is a
mirrored rule in the P-01 ``permissions`` table, so every capability check
anywhere in the system goes through the one deny-by-default
PermissionEngine:

- grant  -> ledger row (status=granted) + engine allow rule
            (principal_type='agent', permission=<capability name>)
- revoke -> ledger row (status=revoked) + allow removed + explicit deny
            rule written (an explicit deny always wins in the engine)
- expiry -> ledger row (status=expired) + allow removed

An agent therefore holds ZERO factory capabilities until a grant exists:
capability names are deliberately absent from the P-01 agent role
defaults. There is no inheritance: a child agent's ledger starts empty
regardless of its parent's grants, and grants name exactly one agent id.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select

from ..core.exceptions import NotFoundError, PermissionDeniedError
from ..database.models.agents import AgentCapability, AgentPermission
from ..database.models.base import as_utc, utcnow
from ..database.models.core import Permission as PermissionRow
from ..database.repositories.agents import AgentPermissionRepository, CapabilityRepository
from ..permissions.approvals import ApprovalService
from ..permissions.engine import PermissionEngine
from ..permissions.models import Principal, PrincipalType
from .errors import CapabilityProhibitedError, CapabilityUnsupportedError

GRANT_ACTION = "agent_factory.grant_capability"


def agent_principal(agent_id: str) -> Principal:
    return Principal(PrincipalType.AGENT, agent_id)


class CapabilityService:
    def __init__(self, session_factory, permissions: PermissionEngine,
                 approvals: ApprovalService):
        self._session_factory = session_factory
        self._permissions = permissions
        self._approvals = approvals

    # ------------------------------------------------------------- catalogue
    def list_catalogue(self) -> list[AgentCapability]:
        session = self._session_factory()
        try:
            return CapabilityRepository(session).list()
        finally:
            session.close()

    def get_capability(self, name: str) -> AgentCapability:
        session = self._session_factory()
        try:
            cap = CapabilityRepository(session).get_by_name(name)
            if cap is None:
                raise NotFoundError(f"capability '{name}' is not in the catalogue")
            return cap
        finally:
            session.close()

    # ---------------------------------------------------------------- checks
    def has_capability(self, agent_id: str, capability_name: str) -> bool:
        """The authoritative check: live ledger grant AND the P-01
        permission engine allowing the capability for this agent."""
        session = self._session_factory()
        try:
            cap = CapabilityRepository(session).get_by_name(capability_name)
            if cap is None:
                return False
            grant = AgentPermissionRepository(session).active_grant(agent_id, cap.id)
            if grant is None or self._expired(grant):
                return False
        finally:
            session.close()
        decision = self._permissions.check(
            agent_principal(agent_id), capability_name, audit=True)
        return decision.allowed

    def granted_capability_names(self, agent_id: str) -> list[str]:
        session = self._session_factory()
        try:
            repo = AgentPermissionRepository(session)
            caps = {c.id: c.name for c in CapabilityRepository(session).list()}
            return sorted(
                caps[g.capability_id] for g in repo.for_agent(agent_id, status="granted")
                if not self._expired(g) and g.capability_id in caps)
        finally:
            session.close()

    def grants_for_agent(self, agent_id: str) -> list[AgentPermission]:
        session = self._session_factory()
        try:
            return AgentPermissionRepository(session).for_agent(agent_id)
        finally:
            session.close()

    @staticmethod
    def _expired(grant: AgentPermission) -> bool:
        if grant.expires_at is None:
            return False
        # P-14 Stage B (DEF-D2): standardised naive→aware shim.
        return as_utc(grant.expires_at) <= utcnow()

    # ----------------------------------------------------------------- grant
    def grant(self, agent_id: str, capability_name: str, *, granted_by: Principal,
              approval_reference: str | None = None, scope: str | None = None,
              expires_at: dt.datetime | None = None) -> AgentPermission:
        """Write a grant (ledger + engine mirror). Callers are responsible
        for the policy decision (level checks / approvals) BEFORE calling;
        this method still refuses prohibited and unsupported capabilities
        as a structural backstop."""
        session = self._session_factory()
        try:
            cap_repo = CapabilityRepository(session)
            cap = cap_repo.get_by_name(capability_name)
            if cap is None:
                raise NotFoundError(f"capability '{capability_name}' is not in the catalogue")
            if cap.approval_level >= 3 or not cap.enabled:
                raise CapabilityProhibitedError(
                    f"capability '{capability_name}' is prohibited (approval level 3) "
                    "and can never be granted",
                    details={"error_category": "CAPABILITY_PROHIBITED"})
            if not cap.supported:
                raise CapabilityUnsupportedError(
                    f"capability '{capability_name}' is catalogued but not backed by "
                    "any module in this build; it cannot be granted",
                    details={"error_category": "CAPABILITY_UNSUPPORTED"})
            grants = AgentPermissionRepository(session)
            existing = grants.active_grant(agent_id, cap.id)
            if existing is not None and not self._expired(existing):
                return existing
            grant = AgentPermission(
                agent_id=agent_id, capability_id=cap.id, scope=scope,
                approval_level=cap.approval_level,
                approval_reference=approval_reference,
                granted_by_type=granted_by.type.value, granted_by_id=granted_by.id,
                granted_at=utcnow(), expires_at=expires_at, status="granted")
            grants.add(grant)
            self._mirror_allow(session, agent_id, capability_name, scope)
            session.commit()
            return grant
        finally:
            session.close()

    def revoke(self, agent_id: str, capability_name: str, *, revoked_by: Principal) -> AgentPermission:
        session = self._session_factory()
        try:
            cap = CapabilityRepository(session).get_by_name(capability_name)
            if cap is None:
                raise NotFoundError(f"capability '{capability_name}' is not in the catalogue")
            grants = AgentPermissionRepository(session)
            grant = grants.active_grant(agent_id, cap.id)
            if grant is None:
                raise NotFoundError(
                    f"agent {agent_id} holds no active grant for '{capability_name}'")
            grant.status = "revoked"
            grant.revoked_at = utcnow()
            grants.save(grant)
            self._mirror_deny(session, agent_id, capability_name, grant.scope)
            session.commit()
            return grant
        finally:
            session.close()

    def record_denial(self, agent_id: str, capability_name: str, *, reason: str) -> None:
        """Persist a refused grant decision in the ledger (status=denied)
        so the refusal itself is part of the agent's record."""
        session = self._session_factory()
        try:
            cap = CapabilityRepository(session).get_by_name(capability_name)
            if cap is None:
                return
            AgentPermissionRepository(session).add(AgentPermission(
                agent_id=agent_id, capability_id=cap.id,
                approval_level=cap.approval_level, status="denied",
                granted_at=None))
        finally:
            session.close()

    def sweep_expired(self) -> int:
        session = self._session_factory()
        try:
            repo = AgentPermissionRepository(session)
            count = 0
            for grant in list(session.scalars(
                    select(AgentPermission).where(AgentPermission.status == "granted")).all()):
                if self._expired(grant):
                    grant.status = "expired"
                    repo.save(grant)
                    self._remove_allow(session, grant.agent_id,
                                       self._capability_name(session, grant.capability_id),
                                       grant.scope)
                    count += 1
            session.commit()
            return count
        finally:
            session.close()

    def _capability_name(self, session, capability_id: str) -> str | None:
        cap = CapabilityRepository(session).get(capability_id)
        return cap.name if cap else None

    # ---------------------------------------------------- engine mirror rows
    def _mirror_allow(self, session, agent_id: str, capability_name: str,
                      scope: str | None) -> None:
        # A fresh grant supersedes any earlier deny mirror for the same
        # (agent, capability, scope) identity.
        session.execute(delete(PermissionRow).where(
            PermissionRow.principal_type == "agent",
            PermissionRow.principal_id == agent_id,
            PermissionRow.permission == capability_name,
            PermissionRow.resource.is_(scope) if scope is None
            else PermissionRow.resource == scope))
        session.add(PermissionRow(
            principal_type="agent", principal_id=agent_id,
            permission=capability_name, effect="allow", resource=scope))
        session.flush()

    def _mirror_deny(self, session, agent_id: str, capability_name: str,
                     scope: str | None) -> None:
        self._remove_allow(session, agent_id, capability_name, scope)
        session.add(PermissionRow(
            principal_type="agent", principal_id=agent_id,
            permission=capability_name, effect="deny", resource=scope))
        session.flush()

    def _remove_allow(self, session, agent_id: str, capability_name: str | None,
                      scope: str | None) -> None:
        if capability_name is None:
            return
        session.execute(delete(PermissionRow).where(
            PermissionRow.principal_type == "agent",
            PermissionRow.principal_id == agent_id,
            PermissionRow.permission == capability_name,
            PermissionRow.effect == "allow",
            PermissionRow.resource.is_(scope) if scope is None
            else PermissionRow.resource == scope))
        session.flush()

    # ------------------------------------------------- approval-bound request
    def create_grant_approval(self, *, requester: Principal, agent_id: str,
                              capability_name: str, scope: str | None,
                              reason: str | None):
        """Create the hash-bound P-01 approval for a Level-2 grant. The
        agent remains WITHOUT the capability until the owner approves AND
        the factory applies the approval (verify_binding)."""
        return self._approvals.create(
            requester, action=GRANT_ACTION, resource=agent_id,
            risk_classification="high", reason=reason,
            requested_permissions=[capability_name],
            parameters={"agent_id": agent_id, "capability": capability_name,
                        "scope": scope})

    def apply_grant_approval(self, *, approver: Principal, agent_id: str,
                               approval_id: str, approve: bool) -> dict:
        if approver.type is not PrincipalType.OWNER:
            raise PermissionDeniedError(
                "only the owner may decide capability grant approvals",
                details={"error_category": "CAPABILITY_NOT_AUTHORIZED"})
        approval = self._approvals.get(approval_id)
        params = approval.parameters or {}
        if approval.action != GRANT_ACTION or params.get("agent_id") != agent_id:
            raise PermissionDeniedError(
                "approval does not bind to this agent capability grant",
                details={"error_category": "CAPABILITY_NOT_AUTHORIZED"})
        decided = self._approvals.decide(approval_id, approver, approve)
        capability_name = params.get("capability")
        if not approve:
            self.record_denial(agent_id, capability_name,
                               reason="owner rejected the grant request")
            return {"status": "rejected", "approval_id": approval_id,
                    "capability": capability_name}
        if not ApprovalService.verify_binding(
                decided, GRANT_ACTION, agent_id,
                {"agent_id": agent_id, "capability": capability_name,
                 "scope": params.get("scope")}):
            raise PermissionDeniedError(
                "approval parameters no longer match the grant request (hash binding failed)",
                details={"error_category": "CAPABILITY_NOT_AUTHORIZED"})
        grant = self.grant(agent_id, capability_name, granted_by=approver,
                           approval_reference=approval_id,
                           scope=params.get("scope"))
        return {"status": "granted", "approval_id": approval_id,
                "capability": capability_name, "grant_id": grant.id}
