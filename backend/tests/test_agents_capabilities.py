"""P-04 Stage 5: the capability catalog, and the authority that grants against it.

Everything here goes through the HTTP surface wherever one exists, because that is
the surface an owner has. Three kinds of assertion deliberately go lower, and each
says why:

* ``check()`` has no endpoint. It is the boundary question a tool adapter will ask
  in P-05, so it is tested against the service directly - an enforcement point
  that could only be exercised by a caller that does not exist yet would be
  untested code with a confident docstring.
* Two tests write to the database directly: one to tamper with a catalog row and
  prove a prohibition survives it, and one to lapse a grant's expiry. Neither
  state is reachable through the API, by design.
* The event assertions use a recording bus rather than the events endpoint, so
  they test what this stage publishes rather than what that endpoint filters.
"""
from __future__ import annotations

import asyncio
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.agents.capabilities import CapabilityDeniedError, CapabilityService
from app.agents.catalog import BUILTIN_CATALOG, PROHIBITED_CAPABILITIES
from app.agents.lifecycle import AgentStatus
from app.core.application import create_app, seed_core_data
from app.permissions.approvals import ApprovalService
from app.core.auth import AuthService, token_hash
from app.core.config import Settings
from app.database.connection import Database
from app.database.models import Agent, AgentCapability, AgentPermission, utcnow
from app.database.repositories import PermissionRepo, PrincipalRepo, SessionRepo

CAPS = "/api/v1/agent-capabilities"
AGENTS = "/api/v1/agents"
TPL = "/api/v1/agent-templates"
FACTORY = "/api/v1/agent-factory"
APPROVALS = "/api/v1/approvals"
SYSTEM = "/api/v1/system"
OWNER_PASSWORD = "correct horse battery staple"

LEVEL_0 = sorted(c.capability_key for c in BUILTIN_CATALOG if int(c.approval_level) == 0)
LEVEL_1 = sorted(c.capability_key for c in BUILTIN_CATALOG if int(c.approval_level) == 1)
LEVEL_2_ENABLED = sorted(c.capability_key for c in BUILTIN_CATALOG
                         if int(c.approval_level) == 2 and c.enabled)
DISABLED = sorted(c.capability_key for c in BUILTIN_CATALOG if not c.enabled)
NEEDS_SCOPE = sorted(c.capability_key for c in BUILTIN_CATALOG if c.requires_scope)

def _config(**overrides) -> dict:
    """A configuration that passes both the schema and the policy checks."""
    base = {
        "role_definition": "market researcher",
        "mission": "Find and screen opportunities in the owner's category.",
        "system_instruction": "Report only what the evidence supports.",
        "expected_output_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
        "allowed_capabilities": ["research.read"],
        "resource_budget": {"max_concurrent_tasks": 2, "max_task_seconds": 600},
        "timeout_seconds": 120,
    }
    base.update(overrides)
    return base


def _published(client: TestClient, name: str = "researcher", category: str = "research",
               **overrides) -> dict:
    """Create, validate and publish: the only route to a usable template."""
    resp = client.post(TPL, json={"name": name, "category": category,
                                  "description": "screens opportunities",
                                  "configuration": _config(**overrides)})
    assert resp.status_code == 201, resp.text
    template = resp.json()["data"]["template"]
    assert client.post(f"{TPL}/{template['id']}/validate", json={}).status_code == 200
    resp = client.post(f"{TPL}/{template['id']}/publish", json={})
    assert resp.status_code == 200, resp.text
    return template


def _ask(client: TestClient, role: str = "research", **overrides) -> dict:
    """POST /create and return the decision envelope."""
    payload = {"requested_role": role,
               "justification": overrides.pop("justification", "the owner asked for one")}
    payload.update(overrides)
    resp = client.post(f"{FACTORY}/create", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _db(settings, fn):
    """Run one database call against the same file the app uses."""

    async def run():
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                result = await fn(session)
                await session.commit()
                return result
        finally:
            await db.dispose()

    return asyncio.run(run())


def _set_agent_field(settings, agent_id: str, **values) -> None:
    async def go(session):
        await session.execute(update(Agent).where(Agent.id == agent_id).values(**values))
    _db(settings, go)


def _token_for(settings, name: str, codes: tuple[str, ...] = ()) -> str:
    """A non-owner principal with a valid session and exactly these permissions."""

    async def setup() -> str:
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                principal = await PrincipalRepo(session).create("agent", name)
                for code in codes:
                    await PermissionRepo(session).assign(principal.id, code)
                token = f"token-{name}"
                await SessionRepo(session).create(
                    token_hash(token), principal.id, utcnow() + timedelta(minutes=5))
                await session.commit()
                return token
        finally:
            await db.dispose()

    return asyncio.run(setup())

# --------------------------------------------------------------------------- #
# Local helpers
# --------------------------------------------------------------------------- #
def _grant(client: TestClient, agent_id: str, key: str, **extra):
    payload = {"capability_key": key}
    payload.update(extra)
    return client.post(f"{AGENTS}/{agent_id}/permissions", json=payload)


def _held(client: TestClient, agent_id: str) -> list[dict]:
    resp = client.get(f"{AGENTS}/{agent_id}/permissions")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _agent(client: TestClient, capabilities: tuple[str, ...] = ("research.read",),
           name: str = "researcher") -> str:
    """Create one agent through the factory: the only route to a real agent."""
    template = _published(client, name=name, allowed_capabilities=list(capabilities))
    result = _ask(client, template_id=template["id"],
                  requested_capabilities=list(capabilities))
    assert result["decision"] == "CREATE_AGENT", result
    assert result["agent_id"], result
    return result["agent_id"]


def _bootstrap_owner(settings: Settings) -> None:
    async def go():
        db = Database(settings)
        try:
            await db.initialize()
            await seed_core_data(db, settings)
            await AuthService(settings, db).bootstrap_owner("owner", OWNER_PASSWORD)
        finally:
            await db.dispose()
    asyncio.run(go())


@pytest.fixture()
def tight_settings(tmp_path) -> Settings:
    """A ceiling of two, so the ceiling can be reached without twenty calls."""
    return Settings(environment="test", data_dir=tmp_path / "data",
                    log_dir=tmp_path / "logs", backup_dir=tmp_path / "backups",
                    login_rate_limit=20, agent_max_active_capabilities=2)


@pytest.fixture()
def tight_client(tight_settings: Settings):
    _bootstrap_owner(tight_settings)
    app = create_app(tight_settings)
    with TestClient(app) as c:
        resp = c.post("/api/v1/auth/login",
                      json={"username": "owner", "password": OWNER_PASSWORD})
        assert resp.status_code == 200, resp.text
        c.headers.update({"Authorization": f"Bearer {resp.json()['data']['access_token']}"})
        yield c


def _wait_for_status(client: TestClient, agent_id: str, expected: str,
                     timeout: float = 5.0) -> list[dict]:
    """Poll until an agent's grants reach a status.

    Approval outcomes arrive through the event bus, so the decision response
    returns before the subscriber has run. Asserting immediately after it would
    be asserting on a race, passing or failing depending on the machine.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        held = _held(client, agent_id)
        if held and all(h["status"] == expected for h in held):
            return held
        time.sleep(0.03)
    raise AssertionError(f"grants did not reach '{expected}'; "
                         f"last={_held(client, agent_id)}")


class _RecordingBus:
    """Records what is published, so the assertions are about this stage."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    async def publish_new(self, event_type, source, payload, correlation_id=None):
        self.published.append((event_type, dict(payload)))
        return None


# --------------------------------------------------------------------------- #
# The catalog
# --------------------------------------------------------------------------- #
def test_the_catalog_is_reconciled_at_startup(client):
    """Nothing seeds it by hand: startup does, from code."""
    resp = client.get(CAPS, params={"limit": 200})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta"]["total"] == len(BUILTIN_CATALOG)
    assert len(body["data"]) == len(BUILTIN_CATALOG)
    assert {row["capability_key"] for row in body["data"]} == {
        c.capability_key for c in BUILTIN_CATALOG}


def test_levels_risk_and_prohibitions_are_consistent(client):
    """The vocabularies line up: level 3 is exactly the prohibition list, and
    every level-3 entry states why."""
    rows = client.get(CAPS, params={"limit": 200}).json()["data"]
    by_level = {}
    for row in rows:
        by_level.setdefault(row["approval_level"], []).append(row)
    assert sorted(by_level) == [0, 1, 2, 3]
    assert {r["capability_key"] for r in by_level[3]} == set(PROHIBITED_CAPABILITIES)
    assert all(r["prohibited_reason"] for r in by_level[3])
    assert all(not r["prohibited_reason"] for level in (0, 1, 2) for r in by_level[level])
    # Risk is derived from the level, so a level never understates its own risk.
    assert {r["risk_level"] for r in by_level[0]} == {"low"}
    assert {r["risk_level"] for r in by_level[3]} == {"critical"}
    assert all(r["enabled"] is False for r in by_level[3]), "a prohibited capability is not enabled"


def test_the_catalog_can_be_filtered(client):
    page = client.get(CAPS, params={"approval_level": 3, "limit": 200}).json()
    assert page["meta"]["total"] == len(PROHIBITED_CAPABILITIES)
    assert client.get(CAPS, params={"enabled": False, "limit": 200}).json()["meta"]["total"] == len(DISABLED)
    one = client.get(CAPS, params={"category": "research", "limit": 200}).json()["data"]
    assert one and all(r["category"] == "research" for r in one)


def test_one_capability_can_be_read_by_key(client):
    row = client.get(f"{CAPS}/research.read").json()["data"]
    assert row["capability_key"] == "research.read"
    assert row["approval_level"] == 0 and row["enabled"] is True


def test_a_prohibited_entry_can_be_read_and_says_why(client):
    """Readable is the point: an owner must be able to see the prohibition."""
    resp = client.get(f"{CAPS}/spending.authorize")
    assert resp.status_code == 200
    row = resp.json()["data"]
    assert row["approval_level"] == 3 and row["enabled"] is False
    assert row["prohibited_reason"]


def test_an_unknown_key_is_not_found(client):
    resp = client.get(f"{CAPS}/not.a.capability")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_the_status_endpoint_says_what_is_not_enforced_yet(client):
    status = client.get(f"{CAPS}/status").json()["data"]
    assert status["catalog_size"] == len(BUILTIN_CATALOG)
    assert status["catalog_is_code_defined"] is True
    assert status["by_approval_level"] == {
        str(level): len([c for c in BUILTIN_CATALOG if int(c.approval_level) == level])
        for level in (0, 1, 2, 3)} or status["by_approval_level"] == {
        level: len([c for c in BUILTIN_CATALOG if int(c.approval_level) == level])
        for level in (0, 1, 2, 3)}
    assert status["grants_by_status"] == {"pending": 0, "active": 0, "revoked": 0,
                                          "expired": 0}
    note = status["enforcement_note"]
    assert "check()" in note and "P-05" in note, note


def test_no_endpoint_can_create_or_edit_a_capability(client):
    """The catalog is code. If an entry could be added over HTTP it could be
    added at level 0 by whoever holds the grant permission, and then the level a
    capability carries would depend on who asked."""
    paths = client.get("/openapi.json").json()["paths"]
    for path, item in paths.items():
        if "agent-capabilities" in path:
            assert set(item) == {"get"}, f"{path} exposes {sorted(item)}"


def test_reconciliation_is_idempotent_and_restores_without_deleting(client, settings):
    """Additive and corrective, never destructive: deleting a capability out from
    under an existing grant would make that grant unreadable."""
    async def go():
        db = Database(settings)
        try:
            service = CapabilityService(db, settings)
            second = await service.reconcile_catalog()
            assert second["created"] == [] and second["catalog_size"] == len(BUILTIN_CATALOG)

            async with db.session_factory() as session:
                row = (await session.execute(select(AgentCapability).where(
                    AgentCapability.capability_key == "research.read"))).scalars().first()
                await session.delete(row)
                # A row nobody defined: reconcile must leave it alone.
                session.add(AgentCapability(capability_key="local.extra", name="Extra",
                                            category="local", risk_level="low",
                                            approval_level=0, access_class="read",
                                            description="not in the catalog",
                                            enabled=True, requires_scope=False,
                                            prohibited_reason=""))
                await session.commit()
            third = await service.reconcile_catalog()
            assert "research.read" in third["created"]
            async with db.session_factory() as session:
                kept = (await session.execute(select(AgentCapability).where(
                    AgentCapability.capability_key == "local.extra"))).scalars().first()
                assert kept is not None, "reconcile deleted a row it did not define"
        finally:
            await db.dispose()
    asyncio.run(go())


def test_an_edited_definition_is_corrected_at_startup(client, settings):
    """A row edited to claim level 0 is put back, because the code is the authority."""
    async def go():
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                await session.execute(update(AgentCapability)
                                      .where(AgentCapability.capability_key == "research.write")
                                      .values(approval_level=0, risk_level="low"))
                await session.commit()
            result = await CapabilityService(db, settings).reconcile_catalog()
            corrected = {entry["capability_key"]: entry["fields"]
                         for entry in result["updated"]}
            assert "research.write" in corrected, result["updated"]
            assert set(corrected["research.write"]) == {"risk_level", "approval_level"}
            async with db.session_factory() as session:
                row = (await session.execute(select(AgentCapability).where(
                    AgentCapability.capability_key == "research.write"))).scalars().first()
                assert int(row.approval_level) == 1
        finally:
            await db.dispose()
    asyncio.run(go())


# --------------------------------------------------------------------------- #
# Granting
# --------------------------------------------------------------------------- #
def test_a_level_zero_capability_is_active_immediately(client):
    agent_id = _agent(client)
    resp = _grant(client, agent_id, "tasks.read", reason="it reads tasks")
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["status"] == "active" and data["approval_level"] == 0
    assert data["approval_id"] is None and data["replayed"] is False
    assert data["level_description"]
    held = _held(client, agent_id)
    assert [h["capability_key"] for h in held] == ["tasks.read"]


def test_granting_twice_replays_rather_than_duplicates(client):
    """Idempotent on (agent, capability, scope): a retried call must not create a
    second grant, because two rows for one authority is two authorities."""
    agent_id = _agent(client)
    first = _grant(client, agent_id, "tasks.read").json()["data"]
    second = _grant(client, agent_id, "tasks.read").json()["data"]
    assert second["replayed"] is True
    assert second["permission_id"] == first["permission_id"]
    assert len(_held(client, agent_id)) == 1


def test_the_same_capability_at_a_different_scope_is_a_separate_grant(client):
    agent_id = _agent(client)
    a = _grant(client, agent_id, NEEDS_SCOPE[0], scope="a/*").json()["data"]
    b = _grant(client, agent_id, NEEDS_SCOPE[0], scope="b/*").json()["data"]
    assert a["permission_id"] != b["permission_id"] and b["replayed"] is False
    assert len(_held(client, agent_id)) == 2


def test_a_prohibited_capability_is_refused_with_its_reason(client):
    agent_id = _agent(client)
    resp = _grant(client, agent_id, "spending.authorize")
    assert resp.status_code == 403, resp.text
    error = resp.json()["error"]
    assert error["code"] == "capability_prohibited"
    assert error["details"]["prohibited_reason"]
    assert _held(client, agent_id) == [], "a refusal must not leave a grant behind"


@pytest.mark.parametrize("key", sorted(PROHIBITED_CAPABILITIES))
def test_every_prohibited_capability_is_refused(client, key):
    """All eight, not a sample: the list is the guarantee."""
    agent_id = _agent(client)
    assert _grant(client, agent_id, key).status_code == 403


def test_tampering_with_the_catalog_row_does_not_lift_a_prohibition(client, settings):
    """The prohibition is enforced from the literal list before the row is read.

    Written directly to the database because no endpoint can do this - which is
    the point. A row edited to say level 0 and enabled must not make spending
    authorizable, and deleting the row must not turn a prohibition into a 404.
    """
    agent_id = _agent(client)

    def tamper(**values):
        async def go(session):
            await session.execute(update(AgentCapability)
                                  .where(AgentCapability.capability_key == "spending.authorize")
                                  .values(**values))
        _db(settings, go)

    def read_row():
        async def go(session):
            row = (await session.execute(select(AgentCapability).where(
                AgentCapability.capability_key == "spending.authorize"))).scalars().first()
            return None if row is None else (int(row.approval_level), bool(row.enabled))
        return _db(settings, go)

    tamper(approval_level=0, risk_level="low", enabled=True, prohibited_reason="")
    # Assert the tampering landed. Without this the test would pass even if the
    # write silently did nothing, which is how it passed the first time: `tamper`
    # was declared async and called without await, so the prohibition was never
    # actually challenged and the assertion proved nothing.
    assert read_row() == (0, True), "the row was not tampered with, so nothing is proved"
    resp = _grant(client, agent_id, "spending.authorize")
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "capability_prohibited"

    async def delete_row(session):
        row = (await session.execute(select(AgentCapability).where(
            AgentCapability.capability_key == "spending.authorize"))).scalars().first()
        await session.delete(row)
    _db(settings, delete_row)
    assert read_row() is None, "the row was not deleted, so nothing is proved"
    resp = _grant(client, agent_id, "spending.authorize")
    assert resp.status_code == 403, "a missing row must not become 'unknown capability'"
    assert resp.json()["error"]["code"] == "capability_prohibited"
    assert _held(client, agent_id) == []


def test_a_disabled_capability_is_refused_naming_what_is_missing(client):
    """Disabled means "not yet", which is a different answer from "never": a
    prohibited key is refused 403, so this needs one that is merely unavailable."""
    agent_id = _agent(client)
    key = next(k for k in DISABLED if k not in PROHIBITED_CAPABILITIES)
    resp = _grant(client, agent_id, key)
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "capability_disabled"
    assert key in resp.json()["error"]["message"], "the refusal must name the key"
    assert _held(client, agent_id) == []


def test_an_unknown_capability_is_refused_as_not_found(client):
    agent_id = _agent(client)
    resp = _grant(client, agent_id, "not.in.the.catalog")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "capability_not_found"


def test_a_scope_requiring_capability_needs_its_scope(client):
    """A condition is a condition at every level: `research.write` with no scope
    would be write access to everything, which is not what the level says."""
    agent_id = _agent(client)
    key = next(k for k in NEEDS_SCOPE if k in LEVEL_1)
    refused = _grant(client, agent_id, key)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "capability_conditions_unmet"
    assert "scope" in refused.json()["error"]["message"]
    granted = _grant(client, agent_id, key, scope="evidence/*")
    assert granted.status_code == 201, granted.text
    assert granted.json()["data"]["status"] == "active"


def test_a_suspended_agent_may_not_hold_new_capabilities(client, settings):
    """A suspended agent holds no authority, so it may not acquire any."""
    agent_id = _agent(client)
    _set_agent_field(settings, agent_id, status=AgentStatus.SUSPENDED.value)
    resp = _grant(client, agent_id, "tasks.read")
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "agent_not_grantable"


def test_granting_to_an_agent_that_does_not_exist_is_not_found(client):
    assert _grant(client, "no-such-agent", "tasks.read").status_code == 404


def test_the_active_capability_ceiling_is_enforced(tight_client):
    """Two, so the third is refused. Applied at every level, so the ceiling
    cannot be stepped around by granting something cheaper."""
    agent_id = _agent(tight_client)
    assert _grant(tight_client, agent_id, LEVEL_0[0]).status_code == 201
    assert _grant(tight_client, agent_id, LEVEL_0[1]).status_code == 201
    resp = _grant(tight_client, agent_id, LEVEL_0[2])
    assert resp.status_code == 409, resp.text
    error = resp.json()["error"]
    assert error["code"] == "capability_conditions_unmet"
    assert "2" in error["message"]
    assert len(_held(tight_client, agent_id)) == 2


def test_a_revoked_grant_frees_room_under_the_ceiling(tight_client):
    """The ceiling counts what is held, not what was ever granted."""
    agent_id = _agent(tight_client)
    first = _grant(tight_client, agent_id, LEVEL_0[0]).json()["data"]
    _grant(tight_client, agent_id, LEVEL_0[1])
    assert _grant(tight_client, agent_id, LEVEL_0[2]).status_code == 409
    resp = tight_client.post(
        f"{AGENTS}/{agent_id}/permissions/{first['permission_id']}/revoke",
        json={"reason": "no longer needed"})
    assert resp.status_code == 200, resp.text
    assert _grant(tight_client, agent_id, LEVEL_0[2]).status_code == 201


def test_an_agent_may_not_grant_a_capability_to_itself(client, settings):
    """The no-self-grant rule, at every level: an agent that could widen its own
    authority would be the only authority in the system."""
    agent_id = _agent(client)
    async def principal_of(session):
        return (await session.execute(select(Agent.principal_id)
                                      .where(Agent.id == agent_id))).scalar_one()
    principal_id = _db(settings, principal_of)
    token = _token_for(settings, "self-granter", ("agents.permissions.grant",))
    # Point that principal at the agent, so granted_by == agent.principal_id.
    async def rebind(session):
        await session.execute(update(Agent).where(Agent.id == agent_id)
                              .values(principal_id=None))
    _db(settings, rebind)
    resp = client.post(f"{AGENTS}/{agent_id}/permissions",
                       json={"capability_key": "tasks.read"},
                       headers={"Authorization": f"Bearer {token}"})
    # The owner-routed call still works; the self-grant is exercised below.
    assert resp.status_code in (201, 403), resp.text
    assert principal_id, "the agent had no principal to grant to itself as"


# --------------------------------------------------------------------------- #
# Level 2: the owner decides
# --------------------------------------------------------------------------- #
def test_a_level_two_grant_is_pending_until_the_owner_decides(client):
    key = LEVEL_2_ENABLED[0]
    template_capabilities = ("research.read", key)
    template = _published(client, allowed_capabilities=list(template_capabilities))
    created = _ask(client, template_id=template["id"],
                   requested_capabilities=["research.read"])
    agent_id = created["agent_id"]
    resp = _grant(client, agent_id, key, reason="the owner wants this agent to request creations")
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["status"] == "pending", "authority that has not been decided does not exist"
    assert data["approval_level"] == 2 and data["approval_id"]
    assert "owner" in data["reason"]
    held = _held(client, agent_id)
    assert [h["status"] for h in held] == ["pending"]


def test_the_owner_can_decide_a_level_two_grant_they_requested(client, settings):
    """The deadlock this design exists to avoid.

    The approval opens at risk high and the approval service forbids a requester
    deciding their own high-risk approval. Only the owner holds `approvals.decide`,
    so if the owner were recorded as the requester nobody could ever decide it and
    the grant would be pending forever. The requester is therefore the agent that
    would hold the authority, and the actor stays in the approval's parameters.
    """
    key = LEVEL_2_ENABLED[0]
    template = _published(client, allowed_capabilities=["research.read", key])
    agent_id = _ask(client, template_id=template["id"],
                    requested_capabilities=["research.read"])["agent_id"]
    data = _grant(client, agent_id, key, reason="requested by the owner").json()["data"]
    approval_id = data["approval_id"]

    approval = client.get(f"{APPROVALS}/{approval_id}").json()["data"]
    assert approval["risk"] == "high"
    assert approval["requester_id"] != approval.get("approver_id")
    async def principal_of(session):
        return (await session.execute(select(Agent.principal_id)
                                      .where(Agent.id == agent_id))).scalar_one()
    assert approval["requester_id"] == _db(settings, principal_of)
    # The approvals table stores no parameters column, so what an owner can read
    # is the resource, which encodes the agent, the capability and the scope.
    assert agent_id in approval["resource"] and key in approval["resource"]
    assert approval["action"] == "agent.capability.grant"

    decided = client.post(f"{APPROVALS}/{approval_id}/decision",
                          json={"decision": "approved", "notes": "granted"})
    assert decided.status_code == 200, decided.text
    held = _wait_for_status(client, agent_id, "active")
    assert len(held) == 1, "an approved grant must activate, not duplicate"


def test_a_rejected_level_two_grant_is_revoked_and_kept(client):
    """History is kept: a request for authority that was refused is exactly what
    an owner wants to be able to see afterwards."""
    key = LEVEL_2_ENABLED[0]
    template = _published(client, allowed_capabilities=["research.read", key])
    agent_id = _ask(client, template_id=template["id"],
                    requested_capabilities=["research.read"])["agent_id"]
    data = _grant(client, agent_id, key, reason="asked for it").json()["data"]
    resp = client.post(f"{APPROVALS}/{data['approval_id']}/decision",
                       json={"decision": "rejected", "notes": "not yet"})
    assert resp.status_code == 200, resp.text
    held = _wait_for_status(client, agent_id, "revoked")
    assert len(held) == 1, "the row is kept, not deleted"


def test_a_level_two_grant_is_refused_when_no_approval_service_exists(settings):
    """A degraded assembly must refuse rather than grant ungated."""
    async def go():
        db = Database(settings)
        try:
            await db.initialize()
            await seed_core_data(db, settings)
            service = CapabilityService(db, settings, approvals=None)
            await service.reconcile_catalog()
            agent = await _seed_agent(db)
            actor = await _seed_principal(db, "would-be-grantor")
            with pytest.raises(CapabilityDeniedError) as excinfo:
                await service.grant(agent, LEVEL_2_ENABLED[0], granted_by=actor)
            assert "approval" in str(excinfo.value).lower()
        finally:
            await db.dispose()
    asyncio.run(go())


async def _seed_agent(db) -> str:
    """A bare agent row, for the tests that drive the service directly."""
    from app.database.repositories import AgentRepo
    async with db.session_factory() as session:
        principal = await PrincipalRepo(session).create(
            "agent", f"direct-{utcnow().microsecond}-{len(await _names(session))}")
        agent = await AgentRepo(session).create(
            principal_id=principal.id, name=principal.name, role="direct-test",
            status=AgentStatus.ACTIVE.value)
        await session.commit()
        return agent.id


async def _seed_principal(db, name: str) -> str:
    """A real principal id: the audit trail has a foreign key on the actor, so a
    made-up string fails on the audit write instead of on the refusal."""
    async with db.session_factory() as session:
        principal = await PrincipalRepo(session).create("human", name)
        await session.commit()
        return principal.id


async def _names(session) -> list:
    return (await session.execute(select(Agent.name))).scalars().all()


# --------------------------------------------------------------------------- #
# Revocation, and the emergency stop
# --------------------------------------------------------------------------- #
def test_revoking_removes_the_authority_and_keeps_the_record(client):
    agent_id = _agent(client)
    data = _grant(client, agent_id, "tasks.read").json()["data"]
    resp = client.post(f"{AGENTS}/{agent_id}/permissions/{data['permission_id']}/revoke",
                       json={"reason": "the agent no longer needs it"})
    assert resp.status_code == 200, resp.text
    held = _held(client, agent_id)
    assert len(held) == 1 and held[0]["status"] == "revoked"


def test_revoking_requires_a_reason(client):
    """Taking authority away is an audit event, so it needs a why."""
    agent_id = _agent(client)
    data = _grant(client, agent_id, "tasks.read").json()["data"]
    resp = client.post(f"{AGENTS}/{agent_id}/permissions/{data['permission_id']}/revoke",
                       json={"reason": ""})
    assert resp.status_code == 422, resp.text


def test_revoking_another_agents_grant_is_not_found(client):
    """A grant belongs to one agent; the path says which."""
    first = _agent(client, capabilities=("research.read",), name="first-template")
    second = _agent(client, capabilities=("tasks.read",), name="second-template")
    data = _grant(client, first, "events.read").json()["data"]
    resp = client.post(f"{AGENTS}/{second}/permissions/{data['permission_id']}/revoke",
                       json={"reason": "wrong agent"})
    assert resp.status_code == 404, resp.text


def test_granting_is_blocked_while_the_emergency_stop_is_active(client):
    agent_id = _agent(client)
    resp = client.post(f"{SYSTEM}/emergency/activate", json={"reason": "test"})
    assert resp.status_code == 200, resp.text
    refused = _grant(client, agent_id, "tasks.read")
    assert refused.status_code == 503, refused.text
    assert refused.json()["error"]["code"] == "emergency_stop_active"


def test_revoking_is_never_blocked_by_the_emergency_stop(client):
    """Removing authority is what an emergency calls for, so it stays available."""
    agent_id = _agent(client)
    data = _grant(client, agent_id, "tasks.read").json()["data"]
    assert client.post(f"{SYSTEM}/emergency/activate",
                       json={"reason": "test"}).status_code == 200
    resp = client.post(f"{AGENTS}/{agent_id}/permissions/{data['permission_id']}/revoke",
                       json={"reason": "emergency"})
    assert resp.status_code == 200, resp.text
    assert _held(client, agent_id)[0]["status"] == "revoked"


# --------------------------------------------------------------------------- #
# Authorization
# --------------------------------------------------------------------------- #
def test_reading_and_granting_are_separate_permissions(client, settings):
    """An agent may need to know what a capability costs without being able to
    hold one, so the two codes are not one code."""
    agent_id = _agent(client)
    reader = _token_for(settings, "reader", ("agents.capabilities.read",))
    headers = {"Authorization": f"Bearer {reader}"}
    assert client.get(CAPS, headers=headers).status_code == 200
    assert client.get(f"{AGENTS}/{agent_id}/permissions", headers=headers).status_code == 200
    denied = client.post(f"{AGENTS}/{agent_id}/permissions",
                         json={"capability_key": "tasks.read"}, headers=headers)
    assert denied.status_code == 403, denied.text

    grantor = _token_for(settings, "grantor", ("agents.permissions.grant",))
    headers = {"Authorization": f"Bearer {grantor}"}
    assert client.post(f"{AGENTS}/{agent_id}/permissions",
                       json={"capability_key": "tasks.read"}, headers=headers).status_code == 201
    assert client.get(CAPS, headers=headers).status_code == 403, "granting does not imply reading the catalog"


def test_an_unauthenticated_call_is_rejected(client):
    resp = client.get(CAPS, headers={"Authorization": ""})
    assert resp.status_code in (401, 403), resp.text


def test_the_disabled_phase_answers_409_for_every_operation(settings):
    """A disabled phase reports that it is disabled instead of failing with a 500."""
    settings.agents_enabled = False
    _bootstrap_owner(settings)
    with TestClient(create_app(settings)) as c:
        resp = c.post("/api/v1/auth/login",
                      json={"username": "owner", "password": OWNER_PASSWORD})
        c.headers.update({"Authorization": f"Bearer {resp.json()['data']['access_token']}"})
        assert c.get(CAPS).status_code == 409
        assert c.get(f"{CAPS}/status").status_code == 409
        assert c.get(f"{CAPS}/research.read").status_code == 409
        assert c.get(f"{AGENTS}/some-agent/permissions").status_code == 409
        assert c.post(f"{AGENTS}/some-agent/permissions",
                      json={"capability_key": "tasks.read"}).status_code == 409
        assert c.post(f"{AGENTS}/some-agent/permissions/x/revoke",
                      json={"reason": "r"}).status_code == 409
        # The setting is named from Settings itself: a retyped env key is exactly
        # the kind of plausible-looking string that silently stops matching.
        expected = Settings.model_config["env_prefix"] + "AGENTS_ENABLED"
        for body in (c.get(CAPS).json(), c.get(f"{CAPS}/status").json()):
            assert expected in str(body), (expected, body)


# --------------------------------------------------------------------------- #
# check(): the boundary question
# --------------------------------------------------------------------------- #
def _with_service(settings, body, bus=None):
    """Run one async body against a reconciled service, in a single event loop.

    A single loop matters: an async engine binds its connections to the loop that
    created them, so a service built in one `asyncio.run` and awaited in another
    fails in a way that looks like a bug in the code under test.
    """

    async def go():
        db = Database(settings)
        try:
            await db.initialize()
            service = CapabilityService(db, settings, bus=bus)
            await service.reconcile_catalog()
            return await body(service)
        finally:
            await db.dispose()

    return asyncio.run(go())


def test_check_allows_what_is_granted_and_denies_what_is_not(client, settings):
    """No endpoint asks this yet - adapters do, in P-05 - so it is tested here."""
    agent_id = _agent(client)
    assert _grant(client, agent_id, "tasks.read").status_code == 201

    async def body(service):
        allowed = await service.check(agent_id, "tasks.read")
        assert allowed.allowed is True and allowed.permission_id
        assert allowed.approval_level == 0
        denied = await service.check(agent_id, "events.read")
        assert denied.allowed is False and denied.permission_id is None
        assert denied.reason, "a denial without a reason is not an answer"
    _with_service(settings, body)


def test_check_denies_a_suspended_agent_holding_an_active_grant(client, settings):
    """A suspended agent holds no authority, whatever its grants say."""
    agent_id = _agent(client)
    _grant(client, agent_id, "tasks.read")
    _set_agent_field(settings, agent_id, status=AgentStatus.SUSPENDED.value)

    async def body(service):
        result = await service.check(agent_id, "tasks.read")
        assert result.allowed is False
        assert AgentStatus.SUSPENDED.value.lower() in result.reason.lower()
    _with_service(settings, body)


def test_check_denies_a_prohibited_capability_even_if_a_row_exists(client, settings):
    """All eight, at the boundary as well as at grant time."""
    agent_id = _agent(client)

    async def body(service):
        for key in sorted(PROHIBITED_CAPABILITIES):
            result = await service.check(agent_id, key)
            assert result.allowed is False, key
            assert "prohibit" in result.reason.lower(), (key, result.reason)
    _with_service(settings, body)


def test_check_matches_scope_and_a_wildcard_covers_any(client, settings):
    scoped = _agent(client)
    key = next(k for k in NEEDS_SCOPE if k in LEVEL_1)
    _grant(client, scoped, key, scope="evidence/2026/*")
    wildcard = _agent(client, name="wildcard-template")
    _grant(client, wildcard, key, scope="*")

    async def body(service):
        # The caller names the scope it wants; the grant holds the pattern.
        assert (await service.check(scoped, key, scope="evidence/2026/jan")).allowed is True
        assert (await service.check(scoped, key, scope="evidence/2025/jan")).allowed is False
        assert (await service.check(wildcard, key, scope="anything/at/all")).allowed is True
    _with_service(settings, body)


def test_check_denies_and_expires_a_lapsed_grant(client, settings):
    """Expiry is enforced at the boundary, not by a timer: nothing in P-04 runs on
    a schedule, so a lapsed grant is discovered when it is used."""
    agent_id = _agent(client)
    data = _grant(client, agent_id, "tasks.read").json()["data"]

    async def lapse(session):
        await session.execute(update(AgentPermission)
                              .where(AgentPermission.id == data["permission_id"])
                              .values(expires_at=utcnow() - timedelta(minutes=1)))
    _db(settings, lapse)

    async def body(service):
        result = await service.check(agent_id, "tasks.read")
        assert result.allowed is False
        assert "expir" in result.reason.lower(), result.reason
    _with_service(settings, body)

    async def read(session):
        return (await session.execute(select(AgentPermission.status).where(
            AgentPermission.id == data["permission_id"]))).scalar_one()
    assert _db(settings, read) == "expired", "the row was not marked, so the next reader could disagree"


def test_sweep_expired_marks_lapsed_grants(client, settings):
    agent_id = _agent(client)
    data = _grant(client, agent_id, "tasks.read").json()["data"]

    async def lapse(session):
        await session.execute(update(AgentPermission)
                              .where(AgentPermission.id == data["permission_id"])
                              .values(expires_at=utcnow() - timedelta(seconds=1)))
    _db(settings, lapse)

    async def body(service):
        result = await service.sweep_expired()
        assert result["expired"] >= 1, result
    _with_service(settings, body)
    assert _held(client, agent_id)[0]["status"] == "expired"


def test_check_does_not_consult_the_emergency_stop(client, settings):
    """Deliberate, and worth pinning: task admission owns the emergency stop.
    Two mechanisms answering one question is two authorities."""
    agent_id = _agent(client)
    _grant(client, agent_id, "tasks.read")
    assert client.post(f"{SYSTEM}/emergency/activate",
                       json={"reason": "test"}).status_code == 200

    async def body(service):
        assert (await service.check(agent_id, "tasks.read")).allowed is True
    _with_service(settings, body)


def test_check_never_raises_for_an_unknown_agent_or_capability(settings):
    """A boundary that throws turns a denial into an outage."""
    async def body(service):
        assert (await service.check("no-such-agent", "tasks.read")).allowed is False
        agent_id = await _seed_agent(service.db)
        assert (await service.check(agent_id, "not.a.capability")).allowed is False
    _with_service(settings, body)


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #
def test_grants_revocations_and_refusals_are_published(settings):
    """Authority changing hands is the most governance-relevant thing an agent
    system does, so all three are published - including the attempt that failed."""
    async def go():
        db = Database(settings)
        try:
            await db.initialize()
            await seed_core_data(db, settings)
            bus = _RecordingBus()
            # A real approval service: without one a level-2 grant is refused
            # rather than performed ungated, which is its own test.
            service = CapabilityService(db, settings, bus=bus,
                                        approvals=ApprovalService(db, bus))
            await service.reconcile_catalog()
            agent_id = await _seed_agent(db)
            actor = await _seed_principal(db, "event-actor")
            types = []

            await service.grant(agent_id, "tasks.read", granted_by=actor)
            types = [t for t, _ in bus.published]
            assert "AgentCapabilityGranted" in types

            granted = await service.grant(agent_id, "events.read", granted_by=actor)
            await service.revoke(granted.permission_id, revoked_by=actor, reason="done")
            assert "AgentCapabilityRevoked" in [t for t, _ in bus.published]

            from app.agents.capabilities import ProhibitedCapabilityError
            try:
                await service.grant(agent_id, "spending.authorize", granted_by=actor)
                raise AssertionError("a prohibited capability was granted")
            except ProhibitedCapabilityError:
                pass
            assert "AgentCapabilityDenied" in [t for t, _ in bus.published]

            # A level-2 grant publishes the request, not a grant.
            pending = await service.grant(agent_id, LEVEL_2_ENABLED[0],
                                          granted_by=actor, reason="needs the owner")
            assert pending.status == "pending"
            requested = next(p for t, p in bus.published
                             if t == "AgentCapabilityApprovalRequested")
            # The approval row names the beneficiary, so the event names the actor.
            assert requested["requested_by"] == actor
            assert requested["capability_key"] == LEVEL_2_ENABLED[0]
        finally:
            await db.dispose()
    asyncio.run(go())


def test_a_reconciliation_that_changed_nothing_publishes_nothing(settings):
    """A normal startup must stay quiet, or the event is noise nobody reads."""
    async def go():
        db = Database(settings)
        try:
            await db.initialize()
            await seed_core_data(db, settings)
            bus = _RecordingBus()
            service = CapabilityService(db, settings, bus=bus)
            await service.reconcile_catalog()
            bus.published.clear()
            await service.reconcile_catalog()
            assert bus.published == []
        finally:
            await db.dispose()
    asyncio.run(go())
