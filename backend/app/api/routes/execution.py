"""Execution API (P-05, §22 surface).

The Command Center UI is P-11 scope; P-05 exposes the full monitoring
and control surface as endpoints: tool discovery, requests, convenience
wrappers per adapter, workflows, standing authorizations, settings,
health report, metrics, emergency stop. Every mutation is enforced
server-side by the ExecutionService/policy — routes only transport.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...core.application import Application
from ...core.exceptions import NotFoundError, PermissionDeniedError
from ...database.repositories.execution import (
    BrowserSessionRepository, ExecutionRunRepository,
    WorkflowDefinitionRepository, WorkflowRunRepository,
    WorkflowStepRunRepository,
)
from ...execution.schemas import (
    ExecutionRequestIn, ExecutionSettingsIn, StandingAuthorizationIn,
    WorkflowDefinitionIn, WorkflowRunIn,
)
from ...execution.service import request_to_dict
from ...permissions.models import Principal, PrincipalType
from ..dependencies import correlation_id, get_application, get_principal
from ..schemas.common import ok, page
from ..schemas.execution import (
    WrapperIn, browser_session_to_dict, standing_authorization_to_dict,
    workflow_definition_to_dict, workflow_run_to_dict, workspace_to_dict,
)

router = APIRouter(tags=["execution"])


def _service(application: Application):
    if application.execution is None:
        raise NotFoundError("execution engine is not initialised")
    return application.execution


async def _submit_and_maybe_execute(application, principal, payload: ExecutionRequestIn,
                                    auto_execute: bool):
    service = _service(application)
    execution_request = service.submit(principal, payload)
    if auto_execute and execution_request.status == "QUEUED":
        execution_request = await service.execute(principal, execution_request.id)
    return execution_request


def _wrapper_payload(body: WrapperIn, tool: str, action: str) -> ExecutionRequestIn:
    return ExecutionRequestIn(
        agent_id=body.agent_id, tool=tool, action=action, parameters=body.parameters,
        task_id=body.task_id, business_ref=body.business_ref,
        requested_scope=body.requested_scope, priority=body.priority,
        timeout_seconds=body.timeout_seconds, retry_policy=body.retry_policy,
        expected_outcome=body.expected_outcome, idempotency_key=body.idempotency_key,
        approval_id=body.approval_id)


# --------------------------------------------------------------------- tools
@router.get("/execution/tools")
async def list_tools(request: Request, limit: int = Query(default=100, ge=1, le=200),
                     offset: int = Query(default=0, ge=0),
                     application: Application = Depends(get_application),
                     principal: Principal = Depends(get_principal)):
    service = _service(application)
    rows, total = service.registry.list_tools(limit, offset)
    admin = principal.type is PrincipalType.OWNER
    view = service.registry.admin_view if admin else service.registry.discovery_view
    return page([view(t) for t in rows], total, limit, offset, correlation_id(request))


@router.post("/execution/tools/{name}/validate")
async def validate_tool(name: str, request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(get_principal)):
    if principal.type is not PrincipalType.OWNER:
        raise PermissionDeniedError("tool validation is owner-only")
    service = _service(application)
    tool = service.registry.get_tool(name)
    adapter = service.adapters.get(tool.adapter_type)
    report = adapter.health() if adapter else {"status": "missing_dependency",
                                               "health_status": "unavailable", "details": {}}
    status = "disabled" if name == "desktop" else report["status"]
    updated = service.registry.apply_health(name, status=status,
                                            health_status=report["health_status"],
                                            details=report["details"])
    return ok(service.registry.admin_view(updated), correlation_id(request))


@router.post("/execution/tools/{name}/disable")
async def disable_tool(name: str, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(get_principal)):
    if principal.type is not PrincipalType.OWNER:
        raise PermissionDeniedError("disabling a tool is owner-only")
    service = _service(application)
    updated = service.registry.disable(name)
    return ok(service.registry.admin_view(updated), correlation_id(request))


# ---------------------------------------------------------------- workspaces
@router.get("/execution/workspaces")
async def list_workspaces(request: Request,
                          application: Application = Depends(get_application),
                          _: Principal = Depends(get_principal)):
    service = _service(application)
    rows = service.workspaces.list_workspaces()
    return ok([workspace_to_dict(r) for r in rows], correlation_id(request))


@router.post("/execution/workspaces/agent/{agent_id}", status_code=201)
async def ensure_agent_workspace(agent_id: str, request: Request,
                                 application: Application = Depends(get_application),
                                 principal: Principal = Depends(get_principal)):
    if principal.type is PrincipalType.AGENT and principal.id != agent_id:
        raise PermissionDeniedError("an agent may only ensure its own workspace")
    service = _service(application)
    row = service.workspaces.ensure_agent_workspace(agent_id)
    return ok(workspace_to_dict(row), correlation_id(request))


# ------------------------------------------------------------------ requests
@router.post("/execution/requests", status_code=201)
async def submit_request(body: ExecutionRequestIn, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(get_principal)):
    service = _service(application)
    execution_request = service.submit(principal, body)
    return ok(request_to_dict(execution_request), correlation_id(request))


@router.get("/execution/requests")
async def list_requests(request: Request, agent_id: str | None = None,
                        status: str | None = None,
                        limit: int = Query(default=50, ge=1, le=200),
                        offset: int = Query(default=0, ge=0),
                        application: Application = Depends(get_application),
                        _: Principal = Depends(get_principal)):
    service = _service(application)
    rows, total = service.list_requests(agent_id=agent_id, status=status,
                                        limit=limit, offset=offset)
    return page([request_to_dict(r) for r in rows], total, limit, offset,
                correlation_id(request))


@router.get("/execution/requests/{request_id}")
async def get_request(request_id: str, request: Request,
                      application: Application = Depends(get_application),
                      _: Principal = Depends(get_principal)):
    service = _service(application)
    execution_request = service.get_request(request_id)
    session = application.session_factory()
    try:
        runs = ExecutionRunRepository(session).for_request(request_id)
        run_dicts = [{
            "id": r.id, "attempt_number": r.attempt_number, "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "duration_ms": r.duration_ms, "exit_code": r.exit_code,
            "result": r.result, "result_summary": r.result_summary,
            "error_category": r.error_category, "resource_usage": r.resource_usage,
        } for r in runs]
    finally:
        session.close()
    data = request_to_dict(execution_request)
    data["runs"] = run_dicts
    return ok(data, correlation_id(request))


@router.post("/execution/requests/{request_id}/execute")
async def execute_request(request_id: str, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal)):
    service = _service(application)
    execution_request = await service.execute(principal, request_id)
    return ok(request_to_dict(execution_request), correlation_id(request))


@router.post("/execution/requests/{request_id}/cancel")
async def cancel_request(request_id: str, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(get_principal)):
    service = _service(application)
    execution_request = await service.cancel_async(principal, request_id)
    return ok(request_to_dict(execution_request), correlation_id(request))


@router.post("/execution/requests/{request_id}/request-approval")
async def request_approval(request_id: str, request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal)):
    service = _service(application)
    execution_request = service.request_approval(principal, request_id)
    return ok(request_to_dict(execution_request), correlation_id(request))


@router.get("/execution/requests/{request_id}/evidence")
async def request_evidence(request_id: str, request: Request,
                           application: Application = Depends(get_application),
                           _: Principal = Depends(get_principal)):
    service = _service(application)
    service.get_request(request_id)  # 404 if unknown
    return ok(service.evidence_for_request(request_id), correlation_id(request))


@router.get("/execution/requests/{request_id}/audit")
async def request_audit(request_id: str, request: Request,
                        application: Application = Depends(get_application),
                        _: Principal = Depends(get_principal)):
    service = _service(application)
    service.get_request(request_id)
    return ok(service.audit_for_request(request_id), correlation_id(request))


# ------------------------------------------------------- convenience wrappers
@router.post("/execution/files/{action}", status_code=201)
async def filesystem_action(action: str, body: WrapperIn, request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal)):
    execution_request = await _submit_and_maybe_execute(
        application, principal, _wrapper_payload(body, "filesystem", action),
        body.auto_execute)
    return ok(request_to_dict(execution_request), correlation_id(request))


@router.post("/execution/documents/{action}", status_code=201)
async def documents_action(action: str, body: WrapperIn, request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal)):
    execution_request = await _submit_and_maybe_execute(
        application, principal, _wrapper_payload(body, "documents", action),
        body.auto_execute)
    return ok(request_to_dict(execution_request), correlation_id(request))


@router.post("/execution/code/run", status_code=201)
async def code_run(body: WrapperIn, request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(get_principal)):
    execution_request = await _submit_and_maybe_execute(
        application, principal, _wrapper_payload(body, "code_python", "run"),
        body.auto_execute)
    return ok(request_to_dict(execution_request), correlation_id(request))


@router.post("/execution/api/{method}", status_code=201)
async def api_call(method: str, body: WrapperIn, request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(get_principal)):
    execution_request = await _submit_and_maybe_execute(
        application, principal, _wrapper_payload(body, "api_http", method.lower()),
        body.auto_execute)
    return ok(request_to_dict(execution_request), correlation_id(request))


@router.post("/execution/browser/{action}", status_code=201)
async def browser_action(action: str, body: WrapperIn, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(get_principal)):
    execution_request = await _submit_and_maybe_execute(
        application, principal, _wrapper_payload(body, "browser", action),
        body.auto_execute)
    return ok(request_to_dict(execution_request), correlation_id(request))


@router.get("/execution/browser/sessions")
async def list_browser_sessions(request: Request, agent_id: str | None = None,
                                status: str | None = None,
                                limit: int = Query(default=50, ge=1, le=200),
                                offset: int = Query(default=0, ge=0),
                                application: Application = Depends(get_application),
                                _: Principal = Depends(get_principal)):
    session = application.session_factory()
    try:
        rows, total = BrowserSessionRepository(session).list(
            agent_id=agent_id, status=status, limit=limit, offset=offset)
        return page([browser_session_to_dict(r) for r in rows], total, limit, offset,
                    correlation_id(request))
    finally:
        session.close()


@router.post("/execution/desktop/{action}", status_code=201)
async def desktop_action(action: str, body: WrapperIn, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(get_principal)):
    """The desktop tool is disabled in this environment; submissions are
    recorded and refused by policy — never simulated (§30)."""
    execution_request = await _submit_and_maybe_execute(
        application, principal, _wrapper_payload(body, "desktop", action),
        body.auto_execute)
    return ok(request_to_dict(execution_request), correlation_id(request))


# ----------------------------------------------------------------- workflows
@router.post("/execution/workflows", status_code=201)
async def create_workflow(body: WorkflowDefinitionIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal)):
    service = _service(application)
    row = service.workflows.create_definition(principal, body)
    return ok(workflow_definition_to_dict(row), correlation_id(request))


@router.get("/execution/workflows")
async def list_workflows(request: Request, limit: int = Query(default=50, ge=1, le=200),
                         offset: int = Query(default=0, ge=0),
                         application: Application = Depends(get_application),
                         _: Principal = Depends(get_principal)):
    session = application.session_factory()
    try:
        rows, total = WorkflowDefinitionRepository(session).list(limit, offset)
        return page([workflow_definition_to_dict(r) for r in rows], total, limit, offset,
                    correlation_id(request))
    finally:
        session.close()


@router.post("/execution/workflows/{definition_id}/runs", status_code=201)
async def start_workflow_run(definition_id: str, body: WorkflowRunIn, request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(get_principal)):
    service = _service(application)
    run = await service.workflows.start_run(principal, definition_id, body)
    return ok(_run_with_steps(application, run.id), correlation_id(request))


def _run_with_steps(application: Application, run_id: str) -> dict:
    session = application.session_factory()
    try:
        run = WorkflowRunRepository(session).get(run_id)
        if run is None:
            raise NotFoundError(f"workflow run '{run_id}' not found")
        steps = WorkflowStepRunRepository(session).for_run(run_id)
        return workflow_run_to_dict(run, steps)
    finally:
        session.close()


@router.get("/execution/workflow-runs")
async def list_workflow_runs(request: Request, status: str | None = None,
                             limit: int = Query(default=50, ge=1, le=200),
                             offset: int = Query(default=0, ge=0),
                             application: Application = Depends(get_application),
                             _: Principal = Depends(get_principal)):
    session = application.session_factory()
    try:
        rows, total = WorkflowRunRepository(session).list(status=status, limit=limit,
                                                          offset=offset)
        return page([workflow_run_to_dict(r) for r in rows], total, limit, offset,
                    correlation_id(request))
    finally:
        session.close()


@router.get("/execution/workflow-runs/{run_id}")
async def get_workflow_run(run_id: str, request: Request,
                           application: Application = Depends(get_application),
                           _: Principal = Depends(get_principal)):
    return ok(_run_with_steps(application, run_id), correlation_id(request))


@router.post("/execution/workflow-runs/{run_id}/pause")
async def pause_workflow_run(run_id: str, request: Request,
                             application: Application = Depends(get_application),
                             _: Principal = Depends(get_principal)):
    service = _service(application)
    service.workflows.pause(run_id)
    return ok(_run_with_steps(application, run_id), correlation_id(request))


@router.post("/execution/workflow-runs/{run_id}/resume")
async def resume_workflow_run(run_id: str, request: Request,
                              application: Application = Depends(get_application),
                              principal: Principal = Depends(get_principal)):
    service = _service(application)
    await service.workflows.resume(principal, run_id)
    return ok(_run_with_steps(application, run_id), correlation_id(request))


@router.post("/execution/workflow-runs/{run_id}/cancel")
async def cancel_workflow_run(run_id: str, request: Request,
                              application: Application = Depends(get_application),
                              _: Principal = Depends(get_principal)):
    service = _service(application)
    service.workflows.cancel(run_id)
    return ok(_run_with_steps(application, run_id), correlation_id(request))


# ------------------------------------------------------- standing authorizations
@router.post("/execution/standing-authorizations", status_code=201)
async def create_standing_authorization(body: StandingAuthorizationIn, request: Request,
                                        application: Application = Depends(get_application),
                                        principal: Principal = Depends(get_principal)):
    service = _service(application)
    row = service.create_standing_authorization(principal, body)
    return ok(standing_authorization_to_dict(row), correlation_id(request))


@router.get("/execution/standing-authorizations")
async def list_standing_authorizations(request: Request, status: str | None = None,
                                       limit: int = Query(default=50, ge=1, le=200),
                                       offset: int = Query(default=0, ge=0),
                                       application: Application = Depends(get_application),
                                       _: Principal = Depends(get_principal)):
    service = _service(application)
    rows, total = service.list_standing_authorizations(status=status, limit=limit,
                                                       offset=offset)
    return page([standing_authorization_to_dict(r) for r in rows], total, limit, offset,
                correlation_id(request))


@router.post("/execution/standing-authorizations/{auth_id}/revoke")
async def revoke_standing_authorization(auth_id: str, request: Request,
                                        application: Application = Depends(get_application),
                                        principal: Principal = Depends(get_principal)):
    service = _service(application)
    row = service.revoke_standing_authorization(principal, auth_id)
    return ok(standing_authorization_to_dict(row), correlation_id(request))


# --------------------------------------------------------- settings & status
@router.get("/execution/settings")
async def get_execution_settings(request: Request,
                                 application: Application = Depends(get_application),
                                 _: Principal = Depends(get_principal)):
    service = _service(application)
    return ok(service.get_settings(), correlation_id(request))


@router.patch("/execution/settings")
async def update_execution_settings(body: ExecutionSettingsIn, request: Request,
                                    application: Application = Depends(get_application),
                                    principal: Principal = Depends(get_principal)):
    service = _service(application)
    return ok(service.update_settings(principal, body.values), correlation_id(request))


@router.get("/execution/status")
async def execution_status(request: Request,
                           application: Application = Depends(get_application),
                           _: Principal = Depends(get_principal)):
    service = _service(application)
    return ok(service.metrics(), correlation_id(request))


@router.get("/execution/health-report")
async def execution_health_report(request: Request,
                                  application: Application = Depends(get_application),
                                  _: Principal = Depends(get_principal)):
    service = _service(application)
    return ok(service.startup_health_report(), correlation_id(request))


@router.post("/execution/emergency-stop")
async def execution_emergency_stop(request: Request,
                                   application: Application = Depends(get_application),
                                   principal: Principal = Depends(get_principal)):
    service = _service(application)
    report = await service.emergency_stop(principal)
    return ok(report, correlation_id(request))


@router.post("/execution/emergency-resume")
async def execution_emergency_resume(request: Request,
                                     application: Application = Depends(get_application),
                                     principal: Principal = Depends(get_principal)):
    service = _service(application)
    return ok(service.emergency_resume(principal), correlation_id(request))
