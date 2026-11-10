"""Repository layer for P-13 portfolio tables. All SQL for the
portfolio package lives here; API routes never build queries.

Append-only by convention for usage records, allocations, risk
assessments and reports; registry/graph/grant rows change only
through governed status transitions performed by the service.
No financial records are stored or read here beyond the typed
management-accounting allocations (P-07 is the only ledger).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.portfolio import (
    BusinessPortfolio, BusinessRelationship, CrossBusinessOpportunity,
    CrossBusinessPermission, InternalCostAllocation, NewVentureProposal,
    PortfolioAgentAssignment, PortfolioBusinessMembership,
    PortfolioObjective, PortfolioRecommendation, PortfolioReport,
    PortfolioRiskAssessment, PortfolioWorkflow,
    PortfolioWorkflowParticipation, ResourceAllocation, ResourceQuota,
    SharedService, SharedServiceAccess, SharedServiceUsage,
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

    def list(self, *, limit: int = 100, offset: int = 0, **filters):
        stmt = select(self.model)
        count = select(func.count()).select_from(self.model)
        for name, value in filters.items():
            if value is None:
                continue
            column = getattr(self.model, name)
            stmt = stmt.where(column == value)
            count = count.where(column == value)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(self.model.created_at.desc())
            .limit(limit).offset(offset)))
        return rows, total


class PortfolioRepository(_Repo):
    model = BusinessPortfolio


class MembershipRepository(_Repo):
    model = PortfolioBusinessMembership

    def get_membership(self, portfolio_id: str, business_id: str):
        return self.session.scalar(
            select(PortfolioBusinessMembership).where(
                PortfolioBusinessMembership.portfolio_id == portfolio_id,
                PortfolioBusinessMembership.business_id == business_id))

    def for_portfolio(self, portfolio_id: str, *, active_only: bool = False):
        stmt = select(PortfolioBusinessMembership).where(
            PortfolioBusinessMembership.portfolio_id == portfolio_id)
        if active_only:
            stmt = stmt.where(
                PortfolioBusinessMembership.status != "REMOVED")
        return list(self.session.scalars(
            stmt.order_by(PortfolioBusinessMembership.created_at)))


class ObjectiveRepository(_Repo):
    model = PortfolioObjective


class RelationshipRepository(_Repo):
    model = BusinessRelationship

    def for_business(self, portfolio_id: str, business_id: str):
        return list(self.session.scalars(
            select(BusinessRelationship).where(
                BusinessRelationship.portfolio_id == portfolio_id,
                (BusinessRelationship.source_business_id == business_id)
                | (BusinessRelationship.target_business_id == business_id))
            .order_by(BusinessRelationship.created_at.desc())))


class OpportunityRepository(_Repo):
    model = CrossBusinessOpportunity


class RecommendationRepository(_Repo):
    model = PortfolioRecommendation


class SharedServiceRepository(_Repo):
    model = SharedService


class ServiceAccessRepository(_Repo):
    model = SharedServiceAccess

    def get_access(self, service_id: str, business_id: str):
        return self.session.scalar(
            select(SharedServiceAccess).where(
                SharedServiceAccess.service_id == service_id,
                SharedServiceAccess.business_id == business_id))

    def for_service(self, service_id: str):
        return list(self.session.scalars(
            select(SharedServiceAccess).where(
                SharedServiceAccess.service_id == service_id)))


class ServiceUsageRepository(_Repo):
    model = SharedServiceUsage

    def for_service(self, service_id: str):
        return list(self.session.scalars(
            select(SharedServiceUsage).where(
                SharedServiceUsage.service_id == service_id)
            .order_by(SharedServiceUsage.created_at.desc())))

    def total_units(self, access_id: str) -> int:
        return int(self.session.scalar(
            select(func.coalesce(func.sum(SharedServiceUsage.units), 0))
            .where(SharedServiceUsage.access_id == access_id)) or 0)


class AllocationRepository(_Repo):
    model = InternalCostAllocation


class QuotaRepository(_Repo):
    model = ResourceQuota

    def get_quota(self, portfolio_id: str, business_id: str, kind: str):
        return self.session.scalar(
            select(ResourceQuota).where(
                ResourceQuota.portfolio_id == portfolio_id,
                ResourceQuota.business_id == business_id,
                ResourceQuota.resource_kind == kind))


class ResourceAllocationRepository(_Repo):
    model = ResourceAllocation

    def active_units(self, portfolio_id: str, kind: str,
                     business_id: str | None = None) -> int:
        stmt = select(func.coalesce(func.sum(ResourceAllocation.units), 0)).where(
            ResourceAllocation.portfolio_id == portfolio_id,
            ResourceAllocation.resource_kind == kind,
            ResourceAllocation.status == "ACTIVE")
        if business_id is not None:
            stmt = stmt.where(ResourceAllocation.business_id == business_id)
        return int(self.session.scalar(stmt) or 0)


class GrantRepository(_Repo):
    model = CrossBusinessPermission

    def active_for(self, agent_id: str, source_id: str, target_id: str):
        return list(self.session.scalars(
            select(CrossBusinessPermission).where(
                CrossBusinessPermission.grantee_agent_id == agent_id,
                CrossBusinessPermission.source_business_id == source_id,
                CrossBusinessPermission.target_business_id == target_id,
                CrossBusinessPermission.status == "ACTIVE")))


class AgentAssignmentRepository(_Repo):
    model = PortfolioAgentAssignment

    def active_for_agent(self, agent_id: str):
        return list(self.session.scalars(
            select(PortfolioAgentAssignment).where(
                PortfolioAgentAssignment.agent_id == agent_id,
                PortfolioAgentAssignment.status == "ACTIVE")))


class PortfolioWorkflowRepository(_Repo):
    model = PortfolioWorkflow


class ParticipationRepository(_Repo):
    model = PortfolioWorkflowParticipation

    def for_workflow(self, workflow_id: str):
        return list(self.session.scalars(
            select(PortfolioWorkflowParticipation).where(
                PortfolioWorkflowParticipation.portfolio_workflow_id
                == workflow_id)
            .order_by(PortfolioWorkflowParticipation.created_at)))


class RiskAssessmentRepository(_Repo):
    model = PortfolioRiskAssessment


class ReportRepository(_Repo):
    model = PortfolioReport


class VentureRepository(_Repo):
    model = NewVentureProposal
