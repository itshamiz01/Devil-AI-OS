from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...database.repositories import ExecutionRepo, TaskRepo
from ...permissions.models import ApprovalView
from ...tasks.models import TaskExecutionView, TaskSubmitRequest, TaskView
from ..dependencies import get_services, require_permission
from ..schemas.common import envelope

router = APIRouter(prefix="/tasks", tags=["tasks"])


def view(task) -> dict:
    return TaskView.model_validate(task).model_dump(mode="json")


@router.post("", status_code=201)
async def submit(request: Request, body: TaskSubmitRequest, principal=Depends(require_permission("tasks.submit"))):
    services = get_services(request)
    task = await services.tasks.submit(principal.id, body, getattr(request.state, "correlation_id", None))
    return envelope(view(task))


@router.get("")
async def list_tasks(request: Request, status: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), principal=Depends(require_permission("tasks.read"))):
    services = get_services(request)
    async with services.db.session_factory() as session:
        tasks = await TaskRepo(session).list(status, limit, offset)
    return envelope([view(t) for t in tasks], limit=limit, offset=offset)


@router.get("/{task_id}")
async def get_task(task_id: str, request: Request, principal=Depends(require_permission("tasks.read"))):
    services = get_services(request)
    return envelope(view(await services.tasks.get(task_id)))


@router.get("/{task_id}/history")
async def history(task_id: str, request: Request, principal=Depends(require_permission("tasks.read"))):
    services = get_services(request)
    await services.tasks.get(task_id)
    async with services.db.session_factory() as session:
        executions = await ExecutionRepo(session).list_for_task(task_id)
    return envelope([TaskExecutionView.model_validate(e).model_dump(mode="json") for e in executions])


@router.post("/{task_id}/cancel")
async def cancel(task_id: str, request: Request, principal=Depends(require_permission("tasks.cancel"))):
    services = get_services(request)
    return envelope(view(await services.tasks.cancel(principal.id, task_id, getattr(request.state, "correlation_id", None))))


@router.post("/{task_id}/retry")
async def retry(task_id: str, request: Request, principal=Depends(require_permission("tasks.retry"))):
    services = get_services(request)
    return envelope(view(await services.tasks.retry(principal.id, task_id)))


@router.post("/{task_id}/pause")
async def pause(task_id: str, request: Request, principal=Depends(require_permission("tasks.pause"))):
    services = get_services(request)
    return envelope(view(await services.tasks.pause(principal.id, task_id)))


@router.post("/{task_id}/resume")
async def resume(task_id: str, request: Request, principal=Depends(require_permission("tasks.pause"))):
    services = get_services(request)
    return envelope(view(await services.tasks.resume(principal.id, task_id)))
