from __future__ import annotations

from datetime import timedelta

from ..core.exceptions import ConflictError, ForbiddenError, NotFoundError
from ..database.connection import Database
from ..database.models import utcnow
from ..database.repositories import ApprovalRepo, AuditRepo
from ..events.bus import EventBus
from .models import ApprovalCreateRequest, ApprovalDecisionRequest, canonical_payload_hash


class ApprovalService:
    def __init__(self, db: Database, bus: EventBus):
        self.db = db
        self.bus = bus

    async def create(self, principal_id: str, request: ApprovalCreateRequest, correlation_id: str | None = None):
        payload_hash = canonical_payload_hash(request.action, request.resource, request.requested_permissions, request.parameters)
        async with self.db.session_factory() as session:
            approval = await ApprovalRepo(session).create(
                requester_id=principal_id, action=request.action, resource=request.resource, risk=request.risk,
                reason=request.reason, requested_permissions=request.requested_permissions, payload_hash=payload_hash,
                status="pending", expires_at=utcnow() + timedelta(seconds=request.ttl_seconds),
            )
            await AuditRepo(session).record("approval.requested", "allowed", principal_id=principal_id, resource=approval.id, action=request.action, correlation_id=correlation_id, payload={"payload_hash": payload_hash})
            await session.commit()
            approval_id = approval.id
        await self.bus.publish_new("ApprovalRequested", "approvals", {"action": request.action}, correlation_id=correlation_id)
        return await self.get(approval_id)

    async def get(self, approval_id: str):
        async with self.db.session_factory() as session:
            approval = await ApprovalRepo(session).get(approval_id)
            if not approval:
                raise NotFoundError("Approval not found")
            if approval.status == "pending":
                exp = approval.expires_at
                from datetime import timezone
                if exp.tzinfo is None: exp = exp.replace(tzinfo=timezone.utc)
                if exp <= utcnow():
                    approval.status = "expired"
                    await session.commit()
            return approval

    async def decide(self, approver_id: str, approval_id: str, request: ApprovalDecisionRequest, correlation_id: str | None = None):
        async with self.db.session_factory() as session:
            repo = ApprovalRepo(session)
            approval = await repo.get(approval_id)
            if not approval:
                raise NotFoundError("Approval not found")
            if approval.status != "pending":
                raise ConflictError(f"Approval is already {approval.status}")
            from datetime import timezone
            exp = approval.expires_at
            if exp.tzinfo is None: exp = exp.replace(tzinfo=timezone.utc)
            if exp <= utcnow():
                approval.status = "expired"
                await session.commit()
                raise ConflictError("Approval has expired")
            if approval.requester_id == approver_id and approval.risk in {"high", "critical"}:
                raise ForbiddenError("Requester cannot approve their own high/critical risk action")
            approval.status = request.decision
            approval.approver_id = approver_id
            approval.decided_at = utcnow()
            approval.notes = request.notes
            await AuditRepo(session).record(f"approval.{request.decision}", "allowed", principal_id=approver_id, resource=approval.id, action=approval.action, correlation_id=correlation_id, payload={"payload_hash": approval.payload_hash})
            await session.commit()
        await self.bus.publish_new("ApprovalGranted" if request.decision == "approved" else "ApprovalRejected", "approvals", {"approval_id": approval_id}, correlation_id=correlation_id)
        return await self.get(approval_id)

    @staticmethod
    def verify_binding(approval, action: str, resource: str, permissions: list[str], parameters: dict) -> bool:
        return approval.payload_hash == canonical_payload_hash(action, resource, permissions, parameters)
