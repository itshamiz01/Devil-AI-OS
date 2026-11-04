"""The agent creation engine (P-04 Stage 4).

Turns a requirement into one of six decisions — ``CREATE_AGENT``,
``REUSE_EXISTING``, ``ASSIGN_EXISTING``, ``QUEUE``, ``REQUEST_OWNER_APPROVAL``,
``REJECT`` — and, for the decisions that have an execution path in this stage,
carries it out.

**No model is consulted anywhere in this module.** Every decision is the output
of an ordered list of checks against the database, the configuration limits and
the resource monitor. A recommendation from a model would be an opinion; a
decision that creates an identity has to be reproducible, and the only way to
make it reproducible is to not ask anything that can answer differently twice.

The checks run in this order, and evaluation stops at the first one that forces
a decision:

1. the emergency stop is clear;
2. a published template with a valid current version can be resolved;
3. every requested capability is inside that template's allowed set;
4. the delegation depth stays within its ceiling;
5. an existing agent can be reused instead of creating one;
6. the registry is within its limits;
7. resources are not under pressure;
8. the template does not require owner approval to instantiate.

Order is policy, not decoration. Reuse is checked **before** limits so that a
full registry still answers "use the agent you already have" rather than
queueing work that need not be created, and approval is checked **last** so an
owner is never asked to approve a creation that would be refused anyway.

Two things this stage deliberately does not do. It never produces
``ASSIGN_EXISTING`` — assignment validation is Stage 6, and emitting a decision
this module cannot execute would be a promise with nothing behind it. And it
does not cross-check capabilities against the ``agent_capabilities`` catalog,
which is empty until Stage 5 governs it; a check against an empty catalog would
either refuse everything or pass everything, and both answers would be false.
"""

from __future__ import annotations

import re
from typing import Any, Sequence
from uuid import uuid4

from ..core.config import Settings
from ..database.connection import Database
from ..database.repositories import (
    AgentCreationRequestRepo,
    AgentRepo,
    AgentTemplateRepo,
)
from .lifecycle import AgentStatus
from .schemas import (CREATION_DECISIONS, CreationDecision,
                      CreationRequestInput, TemplateConfiguration)

__all__ = [
    "APPROVAL_REQUIRED_TOKEN",
    "CREATION_APPROVAL_ACTION",
    "LIVE_STATUSES",
    "REUSABLE_STATUSES",
    "AgentFactory",
    "Check",
    "Evaluation",
]

#: The approval action recorded for a gated creation. Reusing the central
#: approval service means the owner decides through the same endpoint, with the
#: same audit trail, as every other gated action in the system.
CREATION_APPROVAL_ACTION = "agent.create"

#: A template whose ``approval_requirements`` contains this token cannot be
#: instantiated without its owner's decision.
APPROVAL_REQUIRED_TOKEN = "agent_creation"

#: Everything except RETIRED counts against the registry ceiling: a suspended or
#: failed agent still exists and still holds its identity and permissions.
LIVE_STATUSES = tuple(s.value for s in AgentStatus if s is not AgentStatus.RETIRED)

#: Statuses in which an existing agent may take on more work without a new
#: identity being minted. PROPOSED, INITIALIZING and PENDING_APPROVAL are
#: excluded because such an agent is not usable yet; DEGRADED, SUSPENDED and
#: FAILED are excluded because reusing one would hide a problem.
REUSABLE_STATUSES = (AgentStatus.ACTIVE.value, AgentStatus.IDLE.value)

_NAME_SAFE = re.compile(r"[^a-z0-9-]+")


class Check:
    """One deterministic check and the detail that decided it."""

    __slots__ = ("name", "passed", "detail")

    def __init__(self, name: str, passed: bool, detail: str = "") -> None:
        self.name = name
        self.passed = passed
        self.detail = detail

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


class Evaluation:
    """The outcome of running the checks, plus what execution produced."""

    def __init__(self, decision: CreationDecision, reason: str,
                 checks: Sequence[Check] | None = None) -> None:
        self.decision = decision
        self.reason = reason
        self.checks: list[Check] = list(checks or [])
        self.template_id: str | None = None
        self.template_version: int | None = None
        self.reuse_agent_id: str | None = None
        self.agent_id: str | None = None
        self.request_id: str | None = None
        self.approval_id: str | None = None
        self.approval_required = False
        self.replayed = False
        self.recorded = False
        self.limits: dict[str, Any] = {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "checks": [c.as_dict() for c in self.checks],
            "template_id": self.template_id,
            "template_version": self.template_version,
            "reuse_agent_id": self.reuse_agent_id,
            "agent_id": self.agent_id,
            "request_id": self.request_id,
            "approval_id": self.approval_id,
            "approval_required": self.approval_required,
            "replayed": self.replayed,
            "recorded": self.recorded,
            "limits": self.limits,
        }


class AgentFactory:
    """Creation decisions and their execution."""

    def __init__(self, db: Database, settings: Settings, monitor: Any = None,
                 emergency: Any = None) -> None:
        self.db = db
        self.settings = settings
        self.monitor = monitor
        self.emergency = emergency

    # ------------------------------------------------------------------ #
    # The decision
    # ------------------------------------------------------------------ #
    async def evaluate(self, request: CreationRequestInput) -> Evaluation:
        """Run the checks. Writes nothing; ``recorded`` stays false."""
        checks: list[Check] = []

        # 1. Emergency stop. Deterministic and first: nothing else about capacity
        #    or templates matters while the owner has halted the system.
        if self.emergency is not None and await self.emergency.is_active():
            checks.append(Check("emergency_stop_clear", False,
                                "the global emergency stop is active"))
            return Evaluation(CreationDecision.REJECT,
                              "the emergency stop is active; no agent may be created "
                              "until the owner clears it", checks)
        checks.append(Check("emergency_stop_clear", True, "no emergency stop is active"))

        # 2. Template resolution.
        template, version_row, configuration, detail = await self._resolve_template(request)
        if template is None or version_row is None or configuration is None:
            checks.append(Check("template_resolved", False, detail))
            return Evaluation(CreationDecision.REJECT, detail, checks)
        checks.append(Check("template_resolved", True, detail))

        evaluation = Evaluation(CreationDecision.CREATE_AGENT, "", checks)
        # The evaluation copies the list it is handed, so from here on the checks
        # live on the evaluation: appending to the local list would silently drop
        # them from the response, and a decision returned without the checks that
        # produced it is not auditable. Rebinding makes the ownership explicit.
        checks = evaluation.checks
        evaluation.template_id = template.id
        evaluation.template_version = version_row.version
        evaluation.limits = await self._limits_snapshot(template.id)

        # 3. Capabilities must be inside the template's allowed set.
        missing = sorted(set(request.requested_capabilities)
                         - set(configuration.allowed_capabilities))
        if missing:
            detail = ("the template does not allow: " + ", ".join(missing)
                      + "; a capability cannot be granted by asking for it")
            checks.append(Check("capabilities_within_template", False, detail))
            evaluation.decision = CreationDecision.REJECT
            evaluation.reason = detail
            return evaluation
        checks.append(Check(
            "capabilities_within_template", True,
            f"{len(request.requested_capabilities)} requested, all inside the template's "
            f"allowed set (catalog cross-check is P-04 Stage 5)"))

        # 4. Delegation depth.
        depth, detail = await self._delegation_depth(request.parent_agent_id)
        if depth is None:
            checks.append(Check("delegation_within_limit", False, detail))
            evaluation.decision = CreationDecision.REJECT
            evaluation.reason = detail
            return evaluation
        checks.append(Check("delegation_within_limit", True, detail))

        # 5. Reuse before creation. The check is named for the condition that
        #    lets creation proceed, so `passed` means the same thing everywhere:
        #    false means this check forced the decision. Reporting "reuse found"
        #    as passed=true would leave a reader scanning for false to explain a
        #    perfectly ordinary REUSE_EXISTING.
        if request.allow_reuse:
            candidate = await self._reuse_candidate(template.id, request.requested_role)
            if candidate is not None:
                detail = (f"agent {candidate.id} ('{candidate.name}') already fills this "
                          f"role from the same template and is {candidate.status}, so no "
                          "new identity is needed")
                checks.append(Check("no_reusable_agent_exists", False, detail))
                evaluation.decision = CreationDecision.REUSE_EXISTING
                evaluation.reason = detail
                evaluation.reuse_agent_id = candidate.id
                evaluation.agent_id = candidate.id
                return evaluation
            checks.append(Check(
                "no_reusable_agent_exists", True,
                "no agent from this template fills this role in a reusable state "
                f"({', '.join(REUSABLE_STATUSES)})"))

        # 6. Registry limits.
        limits = evaluation.limits
        if limits["live_agents"] >= self.settings.agent_max_total:
            return await self._queue_or_reject(
                evaluation, "registry_limit",
                f"{limits['live_agents']} live agents already exist, the ceiling is "
                f"{self.settings.agent_max_total}")
        if limits["agents_for_template"] >= self.settings.agent_max_per_template:
            return await self._queue_or_reject(
                evaluation, "registry_limit",
                f"{limits['agents_for_template']} agents already exist from this "
                f"template, the per-template ceiling is "
                f"{self.settings.agent_max_per_template}")
        checks.append(Check("registry_within_limits", True,
                            f"{limits['live_agents']}/{self.settings.agent_max_total} live, "
                            f"{limits['agents_for_template']}/"
                            f"{self.settings.agent_max_per_template} for this template"))

        # 7. Resource pressure.
        if self.monitor is not None:
            pressure = self.monitor.resource_pressure()
            if pressure and not request.essential:
                return await self._queue_or_reject(
                    evaluation, "resources_available",
                    "resource pressure reported: " + ", ".join(pressure))
            checks.append(Check(
                "resources_available", True,
                "no resource pressure" if not pressure
                else "resource pressure reported but the request is marked essential: "
                     + ", ".join(pressure)))

        # 8. Approval requirement.
        needs_approval = (
            APPROVAL_REQUIRED_TOKEN in configuration.approval_requirements
            or configuration.security_classification == "restricted"
        )
        evaluation.approval_required = needs_approval
        if needs_approval:
            why = []
            if APPROVAL_REQUIRED_TOKEN in configuration.approval_requirements:
                why.append(f"the template lists '{APPROVAL_REQUIRED_TOKEN}' in "
                           "approval_requirements")
            if configuration.security_classification == "restricted":
                why.append("the template's security classification is 'restricted'")
            detail = "; ".join(why)
            checks.append(Check("approval_not_required", False, detail))
            evaluation.decision = CreationDecision.REQUEST_OWNER_APPROVAL
            evaluation.reason = f"owner approval is required because {detail}"
            return evaluation
        checks.append(Check("approval_not_required", True,
                            "the template requires no approval to instantiate"))

        evaluation.decision = CreationDecision.CREATE_AGENT
        evaluation.reason = ("every check passed: the template is published and valid, the "
                             "capabilities are inside it, no existing agent can be reused, "
                             "and the registry and resources allow one more")
        return evaluation

    async def status(self) -> dict[str, Any]:
        """Registry and queue counts against the configured ceilings.

        Read-only, and it says plainly which part of the decision is not yet
        governed: the capability catalog is empty until Stage 5, so a verdict
        that claimed to have checked it would be a false assurance.
        """
        async with self.db.session_factory() as session:
            agents = AgentRepo(session)
            requests = AgentCreationRequestRepo(session)
            live = await agents.count(statuses=LIVE_STATUSES)
            retired = await agents.count(statuses=[AgentStatus.RETIRED.value])
            queued = await requests.count(decision="QUEUE")
            pending_approval = await requests.count(approval_status="pending")
            decisions = {d: await requests.count(decision=d) for d in CREATION_DECISIONS}
        return {
            "live_agents": live,
            "retired_agents": retired,
            "queued_requests": queued,
            "requests_awaiting_approval": pending_approval,
            "decisions_recorded": decisions,
            "limits": {
                "agent_max_total": self.settings.agent_max_total,
                "agent_max_per_template": self.settings.agent_max_per_template,
                "agent_max_creation_queue": self.settings.agent_max_creation_queue,
                "agent_max_delegation_depth": self.settings.agent_max_delegation_depth,
            },
            "capability_catalog_checked": False,
            "capability_catalog_note": (
                "requested capabilities are checked against the template's allowed set "
                "only; the agent_capabilities catalog is populated and governed in "
                "P-04 Stage 5"
            ),
            "assignment_supported": False,
            "assignment_note": (
                "ASSIGN_EXISTING is declared in the decision vocabulary but never "
                "emitted here; assignment validation is P-04 Stage 6"
            ),
        }

    # ------------------------------------------------------------------ #
    # The checks, in the order they run
    # ------------------------------------------------------------------ #
    async def _resolve_template(self, request: CreationRequestInput):
        """Find the published, validly-configured template this request would use."""
        async with self.db.session_factory() as session:
            repo = AgentTemplateRepo(session)
            if request.template_id:
                template = await repo.get(request.template_id)
                if template is None:
                    return None, None, None, f"template {request.template_id} does not exist"
                candidates = [template]
            else:
                # Deterministic resolution only: an exact, case-insensitive match
                # on name or category. Fuzzy matching a free-text role against a
                # free-text role_definition would make the decision depend on
                # string similarity, which is not reproducible.
                wanted = request.requested_role.strip().lower()
                published = await repo.list(500, 0, status="published")
                candidates = [t for t in published
                              if t.name.strip().lower() == wanted
                              or t.category.strip().lower() == wanted]
                if not candidates:
                    return None, None, None, (
                        f"no published template matches role '{request.requested_role}' "
                        "by name or category; pass template_id explicitly")
                if len(candidates) > 1:
                    return None, None, None, (
                        f"{len(candidates)} published templates match role "
                        f"'{request.requested_role}' ({', '.join(sorted(t.name for t in candidates))}); "
                        "pass template_id explicitly rather than let the engine choose")
            template = candidates[0]
            if template.status != "published":
                return None, None, None, (
                    f"template '{template.name}' is '{template.status}', not published")
            version_row = await repo.get_version(template.id, template.current_version)
            if version_row is None:
                return None, None, None, (
                    f"template '{template.name}' points at version "
                    f"{template.current_version}, which does not exist")
            if version_row.validation_status != "valid":
                return None, None, None, (
                    f"template '{template.name}' version {version_row.version} is "
                    f"'{version_row.validation_status}'; only a version with a valid "
                    "verdict may produce an agent")
            try:
                configuration = TemplateConfiguration.model_validate(
                    version_row.configuration_json or {})
            except Exception as exc:  # noqa: BLE001 - reported, never fatal
                return None, None, None, (
                    f"template '{template.name}' version {version_row.version} holds a "
                    f"configuration that no longer parses: {type(exc).__name__}")
            detail = (f"template '{template.name}' version {version_row.version} "
                      f"({template.category})")
            return template, version_row, configuration, detail

    async def _delegation_depth(self, parent_agent_id: str | None):
        """Return (depth, detail); depth is None when the request must be refused."""
        if not parent_agent_id:
            return 0, "no parent agent; delegation depth 0"
        ceiling = self.settings.agent_max_delegation_depth
        async with self.db.session_factory() as session:
            repo = AgentRepo(session)
            parent = await repo.get(parent_agent_id)
            if parent is None:
                return None, f"parent agent {parent_agent_id} does not exist"
            if parent.status == AgentStatus.RETIRED.value:
                return None, f"parent agent {parent_agent_id} is retired"
            depth = 1
            seen = {parent_agent_id}
            current = parent
            while current.parent_agent_id:
                if current.parent_agent_id in seen:
                    return None, "the parent chain contains a cycle"
                seen.add(current.parent_agent_id)
                current = await repo.get(current.parent_agent_id)
                if current is None:
                    return None, "the parent chain references a missing agent"
                depth += 1
                if depth > ceiling:
                    break
        if depth > ceiling:
            return None, (f"delegation depth would be {depth}, the ceiling is {ceiling}")
        return depth, f"delegation depth {depth} of a ceiling of {ceiling}"

    async def _reuse_candidate(self, template_id: str, role: str):
        wanted = role.strip().lower()
        async with self.db.session_factory() as session:
            repo = AgentRepo(session)
            for agent in await repo.by_template(template_id):
                if agent.status in REUSABLE_STATUSES and agent.role.strip().lower() == wanted:
                    return agent
        return None

    async def _limits_snapshot(self, template_id: str) -> dict[str, Any]:
        async with self.db.session_factory() as session:
            agents = AgentRepo(session)
            requests = AgentCreationRequestRepo(session)
            return {
                "live_agents": await agents.count(statuses=LIVE_STATUSES),
                "agents_for_template": await agents.count(statuses=LIVE_STATUSES,
                                                          template_id=template_id),
                "queued_requests": await requests.count(decision="QUEUE"),
                "agent_max_total": self.settings.agent_max_total,
                "agent_max_per_template": self.settings.agent_max_per_template,
                "agent_max_creation_queue": self.settings.agent_max_creation_queue,
            }

    async def _queue_or_reject(self, evaluation: Evaluation, check_name: str,
                               detail: str) -> Evaluation:
        """Queue when there is room, reject when there is not.

        Queuing without a bound is refusing slowly and without telling anyone, so
        a full queue produces REJECT with the queue depth in the reason.
        """
        ceiling = self.settings.agent_max_creation_queue
        queued = evaluation.limits.get("queued_requests", 0)
        if queued >= ceiling:
            evaluation.checks.append(Check(check_name, False, detail))
            evaluation.checks.append(Check(
                "queue_has_room", False,
                f"{queued} requests are already queued, the ceiling is {ceiling}"))
            evaluation.decision = CreationDecision.REJECT
            evaluation.reason = f"{detail}; the creation queue is full ({queued}/{ceiling})"
            return evaluation
        evaluation.checks.append(Check(check_name, False, detail))
        evaluation.checks.append(Check(
            "queue_has_room", True,
            f"{queued}/{ceiling} queue slots used; the request is held rather than refused"))
        evaluation.decision = CreationDecision.QUEUE
        evaluation.reason = f"{detail}; queued for a later drain"
        return evaluation

    def generated_name(self, role: str) -> str:
        """A unique-enough identity name derived from the requested role.

        The *decision* is deterministic; the *identifier* need not be, and making
        it so would mean deriving names from a counter that two concurrent
        requests could read alike. A random suffix plus the unique constraint on
        ``agents.name`` and ``principals.name`` is what actually guarantees
        uniqueness, with a bounded retry in the executor.
        """
        slug = _NAME_SAFE.sub("-", role.strip().lower()).strip("-") or "agent"
        return f"agent-{slug[:60]}-{uuid4().hex[:8]}"
