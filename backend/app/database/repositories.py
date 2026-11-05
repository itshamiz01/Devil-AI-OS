from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import (
    ASSIGNMENT_STATUSES,
    IN_FLIGHT_ASSIGNMENT_STATUSES,
)
from .models import (
    AgentAssignment,
    Agent, AgentCapability, AgentCreationRequest, AgentPermission, AgentTemplate,
    AgentTemplateVersion, Approval,
    AuditEvent, AuthSession, OwnerCredential, Permission, PermissionAssignment,
    Principal, SystemConfiguration, SystemEvent, Task, TaskExecution, utcnow,
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

    # ---- P-04 Stage 4: the registry becomes writable ------------------------
    async def create(self, *, principal_id: str, name: str, role: str, status: str,
                     metadata_json: dict | None = None, template_id: str | None = None,
                     template_version: int | None = None,
                     configuration_version: int = 1,
                     parent_agent_id: str | None = None,
                     business_id: str | None = None) -> Agent:
        agent = Agent(
            principal_id=principal_id, name=name, role=role, status=status,
            metadata_json=metadata_json or {}, template_id=template_id,
            template_version=template_version, configuration_version=configuration_version,
            parent_agent_id=parent_agent_id, business_id=business_id,
        )
        self.session.add(agent)
        await self.session.flush()
        return agent

    async def by_principal(self, principal_id: str) -> Agent | None:
        q = select(Agent).where(Agent.principal_id == principal_id)
        return (await self.session.execute(q)).scalars().first()

    async def by_template(self, template_id: str) -> Sequence[Agent]:
        q = select(Agent).where(Agent.template_id == template_id)
        return (await self.session.execute(q)).scalars().all()

    async def by_status(self, statuses: Sequence[str]) -> Sequence[Agent]:
        q = select(Agent).where(Agent.status.in_(list(statuses)))
        return (await self.session.execute(q)).scalars().all()

    async def count(self, statuses: Sequence[str] | None = None,
                    template_id: str | None = None) -> int:
        q = select(func.count()).select_from(Agent)
        if statuses is not None: q = q.where(Agent.status.in_(list(statuses)))
        if template_id is not None: q = q.where(Agent.template_id == template_id)
        return int((await self.session.execute(q)).scalar_one())

    async def set_status(self, agent_id: str, status: str,
                         retired_at: datetime | None = None) -> None:
        values: dict[str, Any] = {"status": status, "updated_at": utcnow()}
        if retired_at is not None: values["retired_at"] = retired_at
        await self.session.execute(update(Agent).where(Agent.id == agent_id).values(**values))
        await self.session.flush()


class AgentCreationRequestRepo:
    """The creation-request ledger (P-04 Stage 4).

    Every request is recorded with its decision and the reason for it, whether
    or not an agent resulted. A decision that exists only in an HTTP response
    cannot be audited after the fact.
    """

    def __init__(self, session: AsyncSession): self.session = session

    async def create(self, *, requested_role: str, justification: str,
                     requested_capabilities: list[str] | None = None,
                     resource_estimate: dict | None = None,
                     requested_template_id: str | None = None,
                     business_id: str | None = None,
                     idempotency_key: str | None = None) -> AgentCreationRequest:
        row = AgentCreationRequest(
            requested_role=requested_role, justification=justification,
            requested_capabilities=list(requested_capabilities or []),
            resource_estimate=dict(resource_estimate or {}),
            requested_template_id=requested_template_id, business_id=business_id,
            idempotency_key=idempotency_key, approval_status="not_required",
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, request_id: str) -> AgentCreationRequest | None:
        return await self.session.get(AgentCreationRequest, request_id)

    async def by_idempotency_key(self, key: str) -> AgentCreationRequest | None:
        q = select(AgentCreationRequest).where(AgentCreationRequest.idempotency_key == key)
        return (await self.session.execute(q)).scalars().first()

    def _filtered(self, decision: str | None, approval_status: str | None):
        q = select(AgentCreationRequest)
        if decision: q = q.where(AgentCreationRequest.decision == decision)
        if approval_status: q = q.where(AgentCreationRequest.approval_status == approval_status)
        return q

    async def list(self, limit: int, offset: int, decision: str | None = None,
                   approval_status: str | None = None) -> Sequence[AgentCreationRequest]:
        q = self._filtered(decision, approval_status).order_by(
            AgentCreationRequest.created_at.desc()).limit(limit).offset(offset)
        return (await self.session.execute(q)).scalars().all()

    async def count(self, decision: str | None = None,
                    approval_status: str | None = None) -> int:
        base = self._filtered(decision, approval_status).subquery()
        return int((await self.session.execute(select(func.count()).select_from(base))).scalar_one())

    async def queued(self, limit: int = 50) -> Sequence[AgentCreationRequest]:
        """Queued requests, oldest first: a queue is drained FIFO or not fairly."""
        q = select(AgentCreationRequest).where(
            AgentCreationRequest.decision == "QUEUE",
            AgentCreationRequest.completed_at.is_(None),
        ).order_by(AgentCreationRequest.created_at.asc()).limit(limit)
        return (await self.session.execute(q)).scalars().all()

    async def by_approval(self, approval_id: str) -> AgentCreationRequest | None:
        q = select(AgentCreationRequest).where(AgentCreationRequest.approval_id == approval_id)
        return (await self.session.execute(q)).scalars().first()

    async def set_decision(self, request_id: str, *, decision: str, reason: str,
                           approval_status: str | None = None,
                           approval_id: str | None = None,
                           completed: bool = False) -> None:
        values: dict[str, Any] = {"decision": decision, "decision_reason": reason,
                                  "updated_at": utcnow()}
        if approval_status is not None: values["approval_status"] = approval_status
        if approval_id is not None: values["approval_id"] = approval_id
        if completed: values["completed_at"] = utcnow()
        await self.session.execute(
            update(AgentCreationRequest).where(AgentCreationRequest.id == request_id)
            .values(**values))
        await self.session.flush()


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


class AgentCapabilityRepo:
    """The capability catalog (P-04 Stage 5).

    ``upsert_definition`` reconciles a code-defined entry into the table on every
    startup, so a catalog change ships with the code that needs it instead of
    depending on someone running a script.
    """

    def __init__(self, session: AsyncSession): self.session = session

    async def list(self, limit: int, offset: int, category: str | None = None,
                   risk_level: str | None = None, approval_level: int | None = None,
                   enabled: bool | None = None) -> Sequence[AgentCapability]:
        q = self._filtered(select(AgentCapability), category, risk_level,
                           approval_level, enabled).order_by(
            AgentCapability.approval_level.desc(), AgentCapability.capability_key.asc()
        ).limit(limit).offset(offset)
        return (await self.session.execute(q)).scalars().all()

    async def count(self, category: str | None = None, risk_level: str | None = None,
                    approval_level: int | None = None,
                    enabled: bool | None = None) -> int:
        base = self._filtered(select(AgentCapability), category, risk_level,
                              approval_level, enabled).subquery()
        return int((await self.session.execute(select(func.count()).select_from(base))).scalar_one())

    def _filtered(self, q, category, risk_level, approval_level, enabled):
        if category: q = q.where(AgentCapability.category == category)
        if risk_level: q = q.where(AgentCapability.risk_level == risk_level)
        if approval_level is not None: q = q.where(AgentCapability.approval_level == approval_level)
        if enabled is not None: q = q.where(AgentCapability.enabled == enabled)
        return q

    async def get(self, capability_id: str) -> AgentCapability | None:
        return await self.session.get(AgentCapability, capability_id)

    async def by_key(self, capability_key: str) -> AgentCapability | None:
        q = select(AgentCapability).where(AgentCapability.capability_key == capability_key)
        return (await self.session.execute(q)).scalars().first()

    async def by_keys(self, keys: Sequence[str]) -> Sequence[AgentCapability]:
        if not keys:
            return []
        q = select(AgentCapability).where(AgentCapability.capability_key.in_(list(keys)))
        return (await self.session.execute(q)).scalars().all()

    async def keys_by_ids(self, capability_ids: Sequence[str]) -> dict[str, str]:
        """Resolve ids to keys in one query.

        Callers list grants and need a key beside each one; looking each grant's
        capability up separately turns a page of grants into a page of queries.
        """
        ids = list(dict.fromkeys(capability_ids))
        if not ids:
            return {}
        q = select(AgentCapability.id, AgentCapability.capability_key).where(
            AgentCapability.id.in_(ids))
        return {cid: key for cid, key in (await self.session.execute(q)).all()}

    async def upsert_definition(self, *, capability_key: str, name: str, category: str,
                                risk_level: str, approval_level: int, access_class: str,
                                description: str = "", enabled: bool = True,
                                requires_scope: bool = False,
                                prohibited_reason: str = "") -> AgentCapability:
        row = await self.by_key(capability_key)
        if row is None:
            row = AgentCapability(capability_key=capability_key)
            self.session.add(row)
        row.name = name
        row.category = category
        row.risk_level = risk_level
        row.approval_level = int(approval_level)
        row.access_class = access_class
        row.description = description
        row.enabled = enabled
        row.requires_scope = requires_scope
        row.prohibited_reason = prohibited_reason
        row.updated_at = utcnow()
        await self.session.flush()
        return row


class AgentPermissionRepo:
    """Capability grants to agents (P-04 Stage 5). Nothing is implicit."""

    def __init__(self, session: AsyncSession): self.session = session

    async def create(self, *, agent_id: str, capability_id: str, scope: str = "",
                     approval_level: int, status: str = "active",
                     approval_id: str | None = None,
                     expires_at: datetime | None = None) -> AgentPermission:
        row = AgentPermission(
            agent_id=agent_id, capability_id=capability_id, scope=scope,
            approval_level=int(approval_level), status=status, approval_id=approval_id,
            expires_at=expires_at, granted_at=utcnow())
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, permission_id: str) -> AgentPermission | None:
        return await self.session.get(AgentPermission, permission_id)

    async def for_agent(self, agent_id: str, status: str | None = None,
                        limit: int = 200, offset: int = 0) -> Sequence[AgentPermission]:
        q = select(AgentPermission).where(AgentPermission.agent_id == agent_id)
        if status: q = q.where(AgentPermission.status == status)
        q = q.order_by(AgentPermission.granted_at.desc()).limit(limit).offset(offset)
        return (await self.session.execute(q)).scalars().all()

    async def count_for_agent(self, agent_id: str, status: str | None = None) -> int:
        q = select(func.count()).select_from(AgentPermission).where(
            AgentPermission.agent_id == agent_id)
        if status: q = q.where(AgentPermission.status == status)
        return int((await self.session.execute(q)).scalar_one())

    async def count_by_status(self) -> dict[str, int]:
        """Every grant in the system, grouped by status, in one query.

        Deliberately not ``for_agent("")``: an empty agent id matches no row, so
        counting per status through it reports zero for the whole system while
        looking as though it had asked the right question.
        """
        q = select(AgentPermission.status, func.count()).group_by(AgentPermission.status)
        return {status: int(number)
                for status, number in (await self.session.execute(q)).all()}

    async def find(self, agent_id: str, capability_id: str, scope: str,
                   statuses: Sequence[str] = ("pending", "active")) -> AgentPermission | None:
        """The existing grant for this agent, capability and scope, if any.

        Granting is idempotent on that triple: a second grant of the same thing
        returns the first rather than creating an ambiguity that revocation would
        then have to guess about.
        """
        q = select(AgentPermission).where(
            AgentPermission.agent_id == agent_id,
            AgentPermission.capability_id == capability_id,
            AgentPermission.scope == scope,
            AgentPermission.status.in_(list(statuses)),
        ).order_by(AgentPermission.granted_at.desc()).limit(1)
        return (await self.session.execute(q)).scalars().first()

    async def by_approval(self, approval_id: str) -> AgentPermission | None:
        q = select(AgentPermission).where(AgentPermission.approval_id == approval_id)
        return (await self.session.execute(q)).scalars().first()

    async def set_status(self, permission_id: str, status: str, *,
                         revoked_at: datetime | None = None,
                         approval_id: str | None = None) -> None:
        values: dict[str, Any] = {"status": status, "updated_at": utcnow()}
        if revoked_at is not None: values["revoked_at"] = revoked_at
        if approval_id is not None: values["approval_id"] = approval_id
        await self.session.execute(
            update(AgentPermission).where(AgentPermission.id == permission_id).values(**values))
        await self.session.flush()

    async def expirable(self, now: datetime, limit: int = 200) -> Sequence[AgentPermission]:
        """Active or pending grants whose expiry has passed."""
        q = select(AgentPermission).where(
            AgentPermission.status.in_(["active", "pending"]),
            AgentPermission.expires_at.is_not(None),
            AgentPermission.expires_at < now,
        ).limit(limit)
        return (await self.session.execute(q)).scalars().all()


class AgentAssignmentRepo:
    """The assignment ledger. `tasks.id` stays the live pointer on the task."""

    def __init__(self, session): self.session = session

    async def create(self, **kwargs: Any) -> AgentAssignment:
        row = AgentAssignment(**kwargs)
        self.session.add(row); await self.session.flush(); return row

    async def get(self, assignment_id: str) -> AgentAssignment | None:
        return await self.session.get(AgentAssignment, assignment_id)

    async def for_task(self, task_id: str) -> AgentAssignment | None:
        r = await self.session.execute(
            select(AgentAssignment).where(AgentAssignment.task_id == task_id))
        return r.scalars().first()

    async def list_for_agent(self, agent_id: str,
                             statuses: Sequence[str] | None = None) -> Sequence[AgentAssignment]:
        q = select(AgentAssignment).where(AgentAssignment.agent_id == agent_id)
        if statuses:
            q = q.where(AgentAssignment.status.in_(statuses))
        r = await self.session.execute(
            q.order_by(AgentAssignment.assigned_at.desc(), AgentAssignment.id))
        return list(r.scalars().all())

    async def count_in_flight(self, agent_id: str) -> int:
        r = await self.session.execute(
            select(func.count(AgentAssignment.id)).where(
                AgentAssignment.agent_id == agent_id,
                AgentAssignment.status.in_(IN_FLIGHT_ASSIGNMENT_STATUSES)))
        return int(r.scalar() or 0)

    async def list_all(self, *, status: str | None = None, agent_id: str | None = None,
                       limit: int = 100, offset: int = 0) -> Sequence[AgentAssignment]:
        q = select(AgentAssignment)
        if status:
            q = q.where(AgentAssignment.status == status)
        if agent_id:
            q = q.where(AgentAssignment.agent_id == agent_id)
        r = await self.session.execute(
            q.order_by(AgentAssignment.assigned_at.desc(), AgentAssignment.id)
             .limit(limit).offset(offset))
        return list(r.scalars().all())

    async def count(self, *, status: str | None = None, agent_id: str | None = None) -> int:
        q = select(func.count(AgentAssignment.id))
        if status:
            q = q.where(AgentAssignment.status == status)
        if agent_id:
            q = q.where(AgentAssignment.agent_id == agent_id)
        r = await self.session.execute(q)
        return int(r.scalar() or 0)

    async def count_by_status(self) -> dict[str, int]:
        """Every status is reported, including the ones holding nothing. Counting
        only what exists would report a zero-status ledger as an empty dict, which
        reads the same as a ledger that could not be consulted."""
        r = await self.session.execute(
            select(AgentAssignment.status, func.count(AgentAssignment.id))
            .group_by(AgentAssignment.status))
        counts = {str(s): int(n) for s, n in r.all()}
        return {s: counts.get(s, 0) for s in ASSIGNMENT_STATUSES}

    async def update(self, row: AgentAssignment, **changes: Any) -> AgentAssignment:
        for k, v in changes.items(): setattr(row, k, v)
        row.updated_at = utcnow()
        self.session.add(row); await self.session.flush(); return row
