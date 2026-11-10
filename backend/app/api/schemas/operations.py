"""Request schemas for the P-12 Autonomous Operations API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowCreateIn(BaseModel):
    name: str | None = None
    business_id: str | None = None
    objective: str | None = None
    description: str | None = None
    origin: str | None = None
    template: str | None = None
    definition: dict | None = None
    priority: int = 5
    priority_class: int | None = None
    autonomy_level: int = 1
    execution_policy: dict = Field(default_factory=dict)
    budget_id: str | None = None
    deadline: str | None = None
    success_conditions: dict = Field(default_factory=dict)
    failure_conditions: dict = Field(default_factory=dict)
    verification_policy: dict = Field(default_factory=dict)
    idempotency_key: str | None = None
    correlation_id: str | None = None


class AutonomyPolicyIn(BaseModel):
    scope_type: str
    scope_ref: str = ""
    agent_ref: str | None = None
    level: int
    action_caps: dict = Field(default_factory=dict)
    reason: str | None = None


class SettingsUpdateIn(BaseModel):
    max_concurrent_workflows: int | None = None
    max_concurrent_tasks_global: int | None = None
    max_concurrent_tasks_per_business: int | None = None
    max_concurrent_tasks_per_agent: int | None = None
    max_queue_depth: int | None = None
    low_resource_mode: bool | None = None
    default_autonomy_level: int | None = None
    circuit_breaker_threshold: int | None = None
    circuit_breaker_cooldown_seconds: int | None = None
    default_max_retries: int | None = None
    tick_interval_seconds: float | None = None


class TriggerCreateIn(BaseModel):
    name: str | None = None
    trigger_type: str
    business_id: str | None = None
    workflow_template: dict
    schedule: dict = Field(default_factory=dict)
    event_type: str | None = None
    threshold: dict = Field(default_factory=dict)


class TriggerStatusIn(BaseModel):
    status: str


class EmergencyStopIn(BaseModel):
    scope: str
    ref: str | None = None
    reason: str = ""


class ReassignIn(BaseModel):
    agent_id: str


class DeadLetterResolveIn(BaseModel):
    resolution: str


class ReportGenerateIn(BaseModel):
    kind: str
    business_id: str | None = None
