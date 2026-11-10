"""Execution Policy Engine + Capability Validator (§§8/8.1/17).

Deterministic backend code — an LLM never classifies its own action as
authorized (§8.1). The ten §8.1 checks run IN ORDER and the first failure
stops evaluation; every check outcome is recorded on the decision so a
refusal is always explainable:

1. agent identity (the caller may act for this agent; the agent exists)
2. agent status (assignable lifecycle state)
3. assigned task (a named task exists and is not another agent's)
4. required capabilities (live P-04 grants via CapabilityService)
5. requested scope (workspace authorization / host & domain allowlists)
6. tool status (registry: available/degraded only)
7. risk category (tool action risk, escalated by the §10.4 code screen)
8. approval status (Risk >= 2 needs a verified approval or a matching
   standing authorization; Risk 3 is rejected outright — no path exists)
9. resource limits (timeout ceiling, payload size ceiling)
10. policy restrictions (mode gates, execution emergency stop,
    simulation = no side effects)

Priority NEVER overrides risk (§8): priority is not an input to any check.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from urllib.parse import urlparse

from ..agents.capabilities import CapabilityService
from ..agents.lifecycle import ASSIGNABLE_STATES
from ..database.models.base import utcnow
from ..database.models.core import Agent, Task
from ..database.models.execution import ExecutionTool, StandingAuthorization
from ..database.repositories.core import TaskRepository
from ..database.repositories.execution import StandingAuthorizationRepository
from ..permissions.engine import PermissionEngine
from ..permissions.models import Principal, PrincipalType
from .workspaces import WorkspaceManager

READ_ACTIONS = {
    "filesystem": {"list", "read", "metadata", "hash", "search"},
    "documents": {"read_text", "read_csv", "summarize_csv"},
}

# Actions a standing authorization may NEVER cover (§17 + audit §7).
STANDING_AUTH_EXCLUDED_ACTIONS = {"delete_permanent"}


@dataclass
class PolicyDecision:
    allowed: bool = False
    requires_approval: bool = False
    prohibited: bool = False
    risk_level: int = 0
    escalated: bool = False
    escalation_reasons: list[str] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)
    reason: str = ""
    standing_authorization_id: str | None = None

    def record(self, check: str, passed: bool, reason: str) -> bool:
        self.checks.append({"check": check, "passed": passed, "reason": reason})
        if not passed and not self.reason:
            self.reason = reason
        return passed


@dataclass
class PolicyContext:
    principal: Principal
    agent: Agent
    tool: ExecutionTool
    action_spec: dict
    parameters: dict
    requested_scope: str | None
    business_ref: str | None
    task_id: str | None
    mode: str
    settings: dict
    approval_satisfied: bool = False  # verified by the service (hash binding)
    code_screen: dict | None = None  # {"hard": [...], "soft": [...]} for code runs


def host_matches(host: str, allowlist: list[str]) -> bool:
    """Exact host match, or a ``*.example.com`` entry matching subdomains."""
    host = (host or "").strip().lower()
    for entry in allowlist or []:
        entry = str(entry).strip().lower()
        if entry.startswith("*."):
            if host.endswith(entry[1:]) and host != entry[2:]:
                return True
        elif host == entry:
            return True
    return False


def match_standing_authorization(rows: list[StandingAuthorization], *,
                                 tool_name: str, action_name: str, scope: str | None,
                                 agent_id: str, agent_role: str | None,
                                 now: dt.datetime | None = None) -> StandingAuthorization | None:
    """Narrow matching (§17): exact tool+action, scope prefix, subject is
    the agent or its role, not expired/revoked/exhausted, and never for an
    excluded action."""
    if action_name in STANDING_AUTH_EXCLUDED_ACTIONS:
        return None
    now = now or utcnow()
    for row in rows:
        if row.status != "active" or row.revoked_at is not None:
            continue
        if row.tool_name != tool_name or row.action_name != action_name:
            continue
        expires = row.expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=dt.timezone.utc)
        if expires is not None and expires <= now:
            continue
        if row.uses >= row.max_uses:
            continue
        if row.agent_id is not None and row.agent_id != agent_id:
            continue
        if row.role is not None and row.role != agent_role:
            continue
        if scope is not None and not scope.startswith(row.scope_pattern):
            continue
        return row
    return None


class ExecutionPolicy:
    def __init__(self, session_factory, permissions: PermissionEngine,
                 capabilities: CapabilityService, workspaces: WorkspaceManager):
        self._session_factory = session_factory
        self._permissions = permissions
        self._capabilities = capabilities
        self._workspaces = workspaces

    # ------------------------------------------------------------- evaluation
    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        decision = PolicyDecision()
        action_name = ctx.action_spec["name"]
        base_risk = int(ctx.action_spec["risk_level"])
        decision.risk_level = base_risk

        # 10 (partly first): global restrictions that deny everything.
        if ctx.settings.get("emergency_stop") or ctx.mode == "emergency":
            decision.record("policy_restrictions", False,
                            "execution is halted (emergency stop / emergency mode)")
            return decision

        # 1. Agent identity: the caller must be entitled to act for the agent.
        if not self._identity_ok(ctx):
            decision.record("agent_identity", False,
                            "caller is not entitled to submit execution requests for this agent")
            return decision
        decision.record("agent_identity", True, "caller entitled; agent verified from the registry")

        # 2. Agent status.
        if ctx.agent.status not in ASSIGNABLE_STATES:
            decision.record("agent_status", False,
                            f"agent is in lifecycle state '{ctx.agent.status}' and cannot execute")
            return decision
        decision.record("agent_status", True, f"agent state '{ctx.agent.status}' is assignable")

        # 3. Assigned task.
        if ctx.task_id is not None:
            task = self._get_task(ctx.task_id)
            if task is None:
                decision.record("assigned_task", False, f"task '{ctx.task_id}' does not exist")
                return decision
            if task.assigned_agent_id is not None and task.assigned_agent_id != ctx.agent.id:
                decision.record("assigned_task", False,
                                "task is assigned to a different agent")
                return decision
            decision.record("assigned_task", True, "task exists and is not another agent's")
        else:
            decision.record("assigned_task", True, "no task link requested")

        # 4. Required capabilities — live P-04 grants, never role inference.
        required = list(ctx.action_spec.get("required_capabilities") or [])
        missing = [cap for cap in required
                   if not self._capabilities.has_capability(ctx.agent.id, cap)]
        if missing:
            decision.record("capabilities", False,
                            f"agent lacks required capabilities: {', '.join(missing)}")
            return decision
        decision.record("capabilities", True,
                        "all required capabilities held" if required else "no capabilities required")

        # 5. Requested scope.
        scope_ok, scope_reason = self._scope_ok(ctx)
        if not scope_ok:
            decision.record("requested_scope", False, scope_reason)
            return decision
        decision.record("requested_scope", True, scope_reason)

        # 6. Tool status.
        if ctx.tool.status not in ("available", "degraded"):
            decision.record("tool_status", False,
                            f"tool '{ctx.tool.name}' status is '{ctx.tool.status}'")
            return decision
        decision.record("tool_status", True, f"tool status '{ctx.tool.status}'")

        # 7. Risk category (+ §10.4 escalation for code).
        risk = base_risk
        if ctx.code_screen is not None:
            if ctx.code_screen.get("hard"):
                decision.risk_level = 3
                decision.prohibited = True
                decision.record(
                    "risk_category", False,
                    "code screen: prohibited constructs detected "
                    f"({', '.join(ctx.code_screen['hard'])}) — Risk 3, rejected")
                return decision
            if ctx.code_screen.get("soft"):
                risk = max(risk, 2)
                decision.escalated = True
                decision.escalation_reasons = list(ctx.code_screen["soft"])
        decision.risk_level = risk
        if risk >= 3:
            decision.prohibited = True
            decision.record("risk_category", False,
                            "Risk 3 operations are rejected by the normal execution system (§8)")
            return decision
        decision.record("risk_category", True,
                        f"risk level {risk}" + (" (escalated by code screen)" if decision.escalated else ""))

        # 8. Approval status.
        if risk >= 2 and not ctx.approval_satisfied:
            standing = self._find_standing_authorization(ctx)
            if standing is not None:
                decision.standing_authorization_id = standing.id
                decision.record("approval_status", True,
                                f"covered by standing authorization {standing.id} "
                                f"({standing.uses}/{standing.max_uses} uses)")
            else:
                decision.requires_approval = True
                decision.record("approval_status", False,
                                "Risk 2 action requires owner approval "
                                "(no verified approval, no matching standing authorization)")
                return decision
        else:
            decision.record("approval_status", True,
                            "approval verified" if risk >= 2 else "no approval required at this risk level")

        # 9. Resource limits (payload ceilings; concurrency lives in the scheduler).
        payload_bytes = len(json.dumps(ctx.parameters, default=str).encode("utf-8"))
        if payload_bytes > int(ctx.settings["max_input_bytes"]):
            decision.record("resource_limits", False,
                            f"request payload {payload_bytes} bytes exceeds the "
                            f"{ctx.settings['max_input_bytes']}-byte ceiling")
            return decision
        decision.record("resource_limits", True, "payload within ceilings")

        # 10. Mode restrictions: simulation permits only real read actions.
        if ctx.mode == "simulation" and not self._is_read_action(ctx):
            decision.record("policy_restrictions", False,
                            "simulation mode: side-effecting execution is refused "
                            "(reads and validation only)")
            return decision
        decision.record("policy_restrictions", True, "no active restriction blocks this request")

        decision.allowed = True
        decision.reason = "all policy checks passed"
        return decision

    # ---------------------------------------------------------------- helpers
    def _identity_ok(self, ctx: PolicyContext) -> bool:
        principal = ctx.principal
        if principal.type is PrincipalType.OWNER:
            return True
        if principal.type is PrincipalType.AGENT:
            return principal.id == ctx.agent.id
        decision = self._permissions.check(principal, "manage_agents")
        return decision.allowed

    def _get_task(self, task_id: str) -> Task | None:
        session = self._session_factory()
        try:
            return TaskRepository(session).get(task_id)
        finally:
            session.close()

    @staticmethod
    def _is_read_action(ctx: PolicyContext) -> bool:
        reads = READ_ACTIONS.get(ctx.tool.adapter_type)
        if reads is not None:
            return ctx.action_spec["name"] in reads
        if ctx.tool.adapter_type == "api":
            return ctx.action_spec["name"] == "get"
        if ctx.tool.adapter_type == "browser":
            return ctx.action_spec["name"] in (
                "open_session", "navigate", "inspect", "extract", "screenshot", "close_session")
        return False

    def _scope_ok(self, ctx: PolicyContext) -> tuple[bool, str]:
        adapter = ctx.tool.adapter_type
        action = ctx.action_spec["name"]
        params = ctx.parameters
        if adapter in ("filesystem", "documents"):
            if adapter == "filesystem" and action == "delete_permanent":
                # The single governed exception to quarantine read-only:
                # permanent deletion applies ONLY inside quarantine, and
                # the Risk-2 hash-bound approval (checked later) is the
                # control — standing authorizations never cover it.
                if str(params.get("workspace") or "") != "quarantine":
                    return False, ("permanent deletion applies only to files "
                                   "already in the quarantine workspace")
                return True, "quarantine scope for governed permanent deletion"
            write = action not in READ_ACTIONS.get(adapter, set())
            names = []
            if adapter == "filesystem" and action in ("copy", "move"):
                names = [(params.get("source_workspace"), False),
                         (params.get("dest_workspace"), True)]
            else:
                names = [(params.get("workspace"), write)]
            for name, is_write in names:
                if not name:
                    return False, f"action '{action}' requires a workspace parameter"
                try:
                    workspace = self._workspaces.get_workspace(str(name))
                except Exception as exc:
                    return False, str(exc)
                if not WorkspaceManager.is_authorized(
                        workspace, ctx.agent.id, write=is_write,
                        business_ref=ctx.business_ref):
                    return False, (f"agent is not authorized for workspace '{name}' "
                                   f"({'write' if is_write else 'read'})")
            return True, "workspace scope authorized"
        if adapter == "api":
            url = str(params.get("url") or "")
            host = (urlparse(url).hostname or "").lower()
            if not host:
                return False, "API request has no host"
            if not host_matches(host, list(ctx.settings.get("api_allowlist") or [])):
                return False, f"host '{host}' is not on the owner-governed API allowlist"
            return True, f"host '{host}' allowlisted"
        if adapter == "browser":
            if action in ("navigate",):
                url = str(params.get("url") or "")
                host = (urlparse(url).hostname or "").lower()
                if not host:
                    return False, "browser navigation has no host"
                session_domains = params.get("_session_allowed_domains")
                if session_domains is not None and not host_matches(host, list(session_domains)):
                    return False, f"domain '{host}' is outside the session's allowed domains"
                allowlist = list(ctx.settings.get("browser_allowlist") or [])
                if allowlist and not host_matches(host, allowlist):
                    return False, f"domain '{host}' is not on the owner-governed browser allowlist"
                return True, f"domain '{host}' within session scope"
            return True, "session-scoped action"
        return True, "no scope constraint for this adapter"

    def _find_standing_authorization(self, ctx: PolicyContext) -> StandingAuthorization | None:
        if ctx.action_spec["name"] in STANDING_AUTH_EXCLUDED_ACTIONS:
            return None
        session = self._session_factory()
        try:
            rows = StandingAuthorizationRepository(session).active()
        finally:
            session.close()
        return match_standing_authorization(
            rows, tool_name=ctx.tool.name, action_name=ctx.action_spec["name"],
            scope=ctx.requested_scope, agent_id=ctx.agent.id, agent_role=ctx.agent.role)
