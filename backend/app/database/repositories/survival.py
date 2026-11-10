"""Repository layer for P-08 survival tables. All SQL for the
survival package lives here or in the survival services built on
these repositories; API routes never build queries directly.
History tables (snapshots, dimensions, evaluations, overlays,
outcomes, forecasts) are append-only by convention: repositories
expose no delete."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.survival import (
    BusinessDecision, BusinessDecisionAlternative, BusinessExperiment,
    BusinessHealthDimension, BusinessHealthSnapshot,
    BusinessLifecycleOverlay, BusinessMonitoringEvent,
    BusinessObservation, BusinessPauseControl, CapitalAllocationProposal,
    ClosureReview, DecisionOutcome, ExperimentEvaluation, RecoveryPlan,
    ResourceAllocationProposal, ScalingAssessment, ScalingPlan,
    SurvivalForecast,
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

    def list(self, *, limit: int = 50, offset: int = 0,
             business_id: str | None = None,
             filters: dict | None = None) -> tuple[list, int]:
        stmt = select(self.model)
        count_stmt = select(func.count()).select_from(self.model)
        conditions = []
        if business_id is not None and hasattr(self.model, "business_id"):
            conditions.append(self.model.business_id == business_id)
        for key, value in (filters or {}).items():
            if value is not None and hasattr(self.model, key):
                conditions.append(getattr(self.model, key) == value)
        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        total = self.session.scalar(count_stmt) or 0
        rows = self.session.scalars(
            stmt.order_by(self.model.created_at.desc())
            .limit(limit).offset(offset)).all()
        return list(rows), total


class HealthSnapshotRepository(_Repo):
    model = BusinessHealthSnapshot

    def latest_for(self, business_id: str):
        return self.session.scalars(
            select(BusinessHealthSnapshot)
            .where(BusinessHealthSnapshot.business_id == business_id)
            .order_by(BusinessHealthSnapshot.created_at.desc())
            .limit(1)).first()

    def count_for(self, business_id: str) -> int:
        return self.session.scalar(
            select(func.count()).select_from(BusinessHealthSnapshot)
            .where(BusinessHealthSnapshot.business_id == business_id)) or 0


class HealthDimensionRepository(_Repo):
    model = BusinessHealthDimension

    def for_snapshot(self, snapshot_id: str) -> list:
        return list(self.session.scalars(
            select(BusinessHealthDimension)
            .where(BusinessHealthDimension.snapshot_id == snapshot_id)
            .order_by(BusinessHealthDimension.dimension)).all())


class MonitoringEventRepository(_Repo):
    model = BusinessMonitoringEvent


class ObservationRepository(_Repo):
    model = BusinessObservation

    def for_business(self, business_id: str, limit: int = 200) -> list:
        return list(self.session.scalars(
            select(BusinessObservation)
            .where(BusinessObservation.business_id == business_id)
            .order_by(BusinessObservation.created_at.desc())
            .limit(limit)).all())


class DecisionRepository(_Repo):
    model = BusinessDecision

    def by_execution_key(self, key: str):
        return self.session.scalars(
            select(BusinessDecision)
            .where(BusinessDecision.execution_key == key)).first()


class DecisionAlternativeRepository(_Repo):
    model = BusinessDecisionAlternative

    def for_decision(self, decision_id: str) -> list:
        return list(self.session.scalars(
            select(BusinessDecisionAlternative)
            .where(BusinessDecisionAlternative.decision_id == decision_id)
            .order_by(BusinessDecisionAlternative.created_at)).all())


class LifecycleOverlayRepository(_Repo):
    model = BusinessLifecycleOverlay

    def latest_for(self, business_id: str):
        return self.session.scalars(
            select(BusinessLifecycleOverlay)
            .where(BusinessLifecycleOverlay.business_id == business_id)
            .order_by(BusinessLifecycleOverlay.created_at.desc())
            .limit(1)).first()


class ExperimentRepository(_Repo):
    model = BusinessExperiment


class ExperimentEvaluationRepository(_Repo):
    model = ExperimentEvaluation

    def for_experiment(self, experiment_id: str) -> list:
        return list(self.session.scalars(
            select(ExperimentEvaluation)
            .where(ExperimentEvaluation.experiment_id == experiment_id)
            .order_by(ExperimentEvaluation.created_at.desc())).all())


class ScalingAssessmentRepository(_Repo):
    model = ScalingAssessment

    def latest_for(self, business_id: str):
        return self.session.scalars(
            select(ScalingAssessment)
            .where(ScalingAssessment.business_id == business_id)
            .order_by(ScalingAssessment.created_at.desc())
            .limit(1)).first()


class ScalingPlanRepository(_Repo):
    model = ScalingPlan


class RecoveryPlanRepository(_Repo):
    model = RecoveryPlan

    def active_for(self, business_id: str):
        return self.session.scalars(
            select(RecoveryPlan)
            .where(RecoveryPlan.business_id == business_id,
                   RecoveryPlan.status.in_(("PROPOSED", "APPROVED", "ACTIVE")))
            .order_by(RecoveryPlan.created_at.desc())
            .limit(1)).first()


class ClosureReviewRepository(_Repo):
    model = ClosureReview

    def open_for(self, business_id: str):
        return self.session.scalars(
            select(ClosureReview)
            .where(ClosureReview.business_id == business_id,
                   ClosureReview.stage.notin_(("CLOSED", "ARCHIVED", "REJECTED")))
            .order_by(ClosureReview.created_at.desc())
            .limit(1)).first()


class CapitalAllocationRepository(_Repo):
    model = CapitalAllocationProposal


class ResourceAllocationRepository(_Repo):
    model = ResourceAllocationProposal


class SurvivalForecastRepository(_Repo):
    model = SurvivalForecast


class DecisionOutcomeRepository(_Repo):
    model = DecisionOutcome


class PauseControlRepository(_Repo):
    model = BusinessPauseControl

    def active_for(self, business_id: str):
        return self.session.scalars(
            select(BusinessPauseControl)
            .where(BusinessPauseControl.business_id == business_id,
                   BusinessPauseControl.active.is_(True))
            .order_by(BusinessPauseControl.created_at.desc())
            .limit(1)).first()
