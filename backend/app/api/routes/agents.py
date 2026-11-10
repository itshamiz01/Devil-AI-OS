"""Agents API. P-01 shipped the read-only registry views; P-04 extends
this router with the Dynamic Agent Factory management surface (§19):
creation through the governed pipeline, lifecycle controls, capability
grants, assignment, health/metrics/events. All mutations are enforced
server-side by the factory service (manage_agents / owner checks)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...core.application import Application
from ...core.exceptions import NotFoundError
from ...database.repositories.core import AgentRepository
from ...permissions.models import Principal
from ..dependencies import correlation_id, get_application, get_principal
from ..schemas.agent_factory import (
    AgentConfigUpdateIn, AssignmentIn, CapabilityApproveIn,
    CapabilityRequestIn, CapabilityRevokeIn, ConfigRollbackIn,
    CreationRequirementIn, InferenceIn,
)
from ..schemas.agents import AgentOut
from ..schemas.common import ok, page

router = APIRouter(tags=["agents"])


@router.get("/agents")
async def list_agents(request: Request, limit: int = Query(default=50, ge=1, le=200),
                      offset: int = Query(default=0, ge=0),
                      application: Application = Depends(get_application),
                      _: Principal = Depends(get_principal)):
    session = application.session_factory()
    try:
        rows, total = AgentRepository(session).list(limit, offset)
        return page([AgentOut.from_model(a).model_dump() for a in rows], total, limit, offset,
                    correlation_id(request))
    finally:
        session.close()


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, request: Request,
                    application: Application = Depends(get_application),
                    _: Principal = Depends(get_principal)):
    session = application.session_factory()
    try:
        agent = AgentRepository(session).get(agent_id)
        if agent is None:
            raise NotFoundError(f"agent {agent_id} not found")
        return ok(AgentOut.from_model(agent).model_dump(), correlation_id(request))
    finally:
        session.close()


# ------------------------------------------------------- P-04 factory surface

@router.post("/agents", status_code=201)
async def create_agent(body: CreationRequirementIn, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(get_principal)):
    """Direct registration = the governed §7 creation pipeline in
    template mode (identical decisions/approvals to /agent-factory/create)."""
    result = await application.agents.create_agent(
        body.model_dump(exclude_none=True), principal=principal)
    return ok(result, correlation_id(request))


@router.patch("/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentConfigUpdateIn, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(get_principal)):
    result = await application.agents.update_agent_config(
        agent_id, body.changes, principal=principal, reason=body.reason)
    return ok(result, correlation_id(request))


@router.post("/agents/{agent_id}/suspend")
async def suspend_agent(agent_id: str, request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(get_principal)):
    agent = await application.agents.suspend_agent(agent_id, principal=principal)
    return ok(application.agents.agent_to_dict(agent), correlation_id(request))


@router.post("/agents/{agent_id}/resume")
async def resume_agent(agent_id: str, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(get_principal)):
    agent = await application.agents.resume_agent(agent_id, principal=principal)
    return ok(application.agents.agent_to_dict(agent), correlation_id(request))


@router.post("/agents/{agent_id}/retire")
async def retire_agent(agent_id: str, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(get_principal)):
    agent = await application.agents.retire_agent(agent_id, principal=principal)
    return ok(application.agents.agent_to_dict(agent), correlation_id(request))


@router.get("/agents/{agent_id}/permissions")
async def agent_permissions(agent_id: str, request: Request,
                            application: Application = Depends(get_application),
                            _: Principal = Depends(get_principal)):
    factory = application.agents
    factory.get_agent(agent_id)
    session = application.session_factory()
    try:
        from ...database.repositories.agents import CapabilityRepository
        names = {c.id: c.name for c in CapabilityRepository(session).list()}
    finally:
        session.close()
    grants = [{"id": g.id, "capability": names.get(g.capability_id),
               "capability_id": g.capability_id, "scope": g.scope,
               "approval_level": g.approval_level,
               "approval_reference": g.approval_reference,
               "status": g.status,
               "granted_at": g.granted_at.isoformat() if g.granted_at else None,
               "expires_at": g.expires_at.isoformat() if g.expires_at else None,
               "revoked_at": g.revoked_at.isoformat() if g.revoked_at else None}
              for g in factory.capabilities.grants_for_agent(agent_id)]
    return ok({"agent_id": agent_id, "grants": grants,
               "effective_capabilities":
                   factory.capabilities.granted_capability_names(agent_id)},
              correlation_id(request))


@router.post("/agents/{agent_id}/permissions/request")
async def request_capability(agent_id: str, body: CapabilityRequestIn,
                             request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(get_principal)):
    result = await application.agents.request_capability(
        agent_id, body.capability, principal=principal, reason=body.reason,
        scope=body.scope)
    return ok(result, correlation_id(request))


@router.post("/agents/{agent_id}/permissions/revoke")
async def revoke_capability(agent_id: str, body: CapabilityRevokeIn,
                            request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal)):
    result = await application.agents.revoke_capability(
        agent_id, body.capability, principal=principal)
    return ok(result, correlation_id(request))


@router.post("/agents/{agent_id}/permissions/approve")
async def approve_capability(agent_id: str, body: CapabilityApproveIn,
                             request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(get_principal)):
    result = await application.agents.approve_capability(
        agent_id, body.approval_id, approver=principal, approve=body.approve)
    return ok(result, correlation_id(request))


@router.post("/agents/{agent_id}/assign", status_code=201)
async def assign(agent_id: str, body: AssignmentIn, request: Request,
                 application: Application = Depends(get_application),
                 principal: Principal = Depends(get_principal)):
    result = await application.agents.assign(
        agent_id, body.model_dump(exclude_none=True), principal=principal)
    return ok(result, correlation_id(request))


@router.get("/agents/{agent_id}/assignments")
async def list_assignments(agent_id: str, request: Request,
                           limit: int = Query(default=50, ge=1, le=200),
                           offset: int = Query(default=0, ge=0),
                           application: Application = Depends(get_application),
                           _: Principal = Depends(get_principal)):
    rows, total = application.agents.list_assignments(agent_id, limit, offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/agents/{agent_id}/health")
async def agent_health(agent_id: str, request: Request,
                       application: Application = Depends(get_application),
                       _: Principal = Depends(get_principal)):
    return ok(application.agents.compute_health(agent_id), correlation_id(request))


@router.get("/agents/{agent_id}/metrics")
async def agent_metrics(agent_id: str, request: Request,
                        application: Application = Depends(get_application),
                        _: Principal = Depends(get_principal)):
    return ok(application.agents.agent_metrics(agent_id), correlation_id(request))


@router.get("/agents/{agent_id}/events")
async def agent_events(agent_id: str, request: Request,
                       limit: int = Query(default=50, ge=1, le=200),
                       application: Application = Depends(get_application),
                       _: Principal = Depends(get_principal)):
    return ok(application.agents.agent_events(agent_id, limit), correlation_id(request))


@router.get("/agents/{agent_id}/config-history")
async def agent_config_history(agent_id: str, request: Request,
                               application: Application = Depends(get_application),
                               _: Principal = Depends(get_principal)):
    return ok(application.agents.config_history(agent_id), correlation_id(request))


@router.post("/agents/{agent_id}/config/rollback")
async def rollback_config(agent_id: str, body: ConfigRollbackIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal)):
    result = await application.agents.rollback_agent_config(
        agent_id, version=body.version, principal=principal)
    return ok(result, correlation_id(request))


@router.post("/agents/{agent_id}/inference")
async def agent_inference(agent_id: str, body: InferenceIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal)):
    result = await application.agents.run_inference(
        agent_id, body.task_class, principal=principal)
    return ok(result, correlation_id(request))


@router.get("/agents/{agent_id}/memory")
async def agent_memory(agent_id: str, scope: str, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(get_principal)):
    result = application.agents.memory.read(
        requester=principal, agent_id=agent_id, scope=scope)
    return ok(result, correlation_id(request))
