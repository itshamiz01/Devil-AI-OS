"""Human approval framework (P-01 §9.4).

An approval is bound to the exact action + parameters via a SHA-256 hash;
if the parameters change, :meth:`ApprovalService.verify_binding` fails and
a new approval is required. Creating a request does NOT authorize anything.

P-10 hardening (closing the residual carried since P-07):
:meth:`ApprovalService.decide` now enforces, AT THE SERVICE LEVEL,
(1) the decider must hold ``approve_actions`` under the permission
engine — previously only the API route checked this, so any
in-process caller could decide with any principal; and (2) a
non-owner approver may never decide a request it originated
(self-approval). The owner deciding an owner-initiated governed step
(P-02 plan approval, P-06 declaration/blueprint) remains by design:
the owner is the root authority. See
``docs/audits/P10_PRE_IMPLEMENTATION_AUDIT.md`` §4.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from ..core.exceptions import ApprovalError, NotFoundError, PermissionDeniedError
from ..database.models.base import as_utc, utcnow
from ..database.models.core import Approval
from ..database.repositories.core import ApprovalRepository
from .engine import PermissionEngine
from .models import Principal, PrincipalType

APPROVAL_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"approved", "rejected", "expired", "cancelled"},
    "approved": set(),
    "rejected": set(),
    "expired": set(),
    "cancelled": set(),
}


def parameters_hash(action: str, resource: str | None, parameters: dict) -> str:
    canonical = json.dumps(
        {"action": action, "resource": resource, "parameters": parameters},
        sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ApprovalService:
    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._engine = PermissionEngine(session_factory)

    def create(self, requester: Principal, action: str, resource: str | None,
               risk_classification: str, reason: str | None,
               requested_permissions: list[str], parameters: dict,
               expires_at: dt.datetime | None = None) -> Approval:
        session = self._session_factory()
        try:
            approval = Approval(
                requesting_principal_type=requester.type.value,
                requesting_principal_id=requester.id,
                action=action, resource=resource,
                risk_classification=risk_classification, reason=reason,
                requested_permissions=requested_permissions, parameters=parameters,
                parameters_hash=parameters_hash(action, resource, parameters),
                status="pending", expires_at=expires_at,
            )
            return ApprovalRepository(session).add(approval)
        finally:
            session.close()

    def get(self, approval_id: str) -> Approval:
        session = self._session_factory()
        try:
            approval = ApprovalRepository(session).get(approval_id)
            if approval is None:
                raise NotFoundError(f"approval {approval_id} not found")
            self._expire_if_needed(session, approval)
            return approval
        finally:
            session.close()

    def list(self, status: str | None = None, limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            return ApprovalRepository(session).list(status, limit, offset)
        finally:
            session.close()

    def decide(self, approval_id: str, approver: Principal, approve: bool,
               notes: str | None = None) -> Approval:
        session = self._session_factory()
        try:
            repo = ApprovalRepository(session)
            approval = repo.get(approval_id)
            if approval is None:
                raise NotFoundError(f"approval {approval_id} not found")
            self._expire_if_needed(session, approval)
            # P-10 service-level governance (see module docstring):
            # the decider must hold approve_actions under the engine,
            # whoever calls this service — API route or internal flow.
            decision = self._engine.check(
                approver, "approve_actions",
                resource=f"approval:{approval_id}", audit=True)
            if not decision.allowed:
                raise PermissionDeniedError(
                    "approval decisions require the 'approve_actions' "
                    f"authority ({decision.reason})",
                    details={"error_category": "APPROVAL_AUTHORITY"})
            # Self-approval: a non-owner approver may never decide a
            # request it originated.
            if approver.type is not PrincipalType.OWNER \
                    and approver.type.value == approval.requesting_principal_type \
                    and approver.id == approval.requesting_principal_id:
                raise PermissionDeniedError(
                    "self-approval is refused: the requesting principal "
                    "cannot decide its own approval request",
                    details={"error_category": "APPROVAL_SELF_APPROVAL"})
            target = "approved" if approve else "rejected"
            if target not in APPROVAL_TRANSITIONS.get(approval.status, set()):
                raise ApprovalError(
                    f"cannot decide an approval in state '{approval.status}'",
                    details={"status": approval.status})
            approval.status = target
            approval.approver_id = f"{approver.type.value}:{approver.id}"
            approval.decision_at = utcnow()
            approval.decision_notes = notes
            return repo.save(approval)
        finally:
            session.close()

    def cancel(self, approval_id: str) -> Approval:
        session = self._session_factory()
        try:
            repo = ApprovalRepository(session)
            approval = repo.get(approval_id)
            if approval is None:
                raise NotFoundError(f"approval {approval_id} not found")
            if "cancelled" not in APPROVAL_TRANSITIONS.get(approval.status, set()):
                raise ApprovalError(f"cannot cancel an approval in state '{approval.status}'")
            approval.status = "cancelled"
            return repo.save(approval)
        finally:
            session.close()

    @staticmethod
    def verify_binding(approval: Approval, action: str, resource: str | None,
                       parameters: dict) -> bool:
        """True only if the action+parameters still match what was approved."""
        if approval.status != "approved":
            return False
        return approval.parameters_hash == parameters_hash(action, resource, parameters)

    @staticmethod
    def _expire_if_needed(session, approval: Approval) -> None:
        if approval.status == "pending" and approval.expires_at is not None:
            # P-14 Stage B (DEF-D2): standardised naive→aware shim.
            if as_utc(approval.expires_at) <= utcnow():
                approval.status = "expired"
                ApprovalRepository(session).save(approval)
