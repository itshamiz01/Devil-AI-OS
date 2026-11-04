"""Tests for the owner-controlled global emergency stop.

Covers the P-01 portion of the ``SECURITY_FOUNDATION.md`` §10 / §11 gate:
persistent state, owner-only control, admission blocking, essential paths kept
available, in-flight work brought under control, and survival across restart
with no automatic clearing.
"""

import asyncio
from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.application import create_app
from app.core.auth import token_hash
from sqlalchemy import delete

from app.database.connection import Database
from app.database.models import PermissionAssignment, utcnow
from app.database.repositories import PermissionRepo, PrincipalRepo, SessionRepo, TaskRepo
from conftest import _bootstrap, wait_task


def _activate(client: TestClient, reason: str = "owner halt") -> dict:
    resp = client.post("/api/v1/system/emergency/activate", json={"reason": reason})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_emergency_blocks_nonessential_but_preserves_essential(client: TestClient):
    """The halt must stop ordinary work while keeping owner-control paths alive."""
    state = _activate(client)
    assert state["active"] is True
    assert state["activated_by"]

    # system.echo is not essential -> refused with the dedicated 503 code.
    blocked = client.post("/api/v1/tasks", json={"name": "blocked", "handler": "system.echo", "payload": {"message": "hi"}})
    assert blocked.status_code == 503, blocked.text
    assert blocked.json()["error"]["code"] == "emergency_stop_active"

    # system.noop is essential -> still admitted and still executes, because
    # SECURITY_FOUNDATION §10 requires essential paths to remain available.
    allowed = client.post("/api/v1/tasks", json={"name": "essential", "handler": "system.noop"})
    assert allowed.status_code == 201, allowed.text
    task = wait_task(client, allowed.json()["data"]["id"], {"COMPLETED"})
    assert task["status"] == "COMPLETED"


def test_emergency_requires_a_reason(client: TestClient):
    """An unexplained halt would leave no audit trail, so it is rejected."""
    empty = client.post("/api/v1/system/emergency/activate", json={"reason": ""})
    assert empty.status_code == 422
    missing = client.post("/api/v1/system/emergency/activate", json={})
    assert missing.status_code == 422
    # Nothing was activated by the rejected calls.
    status = client.get("/api/v1/system/emergency")
    assert status.json()["data"]["active"] is False


def test_emergency_reflects_in_health_without_faking_an_outage(client: TestClient):
    """Degraded, not unavailable: the process is up and still owner-controllable."""
    health_before = client.get("/api/v1/health").json()["data"]
    assert health_before["checks"]["emergency_stop_active"] is False

    _activate(client)

    health = client.get("/api/v1/health").json()["data"]
    assert health["status"] == "degraded"
    assert health["checks"]["emergency_stop_active"] is True
    assert health["emergency"]["active"] is True

    # Readiness stays true: an emergency is a deliberate owner state, not a
    # dependency failure, and reporting not-ready would hide the control path
    # an owner needs in order to clear it.
    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    assert ready.json()["data"]["ready"] is True

    status = client.get("/api/v1/system/status").json()["data"]
    assert status["lifecycle"] == "DEGRADED"


def test_emergency_clear_restores_admission(client: TestClient):
    _activate(client)
    blocked = client.post("/api/v1/tasks", json={"name": "b", "handler": "system.echo", "payload": {"message": "x"}})
    assert blocked.status_code == 503

    cleared = client.post("/api/v1/system/emergency/clear", json={"reason": "resolved"})
    assert cleared.status_code == 200
    assert cleared.json()["data"]["active"] is False
    assert cleared.json()["data"]["deactivate_reason"] == "resolved"

    now_ok = client.post("/api/v1/tasks", json={"name": "after", "handler": "system.echo", "payload": {"message": "x"}})
    assert now_ok.status_code == 201, now_ok.text
    assert client.get("/api/v1/system/status").json()["data"]["lifecycle"] == "READY"


def test_emergency_activate_is_idempotent(client: TestClient):
    first = _activate(client, "first reason")
    second = _activate(client, "second reason")
    # The original activation is preserved rather than overwritten, so the audit
    # trail keeps the reason the owner actually halted the system.
    assert second["activated_at"] == first["activated_at"]
    assert second["reason"] == "first reason"


def test_emergency_is_audited(client: TestClient):
    _activate(client, "audit check")
    client.post("/api/v1/system/emergency/clear", json={"reason": "audit clear"})
    audit = client.get("/api/v1/audit").json()["data"]
    types = {e["event_type"] for e in audit}
    assert "emergency.activated" in types
    assert "emergency.deactivated" in types


def test_emergency_denied_to_non_owner_principal(client: TestClient, settings):
    """Only the owner may halt or restart the system (Constitution §12)."""

    async def make_agent_token() -> str:
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                principal = await PrincipalRepo(session).create("agent", "emergency-agent")
                token = "agent-emergency-token"
                await SessionRepo(session).create(token_hash(token), principal.id, utcnow() + timedelta(minutes=5))
                await session.commit()
                return token
        finally:
            await db.dispose()

    token = asyncio.run(make_agent_token())
    headers = {"Authorization": f"Bearer {token}"}

    assert client.post("/api/v1/system/emergency/activate", json={"reason": "agent halt"}, headers=headers).status_code == 403
    assert client.post("/api/v1/system/emergency/clear", json={"reason": "agent clear"}, headers=headers).status_code == 403

    # The owner's own view is unaffected by the refused attempts.
    assert client.get("/api/v1/system/emergency").json()["data"]["active"] is False


def test_emergency_pauses_queued_nonessential_work(client: TestClient, settings):
    """Activation must act on work already in flight, not just new submissions."""

    async def insert_queued() -> tuple[str, str]:
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                owner = await PrincipalRepo(session).by_name("owner")
                repo = TaskRepo(session)
                ordinary = await repo.create(name="queued-ordinary", handler="system.echo", status="QUEUED", creator_id=owner.id, payload={}, essential=False)
                essential = await repo.create(name="queued-essential", handler="system.noop", status="QUEUED", creator_id=owner.id, payload={}, essential=True)
                await session.commit()
                return ordinary.id, essential.id
        finally:
            await db.dispose()

    ordinary_id, essential_id = asyncio.run(insert_queued())

    result = _activate(client)
    assert result["in_flight"]["paused"] >= 1

    ordinary = client.get(f"/api/v1/tasks/{ordinary_id}").json()["data"]
    assert ordinary["status"] == "PAUSED"
    assert ordinary["error_details"]["code"] == "EMERGENCY_STOP"

    # Essential work is deliberately left alone.
    essential = client.get(f"/api/v1/tasks/{essential_id}").json()["data"]
    assert essential["status"] == "QUEUED"


def test_emergency_survives_restart_and_never_auto_clears(settings, owner_credentials):
    """The core §10 requirement: persist across restart, clear only by owner."""
    asyncio.run(_bootstrap(settings, *owner_credentials))

    with TestClient(create_app(settings)) as first:
        login = first.post("/api/v1/auth/login", json={"username": owner_credentials[0], "password": owner_credentials[1]})
        first.headers.update({"Authorization": f"Bearer {login.json()['data']['access_token']}"})
        _activate(first, "halt before restart")
        assert first.get("/api/v1/system/emergency").json()["data"]["active"] is True

    # A brand-new application instance over the same data directory: nothing in
    # startup may clear the emergency, and the lifecycle must come up DEGRADED.
    with TestClient(create_app(settings)) as second:
        login = second.post("/api/v1/auth/login", json={"username": owner_credentials[0], "password": owner_credentials[1]})
        second.headers.update({"Authorization": f"Bearer {login.json()['data']['access_token']}"})

        state = second.get("/api/v1/system/emergency").json()["data"]
        assert state["active"] is True, "emergency state must survive restart"
        assert state["reason"] == "halt before restart"

        assert second.get("/api/v1/system/status").json()["data"]["lifecycle"] == "DEGRADED"

        still_blocked = second.post("/api/v1/tasks", json={"name": "post-restart", "handler": "system.echo", "payload": {"message": "x"}})
        assert still_blocked.status_code == 503

        # Only an explicit owner action ends it.
        cleared = second.post("/api/v1/system/emergency/clear", json={"reason": "owner cleared after restart"})
        assert cleared.json()["data"]["active"] is False
        assert second.post("/api/v1/tasks", json={"name": "resumed", "handler": "system.echo", "payload": {"message": "x"}}).status_code == 201


def _login(client: TestClient, creds) -> None:
    resp = client.post("/api/v1/auth/login", json={"username": creds[0], "password": creds[1]})
    assert resp.status_code == 200, resp.text
    client.headers.update({"Authorization": f"Bearer {resp.json()['data']['access_token']}"})


def test_owner_regains_new_permission_after_upgrade(settings, owner_credentials):
    """An owner whose database predates `system.emergency` must not be locked out.

    grant_owner_permissions only runs during bootstrap, so without startup
    reconciliation a pre-existing owner would permanently lack any permission
    added later — including the emergency stop they are supposed to control.
    """
    asyncio.run(_bootstrap(settings, *owner_credentials))

    async def revoke() -> str:
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                owner = await PrincipalRepo(session).by_name(owner_credentials[0])
                await session.execute(delete(PermissionAssignment).where(
                    PermissionAssignment.principal_id == owner.id,
                    PermissionAssignment.permission_code == "system.emergency",
                ))
                await session.commit()
                return owner.id
        finally:
            await db.dispose()

    owner_id = asyncio.run(revoke())

    with TestClient(create_app(settings)) as c:
        _login(c, owner_credentials)
        # The control is usable again purely because startup reconciled it.
        resp = c.post("/api/v1/system/emergency/activate", json={"reason": "upgrade path check"})
        assert resp.status_code == 200, resp.text

        audit = c.get("/api/v1/audit").json()["data"]
        assert any(
            e["event_type"] == "permission.owner_reconciled" and e["principal_id"] == owner_id
            for e in audit
        ), "the reconciliation must be audited"


def test_reconciliation_never_widens_a_non_owner_principal(settings, owner_credentials):
    """Reconciling the owner must not become a backdoor that elevates agents."""
    asyncio.run(_bootstrap(settings, *owner_credentials))

    async def add_agent() -> str:
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                agent = await PrincipalRepo(session).create("agent", "reconcile-agent")
                await session.commit()
                return agent.id
        finally:
            await db.dispose()

    agent_id = asyncio.run(add_agent())

    # A restart runs seed_core_data again over a database that now holds an agent.
    with TestClient(create_app(settings)) as c:
        _login(c, owner_credentials)
        assert c.get("/api/v1/system/status").status_code == 200

    async def held_permissions() -> list:
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                return [a.permission_code for a in await PermissionRepo(session).assignments(agent_id)]
        finally:
            await db.dispose()

    assert asyncio.run(held_permissions()) == []
