"""P-15 security tests: P-10 governance cannot be bypassed through
the reliability surface (§15). Writes are owner-gated in the service;
reads require authentication; the readiness gate cannot be argued
around; P-15 tables carry no money; observing P-07 never mutates it.
"""
from __future__ import annotations

import pytest

from app.core.exceptions import PermissionDeniedError
from tests.p15_support import (  # noqa: F401
    AGENT, OWNER, SERVICE, app_rel, client_rel,
)

pytestmark = pytest.mark.asyncio


async def test_agent_cannot_create_or_resolve_incidents(app_rel):
    svc = app_rel.reliability
    with pytest.raises(PermissionDeniedError):
        svc.create_incident(AGENT, {"severity": "P3", "component": "x",
                                    "kind": "y", "title": "z"})
    created = svc.create_incident(OWNER, {
        "severity": "P3", "component": "x", "kind": "y", "title": "z"})
    with pytest.raises(PermissionDeniedError):
        svc.acknowledge_incident(AGENT, created["id"])
    with pytest.raises(PermissionDeniedError):
        svc.resolve_incident(AGENT, created["id"], {})
    with pytest.raises(PermissionDeniedError):
        svc.resolve_incident(SERVICE, created["id"], {})


async def test_agent_cannot_run_benchmarks_backups_or_settings(app_rel):
    svc = app_rel.reliability
    with pytest.raises(PermissionDeniedError):
        await svc.run_benchmark(AGENT)
    with pytest.raises(PermissionDeniedError):
        svc.create_backup(AGENT)
    with pytest.raises(PermissionDeniedError):
        svc.update_settings(AGENT, {"backup_max_age_hours": 24})
    with pytest.raises(PermissionDeniedError):
        svc.update_settings(SERVICE, {"backup_max_age_hours": 24})


def test_http_requires_authentication(client_rel):
    for method, path in (("GET", "/api/v1/reliability/overview"),
                         ("GET", "/api/v1/reliability/incidents"),
                         ("GET", "/api/v1/reliability/readiness"),
                         ("POST", "/api/v1/reliability/samples"),
                         ("POST", "/api/v1/reliability/incidents"),
                         ("POST", "/api/v1/reliability/benchmarks"),
                         ("POST", "/api/v1/reliability/backups")):
        resp = client_rel.request(method, path, json={})
        assert resp.status_code in (401, 422), (method, path, resp.status_code)
        if resp.status_code == 422:  # body validation must not precede auth
            resp = client_rel.request(method, path)
            assert resp.status_code == 401, (method, path)


def test_no_money_columns_in_p15_tables():
    from app.database.models.reliability import (
        BenchmarkRun, PerformanceSample, ReadinessSnapshot, ReliabilityIncident,
    )
    banned = ("amount", "minor", "balance", "price", "cost", "revenue",
              "profit", "currency")
    for model in (PerformanceSample, ReliabilityIncident,
                  ReadinessSnapshot, BenchmarkRun):
        for column in model.__table__.columns:
            assert not any(b in column.name for b in banned), \
                f"{model.__tablename__}.{column.name} looks monetary"


async def test_financial_observation_never_mutates_p07(app_rel):
    from sqlalchemy import func, select

    from app.database.models.financial import JournalEntry
    svc = app_rel.reliability
    session = app_rel.session_factory()
    try:
        before = session.scalar(
            select(func.count()).select_from(JournalEntry)) or 0
    finally:
        session.close()
    svc.financial_reliability()
    await svc.collect_evidence()
    session = app_rel.session_factory()
    try:
        after = session.scalar(
            select(func.count()).select_from(JournalEntry)) or 0
    finally:
        session.close()
    assert after == before, "P-15 observation must never write to P-07"


async def test_readiness_snapshot_records_gate_state(app_rel):
    svc = app_rel.reliability
    result = await svc.compute_readiness()
    # On a healthy staging application the gate holds; the snapshot
    # must record the gate state it computed, never a bare score.
    assert result["critical_gate_ok"] is True
    assert result["blockers"], "external blockers must always be recorded"
    assert all(b["scope"] in ("critical", "external", "operational")
               for b in result["blockers"])
