"""Persistence for the P-03 opportunity tables (§21).

Follows the P-02 repository convention exactly: a ``_x_values(model)`` mapping for
writes, a ``_to_x(row)`` constructor for reads, and upsert-by-primary-key saves
through ``Database.session_factory``.  No independent database infrastructure, and
no schema of its own.

Decimals cross the boundary as exact text.  ``_dec`` writes and ``_num`` reads, so
money never touches a float: SQLite would otherwise store a Numeric column as REAL
and silently change the §13 arithmetic between a write and a read.

:func:`verify_mapping_completeness` diffs every pydantic field against the columns
actually written for it.  A field with no column makes persistence silently lossy
- the object saves, reads back, and quietly lacks data - so that diff is a checked
invariant rather than something to discover in production.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select

from app.database.connection import Database
from app.database.models import (
    CommercialAnalysis,
    CompetitorRecord,
    MarketAnalysis,
    Opportunity,
    OpportunityCandidate,
    OpportunityHistory,
    OpportunityReportRecord,
    OpportunityScoreRecord,
    ResearchSource,
    ResearchSweep,
    RiskFindingRecord,
    SourceEvidenceRecord,
    new_id,
)
from app.opportunities import schemas as _schemas
from app.opportunities.schemas import (
    Assumption,
    BreakEvenResult,
    BudgetCompatibility,
    BudgetConstraint,
    BusinessModelAnalysis,
    CompetitorAssessment,
    CompetitorProfile,
    CommercialAssessment,
    CostStructure,
    DistributionChannel,
    FinalClassification,
    MarketAssessment,
    MarketSizing,
    Opportunity as OpportunitySchema,
    OpportunityCandidate as CandidateSchema,
    OpportunityReport,
    OpportunityScore,
    RiskAssessment,
    RiskFinding,
    ScenarioProjection,
    ScoringOutcome,
    SourceDescriptor,
    SourceEvidence,
    ValidationAssessment,
)

__all__ = ["OpportunityRepository", "verify_mapping_completeness", "MAPPING_GAPS"]


def _dec(value: Any) -> str | None:
    """Exact decimal text for storage.  ``None`` stays ``None`` - never ``"0"``."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    return str(Decimal(str(value)))


def _num(text: Any) -> Decimal | None:
    """Parse stored decimal text.  A malformed value is refused, not defaulted."""
    if text is None or text == "":
        return None
    try:
        return Decimal(str(text))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"stored value {text!r} is not a valid decimal") from exc


def _enum(value: Any) -> str | None:
    return None if value is None else getattr(value, "value", str(value))


def _list(value: Any) -> list[Any]:
    return [] if value is None else list(value)


def _dict(value: Any) -> dict[str, Any]:
    return {} if value is None else dict(value)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OpportunityRepository:
    """Reads and writes the P-03 opportunity tables."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Candidates (§7)
    # ------------------------------------------------------------------ #
    def _candidate_values(self, candidate: CandidateSchema) -> dict[str, Any]:
        return {
            "title": candidate.title[:200],
            "description": candidate.description,
            "category": _enum(candidate.category),
            "discovery_method": _enum(candidate.discovery_method),
            "derived_from": (candidate.derived_from or "")[:256] or None,
            "target_customer": candidate.target_customer,
            "problem_addressed": candidate.problem_addressed,
            "proposed_offering": candidate.proposed_offering,
            "budget_band": _enum(candidate.budget_band),
            # A Literal[str], not an enum: passing it through _enum() worked by
            # accident, but naming the type correctly keeps the reader honest.
            "generated_by": candidate.generated_by or "deterministic_rule",
            "duplicate_of": candidate.duplicate_of,
            "generated_at": candidate.generated_at,
        }

    def _to_candidate(self, row: OpportunityCandidate) -> CandidateSchema:
        from app.opportunities.schemas import (
            BusinessCategory,
            BudgetBand,
            DiscoveryMethod,
        )

        return CandidateSchema(
            candidate_id=row.candidate_id,
            title=row.title,
            description=row.description,
            category=BusinessCategory(row.category),
            discovery_method=DiscoveryMethod(row.discovery_method),
            derived_from=row.derived_from,
            target_customer=row.target_customer,
            problem_addressed=row.problem_addressed,
            proposed_offering=row.proposed_offering,
            budget_band=BudgetBand(row.budget_band) if row.budget_band else None,
            generated_by=row.generated_by or "deterministic_rule",
            duplicate_of=row.duplicate_of,
            generated_at=row.generated_at,
        )

    async def save_candidate(self, candidate: CandidateSchema) -> None:
        async with self.db.session_factory() as session:
            row = (
                await session.execute(
                    select(OpportunityCandidate).where(
                        OpportunityCandidate.candidate_id == candidate.candidate_id
                    )
                )
            ).scalar_one_or_none()
            values = self._candidate_values(candidate)
            if row is None:
                session.add(OpportunityCandidate(id=new_id(), candidate_id=candidate.candidate_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            await session.commit()

    # ------------------------------------------------------------------ #
    # Opportunities (§17)
    #
    # The aggregate is split across tables: the opportunity row holds identity,
    # state, budget and the fields with no analysis table of their own, while the
    # market, competitor, commercial, risk and scoring results live in their own
    # tables.  `load_opportunity` reassembles the whole object, so nothing that was
    # written is silently absent on read.
    # ------------------------------------------------------------------ #
    def _opportunity_values(self, opportunity: OpportunitySchema) -> dict[str, Any]:
        budget = opportunity.budget
        return {
            # Not a schema field: derived from the embedded candidate so it cannot
            # drift from the candidate that was actually stored.
            "candidate_id": opportunity.candidate.candidate_id,
            "title": opportunity.candidate.title[:200],
            "category": _enum(opportunity.candidate.category),
            "discovery_method": _enum(opportunity.candidate.discovery_method),
            "state": _enum(opportunity.state),
            "final_classification": _enum(opportunity.final_classification),
            # Opportunity has no `recommendable` field.  It is derived from the
            # classification, because two columns that can disagree about whether
            # to recommend would be worse than one.
            "recommendable": opportunity.final_classification
            is FinalClassification.RECOMMENDED,
            "budget_available_capital": _dec(budget.available_capital) if budget else None,
            "budget_currency": budget.currency if budget else None,
            "budget_band": _enum(budget.band) if budget else None,
            "budget_owner_stated": bool(budget.owner_stated) if budget else True,
            "validation_level": opportunity.validation.level.value,
            "evidence_ids": _list(opportunity.evidence_ids),
            "rejection_reasons": _list(opportunity.rejection_reasons),
            # Assumption objects, not strings: a JSON column cannot hold a model.
            "assumptions": [a.model_dump(mode="json") for a in opportunity.assumptions],
            "business_model": (
                opportunity.business_model.model_dump(mode="json")
                if opportunity.business_model
                else {}
            ),
            "distribution": [d.model_dump(mode="json") for d in opportunity.distribution],
            "owner_notes": opportunity.owner_notes,
        }

    def _to_opportunity(
        self,
        row: Opportunity,
        candidate: CandidateSchema,
        *,
        market: MarketSizing | None = None,
        competitors: Sequence[CompetitorProfile] = (),
        costs: CostStructure | None = None,
        scenarios: Sequence[ScenarioProjection] = (),
        break_even: BreakEvenResult | None = None,
        budget_compatibility: BudgetCompatibility | None = None,
        risks: Sequence[RiskFinding] = (),
        score: OpportunityScore | None = None,
    ) -> OpportunitySchema:
        from app.opportunities.schemas import OpportunityState

        budget = None
        if row.budget_available_capital is not None:
            budget = BudgetConstraint(
                available_capital=_num(row.budget_available_capital),
                currency=row.budget_currency or "USD",
                band=row.budget_band,
                owner_stated=bool(row.budget_owner_stated),
            )
        return OpportunitySchema(
            opportunity_id=row.opportunity_id,
            candidate=candidate,
            state=OpportunityState(row.state),
            budget=budget,
            market=market,
            competitors=tuple(competitors),
            business_model=(
                BusinessModelAnalysis.model_validate(row.business_model)
                if row.business_model
                else None
            ),
            costs=costs or CostStructure(),
            scenarios=tuple(scenarios),
            break_even=break_even,
            budget_compatibility=budget_compatibility,
            distribution=tuple(
                DistributionChannel.model_validate(d) for d in (row.distribution or ())
            ),
            risks=tuple(risks),
            score=score,
            validation=ValidationAssessment(level=row.validation_level or 0),
            assumptions=tuple(
                Assumption.model_validate(a) for a in (row.assumptions or ())
            ),
            evidence_ids=tuple(row.evidence_ids or ()),
            rejection_reasons=tuple(row.rejection_reasons or ()),
            final_classification=(
                FinalClassification(row.final_classification)
                if row.final_classification
                else None
            ),
            owner_notes=row.owner_notes,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def save_opportunity(self, opportunity: OpportunitySchema) -> None:
        await self.save_candidate(opportunity.candidate)
        async with self.db.session_factory() as session:
            row = (
                await session.execute(
                    select(Opportunity).where(
                        Opportunity.opportunity_id == opportunity.opportunity_id
                    )
                )
            ).scalar_one_or_none()
            values = self._opportunity_values(opportunity)
            if row is None:
                session.add(
                    Opportunity(id=new_id(), opportunity_id=opportunity.opportunity_id, **values)
                )
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            await session.commit()

    async def _opportunity_row(self, session: Any, opportunity_id: str) -> Opportunity | None:
        return (
            await session.execute(
                select(Opportunity).where(Opportunity.opportunity_id == opportunity_id)
            )
        ).scalar_one_or_none()

    async def _candidate_row(self, session: Any, candidate_id: str) -> OpportunityCandidate | None:
        return (
            await session.execute(
                select(OpportunityCandidate).where(
                    OpportunityCandidate.candidate_id == candidate_id
                )
            )
        ).scalar_one_or_none()

    async def load_opportunity(
        self, opportunity_id: str, *, include_analyses: bool = True
    ) -> OpportunitySchema | None:
        async with self.db.session_factory() as session:
            row = await self._opportunity_row(session, opportunity_id)
            if row is None:
                return None
            cand = await self._candidate_row(session, row.candidate_id)
            if cand is None:  # pragma: no cover - would mean a broken write
                raise ValueError(
                    f"opportunity '{opportunity_id}' references a missing candidate"
                )
            candidate = self._to_candidate(cand)
            if not include_analyses:
                return self._to_opportunity(row, candidate)
            market_row = await self._one(session, MarketAnalysis, opportunity_id)
            comm_row = await self._one(session, CommercialAnalysis, opportunity_id)
            score_row = await self._one(session, OpportunityScoreRecord, opportunity_id)
            competitor_rows = (
                await session.execute(
                    select(CompetitorRecord).where(
                        CompetitorRecord.opportunity_id == opportunity_id
                    )
                )
            ).scalars().all()
            risk_rows = (
                await session.execute(
                    select(RiskFindingRecord).where(
                        RiskFindingRecord.opportunity_id == opportunity_id
                    )
                )
            ).scalars().all()

            market = None
            if market_row is not None and market_row.sizing:
                market = MarketSizing.model_validate(market_row.sizing)
            competitors = tuple(self._to_profile(r) for r in competitor_rows)
            scenarios: list[ScenarioProjection] = []
            costs = None
            break_even = None
            budget_compatibility = None
            if comm_row is not None:
                costs = CostStructure.model_validate(comm_row.costs or {})
                scenarios = [
                    ScenarioProjection.model_validate(s) for s in (comm_row.scenarios or ())
                ]
                if comm_row.break_even:
                    break_even = BreakEvenResult.model_validate(comm_row.break_even)
                if comm_row.budget_compatibility:
                    budget_compatibility = BudgetCompatibility.model_validate(
                        comm_row.budget_compatibility
                    )
            risks = tuple(self._to_finding(r) for r in risk_rows)
            score = self._to_score(score_row) if score_row is not None else None
            return self._to_opportunity(
                row,
                candidate,
                market=market,
                competitors=competitors,
                costs=costs,
                scenarios=scenarios,
                break_even=break_even,
                budget_compatibility=budget_compatibility,
                risks=risks,
                score=score,
            )

    async def _one(self, session: Any, model: Any, opportunity_id: str) -> Any:
        return (
            await session.execute(
                select(model).where(model.opportunity_id == opportunity_id)
            )
        ).scalar_one_or_none()

    def _to_profile(self, row: CompetitorRecord) -> CompetitorProfile:
        return CompetitorProfile(
            competitor_id=row.competitor_id,
            name=row.name,
            url=row.url,
            offering=row.offering,
            positioning=row.positioning,
            price_points=tuple(_num(p) for p in (row.price_points or ()) if p is not None),
            price_currency=row.price_currency or "USD",
            pricing_provenance=row.pricing_provenance or "unknown",
            rating=_num(row.rating),
            review_count=row.review_count,
            rating_provenance=row.rating_provenance or "unknown",
            strengths=tuple(row.strengths or ()),
            weaknesses=tuple(row.weaknesses or ()),
            complaint_themes=tuple(row.complaint_themes or ()),
            identified_gaps=tuple(row.identified_gaps or ()),
            evidence_ids=tuple(row.evidence_ids or ()),
            observed_at=row.observed_at,
            inspected=bool(row.inspected),
        )

    def _to_finding(self, row: RiskFindingRecord) -> RiskFinding:
        from app.opportunities.schemas import RiskSeverity

        return RiskFinding(
            finding_id=row.finding_id,
            # category is a Literal[str], not an enum - there is no RiskCategory.
            category=row.category,
            severity=RiskSeverity(row.severity),
            description=row.description,
            jurisdiction=row.jurisdiction,
            platform=row.platform,
            mitigation=row.mitigation,
            evidence_ids=tuple(row.evidence_ids or ()),
            blocks_recommendation=bool(row.blocks_recommendation),
        )

    def _to_score(self, row: OpportunityScoreRecord) -> OpportunityScore:
        from app.opportunities.schemas import ScoreDimension

        return OpportunityScore(
            dimensions=tuple(
                ScoreDimension.model_validate(d) for d in (row.dimensions or ())
            ),
            weights_sum=_num(row.weights_sum),
            attractiveness=_num(row.attractiveness),
            evidence_quality=_num(row.evidence_quality),
            scorable_count=int(row.scorable_count),
            unscored_dimensions=tuple(row.unscored_dimensions or ()),
            coverage_pct=_num(row.coverage_pct),
            ranking_key=tuple(row.ranking_key or ()),
        )

    async def list_opportunities(
        self, *, state: str | None = None, limit: int = 100, include_analyses: bool = False
    ) -> list[OpportunitySchema]:
        async with self.db.session_factory() as session:
            query = select(Opportunity).order_by(Opportunity.opportunity_id).limit(limit)
            if state is not None:
                query = query.where(Opportunity.state == state)
            rows = (await session.execute(query)).scalars().all()
            ids = [r.opportunity_id for r in rows]
        return [
            loaded
            for oid in ids
            if (loaded := await self.load_opportunity(oid, include_analyses=include_analyses))
        ]

    async def count_opportunities(self, *, state: str | None = None) -> int:
        from sqlalchemy import func

        async with self.db.session_factory() as session:
            query = select(func.count()).select_from(Opportunity)
            if state is not None:
                query = query.where(Opportunity.state == state)
            return int((await session.execute(query)).scalar_one())

    # ------------------------------------------------------------------ #
    # Lifecycle history (§17) - append only
    # ------------------------------------------------------------------ #
    async def append_history(
        self,
        *,
        opportunity_id: str,
        from_state: str | None,
        to_state: str,
        reason: str,
        actor: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        async with self.db.session_factory() as session:
            session.add(
                OpportunityHistory(
                    id=new_id(),
                    opportunity_id=opportunity_id,
                    from_state=from_state,
                    to_state=to_state,
                    reason=reason,
                    actor=actor[:120],
                    recorded_at=_utcnow(),
                    metadata_=_dict(metadata),
                )
            )
            await session.commit()

    async def list_history(self, opportunity_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        async with self.db.session_factory() as session:
            rows = (
                await session.execute(
                    select(OpportunityHistory)
                    .where(OpportunityHistory.opportunity_id == opportunity_id)
                    .order_by(OpportunityHistory.recorded_at)
                    .limit(limit)
                )
            ).scalars().all()
            return [
                {
                    "from_state": r.from_state,
                    "to_state": r.to_state,
                    "reason": r.reason,
                    "actor": r.actor,
                    "recorded_at": r.recorded_at,
                    "metadata": dict(r.metadata_ or {}),
                }
                for r in rows
            ]

    # ------------------------------------------------------------------ #
    # Evidence (§9)
    # ------------------------------------------------------------------ #
    def _evidence_values(self, ev: SourceEvidence) -> dict[str, Any]:
        return {
            "opportunity_id": ev.opportunity_id,
            "evidence_type": _enum(ev.evidence_type),
            "classification": _enum(ev.classification),
            "claim": ev.claim,
            "observed_value": ev.observed_value,
            "numeric_value": _dec(ev.numeric_value),
            "unit": ev.unit,
            "source_id": ev.source_id,
            # A reference, never the artefact: retrieved bodies stay out of the
            # database so untrusted content cannot be replayed from storage.
            "source_url": (ev.source_url or "")[:2048] or None,
            "publication_date": ev.publication_date,
            "collected_at": ev.collected_at,
            "reliability": _enum(ev.reliability),
            "trust_domain": _enum(ev.trust_domain),
            "independence_group": (ev.independence_group or "")[:128] or None,
            "supersedes": ev.supersedes,
            "contradicts": _list(ev.contradicts),
            "stale_after_days": ev.stale_after_days,
            "notes": ev.notes,
        }

    def _to_evidence(self, row: SourceEvidenceRecord) -> SourceEvidence:
        from app.intelligence.schemas import EvidenceReliability, TrustDomain
        from app.opportunities.schemas import EvidenceClassification, EvidenceType

        return SourceEvidence(
            evidence_id=row.evidence_id,
            opportunity_id=row.opportunity_id,
            evidence_type=EvidenceType(row.evidence_type),
            classification=EvidenceClassification(row.classification),
            claim=row.claim,
            observed_value=row.observed_value,
            numeric_value=_num(row.numeric_value),
            unit=row.unit,
            source_id=row.source_id,
            source_url=row.source_url,
            publication_date=row.publication_date,
            collected_at=row.collected_at,
            reliability=EvidenceReliability(row.reliability),
            trust_domain=TrustDomain(row.trust_domain),
            independence_group=row.independence_group,
            supersedes=row.supersedes,
            contradicts=tuple(row.contradicts or ()),
            stale_after_days=row.stale_after_days,
            notes=row.notes,
        )

    async def save_evidence(self, evidence: SourceEvidence) -> None:
        async with self.db.session_factory() as session:
            row = (
                await session.execute(
                    select(SourceEvidenceRecord).where(
                        SourceEvidenceRecord.evidence_id == evidence.evidence_id
                    )
                )
            ).scalar_one_or_none()
            values = self._evidence_values(evidence)
            if row is None:
                session.add(
                    SourceEvidenceRecord(id=new_id(), evidence_id=evidence.evidence_id, **values)
                )
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            await session.commit()

    async def list_evidence(
        self, *, opportunity_id: str | None = None, limit: int = 500
    ) -> list[SourceEvidence]:
        async with self.db.session_factory() as session:
            query = select(SourceEvidenceRecord).order_by(SourceEvidenceRecord.evidence_id).limit(limit)
            if opportunity_id is not None:
                query = query.where(SourceEvidenceRecord.opportunity_id == opportunity_id)
            rows = (await session.execute(query)).scalars().all()
            return [self._to_evidence(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Sources (§8) - credentials are never written
    # ------------------------------------------------------------------ #
    def _source_values(self, d: SourceDescriptor) -> dict[str, Any]:
        values = {
            "name": d.name[:200],
            "source_type": _enum(d.source_type),
            "access_method": _enum(d.access_method),
            "requires_auth": bool(d.requires_auth),
            "auth_mechanism": _enum(d.auth_mechanism) or "none",
            "rate_limit_per_minute": d.rate_limit_per_minute,
            "returned_fields": _list(d.returned_fields),
            "refresh_frequency": _enum(d.refresh_frequency) or "manual",
            "licensing": d.licensing[:400],
            "reliability": _enum(d.reliability),
            "supported_operations": _list(d.supported_operations),
            "status": _enum(d.status),
            "endpoint_template": (d.endpoint_template or "")[:512] or None,
            "notes": d.notes,
        }
        # Defence in depth: even if a descriptor somehow carried a credential
        # field, it is stripped here rather than persisted.
        return {k: v for k, v in values.items() if k not in {"api_key", "token", "secret", "password"}}

    async def save_source(self, descriptor: SourceDescriptor) -> None:
        async with self.db.session_factory() as session:
            row = (
                await session.execute(
                    select(ResearchSource).where(ResearchSource.source_id == descriptor.source_id)
                )
            ).scalar_one_or_none()
            values = self._source_values(descriptor)
            if row is None:
                session.add(ResearchSource(id=new_id(), source_id=descriptor.source_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            await session.commit()

    async def list_sources(self, *, limit: int = 200) -> list[SourceDescriptor]:
        from app.intelligence.schemas import EvidenceReliability
        from app.opportunities.schemas import (
            AcquisitionMethod,
            SourceStatus,
            SourceType,
        )

        async with self.db.session_factory() as session:
            rows = (
                await session.execute(select(ResearchSource).order_by(ResearchSource.source_id).limit(limit))
            ).scalars().all()
            out: list[SourceDescriptor] = []
            for r in rows:
                out.append(
                    SourceDescriptor(
                        source_id=r.source_id,
                        name=r.name,
                        source_type=SourceType(r.source_type),
                        access_method=AcquisitionMethod(r.access_method),
                        requires_auth=bool(r.requires_auth),
                        # Literal[str]: pydantic validates the value on construction.
                        auth_mechanism=r.auth_mechanism or "none",
                        rate_limit_per_minute=r.rate_limit_per_minute,
                        returned_fields=tuple(r.returned_fields or ()),
                        refresh_frequency=r.refresh_frequency or "manual",
                        licensing=r.licensing,
                        reliability=EvidenceReliability(r.reliability),
                        supported_operations=tuple(r.supported_operations or ("search",)),
                        status=SourceStatus(r.status),
                        endpoint_template=r.endpoint_template,
                        notes=r.notes,
                    )
                )
            return out

    # ------------------------------------------------------------------ #
    # Research sweeps (§20) - refusals are kept
    # ------------------------------------------------------------------ #
    async def record_sweep(
        self,
        *,
        opportunity_id: str,
        stage: str,
        operation: str = "search",
        query: str | None = None,
        source_ids: Sequence[str] = (),
        responses_obtained: int = 0,
        evidence_extracted: int = 0,
        refusals: Sequence[dict[str, Any]] = (),
        task_id: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> str:
        sweep_id = new_id()
        async with self.db.session_factory() as session:
            session.add(
                ResearchSweep(
                    id=sweep_id,
                    opportunity_id=opportunity_id,
                    stage=stage[:32],
                    operation=operation[:64],
                    query=(query or "")[:512] or None,
                    source_ids=_list(source_ids),
                    responses_obtained=int(responses_obtained),
                    evidence_extracted=int(evidence_extracted),
                    refusals=_list(refusals),
                    task_id=task_id,
                    started_at=started_at,
                    finished_at=finished_at,
                )
            )
            await session.commit()
        return sweep_id

    async def list_sweeps(self, opportunity_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        async with self.db.session_factory() as session:
            rows = (
                await session.execute(
                    select(ResearchSweep)
                    .where(ResearchSweep.opportunity_id == opportunity_id)
                    .order_by(ResearchSweep.created_at)
                    .limit(limit)
                )
            ).scalars().all()
            return [
                {
                    "id": r.id,
                    "stage": r.stage,
                    "operation": r.operation,
                    "query": r.query,
                    "source_ids": list(r.source_ids or ()),
                    "responses_obtained": r.responses_obtained,
                    "evidence_extracted": r.evidence_extracted,
                    "refusals": list(r.refusals or ()),
                    "task_id": r.task_id,
                    "started_at": r.started_at,
                    "finished_at": r.finished_at,
                }
                for r in rows
            ]

    # ------------------------------------------------------------------ #
    # Analysis records (§10-§16, §23)
    # ------------------------------------------------------------------ #
    async def save_market_analysis(self, opportunity_id: str, assessment: MarketAssessment) -> None:
        values = {
            "verdict": assessment.verdict[:32],
            "demand_evidence_level": _enum(assessment.demand_evidence_level),
            "problem_importance": _enum(assessment.problem_importance) or "unknown",
            "problem_importance_basis": assessment.problem_importance_basis,
            "customer_description": assessment.customer_description,
            "sizing": assessment.sizing.model_dump(mode="json") if assessment.sizing else {},
            "signals": [s.model_dump(mode="json") for s in assessment.signals],
            "willingness_indicators": _list(assessment.willingness_indicators),
            "data_gaps": _list(assessment.data_gaps),
            "reasons": _list(assessment.reasons),
        }
        await self._upsert(MarketAnalysis, "opportunity_id", opportunity_id, values)

    async def save_competitor_assessment(
        self, opportunity_id: str, assessment: CompetitorAssessment
    ) -> None:
        async with self.db.session_factory() as session:
            for c in assessment.competitors:
                row = (
                    await session.execute(
                        select(CompetitorRecord).where(CompetitorRecord.competitor_id == c.competitor_id)
                    )
                ).scalar_one_or_none()
                values = {
                    "opportunity_id": opportunity_id,
                    "name": c.name[:200],
                    "url": (c.url or "")[:2048] or None,
                    "offering": c.offering,
                    "positioning": c.positioning,
                    "price_points": [_dec(p) for p in c.price_points],
                    "price_currency": c.price_currency or "USD",
                    "pricing_provenance": _enum(c.pricing_provenance) or "unknown",
                    "rating": _dec(c.rating),
                    "review_count": c.review_count,
                    "rating_provenance": _enum(c.rating_provenance) or "unknown",
                    "strengths": _list(c.strengths),
                    "weaknesses": _list(c.weaknesses),
                    "complaint_themes": _list(c.complaint_themes),
                    "identified_gaps": _list(c.identified_gaps),
                    "evidence_ids": _list(c.evidence_ids),
                    "observed_at": c.observed_at,
                    "inspected": bool(c.inspected),
                }
                if row is None:
                    session.add(CompetitorRecord(id=new_id(), competitor_id=c.competitor_id, **values))
                else:
                    for key, value in values.items():
                        setattr(row, key, value)
            await session.commit()

    async def save_commercial_analysis(
        self, opportunity_id: str, assessment: CommercialAssessment
    ) -> None:
        values = {
            "verdict": assessment.verdict[:32],
            "viable": bool(assessment.viable),
            "affordable": bool(assessment.affordable),
            "costs": assessment.costs.model_dump(mode="json"),
            "scenarios": [s.model_dump(mode="json") for s in assessment.scenarios],
            "break_even": assessment.break_even.model_dump(mode="json") if assessment.break_even else {},
            "budget_compatibility": (
                assessment.budget_compatibility.model_dump(mode="json")
                if assessment.budget_compatibility
                else {}
            ),
            "unpriced_cost_items": _list(assessment.unpriced_cost_items),
            "budget_was_modified": bool(assessment.budget_was_modified),
            "reasons": _list(assessment.reasons),
            "assumptions": _list(assessment.assumptions),
        }
        await self._upsert(CommercialAnalysis, "opportunity_id", opportunity_id, values)

    async def save_risk_assessment(self, opportunity_id: str, assessment: RiskAssessment) -> None:
        async with self.db.session_factory() as session:
            for f in assessment.findings:
                row = (
                    await session.execute(
                        select(RiskFindingRecord).where(RiskFindingRecord.finding_id == f.finding_id)
                    )
                ).scalar_one_or_none()
                values = {
                    "opportunity_id": opportunity_id,
                    "category": _enum(f.category),
                    "severity": _enum(f.severity),
                    "description": f.description,
                    "jurisdiction": (f.jurisdiction or "")[:64] or None,
                    "platform": (f.platform or "")[:120] or None,
                    "mitigation": f.mitigation,
                    "evidence_ids": _list(f.evidence_ids),
                    "blocks_recommendation": bool(f.blocks_recommendation),
                    "risk_verdict": assessment.verdict[:32],
                    "prohibited_category_matched": assessment.prohibited_category_matched,
                    # Assessment-level fields, denormalised onto each finding so the
                    # whole RiskAssessment can be rebuilt on read.
                    "highest_severity": _enum(assessment.highest_severity),
                    "blocked": bool(assessment.blocked),
                    "jurisdictions_considered": _list(assessment.jurisdictions_considered),
                    "data_gaps": _list(assessment.data_gaps),
                    "reasons": _list(assessment.reasons),
                }
                if row is None:
                    session.add(RiskFindingRecord(id=new_id(), finding_id=f.finding_id, **values))
                else:
                    for key, value in values.items():
                        setattr(row, key, value)
            await session.commit()

    async def save_scoring_outcome(
        self,
        opportunity_id: str,
        outcome: ScoringOutcome,
        *,
        validation: ValidationAssessment | None = None,
    ) -> None:
        """Persist the §16 score and, when supplied, the §18 validation snapshot.

        ``ScoringOutcome`` carries no validation field - validation lives on the
        opportunity - so it is passed in explicitly rather than read from an
        attribute that does not exist.
        """
        score = outcome.score
        values = {
            "dimensions": [d.model_dump(mode="json") for d in score.dimensions],
            "weights_sum": _dec(score.weights_sum),
            "attractiveness": _dec(score.attractiveness),
            "evidence_quality": _dec(score.evidence_quality),
            "scorable_count": int(score.scorable_count),
            "unscored_dimensions": _list(score.unscored_dimensions),
            "coverage_pct": _dec(score.coverage_pct),
            "ranking_key": [str(k) for k in score.ranking_key],
            "weights_fingerprint": (outcome.weights_fingerprint or "")[:32],
            "hard_rejections": _list(outcome.hard_rejections),
            "rejected": bool(outcome.rejected),
            "recommendable": bool(outcome.recommendable),
            "final_classification": _enum(outcome.final_classification),
            "validation_level": validation.level.value if validation else 0,
            "validation_satisfied": _list(validation.satisfied_inputs) if validation else [],
            "validation_rejected": _list(validation.rejected_inputs) if validation else [],
            "validation_blocking": validation.blocking_prohibition if validation else None,
            "validation_next_level": (
                validation.next_level.value if validation and validation.next_level else None
            ),
            "validation_next_requirement": validation.next_level_requirement if validation else None,
            "reasons": _list(outcome.reasons),
        }
        await self._upsert(OpportunityScoreRecord, "opportunity_id", opportunity_id, values)

    async def save_report(self, opportunity_id: str, report: OpportunityReport) -> None:
        values = {
            "title": report.title[:300],
            "final_classification": _enum(report.final_classification),
            "sections": {k.value if hasattr(k, "value") else str(k): v for k, v in report.sections.items()},
            "headline_metrics": _dict(report.headline_metrics),
            "evidence_index": [e.model_dump(mode="json") for e in report.evidence_index],
            "refusals": _list(report.refusals),
            "assumptions": _list(report.assumptions),
            "score_snapshot": report.score.model_dump(mode="json") if report.score else {},
            "validation_snapshot": (
                report.validation.model_dump(mode="json") if report.validation else {}
            ),
            "is_test_data": bool(report.is_test_data),
            "test_data_notice": report.test_data_notice,
            "generated_at": report.generated_at or _utcnow(),
        }
        await self._upsert(OpportunityReportRecord, "opportunity_id", opportunity_id, values,
                           extra={"report_id": report.report_id})

    async def load_report(self, opportunity_id: str) -> dict[str, Any] | None:
        async with self.db.session_factory() as session:
            row = (
                await session.execute(
                    select(OpportunityReportRecord).where(
                        OpportunityReportRecord.opportunity_id == opportunity_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return {
                "report_id": row.report_id,
                "title": row.title,
                "final_classification": row.final_classification,
                "sections": dict(row.sections or {}),
                "headline_metrics": dict(row.headline_metrics or {}),
                "evidence_index": list(row.evidence_index or ()),
                "refusals": list(row.refusals or ()),
                "assumptions": list(row.assumptions or ()),
                "score_snapshot": dict(row.score_snapshot or {}),
                "validation_snapshot": dict(row.validation_snapshot or {}),
                "is_test_data": bool(row.is_test_data),
                "test_data_notice": row.test_data_notice,
                "generated_at": row.generated_at,
            }

    async def _upsert(
        self,
        model: Any,
        key_column: str,
        key_value: str,
        values: dict[str, Any],
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Upsert one row per opportunity for a single-valued analysis table."""
        async with self.db.session_factory() as session:
            column = getattr(model, key_column)
            row = (await session.execute(select(model).where(column == key_value))).scalar_one_or_none()
            if row is None:
                session.add(model(id=new_id(), **{key_column: key_value}, **(extra or {}), **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
                for key, value in (extra or {}).items():
                    setattr(row, key, value)
            await session.commit()


# --------------------------------------------------------------------------- #
# Mapping completeness
#
# A pydantic field with no column behind it makes persistence silently lossy: the
# object saves, reads back, and quietly lacks data.  This diff turns that from a
# production surprise into a checked invariant.  The sets below name, for each
# schema, the fields that ARE persisted; anything left over is reported.
# --------------------------------------------------------------------------- #
_PERSISTED: dict[str, frozenset[str]] = {
    "OpportunityCandidate": frozenset(
        {"candidate_id", "title", "description", "category", "discovery_method", "derived_from",
         "target_customer", "problem_addressed", "proposed_offering", "budget_band",
         "generated_by", "duplicate_of", "generated_at"}
    ),
    "Opportunity": frozenset(
        {"opportunity_id", "candidate", "state", "budget", "validation",
         "evidence_ids", "rejection_reasons", "assumptions", "final_classification",
         "owner_notes", "business_model", "distribution",
         # Reassembled by load_opportunity() from their own tables, so they are
         # persisted - just not on the opportunities row.
         "market", "competitors", "costs", "scenarios", "break_even",
         "budget_compatibility", "risks", "score",
         "created_at", "updated_at"}
    ),
    "SourceEvidence": frozenset(
        {"evidence_id", "opportunity_id", "evidence_type", "classification", "claim",
         "observed_value", "numeric_value", "unit", "source_id", "source_url",
         "publication_date", "collected_at", "reliability", "trust_domain",
         "independence_group", "supersedes", "contradicts", "stale_after_days",
         "notes"}
    ),
    "SourceDescriptor": frozenset(
        {"source_id", "name", "source_type", "access_method", "requires_auth",
         "auth_mechanism", "rate_limit_per_minute", "returned_fields", "refresh_frequency",
         "licensing", "reliability", "supported_operations", "status", "endpoint_template",
         "notes"}
    ),
}

#: Fields deliberately NOT persisted, each with the reason.  Deliberate omission is
#: fine; unnoticed omission is not, so the reason is recorded here and checked.
_INTENTIONAL_OMISSIONS: dict[str, dict[str, str]] = {
    "Opportunity": {
        # Derived from the candidate row and rebuilt on read; storing both would
        # let them disagree.
        "created_at": "carried by the row's created_at",
        "updated_at": "carried by the row's updated_at",
    },
}


def verify_mapping_completeness() -> dict[str, Any]:
    """Diff persisted fields against every schema field, for the audited models."""
    gaps: dict[str, list[str]] = {}
    for name, persisted in _PERSISTED.items():
        model = getattr(_schemas, name, None)
        if model is None:  # pragma: no cover - would mean the schema was renamed
            gaps[name] = ["<model not importable>"]
            continue
        fields = set(model.model_fields)
        omitted = set(_INTENTIONAL_OMISSIONS.get(name, {}))
        missing = sorted(fields - persisted - omitted)
        unknown = sorted(persisted - fields)
        if missing:
            gaps[name] = [f"NOT PERSISTED: {m}" for m in missing]
        if unknown:
            gaps.setdefault(name, []).extend(f"NOT A FIELD: {u}" for u in unknown)
    return {"checked": sorted(_PERSISTED), "gaps": gaps, "clean": not gaps}


MAPPING_GAPS = verify_mapping_completeness()
