"""P-18 vocabularies, settings and catalogues.

Everything here is declared data: lifecycle templates by business
model (§3), ticket categories and priority factors (§7),
communication kinds with their approval discipline (§8), feedback
kinds and score ranges (§10), health rules (§12), the integration
catalogue (every surface honestly NOT CONFIGURED) and the §14
agent role definitions seeded into the P-04 Agent Factory.

No SLA numbers live here: SLA targets are owner-configured per
business (``cx_sla_policies``) or absent — the engine never
invents a contractual target. No figure in this module is a
measurement.
"""
from __future__ import annotations


def actor_of(principal) -> str:
    if principal is None:
        return "system"
    return f"{principal.type.value}:{principal.id}"


ENGINE_NAME = ("P-18 Customer Experience, Service Delivery & "
               "Customer Success Engine")
SETTINGS_KEY = "experience.settings"

AUTONOMY_LEVELS = (0, 1, 2, 3)
# §18: 0 observation, 1 recommendations, 2 approved execution,
# 3 bounded autonomous operations (internal, low-risk). The
# staging default is 1 (recommendations): customer data writes
# are owner-gated in-service regardless, and no customer-facing
# transport exists to execute through anyway.

DEFAULT_SETTINGS = {
    "autonomy_level": 1,
    "communications_stopped": False,
    "auto_evaluation_enabled": True,
    # hours an in-progress onboarding may sit before the
    # evaluation pass flags it stalled (owner-editable)
    "onboarding_stall_hours": 72,
    # hours a fulfillment may sit unassigned before the
    # evaluation pass flags unassigned work
    "unassigned_work_hours": 24,
    # anti-spam discipline for operational messages (per
    # customer, rolling 30 days) — service messages are
    # operational, never marketing
    "comm_frequency_limit_per_30d": 30,
    # minimum days between feedback requests to one customer
    "feedback_request_interval_days": 14,
    "health_weights": {
        "open_critical_ticket": 30,
        "open_high_ticket": 15,
        "open_ticket": 5,
        "reopened_ticket": 10,
        "fulfillment_problem": 15,
        "onboarding_incomplete": 10,
        "low_feedback": 10,
    },
}

# ------------------------------------------------------------ §3 lifecycle
BUSINESS_MODELS = (
    "physical_product", "digital_product", "subscription", "saas",
    "education", "content_publishing", "consulting", "freelance",
    "agency", "local_service", "ai_product", "membership", "other",
)

# Stage kinds from the §3 lifecycle list. Onboarding templates use
# the subset relevant to each business model; the sequences below
# are system defaults (labelled system_default wherever used) and
# businesses may replace them with their own templates.
def _stage(key, label, kind):
    return {"key": key, "label": label, "kind": kind}


_COMMON_OPENING = [
    _stage("purchase_completed", "Purchase completed", "purchase"),
    _stage("request_received", "Order / service request received",
           "purchase"),
    _stage("onboarding_started", "Customer onboarding initiated",
           "onboarding"),
    _stage("information_verified", "Customer information verified",
           "verification"),
]
_COMMON_CLOSING = [
    _stage("customer_notified", "Customer notified", "notification"),
    _stage("assistance_available", "Assistance available if required",
           "assistance"),
    _stage("satisfaction_evaluated", "Satisfaction evaluated",
           "satisfaction"),
    _stage("success_monitored", "Customer success monitored",
           "success"),
]

DEFAULT_LIFECYCLES: dict[str, list] = {
    "physical_product": _COMMON_OPENING + [
        _stage("preparation", "Delivery preparation", "preparation"),
        _stage("fulfillment_started", "Fulfillment initiated",
               "fulfillment"),
        _stage("delivered", "Delivery completed", "delivery"),
    ] + _COMMON_CLOSING,
    "digital_product": _COMMON_OPENING + [
        _stage("preparation", "Delivery preparation", "preparation"),
        _stage("access_provisioned", "Access / license provisioned",
               "fulfillment"),
        _stage("delivered", "Digital delivery completed", "delivery"),
    ] + _COMMON_CLOSING,
    "subscription": _COMMON_OPENING + [
        _stage("preparation", "Service preparation", "preparation"),
        _stage("subscription_activated", "Subscription activated",
               "fulfillment"),
        _stage("delivered", "Service access delivered", "delivery"),
    ] + _COMMON_CLOSING,
    "saas": _COMMON_OPENING + [
        _stage("preparation", "Account preparation", "preparation"),
        _stage("account_provisioned", "Account provisioned",
               "fulfillment"),
        _stage("delivered", "Workspace delivered", "delivery"),
    ] + _COMMON_CLOSING,
    "education": _COMMON_OPENING + [
        _stage("preparation", "Enrolment preparation", "preparation"),
        _stage("enrolled", "Customer enrolled", "fulfillment"),
        _stage("delivered", "Course access delivered", "delivery"),
    ] + _COMMON_CLOSING,
    "content_publishing": _COMMON_OPENING + [
        _stage("preparation", "Delivery preparation", "preparation"),
        _stage("access_provisioned", "Content access provisioned",
               "fulfillment"),
        _stage("delivered", "Content delivered", "delivery"),
    ] + _COMMON_CLOSING,
    "consulting": _COMMON_OPENING + [
        _stage("preparation", "Engagement preparation", "preparation"),
        _stage("engagement_started", "Engagement started",
               "fulfillment"),
        _stage("delivered", "Engagement delivered", "delivery"),
    ] + _COMMON_CLOSING,
    "freelance": _COMMON_OPENING + [
        _stage("preparation", "Project preparation", "preparation"),
        _stage("work_started", "Work started", "fulfillment"),
        _stage("delivered", "Work delivered", "delivery"),
    ] + _COMMON_CLOSING,
    "agency": _COMMON_OPENING + [
        _stage("preparation", "Project preparation", "preparation"),
        _stage("work_started", "Project work started", "fulfillment"),
        _stage("delivered", "Deliverables delivered", "delivery"),
    ] + _COMMON_CLOSING,
    "local_service": _COMMON_OPENING + [
        _stage("preparation", "Service preparation", "preparation"),
        _stage("appointment_scheduled", "Appointment scheduled",
               "fulfillment"),
        _stage("delivered", "Service completed", "delivery"),
    ] + _COMMON_CLOSING,
    "ai_product": _COMMON_OPENING + [
        _stage("preparation", "Account preparation", "preparation"),
        _stage("account_provisioned", "Account provisioned",
               "fulfillment"),
        _stage("delivered", "Product access delivered", "delivery"),
    ] + _COMMON_CLOSING,
    "membership": _COMMON_OPENING + [
        _stage("preparation", "Membership preparation", "preparation"),
        _stage("membership_activated", "Membership activated",
               "fulfillment"),
        _stage("delivered", "Member access delivered", "delivery"),
    ] + _COMMON_CLOSING,
    "other": _COMMON_OPENING + [
        _stage("preparation", "Delivery preparation", "preparation"),
        _stage("fulfillment_started", "Fulfillment initiated",
               "fulfillment"),
        _stage("delivered", "Delivery / service completed",
               "delivery"),
    ] + _COMMON_CLOSING,
}

ONBOARDING_STEP_KINDS = ("onboarding", "verification")
ONBOARDING_STATUSES = ("not_started", "in_progress", "completed",
                       "stalled", "failed")

# ------------------------------------------------------------ §5 fulfillment
FULFILLMENT_KINDS = ("physical", "digital", "service")
FULFILLMENT_STATUSES = ("received", "preparing", "in_progress",
                        "shipped", "delivered", "completed",
                        "failed", "returned")
FULFILLMENT_STATUS_FLOWS = {
    "physical": ("received", "preparing", "shipped", "delivered",
                 "failed", "returned"),
    "digital": ("received", "preparing", "delivered", "completed",
                "failed"),
    "service": ("received", "in_progress", "completed", "failed"),
}
FULFILLMENT_STATUS_SOURCES = ("manual", "owner_declared",
                              "integration")
ACCEPTANCE_STATES = ("pending", "accepted", "rejected")

# ------------------------------------------------------------ §7 tickets
TICKET_CATEGORIES = (
    "product_problem", "delivery_problem", "payment_question",
    "account_access", "technical_issue", "subscription_issue",
    "refund_request", "cancellation_request",
    "service_quality_complaint", "general_inquiry", "feature_request",
    "other",
)
TICKET_STATUSES = ("new", "classified", "assigned", "in_progress",
                   "waiting_for_customer", "escalated", "resolved",
                   "closed")
TICKET_TRANSITIONS = {
    "new": ("classified", "assigned", "in_progress", "escalated",
            "resolved", "closed"),
    "classified": ("assigned", "in_progress", "escalated",
                   "resolved", "closed"),
    "assigned": ("in_progress", "waiting_for_customer", "escalated",
                 "resolved", "closed"),
    "in_progress": ("waiting_for_customer", "escalated", "resolved",
                    "closed"),
    "waiting_for_customer": ("in_progress", "escalated", "resolved",
                             "closed"),
    "escalated": ("assigned", "in_progress", "resolved", "closed"),
    "resolved": ("closed", "in_progress"),   # reopen -> in_progress
    "closed": ("in_progress",),              # reopen -> in_progress
}
PRIORITY_LEVELS = ("low", "medium", "high", "critical")
# Explainable priority (§7): each factor is scored 0..3 by the
# caller from the case facts; the weighted sum maps to a band and
# the full breakdown is stored on the ticket.
PRIORITY_FACTORS = ("customer_impact", "business_impact", "security",
                    "financial", "service_disruption", "contractual",
                    "time_sensitivity")
PRIORITY_WEIGHTS = {"customer_impact": 3, "business_impact": 2,
                    "security": 4, "financial": 3,
                    "service_disruption": 3, "contractual": 2,
                    "time_sensitivity": 2}
# Categories whose floor priority is high regardless of factors:
# a security implication or a money question is never "low".
CATEGORY_PRIORITY_FLOORS = {"account_access": "high",
                            "refund_request": "high",
                            "payment_question": "medium"}

# ------------------------------------------------------------ §8 communications
# kind -> (requires_approval, essential). Essential operational
# messages (purchase confirmation, resolution notices) are exempt
# from the marketing-style opt-out but never from consent or
# suppression. Refund *promises* are not a kind at all: P-18 can
# never promise a refund — refunds live in §11 resolutions and
# P-07 (§8 + Article-0-adjacent honesty).
COMMUNICATION_KINDS: dict[str, tuple[bool, bool]] = {
    "purchase_confirmation": (False, True),
    "welcome": (False, False),
    "onboarding_instructions": (False, False),
    "delivery_notification": (False, True),
    "milestone_notification": (False, False),
    "appointment_reminder": (False, False),
    "troubleshooting_instructions": (False, False),
    "ticket_update": (False, True),
    "resolution_notification": (False, True),
    "feedback_request": (False, False),
    "service_announcement": (True, False),
    "financial_commitment": (True, False),
    "contractual_statement": (True, False),
    "legal_statement": (True, False),
}
COMMUNICATION_CHANNELS = ("email", "in_app", "sms", "chat", "phone")
DISPATCH_BLOCKED_NOTE = (
    "no customer communication transport is configured "
    "(REQUIRES OWNER CONFIGURATION); the message is queued only "
    "and has NOT been sent")

# ------------------------------------------------------------ §6 support answers
CONFIDENCE_CLASSES = ("verified", "partially_verified",
                      "insufficient_information",
                      "human_review_required")
# keyword-overlap score at/above which an approved article is a
# verified ground; between the partial floor and the verified
# threshold the answer is partial and a human is flagged.
KB_VERIFIED_THRESHOLD = 0.5
KB_PARTIAL_THRESHOLD = 0.18

# ------------------------------------------------------------ §10 feedback
FEEDBACK_KINDS = ("csat", "nps", "effort", "product", "service",
                  "support", "delivery", "complaint",
                  "feature_request")
FEEDBACK_SCORE_RANGES = {"csat": (1, 5), "nps": (0, 10),
                         "effort": (1, 5)}
FEEDBACK_SOURCES = ("recorded", "owner_declared")

# ------------------------------------------------------------ §11 resolution
PROBLEM_CLASSES = ("product", "delivery", "payment", "account",
                   "technical", "subscription", "service_quality",
                   "general")
ROOT_CAUSE_GROUPS = ("product", "service", "process",
                     "fulfillment_provider", "technical",
                     "communication", "human_error",
                     "policy_ambiguity")
RESOLUTION_ACTIONS = ("replacement", "redelivery",
                      "technical_assistance", "service_correction",
                      "account_restoration", "human_escalation",
                      "refund_recommendation",
                      "goodwill_recommendation")
FINANCIAL_ACTIONS = ("refund_recommendation",
                     "goodwill_recommendation")
RESOLUTION_STATUSES = ("recommended", "approved", "executed",
                       "rejected", "verified", "closed")

# ------------------------------------------------------------ §9 quality
QUALITY_DIMENSIONS = ("accuracy", "completeness", "clarity",
                      "relevance", "resolution_effectiveness",
                      "professionalism", "consistency",
                      "customer_effort", "timeliness",
                      "policy_compliance")

# ------------------------------------------------------------ §12 success
HEALTH_CLASSIFICATIONS = ("healthy", "stable", "needs_attention",
                          "at_risk", "critical", "insufficient_data")
SUCCESS_TASK_KINDS = ("onboarding_assistance", "product_education",
                      "troubleshoot", "service_review",
                      "human_support", "configuration_guidance")
SUCCESS_TASK_SOURCES = ("owner", "health_evaluation", "incident",
                        "ticket")

# ------------------------------------------------------------ §5/§7 incidents
INCIDENT_KINDS = ("delayed_fulfillment", "failed_provisioning",
                  "missing_deliverable", "unassigned_work",
                  "sla_breach", "onboarding_stalled",
                  "repeated_failure")
INCIDENT_SEVERITIES = ("low", "medium", "high", "critical")

# ------------------------------------------------------------ §16 integrations
# Every external surface is honestly unconfigured (P-17 pattern).
INTEGRATIONS = [
    {"key": "support_email", "label": "Support email inbox",
     "status": "not_configured",
     "note": "REQUIRES OWNER CONFIGURATION — no inbox is connected; "
             "tickets are recorded by operators, not received"},
    {"key": "website_chat", "label": "Website chat",
     "status": "not_configured",
     "note": "REQUIRES OWNER CONFIGURATION — no chat widget is "
             "connected"},
    {"key": "messaging_platforms", "label": "Messaging platforms",
     "status": "not_configured",
     "note": "REQUIRES OWNER CONFIGURATION — no messaging platform "
             "is connected"},
    {"key": "logistics_tracking", "label": "Logistics / shipment "
     "tracking", "status": "not_configured",
     "note": "REQUIRES OWNER CONFIGURATION — fulfillment status is "
             "manually supplied or owner-declared and labelled so"},
    {"key": "digital_delivery", "label": "Digital delivery / "
     "entitlement provider", "status": "not_configured",
     "note": "REQUIRES OWNER CONFIGURATION — provisioning outcomes "
             "are recorded by operators, never fabricated"},
    {"key": "appointment_scheduling", "label": "Appointment "
     "scheduling", "status": "not_configured",
     "note": "REQUIRES OWNER CONFIGURATION — appointments are "
             "recorded as milestones, not booked"},
    {"key": "survey_delivery", "label": "Survey delivery",
     "status": "not_configured",
     "note": "REQUIRES OWNER CONFIGURATION — feedback is recorded "
             "from responses the business supplies"},
    {"key": "communication_transport", "label": "Customer "
     "communication transport", "status": "not_configured",
     "note": "REQUIRES OWNER CONFIGURATION — communications queue "
             "but never send"},
]

# ------------------------------------------------------------ §14 agent roles
_READ_CAPS = ["internal_reasoning", "internal_database_read",
              "memory_read"]
_DRAFT_CAPS = ["internal_reasoning", "memory_read"]
_WRITE_CAPS = ["internal_reasoning", "internal_database_read",
               "internal_database_write", "memory_read"]
_HANDLERS = ["core.echo_check", "core.health_snapshot", "core.noop"]

# No P-18 role receives external_communication (nothing may send)
# or any financial capability (refunds stay owner-executed through
# P-07); roles are scoped, read/draft-first definitions (§14).
AGENT_ROLES: list[dict] = [
    {"name": "Customer Onboarding Agent",
     "role": "p18_customer_onboarding_agent",
     "agent_type": "operations", "capabilities": _WRITE_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Guide new customers through the business's onboarding steps and flag stalls.",
     "instruction": "You are a customer onboarding agent. Work only from the business's configured onboarding template and the customer's recorded state; never invent steps, requirements or deadlines.",
     "responsibility": "Track onboarding progress and surface stalled customers."},
    {"name": "Fulfillment Monitoring Agent",
     "role": "p18_fulfillment_monitoring_agent",
     "agent_type": "operations", "capabilities": _READ_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Monitor fulfillment records for delays, failures and unassigned work.",
     "instruction": "You are a fulfillment monitoring agent. Report only recorded fulfillment states and their source labels; never claim a shipment or delivery you cannot cite.",
     "responsibility": "Detect and report fulfillment problems as incidents."},
    {"name": "Customer Support Agent",
     "role": "p18_customer_support_agent",
     "agent_type": "support", "capabilities": _DRAFT_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Draft support answers grounded only in approved knowledge articles.",
     "instruction": "You are a customer support agent. Answer only from approved knowledge articles and cite them; if the knowledge base cannot verify an answer, say so and escalate. Never invent policies, prices, warranties, dates or refund terms, and never impersonate a human employee.",
     "responsibility": "Draft grounded support answers with confidence classes."},
    {"name": "Ticket Classification Agent",
     "role": "p18_ticket_classification_agent",
     "agent_type": "support", "capabilities": _WRITE_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Classify support tickets and compute explainable priorities from declared factors.",
     "instruction": "You are a ticket classification agent. Use only the declared categories and priority factors; record the factor breakdown so every priority is explainable.",
     "responsibility": "Categorise tickets and assign explainable priorities."},
    {"name": "Support Quality Assurance Agent",
     "role": "p18_support_qa_agent",
     "agent_type": "analysis", "capabilities": _READ_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Sample support cases and record quality reviews under the documented method.",
     "instruction": "You are a support quality assurance agent. Score only the documented quality dimensions from recorded case evidence; never present a review score as customer satisfaction.",
     "responsibility": "Produce sampled QA reviews with evidence."},
    {"name": "Customer Feedback Analysis Agent",
     "role": "p18_feedback_analysis_agent",
     "agent_type": "analysis", "capabilities": _READ_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Analyse recorded customer feedback for repeated themes and complaints.",
     "instruction": "You are a feedback analysis agent. Work only from recorded feedback rows and cite them; distinguish actual responses from any estimate — you produce no sentiment estimates.",
     "responsibility": "Surface feedback themes backed by recorded evidence."},
    {"name": "Issue Resolution Coordinator",
     "role": "p18_issue_resolution_coordinator",
     "agent_type": "operations", "capabilities": _WRITE_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Coordinate issue resolution and prepare service-recovery recommendations.",
     "instruction": "You are an issue resolution coordinator. You may prepare recovery recommendations, but you may never execute a refund, compensation or financial commitment — those remain with the owner and P-07.",
     "responsibility": "Track resolution cases to a verified outcome."},
    {"name": "Customer Success Analyst",
     "role": "p18_customer_success_analyst",
     "agent_type": "analysis", "capabilities": _READ_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Compute customer health classifications from recorded service signals.",
     "instruction": "You are a customer success analyst. Classify health only from recorded signals with factors and evidence; never present a health classification as a churn prediction or a customer's decision.",
     "responsibility": "Produce evidence-backed customer health snapshots."},
    {"name": "Knowledge Base Maintenance Agent",
     "role": "p18_kb_maintenance_agent",
     "agent_type": "production", "capabilities": _DRAFT_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Draft knowledge articles and flag stale or contradictory content.",
     "instruction": "You are a knowledge base maintenance agent. Drafts you write stay drafts until the owner approves them; never publish policy-sensitive content and never edit an approved article silently.",
     "responsibility": "Keep the knowledge base current under owner approval."},
    {"name": "Service Performance Analyst",
     "role": "p18_service_performance_analyst",
     "agent_type": "analysis", "capabilities": _READ_CAPS,
     "outputs": ["summary", "evidence_refs"],
     "mission": "Report service performance: SLA compliance, resolution times, recurring issues.",
     "instruction": "You are a service performance analyst. Compute only from recorded data; when a metric's data is missing, report it unavailable instead of estimating it.",
     "responsibility": "Produce service performance reports with sample sizes."},
]
