"""P-04 Stage 3: the agent template registry and its validation gate.

Everything here goes through the HTTP surface, because that is the surface an
owner actually has: a verdict that is only reachable by calling the service
directly would not be evidence about the product.
"""
from __future__ import annotations

import asyncio
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.agents.templates import TEMPLATE_TRANSITIONS, diff_configurations
from app.core.auth import token_hash
from app.database.connection import Database
from app.database.models import utcnow
from app.database.repositories import PrincipalRepo, SessionRepo

TPL = "/api/v1/agent-templates"


def _config(**overrides) -> dict:
    """A configuration that passes both the schema and the policy checks."""
    base = {
        "role_definition": "market researcher",
        "mission": "Find and screen opportunities in the owner's category.",
        "system_instruction": "Report only what the evidence supports; say when it does not.",
        "expected_output_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}, "confidence": {"type": "number"}},
            "required": ["summary"],
        },
        "allowed_capabilities": ["research.read"],
        "resource_budget": {"max_concurrent_tasks": 2, "max_task_seconds": 600},
        "timeout_seconds": 120,
    }
    base.update(overrides)
    return base


def _create(client: TestClient, name: str = "researcher", **overrides) -> dict:
    resp = client.post(TPL, json={
        "name": name, "category": overrides.pop("category", "research"),
        "description": overrides.pop("description", "screens opportunities"),
        "configuration": _config(**overrides),
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _publish(client: TestClient, template_id: str, version: int | None = None) -> dict:
    """Validate then publish: the only route to a published template."""
    assert client.post(f"{TPL}/{template_id}/validate",
                       json={"version": version}).status_code == 200
    resp = client.post(f"{TPL}/{template_id}/publish", json={"version": version})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _wait_for_event(client: TestClient, event_type: str, template_id: str,
                    timeout: float = 5.0) -> dict:
    """The bus writes asynchronously, so an event is polled for, not assumed."""
    deadline = time.monotonic() + timeout
    seen: list[dict] = []
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/events?event_type={event_type}&limit=200")
        assert resp.status_code == 200, resp.text
        seen = [e for e in resp.json()["data"]
                if e.get("payload", {}).get("template_id") == template_id]
        if seen:
            return seen[0]
        time.sleep(0.03)
    raise AssertionError(f"no {event_type} event for {template_id}; saw {len(seen)}")


def _agent_token(settings) -> str:
    """A non-owner principal with a valid session and no permissions."""

    async def setup() -> str:
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                principal = await PrincipalRepo(session).create("agent", "template-probe")
                token = "agent-token-templates"
                await SessionRepo(session).create(
                    token_hash(token), principal.id, utcnow() + timedelta(minutes=5))
                await session.commit()
                return token
        finally:
            await db.dispose()

    return asyncio.run(setup())


# --------------------------------------------------------------------------- #
# Creation and reads
# --------------------------------------------------------------------------- #
def test_creating_a_template_yields_a_draft_holding_an_unvalidated_version(client):
    data = _create(client)
    assert data["template"]["status"] == "draft"
    assert data["template"]["current_version"] == 1
    assert data["version"]["version"] == 1
    assert data["version"]["validation_status"] == "unvalidated"
    assert data["version"]["validation_details"] is None
    assert data["version"]["created_by"], "authorship must be recorded"


def test_an_unknown_configuration_key_is_refused_not_dropped(client):
    """A misspelled ``allowed_capabilitys`` that was quietly discarded would
    produce a template granting nothing, and the omission would read as a
    decision. The P-03 convention applies: an unexpected field is a 422."""
    resp = client.post(TPL, json={
        "name": "typo", "category": "research",
        "configuration": _config(allowed_capabilitys=["research.read"])})
    assert resp.status_code == 422, resp.text
    body = resp.json()["error"]
    assert body["code"] == "template_configuration_invalid"
    assert any("allowed_capabilitys" in i for i in body["details"]["issues"])
    assert client.get(TPL).json()["meta"]["total"] == 0


def test_an_unknown_top_level_request_field_is_refused(client):
    resp = client.post(TPL, json={"name": "x", "category": "research",
                                  "configuration": _config(), "hint": "ignored?"})
    assert resp.status_code == 422, resp.text


def test_the_stored_configuration_is_the_canonical_shape(client):
    """Defaults are materialised at the boundary, so two equivalent documents
    store identically - which is what makes the fingerprint mean anything."""
    data = _create(client)
    stored = data["version"]["configuration"]
    assert stored["timeout_seconds"] == 120
    assert stored["security_classification"] == "internal"
    assert stored["resource_budget"]["max_child_agents"] == 0
    assert stored["retry_policy"] == {"max_retries": 2, "base_delay_seconds": 0.1,
                                      "max_delay_seconds": 5.0}


def test_a_configuration_that_does_not_parse_is_refused_with_its_reasons(client):
    resp = client.post(TPL, json={"name": "broken", "category": "research",
                                  "configuration": {"mission": 123}})
    assert resp.status_code == 422, resp.text
    body = resp.json()["error"]
    assert body["code"] == "template_configuration_invalid"
    assert body["details"]["issues"], "a refusal must say why"
    assert client.get(TPL).json()["meta"]["total"] == 0, "nothing may be stored"


def test_a_template_may_not_both_allow_and_restrict_a_capability(client):
    resp = client.post(TPL, json={
        "name": "contradictory", "category": "research",
        "configuration": _config(allowed_capabilities=["research.read"],
                                 restricted_capabilities=["research.read"])})
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "template_configuration_invalid"


def test_duplicate_template_names_are_refused(client):
    _create(client, name="unique-name")
    resp = client.post(TPL, json={"name": "unique-name", "category": "research",
                                  "configuration": _config()})
    assert resp.status_code == 409, resp.text


def test_listing_reports_a_total_and_honours_filters(client):
    _create(client, name="alpha", category="research")
    _create(client, name="beta", category="operations")
    published = _create(client, name="gamma", category="research")
    _publish(client, published["template"]["id"])

    everything = client.get(TPL).json()
    assert everything["meta"]["total"] == 3
    drafts = client.get(f"{TPL}?status=draft").json()
    assert drafts["meta"]["total"] == 2
    research = client.get(f"{TPL}?category=research").json()
    assert research["meta"]["total"] == 2
    both = client.get(f"{TPL}?status=published&category=research").json()
    assert both["meta"]["total"] == 1
    assert both["data"][0]["name"] == "gamma"


def test_pagination_is_bounded_and_offset_applies(client):
    for i in range(3):
        _create(client, name=f"page-{i}")
    page = client.get(f"{TPL}?limit=2&offset=0").json()
    assert len(page["data"]) == 2
    assert page["meta"]["total"] == 3
    rest = client.get(f"{TPL}?limit=2&offset=2").json()
    assert len(rest["data"]) == 1
    assert client.get(f"{TPL}?limit=0").status_code == 422
    assert client.get(f"{TPL}?limit=201").status_code == 422


def test_reading_an_unknown_template_or_version_is_a_404(client):
    assert client.get(f"{TPL}/no-such-id").status_code == 404
    created = _create(client)
    tid = created["template"]["id"]
    assert client.get(f"{TPL}/{tid}/versions/99").status_code == 404
    assert client.get("/api/v1/agent-templates/no-such-id/versions").status_code == 404


# --------------------------------------------------------------------------- #
# Versions are immutable
# --------------------------------------------------------------------------- #
def test_revising_appends_a_version_and_never_edits_the_previous_one(client):
    tid = _create(client)["template"]["id"]
    first = client.get(f"{TPL}/{tid}/versions/1").json()["data"]

    resp = client.post(f"{TPL}/{tid}/versions",
                       json={"configuration": _config(mission="A narrower mission."),
                             "reason": "scope narrowed"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["version"] == 2
    assert resp.json()["data"]["validation_status"] == "unvalidated"

    unchanged = client.get(f"{TPL}/{tid}/versions/1").json()["data"]
    assert unchanged["configuration"] == first["configuration"]
    assert unchanged["id"] == first["id"]
    versions = client.get(f"{TPL}/{tid}/versions").json()["data"]
    assert [v["version"] for v in versions] == [2, 1], "newest first"


def test_current_version_does_not_move_when_a_template_is_revised(client):
    """Publishing selects a version; merely writing one must not."""
    tid = _create(client)["template"]["id"]
    _publish(client, tid, 1)
    client.post(f"{TPL}/{tid}/versions", json={"configuration": _config()})
    template = client.get(f"{TPL}/{tid}").json()["data"]
    assert template["status"] == "published"
    assert template["current_version"] == 1, "a revision must not silently take effect"


# --------------------------------------------------------------------------- #
# The validation gate
# --------------------------------------------------------------------------- #
def test_a_configuration_with_no_output_contract_is_judged_invalid(client):
    tid = _create(client, expected_output_schema={})["template"]["id"]
    resp = client.post(f"{TPL}/{tid}/validate", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["validation_status"] == "invalid"
    assert any("expected_output_schema" in i for i in data["details"]["issues"])
    # The verdict is persisted, not merely returned.
    stored = client.get(f"{TPL}/{tid}/versions/1").json()["data"]
    assert stored["validation_status"] == "invalid"
    assert stored["validation_details"]["issues"] == data["details"]["issues"]


def test_blank_intent_fields_are_judged_invalid(client):
    tid = _create(client, role_definition="   ", system_instruction="")["template"]["id"]
    data = client.post(f"{TPL}/{tid}/validate", json={}).json()["data"]
    assert data["validation_status"] == "invalid"
    joined = " ".join(data["details"]["issues"])
    assert "role_definition" in joined and "system_instruction" in joined


def test_a_valid_configuration_is_judged_valid_and_says_what_was_not_checked(client):
    tid = _create(client)["template"]["id"]
    data = client.post(f"{TPL}/{tid}/validate", json={}).json()["data"]
    assert data["validation_status"] == "valid"
    assert data["details"]["issues"] == []
    assert data["details"]["configuration_fingerprint"]
    # Honesty about scope: the capability catalog is a Stage 5 concern.
    assert data["details"]["capability_catalog_checked"] is False
    assert "Stage 5" in data["details"]["capability_catalog_note"]


def test_a_template_with_no_capabilities_is_valid_but_warned(client):
    tid = _create(client, allowed_capabilities=[])["template"]["id"]
    data = client.post(f"{TPL}/{tid}/validate", json={}).json()["data"]
    assert data["validation_status"] == "valid", "a warning is not a refusal"
    assert any("no capability" in w for w in data["details"]["warnings"])


def test_duplicate_capability_keys_are_an_issue(client):
    tid = _create(client, allowed_capabilities=["a.read", "a.read"])["template"]["id"]
    data = client.post(f"{TPL}/{tid}/validate", json={}).json()["data"]
    assert data["validation_status"] == "invalid"
    assert any("duplicate" in i for i in data["details"]["issues"])


def test_validating_a_specific_version_leaves_the_others_alone(client):
    tid = _create(client)["template"]["id"]
    client.post(f"{TPL}/{tid}/versions", json={"configuration": _config(
        expected_output_schema={})})
    good = client.post(f"{TPL}/{tid}/validate", json={"version": 1}).json()["data"]
    bad = client.post(f"{TPL}/{tid}/validate", json={"version": 2}).json()["data"]
    assert good["validation_status"] == "valid"
    assert bad["validation_status"] == "invalid"


# --------------------------------------------------------------------------- #
# Publishing, deprecating, restoring
# --------------------------------------------------------------------------- #
def test_an_unvalidated_version_cannot_be_published(client):
    tid = _create(client)["template"]["id"]
    resp = client.post(f"{TPL}/{tid}/publish", json={})
    assert resp.status_code == 409, resp.text
    error = resp.json()["error"]
    assert error["details"]["validation_status"] == "unvalidated"
    assert client.get(f"{TPL}/{tid}").json()["data"]["status"] == "draft"


def test_an_invalid_version_cannot_be_published_even_after_validation(client):
    tid = _create(client, expected_output_schema={})["template"]["id"]
    client.post(f"{TPL}/{tid}/validate", json={})
    resp = client.post(f"{TPL}/{tid}/publish", json={})
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["details"]["validation_status"] == "invalid"
    assert resp.json()["error"]["details"]["issues"], "the refusal carries its reasons"


def test_publishing_a_valid_version_selects_it(client):
    tid = _create(client)["template"]["id"]
    client.post(f"{TPL}/{tid}/versions", json={"configuration": _config(
        mission="Second attempt.")})
    published = _publish(client, tid, 2)
    assert published["status"] == "published"
    assert published["current_version"] == 2


def test_a_deprecated_template_cannot_be_revised_or_published(client):
    tid = _create(client)["template"]["id"]
    _publish(client, tid)
    assert client.post(f"{TPL}/{tid}/deprecate",
                       json={"reason": "superseded"}).json()["data"]["status"] == "deprecated"
    assert client.post(f"{TPL}/{tid}/versions",
                       json={"configuration": _config()}).status_code == 409
    resp = client.post(f"{TPL}/{tid}/publish", json={})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invalid_template_transition"
    assert resp.json()["error"]["details"]["current"] == "deprecated"


def test_restoring_a_deprecated_template_returns_a_draft_not_a_published_one(client):
    """A withdrawn template governs agent creation, so resuming that authority
    takes a deliberate second act rather than happening on restore."""
    tid = _create(client)["template"]["id"]
    _publish(client, tid)
    client.post(f"{TPL}/{tid}/deprecate", json={"reason": "review"})
    restored = client.post(f"{TPL}/{tid}/restore").json()["data"]
    assert restored["status"] == "draft"
    assert client.post(f"{TPL}/{tid}/restore").status_code == 409, "draft cannot restore"


def test_a_draft_can_be_deprecated_without_ever_being_published(client):
    tid = _create(client)["template"]["id"]
    resp = client.post(f"{TPL}/{tid}/deprecate", json={"reason": "abandoned"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "deprecated"


def test_deprecating_requires_a_reason(client):
    tid = _create(client)["template"]["id"]
    assert client.post(f"{TPL}/{tid}/deprecate", json={}).status_code == 422
    assert client.post(f"{TPL}/{tid}/deprecate", json={"reason": ""}).status_code == 422


# --------------------------------------------------------------------------- #
# Cloning and comparison
# --------------------------------------------------------------------------- #
def test_cloning_produces_a_draft_whose_version_is_unvalidated(client):
    """A verdict is evidence about one document under one template id; it does
    not transfer by assertion."""
    tid = _create(client, name="source")["template"]["id"]
    _publish(client, tid)
    resp = client.post(f"{TPL}/{tid}/clone", json={"name": "clone-of-source"})
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["template"]["status"] == "draft"
    assert data["version"]["validation_status"] == "unvalidated"
    assert data["cloned_from"] == {"template_id": tid, "version": 1}
    assert data["version"]["configuration"] == client.get(
        f"{TPL}/{tid}/versions/1").json()["data"]["configuration"]
    assert client.post(f"{TPL}/{data['template']['id']}/publish",
                       json={}).status_code == 409


def test_cloning_to_an_existing_name_is_refused(client):
    tid = _create(client, name="original")["template"]["id"]
    _create(client, name="taken")
    assert client.post(f"{TPL}/{tid}/clone", json={"name": "taken"}).status_code == 409


def test_compare_reports_added_removed_and_changed_fields(client):
    tid = _create(client)["template"]["id"]
    client.post(f"{TPL}/{tid}/versions", json={"configuration": _config(
        mission="Changed mission.", timeout_seconds=90,
        allowed_capabilities=["research.read", "analysis.read"])})
    diff = client.get(f"{TPL}/{tid}/compare?left=1&right=2").json()["data"]
    assert diff["identical"] is False
    assert diff["changed"]["mission"] == {
        "from": "Find and screen opportunities in the owner's category.",
        "to": "Changed mission."}
    assert diff["changed"]["timeout_seconds"] == {"from": 120, "to": 90}
    assert diff["changed"]["allowed_capabilities"]["to"] == ["research.read", "analysis.read"]
    assert diff["added"] == [] and diff["removed"] == []
    assert diff["left_validation_status"] == "unvalidated"


def test_comparing_a_version_with_itself_reports_identical(client):
    tid = _create(client)["template"]["id"]
    diff = client.get(f"{TPL}/{tid}/compare?left=1&right=1").json()["data"]
    assert diff["identical"] is True
    assert diff == {**diff, "added": [], "removed": [], "changed": {}}


def test_compare_requires_both_version_numbers(client):
    tid = _create(client)["template"]["id"]
    assert client.get(f"{TPL}/{tid}/compare?left=1").status_code == 422
    assert client.get(f"{TPL}/{tid}/compare?left=1&right=99").status_code == 404


def test_diff_configurations_is_deterministic_and_key_order_insensitive():
    left = {"a": 1, "b": {"x": 1, "y": 2}, "c": [1, 2]}
    right = {"c": [1, 2], "b": {"y": 2, "x": 1}, "a": 1, "d": True}
    first = diff_configurations(left, right)
    second = diff_configurations(left, right)
    assert first == second
    assert first["added"] == ["d"] and first["removed"] == []
    assert first["changed"] == {}, "nested equality is compared as a whole"
    assert first["identical"] is False


def test_the_template_status_graph_is_closed():
    assert TEMPLATE_TRANSITIONS == {
        "draft": frozenset({"published", "deprecated"}),
        "published": frozenset({"deprecated"}),
        "deprecated": frozenset({"draft"}),
    }
    for targets in TEMPLATE_TRANSITIONS.values():
        for target in targets:
            assert target in TEMPLATE_TRANSITIONS


# --------------------------------------------------------------------------- #
# Auditability and authority
# --------------------------------------------------------------------------- #
def test_template_state_changes_are_published_as_events(client):
    tid = _create(client)["template"]["id"]
    assert _wait_for_event(client, "AgentTemplateCreated", tid)["payload"]["version"] == 1
    _publish(client, tid)
    validated = _wait_for_event(client, "AgentTemplateValidated", tid)
    assert validated["payload"]["validation_status"] == "valid"
    published = _wait_for_event(client, "AgentTemplatePublished", tid)
    assert published["payload"]["fingerprint"], "the event names the document published"
    client.post(f"{TPL}/{tid}/deprecate", json={"reason": "end of life"})
    assert _wait_for_event(client, "AgentTemplateDeprecated", tid)["payload"]["reason"] == "end of life"
    client.post(f"{TPL}/{tid}/restore")
    assert _wait_for_event(client, "AgentTemplateRestored", tid)


def test_a_refused_publication_is_also_visible(client):
    tid = _create(client, expected_output_schema={})["template"]["id"]
    client.post(f"{TPL}/{tid}/validate", json={})
    event = _wait_for_event(client, "AgentTemplateValidated", tid)
    assert event["payload"]["validation_status"] == "invalid"
    assert event["payload"]["issue_count"] >= 1


@pytest.mark.parametrize("method,path,payload", [
    ("get", TPL, None),
    ("post", TPL, {"name": "x", "category": "y", "configuration": {}}),
    ("get", f"{TPL}/some-id", None),
    ("get", f"{TPL}/some-id/versions", None),
    ("post", f"{TPL}/some-id/validate", {}),
    ("post", f"{TPL}/some-id/publish", {}),
    ("post", f"{TPL}/some-id/deprecate", {"reason": "r"}),
    ("post", f"{TPL}/some-id/restore", None),
    ("post", f"{TPL}/some-id/clone", {"name": "c"}),
    ("get", f"{TPL}/some-id/compare?left=1&right=2", None),
])
def test_a_principal_without_agent_permissions_is_refused(client, settings, method, path, payload):
    """The application can never define or publish the templates that govern its
    own agents: both codes are absent from SYSTEM_PERMISSIONS."""
    token = _agent_token(settings)
    resp = client.request(method, path, json=payload,
                          headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}: {resp.text[:200]}"


def test_the_subsystem_reports_what_is_not_built_yet(client, settings):
    """A status that claimed a creation engine exists would be a false claim."""
    from app.agents.subsystem import build_agents

    services = build_agents(settings, Database(settings), None)
    status = services.status()
    assert status["templates"] is True
    assert status["factory"] is False
    assert status["capabilities"] is False
    assert any("Stage 4" in n for n in status["notes"])


def test_the_subsystem_status_endpoint_reports_what_is_not_built(client):
    """Declared before /{agent_id}, so the literal path is not captured as an id."""
    resp = client.get("/api/v1/agents/status")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["enabled"] is True
    assert data["templates"] is True
    assert data["factory"] is False
    assert data["capabilities"] is False
    assert data["assignments"] is False
    assert data["resources"] is False
    assert data["monitoring"] is False
    assert any("Stage 4" in n for n in data["notes"])


def test_the_registry_payload_carries_the_stage_2_columns(client):
    resp = client.get("/api/v1/agents")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == [], "no agent can be created before Stage 4"

    from app.api.schemas.common import AgentView

    fields = set(AgentView.model_fields)
    assert {"template_id", "template_version", "configuration_version",
            "parent_agent_id", "business_id", "retired_at"} <= fields
    for name in ("template_id", "template_version", "configuration_version",
                 "parent_agent_id", "business_id", "retired_at"):
        assert AgentView.model_fields[name].default is None, name
