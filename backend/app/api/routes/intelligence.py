"""Master Intelligence API (P-02).

Same envelope / auth / correlation conventions as P-01. Permission gates:
mission intake & planning use ``submit_tasks``; plan approval uses
``approve_actions`` (Owner role only in the default policies); execution
uses ``execute_tools``; reads use ``read_system_data``; model profile
writes use ``modify_system_config`` AND an Owner-principal check in the
service (Article 0) — non-owner attempts are 403 and audited twice (the
permission engine audits its own check; the service records the attempt).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...core.application import Application
from ...permissions.models import Principal
from ..dependencies import correlation_id, get_application, require_permission
from ..schemas.common import ok, page
from ..schemas.intelligence import (
    DecisionOut, MissionCreate, MissionOut, ModelProfileOut,
    ModelProfileUpsert, PlanOut,
)

router = APIRouter(tags=["intelligence"])


# --------------------------------------------------------------- missions
@router.post("/missions", status_code=201)
async def create_mission(body: MissionCreate, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(require_permission("submit_tasks"))):
    mission = await application.intelligence.create_mission(
        principal, body.text, correlation_id=correlation_id(request))
    return ok(MissionOut.from_model(mission).model_dump(), correlation_id(request))


@router.get("/missions")
async def list_missions(request: Request, status: str | None = None,
                        limit: int = Query(default=50, ge=1, le=200),
                        offset: int = Query(default=0, ge=0),
                        application: Application = Depends(get_application),
                        _: Principal = Depends(require_permission("read_system_data"))):
    rows, total = application.intelligence.list_missions(status, limit, offset)
    return page([MissionOut.from_model(m).model_dump() for m in rows], total,
                limit, offset, correlation_id(request))


@router.get("/missions/{mission_id}")
async def get_mission(mission_id: str, request: Request,
                      application: Application = Depends(get_application),
                      _: Principal = Depends(require_permission("read_system_data"))):
    mission = application.intelligence.get_mission(mission_id)
    return ok(MissionOut.from_model(mission).model_dump(), correlation_id(request))


@router.post("/opportunities/{opportunity_id}/assess")
async def assess_opportunity(opportunity_id: str, request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(require_permission("read_system_data"))):
    """P-14 Stage B (DEF-E1): thin P-02 assessment of a P-03
    opportunity — P-02 consumes P-03's own evaluation report and
    records the assessment as a decision record. Read-only against
    P-03; no P-03 state changes."""
    result = await application.intelligence.assess_opportunity(
        principal, opportunity_id, correlation_id=correlation_id(request))
    return ok(result, correlation_id(request))


@router.post("/missions/{mission_id}/plan", status_code=201)
async def create_plan(mission_id: str, request: Request,
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(require_permission("submit_tasks"))):
    plan = await application.intelligence.create_plan(
        principal, mission_id, correlation_id=correlation_id(request))
    return ok(PlanOut.from_model(plan).model_dump(), correlation_id(request))


# ------------------------------------------------------------------ plans
@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str, request: Request,
                   application: Application = Depends(get_application),
                   _: Principal = Depends(require_permission("read_system_data"))):
    plan = application.intelligence.get_plan(plan_id)
    data = PlanOut.from_model(plan).model_dump()
    # Mission-scoped records (router selection happens before the plan row
    # exists, so its plan_id is NULL) belong to this plan's story too.
    decisions, _ = application.intelligence.recorder.list(
        mission_id=plan.mission_id, limit=500)
    decisions = [d for d in decisions if d.plan_id in (None, plan_id)]
    data["decision_records"] = [DecisionOut.from_model(d).model_dump() for d in decisions]
    return ok(data, correlation_id(request))


@router.post("/plans/{plan_id}/approve")
async def approve_plan(plan_id: str, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(require_permission("approve_actions"))):
    plan = await application.intelligence.approve_plan(
        principal, plan_id, correlation_id=correlation_id(request))
    return ok(PlanOut.from_model(plan).model_dump(), correlation_id(request))


@router.post("/plans/{plan_id}/execute")
async def execute_plan(plan_id: str, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(require_permission("execute_tools"))):
    plan = await application.intelligence.execute_plan(
        principal, plan_id, correlation_id=correlation_id(request))
    return ok(PlanOut.from_model(plan).model_dump(), correlation_id(request))


@router.get("/plans/{plan_id}/explanation")
async def plan_explanation(plan_id: str, request: Request,
                           application: Application = Depends(get_application),
                           _: Principal = Depends(require_permission("read_system_data"))):
    return ok(application.intelligence.explanation(plan_id), correlation_id(request))


# ----------------------------------------------------------------- models
@router.get("/models/profiles")
async def list_profiles(request: Request,
                        application: Application = Depends(get_application),
                        _: Principal = Depends(require_permission("read_system_data"))):
    profiles = application.intelligence.list_profiles()
    return ok([ModelProfileOut.from_model(p).model_dump() for p in profiles],
              correlation_id(request))


@router.put("/models/profiles/{name}")
async def upsert_profile(name: str, body: ModelProfileUpsert, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(
                             require_permission("modify_system_config"))):
    profile = application.intelligence.upsert_profile(
        principal, name, body.model_dump(exclude_unset=True),
        correlation_id=correlation_id(request))
    return ok(ModelProfileOut.from_model(profile).model_dump(), correlation_id(request))


@router.get("/models/status")
async def models_status(request: Request,
                        application: Application = Depends(get_application),
                        _: Principal = Depends(require_permission("read_system_data"))):
    return ok(await application.intelligence.models_status(), correlation_id(request))


# -------------------------------------------------------------- decisions
@router.get("/decisions")
async def list_decisions(request: Request, mission_id: str | None = None,
                         plan_id: str | None = None,
                         limit: int = Query(default=200, ge=1, le=500),
                         offset: int = Query(default=0, ge=0),
                         application: Application = Depends(get_application),
                         _: Principal = Depends(require_permission("read_system_data"))):
    rows, total = application.intelligence.recorder.list(
        mission_id=mission_id, plan_id=plan_id, limit=limit, offset=offset)
    return page([DecisionOut.from_model(d).model_dump() for d in rows], total,
                limit, offset, correlation_id(request))
