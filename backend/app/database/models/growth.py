"""SQLAlchemy models for the P-17 Customer Acquisition, Marketing &
Revenue Growth Engine tables.

One additive migration creates these tables; no P-01..P-16 table is
altered. P-17 is the commercial growth layer over P-06 (businesses),
P-07 (money), P-08 (experiments), P-13 (portfolio) and P-16 (economy
strategy + the owner's profitability gate), so its tables hold only
state no earlier phase owns: brand profiles, customer research
(personas, ICPs, channel evaluations), marketing strategies,
campaigns, content, leads and their suppressions, the deal-level
sales pipeline, the CRM layer, interactions, funnel events, growth
experiment designs, SEO records, communication templates/messages
and partnerships.

Discipline carried from P-07/P-13/P-16:

* **No ledger, balance or account columns.** Amount fields are a
  budget *ceiling* (proposal data), an *estimated* deal value
  (labelled ESTIMATE in every response) or recorded terms. Actual
  spend is read live from P-07 expenses (category marketing /
  advertising, ``project_ref = "p17-campaign:<id>"``); attributed
  revenue is read live from P-07 revenue metrics by channel tag.
  A named test proves P-07's consolidated output is byte-equal
  before and after every P-17 write flow.
* **No execution state.** Approvals are P-01 records (only the id
  is referenced), experiments execute in P-08 (only the id is
  referenced), businesses are created by P-06 (never here), and no
  message is ever recorded as sent — no transport is configured.
* **Customer data is per-business.** Leads and customers carry a
  business_id on every row and a dedupe key unique per business;
  no code path copies a customer from one business to another.
* Cross-engine references are plain indexed ids, so the migration
  cycle never entangles P-17 with earlier tables' lifecycles.
"""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class BrandProfile(Base, TimestampMixin):
    """One §6 brand profile per business. Brand identity never
    crosses businesses: the profile is keyed by business_id and
    content review checks against *this* business's prohibited
    claims only."""

    __tablename__ = "growth_brand_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True)
    brand_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    identity: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tone_of_voice: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    colors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    typography: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    logo_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    messaging_guidelines: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prohibited_claims: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    product_information: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assets: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CustomerPersona(Base, TimestampMixin):
    """One §4.1 customer persona for a business. Every persona
    carries its evidence with an honesty kind per item —
    verified | public_research | assumption | hypothesis — so
    research is never silently upgraded into fact."""

    __tablename__ = "customer_personas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    segment: Mapped[str] = mapped_column(String(200), nullable=False)
    needs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    problems: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    motivations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    budget_sensitivity: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unknown")
    # budget_sensitivity: low|medium|high|unknown
    product_category: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    objections: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    discovery_channels: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    buying_journey: Mapped[str] = mapped_column(Text, nullable=False, default="")
    demographics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # only lawfully available, relevant, owner-declared demographics
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # [{summary, kind: verified|public_research|assumption|hypothesis,
    #   source_ref}]
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class IdealCustomerProfile(Base, TimestampMixin):
    """One §4.2 ICP for a business, B2B or B2C. Factor scores are
    declared attractiveness inputs; the priority score is computed
    deterministically from them (scoring.py) and is a
    prioritisation estimate, never a demand measurement."""

    __tablename__ = "ideal_customer_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    # kind: b2b|b2c
    segment: Mapped[str] = mapped_column(String(200), nullable=False)
    criteria: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # B2B: industry, company_size, business_model, challenges,
    # technology, purchasing_capacity, decision_makers, procurement,
    # sales_cycle. B2C: needs, preferences, motivations,
    # price_sensitivity, frequency, expectations, retention_potential
    factor_scores: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # product_fit, demand, commercial_potential, acquisition_feasibility,
    # retention_potential, strategic_fit — each 0..100
    priority_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class ChannelEvaluation(Base, TimestampMixin):
    """One §4.3 acquisition-channel evaluation for a business. The
    evaluation is declared research (estimates labelled as such);
    the expected-value score is computed from it. No channel here
    implies a connected platform — see the integrations read model
    (every external surface is NOT CONFIGURED)."""

    __tablename__ = "growth_channel_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    channel_key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    # channel_key: seo|content_marketing|youtube|social_organic|
    # community|referral|partnerships_organic|directories|
    # newsletter|search_ads|social_ads|display_ads|sponsored_content|
    # influencer|industry_publications|paid_directories|
    # business_partnerships|outreach_authorized|sales_conversations|
    # networking|b2b_prospecting|inbound_sales|free_trial|freemium|
    # product_demo|referral_features|free_tools|education_resources|other
    category: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # category: organic|paid|direct|product_led
    evaluation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # target_audience, estimated_reach, estimated_acquisition_cost,
    # conversion_potential, time_to_results, competition,
    # platform_dependency, compliance_requirements, workload —
    # declared estimates, labelled ESTIMATE in responses
    factor_scores: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # audience_fit, economics, conversion_potential, speed,
    # independence, feasibility — each 0..100
    expected_value_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="candidate", index=True)
    # status: candidate|recommended|active|rejected
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class MarketingStrategy(Base, TimestampMixin):
    """One §5 marketing strategy for a business — the fifteen
    required sections held as structured fields. Approval is a
    governed owner decision (P-01 hash-bound approval id stored);
    expansion-kind strategies additionally respect the P-16
    profitability gate, with the per-item owner override recorded
    on the row."""

    __tablename__ = "marketing_strategies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    approach: Mapped[str] = mapped_column(String(32), nullable=False, default="content")
    # approach: educational|content|performance|product_led|
    # community_led|partnership|referral|b2b|local|international
    kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default="improve", index=True)
    # kind: improve|diversify|capital_efficiency|expansion — the
    # owner's mechanical ordering categories (P-16)
    sections: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # business_positioning, product_positioning, target_segments,
    # value_proposition, brand_messaging, differentiation,
    # objectives, channels, content_strategy, campaign_strategy,
    # budget_assumptions, conversion_targets, performance_metrics,
    # risk_assessment, execution_timeline
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", index=True)
    # status: draft|proposed|approved|rejected|archived
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    gate_override: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {by, reason, at} — owner-only profitability-gate override
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class MarketingCampaign(Base, TimestampMixin):
    """One §7 campaign. ``budget_ceiling_minor`` is a ceiling the
    owner approved — proposal data, never spend. Actual spend is
    read from P-07 (expenses tagged with this campaign's
    project_ref); attributed revenue is read from P-07 revenue by
    ``attribution_channel``. ``purpose = expansion`` campaigns are
    profitability-gated at approval (P-16)."""

    __tablename__ = "marketing_campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # short slug, unique per business; attribution_channel = p17-<code>
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    purpose: Mapped[str] = mapped_column(
        String(24), nullable=False, default="acquisition", index=True)
    # purpose: retention|conversion|acquisition|expansion
    strategy_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    channel_evaluation_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    channel_key: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    target_audience: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {persona_ids, icp_ids, segment description}
    start_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    budget_ceiling_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    expected_results: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # declared expectations — labelled ESTIMATE, never results
    creative_asset_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    landing_page: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    conversion_event: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="idea", index=True)
    # status: idea|research|strategy|draft|approval_pending|approved|
    # scheduled|active|paused|completed|analyzed|archived
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    gate_override: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    auto_pause_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {enabled, max_cac_minor, min_conversions, max_spend_minor} —
    # approved with the campaign; enforced only at autonomy level 4
    spend_request_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # P-07 spending-request ids prepared from this campaign
    paused_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class ContentItem(Base, TimestampMixin):
    """One §6 content item in the governed production workflow.
    Review state (fact check, brand consistency, copyright /
    licensing, quality) is recorded explicitly; an item whose body
    contains one of its own business's prohibited claims fails the
    brand check mechanically. Release records an owner-attested
    external reference — the system publishes nothing itself."""

    __tablename__ = "content_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # kind: blog_article|landing_copy|product_description|email|
    # newsletter|ad_copy|social_caption|educational|case_study|
    # announcement|sales_material|social_graphic|ad_creative|
    # infographic|banner|presentation|video_script|video_concept|
    # voiceover_script|podcast_script|other
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    brief: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {objective, audience, key_points}
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", index=True)
    # status: draft|in_review|approved|scheduled|released|archived
    review: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {fact_check: {status, notes}, brand_consistency: {...},
    #  copyright_licensing: {...}, quality: {...}} each pass|fail|pending
    scheduled_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    release_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # owner-attested external reference recorded at release
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class GrowthLead(Base, TimestampMixin):
    """One §8 lead. Contact data is owner/agent-declared from
    legitimate sources only (source kind is validated against the
    authorized vocabulary — purchased/scraped sources are refused
    at the service layer). ``dedupe_key`` is the normalized contact
    identity, unique per business, so a lead can never be imported
    twice for the same business. Scores are computed with their
    factor explanation stored alongside (§9)."""

    __tablename__ = "growth_leads"
    __table_args__ = ()

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    contact: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {name, email, phone, company, role} — declared data
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # source_kind: website_form|product_registration|free_trial|
    # inbound_inquiry|newsletter|referral|authorized_b2b_prospecting|
    # public_business_contact|approved_integration|manual_entry
    source_channel: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    consent_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unknown", index=True)
    # consent_status: granted|withdrawn|unknown|not_required
    lawful_basis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    segment: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    interest: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_factors: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    score_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default="new", index=True)
    # stage: new|contact_verified|consent_verified|qualifying|
    # qualified|sales_conversation|proposal_sent|negotiation|
    # converted|lost|disqualified
    assigned_to: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    converted_customer_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class LeadSuppression(Base, TimestampMixin):
    """One §8 suppression record: a contact identity that must
    never be contacted for this business again. Checked at lead
    import (a suppressed identity is refused/flagged) and at
    communication queue time (hard refusal)."""

    __tablename__ = "lead_suppressions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # reason: opt_out|unsubscribed|do_not_contact|hard_bounce|complaint
    source: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class SalesOpportunity(Base, TimestampMixin):
    """One §10 deal-level sales opportunity. NOT a P-03 business
    opportunity and NOT a P-16 economic opportunity: this is one
    prospective deal with one lead for one business.
    ``estimated_value_minor`` is an ESTIMATE, labelled as such;
    realized revenue exists only in P-07."""

    __tablename__ = "sales_opportunities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    product: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    estimated_value_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    stage: Mapped[str] = mapped_column(
        String(24), nullable=False, default="new", index=True)
    # stage: new|discovery|qualification|demonstration|proposal|
    # negotiation|closed_won|closed_lost
    probability: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 0..100 declared estimate
    expected_close_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    assigned_to: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    next_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    lost_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CrmCustomer(Base, TimestampMixin):
    """One §11 CRM customer of exactly one business. A customer of
    business A is never a customer of business B unless separately
    created there through a governed path with its own basis (§11)
    — no copy function exists. Purchase facts are read live from
    P-07 by ``p07_customer_ref``; this row holds relationship
    state only."""

    __tablename__ = "crm_customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    contact: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    p07_customer_ref: Mapped[str | None] = mapped_column(
        String(200), nullable=True, index=True)
    segment: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    lifecycle_stage: Mapped[str] = mapped_column(
        String(24), nullable=False, default="onboarding", index=True)
    # lifecycle_stage: onboarding|active|engaged|at_risk|dormant|
    # churned|renewed
    consent_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unknown")
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {communication_opt_in: bool, channels: [...], notes}
    acquisition_campaign_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True)
    acquisition_channel: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    source_lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    health_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_factors: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    health_computed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class GrowthInteraction(Base, TimestampMixin):
    """One §8/§10/§11 interaction record for a lead, customer,
    sales opportunity or partnership. Append-only history; the
    record of *what happened*, never a claim that an external
    message was delivered."""

    __tablename__ = "growth_interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    subject_kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    # subject_kind: lead|customer|sales_opportunity|partnership
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # kind: note|call|meeting|email_drafted|email_queued|proposal|
    # demo|support|feedback|renewal|follow_up|other
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outcome: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class FunnelEvent(Base, TimestampMixin):
    """One §13 funnel measurement: a stage count for a business
    over a period, from a declared source. Declared counts are
    labelled DECLARED in every response and are kept distinct from
    the system-counted anchors (leads, conversions, P-07 records)
    the funnel summary computes alongside them."""

    __tablename__ = "funnel_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    # stage: awareness|interest|consideration|intent|conversion|
    # onboarding|retention|expansion
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    period_start: Mapped[str] = mapped_column(String(10), nullable=False)
    period_end: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="declared")
    # source: declared|imported — always labelled, never system-measured
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class GrowthExperiment(Base, TimestampMixin):
    """One §14 A/B / conversion experiment design. Following the
    Constitution's pre-declaration rule (via P-16's precedent), the
    design is declared in full before approval; on approval the
    handoff creates the real experiment in P-08, which binds a
    P-07 budget and enforces the stop-loss. Conclusions are only
    recorded when the declared minimum evaluation is met —
    otherwise the result stays INSUFFICIENT_DATA."""

    __tablename__ = "growth_experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    control_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    test_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    primary_metric: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    minimum_evaluation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {min_observations_per_variant: int, notes}
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    budget_ceiling_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_acceptable_loss_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", index=True)
    # status: draft|approved|handed_off|concluded|rejected
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    p08_experiment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    observations: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {control: {n, successes}, test: {n, successes}} — declared results
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {verdict: control|test|insufficient_data, rates, recommendation}
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class SeoRecord(Base, TimestampMixin):
    """One §15 SEO record for a business: a keyword set, a technical
    audit, a content plan or a performance snapshot. Every record
    carries a mandatory source label — the system has no crawler
    and no search feed, so nothing here is system-measured."""

    __tablename__ = "seo_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # kind: keyword_set|technical_audit|content_plan|performance_snapshot
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="declared")
    # source: declared|imported|owner_attested
    period_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    period_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CommunicationTemplate(Base, TimestampMixin):
    """One §16 communication template. Bodies are drafts until
    approved; approval is a governed owner decision. Deceptive
    subject lines and false urgency are refused at the service
    layer via the business's prohibited-claims check plus the
    template review fields."""

    __tablename__ = "communication_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # kind: welcome|onboarding|transactional|newsletter|educational|
    # product_update|renewal_reminder|feedback_request|
    # support_follow_up|sales_outreach
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", index=True)
    # status: draft|approved|archived
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CommunicationMessage(Base, TimestampMixin):
    """One §16 prepared communication to one recipient. Queueing
    enforces consent, suppression and frequency rules; dispatch is
    honestly blocked — no email transport is configured — so the
    terminal states are ``dispatch_blocked`` (with the reason) or
    a refusal. No row is ever marked sent or delivered."""

    __tablename__ = "communication_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    recipient_kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # recipient_kind: lead|customer
    recipient_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(24), nullable=False, default="email")
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="drafted", index=True)
    # status: drafted|queued|dispatch_blocked|refused|cancelled
    refusal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatch_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class Partnership(Base, TimestampMixin):
    """One §18 partnership pipeline record. Stage movement is
    governed; ``agreement_approved`` is an internal owner decision
    record only — the system never enters a binding agreement,
    signs anything, or commits revenue share. Terms are text."""

    __tablename__ = "partnerships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    partner_name: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # kind: strategic|referral|affiliate|reseller|distribution|
    # integration|co_marketing|industry_collaboration
    stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default="discovered", index=True)
    # stage: discovered|researched|qualified|proposal_drafted|
    # approval_pending|negotiation|agreement_approved|active|
    # performance_review|closed
    evaluation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # strategic_fit, audience_compatibility, commercial_value,
    # reputation, legal_requirements, revenue_share_structure,
    # operational_dependencies, brand_risks
    contact_proposal: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    referral_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    # referral attribution joins P-07 revenue by channel tag
    # "partner-<referral_code>" when the owner records it there
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
