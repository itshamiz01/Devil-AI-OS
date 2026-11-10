"""P-08 API schemas.

Amounts that P-08 *records as declared expectations or proposals*
(experiment budgets, plan targets, allocation amounts) are integer
minor units (JSON ints) or decimal strings — never JSON floats:
integers are exact, strings are exact. Figures P-08 *reports* all
come verbatim from P-07 (§6.1/§32 rule 3).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SettingsUpdateIn(BaseModel):
    health_weights: dict | None = None
    health_bands: dict | None = None
    scaling_criteria: dict | None = None
    max_increment_ratio: str | None = None
    max_business_capital_share: str | None = None
    concentration_threshold: str | None = None
    max_concurrent_agents: int | None = None
    inference_slots: int | None = None


class ObservationIn(BaseModel):
    kind: str
    metrics: dict = Field(default_factory=dict)
    source: str = "manual"
    reliability: str = "tentative"
    evidence_refs: list = Field(default_factory=list)
    observed_on: str | None = None


class EvaluateIn(BaseModel):
    pass


class OverlayIn(BaseModel):
    to_state: str
    reason: str = ""
    decision_id: str | None = None


class PauseIn(BaseModel):
    reason: str = ""


class DecisionAlternativeIn(BaseModel):
    kind: str
    summary: str
    expected_cost_minor: int | None = None
    expected_downside: str = ""
    score_bps: int | None = None
    recommended: bool = False


class DecisionCreateIn(BaseModel):
    decision_type: str
    trigger: str = ""
    evidence: list = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    risk_assessment: str = ""
    expected_benefit: str = ""
    estimated_cost_minor: int | None = None
    estimated_cost_currency: str | None = None
    expected_downside: str = ""
    confidence: str = "low"
    reversibility: str = "reversible"
    time_horizon_days: int | None = None
    score_bps: int | None = None
    expires_on: str | None = None
    review_conditions: str = ""
    alternatives: list[DecisionAlternativeIn] = Field(default_factory=list)


class DecisionReviewIn(BaseModel):
    reason: str | None = None
    approval_id: str | None = None


class DecisionExecuteIn(BaseModel):
    idempotency_key: str | None = None


class ExperimentDeclareIn(BaseModel):
    name: str = "experiment"
    hypothesis: str = ""
    problem: str = ""
    target_customer: str = ""
    expected_outcome: str = ""
    success_metric: str = ""
    failure_metric: str = ""
    minimum_evidence: str = ""
    max_duration_days: int | None = None
    approved_budget_minor: int | None = None
    max_acceptable_loss_minor: int | None = None
    evaluation_schedule: str = ""
    currency: str = "INR"
    operational_requirements: str = ""
    required_agents: list = Field(default_factory=list)
    data_sources: list = Field(default_factory=list)
    declaration_id: str | None = None


class ExperimentSpendIn(BaseModel):
    amount_minor: int


class ExperimentApproveIn(BaseModel):
    approval_id: str | None = None


class ExperimentEvaluateIn(BaseModel):
    classification: str
    observed_metric_value: str | None = None
    actual_outcome: str = ""
    unexpected_findings: str = ""
    lessons: str = ""
    recommended_next_step: str = ""


class ExperimentStopIn(BaseModel):
    reason: str = ""


class ScalingAssessIn(BaseModel):
    pass


class ScalingPlanIn(BaseModel):
    budget_id: str
    proposed_amount_minor: int
    success_conditions: str = ""
    stop_conditions: str = ""
    strict: bool = False


class RecoveryAssessIn(BaseModel):
    pass


class RecoveryPlanIn(BaseModel):
    root_cause: str = ""
    failure_kind: str = "unknown"
    corrective_actions: list = Field(default_factory=list)
    responsible_agents: list = Field(default_factory=list)
    budget_minor: int = 0
    currency: str = "INR"
    timeline_days: int
    expected_outcome: str = ""
    success_thresholds: str
    failure_thresholds: str
    escalation_rules: str = ""


class RecoveryConcludeIn(BaseModel):
    outcome: str


class ClosureProposeIn(BaseModel):
    reason: str = ""


class ClosureExecuteIn(BaseModel):
    approval_id: str | None = None


class ClosureAdvanceIn(BaseModel):
    to_stage: str


class AllocationRequestIn(BaseModel):
    business_id: str
    amount_minor: int | None = None
    purpose: str = ""
    expected_result: str = ""
    max_loss_minor: int | None = None
    review_on: str | None = None


class AllocationProposeIn(BaseModel):
    currency: str = "INR"
    category: str = "growth"
    source_kind: str = "available_capital"
    requests: list[AllocationRequestIn] = Field(default_factory=list)


class ResourceProposeIn(BaseModel):
    requested_agents: int


class ForecastCreateIn(BaseModel):
    kind: str = "survival"
    scenario: str = "base"
    period_label: str = "next_period"
    assumptions: list | None = None
    expected: dict = Field(default_factory=dict)
    confidence: str = "low"
    p07_forecast_id: str | None = None


class OutcomeRecordIn(BaseModel):
    decision_id: str | None = None
    experiment_id: str | None = None
    problem: str = ""
    evidence_at_decision: list = Field(default_factory=list)
    expected_outcome: str = ""
    actual_outcome: str = ""
    actuals: dict = Field(default_factory=dict)
    cost_minor: int | None = None
    decision_quality: str = "unrated"
    failure_kind: str | None = None
    lesson: str = ""
    future_implications: str = ""
    forecast_error: dict = Field(default_factory=dict)


class AnalystQueryIn(BaseModel):
    intent: str
    business_id: str | None = None
