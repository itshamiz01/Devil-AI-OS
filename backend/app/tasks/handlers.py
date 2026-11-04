from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field, ValidationError

from ..core.exceptions import AppError


class HandlerError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class NoopPayload(BaseModel):
    pass


class EchoPayload(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class WaitPayload(BaseModel):
    duration_ms: int = Field(default=100, ge=0, le=5000)


#: The six research stages P-03 can enqueue (§24). Kept in sync with
#: ``ResearchTaskSpec.stage``; a value outside this set is refused at submit time
#: rather than reaching the handler.
RESEARCH_STAGES = (
    "source_sweep",
    "market_sizing",
    "competitor_scan",
    "cost_verification",
    "demand_verification",
    "compliance_scan",
)


class ResearchSweepPayload(BaseModel):
    """Payload for a P-03 research task (§24).

    Carries no credentials and no host list: which sources may be contacted is
    decided by the engine's registry and network policy at execution time, so a
    task payload cannot widen the egress allowlist.
    """

    opportunity_id: str = Field(min_length=1, max_length=64)
    stage: str = Field(min_length=1, max_length=32)
    source_ids: tuple[str, ...] = ()
    query: str | None = Field(default=None, max_length=512)
    max_items: int = Field(default=25, ge=1, le=1000)


@dataclass
class ExecutionContext:
    task_id: str
    cancellation: asyncio.Event


@dataclass
class Handler:
    name: str
    payload_model: type[BaseModel]
    essential: bool
    retryable: bool
    execute: Callable[[BaseModel, ExecutionContext], Awaitable[dict[str, Any]]]


async def _noop(payload: BaseModel, ctx: ExecutionContext) -> dict:
    return {"ok": True, "handler": "system.noop"}


async def _echo(payload: EchoPayload, ctx: ExecutionContext) -> dict:
    return {"message": payload.message}


async def _wait(payload: WaitPayload, ctx: ExecutionContext) -> dict:
    remaining = payload.duration_ms
    while remaining > 0:
        if ctx.cancellation.is_set():
            raise asyncio.CancelledError()
        step = min(50, remaining)
        await asyncio.sleep(step / 1000)
        remaining -= step
    if ctx.cancellation.is_set():
        raise asyncio.CancelledError()
    return {"waited_ms": payload.duration_ms}


# --------------------------------------------------------------------------- #
# P-03 research handler (§24)
#
# A handler receives only its payload and an ExecutionContext, so it has no route
# to the opportunity engine. Rather than reach into application state implicitly,
# the engine is bound explicitly by the application lifespan and this handler
# fails loudly when it is not - an unbound research task must be a visible error,
# not a silently skipped one.
#
# Deciding *when* to research is P-12. This handler only executes a sweep that
# something else already decided to enqueue; it schedules nothing itself.
# --------------------------------------------------------------------------- #

_RESEARCH_BACKEND: dict[str, Any] = {}


def set_research_backend(services: Any) -> None:
    """Bind the P-03 subsystem so ``research.sweep`` tasks can execute."""
    _RESEARCH_BACKEND["services"] = services


def clear_research_backend() -> None:
    """Unbind on shutdown, so a stale engine cannot be used by a later lifespan."""
    _RESEARCH_BACKEND.clear()


async def _research_sweep(payload: ResearchSweepPayload, ctx: ExecutionContext) -> dict:
    services = _RESEARCH_BACKEND.get("services")
    if services is None:
        # Not retryable: nothing about retrying makes an unbound engine bound.
        raise HandlerError(
            "no opportunity engine is bound, so the research sweep could not run",
            retryable=False,
        )
    if payload.stage not in RESEARCH_STAGES:
        raise HandlerError(f"unknown research stage '{payload.stage}'", retryable=False)

    engine = services.engine
    try:
        record = engine.get(payload.opportunity_id)
    except KeyError as exc:
        raise HandlerError(str(exc), retryable=False) from None

    if ctx.cancellation.is_set():
        raise asyncio.CancelledError()

    if payload.stage == "source_sweep":
        # The sweep always completes. Reaching no source is a *result* - one refusal
        # per source attempted - not a failure, so it must not be retried into a
        # loop by the task manager.
        workflow = engine.research(record, query=payload.query, actor="task:research.sweep")
        refusals = [r for stage in workflow.stages for r in stage.refusals]
        return {
            "opportunity_id": payload.opportunity_id,
            "stage": payload.stage,
            "completed": workflow.completed,
            "halted_at": workflow.halted_at.value if workflow.halted_at else None,
            "halt_reason": workflow.halt_reason,
            "responses_obtained": sum(s.items_produced for s in workflow.stages),
            "evidence_extracted": workflow.total_evidence,
            "refusals": len(refusals),
            "refusal_categories": sorted({r.get("category", "unknown") for r in refusals}),
        }

    # The remaining stages analyse evidence already held; they acquire nothing, so
    # they are reported as not acquiring rather than pretending to have swept.
    engine.analyse(record, actor="task:research.sweep")
    outcome = record.outcome
    return {
        "opportunity_id": payload.opportunity_id,
        "stage": payload.stage,
        "completed": True,
        "responses_obtained": 0,
        "refusals": 0,
        "final_classification": (
            outcome.final_classification.value if outcome is not None else None
        ),
        "note": (
            "this stage analyses evidence already held; it performs no acquisition"
        ),
    }


HANDLERS: dict[str, Handler] = {
    "system.noop": Handler("system.noop", NoopPayload, True, True, _noop),
    "system.echo": Handler("system.echo", EchoPayload, False, True, _echo),
    "system.wait": Handler("system.wait", WaitPayload, False, True, _wait),
    # Not essential: research may be denied while the owner's emergency stop is
    # active, and it is not an owner-control, audit or recovery path.
    # Retryable: a transient acquisition error may succeed later, but a refusal is
    # a completed result rather than an error, so refusals never retry.
    "research.sweep": Handler(
        "research.sweep", ResearchSweepPayload, False, True, _research_sweep
    ),
}


def validate_payload(handler_name: str, payload: dict) -> dict:
    handler = HANDLERS.get(handler_name)
    if not handler:
        raise AppError("Unknown or disallowed task handler", {"handler": handler_name})
    try:
        validated = handler.payload_model.model_validate(payload)
    except ValidationError as exc:
        raise AppError("Invalid task payload", {"errors": exc.errors()}) from exc
    return validated.model_dump()
