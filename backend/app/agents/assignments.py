"""Assignment validation, delegation depth and output-contract enforcement
(P-04 Stage 6).

This module decides whether one piece of work may be given to one agent, records
the decision in the `agent_assignments` ledger, and judges the result against the
contract the assignment carried. It does **not** run anything: execution belongs to
`TaskManager`, and an assignment module that also dispatched work would be a second
scheduler with its own idea of what is allowed to run.

Three things are enforced here rather than hoped for:

**Nine rules, in order, stopping at the first refusal.** A refusal names the rule
that refused, so a caller learns *which* condition failed instead of only that
something did. The rules are declared in `ASSIGNMENT_RULES` and each one's source
is documented there; the phase brief's own enumeration is not in this repository,
so the list is reconstructed from what is — the plan's component contract, the
governance document's assignment lifecycle and acceptance list, the Stage-2
columns, and the ceilings Stage 4 already enforces.

**A refusal writes no row.** The ledger's vocabulary has no `refused` member, and
adding one would let the table be read as a list of work that includes work nobody
was ever given. A refusal is an audit row, which is where a decision that produced
no state belongs. No event is published for one either: the event carries a status
drawn from the ledger vocabulary, so publishing a refusal would put a value into
the stream the table can never hold.

**Completion is judged, not accepted.** `complete()` validates the result against
the assignment's `expected_output_schema` and marks the assignment failed when the
contract is not satisfied, whatever the agent reported. This is the first caller of
`CapabilityService.check()` — until now the boundary Stage 5 built had nothing
asking it a question — and it is the deterministic verification the governance
document requires before a parent is told work is done.

The validator implements a deliberate subset of JSON Schema: `type`, `required`,
`properties`, `items` and `additionalProperties`. Adding a schema dependency for
one call site is a heavier commitment than the check needs, and the subset covers
what a template's own `expected_output_schema` can express. A contract naming a
keyword this validator does not implement is **refused**, not passed: an unchecked
result that looks checked is worse than a refusal.

`tasks.assigned_agent_id` is deliberately left alone. The task row is the task
manager's, and a second writer to the same column would make "who is doing this"
depend on which module wrote last. The ledger is the record; P-05 dispatch should
read it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from ..core.config import Settings
from ..core.exceptions import ConflictError, NotFoundError
from ..database.models import utcnow
from ..database.repositories import (
    AgentAssignmentRepo,
    AgentRepo,
    AgentTemplateRepo,
    AuditRepo,
    TaskRepo,
)
from .factory import Check
from .schemas import (
    ASSIGNABLE_AGENT_STATES,
    ASSIGNABLE_TASK_STATES,
    ASSIGNMENT_RULES,
    ASSIGNMENT_STATUSES,
    ASSIGNMENT_TRANSITIONS,
    IN_FLIGHT_ASSIGNMENT_STATUSES,
    AgentAssignmentView,
    TemplateConfiguration,
)

__all__ = [
    "ASSIGNMENT_ACTION",
    "AssignmentNotFoundError",
    "AssignmentRefusedError",
    "AssignmentTransitionError",
    "CompletionResult",
    "AssignmentEvaluation",
    "AssignmentService",
    "validate_output_contract",
]

#: Permission code every assignment write is audited against.
ASSIGNMENT_ACTION = "agents.write"


class AssignmentNotFoundError(NotFoundError):
    """No ledger row carries that id."""

    code = "assignment_not_found"


class AssignmentTransitionError(ConflictError):
    """The ledger's transitions are forward only; this one is not available."""

    code = "assignment_transition_invalid"


class AssignmentRefusedError(ConflictError):
    """One of the nine rules refused, and the body says which.

    A `409` rather than a `200` with a sad field in it, for the reason Stage 5
    established for capability refusals: a caller must not be able to read past a
    refusal. Unlike Stage 5 this one carries the whole evaluation in `details`,
    because an assignment refusal is a decision about work rather than a
    prohibition, and the rules that *did* pass are part of the answer.
    """

    code = "assignment_refused"


# --------------------------------------------------------------------------- #
# Output-contract enforcement
# --------------------------------------------------------------------------- #
_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate_output_contract(result: Any, schema: dict[str, Any],
                             path: str = "$") -> list[str]:
    """Return the ways `result` fails `schema`. Empty means it satisfies it.

    An empty schema declares no contract and therefore accepts anything. That is
    not a loophole in the code so much as a fact about the caller: an assignment
    created without a schema cannot be judged, which is why the normal source of a
    contract is the template's own `expected_output_schema`.
    """
    violations: list[str] = []
    if not schema:
        return violations

    expected = schema.get("type")
    if expected is not None:
        check = _TYPE_CHECKS.get(expected)
        if check is None:
            # Fail closed. Guessing at a keyword this validator does not implement
            # would let an unchecked result be recorded as a verified one.
            violations.append(
                f"{path}: the contract names a type this validator does not "
                f"implement ('{expected}'), so the result was not checked")
            return violations
        if not check(result):
            violations.append(f"{path}: expected {expected}, got {type(result).__name__}")
            return violations

    if isinstance(result, dict):
        for key in schema.get("required") or []:
            if key not in result:
                violations.append(f"{path}: required key '{key}' is missing")
        properties = schema.get("properties") or {}
        for key, sub in properties.items():
            if key in result and isinstance(sub, dict):
                violations.extend(validate_output_contract(result[key], sub, f"{path}.{key}"))
        if schema.get("additionalProperties") is False and properties:
            for key in result:
                if key not in properties:
                    violations.append(f"{path}: unexpected key '{key}'")

    if isinstance(result, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(result):
            violations.extend(
                validate_output_contract(item, schema["items"], f"{path}[{index}]"))
    return violations


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
@dataclass
class AssignmentEvaluation:
    """The outcome of an assignment request: a decision plus the rules behind it."""

    agent_id: str
    task_id: str
    assigned: bool
    reason: str = ""
    checks: list[Check] = field(default_factory=list)
    assignment_id: str | None = None
    delegation_depth: int = 0
    required_capabilities: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "assigned": self.assigned,
            "reason": self.reason,
            "assignment_id": self.assignment_id,
            "delegation_depth": self.delegation_depth,
            "required_capabilities": list(self.required_capabilities),
            "checks": [c.as_dict() for c in self.checks],
        }


@dataclass
class CompletionResult:
    assignment_id: str
    status: str
    accepted: bool
    reason: str
    contract_violations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "assignment_id": self.assignment_id, "status": self.status,
            "accepted": self.accepted, "reason": self.reason,
            "contract_violations": list(self.contract_violations),
        }


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
class AssignmentService:
    def __init__(self, db: Any, settings: Settings, *, capabilities: Any = None,
                 emergency: Any = None, bus: Any = None) -> None:
        self.db = db
        self.settings = settings
        self.capabilities = capabilities
        self.emergency = emergency
        self.bus = bus

    # ------------------------------------------------------------------ #
    # Assignment
    # ------------------------------------------------------------------ #
    async def assign(self, agent_id: str, task_id: str, *,
                     required_capabilities: Sequence[str] = (),
                     expected_output_schema: dict[str, Any] | None = None,
                     priority: int = 5, assigned_by: str | None = None,
                     reason: str = "", correlation_id: str | None = None,
                     ) -> AssignmentEvaluation:
        """Run the nine rules and, if all pass, record the assignment."""
        checks: list[Check] = []
        requested = list(dict.fromkeys(required_capabilities or []))
        schema = dict(expected_output_schema or {})
        rules = ASSIGNMENT_RULES

        async with self.db.session_factory() as session:
            tasks, agents = TaskRepo(session), AgentRepo(session)
            ledger, templates = AgentAssignmentRepo(session), AgentTemplateRepo(session)

            def refuse(detail: str) -> AssignmentEvaluation:
                return AssignmentEvaluation(agent_id, task_id, False, detail, checks,
                                            required_capabilities=requested)

            # 1. The work exists and can still be given out.
            task = await tasks.get(task_id)
            if task is None:
                return await self._refuse(session, refuse, checks, rules[0],
                                          f"task {task_id} does not exist",
                                          requested, assigned_by, correlation_id)
            if task.status not in ASSIGNABLE_TASK_STATES:
                return await self._refuse(session, refuse, checks, rules[0],
                    f"task '{task.name}' is {task.status}, which cannot be given "
                    f"out; only {', '.join(sorted(ASSIGNABLE_TASK_STATES))} can",
                    requested, assigned_by, correlation_id)
            checks.append(Check(rules[0], True, f"task '{task.name}' is {task.status}"))

            # 2. Nobody already holds it.
            #
            # A row in a terminal status is history, not a hold, so it does not
            # block reassignment: work has to be movable, and governance requires
            # reassignment precisely after the previous hold is released. The
            # Stage-2 schema puts a UNIQUE on `task_id`, so the ledger carries one
            # row per task and a reassignment supersedes that row in place rather
            # than adding a second one. The previous holder is preserved in
            # `failure_reason`, which is the only place it can survive; a
            # per-attempt history needs that UNIQUE dropped, and alembic cannot
            # address an unnamed constraint (ADR-0024), so it is recorded as a
            # limitation rather than done quietly here.
            existing = await ledger.for_task(task_id)
            live = (existing is not None
                    and existing.status in IN_FLIGHT_ASSIGNMENT_STATUSES)
            if live or (existing is None and task.assigned_agent_id):
                holder = existing.agent_id if live else task.assigned_agent_id
                where = (f"assignment {existing.id} ({existing.status})" if live
                         else "the task's own assignment pointer")
                return await self._refuse(session, refuse, checks, rules[1],
                    f"this task is already held by agent {holder} through {where}; "
                    "work is reassigned only after the previous assignment is "
                    "cancelled, so that who is doing it never has two answers",
                    requested, assigned_by, correlation_id)
            superseded = None
            if existing is not None:
                superseded = (f"superseded: previously held by agent "
                              f"{existing.agent_id}, which reached "
                              f"'{existing.status}'")
                checks.append(Check(rules[1], True,
                                    f"the only prior assignment for this task is "
                                    f"'{existing.status}' and is superseded in place"))
            else:
                checks.append(Check(
                    rules[1], True,
                    "no assignment and no live pointer exist for this task"))

            # 3. The system is not halted.
            if self.emergency is not None and await self.emergency.is_active():
                return await self._refuse(session, refuse, checks, rules[2],
                    "the global emergency stop is active; no new work may be handed "
                    "out while it is", requested, assigned_by, correlation_id)
            checks.append(Check(rules[2], True, "no emergency stop is active"))

            # 4. The agent can accept work.
            agent = await agents.get(agent_id)
            if agent is None:
                return await self._refuse(session, refuse, checks, rules[3],
                    f"agent {agent_id} does not exist", requested, assigned_by,
                    correlation_id)
            if agent.status not in ASSIGNABLE_AGENT_STATES:
                return await self._refuse(session, refuse, checks, rules[3],
                    f"agent '{agent.name}' is {agent.status}; only "
                    f"{', '.join(sorted(ASSIGNABLE_AGENT_STATES))} may accept work",
                    requested, assigned_by, correlation_id)
            checks.append(Check(rules[3], True, f"agent '{agent.name}' is {agent.status}"))

            # 5. Delegation depth, with the parent chain walked for cycles.
            depth, cycle = await self._delegation_depth(agents, agent)
            if cycle is not None:
                return await self._refuse(session, refuse, checks, rules[4],
                    f"agent '{agent.name}' has itself as an ancestor through "
                    f"{cycle}, so its delegation depth cannot be computed",
                    requested, assigned_by, correlation_id)
            ceiling = self.settings.agent_max_delegation_depth
            if depth > ceiling:
                return await self._refuse(session, refuse, checks, rules[4],
                    f"agent '{agent.name}' sits at delegation depth {depth} and the "
                    f"ceiling is {ceiling}", requested, assigned_by, correlation_id)
            checks.append(Check(rules[4], True,
                                f"delegation depth {depth} of a ceiling of {ceiling}"))

            # 6. Business isolation.
            declared = (task.payload or {}).get("business_id") if isinstance(task.payload, dict) else None
            if declared and agent.business_id and declared != agent.business_id:
                return await self._refuse(session, refuse, checks, rules[5],
                    f"task '{task.name}' declares business {declared} and agent "
                    f"'{agent.name}' belongs to business {agent.business_id}; work "
                    "does not cross a business boundary", requested, assigned_by,
                    correlation_id)
            if declared and not agent.business_id:
                return await self._refuse(session, refuse, checks, rules[5],
                    f"task '{task.name}' declares business {declared} and agent "
                    f"'{agent.name}' belongs to none, so it cannot show it is "
                    "inside that business", requested, assigned_by, correlation_id)
            checks.append(Check(rules[5], True,
                (f"task and agent are both inside business {declared}" if declared
                 else "the task declares no business, so isolation could not be "
                      "checked against one (tasks carry no business column; only a "
                      "payload can declare one)")))

            # 7. The agent holds the authority the work needs.
            if requested:
                if self.capabilities is None:
                    return await self._refuse(session, refuse, checks, rules[6],
                        "the work requires "
                        f"{', '.join(requested)} and the capability authority is not "
                        "available, so the requirement cannot be verified; work is "
                        "not assigned on an unverified authority",
                        requested, assigned_by, correlation_id)
                for key in requested:
                    verdict = await self.capabilities.check(agent_id, key)
                    if not verdict.allowed:
                        return await self._refuse(session, refuse, checks, rules[6],
                            f"agent '{agent.name}' may not use '{key}': {verdict.reason}",
                            requested, assigned_by, correlation_id)
                checks.append(Check(rules[6], True,
                    f"the agent holds all {len(requested)} required capabilities: "
                    f"{', '.join(requested)}"))
            else:
                checks.append(Check(rules[6], True,
                                    "the work requires no capability"))

            # 8. No permission escalation: the request stays inside what the
            #    template authorized. An assignment may not widen an agent.
            configuration, detail = await self._configuration(templates, agent)
            if configuration is None:
                return await self._refuse(session, refuse, checks, rules[7],
                    f"the ceiling an assignment must stay inside could not be read "
                    f"({detail}), so escalation cannot be ruled out",
                    requested, assigned_by, correlation_id)
            allowed = set(configuration.allowed_capabilities or [])
            outside = [key for key in requested if key not in allowed]
            if outside:
                return await self._refuse(session, refuse, checks, rules[7],
                    f"'{agent.name}' was built from a template that authorizes "
                    f"{len(allowed)} capabilities, and {', '.join(outside)} is not "
                    "among them; an assignment may not widen an agent beyond its "
                    "template", requested, assigned_by, correlation_id)
            checks.append(Check(rules[7], True,
                f"every required capability is inside the template's "
                f"{len(allowed)} authorized capabilities"))

            # 9. Concurrency inside the agent's own budget.
            in_flight = await ledger.count_in_flight(agent_id)
            budget = int(configuration.resource_budget.max_concurrent_tasks)
            if in_flight >= budget:
                return await self._refuse(session, refuse, checks, rules[8],
                    f"agent '{agent.name}' already has {in_flight} assignment(s) in "
                    f"flight and its budget allows {budget}", requested, assigned_by,
                    correlation_id)
            checks.append(Check(rules[8], True,
                                f"{in_flight} of {budget} concurrent slots in use"))

            if existing is not None:
                row = await ledger.update(
                    existing, agent_id=agent_id, status="assigned",
                    priority=int(priority), required_capabilities=requested,
                    expected_output_schema=schema, delegation_depth=depth,
                    assigned_at=utcnow(), started_at=None, completed_at=None,
                    failure_reason=superseded)
            else:
                row = await ledger.create(
                    agent_id=agent_id, task_id=task_id, status="assigned",
                    priority=int(priority), required_capabilities=requested,
                    expected_output_schema=schema, delegation_depth=depth)
            assignment_id = row.id
            await AuditRepo(session).record(
                "assignment.recorded", "allowed", resource=assignment_id,
                principal_id=assigned_by, action=ASSIGNMENT_ACTION,
                correlation_id=correlation_id,
                payload={"agent_id": agent_id, "task_id": task_id, "priority": priority,
                         "delegation_depth": depth, "required_capabilities": requested,
                         "assigned_by": assigned_by, "reason": reason,
                         "output_contract_declared": bool(schema)})
            await session.commit()

        await self._emit("AgentAssignmentChanged",
                         {"assignment_id": assignment_id, "agent_id": agent_id,
                          "task_id": task_id, "status": "assigned",
                          "delegation_depth": depth, "reason": reason or "all nine assignment rules passed"},
                         correlation_id)
        return AssignmentEvaluation(agent_id, task_id, True,
                                    reason or "all nine assignment rules passed",
                                    checks, assignment_id=assignment_id,
                                    delegation_depth=depth,
                                    required_capabilities=requested)

    async def _refuse(self, session: Any, refuse: Any, checks: list[Check],
                      rule: str, detail: str, requested: Sequence[str],
                      assigned_by: str | None, correlation_id: str | None):
        """Record a refusal as an audit row and return it. No ledger row, no event."""
        checks.append(Check(rule, False, detail))
        evaluation = refuse(detail)
        await AuditRepo(session).record(
            "assignment.refused", "denied", resource=evaluation.task_id,
            principal_id=assigned_by, action=ASSIGNMENT_ACTION,
            correlation_id=correlation_id,
            payload={"agent_id": evaluation.agent_id, "task_id": evaluation.task_id,
                     "rule": rule, "reason": detail,
                     "required_capabilities": list(requested),
                     "assigned_by": assigned_by})
        await session.commit()
        return evaluation

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def start(self, assignment_id: str, *, actor: str | None = None,
                    correlation_id: str | None = None) -> AgentAssignmentView:
        """`assigned` to `in_progress`. Records that work began; does not begin it."""
        return await self._transition(assignment_id, "in_progress", actor=actor,
                                      correlation_id=correlation_id,
                                      started_at=utcnow())

    async def cancel(self, assignment_id: str, *, reason: str = "",
                     actor: str | None = None,
                     correlation_id: str | None = None) -> AgentAssignmentView:
        """Withdraw the assignment. The task's own cancellation stays the task
        manager's business; this closes the ledger row that said who would do it."""
        return await self._transition(assignment_id, "cancelled", actor=actor,
                                      correlation_id=correlation_id,
                                      completed_at=utcnow(),
                                      failure_reason=reason or "the assignment was cancelled")

    async def complete(self, assignment_id: str, *, succeeded: bool = True,
                       result: dict[str, Any] | None = None, actor: str | None = None,
                       reason: str = "", correlation_id: str | None = None,
                       ) -> CompletionResult:
        """Judge the result against the contract and close the assignment.

        A report of success that does not satisfy the contract is recorded as a
        failure. That is the point: without it, "done" is whatever the agent said.
        """
        payload = dict(result or {})
        async with self.db.session_factory() as session:
            ledger = AgentAssignmentRepo(session)
            row = await ledger.get(assignment_id)
            if row is None:
                raise AssignmentNotFoundError(
                    f"assignment {assignment_id} does not exist")
            violations = validate_output_contract(payload, row.expected_output_schema)
            if not succeeded:
                status, accepted = "failed", False
                detail = reason or "the agent reported that the work did not succeed"
            elif violations:
                status, accepted = "failed", False
                detail = ("the result did not satisfy the assignment's output "
                          "contract: " + "; ".join(violations))
            else:
                status, accepted = "completed", True
                detail = (reason or "the result satisfied the output contract"
                          if row.expected_output_schema
                          else reason or "no output contract was declared, so the "
                                         "result was recorded unjudged")
            self._assert_transition(row.status, status)
            agent_id, task_id = row.agent_id, row.task_id
            await ledger.update(row, status=status, completed_at=utcnow(),
                                failure_reason=None if accepted else detail)
            await AuditRepo(session).record(
                "assignment.completed" if accepted else "assignment.failed",
                "allowed" if accepted else "denied", resource=assignment_id,
                principal_id=actor, action=ASSIGNMENT_ACTION,
                correlation_id=correlation_id,
                payload={"agent_id": agent_id, "task_id": task_id,
                         "reported_success": succeeded, "accepted": accepted,
                         "contract_violations": violations, "reason": detail,
                         "contract_declared": bool(row.expected_output_schema),
                         "actor": actor})
            await session.commit()

        await self._emit("AgentAssignmentChanged",
                         {"assignment_id": assignment_id, "agent_id": agent_id,
                          "task_id": task_id, "status": status, "accepted": accepted,
                          "reason": detail}, correlation_id)
        return CompletionResult(assignment_id, status, accepted, detail, violations)

    async def _transition(self, assignment_id: str, target: str, *,
                          actor: str | None = None, correlation_id: str | None = None,
                          **changes: Any) -> AgentAssignmentView:
        async with self.db.session_factory() as session:
            ledger = AgentAssignmentRepo(session)
            row = await ledger.get(assignment_id)
            if row is None:
                raise AssignmentNotFoundError(
                    f"assignment {assignment_id} does not exist")
            self._assert_transition(row.status, target)
            # Captured before the update. Reading it afterwards would record the new
            # status as the one it came from, and the audit row would describe a
            # transition that did not happen.
            previous = row.status
            await ledger.update(row, status=target, **changes)
            agent_id, task_id = row.agent_id, row.task_id
            view = AgentAssignmentView.from_row(row)
            await AuditRepo(session).record(
                f"assignment.{target}", "allowed", resource=assignment_id,
                principal_id=actor, action=ASSIGNMENT_ACTION,
                correlation_id=correlation_id,
                payload={"agent_id": agent_id, "task_id": task_id,
                         "from": previous, "to": target, "actor": actor})
            await session.commit()
        await self._emit("AgentAssignmentChanged",
                         {"assignment_id": assignment_id, "agent_id": agent_id,
                          "task_id": task_id, "status": target}, correlation_id)
        return view

    @staticmethod
    def _assert_transition(current: str, target: str) -> None:
        allowed = ASSIGNMENT_TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            raise AssignmentTransitionError(
                f"an assignment that is '{current}' cannot become '{target}'; "
                + ("it is terminal" if not allowed
                   else f"only {', '.join(sorted(allowed))} follow it"))

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    async def get(self, assignment_id: str) -> AgentAssignmentView:
        async with self.db.session_factory() as session:
            row = await AgentAssignmentRepo(session).get(assignment_id)
            if row is None:
                raise AssignmentNotFoundError(
                    f"assignment {assignment_id} does not exist")
            return await self._view(session, row)

    async def list_assignments(self, *, agent_id: str | None = None,
                               status: str | None = None, limit: int = 100,
                               offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        async with self.db.session_factory() as session:
            ledger = AgentAssignmentRepo(session)
            rows = await ledger.list_all(status=status, agent_id=agent_id,
                                         limit=limit, offset=offset)
            total = await ledger.count(status=status, agent_id=agent_id)
            views = [(await self._view(session, row)).model_dump(mode="json")
                     for row in rows]
            return views, total

    async def list_for_agent(self, agent_id: str, *, limit: int = 100,
                             offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return await self.list_assignments(agent_id=agent_id, limit=limit, offset=offset)

    async def _view(self, session: Any, row: Any) -> AgentAssignmentView:
        """Resolve the task's state and the agent's name beside the row.

        Neither is copied into the ledger: the task's state moves under the
        assignment, and a stored copy would go stale and then read as a fact about
        the assignment rather than about the moment it was read.
        """
        task = await TaskRepo(session).get(row.task_id)
        agent = await AgentRepo(session).get(row.agent_id)
        return AgentAssignmentView.from_row(
            row, task_status=task.status if task is not None else None,
            agent_name=agent.name if agent is not None else None)

    async def status(self) -> dict[str, Any]:
        """What the ledger holds, with the gaps stated rather than implied away."""
        async with self.db.session_factory() as session:
            ledger = AgentAssignmentRepo(session)
            by_status = await ledger.count_by_status()
            in_flight = sum(by_status.get(s, 0) for s in IN_FLIGHT_ASSIGNMENT_STATUSES)
        return {
            "assignments_by_status": by_status,
            "in_flight": in_flight,
            "statuses": list(ASSIGNMENT_STATUSES),
            "rules": list(ASSIGNMENT_RULES),
            "capability_authority_available": self.capabilities is not None,
            # Nothing observes task progress yet, so an assignment can sit in
            # `assigned` after the task has run. Stated rather than left to be
            # inferred from a healthy-looking count.
            "progress_observed": False,
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    async def _delegation_depth(self, agents: AgentRepo, agent: Any) -> tuple[int, str | None]:
        """Depth of `agent` in the parent chain, or the cycle that stopped the walk."""
        depth, seen, current = 0, {agent.id}, agent
        while getattr(current, "parent_agent_id", None):
            parent = await agents.get(current.parent_agent_id)
            if parent is None:
                break
            if parent.id in seen:
                return depth, parent.id
            seen.add(parent.id)
            depth += 1
            current = parent
        return depth, None

    async def _configuration(self, templates: AgentTemplateRepo, agent: Any):
        """The configuration of the version the agent was actually built from."""
        template_id = getattr(agent, "template_id", None)
        version = getattr(agent, "template_version", None)
        if not template_id or version is None:
            return None, "the agent records no template version"
        row = await templates.get_version(template_id, version)
        if row is None:
            return None, f"template version {version} no longer exists"
        try:
            return TemplateConfiguration.model_validate(row.configuration_json or {}), None
        except Exception as exc:  # noqa: BLE001 - reported to the caller, never fatal
            return None, f"the stored configuration no longer parses ({type(exc).__name__})"

    async def _emit(self, event_type: str, payload: dict[str, Any],
                    correlation_id: str | None) -> None:
        if self.bus is None:
            return
        await self.bus.publish_new(event_type, "agent_assignments", payload,
                                   correlation_id=correlation_id)
