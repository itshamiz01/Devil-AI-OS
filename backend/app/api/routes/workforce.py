"""Workforce API (/workforce) — Agentic Workforce Transformation.

All counts and profiles come from the database (P-01 agents registry +
workforce_profiles). Authorization is enforced in the service layer:
seeding and lifecycle controls are owner-only; work-order dispatch is
manager/CEO/owner; deliverable review is the employee's manager or the
owner; restricted work orders escalate to the P-01 approval path and
are never dispatched directly.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...core.application import Application
from ...permissions.models import Principal
from ..dependencies import correlation_id, get_application, get_principal
from ..schemas.common import ok, page
from ..schemas.workforce import (
    DeliverableIn, HandoffIn, ObjectiveIn, ReviewIn, WorkOrderIn,
)

router = APIRouter(tags=["workforce"])


def _svc(application: Application):
    return application.workforce


@router.post("/workforce/seed")
async def seed_workforce(request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(get_principal)):
    result = _svc(application).seed_workforce(principal)
    return ok(result, correlation_id(request))


@router.get("/workforce/overview")
async def overview(request: Request,
                   application: Application = Depends(get_application),
                   _: Principal = Depends(get_principal)):
    return ok(_svc(application).overview(), correlation_id(request))


@router.get("/workforce/departments")
async def departments(request: Request,
                      application: Application = Depends(get_application),
                      _: Principal = Depends(get_principal)):
    return ok(_svc(application).list_departments(), correlation_id(request))


@router.get("/workforce/departments/{department_code}/performance")
async def department_performance(department_code: str, request: Request,
                                 application: Application = Depends(get_application),
                                 _: Principal = Depends(get_principal)):
    return ok(_svc(application).department_performance(department_code),
              correlation_id(request))


@router.get("/workforce/employees")
async def employees(request: Request, level: str | None = None,
                    department_code: str | None = None, status: str | None = None,
                    limit: int = Query(default=200, ge=1, le=500),
                    offset: int = Query(default=0, ge=0),
                    application: Application = Depends(get_application),
                    _: Principal = Depends(get_principal)):
    rows, total = _svc(application).list_employees(
        level=level, department_code=department_code, status=status,
        limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/workforce/employees/{employee_code}")
async def employee(employee_code: str, request: Request,
                   application: Application = Depends(get_application),
                   _: Principal = Depends(get_principal)):
    return ok(_svc(application).get_employee(employee_code),
              correlation_id(request))


@router.get("/workforce/employees/{employee_code}/performance")
async def employee_performance(employee_code: str, request: Request,
                               application: Application = Depends(get_application),
                               _: Principal = Depends(get_principal)):
    return ok(_svc(application).employee_performance(employee_code),
              correlation_id(request))


@router.post("/workforce/employees/{employee_code}/{action}")
async def employee_action(employee_code: str, action: str, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal)):
    """action in pause|resume|disable|enable|block|unblock (owner-only)."""
    result = _svc(application).set_employee_status(principal, employee_code, action)
    return ok(result, correlation_id(request))


@router.post("/workforce/objectives", status_code=201)
async def submit_objective(body: ObjectiveIn, request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal)):
    result = _svc(application).submit_objective(
        principal, title=body.title, description=body.description,
        department_codes=body.department_codes)
    return ok(result, correlation_id(request))


@router.get("/workforce/objectives")
async def list_objectives(request: Request,
                          limit: int = Query(default=50, ge=1, le=200),
                          offset: int = Query(default=0, ge=0),
                          application: Application = Depends(get_application),
                          _: Principal = Depends(get_principal)):
    rows, total = _svc(application).list_objectives(limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/workforce/objectives/{objective_id}")
async def get_objective(objective_id: str, request: Request,
                        application: Application = Depends(get_application),
                        _: Principal = Depends(get_principal)):
    return ok(_svc(application).get_objective(objective_id),
              correlation_id(request))


@router.post("/workforce/objectives/{objective_id}/consolidate")
async def consolidate(objective_id: str, request: Request,
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(get_principal)):
    result = _svc(application).consolidate_objective(principal, objective_id)
    return ok(result, correlation_id(request))


@router.post("/workforce/work-orders", status_code=201)
async def dispatch_work_order(body: WorkOrderIn, request: Request,
                              application: Application = Depends(get_application),
                              principal: Principal = Depends(get_principal)):
    result = await _svc(application).dispatch_work_order(
        principal, objective_id=body.objective_id,
        employee_code=body.employee_code, objective=body.objective,
        instructions=body.instructions,
        expected_deliverable=body.expected_deliverable,
        priority=body.priority, deadline=body.deadline,
        restricted=body.restricted)
    return ok(result, correlation_id(request))


@router.post("/workforce/work-orders/{assignment_id}/accept")
async def accept_work_order(assignment_id: str, request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal)):
    return ok(_svc(application).accept_work_order(principal, assignment_id),
              correlation_id(request))


@router.post("/workforce/work-orders/{assignment_id}/deliverable")
async def submit_deliverable(assignment_id: str, body: DeliverableIn,
                             request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(get_principal)):
    result = _svc(application).submit_deliverable(
        principal, assignment_id, work_performed=body.work_performed,
        result=body.result, evidence=body.evidence,
        limitations=body.limitations, outstanding_issues=body.outstanding_issues)
    return ok(result, correlation_id(request))


@router.post("/workforce/deliverables/{deliverable_id}/review")
async def review_deliverable(deliverable_id: str, body: ReviewIn,
                             request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(get_principal)):
    result = _svc(application).review_deliverable(
        principal, deliverable_id, accept=body.accept,
        quality_score=body.quality_score, notes=body.notes)
    return ok(result, correlation_id(request))


@router.post("/workforce/handoffs", status_code=201)
async def create_handoff(body: HandoffIn, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(get_principal)):
    result = _svc(application).create_handoff(
        principal, from_code=body.from_code, to_code=body.to_code,
        objective=body.objective, task_ref=body.task_ref,
        work_completed=body.work_completed, next_actions=body.next_actions)
    return ok(result, correlation_id(request))
