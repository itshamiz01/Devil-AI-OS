"""Security tests (P-01 §16.3): auth, authorization, approval misuse,
permission bypass, secret hygiene, malformed inputs, path traversal."""
from __future__ import annotations

import logging

from app.core.auth import hash_password, verify_password
from app.permissions.models import Principal, PrincipalType
from tests.conftest import OWNER


def test_unauthenticated_requests_rejected(client):
    for path in ("/api/v1/tasks", "/api/v1/system/status", "/api/v1/approvals",
                 "/api/v1/agents", "/api/v1/events", "/api/v1/health/ready"):
        assert client.get(path).status_code == 401, path


def test_invalid_token_rejected(client):
    resp = client.get("/api/v1/tasks", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_wrong_password_rejected(client):
    resp = client.post("/api/v1/auth/login",
                       json={"username": "owner", "password": "wrong-password"})
    assert resp.status_code == 401


def test_service_principal_forbidden_from_approvals(client, auth_headers, service_headers):
    create = client.post("/api/v1/approvals", headers=auth_headers, json={
        "action": "x", "parameters": {}})
    approval_id = create.json()["data"]["id"]
    # Service token may read but must NOT decide approvals (403, not 401).
    assert client.get("/api/v1/approvals", headers=service_headers).status_code == 200
    resp = client.post(f"/api/v1/approvals/{approval_id}/decision",
                       headers=service_headers, json={"approve": True})
    assert resp.status_code == 403


def test_service_principal_cannot_cancel_tasks(client, auth_headers, service_headers):
    create = client.post("/api/v1/tasks", headers=auth_headers,
                         json={"name": "t", "handler_name": "core.noop"})
    task_id = create.json()["data"]["id"]
    # Cancellation goes through the permission engine: service lacks cancel_tasks.
    resp = client.post(f"/api/v1/tasks/{task_id}/cancel", headers=service_headers)
    assert resp.status_code == 403


def test_approval_cannot_be_decided_twice(client, auth_headers):
    create = client.post("/api/v1/approvals", headers=auth_headers, json={
        "action": "y", "parameters": {}})
    aid = create.json()["data"]["id"]
    assert client.post(f"/api/v1/approvals/{aid}/decision", headers=auth_headers,
                       json={"approve": False}).status_code == 200
    assert client.post(f"/api/v1/approvals/{aid}/decision", headers=auth_headers,
                       json={"approve": True}).status_code == 409


def test_malformed_inputs_rejected(client, auth_headers):
    assert client.post("/api/v1/tasks", headers=auth_headers,
                       json={"handler_name": "core.noop"}).status_code == 422  # missing name
    assert client.post("/api/v1/tasks", headers=auth_headers, json={
        "name": "x", "handler_name": "core.noop", "priority": 999}).status_code == 422
    assert client.post("/api/v1/auth/login", json={"username": "owner"}).status_code == 422


def test_task_cannot_smuggle_code_or_commands(client, auth_headers):
    resp = client.post("/api/v1/tasks", headers=auth_headers, json={
        "name": "evil", "handler_name": "os.system", "payload": {"command": "echo pwned"}})
    assert resp.status_code == 422  # unknown handler rejected at submission


def test_path_traversal_surface(client, auth_headers):
    # There is no file-serving endpoint in P-01; traversal attempts against
    # id parameters must simply 404, never error or leak filesystem data.
    resp = client.get("/api/v1/tasks/..%2F..%2Fetc%2Fpasswd", headers=auth_headers)
    assert resp.status_code == 404
    assert "root:" not in resp.text


def test_password_hashing_is_not_plaintext():
    stored = hash_password("correct horse battery staple")
    assert "correct horse" not in stored
    assert stored.startswith("scrypt$")
    assert verify_password("correct horse battery staple", stored)
    assert not verify_password("wrong", stored)


def test_secrets_not_written_to_log_file(client, auth_headers, settings):
    client.get("/api/v1/system/status", headers=auth_headers)
    log_text = settings.effective_log_file.read_text(errors="ignore")
    assert "test-owner-password-123" not in log_text
    assert "dev-token-for-tests" not in log_text
    assert "service-token-for-tests" not in log_text


def test_permission_bypass_via_direct_engine(application):
    agent = Principal(PrincipalType.AGENT, "agent-x")
    external = Principal(PrincipalType.EXTERNAL, "ext-x")
    for perm in ("approve_actions", "modify_system_config", "access_sensitive_data",
                 "manage_agents", "request_financial_operations"):
        assert not application.permissions.check(agent, perm).allowed, perm
        assert not application.permissions.check(external, perm).allowed, perm


def test_audit_events_record_permission_decisions(client, auth_headers):
    client.get("/api/v1/system/status", headers=auth_headers)
    from app.database.models.core import AuditEvent
    session = client.app.state.application.session_factory()
    try:
        rows = session.query(AuditEvent).filter_by(action="permission.check").all()
        assert rows, "permission checks must be audited"
        assert any(r.decision == "allow" for r in rows)
    finally:
        session.close()
