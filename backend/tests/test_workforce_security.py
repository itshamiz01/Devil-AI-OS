"""Workforce security tests (§25 security tests + §29 non-negotiables):
no self-permission changes, no manager override of P-10, no CEO bypass
of owner approval, disabled employees keep history, emergency stop."""
from __future__ import annotations

import pytest

from app.agents.errors import CapabilityProhibitedError
from app.core.exceptions import (
    InvalidStateTransitionError, PermissionDeniedError,
)
from app.permissions.models import Principal, PrincipalType
from tests.conftest import AGENT, OWNER
from tests.workforce_support import agent_id_for, principal_for, seed


@pytest.fixture()
async def svc(application):
    service, _ = seed(application)
    return service


async def test_agent_cannot_seed_or_control_lifecycle(application, svc):
    with pytest.raises(PermissionDeniedError):
        svc.seed_workforce(AGENT)
    employee = principal_for(application, "DEV-RES-011")
    # an employee cannot pause itself (or anyone)
    with pytest.raises(PermissionDeniedError):
        svc.set_employee_status(employee, "DEV-RES-011", "pause")
    # a manager cannot pause its own employee either: owner-only control
    mgr = principal_for(application, "DEV-MGR-002")
    with pytest.raises(PermissionDeniedError):
        svc.set_employee_status(mgr, "DEV-RES-011", "pause")
    # objective intake is owner-only too
    with pytest.raises(PermissionDeniedError):
        svc.submit_objective(employee, title="self-assigned",
                             description="employee inventing objectives")


async def test_employee_cannot_modify_own_permissions_or_config(application, svc):
    emp_id = agent_id_for(application, "DEV-RES-011")
    employee = Principal(PrincipalType.AGENT, emp_id)
    # factory config updates require manage_agents — agents do not hold it
    with pytest.raises(PermissionDeniedError):
        await application.agents.update_agent_config(
            emp_id, {"description": "self-promoted"}, principal=employee)
    # a profile's tool_access is a DECLARATION, not a grant: the employee
    # holds zero factory capability grants until the governed grant path
    assert application.agents.capabilities.granted_capability_names(emp_id) == []
    # prohibited capabilities can never be granted — even by the owner
    with pytest.raises(CapabilityProhibitedError):
        application.agents.capabilities.grant(
            emp_id, "reveal_secrets", granted_by=OWNER)
    with pytest.raises(CapabilityProhibitedError):
        application.agents.capabilities.grant(
            emp_id, "bypass_approvals", granted_by=OWNER)


async def test_restricted_work_escalates_and_ceo_cannot_approve(application, svc):
    obj = svc.submit_objective(
        OWNER, title="Announce the new report",
        description="Prepare the announcement pack.",
        department_codes=["research"])
    order = await svc.dispatch_work_order(
        OWNER, objective_id=obj["id"], employee_code="DEV-RES-011",
        objective="Publish the report publicly and send email to customers")
    assert order["status"] == "escalated_to_owner_approval"
    approval_id = order["approval_id"]
    # nothing was assigned to the employee
    assert svc.overview()["work_orders_total"] == 0
    # the CEO cannot decide its own escalation (no approve_actions)
    ceo = principal_for(application, "DEV-CEO-001")
    with pytest.raises(PermissionDeniedError):
        application.approvals.decide(approval_id, ceo, True)
    # neither can a manager (no P-10 override)
    mgr = principal_for(application, "DEV-MGR-002")
    with pytest.raises(PermissionDeniedError):
        application.approvals.decide(approval_id, mgr, True)
    # still pending; the owner CAN decide (the authority path works)
    approval = application.approvals.get(approval_id)
    assert approval.status == "pending"
    decided = application.approvals.decide(approval_id, OWNER, True)
    assert decided.status == "approved"


async def test_disabled_employee_keeps_history(application, svc):
    obj = svc.submit_objective(
        OWNER, title="Evidence sprint", description="Collect evidence.",
        department_codes=["research"])
    order = await svc.dispatch_work_order(
        OWNER, objective_id=obj["id"], employee_code="DEV-RES-011",
        objective="Collect demand evidence")
    employee = principal_for(application, "DEV-RES-011")
    mgr = principal_for(application, "DEV-MGR-002")
    svc.accept_work_order(employee, order["assignment_id"])
    sub = svc.submit_deliverable(employee, order["assignment_id"],
                                 work_performed="done", result="evidence in")
    svc.review_deliverable(mgr, sub["deliverable_id"], accept=True,
                           quality_score=75)
    # disable: profile, assignments and performance all survive
    svc.set_employee_status(OWNER, "DEV-RES-011", "disable")
    profile = svc.get_employee("DEV-RES-011")
    assert profile["workforce_status"] == "DISABLED"
    assert len(profile["assignments"]) == 1
    assert profile["performance"]["data_status"] == "measured"
    # a disabled employee cannot receive new work
    obj2 = svc.submit_objective(
        OWNER, title="More evidence", description="Collect more.",
        department_codes=["research"])
    with pytest.raises(InvalidStateTransitionError):
        await svc.dispatch_work_order(
            OWNER, objective_id=obj2["id"], employee_code="DEV-RES-011",
            objective="More evidence")
    # and can be re-enabled by the owner
    svc.set_employee_status(OWNER, "DEV-RES-011", "enable")
    assert svc.get_employee("DEV-RES-011")["workforce_status"] == "AVAILABLE"


async def test_global_emergency_stop_blocks_dispatch(application, svc):
    obj = svc.submit_objective(
        OWNER, title="Evidence sprint", description="Collect evidence.",
        department_codes=["research"])
    await application.operations.emergency_stop(OWNER, "global", None)
    try:
        with pytest.raises(InvalidStateTransitionError):
            await svc.dispatch_work_order(
                OWNER, objective_id=obj["id"], employee_code="DEV-RES-011",
                objective="Collect demand evidence")
    finally:
        await application.operations.emergency_resume(OWNER, "global", None)
    # after the owner resumes, dispatch works again
    order = await svc.dispatch_work_order(
        OWNER, objective_id=obj["id"], employee_code="DEV-RES-011",
        objective="Collect demand evidence")
    assert order["status"] == "assigned"
