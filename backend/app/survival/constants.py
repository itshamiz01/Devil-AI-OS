"""P-08 constants: owner-governed settings (§7.3 weights, §10.2
criteria sets, §10.4 increment cap), classifications, the decision
type → autonomy level table (§20.2/§3.3), the P-08→P-06 lifecycle
mapping (audit §4) and the hard-gate catalogue.

Settings live in ``system_config`` under ``SETTINGS_KEY`` and are
writable only by the Owner principal — agents can never rewrite the
rules that govern them (Article 0). Every threshold P-08 enforces is
read from these settings at evaluation time, never hardcoded into a
decision.
"""
from __future__ import annotations

SETTINGS_KEY = "survival.settings"
SOURCE = "survival-engine"

# ------------------------------------------------------------------ §7.2
CLASSIFICATIONS = [
    "EXCELLENT", "HEALTHY", "STABLE", "WATCH", "AT_RISK", "CRITICAL",
    "INSUFFICIENT_DATA",
]
# Severity order for hard-gate caps (worse = later).
SEVERITY = {name: i for i, name in enumerate(
    ["EXCELLENT", "HEALTHY", "STABLE", "WATCH", "AT_RISK", "CRITICAL"])}

DIMENSIONS = [
    "financial", "market", "commercial", "operational", "product",
    "strategic", "governance",
]

CONFIDENCE_LEVELS = ["low", "moderate", "high"]

# ------------------------------------------------------------------ §5.1
# P-08 operational overlay states. The P-06 lifecycle is the only
# business state machine; overlays are P-08's operational reading.
OVERLAY_STATES = [
    "PROPOSED", "VALIDATING", "APPROVED", "BUILDING", "LAUNCH_READY",
    "LAUNCHED", "EARLY_OPERATIONS", "GROWING", "STABLE", "SCALING",
    "OPTIMIZING", "AT_RISK", "RECOVERY", "PAUSED", "CLOSURE_REVIEW",
    "CLOSED", "ARCHIVED",
]

# P-06 status -> base overlay (audit §4 mapping). OPERATIONAL refines
# further from evidence in the health engine.
P06_TO_OVERLAY = {
    "PROPOSED": "PROPOSED",
    "ELIGIBILITY_REVIEW": "VALIDATING",
    "BLUEPRINTING": "BUILDING",
    "BLUEPRINT_READY": "BUILDING",
    "APPROVAL_PENDING": "BUILDING",
    "PRODUCT_PLANNING": "BUILDING",
    "IN_DEVELOPMENT": "BUILDING",
    "INTERNAL_TESTING": "BUILDING",
    "DISTRIBUTION_PREPARATION": "BUILDING",
    "LAUNCH_REVIEW": "BUILDING",
    "READY_FOR_LAUNCH": "LAUNCH_READY",
    "LAUNCH_APPROVAL_PENDING": "LAUNCH_READY",
    "LAUNCHING": "LAUNCH_READY",
    "OPERATIONAL": "EARLY_OPERATIONS",
    "PAUSED": "PAUSED",
    "BLOCKED": "AT_RISK",
    "FAILED": "CLOSURE_REVIEW",
    "ARCHIVED": "ARCHIVED",
}

OVERLAY_TRANSITIONS: dict[str, set[str]] = {
    "PROPOSED": {"VALIDATING", "BUILDING", "CLOSURE_REVIEW", "ARCHIVED"},
    "VALIDATING": {"APPROVED", "BUILDING", "CLOSURE_REVIEW", "ARCHIVED"},
    "APPROVED": {"BUILDING", "CLOSURE_REVIEW", "ARCHIVED"},
    "BUILDING": {"LAUNCH_READY", "AT_RISK", "PAUSED", "CLOSURE_REVIEW"},
    "LAUNCH_READY": {"LAUNCHED", "AT_RISK", "PAUSED", "CLOSURE_REVIEW"},
    "LAUNCHED": {"EARLY_OPERATIONS", "AT_RISK", "PAUSED", "CLOSURE_REVIEW"},
    "EARLY_OPERATIONS": {"GROWING", "STABLE", "AT_RISK", "PAUSED",
                         "CLOSURE_REVIEW"},
    "GROWING": {"SCALING", "STABLE", "OPTIMIZING", "AT_RISK", "PAUSED",
                "CLOSURE_REVIEW"},
    "STABLE": {"GROWING", "SCALING", "OPTIMIZING", "AT_RISK", "PAUSED",
               "CLOSURE_REVIEW"},
    "SCALING": {"OPTIMIZING", "STABLE", "AT_RISK", "PAUSED",
                "CLOSURE_REVIEW"},
    "OPTIMIZING": {"STABLE", "GROWING", "AT_RISK", "PAUSED",
                   "CLOSURE_REVIEW"},
    "AT_RISK": {"RECOVERY", "STABLE", "PAUSED", "CLOSURE_REVIEW"},
    "RECOVERY": {"STABLE", "AT_RISK", "CLOSURE_REVIEW", "PAUSED"},
    "PAUSED": {"EARLY_OPERATIONS", "STABLE", "AT_RISK", "CLOSURE_REVIEW",
               "BUILDING", "LAUNCH_READY"},
    "CLOSURE_REVIEW": {"CLOSED", "STABLE", "AT_RISK"},
    "CLOSED": {"ARCHIVED"},
    "ARCHIVED": set(),
}

# ------------------------------------------------------------------ §8.1
DECISION_TYPES = [
    "CONTINUE", "MONITOR", "INVESTIGATE", "IMPROVE", "OPTIMIZE",
    "RUN_EXPERIMENT", "REDUCE_COSTS", "INCREASE_RESOURCES", "SCALE",
    "EXPAND_MARKET", "EXPAND_PRODUCT", "CHANGE_STRATEGY", "RECOVER",
    "PAUSE", "REVIEW_FOR_CLOSURE", "CLOSE",
]

# §20.2 autonomy levels by decision type. Level 4 is owner-only with
# NO agent path (structural, mirroring P-04's Level-3 prohibition and
# P-07's blocked Level 3). CLOSE is Level 4 (§3.3/§14.4). SCALE and
# capital-affecting decisions are Level 3 (approval-required).
AUTONOMY_LEVELS: dict[str, int] = {
    "CONTINUE": 0, "MONITOR": 0, "INVESTIGATE": 1, "IMPROVE": 1,
    "OPTIMIZE": 2, "RUN_EXPERIMENT": 3, "REDUCE_COSTS": 2,
    "INCREASE_RESOURCES": 3, "SCALE": 3, "EXPAND_MARKET": 3,
    "EXPAND_PRODUCT": 3, "CHANGE_STRATEGY": 3, "RECOVER": 3,
    "PAUSE": 2, "REVIEW_FOR_CLOSURE": 1, "CLOSE": 4,
}

DECISION_STATUSES = [
    "PROPOSED", "PENDING_APPROVAL", "APPROVED", "REJECTED", "EXECUTED",
    "EXPIRED", "BLOCKED",
]

# Approval action names carried by the central P-01 ApprovalService
# (audit §2: no survival_approvals table).
APPROVAL_ACTION_DECISION = "survival.decision"
APPROVAL_ACTION_CLOSE = "survival.close"
APPROVAL_ACTION_EXPERIMENT = "survival.experiment"
APPROVAL_ACTION_ALLOCATION = "survival.allocation"

# ------------------------------------------------------------------ §9
EXPERIMENT_STATUSES = [
    "PROPOSED", "DESIGNED", "APPROVED", "RUNNING", "OBSERVING",
    "SUCCESSFUL", "INCONCLUSIVE", "FAILED", "STOPPED", "ARCHIVED",
]
EVALUATION_CLASSES = [
    "VALIDATED", "PARTIALLY_VALIDATED", "INCONCLUSIVE", "INVALIDATED",
    "FAILED",
]
STOP_REASONS = [
    "budget_exhausted", "max_loss_reached", "time_limit",
    "compliance_risk", "security_risk", "hypothesis_invalidated",
    "evidence_unobtainable", "owner_instruction", "manual",
]

# §6.2: vanity metrics can never validate a business or lift a
# dimension. Observation kinds whose metrics are wholly vanity.
VANITY_KINDS = {"traffic", "social_followers", "impressions", "downloads"}
VANITY_METRIC_KEYS = {
    "page_views", "sessions", "followers", "impressions", "downloads",
    "likes", "traffic",
}

# ---------------------------------------------------------------- §13.4
RECOVERY_OUTCOMES = [
    "RECOVERED", "IMPROVING", "NO_SIGNIFICANT_CHANGE", "DETERIORATING",
    "RECOVERY_FAILED",
]
FAILURE_KINDS = [
    "bad_opportunity_selection", "bad_business_model", "bad_implementation",
    "bad_distribution", "external_conditions", "insufficient_evidence",
    "incorrect_timing", "operational", "temporary_operational", "unknown",
]

# ---------------------------------------------------------------- §14.3
CLOSURE_STAGES = [
    "PROPOSED_CLOSURE", "RISK_REVIEW", "FINANCIAL_REVIEW",
    "CUSTOMER_OBLIGATION_REVIEW", "OWNER_APPROVAL", "WIND_DOWN",
    "CLOSED", "ARCHIVED",
]

# ---------------------------------------------------------------- §16.2
ALLOCATION_CATEGORIES = [
    "business_operating", "experiment", "growth", "emergency",
    "recovery", "reserve",
]

# ------------------------------------------------------- default settings
# §10.2 criteria sets per P-06 template category. Thresholds are
# dimensionless counts/ratios over P-07 readings and P-08
# observations — P-08 never sets monetary thresholds of its own
# beyond comparing P-07 figures to each other.
_BASE_CRITERIA = {
    "min_snapshots_with_revenue": 2,
    "min_distinct_customers": 3,
    "min_repeat_customers": 1,
    "max_refund_rate": "0.10",
    "max_chargeback_rate": "0.02",
    "require_positive_contribution": True,
    "require_delivery_evidence": True,
    "require_mrr": False,
    "min_active_subscriptions": 0,
}

DEFAULT_SETTINGS: dict = {
    "version": "survival-settings-v1",
    # §7.3 proposed weights (dimension -> weight), owner-governed.
    "health_weights": {
        "financial": 25, "market": 15, "commercial": 15,
        "operational": 15, "product": 10, "strategic": 10,
        "governance": 10,
    },
    # Classification bands over the weighted score (0..1 as string).
    "health_bands": {
        "excellent": "0.85", "healthy": "0.70", "stable": "0.55",
        "watch": "0.40", "at_risk": "0.25",
    },
    # §10.4: one scaling step may propose at most this ratio over the
    # current P-07 budget figure. 5x jumps are structurally impossible.
    "max_increment_ratio": "0.5",
    # §16: no single business may be proposed more than this share of
    # available portfolio capital in one allocation round.
    "max_business_capital_share": "0.5",
    # §7.3 hard gate: concentration share (of P-07 collected-by-X)
    # above which the portfolio names a concentration risk.
    "concentration_threshold": "0.6",
    # §17: hardware profile (owner's CPU-only machine; P-00 verdict):
    # one shared inference slot, bounded agent concurrency.
    "max_concurrent_agents": 4,
    "inference_slots": 1,
    # Monitoring cadence (§6.5): event-driven + bounded evaluations;
    # no continuous polling daemon exists in staging.
    "monitoring": {
        "mode": "event_driven_plus_on_demand",
        "critical_signals": "event_driven",
        "operational_summary": "daily",
        "business_review": "weekly",
        "financial_review": "monthly",
        "portfolio_review": "quarterly",
    },
    "scaling_criteria": {
        "digital_products": dict(_BASE_CRITERIA),
        "software": dict(_BASE_CRITERIA, require_mrr=True,
                         min_active_subscriptions=3,
                         min_repeat_customers=2),
        "content": dict(_BASE_CRITERIA, min_repeat_customers=0,
                        min_distinct_customers=5),
        "services": dict(_BASE_CRITERIA, min_repeat_customers=2),
    },
}

# §19 deterministic analyst intents (the NL layer is NOT IMPLEMENTED;
# see analyst.py). Every figure carries a provenance classification.
ANALYST_INTENTS = [
    "most_stable_business", "business_needing_attention",
    "resource_recommendation", "cost_reduction_candidates",
    "scaling_readiness", "experiment_advice", "best_channel",
    "model_sustainability", "market_expansion_advice",
    "max_safe_experiment_budget", "pause_candidates",
    "biggest_portfolio_risk", "resource_consumers",
]
