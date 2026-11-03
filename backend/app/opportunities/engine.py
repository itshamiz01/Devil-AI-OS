"""P-03 opportunity discovery engine: the §20 workflow, end to end.

This is the orchestrator.  It owns the opportunity records, drives the workflow
stages in order, and produces the report.  Every analytical component lives in its
own module; the engine's job is sequencing and honest bookkeeping.

Three behaviours define it:

* **The pipeline always completes.**  A stage that obtains nothing records that
  fact and the workflow continues.  Halting would hide the reason an opportunity
  could not be evaluated, which is exactly what the owner needs to see.
* **Rejection is an output, not an exception.**  A compliance block, an
  unaffordable cost structure or contradicted demand ends the evaluation with a
  classification and a reason.  Nothing raises.
* **Refusals travel with the result.**  Every source that was asked and could not
  answer is carried through to the report, so "insufficient evidence" always comes
  with the reason it was insufficient.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.opportunities.analysis import (
    BusinessModelAnalyser,
    CompetitorAnalyser,
    DistributionAnalyser,
    MarketAnalyser,
)
from app.opportunities.commercial import CommercialFeasibilityEngine, CommercialInputs
from app.opportunities.discovery import DiscoveryContext, DiscoveryEngine, DiscoveryReport
from app.opportunities.evidence import EvidenceExtractor, EvidenceStore
from app.opportunities.governance import GovernanceAction, GovernanceGate
from app.opportunities.lifecycle import OpportunityLifecycle
from app.opportunities.reports import ReportGenerator
from app.opportunities.research import (
    ResearchScheduler,
    ResearchStage,
    StageResult,
    WorkflowReport,
    summarise_refusals,
)
from app.opportunities.risk import ComplianceScreen, RiskEngine
from app.opportunities.schemas import (
    BudgetConstraint,
    BusinessModelAnalysis,
    CompetitorAssessment,
    CommercialAssessment,
    CostStructure,
    DistributionAssessment,
    FinalClassification,
    MarketAssessment,
    Opportunity,
    OpportunityCandidate,
    OpportunityReport,
    OpportunityState,
    RiskAssessment,
    ScoringOutcome,
    ScreeningResult,
    SourceEvidence,
    ValidationLevel,
)
from app.opportunities.scoring import OpportunityScorer
from app.opportunities.sources import SourceRegistry
from app.opportunities.validation import ValidationEngine

__all__ = ["OpportunityEngine", "OpportunityRecord"]


class OpportunityRecord:
    """One opportunity plus everything learned about it."""

    def __init__(self, opportunity: Opportunity):
        self.opportunity = opportunity
        self.market: MarketAssessment | None = None
        self.competitors: CompetitorAssessment | None = None
        self.business_model: BusinessModelAnalysis | None = None
        self.commercial: CommercialAssessment | None = None
        self.distribution: DistributionAssessment | None = None
        self.risk: RiskAssessment | None = None
        self.outcome: ScoringOutcome | None = None
        self.workflow: WorkflowReport | None = None
        self.report: OpportunityReport | None = None
        self.screening: "ScreeningResult | None" = None

    @property
    def opportunity_id(self) -> str:
        return self.opportunity.opportunity_id

    def evidence_ids(self) -> tuple[str, ...]:
        return self.opportunity.evidence_ids


class OpportunityEngine:
    """Drives discovery, research, analysis, scoring, validation and reporting."""

    def __init__(
        self,
        *,
        registry: SourceRegistry | None = None,
        governance: GovernanceGate | None = None,
        weights: dict | None = None,
        task_manager: Any = None,
        minimum_validation_level: ValidationLevel = ValidationLevel.LEVEL_3_COMMERCIAL_EVIDENCE,
    ):
        self.registry = registry or SourceRegistry()
        self.governance = governance or GovernanceGate()
        self.evidence = EvidenceStore()
        self.extractor = EvidenceExtractor()
        self.lifecycle = OpportunityLifecycle()
        self.discovery = DiscoveryEngine()
        self.commercial_engine = CommercialFeasibilityEngine()
        self.market_analyser = MarketAnalyser()
        self.competitor_analyser = CompetitorAnalyser()
        self.model_analyser = BusinessModelAnalyser()
        self.distribution_analyser = DistributionAnalyser()
        self.risk_engine = RiskEngine()
        # Named compliance_screen, not screen: an instance attribute called
        # `screen` shadows the screen() method below, so `engine.screen(...)`
        # resolves to the ComplianceScreen object and raises TypeError.
        self.compliance_screen = ComplianceScreen()
        self.validation_engine = ValidationEngine()
        self.scorer = OpportunityScorer(weights)
        self.scheduler = ResearchScheduler(
            self.registry, task_manager=task_manager, governance=self.governance
        )
        self.reports = ReportGenerator()
        self.minimum_validation_level = minimum_validation_level
        self._records: dict[str, OpportunityRecord] = {}

    # ------------------------------------------------------------------ #
    # Discovery (§7)
    # ------------------------------------------------------------------ #
    def discover(self, context: DiscoveryContext) -> DiscoveryReport:
        decision = self.governance.authorize(GovernanceAction.PERMITTED_GENERATE_CANDIDATE)
        if not decision.permitted:  # pragma: no cover - defensive
            raise PermissionError(decision.reason)
        existing = tuple(
            r.opportunity.candidate.title for r in self._records.values()
        )
        enriched = context.model_copy(
            update={"existing_titles": tuple(set(context.existing_titles) | set(existing))}
        )
        return self.discovery.generate(enriched)

    # ------------------------------------------------------------------ #
    def open(
        self,
        candidate: OpportunityCandidate,
        *,
        budget: BudgetConstraint | None = None,
        actor: str = "owner",
    ) -> OpportunityRecord:
        opportunity, _ = self.lifecycle.open_opportunity(candidate, budget=budget, actor=actor)
        record = OpportunityRecord(opportunity)
        self._records[opportunity.opportunity_id] = record
        return record

    def restore(self, opportunity: Opportunity) -> OpportunityRecord:
        """Adopt a persisted opportunity after a restart.

        Visibility only.  The state, history and classification come back exactly
        as they were stored: nothing is re-researched, re-scored or re-recommended,
        and no sweep is dispatched.  Autonomous scheduling is P-12, so a restart
        must not silently resume work that was interrupted.
        """
        existing = self._records.get(opportunity.opportunity_id)
        if existing is not None:
            existing.opportunity = opportunity
            return existing
        record = OpportunityRecord(opportunity)
        self._records[opportunity.opportunity_id] = record
        return record

    def get(self, opportunity_id: str) -> OpportunityRecord:
        try:
            return self._records[opportunity_id]
        except KeyError:
            raise KeyError(f"opportunity '{opportunity_id}' is not known") from None

    def list_records(self) -> list[OpportunityRecord]:
        return sorted(self._records.values(), key=lambda r: r.opportunity_id)

    # ------------------------------------------------------------------ #
    def screen(
        self,
        record: OpportunityRecord,
        *,
        jurisdictions: Sequence[str] = (),
        duplicate_of: str | None = None,
        actor: str = "system",
    ):
        """§17 initial screening: the cheapest rejection in the pipeline."""
        result = self.lifecycle.screen(
            record.opportunity.candidate,
            budget=record.opportunity.budget,
            jurisdictions=tuple(jurisdictions),
            duplicate_of=duplicate_of,
            existing_ids=tuple(self._records),
        )
        record.screening = result
        record.opportunity, _ = self.lifecycle.apply_screening(
            record.opportunity, result, actor=actor
        )
        if not result.passed:
            record.opportunity = record.opportunity.model_copy(
                update={
                    "rejection_reasons": tuple(result.rejections)
                    or tuple(f"missing: {m}" for m in result.missing_constraints)
                    or (f"duplicate of {result.duplicate_of}",),
                    "final_classification": (
                        FinalClassification.REJECTED_COMPLIANCE
                        if result.compliance_blocked
                        else FinalClassification.INSUFFICIENT_EVIDENCE
                    ),
                }
            )
        return result

    # ------------------------------------------------------------------ #
    def _stage(
        self,
        stage: ResearchStage,
        summary: str,
        *,
        items: int = 0,
        refusals: Sequence[dict[str, Any]] = (),
        gaps: Sequence[str] = (),
        evidence_ids: Sequence[str] = (),
        started: datetime | None = None,
        skipped: str | None = None,
    ) -> StageResult:
        now = datetime.now(timezone.utc)
        if skipped is not None:
            return StageResult(stage=stage, executed=False, summary=summary, skipped_reason=skipped)
        return StageResult(
            stage=stage,
            executed=True,
            summary=summary,
            items_produced=items,
            refusals=tuple(refusals),
            data_gaps=tuple(gaps),
            evidence_ids=tuple(evidence_ids),
            started_at=started or now,
            finished_at=now,
        )

    def research(
        self,
        record: OpportunityRecord,
        *,
        query: str | None = None,
        operations: Sequence[str] = ("search",),
        actor: str = "system",
    ) -> WorkflowReport:
        """Run the acquisition stages and store whatever evidence is obtained.

        In a deployment with no reachable sources this produces an empty evidence
        set and a refusal for every source attempted.  That is the correct result,
        and it is recorded rather than worked around.
        """
        stages: list[StageResult] = []
        oid = record.opportunity_id
        started = datetime.now(timezone.utc)

        stages.append(
            self._stage(
                ResearchStage.INTAKE,
                f"opportunity '{record.opportunity.candidate.title}' accepted for research",
                items=1,
                started=started,
            )
        )
        screening = record.screening
        if screening is None:
            screening = self.screen(record)
        stages.append(
            self._stage(
                ResearchStage.INITIAL_SCREENING,
                "screening " + ("passed" if screening.passed else "did not pass"),
                items=1,
                gaps=tuple(screening.missing_constraints),
                started=started,
            )
        )
        if not screening.passed:
            report = WorkflowReport(
                opportunity_id=oid,
                stages=tuple(stages),
                completed=False,
                halted_at=ResearchStage.INITIAL_SCREENING,
                halt_reason=(
                    "; ".join(screening.rejections)
                    or "; ".join(f"missing: {m}" for m in screening.missing_constraints)
                    or f"duplicate of {screening.duplicate_of}"
                ),
                finished_at=datetime.now(timezone.utc),
            )
            record.workflow = report
            return report

        source_ids = tuple(self.scheduler.select_sources(include_unauthorized=True))
        stages.append(
            self._stage(
                ResearchStage.SOURCE_SELECTION,
                f"{len(source_ids)} registered source(s) selected for the sweep",
                items=len(source_ids),
                gaps=() if source_ids else ("no research source is registered",),
                started=started,
            )
        )

        all_refusals: list[dict[str, Any]] = []
        acquired = 0
        extracted_ids: list[str] = []
        for operation in operations:
            spec = self.scheduler.build_spec(
                oid, "source_sweep", source_ids=source_ids, query=query
            )
            results = self.scheduler.sweep(spec, operation=operation)
            all_refusals.extend(summarise_refusals(results))
            for sid, result in sorted(results.items()):
                if not result.ok or result.content is None:
                    continue
                acquired += 1
                descriptor = self.registry.get(sid)
                records = self.extractor.extract(
                    result.content, descriptor=descriptor, opportunity_id=oid
                )
                extracted_ids.extend(
                    r.evidence_id for r in self.evidence.add_all(records)
                )
        stages.append(
            self._stage(
                ResearchStage.ACQUISITION,
                f"{acquired} response(s) obtained, {len(all_refusals)} refusal(s)",
                items=acquired,
                refusals=tuple(all_refusals),
                gaps=()
                if acquired
                else ("no source returned content; no evidence could be extracted",),
                started=started,
            )
        )

        evidence = self.evidence.for_opportunity(oid)
        stages.append(
            self._stage(
                ResearchStage.EVIDENCE_EXTRACTION,
                f"{len(extracted_ids)} record(s) extracted from {acquired} response(s); "
                f"{len(evidence)} held for this opportunity",
                items=len(extracted_ids),
                gaps=()
                if extracted_ids
                else (
                    "no content was retrieved, so no evidence could be extracted; "
                    "the evidence set is empty and nothing has been inferred in its place"
                ),
                evidence_ids=tuple(dict.fromkeys(extracted_ids)),
                started=started,
            )
        )

        report = WorkflowReport(
            opportunity_id=oid,
            stages=tuple(stages),
            completed=True,
            finished_at=datetime.now(timezone.utc),
        )
        record.workflow = report
        return report

    # ------------------------------------------------------------------ #
    def analyse(
        self,
        record: OpportunityRecord,
        *,
        jurisdictions: Sequence[str] = (),
        platforms: Sequence[str] = (),
        costs: CostStructure | None = None,
        price_per_unit: Decimal | None = None,
        price_provenance: Any = None,
        base_units_monthly: Decimal | None = None,
        units_provenance: Any = None,
        competitor_gaps: Sequence[str] = (),
        differentiation_basis: str | None = None,
        channels: Sequence[Any] = (),
        revenue_mechanism: str | None = None,
        declared_validation_inputs: Sequence[str] = (),
        stated_capabilities: Sequence[str] = (),
        required_capabilities: Sequence[str] = (),
        actor: str = "system",
    ) -> OpportunityRecord:
        """Run every analysis stage and score the result."""
        oid = record.opportunity_id
        evidence = self.evidence.for_opportunity(oid)

        # Promote corroborated evidence before anything scores against it.
        self.evidence.corroborate(oid)
        self.evidence.mark_stale()
        evidence = self.evidence.for_opportunity(oid)

        record.market = self.market_analyser.analyse(evidence, geography=tuple(jurisdictions))
        record.competitors = self.competitor_analyser.analyse(
            evidence, gaps=tuple(competitor_gaps), differentiation_basis=differentiation_basis
        )
        record.business_model = self.model_analyser.derive(
            evidence, revenue_mechanism=revenue_mechanism
        )
        record.distribution = self.distribution_analyser.analyse(evidence, channels=tuple(channels))
        record.risk = self.risk_engine.assess(
            text=" ".join(
                filter(
                    None,
                    (
                        record.opportunity.candidate.title,
                        record.opportunity.candidate.description,
                        record.opportunity.candidate.problem_addressed,
                        record.opportunity.candidate.proposed_offering,
                    ),
                )
            ),
            category=record.opportunity.candidate.category,
            jurisdictions=tuple(jurisdictions),
            platforms=tuple(platforms),
        )

        if costs is not None:
            from app.opportunities.schemas import Provenance

            record.commercial = self.commercial_engine.assess(
                CommercialInputs(
                    costs=costs,
                    price_per_unit=price_per_unit,
                    price_provenance=price_provenance or Provenance.UNKNOWN,
                    base_units_monthly=base_units_monthly,
                    units_provenance=units_provenance or Provenance.UNKNOWN,
                    budget=record.opportunity.budget,
                )
            )
        else:
            record.commercial = None

        record.opportunity = record.opportunity.model_copy(
            update={
                "market": record.market.sizing if record.market else None,
                "competitors": record.competitors.competitors if record.competitors else (),
                "business_model": record.business_model,
                "costs": costs or CostStructure(),
                "scenarios": record.commercial.scenarios if record.commercial else (),
                "break_even": record.commercial.break_even if record.commercial else None,
                "budget_compatibility": (
                    record.commercial.budget_compatibility if record.commercial else None
                ),
                "distribution": record.distribution.channels if record.distribution else (),
                "risks": record.risk.findings if record.risk else (),
                "evidence_ids": tuple(e.evidence_id for e in evidence),
                "assumptions": record.commercial.assumptions if record.commercial else (),
            }
        )

        record.opportunity = record.opportunity.model_copy(
            update={
                "validation": self.validation_engine.determine(
                    evidence, declared_inputs=tuple(declared_validation_inputs)
                )
            }
        )

        record.outcome = self.scorer.score(
            market=record.market,
            competitors=record.competitors,
            business_model=record.business_model,
            commercial=record.commercial,
            distribution=record.distribution,
            risk=record.risk,
            validation=record.opportunity.validation,
            evidence=evidence,
            stated_capabilities=stated_capabilities,
            required_capabilities=required_capabilities,
            minimum_validation_level=self.minimum_validation_level,
        )
        record.opportunity = record.opportunity.model_copy(
            update={
                "score": record.outcome.score,
                "final_classification": record.outcome.final_classification,
            }
        )
        if record.outcome.hard_rejections:
            record.opportunity = record.opportunity.model_copy(
                update={
                    "rejection_reasons": tuple(
                        dict.fromkeys(
                            list(record.opportunity.rejection_reasons)
                            + list(record.outcome.hard_rejections)
                        )
                    )
                }
            )
        return record

    # ------------------------------------------------------------------ #
    def advance(
        self,
        record: OpportunityRecord,
        target: OpportunityState,
        *,
        reason: str,
        actor: str = "system",
    ) -> Opportunity:
        record.opportunity, _ = self.lifecycle.record(
            record.opportunity, target, reason=reason, actor=actor
        )
        return record.opportunity

    def report(self, record: OpportunityRecord, *, is_test_data: bool = True) -> OpportunityReport:
        """Generate the §23 report."""
        self.governance.authorize(GovernanceAction.PERMITTED_GENERATE_REPORT)
        refusals: list[dict[str, Any]] = []
        if record.workflow is not None:
            for stage in record.workflow.stages:
                refusals.extend(stage.refusals)
        evidence = self.evidence.for_opportunity(record.opportunity_id)
        report = self.reports.generate(
            record.opportunity,
            outcome=record.outcome,
            market=record.market,
            competitors=record.competitors,
            business_model=record.business_model,
            commercial=record.commercial,
            distribution=record.distribution,
            risk=record.risk,
            evidence=evidence,
            refusals=tuple(refusals),
            is_test_data=is_test_data,
        )
        record.report = report
        return report

    # ------------------------------------------------------------------ #
    def rank(self, records: Sequence[OpportunityRecord] | None = None) -> list[OpportunityRecord]:
        """Rank opportunities reproducibly (§16).

        Sorting is by the deterministic ranking key, then by opportunity id as a
        final tie-break, so the order never depends on insertion order, dict
        ordering or set iteration.
        """
        pool = list(records) if records is not None else self.list_records()
        scored = [r for r in pool if r.outcome is not None]
        unscored = [r for r in pool if r.outcome is None]
        scored.sort(key=lambda r: (r.outcome.score.ranking_key, r.opportunity_id))
        scored.reverse()  # highest attractiveness first
        unscored.sort(key=lambda r: r.opportunity_id)
        return scored + unscored

    def status(self) -> dict[str, Any]:
        records = self.list_records()
        by_state: dict[str, int] = {}
        by_classification: dict[str, int] = {}
        for record in records:
            by_state[record.opportunity.state.value] = (
                by_state.get(record.opportunity.state.value, 0) + 1
            )
            fc = record.opportunity.final_classification
            key = fc.value if fc else "unclassified"
            by_classification[key] = by_classification.get(key, 0) + 1
        return {
            "opportunities": len(records),
            "by_state": dict(sorted(by_state.items())),
            "by_final_classification": dict(sorted(by_classification.items())),
            "evidence_records": len(self.evidence.all()),
            "sources_registered": self.registry.snapshot()["registered"],
            "sources_authorized": self.registry.snapshot()["authorized"],
            "governance": self.governance.snapshot(),
            "scheduler": self.scheduler.snapshot(),
            "minimum_validation_level": self.minimum_validation_level.value,
            "weights_fingerprint": self.scorer.weights_fingerprint,
        }

