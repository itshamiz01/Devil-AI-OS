"""Failure tests (P-01 §16.4): DB unavailable, queue full, timeouts,
subscriber failure, resource thresholds, shutdown behaviour."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import make_settings, wait_for_status, OWNER


def test_database_unavailable_startup_fails_safely(tmp_path):
    """A broken DB URL must produce a FAILED startup, not a 'healthy' app
    and not an unhandled crash loop."""
    settings = make_settings(tmp_path, database_url="sqlite:////nonexistent-dir-xyz/nope.db",
                             auto_migrate=False)
    app = create_app(settings)
    with pytest.raises(Exception):
        with TestClient(app, raise_server_exceptions=True):
            pass
    assert app.state.application.lifecycle.state.value == "failed"


async def test_readiness_not_ready_when_db_dies(application):
    # Break the engine after startup: readiness must flip to not-ready.
    application.engine.dispose()
    import sqlite3
    application.engine.pool.dispose() if hasattr(application.engine, "pool") else None
    # Point the monitor at a dead engine by replacing it with a bogus one.
    from sqlalchemy import create_engine
    application.monitor.engine = create_engine("sqlite:////nonexistent-dir-xyz/dead.db")
    assert application.monitor.database_healthy() is False


async def test_queue_full_backpressure_error(application):
    application.tasks.max_concurrency = 0
    application.tasks.queue.capacity = 2
    await application.tasks.submit(OWNER, name="one", handler_name="core.noop")
    await application.tasks.submit(OWNER, name="two", handler_name="core.noop")
    from app.core.exceptions import QueueFullError
    with pytest.raises(QueueFullError):
        await application.tasks.submit(OWNER, name="three", handler_name="core.noop")


async def test_nonessential_blocked_when_thresholds_exceeded(application, monkeypatch):
    monkeypatch.setattr(application.monitor, "admission_block_reason",
                        lambda: "resource threshold exceeded: cpu")
    from app.core.exceptions import ResourceBlockedError
    with pytest.raises(ResourceBlockedError):
        await application.tasks.submit(OWNER, name="nice-to-have", handler_name="core.noop")
    # Essential tasks are still admitted.
    task = await application.tasks.submit(OWNER, name="essential", handler_name="core.noop",
                                          essential=True)
    await wait_for_status(application.tasks, task.id, {"completed"})


async def test_task_timeout_marks_failed_with_history(application):
    task = await application.tasks.submit(OWNER, name="slow", handler_name="core.wait",
                                          payload={"milliseconds": 3000}, timeout_seconds=0.15)
    await wait_for_status(application.tasks, task.id, {"failed"})
    history = application.tasks.history(task.id)
    assert history[0].status == "failed" and history[0].error["kind"] == "timeout"


async def test_graceful_shutdown_stops_accepting(application):
    await application.tasks.stop(timeout=2)
    from app.core.exceptions import QueueFullError
    with pytest.raises(QueueFullError):
        await application.tasks.submit(OWNER, name="too-late", handler_name="core.noop")


def test_health_live_vs_ready_distinction(client, auth_headers):
    live = client.get("/api/v1/health/live")
    assert live.status_code == 200 and live.json()["data"]["status"] == "alive"
    ready = client.get("/api/v1/health/ready", headers=auth_headers)
    assert ready.status_code == 200
    # Ready carries dependency information that live must not.
    assert "database_healthy" in ready.json()["data"]
    assert "database_healthy" not in live.json()["data"]
