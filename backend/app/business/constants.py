"""P-06 constants: settings key/defaults (§6 minimum level is governance
config, never hardcoded into decisions), eligibility decisions (§6),
assumption statuses (§8.5), readiness results (§20), platform-gate
catalogue (§14) and the template-validation denylist (§9/§15/§33).
"""
from __future__ import annotations

SETTINGS_KEY = "business.settings"

DEFAULT_SETTINGS: dict = {
    # Owner-governed (system_config). P-03 levels are 0..5; creation
    # requires a commercially assessed opportunity by default.
    "min_validation_level": 3,
    "default_currency": "USD",
    "require_creation_approval": True,
    "require_declaration_before_run": True,
    "version": "business-settings-v1",
}

# §6 eligibility decisions.
ELIGIBLE_FOR_CREATION = "ELIGIBLE_FOR_CREATION"
ELIGIBLE_WITH_CONDITIONS = "ELIGIBLE_WITH_CONDITIONS"
REQUIRES_MORE_RESEARCH = "REQUIRES_MORE_RESEARCH"
REQUIRES_MORE_VALIDATION = "REQUIRES_MORE_VALIDATION"
REQUIRES_OWNER_APPROVAL = "REQUIRES_OWNER_APPROVAL"
REJECTED = "REJECTED"
DEFERRED = "DEFERRED"
ELIGIBILITY_DECISIONS = {
    ELIGIBLE_FOR_CREATION, ELIGIBLE_WITH_CONDITIONS, REQUIRES_MORE_RESEARCH,
    REQUIRES_MORE_VALIDATION, REQUIRES_OWNER_APPROVAL, REJECTED, DEFERRED,
}
# Decisions under which create_business may proceed (approval is checked
# separately and additionally — see service.create_business).
CREATABLE_DECISIONS = {ELIGIBLE_FOR_CREATION, ELIGIBLE_WITH_CONDITIONS}

# §8.5 assumption register statuses.
ASSUMPTION_STATUSES = {
    "VERIFIED", "SUPPORTED", "TENTATIVE", "UNVERIFIED", "CONTRADICTED",
}

# §20 readiness results, in precedence order (hard blockers first).
READINESS_RESULTS = {
    "READY", "READY_WITH_WARNINGS", "NOT_READY", "BLOCKED",
    "OWNER_REVIEW_REQUIRED",
}
READINESS_PASSING = {"READY", "READY_WITH_WARNINGS"}

READINESS_DISCLAIMER = (
    "This review is a deterministic internal assessment against stored "
    "evidence. Legal, tax, licensing and regulatory readiness are NOT "
    "independently certified by this system; items flagged for "
    "professional review require a qualified human professional.")

# §18 workspace subdirectories (created by workflow mkdir steps).
WORKSPACE_SUBDIRS = [
    "blueprint", "product", "brand", "marketing", "sales", "operations",
    "customer_support", "financial_records", "evidence", "reports",
    "website", "legal",
]

# Template-validation denylist: parameter keys that would imply money
# movement or external sending. No P-05 tool performs these, and a
# template naming them is rejected at validation (§9/§15/§33 rule 8/12).
FORBIDDEN_STEP_KEYS = {
    "payment", "payments", "charge", "checkout", "wallet", "payout",
    "transfer", "bank_account", "card_number", "send_email", "send_to",
    "recipients", "publish_live", "auto_post",
}
# Tools/actions a template may never use: desktop is DISABLED in P-05;
# browser interactive actions are ADAPTER_UNAVAILABLE; neither may be
# smuggled into a "creation" template.
FORBIDDEN_TEMPLATE_TOOLS = {"desktop"}
FORBIDDEN_TEMPLATE_ACTIONS = {("browser", "interact")}

FIXTURE_MARKER = "FIXTURE"

# Approval action names carried by the central P-01 ApprovalService
# (audit §5: no business_approvals table).
APPROVAL_ACTION_CREATE = "business.create"
APPROVAL_ACTION_DECLARATION = "business.declaration"
APPROVAL_ACTION_BLUEPRINT = "business.blueprint"
APPROVAL_ACTION_LAUNCH = "business.launch"
