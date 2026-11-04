"""Typed schemas for the agent factory (P-04 §6, §5).

These are the payloads that travel between the API, the factory and the
database. Validation happens here, at the boundary, so an invalid template can
never reach a repository - and therefore can never produce an active agent.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

SecurityClassification = Literal["internal", "confidential", "restricted"]
MeasurementType = Literal["measured", "estimated", "unavailable"]


class ResourceBudget(BaseModel):
    """Ceilings for one agent. All are limits, never allocations."""

    max_concurrent_tasks: int = Field(default=1, ge=1, le=16)
    max_task_seconds: int = Field(default=300, ge=1, le=86400)
    max_retries: int = Field(default=2, ge=0, le=10)
    max_inference_requests: int = Field(default=8, ge=1, le=256)
    max_child_agents: int = Field(default=0, ge=0, le=8)
    max_queue_occupancy: int = Field(default=4, ge=1, le=64)


class RetryPolicy(BaseModel):
    max_retries: int = Field(default=2, ge=0, le=10)
    base_delay_seconds: float = Field(default=0.1, ge=0.0, le=60.0)
    max_delay_seconds: float = Field(default=5.0, ge=0.0, le=300.0)


class TemplateConfiguration(BaseModel):
    """Everything a template says about the agents it produces."""

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


class AgentTemplateVersionView(BaseModel):
    id: str
    template_id: str
    version: int
    configuration: TemplateConfiguration
    validation_status: str
    created_by: str | None
    created_at: datetime


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
    decision: str | None
    decision_reason: str | None
    approval_status: str
    approval_id: str | None
    created_at: datetime
    completed_at: datetime | None


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
