"""Tool Registry view (P-02).

Wraps the P-01 HandlerRegistry with permission metadata. This is a VIEW,
not a second execution path: validation and execution still happen inside
the P-01 registry / task manager. No tool can be added at runtime by a
mission, a plan, or a model — the registry contents are code, and code is
governance (Article 0).

All four P-01 built-in handlers are read-only internal utilities, so they
are classified L0/L1 (observe/prepare) with the ``execute_tools``
permission. No L2+ tool exists yet; when one is added it must be declared
here and will then route plan approval through the P-01 approvals flow.
"""
from __future__ import annotations

from ..tasks.handlers import HandlerRegistry

TOOL_METADATA: dict[str, dict] = {
    "core.noop": {
        "level": "L0", "permission": "execute_tools", "task_class": "standard",
        "description": "No-op liveness probe for the governed execution path.",
    },
    "core.echo_check": {
        "level": "L1", "permission": "execute_tools", "task_class": "standard",
        "description": "Echoes a validated payload back; used as a task-system self-test.",
    },
    "core.health_snapshot": {
        "level": "L0", "permission": "execute_tools", "task_class": "fast",
        "description": "Returns current resource usage and database health from the monitor.",
    },
    "core.wait": {
        "level": "L1", "permission": "execute_tools", "task_class": "standard",
        "description": "Bounded sleep (<=10s); exists so timing behaviour is testable.",
    },
    "opportunity.research": {
        "level": "L1", "permission": "execute_tools", "task_class": "standard",
        "description": "P-03 evidence collection for one research session, from registered sources only.",
    },
}

DEFAULT_METADATA = {
    "level": "L1", "permission": "execute_tools", "task_class": "standard",
    "description": "",
}

# Levels at or above this require the P-01 approvals flow before execution.
APPROVAL_REQUIRED_LEVELS = {"L2", "L3", "L4"}


class ToolRegistryView:
    def __init__(self, registry: HandlerRegistry):
        self._registry = registry

    @property
    def registry(self) -> HandlerRegistry:
        return self._registry

    def has(self, name: str) -> bool:
        return self._registry.has(name)

    def metadata(self, name: str) -> dict:
        return {**DEFAULT_METADATA, **TOOL_METADATA.get(name, {})}

    def level(self, name: str) -> str:
        return self.metadata(name)["level"]

    def permission(self, name: str) -> str:
        return self.metadata(name)["permission"]

    def requires_approval(self, name: str) -> bool:
        return self.level(name) in APPROVAL_REQUIRED_LEVELS

    def validate_payload(self, name: str, payload: dict) -> dict:
        return self._registry.validate_payload(name, payload)

    def list_tools(self) -> list[dict]:
        return [
            {"name": name, **self.metadata(name)}
            for name in self._registry.names()
        ]
