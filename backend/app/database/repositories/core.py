"""Repository layer (P-01 §6.3): all SQL lives here / in services built on
these repositories; API routes never build queries directly."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models.core import (
    Agent, AppSession, Approval, AuditEvent, Permission, SystemConfig, SystemEvent, Task, TaskExecution,
)
from ..models.base import utcnow


class TaskRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, task: Task) -> Task:
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def get(self, task_id: str) -> Task | None:
        # Eager-load executions so callers may inspect attempt history after
        # the session closes (detached-instance safety).
        return self.session.scalar(
            select(Task).options(selectinload(Task.executions)).where(Task.id == task_id))

    def get_by_idempotency_key(self, key: str) -> Task | None:
        return self.session.scalar(select(Task).where(Task.idempotency_key == key))

    def list(self, status: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[Task], int]:
        stmt = select(Task)
        count_stmt = select(func.count()).select_from(Task)
        if status:
            stmt = stmt.where(Task.status == status)
            count_stmt = count_stmt.where(Task.status == status)
        total = self.session.scalar(count_stmt) or 0
        rows = self.session.scalars(
            stmt.order_by(Task.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(rows), total

    def due_tasks(self, now: dt.datetime, limit: int = 50) -> list[Task]:
        stmt = (
            select(Task)
            .where(
                Task.status.in_(["queued", "retry_pending"]),
                (Task.next_attempt_at.is_(None)) | (Task.next_attempt_at <= now),
            )
            .order_by(Task.priority.desc(), Task.created_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def by_status(self, statuses: list[str]) -> list[Task]:
        return list(self.session.scalars(select(Task).where(Task.status.in_(statuses))).all())

    def count_by_status(self, status: str) -> int:
        return self.session.scalar(
            select(func.count()).select_from(Task).where(Task.status == status)
        ) or 0

    def save(self, task: Task) -> Task:
        task.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(task)
        return task

    def add_execution(self, execution: TaskExecution) -> TaskExecution:
        self.session.add(execution)
        self.session.commit()
        self.session.refresh(execution)
        return execution

    def save_execution(self, execution: TaskExecution) -> TaskExecution:
        self.session.commit()
        self.session.refresh(execution)
        return execution


class AgentRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, agent: Agent) -> Agent:
        self.session.add(agent)
        self.session.commit()
        self.session.refresh(agent)
        return agent

    def get(self, agent_id: str) -> Agent | None:
        return self.session.get(Agent, agent_id)

    def list(self, limit: int = 50, offset: int = 0) -> tuple[list[Agent], int]:
        total = self.session.scalar(select(func.count()).select_from(Agent)) or 0
        rows = self.session.scalars(
            select(Agent).order_by(Agent.created_at.asc()).limit(limit).offset(offset)
        ).all()
        return list(rows), total


class ApprovalRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, approval: Approval) -> Approval:
        self.session.add(approval)
        self.session.commit()
        self.session.refresh(approval)
        return approval

    def get(self, approval_id: str) -> Approval | None:
        return self.session.get(Approval, approval_id)

    def list(self, status: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[Approval], int]:
        stmt = select(Approval)
        count_stmt = select(func.count()).select_from(Approval)
        if status:
            stmt = stmt.where(Approval.status == status)
            count_stmt = count_stmt.where(Approval.status == status)
        total = self.session.scalar(count_stmt) or 0
        rows = self.session.scalars(
            stmt.order_by(Approval.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(rows), total

    def save(self, approval: Approval) -> Approval:
        approval.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(approval)
        return approval


class PermissionRepository:
    def __init__(self, session: Session):
        self.session = session

    def rules_for(self, principal_type: str, principal_id: str) -> list[Permission]:
        stmt = select(Permission).where(
            Permission.principal_type == principal_type,
            (Permission.principal_id == principal_id) | (Permission.principal_id.is_(None)),
        )
        return list(self.session.scalars(stmt).all())

    def add(self, rule: Permission) -> Permission:
        self.session.add(rule)
        self.session.commit()
        self.session.refresh(rule)
        return rule


class AuditRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, event: AuditEvent) -> AuditEvent:
        if event.created_at is None:
            event.created_at = utcnow()
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event


class SystemEventRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, event: SystemEvent) -> SystemEvent:
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def list(self, event_type: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[SystemEvent], int]:
        stmt = select(SystemEvent)
        count_stmt = select(func.count()).select_from(SystemEvent)
        if event_type:
            stmt = stmt.where(SystemEvent.event_type == event_type)
            count_stmt = count_stmt.where(SystemEvent.event_type == event_type)
        total = self.session.scalar(count_stmt) or 0
        rows = self.session.scalars(
            stmt.order_by(SystemEvent.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(rows), total


class ConfigRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, key: str) -> SystemConfig | None:
        return self.session.scalar(select(SystemConfig).where(SystemConfig.key == key))

    def set(self, key: str, value: str | None, description: str | None = None) -> SystemConfig:
        row = self.get(key)
        if row is None:
            row = SystemConfig(key=key, value=value, description=description)
            self.session.add(row)
        else:
            row.value = value
            if description:
                row.description = description
            row.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(row)
        return row


class SessionRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, session_row: AppSession) -> AppSession:
        self.session.add(session_row)
        self.session.commit()
        self.session.refresh(session_row)
        return session_row

    def get_by_token_hash(self, token_hash: str) -> AppSession | None:
        return self.session.scalar(select(AppSession).where(AppSession.token_hash == token_hash))

    def save(self, session_row: AppSession) -> AppSession:
        self.session.commit()
        self.session.refresh(session_row)
        return session_row
