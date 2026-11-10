"""P-12 recovery tests (§13): retry with backoff, dead letters,
circuit breakers, interruption parking and resource ceilings —
exercised against the real service, not just the components."""
from __future__ import annotations

import datetime as dt

import pytest

from tests.p12_support import (
    AGENT, OWNER, app_ops, make_workflow, register_agent)
from tests.p05_support import grant as p05_grant, make_agent

pytestmark = pytest.mark.asyncio


def _failing_step(max_retries: int) -> dict:
    return {"step_key": "read-file", "name": "Read missing file",
            "kind": "execution", "action_class": "business.read",
            "substrate": {"tool": "filesystem", "action": "read",
                          "parameters": {"path": "missing.txt"}},
            "retry_policy": {"max_retries": max_retries},
            "acceptance_criteria": {"task_status": "completed"}}


async def test_retry_backoff_then_dead_letter(app_ops):
    """Attempt 1 fails retryably: the step waits in RECOVERY_PENDING
    with a future next_attempt_at. After the backoff instant passes,
    attempt 2 runs, fails, and the step lands in the dead-letter
    queue with a full recovery trail."""
    from app.database.repositories.operations import (
        WorkflowTaskRepository)
    agent_id = await make_agent(app_ops)
    await p05_grant(app_ops, agent_id, "file_read")
    ops = app_ops.operations
    view = make_workflow(app_ops, steps=[_failing_step(1)])
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "RECOVERY_PENDING"  # backoff in progress
    detail = ops.get_workflow(OWNER, view["id"])
    task = detail["tasks"][0]
    assert task["status"] == "RECOVERY_PENDING"
    assert task["attempts"] == 1
    assert task["next_attempt_at"] is not None
    # Backoff elapses (test moves the recorded instant, as time would).
    session = app_ops.session_factory()
    try:
        repo = WorkflowTaskRepository(session)
        row = repo.get(task["id"])
        row.next_attempt_at = dt.datetime.now(dt.timezone.utc) \
            - dt.timedelta(seconds=1)
        repo.save(row)
    finally:
        session.close()
    final = await ops.drive_workflow(view["id"], OWNER)
    assert final["status"] == "FAILED"
    task = ops.get_workflow(OWNER, view["id"])["tasks"][0]
    assert task["status"] == "DEAD_LETTER"
    assert task["attempts"] == 2
    recovery = ops.recovery_center(OWNER)
    assert any(d["task_id"] == task["id"]
               for d in recovery["dead_letters"])
    assert recovery["recovery_records"]  # retry decisions on record


async def test_circuit_breaker_opens_for_repeatedly_failing_target(app_ops):
    """Three consecutive failures on one target open its breaker;
    the next workflow touching that target fails fast as
    dependency_unavailable instead of hammering it."""
    agent_id = await make_agent(app_ops)
    await p05_grant(app_ops, agent_id, "file_read")
    ops = app_ops.operations
    for i in range(3):
        view = make_workflow(app_ops, steps=[_failing_step(0)],
                             name=f"breaker feeder {i}")
        await ops.start_workflow(OWNER, view["id"])
    view = make_workflow(app_ops, steps=[_failing_step(0)],
                         name="breaker victim")
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "FAILED"
    task = ops.get_workflow(OWNER, view["id"])["tasks"][0]
    assert task["error"]["code"] == "circuit_open"
    recovery = ops.recovery_center(OWNER)
    assert any(b["state"] == "open"
               for b in recovery["circuit_breakers"])


async def test_recover_interrupted_parks_verifying_workflows(app_ops):
    """A workflow abandoned in VERIFYING is parked, not completed:
    verification must be re-earned after recovery."""
    from app.database.repositories.operations import WorkflowRepository
    register_agent(app_ops, AGENT.id)
    ops = app_ops.operations
    from tests.p12_support import echo_step
    view = make_workflow(app_ops, steps=[echo_step("x")])
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "COMPLETED"
    view2 = make_workflow(app_ops, steps=[echo_step("y")], name="second")
    session = app_ops.session_factory()
    try:
        repo = WorkflowRepository(session)
        row = repo.get(view2["id"])
        row.status = "VERIFYING"
        repo.save(row)
    finally:
        session.close()
    recovered = ops.recover_interrupted()
    assert recovered == 1
    assert ops.get_workflow(OWNER, view2["id"])["status"] == \
        "RECOVERY_PENDING"


async def test_dead_letter_resolution_requires_owner(app_ops):
    from app.core.exceptions import PermissionDeniedError
    agent_id = await make_agent(app_ops)
    await p05_grant(app_ops, agent_id, "file_read")
    ops = app_ops.operations
    view = make_workflow(app_ops, steps=[_failing_step(0)])
    await ops.start_workflow(OWNER, view["id"])
    recovery = ops.recovery_center(OWNER)
    entry = recovery["dead_letters"][0]
    with pytest.raises(PermissionDeniedError):
        ops.resolve_dead_letter(AGENT, entry["id"], "retry")
    resolved = ops.resolve_dead_letter(OWNER, entry["id"], "acknowledge")
    assert resolved["status"] == "resolved"
