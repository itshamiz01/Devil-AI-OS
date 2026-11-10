from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query, Request

from ...core.application import Application
from ...core.exceptions import ApprovalError, PermissionDeniedError
from ...database.models.base import utcnow
from ...database.models.core import AuditEvent
from ...database.repositories.core import AuditRepository
from ...events.events import Event, EventType
from ...permissions.models import Permission, Principal
from ..dependencies import correlation_id, get_application, require_permission
from ..schemas.approvals import ApprovalCreate, ApprovalDecisionIn, ApprovalOut
from ..schemas.common import ok, page

router = APIRouter(tags=["approvals"])


@router.post("/approvals", status_code=201)
async def create_approval(body: ApprovalCreate, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(require_permission("read_system_data"))):
    expires = None
    if body.expires_at:
        expires = dt.datetime.fromisoformat(body.expires_at.replace("Z", "+00:00"))
    approval = application.approvals.create(
        principal, action=body.action, resource=body.resource,
        risk_classification=body.risk_classification, reason=body.reason,
        requested_permissions=body.requested_permissions, parameters=body.parameters,
        expires_at=expires)
    await application.bus.publish(Event(
        EventType.APPROVAL_REQUESTED, source="api.approvals",
        correlation_id=correlation_id(request),
        payload={"approval_id": approval.id, "action": approval.action}))
    return ok(ApprovalOut.from_model(approval).model_dump(), correlation_id(request))


@router.get("/approvals")
async def list_approvals(request: Request, status: str | None = None,
                         limit: int = Query(default=50, ge=1, le=200),
                         offset: int = Query(default=0, ge=0),
                         application: Application = Depends(get_application),
                         _: Principal = Depends(require_permission("read_system_data"))):
    rows, total = application.approvals.list(status, limit, offset)
    return page([ApprovalOut.from_model(a).model_dump() for a in rows], total, limit, offset,
                correlation_id(request))


@router.get("/approvals/{approval_id}")
async def get_approval(approval_id: str, request: Request,
                       application: Application = Depends(get_application),
                       _: Principal = Depends(require_permission("read_system_data"))):
    approval = application.approvals.get(approval_id)
    return ok(ApprovalOut.from_model(approval).model_dump(), correlation_id(request))


@router.post("/approvals/{approval_id}/decision")
async def decide_approval(approval_id: str, body: ApprovalDecisionIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(require_permission("approve_actions"))):
    approval = application.approvals.decide(approval_id, principal, body.approve, body.notes)
    # Audit the decision (approvals themselves also generate audit entries
    # through the permission check above).
    session = application.session_factory()
    try:
        AuditRepository(session).add(AuditEvent(
            actor_type=principal.type.value, actor_id=principal.id,
            action="approval.decision", target_type="approval", target_id=approval.id,
            decision=approval.status, reason=body.notes,
            correlation_id=correlation_id(request),
            details={"action": approval.action, "parameters_hash": approval.parameters_hash},
            created_at=utcnow()))
    finally:
        session.close()
    await application.bus.publish(Event(
        EventType.APPROVAL_GRANTED if body.approve else EventType.APPROVAL_REJECTED,
        source="api.approvals", correlation_id=correlation_id(request),
        payload={"approval_id": approval.id, "action": approval.action}))
    # If this approval gates a task, verify the binding before releasing it:
    # the approved parameters must still match the task exactly.
    if body.approve and approval.action == "task.execute":
        params = approval.parameters or {}
        task_id = params.get("task_id")
        if task_id:
            task = application.tasks.get(task_id)
            expected = {"task_id": task.id, "handler_name": task.handler_name, "payload": task.payload}
            if not application.approvals.verify_binding(approval, "task.execute",
                                                        approval.resource, expected):
                raise ApprovalError(
                    "task parameters changed since approval was requested; "
                    "the approval no longer binds this task and a new approval is required",
                    details={"approval_id": approval.id, "task_id": task_id})
            application.tasks.approve_task(task_id)
    return ok(ApprovalOut.from_model(approval).model_dump(), correlation_id(request))
