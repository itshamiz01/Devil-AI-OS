"""P-04 Dynamic Agent Factory API schemas (§19)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class TemplateCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    description: str | None = None
    configuration: dict


class TemplateUpdateIn(BaseModel):
    configuration: dict | None = None
    description: str | None = None


class TemplateCloneIn(BaseModel):
    new_name: str = Field(min_length=1, max_length=200)


class TemplatePublishIn(BaseModel):
    version: int | None = None


class TemplateRestoreIn(BaseModel):
    version: int = Field(ge=1)


class CreationRequirementIn(BaseModel):
    role: str = Field(min_length=1, max_length=200)
    template_id: str | None = None
    template_name: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    business_ref: str | None = None
    justification: str | None = None
    parent_agent_id: str | None = None
    name: str | None = Field(default=None, max_length=200)
    essential: bool = False
    task: dict | None = None
    config_overrides: dict | None = None
    resource_estimate: dict = Field(default_factory=dict)
    idempotency_key: str | None = None


class CreationDecisionIn(BaseModel):
    approve: bool = True
    notes: str | None = None


class AgentConfigUpdateIn(BaseModel):
    changes: dict
    reason: str | None = None


class ConfigRollbackIn(BaseModel):
    version: int = Field(ge=1)


class CapabilityRequestIn(BaseModel):
    capability: str = Field(min_length=1, max_length=100)
    reason: str | None = None
    scope: str | None = None


class CapabilityRevokeIn(BaseModel):
    capability: str = Field(min_length=1, max_length=100)


class CapabilityApproveIn(BaseModel):
    approval_id: str
    approve: bool = True


class AssignmentIn(BaseModel):
    objective: str = Field(min_length=1, max_length=2000)
    handler_name: str = Field(min_length=1, max_length=200)
    task_payload: dict = Field(default_factory=dict)
    name: str | None = None
    category: str = "agent_assignment"
    required_capabilities: list[str] = Field(default_factory=list)
    input_refs: list = Field(default_factory=list)
    priority: int = Field(default=5, ge=0, le=100)
    timeout_seconds: float = Field(default=30.0, gt=0, le=3600)
    retry_limit: int = Field(default=0, ge=0, le=10)
    expected_output: dict = Field(default_factory=dict)
    quality_requirements: dict = Field(default_factory=dict)
    business_ref: str | None = None
    parent_assignment_id: str | None = None
    depends_on_assignment_id: str | None = None
    idempotency_key: str | None = None


class InferenceIn(BaseModel):
    task_class: str = Field(default="general", max_length=100)


class EmergencyStopIn(BaseModel):
    scope: str = Field(default="all", pattern="^(all|agent)$")
    agent_id: str | None = None
    reason: str | None = None


class SettingsUpdateIn(BaseModel):
    updates: dict
