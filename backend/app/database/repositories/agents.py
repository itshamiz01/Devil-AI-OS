"""Repositories for the P-04 agent-factory tables (SQL lives here and in
the services built on these repositories, per the P-01 §6.3 convention)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.agents import (
    AgentAssignment, AgentCapability, AgentConfigurationHistory,
    AgentCreationRequest, AgentHealth, AgentMetric, AgentPermission,
    AgentTemplate, AgentTemplateVersion,
)
from ..models.base import utcnow
from ..models.core import Agent


class _BaseRepo:
    def __init__(self, session: Session):
        self.session = session

    def add(self, row):
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def save(self, row):
        if hasattr(row, "updated_at"):
            row.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(row)
        return row


class AgentQueryRepository(_BaseRepo):
    """Read helpers over the P-01 ``agents`` registry (extended by P-04)."""

    def get(self, agent_id: str) -> Agent | None:
        return self.session.get(Agent, agent_id)

    def count_all(self) -> int:
        return self.session.scalar(select(func.count()).select_from(Agent)) or 0

    def count_by_status(self, statuses: list[str]) -> int:
        return self.session.scalar(
            select(func.count()).select_from(Agent).where(Agent.status.in_(statuses))) or 0

    def count_by_business(self, business_ref: str, statuses: list[str] | None = None) -> int:
        stmt = select(func.count()).select_from(Agent).where(Agent.business_ref == business_ref)
        if statuses:
            stmt = stmt.where(Agent.status.in_(statuses))
        return self.session.scalar(stmt) or 0

    def count_children(self, parent_agent_id: str) -> int:
        return self.session.scalar(
            select(func.count()).select_from(Agent)
            .where(Agent.parent_agent_id == parent_agent_id)) or 0

    def by_role(self, role: str, statuses: list[str] | None = None) -> list[Agent]:
        stmt = select(Agent).where(Agent.role == role)
        if statuses:
            stmt = stmt.where(Agent.status.in_(statuses))
        return list(self.session.scalars(stmt.order_by(Agent.created_at.asc())).all())

    def by_status(self, statuses: list[str]) -> list[Agent]:
        return list(self.session.scalars(
            select(Agent).where(Agent.status.in_(statuses)).order_by(Agent.created_at.asc())).all())

    def creations_since(self, since: dt.datetime) -> int:
        return self.session.scalar(
            select(func.count()).select_from(Agent).where(
                Agent.template_id.is_not(None), Agent.created_at >= since)) or 0


class TemplateRepository(_BaseRepo):
    def get(self, template_id: str) -> AgentTemplate | None:
        return self.session.get(AgentTemplate, template_id)

    def get_by_name(self, name: str) -> AgentTemplate | None:
        return self.session.scalar(select(AgentTemplate).where(AgentTemplate.name == name))

    def list(self, limit: int = 50, offset: int = 0) -> tuple[list[AgentTemplate], int]:
        total = self.session.scalar(select(func.count()).select_from(AgentTemplate)) or 0
        rows = self.session.scalars(
            select(AgentTemplate).order_by(AgentTemplate.created_at.asc())
            .limit(limit).offset(offset)).all()
        return list(rows), total

    def version(self, template_id: str, version: int) -> AgentTemplateVersion | None:
        return self.session.scalar(
            select(AgentTemplateVersion).where(
                AgentTemplateVersion.template_id == template_id,
                AgentTemplateVersion.version == version))

    def versions(self, template_id: str) -> list[AgentTemplateVersion]:
        return list(self.session.scalars(
            select(AgentTemplateVersion).where(
                AgentTemplateVersion.template_id == template_id)
            .order_by(AgentTemplateVersion.version.asc())).all())


class CapabilityRepository(_BaseRepo):
    def get(self, capability_id: str) -> AgentCapability | None:
        return self.session.get(AgentCapability, capability_id)

    def get_by_name(self, name: str) -> AgentCapability | None:
        return self.session.scalar(select(AgentCapability).where(AgentCapability.name == name))

    def list(self) -> list[AgentCapability]:
        return list(self.session.scalars(
            select(AgentCapability).order_by(AgentCapability.name.asc())).all())


class AgentPermissionRepository(_BaseRepo):
    def get(self, grant_id: str) -> AgentPermission | None:
        return self.session.get(AgentPermission, grant_id)

    def for_agent(self, agent_id: str, status: str | None = None) -> list[AgentPermission]:
        stmt = select(AgentPermission).where(AgentPermission.agent_id == agent_id)
        if status:
            stmt = stmt.where(AgentPermission.status == status)
        return list(self.session.scalars(stmt.order_by(AgentPermission.created_at.asc())).all())

    def active_grant(self, agent_id: str, capability_id: str) -> AgentPermission | None:
        return self.session.scalar(
            select(AgentPermission).where(
                AgentPermission.agent_id == agent_id,
                AgentPermission.capability_id == capability_id,
                AgentPermission.status == "granted"))


class CreationRequestRepository(_BaseRepo):
    def get(self, request_id: str) -> AgentCreationRequest | None:
        return self.session.get(AgentCreationRequest, request_id)

    def get_by_idempotency_key(self, key: str) -> AgentCreationRequest | None:
        return self.session.scalar(
            select(AgentCreationRequest).where(AgentCreationRequest.idempotency_key == key))

    def list(self, decision: str | None = None, limit: int = 50,
             offset: int = 0) -> tuple[list[AgentCreationRequest], int]:
        stmt = select(AgentCreationRequest)
        count_stmt = select(func.count()).select_from(AgentCreationRequest)
        if decision:
            stmt = stmt.where(AgentCreationRequest.decision == decision)
            count_stmt = count_stmt.where(AgentCreationRequest.decision == decision)
        total = self.session.scalar(count_stmt) or 0
        rows = self.session.scalars(
            stmt.order_by(AgentCreationRequest.created_at.desc())
            .limit(limit).offset(offset)).all()
        return list(rows), total

    def count_failed_initializations(self, role: str, template_id: str | None) -> int:
        """Failed-init attempts are creation requests that completed with a
        created agent which is now in FAILED state — counted via the audit
        trail is overkill; the service records them on the request rows
        whose created agent failed init (decision CREATE_AGENT and the
        agent's status FAILED). This helper counts matching requests."""
        stmt = (
            select(func.count()).select_from(AgentCreationRequest)
            .join(Agent, Agent.id == AgentCreationRequest.created_agent_id)
            .where(AgentCreationRequest.requested_role == role,
                   Agent.status == "failed"))
        if template_id:
            stmt = stmt.where(AgentCreationRequest.requested_template_id == template_id)
        return self.session.scalar(stmt) or 0


class AssignmentRepository(_BaseRepo):
    def get(self, assignment_id: str) -> AgentAssignment | None:
        return self.session.get(AgentAssignment, assignment_id)

    def get_by_idempotency_key(self, key: str) -> AgentAssignment | None:
        return self.session.scalar(
            select(AgentAssignment).where(AgentAssignment.idempotency_key == key))

    def for_agent(self, agent_id: str, limit: int = 50, offset: int = 0,
                  ) -> tuple[list[AgentAssignment], int]:
        stmt = select(AgentAssignment).where(AgentAssignment.agent_id == agent_id)
        total = self.session.scalar(
            select(func.count()).select_from(AgentAssignment)
            .where(AgentAssignment.agent_id == agent_id)) or 0
        rows = self.session.scalars(
            stmt.order_by(AgentAssignment.created_at.desc())
            .limit(limit).offset(offset)).all()
        return list(rows), total

    def active_for_agent(self, agent_id: str) -> list[AgentAssignment]:
        return list(self.session.scalars(
            select(AgentAssignment).where(
                AgentAssignment.agent_id == agent_id,
                AgentAssignment.status.in_(["assigned", "running"]))).all())

    def children_of(self, assignment_id: str) -> list[AgentAssignment]:
        return list(self.session.scalars(
            select(AgentAssignment).where(
                AgentAssignment.parent_assignment_id == assignment_id)).all())

    def by_task(self, task_id: str) -> AgentAssignment | None:
        return self.session.scalar(
            select(AgentAssignment).where(AgentAssignment.task_id == task_id))


class HealthRepository(_BaseRepo):
    def latest(self, agent_id: str) -> AgentHealth | None:
        return self.session.scalar(
            select(AgentHealth).where(AgentHealth.agent_id == agent_id)
            .order_by(AgentHealth.last_check.desc()).limit(1))


class MetricRepository(_BaseRepo):
    def for_agent(self, agent_id: str, limit: int = 200) -> list[AgentMetric]:
        return list(self.session.scalars(
            select(AgentMetric).where(AgentMetric.agent_id == agent_id)
            .order_by(AgentMetric.recorded_at.desc()).limit(limit)).all())


class ConfigHistoryRepository(_BaseRepo):
    def for_agent(self, agent_id: str) -> list[AgentConfigurationHistory]:
        return list(self.session.scalars(
            select(AgentConfigurationHistory).where(
                AgentConfigurationHistory.agent_id == agent_id)
            .order_by(AgentConfigurationHistory.configuration_version.asc())).all())

    def get_version(self, agent_id: str, version: int) -> AgentConfigurationHistory | None:
        return self.session.scalar(
            select(AgentConfigurationHistory).where(
                AgentConfigurationHistory.agent_id == agent_id,
                AgentConfigurationHistory.configuration_version == version))
