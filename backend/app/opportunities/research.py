"""P-03 §20 research workflow and §24 research scheduling.

The workflow is a fixed sequence of stages.  Each stage produces a
:class:`StageResult` recording what it did, what it obtained and what it could not
obtain.  A stage that acquires nothing is not a failed stage - it is a stage whose
result says "nothing was available", and the pipeline continues with an empty
evidence set.  That distinction is what allows the final report to say
"insufficient verified evidence" instead of quietly inventing a market.

§24 scheduling is deliberately limited: this module can *enqueue* research work on
the P-01 task manager and report what it enqueued.  Deciding autonomously when to
re-run research, and acting on that decision without the owner, is P-12 work and
is not implemented here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.opportunities.governance import GovernanceAction, GovernanceGate
from app.opportunities.schemas import (
    AcquisitionMethod,
    RetrievedContent,
    ResearchTaskSpec,
    SourceEvidence,
    SourceStatus,
    SourceType,
)
from app.opportunities.sources import FetchResult, RefusalCategory, SourceRegistry

__all__ = [
    "ResearchStage",
    "ResearchScheduler",
    "StageResult",
    "WorkflowReport",
    "WORKFLOW_STAGES",
]


class ResearchStage(str, Enum):
    """The §20 workflow stages, in execution order."""

    INTAKE = "intake"
    INITIAL_SCREENING = "initial_screening"
    SOURCE_SELECTION = "source_selection"
    ACQUISITION = "acquisition"
    EVIDENCE_EXTRACTION = "evidence_extraction"
    MARKET_ANALYSIS = "market_analysis"
    COMPETITOR_ANALYSIS = "competitor_analysis"
    BUSINESS_MODEL_ANALYSIS = "business_model_analysis"
    COMMERCIAL_ANALYSIS = "commercial_analysis"
    RISK_REVIEW = "risk_review"
    SCORING = "scoring"
    VALIDATION = "validation"
    REPORTING = "reporting"


WORKFLOW_STAGES: tuple[ResearchStage, ...] = tuple(ResearchStage)


class StageResult(BaseModel):
    """What one workflow stage did."""

    model_config = ConfigDict(extra="forbid")

    stage: ResearchStage
    executed: bool = False
    summary: str = Field(min_length=1)
    items_produced: int = 0
    refusals: tuple[dict[str, Any], ...] = ()
    data_gaps: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    started_at: datetime | None = None
    finished_at: datetime | None = None
    skipped_reason: str | None = None

    @model_validator(mode="after")
    def _executed_needs_times(self) -> "StageResult":
        if self.executed and (self.started_at is None or self.finished_at is None):
            raise ValueError("an executed stage must record start and finish times")
        if not self.executed and not self.skipped_reason:
            raise ValueError("a stage that did not execute must say why")
        if self.finished_at and self.started_at and self.finished_at < self.started_at:
            raise ValueError("a stage finished before it started")
        return self

    @property
    def duration_ms(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds() * 1000.0


class WorkflowReport(BaseModel):
    """The record of one complete workflow run."""

    model_config = ConfigDict(extra="forbid")

    opportunity_id: str
    stages: tuple[StageResult, ...] = ()
    completed: bool = False
    halted_at: ResearchStage | None = None
    halt_reason: str | None = None
    total_refusals: int = 0
    total_evidence: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def _totals(self) -> "WorkflowReport":
        object.__setattr__(
            self, "total_refusals", sum(len(s.refusals) for s in self.stages)
        )
        object.__setattr__(
            self, "total_evidence", sum(len(s.evidence_ids) for s in self.stages)
        )
        if self.completed and self.halted_at is not None:
            raise ValueError("a completed workflow cannot also be halted")
        return self

    def stage(self, stage: ResearchStage) -> StageResult | None:
        return next((s for s in self.stages if s.stage is stage), None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "completed": self.completed,
            "halted_at": self.halted_at.value if self.halted_at else None,
            "halt_reason": self.halt_reason,
            "stages_executed": sum(1 for s in self.stages if s.executed),
            "stages_total": len(self.stages),
            "total_refusals": self.total_refusals,
            "total_evidence": self.total_evidence,
            "stages": [
                {
                    "stage": s.stage.value,
                    "executed": s.executed,
                    "summary": s.summary,
                    "items_produced": s.items_produced,
                    "refusals": len(s.refusals),
                    "data_gaps": list(s.data_gaps),
                    "duration_ms": s.duration_ms,
                    "skipped_reason": s.skipped_reason,
                }
                for s in self.stages
            ],
        }


class ResearchScheduler:
    """§24 limited research scheduling on top of the P-01 task manager.

    This class builds task submissions and, when a task manager is supplied,
    hands them over.  It does not decide *when* to research: the caller decides.
    Autonomous scheduling is P-12.
    """

    def __init__(
        self,
        registry: SourceRegistry,
        *,
        task_manager: Any = None,
        governance: GovernanceGate | None = None,
    ):
        self.registry = registry
        self.tasks = task_manager
        self.governance = governance or GovernanceGate()
        self._submissions: list[dict[str, Any]] = []

    def select_sources(
        self,
        *,
        source_types: tuple[SourceType, ...] = (),
        include_unauthorized: bool = False,
    ) -> list[str]:
        """Pick the sources a research sweep should attempt.

        Unauthorised sources are included by default *for reporting purposes*:
        knowing that a needed source exists but is not configured is more useful
        than silently omitting it.  They will refuse at acquisition time, and that
        refusal is the finding.
        """
        chosen = []
        for descriptor in self.registry.list_sources():
            if source_types and descriptor.source_type not in source_types:
                continue
            if not include_unauthorized and descriptor.status is not SourceStatus.AUTHORIZED:
                continue
            chosen.append(descriptor.source_id)
        return sorted(chosen)

    def build_spec(
        self,
        opportunity_id: str,
        stage: str,
        *,
        source_ids: tuple[str, ...] = (),
        query: str | None = None,
        max_items: int = 25,
    ) -> ResearchTaskSpec:
        return ResearchTaskSpec(
            opportunity_id=opportunity_id,
            stage=stage,  # type: ignore[arg-type]
            source_ids=source_ids or tuple(self.select_sources(include_unauthorized=True)),
            query=query,
            max_items=max_items,
        )

    def sweep(
        self,
        spec: ResearchTaskSpec,
        *,
        operation: str = "search",
    ) -> dict[str, FetchResult]:
        """Run one acquisition sweep across the spec's sources.

        Governed: the sweep is an authorised action only if searching an
        authorised source is.  Nothing here can spend money, because the registry
        refuses any source whose acquisition would require payment.
        """
        decision = self.governance.authorize(
            GovernanceAction.PERMITTED_SEARCH_AUTHORIZED_SOURCE,
            detail=f"sweep {spec.stage} for {spec.opportunity_id}",
        )
        if not decision.permitted:  # pragma: no cover - defensive
            raise PermissionError(decision.reason)
        return self.registry.fetch_many(spec.source_ids, operation, {"query": spec.query or ""})

    def enqueue(self, spec: ResearchTaskSpec, *, principal_id: str) -> dict[str, Any]:
        """Hand a research task to the P-01 task manager.

        Returns a record of what was submitted.  When no task manager is wired the
        submission is recorded and reported as not dispatched - never silently
        presented as queued.
        """
        record = {
            "opportunity_id": spec.opportunity_id,
            "stage": spec.stage,
            "task_name": spec.task_name(),
            "handler": spec.handler(),
            "source_ids": list(spec.source_ids),
            "principal_id": principal_id,
            "dispatched": False,
            "task_id": None,
            "reason": None,
        }
        if self.tasks is None:
            record["reason"] = "no task manager is wired; the research task was not dispatched"
            self._submissions.append(record)
            return record
        try:
            task_id = self.tasks.submit(
                name=spec.task_name(),
                handler=spec.handler(),
                payload={
                    "opportunity_id": spec.opportunity_id,
                    "stage": spec.stage,
                    "source_ids": list(spec.source_ids),
                    "query": spec.query,
                    "max_items": spec.max_items,
                },
                principal_id=principal_id,
                priority=spec.priority,
                idempotency_key=f"{spec.opportunity_id}:{spec.stage}"[:128],
            )
            record["dispatched"] = True
            record["task_id"] = getattr(task_id, "task_id", task_id)
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            record["reason"] = f"{type(exc).__name__}: {exc}"[:400]
        self._submissions.append(record)
        return record

    def submissions(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._submissions)

    def snapshot(self) -> dict[str, Any]:
        return {
            "task_manager_wired": self.tasks is not None,
            "submissions": len(self._submissions),
            "dispatched": sum(1 for s in self._submissions if s["dispatched"]),
            "sources_available": len(self.select_sources(include_unauthorized=True)),
            "sources_authorized": len(self.select_sources()),
            "autonomous_scheduling": False,
            "autonomous_scheduling_note": (
                "research timing is decided by the caller; autonomous scheduling "
                "is P-12 and is not implemented in P-03"
            ),
        }


def summarise_refusals(results: dict[str, FetchResult]) -> tuple[dict[str, Any], ...]:
    """Flatten acquisition refusals into audit records."""
    out = []
    for source_id, result in sorted(results.items()):
        if result.ok:
            continue
        refusal = result.refusal
        assert refusal is not None
        out.append(
            {
                "source_id": source_id,
                "operation": refusal.operation,
                "category": refusal.category.value,
                "detail": refusal.detail,
                "retryable": refusal.retryable,
                "http_status": refusal.http_status,
            }
        )
    return tuple(out)


def successful_content(results: dict[str, FetchResult]) -> list[RetrievedContent]:
    return [r.content for r in results.values() if r.ok and r.content is not None]


def refusal_categories(results: dict[str, FetchResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results.values():
        if result.ok or result.refusal is None:
            continue
        key = result.refusal.category.value
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
