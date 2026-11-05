"""Agent assignment API (P-04 Stage 6).

One write family and one read family over the assignment ledger:

* ``POST /api/v1/agents/{agent_id}/assign`` — ask for work to be given to an agent.
* ``/api/v1/assignments`` — the ledger: what was assigned, what it became, and why.

Authorization is per operation:

* ``agents.write`` — assign, start, complete and cancel. Stage 6 added this code
  because handing work to an agent changes what the system will do next, and
  ``agents.read`` has only ever looked at the registry. Widening a read permission
  to cover assignment would have made every existing reader able to commit work.
* ``agents.read`` — read the ledger and its status.

Three disclosure rules shape the responses, all of them consequences of decisions
documented in :mod:`app.agents.assignments`.

* **A refusal is a `409`, not a `200` with a sad field in it.** The body carries the
  whole evaluation — every rule that ran, which one refused, and why — so a caller
  cannot ignore the refusal and cannot be left guessing which condition failed.
* **A refusal creates no resource.** Nothing is recorded in the ledger, so the
  `201` on this endpoint always means a row exists, and the ledger can be read as a
  list of work somebody was actually given.
* **Completion reports whether the result was accepted, and what it violated.** An
  agent reporting success against a contract it did not satisfy produces a `failed`
  assignment with the violations listed. That is the point of the endpoint: without
  it, "done" would mean whatever the agent said.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from ...agents.schemas import (
    AssignmentCompletionInput,
    AssignmentInput,
    AssignmentTransitionInput,
)
from ...agents.assignments import AssignmentRefusedError
from ...core.exceptions import ConflictError
from ..dependencies import get_services, require_permission
from ..schemas.common import envelope

router = APIRouter(tags=["agents"])


def _agents(request: Request) -> Any:
    """The assembled subsystem, or a 409 that names the setting to change."""
    services = get_services(request)
    if getattr(services, "agents", None) is None:
        raise ConflictError(
            "the agent subsystem is not enabled",
            details={"hint": "set AUTONOMOUS_AGENTS_ENABLED=true"})
    return services.agents


def _correlation(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


@router.post("/agents/{agent_id}/assign", status_code=201)
async def assign_work(
    agent_id: str,
    request: Request,
    payload: AssignmentInput,
    principal=Depends(require_permission("agents.write")),
):
    """Run the nine assignment rules; record the work if all of them pass.

    `201` only when a ledger row exists. A refusal is a `409` carrying the full
    evaluation, because the caller is entitled to know which rule said no and a
    `200` would let the refusal be read past.
    """
    agents = _agents(request)
    evaluation = await agents.assignments.assign(
        agent_id, payload.task_id,
        required_capabilities=payload.required_capabilities,
        expected_output_schema=payload.expected_output_schema,
        priority=payload.priority, assigned_by=principal.id,
        reason=payload.reason, correlation_id=_correlation(request))
    if not evaluation.assigned:
        raise AssignmentRefusedError(evaluation.reason,
                                     details={"evaluation": evaluation.as_dict()})
    return envelope(evaluation.as_dict())


@router.get("/agents/{agent_id}/assignments")
async def list_agent_assignments(
    agent_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal=Depends(require_permission("agents.read")),
):
    agents = _agents(request)
    rows, total = await agents.assignments.list_for_agent(
        agent_id, limit=limit, offset=offset)
    return envelope(rows, limit=limit, offset=offset, total=total)


# Declared before `/assignments/{assignment_id}`: FastAPI matches in order, and a
# literal segment declared second would be read as an identifier.
@router.get("/assignments/status")
async def assignment_status(
    request: Request,
    principal=Depends(require_permission("agents.read")),
):
    """What the ledger holds, including what is not observed yet."""
    agents = _agents(request)
    return envelope(await agents.assignments.status())


@router.get("/assignments")
async def list_assignments(
    request: Request,
    status: str | None = Query(default=None, max_length=32),
    agent_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal=Depends(require_permission("agents.read")),
):
    agents = _agents(request)
    rows, total = await agents.assignments.list_assignments(
        agent_id=agent_id, status=status, limit=limit, offset=offset)
    return envelope(rows, limit=limit, offset=offset, total=total)


@router.get("/assignments/{assignment_id}")
async def get_assignment(
    assignment_id: str,
    request: Request,
    principal=Depends(require_permission("agents.read")),
):
    agents = _agents(request)
    view = await agents.assignments.get(assignment_id)
    return envelope(view.model_dump(mode="json"))


@router.post("/assignments/{assignment_id}/start")
async def start_assignment(
    assignment_id: str,
    request: Request,
    payload: AssignmentTransitionInput | None = None,
    principal=Depends(require_permission("agents.write")),
):
    """Record that work began. It does not begin anything: execution is the task
    manager's, and a second dispatcher would leave two authorities over what runs."""
    agents = _agents(request)
    view = await agents.assignments.start(
        assignment_id, actor=principal.id, correlation_id=_correlation(request))
    return envelope(view.model_dump(mode="json"))


@router.post("/assignments/{assignment_id}/complete")
async def complete_assignment(
    assignment_id: str,
    request: Request,
    payload: AssignmentCompletionInput,
    principal=Depends(require_permission("agents.write")),
):
    """Judge the result against the assignment's output contract and close it.

    A reported success whose result does not satisfy the contract is recorded as
    `failed` with the violations listed, which is the deterministic verification
    the governance document requires before a parent is told work is done.
    """
    agents = _agents(request)
    outcome = await agents.assignments.complete(
        assignment_id, succeeded=payload.succeeded, result=payload.result,
        actor=principal.id, reason=payload.reason,
        correlation_id=_correlation(request))
    return envelope(outcome.as_dict())


@router.post("/assignments/{assignment_id}/cancel")
async def cancel_assignment(
    assignment_id: str,
    request: Request,
    payload: AssignmentTransitionInput | None = None,
    principal=Depends(require_permission("agents.write")),
):
    """Withdraw the assignment so the task can be given to somebody else.

    Cancelling the task itself stays the task manager's business; this closes the
    ledger row that said who would do it, which is what rule 2 requires before a
    reassignment.
    """
    agents = _agents(request)
    view = await agents.assignments.cancel(
        assignment_id, reason=(payload.reason if payload else ""),
        actor=principal.id, correlation_id=_correlation(request))
    return envelope(view.model_dump(mode="json"))
