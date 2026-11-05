"""P-05 Stage 2: the execution API over HTTP.

Proves the route-layer contract the service tests cannot: authentication is
required, permissions are enforced per operation (read is not submit is not
admin), a policy refusal is a 409 carrying the evaluation rather than a 200
with a sad field, and the subsystem reports itself disabled honestly when
AUTONOMUS_EXECUTION_ENABLED=false.

The agent principal is a real one - a principal row with a session token and
exactly the permission codes each test grants - because the identity rule
(submit as the principal you authenticated as) is only meaningful when the
request actually arrives over HTTP with a token.
"""
import asyncio
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.auth import token_hash
from app.database.connection import Database
from app.database.models import Agent, Principal, Task, utcnow
from app.database.repositories import PermissionRepo, PrincipalRepo, SessionRepo

EXECUTION = "/api/v1/execution"


def _db(settings, fn):
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


def _agent_client(settings, client, codes=("execution.submit",)):
    """An authenticated client for one agent principal holding `codes`."""
    suffix = uuid.uuid4().hex[:8]

    async def setup(session):
        principal = await PrincipalRepo(session).create("agent", f"agent-{suffix}")
        for code in codes:
            await PermissionRepo(session).assign(principal.id, code)
        token = f"token-{suffix}"
        await SessionRepo(session).create(
            token_hash(token), principal.id, utcnow() + timedelta(minutes=30))
        agent = Agent(principal_id=principal.id, name=f"worker-{suffix}",
                      role="research", status="ACTIVE")
        session.add(agent)
        await session.flush()
        owner = (await session.execute(
            select(Principal).where(Principal.kind == "owner"))).scalars().first()
        task = Task(name="job", handler="test.handler", status="QUEUED",
                    creator_id=owner.id, assigned_agent_id=agent.id)
        session.add(task)
        await session.flush()
        return token, agent.id, task.id

    token, agent_id, task_id = _db(settings, setup)
    agent_client = client.__class__(client.app)
    agent_client.headers.update({"Authorization": f"Bearer {token}"})
    return agent_client, agent_id, task_id


def _available_tool(client, **over):
    definition = {"name": f"fs-{uuid.uuid4().hex[:6]}", "adapter_type": "filesystem",
                  "supported_actions": ["read"], "risk_level": 0}
    definition.update(over)
    resp = client.post(f"{EXECUTION}/tools/register", json=definition)
    assert resp.status_code == 201, resp.text
    tool = resp.json()["data"]
    resp = client.post(f"{EXECUTION}/tools/{tool['id']}/validate")
    assert resp.status_code == 200 and resp.json()["data"]["available"], resp.text
    return tool


def test_tools_lifecycle_over_http(client):
    tool = _available_tool(client)
    assert tool["status"] == "REGISTERED"  # registration declares; validation admits

    resp = client.get(f"{EXECUTION}/tools")
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["data"]}
    assert {"browser.session", "desktop.window"} <= names

    resp = client.get(f"{EXECUTION}/tools/{tool['id']}")
    assert resp.json()["data"]["status"] == "AVAILABLE"
    assert "configuration_reference" not in resp.json()["data"]  # §7 discovery

    resp = client.post(f"{EXECUTION}/tools/{tool['id']}/disable",
                       json={"reason": " under review "})
    assert resp.json()["data"]["status"] == "DISABLED"

    resp = client.get(f"{EXECUTION}/tools/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "execution_tool_not_found"


def test_submit_queue_cancel_over_http(client, settings):
    tool = _available_tool(client)
    agent_client, agent_id, task_id = _agent_client(settings, client)
    payload = {"task_id": task_id, "tool_id": tool["id"], "action_name": "read",
               "requested_scope": "workspace:reports"}

    resp = agent_client.post(f"{EXECUTION}/requests", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["status"] == "QUEUED" and body["agent_id"] == agent_id
    assert all(c["passed"] for c in body["evaluation"]["checks"])

    request_id = body["id"]
    resp = client.get(f"{EXECUTION}/requests/{request_id}")
    assert resp.status_code == 200
    resp = client.get(f"{EXECUTION}/requests", params={"status": "QUEUED"})
    assert request_id in {r["id"] for r in resp.json()["data"]}

    resp = agent_client.post(f"{EXECUTION}/requests/{request_id}/cancel", json={})
    assert resp.json()["data"]["status"] == "CANCELLED"
    # A finished request is a record, not a draft.
    resp = agent_client.post(f"{EXECUTION}/requests/{request_id}/cancel", json={})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "execution_transition_invalid"


def test_a_policy_refusal_is_a_409_carrying_the_evaluation(client, settings):
    tool = _available_tool(client, supported_actions=["audit.delete"])
    agent_client, agent_id, task_id = _agent_client(settings, client)
    resp = agent_client.post(f"{EXECUTION}/requests", json={
        "task_id": task_id, "tool_id": tool["id"], "action_name": "audit.delete",
        "requested_scope": "workspace:reports"})
    assert resp.status_code == 409, resp.text
    error = resp.json()["error"]
    assert error["code"] == "execution_refused"
    assert error["details"]["status"] == "REJECTED"
    failed = [c["name"] for c in error["details"]["evaluation"]["checks"]
              if not c["passed"]]
    assert failed == ["risk_category"]
    # ...and the rejected row remains, readable by the owner.
    resp = client.get(f"{EXECUTION}/requests/{error['details']['request_id']}")
    assert resp.json()["data"]["status"] == "REJECTED"
    assert resp.json()["data"]["risk_level"] == 3


def test_permissions_are_enforced_per_operation(client, settings):
    # A principal with only execution.read can look, but not submit or admin.
    reader, agent_id, task_id = _agent_client(settings, client,
                                              codes=("execution.read",))
    resp = reader.post(f"{EXECUTION}/requests", json={
        "task_id": task_id, "tool_id": "x", "action_name": "read"})
    assert resp.status_code == 403
    resp = reader.post(f"{EXECUTION}/tools/register", json={
        "name": "x", "adapter_type": "filesystem"})
    assert resp.status_code == 403
    resp = reader.get(f"{EXECUTION}/tools")
    assert resp.status_code == 200

    # No token at all is a 401, not a 403: unauthenticated is not unauthorized.
    anon = client.__class__(client.app)
    resp = anon.get(f"{EXECUTION}/tools")
    assert resp.status_code == 401


def test_the_owner_cannot_submit_as_an_agent(client):
    """The owner holds every permission code, including execution.submit -
    and still cannot submit, because no agent is bound to the owner
    principal. Authority to permit is not identity to act."""
    tool = _available_tool(client)
    resp = client.post(f"{EXECUTION}/requests", json={
        "task_id": "anything", "tool_id": tool["id"], "action_name": "read"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "execution_identity_required"


def test_status_reports_the_stage_and_its_gaps(client):
    resp = client.get(f"{EXECUTION}/status")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["policy"] is True and body["tool_registry"] is True
    assert body["adapters"]["filesystem"] is False  # Stage 3, not yet
    assert body["adapters"]["browser"].startswith("disabled")
    assert body["requests"]["execution_draining"] is False
    assert body["registry"]["unsupported_adapters"]


def test_execution_disabled_answers_409_naming_the_setting(settings, client):
    from app.core.application import create_app
    from fastapi.testclient import TestClient
    from tests.conftest import _bootstrap
    import asyncio as _asyncio

    disabled = settings.__class__(**{**settings.model_dump(),
                                     "execution_enabled": False})
    _asyncio.run(_bootstrap(disabled))
    app = create_app(disabled)
    with TestClient(app) as c:
        login = c.post("/api/v1/auth/login",
                       json={"username": "owner",
                             "password": "correct horse battery staple"})
        token = login.json()["data"]["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        resp = c.get(f"{EXECUTION}/tools")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "execution_disabled"
        assert "AUTONOMUS_EXECUTION_ENABLED" in str(resp.json()["error"]["details"])
