"""Business Creation Engine routes (P-06, §25).

Authorisation mirrors the P-03/P-05 pattern: route-level permission
checks against the P-01 catalogue (read_business_data /
modify_business_data / approve_actions) plus service-level owner checks
for governance writes. No route can publish, send, or move money —
those capabilities do not exist in this phase.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...permissions.models import Permission
from ..dependencies import correlation_id, get_application, require_permission
from ..schemas.business import (
    AssumptionIn, BusinessCreateIn, BusinessSettingsIn, CampaignIn,
    CreationApprovalRequestIn, DeclarationIn, EligibilityIn, EvidenceIn,
    LaunchIn, TemplateVersionIn, TransitionIn, WorkspaceProbeIn,
)
from ..schemas.common import ok, page

router = APIRouter(tags=["business"])

READ = require_permission(Permission.READ_BUSINESS_DATA)
WRITE = require_permission(Permission.MODIFY_BUSINESS_DATA)
APPROVE = require_permission(Permission.APPROVE_ACTIONS)


def _svc(request: Request):
    return get_application(request).business


@router.get("/business/status")
async def business_status(request: Request, _=Depends(READ)):
    return ok(_svc(request).engine_status())


@router.get("/business/settings")
async def get_business_settings(request: Request, _=Depends(READ)):
    return ok(_svc(request).get_settings())


@router.put("/business/settings")
async def update_business_settings(request: Request, payload: BusinessSettingsIn,
                                   principal=Depends(WRITE)):
    return ok(_svc(request).update_settings(principal, payload.values))


@router.get("/business/templates")
async def list_templates(request: Request, _=Depends(READ),
                         limit: int = Query(100, ge=1, le=500),
                         offset: int = Query(0, ge=0)):
    rows, total = _svc(request).list_templates()
    return page(rows[offset:offset + limit], total, limit, offset)


@router.get("/business/templates/{name}")
async def get_template(request: Request, name: str, _=Depends(READ)):
    return ok(_svc(request).get_template(name))


@router.post("/business/templates", status_code=201)
async def publish_template(request: Request, payload: TemplateVersionIn,
                           principal=Depends(WRITE),
                           cid: str = Depends(correlation_id)):
    return ok(await _svc(request).create_template_version(
        principal, payload.name, payload.definition, cid))


@router.post("/business/creation-approvals")
async def request_creation_approval(request: Request,
                                    payload: CreationApprovalRequestIn,
                                    principal=Depends(WRITE),
                                    cid: str = Depends(correlation_id)):
    return ok(await _svc(request).request_creation_approval(
        principal, payload.opportunity_id, payload.template_name,
        payload.reason, cid))


@router.post("/business/eligibility")
async def evaluate_eligibility(request: Request, payload: EligibilityIn,
                               principal=Depends(READ),
                               cid: str = Depends(correlation_id)):
    return ok(await _svc(request).evaluate_eligibility(
        principal, payload.opportunity_id, approval_id=payload.approval_id,
        template_name=payload.template_name, correlation_id=cid))


@router.post("/business/businesses", status_code=201)
async def create_business(request: Request, payload: BusinessCreateIn,
                          principal=Depends(WRITE),
                          cid: str = Depends(correlation_id)):
    return ok(await _svc(request).create_business(
        principal, payload.model_dump(), cid))


@router.get("/business/businesses")
async def list_businesses(request: Request, _=Depends(READ),
                          status: str | None = None,
                          opportunity_id: str | None = None,
                          limit: int = Query(100, ge=1, le=500),
                          offset: int = Query(0, ge=0)):
    rows, total = _svc(request).list_businesses(
        status=status, opportunity_id=opportunity_id,
        limit=limit, offset=offset)
    return page(rows, total, limit, offset)


@router.get("/business/businesses/{business_id}")
async def get_business(request: Request, business_id: str, _=Depends(READ)):
    return ok(_svc(request).get_business(business_id))


@router.post("/business/businesses/{business_id}/transition")
async def transition_business(request: Request, business_id: str,
                              payload: TransitionIn,
                              principal=Depends(WRITE),
                              cid: str = Depends(correlation_id)):
    return ok(await _svc(request).transition_business(
        principal, business_id, payload.target, reason=payload.reason,
        correlation_id=cid))


@router.get("/business/businesses/{business_id}/lifecycle")
async def lifecycle(request: Request, business_id: str, _=Depends(READ),
                    limit: int = Query(200, ge=1, le=500),
                    offset: int = Query(0, ge=0)):
    rows, total = _svc(request).lifecycle_events(business_id)
    return page(rows[offset:offset + limit], total, limit, offset)


@router.post("/business/businesses/{business_id}/declarations", status_code=201)
async def create_declaration(request: Request, business_id: str,
                             payload: DeclarationIn,
                             principal=Depends(WRITE),
                             cid: str = Depends(correlation_id)):
    return ok(await _svc(request).create_declaration(
        principal, business_id, payload.model_dump(), cid))


@router.get("/business/businesses/{business_id}/declarations")
async def list_declarations(request: Request, business_id: str,
                            _=Depends(READ)):
    rows, total = _svc(request).list_declarations(business_id)
    return page(rows, total, 200, 0)


@router.post("/business/businesses/{business_id}/declarations/{declaration_id}/approve")
async def approve_declaration(request: Request, business_id: str,
                              declaration_id: str,
                              principal=Depends(APPROVE),
                              cid: str = Depends(correlation_id)):
    return ok(await _svc(request).approve_declaration(
        principal, business_id, declaration_id, cid))


@router.post("/business/businesses/{business_id}/blueprint")
async def generate_blueprint(request: Request, business_id: str,
                             principal=Depends(WRITE),
                             cid: str = Depends(correlation_id)):
    return ok(await _svc(request).generate_blueprint(
        principal, business_id, cid))


@router.get("/business/businesses/{business_id}/blueprint")
async def get_blueprint(request: Request, business_id: str, _=Depends(READ)):
    return ok(_svc(request).get_blueprint(business_id))


@router.post("/business/businesses/{business_id}/blueprint/approve")
async def approve_blueprint(request: Request, business_id: str,
                            principal=Depends(APPROVE),
                            cid: str = Depends(correlation_id)):
    return ok(await _svc(request).approve_blueprint(
        principal, business_id, cid))


@router.post("/business/businesses/{business_id}/creation-run")
async def run_creation(request: Request, business_id: str,
                       principal=Depends(WRITE),
                       cid: str = Depends(correlation_id)):
    return ok(await _svc(request).run_creation(principal, business_id, cid))


@router.get("/business/businesses/{business_id}/product")
async def get_product(request: Request, business_id: str, _=Depends(READ)):
    return ok(_svc(request).get_product(business_id))


@router.get("/business/businesses/{business_id}/assets")
async def list_assets(request: Request, business_id: str, _=Depends(READ)):
    rows, total = _svc(request).list_assets(business_id)
    return page(rows, total, 200, 0)


@router.post("/business/businesses/{business_id}/channels/evaluate")
async def evaluate_channels(request: Request, business_id: str,
                            principal=Depends(WRITE),
                            cid: str = Depends(correlation_id)):
    return ok(await _svc(request).evaluate_channels(
        principal, business_id, cid))


@router.get("/business/businesses/{business_id}/channels")
async def list_channels(request: Request, business_id: str, _=Depends(READ)):
    rows, total = _svc(request).list_channels(business_id)
    return page(rows, total, 200, 0)


@router.post("/business/businesses/{business_id}/channels/{channel_id}/publish")
async def publish_attempt(request: Request, business_id: str, channel_id: str,
                          principal=Depends(WRITE),
                          cid: str = Depends(correlation_id)):
    return ok(await _svc(request).record_publish_attempt(
        principal, business_id, channel_id, cid))


@router.post("/business/businesses/{business_id}/readiness")
async def evaluate_readiness(request: Request, business_id: str,
                             principal=Depends(WRITE),
                             cid: str = Depends(correlation_id)):
    return ok(await _svc(request).evaluate_readiness(
        principal, business_id, cid))


@router.get("/business/businesses/{business_id}/readiness")
async def latest_readiness(request: Request, business_id: str,
                           _=Depends(READ)):
    return ok(_svc(request).latest_readiness(business_id))


@router.post("/business/businesses/{business_id}/launch/request")
async def request_launch(request: Request, business_id: str,
                         principal=Depends(WRITE),
                         cid: str = Depends(correlation_id)):
    return ok(await _svc(request).request_launch(principal, business_id, cid))


@router.post("/business/businesses/{business_id}/launch")
async def launch(request: Request, business_id: str, payload: LaunchIn,
                 principal=Depends(APPROVE),
                 cid: str = Depends(correlation_id)):
    return ok(await _svc(request).launch(
        principal, business_id, payload.approval_id, cid))


@router.get("/business/businesses/{business_id}/assignments")
async def assignments(request: Request, business_id: str, _=Depends(READ)):
    rows, total = _svc(request).assignments(business_id)
    return page(rows, total, 200, 0)


@router.post("/business/businesses/{business_id}/workspace-access")
async def workspace_probe(request: Request, business_id: str,
                          payload: WorkspaceProbeIn,
                          principal=Depends(READ),
                          cid: str = Depends(correlation_id)):
    return ok(await _svc(request).probe_workspace_access(
        principal, business_id, payload.agent_id, cid))


@router.post("/business/businesses/{business_id}/evidence", status_code=201)
async def add_evidence(request: Request, business_id: str,
                       payload: EvidenceIn, principal=Depends(WRITE)):
    return ok(_svc(request).add_evidence(
        principal, business_id, payload.model_dump()))


@router.get("/business/businesses/{business_id}/evidence")
async def list_evidence(request: Request, business_id: str, _=Depends(READ)):
    rows, total = _svc(request).list_evidence(business_id)
    return page(rows, total, 200, 0)


@router.post("/business/businesses/{business_id}/assumptions", status_code=201)
async def add_assumption(request: Request, business_id: str,
                         payload: AssumptionIn, principal=Depends(WRITE)):
    return ok(_svc(request).add_assumption(
        principal, business_id, payload.model_dump()))


@router.get("/business/businesses/{business_id}/assumptions")
async def list_assumptions(request: Request, business_id: str,
                           _=Depends(READ)):
    rows, total = _svc(request).list_assumptions(business_id)
    return page(rows, total, 200, 0)


@router.post("/business/businesses/{business_id}/campaigns", status_code=201)
async def create_campaign(request: Request, business_id: str,
                          payload: CampaignIn, principal=Depends(WRITE)):
    return ok(_svc(request).create_campaign_draft(
        principal, business_id, payload.model_dump()))


@router.get("/business/businesses/{business_id}/financial-inputs")
async def financial_inputs(request: Request, business_id: str,
                           _=Depends(READ)):
    return ok(_svc(request).financial_inputs(business_id))
