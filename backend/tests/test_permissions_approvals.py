import asyncio

from fastapi.testclient import TestClient

from app.core.exceptions import ForbiddenError
from app.database.connection import Database
from app.database.repositories import PrincipalRepo, SessionRepo
from app.permissions.engine import PermissionEngine
from app.permissions.models import canonical_payload_hash
from app.core.auth import token_hash
from app.database.models import utcnow
from datetime import timedelta


def test_approval_create_and_decision(client: TestClient):
    resp = client.post("/api/v1/approvals", json={"action": "test.action", "resource": "test", "risk": "low", "reason": "test", "parameters": {"x": 1}})
    assert resp.status_code == 201
    approval_id = resp.json()["data"]["id"]
    decision = client.post(f"/api/v1/approvals/{approval_id}/decision", json={"decision": "approved", "notes": "ok"})
    assert decision.status_code == 200
    assert decision.json()["data"]["status"] == "approved"
    again = client.post(f"/api/v1/approvals/{approval_id}/decision", json={"decision": "rejected"})
    assert again.status_code == 409


def test_high_risk_self_approval_forbidden(client: TestClient):
    resp = client.post("/api/v1/approvals", json={"action": "test.high", "resource": "test", "risk": "high", "reason": "test"})
    approval_id = resp.json()["data"]["id"]
    decision = client.post(f"/api/v1/approvals/{approval_id}/decision", json={"decision": "approved"})
    assert decision.status_code == 403


def test_approval_binding():
    h1 = canonical_payload_hash("a", "r", ["p"], {"x": 1})
    h2 = canonical_payload_hash("a", "r", ["p"], {"x": 2})
    assert h1 != h2


def test_permission_denied_for_agent(client: TestClient, settings):
    async def setup_agent():
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                principal = await PrincipalRepo(session).create("agent", "test-agent")
                token = "agent-token"
                await SessionRepo(session).create(token_hash(token), principal.id, utcnow() + timedelta(minutes=5))
                await session.commit()
                engine = PermissionEngine(db)
                try:
                    await engine.check(principal.id, "tasks.submit")
                    raised = False
                except ForbiddenError:
                    raised = True
                return token, raised
        finally:
            await db.dispose()
    token, raised = asyncio.run(setup_agent())
    assert raised
    resp = client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
