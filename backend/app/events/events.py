"""Event types and the event model (P-01 §8)."""
from __future__ import annotations

import datetime as dt
import enum
import uuid
from dataclasses import dataclass, field


class EventType(str, enum.Enum):
    APPLICATION_STARTED = "ApplicationStarted"
    APPLICATION_READY = "ApplicationReady"
    APPLICATION_STOPPING = "ApplicationStopping"
    APPLICATION_STOPPED = "ApplicationStopped"
    TASK_CREATED = "TaskCreated"
    TASK_QUEUED = "TaskQueued"
    TASK_STARTED = "TaskStarted"
    TASK_PROGRESS_UPDATED = "TaskProgressUpdated"
    TASK_COMPLETED = "TaskCompleted"
    TASK_FAILED = "TaskFailed"
    TASK_CANCELLED = "TaskCancelled"
    APPROVAL_REQUESTED = "ApprovalRequested"
    APPROVAL_GRANTED = "ApprovalGranted"
    APPROVAL_REJECTED = "ApprovalRejected"
    PERMISSION_DENIED = "PermissionDenied"
    SYSTEM_WARNING = "SystemWarning"
    SYSTEM_ERROR = "SystemError"
    DATABASE_UNAVAILABLE = "DatabaseUnavailable"
    RESOURCE_THRESHOLD_EXCEEDED = "ResourceThresholdExceeded"
    # P-02 Master Intelligence events
    MISSION_RECEIVED = "MissionReceived"
    PLAN_CREATED = "PlanCreated"
    PLAN_APPROVED = "PlanApproved"
    PLAN_EXECUTION_STARTED = "PlanExecutionStarted"
    STEP_VERIFIED = "StepVerified"
    STEP_VERIFICATION_FAILED = "StepVerificationFailed"
    DECISION_RECORDED = "DecisionRecorded"
    PLAN_COMPLETED = "PlanCompleted"
    PLAN_FAILED = "PlanFailed"
    # P-03 Opportunity Discovery events
    OPPORTUNITY_DISCOVERED = "OpportunityDiscovered"
    OPPORTUNITY_STATUS_CHANGED = "OpportunityStatusChanged"
    RESEARCH_COMPLETED = "ResearchCompleted"
    OPPORTUNITY_SCORED = "OpportunityScored"
    OPPORTUNITY_VALIDATED = "OpportunityValidated"
    OPPORTUNITY_HARD_REJECTED = "OpportunityHardRejected"
    PROMPT_INJECTION_DETECTED = "PromptInjectionDetected"
    # P-04 Dynamic Agent Factory events
    AGENT_CREATED = "AgentCreated"
    AGENT_STATE_CHANGED = "AgentStateChanged"
    AGENT_CREATION_DECIDED = "AgentCreationDecided"
    AGENT_PERMISSION_CHANGED = "AgentPermissionChanged"
    AGENT_ASSIGNED = "AgentAssigned"
    AGENT_HEALTH_CHANGED = "AgentHealthChanged"
    AGENT_EMERGENCY_STOP = "AgentEmergencyStop"
    # P-05 Universal Digital Execution Engine events
    EXECUTION_SUBMITTED = "ExecutionSubmitted"
    EXECUTION_COMPLETED = "ExecutionCompleted"
    EXECUTION_FAILED = "ExecutionFailed"
    EXECUTION_REJECTED = "ExecutionRejected"
    EXECUTION_CANCELLED = "ExecutionCancelled"
    EXECUTION_AWAITING_APPROVAL = "ExecutionAwaitingApproval"
    EXECUTION_VERIFICATION_FAILED = "ExecutionVerificationFailed"
    EXECUTION_EMERGENCY_STOP = "ExecutionEmergencyStop"
    EXECUTION_EMERGENCY_RESUMED = "ExecutionEmergencyResumed"
    SANDBOX_VIOLATION = "SandboxViolation"
    WORKFLOW_STARTED = "WorkflowStarted"
    WORKFLOW_COMPLETED = "WorkflowCompleted"
    WORKFLOW_FAILED = "WorkflowFailed"
    WORKFLOW_PAUSED = "WorkflowPaused"
    WORKFLOW_RECOVERY_REQUIRED = "WorkflowRecoveryRequired"
    # P-06 Business Creation Engine events (§28/§30 of the P-06 prompt).
    BUSINESS_CREATED = "BusinessCreated"
    BUSINESS_LIFECYCLE_CHANGED = "BusinessLifecycleChanged"
    BUSINESS_ELIGIBILITY_DECIDED = "BusinessEligibilityDecided"
    BUSINESS_TEMPLATE_VERSIONED = "BusinessTemplateVersioned"
    BUSINESS_BLUEPRINT_APPROVED = "BusinessBlueprintApproved"
    BUSINESS_DECLARATION_RECORDED = "BusinessDeclarationRecorded"
    BUSINESS_READINESS_REVIEWED = "BusinessReadinessReviewed"
    BUSINESS_PLATFORM_GATE_HIT = "BusinessPlatformGateHit"
    BUSINESS_PUBLISH_REFUSED = "BusinessPublishRefused"
    BUSINESS_ISOLATION_VIOLATION = "BusinessIsolationViolation"
    BUSINESS_LAUNCH_APPROVED = "BusinessLaunchApproved"
    # P-14 Stage B (DEF-I7): non-status business mutations (declaration,
    # blueprint, channel, readiness, campaign changes) — status changes
    # keep flowing through BUSINESS_LIFECYCLE_CHANGED.
    BUSINESS_UPDATED = "BusinessUpdated"
    # P-07 Financial Intelligence Engine events.
    FINANCIAL_PROFILE_CREATED = "FinancialProfileCreated"
    FINANCIAL_JOURNAL_POSTED = "FinancialJournalPosted"
    FINANCIAL_REVENUE_VERIFIED = "FinancialRevenueVerified"
    FINANCIAL_SPEND_BLOCKED = "FinancialSpendBlocked"
    FINANCIAL_ALERT_RAISED = "FinancialAlertRaised"
    FINANCIAL_ISOLATION_VIOLATION = "FinancialIsolationViolation"
    FINANCIAL_RECONCILIATION_DISCREPANCY = "FinancialReconciliationDiscrepancy"
    # P-08 Survival and Scaling Engine events.
    SURVIVAL_HEALTH_EVALUATED = "SurvivalHealthEvaluated"
    SURVIVAL_DECISION_RECORDED = "SurvivalDecisionRecorded"
    SURVIVAL_EXPERIMENT_STOPPED = "SurvivalExperimentStopped"
    SURVIVAL_SCALING_ASSESSED = "SurvivalScalingAssessed"
    SURVIVAL_BUSINESS_PAUSED = "SurvivalBusinessPaused"
    SURVIVAL_BUSINESS_RESUMED = "SurvivalBusinessResumed"
    SURVIVAL_CLOSURE_PROPOSED = "SurvivalClosureProposed"
    SURVIVAL_BUSINESS_CLOSED = "SurvivalBusinessClosed"
    # P-12 Autonomous Operations Engine — business-workflow level
    # events (distinct from the P-05 tool-step WORKFLOW_* types).
    OPERATIONS_WORKFLOW_CREATED = "OperationsWorkflowCreated"
    OPERATIONS_WORKFLOW_VALIDATED = "OperationsWorkflowValidated"
    OPERATIONS_WORKFLOW_STARTED = "OperationsWorkflowStarted"
    OPERATIONS_TASK_STARTED = "OperationsTaskStarted"
    OPERATIONS_TASK_COMPLETED = "OperationsTaskCompleted"
    OPERATIONS_TASK_FAILED = "OperationsTaskFailed"
    OPERATIONS_WORKFLOW_COMPLETED = "OperationsWorkflowCompleted"
    OPERATIONS_WORKFLOW_FAILED = "OperationsWorkflowFailed"
    OPERATIONS_WORKFLOW_PAUSED = "OperationsWorkflowPaused"
    OPERATIONS_APPROVAL_REQUIRED = "OperationsApprovalRequired"
    OPERATIONS_DECISION_RECORDED = "OperationsDecisionRecorded"
    OPERATIONS_TRIGGER_FIRED = "OperationsTriggerFired"
    OPERATIONS_RECOVERY_ATTEMPTED = "OperationsRecoveryAttempted"
    OPERATIONS_TASK_DEAD_LETTERED = "OperationsTaskDeadLettered"
    OPERATIONS_EMERGENCY_STOP = "OperationsEmergencyStop"
    OPERATIONS_EMERGENCY_RESUMED = "OperationsEmergencyResumed"
    OPERATIONS_AUTONOMY_CHANGED = "OperationsAutonomyPolicyChanged"
    OPERATIONS_BUDGET_BLOCKED = "OperationsBudgetBlocked"
    # P-14 Stage B (DEF-I1): the two §6 categories that had no event
    # type at all in Stage A — security incidents (P-10) and portfolio
    # risk assessments (P-13) are now first-class bus events.
    SECURITY_INCIDENT_DETECTED = "SecurityIncidentDetected"
    PORTFOLIO_RISK_DETECTED = "PortfolioRiskDetected"


# Events of these types are also persisted to system_events (critical set).
CRITICAL_EVENT_TYPES = {
    EventType.APPROVAL_REQUESTED, EventType.APPROVAL_GRANTED, EventType.APPROVAL_REJECTED,
    EventType.PERMISSION_DENIED, EventType.SYSTEM_WARNING, EventType.SYSTEM_ERROR,
    EventType.DATABASE_UNAVAILABLE, EventType.RESOURCE_THRESHOLD_EXCEEDED,
    EventType.TASK_FAILED, EventType.APPLICATION_STARTED, EventType.APPLICATION_STOPPED,
    EventType.PLAN_APPROVED, EventType.PLAN_FAILED, EventType.STEP_VERIFICATION_FAILED,
    EventType.DECISION_RECORDED,
    EventType.OPPORTUNITY_STATUS_CHANGED, EventType.OPPORTUNITY_HARD_REJECTED,
    EventType.PROMPT_INJECTION_DETECTED,
    EventType.AGENT_STATE_CHANGED, EventType.AGENT_PERMISSION_CHANGED,
    EventType.AGENT_EMERGENCY_STOP, EventType.AGENT_CREATION_DECIDED,
    EventType.EXECUTION_FAILED, EventType.EXECUTION_REJECTED,
    EventType.EXECUTION_VERIFICATION_FAILED, EventType.EXECUTION_EMERGENCY_STOP,
    EventType.SANDBOX_VIOLATION, EventType.WORKFLOW_FAILED,
    EventType.WORKFLOW_RECOVERY_REQUIRED,
    EventType.BUSINESS_CREATED, EventType.BUSINESS_LIFECYCLE_CHANGED,
    EventType.BUSINESS_ELIGIBILITY_DECIDED, EventType.BUSINESS_READINESS_REVIEWED,
    EventType.BUSINESS_PLATFORM_GATE_HIT, EventType.BUSINESS_PUBLISH_REFUSED,
    EventType.BUSINESS_ISOLATION_VIOLATION, EventType.BUSINESS_LAUNCH_APPROVED,
    EventType.FINANCIAL_PROFILE_CREATED, EventType.FINANCIAL_SPEND_BLOCKED,
    # P-14 Stage B (DEF-I3): journal postings and revenue verifications
    # are financially significant and now persist like the rest of the
    # critical set (their publish sites live in P-07's ledger/revenue
    # services, wired by the facade).
    EventType.FINANCIAL_JOURNAL_POSTED, EventType.FINANCIAL_REVENUE_VERIFIED,
    EventType.FINANCIAL_ISOLATION_VIOLATION,
    EventType.FINANCIAL_RECONCILIATION_DISCREPANCY,
    EventType.FINANCIAL_ALERT_RAISED,
    # P-14 Stage B (DEF-I1).
    EventType.SECURITY_INCIDENT_DETECTED, EventType.PORTFOLIO_RISK_DETECTED,
    EventType.SURVIVAL_BUSINESS_PAUSED, EventType.SURVIVAL_BUSINESS_CLOSED,
    EventType.SURVIVAL_EXPERIMENT_STOPPED,
    EventType.OPERATIONS_WORKFLOW_FAILED, EventType.OPERATIONS_TASK_FAILED,
    EventType.OPERATIONS_TASK_DEAD_LETTERED, EventType.OPERATIONS_EMERGENCY_STOP,
    EventType.OPERATIONS_BUDGET_BLOCKED, EventType.OPERATIONS_APPROVAL_REQUIRED,
}


@dataclass
class Event:
    event_type: EventType
    source: str
    payload: dict = field(default_factory=dict)
    correlation_id: str | None = None
    task_id: str | None = None
    severity: str = "info"
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    # P-14 Stage B (DEF-I2): the remaining §6 envelope fields, all
    # optional and additive — existing publishers and consumers are
    # unaffected. ``processing_status`` is maintained by the bus:
    # pending -> delivered | partially_failed | dropped.
    business_id: str | None = None
    workflow_id: str | None = None
    actor: str | None = None
    schema_version: int = 1
    processing_status: str = "pending"
