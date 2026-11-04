"""Typed intelligence schemas for the P-02 Master Intelligence Engine.

Every cross-module value in the intelligence subsystem is one of these types.
They exist so that model output can be validated against a schema before any
other module consumes it (P-02 §13), and so that reasoning state is inspectable
and auditable rather than locked inside free-form text.

Design rule enforced throughout: a value produced by a model is *never* trusted
merely because the model produced it. Model output enters the system through
`parse_*` helpers that validate it, and anything that fails validation is
rejected rather than repaired silently.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #


class RequestCategory(StrEnum):
    """P-02 §7.1 — the request categories the interpreter recognises.

    Extensible by adding a member; classification logic lives in
    `missions.MissionInterpreter`, not here.
    """

    GENERAL_CONVERSATION = "general_conversation"
    INFORMATION = "information"
    ANALYSIS = "analysis"
    RESEARCH = "research"
    PLANNING = "planning"
    PROJECT_MANAGEMENT = "project_management"
    BUSINESS_OBJECTIVE = "business_objective"
    SYSTEM_MANAGEMENT = "system_management"
    TASK_EXECUTION = "task_execution"
    APPROVAL_REQUIRED = "approval_required"


class MissionClassification(StrEnum):
    """P-02 §7.3 — how much machinery a request actually deserves.

    §7.3 is explicit that an ordinary question must not become a complex
    mission, so classification drives whether a Mission row is created at all.
    """

    SIMPLE_REQUEST = "simple_request"
    INFORMATION_TASK = "information_task"
    ANALYSIS_TASK = "analysis_task"
    SHORT_EXECUTION_TASK = "short_execution_task"
    MULTI_STEP_MISSION = "multi_step_mission"
    LONG_RUNNING_MISSION = "long_running_mission"
    HIGH_RISK_MISSION = "high_risk_mission"
    FINANCIALLY_SENSITIVE_MISSION = "financially_sensitive_mission"
    NEEDS_CLARIFICATION = "needs_clarification"


class MissionState(StrEnum):
    """P-02 §7.5 — the twelve mission states."""

    DRAFT = "DRAFT"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    READY_FOR_PLANNING = "READY_FOR_PLANNING"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


#: Validated mission transitions (P-02 §7.5). Terminal states have no exits, so
#: a completed, failed or cancelled mission can never be silently revived — the
#: same property the P-01 task state machine enforces.
MISSION_TRANSITIONS: dict[MissionState, frozenset[MissionState]] = {
    MissionState.DRAFT: frozenset({MissionState.NEEDS_CLARIFICATION, MissionState.READY_FOR_PLANNING, MissionState.CANCELLED}),
    MissionState.NEEDS_CLARIFICATION: frozenset({MissionState.DRAFT, MissionState.READY_FOR_PLANNING, MissionState.CANCELLED}),
    MissionState.READY_FOR_PLANNING: frozenset({MissionState.PLANNING, MissionState.CANCELLED}),
    MissionState.PLANNING: frozenset({MissionState.AWAITING_APPROVAL, MissionState.APPROVED, MissionState.BLOCKED, MissionState.FAILED, MissionState.CANCELLED}),
    MissionState.AWAITING_APPROVAL: frozenset({MissionState.APPROVED, MissionState.BLOCKED, MissionState.FAILED, MissionState.CANCELLED}),
    MissionState.APPROVED: frozenset({MissionState.EXECUTING, MissionState.PAUSED, MissionState.CANCELLED}),
    MissionState.EXECUTING: frozenset({MissionState.PAUSED, MissionState.BLOCKED, MissionState.COMPLETED, MissionState.FAILED, MissionState.CANCELLED}),
    MissionState.PAUSED: frozenset({MissionState.EXECUTING, MissionState.BLOCKED, MissionState.FAILED, MissionState.CANCELLED}),
    # BLOCKED may return to PLANNING: that is the replanning path (§9.6).
    MissionState.BLOCKED: frozenset({MissionState.PLANNING, MissionState.EXECUTING, MissionState.PAUSED, MissionState.FAILED, MissionState.CANCELLED}),
    MissionState.COMPLETED: frozenset(),
    MissionState.FAILED: frozenset(),
    MissionState.CANCELLED: frozenset(),
}

TERMINAL_MISSION_STATES = frozenset(
    state for state, exits in MISSION_TRANSITIONS.items() if not exits
)


class PlanStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(StrEnum):
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"
    READY = "READY"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class UncertaintyLevel(StrEnum):
    """P-02 §8.4 — how much weight a reasoning output may carry.

    `ASSUMED` and `UNKNOWN` are first-class results, not failures: §8.4 requires
    the system to be able to say it does not have enough information.
    """

    VERIFIED = "verified"
    STRONGLY_SUPPORTED = "strongly_supported"
    TENTATIVE = "tentative"
    ASSUMED = "assumed"
    UNKNOWN = "unknown"
    CONTRADICTED = "contradicted"


#: Ordering from most to least trustworthy, used when a conclusion inherits the
#: weakest level among the evidence it rests on.
UNCERTAINTY_RANK: dict[UncertaintyLevel, int] = {
    UncertaintyLevel.VERIFIED: 0,
    UncertaintyLevel.STRONGLY_SUPPORTED: 1,
    UncertaintyLevel.TENTATIVE: 2,
    UncertaintyLevel.ASSUMED: 3,
    UncertaintyLevel.CONTRADICTED: 4,
    UncertaintyLevel.UNKNOWN: 5,
}


class RiskLevel(StrEnum):
    """P-02 §10.3."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


RISK_RANK: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MODERATE: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


class DecisionStatus(StrEnum):
    """P-02 §16 — these are deliberately distinct states.

    A recommendation is not a decision, a decision proposal is not an authorized
    decision, and an authorized decision is not a completed action. Collapsing
    them is how an advisory system becomes an uncontrolled one.
    """

    RECOMMENDATION = "RECOMMENDATION"
    PROPOSAL = "PROPOSAL"
    AUTHORIZED = "AUTHORIZED"
    EXECUTABLE = "EXECUTABLE"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class ResponseCategory(StrEnum):
    """P-02 §13 — the ten structured response kinds."""

    CONVERSATIONAL_ANSWER = "conversational_answer"
    CLARIFICATION_REQUEST = "clarification_request"
    ANALYSIS_REPORT = "analysis_report"
    MISSION_PROPOSAL = "mission_proposal"
    EXECUTION_PLAN = "execution_plan"
    DECISION_RECOMMENDATION = "decision_recommendation"
    APPROVAL_REQUEST = "approval_request"
    PROGRESS_REPORT = "progress_report"
    COMPLETION_REPORT = "completion_report"
    FAILURE_REPORT = "failure_report"


class ResponseStatus(StrEnum):
    OK = "ok"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_APPROVAL = "needs_approval"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class AutonomyLevel(StrEnum):
    """P-02 §15 — how much execution authority the owner has granted.

    Levels 3 and 4 are declared so that the boundary is explicit and refused by
    code, not merely absent. §15 forbids implementing them in P-02.
    """

    LEVEL_0_ADVISORY = "0_advisory"
    LEVEL_1_ASSISTED = "1_assisted_execution"
    LEVEL_2_CONTROLLED = "2_controlled_autonomy"
    LEVEL_3_DELEGATED = "3_delegated_business_operations"
    LEVEL_4_COORDINATED = "4_multi_business_coordination"


#: Levels that may submit execution tasks at all.
EXECUTION_PERMITTED_LEVELS = frozenset({
    AutonomyLevel.LEVEL_1_ASSISTED,
    AutonomyLevel.LEVEL_2_CONTROLLED,
})

#: Levels that exist only as future-phase declarations. Requesting one is refused
#: rather than silently downgraded, so nobody can believe it is active.
UNIMPLEMENTED_LEVELS = frozenset({
    AutonomyLevel.LEVEL_3_DELEGATED,
    AutonomyLevel.LEVEL_4_COORDINATED,
})


class EvidenceStance(StrEnum):
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    NEUTRAL = "neutral"


class EvidenceReliability(StrEnum):
    """Source trustworthiness, distinct from verification status.

    A highly reliable source can still be unverified, and a model-generated
    statement is never promoted to VERIFIED by this code (§8.2).
    """

    AUTHORITATIVE = "authoritative"
    TRUSTED = "trusted"
    PLAUSIBLE = "plausible"
    UNTRUSTED = "untrusted"
    MODEL_GENERATED = "model_generated"


class HypothesisStatus(StrEnum):
    PROPOSED = "PROPOSED"
    UNDER_VALIDATION = "UNDER_VALIDATION"
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    ABANDONED = "ABANDONED"


class TrustDomain(StrEnum):
    """Provenance of a piece of context (§12.4).

    Anything EXTERNAL is untrusted data: it may inform reasoning but may never
    alter instructions, permissions, policies or owner identity.
    """

    OWNER = "owner"
    SYSTEM = "system"
    VERIFIED = "verified"
    EXTERNAL = "external"
    MODEL = "model"


def validate_mission_transition(current: MissionState, target: MissionState) -> None:
    """Raise ValueError unless the transition is legal.

    Kept as a free function so both the manager and the tests exercise exactly
    one implementation of the rule.
    """
    if target not in MISSION_TRANSITIONS[current]:
        allowed = sorted(s.value for s in MISSION_TRANSITIONS[current]) or ["<terminal>"]
        raise ValueError(
            f"illegal mission transition {current.value} -> {target.value}; "
            f"permitted: {', '.join(allowed)}"
        )


# --------------------------------------------------------------------------- #
# Model layer
# --------------------------------------------------------------------------- #


class ModelCapabilities(BaseModel):
    """What a model can actually do (§6.2).

    `min_ram_gb` is the approximate host RAM the model needs loaded. It is a
    declaration used for admission control, not a measurement.
    """

    model_config = ConfigDict(extra="forbid")

    context_window: int = Field(ge=512, le=2_000_000)
    supports_structured_output: bool = False
    supports_tool_calling: bool = False
    min_ram_gb: float = Field(default=0.0, ge=0.0)
    supports_reasoning: bool = False


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    system: str | None = None
    max_tokens: int = Field(default=512, ge=1, le=32_768)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    timeout_seconds: float = Field(default=60.0, gt=0.0)
    #: Callers declare the purpose so usage accounting and routing can reason
    #: about it without parsing the prompt.
    purpose: str = Field(default="unspecified", max_length=64)
    #: Set when the prompt contains data that must not leave the machine.
    contains_sensitive_data: bool = False
    require_structured_output: bool = False
    correlation_id: str | None = None


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)

    @property
    def total(self) -> int | None:
        if self.prompt_tokens is None and self.completion_tokens is None:
            return None
        return (self.prompt_tokens or 0) + (self.completion_tokens or 0)


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    model_id: str
    provider: str
    local: bool
    duration_ms: float = Field(ge=0.0)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    #: True when the provider returned a finish reason indicating truncation.
    truncated: bool = False
    correlation_id: str | None = None


class ModelHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    healthy: bool
    checked_at: datetime
    detail: str = ""
    latency_ms: float | None = Field(default=None, ge=0.0)


class ModelRecord(BaseModel):
    """A registry entry (§6.2).

    `limitations` is required to be non-empty for cloud models in practice: the
    registry refuses to advertise a model whose data-handling limits are
    undocumented, because §6.3 makes those limits a routing precondition.
    """

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64)
    local: bool
    capabilities: ModelCapabilities
    available: bool = True
    #: Declared maximum cost per 1k tokens; 0.0 for local models.
    cost_per_1k_tokens: float = Field(default=0.0, ge=0.0)
    limitations: list[str] = Field(default_factory=list)
    configuration: dict[str, Any] = Field(default_factory=dict)

    @field_validator("limitations")
    @classmethod
    def _no_empty_strings(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if v and v.strip()]
        return cleaned


# --------------------------------------------------------------------------- #
# Reasoning layer
# --------------------------------------------------------------------------- #


class Evidence(BaseModel):
    """P-02 §8.2 — a single tracked observation."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    mission_id: str | None = None
    source: str = Field(min_length=1, max_length=256)
    observation: str = Field(min_length=1)
    collected_at: datetime
    reliability: EvidenceReliability
    verification_status: UncertaintyLevel
    stance: EvidenceStance = EvidenceStance.NEUTRAL
    trust_domain: TrustDomain = TrustDomain.EXTERNAL
    #: Never store the raw secret-bearing artefact; store a reference.
    content_reference: str | None = None

    @field_validator("verification_status")
    @classmethod
    def _model_output_is_never_verified(cls, value: UncertaintyLevel, info: Any) -> UncertaintyLevel:
        """A model-generated statement cannot be VERIFIED (§8.2).

        This is the single most important epistemic rule in the phase: it stops
        confident-sounding model text from entering the system as fact.
        """
        data = info.data
        if data.get("reliability") == EvidenceReliability.MODEL_GENERATED and value in {
            UncertaintyLevel.VERIFIED,
            UncertaintyLevel.STRONGLY_SUPPORTED,
        }:
            raise ValueError(
                "model-generated evidence cannot be marked verified or strongly "
                "supported; it requires independent confirmation"
            )
        return value


class Hypothesis(BaseModel):
    """P-02 §8.3."""

    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str
    mission_id: str | None = None
    statement: str = Field(min_length=1)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    #: A subjective estimate. §8.3 forbids presenting it as an objective
    #: probability, so it is always reported alongside this label.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_basis: Literal["unvalidated_estimate", "calibrated_measurement"] = "unvalidated_estimate"
    validation_requirement: str | None = None
    status: HypothesisStatus = HypothesisStatus.PROPOSED


class ProblemAnalysis(BaseModel):
    """P-02 §8.1 — produced by deterministic analysis plus optional model input."""

    model_config = ConfigDict(extra="forbid")

    problem: str
    expected_outcome: str | None = None
    known: list[str] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    uncertainty: UncertaintyLevel = UncertaintyLevel.UNKNOWN


class Constraint(BaseModel):
    """An extracted constraint, with its provenance.

    `origin` matters: an owner-stated budget is a hard constraint, while a
    system-generated default must never be mistaken for owner authorization
    (§7.4: "Never invent a budget, authorization or success criterion").
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["budget", "time", "scope", "risk", "resource", "policy", "other"]
    value: str
    numeric_value: float | None = None
    currency: str | None = None
    origin: Literal["owner_stated", "system_default", "inferred", "assumed"]
    required: bool = False


class ClarificationQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    field: str | None = None
    #: §7.4 separates what is genuinely required from what is merely preferred.
    required: bool = True


# --------------------------------------------------------------------------- #
# Mission and plan layer
# --------------------------------------------------------------------------- #


class Mission(BaseModel):
    """P-02 §7.2 — the structured form of an owner objective."""

    model_config = ConfigDict(extra="forbid")

    mission_id: str
    owner_principal_id: str
    title: str = Field(min_length=1, max_length=200)
    original_request: str = Field(min_length=1)
    intended_outcome: str | None = None
    objective: str | None = None
    success_criteria: list[str] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    available_resources: list[str] = Field(default_factory=list)
    financial_limit: float | None = Field(default=None, ge=0.0)
    financial_limit_currency: str | None = None
    time_constraint: str | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    risk: RiskLevel = RiskLevel.LOW
    missing_information: list[ClarificationQuestion] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    approval_required: bool = False
    expected_deliverables: list[str] = Field(default_factory=list)
    category: RequestCategory = RequestCategory.GENERAL_CONVERSATION
    classification: MissionClassification = MissionClassification.SIMPLE_REQUEST
    state: MissionState = MissionState.DRAFT
    #: True when any part of the interpretation came from a model rather than
    #: deterministic extraction. Reasoning outputs must be attributable (§16).
    model_interpreted: bool = False

    @field_validator("financial_limit_currency")
    @classmethod
    def _currency_requires_limit(cls, value: str | None, info: Any) -> str | None:
        if value is not None and info.data.get("financial_limit") is None:
            raise ValueError("a currency without a financial limit is meaningless")
        return value

    def hard_constraints(self) -> list[Constraint]:
        """Constraints the planner may never trade away.

        §12.3 forbids silently dropping critical financial or security
        constraints during context reduction, and this is the accessor the
        context manager must use when truncating.
        """
        return [c for c in self.constraints if c.required or c.kind in {"budget", "policy", "risk"}]


class PlanStep(BaseModel):
    """P-02 §9.1 — one ordered unit of a plan."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    title: str = Field(min_length=1, max_length=300)
    depends_on: list[str] = Field(default_factory=list)
    #: Must name a registered capability. §9.5 rejects plans whose steps cannot
    #: be supported by any capability, which is what stops the planner from
    #: inventing work the system cannot perform.
    capability_id: str | None = None
    expected_output: str | None = None
    completion_criteria: str | None = None
    status: StepStatus = StepStatus.PENDING
    task_id: str | None = None
    #: Steps sharing a group may run in parallel (§9.4).
    parallel_group: str | None = None
    estimated_duration_seconds: float | None = Field(default=None, ge=0.0)
    risk: RiskLevel = RiskLevel.LOW


class Plan(BaseModel):
    """P-02 §9.1."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    mission_id: str
    version: int = Field(default=1, ge=1)
    objective: str = Field(min_length=1)
    strategy: str | None = None
    steps: list[PlanStep] = Field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT
    estimated_resource_requirements: dict[str, Any] = Field(default_factory=dict)
    risk: RiskLevel = RiskLevel.LOW
    approval_required: bool = False
    completion_criteria: list[str] = Field(default_factory=list)
    alternative_strategies: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    #: §9.6 requires recording why a revision happened, not just that it did.
    revision_reason: str | None = None
    supersedes_plan_id: str | None = None

    def step_ids(self) -> set[str]:
        return {s.step_id for s in self.steps}


class PlanValidationError(Exception):
    """Raised when a plan cannot be executed as written (§9.5)."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("plan rejected: " + "; ".join(self.errors))


# --------------------------------------------------------------------------- #
# Decision layer
# --------------------------------------------------------------------------- #


class DecisionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str
    description: str = Field(min_length=1)
    estimated_benefit: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_cost: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_time: float = Field(default=0.0, ge=0.0, le=1.0)
    probability_of_success: float = Field(default=0.0, ge=0.0, le=1.0)
    operational_complexity: float = Field(default=0.0, ge=0.0, le=1.0)
    resource_consumption: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_exposure: float = Field(default=0.0, ge=0.0, le=1.0)
    #: 1.0 = fully reversible, 0.0 = irreversible. Irreversibility is weighted
    #: heavily because §16 forbids irreversible decisions without approval.
    reversibility: float = Field(default=1.0, ge=0.0, le=1.0)
    strategic_alignment: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    """P-02 §10.1."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    mission_id: str | None = None
    problem: str = Field(min_length=1)
    options: list[DecisionOption] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    selected_option_id: str | None = None
    reasoning_summary: str | None = None
    risk: RiskLevel = RiskLevel.LOW
    uncertainty: UncertaintyLevel = UncertaintyLevel.UNKNOWN
    approval_required: bool = False
    status: DecisionStatus = DecisionStatus.RECOMMENDATION
    #: Present when the decision was refused rather than made.
    refusal_reason: str | None = None


# --------------------------------------------------------------------------- #
# Capability and response layer
# --------------------------------------------------------------------------- #


class Capability(BaseModel):
    """P-02 §11.2 — something the system can legitimately perform.

    `implementation` is required at registration time: §11.2 forbids advertising
    capabilities without working implementations, so a capability cannot be
    declared by metadata alone.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    capability_id: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    required_permissions: list[str] = Field(default_factory=list)
    risk: RiskLevel = RiskLevel.LOW
    resource_requirements: dict[str, Any] = Field(default_factory=dict)
    available: bool = True
    supported_task_categories: list[str] = Field(default_factory=list)
    #: The handler name this capability dispatches to, which must be one of the
    #: three registered P-01 handlers. Nothing else is executable.
    task_handler: Literal["system.noop", "system.echo", "system.wait"] | None = None


class IntelligenceResponse(BaseModel):
    """P-02 §13 — the single structured output type.

    Every intelligence API response is one of these, so a client never has to
    parse free-form model text to find out what happened.
    """

    model_config = ConfigDict(extra="forbid")

    status: ResponseStatus
    category: ResponseCategory
    message: str = ""
    mission_id: str | None = None
    task_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    approval_required: bool = False
    suggested_next_step: str | None = None
    #: Non-empty when the engine could not do the work and is saying so plainly.
    limitations: list[str] = Field(default_factory=list)
    correlation_id: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == ResponseStatus.OK


class MissionProgress(BaseModel):
    """P-02 §11.4 — progress derived from real task states.

    §11.4 requires percentages to be calculated from actual task states rather
    than invented by a model, so this is computed by `orchestrator` code from
    persisted step rows and never taken from model output.
    """

    model_config = ConfigDict(extra="forbid")

    mission_id: str
    state: MissionState
    total_steps: int = 0
    completed: int = 0
    active: int = 0
    pending: int = 0
    failed: int = 0
    blocked: int = 0
    awaiting_approval: int = 0
    percent_complete: float = Field(default=0.0, ge=0.0, le=100.0)
    #: Set when progress could not be derived from task states.
    incomplete_data: bool = False
