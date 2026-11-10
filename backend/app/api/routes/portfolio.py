"""Multi-business Coordination Engine API (P-13, §18/§19).

Route map under /api/v1/portfolio:
- status / settings
- portfolios: create, list, get, archive, survival-mode, overview,
  members (register/status/update), objectives
- businesses/{id}: profile, finance; compare
- relationships: create, list, transition
- intelligence: analyze, opportunities (submit/list/decide),
  recommendations (list/decide), concentration, risk
  (assess/latest)
- services: create, list, status, access (request/decide/activate/
  revoke/list), usage (record/view), allocations (create/decide/
  list)
- resources: view, quotas, allocations (propose/decide/activate/
  release), reclaim
- access: grants (create/revoke/list), assignments (create/revoke/
  list), checks (agent data access, agent service access)
- workflows: create, list, authorize participation, start, refresh
- ventures: propose, list, decide, handoff
- strategy, reports (generate/list/get/export)

Permissions mirror the house pattern: read = read_business_data,
write = modify_business_data, govern = approve_actions. The service
additionally enforces owner-only portfolio decisions and the §20
isolation rules — routes never widen service rules. The two access
checks take the CALLER's principal (an agent checks its own access);
they are POST bodies so an agent's identity comes from its token,
never from a parameter.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...permissions.models import Permission
from ..dependencies import correlation_id, get_application, require_permission
from ..schemas import portfolio as S
from ..schemas.common import ok

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

READ = require_permission(Permission.READ_BUSINESS_DATA)
WRITE = require_permission(Permission.MODIFY_BUSINESS_DATA)
GOVERN = require_permission(Permission.APPROVE_ACTIONS)


def _svc(request: Request):
    return get_application(request).portfolio


# ------------------------------------------------------------------ engine
@router.get("/status")
async def status(request: Request, principal=Depends(READ)):
    return ok(_svc(request).engine_status(), correlation_id(request))


@router.get("/settings")
async def get_settings(request: Request, principal=Depends(READ)):
    return ok(_svc(request).get_settings(), correlation_id(request))


@router.patch("/settings")
async def update_settings(body: S.SettingsUpdate, request: Request,
                          principal=Depends(GOVERN)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return ok(_svc(request).update_settings(principal, patch),
              correlation_id(request))


# -------------------------------------------------------------- portfolios
@router.post("/portfolios", status_code=201)
async def create_portfolio(body: S.PortfolioCreate, request: Request,
                           principal=Depends(WRITE)):
    return ok(_svc(request).create_portfolio(principal, body.model_dump()),
              correlation_id(request))


@router.get("/portfolios")
async def list_portfolios(request: Request, principal=Depends(READ)):
    return ok(_svc(request).list_portfolios(principal),
              correlation_id(request))


@router.get("/portfolios/{portfolio_id}")
async def get_portfolio(portfolio_id: str, request: Request,
                        principal=Depends(READ)):
    return ok(_svc(request).get_portfolio(principal, portfolio_id),
              correlation_id(request))


@router.post("/portfolios/{portfolio_id}/archive")
async def archive_portfolio(portfolio_id: str, request: Request,
                            principal=Depends(GOVERN)):
    return ok(_svc(request).archive_portfolio(principal, portfolio_id),
              correlation_id(request))


@router.post("/portfolios/{portfolio_id}/survival-mode")
async def survival_mode(portfolio_id: str, body: S.SurvivalModeBody,
                        request: Request, principal=Depends(GOVERN)):
    return ok(_svc(request).set_survival_mode(
        principal, portfolio_id, body.enabled), correlation_id(request))


@router.get("/portfolios/{portfolio_id}/overview")
async def overview(portfolio_id: str, request: Request,
                   currency: str = Query("INR"),
                   principal=Depends(READ)):
    return ok(_svc(request).portfolio_overview(
        principal, portfolio_id, currency), correlation_id(request))


@router.get("/portfolios/{portfolio_id}/members")
async def members(portfolio_id: str, request: Request,
                  principal=Depends(READ)):
    return ok(_svc(request).list_members(principal, portfolio_id),
              correlation_id(request))


@router.post("/portfolios/{portfolio_id}/members", status_code=201)
async def register_member(portfolio_id: str, body: S.MembershipCreate,
                          request: Request, principal=Depends(WRITE)):
    return ok(_svc(request).register_business(
        principal, portfolio_id, body.model_dump()),
        correlation_id(request))


@router.patch("/portfolios/{portfolio_id}/members/{business_id}")
async def update_member(portfolio_id: str, business_id: str,
                        body: S.MembershipUpdate, request: Request,
                        principal=Depends(WRITE)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return ok(_svc(request).update_membership(
        principal, portfolio_id, business_id, patch),
        correlation_id(request))


@router.post("/portfolios/{portfolio_id}/members/{business_id}/status")
async def member_status(portfolio_id: str, business_id: str,
                        body: S.MembershipStatus, request: Request,
                        principal=Depends(GOVERN)):
    return ok(_svc(request).set_membership_status(
        principal, portfolio_id, business_id, body.status),
        correlation_id(request))


@router.get("/portfolios/{portfolio_id}/objectives")
async def objectives(portfolio_id: str, request: Request,
                     principal=Depends(READ)):
    return ok(_svc(request).list_objectives(principal, portfolio_id),
              correlation_id(request))


@router.post("/portfolios/{portfolio_id}/objectives", status_code=201)
async def create_objective(portfolio_id: str, body: S.ObjectiveCreate,
                           request: Request, principal=Depends(WRITE)):
    return ok(_svc(request).create_objective(
        principal, portfolio_id, body.model_dump()),
        correlation_id(request))


# -------------------------------------------------------------- businesses
@router.get("/businesses/{business_id}/profile")
async def business_profile(business_id: str, request: Request,
                           principal=Depends(READ)):
    return ok(_svc(request).business_profile(principal, business_id),
              correlation_id(request))


@router.get("/businesses/{business_id}/finance")
async def business_finance(business_id: str, request: Request,
                           principal=Depends(READ)):
    return ok(_svc(request).business_finance(principal, business_id),
              correlation_id(request))


@router.get("/compare")
async def compare(request: Request, ids: str = Query(...),
                  currency: str = Query("INR"), principal=Depends(READ)):
    business_ids = [part.strip() for part in ids.split(",") if part.strip()]
    return ok(_svc(request).compare_businesses(
        principal, business_ids, currency), correlation_id(request))


# ----------------------------------------------------------- relationships
@router.post("/relationships", status_code=201)
async def create_relationship(body: S.RelationshipCreate, request: Request,
                              principal=Depends(WRITE)):
    return ok(_svc(request).create_relationship(
        principal, body.model_dump()), correlation_id(request))


@router.get("/relationships")
async def list_relationships(request: Request,
                             portfolio_id: str | None = Query(None),
                             business_id: str | None = Query(None),
                             status: str | None = Query(None),
                             principal=Depends(READ)):
    return ok(_svc(request).list_relationships(
        principal, portfolio_id=portfolio_id, business_id=business_id,
        status=status),
        correlation_id(request))


@router.post("/relationships/{relationship_id}/transition")
async def transition_relationship(relationship_id: str,
                                  body: S.RelationshipTransition,
                                  request: Request,
                                  principal=Depends(GOVERN)):
    return ok(_svc(request).transition_relationship(
        principal, relationship_id, body.status), correlation_id(request))


# ------------------------------------------------------------ intelligence
@router.post("/portfolios/{portfolio_id}/analyze")
async def analyze(portfolio_id: str, request: Request,
                  principal=Depends(GOVERN)):
    return ok(_svc(request).analyze_portfolio(principal, portfolio_id),
              correlation_id(request))


@router.get("/portfolios/{portfolio_id}/opportunities")
async def opportunities(portfolio_id: str, request: Request,
                        status: str | None = Query(None),
                        principal=Depends(READ)):
    return ok(_svc(request).list_opportunities(
        principal, portfolio_id, status=status), correlation_id(request))


@router.post("/portfolios/{portfolio_id}/opportunities", status_code=201)
async def submit_opportunity(portfolio_id: str, body: S.OpportunitySubmit,
                             request: Request, principal=Depends(WRITE)):
    return ok(_svc(request).submit_opportunity(
        principal, portfolio_id, body.model_dump()),
        correlation_id(request))


@router.post("/opportunities/{opportunity_id}/decision")
async def decide_opportunity(opportunity_id: str, body: S.DecisionBody,
                             request: Request, principal=Depends(GOVERN)):
    return ok(_svc(request).decide_opportunity(
        principal, opportunity_id, body.decision, body.rationale),
        correlation_id(request))


@router.get("/portfolios/{portfolio_id}/recommendations")
async def recommendations(portfolio_id: str, request: Request,
                          status: str | None = Query(None),
                          principal=Depends(READ)):
    return ok(_svc(request).list_recommendations(
        principal, portfolio_id, status=status), correlation_id(request))


@router.post("/recommendations/{recommendation_id}/decision")
async def decide_recommendation(recommendation_id: str,
                                body: S.DecisionBody, request: Request,
                                principal=Depends(GOVERN)):
    return ok(_svc(request).decide_recommendation(
        principal, recommendation_id, body.decision, body.rationale),
        correlation_id(request))


@router.get("/portfolios/{portfolio_id}/concentration")
async def concentration(portfolio_id: str, request: Request,
                        currency: str = Query("INR"),
                        principal=Depends(READ)):
    return ok(_svc(request).concentration_view(
        principal, portfolio_id, currency), correlation_id(request))


@router.post("/portfolios/{portfolio_id}/risk/assess")
async def assess_risk(portfolio_id: str, request: Request,
                      principal=Depends(GOVERN)):
    return ok(_svc(request).assess_risk(principal, portfolio_id),
              correlation_id(request))


@router.get("/portfolios/{portfolio_id}/risk")
async def latest_risk(portfolio_id: str, request: Request,
                      principal=Depends(READ)):
    return ok(_svc(request).latest_risk(principal, portfolio_id),
              correlation_id(request))


# ---------------------------------------------------------------- services
@router.post("/services", status_code=201)
async def create_service(body: S.ServiceCreate, request: Request,
                         principal=Depends(WRITE)):
    return ok(_svc(request).create_service(principal, body.model_dump()),
              correlation_id(request))


@router.get("/services")
async def list_services(request: Request, principal=Depends(READ)):
    return ok(_svc(request).list_services(principal),
              correlation_id(request))


@router.post("/services/{service_id}/status")
async def service_status(service_id: str, body: S.ServiceStatusBody,
                         request: Request, principal=Depends(GOVERN)):
    return ok(_svc(request).set_service_status(
        principal, service_id, body.status), correlation_id(request))


@router.get("/services/{service_id}/access")
async def list_access(service_id: str, request: Request,
                      principal=Depends(READ)):
    return ok(_svc(request).list_access(principal, service_id),
              correlation_id(request))


@router.post("/services/{service_id}/access", status_code=201)
async def request_access(service_id: str, body: S.AccessRequest,
                         request: Request, principal=Depends(WRITE)):
    return ok(_svc(request).request_access(
        principal, service_id, body.model_dump()), correlation_id(request))


@router.post("/services/access/{access_id}/decision")
async def decide_access(access_id: str, body: S.ApproveBody,
                        request: Request, principal=Depends(GOVERN)):
    return ok(_svc(request).decide_access(
        principal, access_id, body.approve), correlation_id(request))


@router.post("/services/access/{access_id}/activate")
async def activate_access(access_id: str, request: Request,
                          principal=Depends(GOVERN)):
    return ok(_svc(request).activate_access(principal, access_id),
              correlation_id(request))


@router.post("/services/access/{access_id}/revoke")
async def revoke_access(access_id: str, request: Request,
                        principal=Depends(GOVERN)):
    return ok(_svc(request).revoke_access(principal, access_id),
              correlation_id(request))


@router.post("/services/{service_id}/usage", status_code=201)
async def record_usage(service_id: str, body: S.UsageRecord,
                       request: Request, principal=Depends(WRITE)):
    return ok(_svc(request).record_usage(
        principal, service_id, body.model_dump()), correlation_id(request))


@router.get("/services/{service_id}/usage")
async def usage_view(service_id: str, request: Request,
                     principal=Depends(READ)):
    return ok(_svc(request).usage_view(principal, service_id),
              correlation_id(request))


@router.post("/allocations", status_code=201)
async def create_allocation(body: S.AllocationCreate, request: Request,
                            principal=Depends(WRITE)):
    return ok(_svc(request).create_allocation(
        principal, body.model_dump()), correlation_id(request))


@router.get("/allocations")
async def list_allocations(request: Request,
                           service_id: str | None = Query(None),
                           principal=Depends(READ)):
    return ok(_svc(request).list_allocations(
        principal, service_id=service_id), correlation_id(request))


@router.post("/allocations/{allocation_id}/decision")
async def decide_allocation(allocation_id: str, body: S.ApproveBody,
                            request: Request, principal=Depends(GOVERN)):
    return ok(_svc(request).decide_allocation(
        principal, allocation_id, body.approve), correlation_id(request))


# --------------------------------------------------------------- resources
@router.get("/portfolios/{portfolio_id}/resources")
async def resource_view(portfolio_id: str, request: Request,
                        principal=Depends(READ)):
    return ok(_svc(request).resource_view(principal, portfolio_id),
              correlation_id(request))


@router.post("/portfolios/{portfolio_id}/quotas", status_code=201)
async def set_quota(portfolio_id: str, body: S.QuotaSet, request: Request,
                    principal=Depends(GOVERN)):
    return ok(_svc(request).set_quota(
        principal, portfolio_id, body.model_dump()),
        correlation_id(request))


@router.post("/portfolios/{portfolio_id}/resource-allocations",
             status_code=201)
async def propose_resource(portfolio_id: str, body: S.ResourcePropose,
                           request: Request, principal=Depends(WRITE)):
    return ok(_svc(request).propose_resource_allocation(
        principal, portfolio_id, body.model_dump()),
        correlation_id(request))


@router.post("/resource-allocations/{allocation_id}/decision")
async def decide_resource(allocation_id: str, body: S.ApproveBody,
                          request: Request, principal=Depends(GOVERN)):
    return ok(_svc(request).decide_resource_allocation(
        principal, allocation_id, body.approve), correlation_id(request))


@router.post("/resource-allocations/{allocation_id}/activate")
async def activate_resource(allocation_id: str, request: Request,
                            principal=Depends(GOVERN)):
    return ok(_svc(request).activate_resource_allocation(
        principal, allocation_id), correlation_id(request))


@router.post("/resource-allocations/{allocation_id}/release")
async def release_resource(allocation_id: str, request: Request,
                           principal=Depends(GOVERN)):
    return ok(_svc(request).release_resource_allocation(
        principal, allocation_id), correlation_id(request))


@router.post("/portfolios/{portfolio_id}/resources/reclaim")
async def reclaim(portfolio_id: str, request: Request,
                  principal=Depends(GOVERN)):
    return ok(_svc(request).reclaim_idle(principal, portfolio_id),
              correlation_id(request))


# ------------------------------------------------------------------ access
@router.post("/access/grants", status_code=201)
async def create_grant(body: S.GrantCreate, request: Request,
                       principal=Depends(GOVERN)):
    return ok(_svc(request).grant_access(principal, body.model_dump()),
              correlation_id(request))


@router.get("/access/grants")
async def list_grants(request: Request,
                      agent_id: str | None = Query(None),
                      business_id: str | None = Query(None),
                      principal=Depends(READ)):
    return ok(_svc(request).list_grants(
        principal, agent_id=agent_id, business_id=business_id),
        correlation_id(request))


@router.post("/access/grants/{grant_id}/revoke")
async def revoke_grant(grant_id: str, request: Request,
                       principal=Depends(GOVERN)):
    return ok(_svc(request).revoke_grant(principal, grant_id),
              correlation_id(request))


@router.post("/access/assignments", status_code=201)
async def create_assignment(body: S.AssignmentCreate, request: Request,
                            principal=Depends(GOVERN)):
    return ok(_svc(request).assign_agent(principal, body.model_dump()),
              correlation_id(request))


@router.get("/access/assignments")
async def list_assignments(request: Request,
                           agent_id: str | None = Query(None),
                           principal=Depends(READ)):
    return ok(_svc(request).list_assignments(principal, agent_id=agent_id),
              correlation_id(request))


@router.post("/access/assignments/{assignment_id}/revoke")
async def revoke_assignment(assignment_id: str, request: Request,
                            principal=Depends(GOVERN)):
    return ok(_svc(request).revoke_assignment(principal, assignment_id),
              correlation_id(request))


@router.post("/access/check")
async def check_access(body: S.AccessCheck, request: Request,
                       principal=Depends(READ)):
    """The caller's own checked cross-business access (§20)."""
    return ok(_svc(request).check_agent_access(
        principal, business_id=body.business_id, category=body.category),
        correlation_id(request))


@router.post("/access/check-service")
async def check_service(body: S.ServiceAccessCheck, request: Request,
                        principal=Depends(READ)):
    return ok(_svc(request).check_service_access(
        principal, service_id=body.service_id), correlation_id(request))


# --------------------------------------------------------------- workflows
@router.post("/portfolios/{portfolio_id}/workflows", status_code=201)
async def create_workflow(portfolio_id: str, body: S.WorkflowCreate,
                          request: Request, principal=Depends(WRITE)):
    return ok(_svc(request).create_portfolio_workflow(
        principal, portfolio_id, body.model_dump()),
        correlation_id(request))


@router.get("/portfolios/{portfolio_id}/workflows")
async def list_workflows(portfolio_id: str, request: Request,
                         principal=Depends(READ)):
    return ok(_svc(request).list_portfolio_workflows(
        principal, portfolio_id), correlation_id(request))


@router.post("/workflows/{workflow_id}/authorize")
async def authorize_participation(workflow_id: str,
                                  body: S.ParticipationAuthorize,
                                  request: Request,
                                  principal=Depends(GOVERN)):
    return ok(_svc(request).authorize_participation(
        principal, workflow_id, body.business_id),
        correlation_id(request))


@router.post("/workflows/{workflow_id}/start")
async def start_workflow(workflow_id: str, request: Request,
                         principal=Depends(GOVERN)):
    return ok(_svc(request).start_portfolio_workflow(
        principal, workflow_id), correlation_id(request))


@router.post("/workflows/{workflow_id}/refresh")
async def refresh_workflow(workflow_id: str, request: Request,
                           principal=Depends(READ)):
    return ok(_svc(request).refresh_portfolio_workflow(
        principal, workflow_id), correlation_id(request))


# ---------------------------------------------------------------- ventures
@router.post("/portfolios/{portfolio_id}/ventures", status_code=201)
async def propose_venture(portfolio_id: str, body: S.VentureCreate,
                          request: Request, principal=Depends(WRITE)):
    return ok(_svc(request).propose_venture(
        principal, portfolio_id, body.model_dump()),
        correlation_id(request))


@router.get("/portfolios/{portfolio_id}/ventures")
async def list_ventures(portfolio_id: str, request: Request,
                        principal=Depends(READ)):
    return ok(_svc(request).list_ventures(principal, portfolio_id),
              correlation_id(request))


@router.post("/ventures/{venture_id}/decision")
async def decide_venture(venture_id: str, body: S.ApproveBody,
                         request: Request, principal=Depends(GOVERN)):
    return ok(_svc(request).decide_venture(
        principal, venture_id, body.approve), correlation_id(request))


@router.post("/ventures/{venture_id}/handoff")
async def handoff_venture(venture_id: str, request: Request,
                          principal=Depends(GOVERN)):
    return ok(_svc(request).handoff_venture(principal, venture_id),
              correlation_id(request))


# ---------------------------------------------------------- finance/views
@router.get("/portfolios/{portfolio_id}/finance")
async def portfolio_finance(portfolio_id: str, request: Request,
                            currency: str = Query("INR"),
                            principal=Depends(READ)):
    return ok(_svc(request).portfolio_finance(
        principal, portfolio_id, currency), correlation_id(request))


@router.get("/portfolios/{portfolio_id}/strategy")
async def strategy(portfolio_id: str, request: Request,
                   currency: str = Query("INR"), principal=Depends(READ)):
    return ok(_svc(request).strategy_view(
        principal, portfolio_id, currency), correlation_id(request))


# ----------------------------------------------------------------- reports
@router.post("/portfolios/{portfolio_id}/reports", status_code=201)
async def generate_report(portfolio_id: str, body: S.ReportGenerate,
                          request: Request, principal=Depends(GOVERN)):
    return ok(_svc(request).generate_report(
        principal, portfolio_id, body.model_dump()),
        correlation_id(request))


@router.get("/portfolios/{portfolio_id}/reports")
async def list_reports(portfolio_id: str, request: Request,
                       principal=Depends(READ)):
    return ok(_svc(request).list_reports(principal, portfolio_id),
              correlation_id(request))


@router.get("/reports/{report_id}")
async def get_report(report_id: str, request: Request,
                     principal=Depends(READ)):
    return ok(_svc(request).get_report(principal, report_id),
              correlation_id(request))


@router.get("/reports/{report_id}/export")
async def export_report(report_id: str, request: Request,
                        principal=Depends(READ)):
    return ok(_svc(request).export_report(principal, report_id),
              correlation_id(request))
