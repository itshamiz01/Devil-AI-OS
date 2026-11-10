"""P-17 vocabularies, settings and catalogues.

Everything here is declared data: channel and source vocabularies
from the prompt, scoring weights (owner-editable through settings),
the external-integration catalogue (every surface honestly
NOT CONFIGURED) and the §12 marketing agent role definitions that
are seeded into the P-04 Agent Factory. No figure in this module is
a measurement; scores computed from these weights are
prioritisation estimates.
"""
from __future__ import annotations


def actor_of(principal) -> str:
    if principal is None:
        return "system"
    return f"{principal.type.value}:{principal.id}"


ENGINE_NAME = ("P-17 Customer Acquisition, Marketing & Revenue "
               "Growth Engine")
SETTINGS_KEY = "growth.settings"

AUTONOMY_LEVELS = (1, 2, 3, 4)
# §24: 1 research only, 2 recommendation, 3 controlled execution of
# approved activities, 4 controlled autonomous growth within
# pre-approved rules. The staging default is 2 (recommendation):
# nothing external happens without owner approval, and in staging
# nothing external exists to execute anyway.

# ------------------------------------------------------------ §4.3 channels
# channel_key -> (category, label)
CHANNELS: dict[str, tuple[str, str]] = {
    "seo": ("organic", "Search engine optimization"),
    "content_marketing": ("organic", "Content marketing"),
    "educational_articles": ("organic", "Educational articles"),
    "youtube": ("organic", "YouTube"),
    "social_organic": ("organic", "Social media (organic)"),
    "community": ("organic", "Community participation"),
    "referral_program": ("organic", "Referral programs"),
    "partnerships_organic": ("organic", "Organic partnerships"),
    "directories": ("organic", "Public directories"),
    "newsletter": ("organic", "Email newsletter (valid consent)"),
    "search_ads": ("paid", "Search advertising"),
    "social_ads": ("paid", "Social advertising"),
    "display_ads": ("paid", "Display advertising"),
    "sponsored_content": ("paid", "Sponsored content"),
    "influencer": ("paid", "Influencer partnerships"),
    "industry_publications": ("paid", "Industry publications"),
    "paid_directories": ("paid", "Paid directories"),
    "business_partnerships": ("direct", "Business partnerships"),
    "outreach_authorized": ("direct", "Authorized business outreach"),
    "sales_conversations": ("direct", "Sales conversations"),
    "networking": ("direct", "Industry networking"),
    "b2b_prospecting": ("direct", "B2B prospecting"),
    "inbound_sales": ("direct", "Inbound sales inquiries"),
    "free_trial": ("product_led", "Free trials"),
    "freemium": ("product_led", "Freemium products"),
    "product_demo": ("product_led", "Product demonstrations"),
    "referral_features": ("product_led", "Referral features"),
    "free_tools": ("product_led", "Free tools"),
    "education_resources": ("product_led", "Educational resources"),
    "other": ("organic", "Other"),
}
CHANNEL_CATEGORIES = ("organic", "paid", "direct", "product_led")
CHANNEL_FACTOR_KEYS = ("audience_fit", "economics",
                       "conversion_potential", "speed", "independence",
                       "feasibility")
DEFAULT_CHANNEL_WEIGHTS = {"audience_fit": 3, "economics": 3,
                           "conversion_potential": 3, "speed": 1,
                           "independence": 1, "feasibility": 2}

# ------------------------------------------------------------ §4.2 ICP
ICP_FACTOR_KEYS = ("product_fit", "demand", "commercial_potential",
                   "acquisition_feasibility", "retention_potential",
                   "strategic_fit")
DEFAULT_ICP_WEIGHTS = {"product_fit": 3, "demand": 3,
                       "commercial_potential": 3,
                       "acquisition_feasibility": 2,
                       "retention_potential": 2, "strategic_fit": 2}
B2B_CRITERIA = ("industry", "company_size", "business_model",
                "operational_challenges", "technology_requirements",
                "purchasing_capacity", "decision_maker_roles",
                "procurement_requirements", "sales_cycle")
B2C_CRITERIA = ("needs", "product_preferences", "motivations",
                "price_sensitivity", "purchase_frequency",
                "expectations", "retention_potential")

EVIDENCE_KINDS = ("verified", "public_research", "assumption",
                  "hypothesis")

# ------------------------------------------------------------ §5 strategies
STRATEGY_APPROACHES = ("educational", "content", "performance",
                       "product_led", "community_led", "partnership",
                       "referral", "b2b", "local", "international")
STRATEGY_KINDS = ("improve", "diversify", "capital_efficiency",
                  "expansion")
# §19 recommendation ordering (the owner's P-16 priority, mechanical):
# improve existing businesses first, then diversify, then capital
# efficiency, then expansion/new ventures last.
RECOMMENDATION_KIND_RANK = {"improve": 0, "diversify": 1,
                            "capital_efficiency": 2, "expansion": 3}
STRATEGY_SECTION_KEYS = (
    "business_positioning", "product_positioning", "target_segments",
    "value_proposition", "brand_messaging", "differentiation",
    "objectives", "channels", "content_strategy", "campaign_strategy",
    "budget_assumptions", "conversion_targets", "performance_metrics",
    "risk_assessment", "execution_timeline")

# ------------------------------------------------------------ §7 campaigns
CAMPAIGN_PURPOSES = ("retention", "conversion", "acquisition",
                     "expansion")
CAMPAIGN_STATUSES = ("idea", "research", "strategy", "draft",
                     "approval_pending", "approved", "scheduled",
                     "active", "paused", "completed", "analyzed",
                     "archived")
CAMPAIGN_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "idea": ("research", "draft", "archived"),
    "research": ("strategy", "draft", "archived"),
    "strategy": ("draft", "archived"),
    "draft": ("approval_pending", "archived"),
    "approval_pending": ("draft", "archived"),  # approval is its own path
    "approved": ("scheduled", "active", "archived"),
    "scheduled": ("active", "paused", "archived"),
    "active": ("paused", "completed", "archived"),
    "paused": ("active", "completed", "archived"),
    "completed": ("analyzed", "archived"),
    "analyzed": ("archived",),
    "archived": (),
}

CONTENT_KINDS = ("blog_article", "landing_copy", "product_description",
                 "email", "newsletter", "ad_copy", "social_caption",
                 "educational", "case_study", "announcement",
                 "sales_material", "social_graphic", "ad_creative",
                 "infographic", "banner", "presentation", "video_script",
                 "video_concept", "voiceover_script", "podcast_script",
                 "other")
REVIEW_SECTIONS = ("fact_check", "brand_consistency",
                   "copyright_licensing", "quality")

# ------------------------------------------------------------ §8 leads
LEAD_SOURCES = ("website_form", "product_registration", "free_trial",
                "inbound_inquiry", "newsletter", "referral",
                "authorized_b2b_prospecting", "public_business_contact",
                "approved_integration", "manual_entry")
# §3 rules 9/10: these source kinds can never be legitimate.
FORBIDDEN_LEAD_SOURCES = ("purchased_list", "purchased_database",
                          "scraped", "scraping", "third_party_database",
                          "leaked", "unknown_bulk")
CONSENT_STATUSES = ("granted", "withdrawn", "unknown", "not_required")
LEAD_STAGES = ("new", "contact_verified", "consent_verified",
               "qualifying", "qualified", "sales_conversation",
               "proposal_sent", "negotiation", "converted", "lost",
               "disqualified")
SUPPRESSION_REASONS = ("opt_out", "unsubscribed", "do_not_contact",
                       "hard_bounce", "complaint")

# ------------------------------------------------------------ §9 lead scoring
LEAD_SCORE_FACTORS = ("product_interest", "requirements_fit",
                      "budget_compatibility", "business_fit",
                      "engagement", "purchase_intent",
                      "decision_authority", "timing")
DEFAULT_LEAD_SCORE_WEIGHTS = {
    "product_interest": 18, "requirements_fit": 14,
    "budget_compatibility": 14, "business_fit": 14, "engagement": 12,
    "purchase_intent": 14, "decision_authority": 7, "timing": 7}
SCORE_BANDS = ((85, "high_priority"), (70, "qualified_prospect"),
               (50, "potential"), (30, "nurture"), (0, "low_priority"))
# §9: sensitive personal attributes are never scoring factors; the
# factor vocabulary above is the complete, closed set.

# ------------------------------------------------------------ §10 sales
SALES_STAGES = ("new", "discovery", "qualification", "demonstration",
                "proposal", "negotiation", "closed_won", "closed_lost")
STAGE_DEFAULT_PROBABILITY = {"new": 5, "discovery": 10,
                             "qualification": 25, "demonstration": 40,
                             "proposal": 60, "negotiation": 80,
                             "closed_won": 100, "closed_lost": 0}

# ------------------------------------------------------------ §11 CRM
CUSTOMER_LIFECYCLES = ("onboarding", "active", "engaged", "at_risk",
                       "dormant", "churned", "renewed")
INTERACTION_KINDS = ("note", "call", "meeting", "email_drafted",
                     "email_queued", "proposal", "demo", "support",
                     "feedback", "renewal", "follow_up", "other")

# ------------------------------------------------------------ §13 funnel
FUNNEL_STAGES = ("awareness", "interest", "consideration", "intent",
                 "conversion", "onboarding", "retention", "expansion")

# ------------------------------------------------------------ §15 SEO
SEO_KINDS = ("keyword_set", "technical_audit", "content_plan",
             "performance_snapshot")
SEO_SOURCES = ("declared", "imported", "owner_attested")

# ------------------------------------------------------------ §16 comms
COMMUNICATION_KINDS = ("welcome", "onboarding", "transactional",
                       "newsletter", "educational", "product_update",
                       "renewal_reminder", "feedback_request",
                       "support_follow_up", "sales_outreach")
# False-urgency / deceptive phrasing patterns refused in subjects and
# bodies (§16 + §3 rule 12). Lowercase substring match; documented
# in P17_SECURITY_REVIEW.md as a guardrail, not a censor.
DECEPTIVE_PATTERNS = ("act now or lose", "guaranteed results",
                      "100% guaranteed", "you have won", "free money",
                      "risk-free profit", "expires in 5 minutes",
                      "final notice (fake)", "urgent!!!")

# ------------------------------------------------------------ §18 partners
PARTNERSHIP_KINDS = ("strategic", "referral", "affiliate", "reseller",
                     "distribution", "integration", "co_marketing",
                     "industry_collaboration")
PARTNERSHIP_STAGES = ("discovered", "researched", "qualified",
                      "proposal_drafted", "approval_pending",
                      "negotiation", "agreement_approved", "active",
                      "performance_review", "closed")

# ------------------------------------------------------------ §19/§21 money ties
CAC_EXPENSE_CATEGORIES = ("marketing", "advertising")
CAMPAIGN_PROJECT_REF_PREFIX = "p17-campaign:"
ATTRIBUTION_CHANNEL_PREFIX = "p17-"
PARTNER_CHANNEL_PREFIX = "partner-"

# ------------------------------------------------------------ integrations
# Every external marketing surface: honestly not configured. Building
# a connector is an owner-configuration act (credentials, platform
# approval), never something the engine simulates.
INTEGRATIONS: list[dict] = [
    {"key": "email_transport", "label": "Email transport (SMTP/provider)",
     "needed_for": "sending any customer communication"},
    {"key": "search_ads", "label": "Search advertising platform",
     "needed_for": "paid search campaigns"},
    {"key": "social_ads", "label": "Social advertising platform",
     "needed_for": "paid social campaigns"},
    {"key": "social_publishing", "label": "Social publishing",
     "needed_for": "publishing social content"},
    {"key": "search_console", "label": "Search console / SEO data",
     "needed_for": "measured SEO performance"},
    {"key": "web_analytics", "label": "Web analytics",
     "needed_for": "measured funnel traffic"},
    {"key": "video_platform", "label": "Video platform",
     "needed_for": "publishing video content"},
    {"key": "affiliate_network", "label": "Affiliate network",
     "needed_for": "tracked affiliate payouts"},
]

# ------------------------------------------------------------ §12 agents
_READ_CAPS = ["internal_reasoning", "internal_database_read", "memory_read"]
_DRAFT_CAPS = ["internal_reasoning", "memory_read"]
_WRITE_CAPS = ["internal_reasoning", "internal_database_read",
               "internal_database_write", "memory_read"]
_HANDLERS = ["core.echo_check", "core.health_snapshot", "core.noop"]

# (template name, role, agent_type, capabilities, output fields,
#  mission, instruction, responsibility)
AGENT_ROLES: list[dict] = [
    {"name": "Market Research Agent", "role": "p17_market_research_agent",
     "agent_type": "intelligence", "capabilities": _READ_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Research customer markets for assigned businesses from recorded evidence.",
     "instruction": "You are a market research agent. Use only recorded evidence and authorized public-source notes entered by the owner; cite evidence references; never invent market data.",
     "responsibility": "Produce evidence-backed customer market research."},
    {"name": "Audience Research Agent", "role": "p17_audience_research_agent",
     "agent_type": "intelligence", "capabilities": _READ_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Draft customer personas and audience findings with honesty-labelled evidence.",
     "instruction": "You are an audience research agent. Label every claim verified, public research, assumption or hypothesis; never present an assumption as a fact.",
     "responsibility": "Draft personas with labelled evidence."},
    {"name": "Marketing Strategy Agent", "role": "p17_marketing_strategy_agent",
     "agent_type": "strategy", "capabilities": _READ_CAPS,
     "outputs": ["summary", "recommendation", "risks"],
     "mission": "Draft marketing strategies for owner approval.",
     "instruction": "You are a marketing strategy agent. Strategies are proposals for the owner, never decisions; respect the profitability-first ordering; never promise results.",
     "responsibility": "Draft marketing strategies with risks and assumptions."},
    {"name": "SEO Research Agent", "role": "p17_seo_research_agent",
     "agent_type": "intelligence", "capabilities": _READ_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Research search demand and content gaps from recorded SEO data.",
     "instruction": "You are an SEO research agent. Work from recorded keyword and audit data only; state when no measured search data exists; never use manipulative SEO tactics.",
     "responsibility": "Produce SEO research from recorded data."},
    {"name": "Content Production Agent", "role": "p17_content_production_agent",
     "agent_type": "production", "capabilities": _DRAFT_CAPS,
     "outputs": ["summary", "draft"],
     "mission": "Draft marketing content from approved briefs for human review.",
     "instruction": "You are a content production agent. Produce drafts only; follow the business's own brand profile and prohibited claims; never claim publication.",
     "responsibility": "Draft content from briefs."},
    {"name": "Social Media Marketing Agent", "role": "p17_social_media_agent",
     "agent_type": "production", "capabilities": _DRAFT_CAPS,
     "outputs": ["summary", "draft"],
     "mission": "Draft social content for approved campaigns.",
     "instruction": "You are a social media marketing agent. Drafts only — no platform is connected and nothing you produce is posted; never fabricate engagement.",
     "responsibility": "Draft social content for review."},
    {"name": "Campaign Management Agent", "role": "p17_campaign_management_agent",
     "agent_type": "operations", "capabilities": _READ_CAPS,
     "outputs": ["summary", "recommendation"],
     "mission": "Monitor campaign state and draft campaign changes for approval.",
     "instruction": "You are a campaign management agent. Report spend and results only from P-07 records; recommend pauses where the data shows waste; never increase a budget.",
     "responsibility": "Monitor campaigns and draft changes."},
    {"name": "Lead Generation Agent", "role": "p17_lead_generation_agent",
     "agent_type": "operations", "capabilities": _READ_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Identify lead sources from authorized channels recorded in the system.",
     "instruction": "You are a lead generation agent. Only authorized sources exist for you: no purchased lists, no scraping, no private data. Report sources, never invent contacts.",
     "responsibility": "Identify authorized lead sources."},
    {"name": "Lead Qualification Agent", "role": "p17_lead_qualification_agent",
     "agent_type": "operations", "capabilities": _READ_CAPS,
     "outputs": ["summary", "score_factors"],
     "mission": "Explain lead scores and qualification state from recorded factors.",
     "instruction": "You are a lead qualification agent. A score is a prioritisation estimate, not a purchase guarantee; explain factors; never use sensitive personal attributes.",
     "responsibility": "Explain lead qualification from recorded factors."},
    {"name": "Sales Intelligence Agent", "role": "p17_sales_intelligence_agent",
     "agent_type": "intelligence", "capabilities": _READ_CAPS,
     "outputs": ["summary", "recommendation"],
     "mission": "Prepare sales conversation briefs and objection analysis from recorded interactions.",
     "instruction": "You are a sales intelligence agent. Prepare briefs from recorded data only; proposals you draft require owner approval before anything is sent or committed.",
     "responsibility": "Prepare sales briefs from recorded interactions."},
    {"name": "CRM Management Agent", "role": "p17_crm_management_agent",
     "agent_type": "operations", "capabilities": _WRITE_CAPS,
     "outputs": ["summary"],
     "mission": "Maintain authorized CRM records within one business at a time.",
     "instruction": "You are a CRM management agent. Customer data never crosses businesses; update only records you are explicitly assigned; respect consent and suppression absolutely.",
     "responsibility": "Maintain CRM records under governance."},
    {"name": "Email Marketing Agent", "role": "p17_email_marketing_agent",
     "agent_type": "production", "capabilities": _DRAFT_CAPS,
     "outputs": ["summary", "draft"],
     "mission": "Draft email templates and sequences for approval.",
     "instruction": "You are an email marketing agent. Drafts only; no transport is configured and nothing is sent; no deceptive subjects, no false urgency; consent governs every recipient.",
     "responsibility": "Draft email content for approval."},
    {"name": "Conversion Optimization Agent", "role": "p17_conversion_optimization_agent",
     "agent_type": "strategy", "capabilities": _READ_CAPS,
     "outputs": ["summary", "recommendation"],
     "mission": "Analyse funnel data and draft pre-declared experiments.",
     "instruction": "You are a conversion optimization agent. Never declare a winner on insufficient data; every experiment needs a hypothesis, a primary metric and a minimum evaluation before it runs.",
     "responsibility": "Analyse funnels and draft experiments."},
    {"name": "Customer Retention Agent", "role": "p17_customer_retention_agent",
     "agent_type": "operations", "capabilities": _READ_CAPS,
     "outputs": ["summary", "recommendation"],
     "mission": "Identify at-risk customers from recorded health factors and recommend care actions.",
     "instruction": "You are a customer retention agent. Recommend onboarding, education and support — never manipulative retention tactics; health scores are estimates with stated factors.",
     "responsibility": "Flag at-risk customers with recommended actions."},
    {"name": "Marketing Analytics Agent", "role": "p17_marketing_analytics_agent",
     "agent_type": "intelligence", "capabilities": _READ_CAPS,
     "outputs": ["summary", "methodology"],
     "mission": "Compute growth analytics from P-07 verified figures and recorded growth state.",
     "instruction": "You are a marketing analytics agent. Distinguish verified, attributed and estimated figures in every output; attribution is not causation; projected revenue is never realized revenue.",
     "responsibility": "Produce labelled growth analytics."},
    {"name": "Partnership Research Agent", "role": "p17_partnership_research_agent",
     "agent_type": "intelligence", "capabilities": _READ_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Research partnership candidates from recorded, sourced information.",
     "instruction": "You are a partnership research agent. Evaluate fit from recorded evidence; you never contact partners and never enter agreements.",
     "responsibility": "Research partnership candidates."},
    {"name": "Brand Compliance Agent", "role": "p17_brand_compliance_agent",
     "agent_type": "operations", "capabilities": _READ_CAPS,
     "outputs": ["summary", "violations"],
     "mission": "Check content against the owning business's brand profile and prohibited claims.",
     "instruction": "You are a brand compliance agent. Check only against the owning business's own brand profile; brands never mix; flag deceptive or prohibited claims.",
     "responsibility": "Review content for brand compliance."},
]

DEFAULT_SETTINGS = {
    "autonomy_level": 2,
    "all_campaigns_paused": False,
    "communications_stopped": False,
    "outreach_suspended": False,
    "marketing_spend_frozen": False,
    "lead_score_weights": dict(DEFAULT_LEAD_SCORE_WEIGHTS),
    "icp_weights": dict(DEFAULT_ICP_WEIGHTS),
    "channel_weights": dict(DEFAULT_CHANNEL_WEIGHTS),
    "comm_frequency_limit_per_30d": 4,
    "cac_expense_categories": list(CAC_EXPENSE_CATEGORIES),
}
