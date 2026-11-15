"""Organizational API surface for the 111-employee virtual organization (§23).

Every endpoint is permission-gated through the existing P-01 permission engine
and returns the standard JSON envelope. The workforce subsystem is reached
through ``services.workforce``; when it is not assembled, the endpoints report
that honestly rather than failing obscurely.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...core.exceptions import ConflictError
from ...workforce.schemas import (
    HandoffCreate,
    MessageCreate,
    ObjectiveCreate,
    WorkOrderCreate,
)
from ..dependencies import get_services, require_permission
from ..schemas.common import envelope

router = APIRouter(prefix="/workforce", tags=["workforce"])


def _require_workforce(request: Request):
    """The workforce subsystem, or a 409 saying it is not enabled."""
    services = get_services(request)
    workforce = getattr(services, "workforce", None)
    if workforce is None:
        raise ConflictError(
            "the workforce subsystem is not enabled",
            details={"hint": "set AUTONOMUS_WORKFORCE_ENABLED=true"},
        )
    return workforce


# --------------------------------------------------------------------------- #
# Organization
# --------------------------------------------------------------------------- #
@router.get("/overview")
async def organization_overview(request: Request,
                                principal=Depends(require_permission("workforce.read"))):
    services = _require_workforce(request)
    return envelope(await services.workforce.overview())


@router.get("/structure")
async def organization_structure(request: Request,
                                 principal=Depends(require_permission("workforce.read"))):
    services = _require_workforce(request)
    return envelope(await services.workforce.structure())


@router.get("/status")
async def workforce_status(request: Request,
                           principal=Depends(require_permission("workforce.read"))):
    services = get_services(request)
    workforce = getattr(services, "workforce", None)
    if workforce is None:
        return envelope({"enabled": False, "reason": "the workforce subsystem is not assembled"})
    return envelope(workforce.status())


# --------------------------------------------------------------------------- #
# Departments
# --------------------------------------------------------------------------- #
@router.get("/departments")
async def list_departments(request: Request,
                           principal=Depends(require_permission("workforce.read"))):
    services = _require_workforce(request)
    return envelope(await services.workforce.list_departments())


@router.get("/departments/{code}/performance")
async def department_performance(code: str, request: Request,
                                 principal=Depends(require_permission("workforce.performance"))):
    services = _require_workforce(request)
    return envelope(await services.performance.department_kpis(code))


# --------------------------------------------------------------------------- #
# Employees
# --------------------------------------------------------------------------- #
@router.get("/employees")
async def list_employees(request: Request,
                         department_code: str | None = Query(None),
                         status: str | None = Query(None),
                         principal=Depends(require_permission("workforce.read"))):
    services = _require_workforce(request)
    return envelope(await services.workforce.list_employees(
        department_code=department_code, status=status))


@router.get("/employees/{employee_id}")
async def get_employee(employee_id: str, request: Request,
                       principal=Depends(require_permission("workforce.read"))):
    services = _require_workforce(request)
    return envelope(await services.workforce.get_employee(employee_id))


@router.patch("/employees/{employee_id}/status")
async def update_employee_status(employee_id: str, request: Request,
                                 body: dict,
                                 principal=Depends(require_permission("workforce.manage"))):
    services = _require_workforce(request)
    status = body.get("status")
    reason = body.get("reason", "")
    if not status:
        raise ConflictError("status is required", details={"hint": "provide a status"})
    actor = principal.name if getattr(principal, "name", None) else "owner"
    return envelope(await services.workforce.update_employee_status(
        employee_id, status, reason, actor=actor))


# --------------------------------------------------------------------------- #
# CEO
# --------------------------------------------------------------------------- #
@router.post("/objectives")
async def submit_objective(request: Request, body: ObjectiveCreate,
                           principal=Depends(require_permission("workforce.ceo"))):
    services = _require_workforce(request)
    return envelope(await services.ceo.submit_objective(body, source="owner"))


@router.get("/objectives")
async def list_objectives(request: Request,
                          principal=Depends(require_permission("workforce.read"))):
    services = _require_workforce(request)
    async with services.db.session_factory() as session:
        from ...database.repositories import WorkforceObjectiveRepo
        rows = await WorkforceObjectiveRepo(session).list_all()
    return envelope([services.workforce._objective_summary(o) for o in rows])


@router.post("/objectives/{objective_id}/delegate")
async def delegate_objective(objective_id: str, request: Request, body: dict,
                             principal=Depends(require_permission("workforce.ceo"))):
    services = _require_workforce(request)
    departments = body.get("departments", [])
    return envelope(await services.workforce.delegate_objective(
        objective_id, departments=departments))


@router.get("/ceo/briefing")
async def ceo_briefing(request: Request,
                       principal=Depends(require_permission("workforce.ceo"))):
    services = _require_workforce(request)
    return envelope(await services.ceo.morning_briefing())


@router.get("/ceo/end-of-day")
async def ceo_end_of_day(request: Request,
                         principal=Depends(require_permission("workforce.ceo"))):
    services = _require_workforce(request)
    return envelope(await services.ceo.end_of_day_report())


@router.get("/ceo/weekly-review")
async def ceo_weekly_review(request: Request,
                            principal=Depends(require_permission("workforce.ceo"))):
    services = _require_workforce(request)
    return envelope(await services.ceo.weekly_review())


# --------------------------------------------------------------------------- #
# Work orders (tasks)
# --------------------------------------------------------------------------- #
@router.post("/work-orders")
async def create_work_order(request: Request, body: WorkOrderCreate,
                            principal=Depends(require_permission("workforce.assign"))):
    services = _require_workforce(request)
    # The assigning manager is resolved from the caller's identity; the CEO
    # assigns through the CEO office, managers through their own employee id.
    manager_employee_id = body.employee_id and _resolve_assigner(request, body)
    return envelope(await services.workforce.create_work_order(
        body, manager_employee_id=manager_employee_id))


def _resolve_assigner(request: Request, body: WorkOrderCreate) -> str:
    """The employee id of the manager assigning this work order.

    In this backend the assigning principal is the manager; the caller passes
    the manager employee id explicitly via the request when acting as a
    manager. For the CEO office path, the CEO id is used.
    """
    manager = getattr(request.state, "workforce_assigner", None)
    if manager:
        return manager
    # Default: the CEO delegates; a manager's own id is supplied by the
    # manager-facing flow. Without an explicit assigner, the CEO is the only
    # role that may assign without a named manager.
    return "DEV-CEO-001"


@router.get("/work-orders")
async def list_work_orders(request: Request, status: str | None = Query(None),
                           principal=Depends(require_permission("workforce.read"))):
    services = _require_workforce(request)
    async with services.db.session_factory() as session:
        from ...database.repositories import WorkforceWorkOrderRepo
        if status:
            rows = await WorkforceWorkOrderRepo(session).by_status(status)
        else:
            rows = await WorkforceWorkOrderRepo(session).list_all()
    return envelope([services.workforce._order_summary(o) for o in rows])


@router.post("/work-orders/{order_id}/advance")
async def advance_work_order(order_id: str, request: Request, body: dict,
                             principal=Depends(require_permission("workforce.assign"))):
    services = _require_workforce(request)
    action = body.get("action")
    if not action:
        raise ConflictError("action is required")
    return envelope(await services.workforce.advance_work_order(
        order_id, action=action, result=body.get("result"),
        evidence=body.get("evidence")))


# --------------------------------------------------------------------------- #
# Communication
# --------------------------------------------------------------------------- #
@router.post("/handoffs")
async def create_handoff(request: Request, body: HandoffCreate,
                         principal=Depends(require_permission("workforce.communicate"))):
    services = _require_workforce(request)
    from_employee_id = getattr(request.state, "workforce_actor", "DEV-CEO-001")
    return envelope(await services.workforce.create_handoff(
        body, from_employee_id=from_employee_id))


@router.get("/handoffs")
async def list_handoffs(request: Request,
                        principal=Depends(require_permission("workforce.read"))):
    services = _require_workforce(request)
    return envelope(await services.workforce.list_handoffs())


@router.post("/messages")
async def send_message(request: Request, body: MessageCreate,
                       principal=Depends(require_permission("workforce.communicate"))):
    services = _require_workforce(request)
    from_employee_id = getattr(request.state, "workforce_actor", "DEV-CEO-001")
    return envelope(await services.workforce.send_message(
        body, from_employee_id=from_employee_id))


@router.get("/messages/{a_id}/{b_id}")
async def conversation(a_id: str, b_id: str, request: Request,
                       principal=Depends(require_permission("workforce.read"))):
    services = _require_workforce(request)
    return envelope(await services.workforce.conversation(a_id, b_id))


# --------------------------------------------------------------------------- #
# Performance
# --------------------------------------------------------------------------- #
@router.get("/employees/{employee_id}/kpis")
async def employee_kpis(employee_id: str, request: Request,
                        principal=Depends(require_permission("workforce.performance"))):
    services = _require_workforce(request)
    return envelope(await services.performance.employee_kpis(employee_id))


@router.post("/performance/recompute")
async def recompute_performance(request: Request,
                                principal=Depends(require_permission("workforce.performance"))):
    services = _require_workforce(request)
    return envelope(await services.performance.recompute_all())


# --------------------------------------------------------------------------- #
# Memory
# --------------------------------------------------------------------------- #
@router.post("/employees/{employee_id}/memory")
async def record_memory(employee_id: str, request: Request, body: dict,
                        principal=Depends(require_permission("workforce.memory"))):
    services = _require_workforce(request)
    return envelope(await services.memory.record(
        employee_id, category=body.get("category", ""),
        content=body.get("content", ""), scope=body.get("scope", ""),
        shared_with=body.get("shared_with", [])))


@router.get("/employees/{employee_id}/memory")
async def read_memory(employee_id: str, request: Request,
                      category: str | None = Query(None),
                      principal=Depends(require_permission("workforce.memory"))):
    services = _require_workforce(request)
    return envelope(await services.memory.read(employee_id, category=category))
