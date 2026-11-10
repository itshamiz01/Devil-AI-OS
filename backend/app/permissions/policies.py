"""Default role policies (P-01 §9). Deny-by-default: anything not granted
here or by an explicit DB allow rule is denied. DB rules can add allows or
explicit denies; an explicit deny always wins (enforced in engine.py).
"""
from __future__ import annotations

from .models import ALL_PERMISSIONS, PrincipalType

ROLE_DEFAULTS: dict[str, set[str]] = {
    PrincipalType.OWNER.value: set(ALL_PERMISSIONS),
    PrincipalType.SYSTEM.value: {
        "read_system_data", "write_system_data", "submit_tasks", "cancel_tasks",
        "execute_tools", "read_business_data", "modify_business_data",
    },
    PrincipalType.SERVICE.value: {
        "read_system_data", "submit_tasks",
    },
    PrincipalType.AGENT.value: {
        "read_system_data", "submit_tasks", "cancel_tasks", "execute_tools",
        "read_business_data",
    },
    PrincipalType.EXTERNAL.value: set(),
}

# Permissions that always require a human approval in addition to a grant.
APPROVAL_REQUIRED_PERMISSIONS = {
    "request_financial_operations",
    "modify_system_config",
    "access_sensitive_data",
}
