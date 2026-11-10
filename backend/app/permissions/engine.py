"""Deny-by-default permission engine with audit logging (P-01 §9.3).

Evaluation order:
1. Explicit DB deny for this principal (specific id, then role-level) -> DENY
2. Explicit DB allow for this principal (resource must match when set) -> ALLOW
3. Role default policy -> ALLOW when the permission is in the role set
4. Otherwise -> DENY (including when permission data is unavailable)

Every check is written to ``audit_events``. Grants for permissions in
``APPROVAL_REQUIRED_PERMISSIONS`` additionally flag ``requires_approval`` —
a grant alone never executes such an operation.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..database.models.base import utcnow
from ..database.models.core import AuditEvent
from ..database.repositories.core import AuditRepository, PermissionRepository
from .models import AuthorizationDecision, Principal
from .policies import APPROVAL_REQUIRED_PERMISSIONS, ROLE_DEFAULTS


class PermissionEngine:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def check(self, principal: Principal, permission: str,
              resource: str | None = None, correlation_id: str | None = None,
              audit: bool = True) -> AuthorizationDecision:
        session: Session = self._session_factory()
        try:
            try:
                rules = PermissionRepository(session).rules_for(principal.type.value, principal.id)
            except Exception:
                decision = AuthorizationDecision(
                    allowed=False, reason="permission data unavailable; failing safely (deny)")
                self._audit(session, principal, permission, resource, decision, correlation_id)
                return decision

            # 1. explicit denies (principal-specific beats role-level, both deny)
            for rule in rules:
                if rule.permission == permission and rule.effect == "deny" \
                        and (rule.resource is None or rule.resource == resource):
                    decision = AuthorizationDecision(
                        allowed=False,
                        reason=f"explicit deny rule #{rule.id}",
                        matched_rule=f"db-deny:{rule.id}")
                    self._audit(session, principal, permission, resource, decision, correlation_id)
                    return decision
            # 2. explicit allows
            for rule in rules:
                if rule.permission == permission and rule.effect == "allow" \
                        and (rule.resource is None or rule.resource == resource):
                    decision = self._allow(f"explicit allow rule #{rule.id}", f"db-allow:{rule.id}", permission)
                    self._audit(session, principal, permission, resource, decision, correlation_id)
                    return decision
            # 3. role defaults
            if permission in ROLE_DEFAULTS.get(principal.type.value, set()):
                decision = self._allow("role default policy", f"role:{principal.type.value}", permission)
                self._audit(session, principal, permission, resource, decision, correlation_id)
                return decision
            # 4. deny by default
            decision = AuthorizationDecision(
                allowed=False, reason="not granted by any policy (deny-by-default)")
            self._audit(session, principal, permission, resource, decision, correlation_id)
            return decision
        finally:
            session.close()

    @staticmethod
    def _allow(reason: str, matched: str, permission: str) -> AuthorizationDecision:
        return AuthorizationDecision(
            allowed=True, reason=reason, matched_rule=matched,
            requires_approval=permission in APPROVAL_REQUIRED_PERMISSIONS)

    @staticmethod
    def _audit(session: Session, principal: Principal, permission: str, resource: str | None,
               decision: AuthorizationDecision, correlation_id: str | None) -> None:
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value, actor_id=principal.id,
                action="permission.check", target_type="permission", target_id=permission,
                decision="allow" if decision.allowed else "deny",
                reason=decision.reason, correlation_id=correlation_id,
                details={"resource": resource, "matched_rule": decision.matched_rule,
                         "requires_approval": decision.requires_approval},
                created_at=utcnow(),
            ))
        except Exception:
            session.rollback()

    def require(self, principal: Principal, permission: str, resource: str | None = None,
                correlation_id: str | None = None) -> AuthorizationDecision:
        from ..core.exceptions import PermissionDeniedError

        decision = self.check(principal, permission, resource, correlation_id)
        if not decision.allowed:
            raise PermissionDeniedError(
                f"principal {principal.type.value}:{principal.id} lacks permission '{permission}'",
                details={"reason": decision.reason})
        return decision
