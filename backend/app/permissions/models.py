"""Principal and permission vocabulary (P-01 §9.1–9.2)."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


class PrincipalType(str, enum.Enum):
    OWNER = "owner"
    SYSTEM = "system"
    AGENT = "agent"
    SERVICE = "service"
    EXTERNAL = "external"


class Permission(str, enum.Enum):
    READ_SYSTEM_DATA = "read_system_data"
    WRITE_SYSTEM_DATA = "write_system_data"
    SUBMIT_TASKS = "submit_tasks"
    CANCEL_TASKS = "cancel_tasks"
    EXECUTE_TOOLS = "execute_tools"
    READ_BUSINESS_DATA = "read_business_data"
    MODIFY_BUSINESS_DATA = "modify_business_data"
    ACCESS_SENSITIVE_DATA = "access_sensitive_data"
    REQUEST_FINANCIAL_OPERATIONS = "request_financial_operations"
    APPROVE_ACTIONS = "approve_actions"
    MODIFY_SYSTEM_CONFIG = "modify_system_config"
    MANAGE_AGENTS = "manage_agents"


ALL_PERMISSIONS = [p.value for p in Permission]


@dataclass(frozen=True)
class Principal:
    type: PrincipalType
    id: str
    name: str = ""

    def __post_init__(self):
        if not self.id:
            raise ValueError("principal id must not be empty")


@dataclass
class AuthorizationDecision:
    allowed: bool
    reason: str
    matched_rule: str | None = None
    requires_approval: bool = False
    details: dict = field(default_factory=dict)
