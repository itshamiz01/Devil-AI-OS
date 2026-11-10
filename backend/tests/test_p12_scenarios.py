"""P-12 mandatory acceptance scenarios (§23) as named tests.

Each test is the scenario: setup → governed action → the exact
expected system behaviour, asserted on real rows (workflows, tasks,
approvals, P-07 spending requests, P-09 learning records), never on
mocked internals.
"""
from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from app.core.exceptions import (
    InvalidStateTransitionError, PermissionDeniedError)
from app.permissions.models import Permission
from app.permissions.models import Principal, PrincipalType
from tests.p06_support import make_fixture_business
from tests.p12_support import (  # noqa: F401
    AGENT, AGENT2, OWNER, SYSTEM, app_ops, business_with_profile,
    echo_step, grant_capability, grant_permission, make_workflow, money,
    register_agent,
)

AGENT_B = Principal(PrincipalType.AGENT, "agent-b")


def _link(application, workflow_id: str, purpose: str = "task_step"):
    from app.database.repositories.operations import ApprovalLinkRepository
    session = application.session_factory()
    try:
        for link in ApprovalLinkRepository(session).list_for_workflow(
                workflow_id):
            if link.purpose == purpose and link.status == "pending":
                return link.approval_id
        return None
    finally:
        session.close()


def _task(application, workflow_id: str, step_key: str) -> dict:
    detail = application.operations.get_workflow(OWNER, workflow_id)
    return next(t for t in detail["tasks"] if t["step_key"] == step_key)


# ------------------------------------------------------------ Scenario 1
async def test_scenario_01_scheduled_recurring_workflow(app_ops):
    """A recurring operations workflow is created from its schedule,
    executes, and is recorded — exactly once per scheduled instant."""
    ops = app_ops.operations
    trigger = ops.create_trigger(OWNER, {
        "name": "hourly monitoring", "trigger_type": "time",
        "schedule": {"kind": "interval", "every_seconds": 3600},
        "workflow_template": {
            "name": "Scheduled monitoring", "template": "monitoring_report",
            "objective": "recurring monitoring", "autonomy_level": 2}})
    from app.database.repositories.operations import TriggerRepository
    session = app_ops.session_factory()
    try:
        repo = TriggerRepository(session)
        row = repo.get(trigger["id"])
        row.next_fire_at = dt.datetime.now(dt.timezone.utc) \
            - dt.timedelta(seconds=5)
        repo.save(row)
    finally:
        session.close()
    summary = await ops.tick()
    assert summary["fired"] and summary["fired"][0]["driven"] is True
    workflows = ops.list_workflows(OWNER, origin="schedule")
    assert workflows["total"] == 1
    workflow = workflows["items"][0]
    assert workflow["status"] == "COMPLETED"
    assert workflow["verified_outcome"] == "verified"
    after = ops.list_triggers(OWNER)["items"][0]
    assert after["fire_count"] == 1 and after["missed_count"] == 0
    # A second immediate tick must not duplicate the run (fire key).
    summary2 = await ops.tick()
    assert not summary2["fired"]
    assert ops.list_workflows(OWNER, origin="schedule")["total"] == 1


# ------------------------------------------------------------ Scenario 2
async def test_scenario_02_intelligence_plan_becomes_governed_workflow(app_ops):
    """Master Intelligence produces a structured plan (deterministic
    baseline planner — no real LLM in staging); P-12 imports it into
    tasks, the restricted step waits for owner approval, and the
    result is independently verified."""
    mission = await app_ops.intelligence.create_mission(
        OWNER, "Run a system health check and publish the findings")
    plan = await app_ops.intelligence.create_plan(OWNER, mission.id)
    session = app_ops.session_factory()
    try:
        from app.database.models.intelligence import PlanStep
        steps = list(session.query(PlanStep).filter_by(plan_id=plan.id)
                     .order_by(PlanStep.order_index))
    finally:
        session.close()
    assert steps, "baseline planner produced no steps"
    # Faithful import: each plan step becomes a workflow task on the
    # same P-01 handler with the same payload; a governed publish
    # step (restricted action) closes the workflow.
    wf_steps = []
    for i, step in enumerate(steps):
        wf_steps.append({
            "step_key": f"step-{i + 1}", "name": step.name,
            "kind": "task_handler", "action_class": "business.read",
            "substrate": {"handler": step.tool_name,
                          "payload": step.payload or {}},
            "depends_on": [f"step-{i}"] if i else [],
            "acceptance_criteria": {"task_status": "completed"}})
    wf_steps.append({
        "step_key": "publish", "name": "Publish findings",
        "kind": "task_handler", "action_class": "content.publish",
        "substrate": {"handler": "core.echo_check",
                      "payload": {"message": "findings published"}},
        "depends_on": [f"step-{len(steps)}"],
        "acceptance_criteria": {"task_status": "completed"}})
    ops = app_ops.operations
    created = ops.create_workflow(OWNER, {
        "name": "Content plan execution", "origin": "intelligence",
        "objective": mission.text, "autonomy_level": 2,
        "definition": {"steps": wf_steps, "source_plan_id": plan.id,
                       "planner": "p02-baseline"}})
    view = ops.validate_workflow(OWNER, created["id"])
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "WAITING_FOR_APPROVAL"
    approval_id = _link(app_ops, view["id"])
    assert approval_id
    app_ops.approvals.decide(approval_id, OWNER, True)
    resolved = await ops.check_approvals(OWNER)
    assert resolved["driven"] == [view["id"]]
    final = ops.get_workflow(OWNER, view["id"])
    assert final["status"] == "COMPLETED"
    assert all(t["verification_status"] == "verified"
               for t in final["tasks"])


# ------------------------------------------------------------ Scenario 3
async def test_scenario_03_agent_cannot_approve_own_restricted_action(app_ops):
    """An agent's restricted action creates a P-01 approval; the
    agent's attempt to approve it is refused at the ApprovalService
    level; the owner's approval releases exactly that step."""
    _opp, business = await make_fixture_business(app_ops)
    business_id = business["id"]
    register_agent(app_ops, AGENT.id, business_ref=business_id)
    grant_permission(app_ops, AGENT, "modify_business_data")
    ops = app_ops.operations
    view = make_workflow(
        app_ops, steps=[echo_step(
            "publish", action_class="content.publish",
            assigned_agent_id=AGENT.id)],
        business_id=business_id, autonomy_level=3)
    result = await ops.start_workflow(AGENT, view["id"])
    assert result["status"] == "WAITING_FOR_APPROVAL"
    approval_id = _link(app_ops, view["id"])
    assert approval_id
    with pytest.raises(PermissionDeniedError):
        app_ops.approvals.decide(approval_id, AGENT, True)
    assert _task(app_ops, view["id"], "publish")["substrate_ref"] is None
    app_ops.approvals.decide(approval_id, OWNER, True)
    await ops.check_approvals(OWNER)
    final = ops.get_workflow(OWNER, view["id"])
    assert final["status"] == "COMPLETED"
    assert _task(app_ops, view["id"], "publish")["substrate_ref"]


# ------------------------------------------------------------ Scenario 4
async def test_scenario_04_two_businesses_operate_independently(app_ops):
    """Two businesses run workflows at the same time; each task is
    executed by an agent of its own business; records stay scoped."""
    _o1, biz_a = await make_fixture_business(app_ops, name="Business A")
    _o2, biz_b = await make_fixture_business(app_ops, name="Business B")
    register_agent(app_ops, AGENT.id, business_ref=biz_a["id"])
    register_agent(app_ops, AGENT_B.id, business_ref=biz_b["id"])
    grant_capability(app_ops, AGENT.id, "web_research")
    grant_capability(app_ops, AGENT_B.id, "web_research")
    ops = app_ops.operations
    step = echo_step("research", required_capabilities=["web_research"])
    wf_a = make_workflow(app_ops, steps=[dict(step)], business_id=biz_a["id"])
    wf_b = make_workflow(app_ops, steps=[dict(step)], business_id=biz_b["id"])
    result_a, result_b = await asyncio.gather(
        ops.start_workflow(OWNER, wf_a["id"]),
        ops.start_workflow(OWNER, wf_b["id"]))
    assert result_a["status"] == "COMPLETED"
    assert result_b["status"] == "COMPLETED"
    assert _task(app_ops, wf_a["id"], "research")["assigned_agent_id"] \
        == AGENT.id
    assert _task(app_ops, wf_b["id"], "research")["assigned_agent_id"] \
        == AGENT_B.id
    assert ops.business_operations(OWNER, biz_a["id"])["workflows_total"] == 1
    assert ops.business_operations(OWNER, biz_b["id"])["workflows_total"] == 1


# ------------------------------------------------------------ Scenario 5
async def test_scenario_05_autonomy_increase_does_not_leak(app_ops):
    """Owner raises Business A to Level 3. Business B's resolution
    contains no trace of A's policy and stays at its own level."""
    _o1, biz_a = await make_fixture_business(app_ops, name="Biz A")
    _o2, biz_b = await make_fixture_business(app_ops, name="Biz B")
    ops = app_ops.operations
    ops.set_autonomy_policy(OWNER, {
        "scope_type": "business", "scope_ref": biz_a["id"], "level": 3,
        "reason": "trusted operations"})
    res_a = ops.resolve_autonomy(
        business_id=biz_a["id"], agent_id=None, workflow_id=None,
        workflow_declared_level=3, action_class="content.publish",
        declared_by_owner=True)
    res_b = ops.resolve_autonomy(
        business_id=biz_b["id"], agent_id=None, workflow_id=None,
        workflow_declared_level=1, action_class="content.publish",
        declared_by_owner=False)
    assert res_a["effective_level"] == 3 and res_a["may_execute"]
    assert res_b["effective_level"] == 1
    assert res_b["approval_required"] is True
    assert "business_policy" not in res_b["ceilings"]


# ------------------------------------------------------------ Scenario 6
async def test_scenario_06_agent_unavailable_mid_workflow(app_ops):
    """An assignee that is unavailable when its step is reached is
    replaced by a healthy eligible agent (recorded as a recovery
    reassignment); the workflow completes instead of continuing
    blindly on the dead assignee or dropping the step."""
    _o, business = await make_fixture_business(app_ops)
    business_id = business["id"]
    register_agent(app_ops, AGENT.id, business_ref=business_id)
    register_agent(app_ops, AGENT2.id, business_ref=business_id)
    grant_capability(app_ops, AGENT.id, "web_research")
    grant_capability(app_ops, AGENT2.id, "web_research")
    # Agent-1 becomes unavailable (suspended) before the run.
    from app.database.models.core import Agent as AgentRow
    session = app_ops.session_factory()
    try:
        row = session.get(AgentRow, AGENT.id)
        row.status = "suspended"
        session.commit()
    finally:
        session.close()
    ops = app_ops.operations
    steps = [echo_step("first", required_capabilities=["web_research"]),
             echo_step("second", required_capabilities=["web_research"],
                       depends_on=["first"], assigned_agent_id=AGENT.id)]
    view = make_workflow(app_ops, steps=steps, business_id=business_id)
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "COMPLETED"
    second = _task(app_ops, view["id"], "second")
    assert second["assigned_agent_id"] == AGENT2.id
    recovery = ops.recovery_center(OWNER)
    assert any(r["action"] == "reassign" and r["task_id"] == second["id"]
               for r in recovery["recovery_records"])


# ------------------------------------------------------------ Scenario 7
async def test_scenario_07_budget_violation_blocks_execution(app_ops):
    """A step whose spend exceeds its P-07 budget is BLOCKED by
    P-07's held decision — nothing executes — until the owner
    approves the exact spend; a Level-3 kind is blocked outright."""
    business_id, _profile = await business_with_profile(app_ops)
    fin = app_ops.financial
    fin.record_opening_balance(OWNER, business_id, {
        "amount": money(app_ops, "10000.00"), "entry_date": "2026-11-01"})
    budget = fin.budgets.create_budget(OWNER, {
        "scope_type": "business", "business_id": business_id,
        "name": "Operations", "amount": money(app_ops, "2000.00"),
        "period_start": "2026-11-01", "period_end": "2026-11-30",
        "approval_requirement": "level_1"})
    ops = app_ops.operations
    spend_step = echo_step(
        "advertise",
        budget_ref={"requires_spend": True, "budget_id": budget["id"],
                    "spend_kind": "expense", "category": "advertising"},
        input_data={"spend_amount_minor": 250000, "currency": "INR"})
    view = make_workflow(app_ops, steps=[spend_step],
                         business_id=business_id, budget_id=budget["id"])
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "WAITING_FOR_APPROVAL"
    task = _task(app_ops, view["id"], "advertise")
    assert task["status"] == "WAITING_FOR_APPROVAL"
    assert task["substrate_ref"] is None  # nothing executed
    spend_id = task["result"]["spend"]["spend_request_id"]
    assert fin.budgets.get_request(spend_id)["status"] == "held_for_owner"
    # Owner approves the exact spend (P-01 approval → P-07 decision).
    approval_id = _link(app_ops, view["id"], purpose="spend")
    assert approval_id
    app_ops.approvals.decide(approval_id, OWNER, True)
    await ops.check_approvals(OWNER)
    assert fin.budgets.get_request(spend_id)["status"] == \
        "authorised_owner"
    final = ops.get_workflow(OWNER, view["id"])
    assert final["status"] == "COMPLETED"
    assert _task(app_ops, view["id"], "advertise")["substrate_ref"]

    # Level-3 kind: structurally blocked by P-07 — workflow fails,
    # the block is recorded, nothing executes.
    blocked_step = echo_step(
        "move-money",
        budget_ref={"requires_spend": True, "budget_id": budget["id"],
                    "spend_kind": "transfer", "category": "operations"},
        input_data={"spend_amount_minor": 1000, "currency": "INR"})
    view2 = make_workflow(app_ops, steps=[blocked_step],
                          business_id=business_id, budget_id=budget["id"])
    result2 = await ops.start_workflow(OWNER, view2["id"])
    assert result2["status"] == "FAILED"
    task2 = _task(app_ops, view2["id"], "move-money")
    assert task2["status"] == "FAILED"
    assert task2["substrate_ref"] is None
    decisions = ops.list_decisions(OWNER, workflow_id=view2["id"])["items"]
    assert any(d["category"] == "REJECT" for d in decisions)


# ------------------------------------------------------------ Scenario 8
async def test_scenario_08_external_tool_failure_recorded(app_ops):
    """A P-05 tool execution fails: the workflow does not report
    success, the failure is classified and recorded, and the dead
    letter queue holds the step for investigation."""
    from tests.p05_support import grant as p05_grant, make_agent
    agent_id = await make_agent(app_ops)  # P-04 factory agent
    await p05_grant(app_ops, agent_id, "file_read")  # P-05's own gate
    ops = app_ops.operations
    step = {"step_key": "read-file", "name": "Read missing file",
            "kind": "execution", "action_class": "business.read",
            "substrate": {"tool": "filesystem", "action": "read",
                          "parameters": {"path": "no-such-file.txt"}},
            "retry_policy": {"max_retries": 0},
            "acceptance_criteria": {"task_status": "completed"}}
    view = make_workflow(app_ops, steps=[step])
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "FAILED"
    assert result["verified_outcome"] != "verified"
    task = _task(app_ops, view["id"], "read-file")
    assert task["status"] in ("FAILED", "DEAD_LETTER")
    assert task["assigned_agent_id"] == agent_id
    # The P-05 request itself records the failed execution.
    request = app_ops.execution.get_request(task["substrate_ref"])
    assert request.status == "FAILED"
    recovery = ops.recovery_center(OWNER)
    assert recovery["dead_letter_total"] >= 1
    assert any(d["workflow_id"] == view["id"]
               for d in recovery["dead_letters"])


# ----------------------------------------------------------------------
# Scenarios 9-15
# ----------------------------------------------------------------------

async def test_scenario_09_interrupted_workflow_resumes_without_duplication(
        app_ops):
    """A workflow interrupted after step 1 recovers and completes:
    step 1 is NOT executed a second time (idempotency + checkpoint)."""
    from app.database.repositories.operations import WorkflowRepository
    register_agent(app_ops, AGENT.id)
    grant_permission(app_ops, AGENT, Permission.MODIFY_BUSINESS_DATA)
    ops = app_ops.operations
    steps = [echo_step("first", message="step-one"),
             {"step_key": "publish", "name": "Publish", "kind": "task_handler",
              "action_class": "content.publish",
              "substrate": {"handler": "core.echo_check",
                            "payload": {"message": "published"}},
              "depends_on": ["first"],
              "acceptance_criteria": {"task_status": "completed"}}]
    view = make_workflow(app_ops, steps=steps, autonomy_level=2)
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "WAITING_FOR_APPROVAL"
    first = _task(app_ops, view["id"], "first")
    assert first["status"] == "COMPLETED"
    substrate_task_id = first["substrate_ref"]

    # Simulate a crash: the workflow is left RUNNING mid-flight.
    session = app_ops.session_factory()
    try:
        repo = WorkflowRepository(session)
        row = repo.get(view["id"])
        row.status = "RUNNING"
        repo.save(row)
    finally:
        session.close()
    recovered = ops.recover_interrupted()
    assert recovered == 1
    assert ops.get_workflow(OWNER, view["id"])["status"] == \
        "RECOVERY_PENDING"

    # Owner approves the parked step; processing resumes.
    link = _link(app_ops, view["id"])
    app_ops.approvals.decide(link, OWNER, True)
    resumed = await ops.check_approvals(OWNER)
    assert view["id"] in resumed["driven"]
    final = ops.get_workflow(OWNER, view["id"])
    assert final["status"] == "COMPLETED"
    # Step 1 executed exactly once across interruption + resume.
    history = app_ops.tasks.history(substrate_task_id)
    assert len(history) == 1
    checkpoints = final["checkpoints"]
    assert any(any(entry["step_key"] == "first"
                   for entry in (c["completed_steps"] or []))
               for c in checkpoints)


async def test_scenario_10_conflicting_workflows_one_deferred(app_ops):
    """Two workflows contend for the same business resource: the
    second is deferred with a recorded decision; the first completes;
    the second then runs. No duplicate execution."""
    register_agent(app_ops, AGENT.id)
    _o, business = await make_fixture_business(app_ops)
    business_id = business["id"]
    ops = app_ops.operations

    def wait_step():
        return {"step_key": "hold", "name": "Hold resource",
                "kind": "task_handler", "action_class": "task.update_status",
                "substrate": {"handler": "core.wait",
                              "payload": {"milliseconds": 1500}},
                "acceptance_criteria": {"task_status": "completed"}}

    policy = {"resource_ref": "content-calendar"}
    first = make_workflow(app_ops, steps=[wait_step()],
                          business_id=business_id, name="first holder",
                          execution_policy=policy)
    second = make_workflow(app_ops, steps=[echo_step("hold")],
                           business_id=business_id, name="second contender",
                           execution_policy=policy)
    task = asyncio.create_task(ops.start_workflow(OWNER, first["id"]))
    # Wait until the first workflow's step is genuinely executing
    # (state-based, not a fixed sleep — the contention must be real).
    for _ in range(100):
        state = _task(app_ops, first["id"], "hold")["status"]
        if state == "RUNNING":
            break
        await asyncio.sleep(0.02)
    assert state == "RUNNING"
    second_result = await ops.start_workflow(OWNER, second["id"])
    assert second_result["status"] in ("RUNNING", "PAUSED")
    second_task = _task(app_ops, second["id"], "hold")
    assert second_task["status"] == "PENDING"  # deferred, not executed
    decisions = ops.list_decisions(OWNER, workflow_id=second["id"])
    assert any(d["category"] == "DEFER" for d in decisions["items"])
    first_result = await task
    assert first_result["status"] == "COMPLETED"
    # After the incumbent finishes, the deferred workflow proceeds.
    second_final = await ops.drive_workflow(second["id"], OWNER)
    assert second_final["status"] == "COMPLETED"
    history = app_ops.tasks.history(
        _task(app_ops, second["id"], "hold")["substrate_ref"])
    assert len(history) == 1


async def test_scenario_11_business_emergency_stop_is_scoped(app_ops):
    """Stopping Business A pauses only A; Business B keeps running.
    Restart of A requires the owner."""
    _o1, biz_a = await make_fixture_business(app_ops, name="Biz Alpha")
    _o2, biz_b = await make_fixture_business(app_ops, name="Biz Beta")
    register_agent(app_ops, AGENT.id, business_ref=biz_a["id"])
    register_agent(app_ops, AGENT2.id, business_ref=biz_b["id"])
    ops = app_ops.operations
    wf_a = make_workflow(app_ops, steps=[echo_step("a1")],
                         business_id=biz_a["id"], name="A work")
    wf_b = make_workflow(app_ops, steps=[echo_step("b1")],
                         business_id=biz_b["id"], name="B work")
    # Start A (completes), then a second A workflow is created.
    await ops.start_workflow(OWNER, wf_a["id"])

    stop = await ops.emergency_stop(OWNER, "business", biz_a["id"])
    assert stop["scope"] == "business"
    assert app_ops.survival.is_paused(biz_a["id"]) is True
    assert app_ops.survival.is_paused(biz_b["id"]) is False
    # Business B is entirely unaffected.
    result_b = await ops.start_workflow(OWNER, wf_b["id"])
    assert result_b["status"] == "COMPLETED"
    # New work for A does not execute while stopped: the decision
    # engine pauses it before any substrate call.
    wf_a2 = make_workflow(app_ops, steps=[echo_step("a2")],
                          business_id=biz_a["id"], name="A later work")
    paused = await ops.start_workflow(OWNER, wf_a2["id"])
    assert paused["status"] == "PAUSED"
    assert _task(app_ops, wf_a2["id"], "a2")["substrate_ref"] is None
    # A non-owner cannot restart the business.
    with pytest.raises(PermissionDeniedError):
        await ops.emergency_resume(AGENT, "business", biz_a["id"])
    # The owner resumes; A's paused workflow can now complete.
    await ops.emergency_resume(OWNER, "business", biz_a["id"])
    assert app_ops.survival.is_paused(biz_a["id"]) is False
    resumed = await ops.resume_workflow(OWNER, wf_a2["id"])
    assert resumed["status"] == "COMPLETED"


async def test_scenario_12_completion_is_not_success_without_verification(
        app_ops):
    """The substrate completes but the acceptance criteria fail:
    the workflow is FAILED with verification evidence, never
    reported as verified success."""
    register_agent(app_ops, AGENT.id)
    ops = app_ops.operations
    step = echo_step("check")
    step["acceptance_criteria"] = {"result_equals": {"ok": False}}
    view = make_workflow(app_ops, steps=[step])
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "FAILED"
    assert result["verified_outcome"] == "failed"
    task = _task(app_ops, view["id"], "check")
    assert task["status"] == "FAILED"
    assert task["verification_status"] == "failed"
    assert task["error"]["verification"]["status"] == "failed"
    # The substrate really did complete — verification still failed it.
    substrate = app_ops.tasks.get(task["substrate_ref"])
    assert substrate.status == "completed"


async def test_scenario_13_learning_only_from_verified_outcomes(app_ops):
    """Verified completion records exactly one P-09 learning entry;
    a failed-verification workflow records none."""
    from app.database.models.memory import LearningRecord
    register_agent(app_ops, AGENT.id)
    ops = app_ops.operations
    good = make_workflow(app_ops, steps=[echo_step("ok")], name="verified run")
    result = await ops.start_workflow(OWNER, good["id"])
    assert result["status"] == "COMPLETED"
    assert result["learning_record_id"]

    bad_step = echo_step("check")
    bad_step["acceptance_criteria"] = {"result_equals": {"ok": False}}
    bad = make_workflow(app_ops, steps=[bad_step], name="failed run")
    failed = await ops.start_workflow(OWNER, bad["id"])
    assert failed["status"] == "FAILED"
    assert failed["learning_record_id"] is None

    session = app_ops.session_factory()
    try:
        good_records = list(session.query(LearningRecord)
                            .filter_by(source_ref=good["id"]))
        bad_records = list(session.query(LearningRecord)
                           .filter_by(source_ref=bad["id"]))
    finally:
        session.close()
    assert len(good_records) == 1
    # Mechanically capped by P-09: one observation never claims more.
    assert good_records[0].confidence == "LOW"
    assert bad_records == []


async def test_scenario_14_unauthorized_autonomous_action_blocked(app_ops):
    """Agent scoping, governance authority, rejected approvals and
    raw-instruction creation are all refused; nothing executes."""
    from app.core.exceptions import ValidationError
    register_agent(app_ops, AGENT.id, business_ref="biz-owned-by-test")
    _o, business = await make_fixture_business(app_ops)
    ops = app_ops.operations
    # An agent cannot create a workflow for a business it is not
    # scoped to.
    with pytest.raises(PermissionDeniedError):
        ops.create_workflow(AGENT, {
            "name": "intrusion", "business_id": business["id"],
            "definition": {"steps": [echo_step("x")]}})
    # An agent cannot set autonomy policy (governance is owner-only).
    with pytest.raises(PermissionDeniedError):
        ops.set_autonomy_policy(AGENT, {
            "scope_type": "global", "max_level": 4})
    # Raw instruction text is not an executable workflow definition.
    with pytest.raises(ValidationError):
        ops.create_workflow(OWNER, {
            "name": "raw", "definition": {"instruction": "do anything"}})
    # A rejected owner approval means the step NEVER executes.
    grant_permission(app_ops, AGENT, Permission.MODIFY_BUSINESS_DATA)
    view = make_workflow(app_ops, steps=[{
        "step_key": "transfer", "name": "Transfer", "kind": "task_handler",
        "action_class": "financial.transfer",
        "substrate": {"handler": "core.echo_check",
                      "payload": {"message": "x"}},
        "acceptance_criteria": {"task_status": "completed"}}],
        autonomy_level=4)
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "WAITING_FOR_APPROVAL"
    link = _link(app_ops, view["id"])
    app_ops.approvals.decide(link, OWNER, False)
    await ops.check_approvals(OWNER)
    task = _task(app_ops, view["id"], "transfer")
    assert task["status"] == "FAILED"
    assert task["substrate_ref"] is None  # never reached the substrate
    # The pipeline is the only surface: no direct step execution API.
    assert not hasattr(ops, "execute_step_directly")


async def test_scenario_15_owner_raises_autonomy_for_one_workflow(app_ops):
    """The owner raises autonomy for ONE workflow: its resolution
    rises; a sibling workflow and the agent's general permissions
    are unchanged."""
    register_agent(app_ops, AGENT.id)
    grant_permission(app_ops, AGENT, Permission.MODIFY_BUSINESS_DATA)
    ops = app_ops.operations

    def publish_workflow(name):
        return make_workflow(app_ops, steps=[{
            "step_key": "publish", "name": "Publish", "kind": "task_handler",
            "action_class": "content.publish",
            "substrate": {"handler": "core.echo_check",
                          "payload": {"message": "go"}},
            "acceptance_criteria": {"task_status": "completed"}}],
            name=name, autonomy_level=1)

    raised = publish_workflow("raised workflow")
    sibling = publish_workflow("sibling workflow")
    ops.set_autonomy_policy(OWNER, {
        "scope_type": "workflow", "scope_ref": raised["id"],
        "max_level": 3, "reason": "owner raises this workflow only"})
    res_raised = ops.resolve_autonomy(
        business_id=None, workflow_id=raised["id"], agent_id=AGENT.id,
        workflow_declared_level=1, declared_by_owner=True,
        action_class="content.publish")
    res_sibling = ops.resolve_autonomy(
        business_id=None, workflow_id=sibling["id"], agent_id=AGENT.id,
        workflow_declared_level=1, declared_by_owner=True,
        action_class="content.publish")
    assert res_raised["effective_level"] == 3
    assert res_sibling["effective_level"] == 1
    assert res_sibling["approval_required"] is True
    # The agent's underlying permissions did not widen.
    engine = app_ops.permissions
    assert engine.check(AGENT, Permission.APPROVE_ACTIONS).allowed is False
    assert engine.check(AGENT, Permission.MODIFY_SYSTEM_CONFIG).allowed \
        is False
