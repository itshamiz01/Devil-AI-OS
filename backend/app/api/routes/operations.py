"""Autonomous Operations Engine API (P-12, §19/§21).

Route map under /api/v1/operations:
- status / settings / overview / safety
- workflows: create, list, get (+tasks/history), validate, start,
  pause, resume, cancel, reassign task
- approvals: center view, check (resolve pending links)
- autonomy: policies list/set, resolve preview
- triggers: create, list, pause/resume/cancel, tick (manual pass)
- scheduler view, recovery center, dead letters
- businesses/{id} operations view, agents view
- emergency stop/resume (scoped, owner-gated by the services)
- reports: generate, list, get

Permissions mirror the house pattern: read = read_business_data,
write = modify_business_data, govern = approve_actions. The service
additionally enforces owner-only rules (autonomy policies, settings,
emergency resume, dead-letter resolution) and per-business agent
scoping — routes never widen service rules.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...permissions.models import Permission
from ..dependencies import correlation_id, get_application, require_permission
from ..schemas import operations as S
from ..schemas.common import ok

router = APIRouter(prefix="/operations", tags=["operations"])

READ = require_permission(Permission.READ_BUSINESS_DATA)
WRITE = require_permission(Permission.MODIFY_BUSINESS_DATA)
GOVERN = require_permission(Permission.APPROVE_ACTIONS)


def _svc(request: Request):
    return get_application(request).operations


# ------------------------------------------------------------------ engine
@router.get("/status")
async def status(request: Request, principal=Depends(READ)):
    return ok(_svc(request).engine_status(), correlation_id(request))


@router.get("/settings")
async def get_settings(request: Request, principal=Depends(READ)):
    return ok(_svc(request).get_settings(), correlation_id(request))


@router.patch("/settings")
async def update_settings(request: Request, body: S.SettingsUpdateIn,
                          principal=Depends(GOVERN)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return ok(_svc(request).update_settings(principal, patch),
              correlation_id(request))


@router.get("/overview")
async def overview(request: Request, principal=Depends(READ)):
    return ok(_svc(request).overview(principal), correlation_id(request))


@router.get("/safety")
async def safety(request: Request, principal=Depends(READ)):
    return ok(_svc(request).safety_status(principal),
              correlation_id(request))


# ------------------------------------------------------------------ workflows
@router.post("/workflows", status_code=201)
async def create_workflow(request: Request, body: S.WorkflowCreateIn,
                          principal=Depends(WRITE)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return ok(_svc(request).create_workflow(principal, data),
              correlation_id(request))


@router.get("/workflows")
async def list_workflows(request: Request,
                         business_id: str | None = None,
                         status: str | None = None,
                         origin: str | None = None,
                         limit: int = Query(default=50, ge=1, le=200),
                         offset: int = Query(default=0, ge=0),
                         principal=Depends(READ)):
    return ok(_svc(request).list_workflows(
        principal, business_id=business_id, status=status, origin=origin,
        limit=limit, offset=offset), correlation_id(request))


@router.get("/workflows/{workflow_id}")
async def get_workflow(request: Request, workflow_id: str,
                       principal=Depends(READ)):
    return ok(_svc(request).get_workflow(principal, workflow_id),
              correlation_id(request))


@router.get("/workflows/{workflow_id}/history")
async def workflow_history(request: Request, workflow_id: str,
                           principal=Depends(READ)):
    return ok(_svc(request).workflow_history(principal, workflow_id),
              correlation_id(request))


@router.post("/workflows/{workflow_id}/validate")
async def validate_workflow(request: Request, workflow_id: str,
                            principal=Depends(WRITE)):
    return ok(_svc(request).validate_workflow(principal, workflow_id),
              correlation_id(request))


@router.post("/workflows/{workflow_id}/start")
async def start_workflow(request: Request, workflow_id: str,
                         principal=Depends(WRITE)):
    return ok(await _svc(request).start_workflow(principal, workflow_id),
              correlation_id(request))


@router.post("/workflows/{workflow_id}/pause")
async def pause_workflow(request: Request, workflow_id: str,
                         principal=Depends(WRITE)):
    return ok(_svc(request).pause_workflow(principal, workflow_id),
              correlation_id(request))


@router.post("/workflows/{workflow_id}/resume")
async def resume_workflow(request: Request, workflow_id: str,
                          principal=Depends(WRITE)):
    return ok(await _svc(request).resume_workflow(principal, workflow_id),
              correlation_id(request))


@router.post("/workflows/{workflow_id}/cancel")
async def cancel_workflow(request: Request, workflow_id: str,
                          principal=Depends(WRITE)):
    return ok(_svc(request).cancel_workflow(principal, workflow_id),
              correlation_id(request))


@router.post("/workflows/{workflow_id}/tasks/{task_id}/reassign")
async def reassign_task(request: Request, workflow_id: str, task_id: str,
                        body: S.ReassignIn, principal=Depends(GOVERN)):
    return ok(_svc(request).reassign_task(principal, workflow_id, task_id,
                                          body.agent_id),
              correlation_id(request))


@router.get("/workflows/{workflow_id}/decisions")
async def workflow_decisions(request: Request, workflow_id: str,
                             principal=Depends(READ)):
    return ok(_svc(request).list_decisions(principal,
                                           workflow_id=workflow_id),
              correlation_id(request))


# ------------------------------------------------------------------ approvals
@router.get("/approvals")
async def approvals_center(request: Request, principal=Depends(READ)):
    return ok(_svc(request).approvals_center(principal),
              correlation_id(request))


@router.post("/approvals/check")
async def check_approvals(request: Request, principal=Depends(GOVERN)):
    return ok(await _svc(request).check_approvals(principal),
              correlation_id(request))


# ------------------------------------------------------------------ autonomy
@router.get("/autonomy/policies")
async def list_policies(request: Request, principal=Depends(READ)):
    return ok(_svc(request).list_autonomy_policies(principal),
              correlation_id(request))


@router.post("/autonomy/policies", status_code=201)
async def set_policy(request: Request, body: S.AutonomyPolicyIn,
                     principal=Depends(GOVERN)):
    return ok(_svc(request).set_autonomy_policy(
        principal, body.model_dump()), correlation_id(request))


@router.get("/autonomy/resolve")
async def resolve(request: Request, action_class: str,
                  business_id: str | None = None,
                  agent_id: str | None = None,
                  workflow_id: str | None = None,
                  declared_level: int = 1,
                  principal=Depends(READ)):
    return ok(_svc(request).resolve_autonomy(
        business_id=business_id, agent_id=agent_id,
        workflow_id=workflow_id, workflow_declared_level=declared_level,
        action_class=action_class), correlation_id(request))


# ------------------------------------------------------------------ triggers / scheduler
@router.post("/triggers", status_code=201)
async def create_trigger(request: Request, body: S.TriggerCreateIn,
                         principal=Depends(WRITE)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return ok(_svc(request).create_trigger(principal, data),
              correlation_id(request))


@router.get("/triggers")
async def list_triggers(request: Request, status: str | None = None,
                        principal=Depends(READ)):
    return ok(_svc(request).list_triggers(principal, status=status),
              correlation_id(request))


@router.post("/triggers/{trigger_id}/status")
async def set_trigger_status(request: Request, trigger_id: str,
                             body: S.TriggerStatusIn,
                             principal=Depends(WRITE)):
    return ok(_svc(request).set_trigger_status(principal, trigger_id,
                                               body.status),
              correlation_id(request))


@router.post("/scheduler/tick")
async def tick(request: Request, principal=Depends(GOVERN)):
    return ok(await _svc(request).tick(), correlation_id(request))


# ------------------------------------------------------------------ recovery
@router.get("/recovery")
async def recovery_center(request: Request, principal=Depends(READ)):
    return ok(_svc(request).recovery_center(principal),
              correlation_id(request))


@router.post("/recovery/dead-letters/{dead_id}/resolve")
async def resolve_dead_letter(request: Request, dead_id: str,
                              body: S.DeadLetterResolveIn,
                              principal=Depends(GOVERN)):
    return ok(_svc(request).resolve_dead_letter(principal, dead_id,
                                                body.resolution),
              correlation_id(request))


# ------------------------------------------------------------------ businesses / agents
@router.get("/businesses/{business_id}")
async def business_operations(request: Request, business_id: str,
                              principal=Depends(READ)):
    return ok(_svc(request).business_operations(principal, business_id),
              correlation_id(request))


@router.get("/agents")
async def agent_operations(request: Request, principal=Depends(READ)):
    return ok(_svc(request).agent_operations(principal),
              correlation_id(request))


@router.get("/decisions")
async def decisions(request: Request, business_id: str | None = None,
                    limit: int = Query(default=100, ge=1, le=200),
                    principal=Depends(READ)):
    return ok(_svc(request).list_decisions(
        principal, business_id=business_id, limit=limit),
        correlation_id(request))


# ------------------------------------------------------------------ emergency
@router.post("/emergency/stop")
async def emergency_stop(request: Request, body: S.EmergencyStopIn,
                         principal=Depends(GOVERN)):
    return ok(await _svc(request).emergency_stop(
        principal, body.scope, body.ref, body.reason),
        correlation_id(request))


@router.post("/emergency/resume")
async def emergency_resume(request: Request, body: S.EmergencyStopIn,
                           principal=Depends(GOVERN)):
    return ok(await _svc(request).emergency_resume(
        principal, body.scope, body.ref), correlation_id(request))


# ------------------------------------------------------------------ reports
@router.post("/reports", status_code=201)
async def generate_report(request: Request, body: S.ReportGenerateIn,
                          principal=Depends(WRITE)):
    return ok(_svc(request).generate_report(
        principal, body.kind, business_id=body.business_id),
        correlation_id(request))


@router.get("/reports")
async def list_reports(request: Request, kind: str | None = None,
                       principal=Depends(READ)):
    return ok(_svc(request).list_reports(principal, kind=kind),
              correlation_id(request))


@router.get("/reports/{report_id}")
async def get_report(request: Request, report_id: str,
                     principal=Depends(READ)):
    return ok(_svc(request).get_report(principal, report_id),
              correlation_id(request))
