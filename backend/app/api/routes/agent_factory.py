"""P-04 Dynamic Agent Factory API (§19): templates, factory pipeline,
capabilities catalogue and factory administration. Authorization is
enforced in the service layer (manage_agents for mutations; owner-only
for approvals, settings and emergency controls)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...core.application import Application
from ...permissions.models import Principal
from ..dependencies import correlation_id, get_application, get_principal
from ..schemas.agent_factory import (
    CreationDecisionIn, CreationRequirementIn, EmergencyStopIn,
    SettingsUpdateIn, TemplateCloneIn, TemplateCreateIn, TemplatePublishIn,
    TemplateRestoreIn, TemplateUpdateIn,
)
from ..schemas.common import ok, page

router = APIRouter(tags=["agent-factory"])


def _template_out(factory, template) -> dict:
    current = factory.templates.get_version(template.id, template.current_version) \
        if template.current_version else None
    return {
        "id": template.id, "name": template.name, "category": template.category,
        "description": template.description, "status": template.status,
        "current_version": template.current_version,
        "published_version": template.published_version,
        "current_validation_status": current.validation_status if current else None,
        "current_validation_errors": current.validation_errors if current else [],
        "created_by": template.created_by_id,
        "created_at": template.created_at.isoformat() if template.created_at else None,
    }


def _version_out(row) -> dict:
    return {
        "template_id": row.template_id, "version": row.version,
        "configuration": row.configuration,
        "validation_status": row.validation_status,
        "validation_errors": row.validation_errors,
        "created_by": row.created_by_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ------------------------------------------------------------------ templates
@router.get("/agent-templates")
async def list_templates(request: Request,
                         limit: int = Query(default=50, ge=1, le=200),
                         offset: int = Query(default=0, ge=0),
                         application: Application = Depends(get_application),
                         _: Principal = Depends(get_principal)):
    rows, total = application.agents.templates.list(limit, offset)
    return page([_template_out(application.agents, t) for t in rows],
                total, limit, offset, correlation_id(request))


@router.post("/agent-templates", status_code=201)
async def create_template(body: TemplateCreateIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal)):
    factory = application.agents
    factory._require_manage(principal, "agent_factory.template_create")
    template = factory.templates.create(
        principal, name=body.name, category=body.category,
        description=body.description, configuration=body.configuration,
        settings=factory.settings_values())
    return ok(_template_out(factory, template), correlation_id(request))


@router.get("/agent-templates/{template_id}")
async def get_template(template_id: str, request: Request,
                       application: Application = Depends(get_application),
                       _: Principal = Depends(get_principal)):
    factory = application.agents
    template = factory.templates.get(template_id)
    data = _template_out(factory, template)
    if template.published_version:
        data["published_configuration"] = factory.templates.get_version(
            template_id, template.published_version).configuration
    return ok(data, correlation_id(request))


@router.patch("/agent-templates/{template_id}")
async def update_template(template_id: str, body: TemplateUpdateIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal)):
    factory = application.agents
    factory._require_manage(principal, "agent_factory.template_update")
    template = factory.templates.update(
        principal, template_id, configuration=body.configuration,
        description=body.description, settings=factory.settings_values())
    return ok(_template_out(factory, template), correlation_id(request))


@router.post("/agent-templates/{template_id}/clone")
async def clone_template(template_id: str, body: TemplateCloneIn, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(get_principal)):
    factory = application.agents
    factory._require_manage(principal, "agent_factory.template_clone")
    template = factory.templates.clone(
        principal, template_id, new_name=body.new_name,
        settings=factory.settings_values())
    return ok(_template_out(factory, template), correlation_id(request))


@router.post("/agent-templates/{template_id}/validate")
async def validate_template(template_id: str, request: Request,
                            version: int | None = None,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal)):
    factory = application.agents
    row = factory.templates.validate(
        template_id, version=version, settings=factory.settings_values())
    return ok(_version_out(row), correlation_id(request))


@router.post("/agent-templates/{template_id}/publish")
async def publish_template(template_id: str, body: TemplatePublishIn, request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal)):
    factory = application.agents
    factory._require_manage(principal, "agent_factory.template_publish")
    template = factory.templates.publish(principal, template_id, version=body.version)
    return ok(_template_out(factory, template), correlation_id(request))


@router.post("/agent-templates/{template_id}/deprecate")
async def deprecate_template(template_id: str, request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(get_principal)):
    factory = application.agents
    factory._require_manage(principal, "agent_factory.template_deprecate")
    template = factory.templates.deprecate(principal, template_id)
    return ok(_template_out(factory, template), correlation_id(request))


@router.post("/agent-templates/{template_id}/restore")
async def restore_template(template_id: str, body: TemplateRestoreIn, request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal)):
    factory = application.agents
    factory._require_manage(principal, "agent_factory.template_restore")
    template = factory.templates.restore(
        principal, template_id, version=body.version,
        settings=factory.settings_values())
    return ok(_template_out(factory, template), correlation_id(request))


@router.get("/agent-templates/{template_id}/versions")
async def template_versions(template_id: str, request: Request,
                            application: Application = Depends(get_application),
                            _: Principal = Depends(get_principal)):
    rows = application.agents.templates.list_versions(template_id)
    return ok([_version_out(r) for r in rows], correlation_id(request))


@router.get("/agent-templates/{template_id}/compare")
async def compare_template_versions(template_id: str, from_version: int,
                                    to_version: int, request: Request,
                                    application: Application = Depends(get_application),
                                    _: Principal = Depends(get_principal)):
    factory = application.agents
    a = factory.templates.get_version(template_id, from_version)
    b = factory.templates.get_version(template_id, to_version)
    return ok(factory.templates.compare(a.configuration, b.configuration),
              correlation_id(request))


# -------------------------------------------------------------------- factory
@router.post("/agent-factory/evaluate")
async def evaluate_creation(body: CreationRequirementIn, request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal)):
    result = await application.agents.evaluate_creation(
        body.model_dump(exclude_none=True), principal=principal)
    return ok(result, correlation_id(request))


@router.post("/agent-factory/create", status_code=201)
async def create_via_factory(body: CreationRequirementIn, request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(get_principal)):
    result = await application.agents.create_agent(
        body.model_dump(exclude_none=True), principal=principal)
    return ok(result, correlation_id(request))


@router.get("/agent-factory/requests")
async def list_creation_requests(request: Request,
                                 decision: str | None = None,
                                 limit: int = Query(default=50, ge=1, le=200),
                                 offset: int = Query(default=0, ge=0),
                                 application: Application = Depends(get_application),
                                 _: Principal = Depends(get_principal)):
    rows, total = application.agents.list_creation_requests(decision, limit, offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/agent-factory/requests/{request_id}")
async def get_creation_request(request_id: str, request: Request,
                               application: Application = Depends(get_application),
                               _: Principal = Depends(get_principal)):
    return ok(application.agents.get_creation_request(request_id),
              correlation_id(request))


@router.post("/agent-factory/requests/{request_id}/approve")
async def approve_creation(request_id: str, body: CreationDecisionIn, request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal)):
    result = await application.agents.approve_creation(
        request_id, approver=principal, approve=True, notes=body.notes)
    return ok(result, correlation_id(request))


@router.post("/agent-factory/requests/{request_id}/reject")
async def reject_creation(request_id: str, body: CreationDecisionIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal)):
    result = await application.agents.approve_creation(
        request_id, approver=principal, approve=False, notes=body.notes)
    return ok(result, correlation_id(request))


# --------------------------------------------------------------- capabilities
@router.get("/agent-capabilities")
async def list_capabilities(request: Request,
                            application: Application = Depends(get_application),
                            _: Principal = Depends(get_principal)):
    caps = application.agents.capabilities.list_catalogue()
    return ok([{"id": c.id, "name": c.name, "description": c.description,
                "category": c.category, "risk_level": c.risk_level,
                "approval_level": c.approval_level, "action_class": c.action_class,
                "mapped_permission": c.mapped_permission, "supported": c.supported,
                "enabled": c.enabled} for c in caps], correlation_id(request))


# ------------------------------------------------------------------------ admin
@router.get("/agent-factory/status")
async def factory_status(request: Request,
                         application: Application = Depends(get_application),
                         _: Principal = Depends(get_principal)):
    return ok(application.agents.factory_status(), correlation_id(request))


@router.get("/agent-factory/resources")
async def factory_resources(request: Request,
                            application: Application = Depends(get_application),
                            _: Principal = Depends(get_principal)):
    return ok(application.agents.factory_resources(), correlation_id(request))


@router.get("/agent-factory/scaling")
async def factory_scaling(request: Request,
                          application: Application = Depends(get_application),
                          _: Principal = Depends(get_principal)):
    return ok(application.agents.scaling_evaluate(), correlation_id(request))


@router.get("/agent-factory/settings")
async def factory_settings(request: Request,
                           application: Application = Depends(get_application),
                           _: Principal = Depends(get_principal)):
    return ok(application.agents.get_settings(), correlation_id(request))


@router.patch("/agent-factory/settings")
async def update_factory_settings(body: SettingsUpdateIn, request: Request,
                                  application: Application = Depends(get_application),
                                  principal: Principal = Depends(get_principal)):
    return ok(application.agents.update_settings(principal, body.updates),
              correlation_id(request))


@router.post("/agent-factory/emergency-stop")
async def emergency_stop(body: EmergencyStopIn, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(get_principal)):
    result = await application.agents.emergency_stop(
        principal=principal, scope=body.scope, agent_id=body.agent_id,
        reason=body.reason)
    return ok(result, correlation_id(request))


@router.post("/agent-factory/resume-operations")
async def resume_operations(request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal)):
    result = await application.agents.resume_operations(principal=principal)
    return ok(result, correlation_id(request))


@router.post("/agent-factory/maintenance")
async def run_maintenance(request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal)):
    result = await application.agents.run_maintenance(principal=principal)
    return ok(result, correlation_id(request))
