"""Strategic planning engine (P-02 §9).

Turns a validated mission into an executable plan, and refuses to produce one
when the mission is not ready.

Three properties matter more than cleverness here:

* **Every step names a registered capability** (§9.5). A plan may not propose
  work the system cannot perform, which is what stops a planner from inventing
  steps like "conduct market research" when no such capability exists.
* **The dependency graph is acyclic and reference-checked** (§9.3). Cycles and
  dangling references are rejected at validation time, not discovered at
  execution time.
* **Decomposition is deterministic.** The strategy templates below are plain
  data. A model may later propose alternative decompositions, but it cannot
  produce the plan of record without validation, because §16 forbids assuming a
  plan is executable merely because a model generated it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .capabilities import CapabilityRegistry
from .schemas import (
    RISK_RANK,
    Mission,
    MissionState,
    Plan,
    PlanStatus,
    PlanStep,
    PlanValidationError,
    RequestCategory,
    RiskLevel,
    StepStatus,
)

#: Hard ceiling on steps per plan. Unbounded decomposition is a resource risk
#: (§16: never silently exceed resource limits) and produces plans nobody reads.
MAX_PLAN_STEPS = 24

#: Hard ceiling on dependency fan-in per step, to keep graphs reviewable.
MAX_DEPENDENCIES_PER_STEP = 6


# --------------------------------------------------------------------------- #
# Dependency resolution
# --------------------------------------------------------------------------- #


class DependencyResolver:
    """Validates and orders a plan's dependency graph (§9.3)."""

    def validate_references(self, steps: list[PlanStep]) -> list[str]:
        """Return every dangling or self-referential dependency."""
        ids = {s.step_id for s in steps}
        errors: list[str] = []
        seen_pairs: set[tuple[str, str]] = set()
        for step in steps:
            for dep in step.depends_on:
                if dep == step.step_id:
                    errors.append(f"step {step.step_id!r} depends on itself")
                elif dep not in ids:
                    errors.append(f"step {step.step_id!r} depends on unknown step {dep!r}")
                elif (step.step_id, dep) in seen_pairs:
                    errors.append(f"step {step.step_id!r} lists dependency {dep!r} twice")
                seen_pairs.add((step.step_id, dep))
            if len(step.depends_on) > MAX_DEPENDENCIES_PER_STEP:
                errors.append(
                    f"step {step.step_id!r} has {len(step.depends_on)} dependencies, "
                    f"exceeding the limit of {MAX_DEPENDENCIES_PER_STEP}"
                )
        return errors

    def find_cycles(self, steps: list[PlanStep]) -> list[list[str]]:
        """Return every cycle as an ordered list of step ids.

        Iterative depth-first search with an explicit stack: a recursive walk
        could overflow on a pathologically deep graph, and plan graphs come from
        data the owner influenced.
        """
        adjacency = {s.step_id: list(s.depends_on) for s in steps}
        WHITE, GREY, BLACK = 0, 1, 2
        colour = {sid: WHITE for sid in adjacency}
        cycles: list[list[str]] = []
        path: list[str] = []

        for root in adjacency:
            if colour[root] != WHITE:
                continue
            stack: list[tuple[str, int]] = [(root, 0)]
            colour[root] = GREY
            path.append(root)
            while stack:
                node, index = stack[-1]
                neighbours = [n for n in adjacency.get(node, []) if n in adjacency]
                if index < len(neighbours):
                    stack[-1] = (node, index + 1)
                    nxt = neighbours[index]
                    if colour[nxt] == GREY:
                        start = path.index(nxt)
                        cycles.append(path[start:] + [nxt])
                    elif colour[nxt] == WHITE:
                        colour[nxt] = GREY
                        path.append(nxt)
                        stack.append((nxt, 0))
                else:
                    colour[node] = BLACK
                    stack.pop()
                    if path and path[-1] == node:
                        path.pop()
        return cycles

    def topological_order(self, steps: list[PlanStep]) -> list[str]:
        """Kahn's algorithm. Raises if the graph is not a DAG."""
        cycles = self.find_cycles(steps)
        if cycles:
            raise PlanValidationError([f"dependency cycle detected: {' -> '.join(cycles[0])}"])

        indegree = {s.step_id: 0 for s in steps}
        dependents: dict[str, list[str]] = {s.step_id: [] for s in steps}
        for step in steps:
            for dep in step.depends_on:
                if dep in indegree:
                    indegree[step.step_id] += 1
                    dependents[dep].append(step.step_id)

        # Deterministic ordering: among equally-ready steps, keep declaration
        # order so a plan validates identically on every run.
        queue = [s.step_id for s in steps if indegree[s.step_id] == 0]
        order: list[str] = []
        while queue:
            current = queue.pop(0)
            order.append(current)
            for nxt in dependents[current]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        if len(order) != len(steps):
            raise PlanValidationError(["dependency graph could not be fully ordered"])
        return order

    def assign_parallel_groups(self, steps: list[PlanStep]) -> dict[str, str | None]:
        """Group steps that may safely run concurrently (§9.4).

        Depth is the longest path from a root, so two steps share a group only
        when neither depends on the other, directly or transitively. Single-member
        groups get no label: calling a lone step "parallel" would be misleading.
        """
        by_id = {s.step_id: s for s in steps}
        depth: dict[str, int] = {}

        def compute(sid: str, seen: frozenset[str]) -> int:
            if sid in depth:
                return depth[sid]
            if sid in seen:  # defensive; cycles are rejected before this runs
                return 0
            deps = [d for d in by_id[sid].depends_on if d in by_id]
            value = 0 if not deps else 1 + max(compute(d, seen | {sid}) for d in deps)
            depth[sid] = value
            return value

        for step in steps:
            compute(step.step_id, frozenset())

        buckets: dict[int, list[str]] = {}
        for sid, level in depth.items():
            buckets.setdefault(level, []).append(sid)

        groups: dict[str, str | None] = {}
        for level, members in buckets.items():
            # Declaration order within a level keeps output stable.
            ordered = [s.step_id for s in steps if s.step_id in set(members)]
            label = f"parallel-{level}" if len(ordered) > 1 else None
            for sid in ordered:
                groups[sid] = label
        return groups

    def ready_steps(self, steps: list[PlanStep]) -> list[PlanStep]:
        """Steps whose dependencies have all completed (§9.3).

        A step whose dependency failed or was cancelled is *not* ready: it stays
        blocked rather than running on missing input.
        """
        by_id = {s.step_id: s for s in steps}
        ready: list[PlanStep] = []
        for step in steps:
            if step.status not in {StepStatus.PENDING, StepStatus.BLOCKED}:
                continue
            deps = [by_id[d] for d in step.depends_on if d in by_id]
            if all(d.status == StepStatus.COMPLETED for d in deps):
                ready.append(step)
        return ready

    def blocked_by_failure(self, steps: list[PlanStep]) -> list[str]:
        """Steps that can never proceed because an ancestor failed.

        Used by the orchestrator so a failure propagates explicitly instead of
        leaving descendants permanently "pending" (§11.5).
        """
        by_id = {s.step_id: s for s in steps}
        failed = {s.step_id for s in steps if s.status in {StepStatus.FAILED, StepStatus.CANCELLED}}
        affected: set[str] = set()
        changed = True
        while changed:
            changed = False
            for step in steps:
                if step.step_id in affected or step.step_id in failed:
                    continue
                if any(d in failed or d in affected for d in step.depends_on if d in by_id):
                    affected.add(step.step_id)
                    changed = True
        return sorted(affected)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ValidationPolicy:
    """Tunables for plan validation (§9.5)."""

    require_success_criteria_above_risk: RiskLevel = RiskLevel.HIGH
    max_steps: int = MAX_PLAN_STEPS
    #: When True, a mission still awaiting clarification cannot be planned.
    block_unclarified_missions: bool = True
    #: Maximum total estimated wall-clock seconds, if the mission states a limit.
    enforce_time_constraint: bool = True


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def raise_if_invalid(self) -> None:
        if not self.valid:
            raise PlanValidationError(self.errors)


class PlanValidator:
    """Rejects plans that cannot legitimately be executed (§9.5)."""

    def __init__(self, capabilities: CapabilityRegistry, *, policy: ValidationPolicy | None = None) -> None:
        self.capabilities = capabilities
        self.policy = policy or ValidationPolicy()
        self.resolver = DependencyResolver()

    def validate(self, plan: Plan, mission: Mission, *, principal_permissions: set[str] | None = None) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        # -- mission consistency --
        if plan.mission_id != mission.mission_id:
            errors.append(
                f"plan references mission {plan.mission_id!r} but was validated against "
                f"{mission.mission_id!r}"
            )
        if not plan.objective.strip():
            errors.append("plan has no objective")
        if not plan.steps:
            errors.append("plan has no steps")
        if len(plan.steps) > self.policy.max_steps:
            errors.append(
                f"plan has {len(plan.steps)} steps, exceeding the limit of {self.policy.max_steps}"
            )

        # -- duplicate step identities would allow double execution (§9.3) --
        ids = [s.step_id for s in plan.steps]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            errors.append(f"duplicate step ids would permit duplicate execution: {duplicates}")

        # -- unclarified missions --
        if self.policy.block_unclarified_missions:
            if mission.state == MissionState.NEEDS_CLARIFICATION or mission.missing_information:
                missing = "; ".join(q.question for q in mission.missing_information) or "mission state is NEEDS_CLARIFICATION"
                errors.append(f"mission requires clarification before planning: {missing}")

        # -- dependency graph --
        errors.extend(self.resolver.validate_references(plan.steps))
        for cycle in self.resolver.find_cycles(plan.steps):
            errors.append(f"circular dependency: {' -> '.join(cycle)}")

        # -- capabilities must exist and be available (§9.5, §11.2) --
        for step in plan.steps:
            if step.capability_id is None:
                errors.append(f"step {step.step_id!r} names no capability")
                continue
            if not self.capabilities.has(step.capability_id):
                errors.append(
                    f"step {step.step_id!r} requires unregistered capability "
                    f"{step.capability_id!r}; a plan may not propose work the system cannot perform"
                )
            elif not self.capabilities.get(step.capability_id).available:
                errors.append(f"step {step.step_id!r} requires unavailable capability {step.capability_id!r}")

        # -- permissions --
        if principal_permissions is not None:
            for step in plan.steps:
                if step.capability_id is None or not self.capabilities.has(step.capability_id):
                    continue
                required = self.capabilities.get(step.capability_id).required_permissions
                missing = [p for p in required if p not in principal_permissions]
                if missing:
                    errors.append(
                        f"step {step.step_id!r} requires permission(s) the principal lacks: {missing}"
                    )

        # -- risk: a plan is never safer than its riskiest step --
        step_risks = [
            self.capabilities.get(s.capability_id).risk
            for s in plan.steps
            if s.capability_id and self.capabilities.has(s.capability_id)
        ]
        if step_risks:
            worst = max(step_risks, key=lambda r: RISK_RANK[r])
            if RISK_RANK[plan.risk] < RISK_RANK[worst]:
                errors.append(
                    f"plan risk {plan.risk.value} understates its riskiest step ({worst.value})"
                )
            if RISK_RANK[worst] >= RISK_RANK[RiskLevel.HIGH] and not plan.approval_required:
                errors.append("a plan containing HIGH or CRITICAL risk steps must require approval")

        # -- success criteria --
        threshold = self.policy.require_success_criteria_above_risk
        if RISK_RANK[mission.risk] >= RISK_RANK[threshold] and not mission.success_criteria:
            errors.append(
                f"a mission at risk {mission.risk.value} needs owner-stated success criteria "
                "before it can be planned; success criteria are never invented"
            )
        elif not mission.success_criteria:
            warnings.append(
                "the mission states no success criteria, so completion will be measured by "
                "step completion rather than by an owner-defined outcome"
            )

        # -- time constraint --
        if self.policy.enforce_time_constraint and mission.time_constraint:
            total = sum(s.estimated_duration_seconds or 0.0 for s in plan.steps)
            budget = _parse_time_budget_seconds(mission.time_constraint)
            if budget is not None and total > budget:
                errors.append(
                    f"plan estimates {total:.0f}s of work but the mission allows {budget:.0f}s"
                )

        # -- financial limit is a hard constraint that must survive planning --
        budget_constraints = [c for c in mission.constraints if c.kind == "budget"]
        if budget_constraints and not any("budget" in e.lower() or "financial" in e.lower()
                                          for e in plan.estimated_resource_requirements.keys() | set(plan.completion_criteria)):
            warnings.append(
                "the mission states a financial limit; the plan records no explicit budget control"
            )

        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)


_TIME_UNITS = {"hour": 3600, "day": 86400, "week": 604800, "month": 2592000, "year": 31536000}


def _parse_time_budget_seconds(text: str) -> float | None:
    """Best-effort conversion of an owner time phrase into seconds."""
    match = re.search(r"(\d+)\s*(hour|day|week|month|year)s?", text, re.IGNORECASE)
    if match:
        return float(match.group(1)) * _TIME_UNITS[match.group(2).lower()]
    if re.search(r"\b(?:next\s+)?(hour|day|week|month|year)s?\b", text, re.IGNORECASE):
        unit = re.search(r"(hour|day|week|month|year)s?", text, re.IGNORECASE)
        if unit:
            return float(_TIME_UNITS[unit.group(1).lower()])
    return None


# --------------------------------------------------------------------------- #
# Decomposition and planning
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StepTemplate:
    """One step of a deterministic decomposition strategy."""

    key: str
    title: str
    capability_id: str
    depends_on: tuple[str, ...] = ()
    expected_output: str | None = None
    completion_criteria: str | None = None
    estimated_duration_seconds: float | None = None


#: Decomposition strategies keyed by request category (§9.2).
#:
#: These are deliberately modest. P-02 has no research, browsing or creation
#: capability — those arrive in P-03/P-05/P-06 — so a "research a business"
#: mission decomposes into *scoping and analysis* work the engine can actually
#: do, plus an explicit boundary step. §20 Scenario C forbids pretending that
#: generating a plan completed the market research.
STRATEGIES: dict[RequestCategory, tuple[StepTemplate, ...]] = {
    RequestCategory.RESEARCH: (
        StepTemplate("scope", "Define the research scope and the questions to answer", "analyze.text",
                     expected_output="a written scope with explicit questions",
                     completion_criteria="scope recorded and questions enumerated",
                     estimated_duration_seconds=30),
        StepTemplate("constraints", "Extract and confirm stated constraints and limits", "analyze.text",
                     depends_on=("scope",),
                     expected_output="constraint list with provenance",
                     completion_criteria="every constraint carries an origin",
                     estimated_duration_seconds=20),
        StepTemplate("capability-boundary", "Record which parts require a future phase capability", "plan.generate",
                     depends_on=("scope", "constraints"),
                     expected_output="explicit list of work P-02 cannot perform",
                     completion_criteria="boundary documented; no unsupported step proposed",
                     estimated_duration_seconds=20),
        StepTemplate("report", "Produce the research plan for owner review", "plan.generate",
                     depends_on=("capability-boundary",),
                     expected_output="a reviewable plan, not a researched conclusion",
                     completion_criteria="plan returned to the owner without execution",
                     estimated_duration_seconds=30),
    ),
    RequestCategory.PLANNING: (
        StepTemplate("objective", "Restate the objective in measurable terms", "analyze.text",
                     expected_output="objective statement",
                     completion_criteria="objective recorded",
                     estimated_duration_seconds=20),
        StepTemplate("decompose", "Decompose the objective into ordered steps", "plan.generate",
                     depends_on=("objective",),
                     expected_output="ordered step list",
                     completion_criteria="steps have no circular dependencies",
                     estimated_duration_seconds=40),
        StepTemplate("dependencies", "Identify dependencies and parallelisable work", "plan.generate",
                     depends_on=("decompose",),
                     expected_output="dependency graph with parallel groups",
                     completion_criteria="graph validated acyclic",
                     estimated_duration_seconds=30),
        StepTemplate("assumptions", "List assumptions and open questions", "analyze.text",
                     depends_on=("decompose",),
                     expected_output="assumption register",
                     completion_criteria="assumptions separated from verified facts",
                     estimated_duration_seconds=20),
        StepTemplate("review", "Return the plan for owner review", "plan.generate",
                     depends_on=("dependencies", "assumptions"),
                     expected_output="plan preview awaiting approval",
                     completion_criteria="nothing launched",
                     estimated_duration_seconds=10),
    ),
    RequestCategory.BUSINESS_OBJECTIVE: (
        StepTemplate("define-customer", "Define the intended customer segment", "analyze.text",
                     expected_output="segment description",
                     completion_criteria="segment recorded from owner input, not invented",
                     estimated_duration_seconds=30),
        StepTemplate("constraints", "Confirm budget, time and risk constraints", "analyze.text",
                     expected_output="constraint register",
                     completion_criteria="financial limit captured exactly as stated",
                     estimated_duration_seconds=20),
        StepTemplate("scope-validation", "Scope the demand-validation questions", "plan.generate",
                     depends_on=("define-customer", "constraints"),
                     expected_output="validation questions",
                     completion_criteria="questions defined; no research claimed",
                     estimated_duration_seconds=30),
        StepTemplate("feasibility", "Assess feasibility within the stated limits", "compute.deterministic",
                     depends_on=("scope-validation",),
                     expected_output="deterministic feasibility comparison",
                     completion_criteria="arithmetic performed in code, not by a model",
                     estimated_duration_seconds=30),
        StepTemplate("phase-boundary", "Record that opportunity discovery belongs to P-03", "plan.generate",
                     depends_on=("feasibility",),
                     expected_output="explicit deferral note",
                     completion_criteria="P-02 does not claim completed market research",
                     estimated_duration_seconds=10),
        StepTemplate("decision", "Present the recommendation and required approvals", "evaluate.decision",
                     depends_on=("phase-boundary",),
                     expected_output="decision recommendation",
                     completion_criteria="owner approval required before any execution",
                     estimated_duration_seconds=20),
    ),
    RequestCategory.ANALYSIS: (
        StepTemplate("inputs", "Collect and validate the inputs to analyse", "analyze.text",
                     expected_output="validated inputs",
                     completion_criteria="inputs parsed",
                     estimated_duration_seconds=20),
        StepTemplate("analyze", "Perform the deterministic analysis", "analyze.text",
                     depends_on=("inputs",),
                     expected_output="analysis result",
                     completion_criteria="result produced without model fabrication",
                     estimated_duration_seconds=40),
        StepTemplate("evaluate", "Assess confidence and note uncertainty", "evaluate.decision",
                     depends_on=("analyze",),
                     expected_output="uncertainty assessment",
                     completion_criteria="uncertainty level recorded",
                     estimated_duration_seconds=20),
    ),
    RequestCategory.SYSTEM_MANAGEMENT: (
        StepTemplate("check", "Read the current system state", "task.noop",
                     expected_output="current state",
                     completion_criteria="state retrieved through a registered handler",
                     estimated_duration_seconds=10),
        StepTemplate("act", "Perform the requested management action", "task.echo",
                     depends_on=("check",),
                     expected_output="action result",
                     completion_criteria="action completed via the task manager",
                     estimated_duration_seconds=20),
        StepTemplate("verify", "Verify the resulting state", "task.noop",
                     depends_on=("act",),
                     expected_output="verification result",
                     completion_criteria="post-state confirmed",
                     estimated_duration_seconds=10),
    ),
    RequestCategory.TASK_EXECUTION: (
        StepTemplate("authorize", "Confirm authorization for the requested execution", "analyze.text",
                     expected_output="authorization decision",
                     completion_criteria="permission check passed or approval requested",
                     estimated_duration_seconds=10),
        StepTemplate("execute", "Execute through a registered P-01 handler", "task.echo",
                     depends_on=("authorize",),
                     expected_output="task result",
                     completion_criteria="task reached a terminal state",
                     estimated_duration_seconds=30),
        StepTemplate("verify", "Verify the outcome", "task.noop",
                     depends_on=("execute",),
                     expected_output="verification result",
                     completion_criteria="outcome confirmed from task state",
                     estimated_duration_seconds=10),
    ),
}

#: Fallback strategy for categories with no specific template.
DEFAULT_STRATEGY: tuple[StepTemplate, ...] = (
    StepTemplate("understand", "Restate the request and its constraints", "analyze.text",
                 expected_output="restated request",
                 completion_criteria="request captured faithfully",
                 estimated_duration_seconds=20),
    StepTemplate("assess", "Assess what can legitimately be done", "evaluate.decision",
                 depends_on=("understand",),
                 expected_output="capability assessment",
                 completion_criteria="only registered capabilities proposed",
                 estimated_duration_seconds=20),
    StepTemplate("respond", "Return the result or the limitation to the owner", "plan.generate",
                 depends_on=("assess",),
                 expected_output="owner-facing response",
                 completion_criteria="response delivered; nothing executed",
                 estimated_duration_seconds=10),
)


class TaskDecomposer:
    """Builds plan steps from a strategy template (§9.2)."""

    def __init__(self, capabilities: CapabilityRegistry) -> None:
        self.capabilities = capabilities
        self.resolver = DependencyResolver()

    def strategy_for(self, category: RequestCategory) -> tuple[StepTemplate, ...]:
        return STRATEGIES.get(category, DEFAULT_STRATEGY)

    def decompose(self, mission: Mission, *, plan_id: str) -> list[PlanStep]:
        """Materialise steps, dropping any whose capability is not registered.

        Dropping rather than failing keeps the planner honest: it will not emit a
        step it cannot support, and the validator reports the resulting gap if it
        leaves the plan empty.
        """
        templates = self.strategy_for(mission.category)
        steps: list[PlanStep] = []
        # Template keys are local to the strategy; step ids are namespaced by
        # plan id. Dependencies must be emitted in terms of the namespaced ids,
        # or the validator sees every dependency as a dangling reference.
        emitted: dict[str, str] = {}
        for template in templates:
            if not self.capabilities.has(template.capability_id):
                continue
            if not self.capabilities.get(template.capability_id).available:
                continue
            step_id = f"{plan_id}-{template.key}"
            deps = [emitted[d] for d in template.depends_on if d in emitted]
            steps.append(PlanStep(
                step_id=step_id,
                title=template.title,
                depends_on=deps,
                capability_id=template.capability_id,
                expected_output=template.expected_output,
                completion_criteria=template.completion_criteria,
                estimated_duration_seconds=template.estimated_duration_seconds,
                risk=self.capabilities.get(template.capability_id).risk,
            ))
            emitted[template.key] = step_id

        groups = self.resolver.assign_parallel_groups(steps)
        for step in steps:
            step.parallel_group = groups.get(step.step_id)
        return steps


class Planner:
    """Produces a validated plan from a mission (§9.1, §9.5)."""

    def __init__(
        self,
        capabilities: CapabilityRegistry,
        *,
        validator: PlanValidator | None = None,
        decomposer: TaskDecomposer | None = None,
    ) -> None:
        self.capabilities = capabilities
        self.validator = validator or PlanValidator(capabilities)
        self.decomposer = decomposer or TaskDecomposer(capabilities)
        self._counter = 0

    def new_plan_id(self, mission_id: str) -> str:
        self._counter += 1
        return f"plan-{mission_id}-{self._counter:03d}"

    def draft(self, mission: Mission, *, plan_id: str | None = None) -> Plan:
        """Build an unvalidated draft. Callers must validate before use."""
        pid = plan_id or self.new_plan_id(mission.mission_id)
        steps = self.decomposer.decompose(mission, plan_id=pid)
        capability_ids = [s.capability_id for s in steps if s.capability_id]
        risk = self.capabilities.max_risk(capability_ids)
        # A mission the owner flagged as risky keeps that floor: decomposition
        # into safe steps must not launder a risky objective into a LOW plan.
        if RISK_RANK[mission.risk] > RISK_RANK[risk]:
            risk = mission.risk

        total_seconds = sum(s.estimated_duration_seconds or 0.0 for s in steps)
        return Plan(
            plan_id=pid,
            mission_id=mission.mission_id,
            version=1,
            objective=mission.objective or mission.title,
            strategy=self._strategy_name(mission.category),
            steps=steps,
            status=PlanStatus.DRAFT,
            estimated_resource_requirements={
                "steps": len(steps),
                "estimated_seconds": total_seconds,
                "parallel_groups": sorted({s.parallel_group for s in steps if s.parallel_group}),
                "budget_constraint_present": any(c.kind == "budget" for c in mission.constraints),
            },
            risk=risk,
            approval_required=mission.approval_required or RISK_RANK[risk] >= RISK_RANK[RiskLevel.HIGH],
            completion_criteria=[f"all {len(steps)} plan steps reach a terminal state"],
            alternative_strategies=self._alternatives(mission.category),
        )

    def plan(self, mission: Mission, *, principal_permissions: set[str] | None = None,
             plan_id: str | None = None) -> Plan:
        """Draft, validate, and either return a VALIDATED plan or raise.

        Raising is the correct outcome for an invalid plan (§9.5): returning a
        rejected plan that a caller might execute anyway is how unsafe work gets
        done.
        """
        draft = self.draft(mission, plan_id=plan_id)
        result = self.validator.validate(draft, mission, principal_permissions=principal_permissions)
        if not result.valid:
            draft.status = PlanStatus.REJECTED
            draft.validation_errors = result.errors
            raise PlanValidationError(result.errors)
        draft.status = PlanStatus.VALIDATED
        draft.validation_errors = []
        return draft

    def _strategy_name(self, category: RequestCategory) -> str:
        return f"deterministic-{category.value}-decomposition"

    def _alternatives(self, category: RequestCategory) -> list[str]:
        """Record the strategies that were *not* chosen (§9.1).

        Listed so an owner can see the planner had options, and so a future model
        assisted pass has somewhere to propose alternatives without changing the
        plan of record.
        """
        alternatives = [f"deterministic-{c.value}-decomposition" for c in STRATEGIES if c != category]
        return alternatives[:3]


class Replanner:
    """Revises an existing plan without losing its history (§9.6).

    The previous version is marked SUPERSEDED, never deleted, and the new plan
    records why the revision happened. §9.6 also forbids silently changing the
    owner's objective, so the objective is carried over verbatim unless the owner
    explicitly supplied a new one.
    """

    def __init__(self, planner: Planner) -> None:
        self.planner = planner

    def revise(
        self,
        previous: Plan,
        mission: Mission,
        *,
        reason: str,
        new_objective: str | None = None,
        principal_permissions: set[str] | None = None,
        completed_step_ids: list[str] | None = None,
    ) -> tuple[Plan, Plan]:
        """Return (superseded_previous, new_plan).

        Steps that already completed are carried over as COMPLETED so their work
        is not repeated — §9.3 forbids duplicate task execution, and re-running a
        finished step is exactly that.
        """
        if not reason or not reason.strip():
            raise ValueError("a plan revision must record why it happened")

        revised_mission = mission
        if new_objective and new_objective.strip() and new_objective.strip() != mission.objective:
            # Changing the objective is an owner decision; it is recorded on the
            # new plan rather than applied silently.
            revised_mission = mission.model_copy(update={"objective": new_objective.strip()})

        new_plan = self.planner.draft(
            revised_mission,
            plan_id=f"{previous.plan_id}-v{previous.version + 1}",
        )
        new_plan.version = previous.version + 1
        new_plan.supersedes_plan_id = previous.plan_id
        new_plan.revision_reason = reason.strip()
        if new_objective and new_objective.strip():
            new_plan.objective = new_objective.strip()

        # Derived from the previous plan when the caller does not supply it, so
        # that forgetting the argument cannot cause finished work to be repeated
        # (§9.3 forbids duplicate task execution).
        if completed_step_ids is None:
            done = {s.step_id for s in previous.steps if s.status == StepStatus.COMPLETED}
        else:
            done = set(completed_step_ids)
        if done:
            carried: list[PlanStep] = []
            for step in new_plan.steps:
                # Titles are unique within a strategy, and unlike the step id
                # they survive a change of plan id between versions.
                matching = next((p for p in previous.steps if p.title == step.title), None)
                if matching is not None and matching.step_id in done:
                    carried.append(step.model_copy(update={
                        "status": StepStatus.COMPLETED,
                        "task_id": matching.task_id,
                    }))
                else:
                    carried.append(step)
            new_plan.steps = carried

        result = self.planner.validator.validate(new_plan, revised_mission, principal_permissions=principal_permissions)
        if not result.valid:
            new_plan.status = PlanStatus.REJECTED
            new_plan.validation_errors = result.errors
            raise PlanValidationError(result.errors)

        new_plan.status = PlanStatus.VALIDATED
        previous_superseded = previous.model_copy(update={"status": PlanStatus.SUPERSEDED})
        return previous_superseded, new_plan


__all__ = [
    "DEFAULT_STRATEGY",
    "DependencyResolver",
    "MAX_PLAN_STEPS",
    "PlanValidator",
    "Planner",
    "Replanner",
    "STRATEGIES",
    "StepTemplate",
    "TaskDecomposer",
    "ValidationPolicy",
    "ValidationResult",
]
