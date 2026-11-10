"""SQLAlchemy models for the P-08 Survival and Scaling Engine tables.

One additive migration creates these tables; no P-01..P-07 table is
altered. Approvals reuse the P-01 ``approvals`` table, the audit trail
reuses the append-only P-01 ``audit_events`` table, and owner-governed
settings live in ``system_config`` (key ``survival.settings``) — there
is deliberately no ``survival_approvals``, ``survival_audit`` or
``survival_settings`` table here.

Money discipline (P-08 lock 1): P-08 computes NO financial figure.
Amounts stored here are either (a) verbatim copies of P-07-returned
figures inside snapshot/proposal payloads (labelled with source and
timestamp), or (b) declared proposal amounts awaiting owner decision.
No column in this module is a ledger fact, and no column is a float:
scores and ratios are stored as strings (Decimal-serialised) or as
integer basis points, never as binary floats.
"""
from __future__ import annotations

from sqlalchemy import (
    JSON, BigInteger, Boolean, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class BusinessHealthSnapshot(TimestampMixin, Base):
    """One §7 health evaluation. Append-only: a new evaluation is a new
    row; history is never rewritten (§3.1/§7). ``indicators`` is the
    verbatim P-07 ``p08_indicators`` payload the evaluation consumed,
    so every figure can be traced to its source reading."""

    __tablename__ = "business_health_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    classification: Mapped[str] = mapped_column(
        String(30), nullable=False, default="INSUFFICIENT_DATA", index=True)
    score_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    overlay_state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="EARLY_OPERATIONS")
    hard_gates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[str] = mapped_column(
        String(20), nullable=False, default="low")
    indicators: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    indicators_source: Mapped[str] = mapped_column(
        String(80), nullable=False, default="p07.p08_indicators")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class BusinessHealthDimension(TimestampMixin, Base):
    """One of the seven §7.1 dimensions for one snapshot."""

    __tablename__ = "business_health_dimensions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("business_health_snapshots.id"), nullable=False, index=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    dimension: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="INSUFFICIENT_DATA")
    score_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    freshness: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unknown")
    confidence: Mapped[str] = mapped_column(
        String(20), nullable=False, default="low")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class BusinessMonitoringEvent(TimestampMixin, Base):
    """A §6 monitoring finding (financial/commercial/operational/
    strategic), always with provenance."""

    __tablename__ = "business_monitoring_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="info")
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class BusinessObservation(TimestampMixin, Base):
    """A commercial/operational observation (§6.2/§6.3): evidence with
    provenance and a reliability ceiling — never financial truth.
    Vanity metrics are flagged at write time and can never validate
    a business or lift a health dimension above INSUFFICIENT_DATA."""

    __tablename__ = "business_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    reliability: Mapped[str] = mapped_column(
        String(20), nullable=False, default="tentative")
    is_vanity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    observed_on: Mapped[str] = mapped_column(String(10), nullable=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class BusinessDecision(TimestampMixin, Base):
    """A §8 decision record. The score is decision support only; the
    authorisation state lives in ``status`` + the P-01 hash-bound
    approval referenced by ``approval_id``. Execution is idempotent:
    ``execution_key`` is unique and ``executed_at`` is set exactly
    once."""

    __tablename__ = "business_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    decision_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PROPOSED", index=True)
    autonomy_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    risk_assessment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_benefit: Mapped[str] = mapped_column(Text, nullable=False, default="")
    estimated_cost_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    estimated_cost_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    expected_downside: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[str] = mapped_column(
        String(20), nullable=False, default="low")
    reversibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="reversible")
    time_horizon_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expires_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    review_conditions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    explanation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    execution_key: Mapped[str | None] = mapped_column(
        String(120), nullable=True, unique=True)
    executed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    execution_outcome: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    intelligence_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class BusinessDecisionAlternative(TimestampMixin, Base):
    """One §8.3 alternative considered for a decision."""

    __tablename__ = "business_decision_alternatives"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("business_decisions.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_cost_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expected_downside: Mapped[str] = mapped_column(Text, nullable=False, default="")
    score_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class BusinessLifecycleOverlay(TimestampMixin, Base):
    """A P-08 operational overlay transition (§5.3 history). The P-06
    lifecycle remains the only business state machine; overlays are
    P-08's operational reading of the business, each tied to the
    decision/evidence/approval that caused it."""

    __tablename__ = "business_lifecycle_overlays"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    from_state: Mapped[str] = mapped_column(String(30), nullable=False)
    to_state: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    p06_status: Mapped[str] = mapped_column(String(40), nullable=False)
    decision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(120), nullable=False)


class BusinessExperiment(TimestampMixin, Base):
    """A §9 pre-declared experiment. Every §9.2 field is recorded
    BEFORE the experiment may start (enforced in the service); the
    budget is a real P-07 budget (``budget_id``) so stop-loss blocks
    at the P-07 budget layer. Failed experiments are preserved
    permanently — there is no delete path (§9.5)."""

    __tablename__ = "business_experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PROPOSED", index=True)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    problem: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_customer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False, default="")
    success_metric: Mapped[str] = mapped_column(String(200), nullable=False)
    failure_metric: Mapped[str] = mapped_column(String(200), nullable=False)
    minimum_evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    max_duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_budget_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_acceptable_loss_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    operational_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="")
    required_agents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    data_sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evaluation_schedule: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    declaration_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    owner_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class ExperimentEvaluation(TimestampMixin, Base):
    """A §9.5 evaluation: immutable once written. Actuals are P-07
    readings taken at evaluation time, stored verbatim with source."""

    __tablename__ = "experiment_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("business_experiments.id"), nullable=False, index=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    classification: Mapped[str] = mapped_column(String(30), nullable=False)
    actual_outcome: Mapped[str] = mapped_column(Text, nullable=False, default="")
    observed_metric_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actuals: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actuals_source: Mapped[str] = mapped_column(
        String(80), nullable=False, default="p07.budget_utilisation")
    unexpected_findings: Mapped[str] = mapped_column(Text, nullable=False, default="")
    lessons: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recommended_next_step: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class ScalingAssessment(TimestampMixin, Base):
    """A §10.3 scaling readiness report: satisfied AND unsatisfied
    conditions, hard gates, confidence reductions, downside."""

    __tablename__ = "scaling_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="NOT_READY", index=True)
    stage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    satisfied: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    unsatisfied: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    hard_gates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(
        String(20), nullable=False, default="low")
    financial_impact: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    capacity_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="")
    downside_scenario: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approval_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="")
    snapshot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class ScalingPlan(TimestampMixin, Base):
    """A §10.4 incremental scaling plan: a proposal over P-07 budget
    figures. Creating or approving a plan moves no money and changes
    no P-07 budget — activation is a separate owner-approved step
    that records the proposal outcome (§16.4)."""

    __tablename__ = "scaling_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("scaling_assessments.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PROPOSED", index=True)
    budget_id: Mapped[str] = mapped_column(String(36), nullable=False)
    current_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    proposed_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    increment_ratio_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clamped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    success_conditions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stop_conditions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class RecoveryPlan(TimestampMixin, Base):
    """A §13 recovery plan: finite budget and review period, success
    and failure thresholds, escalation — recovery is never an
    indefinite subsidy."""

    __tablename__ = "recovery_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PROPOSED", index=True)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failure_kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unknown")
    financial_impact: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    corrective_actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    responsible_agents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    budget_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    timeline_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False, default="")
    success_thresholds: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failure_thresholds: Mapped[str] = mapped_column(Text, nullable=False, default="")
    escalation_rules: Mapped[str] = mapped_column(Text, nullable=False, default="")
    review_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class ClosureReview(TimestampMixin, Base):
    """A §14 closure review: the staged workflow plus the obligation
    inventory (P-07 figures, verbatim) that must exist BEFORE any
    closure recommendation. Permanent closure is Level 4."""

    __tablename__ = "closure_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PROPOSED_CLOSURE", index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    inventory: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    risk_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recommendation: Mapped[str] = mapped_column(
        String(40), nullable=False, default="PENDING_REVIEWS")
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    wind_down: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    decision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CapitalAllocationProposal(TimestampMixin, Base):
    """A §16 allocation proposal. Proposals only: actual financial
    movement is outside P-08 (§16.4). A proposal whose source touches
    protected reserves is stored BLOCKED, never actionable."""

    __tablename__ = "capital_allocation_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PROPOSED", index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    source_kind: Mapped[str] = mapped_column(
        String(40), nullable=False, default="available_capital")
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_result: Mapped[str] = mapped_column(Text, nullable=False, default="")
    max_loss_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    score_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rationale: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    review_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class ResourceAllocationProposal(TimestampMixin, Base):
    """A §17 resource proposal: workload measured first (P-04/P-01
    readings), reassignment considered before creation, creation only
    ever through P-04."""

    __tablename__ = "resource_allocation_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PROPOSED", index=True)
    requested_agents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recommended_agents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    workload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    alternatives: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class SurvivalForecast(TimestampMixin, Base):
    """A §18 P-08 forecast. Frozen at creation: the row is never
    updated after insert (enforced in the service), so forecast-vs-
    actual can never rewrite history (§18.4). Financial inputs are
    P-07 readings; where a P-07 forecast exists it is referenced."""

    __tablename__ = "survival_forecasts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="survival", index=True)
    scenario: Mapped[str] = mapped_column(
        String(20), nullable=False, default="base")
    period_label: Mapped[str] = mapped_column(String(20), nullable=False)
    assumptions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    expected: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[str] = mapped_column(
        String(20), nullable=False, default="low")
    p07_forecast_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class DecisionOutcome(TimestampMixin, Base):
    """A §21 learning record: expected vs actual, with decision
    quality judged against the evidence available when the decision
    was made — a lucky outcome does not redeem a poor decision.
    Structured for P-09 consumption (references, not copies)."""

    __tablename__ = "decision_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    decision_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    experiment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    problem: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_at_decision: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actual_outcome: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actuals: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    cost_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    decision_quality: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unrated")
    failure_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lesson: Mapped[str] = mapped_column(Text, nullable=False, default="")
    future_implications: Mapped[str] = mapped_column(Text, nullable=False, default="")
    forecast_error: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class BusinessPauseControl(TimestampMixin, Base):
    """A §25.2 business-level pause control. While active for a
    business, every P-08 execution/spend path for that business is
    blocked; records, obligations and logs are preserved. Lifting
    requires the owner."""

    __tablename__ = "business_pause_controls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="emergency", index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trigger: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    lifted_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lifted_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
