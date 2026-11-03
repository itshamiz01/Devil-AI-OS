"""Intelligence API (P-02 §14).

Backend conversation and intelligence interfaces for the future Command Center.
This is **not** a dashboard and must not be presented as one (§15 of P-01).

Authorization is enforced per operation, not per router:

* `intelligence.use`      — submit a request, create a mission, ask for a plan
* `intelligence.read`     — list/read missions, models, status, progress
* `intelligence.manage`   — approve, pause, cancel, replan
* `intelligence.autonomy` — change the autonomy level (owner only)

All four are derived into `OWNER_PERMISSIONS` and deliberately absent from
`SYSTEM_PERMISSIONS`, so the application can never reason about, re-plan or
re-authorize itself on its own authority.

Two disclosure rules shape every response here (§14): no provider credentials,
and no unrestricted provider configuration. Model records are returned without
their `configuration` dict, which is where a base URL or API key would live.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ...core.exceptions import ConflictError, NotFoundError
from ...intelligence.schemas import AutonomyLevel, MissionState
from ..dependencies import get_services, require_permission
from ..schemas.common import envelope

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


# --------------------------------------------------------------------------- #
# Request schemas
# --------------------------------------------------------------------------- #


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, max_length=64)


class AnalyzeRequest(BaseModel):
    """Untrusted external content to analyse as data (§12.4, §20 G)."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=20000)
    source: str = Field(min_length=1, max_length=256)
    mission_id: str | None = Field(default=None, max_length=36)


class MissionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, max_length=64)


class ReasonRequest(BaseModel):
    """A reason is mandatory for every state change, so the audit trail explains itself."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)


class ReplanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)
    #: Optional, because §9.6 forbids silently changing the owner's objective:
    #: a new objective must be supplied explicitly by the owner.
    new_objective: str | None = Field(default=None, max_length=500)


class AutonomyRequest(BaseModel):
    """Levels 3 and 4 are excluded by the Literal, so they cannot be requested."""

    model_config = ConfigDict(extra="forbid")

    level: Literal["0_advisory", "1_assisted_execution", "2_controlled_autonomy"]
    reason: str = Field(min_length=1, max_length=2000)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _services(request: Request) -> Any:
    services = get_services(request)
    if services.intelligence is None:
        # 409 rather than 503: the engine is deliberately disabled by
        # configuration, which is a conflict with the request, not an outage.
        raise ConflictError("The intelligence engine is disabled by configuration")
    return services


def _correlation(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


def _response(payload: Any) -> dict:
    """Convert an IntelligenceResponse into the standard envelope."""
    return envelope(payload.model_dump(mode="json"))


def _mission_view(record: Any) -> dict:
    """A mission plus its plan summaries and history."""
    mission = record.mission
    return {
        "mission": mission.model_dump(mode="json"),
        "plans": [
            {
                "plan_id": p.plan_id,
                "version": p.version,
                "status": p.status.value,
                "risk": p.risk.value,
                "steps": len(p.steps),
                "approval_required": p.approval_required,
                "revision_reason": p.revision_reason,
                "supersedes_plan_id": p.supersedes_plan_id,
            }
            for p in record.plans
        ],
        "history": list(record.history),
    }


def _require_record(services: Any, mission_id: str) -> Any:
    record = services.intelligence.engine.get_mission(mission_id)
    if record is None:
        raise NotFoundError(f"Mission {mission_id} does not exist")
    return record


# --------------------------------------------------------------------------- #
# Conversation and analysis
# --------------------------------------------------------------------------- #


@router.post("/chat")
async def chat(
    request: Request,
    body: ChatRequest,
    principal=Depends(require_permission("intelligence.use")),
):
    """Submit an owner message and receive a structured intelligence response."""
    services = _services(request)
    result = await services.intelligence.engine.process_request(
        body.message,
        principal_id=principal.id,
        conversation_id=body.conversation_id,
        correlation_id=_correlation(request),
    )
    await services.bus.publish_new(
        "MissionCreated" if result.mission_id and result.category.value == "execution_plan" else "DecisionRecorded",
        "intelligence",
        {"status": result.status.value, "category": result.category.value, "mission_id": result.mission_id},
        correlation_id=_correlation(request),
    )
    return _response(result)


@router.post("/analyze")
async def analyze(
    request: Request,
    body: AnalyzeRequest,
    principal=Depends(require_permission("intelligence.use")),
):
    """Analyse untrusted external content as data, never as instructions."""
    services = _services(request)
    result = services.intelligence.engine.analyse_untrusted(
        body.content,
        source=body.source,
        principal_id=principal.id,
        mission_id=body.mission_id,
        correlation_id=_correlation(request),
    )
    if result.data.get("findings"):
        # §20 G: record a security event when an injection attempt is detected.
        await services.bus.publish_new(
            "PromptInjectionDetected",
            "intelligence",
            {
                "source": body.source,
                "kinds": [f["kind"] for f in result.data["findings"]],
                "principal_id": principal.id,
            },
            severity="warning",
            correlation_id=_correlation(request),
        )
    return _response(result)


# --------------------------------------------------------------------------- #
# Missions
# --------------------------------------------------------------------------- #


@router.post("/missions")
async def create_mission(
    request: Request,
    body: MissionCreateRequest,
    principal=Depends(require_permission("intelligence.use")),
):
    """Interpret a request and, if it warrants one, create a mission."""
    services = _services(request)
    result = await services.intelligence.engine.process_request(
        body.request,
        principal_id=principal.id,
        conversation_id=body.conversation_id,
        correlation_id=_correlation(request),
    )
    if result.mission_id:
        record = _require_record(services, result.mission_id)
        await services.bus.publish_new(
            "MissionCreated", "intelligence",
            {
                "mission_id": result.mission_id,
                "state": record.mission.state.value,
                "risk": record.mission.risk.value,
                "classification": record.mission.classification.value,
            },
            correlation_id=_correlation(request),
        )
    return _response(result)


@router.get("/missions")
async def list_missions(
    request: Request,
    principal=Depends(require_permission("intelligence.read")),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    state: str | None = Query(default=None, max_length=32),
):
    """List the caller's missions, paginated and optionally filtered by state."""
    services = _services(request)
    missions = services.intelligence.engine.list_missions(principal_id=principal.id)
    if state:
        # Filtering on an unknown state yields nothing rather than an error, but
        # an invalid enum value is rejected so a typo is visible.
        try:
            wanted = MissionState(state).value
        except ValueError:
            raise NotFoundError(f"Unknown mission state {state!r}") from None
        missions = [m for m in missions if m.state.value == wanted]
    total = len(missions)
    page = missions[offset: offset + limit]
    return envelope(
        [m.model_dump(mode="json") for m in page],
        total=total, limit=limit, offset=offset, returned=len(page),
    )


@router.get("/missions/{mission_id}")
async def get_mission(
    mission_id: str,
    request: Request,
    principal=Depends(require_permission("intelligence.read")),
):
    services = _services(request)
    record = _require_record(services, mission_id)
    return envelope(_mission_view(record))


@router.get("/missions/{mission_id}/progress")
async def mission_progress(
    mission_id: str,
    request: Request,
    principal=Depends(require_permission("intelligence.read")),
):
    """Progress derived from real task states, never narrated by a model (§11.4)."""
    services = _services(request)
    _require_record(services, mission_id)
    result = await services.intelligence.engine.monitor_mission(mission_id, principal_id=principal.id)
    return _response(result)


@router.post("/missions/{mission_id}/plan")
async def plan_mission(
    mission_id: str,
    request: Request,
    principal=Depends(require_permission("intelligence.use")),
):
    """Generate a plan for review. Launches nothing (§20 B)."""
    services = _services(request)
    _require_record(services, mission_id)
    result = await services.intelligence.engine.generate_plan(
        mission_id, principal_id=principal.id, correlation_id=_correlation(request)
    )
    event = "PlanRejected" if result.status.value == "blocked" else "PlanGenerated"
    await services.bus.publish_new(
        event, "intelligence",
        {"mission_id": mission_id, "plan_id": result.data.get("plan_id"), "status": result.status.value},
        severity="warning" if event == "PlanRejected" else "info",
        correlation_id=_correlation(request),
    )
    return _response(result)


@router.post("/missions/{mission_id}/approve")
async def approve_mission(
    mission_id: str,
    request: Request,
    body: ReasonRequest,
    principal=Depends(require_permission("intelligence.manage")),
):
    """Owner approval of a plan.

    Approval authorizes execution *if the autonomy level permits it*. At the
    default advisory level nothing is dispatched, and the response says so
    plainly rather than implying the work has started (§15, §16).
    """
    services = _services(request)
    record = _require_record(services, mission_id)
    engine = services.intelligence.engine

    # PLANNING is accepted as well as AWAITING_APPROVAL. A low-risk plan that
    # needs no approval still has to be authorized by someone before anything
    # runs: the owner calling this endpoint is that authorization, and §16 keeps
    # "authorized decision" distinct from "executable task". MISSION_TRANSITIONS
    # already permits PLANNING -> APPROVED.
    approvable = {MissionState.AWAITING_APPROVAL, MissionState.PLANNING}
    if record.mission.state not in approvable:
        raise ConflictError(
            f"Mission is {record.mission.state.value}; only "
            f"{', '.join(sorted(s.value for s in approvable))} can be approved"
        )
    required_approval = record.mission.state == MissionState.AWAITING_APPROVAL
    _transition(engine, mission_id, MissionState.APPROVED, principal_id=principal.id, reason=body.reason)
    await services.bus.publish_new(
        "MissionStateChanged", "intelligence",
        {"mission_id": mission_id, "to": MissionState.APPROVED.value, "by": principal.id},
        correlation_id=_correlation(request),
    )

    await _persist(engine, mission_id)

    autonomy = services.intelligence.autonomy
    dispatched: list[dict] = []
    if not autonomy.may_submit_tasks():
        return envelope({
            "mission_id": mission_id,
            "state": MissionState.APPROVED.value,
            "dispatched": [],
            "autonomy_level": autonomy.level.value,
            "message": (
                "The plan is approved, but the current autonomy level is advisory and "
                "may not submit execution tasks. Raise the level (owner-authorized) to "
                "permit dispatch."
            ),
            "approval_was_required": required_approval,
        })

    plan = record.active_plan
    if plan is None:
        raise ConflictError("The mission has no plan to dispatch")
    updated, records = await engine.orchestrator.execute_plan(
        record.mission, plan, principal_id=principal.id, correlation_id=_correlation(request)
    )
    engine._replace_plan(record, updated)
    _transition(
        engine, mission_id, MissionState.EXECUTING, principal_id=principal.id,
        reason="approved plan dispatched through the P-01 task manager",
    )
    # Persisted after dispatch so the recorded task ids survive a restart.
    await _persist(engine, mission_id)
    dispatched = [
        {
            "step_id": r.step_id, "task_id": r.task_id, "capability": r.capability_id,
            "handler": r.handler, "in_process": r.in_process, "refused": r.refused_reason,
        }
        for r in records
    ]
    await services.bus.publish_new(
        "TaskDispatched", "intelligence",
        {"mission_id": mission_id, "plan_id": plan.plan_id, "dispatched": len(records)},
        correlation_id=_correlation(request),
    )
    return envelope({
        "mission_id": mission_id,
        "state": MissionState.EXECUTING.value,
        "dispatched": dispatched,
        "autonomy_level": autonomy.level.value,
        "message": f"{len([d for d in dispatched if d['task_id']])} task(s) submitted through the P-01 task manager.",
        "approval_was_required": required_approval,
    })


@router.post("/missions/{mission_id}/pause")
async def pause_mission(
    mission_id: str,
    request: Request,
    body: ReasonRequest,
    principal=Depends(require_permission("intelligence.manage")),
):
    services = _services(request)
    record = _require_record(services, mission_id)
    engine = services.intelligence.engine
    _transition(engine, mission_id, MissionState.PAUSED, principal_id=principal.id, reason=body.reason)
    await _persist(engine, mission_id)
    paused = await _apply_to_dispatched_tasks(services, record, principal.id, action="pause")
    await services.bus.publish_new(
        "MissionStateChanged", "intelligence",
        {"mission_id": mission_id, "to": MissionState.PAUSED.value, "tasks_affected": len(paused)},
        correlation_id=_correlation(request),
    )
    return envelope({"mission_id": mission_id, "state": MissionState.PAUSED.value, "tasks_paused": paused})


@router.post("/missions/{mission_id}/cancel")
async def cancel_mission(
    mission_id: str,
    request: Request,
    body: ReasonRequest,
    principal=Depends(require_permission("intelligence.manage")),
):
    services = _services(request)
    record = _require_record(services, mission_id)
    engine = services.intelligence.engine
    _transition(engine, mission_id, MissionState.CANCELLED, principal_id=principal.id, reason=body.reason)
    await _persist(engine, mission_id)
    cancelled = await _apply_to_dispatched_tasks(services, record, principal.id, action="cancel")
    await services.bus.publish_new(
        "MissionStateChanged", "intelligence",
        {"mission_id": mission_id, "to": MissionState.CANCELLED.value, "tasks_affected": len(cancelled)},
        correlation_id=_correlation(request),
    )
    return envelope({"mission_id": mission_id, "state": MissionState.CANCELLED.value, "tasks_cancelled": cancelled})


@router.post("/missions/{mission_id}/replan")
async def replan_mission(
    mission_id: str,
    request: Request,
    body: ReplanRequest,
    principal=Depends(require_permission("intelligence.manage")),
):
    """Revise a plan, preserving the previous version and the reason (§9.6)."""
    services = _services(request)
    _require_record(services, mission_id)
    result = await services.intelligence.engine.revise_plan(
        mission_id, reason=body.reason, principal_id=principal.id, new_objective=body.new_objective
    )
    await services.bus.publish_new(
        "PlanRevised" if result.status.value == "ok" else "PlanRejected",
        "intelligence",
        {
            "mission_id": mission_id,
            "version": result.data.get("version"),
            "reason": body.reason,
        },
        correlation_id=_correlation(request),
    )
    return _response(result)


def _transition(engine: Any, mission_id: str, target: MissionState, *, principal_id: str, reason: str) -> None:
    """Request a mission state change, turning an illegal one into a 409.

    The state machine raises ValueError for a transition it does not permit. That
    is a client-visible condition — cancelling an already-cancelled mission, for
    example — and must not surface as an unhandled 500.
    """
    try:
        engine.transition_mission(mission_id, target, principal_id=principal_id, reason=reason)
    except ValueError as exc:
        raise ConflictError(str(exc)) from exc


async def _persist(engine: Any, mission_id: str) -> None:
    """Persist after a synchronous state change.

    `transition_mission` and `_replace_plan` are synchronous, so the persistence
    decorator on the engine's coroutines does not cover them. Without this a
    pause, cancel or approval would be lost on restart while the mission that
    created them survived.
    """
    await engine.persist_mission(mission_id)


async def _apply_to_dispatched_tasks(services: Any, record: Any, principal_id: str, *, action: str) -> list[str]:
    """Pause or cancel the tasks a mission already dispatched.

    Failures on individual tasks are collected rather than raised: a mission
    pause should not abort because one task already reached a terminal state.
    """
    affected: list[str] = []
    plan = record.active_plan
    if plan is None:
        return affected
    for step in plan.steps:
        if not step.task_id or step.status.value in {"COMPLETED", "CANCELLED", "SKIPPED"}:
            continue
        try:
            if action == "pause":
                await services.tasks.pause(principal_id, step.task_id)
            else:
                await services.tasks.cancel(principal_id, step.task_id)
            affected.append(step.task_id)
        except Exception:  # noqa: BLE001 - terminal tasks cannot transition
            continue
    return affected


# --------------------------------------------------------------------------- #
# Models, status and autonomy
# --------------------------------------------------------------------------- #


@router.get("/models")
async def list_models(
    request: Request,
    principal=Depends(require_permission("intelligence.read")),
):
    """Registered models and their health.

    The `configuration` field is deliberately omitted: it is where a provider
    base URL or credential would live, and §14 forbids exposing provider
    configuration through API responses.
    """
    services = _services(request)
    registry = services.intelligence.registry
    return envelope([
        {
            "model_id": r.model_id,
            "provider": r.provider,
            "local": r.local,
            "available": r.available,
            "healthy": registry.is_healthy(r.model_id),
            "capabilities": r.capabilities.model_dump(mode="json"),
            "cost_per_1k_tokens": r.cost_per_1k_tokens,
            "limitations": r.limitations,
        }
        for r in registry.all()
    ])


@router.get("/status")
async def intelligence_status(
    request: Request,
    principal=Depends(require_permission("intelligence.read")),
):
    services = _services(request)
    return envelope(services.intelligence.engine.status())


@router.post("/autonomy")
async def change_autonomy(
    request: Request,
    body: AutonomyRequest,
    principal=Depends(require_permission("intelligence.autonomy")),
):
    """Change the autonomy level. Owner-only by permission (§15).

    `authorized_by_owner` is established here by the permission check having
    passed for `intelligence.autonomy`, which only the owner holds. It is never
    taken from the request body — a model or an agent could otherwise assert it.
    """
    services = _services(request)
    autonomy = services.intelligence.autonomy
    previous = autonomy.level
    state = autonomy.request_change(
        AutonomyLevel(body.level),
        principal_id=principal.id,
        authorized_by_owner=True,
        reason=body.reason,
    )
    await services.bus.publish_new(
        "AutonomyLevelChanged", "intelligence",
        {"from": previous.value, "to": state.level.value, "by": principal.id, "reason": body.reason},
        severity="warning",
        correlation_id=_correlation(request),
    )
    return envelope(autonomy.describe())
