"""Master Intelligence Engine (P-02).

The intelligence layer sits between the owner and the P-01 Core OS. It reasons,
plans and recommends; it never executes directly. All execution passes through
the existing permission, approval and task-management infrastructure.

Two invariants hold across every module in this package:

* **Bounded authority.** Nothing here can bypass `PermissionEngine`, raise its
  own autonomy level, or submit work except through `TaskManager.submit`.
* **No fabricated capability.** When a model is unavailable or evidence is
  insufficient, the engine reports that plainly. It never invents an answer, a
  measurement, a budget or an authorization.

Module map (§4). Each module owns one concern and none of them reach into
persistence, permissions, execution, tools, finance or UI:

| Module | Concern |
|---|---|
| `schemas` | Enums and Pydantic contracts; the mission state machine |
| `providers` | Provider adapters; `none` when no runtime is installed |
| `registry` | Known models and their declared capabilities |
| `router` | Provider-independent selection, admission and fallback (§6) |
| `missions` | Deterministic request interpretation (§7) |
| `reasoning` | Evidence, hypotheses, uncertainty (§8) |
| `capabilities` | What the system can actually do (§11.2) |
| `planning` | Decomposition, dependency graph, validation, replanning (§9) |
| `decisions` | Transparent scoring and risk classification (§10) |
| `autonomy` | Who may act, and at what level (§15) |
| `prompts` | Static invariants and untrusted-content fencing (§12.4) |
| `context` | Assembly, prioritisation, budget, injection scanning (§12) |
| `orchestrator` | Dispatch through P-01 and progress from real states (§11) |
| `output` | Schema validation of model output (§13) |
| `engine` | The facade the API talks to (§5) |
| `factory` | Composition root; wires the engine to P-01 services |
"""

from __future__ import annotations

from .autonomy import AutonomyController, AutonomyEscalationError, AutonomyState
from .capabilities import (
    REAL_HANDLERS,
    CapabilityRegistry,
    UnknownCapabilityError,
    default_capabilities,
)
from .context import (
    AssembledContext,
    ContextItem,
    ContextManager,
    ContextOverflowError,
    ContextPriority,
    InjectionFinding,
)
from .decisions import (
    APPROVAL_MANDATORY_AT,
    DEFAULT_WEIGHTS,
    INVERTED_CRITERIA,
    DecisionEngine,
    DecisionScorer,
    RiskEvaluator,
    RiskFactors,
    ScoringBreakdown,
    UnauthorizedDecisionError,
)
from .engine import IntelligenceEngine, MissionRecord
from .factory import (
    IntelligenceServices,
    build_inference_policy,
    build_intelligence,
    build_providers,
    probe_host_resources,
)
from .missions import Interpretation, MissionInterpreter
from .orchestrator import (
    DispatchPolicy,
    DispatchRecord,
    DispatchRefusedError,
    FailureAssessment,
    Orchestrator,
    ProgressMonitor,
    TaskDispatcher,
)
from .output import (
    AUTHORITY_FIELDS,
    MAX_REPAIR_ATTEMPTS,
    InterpretationPayload,
    StructuredOutputError,
    StructuredOutputParser,
    check_authority_fields,
    extract_json,
)
from .planning import (
    MAX_DEPENDENCIES_PER_STEP,
    MAX_PLAN_STEPS,
    DependencyResolver,
    Planner,
    PlanValidator,
    Replanner,
    TaskDecomposer,
    ValidationPolicy,
    ValidationResult,
)
from .prompts import (
    INVARIANTS,
    SYSTEM_PROMPT,
    UNTRUSTED_BEGIN,
    UNTRUSTED_END,
    fence_untrusted,
    interpretation_request_schema,
)
from .providers import (
    ModelOutputError,
    ModelProvider,
    ModelTimeoutError,
    ModelUnavailableError,
    NoRuntimeProvider,
    OllamaProvider,
)
from .reasoning import (
    EvidenceManager,
    HypothesisManager,
    InsufficientEvidenceError,
    ProblemAnalyzer,
    ReasoningPipeline,
    ReasoningTrace,
    UncertaintyAssessment,
    UncertaintyManager,
    weakest,
)
from .registry import ModelRegistry, UnknownModelError
from .router import (
    CHARS_PER_TOKEN_ESTIMATE,
    InferencePolicy,
    ModelRouter,
    Rejection,
    ResourceSnapshot,
    RouteDecision,
    RouteRequirements,
    UsageRecord,
    estimate_tokens,
)
from .schemas import (
    EXECUTION_PERMITTED_LEVELS,
    TERMINAL_MISSION_STATES,
    UNIMPLEMENTED_LEVELS,
    AutonomyLevel,
    Capability,
    ClarificationQuestion,
    Constraint,
    Decision,
    DecisionOption,
    DecisionStatus,
    Evidence,
    EvidenceReliability,
    EvidenceStance,
    GenerationRequest,
    GenerationResult,
    Hypothesis,
    HypothesisStatus,
    IntelligenceResponse,
    Mission,
    MissionClassification,
    MissionProgress,
    MissionState,
    ModelCapabilities,
    ModelHealth,
    ModelRecord,
    Plan,
    PlanStatus,
    PlanStep,
    PlanValidationError,
    ProblemAnalysis,
    RequestCategory,
    ResponseCategory,
    ResponseStatus,
    RiskLevel,
    StepStatus,
    TokenUsage,
    TrustDomain,
    UncertaintyLevel,
    validate_mission_transition,
)

__all__ = [
    # autonomy (§15)
    "AutonomyController",
    "AutonomyEscalationError",
    "AutonomyState",
    # capabilities (§11.2)
    "REAL_HANDLERS",
    "CapabilityRegistry",
    "UnknownCapabilityError",
    "default_capabilities",
    # context (§12)
    "AssembledContext",
    "ContextItem",
    "ContextManager",
    "ContextOverflowError",
    "ContextPriority",
    "InjectionFinding",
    # decisions (§10)
    "APPROVAL_MANDATORY_AT",
    "DEFAULT_WEIGHTS",
    "INVERTED_CRITERIA",
    "DecisionEngine",
    "DecisionScorer",
    "RiskEvaluator",
    "RiskFactors",
    "ScoringBreakdown",
    "UnauthorizedDecisionError",
    # engine (§5) and composition root
    "IntelligenceEngine",
    "IntelligenceServices",
    "MissionRecord",
    "build_inference_policy",
    "build_intelligence",
    "build_providers",
    "probe_host_resources",
    # missions (§7)
    "Interpretation",
    "MissionInterpreter",
    # orchestration (§11)
    "DispatchPolicy",
    "DispatchRecord",
    "DispatchRefusedError",
    "FailureAssessment",
    "Orchestrator",
    "ProgressMonitor",
    "TaskDispatcher",
    # structured output (§13)
    "AUTHORITY_FIELDS",
    "MAX_REPAIR_ATTEMPTS",
    "InterpretationPayload",
    "StructuredOutputError",
    "StructuredOutputParser",
    "check_authority_fields",
    "extract_json",
    # planning (§9)
    "MAX_DEPENDENCIES_PER_STEP",
    "MAX_PLAN_STEPS",
    "DependencyResolver",
    "PlanValidator",
    "Planner",
    "Replanner",
    "TaskDecomposer",
    "ValidationPolicy",
    "ValidationResult",
    # prompts (§12.4)
    "INVARIANTS",
    "SYSTEM_PROMPT",
    "UNTRUSTED_BEGIN",
    "UNTRUSTED_END",
    "fence_untrusted",
    "interpretation_request_schema",
    # providers and routing (§6)
    "CHARS_PER_TOKEN_ESTIMATE",
    "InferencePolicy",
    "ModelOutputError",
    "ModelProvider",
    "ModelRegistry",
    "ModelRouter",
    "ModelTimeoutError",
    "ModelUnavailableError",
    "NoRuntimeProvider",
    "OllamaProvider",
    "Rejection",
    "ResourceSnapshot",
    "RouteDecision",
    "RouteRequirements",
    "UnknownModelError",
    "UsageRecord",
    "estimate_tokens",
    # reasoning (§8)
    "EvidenceManager",
    "HypothesisManager",
    "InsufficientEvidenceError",
    "ProblemAnalyzer",
    "ReasoningPipeline",
    "ReasoningTrace",
    "UncertaintyAssessment",
    "UncertaintyManager",
    "weakest",
    # schemas and the mission state machine (§7.3)
    "EXECUTION_PERMITTED_LEVELS",
    "TERMINAL_MISSION_STATES",
    "UNIMPLEMENTED_LEVELS",
    "AutonomyLevel",
    "Capability",
    "ClarificationQuestion",
    "Constraint",
    "Decision",
    "DecisionOption",
    "DecisionStatus",
    "Evidence",
    "EvidenceReliability",
    "EvidenceStance",
    "GenerationRequest",
    "GenerationResult",
    "Hypothesis",
    "HypothesisStatus",
    "IntelligenceResponse",
    "Mission",
    "MissionClassification",
    "MissionProgress",
    "MissionState",
    "ModelCapabilities",
    "ModelHealth",
    "ModelRecord",
    "Plan",
    "PlanStatus",
    "PlanStep",
    "PlanValidationError",
    "ProblemAnalysis",
    "RequestCategory",
    "ResponseCategory",
    "ResponseStatus",
    "RiskLevel",
    "StepStatus",
    "TokenUsage",
    "TrustDomain",
    "UncertaintyLevel",
    "validate_mission_transition",
]
