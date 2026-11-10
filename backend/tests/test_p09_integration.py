"""P-09 integration tests (§25.2): migration cycle, application
wiring, HTTP surface, P-04 reconciliation, P-07 financial references
against REAL P-07 records, P-08 decision/experiment integration,
deletion synchronisation and degraded operation over HTTP."""
from __future__ import annotations

from pathlib import Path

from tests.conftest import OWNER
from tests.p08_support import EXPERIMENT, operational_business, verified_sale
from tests.p09_support import app_mem, client_mem, owner_http_headers

MEMORY_TABLES = {
    "memory_records", "memory_versions", "memory_entities",
    "memory_relationships", "memory_embeddings", "memory_ingestion_jobs",
    "memory_contradictions", "memory_retrieval_logs", "learning_records",
    "agent_handoffs", "memory_consolidations", "owner_memory_preferences",
    "memory_review_tasks", "memory_deletion_receipts", "memory_exports",
}


def _alembic_config(url: str):
    from alembic.config import Config
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location",
                           str(backend / "app" / "database" / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _table_names(url: str) -> set[str]:
    from sqlalchemy import create_engine, inspect
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_p09_migration_cycle(tmp_path):
    """P-08 head (108 tables) -> P-09 head (123) -> downgrade (108) ->
    re-upgrade (123): one additive migration, exact and reversible."""
    from alembic import command
    url = f"sqlite:///{tmp_path}/p09_cycle.db"
    config = _alembic_config(url)
    command.upgrade(config, "99902c03a197")
    before = _table_names(url)
    assert len(before) == 108
    assert not (MEMORY_TABLES & before)
    # P-10 disclosure: "head" has since advanced to the additive P-10
    # migration (e37d00443d20 revises 7b13db7e9bfa), so this cycle now
    # targets the P-09 head explicitly — the exact table-count and
    # downgrade assertions below are unchanged in kind.
    command.upgrade(config, "7b13db7e9bfa")
    after = _table_names(url)
    assert len(after) == 123
    assert MEMORY_TABLES <= after
    command.downgrade(config, "99902c03a197")
    assert _table_names(url) == before
    command.upgrade(config, "7b13db7e9bfa")
    assert _table_names(url) == after


async def test_memory_tables_and_facade_on_startup(app_mem):
    from sqlalchemy import inspect
    tables = set(inspect(app_mem.engine).get_table_names())
    assert MEMORY_TABLES <= tables
    assert app_mem.memory is not None
    status = app_mem.memory.status()
    assert status["authority_boundary"].startswith("memory is data")
    assert "reference only" in status["financial_source"]


async def test_p04_reconciliation_capability_and_interface(app_mem):
    caps = {c.name: c for c in app_mem.agents.capabilities.list_catalogue()}
    assert caps["memory_write"].supported is True
    # Creation evaluation no longer rejects memory_write as unbacked.
    result = await app_mem.agents.evaluate_creation(
        {"role": "research_agent", "capabilities": ["memory_write"]},
        principal=OWNER)
    assert not any("not" in r and "backed" in r
                   for r in result["decision_reasons"])
    from tests.p09_support import AGENT
    from tests.p09_support import register_agent
    register_agent(app_mem, "agent-1")
    for scope in ("approved_contextual_memory", "business_context",
                  "approved_lessons_or_evaluations"):
        out = app_mem.agents.memory.read(
            requester=AGENT, agent_id="agent-1", scope=scope)
        assert out["status"] == "ok", scope


# ------------------------------------------------------------ HTTP surface
def test_http_record_lifecycle(client_mem):
    headers = owner_http_headers(client_mem)
    created = client_mem.post("/api/v1/memory", headers=headers, json={
        "title": "HTTP memory", "content": "Created through the HTTP API",
        "truth_class": "user_provided", "source_type": "user_input",
        "access_scope": "ORGANIZATION_SHARED"})
    assert created.status_code == 200, created.text
    record = created.json()["data"]
    got = client_mem.get(f"/api/v1/memory/{record['id']}", headers=headers)
    assert got.status_code == 200
    found = client_mem.post("/api/v1/memory/search", headers=headers,
                            json={"query": "HTTP API"})
    assert found.status_code == 200
    assert any(r["id"] == record["id"] for r in found.json()["data"]["results"])
    deleted = client_mem.delete(f"/api/v1/memory/{record['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["data"]["index_sync_verified"] is True


def test_http_ingest_and_learning_flow(client_mem):
    headers = owner_http_headers(client_mem)
    ingested = client_mem.post("/api/v1/memory/ingest", headers=headers, json={
        "title": "Supplier finding",
        "content": "Supplier reliability finding from the review meeting",
        "source_type": "user_input", "source_ref": "meeting-3"})
    assert ingested.status_code == 200, ingested.text
    assert ingested.json()["data"]["status"] == "STORED"
    learned = client_mem.post("/api/v1/memory/learning/analyze",
                              headers=headers, json={
        "lesson": "Weekly reviews catch supplier issues early",
        "expected_outcome": "no surprises", "actual_outcome": "issue caught",
        "source_type": "task", "source_ref": "task-7"})
    assert learned.status_code == 200, learned.text
    assert learned.json()["data"]["confidence"] == "LOW"
    status = client_mem.get("/api/v1/memory/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["data"]["learning_records"] == 1


def test_http_requires_auth(client_mem):
    resp = client_mem.get("/api/v1/memory/status")
    assert resp.status_code in (401, 403)


# ------------------------------------------- P-07 / P-08 real integrations
async def test_financial_reference_resolves_real_p07_record(app_mem):
    business_id, _profile = await operational_business(app_mem)
    sale = verified_sale(app_mem, business_id, "10.00", customer="cust-1")
    # verified_sale returns a (record, posting) pair or a record dict.
    ref_id = sale["id"] if isinstance(sale, dict) else sale[0]["id"]
    resolved = app_mem.memory.learning.financial_reference(OWNER, ref_id)
    assert resolved["found"] is True
    assert resolved["source"].startswith("p07.")
    bogus = app_mem.memory.learning.financial_reference(OWNER, "no-such-id")
    assert bogus["found"] is False


async def test_learning_from_real_p08_decision(app_mem):
    business_id, _ = await operational_business(app_mem)
    decision = app_mem.survival.decisions.create_decision(
        OWNER, business_id, {
            "decision_type": "INVESTIGATE",
            "trigger": "health gate raised",
            "evidence": [{"source": "p08.health", "id": "fixture"}]})
    record = app_mem.memory.learning.from_decision(OWNER, decision["id"], {
        "expected_outcome": "Root cause identified within one review cycle",
        "actual_outcome": "Investigation found a pricing error; fixed",
        "lesson": "Health-gate investigations surface pricing errors early",
        "evidence_refs": [f"p08:decision:{decision['id']}"]})
    assert record["source_type"] == "decision"
    assert record["source_ref"] == decision["id"]
    assert record["business_id"] == business_id


async def test_graph_traversal_integration(app_mem):
    svc = app_mem.memory
    business = svc.knowledge.upsert_entity(OWNER, {
        "entity_type": "business", "entity_ref": "biz-1", "name": "Biz One"})
    experiment = svc.knowledge.upsert_entity(OWNER, {
        "entity_type": "experiment", "entity_ref": "exp-1", "name": "Exp One"})
    decision = svc.knowledge.upsert_entity(OWNER, {
        "entity_type": "decision", "entity_ref": "dec-1", "name": "Dec One"})
    svc.knowledge.relate(OWNER, {"from_entity_id": business["id"],
                                 "to_entity_id": experiment["id"],
                                 "relation": "ran_experiment"})
    svc.knowledge.relate(OWNER, {"from_entity_id": experiment["id"],
                                 "to_entity_id": decision["id"],
                                 "relation": "approved_by"})
    graph = svc.knowledge.traverse(business["id"], depth=2)
    refs = {e["entity_ref"] for e in graph["entities"]}
    assert {"exp-1", "dec-1"} <= refs
    assert len(graph["edges"]) == 2
