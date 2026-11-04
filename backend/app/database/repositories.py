from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Agent, AgentTemplate, AgentTemplateVersion, Approval, AuditEvent, AuthSession,
    OwnerCredential, Permission, PermissionAssignment, Principal, SystemConfiguration,
    SystemEvent, Task, TaskExecution, utcnow,
)


class PrincipalRepo:
    def __init__(self, session: AsyncSession): self.session = session
    async def get(self, principal_id: str) -> Principal | None: return await self.session.get(Principal, principal_id)
    async def by_name(self, name: str) -> Principal | None:
        return (await self.session.execute(select(Principal).where(Principal.name == name))).scalar_one_or_none()
    async def by_kind(self, kind: str) -> Sequence[Principal]:
        return (await self.session.execute(select(Principal).where(Principal.kind == kind))).scalars().all()
    async def create(self, kind: str, name: str, active: bool = True) -> Principal:
        p = Principal(kind=kind, name=name, active=active); self.session.add(p); await self.session.flush(); return p


class CredentialRepo:
    def __init__(self, session: AsyncSession): self.session = session
    async def get(self, principal_id: str) -> OwnerCredential | None: return await self.session.get(OwnerCredential, principal_id)
    async def set_hash(self, principal_id: str, password_hash: str) -> None:
        cred = await self.get(principal_id)
        if cred: cred.password_hash = password_hash
        else: self.session.add(OwnerCredential(principal_id=principal_id, password_hash=password_hash))
        await self.session.flush()


class SessionRepo:
    def __init__(self, session: AsyncSession): self.session = session
    async def create(self, token_hash: str, principal_id: str, expires_at: datetime) -> AuthSession:
        s = AuthSession(id=token_hash, principal_id=principal_id, expires_at=expires_at); self.session.add(s); await self.session.flush(); return s
    async def valid(self, token_hash: str) -> AuthSession | None:
        s = await self.session.get(AuthSession, token_hash)
        if not s or s.revoked_at is not None: return None
        exp = s.expires_at
        if exp.tzinfo is None: exp = exp.replace(tzinfo=timezone.utc)
        if exp <= utcnow(): return None
        return s
    async def revoke(self, token_hash: str) -> None:
        s = await self.session.get(AuthSession, token_hash)
        if s: s.revoked_at = utcnow(); await self.session.flush()


class PermissionRepo:
    def __init__(self, session: AsyncSession): self.session = session
    async def upsert_definition(self, code: str, category: str, description: str) -> None:
        p = await self.session.get(Permission, code)
        if not p: self.session.add(Permission(code=code, category=category, description=description))
        await self.session.flush()
    async def assignments(self, principal_id: str) -> Sequence[PermissionAssignment]:
        return (await self.session.execute(select(PermissionAssignment).where(PermissionAssignment.principal_id == principal_id))).scalars().all()
    async def assign(self, principal_id: str, code: str, scope: str = "*", effect: str = "allow") -> None:
        existing = (await self.session.execute(select(PermissionAssignment).where(
            PermissionAssignment.principal_id == principal_id, PermissionAssignment.permission_code == code,
            PermissionAssignment.resource_scope == scope, PermissionAssignment.effect == effect))).scalar_one_or_none()
        if not existing:
            self.session.add(PermissionAssignment(principal_id=principal_id, permission_code=code, resource_scope=scope, effect=effect))
            await self.session.flush()


class ApprovalRepo:
    def __init__(self, session: AsyncSession): self.session = session
    async def create(self, **kwargs: Any) -> Approval:
        a = Approval(**kwargs); self.session.add(a); await self.session.flush(); return a
    async def get(self, approval_id: str) -> Approval | None: return await self.session.get(Approval, approval_id)
    async def by_resource(self, action: str, resource: str) -> Approval | None:
        """Most recent approval gating a given resource, newest first."""
        q = select(Approval).where(Approval.action == action, Approval.resource == resource).order_by(Approval.created_at.desc()).limit(1)
        return (await self.session.execute(q)).scalar_one_or_none()
    async def list(self, status: str | None, limit: int, offset: int) -> Sequence[Approval]:
        q = select(Approval).order_by(Approval.created_at.desc()).limit(limit).offset(offset)
        if status: q = q.where(Approval.status == status)
        return (await self.session.execute(q)).scalars().all()


class TaskRepo:
    def __init__(self, session: AsyncSession): self.session = session
    async def create(self, **kwargs: Any) -> Task:
        t = Task(**kwargs); self.session.add(t); await self.session.flush(); return t
    async def get(self, task_id: str) -> Task | None: return await self.session.get(Task, task_id)
    async def by_idempotency(self, key: str) -> Task | None:
        return (await self.session.execute(select(Task).where(Task.idempotency_key == key))).scalar_one_or_none()
    async def list(self, status: str | None, limit: int, offset: int) -> Sequence[Task]:
        q = select(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset)
        if status: q = q.where(Task.status == status)
        return (await self.session.execute(q)).scalars().all()
    async def count_active(self) -> int:
        q = select(func.count()).select_from(Task).where(Task.status.in_(["CREATED","VALIDATING","QUEUED","RUNNING","RETRY_PENDING","WAITING_FOR_APPROVAL"]))
        return int((await self.session.execute(q)).scalar_one())
    async def by_status(self, statuses: list[str]) -> Sequence[Task]:
        return (await self.session.execute(select(Task).where(Task.status.in_(statuses)).order_by(Task.priority, Task.created_at))).scalars().all()
    async def due_retries(self) -> Sequence[Task]:
        return (await self.session.execute(select(Task).where(Task.status == "RETRY_PENDING", Task.next_retry_at <= utcnow()).order_by(Task.priority, Task.created_at))).scalars().all()


class ExecutionRepo:
    def __init__(self, session: AsyncSession): self.session = session
    async def create(self, task_id: str, attempt_number: int, worker_id: str) -> TaskExecution:
        e = TaskExecution(task_id=task_id, attempt_number=attempt_number, worker_id=worker_id, status="RUNNING")
        self.session.add(e); await self.session.flush(); return e
    async def finish(self, execution_id: str, status: str, error: dict | None = None) -> None:
        e = await self.session.get(TaskExecution, execution_id)
        if e: e.status = status; e.finished_at = utcnow(); e.error_details = error; await self.session.flush()
    async def list_for_task(self, task_id: str) -> Sequence[TaskExecution]:
        return (await self.session.execute(select(TaskExecution).where(TaskExecution.task_id == task_id).order_by(TaskExecution.attempt_number))).scalars().all()


class AuditRepo:
    def __init__(self, session: AsyncSession): self.session = session
    async def record(self, event_type: str, outcome: str, principal_id: str | None = None, resource: str = "", action: str = "", correlation_id: str | None = None, payload: dict | None = None) -> AuditEvent:
        e = AuditEvent(event_type=event_type, outcome=outcome, principal_id=principal_id, resource=resource, action=action, correlation_id=correlation_id, payload=payload or {})
        self.session.add(e); await self.session.flush(); return e
    async def list(self, limit: int, offset: int) -> Sequence[AuditEvent]:
        return (await self.session.execute(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset))).scalars().all()


class EventRepo:
    def __init__(self, session: AsyncSession): self.session = session
    async def record(self, event_type: str, source: str, payload: dict, severity: str = "info", correlation_id: str | None = None, task_id: str | None = None) -> SystemEvent:
        e = SystemEvent(event_type=event_type, source=source, payload=payload, severity=severity, correlation_id=correlation_id, task_id=task_id)
        self.session.add(e); await self.session.flush(); return e
    async def list(self, limit: int, offset: int, event_type: str | None = None) -> Sequence[SystemEvent]:
        q = select(SystemEvent).order_by(SystemEvent.created_at.desc()).limit(limit).offset(offset)
        if event_type: q = q.where(SystemEvent.event_type == event_type)
        return (await self.session.execute(q)).scalars().all()


class AgentRepo:
    def __init__(self, session: AsyncSession): self.session = session
    async def list(self, limit: int, offset: int) -> Sequence[Agent]:
        return (await self.session.execute(select(Agent).order_by(Agent.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    async def get(self, agent_id: str) -> Agent | None: return await self.session.get(Agent, agent_id)


class ConfigRepo:
    def __init__(self, session: AsyncSession): self.session = session
    async def set(self, key: str, value: dict) -> None:
        row = await self.session.get(SystemConfiguration, key)
        if row: row.value = value
        else: self.session.add(SystemConfiguration(key=key, value=value))
        await self.session.flush()
    async def get(self, key: str) -> SystemConfiguration | None: return await self.session.get(SystemConfiguration, key)


class AgentTemplateRepo:
    """Agent templates and their immutable versions (P-04 Stage 3).

    A version row is never updated in place except for its validation verdict:
    the configuration document is written once and read back unchanged, so an
    agent created from version 3 can always be explained by version 3.
    """

    def __init__(self, session: AsyncSession): self.session = session

    async def create(self, *, name: str, category: str, description: str = "",
                     status: str = "draft", current_version: int = 0) -> AgentTemplate:
        row = AgentTemplate(name=name, category=category, description=description,
                            status=status, current_version=current_version)
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, template_id: str) -> AgentTemplate | None:
        return await self.session.get(AgentTemplate, template_id)

    async def by_name(self, name: str) -> AgentTemplate | None:
        q = select(AgentTemplate).where(AgentTemplate.name == name)
        return (await self.session.execute(q)).scalars().first()

    def _filtered(self, status: str | None, category: str | None):
        q = select(AgentTemplate)
        if status: q = q.where(AgentTemplate.status == status)
        if category: q = q.where(AgentTemplate.category == category)
        return q

    async def list(self, limit: int, offset: int, status: str | None = None,
                   category: str | None = None) -> Sequence[AgentTemplate]:
        q = self._filtered(status, category).order_by(
            AgentTemplate.created_at.desc()).limit(limit).offset(offset)
        return (await self.session.execute(q)).scalars().all()

    async def count(self, status: str | None = None, category: str | None = None) -> int:
        base = self._filtered(status, category).subquery()
        return int((await self.session.execute(select(func.count()).select_from(base))).scalar_one())

    async def add_version(self, *, template_id: str, version: int, configuration: dict,
                          created_by: str | None = None,
                          validation_status: str = "unvalidated",
                          validation_details: dict | None = None) -> AgentTemplateVersion:
        row = AgentTemplateVersion(
            template_id=template_id, version=version, configuration_json=configuration,
            validation_status=validation_status, validation_details_json=validation_details,
            created_by=created_by,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_version(self, template_id: str, version: int) -> AgentTemplateVersion | None:
        q = select(AgentTemplateVersion).where(
            AgentTemplateVersion.template_id == template_id,
            AgentTemplateVersion.version == version)
        return (await self.session.execute(q)).scalars().first()

    async def latest_version(self, template_id: str) -> int:
        q = select(func.max(AgentTemplateVersion.version)).where(
            AgentTemplateVersion.template_id == template_id)
        return int((await self.session.execute(q)).scalar_one() or 0)

    async def list_versions(self, template_id: str) -> Sequence[AgentTemplateVersion]:
        q = select(AgentTemplateVersion).where(
            AgentTemplateVersion.template_id == template_id).order_by(
            AgentTemplateVersion.version.desc())
        return (await self.session.execute(q)).scalars().all()

    async def set_validation(self, version_id: str, status: str, details: dict) -> None:
        await self.session.execute(
            update(AgentTemplateVersion).where(AgentTemplateVersion.id == version_id)
            .values(validation_status=status, validation_details_json=details,
                    updated_at=utcnow()))
        await self.session.flush()

    async def set_status(self, template_id: str, status: str,
                         current_version: int | None = None) -> None:
        values: dict[str, Any] = {"status": status, "updated_at": utcnow()}
        if current_version is not None: values["current_version"] = current_version
        await self.session.execute(
            update(AgentTemplate).where(AgentTemplate.id == template_id).values(**values))
        await self.session.flush()

    async def set_current_version(self, template_id: str, version: int) -> None:
        await self.session.execute(
            update(AgentTemplate).where(AgentTemplate.id == template_id)
            .values(current_version=version, updated_at=utcnow()))
        await self.session.flush()
