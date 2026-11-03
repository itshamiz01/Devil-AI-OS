import time

from fastapi.testclient import TestClient

from conftest import wait_task


def submit(client, **kwargs):
    body = {"name": "test", "handler": "system.noop", "payload": {}}
    body.update(kwargs)
    return client.post("/api/v1/tasks", json=body)


def test_submit_and_complete(client: TestClient):
    resp = submit(client)
    assert resp.status_code == 201, resp.text
    task_id = resp.json()["data"]["id"]
    task = wait_task(client, task_id, {"COMPLETED"})
    assert task["result"]["ok"] is True
    history = client.get(f"/api/v1/tasks/{task_id}/history")
    assert history.status_code == 200
    assert len(history.json()["data"]) >= 1


def test_echo(client: TestClient):
    resp = submit(client, handler="system.echo", payload={"message": "hello"})
    task = wait_task(client, resp.json()["data"]["id"], {"COMPLETED"})
    assert task["result"]["message"] == "hello"


def test_invalid_payload_rejected(client: TestClient):
    resp = submit(client, handler="system.echo", payload={})
    assert resp.status_code == 400


def test_unknown_handler_rejected(client: TestClient):
    resp = client.post("/api/v1/tasks", json={"name": "x", "handler": "shell.exec", "payload": {}})
    assert resp.status_code == 422


def test_idempotency(client: TestClient):
    a = submit(client, idempotency_key="key-1", handler="system.echo", payload={"message": "a"})
    b = submit(client, idempotency_key="key-1", handler="system.echo", payload={"message": "a"})
    assert a.json()["data"]["id"] == b.json()["data"]["id"]
    c = submit(client, idempotency_key="key-1", handler="system.echo", payload={"message": "b"})
    assert c.status_code == 409


def test_cancel_running(client: TestClient):
    resp = submit(client, handler="system.wait", payload={"duration_ms": 5000})
    task_id = resp.json()["data"]["id"]
    time.sleep(0.1)
    cancel = client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert cancel.status_code == 200
    wait_task(client, task_id, {"CANCELLED"})


def test_timeout_retry_then_fail(client: TestClient):
    resp = submit(client, handler="system.wait", payload={"duration_ms": 200}, timeout_seconds=0.01, max_retries=1)
    task = wait_task(client, resp.json()["data"]["id"], {"FAILED"}, timeout=5)
    assert task["retry_count"] == 1
    assert task["error_details"]["code"] == "TIMEOUT"


def test_queue_capacity(client: TestClient):
    ids = []
    for i in range(6):
        resp = submit(client, handler="system.wait", payload={"duration_ms": 5000}, name=f"wait-{i}")
        ids.append(resp)
    assert any(r.status_code == 429 for r in ids)
    for r in ids:
        if r.status_code == 201:
            client.post(f"/api/v1/tasks/{r.json()['data']['id']}/cancel")


def test_pause_resume_queued(client: TestClient):
    blocker = submit(client, handler="system.wait", payload={"duration_ms": 1000})
    queued = submit(client, handler="system.noop")
    task_id = queued.json()["data"]["id"]
    pause = client.post(f"/api/v1/tasks/{task_id}/pause")
    assert pause.status_code == 200
    assert pause.json()["data"]["status"] == "PAUSED"
    resume = client.post(f"/api/v1/tasks/{task_id}/resume")
    assert resume.status_code == 200
    wait_task(client, task_id, {"COMPLETED"})
    client.post(f"/api/v1/tasks/{blocker.json()['data']['id']}/cancel")


def test_resource_protection(client: TestClient, monkeypatch):
    services = client.app.state.services
    monkeypatch.setattr(services.monitor, "resource_pressure", lambda: ["memory"])
    resp = submit(client, handler="system.echo", payload={"message": "x"})
    assert resp.status_code == 503
    essential = submit(client, handler="system.noop")
    assert essential.status_code == 201
