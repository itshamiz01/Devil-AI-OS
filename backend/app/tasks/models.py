from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, ConfigDict


class TaskState(str, Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    RETRY_PENDING = "RETRY_PENDING"


ALLOWED_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.CREATED: {TaskState.VALIDATING, TaskState.CANCELLED},
    TaskState.VALIDATING: {TaskState.QUEUED, TaskState.FAILED, TaskState.CANCELLED, TaskState.WAITING_FOR_APPROVAL},
    TaskState.QUEUED: {TaskState.RUNNING, TaskState.PAUSED, TaskState.CANCELLED},
    TaskState.RUNNING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED, TaskState.RETRY_PENDING},
    TaskState.RETRY_PENDING: {TaskState.QUEUED, TaskState.CANCELLED, TaskState.PAUSED, TaskState.FAILED},
    TaskState.PAUSED: {TaskState.QUEUED, TaskState.CANCELLED},
    TaskState.WAITING_FOR_APPROVAL: {TaskState.QUEUED, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.FAILED: {TaskState.QUEUED},
    TaskState.COMPLETED: set(),
    TaskState.CANCELLED: set(),
}


class TaskSubmitRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    handler: Literal["system.noop", "system.echo", "system.wait"]
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=5, ge=0, le=9)
    max_retries: int = Field(default=3, ge=0, le=10)
    timeout_seconds: float = Field(default=30.0, gt=0, le=3600)
    idempotency_key: str | None = Field(default=None, max_length=128)
    deadline: datetime | None = None
    approval_required: bool = False


class TaskView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    category: str
    handler: str
    priority: int
    status: str
    creator_id: str
    assigned_agent_id: str | None
    idempotency_key: str | None
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error_details: dict[str, Any] | None
    progress: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    deadline: datetime | None
    retry_count: int
    max_retries: int
    timeout_seconds: float
    cancellation_requested: bool
    approval_required: bool
    essential: bool
    next_retry_at: datetime | None


class TaskExecutionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    task_id: str
    attempt_number: int
    status: str
    worker_id: str
    started_at: datetime
    finished_at: datetime | None
    error_details: dict[str, Any] | None
