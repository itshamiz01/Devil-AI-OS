"""P-16 AI Economy Expansion Engine API.

Route map under /api/v1/economy:
- status / settings
- overview (§15A + §21 KPIs), classifications (§5.1/§15B),
  relationship-map (§5), decisions (§16)
- markets (§4.1), competitors + comparison (§13), countries +
  ranking (§14), segments (§8)
- opportunities (§4.2/§4.3): create, list, get, score, advance,
  gate override; discovery/run (detectors)
- strategies (§4.4): create, list, approve, reject, gate override
- capital (§15E): overview, scenarios; allocations (§9): create,
  list, decide; reinvestment (§10): create, list, decide
- assets (§7), commercialization: create, list, decide, handoff
- experiments (§11): create, list, approve, handoff (to P-08),
  sync-outcome
- diversification (§6/§15D): portfolio + per business
- risk (§12/§15H): compute, latest, list
- recommendations (§15I), patterns (§17)

Permissions mirror the house pattern: read = read_business_data,
write = modify_business_data, govern = approve_actions. The
service additionally enforces owner-only economy decisions and the
§20 isolation rule (aggregates are owner/system-only) — routes
never widen service rules. Nothing here executes a financial
operation: approvals endorse recommendations, handoffs enter
governed pipelines (P-03/P-08), and P-07 remains the only financial
authority.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ...core.application import Application
from ...economy.service import EconomyService
from ...permissions.models import Permission, Principal
from ..dependencies import (
    correlation_id, get_application, get_principal, require_permission,
)
from ..schemas.common import ok

router = APIRouter(tags=["economy"])

READ = require_permission(Permission.READ_BUSINESS_DATA)
WRITE = require_permission(Permission.MODIFY_BUSINESS_DATA)
GOVERN = require_permission(Permission.APPROVE_ACTIONS)


def _svc(application: Application) -> EconomyService:
    return application.economy


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SettingsIn(_In):
    autonomy_level: int | None = None
    expansion_paused: bool | None = None
    capital_commitments_frozen: bool | None = None
    evidence_gate_min_confidence: int | None = None
    evidence_gate_min_items: int | None = None
    concentration_threshold_bps: int | None = None
    factor_weights: dict | None = None
    country_weights: dict | None = None
    reinvestment_shares: dict | None = None


class ClassificationIn(_In):
    industry: str | None = None
    revenue_model: str | None = None
    market: str | None = None
    geographic_exposure: str | None = None
    capital_requirements_band: str | None = None
    strategic_importance: int | None = None
    notes: str | None = None


class DecisionIn(_In):
    business_id: str | None = None
    opportunity_id: str | None = None
    objective: str = Field(min_length=1, max_length=4000)
    supporting_evidence: list = []
    financial_assumptions: dict = {}
    expected_benefits: str = ""
    potential_losses: str = ""
    alternatives: list = []
    confidence: int = 0
    required_permissions: list = []
    recommended_action: str = ""


class OutcomeIn(_In):
    result: str = Field(pattern="^(success|failure|mixed|abandoned)$")
    notes: str = ""


class MarketIn(_In):
    title: str = Field(min_length=1, max_length=300)
    sector: str
    classification: str
    description: str = ""
    target_customers: str = ""
    demand_indicators: list = []
    competitor_notes: str = ""
    revenue_models: list = []
    startup_requirements: str = ""
    operating_costs: str = ""
    acquisition_challenges: str = ""
    legal_regulatory: str = ""
    risks: list = []
    evidence_sources: list = []
    confidence: int = 0
    figures_label: str = "estimates"
    p03_opportunity_id: str | None = None


class CompetitorIn(_In):
    name: str = Field(min_length=1, max_length=300)
    market: str = ""
    market_report_id: str | None = None
    products: list = []
    pricing_notes: str = ""
    business_model: str = ""
    positioning: str = ""
    strengths: list = []
    weaknesses: list = []
    source_refs: list = []


class CountryIn(_In):
    country: str = Field(min_length=1, max_length=120)
    region: str = ""
    criteria_scores: dict = {}
    weights: dict | None = None
    entry_checklist: dict = {}
    notes: str = ""
    status: str = "assessed"


class SegmentIn(_In):
    name: str = Field(min_length=1, max_length=300)
    kind: str
    business_id: str | None = None
    description: str = ""
    needs: list = []
    attributes: dict = {}
    international_checklist: dict = {}


class OpportunityIn(_In):
    title: str = Field(min_length=1, max_length=300)
    kind: str
    description: str = ""
    market_report_id: str | None = None
    p03_opportunity_id: str | None = None
    business_id: str | None = None
    market_tag: str | None = None
    factor_scores: dict = {}
    evidence: list = []
    estimated_investment_minor: int | None = None


class ScoreIn(_In):
    factor_scores: dict | None = None


class AdvanceIn(_In):
    target_stage: str


class OverrideIn(_In):
    reason: str = Field(min_length=1, max_length=2000)


class StrategyIn(_In):
    title: str = Field(min_length=1, max_length=300)
    horizon: str
    kind: str
    objective: str = ""
    business_id: str | None = None
    opportunity_id: str | None = None
    financial_requirements: dict = {}
    timeline: str = ""
    required_resources: list = []
    dependencies: list = []
    expected_outcomes: str = ""
    kpis: list = []
    risks: list = []
    exit_conditions: str = ""


class ApproveIn(_In):
    approval_id: str | None = None


class RejectIn(_In):
    reason: str = ""


class AllocationIn(_In):
    scenario: str
    business_id: str | None = None
    currency: str = "INR"
    proposed: dict = {}
    rationale: str = ""
    expected_benefits: str = ""
    downside: str = ""
    payback_assumptions: str = ""


class DecideIn(_In):
    approve: bool
    approval_id: str | None = None


class ReinvestmentIn(_In):
    business_id: str
    shares: dict | None = None
    adjustments_minor: int = 0


class AssetIn(_In):
    name: str = Field(min_length=1, max_length=300)
    kind: str
    owner_business_id: str | None = None
    ownership_status: str = "unverified"
    commercial_use_permitted: bool = False
    description: str = ""
    assessment: dict = {}
    is_fixture: bool = False


class CommercializationIn(_In):
    asset_id: str
    title: str | None = None
    rationale: str = ""
    pricing_model: str = ""
    estimated_cost_minor: int | None = None


class CommercializationDecideIn(_In):
    approve: bool
    reason: str = ""


class ExperimentIn(_In):
    title: str = Field(min_length=1, max_length=300)
    hypothesis: str = Field(min_length=1)
    target_market: str = ""
    business_id: str | None = None
    opportunity_id: str | None = None
    market_tag: str | None = None
    budget_ceiling_minor: int
    duration_days: int
    success_metrics: list = []
    failure_metrics: list = []
    risk_assessment: str = ""
    stop_conditions: list = []
    problem: str = ""
    target_customer: str = ""
    expected_outcome: str = ""
    minimum_evidence: str = ""
    evaluation_schedule: str = ""
    max_acceptable_loss_minor: int | None = None


# ------------------------------------------------------------ status
@router.get("/economy/status")
async def status(request: Request,
                 application: Application = Depends(get_application),
                 principal: Principal = Depends(get_principal),
                 _: Principal = Depends(READ)):
    return ok(_svc(application).engine_status(principal),
              correlation_id(request))


@router.get("/economy/settings")
async def get_settings(request: Request,
                       application: Application = Depends(get_application),
                       _: Principal = Depends(READ)):
    return ok(_svc(application).get_settings(), correlation_id(request))


@router.patch("/economy/settings")
async def update_settings(body: SettingsIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal),
                          _: Principal = Depends(WRITE)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return ok(_svc(application).update_settings(principal, patch),
              correlation_id(request))


# ---------------------------------------------------------- overview
@router.get("/economy/overview")
async def overview(request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(get_principal),
                   _: Principal = Depends(READ)):
    return ok(_svc(application).overview(principal),
              correlation_id(request))


@router.get("/economy/classifications")
async def classifications(request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal),
                          _: Principal = Depends(READ)):
    return ok(_svc(application).list_classifications(principal),
              correlation_id(request))


@router.post("/economy/classifications/{business_id}", status_code=201)
async def set_classification(business_id: str, body: ClassificationIn,
                             request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(get_principal),
                             _: Principal = Depends(WRITE)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return ok(_svc(application).set_classification(
        principal, business_id, data), correlation_id(request))


@router.get("/economy/relationship-map")
async def relationship_map(request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal),
                           _: Principal = Depends(READ)):
    return ok(_svc(application).relationship_map(principal),
              correlation_id(request))


@router.get("/economy/recommendations")
async def recommendations(request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal),
                          _: Principal = Depends(READ)):
    return ok(_svc(application).strategic_recommendations(principal),
              correlation_id(request))


@router.get("/economy/patterns")
async def patterns(request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(get_principal),
                   _: Principal = Depends(READ)):
    return ok(_svc(application).market_patterns(principal),
              correlation_id(request))


# ---------------------------------------------------------- decisions
@router.get("/economy/decisions")
async def list_decisions(request: Request,
                         business_id: str | None = Query(None),
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(get_principal),
                         _: Principal = Depends(READ)):
    return ok(_svc(application).list_decisions(
        principal, business_id=business_id), correlation_id(request))


@router.post("/economy/decisions", status_code=201)
async def create_decision(body: DecisionIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal),
                          _: Principal = Depends(WRITE)):
    return ok(_svc(application).create_decision(
        principal, body.model_dump()), correlation_id(request))


@router.post("/economy/decisions/{decision_id}/outcome")
async def decision_outcome(decision_id: str, body: OutcomeIn,
                           request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal),
                           _: Principal = Depends(GOVERN)):
    return ok(_svc(application).record_decision_outcome(
        principal, decision_id, body.model_dump()),
        correlation_id(request))


# ------------------------------------------------------------- markets
@router.get("/economy/markets")
async def list_markets(request: Request,
                       classification: str | None = Query(None),
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(get_principal),
                       _: Principal = Depends(READ)):
    return ok(_svc(application).list_market_reports(
        principal, classification=classification),
        correlation_id(request))


@router.post("/economy/markets", status_code=201)
async def create_market(body: MarketIn, request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(get_principal),
                        _: Principal = Depends(WRITE)):
    return ok(_svc(application).create_market_report(
        principal, body.model_dump()), correlation_id(request))


@router.get("/economy/markets/{report_id}")
async def get_market(report_id: str, request: Request,
                     application: Application = Depends(get_application),
                     principal: Principal = Depends(get_principal),
                     _: Principal = Depends(READ)):
    return ok(_svc(application).get_market_report(principal, report_id),
              correlation_id(request))


@router.get("/economy/competitors")
async def list_competitors(request: Request,
                           market: str | None = Query(None),
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal),
                           _: Principal = Depends(READ)):
    return ok(_svc(application).list_competitors(
        principal, market=market), correlation_id(request))


@router.post("/economy/competitors", status_code=201)
async def create_competitor(body: CompetitorIn, request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal),
                            _: Principal = Depends(WRITE)):
    return ok(_svc(application).create_competitor(
        principal, body.model_dump()), correlation_id(request))


@router.get("/economy/competitor-comparison")
async def competitor_comparison(request: Request,
                                market: str = Query(...),
                                application: Application = Depends(get_application),
                                principal: Principal = Depends(get_principal),
                                _: Principal = Depends(READ)):
    return ok(_svc(application).competitor_comparison(
        principal, market=market), correlation_id(request))


@router.get("/economy/countries/ranking")
async def country_ranking(request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal),
                          _: Principal = Depends(READ)):
    return ok(_svc(application).rank_countries(principal),
              correlation_id(request))


@router.post("/economy/countries", status_code=201)
async def create_country(body: CountryIn, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(get_principal),
                         _: Principal = Depends(WRITE)):
    return ok(_svc(application).create_country_assessment(
        principal, body.model_dump()), correlation_id(request))


@router.get("/economy/segments")
async def list_segments(request: Request,
                        business_id: str | None = Query(None),
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(get_principal),
                        _: Principal = Depends(READ)):
    return ok(_svc(application).list_segments(
        principal, business_id=business_id), correlation_id(request))


@router.post("/economy/segments", status_code=201)
async def create_segment(body: SegmentIn, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(get_principal),
                         _: Principal = Depends(WRITE)):
    return ok(_svc(application).create_segment(
        principal, body.model_dump()), correlation_id(request))


# -------------------------------------------------------- opportunities
@router.get("/economy/opportunities")
async def list_opportunities(request: Request,
                             stage: str | None = Query(None),
                             kind: str | None = Query(None),
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(get_principal),
                             _: Principal = Depends(READ)):
    return ok(_svc(application).list_opportunities(
        principal, stage=stage, kind=kind), correlation_id(request))


@router.post("/economy/opportunities", status_code=201)
async def create_opportunity(body: OpportunityIn, request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(get_principal),
                             _: Principal = Depends(WRITE)):
    return ok(_svc(application).create_opportunity(
        principal, body.model_dump()), correlation_id(request))


@router.get("/economy/opportunities/{opportunity_id}")
async def get_opportunity(opportunity_id: str, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal),
                          _: Principal = Depends(READ)):
    return ok(_svc(application).get_opportunity(
        principal, opportunity_id), correlation_id(request))


@router.post("/economy/opportunities/{opportunity_id}/score")
async def score_opportunity(opportunity_id: str, body: ScoreIn,
                            request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal),
                            _: Principal = Depends(WRITE)):
    return ok(_svc(application).score_opportunity(
        principal, opportunity_id, body.factor_scores),
        correlation_id(request))


@router.post("/economy/opportunities/{opportunity_id}/advance")
async def advance_opportunity(opportunity_id: str, body: AdvanceIn,
                              request: Request,
                              application: Application = Depends(get_application),
                              principal: Principal = Depends(get_principal),
                              _: Principal = Depends(GOVERN)):
    return ok(_svc(application).advance_opportunity(
        principal, opportunity_id, body.target_stage),
        correlation_id(request))


@router.post("/economy/opportunities/{opportunity_id}/override")
async def override_opportunity(opportunity_id: str, body: OverrideIn,
                               request: Request,
                               application: Application = Depends(get_application),
                               principal: Principal = Depends(get_principal),
                               _: Principal = Depends(GOVERN)):
    return ok(_svc(application).record_opportunity_override(
        principal, opportunity_id, body.reason),
        correlation_id(request))


@router.post("/economy/discovery/run")
async def run_discovery(request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(get_principal),
                        _: Principal = Depends(WRITE)):
    return ok(_svc(application).run_discovery(principal),
              correlation_id(request))


# ----------------------------------------------------------- strategies
@router.get("/economy/strategies")
async def list_strategies(request: Request,
                          horizon: str | None = Query(None),
                          status: str | None = Query(None),
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal),
                          _: Principal = Depends(READ)):
    return ok(_svc(application).list_strategies(
        principal, horizon=horizon, status=status),
        correlation_id(request))


@router.post("/economy/strategies", status_code=201)
async def create_strategy(body: StrategyIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal),
                          _: Principal = Depends(WRITE)):
    return ok(_svc(application).create_strategy(
        principal, body.model_dump()), correlation_id(request))


@router.post("/economy/strategies/{strategy_id}/approve")
async def approve_strategy(strategy_id: str, body: ApproveIn,
                           request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal),
                           _: Principal = Depends(GOVERN)):
    return ok(_svc(application).approve_strategy(
        principal, strategy_id, body.approval_id),
        correlation_id(request))


@router.post("/economy/strategies/{strategy_id}/reject")
async def reject_strategy(strategy_id: str, body: RejectIn,
                          request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal),
                          _: Principal = Depends(GOVERN)):
    return ok(_svc(application).reject_strategy(
        principal, strategy_id, body.reason), correlation_id(request))


@router.post("/economy/strategies/{strategy_id}/override")
async def override_strategy(strategy_id: str, body: OverrideIn,
                            request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal),
                            _: Principal = Depends(GOVERN)):
    return ok(_svc(application).record_strategy_override(
        principal, strategy_id, body.reason), correlation_id(request))


# -------------------------------------------------------------- capital
@router.get("/economy/capital")
async def capital_overview(request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal),
                           _: Principal = Depends(READ)):
    return ok(_svc(application).capital_overview(principal),
              correlation_id(request))


@router.get("/economy/capital/scenarios")
async def capital_scenarios(request: Request,
                            business_id: str = Query(...),
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal),
                            _: Principal = Depends(READ)):
    return ok(_svc(application).allocation_scenarios(
        principal, business_id=business_id), correlation_id(request))


@router.get("/economy/allocations")
async def list_allocations(request: Request,
                           status: str | None = Query(None),
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal),
                           _: Principal = Depends(READ)):
    return ok(_svc(application).list_allocations(
        principal, status=status), correlation_id(request))


@router.post("/economy/allocations", status_code=201)
async def create_allocation(body: AllocationIn, request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal),
                            _: Principal = Depends(WRITE)):
    return ok(_svc(application).create_allocation(
        principal, body.model_dump()), correlation_id(request))


@router.post("/economy/allocations/{recommendation_id}/decide")
async def decide_allocation(recommendation_id: str, body: DecideIn,
                            request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal),
                            _: Principal = Depends(GOVERN)):
    return ok(_svc(application).decide_allocation(
        principal, recommendation_id, approve=body.approve,
        approval_id=body.approval_id), correlation_id(request))


@router.get("/economy/reinvestment")
async def list_reinvestment(request: Request,
                            business_id: str | None = Query(None),
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal),
                            _: Principal = Depends(READ)):
    return ok(_svc(application).list_reinvestment_plans(
        principal, business_id=business_id), correlation_id(request))


@router.post("/economy/reinvestment", status_code=201)
async def create_reinvestment(body: ReinvestmentIn, request: Request,
                              application: Application = Depends(get_application),
                              principal: Principal = Depends(get_principal),
                              _: Principal = Depends(WRITE)):
    return ok(_svc(application).create_reinvestment_plan(
        principal, body.model_dump()), correlation_id(request))


@router.post("/economy/reinvestment/{plan_id}/decide")
async def decide_reinvestment(plan_id: str, body: DecideIn,
                              request: Request,
                              application: Application = Depends(get_application),
                              principal: Principal = Depends(get_principal),
                              _: Principal = Depends(GOVERN)):
    return ok(_svc(application).decide_reinvestment_plan(
        principal, plan_id, approve=body.approve,
        approval_id=body.approval_id), correlation_id(request))


# --------------------------------------------------------------- assets
@router.get("/economy/assets")
async def list_assets(request: Request,
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(get_principal),
                      _: Principal = Depends(READ)):
    return ok(_svc(application).list_assets(principal),
              correlation_id(request))


@router.post("/economy/assets", status_code=201)
async def create_asset(body: AssetIn, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(get_principal),
                       _: Principal = Depends(WRITE)):
    return ok(_svc(application).create_asset(
        principal, body.model_dump()), correlation_id(request))


@router.get("/economy/commercialization")
async def list_commercialization(request: Request,
                                 application: Application = Depends(get_application),
                                 principal: Principal = Depends(get_principal),
                                 _: Principal = Depends(READ)):
    return ok(_svc(application).list_commercialization(principal),
              correlation_id(request))


@router.post("/economy/commercialization", status_code=201)
async def create_commercialization(body: CommercializationIn,
                                   request: Request,
                                   application: Application = Depends(get_application),
                                   principal: Principal = Depends(get_principal),
                                   _: Principal = Depends(WRITE)):
    return ok(_svc(application).create_commercialization(
        principal, body.model_dump()), correlation_id(request))


@router.post("/economy/commercialization/{proposal_id}/decide")
async def decide_commercialization(proposal_id: str,
                                   body: CommercializationDecideIn,
                                   request: Request,
                                   application: Application = Depends(get_application),
                                   principal: Principal = Depends(get_principal),
                                   _: Principal = Depends(GOVERN)):
    return ok(_svc(application).decide_commercialization(
        principal, proposal_id, approve=body.approve,
        reason=body.reason), correlation_id(request))


@router.post("/economy/commercialization/{proposal_id}/handoff")
async def handoff_commercialization(proposal_id: str, request: Request,
                                    application: Application = Depends(get_application),
                                    principal: Principal = Depends(get_principal),
                                    _: Principal = Depends(GOVERN)):
    return ok(_svc(application).handoff_commercialization(
        principal, proposal_id), correlation_id(request))


# ----------------------------------------------------------- experiments
@router.get("/economy/experiments")
async def list_experiments(request: Request,
                           business_id: str | None = Query(None),
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal),
                           _: Principal = Depends(READ)):
    return ok(_svc(application).list_experiment_proposals(
        principal, business_id=business_id), correlation_id(request))


@router.post("/economy/experiments", status_code=201)
async def create_experiment(body: ExperimentIn, request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal),
                            _: Principal = Depends(WRITE)):
    return ok(_svc(application).create_experiment_proposal(
        principal, body.model_dump()), correlation_id(request))


@router.post("/economy/experiments/{proposal_id}/approve")
async def approve_experiment(proposal_id: str, body: ApproveIn,
                             request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(get_principal),
                             _: Principal = Depends(GOVERN)):
    return ok(_svc(application).approve_experiment_proposal(
        principal, proposal_id, body.approval_id),
        correlation_id(request))


@router.post("/economy/experiments/{proposal_id}/handoff")
async def handoff_experiment(proposal_id: str, request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(get_principal),
                             _: Principal = Depends(GOVERN)):
    return ok(_svc(application).handoff_experiment_proposal(
        principal, proposal_id), correlation_id(request))


@router.post("/economy/experiments/{proposal_id}/sync-outcome")
async def sync_experiment(proposal_id: str, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal),
                          _: Principal = Depends(GOVERN)):
    return ok(_svc(application).sync_experiment_outcome(
        principal, proposal_id), correlation_id(request))


# ------------------------------------------------------- diversification
@router.get("/economy/diversification")
async def portfolio_diversification(request: Request,
                                    application: Application = Depends(get_application),
                                    principal: Principal = Depends(get_principal),
                                    _: Principal = Depends(READ)):
    return ok(_svc(application).portfolio_diversification(principal),
              correlation_id(request))


@router.get("/economy/diversification/{business_id}")
async def business_diversification(business_id: str, request: Request,
                                   application: Application = Depends(get_application),
                                   principal: Principal = Depends(get_principal),
                                   _: Principal = Depends(READ)):
    return ok(_svc(application).business_diversification(
        principal, business_id), correlation_id(request))


# ---------------------------------------------------------------- risk
@router.post("/economy/risk/compute")
async def compute_risk(request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(get_principal),
                       _: Principal = Depends(WRITE)):
    return ok(_svc(application).compute_risk_assessment(principal),
              correlation_id(request))


@router.get("/economy/risk/latest")
async def latest_risk(request: Request,
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(get_principal),
                      _: Principal = Depends(READ)):
    return ok(_svc(application).latest_risk_assessment(principal),
              correlation_id(request))


@router.get("/economy/risk")
async def list_risk(request: Request,
                    application: Application = Depends(get_application),
                    principal: Principal = Depends(get_principal),
                    _: Principal = Depends(READ)):
    return ok(_svc(application).list_risk_assessments(principal),
              correlation_id(request))
