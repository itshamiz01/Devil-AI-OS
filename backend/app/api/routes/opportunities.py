"""Opportunity Discovery API (P-03 §22).

Same envelope / auth / correlation conventions as P-01/P-02. Permission
gates: reads use ``read_business_data``; discovery, research and analysis
writes use ``modify_business_data``; scoring-config writes use
``modify_system_config`` plus the service's Owner-principal check
(ADR-005). There is deliberately NO endpoint that fetches an arbitrary
URL, launches anything, spends anything or sends anything (§26/§33).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...core.application import Application
from ...permissions.models import Principal
from ..dependencies import correlation_id, get_application, require_permission
from ..schemas.common import ok, page
from ..schemas.opportunities import (
    BriefCreate, BriefOut, CommercialAnalysisOut, CommercialAnalysisRequest,
    CompetitorCreate, CompetitorOut, DiscoverRequest, EvidenceCreate, EvidenceOut,
    MarketAnalysisOut, OpportunityCreate, OpportunityOut, RecheckRequest,
    ResearchSessionOut, ResearchStartRequest, ScoreOut, ScoringConfigUpdate,
    SourceCreate, SourceOut, TransitionRequest, ValidateRequest, ValidationOut,
)

router = APIRouter(tags=["opportunities"])

READ = "read_business_data"
WRITE = "modify_business_data"


# ------------------------------------------------------------------ status
@router.get("/opportunities/status")
async def engine_status(request: Request,
                        application: Application = Depends(get_application),
                        _: Principal = Depends(require_permission(READ))):
    return ok(application.opportunities.engine_status(), correlation_id(request))


@router.get("/opportunities/research-queue")
async def research_queue(request: Request,
                         application: Application = Depends(get_application),
                         _: Principal = Depends(require_permission(READ))):
    return ok(application.opportunities.research_queue(), correlation_id(request))


@router.get("/opportunities/rankings")
async def rankings(request: Request, by: str = "overall",
                   limit: int = Query(default=50, ge=1, le=200),
                   application: Application = Depends(get_application),
                   _: Principal = Depends(require_permission(READ))):
    return ok(application.opportunities.rankings(by=by, limit=limit),
              correlation_id(request))


@router.get("/opportunities/scoring-config")
async def get_scoring_config(request: Request,
                             application: Application = Depends(get_application),
                             _: Principal = Depends(require_permission(READ))):
    return ok(application.opportunities.scoring_config(), correlation_id(request))


@router.put("/opportunities/scoring-config")
async def update_scoring_config(body: ScoringConfigUpdate, request: Request,
                                application: Application = Depends(get_application),
                                principal: Principal = Depends(
                                    require_permission("modify_system_config"))):
    config = application.opportunities.update_scoring_weights(
        principal, body.weights, correlation_id=correlation_id(request))
    return ok(config, correlation_id(request))


# ------------------------------------------------------------------ briefs
@router.post("/opportunities/briefs", status_code=201)
async def create_brief(body: BriefCreate, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(require_permission(WRITE))):
    brief = application.opportunities.create_brief(
        principal, body.model_dump(), correlation_id=correlation_id(request))
    return ok(BriefOut.from_model(brief).model_dump(), correlation_id(request))


@router.get("/opportunities/briefs")
async def list_briefs(request: Request, status: str | None = None,
                      limit: int = Query(default=50, ge=1, le=200),
                      offset: int = Query(default=0, ge=0),
                      application: Application = Depends(get_application),
                      _: Principal = Depends(require_permission(READ))):
    rows, total = application.opportunities.list_briefs(status, limit, offset)
    return page([BriefOut.from_model(b).model_dump() for b in rows], total,
                limit, offset, correlation_id(request))


@router.post("/opportunities/discover", status_code=201)
async def discover(body: DiscoverRequest, request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(require_permission(WRITE))):
    result = await application.opportunities.discover(
        principal, body.brief_id, correlation_id=correlation_id(request))
    return ok({
        "brief": BriefOut.from_model(result["brief"]).model_dump(),
        "opportunities": [OpportunityOut.from_model(o).model_dump()
                          for o in result["opportunities"]],
    }, correlation_id(request))


# ------------------------------------------------------------- opportunities
@router.post("/opportunities", status_code=201)
async def create_opportunity(body: OpportunityCreate, request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(require_permission(WRITE))):
    opp = application.opportunities.create_opportunity(
        principal, body.model_dump(), correlation_id=correlation_id(request))
    return ok(OpportunityOut.from_model(opp).model_dump(), correlation_id(request))


@router.get("/opportunities")
async def list_opportunities(request: Request, status: str | None = None,
                             category: str | None = None, geography: str | None = None,
                             brief_id: str | None = None,
                             limit: int = Query(default=50, ge=1, le=200),
                             offset: int = Query(default=0, ge=0),
                             application: Application = Depends(get_application),
                             _: Principal = Depends(require_permission(READ))):
    rows, total = application.opportunities.list_opportunities(
        status, category, geography, brief_id, limit, offset)
    return page([OpportunityOut.from_model(o).model_dump() for o in rows], total,
                limit, offset, correlation_id(request))


@router.get("/opportunities/{opportunity_id}")
async def get_opportunity(opportunity_id: str, request: Request,
                          application: Application = Depends(get_application),
                          _: Principal = Depends(require_permission(READ))):
    opp = application.opportunities.get_opportunity(opportunity_id)
    return ok(OpportunityOut.from_model(opp).model_dump(), correlation_id(request))


@router.post("/opportunities/{opportunity_id}/transition")
async def transition_opportunity(opportunity_id: str, body: TransitionRequest,
                                 request: Request,
                                 application: Application = Depends(get_application),
                                 principal: Principal = Depends(require_permission(WRITE))):
    opp = await application.opportunities.transition(
        principal, opportunity_id, body.target, body.reason,
        correlation_id=correlation_id(request))
    return ok(OpportunityOut.from_model(opp).model_dump(), correlation_id(request))


# ----------------------------------------------------------------- research
@router.post("/opportunities/{opportunity_id}/research", status_code=201)
async def start_research(opportunity_id: str, body: ResearchStartRequest,
                         request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(require_permission(WRITE))):
    research = await application.opportunities.start_research(
        principal, opportunity_id, source_keys=body.source_keys,
        objective=body.objective, correlation_id=correlation_id(request))
    return ok(ResearchSessionOut.from_model(research).model_dump(), correlation_id(request))


@router.get("/opportunities/{opportunity_id}/research")
async def list_research(opportunity_id: str, request: Request,
                        limit: int = Query(default=50, ge=1, le=200),
                        offset: int = Query(default=0, ge=0),
                        application: Application = Depends(get_application),
                        _: Principal = Depends(require_permission(READ))):
    application.opportunities.get_opportunity(opportunity_id)
    rows, total = application.opportunities.list_research_sessions(opportunity_id, limit, offset)
    return page([ResearchSessionOut.from_model(s).model_dump() for s in rows], total,
                limit, offset, correlation_id(request))


@router.get("/research/{research_id}")
async def get_research(research_id: str, request: Request,
                       application: Application = Depends(get_application),
                       _: Principal = Depends(require_permission(READ))):
    research = application.opportunities.get_research_session(research_id)
    return ok(ResearchSessionOut.from_model(research).model_dump(), correlation_id(request))


@router.post("/opportunities/{opportunity_id}/recheck", status_code=201)
async def schedule_recheck(opportunity_id: str, body: RecheckRequest, request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(require_permission(WRITE))):
    research = application.opportunities.schedule_recheck(principal, opportunity_id, body.note)
    return ok(ResearchSessionOut.from_model(research).model_dump(), correlation_id(request))


# ----------------------------------------------------------------- evidence
@router.post("/opportunities/{opportunity_id}/evidence", status_code=201)
async def add_evidence(opportunity_id: str, body: EvidenceCreate, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(require_permission(WRITE))):
    record = application.opportunities.add_evidence(
        principal, opportunity_id, body.model_dump(),
        correlation_id=correlation_id(request))
    return ok(EvidenceOut.from_model(record).model_dump(), correlation_id(request))


@router.get("/opportunities/{opportunity_id}/evidence")
async def list_evidence(opportunity_id: str, request: Request,
                        limit: int = Query(default=200, ge=1, le=500),
                        offset: int = Query(default=0, ge=0),
                        application: Application = Depends(get_application),
                        _: Principal = Depends(require_permission(READ))):
    application.opportunities.get_opportunity(opportunity_id)
    rows, total = application.opportunities.list_evidence(opportunity_id, limit, offset)
    return page([EvidenceOut.from_model(e).model_dump() for e in rows], total,
                limit, offset, correlation_id(request))


# -------------------------------------------------------------- competitors
@router.post("/opportunities/{opportunity_id}/competitors", status_code=201)
async def add_competitor(opportunity_id: str, body: CompetitorCreate, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(require_permission(WRITE))):
    competitor = application.opportunities.add_competitor(
        principal, opportunity_id, body.model_dump())
    return ok(CompetitorOut.from_model(competitor).model_dump(), correlation_id(request))


@router.get("/opportunities/{opportunity_id}/competitors")
async def list_competitors(opportunity_id: str, request: Request,
                           application: Application = Depends(get_application),
                           _: Principal = Depends(require_permission(READ))):
    application.opportunities.get_opportunity(opportunity_id)
    rows = application.opportunities.list_competitors(opportunity_id)
    return ok([CompetitorOut.from_model(c).model_dump() for c in rows],
              correlation_id(request))


# ----------------------------------------------------------------- analyses
@router.post("/opportunities/{opportunity_id}/market-analysis")
async def market_analysis(opportunity_id: str, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(require_permission(WRITE))):
    row = application.opportunities.run_market_analysis(
        principal, opportunity_id, correlation_id=correlation_id(request))
    return ok(MarketAnalysisOut.from_model(row).model_dump(), correlation_id(request))


@router.post("/opportunities/{opportunity_id}/competitor-analysis")
async def competitor_analysis(opportunity_id: str, request: Request,
                              application: Application = Depends(get_application),
                              principal: Principal = Depends(require_permission(WRITE))):
    built = application.opportunities.run_competitor_analysis(principal, opportunity_id)
    return ok(built, correlation_id(request))


@router.post("/opportunities/{opportunity_id}/commercial-analysis")
async def commercial_analysis(opportunity_id: str, body: CommercialAnalysisRequest,
                              request: Request,
                              application: Application = Depends(get_application),
                              principal: Principal = Depends(require_permission(WRITE))):
    data = body.model_dump()
    if data.get("scenario_sales"):
        data["scenario_sales"] = {k: v.model_dump() if hasattr(v, "model_dump") else v
                                  for k, v in body.scenario_sales.items()}
    row = await application.opportunities.run_commercial_analysis(
        principal, opportunity_id, data, correlation_id=correlation_id(request))
    return ok(CommercialAnalysisOut.from_model(row).model_dump(), correlation_id(request))


# ------------------------------------------------------ scoring / validation
@router.post("/opportunities/{opportunity_id}/score")
async def score_opportunity(opportunity_id: str, request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(require_permission(WRITE))):
    score = await application.opportunities.score(
        principal, opportunity_id, correlation_id=correlation_id(request))
    return ok(ScoreOut.from_model(score).model_dump(), correlation_id(request))


@router.post("/opportunities/{opportunity_id}/validate")
async def validate_opportunity(opportunity_id: str, body: ValidateRequest,
                               request: Request,
                               application: Application = Depends(get_application),
                               principal: Principal = Depends(require_permission(WRITE))):
    record = await application.opportunities.validate(
        principal, opportunity_id, claimed_level=body.claimed_level,
        correlation_id=correlation_id(request))
    return ok(ValidationOut.from_model(record).model_dump(), correlation_id(request))


@router.get("/opportunities/{opportunity_id}/validation")
async def get_validation(opportunity_id: str, request: Request,
                         application: Application = Depends(get_application),
                         _: Principal = Depends(require_permission(READ))):
    application.opportunities.get_opportunity(opportunity_id)
    record = application.opportunities.latest_validation(opportunity_id)
    if record is None:
        return ok({"opportunity_id": opportunity_id, "validation": None,
                   "note": "no validation assessment has been run"}, correlation_id(request))
    return ok(ValidationOut.from_model(record).model_dump(), correlation_id(request))


# ---------------------------------------------------------------- reporting
@router.get("/opportunities/{opportunity_id}/report")
async def opportunity_report(opportunity_id: str, request: Request,
                             application: Application = Depends(get_application),
                             _: Principal = Depends(require_permission(READ))):
    return ok(application.opportunities.report(opportunity_id), correlation_id(request))


@router.get("/opportunities/{opportunity_id}/history")
async def opportunity_history(opportunity_id: str, request: Request,
                              limit: int = Query(default=200, ge=1, le=500),
                              offset: int = Query(default=0, ge=0),
                              application: Application = Depends(get_application),
                              _: Principal = Depends(require_permission(READ))):
    application.opportunities.get_opportunity(opportunity_id)
    rows, total = application.opportunities.history(opportunity_id, limit, offset)
    return page([{
        "id": h.id, "event_type": h.event_type, "from_status": h.from_status,
        "to_status": h.to_status, "actor": h.actor, "reason": h.reason,
        "details": h.details or {},
        "at": h.created_at.isoformat() if h.created_at else None,
    } for h in rows], total, limit, offset, correlation_id(request))


# ------------------------------------------------------------------ sources
@router.get("/sources")
async def list_sources(request: Request,
                       application: Application = Depends(get_application),
                       _: Principal = Depends(require_permission(READ))):
    rows = application.opportunities.list_sources()
    return ok([SourceOut.from_model(s).model_dump() for s in rows], correlation_id(request))


@router.post("/sources", status_code=201)
async def create_source(body: SourceCreate, request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(require_permission(WRITE))):
    data = body.model_dump()
    if not data.get("independence_group"):
        data["independence_group"] = data["source_key"]
    source = application.opportunities.create_source(principal, data)
    return ok(SourceOut.from_model(source).model_dump(), correlation_id(request))


@router.post("/sources/{source_id}/fetch")
async def fetch_source(source_id: str, request: Request,
                       application: Application = Depends(get_application),
                       _: Principal = Depends(require_permission(WRITE))):
    result = await application.opportunities.fetch_source(source_id)
    return ok(result, correlation_id(request))
