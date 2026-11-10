"""P-03 Opportunity Discovery entities (additive — P-01/P-02 tables untouched).

Design posture (P-03 prompt §9/§19/§21): every commercial claim the system
makes must be traceable to an ``evidence_records`` row with provenance
(source, URL, retrieval timestamp, reliability classification). Analysis
rows store their inputs and assumptions as JSON so every number in a
report can be recomputed and audited. History is append-only: lifecycle
transitions, scores and validations are new rows, never overwrites.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, new_uuid, utcnow


class ResearchBrief(Base, TimestampMixin):
    """An owner research request: the constraints discovery must honour
    (budget is an owner fact — the engine never silently raises it)."""

    __tablename__ = "research_briefs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    budget_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    # P-14 Stage B (DEF-D1): integer minor units — the canonical money
    # representation going forward; set alongside budget_amount at
    # creation. The Float column is retained, deprecated.
    budget_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    geography: Mapped[str] = mapped_column(String(100), default="global", nullable=False)
    categories: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    constraints: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    creator_type: Mapped[str] = mapped_column(String(32), nullable=False)
    creator_id: Mapped[str] = mapped_column(String(200), nullable=False)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.id"), nullable=True)
    # open -> completed (discovery run finished; opportunities may still evolve)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Opportunity(Base, TimestampMixin):
    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    # Normalised dedup key (lowercased name + category + geography).
    slug: Mapped[str] = mapped_column(String(400), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    target_customer: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    geography: Mapped[str] = mapped_column(String(100), default="global", nullable=False)
    problem_statement: Mapped[str] = mapped_column(Text, default="", nullable=False)
    proposed_solution: Mapped[str] = mapped_column(Text, default="", nullable=False)
    revenue_model: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    discovery_method: Mapped[str] = mapped_column(String(100), default="manual", nullable=False)
    # Lifecycle status — see opportunities.lifecycle.TRANSITIONS.
    status: Mapped[str] = mapped_column(String(40), default="DISCOVERED", index=True, nullable=False)
    validation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    brief_id: Mapped[str | None] = mapped_column(ForeignKey("research_briefs.id"), nullable=True)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.id"), nullable=True)
    duplicate_of_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True)
    # Capability assessment: which system capabilities the model needs vs has.
    capability_fit: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Compliance screening outcome: {verdict, flags, requires_professional_review, matched_rules}
    compliance: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_researched_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchSource(Base, TimestampMixin):
    """A registered research source (adapter catalogue entry). Seeded from
    the owner-provided/seed catalogue; owners may add more. A source row is
    a *declaration* (what the adapter may fetch and how reliable that class
    of source is) — it is never itself evidence of a commercial claim."""

    __tablename__ = "research_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    source_key: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)  # official_platform, marketplace, ...
    access_method: Mapped[str] = mapped_column(String(50), default="web_page", nullable=False)  # seed_document | web_page | rss
    auth_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rate_limit: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reliability_classification: Mapped[str] = mapped_column(String(100), nullable=False)
    usage_restrictions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Independence group: sources sharing a group are NOT independent of
    # each other for corroboration (§9.3 — syndicated copies don't count twice).
    independence_group: Mapped[str] = mapped_column(String(200), nullable=False)
    origin: Mapped[str] = mapped_column(String(50), default="seed", nullable=False)  # seed | owner | manual
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ResearchSession(Base, TimestampMixin):
    """One research run against one opportunity, executed as a P-01 task."""

    __tablename__ = "research_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True, nullable=False)
    objective: Mapped[str] = mapped_column(Text, default="", nullable=False)
    stage: Mapped[str] = mapped_column(String(100), default="collect_evidence", nullable=False)
    # pending -> running -> completed | failed
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    sources_examined: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    findings_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    opportunity: Mapped["Opportunity"] = relationship()


class EvidenceRecord(Base, TimestampMixin):
    """One claim + its provenance. The heart of the evidence discipline:
    no claim exists in a report without a row here, and every row states
    how much the claim may be trusted and where it came from."""

    __tablename__ = "evidence_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True, nullable=False)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("research_sources.id"), nullable=True)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # demand, problem, pricing, ...
    # VERIFIED | CORROBORATED | SUPPORTING | TENTATIVE | UNVERIFIED | CONTRADICTED | OUTDATED
    classification: Mapped[str] = mapped_column(String(32), default="UNVERIFIED", index=True, nullable=False)
    # source_claim (came from a source) | owner_real_world (L4-grade) | owner_payment (L5-grade)
    evidence_kind: Mapped[str] = mapped_column(String(32), default="source_claim", nullable=False)
    # Normalised topic key used for corroboration/contradiction matching.
    topic_key: Mapped[str] = mapped_column(String(200), default="", index=True, nullable=False)
    independence_group: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    retrieval_timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    publication_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(100), default="manual", nullable=False)
    freshness_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)  # fresh | stale | unknown
    recorded_by: Mapped[str] = mapped_column(String(200), default="system", nullable=False)

    opportunity: Mapped["Opportunity"] = relationship()
    source: Mapped["ResearchSource | None"] = relationship()


class Competitor(Base, TimestampMixin):
    __tablename__ = "competitors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    website: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    product: Mapped[str] = mapped_column(Text, default="", nullable=False)
    competitor_type: Mapped[str] = mapped_column(String(50), default="direct", nullable=False)
    pricing_claim: Mapped[str | None] = mapped_column(Text, nullable=True)
    pricing_evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence_records.id"), nullable=True)
    features: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    strengths: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    weaknesses: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    positioning: Mapped[str] = mapped_column(Text, default="", nullable=False)

    opportunity: Mapped["Opportunity"] = relationship()


class MarketAnalysis(Base, TimestampMixin):
    __tablename__ = "market_analyses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True, nullable=False)
    customer_segment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    geographic_market: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    problem_analysis: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    demand_indicators: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # {tam: {value, methodology} | {value: None, note: "cannot be established"}, sam: ..., som: ...}
    market_size: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    saturation: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    gaps: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    inputs_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class CommercialAnalysis(Base, TimestampMixin):
    __tablename__ = "commercial_analyses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True, nullable=False)
    revenue_model: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    # Cost lines: [{name, amount, classification: verified|quoted|historical|estimate|unknown, source_note}]
    startup_costs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recurring_costs_monthly: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    variable_costs_per_sale: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # {price, classification, basis}
    price_assumption: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # {conservative|base|optimistic: {assumptions, sales_per_month, revenue, gross_profit,
    #  contribution_margin, operating_profit, net_cash_flow}}
    scenarios: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # {contribution_per_sale, break_even_sales_per_month, break_even_revenue, feasible: bool|None}
    break_even: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # {budget_amount, minimum_viable_cost, recurring_monthly, contingency_required,
    #  maximum_affordable_experiment_cost, compatible}
    budget: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    distribution: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    inputs_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class OpportunityScore(Base, TimestampMixin):
    __tablename__ = "opportunity_scores"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True, nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(50), nullable=False)
    dimensions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # dimension -> 0..5
    dimension_reasons: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    weights: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    weighted_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # 0..5
    # Evidence quality reported SEPARATELY from attractiveness (§16.3).
    evidence_quality: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # 0..5
    risk_classification: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    # {rule, reason} when a hard rejection overrides the numeric score, else None.
    hard_rejection: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommendation: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    inputs_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ValidationRecord(Base, TimestampMixin):
    __tablename__ = "validation_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    criteria_met: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    criteria_missing: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    reviewer: Mapped[str] = mapped_column(String(200), nullable=False)
    decision: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class OpportunityHistory(Base):
    """Append-only lifecycle/research history (§17, §21). Never updated."""

    __tablename__ = "opportunity_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
