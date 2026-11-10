"""P-14 Stage B — repair verification tests.

One focused test per repaired defect that the Stage A audit suites
asserted only as a gap (or did not cover): DEF-I5 (P-05 submission
routed through the P-10 PermissionBroker), DEF-I4 (event dead
letters), DEF-A3 (§14 monitoring surface payload), DEF-A4 (guarded
restore preview), DEF-D1 (integer minor-unit budget columns).
DEF-F1/E1/E2/I1/I3 are covered by test_p14_financial.py and the
updated test_p14_e2e.py scenarios.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.application import Application
from app.core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError)
from app.dashboard.service import DashboardService
from app.database.models.core import EventDeadLetter
from app.database.models.opportunities import ResearchBrief
from app.database.models.security import SecurityBrokerDecision
from app.events.events import Event, EventType
from app.execution.schemas import ExecutionRequestIn
from app.permissions.models import Principal, PrincipalType
from tests.conftest import OWNER, make_settings
from tests.p05_support import grant, make_agent


@pytest.fixture()
async def app_b(tmp_path):
    """Controlled-mode application (broker attached by the assembly)."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


def _broker_decisions(application, action: str) -> list:
    session = application.session_factory()
    try:
        return session.execute(
            select(SecurityBrokerDecision)
            .where(SecurityBrokerDecision.action == action)).scalars().all()
    finally:
        session.close()


# ------------------------------------------------------------- DEF-I5
async def test_i5_broker_hard_gate_rejects_suspended_agent_submission(app_b):
    """A security-layer suspension (broker-only gate) now denies a
    P-05 submission that the P-05 policy alone would have queued."""
    agent_id = await make_agent(app_b)
    await grant(app_b, agent_id, "file_read")
    app_b.security.impose_restriction(OWNER, agent_id, "suspended",
                                      reason="Stage B I5 test")
    agent = Principal(PrincipalType.AGENT, agent_id)
    request = app_b.execution.submit(agent, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="read",
        parameters={"workspace": f"agent:{agent_id}", "path": "notes.txt"}))
    assert request.status == "REJECTED", request.status
    assert "suspended" in (request.result_summary or "")
    decisions = _broker_decisions(app_b, "filesystem.read")
    assert decisions and decisions[-1].allowed is False


async def test_i5_normal_submission_queues_and_is_ledgered(app_b):
    """An unrestricted agent's submission proceeds as before, and the
    broker authorization is recorded in its decision ledger."""
    agent_id = await make_agent(app_b)
    await grant(app_b, agent_id, "file_read")
    agent = Principal(PrincipalType.AGENT, agent_id)
    request = app_b.execution.submit(agent, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="read",
        parameters={"workspace": f"agent:{agent_id}", "path": "notes.txt"}))
    assert request.status == "QUEUED", request.status
    decisions = _broker_decisions(app_b, "filesystem.read")
    assert decisions and decisions[-1].allowed is True


# ------------------------------------------------------------- DEF-I4
async def test_i4_failed_delivery_is_dead_lettered(app_b):
    """A failing subscriber's delivery is recorded durably, not
    count-and-forget."""
    async def bad_handler(event):
        raise RuntimeError("stage B dead-letter probe")

    app_b.bus.subscribe(EventType.SECURITY_INCIDENT_DETECTED, bad_handler)
    await app_b.bus.publish(Event(
        event_type=EventType.SECURITY_INCIDENT_DETECTED,
        source="stage-b-test", payload={"probe": True}))
    session = app_b.session_factory()
    try:
        count = session.scalar(
            select(func.count()).select_from(EventDeadLetter)
            .where(EventDeadLetter.event_type
                   == "SecurityIncidentDetected")) or 0
    finally:
        session.close()
    assert count >= 1


# ------------------------------------------------------------- DEF-A3
async def test_a3_system_health_carries_resources_modules_dead_letters(app_b):
    """The §14 surface: one payload with checks, resource utilization,
    per-module health and dead-letter depth."""
    health = await DashboardService(app_b).system_health()
    assert health["checks"], "no checks in system health payload"
    assert "cpu_percent" in health["resources"]
    assert health["resources"]["source"] == "P-01 system monitor"
    modules = {m["module"] for m in health["modules"]}
    assert "P-01" in modules and "P-02" in modules, modules
    assert isinstance(health["event_dead_letters"], int)


# ------------------------------------------------------------- DEF-A4
async def test_a4_restore_preview_guards_and_plan(app_b):
    """Restore preview: owner-only, requires a verified backup and a
    hash-bound approved approval; never executes."""
    backup = app_b.security.backup.create_backup(OWNER)
    agent = Principal(PrincipalType.AGENT, "agent-x")
    with pytest.raises(PermissionDeniedError):
        app_b.security.restore_preview(agent, backup["id"], "nope")
    # Unknown approval id: refused (NotFoundError from the approval
    # store — the guard never reaches the binding check).
    with pytest.raises((ValidationError, NotFoundError)):
        app_b.security.restore_preview(OWNER, backup["id"], "nope")
    approval = app_b.approvals.create(
        OWNER, "security.restore_backup", "backup", "high",
        "Stage B A4 test restore", [], {"backup_id": backup["id"]})
    app_b.approvals.decide(approval.id, OWNER, True)
    plan = app_b.security.restore_preview(OWNER, backup["id"], approval.id)
    assert plan["executed"] is False
    assert plan["pre_restore_snapshot_id"]
    assert plan["backup_id"] == backup["id"]


# ------------------------------------------------------------- DEF-D1
async def test_d1_research_brief_budget_written_in_minor_units(app_b):
    """New declaration/brief money writes land in integer minor units
    alongside the deprecated float columns."""
    brief = app_b.opportunities.create_brief(OWNER, {
        "title": "Stage B D1 probe", "objective": "validate",
        "budget_amount": 50, "currency": "USD", "geography": "global"})
    session = app_b.session_factory()
    try:
        row = session.get(ResearchBrief, brief.id)
        assert row.budget_minor == 5000
    finally:
        session.close()
