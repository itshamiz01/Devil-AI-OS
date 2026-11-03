"""P-03 §17 opportunity lifecycle.

The state machine lives in :mod:`app.opportunities.schemas` so that both this
module and the tests exercise one implementation of the rule.  What lives here is
the *history*: every transition is appended to an audit trail that is never
edited and never deleted, mirroring the append-only ``mission_history`` design
already accepted in P-02.

The initial-screening gate is here too, because it is the cheapest rejection in
the whole pipeline: a compliance block, a duplicate or a missing owner constraint
is detected before a single research source is contacted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.opportunities.risk import ComplianceScreen, RiskEngine
from app.opportunities.schemas import (
    BudgetConstraint,
    BusinessCategory,
    Opportunity,
    OpportunityCandidate,
    OpportunityState,
    RiskAssessment,
    ScreeningResult,
    TERMINAL_STATES,
    validate_opportunity_transition,
)

__all__ = [
    "HistoryEntry",
    "OpportunityLifecycle",
]


class HistoryEntry(BaseModel):
    """One append-only lifecycle record."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(default_factory=lambda: f"hist-{uuid4().hex[:12]}")
    opportunity_id: str
    from_state: OpportunityState | None = None
    to_state: OpportunityState
    reason: str = Field(min_length=1)
    actor: str = Field(default="system", min_length=1, max_length=120)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _no_secrets_in_reason(self) -> "HistoryEntry":
        lowered = self.reason.lower()
        for marker in ("api_key", "password", "bearer ", "authorization:", "secret="):
            if marker in lowered:
                raise ValueError(
                    "history reason appears to contain credential material and was rejected"
                )
        return self


class OpportunityLifecycle:
    """Transition enforcement plus an append-only history."""

    def __init__(self, *, risk_engine: RiskEngine | None = None):
        self._history: dict[str, list[HistoryEntry]] = {}
        self.risk = risk_engine or RiskEngine()
        self._screen = self.risk.screen

    # ------------------------------------------------------------------ #
    def history(self, opportunity_id: str) -> tuple[HistoryEntry, ...]:
        return tuple(self._history.get(opportunity_id, ()))

    def record(
        self,
        opportunity: Opportunity,
        target: OpportunityState,
        *,
        reason: str,
        actor: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[Opportunity, HistoryEntry]:
        """Transition an opportunity, or raise ``OpportunityTransitionError``.

        Returns a *new* Opportunity; the record passed in is never mutated, so a
        caller holding the pre-transition state can still compare against it.
        """
        validate_opportunity_transition(opportunity.state, target)
        entry = HistoryEntry(
            opportunity_id=opportunity.opportunity_id,
            from_state=opportunity.state,
            to_state=target,
            reason=reason,
            actor=actor,
            metadata=dict(metadata or {}),
        )
        updated = opportunity.model_copy(
            update={"state": target, "updated_at": datetime.now(timezone.utc)}
        )
        self._history.setdefault(opportunity.opportunity_id, []).append(entry)
        return updated, entry

    def is_terminal(self, opportunity: Opportunity) -> bool:
        return opportunity.state in TERMINAL_STATES

    def can_transition(self, opportunity: Opportunity, target: OpportunityState) -> bool:
        from app.opportunities.schemas import OPPORTUNITY_TRANSITIONS

        return target in OPPORTUNITY_TRANSITIONS[opportunity.state]

    def permitted_next(self, opportunity: Opportunity) -> tuple[OpportunityState, ...]:
        from app.opportunities.schemas import OPPORTUNITY_TRANSITIONS

        return tuple(sorted(OPPORTUNITY_TRANSITIONS[opportunity.state], key=lambda s: s.value))

    # ------------------------------------------------------------------ #
    def screen(
        self,
        candidate: OpportunityCandidate,
        *,
        budget: BudgetConstraint | None = None,
        jurisdictions: tuple[str, ...] = (),
        duplicate_of: str | None = None,
        existing_ids: tuple[str, ...] = (),
    ) -> ScreeningResult:
        """The §17 initial-screening gate: reject cheaply, before any research.

        Order matters and is deliberate - compliance first (a prohibited idea
        must never be researched at all), then duplication (do not spend effort
        twice), then the constraints the analysis cannot proceed without.
        """
        rejections: list[str] = []

        # 1. Compliance.  Cheapest and most decisive.
        findings = self._screen.scan_candidate(candidate)
        blocking = [f for f in findings if f.blocks_recommendation]
        if blocking:
            return ScreeningResult(
                compliance_blocked=True,
                rejections=tuple(f.description for f in blocking),
            )

        # 2. Duplication.
        if duplicate_of:
            if duplicate_of not in existing_ids and existing_ids:
                raise ValueError(
                    f"duplicate_of='{duplicate_of}' does not name a known opportunity"
                )
            return ScreeningResult(duplicate_of=duplicate_of)

        # 3. Constraints the analysis genuinely cannot proceed without.
        missing: list[str] = []
        if budget is None:
            missing.append("owner_budget")
        if not jurisdictions:
            # Not fatal to research, but fatal to a compliance verdict, so it is
            # recorded as a gap the owner can close cheaply.
            missing.append("target_jurisdiction")
        if not candidate.problem_addressed and not candidate.proposed_offering:
            missing.append("problem_or_offering")

        return ScreeningResult(missing_constraints=tuple(missing), rejections=tuple(rejections))

    def open_opportunity(
        self,
        candidate: OpportunityCandidate,
        *,
        budget: BudgetConstraint | None = None,
        actor: str = "system",
    ) -> tuple[Opportunity, HistoryEntry]:
        """Create the record and write its first history entry."""
        opportunity = Opportunity(candidate=candidate, budget=budget)
        entry = HistoryEntry(
            opportunity_id=opportunity.opportunity_id,
            from_state=None,
            to_state=OpportunityState.DISCOVERED,
            reason=(
                f"candidate '{candidate.title}' opened via the "
                f"{candidate.discovery_method.value} discovery method"
            ),
            actor=actor,
            metadata={
                "category": candidate.category.value,
                "candidate_id": candidate.candidate_id,
                "budget_band": budget.band.value if budget else None,
            },
        )
        self._history.setdefault(opportunity.opportunity_id, []).append(entry)
        return opportunity, entry

    def apply_screening(
        self,
        opportunity: Opportunity,
        result: ScreeningResult,
        *,
        actor: str = "system",
    ) -> tuple[Opportunity, HistoryEntry]:
        """Move a DISCOVERED opportunity through initial screening."""
        opportunity, entry = self.record(
            opportunity,
            OpportunityState.INITIAL_SCREENING,
            reason="entered initial screening",
            actor=actor,
        )
        reason = (
            "screening passed; proceeding to research"
            if result.passed
            else "; ".join(result.rejections)
            or "; ".join(f"missing: {m}" for m in result.missing_constraints)
            or f"duplicate of {result.duplicate_of}"
        )
        return self.record(
            opportunity,
            result.next_state,
            reason=reason,
            actor=actor,
            metadata={"screening_passed": result.passed},
        )

    def snapshot(self, opportunity_id: str) -> dict[str, Any]:
        entries = self.history(opportunity_id)
        return {
            "opportunity_id": opportunity_id,
            "transitions": len(entries),
            "current_state": entries[-1].to_state.value if entries else None,
            "terminal": entries[-1].to_state in TERMINAL_STATES if entries else False,
            "history": [
                {
                    "from": e.from_state.value if e.from_state else None,
                    "to": e.to_state.value,
                    "reason": e.reason,
                    "actor": e.actor,
                    "recorded_at": e.recorded_at.isoformat(),
                }
                for e in entries
            ],
        }
