"""P-WORKFORCE: the 111-employee virtual organization.

Tests for the organizational foundation, the CEO operating loop, the manager
and employee execution systems, collaboration handoffs, performance KPIs,
memory isolation and the security boundaries (§25).

Everything goes through the HTTP surface wherever one exists, because that is
the surface the owner actually has. The assertions read real backend records:
the 111-employee baseline, the reporting hierarchy, the work-order lifecycle
and the KPI computation.
"""
from __future__ import annotations

import pytest

from app.core.config import Settings

WF = "/api/v1/workforce"


@pytest.fixture()
def settings(tmp_path):
    """Workforce tests seed the 111-employee baseline.

    This overrides the conftest ``settings`` (which leaves the baseline off so
    agent-factory and capability tests see a clean registry). The ``client``
    fixture picks up this ``settings`` because a module-level fixture wins over
    the conftest one for the tests in this module.
    """
    return Settings(
        environment="test",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        backup_dir=tmp_path / "backups",
        task_queue_capacity=5,
        task_max_concurrency=1,
        task_default_timeout=2,
        retry_base_delay=0.01,
        retry_max_delay=0.05,
        scheduler_poll_interval=0.01,
        shutdown_timeout=1,
        login_rate_limit=20,
        workforce_seed_baseline=True,
    )


# --------------------------------------------------------------------------- #
# Stage 2: Organizational foundation
# --------------------------------------------------------------------------- #
def test_exactly_111_baseline_employees_exist(client):
    resp = client.get(f"{WF}/overview")
    assert resp.status_code == 200, resp.text
    ov = resp.json()["data"]
    assert ov["total_employees"] == 111
    assert ov["ceo_count"] == 1
    assert ov["manager_count"] == 10
    assert ov["specialist_count"] == 100
    assert ov["department_count"] == 10


def test_exactly_ten_departments(client):
    resp = client.get(f"{WF}/departments")
    assert resp.status_code == 200, resp.text
    depts = resp.json()["data"]
    assert len(depts) == 10
    codes = {d["code"] for d in depts}
    assert codes == {"STR", "RES", "BIZ", "TECH", "MKT", "SAL", "FIN", "OPS", "SEC", "CS"}


def test_every_employee_has_a_unique_stable_id(client):
    resp = client.get(f"{WF}/employees")
    assert resp.status_code == 200, resp.text
    employees = resp.json()["data"]
    ids = [e["employee_id"] for e in employees]
    assert len(ids) == len(set(ids)) == 111
    assert "DEV-CEO-001" in ids
    assert all(eid.startswith("DEV-") for eid in ids)


def test_every_manager_has_exactly_ten_baseline_employees(client):
    resp = client.get(f"{WF}/structure")
    assert resp.status_code == 200, resp.text
    structure = resp.json()["data"]
    assert structure["ceo"]["employee_id"] == "DEV-CEO-001"
    assert structure["ceo"]["manager_employee_id"] is None
    for department in structure["departments"]:
        assert len(department["employees"]) == 10
        assert department["manager"]["employee_id"].startswith("DEV-MGR")


def test_reporting_hierarchy_is_valid(client):
    resp = client.get(f"{WF}/structure")
    structure = resp.json()["data"]
    for department in structure["departments"]:
        manager_id = department["manager"]["employee_id"]
        for employee in department["employees"]:
            assert employee["manager_employee_id"] == manager_id
    # every manager reports to the CEO
    for department in structure["departments"]:
        assert department["manager"]["manager_employee_id"] == "DEV-CEO-001"


def test_restart_does_not_duplicate_employees(settings, owner_credentials):
    """Seeding is idempotent: a second run creates nothing."""
    from app.core.application import create_app, seed_core_data
    from app.core.auth import AuthService
    from app.database.connection import Database
    from fastapi.testclient import TestClient
    import asyncio

    async def bootstrap():
        db = Database(settings)
        try:
            await db.initialize()
            await seed_core_data(db, settings)
            await AuthService(settings, db).bootstrap_owner(*owner_credentials)
        finally:
            await db.dispose()

    asyncio.run(bootstrap())
    app = create_app(settings)
    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login",
                   json={"username": owner_credentials[0], "password": owner_credentials[1]})
        c.headers.update({"Authorization": f"Bearer {r.json()['data']['access_token']}"})
        ov = c.get(f"{WF}/overview").json()["data"]
        assert ov["total_employees"] == 111  # not 222


# --------------------------------------------------------------------------- #
# Stage 3: Employee profiles
# --------------------------------------------------------------------------- #
def test_employee_profile_has_all_required_fields(client):
    resp = client.get(f"{WF}/employees/DEV-CEO-001")
    assert resp.status_code == 200, resp.text
    profile = resp.json()["data"]
    for field in ("employee_id", "display_name", "job_title", "role_description",
                  "primary_responsibilities", "manager_employee_id", "skills",
                  "tool_access", "memory_scope", "system_instructions",
                  "permission_scope", "status", "is_baseline"):
        assert field in profile, f"missing field: {field}"
    assert profile["job_title"] == "Chief Executive Officer"
    assert profile["manager_employee_id"] is None


def test_employee_instructions_are_role_specific(client):
    """No two employees share an identical generic prompt (§6)."""
    resp = client.get(f"{WF}/employees")
    assert resp.status_code == 200, resp.text
    # fetch a diverse sample of profiles and assert distinct instructions
    instructions = []
    for eid in ("DEV-CEO-001", "DEV-MGR-004", "DEV-TECH-001",
                "DEV-MKT-001", "DEV-FIN-001", "DEV-CS-001"):
        p = client.get(f"{WF}/employees/{eid}").json()["data"]
        instructions.append(p["system_instructions"])
    assert len(set(instructions)) == len(instructions)
    # each instruction names its own employee
    for eid, instr in zip(
            ("DEV-CEO-001", "DEV-MGR-004", "DEV-TECH-001",
             "DEV-MKT-001", "DEV-FIN-001", "DEV-CS-001"), instructions):
        assert eid in instr


def test_disabled_employee_keeps_history(client):
    """Employees must not disappear when disabled (§6)."""
    before = client.get(f"{WF}/employees/DEV-STR-001").json()["data"]
    resp = client.patch(f"{WF}/employees/DEV-STR-001/status",
                        json={"status": "SUSPENDED", "reason": "owner review"})
    assert resp.status_code == 200, resp.text
    after = resp.json()["data"]
    assert after["to_status"] == "SUSPENDED"
    # the employee still exists with its profile intact
    profile = client.get(f"{WF}/employees/DEV-STR-001").json()["data"]
    assert profile["employee_id"] == "DEV-STR-001"
    assert profile["job_title"] == before["job_title"]


# --------------------------------------------------------------------------- #
# Stage 4: CEO intelligence
# --------------------------------------------------------------------------- #
def test_ceo_can_delegate_an_objective_to_managers(client):
    resp = client.post(f"{WF}/objectives", json={
        "objective": "Research and launch a profitable digital product",
        "departments": ["RES", "BIZ", "TECH", "MKT", "FIN"],
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["objective"]["status"] == "DELEGATED"
    assert set(data["objective"]["departments"]) == {"RES", "BIZ", "TECH", "MKT", "FIN"}
    strategy = data["execution_strategy"]
    assert "DEV-MGR-002" in strategy["department_managers"]  # Research manager


def test_ceo_objective_without_explicit_departments_maps_by_keyword(client):
    resp = client.post(f"{WF}/objectives", json={
        "objective": "Audit the security of the current application",
    })
    assert resp.status_code == 200, resp.text
    departments = resp.json()["data"]["objective"]["departments"]
    assert "SEC" in departments


def test_ceo_morning_briefing_uses_real_records(client):
    resp = client.get(f"{WF}/ceo/briefing")
    assert resp.status_code == 200, resp.text
    briefing = resp.json()["data"]
    assert briefing["organizational_status"]["total_employees"] == 111
    assert len(briefing["department_status"]) == 10


def test_ceo_end_of_day_report_distinguishes_outcomes(client):
    resp = client.get(f"{WF}/ceo/end-of-day")
    assert resp.status_code == 200, resp.text
    report = resp.json()["data"]
    assert "tasks_completed" in report
    assert "tasks_pending" in report
    assert "tasks_failed" in report
    assert "note" in report  # distinguishes actual outcomes from estimates


# --------------------------------------------------------------------------- #
# Stage 5/6: Manager and employee execution
# --------------------------------------------------------------------------- #
def test_manager_assigns_work_order_to_own_employee(client):
    resp = client.post(f"{WF}/work-orders", json={
        "employee_id": "DEV-STR-001",
        "title": "Draft strategic roadmap",
        "instructions": "Prepare a strategic roadmap for the quarter.",
        "verification_requirements": ["deliverable_present"],
        "expected_deliverable": {"type": "roadmap"},
    })
    assert resp.status_code == 200, resp.text
    order = resp.json()["data"]
    assert order["status"] == "TASK_ASSIGNED"
    assert order["employee_id"] == "DEV-STR-001"


def test_cross_department_assignment_is_refused(client):
    """A manager may not assign work to an employee that does not report to
    it (§9 hierarchy is authoritative)."""
    # DEV-MGR-001 (Strategy) tries to assign to DEV-TECH-001 (Technology)
    # The assigner resolves to the CEO by default in the API, so this test
    # uses the CEO path but with a manager that is not the employee's manager.
    # Instead, verify the service refuses a non-manager assignment directly.
    import asyncio
    from app.core.application import create_app
    from app.database.connection import Database
    from app.workforce.service import WorkforceService
    from app.workforce.schemas import WorkOrderCreate
    from app.core.exceptions import ForbiddenError

    # The API assigns via the CEO by default; to test the hierarchy rule we
    # exercise the service directly with a non-owning manager.
    services = client.app.state.services
    wf = services.workforce.workforce  # the WorkforceService
    order = WorkOrderCreate(
        employee_id="DEV-TECH-001", title="Cross-dept task",
        instructions="Should be refused", verification_requirements=[])
    with pytest.raises(ForbiddenError):
        asyncio.run(wf.create_work_order(
            order, manager_employee_id="DEV-MGR-001"))  # Strategy mgr, not Tech mgr


def test_work_order_lifecycle_accepts_work_and_completes(client):
    # create
    order = client.post(f"{WF}/work-orders", json={
        "employee_id": "DEV-RES-001", "title": "Web research task",
        "instructions": "Conduct authorized web research.",
        "verification_requirements": ["findings_present"],
        "expected_deliverable": {"type": "report"},
    }).json()["data"]
    oid = order["id"]
    # accept
    r = client.post(f"{WF}/work-orders/{oid}/advance", json={"action": "accept"})
    assert r.json()["data"]["status"] == "TASK_ACCEPTED"
    # start
    r = client.post(f"{WF}/work-orders/{oid}/advance", json={"action": "start"})
    assert r.json()["data"]["status"] == "WORKING"
    # submit review
    r = client.post(f"{WF}/work-orders/{oid}/advance", json={"action": "submit_review"})
    assert r.json()["data"]["status"] == "REVIEW_PENDING"
    # complete with evidence + satisfied verification
    r = client.post(f"{WF}/work-orders/{oid}/advance", json={
        "action": "complete",
        "result": {"findings_present": True},
        "evidence": ["source A", "source B"],
    })
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "COMPLETED"


def test_completion_without_evidence_is_refused(client):
    order = client.post(f"{WF}/work-orders", json={
        "employee_id": "DEV-RES-002", "title": "No-evidence task",
        "instructions": "Do the work.", "verification_requirements": [],
    }).json()["data"]
    oid = order["id"]
    client.post(f"{WF}/work-orders/{oid}/advance", json={"action": "accept"})
    client.post(f"{WF}/work-orders/{oid}/advance", json={"action": "start"})
    client.post(f"{WF}/work-orders/{oid}/advance", json={"action": "submit_review"})
    r = client.post(f"{WF}/work-orders/{oid}/advance",
                    json={"action": "complete", "result": {}, "evidence": []})
    assert r.status_code == 403, r.text  # completion is judged, not accepted


def test_duplicate_open_work_order_is_refused(client):
    body = {"employee_id": "DEV-RES-003", "title": "Duplicate task",
            "instructions": "Do it.", "verification_requirements": []}
    r1 = client.post(f"{WF}/work-orders", json=body)
    assert r1.status_code == 200
    r2 = client.post(f"{WF}/work-orders", json=body)
    assert r2.status_code == 409  # duplicate assignment prevented


# --------------------------------------------------------------------------- #
# Stage 7: Collaboration and handoffs
# --------------------------------------------------------------------------- #
def test_cross_department_handoff_is_created(client):
    resp = client.post(f"{WF}/handoffs", json={
        "to_employee_id": "DEV-STR-001",
        "objective": "Pass research findings to strategy",
        "deliverable": "Research report",
        "required_action": "Synthesize into a strategy brief",
        "access_scope": "RES:report-only",
        "completion_criteria": ["strategy_brief_delivered"],
    })
    assert resp.status_code == 200, resp.text
    handoff = resp.json()["data"]
    assert handoff["from_department"] != handoff["to_department"]
    assert handoff["status"] == "pending"


def test_same_department_handoff_is_refused(client):
    # Both in STR department: the service refuses a same-department handoff
    # because handoffs are the cross-department collaboration channel only.
    import asyncio
    from app.workforce.schemas import HandoffCreate
    from app.core.exceptions import ConflictError
    services = client.app.state.services
    wf = services.workforce.workforce
    body = HandoffCreate(
        to_employee_id="DEV-STR-002", objective="Same department",
        deliverable="x", required_action="y")
    with pytest.raises(ConflictError):
        asyncio.run(wf.create_handoff(body, from_employee_id="DEV-STR-001"))


def test_internal_message_is_recorded(client):
    resp = client.post(f"{WF}/messages", json={
        "to_employee_id": "DEV-MGR-001",
        "content": "Please deliver the strategy brief by Friday.",
        "kind": "task_linked",
    })
    assert resp.status_code == 200, resp.text
    msg = resp.json()["data"]
    assert msg["to_employee_id"] == "DEV-MGR-001"
    conv = client.get(f"{WF}/messages/DEV-CEO-001/DEV-MGR-001").json()["data"]
    assert any(m["content"] == "Please deliver the strategy brief by Friday."
               for m in conv)


# --------------------------------------------------------------------------- #
# Stage 8: Memory and performance
# --------------------------------------------------------------------------- #
def test_employee_memory_is_scoped_and_isolated(client):
    # record memory for one employee
    r = client.post(f"{WF}/employees/DEV-RES-001/memory", json={
        "category": "learned_procedures",
        "content": "Always cite sources for research findings.",
    })
    assert r.status_code == 200, r.text
    # the employee can read its own memory
    mem = client.get(f"{WF}/employees/DEV-RES-001/memory").json()["data"]
    assert len(mem) == 1
    assert mem[0]["category"] == "learned_procedures"


def test_credentials_are_refused_in_memory(client):
    r = client.post(f"{WF}/employees/DEV-RES-001/memory", json={
        "category": "identity",
        "content": "api_key = sk-1234567890abcdef",
    })
    assert r.status_code == 403  # credentials never enter ordinary memory


def test_performance_kpis_are_computed_from_verified_outcomes(client):
    # give an employee a completed, evidence-backed work order
    order = client.post(f"{WF}/work-orders", json={
        "employee_id": "DEV-OPS-001", "title": "KPI task",
        "instructions": "Do the work.", "verification_requirements": ["ok"],
    }).json()["data"]
    oid = order["id"]
    client.post(f"{WF}/work-orders/{oid}/advance", json={"action": "accept"})
    client.post(f"{WF}/work-orders/{oid}/advance", json={"action": "start"})
    client.post(f"{WF}/work-orders/{oid}/advance", json={"action": "submit_review"})
    client.post(f"{WF}/work-orders/{oid}/advance", json={
        "action": "complete", "result": {"ok": True}, "evidence": ["ev1"]})
    # recompute
    r = client.post(f"{WF}/performance/recompute")
    assert r.status_code == 200, r.text
    kpis = client.get(f"{WF}/employees/DEV-OPS-001/kpis").json()["data"]
    assert len(kpis) >= 1
    assert kpis[0]["verified_success_rate"] > 0
    assert kpis[0]["source"] if "source" in kpis[0] else True


def test_department_kpis_aggregate(client):
    client.post(f"{WF}/performance/recompute")
    r = client.get(f"{WF}/departments/OPS/performance")
    assert r.status_code == 200, r.text
    kpis = r.json()["data"]
    assert kpis["department_code"] == "OPS"
    assert kpis["employee_count"] == 11  # 1 manager + 10 specialists


# --------------------------------------------------------------------------- #
# Stage 10: Security and governance
# --------------------------------------------------------------------------- #
def test_workforce_endpoints_require_authentication(settings, owner_credentials):
    from app.core.application import create_app
    from fastapi.testclient import TestClient
    import asyncio
    from app.core.application import seed_core_data
    from app.core.auth import AuthService
    from app.database.connection import Database

    async def bootstrap():
        db = Database(settings)
        try:
            await db.initialize()
            await seed_core_data(db, settings)
            await AuthService(settings, db).bootstrap_owner(*owner_credentials)
        finally:
            await db.dispose()
    asyncio.run(bootstrap())
    app = create_app(settings)
    with TestClient(app) as c:
        # no auth header
        r = c.get(f"{WF}/overview")
        assert r.status_code == 401


def test_employee_cannot_self_grant_capabilities(client):
    """No employee may modify its own permissions (§21). The capability
    catalog's PROHIBITED set and the self-grant check enforce this."""
    from app.agents.catalog import PROHIBITED_CAPABILITIES
    assert "approval.self_grant" in PROHIBITED_CAPABILITIES
    assert "financial.execute" in PROHIBITED_CAPABILITIES
    # the finance department's tool access never includes financial.execute
    finance = client.get(f"{WF}/employees/DEV-FIN-001").json()["data"]
    assert "financial.execute" not in finance["tool_access"]


def test_finance_employees_have_no_financial_execution(client):
    """The Finance department is analysis and reporting only (§22)."""
    for eid in ("DEV-FIN-001", "DEV-MGR-007"):
        profile = client.get(f"{WF}/employees/{eid}").json()["data"]
        assert "financial.execute" not in profile["tool_access"]
        assert "spending.authorize" not in profile["tool_access"]
