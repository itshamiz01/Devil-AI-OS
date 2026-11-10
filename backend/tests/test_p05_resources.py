"""P-05 resource tests (§18/§26, Scenario I): concurrency ceilings are
structured results, never crashes; sessions and payloads are bounded;
metrics report measured values."""
from __future__ import annotations

import asyncio

import pytest

from app.execution.schemas import ExecutionRequestIn
from tests.conftest import OWNER
from tests.p05_support import app_rw, engine, grant, make_agent


# Scenario I: resource exhaustion — the scheduler applies concurrency
# limits, new work stays queued, the application remains responsive.
async def test_scenario_i_subprocess_ceiling_queues_work(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "sandboxed_code_execution")
    service = engine(app_rw)
    service.update_settings(OWNER, {"max_concurrent_subprocesses": 1})

    def payload(marker: str) -> ExecutionRequestIn:
        return ExecutionRequestIn(
            agent_id=agent_id, tool="code_python", action="run",
            parameters={"code": f"import time\ntime.sleep(1.5)\nprint('{marker}')"},
            timeout_seconds=30)

    first = service.submit(OWNER, payload("first"))
    second = service.submit(OWNER, payload("second"))
    assert first.status == second.status == "QUEUED"

    async def run_first():
        return await service.execute(OWNER, first.id)

    task = asyncio.create_task(run_first())
    await asyncio.sleep(0.4)  # first run now holds the only subprocess slot
    blocked = await service.execute(OWNER, second.id)
    assert blocked.status == "QUEUED"
    assert "resource ceiling" in (blocked.result_summary or "")
    completed_first = await task
    assert completed_first.status == "COMPLETED"
    completed_second = await service.execute(OWNER, second.id)
    assert completed_second.status == "COMPLETED"
    metrics = service.metrics()
    assert metrics["ceilings"]["max_concurrent_subprocesses"] == 1
    assert metrics["requests_by_status"]["COMPLETED"] >= 2


async def test_browser_session_ceiling(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "browser_interaction")
    from app.execution.adapters.api import MockTransport
    service = engine(app_rw, browser_transport=MockTransport({}))
    service.update_settings(OWNER, {"max_browser_sessions": 2})
    for _ in range(2):
        opened = await service.submit_and_execute(OWNER, ExecutionRequestIn(
            agent_id=agent_id, tool="browser", action="open_session",
            parameters={"allowed_domains": ["example.com"]}))
        assert opened.status == "COMPLETED"
    third = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="browser", action="open_session",
        parameters={"allowed_domains": ["example.com"]}))
    assert third.status == "FAILED"
    assert third.error_category == "RESOURCE_LIMIT"


async def test_payload_ceiling_rejects_oversized_requests(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "file_write")
    service = engine(app_rw)
    service.update_settings(OWNER, {"max_input_bytes": 200})
    request = service.submit(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="create",
        parameters={"workspace": f"agent:{agent_id}", "path": "big.txt",
                    "content": "x" * 500}))
    assert request.status == "REJECTED"
    assert "exceeds" in request.result_summary


async def test_retry_only_for_idempotent_actions(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "file_read")
    await grant(app_rw, agent_id, "file_write")
    service = engine(app_rw)
    workspace = f"agent:{agent_id}"
    # filesystem move is NOT idempotent: a failed run cannot be retried —
    # repeating a move whose outcome is uncertain is exactly what §16.2
    # forbids.
    failed_move = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="move",
        parameters={"source_workspace": workspace, "source_path": "ghost.txt",
                    "dest_workspace": workspace, "dest_path": "moved.txt"}))
    assert failed_move.status == "FAILED"
    from app.execution.errors import ExecutionStateError
    with pytest.raises(ExecutionStateError):
        await service.execute(OWNER, failed_move.id)
    # An idempotent action (read) may be retried: fail, fix the cause,
    # retry the SAME request to completion.
    failed_read = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="read",
        parameters={"workspace": workspace, "path": "later.txt"}))
    assert failed_read.status == "FAILED"
    created = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="documents", action="create_text",
        parameters={"workspace": workspace, "path": "later.txt", "content": "now"}))
    assert created.status == "COMPLETED"
    retried = await service.execute(OWNER, failed_read.id)
    assert retried.status == "COMPLETED"


async def test_metrics_are_measured_and_labelled(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "file_read")
    service = engine(app_rw)
    await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="list",
        parameters={"workspace": "shared", "path": ""}))
    metrics = service.metrics()
    assert metrics["measurement"].startswith("measured")
    assert metrics["runs_total"] >= 1
    assert metrics["average_run_duration_ms"] is not None
    assert metrics["requests_by_status"]["COMPLETED"] >= 1
