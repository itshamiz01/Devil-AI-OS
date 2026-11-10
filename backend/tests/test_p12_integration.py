"""P-12 shake-out tests: the happy path through the whole stack.
These run first during development; the full suites live in
test_p12_unit / test_p12_scenarios / test_p12_security /
test_p12_recovery."""
from __future__ import annotations

import pytest

from tests.p12_support import (  # noqa: F401
    OWNER, app_ops, client_ops, echo_step, grant_capability,
    make_workflow, register_agent,
)


async def test_happy_path_single_step(app_ops):
    ops = app_ops.operations
    view = make_workflow(app_ops)
    assert view["status"] in ("READY", "SCHEDULED")
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "COMPLETED", result
    assert result["verified_outcome"] == "verified"
    detail = ops.get_workflow(OWNER, view["id"])
    task = detail["tasks"][0]
    assert task["status"] == "COMPLETED"
    assert task["verification_status"] == "verified"
    assert task["substrate_ref"]  # a real P-01 task id
    # P-01 substrate evidence: the task exists and completed.
    substrate = app_ops.tasks.get(task["substrate_ref"])
    assert substrate.status == "completed"
    # Checkpoint written; learning recorded into P-09.
    assert result["learning_record_id"]
    history = ops.workflow_history(OWNER, view["id"])
    assert history["executions"]
    kinds = {e["event_type"] for e in history["events"]}
    assert "workflow.completed" in kinds


async def test_template_workflow_end_to_end(app_ops):
    ops = app_ops.operations
    created = ops.create_workflow(OWNER, {
        "name": "Monitoring", "template": "monitoring_report",
        "objective": "daily monitoring", "autonomy_level": 2})
    view = ops.validate_workflow(OWNER, created["id"])
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "COMPLETED", result
    detail = ops.get_workflow(OWNER, view["id"])
    assert sorted(t["step_key"] for t in detail["tasks"]) == [
        "collect", "report", "summarise"]
    assert all(t["verification_status"] == "verified"
               for t in detail["tasks"])
    # compose_report produced a real operations report.
    reports = ops.list_reports(OWNER)
    assert reports["total"] >= 1


# ----------------------------------------------------------------------
# HTTP surface (real routes, real auth)
# ----------------------------------------------------------------------

def test_operations_api_end_to_end(client_ops):
    """The §19 backend contract over HTTP: create → validate → start
    a workflow; read the overview, safety and recovery views; the
    settings write is owner-gated."""
    from tests.p12_support import owner_http_headers
    headers = owner_http_headers(client_ops)
    base = "/api/v1/operations"

    created = client_ops.post(f"{base}/workflows", headers=headers, json={
        "name": "HTTP workflow", "objective": "prove the API",
        "autonomy_level": 2,
        "definition": {"steps": [{
            "step_key": "only", "name": "Only step", "kind": "task_handler",
            "action_class": "business.read",
            "substrate": {"handler": "core.echo_check",
                          "payload": {"message": "via http"}},
            "acceptance_criteria": {"task_status": "completed"}}]}})
    assert created.status_code == 201, created.text
    workflow = created.json()["data"]
    validated = client_ops.post(
        f"{base}/workflows/{workflow['id']}/validate", headers=headers)
    assert validated.status_code == 200
    assert validated.json()["data"]["status"] == "READY"
    started = client_ops.post(
        f"{base}/workflows/{workflow['id']}/start", headers=headers)
    assert started.status_code == 200
    assert started.json()["data"]["status"] == "COMPLETED"

    overview = client_ops.get(f"{base}/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["data"]["workflows"]["COMPLETED"] >= 1
    safety = client_ops.get(f"{base}/safety", headers=headers)
    assert safety.status_code == 200
    assert safety.json()["data"]["security_mode"] == "normal"
    recovery = client_ops.get(f"{base}/recovery", headers=headers)
    assert recovery.status_code == 200
    assert "dead_letter_total" in recovery.json()["data"]
    approvals = client_ops.get(f"{base}/approvals", headers=headers)
    assert approvals.status_code == 200

    # Unauthenticated callers get nothing.
    assert client_ops.get(f"{base}/overview").status_code == 401


def test_operations_settings_write_requires_owner_role(client_ops):
    from tests.p12_support import owner_http_headers
    headers = owner_http_headers(client_ops)
    resp = client_ops.patch("/api/v1/operations/settings", headers=headers,
                          json={"tick_interval_seconds": 15})
    assert resp.status_code == 200
    assert resp.json()["data"]["tick_interval_seconds"] == 15
    bad = client_ops.patch("/api/v1/operations/settings", headers=headers,
                         json={"tick_interval_seconds": 0})
    assert bad.status_code == 422


# ----------------------------------------------------------------------
# Migration cycle (additive from the P-11 head)
# ----------------------------------------------------------------------

def test_p12_migration_cycle(tmp_path):
    """139 (P-11 head) -> 153 (P-12: fourteen operations tables)
    -> downgrade back to 139 -> re-upgrade to 153. Exact and
    reversible; the new tables are exactly the P-12 set."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    backend = Path(__file__).resolve().parents[1]
    url = f"sqlite:///{tmp_path / 'p12_mig.db'}"
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(backend / "app" / "database" / "migrations"))
    config.set_main_option("sqlalchemy.url", url)

    def count() -> int:
        engine = create_engine(url)
        try:
            return len(inspect(engine).get_table_names())
        finally:
            engine.dispose()

    command.upgrade(config, "193731df4c37")
    assert count() == 139
    # P-13 disclosure: this step originally upgraded to "head"
    # (then the P-12 head, 153). It now targets the P-12 head
    # explicitly — P-13's migration chains from it and head is 172.
    # The full head count is asserted in the P-13 cycle test.
    # Strictness preserved (exact counts).
    command.upgrade(config, "3a77efe78faa")
    assert count() == 153
    engine = create_engine(url)
    names = set(inspect(engine).get_table_names())
    engine.dispose()
    expected = {
        "autonomous_workflows", "operations_workflow_versions",
        "operations_workflow_tasks", "operations_workflow_executions",
        "operations_workflow_checkpoints", "operations_workflow_events",
        "operations_triggers", "operations_assignments",
        "operations_approval_links", "operations_recovery_records",
        "operations_dead_letter", "operations_autonomy_policies",
        "operations_decisions", "operations_reports",
    }
    assert expected <= names
    # P-13 disclosure: the cycle now stops at the P-12 head
    # explicitly (153 tables incl. alembic_version) because P-13's
    # migration chains from it; upgrading to head reaches 172 with
    # P-13's 19 tables. Strictness preserved (exact counts both ways).
    command.downgrade(config, "193731df4c37")
    assert count() == 139
    command.upgrade(config, "3a77efe78faa")
    assert count() == 153


def test_p12_metadata_registers_exactly_fourteen_new_tables():
    from app.database.models.base import Base
    import app.database.models  # noqa: F401  (registers all models)

    # P-13 disclosure: 152 was the P-12 total (138 pre-P-12 + 14);
    # P-13 added 19 portfolio tables, so the exact total is now 171.
    # The P-12 increment is unchanged. Strictness preserved.
    # P-14 Stage B disclosure: Stage B added one table
    # (event_dead_letters, DEF-I4); the exact total is now 172.
    # P-15 disclosure: P-15 added four reliability tables; the exact
    # total is now 176. The P-12 increment is unchanged.
    # P-16 disclosure: P-16 added fourteen economy tables; the exact
    # total is now 190. The P-12 increment is unchanged.
    # P-17 disclosure: P-17 added eighteen growth tables; the exact
    # total is now 208. The P-12 increment is unchanged.
    # P-18 disclosure: P-18 added fifteen experience tables; the
    # exact total is now 223. The P-12 increment is unchanged.
    # Expansion F02 disclosure: F02 added two integration-framework
    # tables; the exact total is now 227. The P-12 increment is unchanged.
    # Expansion F06 disclosure: F06 added three knowledge tables;
    # the exact total is now 234. The P-12 increment is unchanged.
    assert len(Base.metadata.tables) == 234  # 223 pre-F01 + 2 F01 + 2 F02 + 4 F03 + 3 F06 tables
