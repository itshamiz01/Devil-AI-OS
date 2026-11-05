"""Filesystem execution API (P-05 Stage 3).

Six operations, each one an execution request that the scheduler runs:

* ``GET  /execution/files/list`` - directory listing inside a workspace.
* ``GET  /execution/files/read`` - file contents, hash-evidenced.
* ``POST /execution/files/write`` - atomic write (temp + replace).
* ``POST /execution/files/create_dir`` - directory creation.
* ``POST /execution/files/move`` - move within the workspace.
* ``POST /execution/files/delete`` - quarantine-reversible delete.

Two decisions shape this module.

**Every operation is an execution request, not a shortcut around one.** The
route builds an `ExecutionRequestInput` - tool, action, parameters, the
workspace as scope - and hands it to the request manager, so the ten policy
checks, the audit trail and the run row all exist for a file read exactly as
they do for a browser action. A file operation that skipped the request
machinery would be a tool boundary without the boundary's checks, which is the
failure §8.1 exists to prevent.

**The scheduler runs it before the response is returned.** `submit` admits
(and queues); `drain_once` executes; the route returns the final request view.
That makes the outcome visible in one call - honest, because §6.1 forbids
reporting `QUEUED` as if work were done - while the request row still records
what was asked, what ran and what was verified. A write that was capped, a
delete that was quarantined and a read that was truncated are all visible in
the result.

Identity comes from the authenticated principal and scope is the workspace
name, so an agent cannot name another agent's workspace: the workspace is
resolved from the request's agent_id, and the path is proven against that
workspace's root by the adapter (resolved-path containment, not prefix
matching).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ...core.exceptions import NotFoundError
from ...execution.schemas import ExecutionRequestInput
from ..dependencies import get_services, require_permission
from ..schemas.common import envelope
from .execution_requests import ExecutionDisabledError, _correlation

router = APIRouter(prefix="/execution/files", tags=["execution"])


class _FilePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace: str = Field(min_length=1, max_length=128)
    path: str = Field(default="", max_length=512)
    content: str = Field(default="", max_length=8_388_608)
    destination: str = Field(default="", max_length=512)


def _execution(request: Request) -> Any:
    services = get_services(request)
    if getattr(services, "execution", None) is None:
        raise ExecutionDisabledError(
            "the execution subsystem is not enabled",
            details={"hint": "set AUTONOMUS_EXECUTION_ENABLED=true"})
    return services.execution


#: tool_id -> the two built-in tools, resolved at call time by name so the
#: route does not hard-code a registry id (ids are database-generated).
_FS_TOOLS = ("filesystem.read_ops", "filesystem.write_ops")


class ExecutionFileToolNotFound(NotFoundError):
    code = "execution_file_tool_not_found"


async def _tool_id(execution: Any, tool_name: str) -> str:
    """Resolve a built-in tool by name, refusing if it is not registered.

    A tool that is registered but DISABLED (an owner turned it off) passes
    this lookup and is refused by policy check 6 instead - which is the
    right refusal, because "an owner disabled it" is a different fact from
    "nobody registered it".
    """
    async with execution.db.session_factory() as session:
        from sqlalchemy import select
        from ...database.models import ExecutionTool
        row = (await session.execute(
            select(ExecutionTool).where(ExecutionTool.name == tool_name)
            .order_by(ExecutionTool.created_at.desc()))).scalars().first()
    if row is None:
        raise ExecutionFileToolNotFound(
            f"the tool {tool_name} is not registered; the filesystem adapter "
            "registers it at startup, so a missing row means the subsystem "
            "was built before this stage landed")
    return row.id


async def _run(execution: Any, *, tool_name: str, action: str, payload: _FilePayload,
               principal: Any, correlation_id: str | None) -> dict[str, Any]:
    """Submit a filesystem request, drain it, return the final request view."""
    tool_id = await _tool_id(execution, tool_name)
    parameters = {"path": payload.path}
    if action in ("write", "create_dir", "move", "delete"):
        if action == "write":
            parameters["content"] = payload.content
        if action == "move":
            parameters["destination"] = payload.destination
    request_input = ExecutionRequestInput(
        task_id=f"fs-{action}-{payload.workspace}",  # resolved below; see note
        tool_id=tool_id, action_name=action,
        action_parameters=parameters, required_capabilities=[],
        requested_scope=payload.workspace)
    # task_id is a task, not a workspace: the file routes resolve it from the
    # request's own task. The scheduler needs a task row; the submission path
    # requires one. A file operation is work for the agent's task, so the
    # route looks it up from the principal's assignment rather than inventing
    # a synthetic task id that would fail policy check 3 (assigned task).
    task_id = await _agent_task(execution, principal, payload.workspace)
    request_input = request_input.model_copy(update={"task_id": task_id})
    result = await execution.requests.submit(
        principal.id, request_input, correlation_id=correlation_id)
    if result.status == "REJECTED":
        from .execution_requests import ExecutionRefusedError
        evaluation = result.evaluation
        raise ExecutionRefusedError(
            evaluation.reason if evaluation else "the request was refused",
            details={"request_id": result.request_id, "status": "REJECTED",
                     "evaluation": evaluation.as_dict() if evaluation else None})
    if result.status == "AWAITING_APPROVAL":
        return result.as_dict()
    drained = await execution.scheduler.drain_once()
    final = await execution.requests.get(result.request_id)
    body = final.model_dump(mode="json")
    body["drained"] = drained.status if drained else None
    body["drained_result"] = drained.result if drained else None
    return body


async def _agent_task(execution: Any, principal: Any, workspace: str) -> str:
    """The task this principal's agent holds, for the request's task_id.

    §8.1 check 3 refuses a request whose task is not assigned to the agent,
    so a file route cannot invent a task id: the agent must hold a task. The
    route resolves the agent's task from the assignment ledger; if the agent
    holds none, the honest answer is a 409 naming that, not a synthetic task
    that would pass the check while meaning nothing.
    """
    async with execution.db.session_factory() as session:
        from ...database.repositories import AgentAssignmentRepo, AgentRepo
        agent = await AgentRepo(session).by_principal(principal.id)
        if agent is None:
            from ...execution.requests import ExecutionIdentityError
            raise ExecutionIdentityError(
                "no agent is bound to the authenticated principal; file "
                "operations are performed by agents, with identity taken "
                "from the principal rather than the payload")
        row = (await AgentAssignmentRepo(session).for_agent(agent.id))
        if not row:
            from ...core.exceptions import ConflictError
            raise ConflictError(
                "the agent holds no task, so there is no work for this file "
                "operation to belong to; assign a task before requesting "
                "filesystem execution", code="no_assigned_task")
        return row[0].task_id


@router.get("/list")
async def list_files(request: Request,
                     workspace: str = Query(min_length=1, max_length=128),
                     path: str = Query(default="", max_length=512),
                     principal=Depends(require_permission("execution.submit"))):
    """Directory listing inside the workspace named by `workspace`."""
    execution = _execution(request)
    return envelope(await _run(execution, tool_name=_FS_TOOLS[0], action="list",
                               payload=_FilePayload(workspace=workspace, path=path),
                               principal=principal,
                               correlation_id=_correlation(request)))


@router.get("/read")
async def read_file(request: Request,
                    workspace: str = Query(min_length=1, max_length=128),
                    path: str = Query(min_length=1, max_length=512),
                    principal=Depends(require_permission("execution.submit"))):
    """File contents, with a content hash recorded as evidence."""
    execution = _execution(request)
    return envelope(await _run(execution, tool_name=_FS_TOOLS[0], action="read",
                               payload=_FilePayload(workspace=workspace, path=path),
                               principal=principal,
                               correlation_id=_correlation(request)))


@router.post("/write")
async def write_file(request: Request, payload: _FilePayload = Depends(),
                     principal=Depends(require_permission("execution.submit"))):
    """Atomic write: temp file in the destination directory, then replace."""
    execution = _execution(request)
    return envelope(await _run(execution, tool_name=_FS_TOOLS[1], action="write",
                               payload=payload, principal=principal,
                               correlation_id=_correlation(request)))


@router.post("/create_dir")
async def create_dir(request: Request, payload: _FilePayload = Depends(),
                     principal=Depends(require_permission("execution.submit"))):
    """Create a directory inside the workspace."""
    execution = _execution(request)
    return envelope(await _run(execution, tool_name=_FS_TOOLS[1],
                               action="create_dir", payload=payload,
                               principal=principal,
                               correlation_id=_correlation(request)))


@router.post("/move")
async def move_file(request: Request, payload: _FilePayload = Depends(),
                   principal=Depends(require_permission("execution.submit"))):
    """Move a file within the workspace."""
    execution = _execution(request)
    return envelope(await _run(execution, tool_name=_FS_TOOLS[1], action="move",
                               payload=payload, principal=principal,
                               correlation_id=_correlation(request)))


@router.post("/delete")
async def delete_file(request: Request, payload: _FilePayload = Depends(),
                      principal=Depends(require_permission("execution.submit"))):
    """Delete a file: it is moved to quarantine, reversibly, not unlinked."""
    execution = _execution(request)
    return envelope(await _run(execution, tool_name=_FS_TOOLS[1], action="delete",
                               payload=payload, principal=principal,
                               correlation_id=_correlation(request)))
