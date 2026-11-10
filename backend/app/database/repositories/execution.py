"""Repositories for the P-05 execution tables (SQL lives here and in the
services built on these repositories, per the P-01 §6.3 convention)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.base import utcnow
from ..models.execution import (
    BrowserSession, ExecutionEvidence, ExecutionRequest, ExecutionRun,
    ExecutionTool, ExecutionWorkspace, StandingAuthorization,
    WorkflowDefinition, WorkflowRun, WorkflowStepRun,
)


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


class ExecutionToolRepository(_BaseRepo):
    def get(self, tool_id: str) -> ExecutionTool | None:
        return self.session.get(ExecutionTool, tool_id)

    def get_by_name(self, name: str) -> ExecutionTool | None:
        return self.session.scalar(
            select(ExecutionTool).where(ExecutionTool.name == name))

    def list(self, limit: int = 100, offset: int = 0):
        total = self.session.scalar(
            select(func.count()).select_from(ExecutionTool)) or 0
        rows = list(self.session.scalars(
            select(ExecutionTool).order_by(ExecutionTool.name)
            .limit(limit).offset(offset)).all())
        return rows, total


class ExecutionWorkspaceRepository(_BaseRepo):
    def get(self, workspace_id: str) -> ExecutionWorkspace | None:
        return self.session.get(ExecutionWorkspace, workspace_id)

    def get_by_name(self, name: str) -> ExecutionWorkspace | None:
        return self.session.scalar(
            select(ExecutionWorkspace).where(ExecutionWorkspace.name == name))

    def list(self, status: str | None = "active"):
        stmt = select(ExecutionWorkspace).order_by(ExecutionWorkspace.name)
        if status is not None:
            stmt = stmt.where(ExecutionWorkspace.status == status)
        return list(self.session.scalars(stmt).all())

    def for_agent(self, agent_id: str) -> list[ExecutionWorkspace]:
        return list(self.session.scalars(
            select(ExecutionWorkspace).where(
                ExecutionWorkspace.owner_type == "agent",
                ExecutionWorkspace.owner_id == agent_id,
                ExecutionWorkspace.status == "active")).all())


class ExecutionRequestRepository(_BaseRepo):
    def get(self, request_id: str) -> ExecutionRequest | None:
        return self.session.get(ExecutionRequest, request_id)

    def get_by_idempotency_key(self, key: str) -> ExecutionRequest | None:
        return self.session.scalar(
            select(ExecutionRequest).where(ExecutionRequest.idempotency_key == key))

    def list(self, *, agent_id: str | None = None, status: str | None = None,
             limit: int = 50, offset: int = 0):
        stmt = select(ExecutionRequest)
        count_stmt = select(func.count()).select_from(ExecutionRequest)
        if agent_id is not None:
            stmt = stmt.where(ExecutionRequest.agent_id == agent_id)
            count_stmt = count_stmt.where(ExecutionRequest.agent_id == agent_id)
        if status is not None:
            stmt = stmt.where(ExecutionRequest.status == status)
            count_stmt = count_stmt.where(ExecutionRequest.status == status)
        total = self.session.scalar(count_stmt) or 0
        rows = list(self.session.scalars(
            stmt.order_by(ExecutionRequest.created_at.desc())
            .limit(limit).offset(offset)).all())
        return rows, total

    def count_by_status(self, status: str) -> int:
        return self.session.scalar(
            select(func.count()).select_from(ExecutionRequest)
            .where(ExecutionRequest.status == status)) or 0

    def count_all(self) -> int:
        return self.session.scalar(
            select(func.count()).select_from(ExecutionRequest)) or 0

    def in_statuses(self, statuses: list[str]) -> list[ExecutionRequest]:
        return list(self.session.scalars(
            select(ExecutionRequest).where(ExecutionRequest.status.in_(statuses))).all())


class ExecutionRunRepository(_BaseRepo):
    def get(self, run_id: str) -> ExecutionRun | None:
        return self.session.get(ExecutionRun, run_id)

    def for_request(self, request_id: str) -> list[ExecutionRun]:
        return list(self.session.scalars(
            select(ExecutionRun).where(ExecutionRun.request_id == request_id)
            .order_by(ExecutionRun.attempt_number)).all())

    def count_for_request(self, request_id: str) -> int:
        return self.session.scalar(
            select(func.count()).select_from(ExecutionRun)
            .where(ExecutionRun.request_id == request_id)) or 0

    def in_statuses(self, statuses: list[str]) -> list[ExecutionRun]:
        return list(self.session.scalars(
            select(ExecutionRun).where(ExecutionRun.status.in_(statuses))).all())


class ExecutionEvidenceRepository(_BaseRepo):
    def for_run(self, run_id: str) -> list[ExecutionEvidence]:
        return list(self.session.scalars(
            select(ExecutionEvidence).where(ExecutionEvidence.run_id == run_id)
            .order_by(ExecutionEvidence.created_at)).all())

    def for_request(self, request_id: str) -> list[ExecutionEvidence]:
        return list(self.session.scalars(
            select(ExecutionEvidence).where(ExecutionEvidence.request_id == request_id)
            .order_by(ExecutionEvidence.created_at)).all())


class BrowserSessionRepository(_BaseRepo):
    def get(self, session_id: str) -> BrowserSession | None:
        return self.session.get(BrowserSession, session_id)

    def list(self, *, agent_id: str | None = None, status: str | None = None,
             limit: int = 50, offset: int = 0):
        stmt = select(BrowserSession)
        count_stmt = select(func.count()).select_from(BrowserSession)
        if agent_id is not None:
            stmt = stmt.where(BrowserSession.agent_id == agent_id)
            count_stmt = count_stmt.where(BrowserSession.agent_id == agent_id)
        if status is not None:
            stmt = stmt.where(BrowserSession.status == status)
            count_stmt = count_stmt.where(BrowserSession.status == status)
        total = self.session.scalar(count_stmt) or 0
        rows = list(self.session.scalars(
            stmt.order_by(BrowserSession.created_at.desc())
            .limit(limit).offset(offset)).all())
        return rows, total

    def count_active(self) -> int:
        return self.session.scalar(
            select(func.count()).select_from(BrowserSession)
            .where(BrowserSession.status == "active")) or 0

    def active_sessions(self) -> list[BrowserSession]:
        return list(self.session.scalars(
            select(BrowserSession).where(BrowserSession.status == "active")).all())


class WorkflowDefinitionRepository(_BaseRepo):
    def get(self, definition_id: str) -> WorkflowDefinition | None:
        return self.session.get(WorkflowDefinition, definition_id)

    def get_by_name_version(self, name: str, version: int) -> WorkflowDefinition | None:
        return self.session.scalar(
            select(WorkflowDefinition).where(
                WorkflowDefinition.name == name,
                WorkflowDefinition.version == version))

    def list(self, limit: int = 50, offset: int = 0):
        total = self.session.scalar(
            select(func.count()).select_from(WorkflowDefinition)) or 0
        rows = list(self.session.scalars(
            select(WorkflowDefinition).order_by(WorkflowDefinition.name, WorkflowDefinition.version)
            .limit(limit).offset(offset)).all())
        return rows, total


class WorkflowRunRepository(_BaseRepo):
    def get(self, run_id: str) -> WorkflowRun | None:
        return self.session.get(WorkflowRun, run_id)

    def list(self, *, status: str | None = None, limit: int = 50, offset: int = 0):
        stmt = select(WorkflowRun)
        count_stmt = select(func.count()).select_from(WorkflowRun)
        if status is not None:
            stmt = stmt.where(WorkflowRun.status == status)
            count_stmt = count_stmt.where(WorkflowRun.status == status)
        total = self.session.scalar(count_stmt) or 0
        rows = list(self.session.scalars(
            stmt.order_by(WorkflowRun.created_at.desc())
            .limit(limit).offset(offset)).all())
        return rows, total

    def in_statuses(self, statuses: list[str]) -> list[WorkflowRun]:
        return list(self.session.scalars(
            select(WorkflowRun).where(WorkflowRun.status.in_(statuses))).all())


class WorkflowStepRunRepository(_BaseRepo):
    def for_run(self, workflow_run_id: str) -> list[WorkflowStepRun]:
        return list(self.session.scalars(
            select(WorkflowStepRun)
            .where(WorkflowStepRun.workflow_run_id == workflow_run_id)
            .order_by(WorkflowStepRun.started_at)).all())

    def get_by_step(self, workflow_run_id: str, step_id: str) -> WorkflowStepRun | None:
        return self.session.scalar(
            select(WorkflowStepRun).where(
                WorkflowStepRun.workflow_run_id == workflow_run_id,
                WorkflowStepRun.step_id == step_id))


class StandingAuthorizationRepository(_BaseRepo):
    def get(self, auth_id: str) -> StandingAuthorization | None:
        return self.session.get(StandingAuthorization, auth_id)

    def list(self, *, status: str | None = None, limit: int = 50, offset: int = 0):
        stmt = select(StandingAuthorization)
        count_stmt = select(func.count()).select_from(StandingAuthorization)
        if status is not None:
            stmt = stmt.where(StandingAuthorization.status == status)
            count_stmt = count_stmt.where(StandingAuthorization.status == status)
        total = self.session.scalar(count_stmt) or 0
        rows = list(self.session.scalars(
            stmt.order_by(StandingAuthorization.created_at.desc())
            .limit(limit).offset(offset)).all())
        return rows, total

    def active(self) -> list[StandingAuthorization]:
        return list(self.session.scalars(
            select(StandingAuthorization)
            .where(StandingAuthorization.status == "active")).all())
