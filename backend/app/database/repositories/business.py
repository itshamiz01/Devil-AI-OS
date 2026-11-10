"""Repositories for the P-06 business tables (SQL lives here and in the
service built on these repositories, per the P-01 §6.3 convention)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.base import utcnow
from ..models.business import (
    Business, BusinessAgentAssignment, BusinessAsset, BusinessAssumption,
    BusinessBlueprint, BusinessCampaign, BusinessChannel,
    BusinessCreationRun, BusinessDeclaration, BusinessEligibilityEvaluation,
    BusinessEvidence, BusinessLifecycleEvent, BusinessPlaybook,
    BusinessProduct, BusinessReadinessReview, BusinessTemplate,
    BusinessTemplateVersion, ProductRequirement,
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


class BusinessTemplateRepository(_BaseRepo):
    def get(self, template_id: str) -> BusinessTemplate | None:
        return self.session.get(BusinessTemplate, template_id)

    def get_by_name(self, name: str) -> BusinessTemplate | None:
        return self.session.scalar(
            select(BusinessTemplate).where(BusinessTemplate.name == name))

    def list(self, limit: int = 100, offset: int = 0):
        total = self.session.scalar(
            select(func.count()).select_from(BusinessTemplate)) or 0
        rows = list(self.session.scalars(
            select(BusinessTemplate).order_by(BusinessTemplate.name)
            .limit(limit).offset(offset)).all())
        return rows, total


class BusinessTemplateVersionRepository(_BaseRepo):
    def get_version(self, template_id: str, version: int):
        return self.session.scalar(
            select(BusinessTemplateVersion).where(
                BusinessTemplateVersion.template_id == template_id,
                BusinessTemplateVersion.version == version))

    def latest(self, template_id: str):
        return self.session.scalar(
            select(BusinessTemplateVersion).where(
                BusinessTemplateVersion.template_id == template_id)
            .order_by(BusinessTemplateVersion.version.desc()))


class BusinessRepository(_BaseRepo):
    def get(self, business_id: str) -> Business | None:
        return self.session.get(Business, business_id)

    def get_by_slug(self, slug: str) -> Business | None:
        return self.session.scalar(
            select(Business).where(Business.slug == slug))

    def list(self, *, status: str | None = None, opportunity_id: str | None = None,
             limit: int = 100, offset: int = 0):
        stmt = select(Business)
        count = select(func.count()).select_from(Business)
        if status:
            stmt = stmt.where(Business.status == status)
            count = count.where(Business.status == status)
        if opportunity_id:
            stmt = stmt.where(Business.opportunity_id == opportunity_id)
            count = count.where(Business.opportunity_id == opportunity_id)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(Business.created_at.desc())
            .limit(limit).offset(offset)).all())
        return rows, total

    def count_all(self) -> int:
        return self.session.scalar(
            select(func.count()).select_from(Business)) or 0


class _ForBusiness(_BaseRepo):
    model = None
    order = None

    def list_for(self, business_id: str, limit: int = 200, offset: int = 0):
        stmt = select(self.model).where(self.model.business_id == business_id)
        if self.order is not None:
            stmt = stmt.order_by(self.order)
        total = self.session.scalar(
            select(func.count()).select_from(self.model)
            .where(self.model.business_id == business_id)) or 0
        rows = list(self.session.scalars(
            stmt.limit(limit).offset(offset)).all())
        return rows, total

    def latest_for(self, business_id: str):
        rows, _ = self.list_for(business_id, limit=1)
        return rows[0] if rows else None


class BlueprintRepository(_ForBusiness):
    model = BusinessBlueprint
    order = BusinessBlueprint.version.desc()


class DeclarationRepository(_ForBusiness):
    model = BusinessDeclaration

    def approved_for(self, business_id: str) -> BusinessDeclaration | None:
        return self.session.scalar(
            select(BusinessDeclaration).where(
                BusinessDeclaration.business_id == business_id,
                BusinessDeclaration.status == "approved")
            .order_by(BusinessDeclaration.created_at.desc()))


class AssumptionRepository(_ForBusiness):
    model = BusinessAssumption


class ProductRepository(_ForBusiness):
    model = BusinessProduct

    def get(self, product_id: str) -> BusinessProduct | None:
        return self.session.get(BusinessProduct, product_id)


class RequirementRepository(_BaseRepo):
    def list_for_product(self, product_id: str, limit: int = 200):
        return list(self.session.scalars(
            select(ProductRequirement).where(
                ProductRequirement.product_id == product_id)
            .order_by(ProductRequirement.created_at).limit(limit)).all())


class AssetRepository(_ForBusiness):
    model = BusinessAsset


class ChannelRepository(_ForBusiness):
    model = BusinessChannel


class CampaignRepository(_ForBusiness):
    model = BusinessCampaign


class PlaybookRepository(_ForBusiness):
    model = BusinessPlaybook
    order = BusinessPlaybook.version.desc()


class ReadinessRepository(_ForBusiness):
    model = BusinessReadinessReview
    order = BusinessReadinessReview.created_at.desc()


class LifecycleEventRepository(_ForBusiness):
    model = BusinessLifecycleEvent
    order = BusinessLifecycleEvent.created_at.asc()


class EvidenceRepository(_ForBusiness):
    model = BusinessEvidence


class EligibilityRepository(_BaseRepo):
    def list_for_opportunity(self, opportunity_id: str, limit: int = 50):
        return list(self.session.scalars(
            select(BusinessEligibilityEvaluation).where(
                BusinessEligibilityEvaluation.opportunity_id == opportunity_id)
            .order_by(BusinessEligibilityEvaluation.created_at.desc())
            .limit(limit)).all())

    def latest_for_opportunity(self, opportunity_id: str):
        rows = self.list_for_opportunity(opportunity_id, limit=1)
        return rows[0] if rows else None


class CreationRunRepository(_ForBusiness):
    model = BusinessCreationRun
    order = BusinessCreationRun.created_at.desc()


class AssignmentRepository(_ForBusiness):
    model = BusinessAgentAssignment

    def find(self, business_id: str, agent_id: str, role: str | None = None):
        stmt = select(BusinessAgentAssignment).where(
            BusinessAgentAssignment.business_id == business_id,
            BusinessAgentAssignment.agent_id == agent_id)
        if role:
            stmt = stmt.where(
                BusinessAgentAssignment.role_in_business == role)
        return self.session.scalar(stmt)

    def active_for_agent(self, business_id: str, agent_id: str):
        return self.session.scalar(
            select(BusinessAgentAssignment).where(
                BusinessAgentAssignment.business_id == business_id,
                BusinessAgentAssignment.agent_id == agent_id,
                BusinessAgentAssignment.status == "active"))
