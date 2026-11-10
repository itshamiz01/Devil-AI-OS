"""SQLAlchemy models for the P-16 AI Economy Expansion Engine tables.

One additive migration creates these tables; no P-01..P-15 table is
altered. P-16 is an economic *intelligence and recommendation* layer
over P-03/P-06/P-07/P-08/P-13, so its tables hold only state no
earlier phase owns: market research records, the economy-level
opportunity pipeline, expansion strategies, business classifications,
commercialization assets/proposals, customer segments, capital
allocation and reinvestment *recommendations*, experiment
*proposals*, competitor profiles, country assessments, economic
decision records and portfolio risk snapshots.

Discipline carried from P-07/P-12/P-13/P-15:

* **No ledger, balance or account columns.** Amount fields are
  proposal data only (a recommended allocation, an experiment budget
  ceiling), in integer minor units, labelled PROPOSED in every API
  response. Financial truth is read live from P-07 at request time
  and never duplicated here; a named test proves P-07's consolidated
  output is byte-equal before and after every P-16 write flow.
* **No execution state.** Approvals are P-01 records (only the id is
  referenced), experiments execute in P-08 (only the id is
  referenced), businesses are created by P-06 (never here).
* Cross-engine references are plain indexed ids, so the migration
  cycle never entangles P-16 with earlier tables' lifecycles.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid, utcnow


class MarketReport(Base, TimestampMixin):
    """One §4.1 market research record. Content is entered through
    governed writes with mandatory source references; nothing here is
    scraped or fabricated by the system. ``figures_label`` keeps
    estimates visibly distinct from verified facts."""

    __tablename__ = "market_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    sector: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # sector: software_saas|ai_services|digital_products|content_media|
    # education|ecommerce|automation|professional_services|
    # subscriptions|licensing_ip|b2b_services|b2c_services|affiliate|other
    classification: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # classification: established|growing|emerging|experimental|
    # declining|speculative
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_customers: Mapped[str] = mapped_column(Text, nullable=False, default="")
    demand_indicators: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    competitor_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    revenue_models: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    startup_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="")
    operating_costs: Mapped[str] = mapped_column(Text, nullable=False, default="")
    acquisition_challenges: Mapped[str] = mapped_column(Text, nullable=False, default="")
    legal_regulatory: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # confidence: 0..100, declared by the researcher, never invented
    figures_label: Mapped[str] = mapped_column(
        String(24), nullable=False, default="estimates")
    # figures_label: estimates|verified — any number in a report is an
    # estimate unless the sources verify it
    p03_opportunity_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class EconomicOpportunity(Base, TimestampMixin):
    """One §4.2 pipeline entry with its §4.3 score. The pipeline is
    the economy-level view: an entry may link a P-03 opportunity
    (research substrate), an existing business (expansion of what we
    already run) or neither (a market-level idea). Movement through
    the 11 stages is governed: the evidence gate and the owner's
    profitability gate are enforced in the service, not by callers."""

    __tablename__ = "economic_opportunities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # kind: new_business|existing_business_expansion|new_revenue_stream|
    # asset_commercialization|market_entry|automation|other
    source_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual", index=True)
    # source_kind: manual|detector|p03_link|commercialization
    stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default="discovered", index=True)
    # stage: discovered|under_research|market_validation|
    # financial_evaluation|risk_assessment|approval_pending|
    # experimentation|launch_approved|active|rejected|archived
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    market_report_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    p03_opportunity_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    business_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    market_tag: Mapped[str | None] = mapped_column(
        String(80), nullable=True, index=True)
    factor_scores: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    classification_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    estimated_investment_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # proposal data only — an estimate, never a commitment
    gate_override: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {by, reason, at} — owner-only profitability-gate override
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class ExpansionStrategy(Base, TimestampMixin):
    """One §4.4 expansion strategy over one of the three horizons.
    ``kind`` drives the owner's profitability-first ordering and the
    gate: new_business / market_entry strategies cannot be approved
    while the profitability gate is closed (unless the owner records
    an explicit override on the strategy itself)."""

    __tablename__ = "expansion_strategies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    horizon: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # horizon: short|medium|long
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # kind: improve_existing|new_revenue_stream|diversification|
    # capital_efficiency|new_business|market_entry|commercialization
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    business_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    opportunity_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    financial_requirements: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    timeline: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    required_resources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    dependencies: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expected_outcomes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kpis: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    exit_conditions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", index=True)
    # status: draft|proposed|approved|rejected|archived
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    gate_override: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class EconomyClassification(Base, TimestampMixin):
    """One §5.1 classification row per business (owner-declared).
    Derived facts (profitability, maturity, concentration) are
    computed live from P-06/P-07/P-13 at read time and never stored
    here, so a classification can never go stale against the books."""

    __tablename__ = "business_classifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True)
    industry: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    revenue_model: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    # revenue_model: one_time|monthly_subscription|annual_subscription|
    # licensing|usage_based|service_contract|consulting|
    # digital_download|b2b_contract|education|content|affiliate|ip_licensing|mixed
    market: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    geographic_exposure: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    capital_requirements_band: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown")
    # capital_requirements_band: minimal|low|moderate|high|unknown
    strategic_importance: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    # 0..100, owner-declared
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CommercialAsset(Base, TimestampMixin):
    """One §7 asset that might become a commercial product. The ten
    commercialization questions live in ``assessment``; ownership and
    commercial-use permission are explicit fields because a proposal
    may not proceed without them (§7: never sell or license what the
    owner does not own or may not use commercially)."""

    __tablename__ = "commercial_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # kind: software|application|ai_agent|automation_workflow|
    # research_database|template|educational_material|digital_content|
    # api|algorithm|internal_tool|intellectual_property|other
    owner_business_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    ownership_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unverified")
    # ownership_status: verified_owner|licensed|third_party|unverified
    commercial_use_permitted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assessment: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # the §7 ten questions: demand, productizable, development,
    # maintenance, pricing_model, competitors, distribution, costs, risks
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CommercializationProposal(Base, TimestampMixin):
    """One §7 proposal to turn an asset into a product/business.
    Approval makes it a *proposal the owner endorsed* — the handoff
    then creates a P-03 opportunity (level 0) and P-06's governed
    gates decide creation, exactly like the P-13 venture handoff.
    P-16 never sells, licenses or publishes anything."""

    __tablename__ = "commercialization_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    asset_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pricing_model: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    estimated_cost_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # proposal data only — an estimate
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="proposed", index=True)
    # status: proposed|approved|rejected|handed_off
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    p03_opportunity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CustomerSegment(Base, TimestampMixin):
    """One §8 customer/market expansion record. Segments are
    owner-declared from legitimate data; the system fabricates no
    customer data. ``international_checklist`` carries the §8
    pre-expansion evaluations for geographic segments."""

    __tablename__ = "customer_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    # kind: geographic|customer|product
    business_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    needs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # buying behaviour, pricing sensitivity, retention notes, channels,
    # lifetime value notes — declared, never invented
    international_checklist: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # tax, regulations, payments, currency, consumer protection,
    # privacy, localization, distribution — for geographic segments
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class AllocationRecommendation(Base, TimestampMixin):
    """One §9 capital allocation recommendation. A recommendation is
    advice with an audit trail: proposed amounts (integer minor,
    PROPOSED), the P-07 liquidity snapshot it was computed against,
    the downside case and the approval requirement. Approving one
    moves no money — execution, if the owner chooses it, happens
    through P-07's own governed paths."""

    __tablename__ = "allocation_recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    scenario: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # scenario: conservative|balanced|growth
    business_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    proposed: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {target_kind, target_id, amount_minor, purpose} — PROPOSED only
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_benefits: Mapped[str] = mapped_column(Text, nullable=False, default="")
    downside: Mapped[str] = mapped_column(Text, nullable=False, default="")
    liquidity_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # per-business available capital read from P-07 at creation time,
    # with its timestamp; combined cash is never summed (P-13 rule)
    payback_assumptions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="proposed", index=True)
    # status: proposed|approved|rejected
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class ReinvestmentPlan(Base, TimestampMixin):
    """One §10 profit reinvestment plan for a business. The P-07
    figures it rests on are stored as a *labelled snapshot with its
    timestamp* (the books themselves stay in P-07); the allocation
    shares are configurable and the §10 example percentages are a
    default labelled illustrative, never advice."""

    __tablename__ = "reinvestment_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    figures_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # revenue, direct costs, operating expenses, taxes payable,
    # liabilities, net operating cash flow, distributable cash —
    # read from P-07 at creation; snapshot_at records when
    shares: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {category: percent} — must sum to 100; categories configurable
    amounts_minor: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # derived proposed amounts per category — PROPOSED only
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="proposed", index=True)
    # status: proposed|approved|rejected
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class ExperimentProposal(Base, TimestampMixin):
    """One §11 controlled-experiment proposal, following the
    Constitution's pre-declaration rule: hypothesis, budget ceiling,
    duration, success/failure metrics and stop conditions are all
    declared *before* approval. On approval with a business attached,
    the handoff creates the real experiment in P-08 (which binds it
    to a P-07 budget and enforces the stop-loss); without a business
    it remains a validated design with no execution path."""

    __tablename__ = "experiment_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    target_market: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    business_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    opportunity_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    market_tag: Mapped[str | None] = mapped_column(
        String(80), nullable=True, index=True)
    budget_ceiling_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    # proposal data — the ceiling P-08 will bind to a P-07 budget
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    # The remaining P-08 §9.2 pre-declaration fields, captured here so
    # the handoff can build a complete P-08 declaration without
    # inventing values at handoff time.
    problem: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_customer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False, default="")
    minimum_evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evaluation_schedule: Mapped[str] = mapped_column(Text, nullable=False, default="")
    max_acceptable_loss_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # defaults to the budget ceiling at handoff when unset
    success_metrics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    failure_metrics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_assessment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stop_conditions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="proposed", index=True)
    # status: proposed|approved|rejected|handed_off|evaluated
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    p08_experiment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CompetitorProfile(Base, TimestampMixin):
    """One §13 market-level competitor profile from public or
    authorized sources only. ``source_refs`` is mandatory at the
    service layer: a profile without sources cannot be created.
    (Per-opportunity competitor analysis remains P-03's.)"""

    __tablename__ = "competitor_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    market: Mapped[str] = mapped_column(String(200), nullable=False, default="", index=True)
    market_report_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    products: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    pricing_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    business_model: Mapped[str] = mapped_column(Text, nullable=False, default="")
    positioning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    strengths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    weaknesses: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CountryAssessment(Base, TimestampMixin):
    """One §14 country/region entry assessment. Criteria are scored
    0–100 against transparent, configurable weights stored in
    ``weights`` on the row, so every ranking is reproducible. Data is
    research-entered; the system fabricates no country facts."""

    __tablename__ = "country_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    country: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    criteria_scores: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # demand, purchasing_power, regulation, tax, payments, language,
    # currency_risk, competition, distribution_cost, data_protection,
    # ip_protection — each 0..100 attractiveness
    weights: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_checklist: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="assessed", index=True)
    # status: assessed|shortlisted|deferred|rejected
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class EconomicDecision(Base, TimestampMixin):
    """One §16 structured decision record: the thirteen required
    fields plus the actual outcome when it becomes known. Outcomes
    feed P-09 memory (verified outcomes only) and the §17 pattern
    detection; a past success is never treated as proof a strategy
    will work again."""

    __tablename__ = "economic_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    opportunity_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    financial_assumptions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    expected_benefits: Mapped[str] = mapped_column(Text, nullable=False, default="")
    potential_losses: Mapped[str] = mapped_column(Text, nullable=False, default="")
    alternatives: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required_permissions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {result: success|failure|mixed|abandoned, notes, recorded_at}
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class RiskAssessment(Base, TimestampMixin):
    """One §12 portfolio risk snapshot: the detector findings and
    the ten stress-scenario results computed from live P-07 figures
    at ``computed_at``. Scenario outputs are labelled SIMULATION in
    every response — they are arithmetic on current figures, never
    predictions presented as fact."""

    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    computed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(24), nullable=False, default="all_businesses")
    detectors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    scenarios: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    inputs_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # the per-business P-07 figures the arithmetic ran on, with labels
    recommendations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
