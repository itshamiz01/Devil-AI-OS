"""P-15 Performance, Reliability & Production Readiness API.

Reads require the existing ``read_system_data`` permission; writes
require ``modify_system_config`` at the route and are additionally
owner-gated inside the service (the portfolio pattern). P-15 adds no
authority of its own: backups run through the P-10 backup service,
financial suspension and operating mode stay P-10 endpoints, and
nothing here can bypass P-10 governance (§15).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ...core.application import Application
from ...permissions.models import Principal
from ...reliability.service import ReliabilityService
from ..dependencies import correlation_id, get_application, get_principal, require_permission
from ..schemas.common import ok, page

router = APIRouter(tags=["reliability"])

READ = require_permission("read_system_data")
WRITE = require_permission("modify_system_config")


def _svc(application: Application) -> ReliabilityService:
    return application.reliability


class IncidentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: str = Field(pattern="^(P0|P1|P2|P3)$")
    component: str = Field(min_length=1, max_length=80)
    kind: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    detail: str = Field(default="", max_length=4000)


class ResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_cause: str | None = Field(default=None, max_length=4000)
    response: str | None = Field(default=None, max_length=4000)
    recovery_actions: list | None = None
    preventive: str | None = Field(default=None, max_length=4000)


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_interval_seconds: int | None = None
    backup_max_age_hours: int | None = None
    stuck_task_minutes: int | None = None
    benchmark_tolerance_multiplier: float | None = None


class BenchmarkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(default="baseline", pattern="^(baseline|full)$")


@router.get("/reliability/overview")
async def overview(request: Request,
                   application: Application = Depends(get_application),
                   _: Principal = Depends(READ)):
    return ok(await _svc(application).overview(), correlation_id(request))


@router.get("/reliability/samples")
async def samples(request: Request, limit: int = Query(60, ge=1, le=500),
                  application: Application = Depends(get_application),
                  _: Principal = Depends(READ)):
    return ok(_svc(application).list_samples(limit=limit),
              correlation_id(request))


@router.post("/reliability/samples")
async def record_sample(request: Request,
                        application: Application = Depends(get_application),
                        _: Principal = Depends(WRITE)):
    return ok(_svc(application).record_sample(source="manual"),
              correlation_id(request))


@router.post("/reliability/evaluate")
async def evaluate(request: Request,
                   application: Application = Depends(get_application),
                   _: Principal = Depends(WRITE)):
    return ok(_svc(application).evaluate_incidents(), correlation_id(request))


@router.get("/reliability/incidents")
async def incidents(request: Request,
                    status: str | None = Query(None),
                    severity: str | None = Query(None),
                    limit: int = Query(50, ge=1, le=200),
                    offset: int = Query(0, ge=0),
                    application: Application = Depends(get_application),
                    _: Principal = Depends(READ)):
    rows, total = _svc(application).list_incidents(
        status=status, severity=severity, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/reliability/incidents")
async def create_incident(request: Request, body: IncidentIn,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal),
                          _: Principal = Depends(WRITE)):
    return ok(_svc(application).create_incident(principal, body.model_dump()),
              correlation_id(request))


@router.post("/reliability/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(request: Request, incident_id: str,
                               application: Application = Depends(get_application),
                               principal: Principal = Depends(get_principal),
                               _: Principal = Depends(WRITE)):
    return ok(_svc(application).acknowledge_incident(principal, incident_id),
              correlation_id(request))


@router.post("/reliability/incidents/{incident_id}/resolve")
async def resolve_incident(request: Request, incident_id: str, body: ResolveIn,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal),
                           _: Principal = Depends(WRITE)):
    return ok(_svc(application).resolve_incident(
        principal, incident_id, body.model_dump()), correlation_id(request))


@router.get("/reliability/readiness")
async def readiness(request: Request,
                    application: Application = Depends(get_application),
                    _: Principal = Depends(READ)):
    svc = _svc(application)
    return ok({"latest": svc.latest_readiness(),
               "history": svc.readiness_history(limit=10)},
              correlation_id(request))


@router.post("/reliability/readiness/compute")
async def compute_readiness(request: Request,
                            application: Application = Depends(get_application),
                            _: Principal = Depends(WRITE)):
    result = await _svc(application).compute_readiness()
    result = {k: v for k, v in result.items() if k != "evidence"}
    return ok(result, correlation_id(request))


@router.get("/reliability/benchmarks")
async def benchmarks(request: Request, limit: int = Query(20, ge=1, le=100),
                     application: Application = Depends(get_application),
                     _: Principal = Depends(READ)):
    return ok(_svc(application).list_benchmarks(limit=limit),
              correlation_id(request))


@router.post("/reliability/benchmarks")
async def run_benchmark(request: Request, body: BenchmarkIn,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(get_principal),
                        _: Principal = Depends(WRITE)):
    return ok(await _svc(application).run_benchmark(principal, body.kind),
              correlation_id(request))


@router.post("/reliability/backups")
async def create_backup(request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(get_principal),
                        _: Principal = Depends(WRITE)):
    return ok(_svc(application).create_backup(principal),
              correlation_id(request))


@router.get("/reliability/financial")
async def financial(request: Request,
                    application: Application = Depends(get_application),
                    _: Principal = Depends(READ)):
    return ok(_svc(application).financial_reliability(),
              correlation_id(request))


@router.get("/reliability/stability")
async def stability(request: Request,
                    application: Application = Depends(get_application),
                    _: Principal = Depends(READ)):
    return ok(_svc(application).stability_report(), correlation_id(request))


@router.get("/reliability/settings")
async def get_settings(request: Request,
                       application: Application = Depends(get_application),
                       _: Principal = Depends(READ)):
    return ok(_svc(application).get_settings(), correlation_id(request))


@router.put("/reliability/settings")
async def put_settings(request: Request, body: SettingsIn,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(get_principal),
                       _: Principal = Depends(WRITE)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return ok(_svc(application).update_settings(principal, patch),
              correlation_id(request))
