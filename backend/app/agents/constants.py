"""P-04 factory constants: role taxonomy (§5.2), capability catalogue
(§8.1), factory setting defaults (§14.2) and seed templates (§6).

Honesty rules baked into the data:
- A capability is ``supported`` ONLY when an existing module backs it.
  Execution capabilities owned by P-05 (files, browser, sandboxed code,
  external comms, generic APIs) and ``memory_write`` (P-09) are catalogued
  with ``supported=False``: requestable for the record, never grantable.
- Level-3 entries (§8.3) are PROHIBITED: ``enabled=False``,
  ``approval_level=3``. They exist in the catalogue so requests are
  refused *as prohibited* rather than as unknown, and so audits name them.
"""
from __future__ import annotations

# --------------------------------------------------------------------------
# §5.2 role taxonomy: category -> {role_key: display name}
# --------------------------------------------------------------------------
ROLE_TAXONOMY: dict[str, dict[str, str]] = {
    "intelligence": {
        "research_agent": "Research Agent",
        "market_analysis_agent": "Market Analysis Agent",
        "competitor_analysis_agent": "Competitor Analysis Agent",
        "trend_detection_agent": "Trend Detection Agent",
        "customer_intelligence_agent": "Customer Intelligence Agent",
    },
    "strategy": {
        "business_strategy_agent": "Business Strategy Agent",
        "planning_agent": "Planning Agent",
        "decision_support_agent": "Decision Support Agent",
        "opportunity_evaluation_agent": "Opportunity Evaluation Agent",
        "risk_analysis_agent": "Risk Analysis Agent",
    },
    "production": {
        "software_development_agent": "Software Development Agent",
        "content_writing_agent": "Content Writing Agent",
        "design_planning_agent": "Design Planning Agent",
        "product_development_agent": "Product Development Agent",
        "documentation_agent": "Documentation Agent",
    },
    "operations": {
        "workflow_coordination_agent": "Workflow Coordination Agent",
        "task_management_agent": "Task Management Agent",
        "quality_assurance_agent": "Quality Assurance Agent",
        "monitoring_agent": "Monitoring Agent",
        "customer_support_agent": "Customer Support Agent",
    },
    "financial": {
        "financial_analysis_agent": "Financial Analysis Agent",
        "budget_analysis_agent": "Budget Analysis Agent",
        "revenue_analysis_agent": "Revenue Analysis Agent",
        "performance_analysis_agent": "Performance Analysis Agent",
    },
    "governance": {
        "security_review_agent": "Security Review Agent",
        "policy_compliance_agent": "Policy Compliance Agent",
        "audit_agent": "Audit Agent",
        "approval_verification_agent": "Approval Verification Agent",
    },
}

ROLE_TO_CATEGORY: dict[str, str] = {
    role: category for category, roles in ROLE_TAXONOMY.items() for role in roles
}
ROLE_DISPLAY_NAMES: dict[str, str] = {
    role: name for roles in ROLE_TAXONOMY.values() for role, name in roles.items()
}

# --------------------------------------------------------------------------
# §8.1 capability catalogue
# fields: category, risk_level, approval_level, action_class,
#         mapped_permission (P-01 Permission name or None), supported, note
# --------------------------------------------------------------------------
CAPABILITY_CATALOGUE: list[dict] = [
    {"name": "internal_reasoning", "category": "internal", "risk_level": "low",
     "approval_level": 0, "action_class": "execute", "mapped_permission": None,
     "supported": True,
     "description": "Internal reasoning over provided inputs via the SHARED P-02 model router / deterministic baseline. Never a per-agent model instance."},
    {"name": "internal_database_read", "category": "internal_data", "risk_level": "low",
     "approval_level": 0, "action_class": "read", "mapped_permission": "read_business_data",
     "supported": True,
     "description": "Read access to internal business/system records through existing repositories."},
    {"name": "internal_database_write", "category": "internal_data", "risk_level": "medium",
     "approval_level": 1, "action_class": "write", "mapped_permission": "modify_business_data",
     "supported": True,
     "description": "Write access to internal business records through existing governed services."},
    {"name": "memory_read", "category": "memory", "risk_level": "low",
     "approval_level": 0, "action_class": "read", "mapped_permission": None,
     "supported": True,
     "description": "Scoped read of the agent's OWN configuration history and previous task references via the P-04 memory interface (P-09 will extend the scopes)."},
    {"name": "memory_write", "category": "memory", "risk_level": "medium",
     "approval_level": 1, "action_class": "write", "mapped_permission": None,
     "supported": False,
     "description": "Persistent memory writes belong to the P-09 memory engine, which is not built. Catalogued, not grantable."},
    {"name": "file_read", "category": "filesystem", "risk_level": "high",
     "approval_level": 2, "action_class": "read", "mapped_permission": None,
     "supported": True,
     "description": "Reads through the P-05 filesystem/documents adapters, inside managed workspaces only (path-validated, Windows rules enforced). Granted per agent via the factory."},
    {"name": "file_write", "category": "filesystem", "risk_level": "high",
     "approval_level": 2, "action_class": "write", "mapped_permission": None,
     "supported": True,
     "description": "Writes through the P-05 filesystem/documents adapters, inside managed workspaces only: atomic writes, integrity hashes, quarantine-based deletion; permanent deletion is Risk 2."},
    {"name": "web_research", "category": "external", "risk_level": "medium",
     "approval_level": 2, "action_class": "read", "mapped_permission": None,
     "supported": True,
     "description": "Governed web research through the P-03 source adapters / opportunity.research handler only (SSRF-guarded, robots-respecting). External action: owner approval required."},
    {"name": "api_read", "category": "external", "risk_level": "high",
     "approval_level": 2, "action_class": "read", "mapped_permission": None,
     "supported": True,
     "description": "Read-only HTTP (GET) through the P-05 API adapter: host allowlist, SSRF guard, redirect re-validation, response caps."},
    {"name": "api_write", "category": "external", "risk_level": "high",
     "approval_level": 2, "action_class": "write", "mapped_permission": None,
     "supported": True,
     "description": "Mutating HTTP (POST/PUT/PATCH/DELETE) through the P-05 API adapter. Risk 2 per call: owner approval or a narrow standing authorization."},
    {"name": "code_generation", "category": "production", "risk_level": "medium",
     "approval_level": 1, "action_class": "write", "mapped_permission": None,
     "supported": False,
     "description": "No code-generation handler exists in this build; generation/execution workflows are P-05/P-06 scope. Catalogued, not grantable."},
    {"name": "sandboxed_code_execution", "category": "execution", "risk_level": "high",
     "approval_level": 2, "action_class": "execute", "mapped_permission": None,
     "supported": True,
     "description": "Controlled Python execution through the P-05 code adapter. Isolation is PROCESS CONTROLS ONLY (temp workspace, scrubbed env, timeout + process-tree kill, caps) — not a strong sandbox; dangerous-pattern screen applies."},
    {"name": "browser_interaction", "category": "external", "risk_level": "high",
     "approval_level": 2, "action_class": "execute", "mapped_permission": None,
     "supported": True,
     "description": "Governed browser sessions through the P-05 browser adapter: domain allowlists, read-only navigation/inspection/extraction via the SSRF-guarded fetch backend. Interactive automation requires a browser engine unavailable in the staging environment and is refused truthfully there."},
    {"name": "external_communication", "category": "external", "risk_level": "high",
     "approval_level": 2, "action_class": "write", "mapped_permission": None,
     "supported": False,
     "description": "No outbound communication channel exists in this build. Catalogued, not grantable."},
    {"name": "financial_data_read", "category": "financial", "risk_level": "medium",
     "approval_level": 1, "action_class": "read", "mapped_permission": "read_business_data",
     "supported": True,
     "description": "Read of EXISTING business/financial records (e.g. P-03 commercial analyses). A Financial Analysis role does NOT imply wallet or transaction authority. The dedicated finance engine is P-07."},
    {"name": "financial_transaction_request", "category": "financial", "risk_level": "high",
     "approval_level": 2, "action_class": "execute", "mapped_permission": "request_financial_operations",
     "supported": True,
     "description": "May REQUEST a financial operation through the P-01 hash-bound approval framework. Requesting is all that exists: no execution path, no wallet access."},
    # --- Level 3: PROHIBITED (§8.3). enabled=False at seed time. ---
    {"name": "reveal_secrets", "category": "prohibited", "risk_level": "critical",
     "approval_level": 3, "action_class": "read", "mapped_permission": None,
     "supported": False, "enabled": False,
     "description": "PROHIBITED: agents never receive raw credentials, keys, passwords or session tokens."},
    {"name": "disable_security_controls", "category": "prohibited", "risk_level": "critical",
     "approval_level": 3, "action_class": "execute", "mapped_permission": None,
     "supported": False, "enabled": False,
     "description": "PROHIBITED: disabling core security restrictions (Constitution Article 0)."},
    {"name": "bypass_approvals", "category": "prohibited", "risk_level": "critical",
     "approval_level": 3, "action_class": "execute", "mapped_permission": None,
     "supported": False, "enabled": False,
     "description": "PROHIBITED: bypassing the owner approval system (Article 0)."},
    {"name": "modify_audit_records", "category": "prohibited", "risk_level": "critical",
     "approval_level": 3, "action_class": "write", "mapped_permission": None,
     "supported": False, "enabled": False,
     "description": "PROHIBITED: modifying or erasing audit records. The audit API is append-only."},
    {"name": "unrestricted_financial_authority", "category": "prohibited", "risk_level": "critical",
     "approval_level": 3, "action_class": "execute", "mapped_permission": None,
     "supported": False, "enabled": False,
     "description": "PROHIBITED: unrestricted financial authority for an agent (Article 0)."},
]

CAPABILITY_BY_NAME: dict[str, dict] = {c["name"]: c for c in CAPABILITY_CATALOGUE}

# --------------------------------------------------------------------------
# Factory settings (§14.2) — stored in system_config under SETTINGS_KEY,
# writable ONLY by owner/governance principals (service-layer enforced).
# Defaults are sized for the target hardware (i7-4712HQ / 16 GB, CPU-only
# inference — see docs/reports/AI_HARDWARE_FEASIBILITY.md).
# --------------------------------------------------------------------------
SETTINGS_KEY = "agent_factory.settings"
SETTINGS_VERSION = "factory-settings-v1"

DEFAULT_SETTINGS: dict = {
    "max_total_agents": 12,
    "max_active_agents": 8,
    "max_agents_per_business": 4,
    "max_child_agents_per_parent": 3,
    "max_delegation_depth": 3,
    "max_concurrent_tasks_per_agent": 2,
    "max_concurrent_inference_requests": 1,
    "creation_rate_limit_per_hour": 10,
    "max_initialization_failures_per_template": 3,
    "idle_suspend_seconds": 3600,
    "health_check_interval_seconds": 300,
    "creation_enabled": True,
    "assignments_enabled": True,
    "safe_mode": False,
    "max_template_memory_budget_mb": 4096,
    "max_template_task_seconds": 3600,
}

# Hard ceilings a template budget may never exceed regardless of settings
# edits within the validated ranges above (validation reads the settings).
BUDGET_FIELDS = (
    "max_concurrent_tasks", "max_task_seconds", "max_retries",
    "max_inference_requests_per_task", "max_child_agents",
    "max_queue_occupancy", "memory_budget_mb",
)

DEFAULT_RESOURCE_BUDGET: dict = {
    "max_concurrent_tasks": 1,
    "max_task_seconds": 300,
    "max_retries": 1,
    "max_inference_requests_per_task": 4,
    "max_child_agents": 2,
    "max_queue_occupancy": 10,
    # ESTIMATED planning figure for a logical agent's share of the shared
    # runtime — logical agents have no dedicated memory. Always labelled
    # "estimated" in metrics, never "measured".
    "memory_budget_mb": 256,
}

# §12.3 health thresholds (deterministic; documented in AGENT_LIFECYCLE.md
# companion monitoring doc and P04_DYNAMIC_AGENT_FACTORY.md).
HEALTH_THRESHOLDS: dict = {
    "failure_rate_warning": 0.25,
    "failure_rate_degraded": 0.5,
    "min_tasks_for_rate": 4,
    "consecutive_failures_failed": 3,
    "unresponsive_timeout_multiplier": 2.0,
}

# --------------------------------------------------------------------------
# Seed templates (§6). Conservative, internal-only capabilities. All are
# validated by the same validator as owner-created templates at seed time;
# a seed that failed validation would be stored as a draft with the
# failure logged (none is expected to).
# --------------------------------------------------------------------------

def _template_config(role: str, mission: str, instruction: str,
                     responsibility: str, capabilities: list[str],
                     handlers: list[str], output_fields: list[str],
                     budget_overrides: dict | None = None) -> dict:
    budget = dict(DEFAULT_RESOURCE_BUDGET)
    if budget_overrides:
        budget.update(budget_overrides)
    return {
        "role": role,
        "agent_type": ROLE_TO_CATEGORY[role],
        "mission": mission,
        "system_instruction": instruction,
        "primary_responsibility": responsibility,
        "secondary_responsibilities": [],
        "input_schema": {"required_fields": ["objective"]},
        "output_schema": {"required_fields": output_fields},
        "allowed_capabilities": capabilities,
        "restricted_capabilities": [],
        "tool_requirements": {"handlers": handlers},
        "model_requirements": {"task_class": "general", "profile_name": None},
        "memory_requirements": {"scopes": ["agent_configuration_history",
                                           "previous_task_references"]},
        "resource_budget": budget,
        "timeout_seconds": 120,
        "retry_policy": {"max_retries": 1},
        "quality_criteria": {"output_schema_valid": True,
                             "evidence_required_for_claims": True},
        "evaluation_rules": {"min_output_fields": len(output_fields)},
        "approval_requirements": {"creation": "level_0"},
        "security_classification": "internal",
    }


_INTERNAL_CAPS = ["internal_reasoning", "internal_database_read", "memory_read"]

SEED_TEMPLATES: list[dict] = [
    {"name": "Research Agent", "category": "intelligence",
     "description": "Governed market/opportunity research over internal records and the P-03 research pipeline.",
     "configuration": _template_config(
         "research_agent",
         "Investigate assigned research questions and return evidence-backed findings.",
         "You are a research agent. Work only from assigned objectives and granted capabilities; cite evidence references for every claim; never invent data.",
         "Conduct assigned research and report findings with evidence references.",
         _INTERNAL_CAPS,
         ["opportunity.research", "core.echo_check", "core.health_snapshot", "core.noop", "core.wait"],
         ["summary", "evidence_refs"])},
    {"name": "Market Analysis Agent", "category": "intelligence",
     "description": "Structured market analysis over internal records.",
     "configuration": _template_config(
         "market_analysis_agent",
         "Analyse markets for assigned opportunities using internal evidence.",
         "You are a market analysis agent. State methodology and assumptions; where market size cannot be established, say so.",
         "Produce market analyses with stated methodology.",
         _INTERNAL_CAPS,
         ["core.echo_check", "core.health_snapshot", "core.noop"],
         ["summary", "methodology"])},
    {"name": "Competitor Analysis Agent", "category": "intelligence",
     "description": "Competitor comparison over internal records.",
     "configuration": _template_config(
         "competitor_analysis_agent",
         "Compare competitors for assigned opportunities using internal evidence.",
         "You are a competitor analysis agent. Compare only on recorded evidence; flag gaps explicitly.",
         "Produce competitor comparisons with evidence references.",
         _INTERNAL_CAPS,
         ["core.echo_check", "core.health_snapshot", "core.noop"],
         ["summary", "evidence_refs"])},
    {"name": "Business Strategy Agent", "category": "strategy",
     "description": "Strategy evaluation and recommendation drafting.",
     "configuration": _template_config(
         "business_strategy_agent",
         "Evaluate strategic options and draft recommendations for owner review.",
         "You are a business strategy agent. Recommendations are proposals for the owner, never decisions; state assumptions and risks.",
         "Draft strategy evaluations with assumptions and risks.",
         _INTERNAL_CAPS,
         ["core.echo_check", "core.noop"],
         ["summary", "recommendation", "risks"])},
    {"name": "Opportunity Evaluation Agent", "category": "strategy",
     "description": "Evaluates P-03 opportunity records against recorded evidence.",
     "configuration": _template_config(
         "opportunity_evaluation_agent",
         "Evaluate discovered opportunities against their recorded evidence.",
         "You are an opportunity evaluation agent. Use only recorded evidence; insufficient evidence must be reported as such.",
         "Evaluate opportunities and report evidence quality.",
         _INTERNAL_CAPS,
         ["opportunity.research", "core.echo_check", "core.noop"],
         ["summary", "evidence_quality"])},
    {"name": "Content Writing Agent", "category": "production",
     "description": "Drafts written content from assigned briefs (drafts only; publishing is not a P-04 capability).",
     "configuration": _template_config(
         "content_writing_agent",
         "Draft content from assigned briefs for human review.",
         "You are a content writing agent. Produce drafts only; never claim publication or external posting.",
         "Draft written content from briefs.",
         ["internal_reasoning", "memory_read"],
         ["core.echo_check", "core.noop"],
         ["summary", "draft"])},
    {"name": "Documentation Agent", "category": "production",
     "description": "Drafts internal documentation from internal records.",
     "configuration": _template_config(
         "documentation_agent",
         "Draft internal documentation grounded in internal records.",
         "You are a documentation agent. Document only what the records show; mark anything unverified.",
         "Draft documentation from internal records.",
         _INTERNAL_CAPS,
         ["core.echo_check", "core.noop"],
         ["summary", "document"])},
    {"name": "Quality Assurance Agent", "category": "operations",
     "description": "Checks outputs against their contracts and records verdicts.",
     "configuration": _template_config(
         "quality_assurance_agent",
         "Verify outputs against expected schemas and quality criteria.",
         "You are a quality assurance agent. A result missing required fields is a failure, not a success; report exactly what was checked.",
         "Validate outputs and record quality verdicts.",
         _INTERNAL_CAPS,
         ["core.health_snapshot", "core.echo_check", "core.noop"],
         ["summary", "verdict", "checks"])},
    {"name": "Financial Analysis Agent", "category": "financial",
     "description": "Analysis over EXISTING financial/business records. No wallet, payment or transaction authority.",
     "configuration": _template_config(
         "financial_analysis_agent",
         "Analyse existing financial records and report findings.",
         "You are a financial analysis agent. You may read existing records only; you have no transaction authority and must never imply otherwise.",
         "Analyse existing financial records.",
         ["internal_reasoning", "internal_database_read", "financial_data_read", "memory_read"],
         ["core.echo_check", "core.noop"],
         ["summary", "figures"])},
    {"name": "Security Review Agent", "category": "governance",
     "description": "Reviews configurations and requests against security policy; advisory only.",
     "configuration": _template_config(
         "security_review_agent",
         "Review agent configurations and capability requests against policy and report findings.",
         "You are a security review agent. You advise; you cannot grant permissions, change policy, or access secrets.",
         "Review configurations against security policy.",
         _INTERNAL_CAPS,
         ["core.health_snapshot", "core.echo_check", "core.noop"],
         ["summary", "findings"])},
]
