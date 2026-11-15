"""Workforce organization tests (§25): exact headcount, hierarchy,
unique identities, profile completeness, restart idempotency."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.agents.constants import CAPABILITY_BY_NAME
from app.database.models.core import Agent
from app.database.models.workforce import (
    WorkforceDepartment, WorkforceProfile,
)
from app.workforce.definition import KPI_WEIGHTS
from tests.conftest import OWNER
from tests.workforce_support import agent_id_for, seed


@pytest.fixture()
async def svc(application):
    service, _ = seed(application)
    return service


def _all_profiles(application):
    session = application.session_factory()
    try:
        return session.scalars(select(WorkforceProfile)).all()
    finally:
        session.close()


async def test_exactly_111_baseline(application, svc):
    session = application.session_factory()
    try:
        total = session.scalar(select(func.count()).select_from(WorkforceProfile))
        assert total == 111
        by_level = {}
        for level in ("ceo", "manager", "employee"):
            by_level[level] = session.scalar(
                select(func.count()).select_from(WorkforceProfile).where(
                    WorkforceProfile.level == level))
        assert by_level == {"ceo": 1, "manager": 10, "employee": 100}
        depts = session.scalar(select(func.count()).select_from(WorkforceDepartment))
        assert depts == 10
    finally:
        session.close()
    overview = svc.overview()
    assert overview["total_employees"] == 111
    assert overview["ceo"] == 1 and overview["managers"] == 10
    assert overview["employees"] == 100 and overview["departments"] == 10


async def test_unique_codes_and_titles(application, svc):
    profiles = _all_profiles(application)
    codes = [p.employee_code for p in profiles]
    titles = [p.job_title for p in profiles]
    assert len(set(codes)) == 111 and len(set(titles)) == 111
    assert "DEV-CEO-001" in codes
    assert {f"DEV-MGR-{i:03d}" for i in range(1, 11)} <= set(codes)


async def test_reporting_lines(application, svc):
    ceo_id = agent_id_for(application, "DEV-CEO-001")
    session = application.session_factory()
    try:
        ceo = session.get(Agent, ceo_id)
        assert ceo.parent_agent_id is None
        for i in range(1, 11):
            mgr_id = agent_id_for(application, f"DEV-MGR-{i:03d}")
            mgr = session.get(Agent, mgr_id)
            assert mgr.parent_agent_id == ceo_id
            workers = session.scalars(select(Agent).where(
                Agent.parent_agent_id == mgr_id)).all()
            assert len(workers) == 10, f"manager {i} has {len(workers)} reports"
    finally:
        session.close()


async def test_profiles_complete_and_role_specific(application, svc):
    profiles = _all_profiles(application)
    instructions = set()
    for p in profiles:
        assert p.primary_responsibilities, p.employee_code
        assert p.skills, p.employee_code
        assert p.system_instructions and p.job_title in p.system_instructions
        instructions.add(p.system_instructions)
        # tool declarations come only from the supported catalogue
        for tool in p.tool_access:
            assert tool in CAPABILITY_BY_NAME, (p.employee_code, tool)
            assert CAPABILITY_BY_NAME[tool]["supported"], (p.employee_code, tool)
        assert p.kpi_weights == KPI_WEIGHTS
        assert sum(p.kpi_weights.values()) == 100
        assert p.workforce_status in (
            "ACTIVE", "AVAILABLE", "BUSY", "WAITING", "BLOCKED",
            "ON_LEAVE", "SUSPENDED", "DISABLED")
        assert p.memory_scope["credentials"] == "never"
    # role-specific, not one generic prompt x111
    assert len(instructions) == 111


async def test_seed_is_idempotent_across_restart(application):
    svc, first = seed(application)
    assert first["agents"] == 111 and first["profiles"] == 111
    # a fresh service instance over the same DB = application restart
    from app.workforce.service import WorkforceService
    svc2 = WorkforceService(application.session_factory, application.tasks,
                            application.approvals, application.permissions)
    second = svc2.seed_workforce(OWNER)
    assert second["agents"] == 0 and second["profiles"] == 0
    assert second["departments"] == 0 and second["total_profiles"] == 111
    session = application.session_factory()
    try:
        wf_agents = session.scalar(
            select(func.count()).select_from(Agent).where(
                Agent.agent_type.like("workforce_%")))
        assert wf_agents == 111
    finally:
        session.close()


async def test_overview_and_directory_via_api(client, auth_headers):
    r = client.post("/api/v1/workforce/seed", headers=auth_headers)
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/workforce/overview", headers=auth_headers)
    data = r.json()["data"]
    assert data["total_employees"] == 111 and data["departments"] == 10
    r = client.get("/api/v1/workforce/employees?limit=500", headers=auth_headers)
    assert r.json()["meta"]["total"] == 111
    r = client.get("/api/v1/workforce/departments", headers=auth_headers)
    depts = r.json()["data"]
    assert len(depts) == 10
    assert all(d["employee_count"] == 10 for d in depts)
    r = client.get("/api/v1/workforce/employees/DEV-CUS-100", headers=auth_headers)
    emp = r.json()["data"]
    assert emp["job_title"] == "Customer Success Quality Auditor"
    assert emp["manager_code"] == "DEV-MGR-010"
    assert emp["performance"]["data_status"] == "no_data"
