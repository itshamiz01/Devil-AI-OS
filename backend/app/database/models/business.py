"""SQLAlchemy models for the P-06 Business Creation Engine tables.

One additive migration creates these tables; no P-01..P-05 table is
altered. Approvals, opportunities, workspaces and audit events reuse
their existing homes (P-06 pre-implementation audit §5) — there is
deliberately no ``business_approvals`` table and, per P-06 §9/§27,
**no column anywhere in this module can hold collected revenue or
profit**: pricing is data, financial truth belongs to P-07.
"""
from __future__ import annotations

from sqlalchemy import (
    JSON, BigInteger, Boolean, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class BusinessTemplate(TimestampMixin, Base):
    __tablename__ = "business_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class BusinessTemplateVersion(TimestampMixin, Base):
    __tablename__ = "business_template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version",
                                       name="uq_business_template_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    template_id: Mapped[str] = mapped_column(
        ForeignKey("business_templates.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="valid")
    validation_errors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class Business(TimestampMixin, Base):
    __tablename__ = "businesses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    template_id: Mapped[str] = mapped_column(
        ForeignKey("business_templates.id"), nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="PROPOSED", index=True)
    validation_level_at_creation: Mapped[int] = mapped_column(Integer, nullable=False)
    score_at_creation: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_classification: Mapped[str | None] = mapped_column(String(60), nullable=True)
    eligibility_decision: Mapped[str] = mapped_column(String(40), nullable=False)
    eligibility_details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    creation_approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workspace_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Website truth is five separate fields, never collapsed (§13.5/§19).
    website_states: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Launch truth (§19): staging can only ever produce a local package.
    deployment_state: Mapped[str] = mapped_column(
        String(60), nullable=False, default="not_deployed")
    public_availability: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False)
    launched_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    paused_from: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class BusinessBlueprint(TimestampMixin, Base):
    __tablename__ = "business_blueprints"
    __table_args__ = (UniqueConstraint("business_id", "version",
                                       name="uq_business_blueprint_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    blueprint: Mapped[dict] = mapped_column(JSON, nullable=False)
    generation_method: Mapped[str] = mapped_column(
        String(80), nullable=False, default="deterministic_template_from_stored_data")
    approval_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft")
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class BusinessDeclaration(TimestampMixin, Base):
    """The Constitution's pre-declaration: recorded before any creation
    run; readiness and launch are judged against it, never against
    checklist completion."""

    __tablename__ = "business_declarations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    success_criteria: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    budget_cap_amount: Mapped[float] = mapped_column(Float, nullable=False)
    # P-14 Stage B (DEF-D1): integer minor units — canonical going
    # forward; set alongside budget_cap_amount at creation. The Float
    # column is retained, deprecated.
    budget_cap_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    budget_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    min_test_volume: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft")  # draft|approved
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    verdict: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    declared_by: Mapped[str] = mapped_column(String(120), nullable=False)


class BusinessAssumption(TimestampMixin, Base):
    __tablename__ = "business_assumptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    assumption: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    basis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="UNVERIFIED")
    impact_if_wrong: Mapped[str] = mapped_column(Text, nullable=False, default="")
    validation_method: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    last_reviewed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class BusinessProduct(TimestampMixin, Base):
    __tablename__ = "business_products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_type: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_customer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    problem_solved: Mapped[str] = mapped_column(Text, nullable=False, default="")
    core_features: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    excluded_features: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Pricing is DATA (§9): a financial-value object, never a transaction.
    pricing: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    delivery_method: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    support_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[str] = mapped_column(String(30), nullable=False, default="0.1.0")
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="SPECIFIED")
    development_plan: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    quality_review: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ProductRequirement(TimestampMixin, Base):
    __tablename__ = "product_requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("business_products.id"), nullable=False, index=True)
    requirement_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="should")
    acceptance_criteria: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="specified")


class BusinessAsset(TimestampMixin, Base):
    __tablename__ = "business_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    storage_reference: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[str] = mapped_column(String(30), nullable=False, default="1")
    creation_method: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    creator_agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approval_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft")
    usage_rights_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="original_work")
    quality_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unreviewed")
    content_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    associated_product_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class BusinessChannel(TimestampMixin, Base):
    __tablename__ = "business_channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    channel_type: Mapped[str] = mapped_column(String(60), nullable=False)
    platform: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    account_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fees: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    approval_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The §14 platform-gate outcome, recorded at evaluation time.
    platform_gate: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evaluation_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="CANDIDATE")
    # Staging truth: nothing is ever published; states stop at prepared.
    publish_state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_prepared")


class BusinessCampaign(TimestampMixin, Base):
    """Draft-only (§15): there is no send/post path anywhere in P-06."""

    __tablename__ = "business_campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audience: Mapped[str] = mapped_column(Text, nullable=False, default="")
    channel: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assets: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    budget: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    schedule: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    success_metrics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    approval_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft")  # draft is the only state


class BusinessPlaybook(TimestampMixin, Base):
    __tablename__ = "business_playbooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    daily_operations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    weekly_reviews: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    customer_support: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    quality_control: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    incident_response: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    escalation: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    backup_recovery: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    performance_indicators: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    known_risks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    improvement_procedures: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    asset_reference: Mapped[str | None] = mapped_column(Text, nullable=True)


class BusinessReadinessReview(TimestampMixin, Base):
    __tablename__ = "business_readiness_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    overall_status: Mapped[str] = mapped_column(String(40), nullable=False)
    dimensions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    blockers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    outstanding_requirements: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    declaration_comparison: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict)
    disclaimer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewed_by: Mapped[str] = mapped_column(String(120), nullable=False)


class BusinessLifecycleEvent(TimestampMixin, Base):
    __tablename__ = "business_lifecycle_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class BusinessEvidence(TimestampMixin, Base):
    __tablename__ = "business_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(60), nullable=False)
    claim_supported: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    reliability: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium")
    retrieved_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    freshness_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="current")
    associated_decision: Mapped[str] = mapped_column(Text, nullable=False, default="")
    limitations: Mapped[str] = mapped_column(Text, nullable=False, default="")


class BusinessEligibilityEvaluation(TimestampMixin, Base):
    """Append-only record of §6 evaluations (an evaluation never creates
    infrastructure by itself)."""

    __tablename__ = "business_eligibility_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id"), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    checks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    validation_level: Mapped[int] = mapped_column(Integer, nullable=False)
    min_validation_level: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_by: Mapped[str] = mapped_column(String(120), nullable=False)


class BusinessCreationRun(TimestampMixin, Base):
    __tablename__ = "business_creation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    workflow_definition_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="created")
    inputs_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_by: Mapped[str] = mapped_column(String(120), nullable=False)


class BusinessAgentAssignment(TimestampMixin, Base):
    __tablename__ = "business_agent_assignments"
    __table_args__ = (UniqueConstraint(
        "business_id", "agent_id", "role_in_business",
        name="uq_business_agent_assignment"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role_in_business: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="active")
    assigned_by: Mapped[str] = mapped_column(String(120), nullable=False)
