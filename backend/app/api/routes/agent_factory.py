"""Agent Factory API (P-04 Stage 4).

Versioned under ``/api/v1/agent-factory``. Authorization is enforced per
operation:

* ``agents.factory.read``  — evaluate, read the creation ledger, read status
* ``agents.factory.admin`` — create an agent, drain the creation queue

Both derive into ``OWNER_PERMISSIONS`` and neither is in ``SYSTEM_PERMISSIONS``,
so the application can evaluate a creation but cannot authorize one for itself.
Deciding a gated creation is *not* exposed here: it goes through the central
approval endpoints under ``approvals.decide``, so there is one approval surface
in the system rather than a second one only agents know about.

Three disclosure rules shape every response.

* **``/evaluate`` writes nothing, and says so.** It returns ``recorded: false``.
  A preview that quietly left a row behind would make the ledger a record of
  questions asked rather than decisions taken.
* **A decision carries its checks.** Every response lists the checks that ran,
  in order, with the detail that decided each one. Evaluation stops at the first
  check that forces a decision, so a short list means an early decision, not a
  missing one — and ``REJECT`` without a reason is not an answer an owner can
  act on.
* **What is not yet governed is stated.** ``capability_catalog_checked`` is
  ``false`` until Stage 5 populates the catalog, and ``ASSIGN_EXISTING`` is never
  returned because assignment validation is Stage 6. Claiming either would be a
  false assurance about work that has not happened.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from ...agents.schemas import (
    AgentCreationRequestView,
    CreationEvaluationView,
    CreationRequestInput,
)
from ...core.exceptions import ConflictError, NotFoundError
from ...database.repositories import AgentCreationRequestRepo
from ..dependencies import get_services, require_permission
from ..schemas.common import envelope

router = APIRouter(prefix="/agent-factory", tags=["agents"])

#: Accepted filters for the ledger, kept explicit so an unknown value is refused
#: with a 422 rather than silently matching nothing.
_DECISIONS = ("CREATE_AGENT", "REUSE_EXISTING", "ASSIGN_EXISTING", "QUEUE",
              "REQUEST_OWNER_APPROVAL", "REJECT")
_APPROVAL_STATUSES = ("not_required", "pending", "granted", "rejected", "expired")


def _services(request: Request) -> Any:
    """The assembled subsystem, or a 409 that names the setting to change.

    ``AUTONOMUS_AGENTS_ENABLED=false`` leaves ``services.agents`` unassigned.
    Without this guard every operation below would fail with an AttributeError
    and reach the caller as a 500, which reports a server fault for what is a
    configuration choice.
    """
    services = get_services(request)
    if getattr(services, "agents", None) is None:
        raise ConflictError(
            "the agent subsystem is not enabled",
            details={"hint": "set AUTONOMUS_AGENTS_ENABLED=true"},
        )
    return services.agents


def _correlation(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


@router.post("/evaluate")
async def evaluate_creation(
    request: Request,
    payload: CreationRequestInput,
    principal=Depends(require_permission("agents.factory.read")),
):
    """Preview a decision without recording or executing it.

    Runs the same checks in the same order as ``/create``, so the answer is the
    answer — but nothing is written, no identity is minted and no approval is
    opened. ``recorded`` is false in the response to say so explicitly.
    """
    agents = _services(request)
    evaluation = await agents.factory.evaluate(payload)
    return envelope(CreationEvaluationView(**evaluation.as_dict()).model_dump(mode="json"))


@router.post("/create", status_code=201)
async def create_agent(
    request: Request,
    payload: CreationRequestInput,
    principal=Depends(require_permission("agents.factory.admin")),
):
    """Evaluate, record the decision, and carry it out.

    Returns 201 whether or not an agent resulted, because the resource created is
    the recorded decision: ``QUEUE``, ``REQUEST_OWNER_APPROVAL`` and ``REJECT``
    are outcomes, not failures, and reporting them as errors would train a caller
    to treat a refusal as a bug. The ``decision`` field says what happened.
    """
    agents = _services(request)
    evaluation = await agents.creation.create(
        payload, actor_id=principal.id, correlation_id=_correlation(request))
    return envelope(CreationEvaluationView(**evaluation.as_dict()).model_dump(mode="json"))


@router.get("/requests")
async def list_creation_requests(
    request: Request,
    decision: str | None = Query(None),
    approval_status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal=Depends(require_permission("agents.factory.read")),
):
    """The creation ledger, newest first."""
    _services(request)
    services = get_services(request)
    async with services.db.session_factory() as session:
        repo = AgentCreationRequestRepo(session)
        rows = await repo.list(limit, offset, decision=decision,
                               approval_status=approval_status)
        total = await repo.count(decision=decision, approval_status=approval_status)
    return envelope(
        [AgentCreationRequestView.from_row(r).model_dump(mode="json") for r in rows],
        limit=limit, offset=offset, total=total)


@router.get("/requests/{request_id}")
async def get_creation_request(
    request_id: str,
    request: Request,
    principal=Depends(require_permission("agents.factory.read")),
):
    """One recorded decision, including the reason for it."""
    _services(request)
    services = get_services(request)
    async with services.db.session_factory() as session:
        row = await AgentCreationRequestRepo(session).get(request_id)
    if row is None:
        raise NotFoundError("creation request not found")
    return envelope(AgentCreationRequestView.from_row(row).model_dump(mode="json"))


@router.post("/queue/drain")
async def drain_queue(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    principal=Depends(require_permission("agents.factory.admin")),
):
    """Re-evaluate queued requests, oldest first.

    Owner-invoked, never scheduled: autonomous scheduling is P-12, so nothing
    here runs on a timer. Each request is re-evaluated from scratch rather than
    executed on the strength of the decision that queued it, because the facts
    may have changed in either direction. The response reports every outcome, so
    a drain that created nothing is visibly a drain that created nothing.
    """
    agents = _services(request)
    result = await agents.creation.drain_queue(
        actor_id=principal.id, limit=limit, correlation_id=_correlation(request))
    return envelope({
        "swept": result["swept"],
        "considered": result["considered"],
        "outcomes": [CreationEvaluationView(**o).model_dump(mode="json")
                     for o in result["outcomes"]],
    })


@router.get("/status")
async def factory_status(
    request: Request,
    principal=Depends(require_permission("agents.factory.read")),
):
    """Registry and queue counts against the configured ceilings.

    Also reports what this stage does not do, so a caller cannot mistake an
    empty capability catalog for a checked one.
    """
    agents = _services(request)
    return envelope(await agents.factory.status())
