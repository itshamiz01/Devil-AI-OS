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


class AgentPermissionView(BaseModel):
    id: str
    agent_id: str
    capability_id: str
    scope: str
    approval_level: int
    approval_id: str | None
    status: str
    granted_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


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
