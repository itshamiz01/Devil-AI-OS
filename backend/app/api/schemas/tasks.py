from __future__ import annotations

from pydantic import BaseModel

from ...tasks.models import TaskSubmitRequest  # re-exported request schema


class TaskOut(BaseModel):
    id: str
    name: str
    description: str | None
    category: str
    handler_name: str
    payload: dict
    priority: int
    status: str
    creator_type: str
    creator_id: str
    assigned_agent_id: str | None
    retry_count: int
    max_retries: int
    timeout_seconds: float
    progress: dict
    result: dict | None
    error: dict | None
    cancellation_requested: bool
    requires_approval: bool
    essential: bool
    approval_id: str | None
    idempotency_key: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None

    @classmethod
    def from_model(cls, task) -> "TaskOut":
        return cls(
            id=task.id, name=task.name, description=task.description, category=task.category,
            handler_name=task.handler_name, payload=task.payload, priority=task.priority,
            status=task.status, creator_type=task.creator_type, creator_id=task.creator_id,
            assigned_agent_id=task.assigned_agent_id, retry_count=task.retry_count,
            max_retries=task.max_retries, timeout_seconds=task.timeout_seconds,
            progress=task.progress, result=task.result, error=task.error,
            cancellation_requested=task.cancellation_requested,
            requires_approval=task.requires_approval, essential=task.essential,
            approval_id=task.approval_id, idempotency_key=task.idempotency_key,
            created_at=task.created_at.isoformat() if task.created_at else "",
            started_at=task.started_at.isoformat() if task.started_at else None,
            completed_at=task.completed_at.isoformat() if task.completed_at else None)


class TaskExecutionOut(BaseModel):
    id: str
    task_id: str
    attempt_number: int
    status: str
    result: dict | None
    error: dict | None
    duration_ms: float | None

    @classmethod
    def from_model(cls, ex) -> "TaskExecutionOut":
        return cls(id=ex.id, task_id=ex.task_id, attempt_number=ex.attempt_number,
                   status=ex.status, result=ex.result, error=ex.error, duration_ms=ex.duration_ms)
