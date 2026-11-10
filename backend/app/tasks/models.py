"""Task vocabulary: states, validated transitions, error classes (P-01 §7)."""
from __future__ import annotations

import enum

from pydantic import BaseModel, Field


class TaskStatus(str, enum.Enum):
    CREATED = "created"
    VALIDATING = "validating"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    RETRY_PENDING = "retry_pending"


# The state machine. Anything not listed here is an invalid transition and
# raises InvalidStateTransitionError (P-01 §7.1).
TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.VALIDATING, TaskStatus.CANCELLED},
    TaskStatus.VALIDATING: {TaskStatus.QUEUED, TaskStatus.WAITING_FOR_APPROVAL,
                            TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.QUEUED: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.PAUSED},
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED,
                         TaskStatus.PAUSED},  # PAUSED only via startup recovery (interrupted)
    TaskStatus.FAILED: {TaskStatus.RETRY_PENDING, TaskStatus.CANCELLED},
    TaskStatus.RETRY_PENDING: {TaskStatus.QUEUED, TaskStatus.CANCELLED, TaskStatus.PAUSED},
    TaskStatus.PAUSED: {TaskStatus.QUEUED, TaskStatus.CANCELLED},
    TaskStatus.WAITING_FOR_APPROVAL: {TaskStatus.QUEUED, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.CANCELLED: set(),
}


def validate_transition(current: TaskStatus, target: TaskStatus) -> bool:
    return target in TRANSITIONS.get(current, set())


class ErrorKind(str, enum.Enum):
    INVALID_INPUT = "invalid_input"
    PERMISSION_DENIED = "permission_denied"
    SECURITY = "security"
    TIMEOUT = "timeout"
    TRANSIENT = "transient"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"


# Errors that must never be auto-retried (P-01 §7.4).
NON_RETRYABLE_KINDS = {ErrorKind.INVALID_INPUT, ErrorKind.PERMISSION_DENIED, ErrorKind.SECURITY}


class TaskExecutionError(Exception):
    def __init__(self, message: str, kind: ErrorKind = ErrorKind.UNKNOWN):
        super().__init__(message)
        self.kind = kind


class TaskSubmitRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str | None = None
    category: str = "general"
    handler_name: str = Field(min_length=1, max_length=200)
    payload: dict = Field(default_factory=dict)
    priority: int = Field(default=5, ge=0, le=100)
    max_retries: int = Field(default=0, ge=0, le=10)
    timeout_seconds: float = Field(default=30.0, gt=0, le=3600)
    assigned_agent_id: str | None = None
    requires_approval: bool = False
    essential: bool = False
    idempotency_key: str | None = None
    deadline: str | None = None
