"""P-02 integration tests: the acceptance scenario end-to-end (baseline
planner AND FakeProvider LLM path), unregistered-tool rejection, garbage /
timeout fallback, and the additive migration on a fresh database."""
from __future__ import annotations

import pytest
from tests.conftest import make_settings
from fastapi.testclient import TestClient

from app.intelligence.providers import FakeProvider
from app.main import create_app

HEALTH_MISSION = "Check system health and report whether the task system is working"
VALID_FAKE_PLAN = {
    "steps": [
        {"name": "snapshot", "tool_name": "core.health_snapshot", "payload": {},
         "expectation": {"kind": "result_fields", "require_ok": True, "fields": {}}},
        {"name": "echo", "tool_name": "core.echo_check",
         "payload": {"message": "fake plan self-test", "data": {}},
         "expectation": {"kind": "result_fields", "require_ok": True,
                         "fields": {"echo.message": "fake plan self-test"}}},
    ],
    "rationale": "fake provider plan",
}


@pytest.fixture()
def pair(tmp_path, request):
    overrides = getattr(request, "param", {}) or {}
    settings = make_settings(tmp_path, mode="supervised", **overrides)
    app = create_app(settings)
    with TestClient(app) as c:
        yield app, c


def login(c) -> dict:
    resp = c.post("/api/v1/auth/login",
                  json={"username": "owner", "password": "test-owner-password-123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def run_acceptance_flow(c, headers, mission_text=HEALTH_MISSION):
    m = c.post("/api/v1/missions", headers=headers, json={"text": mission_text})
    assert m.status_code == 201, m.text
    mission = m.json()["data"]
    p = c.post(f"/api/v1/missions/{mission['id']}/plan", headers=headers)
    assert p.status_code == 201, p.text
    plan = p.json()["data"]
    a = c.post(f"/api/v1/plans/{plan['id']}/approve", headers=headers)
    assert a.status_code == 200, a.text
    e = c.post(f"/api/v1/plans/{plan['id']}/execute", headers=headers)
    assert e.status_code == 200, e.text
    return mission, e.json()["data"]


def enable_fake_profile(app, c, headers, fake, profile="fake-std"):
    app.state.application.intelligence.providers["fake"] = fake
    resp = c.put(f"/api/v1/models/profiles/{profile}", headers=headers, json={
        "task_classes": ["planning"], "provider": "fake",
        "model_id": "fake-1", "enabled": True, "limits": {"size_rank": 1}})
    assert resp.status_code == 200, resp.text


# ------------------------------------------------------- acceptance: baseline
def test_acceptance_scenario_baseline_planner(pair):
    app, c = pair
    headers = login(c)
    mission, plan = run_acceptance_flow(c, headers)
    assert plan["status"] == "completed"
    assert plan["planner"] == "rule-engine"
    assert all(s["status"] == "completed" and s["verification_status"] == "verified"
               for s in plan["steps"])
    assert all(s["task_id"] for s in plan["steps"])  # real P-01 tasks ran

    detail = c.get(f"/api/v1/plans/{plan['id']}", headers=headers).json()["data"]
    types = {d["decision_type"] for d in detail["decision_records"]}
    assert {"router_selection", "plan_created", "plan_approved",
            "step_verified", "plan_completed"} <= types

    exp = c.get(f"/api/v1/plans/{plan['id']}/explanation", headers=headers).json()["data"]
    assert exp["llm_used"] is False
    assert "No LLM was used" in exp["honesty_statement"]
    assert exp["planner"] == "rule-engine"
    assert all(s["verification_status"] == "verified" for s in exp["steps"])
    assert exp["mission_id"] == mission["id"]


# --------------------------------------------------- acceptance: LLM adapter
def test_acceptance_scenario_with_fake_provider(pair):
    app, c = pair
    headers = login(c)
    enable_fake_profile(app, c, headers, FakeProvider(raw_output=VALID_FAKE_PLAN))
    mission, plan = run_acceptance_flow(
        c, headers, mission_text="Assess the current state of the machine room")
    assert plan["status"] == "completed"
    assert plan["planner"] == "llm:fake:fake-1"
    exp = c.get(f"/api/v1/plans/{plan['id']}/explanation", headers=headers).json()["data"]
    assert exp["llm_used"] is True
    assert "llm:fake:fake-1" in exp["honesty_statement"]
    assert "identical validation gate" in exp["honesty_statement"]


def test_fake_provider_unregistered_tool_rejected(pair):
    app, c = pair
    headers = login(c)
    bad = {"steps": [{"tool_name": "os.system", "payload": {"command": "calc"}}]}
    enable_fake_profile(app, c, headers, FakeProvider(raw_output=bad))
    m = c.post("/api/v1/missions", headers=headers,
               json={"text": "Assess the current state of the machine room"})
    mission_id = m.json()["data"]["id"]
    resp = c.post(f"/api/v1/missions/{mission_id}/plan", headers=headers)
    assert resp.status_code == 422, resp.text
    plan_id = resp.json()["error"]["details"]["plan_id"]
    plan = c.get(f"/api/v1/plans/{plan_id}", headers=headers).json()["data"]
    assert plan["status"] == "rejected"
    decisions = c.get(f"/api/v1/decisions?mission_id={mission_id}",
                      headers=headers).json()["data"]
    assert any(d["decision_type"] == "plan_rejected" for d in decisions)
    tasks = c.get("/api/v1/tasks", headers=headers).json()
    assert tasks["meta"]["total"] == 0  # nothing executed


def test_garbage_llm_output_falls_back_to_baseline(pair):
    app, c = pair
    headers = login(c)
    enable_fake_profile(app, c, headers, FakeProvider(raw_output={"nonsense": True}))
    m = c.post("/api/v1/missions", headers=headers, json={"text": HEALTH_MISSION})
    mission_id = m.json()["data"]["id"]
    resp = c.post(f"/api/v1/missions/{mission_id}/plan", headers=headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["planner"] == "rule-engine"
    decisions = c.get(f"/api/v1/decisions?mission_id={mission_id}",
                      headers=headers).json()["data"]
    assert any(d["decision_type"] == "llm_plan_unusable" for d in decisions)


@pytest.mark.parametrize("pair", [{"llm_plan_timeout_seconds": 0.2}], indirect=True)
def test_provider_timeout_falls_back_to_baseline(pair):
    app, c = pair
    headers = login(c)
    enable_fake_profile(app, c, headers,
                        FakeProvider(raw_output=VALID_FAKE_PLAN, delay_seconds=1.0))
    m = c.post("/api/v1/missions", headers=headers, json={"text": HEALTH_MISSION})
    mission_id = m.json()["data"]["id"]
    resp = c.post(f"/api/v1/missions/{mission_id}/plan", headers=headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["planner"] == "rule-engine"
    decisions = c.get(f"/api/v1/decisions?mission_id={mission_id}",
                      headers=headers).json()["data"]
    assert any(d["decision_type"] == "llm_plan_unusable" for d in decisions)


def test_unplannable_mission_fails_honestly(pair):
    app, c = pair
    headers = login(c)
    m = c.post("/api/v1/missions", headers=headers,
               json={"text": "Investigate quarterly market trends for umbrellas"})
    mission_id = m.json()["data"]["id"]
    resp = c.post(f"/api/v1/missions/{mission_id}/plan", headers=headers)
    assert resp.status_code == 422
    mission = c.get(f"/api/v1/missions/{mission_id}", headers=headers).json()["data"]
    assert mission["status"] == "planning_failed"
    decisions = c.get(f"/api/v1/decisions?mission_id={mission_id}",
                      headers=headers).json()["data"]
    assert any(d["decision_type"] == "plan_failed" for d in decisions)


def test_models_status_and_profiles_endpoints(pair):
    app, c = pair
    headers = login(c)
    status = c.get("/api/v1/models/status", headers=headers).json()["data"]
    assert status["providers"]["ollama"]["available"] is False  # no server here
    assert status["providers"]["cloud"]["available"] is False
    assert "not enabled" in status["providers"]["cloud"]["detail"]
    profiles = c.get("/api/v1/models/profiles", headers=headers).json()["data"]
    assert len(profiles) == 4
    assert all(p["model_id"] == "" and p["enabled"] is False for p in profiles)


# -------------------------------------------------------------- migrations
async def test_p02_migration_creates_tables_on_fresh_db(tmp_path):
    from sqlalchemy import inspect

    from app.core.application import Application

    settings = make_settings(tmp_path, auto_migrate=True)
    application = Application(settings)
    await application.startup()
    try:
        from sqlalchemy import text
        engine = application.engine
        tables = set(inspect(engine).get_table_names())
        assert {"missions", "plans", "plan_steps", "decision_records",
                "model_profiles"} <= tables
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        # Head advanced by the additive P-03 migration (a8ddb3e7260d revises
        # c7a21f9e04b3), then by the additive P-04 migration
        # (a694abea811f revises a8ddb3e7260d), then by the additive P-05
        # migration (6ffcc7e899fa revises a694abea811f); the P-02 tables
        # above remain present and untouched. Exact-head strictness
        # P-08 disclosure: head advanced again by the additive P-08 migration (99902c03a197 revises c3b5cdba2559); same update, same strictness.
        # P-09 disclosure: head advanced again by the additive P-09 migration (7b13db7e9bfa revises 99902c03a197); same update, same strictness.
        # preserved. (P-05 disclosure: head updated, assertion unchanged
        # in kind.)
        # P-06 disclosure: head advanced again by the additive P-06
        # migration (a8d7e0c717b4 revises 6ffcc7e899fa); same update.
        # P-07 disclosure: head advanced again by the additive P-07 migration (c3b5cdba2559 revises a8d7e0c717b4); same update, same strictness.
        # P-10 disclosure: head advanced again by the additive P-10 migration (e37d00443d20 revises 7b13db7e9bfa); same update, same strictness.
        # P-11 disclosure: head advanced again by the additive P-11 migration (193731df4c37 revises e37d00443d20); same update, same strictness.
        # P-12 disclosure: head advanced again by the additive P-12 migration (3a77efe78faa revises 193731df4c37); same update, same strictness.
        # P-13 disclosure: head advanced again by the additive P-13 migration (d02b4208d228 revises 3a77efe78faa); same update, same strictness.
        # P-14 disclosure: head advanced again by the additive P-14 Stage B migration (4d41d6a6a605 revises d02b4208d228); same update, same strictness.
        # P-16 disclosure: head advanced again by the additive P-16 migration (ccd744b29e54 revises d12e4d6cf5ef); same update, same strictness.
        # P-17 disclosure: head advanced again by the additive P-17 migration (afe062122eb5 revises ccd744b29e54); same update, same strictness.
        # P-18 disclosure: head advanced again by the additive P-18 migration (218ddd92a0aa revises afe062122eb5); same update, same strictness.
        # Expansion F01 disclosure: head advanced again by the additive
        # Expansion Feature 1 migration (85b7a9805207 revises 218ddd92a0aa);
        # same update, same strictness.
        # Expansion F02 disclosure: head advanced again by the additive
        # Expansion Feature 2 migration (3f7a1c9e52b4 revises 85b7a9805207);
        # same update, same strictness.
        # Expansion F03 disclosure: head/count advanced by the additive Expansion Feature 3 migration (c41f7a9d03e6 revises 3f7a1c9e52b4; +4 voice tables); same update, same strictness.
        # Expansion F06 disclosure: head/count advanced by the additive Expansion Feature 6 migration (af39baad9c40 revises c41f7a9d03e6; +3 knowledge tables); same update, same strictness.
        assert version == "af39baad9c40"
    finally:
        await application.shutdown()
