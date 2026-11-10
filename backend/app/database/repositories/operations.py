"""Repository layer for P-12 operations tables. All SQL for the
operations package lives here; API routes never build queries.

Append-only by convention: workflow events, versions, decisions,
recovery records and approval links expose no update/delete beyond
status mirroring performed by the service. Monetary data is never
stored (P-07 is the only financial authority).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.operations import (
    AutonomousWorkflow, OperationsApprovalLink, OperationsAssignment,
    OperationsAutonomyPolicy, OperationsDeadLetter, OperationsDecision,
    OperationsRecoveryRecord, OperationsReport, OperationsTrigger,
    WorkflowCheckpoint, WorkflowEvent, WorkflowExecution, WorkflowTask,
    WorkflowVersion,
)


class _Repo:
    model = None

    def __init__(self, session: Session):
        self.session = session

    def add(self, row):
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def save(self, row):
        self.session.commit()
        self.session.refresh(row)
        return row

    def get(self, row_id: str):
        return self.session.get(self.model, row_id)


class WorkflowRepository(_Repo):
    model = AutonomousWorkflow

    def get_by_idempotency_key(self, key: str):
        return self.session.scalar(
            select(AutonomousWorkflow).where(
                AutonomousWorkflow.idempotency_key == key))

    def list(self, *, business_id: str | None = None,
             status: str | None = None, origin: str | None = None,
             limit: int = 50, offset: int = 0) -> tuple[list, int]:
        stmt = select(AutonomousWorkflow)
        count = select(func.count()).select_from(AutonomousWorkflow)
        for column, value in ((AutonomousWorkflow.business_id, business_id),
                              (AutonomousWorkflow.status, status),
                              (AutonomousWorkflow.origin, origin)):
            if value is not None:
                stmt = stmt.where(column == value)
                count = count.where(column == value)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(AutonomousWorkflow.created_at.desc())
            .limit(limit).offset(offset)))
        return rows, total

    def count_by_status(self) -> dict[str, int]:
        rows = self.session.execute(
            select(AutonomousWorkflow.status, func.count())
            .group_by(AutonomousWorkflow.status)).all()
        return {status: n for status, n in rows}

    def running_for_business(self, business_id: str) -> int:
        return self.session.scalar(
            select(func.count()).select_from(AutonomousWorkflow).where(
                AutonomousWorkflow.business_id == business_id,
                AutonomousWorkflow.status.in_(("RUNNING", "VERIFYING")))) or 0


class WorkflowTaskRepository(_Repo):
    model = WorkflowTask

    def list_for_workflow(self, workflow_id: str) -> list:
        return list(self.session.scalars(
            select(WorkflowTask).where(
                WorkflowTask.workflow_id == workflow_id)
            .order_by(WorkflowTask.priority, WorkflowTask.step_key)))

    def get_by_step(self, workflow_id: str, step_key: str):
        return self.session.scalar(
            select(WorkflowTask).where(
                WorkflowTask.workflow_id == workflow_id,
                WorkflowTask.step_key == step_key))

    def count_running(self, *, agent_id: str | None = None,
                      business_workflow_ids: list[str] | None = None) -> int:
        stmt = select(func.count()).select_from(WorkflowTask).where(
            WorkflowTask.status.in_(("RUNNING", "VERIFYING")))
        if agent_id is not None:
            stmt = stmt.where(WorkflowTask.assigned_agent_id == agent_id)
        if business_workflow_ids is not None:
            stmt = stmt.where(
                WorkflowTask.workflow_id.in_(business_workflow_ids))
        return self.session.scalar(stmt) or 0

    def count_by_status(self, workflow_id: str | None = None) -> dict[str, int]:
        stmt = select(WorkflowTask.status, func.count()).group_by(
            WorkflowTask.status)
        if workflow_id is not None:
            stmt = stmt.where(WorkflowTask.workflow_id == workflow_id)
        rows = self.session.execute(stmt).all()
        return {status: n for status, n in rows}


class WorkflowVersionRepository(_Repo):
    model = WorkflowVersion

    def list_for_workflow(self, workflow_id: str) -> list:
        return list(self.session.scalars(
            select(WorkflowVersion).where(
                WorkflowVersion.workflow_id == workflow_id)
            .order_by(WorkflowVersion.version)))


class WorkflowExecutionRepository(_Repo):
    model = WorkflowExecution

    def list_for_workflow(self, workflow_id: str, limit: int = 20) -> list:
        return list(self.session.scalars(
            select(WorkflowExecution).where(
                WorkflowExecution.workflow_id == workflow_id)
            .order_by(WorkflowExecution.attempt_number.desc())
            .limit(limit)))

    def latest(self, workflow_id: str):
        return self.session.scalar(
            select(WorkflowExecution).where(
                WorkflowExecution.workflow_id == workflow_id)
            .order_by(WorkflowExecution.attempt_number.desc()))


class WorkflowCheckpointRepository(_Repo):
    model = WorkflowCheckpoint

    def get_for_workflow(self, workflow_id: str):
        return self.session.scalar(
            select(WorkflowCheckpoint).where(
                WorkflowCheckpoint.workflow_id == workflow_id))


class WorkflowEventRepository(_Repo):
    model = WorkflowEvent

    def list_for_workflow(self, workflow_id: str, limit: int = 100) -> list:
        return list(self.session.scalars(
            select(WorkflowEvent).where(
                WorkflowEvent.workflow_id == workflow_id)
            .order_by(WorkflowEvent.created_at.desc()).limit(limit)))


class TriggerRepository(_Repo):
    model = OperationsTrigger

    def list(self, *, status: str | None = None,
             limit: int = 100, offset: int = 0) -> tuple[list, int]:
        stmt = select(OperationsTrigger)
        count = select(func.count()).select_from(OperationsTrigger)
        if status is not None:
            stmt = stmt.where(OperationsTrigger.status == status)
            count = count.where(OperationsTrigger.status == status)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(OperationsTrigger.created_at.desc())
            .limit(limit).offset(offset)))
        return rows, total


class AssignmentRepository(_Repo):
    model = OperationsAssignment

    def list_for_workflow(self, workflow_id: str) -> list:
        return list(self.session.scalars(
            select(OperationsAssignment).where(
                OperationsAssignment.workflow_id == workflow_id)
            .order_by(OperationsAssignment.created_at.desc())))

    def active_for_task(self, task_id: str):
        return self.session.scalar(
            select(OperationsAssignment).where(
                OperationsAssignment.task_id == task_id,
                OperationsAssignment.status == "assigned")
            .order_by(OperationsAssignment.created_at.desc()))


class ApprovalLinkRepository(_Repo):
    model = OperationsApprovalLink

    def list_for_workflow(self, workflow_id: str) -> list:
        return list(self.session.scalars(
            select(OperationsApprovalLink).where(
                OperationsApprovalLink.workflow_id == workflow_id)
            .order_by(OperationsApprovalLink.created_at.desc())))

    def get_by_approval(self, approval_id: str):
        return self.session.scalar(
            select(OperationsApprovalLink).where(
                OperationsApprovalLink.approval_id == approval_id))

    def pending(self, limit: int = 100) -> list:
        return list(self.session.scalars(
            select(OperationsApprovalLink).where(
                OperationsApprovalLink.status == "pending").limit(limit)))


class RecoveryRecordRepository(_Repo):
    model = OperationsRecoveryRecord

    def list(self, *, workflow_id: str | None = None, limit: int = 100) -> list:
        stmt = select(OperationsRecoveryRecord)
        if workflow_id is not None:
            stmt = stmt.where(
                OperationsRecoveryRecord.workflow_id == workflow_id)
        return list(self.session.scalars(
            stmt.order_by(OperationsRecoveryRecord.created_at.desc())
            .limit(limit)))


class DeadLetterRepository(_Repo):
    model = OperationsDeadLetter

    def list(self, *, status: str | None = None, limit: int = 100) -> tuple[list, int]:
        stmt = select(OperationsDeadLetter)
        count = select(func.count()).select_from(OperationsDeadLetter)
        if status is not None:
            stmt = stmt.where(OperationsDeadLetter.status == status)
            count = count.where(OperationsDeadLetter.status == status)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(OperationsDeadLetter.created_at.desc())
            .limit(limit)))
        return rows, total

    def for_task(self, task_id: str):
        return self.session.scalar(
            select(OperationsDeadLetter).where(
                OperationsDeadLetter.task_id == task_id))


class AutonomyPolicyRepository(_Repo):
    model = OperationsAutonomyPolicy

    def all_rows(self) -> list:
        return list(self.session.scalars(
            select(OperationsAutonomyPolicy).order_by(
                OperationsAutonomyPolicy.scope_type,
                OperationsAutonomyPolicy.scope_ref)))

    def find(self, scope_type: str, scope_ref: str,
             agent_ref: str | None):
        return self.session.scalar(
            select(OperationsAutonomyPolicy).where(
                OperationsAutonomyPolicy.scope_type == scope_type,
                OperationsAutonomyPolicy.scope_ref == scope_ref,
                OperationsAutonomyPolicy.agent_ref.is_(agent_ref)
                if agent_ref is None else
                OperationsAutonomyPolicy.agent_ref == agent_ref))


class DecisionRepository(_Repo):
    model = OperationsDecision

    def list(self, *, workflow_id: str | None = None,
             business_id: str | None = None, limit: int = 100) -> list:
        stmt = select(OperationsDecision)
        if workflow_id is not None:
            stmt = stmt.where(OperationsDecision.workflow_id == workflow_id)
        if business_id is not None:
            stmt = stmt.where(OperationsDecision.business_id == business_id)
        return list(self.session.scalars(
            stmt.order_by(OperationsDecision.created_at.desc()).limit(limit)))

    def count_by_category(self) -> dict[str, int]:
        rows = self.session.execute(
            select(OperationsDecision.category, func.count())
            .group_by(OperationsDecision.category)).all()
        return {cat: n for cat, n in rows}


class ReportRepository(_Repo):
    model = OperationsReport

    def list(self, *, kind: str | None = None, limit: int = 50) -> tuple[list, int]:
        stmt = select(OperationsReport)
        count = select(func.count()).select_from(OperationsReport)
        if kind is not None:
            stmt = stmt.where(OperationsReport.kind == kind)
            count = count.where(OperationsReport.kind == kind)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(OperationsReport.created_at.desc()).limit(limit)))
        return rows, total
