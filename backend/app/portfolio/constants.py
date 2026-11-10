"""P-13 constants: owner-governed settings, governed status sets,
the §4→P-06/P-08 lifecycle derivation, data-category grant rules
(§8/§20) and deterministic detector vocabularies (§6/§7).

Nothing here is a financial or security authority: thresholds are
owner-governed configuration (system_config), grant rules fail
closed, and every category list is a closed set — an unknown
category is never grantable, shareable or readable across
businesses.
"""
from __future__ import annotations

SETTINGS_KEY = "portfolio.settings"


def actor_of(principal) -> str:
    """Audit/actor string for a principal (lives here to stay
    import-cycle-free across the portfolio mixins)."""
    if principal is None:
        return "system:portfolio-engine"
    return f"{principal.type.value}:{principal.id}"

DEFAULT_SETTINGS: dict = {
    # A single business (or channel) holding more than this share of
    # verified collected revenue is a concentration finding (§12).
    "concentration_threshold_bps": 6000,
    # Anti-monopolization: one business may hold at most this share
    # of any shared resource kind's capacity (§10).
    "business_share_cap_bps": 5000,
    # Configured shared-infrastructure capacities (§10). These are
    # owner-declared capacities for the single-machine deployment,
    # not measured hardware telemetry — views label them as such.
    "capacities": {
        "inference_slots": 4,
        "api_quota_units": 1000,
        "storage_mb": 10240,
        "service_capacity_units": 100,
        "agent_hours": 200,
    },
    "version": "portfolio-settings-v1",
}

# ---------------------------------------------------------------- §4
# Portfolio stage derivation. The ONLY lifecycle authority is P-06's
# state machine; P-08's overlay is a health reading on top of it.
# This mapping produces a display label — it stores nothing and
# transitions nothing (audit §1.2).
P06_STAGE = {
    "PROPOSED": "IDEA",
    "ELIGIBILITY_REVIEW": "VALIDATING",
    "BLUEPRINTING": "BUILDING",
    "BLUEPRINT_READY": "APPROVED",
    "APPROVAL_PENDING": "APPROVED",
    "PRODUCT_PLANNING": "BUILDING",
    "IN_DEVELOPMENT": "BUILDING",
    "INTERNAL_TESTING": "BUILDING",
    "DISTRIBUTION_PREPARATION": "BUILDING",
    "LAUNCH_REVIEW": "LAUNCHING",
    "READY_FOR_LAUNCH": "LAUNCHING",
    "LAUNCH_APPROVAL_PENDING": "LAUNCHING",
    "LAUNCHING": "LAUNCHING",
    "OPERATIONAL": "OPERATIONAL",
    "PAUSED": "PAUSED",
    "BLOCKED": "BLOCKED",
    "FAILED": "CLOSING",
    "ARCHIVED": "ARCHIVED",
}

# P-08 overlay readings refine the operational end of the scale.
OVERLAY_STAGE = {
    "VALIDATING": "VALIDATING",
    "APPROVED": "APPROVED",
    "BUILDING": "BUILDING",
    "LAUNCH_READY": "LAUNCHING",
    "LAUNCHED": "OPERATIONAL",
    "EARLY_OPERATIONS": "OPERATIONAL",
    "GROWING": "OPERATIONAL",
    "STABLE": "OPERATIONAL",
    "OPTIMIZING": "OPTIMIZING",
    "SCALING": "SCALING",
    "AT_RISK": "AT_RISK",
    "RECOVERY": "RESTRUCTURING",
    "PAUSED": "PAUSED",
    "CLOSURE_REVIEW": "CLOSING",
    "CLOSED": "CLOSING",
    "ARCHIVED": "ARCHIVED",
}


def portfolio_stage(p06_status: str, overlay_state: str | None) -> str:
    """Derive the §4 portfolio stage label from authoritative state.

    A business is never labelled OPERATIONAL/OPTIMIZING/SCALING by
    P-13: those labels appear only when P-06 says OPERATIONAL and
    the P-08 overlay (evidence-gated) refines the reading.
    """
    if p06_status != "OPERATIONAL":
        return P06_STAGE.get(p06_status, "IDEA")
    if overlay_state and overlay_state in OVERLAY_STAGE:
        return OVERLAY_STAGE[overlay_state]
    return "OPERATIONAL"


# ------------------------------------------------------- membership
MEMBERSHIP_STATUSES = {"ACTIVE", "PAUSED", "REMOVED"}
PORTFOLIO_STATUSES = {"ACTIVE", "ARCHIVED"}
OBJECTIVE_HORIZONS = {
    "IMMEDIATE", "30_DAY", "90_DAY", "ANNUAL", "LONG_TERM",
}
OBJECTIVE_STATUSES = {"ACTIVE", "COMPLETED", "ARCHIVED"}

# ---------------------------------------------------- relationships
RELATIONSHIP_TYPES = {
    "OWNS_PRODUCT", "USES_SERVICE", "PROVIDES_SERVICE",
    "SHARES_INFRASTRUCTURE", "PARTNERSHIP", "SHARED_AUDIENCE",
    "PLATFORM_DEPENDENCY", "SHARES_RESOURCE",
}
RELATIONSHIP_STATUSES = {
    "PROPOSED", "UNDER_REVIEW", "APPROVED", "ACTIVE", "SUSPENDED",
    "TERMINATED", "EXPIRED",
}
RELATIONSHIP_TRANSITIONS: dict[str, set[str]] = {
    "PROPOSED": {"UNDER_REVIEW", "APPROVED", "TERMINATED"},
    "UNDER_REVIEW": {"APPROVED", "TERMINATED"},
    "APPROVED": {"ACTIVE", "SUSPENDED", "TERMINATED", "EXPIRED"},
    "ACTIVE": {"SUSPENDED", "TERMINATED", "EXPIRED"},
    "SUSPENDED": {"ACTIVE", "TERMINATED", "EXPIRED"},
    "TERMINATED": set(),
    "EXPIRED": set(),
}
SHARING_POLICIES = {
    "NONE", "AGGREGATE_ONLY", "SPECIFIC_RECORDS", "READ_ONLY",
    "CONTROLLED_OPERATIONAL", "TIME_LIMITED",
}

# ------------------------------------------- data categories (§8/§20)
# Categories an agent may ever be granted across businesses. Anything
# not listed here does not exist as far as P-13 grants are concerned.
GRANTABLE_CATEGORIES = {
    "aggregate_metrics",        # portfolio-level numbers, no records
    "operational_status",       # lifecycle/health readings
    "financial_summary",        # P-07 summary figures for one business
    "generalized_lessons",      # ORGANIZATION_SHARED memory only
    "market_research",          # shareable research artefacts
    "service_utilization",      # shared-service usage figures
}
# Categories that exist in the system but are NEVER cross-business
# grantable — naming one in a grant/assignment/contribution is a
# validation error, not a silent no-op.
NEVER_GRANTABLE = {
    "credentials", "customer_records", "financial_records",
    "business_memory", "secrets", "platform_accounts",
}
# Categories a portfolio workflow participation may contribute (§13):
# what a business can explicitly offer a joint workflow.
SHAREABLE_CONTRIBUTIONS = {
    "research", "content", "infrastructure", "distribution",
    "aggregate_metrics", "generalized_lessons", "operational_capacity",
}
# Portfolio-scope agent assignments may only carry aggregate-level
# categories (§8: portfolio agents get approved aggregates or
# explicitly authorized data — never record-level detail).
PORTFOLIO_SCOPE_CATEGORIES = {
    "aggregate_metrics", "operational_status", "service_utilization",
    "generalized_lessons",
}

# ------------------------------------------------- opportunities §7
OPPORTUNITY_CATEGORIES = {
    "SHARED_AUDIENCE", "SHARED_INFRASTRUCTURE", "COMPLEMENTARY_PRODUCT",
    "CROSS_PROMOTION", "SHARED_KNOWLEDGE", "SHARED_SERVICE",
    "NEW_VENTURE",
}
OPPORTUNITY_STATUSES = {
    "PROPOSED", "VALIDATED", "REJECTED", "ACCEPTED", "DISMISSED",
}
# Evidence sources the gate trusts: every evidence item must name one
# of these system sources (or be an explicit owner attestation, which
# only the owner can supply). Free-text "evidence" from an agent is
# not evidence.
TRUSTED_EVIDENCE_SOURCES = {
    "p07.metrics", "p07.consolidated", "p07.business_summary",
    "p08.concentration", "p08.lifecycle", "p08.portfolio",
    "p06.business", "p06.channels", "p03.opportunity",
    "p13.shared_service", "p13.relationship", "p09.memory",
    "owner.attestation",
}
EVIDENCE_STATUSES = {"VERIFIED", "SPECULATIVE", "REJECTED"}
CONFIDENCE_LEVELS = {"low", "moderate", "high"}

RECOMMENDATION_KINDS = {
    "CAPITAL_ALLOCATION", "COST_REDUCTION", "SHARED_INFRASTRUCTURE",
    "DIVERSIFICATION", "RISK_REDUCTION", "EXPANSION", "RESTRUCTURING",
    "RESOURCE_REALLOCATION", "SYNERGY", "SURVIVAL",
}
RECOMMENDATION_STATUSES = {"PROPOSED", "ACCEPTED", "REJECTED", "DISMISSED"}

# -------------------------------------------------- shared services
SERVICE_KINDS = {
    "ai_model_infrastructure", "research_infrastructure",
    "content_production", "development_environment", "analytics",
    "monitoring", "backup", "notifications", "document_processing",
    "automation_adapter", "internal_service",
}
SERVICE_STATUSES = {"AVAILABLE", "DEGRADED", "UNAVAILABLE"}
ACCESS_STATUSES = {
    "REQUESTED", "APPROVED", "ACTIVE", "DENIED", "REVOKED", "EXPIRED",
}

# -------------------------------------------------------- resources
RESOURCE_KINDS = {
    "inference_slots", "api_quota_units", "storage_mb",
    "service_capacity_units", "agent_hours",
}
RESOURCE_ALLOCATION_STATUSES = {
    "PROPOSED", "APPROVED", "ACTIVE", "RELEASED", "REVOKED", "DENIED",
}

# ------------------------------------------------------ risk levels
RISK_LEVELS = ["low", "moderate", "high", "critical"]

# ---------------------------------------------------------- reports
REPORT_TYPES = {"SNAPSHOT", "COMPARISON", "FINANCIAL", "STRATEGIC", "RISK"}

# --------------------------------------------------------- ventures
VENTURE_STATUSES = {
    "DRAFT", "PROPOSED", "APPROVED", "REJECTED", "HANDED_TO_P06",
}
