"""Execution request API (P-05 Stage 2).

* ``POST /api/v1/execution/requests`` - an agent submits work for admission.
* ``/api/v1/execution/requests`` - the ledger of what was asked, and what
  policy decided about it.

Authorization is per operation:

* ``execution.submit`` - submit, retry and cancel. The agent's identity comes
  from the authenticated principal, never from the payload; the service
  resolves the agent from `agents.principal_id`, so holding this code is not
  enough to submit as somebody else.
* ``execution.read`` - read the ledger and the subsystem status.

Two disclosure rules, both inherited from the assignment ledger's reasoning:

* **A policy refusal is a `409`, not a `200` with a sad field in it.** The
  body carries the whole evaluation - every check that ran, which one refused,
  and why - so a caller cannot ignore the refusal. Unlike an assignment
  refusal, an execution refusal *does* leave a row, at REJECTED: §6.1 makes
  REJECTED an outcome of a request rather than the absence of one, and what
  agents attempted is something an owner audits.
* **`QUEUED` does not mean running.** Stage 2 admits requests; no adapter
  exists yet to drain the queue, and `/execution/status` says so. The 201
  means "admitted", and inventing a stronger claim here would be precisely
  the failure §6.1's COMPLETED rule exists to prevent.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ...core.exceptions import ConflictError
from ...execution.requests import ExecutionRefusedError
from ...execution.schemas import ExecutionRequestInput
from ..dependencies import get_services, require_permission
from ..schemas.common import envelope

router = APIRouter(prefix="/execution", tags=["execution"])


class ExecutionDisabledError(ConflictError):
    code = "execution_disabled"


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="", max_length=1000)


def _execution(request: Request) -> Any:
    """The assembled subsystem, or a 409 that names the setting to change."""
    services = get_services(request)
    if getattr(services, "execution", None) is None:
        raise ExecutionDisabledError(
            "the execution subsystem is not enabled",
            details={"hint": "set AUTONOMUS_EXECUTION_ENABLED=true"})
    return services.execution


def _correlation(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


@router.post("/requests", status_code=201)
async def submit_request(
    request: Request,
    payload: ExecutionRequestInput,
    principal=Depends(require_permission("execution.submit")),
):
    """Run §8.1's ten policy checks; queue, hold for approval, or reject.

    `201` only when the request was admitted (QUEUED) or is awaiting the
    owner's approval (AWAITING_APPROVAL). A refusal is a `409` carrying the
    full evaluation, with the request recorded at REJECTED.
    """
    execution = _execution(request)
    result = await execution.requests.submit(
        principal.id, payload, correlation_id=_correlation(request))
    if result.status == "REJECTED":
        evaluation = result.evaluation
        raise ExecutionRefusedError(
            evaluation.reason if evaluation else "the request was refused",
            details={"request_id": result.request_id, "status": "REJECTED",
                     "evaluation": evaluation.as_dict() if evaluation else None})
    return envelope(result.as_dict())


# Declared before `/requests/{request_id}`: FastAPI matches in order, and a
# literal segment declared second would be read as an identifier.
@router.get("/status")
async def execution_status(
    request: Request,
    principal=Depends(require_permission("execution.read")),
):
    """What the subsystem is, what it holds, and what it cannot yet do."""
    execution = _execution(request)
    body = execution.status()
    body["registry"] = await execution.registry.status()
    body["requests"] = await execution.requests.status()
    return envelope(body)


@router.get("/requests")
async def list_requests(
    request: Request,
    status: str | None = Query(default=None, max_length=32),
    agent_id: str | None = Query(default=None, max_length=64),
    tool_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal=Depends(require_permission("execution.read")),
):
    execution = _execution(request)
    rows, total = await execution.requests.list_requests(
        status=status, agent_id=agent_id, tool_id=tool_id,
        limit=limit, offset=offset)
    return envelope(rows, limit=limit, offset=offset, total=total)


@router.get("/requests/{request_id}")
async def get_request(
    request_id: str,
    request: Request,
    principal=Depends(require_permission("execution.read")),
):
    execution = _execution(request)
    view = await execution.requests.get(request_id)
    return envelope(view.model_dump(mode="json"))


@router.post("/requests/{request_id}/retry")
async def retry_request(
    request_id: str,
    request: Request,
    principal=Depends(require_permission("execution.submit")),
):
    """Re-run policy after the owner decides, or after a human intervenes.

    Everything is re-evaluated, not only the approval: a capability revoked
    while the request waited is caught here rather than honoured from the
    original submission.
    """
    execution = _execution(request)
    result = await execution.requests.retry(
        request_id, principal.id, correlation_id=_correlation(request))
    if result.status == "REJECTED":
        evaluation = result.evaluation
        raise ExecutionRefusedError(
            evaluation.reason if evaluation else "the request was refused",
            details={"request_id": result.request_id, "status": "REJECTED",
                     "evaluation": evaluation.as_dict() if evaluation else None})
    return envelope(result.as_dict())


@router.post("/requests/{request_id}/cancel")
async def cancel_request(
    request_id: str,
    request: Request,
    payload: CancelRequest | None = None,
    principal=Depends(require_permission("execution.submit")),
):
    """Withdraw an admitted request. Only the submitting agent may, and only
    before a terminal outcome: a finished request is a record, not a draft."""
    execution = _execution(request)
    view = await execution.requests.cancel(
        request_id, principal.id, reason=(payload.reason if payload else ""),
        correlation_id=_correlation(request))
    return envelope(view.model_dump(mode="json"))
