"""Code execution API (P-05 Stage 4).

Three operations, each one an execution request that the scheduler runs:

* ``POST /execution/code/run`` - run a program in the allow-listed interpreter.
* ``GET  /execution/code/runs`` - the ledger of code runs and their outcomes.
* ``GET  /execution/code/runs/{run_id}`` - one code run, with its result.

Two decisions shape this module, both inherited from the filesystem routes.

**Every operation is an execution request, not a shortcut around one.** The
run route builds an `ExecutionRequestInput` - tool, action, parameters, the
workspace as scope - and hands it to the request manager, so the ten policy
checks, the approval gate, the audit trail and the run row all exist for a code
run exactly as they do for a file write. A code run that skipped the request
machinery would be an untrusted-process boundary without the boundary's checks,
which is the failure §8.1 exists to prevent.

**The scheduler runs it before the response is returned** when it can. `submit`
admits; `drain_once` executes; the route returns the final request view. That
makes the outcome visible in one call - honest, because §6.1 forbids reporting
`QUEUED` as if work were done. A code run that is Risk 2 and awaiting the
owner's approval is *not* run: it is returned at `AWAITING_APPROVAL`, because
§30 rule 22 forbids weak-isolated untrusted code running without the human gate,
and pretending it ran would be the failure that rule exists to prevent.

Identity comes from the authenticated principal and scope is the workspace name,
so an agent cannot run code in another agent's workspace: the workspace is
resolved from the request's agent_id, and the run is confined to that
workspace's root by the adapter (the same containment boundary the filesystem
adapter proves against).

**The interpreter is allow-listed and controlled.** The adapter spawns one
executable, resolved from `execution_code_interpreter` (default: the engine's
own interpreter), never a binary the requester names; the child gets a minimal
environment (never the engine's secrets); output is capped; and a wall-clock
timeout kills the whole process tree. `isolation_strength` reports "weak" - a
subprocess with a timeout, not a sandbox - and that is why the tool is Risk 2
and requires owner approval on every run.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ...core.exceptions import NotFoundError
from ...execution.schemas import ExecutionRequestInput, ExecutionRunView
from ..dependencies import get_services, require_permission
from ..schemas.common import envelope
from .execution_requests import ExecutionDisabledError, ExecutionRefusedError, _correlation

router = APIRouter(prefix="/execution/code", tags=["execution"])


class _CodePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=1_048_576)
    #: Optional interpreter, honoured only if it matches an allow-listed path.
    interpreter: str = Field(default="", max_length=512)
    #: Wall-clock timeout override; bounded by the schema's own limit.
    timeout_seconds: int = Field(default=0, ge=0, le=300)


def _execution(request: Request) -> Any:
    services = get_services(request)
    if getattr(services, "execution", None) is None:
        raise ExecutionDisabledError(
            "the execution subsystem is not enabled",
            details={"hint": "set AUTONOMUS_EXECUTION_ENABLED=true"})
    return services.execution


#: The code tool, resolved at call time by name so the route does not
#: hard-code a registry id (ids are database-generated).
_CODE_TOOL = "code.execute"


class ExecutionCodeToolNotFound(NotFoundError):
    code = "execution_code_tool_not_found"


async def _tool_id(execution: Any) -> str:
    """Resolve the built-in code tool by name, refusing if it is not there."""
    async with execution.db.session_factory() as session:
        from ...database.models import ExecutionTool
        row = (await session.execute(
            select(ExecutionTool).where(ExecutionTool.name == _CODE_TOOL)
            .order_by(ExecutionTool.created_at.desc()))).scalars().first()
    if row is None:
        raise ExecutionCodeToolNotFound(
            f"the tool {_CODE_TOOL} is not registered; the code adapter "
            "registers it at startup, so a missing row means the subsystem "
            "was built before Stage 4 landed")
    return row.id


async def _agent_task(execution: Any, principal: Any, workspace: str) -> str:
    """The task this principal's agent holds, for the request's task_id.

    §8.1 check 3 refuses a request whose task is not assigned to the agent, so
    the route cannot invent a task id: the agent must hold a task, resolved
    from the assignment ledger. If it holds none, the honest answer is a 409
    naming that, not a synthetic task that would pass the check while meaning
    nothing.
    """
    async with execution.db.session_factory() as session:
        from ...database.repositories import AgentAssignmentRepo, AgentRepo
        agent = await AgentRepo(session).by_principal(principal.id)
        if agent is None:
            from ...execution.requests import ExecutionIdentityError
            raise ExecutionIdentityError(
                "no agent is bound to the authenticated principal; code "
                "execution is performed by agents, with identity taken "
                "from the principal rather than the payload")
        row = (await AgentAssignmentRepo(session).for_agent(agent.id))
        if not row:
            from ...core.exceptions import ConflictError
            raise ConflictError(
                "the agent holds no task, so there is no work for this code "
                "run to belong to; assign a task before requesting code "
                "execution", code="no_assigned_task")
        return row[0].task_id


async def _run(execution: Any, *, payload: _CodePayload, principal: Any,
               correlation_id: str | None) -> dict[str, Any]:
    """Submit a code request, drain it, return the final request view."""
    tool_id = await _tool_id(execution)
    task_id = await _agent_task(execution, principal, payload.workspace)
    parameters: dict[str, Any] = {"code": payload.code}
    if payload.interpreter:
        parameters["interpreter"] = payload.interpreter
    if payload.timeout_seconds:
        parameters["timeout_seconds"] = payload.timeout_seconds
    request_input = ExecutionRequestInput(
        task_id=task_id, tool_id=tool_id, action_name="run",
        action_parameters=parameters, required_capabilities=[],
        requested_scope=payload.workspace)
    result = await execution.requests.submit(
        principal.id, request_input, correlation_id=correlation_id)
    if result.status == "REJECTED":
        evaluation = result.evaluation
        raise ExecutionRefusedError(
            evaluation.reason if evaluation else "the request was refused",
            details={"request_id": result.request_id, "status": "REJECTED",
                     "evaluation": evaluation.as_dict() if evaluation else None})
    if result.status == "AWAITING_APPROVAL":
        # Risk 2: the run waits for the owner's decision (or a standing
        # authorization). §30 rule 22 - weak-isolated untrusted code does not
        # run without the human gate - so the route reports that honestly
        # rather than draining it into execution.
        return result.as_dict()
    drained = await execution.scheduler.drain_once()
    final = await execution.requests.get(result.request_id)
    body = final.model_dump(mode="json")
    body["drained"] = drained.status if drained else None
    body["drained_result"] = drained.result if drained else None
    return body


@router.post("/run")
async def run_code(request: Request, payload: _CodePayload = Depends(),
                   principal=Depends(require_permission("execution.code.run"))):
    """Run a program in the allow-listed interpreter, inside the workspace."""
    execution = _execution(request)
    return envelope(await _run(execution, payload=payload,
                               principal=principal,
                               correlation_id=_correlation(request)))


@router.get("/runs")
async def list_runs(request: Request,
                    status: str | None = Query(default=None),
                    limit: int = Query(default=50, ge=1, le=200),
                    offset: int = Query(default=0, ge=0),
                    principal=Depends(require_permission("execution.read"))):
    """The ledger of code runs, filterable by request status."""
    execution = _execution(request)
    async with execution.db.session_factory() as session:
        from ...database.models import ExecutionRequest, ExecutionRun
        q = (select(ExecutionRun)
             .join(ExecutionRequest,
                   ExecutionRun.execution_request_id == ExecutionRequest.id)
             .where(ExecutionRequest.adapter_type == "code"))
        if status:
            q = q.where(ExecutionRun.status == status)
        runs = (await session.execute(
            q.order_by(ExecutionRun.created_at.desc())
            .limit(limit).offset(offset))).scalars().all()
    body = [ExecutionRunView.from_row(r).model_dump(mode="json") for r in runs]
    return envelope({"runs": body, "count": len(body)})


@router.get("/runs/{run_id}")
async def get_run(request: Request, run_id: str,
                  principal=Depends(require_permission("execution.read"))):
    """One code run, with its exit code, output and isolation strength."""
    execution = _execution(request)
    async with execution.db.session_factory() as session:
        from ...database.models import ExecutionRequest, ExecutionRun
        row = (await session.execute(
            select(ExecutionRun)
            .join(ExecutionRequest,
                  ExecutionRun.execution_request_id == ExecutionRequest.id)
            .where(ExecutionRun.id == run_id,
                   ExecutionRequest.adapter_type == "code"))).scalars().first()
    if row is None:
        from ...core.exceptions import NotFoundError
        raise NotFoundError(f"code run {run_id} does not exist")
    return envelope(ExecutionRunView.from_row(row).model_dump(mode="json"))
