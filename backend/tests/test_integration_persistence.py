"""Integration: persistence across restarts + interrupted-task recovery +
Alembic migration on a fresh database."""
from __future__ import annotations

import sqlite3

import pytest

from app.core.application import Application
from app.database.connection import run_migrations
from app.permissions.models import Principal, PrincipalType
from tests.conftest import make_settings, wait_for_status

OWNER = Principal(PrincipalType.OWNER, "owner")


async def test_tasks_persist_across_restart(tmp_path):
    settings = make_settings(tmp_path)
    app1 = Application(settings)
    await app1.startup()
    task = await app1.tasks.submit(OWNER, name="persist-me", handler_name="core.noop")
    await wait_for_status(app1.tasks, task.id, {"completed"})
    await app1.shutdown()

    app2 = Application(settings)
    await app2.startup()
    try:
        loaded = app2.tasks.get(task.id)
        assert loaded.status == "completed"
        assert len(app2.tasks.history(task.id)) == 1
    finally:
        await app2.shutdown()


async def test_interrupted_running_task_is_recovered_not_reexecuted(tmp_path):
    settings = make_settings(tmp_path)
    app1 = Application(settings)
    await app1.startup()
    task = await app1.tasks.submit(OWNER, name="long", handler_name="core.wait",
                                   payload={"milliseconds": 10_000}, timeout_seconds=30)
    await wait_for_status(app1.tasks, task.id, {"running"})
    # Simulate a crash: stop the worker WITHOUT graceful task completion,
    # leaving the row in RUNNING.
    app1.tasks._accepting = False
    if app1.tasks._worker_task:
        app1.tasks._worker_task.cancel()
    for running in list(app1.tasks._running):
        running.cancel()
    import asyncio
    await asyncio.sleep(0.3)
    app1.engine.dispose()

    app2 = Application(settings)
    await app2.startup()
    try:
        recovered = app2.tasks.get(task.id)
        assert app2.recovered_task_ids == [task.id]
        assert recovered.status == "paused"
        assert recovered.progress.get("recovery_required") is True
        executions = app2.tasks.history(task.id)
        assert executions and executions[0].status == "interrupted"
        # It must NOT have been blindly re-executed:
        import asyncio as _a
        await _a.sleep(0.3)
        assert app2.tasks.get(task.id).status == "paused"
        assert len(app2.tasks.history(task.id)) == 1
    finally:
        await app2.shutdown()


def test_alembic_upgrade_head_on_fresh_db(tmp_path):
    db = tmp_path / "fresh.db"
    run_migrations(f"sqlite:///{db}")
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {"system_config", "tasks", "task_executions", "agents", "permissions",
                "approvals", "audit_events", "system_events", "app_sessions", "alembic_version"}
    assert expected.issubset(tables)
