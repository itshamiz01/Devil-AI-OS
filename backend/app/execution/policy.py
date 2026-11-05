"""Execution policy: the deterministic boundary of §8 and §8.1.

Nothing in this module asks a model anything. Whether an action may run is
decided by ten checks, in the order §8.1 lists them, stopping at the first
failure, and a failure names the check that failed - the same discipline the
assignment ledger applies to its nine rules, for the same reason: a caller told
only "no" cannot tell a fixable no (grant a capability) from a permanent one
(this action is prohibited), and those need different responses.

Three properties are worth stating because later stages will lean on them.

**Risk is computed here, never read from the request.** The request model has
no risk field. Classification comes from the tool's registered risk and the
action name, so an agent cannot reclassify its own work by describing it
differently, and a high priority cannot lower a classification - §8 says a
high-priority task must never override risk, so priority is read only by the
resource check, where it decides who waits, never by the risk check.

**Risk 3 has no approval path.** A prohibited action is refused before any
approval is consulted, and `classify_risk` returns 3 from the code-level
prohibition list whatever the tool declares. That mirrors the level-3
capability prohibitions in P-04: a prohibition enforced from a literal cannot
be lifted by editing a row.

**Two gates currently always refuse, and say so.** `external_execution_enabled`
is locked false by `Settings.validate_phase_flags` (the P-01 validator refuses
to start with it on), so every `api` and `browser` adapter fails the policy
restrictions check in this build. That is not a policy bug to be fixed here: it
is the phase boundary, and the check exists so the refusal is recorded against
the request rather than discovered when an adapter misbehaves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..agents.schemas import ASSIGNABLE_AGENT_STATES
from ..core.config import Settings
from .schemas import (
    ADAPTERS_UNSUPPORTED_HERE,
    PROHIBITED_ACTIONS,
    RISK_TO_LEVEL,
    ROUTABLE_TOOL_STATES,
)

__all__ = [
    "POLICY_CHECKS",
    "APPROVAL_ACTION",
    "ExecutionCheck",
    "RequestFacts",
    "PolicyEvaluation",
    "ExecutionPolicy",
    "classify_risk",
    "approval_required",
    "binding_parameters",
    "find_standing_authorization",
]

#: §8.1's ten verifications, in the brief's order. Named so a refusal can cite
#: the same list the brief enumerates, and so a test can assert the order.
POLICY_CHECKS = (
    "agent_identity",
    "agent_status",
    "assigned_task",
    "required_capabilities",
    "requested_scope",
    "tool_status",
    "risk_category",
    "approval_status",
    "resource_limits",
    "policy_restrictions",
)

#: The action string every execution approval binds to. One string for every
#: execution approval means the approval queue reads uniformly, and the binding
#: hash (over tool, action, parameters and scope) is what distinguishes one
#: approval from another.
APPROVAL_ACTION = "execution.execute"

#: Adapters whose effects leave this machine. Both are gated on
#: `external_execution_enabled`; see the module docstring for why that gate
#: currently never opens.
EXTERNAL_ADAPTERS = frozenset({"api", "browser"})

#: Priority at or above which work counts as essential under resource pressure.
#: Tasks carry an `essential` flag; execution requests carry only a priority,
#: so the top of the priority range stands in for it, and the mapping is stated
#: here rather than implied.
ESSENTIAL_PRIORITY = 9


@dataclass
class ExecutionCheck:
    """One §8.1 verification and the detail that decided it."""

    name: str
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class RequestFacts:
    """Everything policy needs, normalized from a submission or a stored row.

    Building one of these is the only place that knows whether the facts came
    from `ExecutionRequestInput` or from an `ExecutionRequest` being retried,
    so the checks themselves never branch on it.
    """

    task_id: str
    tool_id: str
    action_name: str
    action_parameters: dict[str, Any] = field(default_factory=dict)
    requested_scope: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    priority: int = 5
    request_id: str | None = None


@dataclass
class PolicyEvaluation:
    """A decision plus the checks behind it.

    `requires_approval` is distinct from a refusal: the request is well-formed
    and permitted in principle, and is waiting for a person. Collapsing the two
    would make an owner-approval wait indistinguishable from a prohibition in
    every downstream count.
    """

    allowed: bool
    risk: int
    reason: str = ""
    requires_approval: bool = False
    standing_authorization_id: str | None = None
    checks: list[ExecutionCheck] = field(default_factory=list)

    @property
    def risk_name(self) -> str:
        return RISK_TO_LEVEL.get(self.risk, "UNKNOWN")

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
            "risk_level": self.risk,
            "risk_name": self.risk_name,
            "reason": self.reason,
            "standing_authorization_id": self.standing_authorization_id,
            "checks": [c.as_dict() for c in self.checks],
        }


# --------------------------------------------------------------------------- #
# Pure classification helpers
# --------------------------------------------------------------------------- #
def classify_risk(tool_risk: int, action_name: str) -> int:
    """The §8 class of an action, from the tool's declaration and the action.

    A prohibited action name is Risk 3 whatever the tool claims, so a tool
    registered at Risk 0 cannot launder a prohibited action by declaring itself
    safe. Anything else takes the tool's registered class: the registry is
    where an action's risk is declared, by a person, at registration.
    """
    if action_name in PROHIBITED_ACTIONS:
        return 3
    return int(tool_risk)


def approval_required(risk: int, tool: Any) -> bool:
    """§8: Risk 2 requires owner approval. A tool may also declare that it
    requires an owner-level approval whatever its risk class, and that
    declaration is honoured rather than overridden by a lower computed risk."""
    if risk >= 2:
        return True
    return int(getattr(tool, "required_approval_level", 0) or 0) >= 2


def binding_parameters(facts: RequestFacts) -> dict[str, Any]:
    """What an execution approval's payload hash commits to.

    Tool, action, parameters and scope: the four things that, if any changed,
    would make the approved action a different action from the executed one.
    The approval service hashes these with the action string and resource, so
    verifying the binding later proves the request being run is the request
    that was approved, not merely a similar one.
    """
    return {
        "tool_id": facts.tool_id,
        "action_name": facts.action_name,
        "action_parameters": dict(facts.action_parameters or {}),
        "requested_scope": facts.requested_scope,
    }


def _matches(pattern: Any, value: str) -> bool:
    return pattern in (None, "", "*") or str(pattern) == value


def find_standing_authorization(entries: Any, *, agent_id: str, tool_id: str,
                                action_name: str, scope: str,
                                now: datetime) -> dict[str, Any] | None:
    """The standing authorization covering this request, if one does (§17).

    An entry matches when it names this agent (or any), this tool (or any),
    this action (or any), a scope that covers the requested one, is unexpired
    and is not revoked. Scope coverage is prefix containment: an authorization
    for `workspace:reports` covers `workspace:reports/daily` and does not
    cover `workspace:other`. Anything malformed is skipped rather than
    raised on - a configuration entry that does not parse must fail closed
    (no match) without taking the policy engine down with it.
    """
    if not isinstance(entries, dict):
        return None
    authorizations = entries.get("authorizations")
    if not isinstance(authorizations, list):
        return None
    for entry in authorizations:
        if not isinstance(entry, dict) or entry.get("revoked"):
            continue
        if not _matches(entry.get("agent_id"), agent_id):
            continue
        if not _matches(entry.get("tool_id"), tool_id):
            continue
        if not _matches(entry.get("action_name"), action_name):
            continue
        granted_scope = str(entry.get("scope") or "")
        if granted_scope not in ("", "*") and not (
                scope == granted_scope or scope.startswith(granted_scope.rstrip("/") + "/")
                or scope.startswith(granted_scope + ":")):
            continue
        expires = entry.get("expires_at")
        if expires:
            try:
                expiry = datetime.fromisoformat(str(expires))
            except ValueError:
                continue
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= now:
                continue
        return entry
    return None


# --------------------------------------------------------------------------- #
# The ten checks
# --------------------------------------------------------------------------- #
class ExecutionPolicy:
    """Runs §8.1's checks. Collaborators are optional in the same way the
    assignment service's are: a missing authority fails closed for the checks
    that need it, rather than the engine being unbuildable in a test."""

    def __init__(self, db: Any, settings: Settings, *, capabilities: Any = None,
                 approvals: Any = None, monitor: Any = None,
                 emergency: Any = None) -> None:
        self.db = db
        self.settings = settings
        self.capabilities = capabilities
        self.approvals = approvals
        self.monitor = monitor
        self.emergency = emergency

    async def evaluate(self, *, principal_id: str, agent: Any, task: Any,
                       tool: Any, facts: RequestFacts,
                       assignment_evidence: str | None,
                       approval: Any = None,
                       standing_entries: Any = None,
                       standing_uses: dict[str, int] | None = None,
                       now: datetime | None = None) -> PolicyEvaluation:
        """Evaluate one request. Rows are inputs, not lookups: the caller owns
        loading, so a refusal for a row that does not exist is the caller's to
        make before a request row can be written against it."""
        now = now or datetime.now(timezone.utc)
        checks: list[ExecutionCheck] = []
        risk = classify_risk(int(getattr(tool, "risk_level", 1) or 0)
                             if tool is not None else 1, facts.action_name)

        def evaluation(allowed: bool, reason: str, **extra: Any) -> PolicyEvaluation:
            return PolicyEvaluation(allowed, risk, reason, checks=checks, **extra)

        def refuse(name: str, detail: str) -> PolicyEvaluation:
            checks.append(ExecutionCheck(name, False, detail))
            return evaluation(False, detail)

        # 1. Agent identity - from the authenticated principal, never supplied.
        if agent is None:
            return refuse(POLICY_CHECKS[0],
                          "no agent is bound to the authenticated principal; "
                          "execution requests are submitted by agents, and the "
                          "agent's identity comes from the principal, not the payload")
        if getattr(agent, "principal_id", None) != principal_id:
            return refuse(POLICY_CHECKS[0],
                          "the authenticated principal is not the principal this "
                          "agent is bound to")
        checks.append(ExecutionCheck(POLICY_CHECKS[0], True,
                                     f"agent '{agent.name}' is bound to the principal"))

        # 2. Agent status.
        if agent.status not in ASSIGNABLE_AGENT_STATES:
            return refuse(POLICY_CHECKS[1],
                          f"agent '{agent.name}' is {agent.status}; only "
                          f"{', '.join(sorted(ASSIGNABLE_AGENT_STATES))} may request "
                          "execution")
        checks.append(ExecutionCheck(POLICY_CHECKS[1], True,
                                     f"agent '{agent.name}' is {agent.status}"))

        # 3. Assigned task.
        if task is None:
            return refuse(POLICY_CHECKS[2], f"task {facts.task_id} does not exist")
        if assignment_evidence is None:
            return refuse(POLICY_CHECKS[2],
                          f"task '{task.name}' is not assigned to agent "
                          f"'{agent.name}'; execution is requested for work the "
                          "agent holds, not work it would like to hold")
        checks.append(ExecutionCheck(POLICY_CHECKS[2], True, assignment_evidence))

        # 4. Required capabilities - the tool's and the request's, together.
        required = list(dict.fromkeys(
            [*(getattr(tool, "capability_requirements", None) or []),
             *(facts.required_capabilities or [])]))
        if required:
            if self.capabilities is None:
                return refuse(POLICY_CHECKS[3],
                              "the work requires "
                              f"{', '.join(required)} and the capability authority "
                              "is not available, so the requirement cannot be "
                              "verified; execution is not permitted on unverified "
                              "authority")
            for key in required:
                verdict = await self.capabilities.check(agent.id, key,
                                                        scope=facts.requested_scope)
                if not verdict.allowed:
                    return refuse(POLICY_CHECKS[3],
                                  f"agent '{agent.name}' may not use '{key}': "
                                  f"{verdict.reason}")
            checks.append(ExecutionCheck(
                POLICY_CHECKS[3], True,
                f"the agent holds all {len(required)} required capabilities: "
                f"{', '.join(required)}"))
        else:
            checks.append(ExecutionCheck(POLICY_CHECKS[3], True,
                                         "the work requires no capability"))

        # 5. Requested scope. Containment against a workspace root is the
        # adapter's to enforce (Stage 3, resolved-path validation); what policy
        # can refuse here is a scope that is absent where one is required, or
        # unrestricted on its face.
        if facts.requested_scope == "*":
            return refuse(POLICY_CHECKS[4],
                          "an unrestricted scope ('*') is not a scope; name the "
                          "workspace or resource the action is confined to")
        if risk >= 1 and not facts.requested_scope:
            return refuse(POLICY_CHECKS[4],
                          f"a risk-{risk} operation must name its scope, so that "
                          "what was authorized can be compared with what was done")
        checks.append(ExecutionCheck(
            POLICY_CHECKS[4], True,
            f"scope '{facts.requested_scope or '(internal, none required)'}' named; "
            "workspace containment is enforced by the adapter"))

        # 6. Tool status.
        if tool is None:
            return refuse(POLICY_CHECKS[5], f"tool {facts.tool_id} is not registered")
        if tool.adapter_type in ADAPTERS_UNSUPPORTED_HERE:
            return refuse(POLICY_CHECKS[5],
                          f"the {tool.adapter_type} adapter is unsupported in this "
                          f"environment: {ADAPTERS_UNSUPPORTED_HERE[tool.adapter_type]}")
        if tool.status not in ROUTABLE_TOOL_STATES:
            detail = f"tool '{tool.name}' is {tool.status}"
            if getattr(tool, "disabled_reason", None):
                detail += f": {tool.disabled_reason}"
            return refuse(POLICY_CHECKS[5], detail + "; only AVAILABLE or DEGRADED "
                          "tools may be routed work")
        if facts.action_name not in (tool.supported_actions or []):
            return refuse(POLICY_CHECKS[5],
                          f"tool '{tool.name}' does not support the action "
                          f"'{facts.action_name}'; it supports "
                          f"{', '.join(tool.supported_actions or []) or 'nothing'}")
        checks.append(ExecutionCheck(POLICY_CHECKS[5], True,
                                     f"tool '{tool.name}' is {tool.status} and "
                                     f"supports '{facts.action_name}'"))

        # 7. Risk category.
        if risk == 3:
            return refuse(POLICY_CHECKS[6],
                          f"'{facts.action_name}' is a prohibited operation "
                          "(§8 Risk 3) and is rejected by the execution system; "
                          "no approval can authorize it")
        checks.append(ExecutionCheck(
            POLICY_CHECKS[6], True,
            f"classified Risk {risk} ({RISK_TO_LEVEL[risk]}); priority "
            f"{facts.priority} does not alter the classification"))

        # 8. Approval status.
        if approval_required(risk, tool):
            if approval is not None:
                from ..permissions.approvals import ApprovalService
                expiry = getattr(approval, "expires_at", None)
                if expiry is not None and expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                expired = expiry is not None and expiry <= now
                if approval.status == "pending" and not expired:
                    # Still waiting on the owner. That is not a refusal: the
                    # request goes back to AWAITING_APPROVAL unchanged, and
                    # treating it as one would let an impatient retry destroy
                    # a request the owner is about to decide.
                    return evaluation(
                        False,
                        "the bound approval is still pending the owner's "
                        "decision",
                        requires_approval=True)
                if expired:
                    return refuse(POLICY_CHECKS[7],
                                  "the bound approval has expired; an expired "
                                  "approval cannot authorize a new action")
                if approval.status != "approved":
                    return refuse(POLICY_CHECKS[7],
                                  f"the bound approval is {approval.status}, not "
                                  "approved")
                if not ApprovalService.verify_binding(
                        approval, APPROVAL_ACTION, facts.request_id or "",
                        required, binding_parameters(facts)):
                    return refuse(POLICY_CHECKS[7],
                                  "the approved action does not match this "
                                  "request: the tool, action, parameters or scope "
                                  "differ from what was approved")
                checks.append(ExecutionCheck(
                    POLICY_CHECKS[7], True,
                    f"approval {approval.id} approved this tool, action, "
                    "parameters and scope"))
            else:
                standing = find_standing_authorization(
                    standing_entries, agent_id=agent.id, tool_id=tool.id,
                    action_name=facts.action_name, scope=facts.requested_scope,
                    now=now)
                if standing is not None:
                    limit = int(standing.get("max_uses") or 0)
                    uses = (standing_uses or {}).get(str(standing.get("id")), 0)
                    if limit and uses >= limit:
                        return evaluation(
                            False,
                            f"standing authorization {standing.get('id')} has "
                            f"carried {uses} requests and its limit is "
                            f"{limit}; owner approval is required",
                            requires_approval=True)
                    checks.append(ExecutionCheck(
                        POLICY_CHECKS[7], True,
                        f"standing authorization {standing.get('id')} covers this "
                        f"action at this scope ({uses}"
                        f"{'/' + str(limit) if limit else ''} uses)"))
                    return evaluation(
                        True,
                        "permitted under standing authorization "
                        f"{standing.get('id')}",
                        standing_authorization_id=str(standing.get("id")))
                return evaluation(
                    False,
                    f"Risk {risk} work requires owner approval and none binds "
                    "this request",
                    requires_approval=True)
        else:
            checks.append(ExecutionCheck(
                POLICY_CHECKS[7], True,
                f"no approval is required at Risk {risk}"))

        # 9. Resource limits.
        pressure = self.monitor.resource_pressure() if self.monitor is not None else []
        if pressure and facts.priority < ESSENTIAL_PRIORITY:
            return refuse(POLICY_CHECKS[8],
                          f"the machine is under resource pressure "
                          f"({', '.join(pressure)}) and this request's priority is "
                          f"{facts.priority}; only essential work (priority "
                          f"{ESSENTIAL_PRIORITY}-10) proceeds, and the rest waits "
                          "rather than competing for a loaded machine")
        checks.append(ExecutionCheck(
            POLICY_CHECKS[8], True,
            "no resource pressure" if not pressure else
            f"resource pressure ({', '.join(pressure)}) admitted for essential "
            f"priority {facts.priority}"))

        # 10. Policy restrictions: the emergency stop and the phase gates.
        if self.emergency is not None and await self.emergency.is_active():
            return refuse(POLICY_CHECKS[9],
                          "the global emergency stop is active; no new execution "
                          "may be admitted while it is")
        if tool.adapter_type in EXTERNAL_ADAPTERS and not self.settings.external_execution_enabled:
            return refuse(POLICY_CHECKS[9],
                          f"the {tool.adapter_type} adapter's effects leave this "
                          "machine and external execution is disabled "
                          "(AUTONOMUS_EXTERNAL_EXECUTION_ENABLED); the work is "
                          "refused at policy rather than attempted and failed")
        if tool.adapter_type == "code" and not self.settings.external_execution_enabled:
            # Code execution stays on the machine, so the external gate does not
            # apply; nothing to refuse here in Stage 2. Recorded so the check
            # list shows the gate was considered, not skipped.
            pass
        checks.append(ExecutionCheck(POLICY_CHECKS[9], True,
                                     "no emergency stop, and no phase gate blocks "
                                     f"the {tool.adapter_type} adapter"))

        return evaluation(True, f"all ten policy checks passed at Risk {risk}")
