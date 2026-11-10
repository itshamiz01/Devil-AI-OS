"""P-16 AI Economy Expansion Engine constants.

Everything owner-governed lives in DEFAULT_SETTINGS (seeded into
SystemConfig under SETTINGS_KEY, the P-13/P-15 pattern): the §18
autonomy level, the pause/freeze flags, the evidence-gate thresholds,
the §4.3 scoring weights, the country-ranking weights and the §10
reinvestment default shares. The code constants below are the
vocabularies (stage names, kinds, classifications) — changing them
would be a schema-level change, so they are not settings.
"""
from __future__ import annotations

SETTINGS_KEY = "economy.settings"

ENGINE_NAME = "P-16 AI Economy Expansion Engine"

# ------------------------------------------------------------- §4.1
MARKET_CLASSIFICATIONS = (
    "established", "growing", "emerging", "experimental",
    "declining", "speculative",
)

MARKET_SECTORS = (
    "software_saas", "ai_services", "digital_products", "content_media",
    "education", "ecommerce", "automation", "professional_services",
    "subscriptions", "licensing_ip", "b2b_services", "b2c_services",
    "affiliate", "other",
)

# ------------------------------------------------------------- §4.2
OPPORTUNITY_STAGES = (
    "discovered", "under_research", "market_validation",
    "financial_evaluation", "risk_assessment", "approval_pending",
    "experimentation", "launch_approved", "active", "rejected",
    "archived",
)

# Forward movement is along this chain; rejected/archived are exits
# reachable from any non-terminal stage; no stage may be skipped over
# a gate boundary (approval_pending, experimentation) without the
# service's gate checks.
OPPORTUNITY_CHAIN = OPPORTUNITY_STAGES[:8]
OPPORTUNITY_TERMINAL = ("active", "rejected", "archived")

OPPORTUNITY_KINDS = (
    "new_business", "existing_business_expansion", "new_revenue_stream",
    "asset_commercialization", "market_entry", "automation", "other",
)

OPPORTUNITY_SOURCES = ("manual", "detector", "p03_link", "commercialization")

# ------------------------------------------------------------- §4.3
# Prompt weights, as settings so the owner can re-govern them; the
# risk factor is entered as a risk LEVEL and inverted before
# weighting (higher risk => lower attractiveness).
FACTOR_KEYS = (
    "market_demand", "profitability_potential", "competitive_advantage",
    "scalability", "capital_efficiency", "operational_feasibility",
    "revenue_diversification", "strategic_compatibility", "risk_profile",
)

DEFAULT_FACTOR_WEIGHTS = {
    "market_demand": 20, "profitability_potential": 15,
    "competitive_advantage": 15, "scalability": 15,
    "capital_efficiency": 10, "operational_feasibility": 10,
    "revenue_diversification": 5, "strategic_compatibility": 5,
    "risk_profile": 5,
}

SCORE_BANDS = (
    (90, "strategic_candidate"),
    (75, "strong_candidate"),
    (60, "controlled_experimentation"),
    (40, "research_further"),
    (0, "reject_or_archive"),
)

# ------------------------------------------------------------- §4.4
STRATEGY_HORIZONS = ("short", "medium", "long")

STRATEGY_KINDS = (
    "improve_existing", "new_revenue_stream", "diversification",
    "capital_efficiency", "new_business", "market_entry",
    "commercialization",
)

# Kinds the owner's profitability gate blocks while the gate is
# closed: creating or entering *new* businesses/markets before the
# existing portfolio is profitable.
GATE_BLOCKED_STRATEGY_KINDS = ("new_business", "market_entry")
GATE_BLOCKED_OPPORTUNITY_KINDS = ("new_business", "market_entry")

# The owner's priority order, used to sort strategic recommendations:
# profitability of what exists, then diversification of what exists,
# then capital efficiency, then new ventures.
RECOMMENDATION_PRIORITY = {
    "improve_existing": 0, "diversification": 1,
    "new_revenue_stream": 1, "capital_efficiency": 2,
    "commercialization": 3, "market_entry": 4, "new_business": 4,
}

# ------------------------------------------------------------- §5/§6
# §5.2 lifecycle labels, derived over P-06's machine + P-08 overlay
# by P-13; P-16 reads P-13's derivation and never stores its own.
LIFECYCLE_LABELS = (
    "idea", "validation", "launch", "early_growth",
    "established_operation", "expansion", "maturity",
    "restructuring", "exit_or_closure",
)

REVENUE_MODELS = (
    "one_time", "monthly_subscription", "annual_subscription",
    "licensing", "usage_based", "service_contract", "consulting",
    "digital_download", "b2b_contract", "education", "content",
    "affiliate", "ip_licensing", "mixed",
)

ASSET_KINDS = (
    "software", "application", "ai_agent", "automation_workflow",
    "research_database", "template", "educational_material",
    "digital_content", "api", "algorithm", "internal_tool",
    "intellectual_property", "other",
)

OWNERSHIP_STATES = ("verified_owner", "licensed", "third_party", "unverified")

SEGMENT_KINDS = ("geographic", "customer", "product")

# ------------------------------------------------------------- §9/§10
ALLOCATION_SCENARIOS = ("conservative", "balanced", "growth")

# §10's illustrative example, shipped as the *default* only and
# labelled illustrative in every response — never advice.
DEFAULT_REINVESTMENT_SHARES = {
    "business_reinvestment": 40, "cash_reserves": 25,
    "new_business_experiments": 15, "infrastructure_technology": 10,
    "owner_distribution": 10,
}

# ------------------------------------------------------------- §14
COUNTRY_CRITERIA = (
    "demand", "purchasing_power", "regulation", "tax", "payments",
    "language", "currency_risk", "competition", "distribution_cost",
    "data_protection", "ip_protection",
)

DEFAULT_COUNTRY_WEIGHTS = {key: 1 for key in COUNTRY_CRITERIA}
DEFAULT_COUNTRY_WEIGHTS["demand"] = 2  # demand counts double by default

# ------------------------------------------------------------- §18
AUTONOMY_LEVELS = (1, 2, 3, 4)
DEFAULT_AUTONOMY_LEVEL = 2  # Recommendation

# P-01 approval actions (hash-bound bindings)
APPROVAL_ACTION_ALLOCATION = "economy.allocation"
APPROVAL_ACTION_REINVESTMENT = "economy.reinvestment"
APPROVAL_ACTION_EXPERIMENT = "economy.experiment"
APPROVAL_ACTION_STRATEGY = "economy.strategy"

# ------------------------------------------------------------- settings
DEFAULT_SETTINGS = {
    "autonomy_level": DEFAULT_AUTONOMY_LEVEL,
    "expansion_paused": False,
    "capital_commitments_frozen": False,
    "evidence_gate_min_confidence": 50,
    "evidence_gate_min_items": 2,
    # share of verified collected revenue (bps) above which a single
    # business / channel / product is flagged as concentration
    "concentration_threshold_bps": 6000,
    "factor_weights": dict(DEFAULT_FACTOR_WEIGHTS),
    "country_weights": dict(DEFAULT_COUNTRY_WEIGHTS),
    "reinvestment_shares": dict(DEFAULT_REINVESTMENT_SHARES),
}


def actor_of(principal) -> str:
    if principal is None:
        return "system:economy-engine"
    return f"{principal.type.value}:{principal.id}"
