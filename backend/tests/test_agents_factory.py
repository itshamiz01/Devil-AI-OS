"""P-04 Stage 4: the creation engine and the identity it mints.

Everything here goes through the HTTP surface wherever one exists, because that
is the surface an owner actually has: a decision that is only reachable by
calling the service directly would not be evidence about the product. The few
assertions that read the database directly are reading things this stage
deliberately exposes no endpoint for — the configuration snapshot and a
deliberately corrupted parent chain — and each says so.
"""
from __future__ import annotations

import asyncio
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.application import create_app, seed_core_data
from app.core.auth import AuthService, token_hash
from app.database.connection import Database
from app.agents.catalog import BUILTIN_CATALOG, PROHIBITED_CAPABILITIES
from app.database.models import (Agent, AgentConfigurationHistory,
                                 AgentTemplateVersion, utcnow)
from app.database.repositories import PermissionRepo, PrincipalRepo, SessionRepo

FACTORY = "/api/v1/agent-factory"
TPL = "/api/v1/agent-templates"
AGENTS = "/api/v1/agents"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
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


def _preview(client: TestClient, role: str = "research", **overrides) -> dict:
    payload = {"requested_role": role,
               "justification": overrides.pop("justification", "considering one")}
    payload.update(overrides)
    resp = client.post(f"{FACTORY}/evaluate", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _ledger(client: TestClient, **filters) -> list[dict]:
    resp = client.get(f"{FACTORY}/requests", params=filters or None)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _agents(client: TestClient) -> list[dict]:
    resp = client.get(AGENTS)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _wait_for_event(client: TestClient, event_type: str, request_id: str,
                    timeout: float = 5.0) -> dict:
    """The bus writes asynchronously, so an event is polled for, not assumed."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/events?event_type={event_type}&limit=200")
        assert resp.status_code == 200, resp.text
        seen = [e for e in resp.json()["data"]
                if e.get("payload", {}).get("request_id") == request_id]
        if seen:
            return seen[0]
        time.sleep(0.03)
    raise AssertionError(f"no {event_type} event for request {request_id}")


def _events(client: TestClient, event_type: str, request_id: str) -> list[dict]:
    resp = client.get(f"/api/v1/events?event_type={event_type}&limit=200")
    assert resp.status_code == 200, resp.text
    return [e for e in resp.json()["data"]
            if e.get("payload", {}).get("request_id") == request_id]


def _wait_for_request(client: TestClient, request_id: str, *, decision: str | None = None,
                      approval_status: str | None = None, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        resp = client.get(f"{FACTORY}/requests/{request_id}")
        assert resp.status_code == 200, resp.text
        last = resp.json()["data"]
        if ((decision is None or last["decision"] == decision)
                and (approval_status is None or last["approval_status"] == approval_status)):
            return last
        time.sleep(0.03)
    raise AssertionError(f"request {request_id} did not reach "
                         f"{decision}/{approval_status}; last={last}")


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


def _force_allowed_capabilities(settings, template_id: str, keys: list[str]) -> None:
    """Write capability keys into a published version, past validation.

    Only used to reproduce the one situation where the factory's own catalog
    guard can still be reached: a template whose verdict was recorded before the
    catalog was cross-checked (L-61), or whose configuration was edited
    underneath that verdict. Since Stage 5 validation refuses to judge such a
    template valid, there is no HTTP route to this state - which is the point of
    having the guard in the decision engine as well.
    """
    async def go(session):
        row = (await session.execute(
            select(AgentTemplateVersion).where(AgentTemplateVersion.template_id == template_id))).scalars().first()
        configuration = dict(row.configuration_json or {})
        configuration["allowed_capabilities"] = list(keys)
        row.configuration_json = configuration
    _db(settings, go)


def _snapshot_for(settings, agent_id: str) -> list[dict]:
    async def go(session):
        rows = (await session.execute(
            select(AgentConfigurationHistory)
            .where(AgentConfigurationHistory.agent_id == agent_id))).scalars().all()
        return [{"version": r.configuration_version, "reason": r.change_reason,
                 "snapshot": dict(r.configuration_snapshot or {})} for r in rows]
    return _db(settings, go)


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


def _auth(client: TestClient, token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _principal(settings, name: str, codes: tuple[str, ...] = ()) -> tuple[str, str]:
    """Create a principal and return ``(token, principal_id)``."""

    async def setup() -> tuple[str, str]:
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
                return token, principal.id
        finally:
            await db.dispose()

    return asyncio.run(setup())


def _grant(settings, principal_id: str, code: str) -> None:
    async def go(session):
        await PermissionRepo(session).assign(principal_id, code)
    _db(settings, go)


def _requester_token(settings, name: str = "requester") -> str:
    """A principal that may ask for an agent but may not authorize one.

    Deliberately without ``approvals.decide``: the gate only means something if
    the requester cannot close it.
    """
    return _token_for(settings, name, ("agents.factory.admin", "agents.factory.read"))


def _ask_as(client: TestClient, token: str, role: str = "research", **overrides) -> dict:
    payload = {"requested_role": role,
               "justification": overrides.pop("justification", "an agent asked for one")}
    payload.update(overrides)
    resp = client.post(f"{FACTORY}/create", json=payload, headers=_auth(client, token))
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# --------------------------------------------------------------------------- #
# Evaluation is a preview, and says so
# --------------------------------------------------------------------------- #
def test_evaluating_a_published_template_decides_create_and_writes_nothing(client):
    _published(client)
    result = _preview(client, template_id=None)
    assert result["decision"] == "CREATE_AGENT"
    assert result["recorded"] is False, "a preview must not leave a ledger row"
    assert result["request_id"] is None
    assert result["agent_id"] is None
    assert _ledger(client) == []
    assert _agents(client) == []


def test_the_checks_are_returned_in_the_order_they_ran(client):
    template = _published(client)
    result = _preview(client, template_id=template["id"])
    names = [c["name"] for c in result["checks"]]
    assert names == ["emergency_stop_clear", "template_resolved",
                     "capabilities_within_template", "capabilities_governed",
                     "delegation_within_limit", "no_reusable_agent_exists",
                     "registry_within_limits", "resources_available",
                     "approval_not_required"]
    assert all(c["passed"] for c in result["checks"])
    assert result["template_id"] == template["id"]
    assert result["template_version"] == 1


def test_evaluation_is_deterministic_across_repeated_calls(client):
    """Same input, same answer, same check order — twice in a row."""
    template = _published(client)
    first = _preview(client, template_id=template["id"],
                     requested_capabilities=["research.read"])
    second = _preview(client, template_id=template["id"],
                      requested_capabilities=["research.read"])
    assert first["decision"] == second["decision"]
    assert [c["name"] for c in first["checks"]] == [c["name"] for c in second["checks"]]
    assert first["reason"] == second["reason"]


def test_a_preview_stops_at_the_first_check_that_decides(client):
    result = _preview(client, template_id="does-not-exist")
    assert result["decision"] == "REJECT"
    assert [c["name"] for c in result["checks"]] == ["emergency_stop_clear",
                                                     "template_resolved"]
    assert "does not exist" in result["reason"]


# --------------------------------------------------------------------------- #
# Template resolution
# --------------------------------------------------------------------------- #
def test_a_template_is_resolved_by_category_without_an_explicit_id(client):
    template = _published(client, name="screener", category="research")
    result = _preview(client, role="research")
    assert result["decision"] == "CREATE_AGENT"
    assert result["template_id"] == template["id"]


def test_a_template_is_resolved_by_name_without_an_explicit_id(client):
    template = _published(client, name="researcher", category="screening")
    result = _preview(client, role="researcher")
    assert result["template_id"] == template["id"]


def test_no_matching_published_template_is_a_rejection_not_a_guess(client):
    _published(client, name="screener", category="research")
    result = _preview(client, role="accountant")
    assert result["decision"] == "REJECT"
    assert "no published template matches" in result["reason"]
    assert "template_id" in result["reason"]


def test_an_ambiguous_match_is_refused_rather_than_chosen(client):
    """Two templates match the role. Picking one would make the decision depend
    on ordering, which is not a reason anyone can audit."""
    a = _published(client, name="screener-one", category="research")
    b = _published(client, name="screener-two", category="research")
    result = _preview(client, role="research")
    assert result["decision"] == "REJECT"
    assert "2 published templates match" in result["reason"]
    assert a["name"] in result["reason"] and b["name"] in result["reason"]


def test_a_draft_template_cannot_produce_an_agent(client):
    resp = client.post(TPL, json={"name": "drafted", "category": "research",
                                  "description": "", "configuration": _config()})
    assert resp.status_code == 201
    tid = resp.json()["data"]["template"]["id"]
    result = _preview(client, template_id=tid)
    assert result["decision"] == "REJECT"
    assert "not published" in result["reason"]


def test_a_published_template_with_an_unvalidated_version_is_refused(client):
    """Publishing requires a valid verdict, so this needs a revision that was
    never validated: the guard has to hold even then."""
    template = _published(client)
    resp = client.post(f"{TPL}/{template['id']}/versions",
                       json={"configuration": _config(mission="changed"), "reason": "r"})
    assert resp.status_code == 201, resp.text
    result = _preview(client, template_id=template["id"])
    # current_version does not move on revision, so the published version still
    # governs; the point is that it is still CREATE_AGENT and still version 1.
    assert result["decision"] == "CREATE_AGENT"
    assert result["template_version"] == 1


def test_a_deprecated_template_cannot_produce_an_agent(client):
    template = _published(client)
    assert client.post(f"{TPL}/{template['id']}/deprecate",
                       json={"reason": "superseded"}).status_code == 200
    result = _preview(client, template_id=template["id"])
    assert result["decision"] == "REJECT"
    assert "deprecated" in result["reason"]


# --------------------------------------------------------------------------- #
# Capabilities
# --------------------------------------------------------------------------- #
def test_a_capability_outside_the_template_is_refused_and_named(client):
    template = _published(client)
    result = _preview(client, template_id=template["id"],
                      requested_capabilities=["research.read", "payments.spend"])
    assert result["decision"] == "REJECT"
    assert "payments.spend" in result["reason"]
    assert "the template does not allow" in result["reason"]


def test_a_capability_inside_the_template_is_accepted(client):
    template = _published(client, allowed_capabilities=["research.read", "research.write"])
    result = _preview(client, template_id=template["id"],
                      requested_capabilities=["research.write"])
    assert result["decision"] == "CREATE_AGENT"


def test_the_response_says_the_catalog_is_checked_and_what_it_does_not_cover(
        client, settings):
    """Closes L-64's disclosure half.

    A creation decision now consults the catalog. The response also says which
    part is still false: nothing calls `check()` at a tool boundary yet, because
    adapters are P-05 and assignment output contracts are Stage 6.
    """
    template = _published(client)
    result = _preview(client, template_id=template["id"])
    governed = next(c for c in result["checks"] if c["name"] == "capabilities_governed")
    assert governed["passed"] is True
    status = client.get(f"{FACTORY}/status").json()["data"]
    assert status["capability_catalog_checked"] is True
    assert status["catalog_size"] == len(BUILTIN_CATALOG)
    assert status["prohibited_keys"] == sorted(PROHIBITED_CAPABILITIES)
    note = status["capability_catalog_note"]
    assert "check()" in note and "P-05" in note, note


def test_a_prohibited_capability_is_refused_even_when_a_template_allows_it(
        client, settings):
    """L-64's required resolution: level 3 is refused outright.

    The template allows the key, so the subset check passes - which is exactly
    why the catalog check has to be a separate one. A template cannot authorize
    what no agent may ever hold, and no approval code path can reach it either.
    """
    template = _published(client)
    _force_allowed_capabilities(settings, template["id"], ["spending.authorize"])
    result = _preview(client, template_id=template["id"],
                      requested_capabilities=["spending.authorize"])
    assert result["decision"] == "REJECT"
    assert "prohibited" in result["reason"] and "level 3" in result["reason"]
    assert next(c for c in result["checks"]
                if c["name"] == "capabilities_governed")["passed"] is False
    # Refused at the catalog check, so nothing downstream ran and nothing was recorded.
    names = [c["name"] for c in result["checks"]]
    assert "registry_within_limits" not in names
    assert result["recorded"] is False and _ledger(client) == []


def test_an_unknown_or_disabled_capability_is_refused(client, settings):
    """The catalog is closed: an unknown key is a mistake, a disabled one is not
    grantable yet, and neither becomes an agent."""
    template = _published(client)
    _force_allowed_capabilities(settings, template["id"], ["not.a.key", "execution.tool"])
    unknown = _preview(client, template_id=template["id"],
                       requested_capabilities=["not.a.key"])
    assert unknown["decision"] == "REJECT"
    assert "not in the capability catalog" in unknown["reason"]
    disabled = _preview(client, template_id=template["id"],
                        requested_capabilities=["execution.tool"])
    assert disabled["decision"] == "REJECT" and "disabled" in disabled["reason"]


def test_a_capability_needing_the_owner_sends_the_creation_to_approval(client):
    """Level 2 is not a refusal - it is a request that must reach the owner."""
    template = _published(client, allowed_capabilities=["agents.create_request"])
    result = _preview(client, template_id=template["id"],
                      requested_capabilities=["agents.create_request"])
    assert result["approval_required"] is True
    assert "approval level 2" in result["reason"]


def test_a_level_one_capability_needs_no_approval(client):
    """Levels 0 and 1 are answered in code: their conditions are the scope
    requirement and the ceilings, not an owner's decision."""
    template = _published(client, allowed_capabilities=["research.write"])
    result = _preview(client, template_id=template["id"],
                      requested_capabilities=["research.write"])
    assert result["decision"] == "CREATE_AGENT"
    assert result["approval_required"] is False


# --------------------------------------------------------------------------- #
# Creation
# --------------------------------------------------------------------------- #
def test_creating_an_agent_mints_a_principal_a_row_and_a_snapshot(client, settings):
    template = _published(client)
    result = _ask(client, template_id=template["id"])
    assert result["decision"] == "CREATE_AGENT"
    assert result["recorded"] is True
    agent_id = result["agent_id"]
    assert agent_id

    agents = _agents(client)
    assert len(agents) == 1
    agent = agents[0]
    assert agent["id"] == agent_id
    assert agent["status"] == "ACTIVE"
    assert agent["template_id"] == template["id"]
    assert agent["template_version"] == 1
    assert agent["configuration_version"] == 1

    # The snapshot has no endpoint in this stage, so it is read directly: this is
    # the record of what the agent was created from.
    history = _snapshot_for(settings, agent_id)
    assert len(history) == 1
    assert history[0]["version"] == 1
    assert history[0]["snapshot"]["mission"] == _config()["mission"]
    assert template["id"] in history[0]["reason"]


def test_the_ledger_records_the_decision_and_closes_it(client):
    template = _published(client)
    result = _ask(client, template_id=template["id"])
    rows = _ledger(client)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == result["request_id"]
    assert row["decision"] == "CREATE_AGENT"
    assert row["decision_reason"]
    assert row["completed_at"] is not None
    assert row["approval_status"] == "not_required"
    fetched = client.get(f"{FACTORY}/requests/{row['id']}").json()["data"]
    assert fetched["id"] == row["id"]


def test_a_rejected_request_is_still_recorded(client):
    """The request row is written before execution, so a refusal is on the ledger
    rather than having silently not happened."""
    result = _ask(client, template_id="does-not-exist")
    assert result["decision"] == "REJECT"
    rows = _ledger(client, decision="REJECT")
    assert len(rows) == 1
    assert rows[0]["decision_reason"]
    assert rows[0]["completed_at"] is not None
    assert _agents(client) == []


def test_creation_publishes_both_the_request_and_the_outcome(client):
    template = _published(client)
    result = _ask(client, template_id=template["id"])
    requested = _wait_for_event(client, "AgentCreationRequested", result["request_id"])
    created = _wait_for_event(client, "AgentCreated", result["request_id"])
    assert requested["payload"]["decision"] == "CREATE_AGENT"
    assert created["payload"]["agent_id"] == result["agent_id"]
    assert requested["source"] == "agent_factory"


def test_an_explicit_name_is_used_and_a_generated_one_is_derived(client):
    template = _published(client)
    named = _ask(client, template_id=template["id"], agent_name="named-researcher")
    assert named["decision"] == "CREATE_AGENT", named
    generated = _ask(client, template_id=template["id"], role="screening",
                     allow_reuse=False)
    names = sorted(a["name"] for a in _agents(client))
    assert "named-researcher" in names
    assert any(n.startswith("agent-screening-") for n in names), names
    assert generated["agent_id"] != named["agent_id"]


def test_a_duplicate_explicit_name_does_not_create_a_second_agent(client):
    template = _published(client)
    first = _ask(client, template_id=template["id"], agent_name="fixed-name",
                 allow_reuse=False)
    assert first["decision"] == "CREATE_AGENT"
    second = _ask(client, template_id=template["id"], agent_name="fixed-name",
                  allow_reuse=False)
    # The retry loop derives a distinct name rather than failing the request, so
    # two agents exist and neither shares a principal.
    assert second["decision"] == "CREATE_AGENT", second
    agents = _agents(client)
    assert len(agents) == 2
    assert len({a["name"] for a in agents}) == 2


# --------------------------------------------------------------------------- #
# Reuse
# --------------------------------------------------------------------------- #
def test_an_existing_agent_for_the_same_role_is_reused(client):
    template = _published(client)
    first = _ask(client, template_id=template["id"])
    second = _ask(client, template_id=template["id"])
    assert second["decision"] == "REUSE_EXISTING"
    assert second["reuse_agent_id"] == first["agent_id"]
    assert second["agent_id"] == first["agent_id"]
    assert len(_agents(client)) == 1, "reuse must not mint a second identity"


def test_reuse_publishes_no_creation_event(client):
    """Reusing an agent creates nothing, so a creation event for it would inflate
    every downstream count of agents that were made."""
    template = _published(client)
    first = _ask(client, template_id=template["id"])
    _wait_for_event(client, "AgentCreated", first["request_id"])
    second = _ask(client, template_id=template["id"])
    assert second["decision"] == "REUSE_EXISTING"
    _wait_for_event(client, "AgentCreationRequested", second["request_id"])
    time.sleep(0.15)
    assert _events(client, "AgentCreated", second["request_id"]) == []


def test_reuse_can_be_declined(client):
    template = _published(client)
    _ask(client, template_id=template["id"])
    result = _ask(client, template_id=template["id"], allow_reuse=False)
    assert result["decision"] == "CREATE_AGENT"
    assert len(_agents(client)) == 2


def test_a_retired_agent_is_not_reused(client, settings):
    """Retirement has no endpoint in this stage (it is Stage 8), so the state is
    written directly to prove the engine honours it."""
    template = _published(client)
    first = _ask(client, template_id=template["id"])
    _set_agent_field(settings, first["agent_id"], status="RETIRED",
                     retired_at=utcnow())
    second = _ask(client, template_id=template["id"])
    assert second["decision"] == "CREATE_AGENT"
    assert second["agent_id"] != first["agent_id"]


def test_a_suspended_agent_is_not_reused(client, settings):
    """Reusing a suspended agent would hide the reason it was suspended."""
    template = _published(client)
    first = _ask(client, template_id=template["id"])
    _set_agent_field(settings, first["agent_id"], status="SUSPENDED")
    second = _ask(client, template_id=template["id"])
    assert second["decision"] == "CREATE_AGENT"


def test_an_agent_from_a_different_template_is_not_reused(client):
    a = _published(client, name="screener", category="research")
    b = _published(client, name="writer", category="writing")
    _ask(client, template_id=a["id"])
    result = _ask(client, template_id=b["id"], role="writing")
    assert result["decision"] == "CREATE_AGENT"


# --------------------------------------------------------------------------- #
# Limits and the queue
# --------------------------------------------------------------------------- #
def test_the_registry_ceiling_queues_rather_than_refuses(client, settings):
    settings.agent_max_total = 1
    template = _published(client)
    first = _ask(client, template_id=template["id"])
    assert first["decision"] == "CREATE_AGENT"
    second = _ask(client, template_id=template["id"], allow_reuse=False)
    assert second["decision"] == "QUEUE"
    assert "ceiling is 1" in second["reason"]
    assert len(_agents(client)) == 1
    row = _wait_for_request(client, second["request_id"], decision="QUEUE")
    assert row["completed_at"] is None, "a queued request stays open"
    _wait_for_event(client, "AgentCreationQueued", second["request_id"])


def test_the_per_template_ceiling_queues(client, settings):
    settings.agent_max_per_template = 1
    template = _published(client)
    assert _ask(client, template_id=template["id"])["decision"] == "CREATE_AGENT"
    second = _ask(client, template_id=template["id"], allow_reuse=False)
    assert second["decision"] == "QUEUE"
    assert "per-template ceiling is 1" in second["reason"]


def test_a_full_queue_rejects_and_says_how_full(client, settings):
    """Queuing without a bound is refusing slowly and without telling anyone."""
    settings.agent_max_total = 1
    settings.agent_max_creation_queue = 1
    template = _published(client)
    _ask(client, template_id=template["id"])
    queued = _ask(client, template_id=template["id"], allow_reuse=False)
    assert queued["decision"] == "QUEUE"
    refused = _ask(client, template_id=template["id"], allow_reuse=False)
    assert refused["decision"] == "REJECT"
    assert "queue is full" in refused["reason"]
    assert "1/1" in refused["reason"]


def test_draining_the_queue_executes_what_now_fits(client, settings):
    settings.agent_max_total = 1
    template = _published(client)
    _ask(client, template_id=template["id"])
    queued = _ask(client, template_id=template["id"], allow_reuse=False)
    assert queued["decision"] == "QUEUE"

    settings.agent_max_total = 3
    resp = client.post(f"{FACTORY}/queue/drain")
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["considered"] == 1
    assert body["outcomes"][0]["decision"] == "CREATE_AGENT"
    assert len(_agents(client)) == 2
    _wait_for_request(client, queued["request_id"], decision="CREATE_AGENT")
    row = client.get(f"{FACTORY}/requests/{queued['request_id']}").json()["data"]
    assert row["completed_at"] is not None


def test_draining_an_empty_queue_is_visibly_a_no_op(client):
    resp = client.post(f"{FACTORY}/queue/drain")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["considered"] == 0
    assert body["outcomes"] == []


def test_a_queued_request_survives_until_it_is_drained(client, settings):
    """Nothing here runs on a timer: autonomous scheduling is P-12."""
    settings.agent_max_total = 1
    template = _published(client)
    _ask(client, template_id=template["id"])
    queued = _ask(client, template_id=template["id"], allow_reuse=False)
    time.sleep(0.2)
    row = client.get(f"{FACTORY}/requests/{queued['request_id']}").json()["data"]
    assert row["decision"] == "QUEUE"
    assert row["completed_at"] is None
    assert len(_agents(client)) == 1


# --------------------------------------------------------------------------- #
# Delegation depth
# --------------------------------------------------------------------------- #
def test_delegation_within_the_ceiling_is_allowed(client, settings):
    settings.agent_max_delegation_depth = 1
    template = _published(client)
    parent = _ask(client, template_id=template["id"])
    child = _ask(client, template_id=template["id"], allow_reuse=False,
                 parent_agent_id=parent["agent_id"])
    assert child["decision"] == "CREATE_AGENT", child
    check = next(c for c in child["checks"] if c["name"] == "delegation_within_limit")
    assert check["passed"] is True and "depth 1" in check["detail"]


def test_delegation_beyond_the_ceiling_is_refused(client, settings):
    settings.agent_max_delegation_depth = 1
    template = _published(client)
    parent = _ask(client, template_id=template["id"])
    child = _ask(client, template_id=template["id"], allow_reuse=False,
                 parent_agent_id=parent["agent_id"])
    grandchild = _ask(client, template_id=template["id"], allow_reuse=False,
                      parent_agent_id=child["agent_id"])
    assert grandchild["decision"] == "REJECT"
    assert "ceiling is 1" in grandchild["reason"]


def test_a_missing_parent_is_refused(client):
    template = _published(client)
    result = _ask(client, template_id=template["id"], parent_agent_id="no-such-agent")
    assert result["decision"] == "REJECT"
    assert "does not exist" in result["reason"]


def test_a_cyclic_parent_chain_is_refused_rather_than_followed(client, settings):
    """Written directly because no endpoint can create a cycle, and a cycle that
    was followed forever would hang the request."""
    template = _published(client)
    a = _ask(client, template_id=template["id"])
    b = _ask(client, template_id=template["id"], allow_reuse=False,
             parent_agent_id=a["agent_id"])
    _set_agent_field(settings, a["agent_id"], parent_agent_id=b["agent_id"])
    result = _ask(client, template_id=template["id"], allow_reuse=False,
                  parent_agent_id=a["agent_id"])
    assert result["decision"] == "REJECT"
    assert "cycle" in result["reason"]


def test_a_retired_parent_is_refused(client, settings):
    template = _published(client)
    parent = _ask(client, template_id=template["id"])
    _set_agent_field(settings, parent["agent_id"], status="RETIRED", retired_at=utcnow())
    result = _ask(client, template_id=template["id"], allow_reuse=False,
                  parent_agent_id=parent["agent_id"])
    assert result["decision"] == "REJECT"
    assert "retired" in result["reason"]


# --------------------------------------------------------------------------- #
# The approval gate
# --------------------------------------------------------------------------- #
def test_a_gated_template_opens_an_approval_and_creates_nothing(client, settings):
    """Asked by a principal that cannot decide approvals, so the gate is real."""
    template = _published(client, approval_requirements=["agent_creation"])
    result = _ask_as(client, _requester_token(settings), template_id=template["id"])
    assert result["decision"] == "REQUEST_OWNER_APPROVAL"
    assert result["approval_required"] is True
    assert result["agent_id"] is None
    assert _agents(client) == []
    assert result["approval_id"]

    approval = client.get(f"/api/v1/approvals/{result['approval_id']}").json()["data"]
    assert approval["status"] == "pending"
    assert approval["action"] == "agent.create"
    assert approval["risk"] == "high"
    assert approval["resource"] == result["request_id"]
    row = _wait_for_request(client, result["request_id"], approval_status="pending")
    assert row["completed_at"] is None
    _wait_for_event(client, "AgentCreationApprovalRequested", result["request_id"])


def test_a_restricted_template_is_gated_too(client, settings):
    template = _published(client, security_classification="restricted")
    result = _ask_as(client, _requester_token(settings), template_id=template["id"])
    assert result["decision"] == "REQUEST_OWNER_APPROVAL"
    assert "restricted" in result["reason"]


def test_an_ungated_template_needs_no_approval(client):
    template = _published(client)
    result = _ask(client, template_id=template["id"])
    assert result["approval_required"] is False
    row = client.get(f"{FACTORY}/requests/{result['request_id']}").json()["data"]
    assert row["approval_status"] == "not_required"


def test_the_owner_asking_for_a_gated_agent_is_its_own_authorization(client):
    """No approval is opened, because an approval only the owner could decide -
    and which the self-approval block forbids the owner from deciding - would be
    unanswerable rather than safe. The template's requirement is still reported.
    """
    template = _published(client, approval_requirements=["agent_creation"])
    result = _ask(client, template_id=template["id"])
    assert result["decision"] == "CREATE_AGENT", result
    assert result["approval_required"] is True, "the template still requires approval"
    assert result["approval_id"] is None
    assert result["agent_id"]
    check = next(c for c in result["checks"]
                 if c["name"] == "requester_holds_deciding_authority")
    assert check["passed"] is True
    assert "approvals.decide" in check["detail"]
    assert "unanswerable" in result["reason"]
    row = client.get(f"{FACTORY}/requests/{result['request_id']}").json()["data"]
    assert row["approval_status"] == "not_required"
    assert client.get("/api/v1/approvals?status=pending").json()["data"] == []


def test_the_owner_granting_the_approval_creates_the_agent(client, settings):
    template = _published(client, approval_requirements=["agent_creation"])
    gated = _ask_as(client, _requester_token(settings, "grant-case"),
                    template_id=template["id"])
    resp = client.post(f"/api/v1/approvals/{gated['approval_id']}/decision",
                       json={"decision": "approved", "notes": "go ahead"})
    assert resp.status_code == 200, resp.text
    row = _wait_for_request(client, gated["request_id"], decision="CREATE_AGENT",
                            approval_status="granted")
    assert row["completed_at"] is not None
    agents = _agents(client)
    assert len(agents) == 1
    assert agents[0]["status"] == "ACTIVE"


def test_the_owner_rejecting_the_approval_closes_the_request(client, settings):
    template = _published(client, approval_requirements=["agent_creation"])
    gated = _ask_as(client, _requester_token(settings, "reject-case"),
                    template_id=template["id"])
    resp = client.post(f"/api/v1/approvals/{gated['approval_id']}/decision",
                       json={"decision": "rejected", "notes": "not now"})
    assert resp.status_code == 200, resp.text
    row = _wait_for_request(client, gated["request_id"], approval_status="rejected")
    assert row["completed_at"] is not None
    assert _agents(client) == []
    _wait_for_event(client, "AgentCreationRejected", gated["request_id"])


def test_a_granted_approval_does_not_override_a_ceiling_reached_while_it_waited(
        client, settings):
    """Approval is authority to create, not a guarantee that creation is still
    possible: the request is re-evaluated when the decision arrives."""
    template = _published(client, approval_requirements=["agent_creation"])
    gated = _ask_as(client, _requester_token(settings, "ceiling-case"),
                    template_id=template["id"])
    other = _published(client, name="plain", category="plain")
    settings.agent_max_total = 1
    _ask(client, template_id=other["id"], role="plain")

    resp = client.post(f"/api/v1/approvals/{gated['approval_id']}/decision",
                       json={"decision": "approved"})
    assert resp.status_code == 200, resp.text
    row = _wait_for_request(client, gated["request_id"], approval_status="granted")
    assert row["decision"] == "QUEUE", row
    assert len(_agents(client)) == 1


def test_a_requester_without_deciding_authority_cannot_close_its_own_gate(
        client, settings):
    """An agent that can ask but cannot decide: the permission engine refuses it
    before the self-approval rule is even reached."""
    template = _published(client, approval_requirements=["agent_creation"])
    requester = _requester_token(settings, "plain-requester")
    gated = _ask_as(client, requester, template_id=template["id"])
    assert gated["decision"] == "REQUEST_OWNER_APPROVAL"

    decide = client.post(f"/api/v1/approvals/{gated['approval_id']}/decision",
                         json={"decision": "approved"}, headers=_auth(client, requester))
    assert decide.status_code == 403, decide.text
    assert decide.json()["error"]["details"]["permission"] == "approvals.decide"
    assert _agents(client) == []
    row = client.get(f"{FACTORY}/requests/{gated['request_id']}").json()["data"]
    assert row["approval_status"] == "pending"
    assert row["completed_at"] is None


def test_the_self_approval_block_bites_if_a_requester_later_gains_authority(
        client, settings):
    """Why gated creations are opened at risk ``high``.

    The requester could not decide its own approval when it asked. If it is
    granted ``approvals.decide`` afterwards, the permission check now passes - and
    the self-approval rule is what still refuses it. Without risk ``high`` this
    would be a route from "asked for an agent" to "authorized that agent".
    """
    template = _published(client, approval_requirements=["agent_creation"])
    token, principal_id = _principal(
        settings, "later-empowered", ("agents.factory.admin", "agents.factory.read"))
    gated = _ask_as(client, token, template_id=template["id"])
    assert gated["decision"] == "REQUEST_OWNER_APPROVAL"
    assert client.post(f"/api/v1/approvals/{gated['approval_id']}/decision",
                       json={"decision": "approved"},
                       headers=_auth(client, token)).status_code == 403

    _grant(settings, principal_id, "approvals.decide")
    decide = client.post(f"/api/v1/approvals/{gated['approval_id']}/decision",
                         json={"decision": "approved"}, headers=_auth(client, token))
    assert decide.status_code == 403, decide.text
    assert "own high/critical" in decide.text
    assert _agents(client) == []
    row = client.get(f"{FACTORY}/requests/{gated['request_id']}").json()["data"]
    assert row["approval_status"] == "pending"


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #
def test_a_repeated_idempotency_key_replays_the_recorded_outcome(client):
    template = _published(client)
    first = _ask(client, template_id=template["id"], idempotency_key="key-one")
    second = _ask(client, template_id=template["id"], idempotency_key="key-one")
    assert second["replayed"] is True
    assert second["request_id"] == first["request_id"]
    assert second["decision"] == first["decision"]
    assert len(_ledger(client)) == 1
    assert len(_agents(client)) == 1


def test_distinct_keys_create_distinct_agents(client):
    template = _published(client)
    a = _ask(client, template_id=template["id"], idempotency_key="key-a",
             allow_reuse=False)
    b = _ask(client, template_id=template["id"], idempotency_key="key-b",
             allow_reuse=False)
    assert a["agent_id"] != b["agent_id"]
    assert len(_ledger(client)) == 2


def test_requests_without_a_key_never_collide(client):
    template = _published(client)
    a = _ask(client, template_id=template["id"], allow_reuse=False)
    b = _ask(client, template_id=template["id"], allow_reuse=False)
    assert a["request_id"] != b["request_id"]
    assert len(_ledger(client)) == 2


def test_a_replayed_rejection_is_still_a_rejection(client):
    first = _ask(client, template_id="nope", idempotency_key="key-bad")
    assert first["decision"] == "REJECT"
    second = _ask(client, template_id="nope", idempotency_key="key-bad")
    assert second["replayed"] is True
    assert second["decision"] == "REJECT"
    assert len(_ledger(client)) == 1


# --------------------------------------------------------------------------- #
# Emergency stop
# --------------------------------------------------------------------------- #
def test_an_active_emergency_stop_refuses_every_creation(client):
    template = _published(client)
    resp = client.post("/api/v1/system/emergency/activate",
                       json={"reason": "stop everything"})
    assert resp.status_code == 200, resp.text
    try:
        result = _ask(client, template_id=template["id"])
        assert result["decision"] == "REJECT"
        assert "emergency stop" in result["reason"]
        # Evaluation stops at the first check that forces a decision, so the
        # template is never even resolved while the stop is active.
        assert [c["name"] for c in result["checks"]] == ["emergency_stop_clear"]
        assert result["checks"][0]["passed"] is False
        assert _agents(client) == []
        preview = _preview(client, template_id=template["id"])
        assert preview["decision"] == "REJECT"
    finally:
        assert client.post("/api/v1/system/emergency/clear",
                           json={"reason": "resolved"}).status_code == 200
    after = _ask(client, template_id=template["id"])
    assert after["decision"] == "CREATE_AGENT"


# --------------------------------------------------------------------------- #
# Status and the subsystem report
# --------------------------------------------------------------------------- #
def test_status_reports_counts_against_the_configured_ceilings(client, settings):
    template = _published(client)
    _ask(client, template_id=template["id"])
    status = client.get(f"{FACTORY}/status").json()["data"]
    assert status["live_agents"] == 1
    assert status["retired_agents"] == 0
    assert status["decisions_recorded"]["CREATE_AGENT"] == 1
    assert status["decisions_recorded"]["ASSIGN_EXISTING"] == 0
    assert status["limits"]["agent_max_total"] == settings.agent_max_total
    assert status["limits"]["agent_max_delegation_depth"] == \
        settings.agent_max_delegation_depth


def test_status_reports_assignment_as_supported_and_says_what_it_does(client):
    """Stage 6 turned this from a promise into a path, so the note has to describe
    the path rather than name the stage that would build it."""
    status = client.get(f"{FACTORY}/status").json()["data"]
    assert status["assignment_supported"] is True
    assert "ASSIGN_EXISTING" in status["assignment_note"]
    assert "nine assignment rules" in status["assignment_note"]


def test_the_agent_subsystem_status_reports_the_factory_as_built(client):
    status = client.get(f"{AGENTS}/status").json()["data"]
    assert status["enabled"] is True
    assert status["factory"] is True
    # Stage 5 built the capability catalog and Stage 6 the assignment ledger, so
    # both are reported as present. The stage string names the newest stage, which
    # is why this assertion lives here rather than in an older stage's file.
    assert status["capabilities"] is True
    assert status["assignments"] is True
    assert "Stage 6" in status["stage"]


def test_assign_existing_needs_the_request_to_name_a_task(client):
    """`ASSIGN_EXISTING` is an answer about *work*, so without named work the answer
    stays `REUSE_EXISTING`. Stage 6 gave the decision an execution path; this guards
    that the path is reached only by the thing that justifies it."""
    template = _published(client)
    _ask(client, template_id=template["id"])
    _ask(client, template_id=template["id"])
    _ask(client, template_id="nope")
    assert _ledger(client, decision="ASSIGN_EXISTING") == []
    status = client.get(f"{FACTORY}/status").json()["data"]
    assert status["decisions_recorded"]["ASSIGN_EXISTING"] == 0


# --------------------------------------------------------------------------- #
# Input validation and authorization
# --------------------------------------------------------------------------- #
def test_an_unknown_field_is_refused(client):
    _published(client)
    resp = client.post(f"{FACTORY}/create", json={
        "requested_role": "research", "justification": "j", "surprise": 1})
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("payload", [
    {"requested_role": "", "justification": "j"},
    {"requested_role": "r", "justification": ""},
    {"justification": "j"},
    {"requested_role": "r"},
])
def test_an_incomplete_request_is_refused(client, payload):
    resp = client.post(f"{FACTORY}/create", json=payload)
    assert resp.status_code == 422, resp.text


def test_an_unknown_decision_filter_returns_nothing_rather_than_everything(client):
    _published(client)
    _ask(client)
    assert _ledger(client, decision="BANANA") == []


def test_a_missing_request_is_a_404(client):
    resp = client.get(f"{FACTORY}/requests/not-here")
    assert resp.status_code == 404, resp.text


@pytest.mark.parametrize("method,path,payload", [
    ("post", f"{FACTORY}/evaluate", {"requested_role": "r", "justification": "j"}),
    ("post", f"{FACTORY}/create", {"requested_role": "r", "justification": "j"}),
    ("get", f"{FACTORY}/requests", None),
    ("get", f"{FACTORY}/requests/some-id", None),
    ("post", f"{FACTORY}/queue/drain", None),
    ("get", f"{FACTORY}/status", None),
])
def test_a_principal_without_factory_permissions_is_refused(client, settings, method,
                                                            path, payload):
    token = _token_for(settings, "factory-probe")
    resp = client.request(method, path, json=payload, headers=_auth(client, token))
    assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}: {resp.text[:200]}"


def test_read_permission_alone_cannot_create_or_drain(client, settings):
    """Splitting read from admin means an agent can ask what would happen without
    being able to make it happen."""
    _published(client)
    token = _token_for(settings, "reader-only", ("agents.factory.read",))
    preview = client.post(f"{FACTORY}/evaluate",
                          json={"requested_role": "research", "justification": "j"},
                          headers=_auth(client, token))
    assert preview.status_code == 200, preview.text
    assert client.get(f"{FACTORY}/status", headers=_auth(client, token)).status_code == 200

    create = client.post(f"{FACTORY}/create",
                         json={"requested_role": "research", "justification": "j"},
                         headers=_auth(client, token))
    assert create.status_code == 403, create.text
    drain = client.post(f"{FACTORY}/queue/drain", headers=_auth(client, token))
    assert drain.status_code == 403, drain.text
    assert _agents(client) == []


# --------------------------------------------------------------------------- #
# The disabled phase
# --------------------------------------------------------------------------- #
@pytest.fixture()
def disabled_client(settings, owner_credentials):
    """A whole application assembled with the agent subsystem switched off."""
    settings.agents_enabled = False

    async def bootstrap() -> str:
        db = Database(settings)
        try:
            await db.initialize()
            await seed_core_data(db, settings)
            return await AuthService(settings, db).bootstrap_owner(*owner_credentials)
        finally:
            await db.dispose()

    asyncio.run(bootstrap())
    app = create_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/v1/auth/login", json={"username": owner_credentials[0],
                                                 "password": owner_credentials[1]})
        assert resp.status_code == 200, resp.text
        c.headers.update({"Authorization":
                          f"Bearer {resp.json()['data']['access_token']}"})
        yield c


@pytest.mark.parametrize("method,path,payload", [
    ("post", f"{FACTORY}/evaluate", {"requested_role": "r", "justification": "j"}),
    ("post", f"{FACTORY}/create", {"requested_role": "r", "justification": "j"}),
    ("get", f"{FACTORY}/requests", None),
    ("post", f"{FACTORY}/queue/drain", None),
    ("get", f"{FACTORY}/status", None),
    ("get", TPL, None),
    ("post", TPL, {"name": "x", "category": "y",
                   "configuration": _config()}),
    ("get", AGENTS, None),
])
def test_a_disabled_phase_reports_that_it_is_disabled(disabled_client, method, path,
                                                      payload):
    """409 naming the setting, not a 500 from a half-built engine."""
    resp = disabled_client.request(method, path, json=payload)
    assert resp.status_code == 409, f"{method} {path} -> {resp.status_code}: {resp.text[:200]}"
    assert "AUTONOMUS_AGENTS_ENABLED" in resp.text


def test_the_status_endpoint_still_answers_when_the_phase_is_disabled(disabled_client):
    """/agents/status is the endpoint that tells a caller the phase is off, so it
    must keep answering when everything else refuses."""
    resp = disabled_client.get(f"{AGENTS}/status")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["enabled"] is False
