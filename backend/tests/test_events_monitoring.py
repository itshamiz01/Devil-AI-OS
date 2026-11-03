from fastapi.testclient import TestClient

from conftest import wait_task


def test_events_and_audit_persisted(client: TestClient):
    resp = client.post("/api/v1/tasks", json={"name": "event-test", "handler": "system.noop"})
    wait_task(client, resp.json()["data"]["id"], {"COMPLETED"})
    events = client.get("/api/v1/events")
    assert events.status_code == 200
    types = {e["event_type"] for e in events.json()["data"]}
    assert "TaskCompleted" in types
    audit = client.get("/api/v1/audit")
    assert audit.status_code == 200
    assert any(e["event_type"] == "task.created" for e in audit.json()["data"])


def test_system_status_and_resources(client: TestClient):
    status = client.get("/api/v1/system/status")
    assert status.status_code == 200
    assert status.json()["data"]["lifecycle"] in {"READY", "DEGRADED"}
    resources = client.get("/api/v1/system/resources")
    assert resources.status_code == 200
    assert "memory_percent" in resources.json()["data"]


def test_health_ready(client: TestClient):
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json()["data"]["ready"] is True
