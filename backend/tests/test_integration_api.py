"""Integration tests over HTTP: health, auth, tasks, approvals, agents, events."""
from __future__ import annotations

import time


def _wait_task(client, headers, task_id, statuses, timeout=5.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/tasks/{task_id}", headers=headers)
        assert resp.status_code == 200
        last = resp.json()["data"]
        if last["status"] in statuses:
            return last
        time.sleep(0.05)
    raise AssertionError(f"task {task_id} stuck at {last and last['status']}")


def test_health_live_is_public(client):
    resp = client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "alive"
    assert resp.headers.get("x-correlation-id")


def test_health_ready_requires_auth_and_distinguishes(client, auth_headers):
    assert client.get("/api/v1/health/ready").status_code == 401
    resp = client.get("/api/v1/health/ready", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] in ("ready", "degraded")
    assert resp.json()["data"]["database_healthy"] is True


def test_system_status_and_resources(client, auth_headers):
    resp = client.get("/api/v1/system/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["database_healthy"] is True and data["queue"] is not None
    resp = client.get("/api/v1/system/resources", headers=auth_headers)
    assert resp.status_code == 200
    assert "cpu_percent" in resp.json()["data"]["resources"]


def test_task_submit_execute_complete_over_api(client, auth_headers):
    resp = client.post("/api/v1/tasks", headers=auth_headers, json={
        "name": "echo via api", "handler_name": "core.echo_check",
        "payload": {"message": "api-hello"}})
    assert resp.status_code == 201, resp.text
    task = resp.json()["data"]
    done = _wait_task(client, auth_headers, task["id"], {"completed"})
    assert done["result"]["echo"]["message"] == "api-hello"
    assert len(done["executions"]) == 1 and done["executions"][0]["status"] == "completed"


def test_task_cancel_over_api(client, auth_headers):
    resp = client.post("/api/v1/tasks", headers=auth_headers, json={
        "name": "queued victim", "handler_name": "core.wait",
        "payload": {"milliseconds": 50}})
    task_id = resp.json()["data"]["id"]
    cancel = client.post(f"/api/v1/tasks/{task_id}/cancel", headers=auth_headers)
    assert cancel.status_code == 200
    final = _wait_task(client, auth_headers, task_id, {"cancelled", "completed"})
    assert final["status"] in ("cancelled", "completed")  # race-tolerant: must be terminal


def test_task_retry_over_api(client, auth_headers):
    resp = client.post("/api/v1/tasks", headers=auth_headers, json={
        "name": "will time out", "handler_name": "core.wait",
        "payload": {"milliseconds": 1500}, "timeout_seconds": 0.1, "max_retries": 0})
    task_id = resp.json()["data"]["id"]
    _wait_task(client, auth_headers, task_id, {"failed"})
    retry = client.post(f"/api/v1/tasks/{task_id}/retry", headers=auth_headers)
    assert retry.status_code == 200
    assert retry.json()["data"]["status"] == "queued"
    _wait_task(client, auth_headers, task_id, {"failed"})  # times out again, honestly


def test_approval_workflow_over_api(client, auth_headers):
    create = client.post("/api/v1/approvals", headers=auth_headers, json={
        "action": "config.change", "resource": "system:settings",
        "risk_classification": "high", "reason": "integration test",
        "requested_permissions": ["modify_system_config"], "parameters": {"k": "v"}})
    assert create.status_code == 201, create.text
    approval = create.json()["data"]
    assert approval["status"] == "pending"
    decision = client.post(f"/api/v1/approvals/{approval['id']}/decision",
                           headers=auth_headers, json={"approve": True, "notes": "ok"})
    assert decision.status_code == 200
    assert decision.json()["data"]["status"] == "approved"
    again = client.post(f"/api/v1/approvals/{approval['id']}/decision",
                        headers=auth_headers, json={"approve": True})
    assert again.status_code == 409  # cannot decide twice


def test_gated_task_released_by_approval(client, auth_headers):
    resp = client.post("/api/v1/tasks", headers=auth_headers, json={
        "name": "gated task", "handler_name": "core.noop", "requires_approval": True})
    assert resp.status_code == 201
    task = resp.json()["data"]
    assert task["status"] == "waiting_for_approval" and task["approval_id"]
    decision = client.post(f"/api/v1/approvals/{task['approval_id']}/decision",
                           headers=auth_headers, json={"approve": True})
    assert decision.status_code == 200, decision.text
    _wait_task(client, auth_headers, task["id"], {"completed"})


def test_agents_endpoints_are_read_only(client, auth_headers):
    # P-01 property: the registry API was read-only (POST -> 404/405).
    # P-04 §19 supersedes that phase boundary: POST /agents now exists as
    # the GOVERNED creation pipeline. The protective intent of the P-01
    # assertion is preserved and strengthened — an empty body is rejected
    # by schema validation (422) and no ungoverned registration path
    # exists; full creation behaviour is covered by the P-04 suites.
    resp = client.get("/api/v1/agents", headers=auth_headers)
    assert resp.status_code == 200 and resp.json()["data"] == []
    assert client.post("/api/v1/agents", headers=auth_headers, json={}).status_code == 422
    assert client.post("/api/v1/agents", json={"role": "research_agent"}).status_code == 401
    assert client.get("/api/v1/agents/does-not-exist", headers=auth_headers).status_code == 404


def test_events_endpoint_lists_persisted_critical_events(client, auth_headers):
    client.post("/api/v1/approvals", headers=auth_headers, json={
        "action": "event.test", "parameters": {}})
    resp = client.get("/api/v1/events", headers=auth_headers)
    assert resp.status_code == 200
    types = [e["event_type"] for e in resp.json()["data"]]
    assert "ApplicationStarted" in types


def test_pagination_meta(client, auth_headers):
    for i in range(3):
        client.post("/api/v1/tasks", headers=auth_headers,
                    json={"name": f"t{i}", "handler_name": "core.noop"})
    resp = client.get("/api/v1/tasks?limit=2&offset=0", headers=auth_headers)
    body = resp.json()
    assert body["meta"]["limit"] == 2 and body["meta"]["total"] >= 3
    assert len(body["data"]) == 2
