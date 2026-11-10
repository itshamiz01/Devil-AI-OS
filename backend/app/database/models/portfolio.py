"""SQLAlchemy models for the P-13 Multi-business Coordination Engine.

One additive migration creates these tables; no P-01..P-12 table is
altered. P-13 is a coordination and intelligence layer over existing
authorities, so its tables hold only portfolio-owned state:

* the portfolio registry (portfolios, memberships, objectives) —
  membership is metadata about P-06 businesses, never a copy of them;
* the business relationship graph (§14) with governed states;
* cross-business opportunities and portfolio recommendations (§6/§7),
  each carrying its evidence payload — the engine's evidence gate
  rejects records whose evidence cannot support the claim;
* the shared-service registry, scoped access grants and usage
  records (§9);
* internal cost allocations (§9/§11) — **management accounting only**:
  an allocation is a typed internal record, never a journal entry,
  never a payment, and P-07 never reads these rows (the P-08 proposal
  precedent: proposal/allocation records may carry an amount; the
  ledger may not be duplicated);
* resource quotas and capacity allocations (§10) over shared
  infrastructure units — disjoint from P-08's capital/resource
  *proposals*, which remain the recommendation path;
* cross-business permission grants and shared-agent assignments
  (§8/§20): scoped, expiring, revocable coordination records;
* portfolio workflow coordination rows (§13) that link to P-12
  sub-workflows — execution truth stays in P-12;
* persisted risk assessments and generated reports (§12/§18) —
  snapshots of computed analysis, always labelled with their data
  sources and completeness;
* new-venture proposals (§17) — recommendations to the owner;
  business creation stays in P-06.

No P-13 table stores a business lifecycle state (P-06's machine is
the only one; the portfolio stage is a derived label), no approval
store (decisions are governed status fields on the owning rows;
P-01 approvals remain the authority where an approval is required),
and no credential material of any kind.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON, Boolean, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class BusinessPortfolio(TimestampMixin, Base):
    """One portfolio: a named collection of independently-owned
    businesses (§3 Level 2). Survival mode (§12) is an advisory
    portfolio state recorded here — it can flag and recommend, and
    it blocks new discretionary P-13 allocations; it cannot pause a
    business (P-08), stop operations (P-10/P-12) or move funds (P-07).
    """

    __tablename__ = "business_portfolios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mission: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ACTIVE", index=True)
    survival_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False)
    survival_activated_by: Mapped[str | None] = mapped_column(
        String(160), nullable=True)
    survival_activated_at: Mapped[str | None] = mapped_column(
        String(40), nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)


class PortfolioBusinessMembership(TimestampMixin, Base):
    """A P-06 business registered in a portfolio (§4). Membership is
    P-13-side metadata only: strategic priority, analytical group
    labels, membership status. Removing a membership never touches
    the business record."""

    __tablename__ = "portfolio_business_memberships"
    __table_args__ = (UniqueConstraint(
        "portfolio_id", "business_id", name="uq_portfolio_membership"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("business_portfolios.id"), nullable=False, index=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ACTIVE", index=True)
    strategic_priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50)
    group_labels: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    registered_by: Mapped[str] = mapped_column(String(160), nullable=False)


class PortfolioObjective(TimestampMixin, Base):
    """An owner-defined portfolio objective (§4/§16) with a planning
    horizon. Targets are descriptive JSON; financial truth referenced
    by an objective is always read live from P-07, never stored here.
    """

    __tablename__ = "portfolio_objectives"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("business_portfolios.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    horizon: Mapped[str] = mapped_column(
        String(30), nullable=False, default="90_DAY")
    targets: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ACTIVE", index=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)


class BusinessRelationship(TimestampMixin, Base):
    """One governed relationship between two businesses (§14).
    Technical relationships never imply legal ownership or
    contractual obligation; the agreement reference is a label the
    owner supplies, not a contract this system creates."""

    __tablename__ = "business_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("business_portfolios.id"), nullable=False, index=True)
    source_business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    target_business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(
        String(60), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PROPOSED", index=True)
    access_scope: Mapped[str] = mapped_column(
        String(40), nullable=False, default="NONE")
    agreement_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    risk_classification: Mapped[str] = mapped_column(
        String(30), nullable=False, default="low")
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    starts_on: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ends_on: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)


class CrossBusinessOpportunity(TimestampMixin, Base):
    """A cross-business opportunity (§7) with its evaluation and the
    evidence supporting it. `evidence_status` records the evidence
    gate's verdict: VERIFIED (every claim traces to a system source),
    SPECULATIVE (labelled, never presented as fact) or REJECTED (the
    gate refused the claim — kept for audit, never actionable)."""

    __tablename__ = "cross_business_opportunities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("business_portfolios.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    business_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evaluation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="SPECULATIVE", index=True)
    confidence: Mapped[str] = mapped_column(
        String(20), nullable=False, default="low")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PROPOSED", index=True)
    origin: Mapped[str] = mapped_column(
        String(30), nullable=False, default="detector")
    decided_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)


class PortfolioRecommendation(TimestampMixin, Base):
    """One portfolio recommendation in the §6 format. Monetary
    figures live inside `financial_implications` JSON as labelled
    estimates or P-07-sourced snapshots (the P-12 convention) — a
    recommendation never moves money and is never presented as
    verified revenue or guaranteed savings."""

    __tablename__ = "portfolio_recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("business_portfolios.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    strategic_objective: Mapped[str] = mapped_column(
        Text, nullable=False, default="")
    affected_business_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expected_benefit: Mapped[str] = mapped_column(Text, nullable=False, default="")
    estimated_cost: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    potential_revenue_impact: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict)
    operational_requirements: Mapped[str] = mapped_column(
        Text, nullable=False, default="")
    financial_implications: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict)
    legal_considerations: Mapped[str] = mapped_column(
        Text, nullable=False, default="")
    risks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    assumptions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(
        String(20), nullable=False, default="low")
    approval_requirements: Mapped[str] = mapped_column(
        Text, nullable=False, default="owner decision")
    proposed_next_steps: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list)
    evidence_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="SPECULATIVE", index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PROPOSED", index=True)
    origin: Mapped[str] = mapped_column(
        String(30), nullable=False, default="detector")
    decided_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)


class SharedService(TimestampMixin, Base):
    """A registered shared service (§9): infrastructure several
    businesses may use under scoped, revocable access grants."""

    __tablename__ = "shared_services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    service_kind: Mapped[str] = mapped_column(
        String(60), nullable=False, index=True)
    supported_categories: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list)
    capacity_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_model: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    security_classification: Mapped[str] = mapped_column(
        String(30), nullable=False, default="internal")
    access_policy: Mapped[str] = mapped_column(
        String(40), nullable=False, default="owner_approval")
    sla: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="AVAILABLE", index=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)


class SharedServiceAccess(TimestampMixin, Base):
    """One business's scoped access grant to a shared service (§9).
    Access exists only while a row is ACTIVE; revocation is
    immediate and verified by the access-check path."""

    __tablename__ = "shared_service_access"
    __table_args__ = (UniqueConstraint(
        "service_id", "business_id", name="uq_shared_service_access"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    service_id: Mapped[str] = mapped_column(
        ForeignKey("shared_services.id"), nullable=False, index=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="REQUESTED", index=True)
    scope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    units_reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime, nullable=True)
    granted_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    revoked_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    requested_by: Mapped[str] = mapped_column(String(160), nullable=False)


class SharedServiceUsage(TimestampMixin, Base):
    """One usage record against an ACTIVE access grant (§9 usage
    records). Recording usage without an active grant is refused by
    the service — this table only ever documents authorized use."""

    __tablename__ = "shared_service_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    access_id: Mapped[str] = mapped_column(
        ForeignKey("shared_service_access.id"), nullable=False, index=True)
    service_id: Mapped[str] = mapped_column(
        ForeignKey("shared_services.id"), nullable=False, index=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recorded_by: Mapped[str] = mapped_column(String(160), nullable=False)


class InternalCostAllocation(TimestampMixin, Base):
    """A management-accounting allocation (§9/§11): one business
    bears an internal share of a shared cost. **This is not a
    payment, not an invoice, not a journal entry.** `kind` is
    permanently INTERNAL_ALLOCATION; no external-payment semantics
    exist on this row, and P-07 totals are provably unaffected by
    these records (regression-tested)."""

    __tablename__ = "internal_cost_allocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("business_portfolios.id"), nullable=False, index=True)
    service_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_services.id"), nullable=True, index=True)
    charged_business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    providing_business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default="INTERNAL_ALLOCATION")
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="RECORDED", index=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)


class ResourceQuota(TimestampMixin, Base):
    """A per-business quota over one shared resource kind (§10).
    Quotas cap allocations; they grant nothing by themselves."""

    __tablename__ = "resource_quotas"
    __table_args__ = (UniqueConstraint(
        "portfolio_id", "business_id", "resource_kind",
        name="uq_resource_quota"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("business_portfolios.id"), nullable=False, index=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    resource_kind: Mapped[str] = mapped_column(
        String(60), nullable=False, index=True)
    quota_units: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)


class ResourceAllocation(TimestampMixin, Base):
    """A capacity allocation of shared infrastructure units to one
    business (§10). Approval enforces capacity, the per-business
    share cap (anti-monopolization) and any quota — the checks run
    in the service, never in the client."""

    __tablename__ = "resource_allocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("business_portfolios.id"), nullable=False, index=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    resource_kind: Mapped[str] = mapped_column(
        String(60), nullable=False, index=True)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PROPOSED", index=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    discretionary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    released_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)


class CrossBusinessPermission(TimestampMixin, Base):
    """An explicit, scoped, expiring cross-business data grant
    (§20). Every grant names source business, target business,
    grantee agent, purpose, authorized data categories and permitted
    actions. Expiry is mandatory: an open-ended cross-business grant
    cannot be created. `credentials` is never a grantable category.
    """

    __tablename__ = "cross_business_permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("business_portfolios.id"), nullable=False, index=True)
    source_business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    target_business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    grantee_agent_id: Mapped[str] = mapped_column(
        String(120), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    authorized_data: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list)
    permitted_actions: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ACTIVE", index=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    granted_by: Mapped[str] = mapped_column(String(160), nullable=False)
    revoked_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    revoked_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class PortfolioAgentAssignment(TimestampMixin, Base):
    """A shared-agent assignment (§8): an agent scoped to one
    business or to a portfolio's aggregate data, with allowed tools,
    allowed data categories, a budget *reference* (a P-07 budget id
    + cap snapshot — money itself stays in P-07) and an expiry.
    Portfolio scope can never carry record-level categories."""

    __tablename__ = "portfolio_agent_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("business_portfolios.id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="BUSINESS")
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    task_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    required_capabilities: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list)
    allowed_tools: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    allowed_data: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    budget_scope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    permission_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ACTIVE", index=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime, nullable=True)
    assigned_by: Mapped[str] = mapped_column(String(160), nullable=False)
    revoked_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    revoked_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class PortfolioWorkflow(TimestampMixin, Base):
    """A cross-business workflow coordination record (§13). The
    coordination state lives here; execution truth lives in the
    P-12 sub-workflows it links. A portfolio workflow grants no
    access between participants — each participation records what
    that business explicitly authorized."""

    __tablename__ = "portfolio_workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("business_portfolios.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT", index=True)
    success_criteria: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)


class PortfolioWorkflowParticipation(TimestampMixin, Base):
    """One business's participation in a portfolio workflow (§13):
    its role, what it explicitly contributes (shareable data
    categories and resources only), its authorization status, the
    P-12 sub-workflow created for it, deliverables and asset
    ownership declarations."""

    __tablename__ = "portfolio_workflow_participations"
    __table_args__ = (UniqueConstraint(
        "portfolio_workflow_id", "business_id",
        name="uq_portfolio_workflow_participation"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_workflow_id: Mapped[str] = mapped_column(
        ForeignKey("portfolio_workflows.id"), nullable=False, index=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    contributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    authorization_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="AUTHORIZED", index=True)
    sub_workflow_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    deliverables: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    asset_ownership: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict)


class PortfolioRiskAssessment(TimestampMixin, Base):
    """A persisted portfolio/business risk assessment (§12): the
    findings are computed from P-07 figures and P-08 readings at
    assessment time and stored with their evidence, so a historical
    assessment stays honest about what it saw."""

    __tablename__ = "portfolio_risk_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("business_portfolios.id"), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PORTFOLIO")
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    overall_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="low", index=True)
    findings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    data_complete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True)
    assessed_by: Mapped[str] = mapped_column(String(160), nullable=False)


class PortfolioReport(TimestampMixin, Base):
    """A generated portfolio report (§18J): a stored snapshot with
    its generation time, period, data sources, metric definitions
    and completeness flags. Reports present P-07/P-08 facts; where
    data is missing the payload says so — a report never fills a
    gap with an invented figure."""

    __tablename__ = "portfolio_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("business_portfolios.id"), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    period: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    data_complete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True)
    generated_by: Mapped[str] = mapped_column(String(160), nullable=False)


class NewVentureProposal(TimestampMixin, Base):
    """A new-venture proposal (§17) in the prompt's full format,
    with the anti-duplication overlap check recorded at creation.
    Approval marks the proposal ready for the owner's own P-06
    path — P-13 never creates the business (Scenario 14)."""

    __tablename__ = "new_venture_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("business_portfolios.id"), nullable=False, index=True)
    concept: Mapped[str] = mapped_column(String(300), nullable=False)
    target_customer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    customer_problem: Mapped[str] = mapped_column(Text, nullable=False, default="")
    market_evidence: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list)
    business_model: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    template: Mapped[str | None] = mapped_column(String(120), nullable=True)
    competitive_position: Mapped[str] = mapped_column(
        Text, nullable=False, default="")
    expected_costs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    funding_requirements: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict)
    revenue_scenarios: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict)
    risk_analysis: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    portfolio_synergy: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cannibalization_risk: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unknown")
    recommended_experiment: Mapped[str] = mapped_column(
        Text, nullable=False, default="")
    overlap_check: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    opportunity_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT", index=True)
    decided_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
