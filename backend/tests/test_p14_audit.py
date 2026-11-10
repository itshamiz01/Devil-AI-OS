"""P-14 Stage A audit probes — system assembly, health, reliability,
performance measurement.

These tests are ADDITIVE audit evidence for the P-14 master integration
audit. They assert only properties the audit must verify independently
of the per-phase suites: that all thirteen module services assemble on
the P-01 substrate, that the full HTTP surface is registered, that the
schema metadata matches the audited table count, that health endpoints
behave, that a fresh install's dashboard is honest (no fabricated
zeros), that a safe restart preserves state without duplicating seeds,
that backups create + checksum-verify, that critical events persist,
that correlation IDs propagate, and they MEASURE API latency on this
staging VM (recorded to docs/p14/P14_PERF_MEASUREMENTS.json — staging
numbers only, not performance targets).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.application import Application
from app.main import create_app
from tests.conftest import OWNER, make_settings
from tests.p06_support import make_fixture_business

PERF_FILE = (Path(__file__).resolve().parents[2]
             / "docs" / "p14" / "P14_PERF_MEASUREMENTS.json")

MODULE_SERVICES = {
    "P-01 permissions": "permissions", "P-01 approvals": "approvals",
    "P-01 event bus": "bus", "P-01 tasks": "tasks", "P-01 auth": "auth",
    "P-01 monitor": "monitor",
    "P-02 intelligence": "intelligence", "P-03 opportunities": "opportunities",
    "P-04 agents": "agents", "P-05 execution": "execution",
    "P-06 business": "business", "P-07 financial": "financial",
    "P-08 survival": "survival", "P-09 memory": "memory",
    "P-10 security": "security", "P-12 operations": "operations",
    "P-13 portfolio": "portfolio",
}

ROUTE_PREFIXES = {
    "P-01": ("/api/v1/auth", "/api/v1/tasks", "/api/v1/approvals",
             "/api/v1/events", "/api/v1/health", "/api/v1/system"),
    "P-02": ("/api/v1/missions", "/api/v1/plans", "/api/v1/models",
             "/api/v1/decisions"),
    "P-03": ("/api/v1/opportunities", "/api/v1/research", "/api/v1/sources"),
    "P-04": ("/api/v1/agent-factory", "/api/v1/agents",
             "/api/v1/agent-templates", "/api/v1/agent-capabilities"),
    "P-05": ("/api/v1/execution",),
    "P-06": ("/api/v1/business",),
    "P-07": ("/api/v1/financial",),
    "P-08": ("/api/v1/survival",),
    "P-09": ("/api/v1/memory",),
    "P-10": ("/api/v1/security",),
    "P-11": ("/api/v1/dashboard",),
    "P-12": ("/api/v1/operations",),
    "P-13": ("/api/v1/portfolio",),
}


@pytest.mark.asyncio
async def test_p14_all_module_services_assembled(application):
    """§3 check 1/2: every module's service object exists and is wired
    after startup on the real assembly path."""
    for label, attr in MODULE_SERVICES.items():
        assert getattr(application, attr, None) is not None, \
            f"{label}: application.{attr} is None after startup"


def test_p14_full_route_surface_registered(settings):
    """§3 check 3 / §5: the registered HTTP surface covers every
    module's prefix; total route count recorded for the audit."""
    app = create_app(settings)
    # This FastAPI version wraps included routers opaquely in
    # app.routes; the OpenAPI schema is the expanded surface.
    paths = set(app.openapi()["paths"])
    for module, prefixes in ROUTE_PREFIXES.items():
        for prefix in prefixes:
            assert any(p == prefix or p.startswith(prefix + "/")
                       for p in paths), f"{module}: no route under {prefix}"
    api_paths = [p for p in paths if p.startswith("/api/v1/")]
    assert len(api_paths) >= 450, f"only {len(api_paths)} API paths"


def test_p14_schema_metadata_table_count():
    """§4 database: model metadata was the audited 171 tables at
    Stage A (172nd is alembic_version in a migrated database).
    P-14 Stage B disclosure: Stage B added the event_dead_letters
    table (DEF-I4) to the metadata, so the exact total is now 172.
    Strictness preserved (exact count).
    P-15 disclosure: P-15 added four reliability tables
    (performance_samples, reliability_incidents, readiness_snapshots,
    benchmark_runs), so the exact total is now 176. Strictness
    preserved (exact count).
    P-16 disclosure: P-16 added fourteen economy tables, so the
    exact total is now 190. Strictness preserved (exact count).
    P-17 disclosure: P-17 added eighteen growth tables, so the
    exact total is now 208. Strictness preserved (exact count).
    P-18 disclosure: P-18 added fifteen experience tables, so the
    exact total is now 223. Strictness preserved (exact count).
    Expansion F01 disclosure: Expansion Feature 1 added two
    identity/device tables, so the exact total is now 225.
    Expansion F02 disclosure: Expansion Feature 2 added two
    integration-framework tables, so the exact total is now 227.
    Expansion F03 disclosure: Expansion Feature 3 added four
    voice tables, so the exact total is now 231.
    Expansion F06 disclosure: Expansion Feature 6 added three
    knowledge tables, so the exact total is now 234.
    Strictness preserved (exact count)."""
    from app.database.models import Base
    assert len(Base.metadata.tables) == 234, \
        f"metadata has {len(Base.metadata.tables)} tables"


def test_p14_health_endpoints(client, auth_headers):
    """§12: liveness is public and minimal; readiness/health require
    permission and report real lifecycle + database state."""
    live = client.get("/api/v1/health/live")
    assert live.status_code == 200
    ready = client.get("/api/v1/health/ready", headers=auth_headers)
    assert ready.status_code == 200, ready.text
    assert ready.json()["data"]["status"] in ("ready", "degraded")
    assert ready.json()["data"]["database_healthy"] is True
    health = client.get("/api/v1/health", headers=auth_headers)
    assert health.status_code == 200
    assert health.json()["data"]["diagnostics"]["database_healthy"] is True
    unauth = client.get("/api/v1/health/ready")
    assert unauth.status_code in (401, 403)


def test_p14_dashboard_zero_state_is_honest(client, auth_headers):
    """§15 + P-11 honesty lock, independently re-verified on a fresh
    install: zero businesses, and available cash is explicitly
    unavailable — never a fabricated 0."""
    resp = client.get("/api/v1/dashboard/overview", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    text = json.dumps(data)
    assert "available_cash" in text
    metrics = {m["key"]: m for section in data.get("sections", [])
               for m in section.get("metrics", [])} \
        if "sections" in data else {}
    cash = metrics.get("available_cash")
    if cash is not None:
        assert cash["value"] is None and cash["state"] == "unavailable", cash


def test_p14_critical_events_are_persisted(client, auth_headers):
    """§6 reliability: critical events (application start) persist and
    are queryable through the permission-filtered events API."""
    resp = client.get("/api/v1/events", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    types = {e.get("event_type") or e.get("type")
             for e in resp.json()["data"]}
    assert "ApplicationStarted" in types, types


def test_p14_correlation_id_propagates(client):
    """§14 traceability: a caller-supplied correlation ID is echoed,
    and one is generated when absent."""
    resp = client.get("/api/v1/health/live",
                      headers={"x-correlation-id": "p14-audit-probe-1"})
    assert resp.headers.get("x-correlation-id") == "p14-audit-probe-1"
    resp2 = client.get("/api/v1/health/live")
    assert resp2.headers.get("x-correlation-id")


@pytest.mark.asyncio
async def test_p14_safe_restart_preserves_state_without_duplicate_seeds(
        tmp_path):
    """§12 safe restart: state created under one process lifecycle is
    intact under a second lifecycle on the same database, and startup
    seeding is idempotent (no duplicate businesses/currencies)."""
    settings = make_settings(tmp_path, mode="controlled")
    app1 = Application(settings)
    await app1.startup()
    _opp, business = await make_fixture_business(
        app1, name="Restart Probe Business")
    business_id = business["id"]
    session = app1.session_factory()
    try:
        from app.database.models.financial import FinancialAccount
        accounts_before = session.query(FinancialAccount).count()
    finally:
        session.close()
    await app1.shutdown()

    app2 = Application(settings)
    await app2.startup()
    try:
        rows, _total = app2.business.list_businesses()
        ids = [r["id"] for r in rows]
        assert business_id in ids
        assert len(ids) == len(set(ids)), "duplicate business after restart"
        session = app2.session_factory()
        try:
            from app.database.models.financial import FinancialAccount
            assert session.query(FinancialAccount).count() == accounts_before
        finally:
            session.close()
    finally:
        await app2.shutdown()


@pytest.mark.asyncio
async def test_p14_backup_create_and_verify(application):
    """§12 backup validation: P-10's backup service creates a backup of
    the live database and checksum-verifies it. (In-app restore does
    NOT exist — restore is a documented manual owner procedure; that
    gap is registered in the P-14 defect register, not asserted here.)"""
    result = application.security.backup.create_backup(OWNER)
    backup_id = result["id"] if "id" in result else result.get("backup_id")
    assert backup_id, result
    verified = application.security.backup.verify_backup(OWNER, backup_id)
    assert verified.get("valid") is True or verified.get("status") in (
        "verified", "valid"), verified


def test_p14_api_latency_measurements(client, auth_headers):
    """§13 performance: MEASURE (do not target) representative GET
    latencies on this Linux staging VM; write the raw measurements to
    docs/p14/P14_PERF_MEASUREMENTS.json as audit evidence."""
    endpoints = [
        "/api/v1/health/live",
        "/api/v1/dashboard/overview",
        "/api/v1/dashboard/finance/summary",
        "/api/v1/financial/overview",
        "/api/v1/portfolio/portfolios",
        "/api/v1/operations/overview",
        "/api/v1/dashboard/security/summary",
        "/api/v1/business/businesses",
        "/api/v1/agents",
        "/api/v1/memory",
    ]
    measurements = {}
    for path in endpoints:
        samples = []
        for _ in range(5):
            start = time.perf_counter()
            resp = client.get(path, headers=auth_headers)
            samples.append(round((time.perf_counter() - start) * 1000, 2))
            assert resp.status_code in (200, 404), (path, resp.status_code)
        measurements[path] = {
            "status": resp.status_code, "samples_ms": samples,
            "median_ms": sorted(samples)[len(samples) // 2],
            "max_ms": max(samples)}
    PERF_FILE.parent.mkdir(parents=True, exist_ok=True)
    PERF_FILE.write_text(json.dumps({
        "environment": "Linux staging VM (shared vCPU), TestClient "
                       "in-process — NOT owner Windows hardware",
        "measurements": measurements}, indent=2))
    # Sanity bound only (this shared VM is slow); the report treats
    # these as measurements, never as passed performance targets.
    for path, m in measurements.items():
        if m["status"] == 200:
            assert m["median_ms"] < 5000, (path, m)
