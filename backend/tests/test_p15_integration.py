"""P-15 integration tests: migration cycle, sampling, the incident
register lifecycle, readiness persistence, benchmarks, stability
honesty, the financial read-model and the HTTP surface."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from tests.p15_support import (  # noqa: F401
    AGENT, OWNER, app_rel, client_rel, owner_http_headers,
)
from tests.p06_support import make_fixture_business  # noqa: F401

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------ migration
def test_p15_migration_cycle(tmp_path):
    from alembic import command
    from alembic.config import Config

    db = tmp_path / "p15_cycle.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")

    def count() -> int:
        with engine.connect() as conn:
            return conn.execute(text(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            )).scalar_one()

    command.upgrade(config, "head")
    # P-16 disclosure: head now also includes the P-16 migration
    # (fourteen economy tables): 191 physical tables.
    # P-17 disclosure: head now also includes the P-17 migration
    # (eighteen growth tables): 209 physical tables.
    # P-18 disclosure: head now also includes the P-18 migration
    # (fifteen experience tables): 224 physical tables.
    # Expansion F01 disclosure: head now also includes the Expansion
    # Feature 1 migration (two identity/device tables): 226 physical tables.
    # Expansion F02 disclosure: head now also includes the Expansion
    # Feature 2 migration (two integration-framework tables): 228 physical tables.
    # Expansion F06 disclosure: head now also includes the Expansion
    # Feature 6 migration (three knowledge tables): 235 physical tables.
    assert count() == 235  # 224 at P-18 head + 2 F01 + 2 F02 + 4 F03 + 3 F06 tables
    command.downgrade(config, "4d41d6a6a605")
    assert count() == 173
    command.upgrade(config, "head")
    assert count() == 235


def test_p15_metadata_registers_exactly_four_new_tables():
    from app.database.models.base import Base
    import app.database.models  # noqa: F401

    # P-16 disclosure: P-16 added fourteen economy tables; the
    # exact total is now 190. The P-15 increment (4) is unchanged.
    # P-17 disclosure: P-17 added eighteen growth tables; the exact
    # total is now 208. The P-15 increment (4) is unchanged.
    # P-18 disclosure: P-18 added fifteen experience tables; the
    # exact total is now 223. The P-15 increment (4) is unchanged.
    # Expansion F01 disclosure: F01 added two identity/device tables;
    # the exact total is now 225. The P-15 increment (4) is unchanged.
    # Expansion F02 disclosure: F02 added two integration-framework tables;
    # the exact total is now 227. The P-15 increment (4) is unchanged.
    # Expansion F06 disclosure: F06 added three knowledge tables;
    # the exact total is now 234. The P-15 increment (4) is unchanged.
    assert len(Base.metadata.tables) == 234  # 223 pre-F01 + 2 F01 + 2 F02 + 4 F03 + 3 F06
    expected = {"performance_samples", "reliability_incidents",
                "readiness_snapshots", "benchmark_runs"}
    assert expected <= set(Base.metadata.tables)


# ------------------------------------------------------------ sampling
async def test_record_sample_persists_measured_values(app_rel):
    svc = app_rel.reliability
    sample = svc.record_sample(source="test")
    assert sample["source"] == "test"
    assert sample["cpu_percent"] is not None
    assert sample["database_healthy"] is True
    assert sample["db_latency_ms"] is not None
    listed = svc.list_samples(limit=10)
    assert [s["id"] for s in listed] == [sample["id"]]
    assert listed[0]["metrics"]["lifecycle_state"]


async def test_sampler_settings_seeded_and_owner_updatable(app_rel):
    svc = app_rel.reliability
    settings = svc.get_settings()
    assert settings["sample_interval_seconds"] == 30
    assert settings["long_duration_targets_hours"] == [24, 72, 168]
    updated = svc.update_settings(OWNER, {"backup_max_age_hours": 48})
    assert updated["backup_max_age_hours"] == 48
    with pytest.raises(Exception):
        svc.update_settings(OWNER, {"backup_max_age_hours": 0})


# ------------------------------------------------------------ incidents
async def test_evaluator_opens_backup_incident_once(app_rel):
    svc = app_rel.reliability
    first = svc.evaluate_incidents()
    kinds = {(i["component"], i["kind"]) for i in first["opened"]}
    assert ("backup", "no_backups") in kinds
    second = svc.evaluate_incidents()
    assert all((i["component"], i["kind"]) != ("backup", "no_backups")
               for i in second["opened"]), "detection must deduplicate"


async def test_backup_creation_auto_resolves_backup_incident(app_rel):
    svc = app_rel.reliability
    svc.evaluate_incidents()
    result = svc.create_backup(OWNER)
    assert result["created"]["id"]
    assert result["verification"], "the P-10 verification must be returned"
    evaluation = svc.evaluate_incidents()
    assert "no_backups" not in str(evaluation["opened"])
    summary = svc.incident_summary()
    kinds_resolved = summary["resolved"]
    assert kinds_resolved >= 1, "the no-backups incident must auto-resolve"


async def test_manual_incident_lifecycle(app_rel):
    svc = app_rel.reliability
    created = svc.create_incident(OWNER, {
        "severity": "P2", "component": "queue", "kind": "manual_drill",
        "title": "Drill incident", "detail": "test"})
    assert created["status"] == "open"
    acked = svc.acknowledge_incident(OWNER, created["id"])
    assert acked["status"] == "acknowledged"
    resolved = svc.resolve_incident(OWNER, created["id"], {
        "root_cause": "drill", "response": "acknowledged and closed",
        "recovery_actions": [{"action": "none_required"}],
        "preventive": "n/a"})
    assert resolved["status"] == "resolved"
    assert resolved["root_cause"] == "drill"
    with pytest.raises(Exception):
        svc.resolve_incident(OWNER, created["id"], {})


async def test_incident_validation(app_rel):
    svc = app_rel.reliability
    with pytest.raises(Exception):
        svc.create_incident(OWNER, {"severity": "P9", "component": "x",
                                    "kind": "y", "title": "z"})
    with pytest.raises(Exception):
        svc.resolve_incident(OWNER, "missing-id", {})


# ------------------------------------------------------------ readiness
async def test_readiness_computed_and_persisted(app_rel):
    svc = app_rel.reliability
    svc.record_sample(source="test")
    result = await svc.compute_readiness()
    assert result["id"], "the snapshot must persist"
    assert result["critical_gate_ok"] is True
    assert set(result["categories"]) == {
        "performance", "reliability", "fault_tolerance_recovery",
        "data_integrity_backup", "security_governance", "observability",
        "testing_validation"}
    assert result["classification"].startswith(
        ("READY FOR CONTROLLED PILOT", "Limited", "Controlled",
         "Development", "Unstable", "Production-ready"))
    latest = svc.latest_readiness()
    assert latest["id"] == result["id"]
    assert latest["overall_score"] == result["overall_score"]
    history = svc.readiness_history(limit=5)
    assert len(history) == 1


async def test_readiness_without_benchmarks_is_docked(app_rel):
    svc = app_rel.reliability
    result = await svc.compute_readiness()
    perf = result["categories"]["performance"]
    assert "benchmarks_recorded" in perf["failed_checks"]
    assert result["recommendations"], "failed checks must recommend actions"


# ------------------------------------------------------------ benchmarks
async def test_benchmark_run_completes_with_real_probes(app_rel):
    svc = app_rel.reliability
    run = await svc.run_benchmark(OWNER)
    assert run["status"] == "completed"
    results = run["results"]
    timings = results["timings_ms_median_of_3"]
    for key in ("dashboard_overview", "dashboard_system_health",
                "financial_consolidated", "journal_page_query_50"):
        assert timings[key] > 0, key
    probes = results["recovery_probes"]
    assert probes["circuit_breaker"]["ok"] is True
    assert probes["retry_policy"]["ok"] is True
    assert probes["event_bus_dead_letter"]["ok"] is True
    assert results["load_probe"]["p95_ms"] > 0
    assert results["stress_observed"]["induced"] is False
    listed = svc.list_benchmarks(limit=5)
    assert listed[0]["id"] == run["id"]


# ------------------------------------------------------------ stability
async def test_stability_report_is_honest_about_incomplete_windows(app_rel):
    svc = app_rel.reliability
    svc.record_sample(source="test")
    report = svc.stability_report()
    assert report["total_samples"] == 1
    for window in report["windows"]:
        assert window["status"] == "INCOMPLETE", window
    assert report["stuck_tasks"] == []


# ------------------------------------------------------------ financial
async def test_financial_reliability_read_model(app_rel):
    _opp, business = await make_fixture_business(app_rel)
    svc = app_rel.reliability
    report = svc.financial_reliability()
    assert report["businesses_checked"] >= 1
    assert report["integrity_ok"] is True
    assert "NOT APPLICABLE" in report["trading"]
    assert report["financial_suspended"] is False


# ------------------------------------------------------------ overview
async def test_overview_panels_present(app_rel):
    svc = app_rel.reliability
    overview = await svc.overview()
    for key in ("health", "history", "ai", "agents", "businesses", "queue",
                "reliability", "data_protection", "readiness", "financial",
                "controls", "resources", "stability"):
        assert key in overview, key
    assert overview["controls"]["source"].startswith("P-10")
    assert overview["resources"]["backpressure"] in ("none", "elevated", "high")


# ------------------------------------------------------------ HTTP
def test_http_surface(client_rel):
    headers = owner_http_headers(client_rel)
    resp = client_rel.get("/api/v1/reliability/overview", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "readiness" in data and "stability" in data

    resp = client_rel.post("/api/v1/reliability/samples", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["source"] == "manual"

    resp = client_rel.post("/api/v1/reliability/incidents", headers=headers,
                           json={"severity": "P3", "component": "http",
                                 "kind": "drill", "title": "HTTP drill"})
    assert resp.status_code == 200, resp.text
    incident_id = resp.json()["data"]["id"]
    resp = client_rel.post(
        f"/api/v1/reliability/incidents/{incident_id}/resolve",
        headers=headers, json={"root_cause": "drill", "response": "closed"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "resolved"

    resp = client_rel.get("/api/v1/reliability/readiness", headers=headers)
    assert resp.status_code == 200
    resp = client_rel.get("/api/v1/reliability/stability", headers=headers)
    assert resp.status_code == 200
    assert all(w["status"] == "INCOMPLETE"
               for w in resp.json()["data"]["windows"])
