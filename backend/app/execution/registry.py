"""Execution Tool Registry (§7).

DB-backed registry seeded from ``constants.TOOL_SEEDS``. A tool becomes
AVAILABLE only when its adapter's health check passes at startup; a tool
whose adapter is degraded (browser: fetch backend up, interactive backend
missing) is DEGRADED; the desktop tool is seeded DISABLED and can never
be flipped available in this environment — enablement is an owner action
on a machine where the adapter genuinely runs (§30 final rule).

Discovery (what agents may see) is a restricted view: descriptions,
actions, input/output contracts, required capabilities, risk — never
configuration references' contents, never credentials (§7).
"""
from __future__ import annotations

from ..core.exceptions import NotFoundError
from ..database.models.execution import ExecutionTool
from ..database.repositories.execution import ExecutionToolRepository
from . import constants as C
from .errors import ToolUnavailableError

# Registry lifecycle (§7). REMOVED is terminal; DISABLED may be re-enabled
# by the owner only through validate (health check), never directly.
TOOL_TRANSITIONS: dict[str, set[str]] = {
    "registered": {"validating", "disabled", "deprecated", "removed"},
    "validating": {"available", "degraded", "disabled"},
    "available": {"degraded", "disabled", "deprecated"},
    "degraded": {"available", "disabled", "deprecated"},
    "disabled": {"validating", "deprecated", "removed"},
    "deprecated": {"removed"},
    "removed": set(),
}


class ToolRegistry:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    # ------------------------------------------------------------------ seed
    def seed_tools(self) -> int:
        session = self._session_factory()
        try:
            repo = ExecutionToolRepository(session)
            existing = {t.name for t in repo.list(limit=500)[0]}
            added = 0
            for seed in C.TOOL_SEEDS:
                if seed["name"] in existing:
                    continue
                required = sorted({cap for a in seed["actions"]
                                   for cap in a["required_capabilities"]})
                repo.add(ExecutionTool(
                    name=seed["name"], description=seed["description"],
                    category=seed["category"], version=seed["version"],
                    adapter_type=seed["adapter_type"], actions=seed["actions"],
                    input_schema=seed["input_schema"], output_schema=seed["output_schema"],
                    required_capabilities=required,
                    risk_level=max((a["risk_level"] for a in seed["actions"]), default=0),
                    approval_level=max((a["approval_level"] for a in seed["actions"]), default=0),
                    supported_os=seed["supported_os"],
                    resource_requirements=seed["resource_requirements"],
                    timeout_default=seed["timeout_default"],
                    retry_eligible=seed["retry_eligible"],
                    idempotency_supported=seed["idempotency_supported"],
                    status=seed.get("seed_status", "registered"),
                    health_status=seed.get("seed_health", "unknown"),
                    health_details={}, config_ref=seed["config_ref"]))
                added += 1
            return added
        finally:
            session.close()

    def apply_health(self, tool_name: str, *, status: str, health_status: str,
                     details: dict) -> ExecutionTool:
        """Record an adapter health-check outcome (startup + validate).
        Health can never resurrect a tool the owner disabled."""
        session = self._session_factory()
        try:
            repo = ExecutionToolRepository(session)
            tool = repo.get_by_name(tool_name)
            if tool is None:
                raise NotFoundError(f"tool '{tool_name}' is not registered")
            if tool.status == "disabled" and status != "disabled":
                tool.health_status = health_status
                tool.health_details = details
                return repo.save(tool)
            tool.status = status
            tool.health_status = health_status
            tool.health_details = details
            return repo.save(tool)
        finally:
            session.close()

    def disable(self, tool_name: str) -> ExecutionTool:
        session = self._session_factory()
        try:
            repo = ExecutionToolRepository(session)
            tool = repo.get_by_name(tool_name)
            if tool is None:
                raise NotFoundError(f"tool '{tool_name}' is not registered")
            tool.status = "disabled"
            tool.health_status = "disabled"
            return repo.save(tool)
        finally:
            session.close()

    # ------------------------------------------------------------------ read
    def get_tool(self, name: str) -> ExecutionTool:
        session = self._session_factory()
        try:
            tool = ExecutionToolRepository(session).get_by_name(name)
            if tool is None:
                raise NotFoundError(f"tool '{name}' is not registered")
            return tool
        finally:
            session.close()

    def list_tools(self, limit: int = 100, offset: int = 0):
        session = self._session_factory()
        try:
            return ExecutionToolRepository(session).list(limit, offset)
        finally:
            session.close()

    @staticmethod
    def action_spec(tool: ExecutionTool, action_name: str) -> dict:
        for action in tool.actions or []:
            if action["name"] == action_name:
                return action
        raise ToolUnavailableError(
            f"tool '{tool.name}' has no action '{action_name}'",
            details={"error_category": "ACTION_UNKNOWN", "tool": tool.name,
                     "action": action_name})

    @staticmethod
    def assert_usable(tool: ExecutionTool) -> None:
        if tool.status == "disabled":
            raise ToolUnavailableError(
                f"tool '{tool.name}' is disabled in this environment",
                details={"error_category": "TOOL_DISABLED", "tool": tool.name,
                         "health": tool.health_status,
                         "health_details": tool.health_details})
        if tool.status not in ("available", "degraded"):
            raise ToolUnavailableError(
                f"tool '{tool.name}' is not available (status '{tool.status}')",
                details={"error_category": "TOOL_NOT_AVAILABLE", "tool": tool.name})

    # -------------------------------------------------------------- discovery
    @staticmethod
    def discovery_view(tool: ExecutionTool) -> dict:
        """The restricted §7 discovery view — safe to show an agent."""
        return {
            "name": tool.name, "description": tool.description,
            "category": tool.category, "version": tool.version,
            "adapter_type": tool.adapter_type,
            "actions": [{"name": a["name"], "risk_level": a["risk_level"],
                         "required_capabilities": a["required_capabilities"],
                         "approval_level": a["approval_level"],
                         "description": a.get("description", "")}
                        for a in tool.actions or []],
            "required_capabilities": tool.required_capabilities,
            "risk_level": tool.risk_level,
            "input_schema": tool.input_schema, "output_schema": tool.output_schema,
            "status": tool.status, "health_status": tool.health_status,
        }

    @staticmethod
    def admin_view(tool: ExecutionTool) -> dict:
        data = ToolRegistry.discovery_view(tool)
        data.update({
            "id": tool.id, "supported_os": tool.supported_os,
            "resource_requirements": tool.resource_requirements,
            "timeout_default": tool.timeout_default,
            "retry_eligible": tool.retry_eligible,
            "idempotency_supported": tool.idempotency_supported,
            "health_details": tool.health_details,
            "config_ref": tool.config_ref,
        })
        return data
