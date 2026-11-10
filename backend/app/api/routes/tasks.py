from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...core.application import Application
from ...permissions.models import Permission, Principal
from ...tasks.models import TaskSubmitRequest
from ..dependencies import correlation_id, get_application, get_principal
from ..schemas.common import ok, page
from ..schemas.tasks import TaskExecutionOut, TaskOut

router = APIRouter(tags=["tasks"])


@router.post("/tasks", status_code=201)
async def submit_task(body: TaskSubmitRequest, request: Request,
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(get_principal)):
    task = await application.tasks.submit(
        principal, name=body.name, handler_name=body.handler_name, payload=body.payload,
        description=body.description, category=body.category, priority=body.priority,
        max_retries=body.max_retries, timeout_seconds=body.timeout_seconds,
        assigned_agent_id=body.assigned_agent_id, requires_approval=body.requires_approval,
        essential=body.essential, idempotency_key=body.idempotency_key,
        correlation_id=correlation_id(request))
    # If approval is required, open the bound approval request now.
    if body.requires_approval and task.approval_id is None:
        approval = application.approvals.create(
            principal, action="task.execute", resource=f"task:{task.id}",
            risk_classification="medium",
            reason=f"approval required before executing task '{task.name}'",
            requested_permissions=[Permission.EXECUTE_TOOLS.value],
            parameters={"task_id": task.id, "handler_name": task.handler_name,
                        "payload": task.payload})
        session = application.session_factory()
        try:
            from ...database.repositories.core import TaskRepository
            repo = TaskRepository(session)
            row = repo.get(task.id)
            row.approval_id = approval.id
            repo.save(row)
        finally:
            session.close()
        task = application.tasks.get(task.id)
    return ok(TaskOut.from_model(task).model_dump(), correlation_id(request))


@router.get("/tasks")
async def list_tasks(request: Request, status: str | None = None,
                     limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
                     application: Application = Depends(get_application),
                     _: Principal = Depends(get_principal)):
    rows, total = application.tasks.list(status=status, limit=limit, offset=offset)
    return page([TaskOut.from_model(t).model_dump() for t in rows], total, limit, offset,
                correlation_id(request))


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request,
                   application: Application = Depends(get_application),
                   _: Principal = Depends(get_principal)):
    task = application.tasks.get(task_id)
    data = TaskOut.from_model(task).model_dump()
    data["executions"] = [TaskExecutionOut.from_model(e).model_dump()
                          for e in application.tasks.history(task_id)]
    return ok(data, correlation_id(request))


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request,
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(get_principal)):
    task = await application.tasks.cancel(principal, task_id,
                                          correlation_id=correlation_id(request))
    return ok(TaskOut.from_model(task).model_dump(), correlation_id(request))


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str, request: Request,
                     application: Application = Depends(get_application),
                     _: Principal = Depends(get_principal)):
    task = await application.tasks.retry(task_id)
    return ok(TaskOut.from_model(task).model_dump(), correlation_id(request))


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str, request: Request,
                     application: Application = Depends(get_application),
                     _: Principal = Depends(get_principal)):
    task = await application.tasks.pause(task_id)
    return ok(TaskOut.from_model(task).model_dump(), correlation_id(request))


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str, request: Request,
                      application: Application = Depends(get_application),
                      _: Principal = Depends(get_principal)):
    task = await application.tasks.resume(task_id)
    return ok(TaskOut.from_model(task).model_dump(), correlation_id(request))
