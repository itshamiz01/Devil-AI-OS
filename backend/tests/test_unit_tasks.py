"""Unit tests: queue bounds/priority, submission validation, idempotency,
retry behaviour, approvals service, permission engine."""
from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from app.core.exceptions import (
    InvalidStateTransitionError, PermissionDeniedError, QueueFullError, ValidationError,
)
from app.permissions.approvals import ApprovalService, parameters_hash
from app.permissions.models import Permission
from app.tasks.handlers import EmptyPayload
from app.tasks.models import TaskStatus
from tests.conftest import AGENT, EXTERNAL, OWNER, SERVICE, wait_for_status


async def test_submit_and_complete_echo(application):
    task = await application.tasks.submit(
        OWNER, name="echo", handler_name="core.echo_check", payload={"message": "hello"})
    status = await wait_for_status(application.tasks, task.id, {"completed"})
    assert status == "completed"
    done = application.tasks.get(task.id)
    assert done.result["echo"]["message"] == "hello"
    assert len(application.tasks.history(task.id)) == 1


async def test_unknown_handler_rejected_at_submission(application):
    with pytest.raises(ValidationError):
        await application.tasks.submit(OWNER, name="bad", handler_name="os.system",
                                       payload={"command": "rm -rf /"})


async def test_invalid_payload_rejected(application):
    with pytest.raises(ValidationError):
        await application.tasks.submit(OWNER, name="bad", handler_name="core.echo_check",
                                       payload={"nope": 1})


async def test_submit_permission_denied_for_external(application):
    with pytest.raises(PermissionDeniedError):
        await application.tasks.submit(EXTERNAL, name="x", handler_name="core.noop")


async def test_idempotency_returns_same_task(application):
    t1 = await application.tasks.submit(OWNER, name="a", handler_name="core.noop",
                                        idempotency_key="key-1")
    t2 = await application.tasks.submit(OWNER, name="a", handler_name="core.noop",
                                        idempotency_key="key-1")
    assert t1.id == t2.id


async def test_queue_capacity_backpressure(application):
    application.tasks.max_concurrency = 0  # worker claims nothing; queue depth stays 1
    application.tasks.queue.capacity = 1
    await application.tasks.submit(OWNER, name="first", handler_name="core.wait",
                                   payload={"milliseconds": 300})
    with pytest.raises(QueueFullError):
        await application.tasks.submit(OWNER, name="second", handler_name="core.noop")


async def test_priority_ordering(application):
    # Block the single worker slot, queue two tasks, then release.
    application.tasks.max_concurrency = 1
    blocker = await application.tasks.submit(OWNER, name="blocker", handler_name="core.wait",
                                             payload={"milliseconds": 400}, priority=5)
    low = await application.tasks.submit(OWNER, name="low", handler_name="core.noop", priority=1)
    high = await application.tasks.submit(OWNER, name="high", handler_name="core.noop", priority=9)
    await wait_for_status(application.tasks, blocker.id, {"completed"})
    await wait_for_status(application.tasks, high.id, {"completed"})
    await wait_for_status(application.tasks, low.id, {"completed"})
    high_task = application.tasks.get(high.id)
    low_task = application.tasks.get(low.id)
    assert high_task.started_at <= low_task.started_at


async def test_retry_on_transient_failure(application):
    calls = {"n": 0}

    async def flaky(payload, context):
        calls["n"] += 1
        if calls["n"] < 3:
            from app.tasks.models import ErrorKind, TaskExecutionError
            raise TaskExecutionError("boom", ErrorKind.TRANSIENT)
        return {"ok": True}

    application.tasks.registry.register("core.flaky_test", flaky, EmptyPayload)
    task = await application.tasks.submit(OWNER, name="flaky", handler_name="core.flaky_test",
                                          max_retries=5)
    await wait_for_status(application.tasks, task.id, {"completed"})
    assert calls["n"] == 3
    assert len(application.tasks.history(task.id)) == 3


async def test_no_retry_on_invalid_input_failure(application):
    async def bad(payload, context):
        from app.tasks.models import ErrorKind, TaskExecutionError
        raise TaskExecutionError("nope", ErrorKind.INVALID_INPUT)

    application.tasks.registry.register("core.bad_test", bad, EmptyPayload)
    task = await application.tasks.submit(OWNER, name="bad", handler_name="core.bad_test",
                                          max_retries=5)
    await wait_for_status(application.tasks, task.id, {"failed"})
    assert len(application.tasks.history(task.id)) == 1


async def test_task_timeout(application):
    task = await application.tasks.submit(OWNER, name="slow", handler_name="core.wait",
                                          payload={"milliseconds": 2000}, timeout_seconds=0.2)
    await wait_for_status(application.tasks, task.id, {"failed"})
    assert application.tasks.get(task.id).error["kind"] == "timeout"


async def test_cancel_queued_task(application):
    application.tasks.max_concurrency = 1
    blocker = await application.tasks.submit(OWNER, name="blocker", handler_name="core.wait",
                                             payload={"milliseconds": 500})
    victim = await application.tasks.submit(OWNER, name="victim", handler_name="core.noop")
    cancelled = await application.tasks.cancel(OWNER, victim.id)
    assert cancelled.status == "cancelled"
    await wait_for_status(application.tasks, blocker.id, {"completed"})


async def test_invalid_transition_raises(application):
    task = await application.tasks.submit(OWNER, name="x", handler_name="core.noop")
    await wait_for_status(application.tasks, task.id, {"completed"})
    session = application.session_factory()
    try:
        from app.database.repositories.core import TaskRepository
        repo = TaskRepository(session)
        row = repo.get(task.id)
        from app.tasks.models import TaskStatus as TS
        with pytest.raises(InvalidStateTransitionError):
            application.tasks.transition(row, TS.RUNNING, repo)
    finally:
        session.close()


async def test_requires_approval_task_waits(application):
    task = await application.tasks.submit(OWNER, name="gated", handler_name="core.noop",
                                          requires_approval=True)
    await asyncio.sleep(0.2)
    assert application.tasks.get(task.id).status == "waiting_for_approval"
    application.tasks.approve_task(task.id)
    await wait_for_status(application.tasks, task.id, {"completed"})


# ---------------------------------------------------------------- approvals
def test_approval_lifecycle_and_binding(application):
    svc: ApprovalService = application.approvals
    approval = svc.create(AGENT, action="task.execute", resource="task:1",
                          risk_classification="high", reason="test",
                          requested_permissions=[Permission.EXECUTE_TOOLS.value],
                          parameters={"task_id": "1", "payload": {"a": 1}})
    assert approval.status == "pending"
    # Creating a request does not authorize: binding fails while pending.
    assert not svc.verify_binding(approval, "task.execute", "task:1",
                                  {"task_id": "1", "payload": {"a": 1}})
    decided = svc.decide(approval.id, OWNER, approve=True)
    assert decided.status == "approved"
    assert svc.verify_binding(decided, "task.execute", "task:1",
                              {"task_id": "1", "payload": {"a": 1}})
    # Changed parameters invalidate the approval.
    assert not svc.verify_binding(decided, "task.execute", "task:1",
                                  {"task_id": "1", "payload": {"a": 2}})
    from app.core.exceptions import ApprovalError
    with pytest.raises(ApprovalError):
        svc.decide(approval.id, OWNER, approve=True)  # already decided


def test_approval_expiry(application):
    svc: ApprovalService = application.approvals
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
    approval = svc.create(AGENT, action="x", resource=None, risk_classification="low",
                          reason=None, requested_permissions=[], parameters={}, expires_at=past)
    loaded = svc.get(approval.id)
    assert loaded.status == "expired"


def test_parameters_hash_is_stable_and_sensitive():
    h1 = parameters_hash("a", "r", {"x": 1, "y": 2})
    h2 = parameters_hash("a", "r", {"y": 2, "x": 1})
    h3 = parameters_hash("a", "r", {"x": 1, "y": 3})
    assert h1 == h2 and h1 != h3


# --------------------------------------------------------------- permissions
def test_permission_engine_role_defaults(application):
    engine = application.permissions
    assert engine.check(OWNER, "approve_actions").allowed
    assert engine.check(AGENT, "submit_tasks").allowed
    assert not engine.check(AGENT, "approve_actions").allowed
    assert not engine.check(EXTERNAL, "read_system_data").allowed
    assert engine.check(SERVICE, "read_system_data").allowed
    assert not engine.check(SERVICE, "approve_actions").allowed
    # Approval-required permissions flag the requirement even when granted.
    decision = engine.check(OWNER, "request_financial_operations")
    assert decision.allowed and decision.requires_approval


def test_permission_engine_explicit_deny_wins(application):
    from app.database.models.core import Permission as PermissionRow
    from app.database.repositories.core import PermissionRepository

    session = application.session_factory()
    try:
        PermissionRepository(session).add(PermissionRow(
            principal_type="agent", principal_id="agent-1",
            permission="submit_tasks", effect="deny", resource=None))
    finally:
        session.close()
    decision = application.permissions.check(AGENT, "submit_tasks")
    assert not decision.allowed and "explicit deny" in decision.reason


def test_permission_engine_db_allow_for_external(application):
    from app.database.models.core import Permission as PermissionRow
    from app.database.repositories.core import PermissionRepository

    session = application.session_factory()
    try:
        PermissionRepository(session).add(PermissionRow(
            principal_type="external", principal_id="ext-1",
            permission="read_system_data", effect="allow", resource=None))
    finally:
        session.close()
    assert application.permissions.check(EXTERNAL, "read_system_data").allowed
