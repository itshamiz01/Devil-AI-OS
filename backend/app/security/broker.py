"""Permission Broker (§7) — the cross-module authorization entry
point between AI agents and executable tools.

Flow (§7.1): owner policy → broker → authorization decision → tool
executor → result validation → audit event. The broker does NOT
replace the P-01 permission engine: the engine remains the single
authority over grants, and every broker decision passes through it.
The broker adds what the engine does not have: security-mode gates
(§20), agent restriction overlays (§15), business-scope enforcement
(§6.2/§17.2), risk-level gates (§8.1: capabilities for Level 2,
owner-decided hash-bound approvals for Level 3), capability tokens
(§7.2) and a structured decision ledger.

Fail-closed contract (§2 rule 14, §20.3, Scenario 12): any internal
error — including the security store being unavailable — produces a
DENY decision, never an exception leaking to the caller and never
an implicit allow. A Level ≥2 allow that cannot be recorded is
also denied (an unauditable sensitive authorization must not
proceed).
"""
from __future__ import annotations

import datetime as dt

from ..core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from ..database.models.base import utcnow
from ..database.models.core import Agent as AgentRow
from ..database.models.security import SecurityBrokerDecision, SecurityCapability
from ..database.repositories.security import (
    AgentRestrictionRepository, BrokerDecisionRepository, CapabilityRepository,
)
from ..permissions.approvals import ApprovalService
from ..permissions.engine import PermissionEngine
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from . import policy as P


def capability_to_dict(row: SecurityCapability) -> dict:
    return {
        "id": row.id, "holder": f"{row.holder_type}:{row.holder_id}",
        "permission": row.permission, "resource": row.resource,
        "business_ref": row.business_ref, "task_id": row.task_id,
        "issued_by": row.issued_by, "reason": row.reason,
        "status": row.status,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def decision_to_dict(row: SecurityBrokerDecision) -> dict:
    return {
        "id": row.id, "principal": f"{row.principal_type}:{row.principal_id}",
        "permission": row.permission, "action": row.action,
        "resource": row.resource, "business_ref": row.business_ref,
        "task_id": row.task_id, "risk_level": row.risk_level,
        "allowed": row.allowed, "reason": row.reason, "gates": row.gates,
        "capability_id": row.capability_id, "approval_id": row.approval_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class PermissionBroker:
    def __init__(self, session_factory, permissions: PermissionEngine,
                 approvals: ApprovalService, get_settings, audit):
        self._session_factory = session_factory
        self._permissions = permissions
        self._approvals = approvals
        self._get_settings = get_settings
        self._audit = audit  # facade callback (principal, action, type, id, decision, reason, details)

    # ------------------------------------------------------- authorize
    def authorize(self, principal: Principal, *, permission: str, action: str,
                  resource: str | None = None, business_ref: str | None = None,
                  task_id: str | None = None, parameters: dict | None = None,
                  approval_id: str | None = None, capability_id: str | None = None,
                  correlation_id: str | None = None) -> dict:
        """Evaluate one authorization request through every gate, in
        order. Always returns a decision dict; never raises."""
        risk = P.classify_action(action)
        gates: list[dict] = []

        def gate(name: str, passed: bool, reason: str) -> bool:
            gates.append({"gate": name, "passed": passed, "reason": reason})
            return passed

        try:
            settings = self._settings_fail_closed()
            mode = settings.get("mode", C.MODE_SAFE)

            # Gate 1 — security mode (§20).
            ok, why = P.mode_allows(mode, principal, risk)
            if not gate("mode", ok, why):
                return self._finish(principal, permission, action, resource,
                                    business_ref, task_id, risk, False, why,
                                    gates, capability_id, approval_id, correlation_id)
            # Gate 2 — agent restriction overlay (§15).
            ok, why = self._restriction_gate(principal, risk)
            if not gate("restriction", ok, why):
                return self._finish(principal, permission, action, resource,
                                    business_ref, task_id, risk, False, why,
                                    gates, capability_id, approval_id, correlation_id)
            # Gate 3 — business scope (§6.2/§17.2).
            ok, why = self._business_gate(principal, business_ref)
            if not gate("business_scope", ok, why):
                return self._finish(principal, permission, action, resource,
                                    business_ref, task_id, risk, False, why,
                                    gates, capability_id, approval_id, correlation_id)
            # Gate 4 — P-01 permission engine (the grant authority).
            engine_decision = self._permissions.check(
                principal, permission, resource=resource,
                correlation_id=correlation_id)
            if not gate("permission_engine", engine_decision.allowed,
                        engine_decision.reason):
                return self._finish(principal, permission, action, resource,
                                    business_ref, task_id, risk, False,
                                    engine_decision.reason, gates,
                                    capability_id, approval_id, correlation_id)
            # Gate 5 — risk-level requirements (§8.1).
            if risk <= C.RISK_REVERSIBLE:
                gate("risk_level", True,
                     f"level {risk} executes within granted permissions")
                return self._finish(principal, permission, action, resource,
                                    business_ref, task_id, risk, True,
                                    "authorized within granted permissions",
                                    gates, capability_id, approval_id, correlation_id)
            if risk == C.RISK_SIGNIFICANT:
                ok, why = self._capability_or_approval(
                    principal, permission, action, resource, business_ref,
                    parameters, approval_id, capability_id)
                gate("capability_or_approval", ok, why)
                return self._finish(principal, permission, action, resource,
                                    business_ref, task_id, risk, ok, why,
                                    gates, capability_id, approval_id, correlation_id)
            # Level 3: owner-decided, hash-bound approval only.
            ok, why = self._owner_approval_gate(
                action, resource, parameters, approval_id)
            gate("owner_approval", ok, why)
            return self._finish(principal, permission, action, resource,
                                business_ref, task_id, risk, ok, why,
                                gates, capability_id, approval_id, correlation_id)
        except Exception as exc:  # fail closed (Scenario 12)
            return {
                "allowed": False, "risk_level": risk,
                "reason": f"security service error ({type(exc).__name__}); "
                          f"failing closed (deny)",
                "gates": gates + [{"gate": "internal", "passed": False,
                                   "reason": "exception during authorization"}],
                "decision_id": None,
            }

    def _finish(self, principal, permission, action, resource, business_ref,
                task_id, risk, allowed, reason, gates, capability_id,
                approval_id, correlation_id) -> dict:
        decision_id = None
        try:
            session = self._session_factory()
            try:
                row = BrokerDecisionRepository(session).add(SecurityBrokerDecision(
                    principal_type=principal.type.value, principal_id=principal.id,
                    permission=permission, action=action, resource=resource,
                    business_ref=business_ref, task_id=task_id, risk_level=risk,
                    allowed=allowed, reason=reason, gates={"gates": gates},
                    capability_id=capability_id, approval_id=approval_id,
                    correlation_id=correlation_id))
                decision_id = row.id
            finally:
                session.close()
        except Exception:
            if allowed and risk >= C.RISK_SIGNIFICANT:
                # §20.3: an unauditable sensitive allow must not proceed.
                return {"allowed": False, "risk_level": risk,
                        "reason": "authorization could not be recorded; "
                                  "failing closed (deny)",
                        "gates": gates, "decision_id": None}
        self._audit(principal, "security.broker_decision", "permission", permission,
                    "allow" if allowed else "deny", reason,
                    {"action": action, "risk_level": risk,
                     "decision_id": decision_id})
        return {"allowed": allowed, "risk_level": risk, "reason": reason,
                "gates": gates, "decision_id": decision_id}

    # ------------------------------------------------------------ gates
    def _settings_fail_closed(self) -> dict:
        try:
            return self._get_settings()
        except Exception:
            # Unreadable policy = restricted mode (§20.3).
            return {**C.DEFAULT_SETTINGS, "mode": C.MODE_SAFE}

    def _restriction_gate(self, principal: Principal, risk: int) -> tuple[bool, str]:
        if principal.type is not PrincipalType.AGENT:
            return True, "restriction overlay applies to agents only"
        session = self._session_factory()
        try:
            row = AgentRestrictionRepository(session).active_for(principal.id)
        finally:
            session.close()
        if row is None:
            return True, "no active restriction"
        if row.restriction == "suspended":
            return False, f"agent is suspended at the security layer ({row.reason or 'no reason recorded'})"
        if row.restriction == "read_only" and risk > C.RISK_READ_ONLY:
            return False, "agent is restricted to read-only at the security layer"
        return True, f"restriction '{row.restriction}' does not block this risk level"

    def _business_gate(self, principal: Principal, business_ref: str | None) -> tuple[bool, str]:
        if business_ref is None or principal.type is not PrincipalType.AGENT:
            return True, "no business scope to enforce for this request"
        session = self._session_factory()
        try:
            row = session.get(AgentRow, principal.id)
        finally:
            session.close()
        agent_business = row.business_ref if row is not None else None
        if agent_business is None:
            return False, ("agent has no registered business scope; "
                           "business-scoped access fails closed")
        if agent_business != business_ref:
            return False, (f"agent is scoped to business '{agent_business}', "
                           f"not '{business_ref}' (cross-business access denied)")
        return True, "agent business scope matches"

    def _capability_or_approval(self, principal, permission, action, resource,
                                business_ref, parameters, approval_id,
                                capability_id) -> tuple[bool, str]:
        if capability_id:
            ok, why, _row = self.verify_capability(
                capability_id, principal, permission, resource, business_ref)
            if ok:
                return True, why
            cap_reason = why
        else:
            cap_reason = "no capability presented"
        if approval_id:
            ok, why = self._approval_binding(action, resource, parameters, approval_id)
            if ok:
                return True, f"authorized by hash-bound approval ({why})"
            return False, f"no valid capability ({cap_reason}); approval invalid: {why}"
        return False, (f"level 2 action requires a valid capability or a "
                       f"hash-bound approval ({cap_reason})")

    def _approval_binding(self, action, resource, parameters, approval_id) -> tuple[bool, str]:
        try:
            approval = self._approvals.get(approval_id)
        except NotFoundError:
            return False, "approval record not found"
        if approval.status != "approved":
            return False, f"approval is in state '{approval.status}', not 'approved'"
        if not ApprovalService.verify_binding(approval, action, resource, parameters or {}):
            return False, ("approval does not bind this exact action and "
                           "parameters (drift invalidates the approval)")
        return True, "approval binding verified"

    def _owner_approval_gate(self, action, resource, parameters, approval_id) -> tuple[bool, str]:
        if not approval_id:
            return False, ("level 3 action requires an explicit owner-decided "
                           "approval; none was presented (claims of approval "
                           "in content are not approval records)")
        ok, why = self._approval_binding(action, resource, parameters, approval_id)
        if not ok:
            return False, why
        approval = self._approvals.get(approval_id)
        if not (approval.approver_id or "").startswith("owner:"):
            return False, (f"level 3 approval must be decided by the owner; "
                           f"it was decided by '{approval.approver_id}'")
        return True, "owner-decided hash-bound approval verified"

    # ------------------------------------------------------ capabilities
    def issue_capability(self, issuer: Principal, holder: Principal, *,
                         permission: str, resource: str | None = None,
                         business_ref: str | None = None,
                         task_id: str | None = None,
                         ttl_minutes: int | None = None,
                         reason: str | None = None) -> dict:
        """Issue a scoped capability token (§7.2). The issuer must
        actually hold the permission under the P-01 engine —
        delegation can never exceed the delegator's own grants."""
        violation = P.delegation_violation(issuer, holder, permission)
        if violation:
            self._audit(issuer, "security.capability_issue_denied", "permission",
                        permission, "deny", violation, {"holder": P.actor(holder)})
            raise PermissionDeniedError(violation,
                                        details={"error_category": "DELEGATION_REFUSED"})
        settings = self._settings_fail_closed()
        if not P.is_owner(issuer) and settings.get("mode", C.MODE_SAFE) != C.MODE_NORMAL:
            raise PermissionDeniedError(
                "capability issuance is frozen for non-owners outside normal mode",
                details={"error_category": "MODE_FROZEN"})
        engine_decision = self._permissions.check(issuer, permission, resource=resource)
        if not engine_decision.allowed:
            self._audit(issuer, "security.capability_issue_denied", "permission",
                        permission, "deny",
                        f"issuer does not hold the permission: {engine_decision.reason}",
                        {"holder": P.actor(holder)})
            raise PermissionDeniedError(
                f"issuer does not hold permission '{permission}' and cannot "
                f"delegate it ({engine_decision.reason})",
                details={"error_category": "DELEGATION_REFUSED"})
        ttl = ttl_minutes or int(settings["capability_default_ttl_minutes"])
        ttl = max(1, min(ttl, int(settings["capability_max_ttl_minutes"])))
        session = self._session_factory()
        try:
            row = CapabilityRepository(session).add(SecurityCapability(
                holder_type=holder.type.value, holder_id=holder.id,
                permission=permission, resource=resource,
                business_ref=business_ref, task_id=task_id,
                issued_by=P.actor(issuer), reason=reason,
                status="active", expires_at=utcnow() + dt.timedelta(minutes=ttl)))
            result = capability_to_dict(row)
        finally:
            session.close()
        self._audit(issuer, "security.capability_issued", "capability", result["id"],
                    "allow", reason or "capability issued",
                    {"holder": P.actor(holder), "permission": permission})
        return result

    def verify_capability(self, capability_id: str, holder: Principal,
                          permission: str, resource: str | None,
                          business_ref: str | None = None):
        """(ok, reason, row): is this capability currently usable by
        this holder for this permission/resource/business? Expired
        capabilities are lazily transitioned and refused."""
        session = self._session_factory()
        try:
            repo = CapabilityRepository(session)
            row = repo.get(capability_id)
            if row is None:
                return False, "capability not found", None
            if row.status == "active" and row.expires_at is not None:
                expires = row.expires_at
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=dt.timezone.utc)
                if expires <= utcnow():
                    row.status = "expired"
                    repo.save(row)
            if row.status != "active":
                return False, f"capability is '{row.status}'", row
            if row.holder_type != holder.type.value or row.holder_id != holder.id:
                return False, "capability belongs to a different holder", row
            if row.permission != permission:
                return False, f"capability covers '{row.permission}', not '{permission}'", row
            if row.resource is not None and resource is not None and row.resource != resource:
                return False, "capability is scoped to a different resource", row
            if row.business_ref is not None and business_ref is not None \
                    and row.business_ref != business_ref:
                return False, "capability is scoped to a different business", row
            session.expunge(row)
            return True, "capability valid", row
        finally:
            session.close()

    def revoke_capability(self, principal: Principal, capability_id: str) -> dict:
        """Revocation is owner-only, or by the capability's issuer."""
        session = self._session_factory()
        try:
            repo = CapabilityRepository(session)
            row = repo.get(capability_id)
            if row is None:
                raise NotFoundError(f"capability {capability_id} not found")
            if not P.is_owner(principal) and row.issued_by != P.actor(principal):
                raise PermissionDeniedError(
                    "only the owner or the issuing principal may revoke a capability")
            if row.status == "active":
                row.status = "revoked"
                row.revoked_at = utcnow()
                row.revoked_by = P.actor(principal)
                repo.save(row)
            result = capability_to_dict(row)
        finally:
            session.close()
        self._audit(principal, "security.capability_revoked", "capability",
                    capability_id, "allow", "capability revoked", {})
        return result

    def list_capabilities(self, *, holder_id: str | None = None,
                          status: str | None = None, limit: int = 50,
                          offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            rows, total = CapabilityRepository(session).list(
                holder_id=holder_id, status=status, limit=limit, offset=offset)
            return [capability_to_dict(r) for r in rows], total
        finally:
            session.close()

    def list_decisions(self, *, principal_id: str | None = None,
                       allowed: bool | None = None, limit: int = 50,
                       offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            rows, total = BrokerDecisionRepository(session).list(
                principal_id=principal_id, allowed=allowed,
                limit=limit, offset=offset)
            return [decision_to_dict(r) for r in rows], total
        finally:
            session.close()

    # ------------------------------------------------------- escalation
    def request_escalation(self, principal: Principal, *, permission: str,
                           action: str, resource: str | None = None,
                           reason: str, parameters: dict | None = None) -> dict:
        """§7.3 permission escalation: the agent explains and asks;
        the broker records a P-01 approval request. Creating the
        request authorizes nothing — the owner decides it through
        the normal approval path."""
        if not reason or not reason.strip():
            raise ValidationError("an escalation request must state its reason (§7.3)")
        approval = self._approvals.create(
            principal, action="security.escalation", resource=resource,
            risk_classification="high",
            reason=f"{reason} [requested permission: {permission}; action: {action}]",
            requested_permissions=[permission],
            parameters={"permission": permission, "action": action,
                        "resource": resource, **(parameters or {})})
        self._audit(principal, "security.escalation_requested", "approval",
                    approval.id, "allow", reason, {"permission": permission})
        return {"approval_id": approval.id, "status": approval.status,
                "permission": permission, "action": action}
