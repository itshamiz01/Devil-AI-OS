"""Constants for the P-12 Autonomous Operations Engine.

Every vocabulary here is either taken verbatim from the P-12 prompt
(§4 autonomy levels, §5 workflow states, §12 decision categories,
§13 failure taxonomy) or mapped onto an existing classified
vocabulary (P-10 action risk names) — P-12 invents no parallel
authority vocabulary.
"""
from __future__ import annotations

SETTINGS_KEY = "operations.settings"

DEFAULT_SETTINGS: dict = {
    # §9 resource management — enforced by counting live substrate
    # executions; the P-01 TaskManager cap remains the hard backstop.
    "max_concurrent_workflows": 4,
    "max_concurrent_tasks_global": 8,
    "max_concurrent_tasks_per_business": 4,
    "max_concurrent_tasks_per_agent": 2,
    "max_queue_depth": 200,
    "low_resource_mode": False,
    # §4 autonomy — the seeded global default is Level 1 (prepare
    # only). Raising it is an owner action (policy row or settings
    # update), never an agent action.
    "default_autonomy_level": 1,
    # §13 recovery
    "circuit_breaker_threshold": 3,
    "circuit_breaker_cooldown_seconds": 300,
    "default_max_retries": 3,
    "retry_base_delay_seconds": 1.0,
    "retry_max_delay_seconds": 60.0,
    # §8 scheduler tick (seconds) for the in-process loop.
    "tick_interval_seconds": 1.0,
    # §16 priority aging: effective priority improves by 1 class per
    # aging window waited (never above the highest class).
    "priority_aging_seconds": 3600,
    "version": 1,
}

# --- §4 autonomy ------------------------------------------------------------
AUTONOMY_LEVELS = {
    0: "Observation Only",
    1: "Assisted Operations",
    2: "Controlled Autonomy",
    3: "Bounded Business Autonomy",
    4: "Portfolio-Level Strategic Autonomy",
}
LEVEL_OBSERVE = 0
LEVEL_ASSISTED = 1
LEVEL_CONTROLLED = 2
LEVEL_BOUNDED = 3
LEVEL_STRATEGIC = 4

# Constitution mode (Settings.mode) caps on effective autonomy.
# simulation = prepare only; emergency = nothing autonomous.
MODE_AUTONOMY_CAPS = {
    "simulation": 1,
    "supervised": 2,
    "controlled": 4,
    "emergency": 0,
}
# P-10 security mode caps: safe mode is observation-only for
# non-owners; emergency stop halts autonomous execution entirely.
SECURITY_MODE_CAPS = {
    "normal": 4,
    "safe_mode": 0,
    "emergency_stop": 0,
}

# --- §5 workflow lifecycle ----------------------------------------------------
WORKFLOW_STATES = (
    "DRAFT", "VALIDATING", "READY", "WAITING_FOR_APPROVAL", "SCHEDULED",
    "RUNNING", "PAUSED", "BLOCKED", "VERIFYING", "COMPLETED", "FAILED",
    "CANCELLED", "EXPIRED", "RECOVERY_PENDING", "COMPENSATING",
    "ARCHIVED",
)
TERMINAL_WORKFLOW_STATES = {"COMPLETED", "FAILED", "CANCELLED", "EXPIRED", "ARCHIVED"}

WORKFLOW_ORIGINS = (
    "owner", "intelligence", "agent", "business", "schedule", "event",
    "threshold", "recovery",
)

# --- §6 task lifecycle ---------------------------------------------------------
TASK_STATES = (
    "PENDING", "READY", "WAITING_FOR_APPROVAL", "RUNNING", "VERIFYING",
    "COMPLETED", "FAILED", "BLOCKED", "RECOVERY_PENDING", "DEAD_LETTER",
    "CANCELLED", "SKIPPED",
)
TERMINAL_TASK_STATES = {"COMPLETED", "FAILED", "DEAD_LETTER", "CANCELLED", "SKIPPED"}

TASK_KINDS = ("task_handler", "execution", "internal")

# Step action classes map onto P-10's classified action vocabulary
# (security/policy.ACTION_RISK). An action name absent from that map
# classifies RISK_CRITICAL in P-10 — fail closed — so P-12 only ever
# offers names from this table (plus, for P-05 steps, the tool
# action's own name, which P-05's policy classifies).
ACTION_CLASSES = (
    "read", "business.read", "financial.view", "memory.retrieve",
    "draft.create", "report.generate", "filesystem.write",
    "task.update_status", "content.publish", "message.send_external",
    "filesystem.delete", "command.execute", "financial.transfer",
)

# The P-01 permission a step's action class requires — the input the
# P-10 broker's gate 4 evaluates (the broker takes the permission
# from its caller; this is P-12's mapping, consistent with the
# financial guard's ACTION_PERMISSIONS precedent).
ACTION_PERMISSIONS = {
    "read": "read_system_data",
    "business.read": "read_business_data",
    "financial.view": "read_business_data",
    "memory.retrieve": "read_system_data",
    "draft.create": "write_system_data",
    "report.generate": "read_system_data",
    "filesystem.write": "execute_tools",
    "task.update_status": "write_system_data",
    "content.publish": "modify_business_data",
    "message.send_external": "modify_business_data",
    "filesystem.delete": "execute_tools",
    "command.execute": "execute_tools",
    "financial.transfer": "request_financial_operations",
}

# --- §12 operational decision categories ---------------------------------------
DECISION_CATEGORIES = (
    "EXECUTE", "EXECUTE_WITH_LIMITS", "REQUEST_APPROVAL", "DEFER",
    "RESEARCH_MORE", "PAUSE", "ESCALATE", "REJECT",
)

# --- §13 failure taxonomy --------------------------------------------------------
FAILURE_CATEGORIES = (
    "temporary_network_failure", "external_service_unavailable",
    "rate_limit", "agent_failure", "tool_failure",
    "invalid_output", "missing_input", "permission_failure",
    "approval_timeout", "budget_failure", "policy_violation",
    "business_paused", "system_overload", "data_conflict",
    "unknown_failure",
)
# Only these classes are ever retried automatically (§13).
RETRYABLE_CATEGORIES = {
    "temporary_network_failure", "external_service_unavailable",
    "rate_limit", "tool_failure", "system_overload",
}
# These must never be retried automatically — they escalate.
NON_RETRYABLE_CATEGORIES = {
    "permission_failure", "policy_violation", "budget_failure",
}

# --- §8 triggers -------------------------------------------------------------------
TRIGGER_TYPES = ("time", "event", "threshold", "owner", "agent")

# --- §10 budget ------------------------------------------------------------------
# Spend kinds are P-07's own vocabulary (financial.constants): kinds
# in LEVEL3_KINDS are structurally blocked there, LEVEL2_KINDS are
# held for the owner, anything else may be Level-1 authorised inside
# an active budget. The decision is always P-07's
# (BudgetService.request_spend); P-12 stores none of the amounts.
SPEND_KINDS = ("expense", "tool", "content", "marketing",
               "new_category", "new_recurring_commitment",
               "budget_increase", "refund", "payout",
               "transfer", "wallet_transfer", "investment",
               "reserve_change", "policy_change", "high_value_transfer")

# --- §15 emergency stop scopes ------------------------------------------------------
STOP_SCOPES = ("global", "business", "agent", "workflow", "external", "financial")

# --- §19 reports ---------------------------------------------------------------------
REPORT_KINDS = ("daily", "weekly", "business", "failure", "resource", "agent")
