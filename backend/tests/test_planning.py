"""P-02 §19.3 — planning tests.

Covers decomposition, dependency generation, circular-dependency detection,
parallel identification, resource constraints, invalid-plan rejection, versioning
and replanning.
"""

from __future__ import annotations

import pytest

from app.intelligence.capabilities import CapabilityRegistry, default_capabilities
from app.intelligence.missions import MissionInterpreter
from app.intelligence.planning import (
    MAX_PLAN_STEPS,
    DependencyResolver,
    Planner,
    PlanValidator,
    Replanner,
    ValidationPolicy,
)
from app.intelligence.schemas import (
    Capability,
    Constraint,
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

OWNER = "owner-principal-1"


@pytest.fixture()
def caps() -> CapabilityRegistry:
    return default_capabilities()


@pytest.fixture()
def planner(caps) -> Planner:
    return Planner(caps)


def make_mission(**overrides) -> Mission:
    base = dict(
        mission_id="m-1",
        owner_principal_id=OWNER,
        title="Test mission",
        original_request="Research an online business opportunity that can be started with $50.",
        objective="Research and scope an opportunity within a $50 budget",
        category=RequestCategory.RESEARCH,
        risk=RiskLevel.LOW,
        constraints=[Constraint(kind="budget", value="50.00 USD", numeric_value=50.0,
                                currency="USD", origin="owner_stated", required=True)],
        financial_limit=50.0,
        financial_limit_currency="USD",
        state=MissionState.READY_FOR_PLANNING,
    )
    base.update(overrides)
    return Mission(**base)


def step(step_id: str, *depends_on: str, capability: str | None = "analyze.text",
         status: StepStatus = StepStatus.PENDING) -> PlanStep:
    return PlanStep(step_id=step_id, title=f"Step {step_id}", depends_on=list(depends_on),
                    capability_id=capability, status=status)


# --------------------------------------------------------------------------- #
# Task decomposition (§9.2)
# --------------------------------------------------------------------------- #


def test_a_research_mission_decomposes_into_ordered_steps(planner):
    plan = planner.plan(make_mission())
    assert plan.status == PlanStatus.VALIDATED
    assert len(plan.steps) == 4
    assert plan.steps[0].depends_on == []
    assert plan.steps[-1].depends_on, "the final step must depend on earlier work"


def test_every_step_names_a_registered_capability(planner, caps):
    """§9.5: a plan may not propose work the system cannot perform."""
    plan = planner.plan(make_mission())
    for plan_step in plan.steps:
        assert plan_step.capability_id is not None
        assert caps.has(plan_step.capability_id)


def test_each_category_gets_its_own_decomposition(planner):
    strategies = set()
    for category in RequestCategory:
        mission = make_mission(category=category, mission_id=f"m-{category.value}")
        try:
            plan = planner.plan(mission)
        except PlanValidationError:
            continue
        strategies.add(plan.strategy)
    assert len(strategies) >= 4, "decomposition must adapt to the mission, not be one fixed template"


def test_a_planning_request_produces_a_reviewable_plan_not_a_launch(planner):
    interpreter = MissionInterpreter()
    text = "Create a roadmap for launching a digital product."
    result = interpreter.interpret(text)
    mission = interpreter.to_mission(text, result, owner_principal_id=OWNER, mission_id="m-roadmap")
    plan = planner.plan(mission)
    assert plan.status == PlanStatus.VALIDATED
    # No step may execute anything external: P-02 has no such capability.
    handlers = {plan_step.capability_id for plan_step in plan.steps}
    assert handlers <= {"analyze.text", "plan.generate", "compute.deterministic",
                        "evaluate.decision", "task.echo", "task.noop", "task.wait"}


def test_steps_record_expected_output_and_completion_criteria(planner):
    plan = planner.plan(make_mission())
    assert all(s.expected_output for s in plan.steps)
    assert all(s.completion_criteria for s in plan.steps)


def test_a_capability_that_disappears_is_not_silently_planned():
    """If a capability is withdrawn, its step must vanish rather than dangle."""
    caps = default_capabilities()
    caps.unregister("plan.generate")
    planner = Planner(caps)
    plan = planner.draft(make_mission())
    assert all(s.capability_id != "plan.generate" for s in plan.steps)


# --------------------------------------------------------------------------- #
# Dependency generation and cycle detection (§9.3)
# --------------------------------------------------------------------------- #


def test_dependencies_reference_namespaced_step_ids(planner):
    """A regression guard: dependencies once used bare template keys."""
    plan = planner.plan(make_mission())
    ids = plan.step_ids()
    for plan_step in plan.steps:
        for dep in plan_step.depends_on:
            assert dep in ids, f"{dep} is not a real step id"


def test_a_cycle_is_detected():
    resolver = DependencyResolver()
    steps = [step("a", "c"), step("b", "a"), step("c", "b")]
    cycles = resolver.find_cycles(steps)
    assert cycles, "a three-node cycle must be detected"


def test_a_self_dependency_is_detected():
    resolver = DependencyResolver()
    errors = resolver.validate_references([step("a", "a")])
    assert any("depends on itself" in e for e in errors)


def test_a_dangling_dependency_is_detected():
    resolver = DependencyResolver()
    errors = resolver.validate_references([step("a", "does-not-exist")])
    assert any("unknown step" in e for e in errors)


def test_a_duplicate_dependency_is_detected():
    resolver = DependencyResolver()
    errors = resolver.validate_references([PlanStep(step_id="a", title="A", depends_on=["b", "b"]) , step("b")])
    assert any("twice" in e for e in errors)


def test_topological_order_respects_dependencies():
    resolver = DependencyResolver()
    steps = [step("c", "b"), step("a"), step("b", "a")]
    order = resolver.topological_order(steps)
    assert order.index("a") < order.index("b") < order.index("c")


def test_topological_order_raises_on_a_cycle():
    resolver = DependencyResolver()
    with pytest.raises(PlanValidationError, match="cycle"):
        resolver.topological_order([step("a", "b"), step("b", "a")])


def test_an_acyclic_diamond_is_accepted():
    resolver = DependencyResolver()
    steps = [step("a"), step("b", "a"), step("c", "a"), step("d", "b", "c")]
    assert resolver.find_cycles(steps) == []
    assert len(resolver.topological_order(steps)) == 4


def test_excessive_fan_in_is_rejected():
    resolver = DependencyResolver()
    deps = [f"d{i}" for i in range(10)]
    steps = [step("target", *deps)] + [step(d) for d in deps]
    errors = resolver.validate_references(steps)
    assert any("exceeding the limit" in e for e in errors)


# --------------------------------------------------------------------------- #
# Parallel task identification (§9.4)
# --------------------------------------------------------------------------- #


def test_independent_steps_at_the_same_depth_are_grouped():
    resolver = DependencyResolver()
    steps = [step("root"), step("left", "root"), step("right", "root")]
    groups = resolver.assign_parallel_groups(steps)
    assert groups["left"] == groups["right"]
    assert groups["left"] is not None
    assert groups["root"] is None, "a lone step is not parallel"


def test_a_sequential_chain_has_no_parallel_groups():
    resolver = DependencyResolver()
    steps = [step("a"), step("b", "a"), step("c", "b")]
    groups = resolver.assign_parallel_groups(steps)
    assert all(g is None for g in groups.values())


def test_a_diamond_marks_the_middle_layer_parallel():
    resolver = DependencyResolver()
    steps = [step("a"), step("b", "a"), step("c", "a"), step("d", "b", "c")]
    groups = resolver.assign_parallel_groups(steps)
    assert groups["b"] == groups["c"]
    assert groups["a"] is None and groups["d"] is None


def test_a_real_plan_reports_its_parallel_groups(planner):
    plan = planner.plan(make_mission(category=RequestCategory.PLANNING, mission_id="m-par"))
    groups = {s.parallel_group for s in plan.steps if s.parallel_group}
    assert groups, "the planning strategy has an independent layer"


def test_ready_steps_exclude_those_with_unmet_dependencies():
    resolver = DependencyResolver()
    steps = [
        step("a", status=StepStatus.PENDING),
        step("b", "a", status=StepStatus.PENDING),
    ]
    ready = resolver.ready_steps(steps)
    assert [s.step_id for s in ready] == ["a"]


def test_a_step_becomes_ready_once_its_dependency_completes():
    resolver = DependencyResolver()
    steps = [
        step("a", status=StepStatus.COMPLETED),
        step("b", "a", status=StepStatus.PENDING),
    ]
    assert [s.step_id for s in resolver.ready_steps(steps)] == ["b"]


def test_a_failed_dependency_blocks_its_descendants():
    """§9.3: prevent execution of blocked tasks."""
    resolver = DependencyResolver()
    steps = [
        step("a", status=StepStatus.FAILED),
        step("b", "a"),
        step("c", "b"),
    ]
    assert resolver.blocked_by_failure(steps) == ["b", "c"]


def test_a_completed_step_is_never_reported_ready_again():
    """§9.3: prevent duplicate task execution."""
    resolver = DependencyResolver()
    steps = [step("a", status=StepStatus.COMPLETED)]
    assert resolver.ready_steps(steps) == []


# --------------------------------------------------------------------------- #
# Resource constraints and plan size (§9.5, §16)
# --------------------------------------------------------------------------- #


def test_an_oversized_plan_is_rejected(caps):
    policy = ValidationPolicy(max_steps=3)
    validator = PlanValidator(caps, policy=policy)
    plan = Plan(plan_id="p", mission_id="m-1", objective="too big",
                steps=[step(f"s{i}") for i in range(5)])
    result = validator.validate(plan, make_mission())
    assert not result.valid
    assert any("exceeding the limit" in e for e in result.errors)


def test_the_default_step_ceiling_is_enforced(caps):
    validator = PlanValidator(caps)
    plan = Plan(plan_id="p", mission_id="m-1", objective="huge",
                steps=[step(f"s{i}") for i in range(MAX_PLAN_STEPS + 1)])
    assert not validator.validate(plan, make_mission()).valid


def test_a_time_constraint_that_cannot_be_met_is_rejected(caps):
    """§9.5: validate against the mission's stated time limit."""
    validator = PlanValidator(caps)
    mission = make_mission(time_constraint="within 1 hour")
    plan = Plan(
        plan_id="p", mission_id="m-1", objective="slow",
        steps=[step("a"), step("b")],
    )
    plan.steps[0].estimated_duration_seconds = 7200
    result = validator.validate(plan, mission)
    assert not result.valid
    assert any("allows" in e for e in result.errors)


def test_a_feasible_time_constraint_is_accepted(caps):
    validator = PlanValidator(caps)
    mission = make_mission(time_constraint="within 30 days")
    plan = planner_plan_with_durations(caps)
    assert validator.validate(plan, mission).valid


def planner_plan_with_durations(caps) -> Plan:
    plan = Plan(plan_id="p", mission_id="m-1", objective="quick", steps=[step("a"), step("b")])
    for s in plan.steps:
        s.estimated_duration_seconds = 60
    return plan


# --------------------------------------------------------------------------- #
# Invalid plan rejection (§9.5)
# --------------------------------------------------------------------------- #


def test_a_plan_with_an_unregistered_capability_is_rejected(caps):
    validator = PlanValidator(caps)
    plan = Plan(plan_id="p", mission_id="m-1", objective="x",
                steps=[step("a", capability="browse.the_web")])
    result = validator.validate(plan, make_mission())
    assert not result.valid
    assert any("unregistered capability" in e for e in result.errors)


def test_a_plan_belonging_to_a_different_mission_is_rejected(caps):
    validator = PlanValidator(caps)
    plan = Plan(plan_id="p", mission_id="other-mission", objective="x", steps=[step("a")])
    result = validator.validate(plan, make_mission())
    assert any("references mission" in e for e in result.errors)


def test_an_empty_plan_is_rejected(caps):
    validator = PlanValidator(caps)
    result = validator.validate(Plan(plan_id="p", mission_id="m-1", objective="x", steps=[]), make_mission())
    assert not result.valid


def test_duplicate_step_ids_are_rejected(caps):
    """§9.3: duplicate identities would permit duplicate execution."""
    validator = PlanValidator(caps)
    plan = Plan(plan_id="p", mission_id="m-1", objective="x", steps=[step("a"), step("a")])
    result = validator.validate(plan, make_mission())
    assert any("duplicate step ids" in e for e in result.errors)


def test_a_cycle_makes_the_plan_invalid(caps):
    validator = PlanValidator(caps)
    plan = Plan(plan_id="p", mission_id="m-1", objective="x",
                steps=[step("a", "b"), step("b", "a")])
    result = validator.validate(plan, make_mission())
    assert any("circular dependency" in e for e in result.errors)


def test_a_step_without_a_capability_is_rejected(caps):
    validator = PlanValidator(caps)
    plan = Plan(plan_id="p", mission_id="m-1", objective="x",
                steps=[PlanStep(step_id="a", title="A", capability_id=None)])
    result = validator.validate(plan, make_mission())
    assert any("names no capability" in e for e in result.errors)


def test_a_plan_needing_permissions_the_principal_lacks_is_rejected(caps):
    """§9.5: validate permission requirements before submission."""
    validator = PlanValidator(caps)
    plan = Plan(plan_id="p", mission_id="m-1", objective="x",
                steps=[step("a", capability="task.echo")])
    result = validator.validate(plan, make_mission(), principal_permissions=set())
    assert not result.valid
    assert any("requires permission" in e for e in result.errors)


def test_the_same_plan_passes_when_the_permission_is_held(caps):
    validator = PlanValidator(caps)
    plan = Plan(plan_id="p", mission_id="m-1", objective="x",
                steps=[step("a", capability="task.echo")])
    assert validator.validate(plan, make_mission(), principal_permissions={"tasks.create"}).valid


def test_an_unavailable_capability_is_rejected():
    caps = default_capabilities()
    caps.register(caps.get("analyze.text").model_copy(update={"available": False}), replace=True)
    validator = PlanValidator(caps)
    plan = Plan(plan_id="p", mission_id="m-1", objective="x", steps=[step("a")])
    result = validator.validate(plan, make_mission())
    assert any("unavailable capability" in e for e in result.errors)


def test_a_plan_understating_its_own_risk_is_rejected(caps):
    """A plan may not look safe by averaging away a risky step."""
    caps.register(Capability(
        capability_id="risky.thing", description="dangerous", risk=RiskLevel.HIGH,
    ), replace=True)
    validator = PlanValidator(caps)
    plan = Plan(plan_id="p", mission_id="m-1", objective="x",
                steps=[step("a", capability="risky.thing")], risk=RiskLevel.LOW)
    result = validator.validate(plan, make_mission())
    assert any("understates its riskiest step" in e for e in result.errors)


def test_a_high_risk_plan_must_require_approval(caps):
    caps.register(Capability(capability_id="risky.thing", description="d", risk=RiskLevel.HIGH))
    validator = PlanValidator(caps)
    plan = Plan(plan_id="p", mission_id="m-1", objective="x",
                steps=[step("a", capability="risky.thing")],
                risk=RiskLevel.HIGH, approval_required=False)
    result = validator.validate(plan, make_mission())
    assert any("must require approval" in e for e in result.errors)


def test_a_mission_awaiting_clarification_cannot_be_planned(caps):
    """§7.4/§9.5: planning on invented information is refused."""
    validator = PlanValidator(caps)
    mission = make_mission(state=MissionState.NEEDS_CLARIFICATION)
    plan = Plan(plan_id="p", mission_id="m-1", objective="x", steps=[step("a")])
    result = validator.validate(plan, mission)
    assert any("requires clarification" in e for e in result.errors)


def test_a_critical_mission_without_success_criteria_cannot_be_planned(caps):
    """§7.4: success criteria are never invented, so their absence blocks planning."""
    validator = PlanValidator(caps)
    mission = make_mission(risk=RiskLevel.CRITICAL, success_criteria=[])
    plan = Plan(plan_id="p", mission_id="m-1", objective="x", steps=[step("a")])
    result = validator.validate(plan, mission)
    assert any("success criteria" in e for e in result.errors)


def test_a_low_risk_mission_without_success_criteria_only_warns(caps):
    validator = PlanValidator(caps)
    plan = Plan(plan_id="p", mission_id="m-1", objective="x", steps=[step("a")])
    result = validator.validate(plan, make_mission(risk=RiskLevel.LOW, success_criteria=[]))
    assert result.valid
    assert any("success criteria" in w for w in result.warnings)


def test_a_rejected_plan_raises_and_records_its_errors(planner):
    mission = make_mission(state=MissionState.NEEDS_CLARIFICATION)
    with pytest.raises(PlanValidationError) as exc:
        planner.plan(mission)
    assert exc.value.errors


def test_a_missing_budget_control_produces_a_warning(caps):
    validator = PlanValidator(caps)
    plan = Plan(plan_id="p", mission_id="m-1", objective="x", steps=[step("a")])
    result = validator.validate(plan, make_mission(risk=RiskLevel.LOW))
    assert any("financial limit" in w for w in result.warnings)


# --------------------------------------------------------------------------- #
# Risk flooring
# --------------------------------------------------------------------------- #


def test_a_risky_mission_cannot_be_laundered_into_a_low_risk_plan(planner):
    """Decomposing a CRITICAL objective into safe steps must not lower its risk."""
    plan = planner.draft(make_mission(risk=RiskLevel.CRITICAL, mission_id="m-risk"))
    assert plan.risk == RiskLevel.CRITICAL
    assert plan.approval_required is True


# --------------------------------------------------------------------------- #
# Plan versioning and replanning (§9.6)
# --------------------------------------------------------------------------- #


def test_a_revision_increments_the_version_and_preserves_history(planner):
    mission = make_mission()
    first = planner.plan(mission)
    replanner = Replanner(planner)
    superseded, second = replanner.revise(first, mission, reason="a dependency became unavailable")
    assert second.version == first.version + 1
    assert superseded.status == PlanStatus.SUPERSEDED
    assert second.supersedes_plan_id == first.plan_id
    assert second.revision_reason == "a dependency became unavailable"


def test_a_revision_without_a_reason_is_refused(planner):
    """§9.6: record why a revision occurred."""
    mission = make_mission()
    first = planner.plan(mission)
    with pytest.raises(ValueError, match="must record why"):
        Replanner(planner).revise(first, mission, reason="   ")


def test_completed_steps_are_not_re_executed_after_a_revision(planner):
    """§9.3: duplicate task execution is prevented across plan versions."""
    mission = make_mission()
    first = planner.plan(mission)
    first.steps[0].status = StepStatus.COMPLETED
    first.steps[0].task_id = "task-abc"
    # completed_step_ids is deliberately NOT passed: deriving it from the
    # previous plan is the safe default, and this asserts that.
    _, second = Replanner(planner).revise(first, mission, reason="later step failed")
    carried = second.steps[0]
    assert carried.status == StepStatus.COMPLETED
    assert carried.task_id == "task-abc"


def test_a_revision_may_change_the_objective_only_when_explicitly_asked(planner):
    mission = make_mission()
    first = planner.plan(mission)
    _, unchanged = Replanner(planner).revise(first, mission, reason="retry after failure")
    assert unchanged.objective == first.objective
    _, changed = Replanner(planner).revise(
        first, mission, reason="owner narrowed the scope", new_objective="Only validate demand"
    )
    assert changed.objective == "Only validate demand"


def test_a_revision_that_fails_validation_is_rejected(planner, caps):
    """Withdrawing every capability a strategy needs leaves nothing to plan.

    Withdrawing only one is not an error: the decomposer drops the unsupported
    step and the remaining plan is still valid, which is the behaviour §9.5 asks
    for. It takes losing all of them to make a plan unplannable.
    """
    mission = make_mission()
    first = planner.plan(mission)
    for capability_id in ("analyze.text", "plan.generate"):
        caps.unregister(capability_id)
    replanner = Replanner(Planner(caps))
    with pytest.raises(PlanValidationError) as exc:
        replanner.revise(first, mission, reason="capabilities withdrawn")
    assert any("no steps" in e for e in exc.value.errors)


def test_plan_versions_can_chain(planner):
    mission = make_mission()
    plan = planner.plan(mission)
    replanner = Replanner(planner)
    for expected_version in (2, 3, 4):
        _, plan = replanner.revise(plan, mission, reason=f"revision {expected_version}")
        assert plan.version == expected_version
    assert plan.supersedes_plan_id.endswith("v3")
