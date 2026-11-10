"""Repository layer for P-02 intelligence entities."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models.base import utcnow
from ..models.intelligence import DecisionRecord, Mission, ModelProfile, Plan, PlanStep


class MissionRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, mission: Mission) -> Mission:
        self.session.add(mission)
        self.session.commit()
        self.session.refresh(mission)
        return mission

    def get(self, mission_id: str) -> Mission | None:
        return self.session.get(Mission, mission_id)

    def list(self, status: str | None = None, limit: int = 50, offset: int = 0):
        stmt = select(Mission)
        count_stmt = select(func.count()).select_from(Mission)
        if status:
            stmt = stmt.where(Mission.status == status)
            count_stmt = count_stmt.where(Mission.status == status)
        total = self.session.scalar(count_stmt) or 0
        rows = self.session.scalars(
            stmt.order_by(Mission.created_at.desc()).limit(limit).offset(offset)).all()
        return list(rows), total

    def save(self, mission: Mission) -> Mission:
        mission.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(mission)
        return mission


class PlanRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, plan: Plan) -> Plan:
        self.session.add(plan)
        self.session.commit()
        self.session.refresh(plan)
        return plan

    def get(self, plan_id: str) -> Plan | None:
        return self.session.scalar(
            select(Plan).options(selectinload(Plan.steps)).where(Plan.id == plan_id))

    def count_for_mission(self, mission_id: str) -> int:
        return self.session.scalar(
            select(func.count()).select_from(Plan).where(Plan.mission_id == mission_id)) or 0

    def latest_for_mission(self, mission_id: str) -> Plan | None:
        return self.session.scalar(
            select(Plan).options(selectinload(Plan.steps))
            .where(Plan.mission_id == mission_id)
            .order_by(Plan.version.desc()))

    def save(self, plan: Plan) -> Plan:
        plan.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(plan)
        return plan

    def add_step(self, step: PlanStep) -> PlanStep:
        self.session.add(step)
        self.session.commit()
        self.session.refresh(step)
        return step

    def save_step(self, step: PlanStep) -> PlanStep:
        self.session.commit()
        self.session.refresh(step)
        return step

    def steps_for(self, plan_id: str) -> list[PlanStep]:
        return list(self.session.scalars(
            select(PlanStep).where(PlanStep.plan_id == plan_id)
            .order_by(PlanStep.order_index)).all())


class DecisionRecordRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, record: DecisionRecord) -> DecisionRecord:
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list(self, mission_id: str | None = None, plan_id: str | None = None,
             limit: int = 200, offset: int = 0):
        stmt = select(DecisionRecord)
        count_stmt = select(func.count()).select_from(DecisionRecord)
        if mission_id:
            stmt = stmt.where(DecisionRecord.mission_id == mission_id)
            count_stmt = count_stmt.where(DecisionRecord.mission_id == mission_id)
        if plan_id:
            stmt = stmt.where(DecisionRecord.plan_id == plan_id)
            count_stmt = count_stmt.where(DecisionRecord.plan_id == plan_id)
        total = self.session.scalar(count_stmt) or 0
        rows = self.session.scalars(
            stmt.order_by(DecisionRecord.created_at.asc(), DecisionRecord.id.asc())
            .limit(limit).offset(offset)).all()
        return list(rows), total


class ModelProfileRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, profile: ModelProfile) -> ModelProfile:
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return profile

    def get_by_name(self, name: str) -> ModelProfile | None:
        return self.session.scalar(select(ModelProfile).where(ModelProfile.name == name))

    def list(self) -> list[ModelProfile]:
        return list(self.session.scalars(
            select(ModelProfile).order_by(ModelProfile.name.asc())).all())

    def save(self, profile: ModelProfile) -> ModelProfile:
        profile.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(profile)
        return profile
