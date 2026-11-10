"""Repository layer for P-03 opportunity entities."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.base import utcnow
from ..models.opportunities import (
    CommercialAnalysis, Competitor, EvidenceRecord, MarketAnalysis, Opportunity,
    OpportunityHistory, OpportunityScore, ResearchBrief, ResearchSession,
    ResearchSource, ValidationRecord,
)


class _BaseRepo:
    model = None

    def __init__(self, session: Session):
        self.session = session

    def add(self, row):
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def get(self, row_id: str):
        return self.session.get(self.model, row_id)

    def save(self, row):
        if hasattr(row, "updated_at"):
            row.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(row)
        return row


class BriefRepository(_BaseRepo):
    model = ResearchBrief

    def list(self, status: str | None = None, limit: int = 50, offset: int = 0):
        stmt = select(ResearchBrief)
        count_stmt = select(func.count()).select_from(ResearchBrief)
        if status:
            stmt = stmt.where(ResearchBrief.status == status)
            count_stmt = count_stmt.where(ResearchBrief.status == status)
        total = self.session.scalar(count_stmt) or 0
        rows = self.session.scalars(
            stmt.order_by(ResearchBrief.created_at.desc()).limit(limit).offset(offset)).all()
        return list(rows), total


class OpportunityRepository(_BaseRepo):
    model = Opportunity

    def get_by_slug(self, slug: str) -> Opportunity | None:
        return self.session.scalar(select(Opportunity).where(Opportunity.slug == slug))

    def list(self, status: str | None = None, category: str | None = None,
             geography: str | None = None, brief_id: str | None = None,
             limit: int = 50, offset: int = 0):
        stmt = select(Opportunity)
        count_stmt = select(func.count()).select_from(Opportunity)
        for column, value in ((Opportunity.status, status), (Opportunity.category, category),
                              (Opportunity.geography, geography), (Opportunity.brief_id, brief_id)):
            if value:
                stmt = stmt.where(column == value)
                count_stmt = count_stmt.where(column == value)
        total = self.session.scalar(count_stmt) or 0
        rows = self.session.scalars(
            stmt.order_by(Opportunity.created_at.desc()).limit(limit).offset(offset)).all()
        return list(rows), total

    def count_by_status(self) -> dict:
        rows = self.session.execute(
            select(Opportunity.status, func.count()).group_by(Opportunity.status)).all()
        return {status: count for status, count in rows}


class SourceRepository(_BaseRepo):
    model = ResearchSource

    def get_by_key(self, source_key: str) -> ResearchSource | None:
        return self.session.scalar(
            select(ResearchSource).where(ResearchSource.source_key == source_key))

    def list(self, enabled_only: bool = False):
        stmt = select(ResearchSource)
        if enabled_only:
            stmt = stmt.where(ResearchSource.enabled.is_(True))
        return list(self.session.scalars(stmt.order_by(ResearchSource.source_key.asc())).all())


class ResearchSessionRepository(_BaseRepo):
    model = ResearchSession

    def list_for(self, opportunity_id: str, limit: int = 50, offset: int = 0):
        stmt = select(ResearchSession).where(ResearchSession.opportunity_id == opportunity_id)
        count_stmt = select(func.count()).select_from(ResearchSession).where(
            ResearchSession.opportunity_id == opportunity_id)
        total = self.session.scalar(count_stmt) or 0
        rows = self.session.scalars(
            stmt.order_by(ResearchSession.created_at.desc()).limit(limit).offset(offset)).all()
        return list(rows), total

    def pending(self, limit: int = 50):
        return list(self.session.scalars(
            select(ResearchSession).where(ResearchSession.status.in_(["pending", "running"]))
            .order_by(ResearchSession.created_at.asc()).limit(limit)).all())


class EvidenceRepository(_BaseRepo):
    model = EvidenceRecord

    def list_for(self, opportunity_id: str, limit: int = 200, offset: int = 0):
        stmt = select(EvidenceRecord).where(EvidenceRecord.opportunity_id == opportunity_id)
        count_stmt = select(func.count()).select_from(EvidenceRecord).where(
            EvidenceRecord.opportunity_id == opportunity_id)
        total = self.session.scalar(count_stmt) or 0
        rows = self.session.scalars(
            stmt.order_by(EvidenceRecord.created_at.asc()).limit(limit).offset(offset)).all()
        return list(rows), total

    def by_topic(self, opportunity_id: str, topic_key: str):
        return list(self.session.scalars(
            select(EvidenceRecord).where(
                EvidenceRecord.opportunity_id == opportunity_id,
                EvidenceRecord.topic_key == topic_key)).all())


class CompetitorRepository(_BaseRepo):
    model = Competitor

    def list_for(self, opportunity_id: str):
        return list(self.session.scalars(
            select(Competitor).where(Competitor.opportunity_id == opportunity_id)
            .order_by(Competitor.created_at.asc())).all())


class MarketAnalysisRepository(_BaseRepo):
    model = MarketAnalysis

    def latest_for(self, opportunity_id: str) -> MarketAnalysis | None:
        return self.session.scalar(
            select(MarketAnalysis).where(MarketAnalysis.opportunity_id == opportunity_id)
            .order_by(MarketAnalysis.created_at.desc()))


class CommercialAnalysisRepository(_BaseRepo):
    model = CommercialAnalysis

    def latest_for(self, opportunity_id: str) -> CommercialAnalysis | None:
        return self.session.scalar(
            select(CommercialAnalysis).where(CommercialAnalysis.opportunity_id == opportunity_id)
            .order_by(CommercialAnalysis.created_at.desc()))


class ScoreRepository(_BaseRepo):
    model = OpportunityScore

    def latest_for(self, opportunity_id: str) -> OpportunityScore | None:
        return self.session.scalar(
            select(OpportunityScore).where(OpportunityScore.opportunity_id == opportunity_id)
            .order_by(OpportunityScore.created_at.desc()))

    def latest_scores(self):
        """Latest score row per opportunity (for rankings)."""
        rows = list(self.session.scalars(
            select(OpportunityScore).order_by(OpportunityScore.created_at.asc())).all())
        latest: dict[str, OpportunityScore] = {}
        for row in rows:
            latest[row.opportunity_id] = row
        return latest


class ValidationRepository(_BaseRepo):
    model = ValidationRecord

    def latest_for(self, opportunity_id: str) -> ValidationRecord | None:
        return self.session.scalar(
            select(ValidationRecord).where(ValidationRecord.opportunity_id == opportunity_id)
            .order_by(ValidationRecord.created_at.desc()))

    def list_for(self, opportunity_id: str):
        return list(self.session.scalars(
            select(ValidationRecord).where(ValidationRecord.opportunity_id == opportunity_id)
            .order_by(ValidationRecord.created_at.asc())).all())


class HistoryRepository(_BaseRepo):
    model = OpportunityHistory

    def list_for(self, opportunity_id: str, limit: int = 200, offset: int = 0):
        stmt = select(OpportunityHistory).where(OpportunityHistory.opportunity_id == opportunity_id)
        count_stmt = select(func.count()).select_from(OpportunityHistory).where(
            OpportunityHistory.opportunity_id == opportunity_id)
        total = self.session.scalar(count_stmt) or 0
        rows = self.session.scalars(
            stmt.order_by(OpportunityHistory.created_at.asc()).limit(limit).offset(offset)).all()
        return list(rows), total
