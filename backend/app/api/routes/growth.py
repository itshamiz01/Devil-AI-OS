"""P-17 Customer Acquisition, Marketing & Revenue Growth Engine API.

Route map under /api/v1/growth:
- status / settings / integrations / agent-roles
- overview (§23A), per-business growth, portfolio (§20)
- brand profiles (§6), personas (§4.1), ICPs (§4.2), channels (§4.3)
- strategies (§5) with gate-respecting decisions
- campaigns (§7): lifecycle, approval, P-07 spend requests,
  metrics, auto-pause evaluation
- content (§6): full review workflow, approval, scheduling,
  owner-attested release
- leads (§8/§9): authorised sources only, dedupe, consent,
  suppression, scoring; sales pipeline (§10); CRM (§11)
- funnels (§12), SEO (§15), communications (§13: queue + honestly
  blocked dispatch), partnerships (§18)
- experiments (§14): pre-declared, P-08 handoff, declared-result
  conclusion
- attribution (§22), budget (§21), retention (§17),
  recommendations (§19)

Permissions mirror the house pattern: read = read_business_data,
write = modify_business_data, govern = approve_actions. The service
additionally enforces owner-only growth decisions and the §20
isolation rule — routes never widen service rules. Nothing here
executes a financial operation; spend exists only as P-07 records.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict

from ...core.application import Application
from ...growth.service import GrowthService
from ...permissions.models import Permission, Principal
from ..dependencies import (
    correlation_id, get_application, require_permission,
)
from ..schemas.common import ok

router = APIRouter(tags=["growth"])

READ = require_permission(Permission.READ_BUSINESS_DATA)
WRITE = require_permission(Permission.MODIFY_BUSINESS_DATA)
GOVERN = require_permission(Permission.APPROVE_ACTIONS)


def _svc(application: Application) -> GrowthService:
    return application.growth


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SettingsIn(_In):
    autonomy_level: int | None = None
    all_campaigns_paused: bool | None = None
    communications_stopped: bool | None = None
    outreach_suspended: bool | None = None
    marketing_spend_frozen: bool | None = None
    lead_score_weights: dict | None = None
    icp_weights: dict | None = None
    channel_weights: dict | None = None
    comm_frequency_limit_per_30d: int | None = None
    cac_expense_categories: list | None = None


class BrandIn(_In):
    brand_name: str | None = None
    identity: str | None = None
    tone_of_voice: str | None = None
    colors: list | None = None
    typography: str | None = None
    logo_refs: list | None = None
    messaging_guidelines: str | None = None
    prohibited_claims: list | None = None
    product_information: str | None = None
    assets: list | None = None


class PersonaIn(_In):
    segment: str
    needs: list | None = None
    problems: list | None = None
    motivations: list | None = None
    budget_sensitivity: str | None = None
    product_category: str | None = None
    objections: list | None = None
    discovery_channels: list | None = None
    buying_journey: str | None = None
    demographics: dict | None = None
    evidence: list | None = None
    is_fixture: bool = False


class IcpIn(_In):
    kind: str
    segment: str
    criteria: dict | None = None
    factor_scores: dict | None = None
    rationale: str | None = None
    is_fixture: bool = False


class ChannelIn(_In):
    channel_key: str
    evaluation: dict | None = None
    factor_scores: dict | None = None
    status: str | None = None
    notes: str | None = None


class StrategyIn(_In):
    title: str
    approach: str | None = None
    kind: str | None = None
    sections: dict | None = None


class DecideIn(_In):
    approval_id: str | None = None
    gate_override_reason: str | None = None


class CampaignIn(_In):
    name: str
    objective: str | None = None
    purpose: str | None = None
    strategy_id: str | None = None
    channel_evaluation_id: str | None = None
    channel_key: str | None = None
    target_audience: dict | None = None
    start_date: str | None = None
    end_date: str | None = None
    budget_ceiling_minor: int | None = None
    currency: str | None = None
    expected_results: dict | None = None
    creative_asset_refs: list | None = None
    landing_page: str | None = None
    conversion_event: str | None = None
    auto_pause_rules: dict | None = None
    is_fixture: bool = False


class TransitionIn(_In):
    target: str


class SpendIn(_In):
    amount_minor: int
    category: str | None = None
    purpose: str | None = None
    budget_id: str | None = None


class ContentIn(_In):
    kind: str
    title: str
    campaign_id: str | None = None
    brief: dict | None = None
    body: str | None = None


class ReviewIn(_In):
    section: str
    status: str
    notes: str | None = None


class ScheduleIn(_In):
    scheduled_at: str


class ReleaseIn(_In):
    external_ref: str


class LeadIn(_In):
    source: str
    source_channel: str | None = None
    contact: dict
    consent_status: str
    lawful_basis: str | None = None
    campaign_id: str | None = None
    segment: str | None = None
    interest: str | None = None
    is_fixture: bool = False


class ImportLeadsIn(_In):
    leads: list[dict]
    campaign_id: str | None = None


class ScoreIn(_In):
    factor_scores: dict


class ConsentIn(_In):
    consent_status: str
    lawful_basis: str | None = None


class SuppressIn(_In):
    reason: str


class OpportunityIn(_In):
    lead_id: str | None = None
    customer_id: str | None = None
    product: str | None = None
    stage: str | None = None
    probability: int | None = None
    estimated_value_minor: int | None = None
    currency: str | None = None
    expected_close_date: str | None = None
    next_action: str | None = None


class OpportunityTransitionIn(_In):
    target: str
    lost_reason: str | None = None
    probability: int | None = None


class CustomerIn(_In):
    contact: dict
    display_name: str | None = None
    lead_id: str | None = None
    dedupe_key: str | None = None
    p07_customer_ref: str | None = None
    lifecycle_stage: str | None = None
    segment: str | None = None
    consent_status: str | None = None
    preferences: dict | None = None
    acquisition_campaign_id: str | None = None
    acquisition_channel: str | None = None
    is_fixture: bool = False


class InteractionIn(_In):
    kind: str | None = None
    summary: str | None = None
    outcome: str | None = None


class FunnelIn(_In):
    stage: str
    count: int
    campaign_id: str | None = None
    period_start: str
    period_end: str
    source: str
    is_fixture: bool = False


class SeoIn(_In):
    kind: str
    source: str
    title: str
    data: dict | None = None
    period_start: str | None = None
    period_end: str | None = None


class TemplateIn(_In):
    name: str
    kind: str
    business_id: str
    subject: str | None = None
    body: str


class QueueIn(_In):
    template_id: str
    lead_id: str | None = None
    customer_id: str | None = None


class PartnershipIn(_In):
    partner_name: str
    kind: str | None = None
    terms: dict | None = None
    evaluation: dict | None = None
    contact_proposal: str | None = None
    notes: str | None = None


class PartnershipTransitionIn(_In):
    target: str
    approval_id: str | None = None


class ExperimentIn(_In):
    title: str
    hypothesis: str
    campaign_id: str | None = None
    control_description: str | None = None
    test_description: str | None = None
    primary_metric: str
    minimum_evaluation: dict
    duration_days: int
    budget_ceiling_minor: int | None = None
    max_acceptable_loss_minor: int | None = None


class ObservationsIn(_In):
    observations: dict


# ------------------------------------------------------------ status
@router.get("/growth/status")
async def status(principal: Principal = Depends(READ),
                 application: Application = Depends(get_application),
                 request: Request = None):
    return ok(_svc(application).engine_status(principal),
              correlation_id(request))


@router.get("/growth/settings")
async def get_settings(principal: Principal = Depends(READ),
                       application: Application = Depends(get_application),
                       request: Request = None):
    return ok(_svc(application).get_settings(), correlation_id(request))


@router.patch("/growth/settings")
async def update_settings(body: SettingsIn,
                          principal: Principal = Depends(GOVERN),
                          application: Application = Depends(get_application),
                          request: Request = None):
    patch = body.model_dump(exclude_none=True)
    return ok(_svc(application).update_settings(principal, patch),
              correlation_id(request))


@router.get("/growth/integrations")
async def integrations(principal: Principal = Depends(READ),
                       application: Application = Depends(get_application),
                       request: Request = None):
    return ok(_svc(application).integrations(principal),
              correlation_id(request))


@router.get("/growth/agent-roles")
async def agent_roles(principal: Principal = Depends(READ),
                      application: Application = Depends(get_application),
                      request: Request = None):
    return ok(_svc(application).agent_roles(principal),
              correlation_id(request))


# -------------------------------------------------- overview / portfolio
@router.get("/growth/overview")
async def overview(principal: Principal = Depends(READ),
                   application: Application = Depends(get_application),
                   request: Request = None):
    return ok(_svc(application).growth_overview(principal),
              correlation_id(request))


@router.get("/growth/portfolio")
async def portfolio(principal: Principal = Depends(READ),
                    application: Application = Depends(get_application),
                    request: Request = None):
    return ok(_svc(application).portfolio_growth(principal),
              correlation_id(request))


@router.get("/growth/recommendations")
async def recommendations(principal: Principal = Depends(READ),
                          application: Application = Depends(get_application),
                          request: Request = None):
    return ok(_svc(application).recommendations(principal),
              correlation_id(request))


@router.get("/growth/businesses/{business_id}")
async def business_growth(business_id: str,
                          principal: Principal = Depends(READ),
                          application: Application = Depends(get_application),
                          request: Request = None):
    return ok(_svc(application).business_growth(principal, business_id),
              correlation_id(request))


@router.get("/growth/businesses/{business_id}/attribution")
async def attribution(business_id: str,
                      principal: Principal = Depends(READ),
                      application: Application = Depends(get_application),
                      request: Request = None):
    return ok(_svc(application).attribution(principal, business_id),
              correlation_id(request))


@router.get("/growth/businesses/{business_id}/budget")
async def budget(business_id: str,
                 principal: Principal = Depends(READ),
                 application: Application = Depends(get_application),
                 request: Request = None):
    return ok(_svc(application).budget_view(principal, business_id),
              correlation_id(request))


@router.get("/growth/businesses/{business_id}/retention")
async def retention(business_id: str,
                    principal: Principal = Depends(READ),
                    application: Application = Depends(get_application),
                    request: Request = None):
    return ok(_svc(application).retention_analytics(principal, business_id),
              correlation_id(request))


# ------------------------------------------------------------- brand
@router.put("/growth/businesses/{business_id}/brand")
async def set_brand(business_id: str, body: BrandIn,
                    principal: Principal = Depends(WRITE),
                    application: Application = Depends(get_application),
                    request: Request = None):
    return ok(_svc(application).set_brand_profile(
        principal, business_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.get("/growth/businesses/{business_id}/brand")
async def get_brand(business_id: str,
                    principal: Principal = Depends(READ),
                    application: Application = Depends(get_application),
                    request: Request = None):
    return ok(_svc(application).get_brand_profile(principal, business_id),
              correlation_id(request))


# --------------------------------------------------- personas / ICPs
@router.post("/growth/businesses/{business_id}/personas", status_code=201)
async def create_persona(business_id: str, body: PersonaIn,
                         principal: Principal = Depends(WRITE),
                         application: Application = Depends(get_application),
                         request: Request = None):
    return ok(_svc(application).create_persona(
        principal, business_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.get("/growth/businesses/{business_id}/personas")
async def list_personas(business_id: str,
                        principal: Principal = Depends(READ),
                        application: Application = Depends(get_application),
                        request: Request = None):
    return ok(_svc(application).list_personas(principal, business_id),
              correlation_id(request))


@router.delete("/growth/personas/{persona_id}")
async def delete_persona(persona_id: str,
                         principal: Principal = Depends(WRITE),
                         application: Application = Depends(get_application),
                         request: Request = None):
    return ok(_svc(application).delete_persona(principal, persona_id),
              correlation_id(request))


@router.post("/growth/businesses/{business_id}/icps", status_code=201)
async def create_icp(business_id: str, body: IcpIn,
                     principal: Principal = Depends(WRITE),
                     application: Application = Depends(get_application),
                     request: Request = None):
    return ok(_svc(application).create_icp(
        principal, business_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.get("/growth/businesses/{business_id}/icps")
async def list_icps(business_id: str,
                    principal: Principal = Depends(READ),
                    application: Application = Depends(get_application),
                    request: Request = None):
    return ok(_svc(application).list_icps(principal, business_id),
              correlation_id(request))


# ------------------------------------------------------------ channels
@router.post("/growth/businesses/{business_id}/channels", status_code=201)
async def create_channel(business_id: str, body: ChannelIn,
                         principal: Principal = Depends(WRITE),
                         application: Application = Depends(get_application),
                         request: Request = None):
    return ok(_svc(application).create_channel_evaluation(
        principal, business_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.get("/growth/businesses/{business_id}/channels")
async def channel_ranking(business_id: str,
                          principal: Principal = Depends(READ),
                          application: Application = Depends(get_application),
                          request: Request = None):
    return ok(_svc(application).channel_ranking(principal, business_id),
              correlation_id(request))


# ---------------------------------------------------------- strategies
@router.post("/growth/businesses/{business_id}/strategies", status_code=201)
async def create_strategy(business_id: str, body: StrategyIn,
                          principal: Principal = Depends(WRITE),
                          application: Application = Depends(get_application),
                          request: Request = None):
    return ok(_svc(application).create_strategy(
        principal, business_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.get("/growth/strategies")
async def list_strategies(business_id: str | None = Query(default=None),
                          status: str | None = Query(default=None),
                          principal: Principal = Depends(READ),
                          application: Application = Depends(get_application),
                          request: Request = None):
    return ok(_svc(application).list_strategies(
        principal, business_id=business_id, status=status),
        correlation_id(request))


@router.post("/growth/strategies/{strategy_id}/approve")
async def approve_strategy(strategy_id: str, body: DecideIn,
                           principal: Principal = Depends(GOVERN),
                           application: Application = Depends(get_application),
                           request: Request = None):
    return ok(_svc(application).decide_strategy(
        principal, strategy_id, "approve",
        approval_id=body.approval_id,
        gate_override_reason=body.gate_override_reason),
        correlation_id(request))


@router.post("/growth/strategies/{strategy_id}/reject")
async def reject_strategy(strategy_id: str, body: DecideIn,
                          principal: Principal = Depends(GOVERN),
                          application: Application = Depends(get_application),
                          request: Request = None):
    return ok(_svc(application).decide_strategy(
        principal, strategy_id, "reject"), correlation_id(request))


# ----------------------------------------------------------- campaigns
@router.post("/growth/businesses/{business_id}/campaigns", status_code=201)
async def create_campaign(business_id: str, body: CampaignIn,
                          principal: Principal = Depends(WRITE),
                          application: Application = Depends(get_application),
                          request: Request = None):
    return ok(_svc(application).create_campaign(
        principal, business_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.get("/growth/campaigns")
async def list_campaigns(business_id: str | None = Query(default=None),
                         status: str | None = Query(default=None),
                         principal: Principal = Depends(READ),
                         application: Application = Depends(get_application),
                         request: Request = None):
    return ok(_svc(application).list_campaigns(
        principal, business_id=business_id, status=status),
        correlation_id(request))


@router.get("/growth/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str,
                       principal: Principal = Depends(READ),
                       application: Application = Depends(get_application),
                       request: Request = None):
    return ok(_svc(application).get_campaign(principal, campaign_id),
              correlation_id(request))


@router.get("/growth/campaigns/{campaign_id}/metrics")
async def campaign_metrics(campaign_id: str,
                           principal: Principal = Depends(READ),
                           application: Application = Depends(get_application),
                           request: Request = None):
    return ok(_svc(application).campaign_metrics(principal, campaign_id),
              correlation_id(request))


@router.post("/growth/campaigns/{campaign_id}/transition")
async def transition_campaign(campaign_id: str, body: TransitionIn,
                              principal: Principal = Depends(WRITE),
                              application: Application = Depends(get_application),
                              request: Request = None):
    return ok(_svc(application).transition_campaign(
        principal, campaign_id, body.target), correlation_id(request))


@router.post("/growth/campaigns/{campaign_id}/approve")
async def approve_campaign(campaign_id: str, body: DecideIn,
                           principal: Principal = Depends(GOVERN),
                           application: Application = Depends(get_application),
                           request: Request = None):
    return ok(_svc(application).approve_campaign(
        principal, campaign_id, approval_id=body.approval_id,
        gate_override_reason=body.gate_override_reason),
        correlation_id(request))


@router.post("/growth/campaigns/{campaign_id}/spend-requests",
             status_code=201)
async def prepare_spend(campaign_id: str, body: SpendIn,
                        principal: Principal = Depends(WRITE),
                        application: Application = Depends(get_application),
                        request: Request = None):
    return ok(_svc(application).prepare_spend_request(
        principal, campaign_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.post("/growth/campaigns/evaluate-auto-pause")
async def evaluate_auto_pause(principal: Principal = Depends(GOVERN),
                              application: Application = Depends(get_application),
                              request: Request = None):
    return ok(_svc(application).evaluate_auto_pause(principal),
              correlation_id(request))


# ------------------------------------------------------------- content
@router.post("/growth/businesses/{business_id}/content", status_code=201)
async def create_content(business_id: str, body: ContentIn,
                         principal: Principal = Depends(WRITE),
                         application: Application = Depends(get_application),
                         request: Request = None):
    return ok(_svc(application).create_content(
        principal, business_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.get("/growth/businesses/{business_id}/content")
async def list_content(business_id: str,
                       status: str | None = Query(default=None),
                       principal: Principal = Depends(READ),
                       application: Application = Depends(get_application),
                       request: Request = None):
    return ok(_svc(application).list_content(
        principal, business_id, status=status), correlation_id(request))


@router.post("/growth/content/{content_id}/review")
async def review_content(content_id: str, body: ReviewIn,
                         principal: Principal = Depends(WRITE),
                         application: Application = Depends(get_application),
                         request: Request = None):
    return ok(_svc(application).review_content(
        principal, content_id, body.section, body.status,
        body.notes or ""), correlation_id(request))


@router.post("/growth/content/{content_id}/approve")
async def approve_content(content_id: str,
                          principal: Principal = Depends(GOVERN),
                          application: Application = Depends(get_application),
                          request: Request = None):
    return ok(_svc(application).approve_content(principal, content_id),
              correlation_id(request))


@router.post("/growth/content/{content_id}/schedule")
async def schedule_content(content_id: str, body: ScheduleIn,
                           principal: Principal = Depends(WRITE),
                           application: Application = Depends(get_application),
                           request: Request = None):
    return ok(_svc(application).schedule_content(
        principal, content_id, body.scheduled_at), correlation_id(request))


@router.post("/growth/content/{content_id}/release")
async def release_content(content_id: str, body: ReleaseIn,
                          principal: Principal = Depends(WRITE),
                          application: Application = Depends(get_application),
                          request: Request = None):
    return ok(_svc(application).release_content(
        principal, content_id, body.external_ref), correlation_id(request))


# --------------------------------------------------------------- leads
@router.post("/growth/businesses/{business_id}/leads", status_code=201)
async def create_lead(business_id: str, body: LeadIn,
                      principal: Principal = Depends(WRITE),
                      application: Application = Depends(get_application),
                      request: Request = None):
    return ok(_svc(application).create_lead(
        principal, business_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.post("/growth/businesses/{business_id}/leads/import",
             status_code=201)
async def import_leads(business_id: str, body: ImportLeadsIn,
                       principal: Principal = Depends(WRITE),
                       application: Application = Depends(get_application),
                       request: Request = None):
    return ok(_svc(application).import_leads(
        principal, business_id, body.leads,
        campaign_id=body.campaign_id), correlation_id(request))


@router.get("/growth/businesses/{business_id}/leads")
async def list_leads(business_id: str,
                     stage: str | None = Query(default=None),
                     principal: Principal = Depends(READ),
                     application: Application = Depends(get_application),
                     request: Request = None):
    return ok(_svc(application).list_leads(
        principal, business_id, stage=stage), correlation_id(request))


@router.post("/growth/leads/{lead_id}/score")
async def score_lead(lead_id: str, body: ScoreIn,
                     principal: Principal = Depends(WRITE),
                     application: Application = Depends(get_application),
                     request: Request = None):
    return ok(_svc(application).score_lead(
        principal, lead_id, body.factor_scores), correlation_id(request))


@router.post("/growth/leads/{lead_id}/transition")
async def transition_lead(lead_id: str, body: TransitionIn,
                          principal: Principal = Depends(WRITE),
                          application: Application = Depends(get_application),
                          request: Request = None):
    return ok(_svc(application).transition_lead(
        principal, lead_id, body.target), correlation_id(request))


@router.post("/growth/leads/{lead_id}/consent")
async def set_consent(lead_id: str, body: ConsentIn,
                      principal: Principal = Depends(WRITE),
                      application: Application = Depends(get_application),
                      request: Request = None):
    return ok(_svc(application).set_consent(
        principal, lead_id, body.consent_status, body.lawful_basis),
        correlation_id(request))


@router.post("/growth/leads/{lead_id}/suppress")
async def suppress_lead(lead_id: str, body: SuppressIn,
                        principal: Principal = Depends(WRITE),
                        application: Application = Depends(get_application),
                        request: Request = None):
    return ok(_svc(application).suppress_lead(
        principal, lead_id, body.reason), correlation_id(request))


@router.get("/growth/businesses/{business_id}/suppressions")
async def list_suppressions(business_id: str,
                            principal: Principal = Depends(READ),
                            application: Application = Depends(get_application),
                            request: Request = None):
    return ok(_svc(application).list_suppressions(principal, business_id),
              correlation_id(request))


@router.post("/growth/leads/{lead_id}/convert", status_code=201)
async def convert_lead(lead_id: str,
                       principal: Principal = Depends(WRITE),
                       application: Application = Depends(get_application),
                       request: Request = None):
    return ok(_svc(application).convert_lead(principal, lead_id),
              correlation_id(request))


# --------------------------------------------------- sales pipeline
@router.post("/growth/businesses/{business_id}/opportunities",
             status_code=201)
async def create_opportunity(business_id: str, body: OpportunityIn,
                             principal: Principal = Depends(WRITE),
                             application: Application = Depends(get_application),
                             request: Request = None):
    return ok(_svc(application).create_opportunity(
        principal, business_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.post("/growth/opportunities/{opportunity_id}/transition")
async def transition_opportunity(opportunity_id: str,
                                 body: OpportunityTransitionIn,
                                 principal: Principal = Depends(WRITE),
                                 application: Application = Depends(get_application),
                                 request: Request = None):
    return ok(_svc(application).transition_opportunity(
        principal, opportunity_id, body.target,
        lost_reason=body.lost_reason, probability=body.probability),
        correlation_id(request))


@router.get("/growth/businesses/{business_id}/pipeline")
async def pipeline(business_id: str,
                   principal: Principal = Depends(READ),
                   application: Application = Depends(get_application),
                   request: Request = None):
    return ok(_svc(application).pipeline_summary(principal, business_id),
              correlation_id(request))


# ----------------------------------------------------------------- CRM
@router.post("/growth/businesses/{business_id}/customers", status_code=201)
async def create_customer(business_id: str, body: CustomerIn,
                          principal: Principal = Depends(WRITE),
                          application: Application = Depends(get_application),
                          request: Request = None):
    return ok(_svc(application).create_customer(
        principal, business_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.get("/growth/businesses/{business_id}/customers")
async def list_customers(business_id: str,
                         lifecycle_stage: str | None = Query(default=None),
                         principal: Principal = Depends(READ),
                         application: Application = Depends(get_application),
                         request: Request = None):
    return ok(_svc(application).list_customers(
        principal, business_id, lifecycle_stage=lifecycle_stage),
        correlation_id(request))


@router.get("/growth/customers/{customer_id}")
async def customer_detail(customer_id: str,
                          principal: Principal = Depends(READ),
                          application: Application = Depends(get_application),
                          request: Request = None):
    return ok(_svc(application).customer_detail(principal, customer_id),
              correlation_id(request))


@router.post("/growth/customers/{customer_id}/interactions",
             status_code=201)
async def record_interaction(customer_id: str, body: InteractionIn,
                             principal: Principal = Depends(WRITE),
                             application: Application = Depends(get_application),
                             request: Request = None):
    return ok(_svc(application).record_interaction(
        principal, customer_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.post("/growth/customers/{customer_id}/health")
async def recompute_health(customer_id: str,
                           principal: Principal = Depends(WRITE),
                           application: Application = Depends(get_application),
                           request: Request = None):
    return ok(_svc(application).recompute_customer_health(
        principal, customer_id), correlation_id(request))


# -------------------------------------------------------------- funnel
@router.post("/growth/businesses/{business_id}/funnel-events",
             status_code=201)
async def record_funnel(business_id: str, body: FunnelIn,
                        principal: Principal = Depends(WRITE),
                        application: Application = Depends(get_application),
                        request: Request = None):
    return ok(_svc(application).record_funnel_event(
        principal, business_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.get("/growth/businesses/{business_id}/funnel")
async def funnel(business_id: str,
                 campaign_id: str | None = Query(default=None),
                 principal: Principal = Depends(READ),
                 application: Application = Depends(get_application),
                 request: Request = None):
    return ok(_svc(application).funnel_summary(
        principal, business_id, campaign_id=campaign_id),
        correlation_id(request))


# ----------------------------------------------------------------- SEO
@router.post("/growth/businesses/{business_id}/seo-records",
             status_code=201)
async def create_seo(business_id: str, body: SeoIn,
                     principal: Principal = Depends(WRITE),
                     application: Application = Depends(get_application),
                     request: Request = None):
    return ok(_svc(application).create_seo_record(
        principal, business_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.get("/growth/businesses/{business_id}/seo")
async def seo_summary(business_id: str,
                      principal: Principal = Depends(READ),
                      application: Application = Depends(get_application),
                      request: Request = None):
    return ok(_svc(application).seo_summary(principal, business_id),
              correlation_id(request))


# ------------------------------------------------------- communications
@router.post("/growth/templates", status_code=201)
async def create_template(body: TemplateIn,
                          principal: Principal = Depends(WRITE),
                          application: Application = Depends(get_application),
                          request: Request = None):
    return ok(_svc(application).create_template(
        principal, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.post("/growth/communications", status_code=201)
async def queue_message(body: QueueIn,
                        principal: Principal = Depends(WRITE),
                        application: Application = Depends(get_application),
                        request: Request = None):
    return ok(_svc(application).queue_message(
        principal, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.get("/growth/businesses/{business_id}/communications")
async def list_messages(business_id: str,
                        status: str | None = Query(default=None),
                        principal: Principal = Depends(READ),
                        application: Application = Depends(get_application),
                        request: Request = None):
    return ok(_svc(application).list_messages(
        principal, business_id, status=status), correlation_id(request))


@router.post("/growth/communications/{message_id}/dispatch")
async def dispatch_message(message_id: str,
                           principal: Principal = Depends(WRITE),
                           application: Application = Depends(get_application),
                           request: Request = None):
    return ok(_svc(application).dispatch_message(principal, message_id),
              correlation_id(request))


# -------------------------------------------------------- partnerships
@router.post("/growth/businesses/{business_id}/partnerships",
             status_code=201)
async def create_partnership(business_id: str, body: PartnershipIn,
                             principal: Principal = Depends(WRITE),
                             application: Application = Depends(get_application),
                             request: Request = None):
    return ok(_svc(application).create_partnership(
        principal, business_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.get("/growth/businesses/{business_id}/partnerships")
async def list_partnerships(business_id: str,
                            principal: Principal = Depends(READ),
                            application: Application = Depends(get_application),
                            request: Request = None):
    return ok(_svc(application).list_partnerships(principal, business_id),
              correlation_id(request))


@router.post("/growth/partnerships/{partnership_id}/transition")
async def transition_partnership(partnership_id: str,
                                 body: PartnershipTransitionIn,
                                 principal: Principal = Depends(GOVERN),
                                 application: Application = Depends(get_application),
                                 request: Request = None):
    return ok(_svc(application).transition_partnership(
        principal, partnership_id, body.target,
        approval_id=body.approval_id), correlation_id(request))


# --------------------------------------------------------- experiments
@router.post("/growth/businesses/{business_id}/experiments",
             status_code=201)
async def create_experiment(business_id: str, body: ExperimentIn,
                            principal: Principal = Depends(WRITE),
                            application: Application = Depends(get_application),
                            request: Request = None):
    return ok(_svc(application).create_experiment(
        principal, business_id, body.model_dump(exclude_none=True)),
        correlation_id(request))


@router.get("/growth/experiments")
async def list_experiments(business_id: str | None = Query(default=None),
                           principal: Principal = Depends(READ),
                           application: Application = Depends(get_application),
                           request: Request = None):
    return ok(_svc(application).list_experiments(
        principal, business_id=business_id), correlation_id(request))


@router.post("/growth/experiments/{experiment_id}/approve")
async def approve_experiment(experiment_id: str, body: DecideIn,
                             principal: Principal = Depends(GOVERN),
                             application: Application = Depends(get_application),
                             request: Request = None):
    return ok(_svc(application).approve_experiment(
        principal, experiment_id, approval_id=body.approval_id),
        correlation_id(request))


@router.post("/growth/experiments/{experiment_id}/handoff")
async def handoff_experiment(experiment_id: str,
                             principal: Principal = Depends(GOVERN),
                             application: Application = Depends(get_application),
                             request: Request = None):
    return ok(_svc(application).handoff_experiment(
        principal, experiment_id), correlation_id(request))


@router.post("/growth/experiments/{experiment_id}/observations")
async def record_observations(experiment_id: str, body: ObservationsIn,
                              principal: Principal = Depends(WRITE),
                              application: Application = Depends(get_application),
                              request: Request = None):
    return ok(_svc(application).record_observations(
        principal, experiment_id, body.observations),
        correlation_id(request))


@router.post("/growth/experiments/{experiment_id}/conclude")
async def conclude_experiment(experiment_id: str,
                              principal: Principal = Depends(GOVERN),
                              application: Application = Depends(get_application),
                              request: Request = None):
    return ok(_svc(application).conclude_experiment(
        principal, experiment_id), correlation_id(request))
