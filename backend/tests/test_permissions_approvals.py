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


# ---------------------------------------------------------------------------
# Permission catalog integrity.
#
# A P-04 pre-implementation audit reported that ``agents.read`` was missing
# from ``PERMISSIONS`` while present in ``OWNER_PERMISSIONS``. It was not
# missing: ``PERMISSIONS`` holds ``(code, category, description)`` tuples, so
# ``"agents.read" in PERMISSIONS`` is ``False`` for a code the catalog
# contains. The false finding reached five documents before it was caught
# (L-60). These tests make the shape executable so the same mistake fails
# loudly instead of silently becoming another audit claim.
# ---------------------------------------------------------------------------

def test_the_catalog_is_a_list_of_triples_not_a_set_of_codes():
    from app.permissions.policies import PERMISSIONS

    assert isinstance(PERMISSIONS, list)
    assert all(isinstance(entry, tuple) and len(entry) == 3 for entry in PERMISSIONS)
    assert all(isinstance(part, str) and part for entry in PERMISSIONS for part in entry)
    # The trap, stated explicitly: the bare-string test is the wrong test.
    assert "agents.read" not in PERMISSIONS
    assert "agents.read" in [code for code, _, _ in PERMISSIONS]


def test_every_catalog_entry_carries_a_category_and_description():
    from app.permissions.policies import PERMISSIONS

    for code, category, description in PERMISSIONS:
        assert category, code
        assert description, code
        assert "." in code, f"{code} is not namespaced"


def test_the_catalog_has_no_duplicate_codes():
    from app.permissions.policies import PERMISSIONS

    codes = [code for code, _, _ in PERMISSIONS]
    assert len(codes) == len(set(codes))


def test_owner_permissions_are_derived_from_the_catalog():
    """An owner-only code that is absent from the catalog cannot be granted to
    anyone else, which is what the withdrawn finding claimed was happening."""
    from app.permissions.policies import OWNER_PERMISSIONS, PERMISSIONS

    assert OWNER_PERMISSIONS == [code for code, _, _ in PERMISSIONS]


def test_system_permissions_are_a_strict_subset_of_the_catalog():
    from app.permissions.policies import PERMISSIONS, SYSTEM_PERMISSIONS

    codes = {code for code, _, _ in PERMISSIONS}
    assert set(SYSTEM_PERMISSIONS) <= codes
    # The system principal must never hold an owner-grade code.
    for forbidden in ("system.emergency", "agents.manage", "agents.read",
                      "approvals.decide", "intelligence.autonomy",
                      "opportunities.sources"):
        assert forbidden not in SYSTEM_PERMISSIONS, forbidden


def test_the_agent_endpoints_are_guarded_by_a_code_that_exists():
    """The two shipped GET /agents routes require agents.read; if that code
    were absent from the catalog they would be owner-only by accident."""
    from app.permissions.policies import PERMISSIONS

    codes = {code for code, _, _ in PERMISSIONS}
    assert {"agents.read", "agents.manage"} <= codes
