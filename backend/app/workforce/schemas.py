"""Schemas and closed vocabularies for the 111-employee virtual organization.

The vocabularies here are the single source of truth for what the database
accepts and what the code can produce: ``models.py`` builds its CHECK
constraints from these tuples, so a state the code emits and a state the
database permits cannot drift apart silently.

Two design notes carried from the P-04 precedent this layer follows:

* **Strict payloads.** Every model refuses unknown keys (``extra="forbid"``),
  so a misspelled field is a 422 rather than a silently dropped hint.
* **Completions are judged, not accepted.** A work order's ``COMPLETED``
  state is set only after the deliverable passes its contract, exactly as
  the P-04 assignment ledger judges completion against ``expected_output_schema``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "EmployeeStatus",
    "WORKFORCE_EMPLOYEE_STATUSES",
    "WorkOrderState",
    "WORKFORCE_WORK_ORDER_STATES",
    "HandoffState",
    "WORKFORCE_HANDOFF_STATES",
    "ObjectiveState",
    "WORKFORCE_OBJECTIVE_STATES",
    "WorkOrderView",
    "HandoffView",
    "MessageView",
    "ObjectiveView",
    "EmployeeProfileView",
    "DepartmentView",
    "PerformanceRecordView",
    "EmployeeStatusUpdate",
    "WorkOrderCreate",
    "HandoffCreate",
    "MessageCreate",
    "ObjectiveCreate",
]

_STRICT = ConfigDict(extra="forbid")


class EmployeeStatus:
    """The employee lifecycle vocabulary (§6).

    These are workforce-level states. The underlying agent registry keeps its
    own lifecycle (P-04); the two are reconciled by the workforce service, which
    is the only writer of agent status for baseline employees.
    """

    ACTIVE = "ACTIVE"
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    ON_LEAVE = "ON_LEAVE"
    SUSPENDED = "SUSPENDED"
    DISABLED = "DISABLED"


WORKFORCE_EMPLOYEE_STATUSES: tuple[str, ...] = (
    EmployeeStatus.ACTIVE,
    EmployeeStatus.AVAILABLE,
    EmployeeStatus.BUSY,
    EmployeeStatus.WAITING,
    EmployeeStatus.BLOCKED,
    EmployeeStatus.ON_LEAVE,
    EmployeeStatus.SUSPENDED,
    EmployeeStatus.DISABLED,
)


class WorkOrderState:
    """The employee workflow (§10): AVAILABLE → TASK_ASSIGNED → TASK_ACCEPTED →
    WORKING → REVIEW_PENDING → COMPLETED, with the side states."""

    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_ACCEPTED = "TASK_ACCEPTED"
    WORKING = "WORKING"
    REVIEW_PENDING = "REVIEW_PENDING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    FAILED = "FAILED"
    REASSIGNED = "REASSIGNED"
    CANCELLED = "CANCELLED"


WORKFORCE_WORK_ORDER_STATES: tuple[str, ...] = (
    WorkOrderState.TASK_ASSIGNED,
    WorkOrderState.TASK_ACCEPTED,
    WorkOrderState.WORKING,
    WorkOrderState.REVIEW_PENDING,
    WorkOrderState.COMPLETED,
    WorkOrderState.BLOCKED,
    WorkOrderState.WAITING_FOR_INPUT,
    WorkOrderState.WAITING_FOR_APPROVAL,
    WorkOrderState.FAILED,
    WorkOrderState.REASSIGNED,
    WorkOrderState.CANCELLED,
)


class HandoffState:
    """A cross-department handoff moves through these states (§7)."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


WORKFORCE_HANDOFF_STATES: tuple[str, ...] = (
    HandoffState.PENDING,
    HandoffState.ACCEPTED,
    HandoffState.IN_PROGRESS,
    HandoffState.COMPLETED,
    HandoffState.REJECTED,
)


class ObjectiveState:
    """An executive objective (§4, §8) moves through these states."""

    OPEN = "OPEN"
    DELEGATED = "DELEGATED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


WORKFORCE_OBJECTIVE_STATES: tuple[str, ...] = (
    ObjectiveState.OPEN,
    ObjectiveState.DELEGATED,
    ObjectiveState.IN_PROGRESS,
    ObjectiveState.COMPLETED,
    ObjectiveState.FAILED,
    ObjectiveState.CANCELLED,
)


# --------------------------------------------------------------------------- #
# Read models (rows from the database)
# --------------------------------------------------------------------------- #
class DepartmentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    manager_employee_id: str
    mission: str


class EmployeeProfileView(BaseModel):
    """The full employee profile (§6). Every field comes from a real row."""

    model_config = ConfigDict(from_attributes=True)

    employee_id: str
    display_name: str
    department_code: str
    department_name: str
    job_title: str
    role_description: str
    primary_responsibilities: list[str]
    secondary_responsibilities: list[str]
    manager_employee_id: str | None
    seniority: int
    skills: list[str]
    tool_access: list[str]
    memory_scope: str
    system_instructions: str
    communication_style: str
    autonomy_level: str
    permission_scope: str
    status: str
    is_baseline: bool
    is_expansion: bool
    current_assignments: list[str]
    created_at: datetime
    last_activity: datetime | None
    configuration_version: int


class WorkOrderView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    employee_id: str
    manager_employee_id: str
    objective_id: str | None
    task_id: str | None
    title: str
    instructions: str
    required_inputs: list[str]
    expected_deliverable: dict[str, Any]
    deadline: datetime | None
    priority: int
    dependencies: list[str]
    available_tools: list[str]
    permission_scope: str
    budget_constraints: dict[str, Any]
    verification_requirements: list[str]
    status: str
    result: dict[str, Any] | None
    evidence: list[str]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class HandoffView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    from_department: str
    to_department: str
    from_employee_id: str
    to_employee_id: str
    source_work_order_id: str | None
    objective: str
    deliverable: str
    context: dict[str, Any]
    references: list[str]
    required_action: str
    access_scope: str
    status: str
    completion_criteria: list[str]
    created_at: datetime
    updated_at: datetime


class MessageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    from_employee_id: str
    to_employee_id: str
    channel_type: str
    task_id: str | None
    handoff_id: str | None
    kind: str
    content: str
    created_at: datetime


class ObjectiveView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    objective: str
    source: str
    status: str
    departments: list[str]
    expected_outcome: str
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class PerformanceRecordView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    employee_id: str
    period: str
    task_completion_rate: float
    quality_score: float
    deadline_adherence: float
    rework_rate: float
    verified_success_rate: float
    resource_efficiency: float
    error_rate: float
    collaboration_quality: float
    policy_compliance: float
    composite_score: float
    weights: dict[str, float]
    source: str
    notes: str
    created_at: datetime


# --------------------------------------------------------------------------- #
# Write models (inbound API payloads)
# --------------------------------------------------------------------------- #
class EmployeeStatusUpdate(BaseModel):
    model_config = _STRICT

    status: Literal[
        "ACTIVE", "AVAILABLE", "BUSY", "WAITING", "BLOCKED",
        "ON_LEAVE", "SUSPENDED", "DISABLED",
    ]
    reason: str = Field(min_length=1, max_length=2000)


class WorkOrderCreate(BaseModel):
    model_config = _STRICT

    employee_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=20_000)
    required_inputs: list[str] = Field(default_factory=list)
    expected_deliverable: dict[str, Any] = Field(default_factory=dict)
    deadline: datetime | None = None
    priority: int = Field(default=5, ge=1, le=10)
    dependencies: list[str] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    permission_scope: str = Field(default="", max_length=512)
    budget_constraints: dict[str, Any] = Field(default_factory=dict)
    verification_requirements: list[str] = Field(default_factory=list)
    objective_id: str | None = None


class HandoffCreate(BaseModel):
    model_config = _STRICT

    to_employee_id: str = Field(min_length=1, max_length=64)
    objective: str = Field(min_length=1, max_length=2000)
    deliverable: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)
    references: list[str] = Field(default_factory=list)
    required_action: str = Field(min_length=1, max_length=2000)
    access_scope: str = Field(default="", max_length=512)
    completion_criteria: list[str] = Field(default_factory=list)
    source_work_order_id: str | None = None


class MessageCreate(BaseModel):
    model_config = _STRICT

    to_employee_id: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=20_000)
    kind: str = Field(default="message", max_length=64)
    task_id: str | None = None
    handoff_id: str | None = None


class ObjectiveCreate(BaseModel):
    model_config = _STRICT

    objective: str = Field(min_length=1, max_length=4000)
    departments: list[str] = Field(default_factory=list)
    expected_outcome: str = Field(default="", max_length=4000)
