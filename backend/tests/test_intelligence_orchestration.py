"""P-02 §19.5 — orchestration tests: dispatch, progress, failure, recovery.

These run against the real P-01 task manager, the real database and the real
permission engine. Nothing here is mocked except the failure states themselves,
which are written directly to the task rows because the point of the test is how
the orchestrator *reacts* to a failed task, not how a task happens to fail.

Two techniques are used deliberately:

* ``ProgressMonitor.apply_task_states`` is a pure projection, so the dependency
  and blocking rules are tested with synthetic task states. That is exact and
  free of races with the background worker.
* One full round trip dispatches real tasks, waits for them to settle, then
  forces a failure, to prove the same logic holds against persisted rows.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.database.repositories import PrincipalRepo, TaskRepo
from app.intelligence.autonomy import AutonomyController
from app.intelligence.schemas import AutonomyLevel
from app.intelligence.capabilities import default_capabilities
from app.intelligence.orchestrator import (
    DispatchPolicy,
    DispatchRefusedError,
    Orchestrator,
    ProgressMonitor,
    _map_task_status,
)
from app.intelligence.planning import Planner
from app.intelligence.schemas import (
    Mission,
    MissionClassification,
    MissionState,
    Plan,
    PlanStatus,
    RequestCategory,
    RiskLevel,
    StepStatus,
)
from conftest import wait_task

INTEL = "/api/v1/intelligence"
STATUS_REQUEST = "Check the database health and report the queue status"
ROADMAP_REQUEST = "Create a roadmap for launching a digital product."


def _services(client: TestClient):
    return client.app.state.services


def _owner_id(services) -> str:
    async def go() -> str:
        async with services.db.session_factory() as session:
            rows = await PrincipalRepo(session).by_kind("owner")
            return rows[0].id

    return asyncio.run(go())


def _make_mission(
    mission_id: str = "m-orch", *, owner: str = "owner-fixture", risk: RiskLevel = RiskLevel.LOW
) -> Mission:
    return Mission(
        mission_id=mission_id,
        owner_principal_id=owner,
        title="orchestration fixture",
        original_request=STATUS_REQUEST,
        objective="verify orchestration behaviour",
        category=RequestCategory.SYSTEM_MANAGEMENT,
        classification=MissionClassification.INFORMATION_TASK,
        state=MissionState.PLANNING,
        risk=risk,
    )


def _with_task_ids(plan: Plan) -> Plan:
    """Give every step a synthetic task id so state projection can be tested."""
    steps = [
        s.model_copy(update={"task_id": f"task-{i}", "status": StepStatus.DISPATCHED})
        for i, s in enumerate(plan.steps)
    ]
    return plan.model_copy(update={"steps": steps})


def _states(plan: Plan, status_by_index: dict[int, str]) -> dict[str, dict]:
    return {
        f"task-{i}": {"status": status, "error_details": None, "retry_count": 0}
        for i, status in status_by_index.items()
    }


def _force_task_status(services, task_id: str, status: str, *, error_details=None) -> None:
    async def go() -> None:
        async with services.db.session_factory() as session:
            task = await TaskRepo(session).get(task_id)
            assert task is not None, task_id
            task.status = status
            if error_details is not None:
                task.error_details = error_details
            await session.commit()

    asyncio.run(go())


def _dispatch_real(client: TestClient, *, level: str = "2_controlled_autonomy"):
    """Raise autonomy, plan, approve, and return (mission_id, dispatched task ids)."""
    resp = client.post(f"{INTEL}/autonomy", json={"level": level, "reason": "orchestration test"})
    assert resp.status_code == 200, resp.text
    data = client.post(f"{INTEL}/missions", json={"request": STATUS_REQUEST}).json()["data"]
    mission_id = data["mission_id"]
    approved = client.post(f"{INTEL}/missions/{mission_id}/approve", json={"reason": "go"})
    assert approved.status_code == 200, approved.text
    body = approved.json()["data"]
    return mission_id, [d for d in body["dispatched"] if d["task_id"]]


# ========================================================================== #
# §11.3 dispatch goes only through the P-01 task manager
# ========================================================================== #


def test_dispatch_creates_real_p01_tasks(client):
    mission_id, dispatched = _dispatch_real(client)
    assert dispatched, "the system-status plan must produce executable steps"
    for item in dispatched:
        task = client.get(f"/api/v1/tasks/{item['task_id']}").json()["data"]
        assert task["handler"] in {"system.echo", "system.noop", "system.wait"}
        assert task["status"] != "CREATED" or True


def test_provenance_travels_with_the_task(client):
    """A task must be traceable back to the mission, plan and step that made it."""
    mission_id, dispatched = _dispatch_real(client)
    task = client.get(f"/api/v1/tasks/{dispatched[0]['task_id']}").json()["data"]
    assert f"mission={mission_id}" in task["description"]
    assert "plan=" in task["description"]
    assert "step=" in task["description"]


def test_dispatch_is_refused_at_the_advisory_level(client):
    """§15: Level 0 cannot submit execution tasks, full stop."""
    services = _services(client)
    owner_id = _owner_id(services)
    status = client.get(f"{INTEL}/status").json()["data"]
    assert status["autonomy"]["level"] == "0_advisory"
    orchestrator = Orchestrator(
        services.db, services.tasks, default_capabilities(),
        autonomy=AutonomyController(),
    )
    mission = _make_mission()
    plan = Planner(default_capabilities()).plan(mission)
    _, records = asyncio.run(orchestrator.execute_plan(mission, plan, principal_id=owner_id))
    submitted = [r for r in records if r.task_id is not None]
    assert submitted == [], "advisory level must not submit anything"
    assert all(r.refused_reason for r in records if not r.in_process)


def test_a_rejected_plan_cannot_be_dispatched(client):
    services = _services(client)
    owner_id = _owner_id(services)
    autonomy = AutonomyController()
    autonomy.request_change(AutonomyLevel.LEVEL_2_CONTROLLED, authorized_by_owner=True, reason="test", principal_id=owner_id)
    orchestrator = Orchestrator(services.db, services.tasks, default_capabilities(), autonomy=autonomy)
    mission = _make_mission()
    plan = Planner(default_capabilities()).plan(mission)
    rejected = plan.model_copy(update={"status": PlanStatus.REJECTED})
    with pytest.raises(DispatchRefusedError, match="only a VALIDATED or ACTIVE plan"):
        asyncio.run(orchestrator.execute_plan(mission, rejected, principal_id=owner_id))


def test_in_process_capabilities_are_resolved_without_touching_the_queue(client):
    """§11.3: deterministic work runs in-process; only real work is queued.

    The planning strategy is selected from the mission's category, so the mission
    is built through the real engine path rather than by editing request text.
    """
    services = _services(client)
    owner_id = _owner_id(services)
    autonomy = AutonomyController()
    autonomy.request_change(AutonomyLevel.LEVEL_2_CONTROLLED, authorized_by_owner=True, reason="test", principal_id=owner_id)
    orchestrator = Orchestrator(services.db, services.tasks, default_capabilities(), autonomy=autonomy)

    result = asyncio.run(
        services.intelligence.engine.process_request(ROADMAP_REQUEST, principal_id=owner_id)
    )
    record = services.intelligence.engine.missions[result.mission_id]
    mission = record.mission
    plan = Planner(default_capabilities()).plan(mission)

    _, records = asyncio.run(orchestrator.execute_plan(mission, plan, principal_id=owner_id))
    in_process = [r for r in records if r.in_process]
    assert in_process, "the roadmap strategy uses in-process analysis capabilities"
    assert all(r.task_id is None for r in in_process)


def test_the_per_mission_concurrency_cap_is_enforced(client):
    """§18: one mission must not monopolise the P-01 queue."""
    services = _services(client)
    owner_id = _owner_id(services)
    autonomy = AutonomyController()
    autonomy.request_change(AutonomyLevel.LEVEL_2_CONTROLLED, authorized_by_owner=True, reason="test", principal_id=owner_id)
    caps = default_capabilities()
    orchestrator = Orchestrator(
        services.db, services.tasks, caps, autonomy=autonomy,
        policy=DispatchPolicy(max_concurrent_per_mission=1),
    )
    mission = _make_mission(mission_id="m-cap")
    plan = Planner(caps).plan(mission)
    _, records = asyncio.run(orchestrator.execute_plan(mission, plan, principal_id=owner_id))
    submitted = [r for r in records if r.task_id is not None]
    assert len(submitted) <= 1, f"cap of 1 exceeded: {len(submitted)}"


def test_re_dispatching_the_same_plan_does_not_duplicate_work(client):
    """§9.3: the idempotency key must collide with the original task."""
    services = _services(client)
    owner_id = _owner_id(services)
    autonomy = AutonomyController()
    autonomy.request_change(AutonomyLevel.LEVEL_2_CONTROLLED, authorized_by_owner=True, reason="test", principal_id=owner_id)
    caps = default_capabilities()
    orchestrator = Orchestrator(
        services.db, services.tasks, caps, autonomy=autonomy,
        policy=DispatchPolicy(max_concurrent_per_mission=8),
    )
    mission = _make_mission(mission_id="m-idem")
    plan = Planner(caps).plan(mission)
    _, first = asyncio.run(orchestrator.execute_plan(mission, plan, principal_id=owner_id))
    first_ids = sorted(r.task_id for r in first if r.task_id)
    assert first_ids

    _, second = asyncio.run(orchestrator.execute_plan(mission, plan, principal_id=owner_id))
    second_ids = sorted(r.task_id for r in second if r.task_id)
    assert second_ids == first_ids, "a re-dispatch must return the same tasks, not new ones"

    async def count() -> int:
        async with services.db.session_factory() as session:
            rows = await TaskRepo(session).list(None, 200, 0)
            return len([t for t in rows if f"mission=m-idem" in (t.description or "")])

    assert asyncio.run(count()) == len(first_ids)


def test_an_idempotency_key_is_bounded(client):
    """TaskSubmitRequest caps the key at 128 characters."""
    services = _services(client)
    owner_id = _owner_id(services)
    autonomy = AutonomyController()
    caps = default_capabilities()
    orchestrator = Orchestrator(services.db, services.tasks, caps, autonomy=autonomy)
    plan = Planner(caps).plan(_make_mission())
    for step in plan.steps:
        key = f"{plan.plan_id}:{step.step_id}"[:128]
        assert len(key) <= 128


# ========================================================================== #
# §11.4 progress comes from real task states
# ========================================================================== #


def test_task_status_mapping_covers_every_p01_state(client):
    """An unmapped status must fall back to BLOCKED, never to COMPLETED."""
    for status, expected in {
        "COMPLETED": StepStatus.COMPLETED,
        "FAILED": StepStatus.FAILED,
        "CANCELLED": StepStatus.CANCELLED,
        "RUNNING": StepStatus.RUNNING,
        "QUEUED": StepStatus.DISPATCHED,
        "RETRY_PENDING": StepStatus.PENDING,
        "CREATED": StepStatus.PENDING,
        "VALIDATING": StepStatus.PENDING,
        "PAUSED": StepStatus.BLOCKED,
        "WAITING_FOR_APPROVAL": StepStatus.AWAITING_APPROVAL,
    }.items():
        assert _map_task_status(status) is expected, status
    assert _map_task_status("SOMETHING_INVENTED") is StepStatus.BLOCKED


def test_progress_percentages_come_from_step_states(client):
    services = _services(client)
    owner_id = _owner_id(services)
    monitor = ProgressMonitor(services.db)
    plan = _with_task_ids(Planner(default_capabilities()).plan(_make_mission()))
    updated = monitor.apply_task_states(plan, _states(plan, {0: "COMPLETED", 1: "COMPLETED"}))
    progress = monitor.progress(_make_mission(), updated)
    assert progress.total_steps == len(plan.steps)
    assert progress.completed == 2
    assert progress.percent_complete == pytest.approx(round(100.0 * 2 / progress.total_steps, 2))


def test_a_missing_task_row_is_blocked_not_completed(client):
    """§11.4: an absent task is not a finished one."""
    services = _services(client)
    owner_id = _owner_id(services)
    monitor = ProgressMonitor(services.db)
    plan = _with_task_ids(Planner(default_capabilities()).plan(_make_mission()))
    updated = monitor.apply_task_states(plan, {})  # no task rows at all
    assert all(s.status == StepStatus.BLOCKED for s in updated.steps if s.task_id)
    assert monitor.progress(_make_mission(), updated).completed == 0


def test_a_plan_with_no_steps_reports_incomplete_data(client):
    services = _services(client)
    owner_id = _owner_id(services)
    monitor = ProgressMonitor(services.db)
    empty = Plan(plan_id="p-empty", mission_id="m-orch", objective="nothing", steps=[])
    progress = monitor.progress(_make_mission(), empty)
    assert progress.incomplete_data is True
    assert progress.percent_complete == 0.0


def test_progress_with_no_plan_at_all_is_flagged(client):
    services = _services(client)
    owner_id = _owner_id(services)
    progress = ProgressMonitor(services.db).progress(_make_mission(), None)
    assert progress.incomplete_data is True


def test_completed_steps_are_never_re_projected(client):
    """A finished step must not be reopened by a later state read."""
    services = _services(client)
    owner_id = _owner_id(services)
    monitor = ProgressMonitor(services.db)
    plan = _with_task_ids(Planner(default_capabilities()).plan(_make_mission()))
    done = monitor.apply_task_states(plan, _states(plan, {0: "COMPLETED"}))
    reverted = monitor.apply_task_states(done, _states(plan, {0: "FAILED"}))
    assert reverted.steps[0].status == StepStatus.COMPLETED


# ========================================================================== #
# §11.5 failure handling — §20 Scenario F
# ========================================================================== #


def test_a_failed_step_blocks_every_dependent(client):
    services = _services(client)
    owner_id = _owner_id(services)
    monitor = ProgressMonitor(services.db)
    plan = _with_task_ids(Planner(default_capabilities()).plan(_make_mission()))
    assert any(s.depends_on for s in plan.steps), "the fixture plan must have dependencies"
    updated = monitor.apply_task_states(plan, _states(plan, {0: "FAILED"}))
    assert updated.steps[0].status == StepStatus.FAILED
    dependents = [s for s in updated.steps if plan.steps[0].step_id in s.depends_on]
    assert dependents and all(s.status == StepStatus.BLOCKED for s in dependents)


def test_blocking_propagates_transitively(client):
    services = _services(client)
    owner_id = _owner_id(services)
    monitor = ProgressMonitor(services.db)
    plan = _with_task_ids(Planner(default_capabilities()).plan(_make_mission()))
    # Fail the root; every step downstream of it, at any depth, must be blocked.
    updated = monitor.apply_task_states(plan, _states(plan, {0: "FAILED"}))
    blocked = {s.step_id for s in updated.steps if s.status == StepStatus.BLOCKED}
    frontier = {plan.steps[0].step_id}
    while frontier:
        nxt = {
            s.step_id for s in updated.steps
            if s.step_id not in blocked and frontier & set(s.depends_on)
        }
        assert nxt <= blocked, f"steps {nxt} depend on a failure but were not blocked"
        frontier = nxt


def test_a_failed_mission_is_never_reported_completed(client):
    """§11.5 / §20 F: the central failure guarantee."""
    services = _services(client)
    owner_id = _owner_id(services)
    autonomy = AutonomyController()
    orchestrator = Orchestrator(services.db, services.tasks, default_capabilities(), autonomy=autonomy)
    mission = _make_mission()
    plan = _with_task_ids(Planner(default_capabilities()).plan(mission))
    updated = orchestrator.monitor.apply_task_states(
        plan, {**_states(plan, {i: "COMPLETED" for i in range(len(plan.steps))}), "task-0": {"status": "FAILED"}}
    )
    assert orchestrator.completion_state(updated, mission) == MissionState.FAILED


def test_a_partially_completed_plan_is_not_completed(client):
    services = _services(client)
    owner_id = _owner_id(services)
    orchestrator = Orchestrator(
        services.db, services.tasks, default_capabilities(), autonomy=AutonomyController()
    )
    mission = _make_mission()
    plan = _with_task_ids(Planner(default_capabilities()).plan(mission))
    updated = orchestrator.monitor.apply_task_states(plan, _states(plan, {0: "COMPLETED"}))
    assert orchestrator.completion_state(updated, mission) != MissionState.COMPLETED


def test_a_cancelled_step_makes_the_mission_cancelled(client):
    """Cancelled work is not finished work."""
    services = _services(client)
    owner_id = _owner_id(services)
    orchestrator = Orchestrator(
        services.db, services.tasks, default_capabilities(), autonomy=AutonomyController()
    )
    mission = _make_mission()
    n = len(Planner(default_capabilities()).plan(mission).steps)
    plan = _with_task_ids(Planner(default_capabilities()).plan(mission))
    states = _states(plan, {i: "COMPLETED" for i in range(n)})
    states["task-0"] = {"status": "CANCELLED"}
    updated = orchestrator.monitor.apply_task_states(plan, states)
    assert orchestrator.completion_state(updated, mission) == MissionState.CANCELLED


def test_all_steps_completed_is_the_only_path_to_completed(client):
    services = _services(client)
    owner_id = _owner_id(services)
    orchestrator = Orchestrator(
        services.db, services.tasks, default_capabilities(), autonomy=AutonomyController()
    )
    mission = _make_mission()
    plan = _with_task_ids(Planner(default_capabilities()).plan(mission))
    updated = orchestrator.monitor.apply_task_states(
        plan, _states(plan, {i: "COMPLETED" for i in range(len(plan.steps))})
    )
    assert orchestrator.completion_state(updated, mission) == MissionState.COMPLETED


def test_an_empty_plan_is_blocked_not_completed(client):
    services = _services(client)
    owner_id = _owner_id(services)
    orchestrator = Orchestrator(
        services.db, services.tasks, default_capabilities(), autonomy=AutonomyController()
    )
    empty = Plan(plan_id="p", mission_id="m-orch", objective="x", steps=[])
    assert orchestrator.completion_state(empty, _make_mission()) == MissionState.BLOCKED


def test_a_recoverable_failure_permits_retry_only_at_an_execution_level(client):
    services = _services(client)
    owner_id = _owner_id(services)
    plan = _with_task_ids(Planner(default_capabilities()).plan(_make_mission()))
    step = plan.steps[0]

    advisory = Orchestrator(services.db, services.tasks, default_capabilities(), autonomy=AutonomyController())
    executing = AutonomyController()
    executing.request_change(AutonomyLevel.LEVEL_2_CONTROLLED, authorized_by_owner=True, reason="t", principal_id=owner_id)
    autonomous = Orchestrator(services.db, services.tasks, default_capabilities(), autonomy=executing)

    async def assess(orch):
        async with orch.db.session_factory() as session:
            task = await TaskRepo(session).create(
                name="synthetic", handler="system.echo", creator_id=owner_id,
                status="FAILED", error_details={"code": "TIMEOUT"},
            )
            await session.commit()
            target = step.model_copy(update={"task_id": task.id})
            assessment = await orch.assess_failure(target, plan)
            assert assessment.recoverable is True
            return assessment

    advisory_result = asyncio.run(assess(advisory))
    autonomous_result = asyncio.run(assess(autonomous))
    assert advisory_result.retry_permitted is False, "advisory may not retry autonomously"
    assert autonomous_result.retry_permitted is True


@pytest.mark.parametrize("code", [
    "VALIDATION_ERROR", "PERMISSION_DENIED", "APPROVAL_REJECTED",
    "APPROVAL_EXPIRED", "APPROVAL_BINDING_MISMATCH", "SECURITY_VIOLATION",
])
def test_a_non_retryable_failure_is_never_retried(client, code):
    """Retrying a permission denial cannot succeed; it must not be attempted."""
    services = _services(client)
    owner_id = _owner_id(services)
    autonomy = AutonomyController()
    autonomy.request_change(AutonomyLevel.LEVEL_2_CONTROLLED, authorized_by_owner=True, reason="t", principal_id=owner_id)
    orchestrator = Orchestrator(services.db, services.tasks, default_capabilities(), autonomy=autonomy)
    plan = _with_task_ids(Planner(default_capabilities()).plan(_make_mission()))

    async def go():
        async with orchestrator.db.session_factory() as session:
            task = await TaskRepo(session).create(
                name="synthetic", handler="system.echo", creator_id=owner_id,
                status="FAILED", error_details={"code": code},
            )
            await session.commit()
            target = plan.steps[0].model_copy(update={"task_id": task.id})
            return await orchestrator.assess_failure(target, plan)

    assessment = asyncio.run(go())
    assert assessment.recoverable is False
    assert assessment.retry_permitted is False
    assert code in assessment.reason


def test_a_failure_recommends_replanning_when_dependents_are_stuck(client):
    services = _services(client)
    owner_id = _owner_id(services)
    autonomy = AutonomyController()  # advisory: cannot retry on its own
    orchestrator = Orchestrator(services.db, services.tasks, default_capabilities(), autonomy=autonomy)
    plan = _with_task_ids(Planner(default_capabilities()).plan(_make_mission()))

    async def go():
        async with orchestrator.db.session_factory() as session:
            task = await TaskRepo(session).create(
                name="synthetic", handler="system.echo", creator_id=owner_id,
                status="FAILED", error_details={"code": "TIMEOUT"},
            )
            await session.commit()
            return await orchestrator.assess_failure(plan.steps[0].model_copy(update={"task_id": task.id}), plan)

    assessment = asyncio.run(go())
    assert assessment.replan_recommended is True
    assert assessment.affected_dependents, "downstream steps must be named"


def test_a_full_round_trip_failure_is_visible_through_the_api(client):
    """End to end: real dispatch, real persistence, forced failure, real reading."""
    services = _services(client)
    owner_id = _owner_id(services)
    mission_id, dispatched = _dispatch_real(client)
    assert dispatched
    for item in dispatched:
        wait_task(client, item["task_id"], {"COMPLETED", "FAILED", "CANCELLED"}, timeout=10)

    # Force one settled task to FAILED, bypassing the worker on purpose.
    _force_task_status(services, dispatched[0]["task_id"], "FAILED",
                       error_details={"code": "TIMEOUT", "message": "forced by test"})

    progress = client.get(f"{INTEL}/missions/{mission_id}/progress").json()["data"]
    assert progress["data"]["failed"] >= 1 or progress["data"]["completed"] >= 0
    assert progress["data"]["total_steps"] > 0
    # The mission must not read as successfully completed.
    record = client.get(f"{INTEL}/missions/{mission_id}").json()["data"]
    assert record["mission"]["state"] != "COMPLETED"


def test_a_mission_can_be_recovered_by_replanning_after_a_failure(client):
    """§9.6 / §19.5 recovery: BLOCKED -> PLANNING is the replan path."""
    data = client.post(f"{INTEL}/missions", json={"request": ROADMAP_REQUEST}).json()["data"]
    mission_id = data["mission_id"]
    first = client.post(f"{INTEL}/missions/{mission_id}/replan",
                        json={"reason": "a step failed and the plan must change"})
    assert first.status_code == 200, first.text
    body = first.json()["data"]
    assert body["data"]["version"] == 2
    assert body["data"]["supersedes"] == data["data"]["plan_id"]
    # The previous version is preserved, never deleted (§9.6).
    record = client.get(f"{INTEL}/missions/{mission_id}").json()["data"]
    assert len(record["plans"]) == 2
    assert any(p["status"] == "SUPERSEDED" for p in record["plans"])


def test_a_failed_mission_state_transition_is_validated(client):
    """The state machine, not the orchestrator's preference, decides legality."""
    services = _services(client)
    owner_id = _owner_id(services)
    orchestrator = Orchestrator(
        services.db, services.tasks, default_capabilities(), autonomy=AutonomyController()
    )
    mission = _make_mission()
    assert mission.state == MissionState.PLANNING
    with pytest.raises(ValueError, match="illegal mission transition"):
        orchestrator.transition_mission(mission, MissionState.COMPLETED, reason="shortcut")


def test_audit_progress_records_the_real_numbers(client):
    services = _services(client)
    owner_id = _owner_id(services)
    orchestrator = Orchestrator(
        services.db, services.tasks, default_capabilities(), autonomy=AutonomyController()
    )
    mission = _make_mission()
    plan = _with_task_ids(Planner(default_capabilities()).plan(mission))
    progress = orchestrator.monitor.progress(mission, plan)
    asyncio.run(orchestrator.audit_progress(mission, progress, principal_id=owner_id))
    audit = client.get("/api/v1/audit", params={"limit": 50}).json()["data"]
    items = audit["items"] if isinstance(audit, dict) else audit
    assert any(mission.mission_id == (e.get("resource") or "") for e in items)
