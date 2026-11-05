"""Execution vocabularies and request models (P-05 Stage 2).

This module is data and validation. It holds no policy and no I/O: the outcome
vocabulary, the tool lifecycle, the risk mapping, and the shape of an execution
request. Everything else in the phase imports from here, which is why the
vocabularies are literals rather than derived — a status that a database CHECK
constraint enforces must not depend on what some module happens to compute today.

Three properties of this vocabulary matter more than its contents.

**Fourteen outcomes, and `COMPLETED` is not one of them by default.** §6.1 of the
brief fixes the list. The rule that gives it meaning is the one underneath: the
engine must not return `COMPLETED` merely because a tool returned without raising.
A tool that succeeds silently has produced `COMPLETED_WITH_WARNINGS` at best until
the result validator has checked the outcome against what was asked for. So the
vocabulary has two success states and the difference between them is evidence, not
mood.

**Requested, approved, executed and verified are four different things.** §6
requires the request to distinguish them and forbids assuming they are identical.
They live in four different places on purpose: what was *requested* is on the
request row, what was *approved* is the approval binding that gate-checked it, what
was *executed* is recorded by the adapter on the run, and what was *verified* is the
result validator's verdict. Collapsing any two of them is how an engine ends up
reporting that it did what it was asked rather than what it did.

**Risk 3 has no approval path.** Risk 0-2 map onto the existing
`app.intelligence.engine.RiskLevel` and Risk 2 requires an owner approval; Risk 3 is
rejected outright, the same shape as P-04's level-3 capability prohibitions. A
high-priority task never overrides a risk classification (§8).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ADAPTER_TYPES",
    "EXECUTION_OUTCOMES",
    "OUTCOME_TRANSITIONS",
    "RESUMABLE_OUTCOMES",
    "TERMINAL_OUTCOMES",
    "TOOL_STATES",
    "TOOL_STATE_TRANSITIONS",
    "RISK_TO_LEVEL",
    "PROHIBITED_RISK",
    "ExecutionOutcome",
    "ToolState",
    "RiskClass",
    "AdapterType",
    "ExecutionRequestInput",
    "RetryPolicyInput",
    "ExecutionRequestView",
    "ExecutionRunView",
    "ToolView",
    "ToolRegistrationInput",
    "WORKFLOW_RUN_STATES",
    "WORKFLOW_DEFINITION_STATUSES",
    "WORKFLOW_STEP_STATES",
    "BROWSER_SESSION_STATES",
    "APPROVAL_RISK_BY_CLASS",
]


# --------------------------------------------------------------------------- #
# §6.1 The fourteen execution outcomes
# --------------------------------------------------------------------------- #
class ExecutionOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    VALIDATING = "VALIDATING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    INTERRUPTED = "INTERRUPTED"
    REQUIRES_HUMAN_ACTION = "REQUIRES_HUMAN_ACTION"
    REQUIRES_RECONCILIATION = "REQUIRES_RECONCILIATION"


#: §6.1's order, which is the lifecycle's order rather than alphabetical: a reader
#: scanning this list sees a request's life, not a dictionary.
EXECUTION_OUTCOMES = tuple(o.value for o in ExecutionOutcome)
assert len(EXECUTION_OUTCOMES) == 14, EXECUTION_OUTCOMES

#: Nothing follows these. `REQUIRES_RECONCILIATION` is terminal even though a human
#: will act on it, because §16.4's whole point is that the engine must not resume an
#: interrupted external action on its own: a person opens a *new* request with the
#: reconciled facts, rather than this row quietly becoming running again.
TERMINAL_OUTCOMES = frozenset({
    ExecutionOutcome.COMPLETED.value,
    ExecutionOutcome.COMPLETED_WITH_WARNINGS.value,
    ExecutionOutcome.FAILED.value,
    ExecutionOutcome.REJECTED.value,
    ExecutionOutcome.CANCELLED.value,
    ExecutionOutcome.TIMED_OUT.value,
    ExecutionOutcome.REQUIRES_RECONCILIATION.value,
})

#: Paused, not finished: these may move again, but only through the transitions
#: below and never by an agent's own say-so.
RESUMABLE_OUTCOMES = frozenset({
    ExecutionOutcome.AWAITING_APPROVAL.value,
    ExecutionOutcome.REQUIRES_HUMAN_ACTION.value,
    ExecutionOutcome.INTERRUPTED.value,
})

OUTCOME_TRANSITIONS: dict[str, frozenset[str]] = {
    "ACCEPTED": frozenset({"VALIDATING", "REJECTED", "CANCELLED"}),
    "VALIDATING": frozenset({"AWAITING_APPROVAL", "QUEUED", "REJECTED", "FAILED", "CANCELLED"}),
    "AWAITING_APPROVAL": frozenset({"QUEUED", "REJECTED", "CANCELLED",
                                    "REQUIRES_HUMAN_ACTION"}),
    "QUEUED": frozenset({"RUNNING", "CANCELLED", "REJECTED", "REQUIRES_HUMAN_ACTION"}),
    "RUNNING": frozenset({"COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED",
                          "TIMED_OUT", "INTERRUPTED", "CANCELLED",
                          "REQUIRES_HUMAN_ACTION", "REQUIRES_RECONCILIATION"}),
    # A pause can be resumed or ended, and an interrupted run that cannot be
    # proven safe goes to reconciliation rather than back to running (§16.4).
    # REJECTED is reachable from both waiting states: a retry re-runs policy,
    # and work policy now refuses was never run, so it is rejected rather than
    # failed.
    "REQUIRES_HUMAN_ACTION": frozenset({"QUEUED", "RUNNING", "CANCELLED", "FAILED",
                                        "REJECTED", "REQUIRES_RECONCILIATION"}),
    "INTERRUPTED": frozenset({"QUEUED", "RUNNING", "FAILED", "CANCELLED",
                              "REJECTED", "REQUIRES_RECONCILIATION"}),
    "COMPLETED": frozenset(),
    "COMPLETED_WITH_WARNINGS": frozenset(),
    "FAILED": frozenset(),
    "REJECTED": frozenset(),
    "CANCELLED": frozenset(),
    "TIMED_OUT": frozenset(),
    "REQUIRES_RECONCILIATION": frozenset(),
}
assert set(OUTCOME_TRANSITIONS) == set(EXECUTION_OUTCOMES)


# --------------------------------------------------------------------------- #
# §7 Tool lifecycle
# --------------------------------------------------------------------------- #
class ToolState(str, Enum):
    REGISTERED = "REGISTERED"
    VALIDATING = "VALIDATING"
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"
    DEPRECATED = "DEPRECATED"
    REMOVED = "REMOVED"


TOOL_STATES = tuple(s.value for s in ToolState)

#: "A tool must not become AVAILABLE until its configuration and health checks
#: pass" (§7), so AVAILABLE is reachable only from VALIDATING. DISABLED is
#: reachable from anything that is not REMOVED, because turning a tool off must
#: never be blocked by where it happens to be — the same asymmetry P-04 applied to
#: capability revocation during an emergency stop.
TOOL_STATE_TRANSITIONS: dict[str, frozenset[str]] = {
    "REGISTERED": frozenset({"VALIDATING", "DISABLED", "REMOVED"}),
    "VALIDATING": frozenset({"AVAILABLE", "DEGRADED", "DISABLED", "REMOVED"}),
    "AVAILABLE": frozenset({"DEGRADED", "DISABLED", "DEPRECATED", "REMOVED"}),
    "DEGRADED": frozenset({"VALIDATING", "AVAILABLE", "DISABLED", "DEPRECATED", "REMOVED"}),
    "DISABLED": frozenset({"VALIDATING", "DEPRECATED", "REMOVED"}),
    "DEPRECATED": frozenset({"DISABLED", "REMOVED"}),
    "REMOVED": frozenset(),
}
assert set(TOOL_STATE_TRANSITIONS) == set(TOOL_STATES)

#: States a request may actually be routed to. DEGRADED is included because a
#: degraded tool still works — it is the scheduler's job to prefer a healthy one,
#: and refusing degraded tools outright would turn a warning into an outage.
ROUTABLE_TOOL_STATES = frozenset({"AVAILABLE", "DEGRADED"})


# --------------------------------------------------------------------------- #
# §8 Risk classification
# --------------------------------------------------------------------------- #
class RiskClass(int, Enum):
    """§8's four categories. Ints because the brief numbers them and orders matter."""

    SAFE_INTERNAL = 0
    CONTROLLED = 1
    SENSITIVE_EXTERNAL = 2
    PROHIBITED = 3


#: The mapping onto the risk vocabulary P-02 already persists, so an execution
#: request and a mission are graded on one scale rather than two that have to be
#: reconciled later.
RISK_TO_LEVEL = {
    0: "LOW",
    1: "MODERATE",
    2: "HIGH",
    3: "CRITICAL",
}

#: Risk 3 is rejected by the normal execution system and has **no approval path**
#: (§8). Kept as its own literal so the refusal can be enforced before any row,
#: tool or approval is consulted — the shape P-04 Stage 5 proved necessary, where
#: enforcing a prohibition from a code literal rather than a table row meant no edit
#: to a row could lift it.
PROHIBITED_RISK = 3

#: §8's Risk-3 examples, as action-name patterns. A prohibition list that only
#: existed as prose would be a rule nobody could test.
PROHIBITED_ACTIONS = frozenset({
    "secrets.read_raw",
    "security.disable",
    "security.bypass",
    "filesystem.unrestricted",
    "code.unrestricted_exec",
    "accounts.unauthorized_access",
    "access_control.bypass",
    "financial.unauthorized_transaction",
    "audit.delete",
    "audit.modify",
    "platform_security.circumvent",
    "uac.approve",
    "uac.bypass",
    "mfa.bypass",
    "captcha.bypass",
})


# --------------------------------------------------------------------------- #
# §5 Adapter families
# --------------------------------------------------------------------------- #
class AdapterType(str, Enum):
    FILESYSTEM = "filesystem"
    CODE = "code"
    BROWSER = "browser"
    DESKTOP = "desktop"
    API = "api"
    DOCUMENT = "document"
    DATA = "data"


ADAPTER_TYPES = tuple(a.value for a in AdapterType)

#: Adapters that exist as interfaces but cannot run here, and why. §30's closing
#: rule: implement the interface, document the limitation, leave it disabled rather
#: than pretend it is operational. Both of these need a display and an input device
#: stack this environment does not have, and the plan already records that the
#: browser adapter ships as a `DisabledAdapter` rather than pulling in Playwright
#: plus browser binaries on a 2 GB-GPU, CPU-bound machine.
ADAPTERS_UNSUPPORTED_HERE = {
    "browser": "no browser binary and no display; Playwright is not installed and "
               "§26/§30 rule 21 forbid adding heavyweight automation here",
    "desktop": "Windows UI Automation is unavailable: this workspace is Linux with "
               "no display server, and §12 cannot be tested on the target machine "
               "from here",
}


# --------------------------------------------------------------------------- #
# §6 The execution request
# --------------------------------------------------------------------------- #
class RetryPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=1, ge=1, le=5)
    backoff_seconds: float = Field(default=0.0, ge=0.0, le=300.0)

    @property
    def retryable(self) -> bool:
        return self.max_attempts > 1


class ExecutionRequestInput(BaseModel):
    """What an agent submits. §6's field list, minus the fields the engine owns.

    `risk_level`, `status` and `approval_reference` are absent on purpose: an agent
    that could declare its own risk classification could declare everything Risk 0,
    and §8.1 is explicit that the engine verifies independently rather than trusting
    the requester. Risk is computed in :mod:`app.execution.policy` from the tool and
    the action, never read from the request.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=64)
    tool_id: str = Field(min_length=1, max_length=64)
    action_name: str = Field(min_length=1, max_length=128)
    action_parameters: dict[str, Any] = Field(default_factory=dict)
    input_references: list[str] = Field(default_factory=list, max_length=64)
    required_capabilities: list[str] = Field(default_factory=list, max_length=32)
    requested_scope: str = Field(default="", max_length=512)
    priority: int = Field(default=5, ge=1, le=10)
    timeout_seconds: int = Field(default=60, ge=1, le=3600)
    retry_policy: RetryPolicyInput = Field(default_factory=RetryPolicyInput)
    expected_output_schema: dict[str, Any] = Field(default_factory=dict)
    #: Repeating a request with the same key returns the original rather than doing
    #: the work twice — the control §16.2 asks for on anything that could duplicate.
    idempotency_key: str | None = Field(default=None, max_length=128)
    business_id: str | None = Field(default=None, max_length=64)


class ExecutionRequestView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    agent_id: str
    tool_id: str
    adapter_type: str
    action_name: str
    requested_scope: str
    risk_level: int
    risk_name: str
    status: str
    priority: int
    timeout_seconds: int
    approval_reference: str | None = None
    idempotency_key: str | None = None
    business_id: str | None = None
    refusal_reason: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Any) -> "ExecutionRequestView":
        return cls(
            id=row.id, task_id=row.task_id, agent_id=row.agent_id, tool_id=row.tool_id,
            adapter_type=row.adapter_type, action_name=row.action_name,
            requested_scope=row.requested_scope, risk_level=int(row.risk_level),
            risk_name=RISK_TO_LEVEL.get(int(row.risk_level), "UNKNOWN"),
            status=row.status, priority=int(row.priority),
            timeout_seconds=int(row.timeout_seconds),
            approval_reference=row.approval_reference,
            idempotency_key=row.idempotency_key, business_id=row.business_id,
            refusal_reason=row.refusal_reason, created_at=row.created_at,
            started_at=row.started_at, completed_at=row.completed_at,
            expires_at=row.expires_at)


class ExecutionRunView(BaseModel):
    """One attempt. Separate from the request because a retry is a second attempt at
    the same request, and collapsing them would lose which attempt produced what."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    execution_request_id: str
    worker_id: str
    status: str
    attempt: int
    #: What the adapter actually did, as opposed to what was asked for. §6 forbids
    #: treating the two as identical, so this is its own column rather than a copy of
    #: the request's action name.
    executed_action: str | None = None
    exit_code: int | None = None
    result_summary: str | None = None
    error_category: str | None = None
    #: The result validator's verdict, which is not the adapter's opinion. A run can
    #: be `COMPLETED_WITH_WARNINGS` because verification found the outcome unproven.
    verification_status: str | None = None
    resource_usage: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Any) -> "ExecutionRunView":
        return cls(
            id=row.id, execution_request_id=row.execution_request_id,
            worker_id=row.worker_id, status=row.status, attempt=int(row.attempt),
            executed_action=row.executed_action, exit_code=row.exit_code,
            result_summary=row.result_summary, error_category=row.error_category,
            verification_status=row.verification_status,
            resource_usage=dict(row.resource_usage or {}),
            started_at=row.started_at, completed_at=row.completed_at)


class ToolView(BaseModel):
    """What tool discovery may expose (§7).

    Deliberately narrower than the row: discovery returns descriptions, supported
    actions, input requirements, output contracts, required capabilities and risk
    classifications. It never returns configuration references or anything that could
    carry a secret, because §7 forbids exposing internal credentials or sensitive
    configuration through discovery.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    category: str
    adapter_type: str
    version: str
    supported_actions: list[str]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    capability_requirements: list[str]
    risk_level: int
    risk_name: str
    required_approval_level: int
    supported_platforms: list[str]
    timeout_default_seconds: int
    retry_eligible: bool
    idempotent: bool
    status: str
    health_status: str
    health_detail: str | None = None
    #: §30 rule 22: isolation strength must say what was *verified*, not what was
    #: hoped for. Absent for tools that run no untrusted code.
    isolation_strength: str | None = None
    disabled_reason: str | None = None

    @classmethod
    def from_row(cls, row: Any) -> "ToolView":
        return cls(
            id=row.id, name=row.name, description=row.description,
            category=row.category, adapter_type=row.adapter_type, version=row.version,
            supported_actions=list(row.supported_actions or []),
            input_schema=dict(row.input_schema or {}),
            output_schema=dict(row.output_schema or {}),
            capability_requirements=list(row.capability_requirements or []),
            risk_level=int(row.risk_level),
            risk_name=RISK_TO_LEVEL.get(int(row.risk_level), "UNKNOWN"),
            required_approval_level=int(row.required_approval_level),
            supported_platforms=list(row.supported_platforms or []),
            timeout_default_seconds=int(row.timeout_default_seconds),
            retry_eligible=bool(row.retry_eligible), idempotent=bool(row.idempotent),
            status=row.status, health_status=row.health_status,
            health_detail=row.health_detail, isolation_strength=row.isolation_strength,
            disabled_reason=row.disabled_reason)


# --------------------------------------------------------------------------- #
# §15.3 Workflow states, §19 session rows
# --------------------------------------------------------------------------- #
#: §15.3's persistent workflow states, verbatim. QUEUED doubles as the state a
#: definition's run waits in before the scheduler (a later stage) picks it up.
WORKFLOW_RUN_STATES = (
    "DRAFT", "VALIDATING", "APPROVED", "QUEUED", "RUNNING", "PAUSED",
    "AWAITING_APPROVAL", "AWAITING_HUMAN", "COMPLETED", "FAILED", "CANCELLED",
    "RECOVERY_REQUIRED",
)

#: Definitions are not runs: a definition is drafted, validated and approved, and
#: may later be disabled. It is never RUNNING, so it gets its own small vocabulary
#: rather than borrowing the run states and implying it executes.
WORKFLOW_DEFINITION_STATUSES = ("draft", "validating", "approved", "disabled")

#: Step-level progress inside a run. Lowercase because a step run is an internal
#: engine record in the style of `task_executions.status`, not one of §6.1's
#: agent-facing outcomes; the run it belongs to carries the outcome vocabulary.
WORKFLOW_STEP_STATES = (
    "pending", "queued", "running", "completed", "failed", "cancelled", "skipped",
)

#: §11.2 requires each browser session to carry a state but does not enumerate the
#: values. These five are the smallest set that covers §11.5's pause-for-human
#: (`paused`) and §11.2's expiration policy (`expired`) without inventing states
#: nothing in this phase can produce.
BROWSER_SESSION_STATES = ("created", "active", "paused", "closed", "expired")

#: The approval service grades risk as low/medium/high/critical
#: (`ApprovalCreateRequest.risk`), which is not `RiskLevel`'s vocabulary
#: (LOW/MODERATE/HIGH/CRITICAL). The two are kept apart deliberately: an execution
#: request records the §8 class, and only the approval it opens is translated.
APPROVAL_RISK_BY_CLASS = {0: "low", 1: "medium", 2: "high", 3: "critical"}


class ToolRegistrationInput(BaseModel):
    """What registering a tool declares (§7).

    `status` and `health_status` are absent for the same reason `risk_level` is
    absent from an execution request: a registrant does not get to declare its own
    tool available and healthy. Registration produces REGISTERED; only validation
    in :mod:`app.execution.registry` can move a tool to AVAILABLE.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    category: str = Field(default="general", max_length=64)
    adapter_type: str = Field(max_length=32)
    version: str = Field(default="1.0.0", max_length=32)
    supported_actions: list[str] = Field(default_factory=list, max_length=64)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    capability_requirements: list[str] = Field(default_factory=list, max_length=32)
    risk_level: int = Field(default=1, ge=0, le=3)
    required_approval_level: int = Field(default=0, ge=0, le=3)
    supported_platforms: list[str] = Field(default_factory=list, max_length=16)
    resource_requirements: dict[str, Any] = Field(default_factory=dict)
    timeout_default_seconds: int = Field(default=60, ge=1, le=3600)
    retry_eligible: bool = False
    idempotent: bool = False
    #: Where the tool's configuration lives. A reference, never the configuration
    #: itself, and never returned by tool discovery (§7).
    configuration_reference: str | None = Field(default=None, max_length=256)
    #: §30 rule 22: what isolation was *verified*, in words. Required by validation
    #: for code tools; a claim here is a claim the validator repeats, so it should
    #: be written as if an auditor will read it, because one will.
    isolation_strength: str | None = Field(default=None, max_length=128)
