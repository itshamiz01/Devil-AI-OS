"""Workforce orchestration tests (§25 hierarchy + task tests):
OWNER -> CEO objective -> manager work order -> employee accept ->
deliverable -> manager review -> task release -> CEO consolidation."""
from __future__ import annotations

import pytest

from app.core.exceptions import (
    InvalidStateTransitionError, PermissionDeniedError, ValidationError,
)
from tests.conftest import OWNER, wait_for_status
from tests.workforce_support import principal_for, seed


@pytest.fixture()
async def svc(application):
    service, _ = seed(application)
    return service


async def _objective(svc, departments=("research",)):
    return svc.submit_objective(
        OWNER, title="Verify the market evidence base",
        description="Research the demand evidence and report findings.",
        department_codes=list(departments))


async def _dispatch(svc, obj_id, code="DEV-RES-011", objective="Collect demand evidence"):
    return await svc.dispatch_work_order(
        OWNER, objective_id=obj_id, employee_code=code, objective=objective,
        instructions="Use authorized sources only.",
        expected_deliverable="Evidence summary with sources")


async def test_plan_alone_dispatches_nothing(application, svc):
    obj = await _objective(svc)
    assert obj["status"] == "plan_ready"
    assert [p["department_code"] for p in obj["plan"]] == ["research"]
    assert obj["plan"][0]["manager_code"] == "DEV-MGR-002"
    assert svc.overview()["work_orders_total"] == 0


async def test_full_cycle_owner_to_report(application, svc):
    obj = await _objective(svc)
    order = await _dispatch(svc, obj["id"])
    assert order["status"] == "assigned"
    # the P-01 task is parked: it cannot execute before manager review
    task = application.tasks.get(order["task_id"])
    assert task.status == "waiting_for_approval"

    employee = principal_for(application, "DEV-RES-011")
    accepted = svc.accept_work_order(employee, order["assignment_id"])
    assert accepted["status"] == "running"

    submitted = svc.submit_deliverable(
        employee, order["assignment_id"],
        work_performed="Reviewed 12 authorized sources",
        result="Demand evidence is positive in 3 of 4 segments",
        evidence=["source-register-12"])
    assert submitted["verification_status"] == "self_reported"

    # the WRONG manager cannot review it
    wrong_mgr = principal_for(application, "DEV-MGR-001")
    with pytest.raises(PermissionDeniedError):
        svc.review_deliverable(wrong_mgr, submitted["deliverable_id"],
                               accept=True, quality_score=50)
    # the employee's own manager reviews and accepts
    mgr = principal_for(application, "DEV-MGR-002")
    reviewed = svc.review_deliverable(
        mgr, submitted["deliverable_id"], accept=True, quality_score=90,
        notes="Evidence register checks out")
    assert reviewed["outcome"] == "accepted"
    assert reviewed["assignment_status"] == "completed"

    # acceptance released the parked task, which now completes in the
    # task engine (recording the reviewed deliverable)
    status = await wait_for_status(application.tasks, order["task_id"],
                                   {"completed"}, timeout=10.0)
    assert status == "completed"

    # KPI read model: measured, from real outcomes only
    perf = svc.employee_performance("DEV-RES-011")
    assert perf["data_status"] == "measured"
    assert perf["components"]["quality"] == 90.0
    assert perf["components"]["verified_success"] == 100.0
    assert perf["components"]["reliability"] == 100.0
    # (90*25 + 100*20 + 100*15) / 60 = 95.83 (deadline/efficiency/
    # collaboration/compliance excluded: no data, weights renormalized)
    assert perf["score"] == 95.83

    report = svc.consolidate_objective(OWNER, obj["id"])
    assert report["work_orders_total"] == 1
    assert report["work_orders_completed"] == 1
    dept = report["departments"]["research"]
    assert dept["deliverables"][0]["verification_status"] == "manager_verified"
    assert svc.get_objective(obj["id"])["status"] == "completed"


async def test_rework_then_accept(application, svc):
    obj = await _objective(svc)
    order = await _dispatch(svc, obj["id"])
    employee = principal_for(application, "DEV-RES-011")
    mgr = principal_for(application, "DEV-MGR-002")
    svc.accept_work_order(employee, order["assignment_id"])
    sub1 = svc.submit_deliverable(employee, order["assignment_id"],
                                  work_performed="draft", result="thin")
    out = svc.review_deliverable(mgr, sub1["deliverable_id"], accept=False,
                                 notes="Evidence missing — rework")
    assert out["outcome"] == "rework_requested"
    assert out["assignment_status"] == "running"
    sub2 = svc.submit_deliverable(employee, order["assignment_id"],
                                  work_performed="full pass",
                                  result="complete with evidence",
                                  evidence=["register-v2"])
    assert sub2["version"] == 2
    out2 = svc.review_deliverable(mgr, sub2["deliverable_id"], accept=True,
                                  quality_score=80)
    assert out2["assignment_status"] == "completed"


async def test_cross_department_assignment_refused(application, svc):
    obj = await _objective(svc)  # research only
    strategy_mgr = principal_for(application, "DEV-MGR-001")
    # a manager may not assign work to another department's employee
    with pytest.raises(PermissionDeniedError):
        await svc.dispatch_work_order(
            strategy_mgr, objective_id=obj["id"], employee_code="DEV-RES-011",
            objective="Strategy manager reaching across departments")
    # and an employee outside the objective's plan cannot be assigned
    with pytest.raises(ValidationError):
        await _dispatch(svc, obj["id"], code="DEV-STR-001")


async def test_handoff_is_the_cross_department_channel(application, svc):
    handoff = svc.create_handoff(
        OWNER, from_code="DEV-RES-011", to_code="DEV-STR-005",
        objective="Evaluate the demand evidence for feasibility",
        task_ref="objective-evidence", work_completed="Evidence register v1")
    assert handoff["from"] == "DEV-RES-011" and handoff["to"] == "DEV-STR-005"
    # an unrelated employee cannot create handoffs between others
    stranger = principal_for(application, "DEV-FIN-061")
    with pytest.raises(PermissionDeniedError):
        svc.create_handoff(stranger, from_code="DEV-RES-012",
                           to_code="DEV-STR-006", objective="sneaky")


async def test_deliverable_requires_acceptance_first(application, svc):
    obj = await _objective(svc)
    order = await _dispatch(svc, obj["id"])
    employee = principal_for(application, "DEV-RES-011")
    with pytest.raises(InvalidStateTransitionError):
        svc.submit_deliverable(employee, order["assignment_id"],
                               work_performed="x", result="y")
