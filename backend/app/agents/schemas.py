"""Typed schemas for the agent factory (P-04 §6, §5).

These are the payloads that travel between the API, the factory and the
database. Validation happens here, at the boundary, so an invalid template can
never reach a repository - and therefore can never produce an active agent.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SecurityClassification = Literal["internal", "confidential", "restricted"]
MeasurementType = Literal["measured", "estimated", "unavailable"]

class CreationDecision(str, Enum):
    """The six decisions the creation engine may return.

    Closed set, and the database CHECK agrees with it: a decision outside this
    enum is a bug, not a judgement call. ``ASSIGN_EXISTING`` is declared now but
    not produced until Stage 6 implements assignment, so a caller can rely on the
    vocabulary without the engine silently inventing an execution path.
    """

    CREATE_AGENT = "CREATE_AGENT"
    REUSE_EXISTING = "REUSE_EXISTING"
    ASSIGN_EXISTING = "ASSIGN_EXISTING"
    QUEUE = "QUEUE"
    REQUEST_OWNER_APPROVAL = "REQUEST_OWNER_APPROVAL"
    REJECT = "REJECT"


#: Derived from the enum, never retyped, so the CHECK constraint and the code
#: cannot drift apart.
CREATION_DECISIONS = tuple(d.value for d in CreationDecision)

#: Approval state of a creation request. ``not_required`` is the default, so an
#: ungated creation is distinguishable from one still waiting on its owner.
CREATION_APPROVAL_STATUSES = (
    "not_required",
    "pending",
    "granted",
    "rejected",
    "expired",
)


#: Every payload in this module refuses unknown keys rather than dropping them.
#: The P-03 API established the convention ("an unexpected body field is a 422,
#: not a silently ignored hint") and it matters more here: a misspelled
#: ``allowed_capabilitys`` that was quietly discarded would produce a template
#: granting nothing, and the operator would read the omission as a decision.
_STRICT = ConfigDict(extra="forbid")


class ResourceBudget(BaseModel):
    """Ceilings for one agent. All are limits, never allocations."""

    model_config = _STRICT

    max_concurrent_tasks: int = Field(default=1, ge=1, le=16)
    max_task_seconds: int = Field(default=300, ge=1, le=86400)
    max_retries: int = Field(default=2, ge=0, le=10)
    max_inference_requests: int = Field(default=8, ge=1, le=256)
    max_child_agents: int = Field(default=0, ge=0, le=8)
    max_queue_occupancy: int = Field(default=4, ge=1, le=64)


class RetryPolicy(BaseModel):
    model_config = _STRICT

    max_retries: int = Field(default=2, ge=0, le=10)
    base_delay_seconds: float = Field(default=0.1, ge=0.0, le=60.0)
    max_delay_seconds: float = Field(default=5.0, ge=0.0, le=300.0)


class TemplateConfiguration(BaseModel):
    """Everything a template says about the agents it produces."""

    model_config = _STRICT

    role_definition: str = Field(min_length=1, max_length=4000)
    mission: str = Field(min_length=1, max_length=4000)
    system_instruction: str = Field(default="", max_length=16000)
    expected_input_schema: dict[str, Any] = Field(default_factory=dict)
    expected_output_schema: dict[str, Any] = Field(default_factory=dict)
    allowed_capabilities: list[str] = Field(default_factory=list)
    restricted_capabilities: list[str] = Field(default_factory=list)
    tool_requirements: list[str] = Field(default_factory=list)
    model_requirements: dict[str, Any] = Field(default_factory=dict)
    memory_requirements: dict[str, Any] = Field(default_factory=dict)
    resource_budget: ResourceBudget = Field(default_factory=ResourceBudget)
    timeout_seconds: int = Field(default=300, ge=1, le=86400)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    quality_criteria: dict[str, Any] = Field(default_factory=dict)
    evaluation_rules: dict[str, Any] = Field(default_factory=dict)
    approval_requirements: list[str] = Field(default_factory=list)
    security_classification: SecurityClassification = "internal"

    @model_validator(mode="after")
    def _capabilities_must_not_contradict(self) -> "TemplateConfiguration":
        overlap = set(self.allowed_capabilities) & set(self.restricted_capabilities)
        if overlap:
            raise ValueError(
                "a capability cannot be both allowed and restricted: "
                + ", ".join(sorted(overlap))
            )
        return self


class AgentTemplateView(BaseModel):
    id: str
    name: str
    category: str
    description: str
    current_version: int
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Any) -> "AgentTemplateView":
        return cls.model_validate(row, from_attributes=True)


class AgentTemplateVersionView(BaseModel):
    """A stored version, exactly as persisted.

    ``configuration`` is the raw stored document, not a parsed
    :class:`TemplateConfiguration`: a version whose ``validation_status`` is
    ``invalid`` must still be readable, and parsing it on the way out would
    turn "this template is invalid" into a 500. ``validation_details`` carries
    the recorded verdict and its issues.
    """

    id: str
    template_id: str
    version: int
    configuration: dict[str, Any]
    validation_status: str
    validation_details: dict[str, Any] | None = None
    created_by: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: Any) -> "AgentTemplateVersionView":
        """Build the view from a stored row.

        Explicit rather than ``model_validate``: the columns are named
        ``configuration_json`` and ``validation_details_json`` while the payload
        calls them ``configuration`` and ``validation_details``, and a silent
        rename in a validator is the kind of thing that breaks without failing.
        """
        return cls(
            id=row.id,
            template_id=row.template_id,
            version=row.version,
            configuration=row.configuration_json or {},
            validation_status=row.validation_status,
            validation_details=row.validation_details_json,
            created_by=row.created_by,
            created_at=row.created_at,
        )


#: Capability risk, using the **same** vocabulary as `approvals.risk` rather than
#: a parallel one: two words for the same idea in one system is how a mapping
#: gets written wrong and nobody notices.
CAPABILITY_RISK_LEVELS = ("low", "medium", "high", "critical")

#: What a capability lets an agent do to data. `execute` is the class that will
#: bind to P-05 tool boundaries; nothing invokes it yet.
CAPABILITY_ACCESS_CLASSES = ("read", "write", "execute")

#: The life of a grant. A denial is deliberately **not** a status: `agent_permissions`
#: records grants, and a refusal is recorded in the audit log and on the event bus,
#: where an attempt that never became a grant belongs.
AGENT_PERMISSION_STATUSES = ("pending", "active", "revoked", "expired")


class ApprovalLevel(int, Enum):
    """How much authority a capability needs before an agent may hold it.

    These are the four levels the P-04 design fixes, and they are the only
    authority model in this phase:

    * ``AUTONOMOUS`` (0) — policy allows it; the grant is recorded and audited.
    * ``CONDITIONAL`` (1) — allowed only if conditions checked in code hold.
    * ``OWNER_APPROVAL`` (2) — an `approvals` row must reach `granted` first.
    * ``PROHIBITED`` (3) — refused unconditionally, with no approval path.
    """

    AUTONOMOUS = 0
    CONDITIONAL = 1
    OWNER_APPROVAL = 2
    PROHIBITED = 3


#: Derived from the enum so the database CHECK and the code cannot drift.
APPROVAL_LEVELS = tuple(int(level) for level in ApprovalLevel)


class CapabilityDefinition(BaseModel):
    """One entry of the built-in catalog, as code.

    The catalog is defined here rather than only in the database for one reason:
    a prohibition that lives in a row can be lifted by editing a row. The level-3
    list in `capabilities.py` is code, and no database change can widen it.
    """

    model_config = _STRICT

    capability_key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    risk_level: Literal["low", "medium", "high", "critical"]
    approval_level: ApprovalLevel
    access_class: Literal["read", "write", "execute"]
    description: str = Field(default="", max_length=2000)
    enabled: bool = True
    #: A conditional capability that must be granted with a non-empty scope.
    requires_scope: bool = False
    #: Set for level 3 only, and required for it: a prohibition without a stated
    #: reason is a rule nobody can argue with or review.
    prohibited_reason: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _prohibited_entries_must_state_why(self) -> "CapabilityDefinition":
        if self.approval_level is ApprovalLevel.PROHIBITED and not self.prohibited_reason:
            raise ValueError("a level-3 capability must state its prohibited_reason")
        if self.approval_level is not ApprovalLevel.PROHIBITED and self.prohibited_reason:
            raise ValueError("prohibited_reason is only meaningful on a level-3 capability")
        return self


class AgentCapabilityView(BaseModel):
    id: str
    capability_key: str
    name: str
    category: str
    risk_level: str
    approval_level: int
    access_class: str
    description: str
    enabled: bool
    requires_scope: bool = False
    prohibited_reason: str = ""

    @classmethod
    def from_row(cls, row: Any) -> "AgentCapabilityView":
        return cls(
            id=row.id, capability_key=row.capability_key, name=row.name,
            category=row.category, risk_level=row.risk_level,
            approval_level=int(row.approval_level), access_class=row.access_class,
            description=row.description, enabled=bool(row.enabled),
            requires_scope=bool(getattr(row, "requires_scope", False)),
            prohibited_reason=getattr(row, "prohibited_reason", "") or "")


class AgentPermissionView(BaseModel):
    id: str
    agent_id: str
    capability_id: str
    capability_key: str | None = None
    scope: str
    approval_level: int
    approval_id: str | None
    status: str
    granted_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None

    @classmethod
    def from_row(cls, row: Any, capability_key: str | None = None) -> "AgentPermissionView":
        return cls(
            id=row.id, agent_id=row.agent_id, capability_id=row.capability_id,
            capability_key=capability_key, scope=row.scope,
            approval_level=int(row.approval_level), approval_id=row.approval_id,
            status=row.status, granted_at=row.granted_at, expires_at=row.expires_at,
            revoked_at=row.revoked_at)


class AgentCreationRequestView(BaseModel):
    id: str
    requested_role: str
    requested_template_id: str | None
    business_id: str | None
    justification: str
    requested_capabilities: list[str]
    resource_estimate: dict[str, Any]
    idempotency_key: str | None = None
    decision: str | None
    decision_reason: str | None
    approval_status: str
    approval_id: str | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_row(cls, row: Any) -> "AgentCreationRequestView":
        return cls(
            id=row.id, requested_role=row.requested_role,
            requested_template_id=row.requested_template_id,
            business_id=row.business_id, justification=row.justification,
            requested_capabilities=list(row.requested_capabilities or []),
            resource_estimate=dict(row.resource_estimate or {}),
            idempotency_key=row.idempotency_key, decision=row.decision,
            decision_reason=row.decision_reason,
            approval_status=row.approval_status, approval_id=row.approval_id,
            created_at=row.created_at, completed_at=row.completed_at)


class AgentRecordView(BaseModel):
    """The registry row as the API returns it, lifecycle included."""

    id: str
    name: str
    role: str
    status: str
    template_id: str | None
    template_version: int | None
    configuration_version: int
    parent_agent_id: str | None
    business_id: str | None
    retired_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CreationRequestInput(BaseModel):
    """What a caller asks the factory for.

    ``essential`` is the only field that can widen what the engine will do under
    resource pressure, and it is recorded with the decision, so a claim of
    essentiality is visible afterwards rather than being a way to skip a queue
    quietly.
    """

    model_config = _STRICT

    requested_role: str = Field(min_length=1, max_length=128)
    justification: str = Field(min_length=1, max_length=4000)
    requested_capabilities: list[str] = Field(default_factory=list, max_length=64)
    template_id: str | None = None
    business_id: str | None = None
    parent_agent_id: str | None = None
    agent_name: str | None = Field(default=None, min_length=1, max_length=128)
    essential: bool = False
    allow_reuse: bool = True
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=64)
    resource_estimate: dict[str, Any] = Field(default_factory=dict)


class CreationCheckView(BaseModel):
    """One deterministic check, with the detail that made it pass or fail."""

    name: str
    passed: bool
    detail: str = ""


class CreationEvaluationView(BaseModel):
    """A decision and everything needed to audit it.

    ``checks`` is returned in evaluation order and evaluation stops at the first
    check that forces a decision, so a short list means an early decision, not a
    missing one. ``recorded`` distinguishes a dry-run evaluation (nothing
    written) from a creation request that was persisted.
    """

    decision: CreationDecision
    reason: str
    checks: list[CreationCheckView]
    template_id: str | None = None
    template_version: int | None = None
    reuse_agent_id: str | None = None
    agent_id: str | None = None
    request_id: str | None = None
    approval_id: str | None = None
    approval_required: bool = False
    replayed: bool = False
    recorded: bool = False
    limits: dict[str, Any] = Field(default_factory=dict)
