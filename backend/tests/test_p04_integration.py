"""P-04 integration tests: migration chain, creation pipeline over HTTP,
assignment through the real P-01 task engine, P-02 shared router, P-03
opportunity linkage, audit generation, emergency stop, idempotency."""
from __future__ import annotations

import pytest

from tests.conftest import OWNER, wait_for_status

NEW_TABLES = {
    "agent_templates", "agent_template_versions", "agent_capabilities",
    "agent_permissions", "agent_creation_requests", "agent_assignments",
    "agent_health", "agent_metrics", "agent_configuration_history",
}


def _create_agent(client, headers, role="research_agent", **extra):
    body = {"role": role, **extra}
    resp = client.post("/api/v1/agent-factory/create", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------- migration
def test_p04_migration_cycle_and_legacy_row_preserved(tmp_path):
    """Full Alembic cycle on a scratch DB: P-03 head -> insert a legacy
    P-01-style agent row -> P-04 head (row preserved, new tables/columns)
    -> downgrade (exact P-03 schema, row intact) -> re-upgrade."""
    import sqlite3
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[1]
    db = tmp_path / "cycle.db"
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location",
                        str(backend / "app" / "database" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")

    command.upgrade(cfg, "a8ddb3e7260d")
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO agents (id, name, role, status, created_at, updated_at) "
        "VALUES ('legacy-1', 'Legacy Agent', 'research', 'created', "
        "'2026-11-08T00:00:00', '2026-11-08T00:00:00')")
    con.commit()
    con.close()

    command.upgrade(cfg, "head")
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert NEW_TABLES <= tables
    cols = {r[1] for r in con.execute("PRAGMA table_info(agents)")}
    assert {"agent_type", "template_id", "template_version",
            "configuration_version", "retired_at"} <= cols
    row = con.execute(
        "SELECT name, status, configuration_version FROM agents "
        "WHERE id='legacy-1'").fetchone()
    assert row == ("Legacy Agent", "created", 1)
    # P-05 disclosure: this upgrade targets "head", which has since
    # advanced to the additive P-05 migration (6ffcc7e899fa revises
    # a694abea811f). The pinned version below is updated to the new head;
    # the P-04 table/column/legacy-row assertions above are unchanged and
    # exact-head strictness is preserved.
    # P-06 disclosure: head advanced again by the additive P-06 migration
    # (a8d7e0c717b4 revises 6ffcc7e899fa); same update, same strictness.
    # P-07 disclosure: head advanced again by the additive P-07
    # migration (c3b5cdba2559 revises a8d7e0c717b4); same update,
    # same strictness.
    # P-08 disclosure: head advanced again by the additive P-08 migration (99902c03a197 revises c3b5cdba2559); same update, same strictness.
    # P-09 disclosure: head advanced again by the additive P-09 migration (7b13db7e9bfa revises 99902c03a197); same update, same strictness.
    # P-10 disclosure: head advanced again by the additive P-10 migration (e37d00443d20 revises 7b13db7e9bfa); same update, same strictness.
    # P-11 disclosure: head advanced again by the additive P-11 migration (193731df4c37 revises e37d00443d20); same update, same strictness.
    # P-12 disclosure: head advanced again by the additive P-12 migration (3a77efe78faa revises 193731df4c37); same update, same strictness.
    # P-13 disclosure: head advanced again by the additive P-13 migration (d02b4208d228 revises 3a77efe78faa); same update, same strictness.
    # P-14 disclosure: head advanced again by the additive P-14 Stage B migration (4d41d6a6a605 revises d02b4208d228); same update, same strictness.
    # P-16 disclosure: head advanced again by the additive P-16 migration (ccd744b29e54 revises d12e4d6cf5ef); same update, same strictness.
        # P-17 disclosure: head advanced again by the additive P-17 migration (afe062122eb5 revises ccd744b29e54); same update, same strictness.
        # P-18 disclosure: head advanced again by the additive P-18 migration (218ddd92a0aa revises afe062122eb5); same update, same strictness.
    # Expansion F01 disclosure: head advanced again by the
    # additive Expansion Feature 1 migration (85b7a9805207
    # revises 218ddd92a0aa); same update, same strictness.
    # Expansion F02 disclosure: head advanced again by the additive
    # Expansion Feature 2 migration (3f7a1c9e52b4 revises
    # 85b7a9805207); same update, same strictness.
    # Expansion F03 disclosure: head/count advanced by the additive Expansion Feature 3 migration (c41f7a9d03e6 revises 3f7a1c9e52b4; +4 voice tables); same update, same strictness.
    # Expansion F06 disclosure: head/count advanced by the additive Expansion Feature 6 migration (af39baad9c40 revises c41f7a9d03e6; +3 knowledge tables); same update, same strictness.
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] \
        == "af39baad9c40"
    con.close()

    command.downgrade(cfg, "a8ddb3e7260d")
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert not (NEW_TABLES & tables)
    assert con.execute("SELECT name FROM agents WHERE id='legacy-1'").fetchone() \
        == ("Legacy Agent",)
    con.close()

    command.upgrade(cfg, "head")
    con = sqlite3.connect(db)
    # Head is now the additive P-06 migration (see disclosure above).
    # P-07 disclosure: head advanced again by the additive P-07
    # migration (c3b5cdba2559 revises a8d7e0c717b4); same update,
    # same strictness.
    # P-08 disclosure: head advanced again by the additive P-08 migration (99902c03a197 revises c3b5cdba2559); same update, same strictness.
    # P-09 disclosure: head advanced again by the additive P-09 migration (7b13db7e9bfa revises 99902c03a197); same update, same strictness.
    # P-10 disclosure: head advanced again by the additive P-10 migration (e37d00443d20 revises 7b13db7e9bfa); same update, same strictness.
    # P-11 disclosure: head advanced again by the additive P-11 migration (193731df4c37 revises e37d00443d20); same update, same strictness.
    # P-12 disclosure: head advanced again by the additive P-12 migration (3a77efe78faa revises 193731df4c37); same update, same strictness.
    # P-13 disclosure: head advanced again by the additive P-13 migration (d02b4208d228 revises 3a77efe78faa); same update, same strictness.
    # P-14 disclosure: head advanced again by the additive P-14 Stage B migration (4d41d6a6a605 revises d02b4208d228); same update, same strictness.
    # P-16 disclosure: head advanced again by the additive P-16 migration (ccd744b29e54 revises d12e4d6cf5ef); same update, same strictness.
        # P-17 disclosure: head advanced again by the additive P-17 migration (afe062122eb5 revises ccd744b29e54); same update, same strictness.
        # P-18 disclosure: head advanced again by the additive P-18 migration (218ddd92a0aa revises afe062122eb5); same update, same strictness.
    # Expansion F01 disclosure: head advanced again by the
    # additive Expansion Feature 1 migration (85b7a9805207
    # revises 218ddd92a0aa); same update, same strictness.
    # Expansion F02 disclosure: head advanced again by the additive
    # Expansion Feature 2 migration (3f7a1c9e52b4 revises
    # 85b7a9805207); same update, same strictness.
    # Expansion F03 disclosure: head/count advanced by the additive Expansion Feature 3 migration (c41f7a9d03e6 revises 3f7a1c9e52b4; +4 voice tables); same update, same strictness.
    # Expansion F06 disclosure: head/count advanced by the additive Expansion Feature 6 migration (af39baad9c40 revises c41f7a9d03e6; +3 knowledge tables); same update, same strictness.
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] \
        == "af39baad9c40"
    con.close()


async def test_p04_tables_present_on_create_all(application):
    from sqlalchemy import inspect
    tables = set(inspect(application.engine).get_table_names())
    assert NEW_TABLES <= tables


# ------------------------------------------------------- Scenario A (create)
def test_scenario_a_create_research_agent_via_api(client, auth_headers):
    data = _create_agent(client, auth_headers)
    assert data["decision"] == "CREATE_AGENT"
    assert data["created_agent_id"]
    agent_id = data["created_agent_id"]

    resp = client.get(f"/api/v1/agents/{agent_id}", headers=auth_headers)
    assert resp.status_code == 200
    agent = resp.json()["data"]
    assert agent["status"] == "active"
    assert agent["role"] == "research_agent"
    assert agent["template_id"] and agent["template_version"] == 1
    assert agent["configuration_version"] == 1

    resp = client.get(f"/api/v1/agents/{agent_id}/permissions",
                      headers=auth_headers)
    effective = resp.json()["data"]["effective_capabilities"]
    assert "internal_reasoning" in effective
    assert "internal_database_read" in effective


# --------------------------------------------------------- Scenario B (reuse)
def test_scenario_b_reuse_existing_agent(client, auth_headers):
    first = _create_agent(client, auth_headers)
    status_before = client.get("/api/v1/agent-factory/status",
                               headers=auth_headers).json()["data"]
    second = _create_agent(client, auth_headers)
    assert second["decision"] == "REUSE_EXISTING_AGENT"
    assert second["reused_agent_id"] == first["created_agent_id"]
    assert second["created_agent_id"] is None
    status_after = client.get("/api/v1/agent-factory/status",
                              headers=auth_headers).json()["data"]
    assert status_after["total_agents"] == status_before["total_agents"]

    with_task = _create_agent(client, auth_headers,
                              task={"handler_name": "core.noop"})
    assert with_task["decision"] == "ASSIGN_TO_EXISTING_AGENT"


# -------------------------------------------------------------- assignments
async def test_assignment_completes_through_task_engine(application):
    factory = application.agents
    created = await factory.create_agent({"role": "research_agent"}, principal=OWNER)
    agent_id = created["created_agent_id"]
    assignment = await factory.assign(
        agent_id,
        {"objective": "echo a marker", "handler_name": "core.echo_check",
         "task_payload": {"message": "hello-factory"},
         "expected_output": {"required_fields": ["echo"]}},
        principal=OWNER)
    assert assignment["status"] == "assigned"
    await wait_for_status(application.tasks, assignment["task_id"],
                          {"completed", "failed"}, timeout=10)
    refreshed = factory.refresh_assignment(assignment["id"])
    assert refreshed["status"] == "completed"
    assert refreshed["output_validation"]["valid"] is True
    agent = factory.get_agent(agent_id)
    assert agent.status == "active"  # busy -> active after completion
    metrics = factory.agent_metrics(agent_id)
    assert metrics["aggregates"]["tasks_completed"]["value"] == 1
    assert metrics["aggregates"]["tasks_completed"]["measurement_type"] == "measured"
    assert metrics["aggregates"]["accuracy_percent"]["measurement_type"] == "unavailable"


async def test_assignment_output_contract_violation_is_not_success(application):
    factory = application.agents
    created = await factory.create_agent({"role": "quality_assurance_agent"},
                                         principal=OWNER)
    agent_id = created["created_agent_id"]
    assignment = await factory.assign(
        agent_id,
        {"objective": "produce an impossible field", "handler_name": "core.noop",
         "task_payload": {},
         "expected_output": {"required_fields": ["nonexistent_field"]}},
        principal=OWNER)
    await wait_for_status(application.tasks, assignment["task_id"],
                          {"completed", "failed"}, timeout=10)
    refreshed = factory.refresh_assignment(assignment["id"])
    assert refreshed["status"] == "output_invalid"
    assert refreshed["output_validation"]["valid"] is False
    assert "nonexistent_field" in refreshed["output_validation"]["missing_fields"]


async def test_assignment_rejected_for_handler_outside_responsibility(application):
    factory = application.agents
    created = await factory.create_agent({"role": "content_writing_agent"},
                                         principal=OWNER)
    agent_id = created["created_agent_id"]
    with pytest.raises(Exception) as excinfo:
        await factory.assign(
            agent_id,
            {"objective": "run research", "handler_name": "opportunity.research",
             "task_payload": {"session_id": "x"}},
            principal=OWNER)
    details = getattr(excinfo.value, "details", {})
    assert details.get("error_category") == "ASSIGNMENT_REJECTED"
    assert any(f["rule"] == "responsibility" for f in details["failures"])
    rows, _ = factory.list_assignments(agent_id)
    assert any(r["status"] == "rejected" for r in rows)


async def test_delegation_depth_and_circular_delegation_rejected(application):
    factory = application.agents
    a = await factory.create_agent({"role": "research_agent"}, principal=OWNER)
    b = await factory.create_agent({"role": "market_analysis_agent"}, principal=OWNER)
    a_id, b_id = a["created_agent_id"], b["created_agent_id"]

    root = await factory.assign(
        a_id, {"objective": "root task", "handler_name": "core.wait",
               "task_payload": {"milliseconds": 1500}, "timeout_seconds": 10},
        principal=OWNER)
    child = await factory.assign(
        b_id, {"objective": "child task", "handler_name": "core.noop",
               "task_payload": {}, "parent_assignment_id": root["id"]},
        principal=OWNER)
    assert child["delegation_depth"] == 1
    # Circular: A delegates under its own descendant chain.
    with pytest.raises(Exception) as excinfo:
        await factory.assign(
            a_id, {"objective": "loop back", "handler_name": "core.noop",
                   "task_payload": {}, "parent_assignment_id": child["id"]},
            principal=OWNER)
    assert any(f["rule"] == "delegation_circular"
               for f in excinfo.value.details["failures"])
    # Depth: settings default max depth 3 — build a chain to the cap.
    current = child
    roles = ["competitor_analysis_agent", "documentation_agent"]
    for role in roles:
        nxt = await factory.create_agent({"role": role}, principal=OWNER)
        current = await factory.assign(
            nxt["created_agent_id"],
            {"objective": f"depth {current['delegation_depth'] + 1}",
             "handler_name": "core.noop", "task_payload": {},
             "parent_assignment_id": current["id"]},
            principal=OWNER)
    assert current["delegation_depth"] == 3
    # The next level exceeds the depth cap regardless of agent.
    c = await factory.create_agent({"role": "quality_assurance_agent"},
                                   principal=OWNER)
    with pytest.raises(Exception) as excinfo:
        await factory.assign(
            c["created_agent_id"],
            {"objective": "too deep", "handler_name": "core.noop",
             "task_payload": {}, "parent_assignment_id": current["id"]},
            principal=OWNER)
    assert any(f["rule"] == "delegation_depth"
               for f in excinfo.value.details["failures"])


# ------------------------------------------------- P-02 shared router (J infra)
async def test_shared_router_inference_uses_single_router(application):
    factory = application.agents
    created = await factory.create_agent({"role": "research_agent"}, principal=OWNER)
    agent_id = created["created_agent_id"]
    out = await factory.run_inference(agent_id, "general", principal=OWNER)
    assert out["shared_infrastructure"] is True
    assert out["router_bindings"] == 1
    # No model profiles are configured in this build: the shared router
    # deterministically falls back to the baseline path, with reasons.
    assert out["kind"] == "baseline"
    assert out["reasons"]
    assert factory.resources._router is application.intelligence._router


# ------------------------------------------------------------- P-03 linkage
def test_p03_opportunity_linked_assignment(client, auth_headers):
    brief = client.post("/api/v1/opportunities/briefs", headers=auth_headers, json={
        "title": "Find a $50 digital business", "objective": "legit, low cost",
        "budget_amount": 50, "currency": "USD", "geography": "global",
        "categories": ["software_services"], "constraints": {}})
    assert brief.status_code == 201, brief.text
    brief_id = brief.json()["data"]["id"]
    disc = client.post("/api/v1/opportunities/discover", headers=auth_headers,
                       json={"brief_id": brief_id})
    assert disc.status_code == 201, disc.text
    opps = client.get("/api/v1/opportunities", headers=auth_headers).json()["data"]
    assert opps, "seed discovery should produce opportunities"
    opportunity_id = opps[0]["id"]

    created = _create_agent(client, auth_headers)
    agent_id = created["created_agent_id"]
    resp = client.post(f"/api/v1/agents/{agent_id}/assign", headers=auth_headers,
                       json={"objective": f"research opportunity {opportunity_id}",
                             "handler_name": "core.echo_check",
                             "task_payload": {"message": opportunity_id},
                             "business_ref": opportunity_id,
                             "expected_output": {"required_fields": ["echo"]}})
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["business_ref"] == opportunity_id


# ------------------------------------------------------------ emergency stop
def test_scenario_h_emergency_stop_via_api(client, auth_headers):
    created = _create_agent(client, auth_headers)
    agent_id = created["created_agent_id"]
    resp = client.post("/api/v1/agent-factory/emergency-stop",
                       headers=auth_headers, json={"scope": "all",
                                                   "reason": "test stop"})
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert agent_id in body["agents_suspended"]
    assert body["safe_mode"] is True

    # Creation and assignment are now stopped, deterministically.
    queued = _create_agent(client, auth_headers, role="market_analysis_agent")
    assert queued["decision"] == "QUEUE_FOR_LATER"
    assign = client.post(f"/api/v1/agents/{agent_id}/assign",
                         headers=auth_headers,
                         json={"objective": "x", "handler_name": "core.noop"})
    assert assign.status_code == 409

    resp = client.post("/api/v1/agent-factory/resume-operations",
                       headers=auth_headers, json={})
    assert resp.status_code == 200
    status = client.get("/api/v1/agent-factory/status",
                        headers=auth_headers).json()["data"]
    assert status["safe_mode"] is False and status["creation_enabled"] is True
    # The suspended agent was NOT auto-resumed by lifting the stop.
    agent = client.get(f"/api/v1/agents/{agent_id}",
                       headers=auth_headers).json()["data"]
    assert agent["status"] == "suspended"


# --------------------------------------------------------------- audit trail
def test_audit_trail_and_agent_events(client, auth_headers):
    created = _create_agent(client, auth_headers)
    agent_id = created["created_agent_id"]
    events = client.get(f"/api/v1/agents/{agent_id}/events",
                        headers=auth_headers).json()["data"]
    actions = {e["action"] for e in events}
    assert "agent_factory.create" in actions
    assert "agent_factory.lifecycle_transition" in actions


# --------------------------------------------------------------- idempotency
def test_creation_idempotency(client, auth_headers):
    body = {"role": "research_agent", "idempotency_key": "req-001"}
    first = client.post("/api/v1/agent-factory/create", headers=auth_headers,
                        json=body).json()["data"]
    second = client.post("/api/v1/agent-factory/create", headers=auth_headers,
                         json=body).json()["data"]
    assert first["id"] == second["id"]
    assert first["created_agent_id"] == second["created_agent_id"]
    status = client.get("/api/v1/agent-factory/status",
                        headers=auth_headers).json()["data"]
    assert status["total_agents"] == 1


# --------------------------------------------------------- settings endpoint
def test_settings_endpoint_owner_update(client, auth_headers, service_headers):
    resp = client.get("/api/v1/agent-factory/settings", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["values"]["max_total_agents"] == 12
    resp = client.patch("/api/v1/agent-factory/settings",
                        headers=service_headers,
                        json={"updates": {"max_total_agents": 3}})
    assert resp.status_code == 403
    resp = client.patch("/api/v1/agent-factory/settings",
                        headers=auth_headers,
                        json={"updates": {"max_total_agents": 3}})
    assert resp.status_code == 200
    assert resp.json()["data"]["values"]["max_total_agents"] == 3
