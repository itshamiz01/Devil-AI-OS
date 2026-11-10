"""Template validation (§6): a template must pass these deterministic
rules before it can be published or produce an agent. Validation is pure
code over the configuration dict plus catalogue/profile lookups — never
model judgement. Returns a list of human-readable errors (empty = valid).
"""
from __future__ import annotations

from .constants import BUDGET_FIELDS, ROLE_TO_CATEGORY

REQUIRED_TEXT_FIELDS = ("mission", "system_instruction", "primary_responsibility")


def validate_template_configuration(
    config: dict,
    *,
    capability_levels: dict[str, int | None],
    model_profile_names: set[str],
    ceilings: dict,
) -> list[str]:
    """``capability_levels`` maps capability name -> approval level, with
    None for names absent from the catalogue. ``ceilings`` carries the
    factory limits from the current factory settings."""
    errors: list[str] = []
    if not isinstance(config, dict):
        return ["configuration must be an object"]

    role = config.get("role")
    if not role or not isinstance(role, str):
        errors.append("role is required")
    agent_type = config.get("agent_type")
    if not agent_type or not isinstance(agent_type, str):
        errors.append("agent_type (category) is required")
    elif role in ROLE_TO_CATEGORY and agent_type != ROLE_TO_CATEGORY[role]:
        errors.append(
            f"agent_type '{agent_type}' does not match the taxonomy category "
            f"'{ROLE_TO_CATEGORY[role]}' for role '{role}'")

    for field_name in REQUIRED_TEXT_FIELDS:
        value = config.get(field_name)
        if not value or not isinstance(value, str) or not value.strip():
            errors.append(f"{field_name} is required and must be non-empty text")

    allowed = config.get("allowed_capabilities") or []
    restricted = config.get("restricted_capabilities") or []
    if not isinstance(allowed, list) or not isinstance(restricted, list):
        errors.append("allowed_capabilities and restricted_capabilities must be lists")
        allowed, restricted = [], []
    for name in allowed:
        level = capability_levels.get(name)
        if level is None:
            errors.append(f"allowed capability '{name}' is not in the capability catalogue")
        elif level >= 3:
            errors.append(
                f"allowed capability '{name}' is PROHIBITED (approval level 3) "
                "and can never appear in a template")
    overlap = sorted(set(allowed) & set(restricted))
    if overlap:
        errors.append(f"capabilities cannot be both allowed and restricted: {overlap}")
    for name in restricted:
        if capability_levels.get(name) is None:
            errors.append(f"restricted capability '{name}' is not in the capability catalogue")

    tools = (config.get("tool_requirements") or {}).get("handlers") or []
    if not isinstance(tools, list) or not tools:
        errors.append("tool_requirements.handlers must be a non-empty list of handler names")
    elif any(not isinstance(h, str) or not h for h in tools):
        errors.append("tool_requirements.handlers must contain handler name strings")

    model_req = config.get("model_requirements") or {}
    profile_name = model_req.get("profile_name")
    if profile_name is not None and profile_name not in model_profile_names:
        errors.append(
            f"model_requirements.profile_name '{profile_name}' does not match an "
            "existing model profile")

    budget = config.get("resource_budget") or {}
    if not isinstance(budget, dict) or not budget:
        errors.append("resource_budget is required")
    else:
        for field_name in BUDGET_FIELDS:
            value = budget.get(field_name)
            if value is None:
                errors.append(f"resource_budget.{field_name} is required")
            elif not isinstance(value, (int, float)) or value < 0:
                errors.append(f"resource_budget.{field_name} must be a non-negative number")
        if isinstance(budget.get("max_concurrent_tasks"), (int, float)) and \
                budget["max_concurrent_tasks"] > ceilings["max_concurrent_tasks_per_agent"]:
            errors.append("resource_budget.max_concurrent_tasks exceeds the factory ceiling")
        if isinstance(budget.get("max_task_seconds"), (int, float)) and \
                budget["max_task_seconds"] > ceilings["max_template_task_seconds"]:
            errors.append("resource_budget.max_task_seconds exceeds the factory ceiling")
        if isinstance(budget.get("memory_budget_mb"), (int, float)) and \
                budget["memory_budget_mb"] > ceilings["max_template_memory_budget_mb"]:
            errors.append("resource_budget.memory_budget_mb exceeds the factory ceiling")
        if isinstance(budget.get("max_retries"), (int, float)) and budget["max_retries"] > 10:
            errors.append("resource_budget.max_retries exceeds the platform maximum of 10")

    timeout = config.get("timeout_seconds")
    if timeout is None or not isinstance(timeout, (int, float)) or timeout <= 0:
        errors.append("timeout_seconds must be a positive number")

    output_schema = config.get("output_schema") or {}
    required_fields = output_schema.get("required_fields")
    if not isinstance(required_fields, list) or not required_fields or \
            any(not isinstance(f, str) or not f for f in required_fields):
        errors.append("output_schema.required_fields must be a non-empty list of field names")

    classification = config.get("security_classification")
    if classification is not None and classification not in ("internal", "restricted", "public"):
        errors.append("security_classification must be one of internal|restricted|public")

    return errors


def validate_output_contract(result: dict | None, expected_output: dict) -> dict:
    """§9.4 output contract: a result missing required fields is NOT a
    success, whatever status the executor claimed."""
    required = (expected_output or {}).get("required_fields") or []
    if not required:
        return {"valid": True, "missing_fields": [], "checked_fields": []}
    if not isinstance(result, dict):
        return {"valid": False, "missing_fields": list(required),
                "checked_fields": list(required),
                "reason": "result is not an object"}
    missing = [f for f in required if f not in result or result.get(f) is None]
    return {"valid": not missing, "missing_fields": missing,
            "checked_fields": list(required)}
