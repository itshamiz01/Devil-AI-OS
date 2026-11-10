"""Survival and Scaling Engine API (P-08, §23).

Route map under /api/v1/survival:
- engine status / settings (owner-governed writes)
- per-business: monitoring (reading, observations, events, checks),
  health (evaluate, latest, snapshots), lifecycle (combined view,
  history, overlay record), pause control, decisions (create/list/
  get, approval request/review, execute), experiments (declare/
  list/get, approve, start, spend gate, stop-loss check, stop,
  evaluate, evaluations), scaling (assess, assessments, plans,
  plan approval), recovery (plans, conclude), closure (propose,
  reviews, advance, execute), forecasts (create/list/vs-actual),
  outcomes (record/list)
- portfolio: overview, concentration, allocations, resources
- analyst: deterministic structured queries (§19)

Permissions mirror P-07: read = read_business_data, write =
modify_business_data, approve = approve_actions. Per-business
access mirrors P-07's FinancialService.assert_business_access.
There is deliberately NO delete route for experiments,
evaluations, snapshots, decisions, forecasts or outcomes (§9.5):
failed experiments and closure history are permanent records.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...permissions.models import Permission
from ..dependencies import correlation_id, get_application, require_permission
from ..schemas import survival as S
from ..schemas.common import ok, page

router = APIRouter(prefix="/survival", tags=["survival"])

READ = require_permission(Permission.READ_BUSINESS_DATA)
WRITE = require_permission(Permission.MODIFY_BUSINESS_DATA)
APPROVE = require_permission(Permission.APPROVE_ACTIONS)


def _svc(request: Request):
    return get_application(request).survival


def _check(request: Request, principal, business_id: str) -> None:
    get_application(request).survival.business_access_check(
        principal, business_id)


# ------------------------------------------------------------------ engine
@router.get("/status")
async def status(request: Request, principal=Depends(READ)):
    return ok(_svc(request).status(), correlation_id(request))


@router.get("/settings")
async def get_settings(request: Request, principal=Depends(READ)):
    return ok(_svc(request).get_settings(), correlation_id(request))


@router.patch("/settings")
async def update_settings(request: Request, body: S.SettingsUpdateIn,
                          principal=Depends(APPROVE)):
    patch = {k: v for k, v in body.model_dump().items()
             if v is not None}
    return ok(_svc(request).update_settings(principal, patch),
              correlation_id(request))


# -------------------------------------------------------------- monitoring
@router.get("/businesses/{business_id}/reading")
async def reading(request: Request, business_id: str,
                  principal=Depends(READ)):
    _check(request, principal, business_id)
    return ok(_svc(request).monitoring.collect(business_id),
              correlation_id(request))


@router.post("/businesses/{business_id}/observations", status_code=201)
async def add_observation(request: Request, business_id: str,
                          body: S.ObservationIn,
                          principal=Depends(WRITE)):
    _check(request, principal, business_id)
    result = _svc(request).monitoring.record_observation(
        principal, business_id, body.model_dump())
    return ok(result, correlation_id(request))


@router.get("/businesses/{business_id}/observations")
async def list_observations(request: Request, business_id: str,
                            kind: str | None = None,
                            limit: int = Query(100, ge=1, le=500),
                            principal=Depends(READ)):
    _check(request, principal, business_id)
    rows = _svc(request).monitoring.list_observations(
        business_id, kind=kind, limit=limit)
    return page(rows, len(rows), limit, 0, correlation_id(request))


@router.get("/businesses/{business_id}/monitoring-events")
async def list_events(request: Request, business_id: str,
                      limit: int = Query(50, ge=1, le=500),
                      offset: int = Query(0, ge=0),
                      principal=Depends(READ)):
    _check(request, principal, business_id)
    rows, total = _svc(request).monitoring.list_events(
        business_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/businesses/{business_id}/checks")
async def run_checks(request: Request, business_id: str,
                     principal=Depends(WRITE)):
    _check(request, principal, business_id)
    svc = _svc(request)
    previous = svc.health.latest_snapshot(business_id)
    return ok(svc.monitoring.run_checks(
        principal, business_id, (previous or {}).get("indicators")),
        correlation_id(request))


# ------------------------------------------------------------------ health
@router.post("/businesses/{business_id}/evaluate")
async def evaluate(request: Request, business_id: str,
                   principal=Depends(WRITE)):
    _check(request, principal, business_id)
    return ok(_svc(request).evaluate(principal, business_id),
              correlation_id(request))


@router.get("/businesses/{business_id}/health")
async def latest_health(request: Request, business_id: str,
                        principal=Depends(READ)):
    _check(request, principal, business_id)
    return ok(_svc(request).health.latest_snapshot(business_id),
              correlation_id(request))


@router.get("/businesses/{business_id}/health/snapshots")
async def list_snapshots(request: Request, business_id: str,
                         limit: int = Query(50, ge=1, le=500),
                         offset: int = Query(0, ge=0),
                         principal=Depends(READ)):
    _check(request, principal, business_id)
    rows, total = _svc(request).health.history(
        business_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/health/snapshots/{snapshot_id}")
async def get_snapshot(request: Request, snapshot_id: str,
                       principal=Depends(READ)):
    snapshot = _svc(request).health.get_snapshot(snapshot_id)
    _check(request, principal, snapshot["business_id"])
    return ok(snapshot, correlation_id(request))


# --------------------------------------------------------------- lifecycle
@router.get("/businesses/{business_id}/lifecycle")
async def lifecycle(request: Request, business_id: str,
                    principal=Depends(READ)):
    _check(request, principal, business_id)
    return ok(_svc(request).lifecycle(business_id),
              correlation_id(request))


@router.get("/businesses/{business_id}/lifecycle/history")
async def lifecycle_history(request: Request, business_id: str,
                            limit: int = Query(100, ge=1, le=500),
                            offset: int = Query(0, ge=0),
                            principal=Depends(READ)):
    _check(request, principal, business_id)
    rows, total = _svc(request).lifecycle_history(
        business_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/businesses/{business_id}/lifecycle/overlay", status_code=201)
async def record_overlay(request: Request, business_id: str,
                         body: S.OverlayIn, principal=Depends(WRITE)):
    _check(request, principal, business_id)
    result = _svc(request).record_overlay(
        principal, business_id, body.model_dump())
    return ok(result, correlation_id(request))


# -------------------------------------------------------------------- pause
@router.get("/businesses/{business_id}/pause")
async def pause_status(request: Request, business_id: str,
                       principal=Depends(READ)):
    _check(request, principal, business_id)
    return ok(_svc(request).pause_status(business_id),
              correlation_id(request))


@router.post("/businesses/{business_id}/pause")
async def pause_business(request: Request, business_id: str,
                         body: S.PauseIn, principal=Depends(WRITE)):
    _check(request, principal, business_id)
    return ok(_svc(request).pause_business(
        principal, business_id, body.reason), correlation_id(request))


@router.post("/businesses/{business_id}/resume")
async def resume_business(request: Request, business_id: str,
                          principal=Depends(APPROVE)):
    _check(request, principal, business_id)
    return ok(_svc(request).resume_business(principal, business_id),
              correlation_id(request))


# --------------------------------------------------------------- decisions
@router.post("/businesses/{business_id}/decisions", status_code=201)
async def create_decision(request: Request, business_id: str,
                          body: S.DecisionCreateIn,
                          principal=Depends(WRITE)):
    _check(request, principal, business_id)
    result = _svc(request).decisions.create_decision(
        principal, business_id, body.model_dump())
    return ok(result, correlation_id(request))


@router.get("/businesses/{business_id}/decisions")
async def list_decisions(request: Request, business_id: str,
                         limit: int = Query(50, ge=1, le=500),
                         offset: int = Query(0, ge=0),
                         principal=Depends(READ)):
    _check(request, principal, business_id)
    rows, total = _svc(request).decisions.list_decisions(
        business_id=business_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/decisions/{decision_id}")
async def get_decision(request: Request, decision_id: str,
                       principal=Depends(READ)):
    decision = _svc(request).decisions.get_decision(decision_id)
    _check(request, principal, decision["business_id"])
    return ok(decision, correlation_id(request))


@router.post("/decisions/{decision_id}/approval", status_code=201)
async def request_decision_approval(request: Request, decision_id: str,
                                    body: S.DecisionReviewIn,
                                    principal=Depends(APPROVE)):
    decision = _svc(request).decisions.get_decision(decision_id)
    _check(request, principal, decision["business_id"])
    return ok(_svc(request).decisions.request_approval(
        principal, decision_id, body.reason), correlation_id(request))


@router.post("/decisions/{decision_id}/review")
async def review_decision(request: Request, decision_id: str,
                          body: S.DecisionReviewIn,
                          principal=Depends(APPROVE)):
    decision = _svc(request).decisions.get_decision(decision_id)
    _check(request, principal, decision["business_id"])
    return ok(_svc(request).decisions.review(
        principal, decision_id, body.model_dump()),
        correlation_id(request))


@router.post("/decisions/{decision_id}/execute")
async def execute_decision(request: Request, decision_id: str,
                           body: S.DecisionExecuteIn,
                           principal=Depends(WRITE)):
    decision = _svc(request).decisions.get_decision(decision_id)
    _check(request, principal, decision["business_id"])
    return ok(_svc(request).decisions.execute(
        principal, decision_id, body.idempotency_key or ""),
        correlation_id(request))


# ------------------------------------------------------------- experiments
@router.post("/businesses/{business_id}/experiments", status_code=201)
async def declare_experiment(request: Request, business_id: str,
                             body: S.ExperimentDeclareIn,
                             principal=Depends(WRITE)):
    _check(request, principal, business_id)
    result = _svc(request).experiments.create_experiment(
        principal, business_id, body.model_dump())
    return ok(result, correlation_id(request))


@router.get("/businesses/{business_id}/experiments")
async def list_experiments(request: Request, business_id: str,
                           limit: int = Query(50, ge=1, le=500),
                           offset: int = Query(0, ge=0),
                           principal=Depends(READ)):
    _check(request, principal, business_id)
    rows, total = _svc(request).experiments.list_experiments(
        business_id=business_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/experiments/{experiment_id}")
async def get_experiment(request: Request, experiment_id: str,
                         principal=Depends(READ)):
    experiment = _svc(request).experiments.get_experiment(experiment_id)
    _check(request, principal, experiment["business_id"])
    return ok(experiment, correlation_id(request))


@router.post("/experiments/{experiment_id}/approve")
async def approve_experiment(request: Request, experiment_id: str,
                             body: S.ExperimentApproveIn,
                             principal=Depends(APPROVE)):
    experiment = _svc(request).experiments.get_experiment(experiment_id)
    _check(request, principal, experiment["business_id"])
    return ok(_svc(request).experiments.approve_experiment(
        principal, experiment_id, body.model_dump()),
        correlation_id(request))


@router.post("/experiments/{experiment_id}/start")
async def start_experiment(request: Request, experiment_id: str,
                           principal=Depends(WRITE)):
    experiment = _svc(request).experiments.get_experiment(experiment_id)
    _check(request, principal, experiment["business_id"])
    return ok(_svc(request).experiments.start_experiment(
        principal, experiment_id), correlation_id(request))


@router.post("/experiments/{experiment_id}/spend")
async def experiment_spend(request: Request, experiment_id: str,
                           body: S.ExperimentSpendIn,
                           principal=Depends(WRITE)):
    experiment = _svc(request).experiments.get_experiment(experiment_id)
    _check(request, principal, experiment["business_id"])
    return ok(_svc(request).experiments.authorise_spend(
        principal, experiment_id, body.amount_minor),
        correlation_id(request))


@router.post("/experiments/{experiment_id}/stop-loss")
async def experiment_stop_loss(request: Request, experiment_id: str,
                               principal=Depends(WRITE)):
    experiment = _svc(request).experiments.get_experiment(experiment_id)
    _check(request, principal, experiment["business_id"])
    return ok(_svc(request).experiments.check_stop_loss(
        principal, experiment_id), correlation_id(request))


@router.post("/experiments/{experiment_id}/stop")
async def stop_experiment(request: Request, experiment_id: str,
                          body: S.ExperimentStopIn,
                          principal=Depends(WRITE)):
    experiment = _svc(request).experiments.get_experiment(experiment_id)
    _check(request, principal, experiment["business_id"])
    return ok(_svc(request).experiments.stop_experiment(
        principal, experiment_id, body.reason), correlation_id(request))


@router.post("/experiments/{experiment_id}/evaluate", status_code=201)
async def evaluate_experiment(request: Request, experiment_id: str,
                              body: S.ExperimentEvaluateIn,
                              principal=Depends(WRITE)):
    experiment = _svc(request).experiments.get_experiment(experiment_id)
    _check(request, principal, experiment["business_id"])
    result = _svc(request).experiments.evaluate_experiment(
        principal, experiment_id, body.model_dump())
    return ok(result, correlation_id(request))


@router.get("/experiments/{experiment_id}/evaluations")
async def list_evaluations(request: Request, experiment_id: str,
                           principal=Depends(READ)):
    experiment = _svc(request).experiments.get_experiment(experiment_id)
    _check(request, principal, experiment["business_id"])
    rows = _svc(request).experiments.list_evaluations(experiment_id)
    return page(rows, len(rows), len(rows) or 1, 0,
                correlation_id(request))


# ----------------------------------------------------------------- scaling
@router.post("/businesses/{business_id}/scaling/assess", status_code=201)
async def assess_scaling(request: Request, business_id: str,
                         principal=Depends(WRITE)):
    _check(request, principal, business_id)
    svc = _svc(request)
    snapshot = svc.evaluate(principal, business_id)["snapshot"]
    result = svc.scaling.assess(principal, business_id, snapshot)
    return ok(result, correlation_id(request))


@router.get("/businesses/{business_id}/scaling/assessments")
async def list_assessments(request: Request, business_id: str,
                           limit: int = Query(50, ge=1, le=500),
                           offset: int = Query(0, ge=0),
                           principal=Depends(READ)):
    _check(request, principal, business_id)
    rows, total = _svc(request).list_scaling_assessments(
        business_id=business_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/businesses/{business_id}/scaling/plans", status_code=201)
async def create_plan(request: Request, business_id: str,
                      body: S.ScalingPlanIn, principal=Depends(WRITE)):
    _check(request, principal, business_id)
    result = _svc(request).scaling.create_plan(
        principal, business_id, body.model_dump())
    return ok(result, correlation_id(request))


@router.get("/businesses/{business_id}/scaling/plans")
async def list_plans(request: Request, business_id: str,
                     limit: int = Query(50, ge=1, le=500),
                     offset: int = Query(0, ge=0),
                     principal=Depends(READ)):
    _check(request, principal, business_id)
    rows, total = _svc(request).scaling.list_plans(
        business_id=business_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/scaling/plans/{plan_id}/approve")
async def approve_plan(request: Request, plan_id: str,
                       principal=Depends(APPROVE)):
    plan = _svc(request).scaling.get_plan(plan_id)
    _check(request, principal, plan["business_id"])
    return ok(_svc(request).scaling.approve_plan(principal, plan_id),
              correlation_id(request))


# ---------------------------------------------------------------- recovery
@router.post("/businesses/{business_id}/recovery/plans", status_code=201)
async def create_recovery_plan(request: Request, business_id: str,
                               body: S.RecoveryPlanIn,
                               principal=Depends(WRITE)):
    _check(request, principal, business_id)
    result = _svc(request).recovery.create_plan(
        principal, business_id, body.model_dump())
    return ok(result, correlation_id(request))


@router.get("/businesses/{business_id}/recovery/plans")
async def list_recovery_plans(request: Request, business_id: str,
                              limit: int = Query(50, ge=1, le=500),
                              offset: int = Query(0, ge=0),
                              principal=Depends(READ)):
    _check(request, principal, business_id)
    rows, total = _svc(request).recovery.list_plans(
        business_id=business_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/recovery/plans/{plan_id}/conclude")
async def conclude_recovery(request: Request, plan_id: str,
                            body: S.RecoveryConcludeIn,
                            principal=Depends(WRITE)):
    _check(request, principal,
           _svc(request).recovery_plan_business(plan_id))
    return ok(_svc(request).recovery.conclude_plan(
        principal, plan_id, body.outcome), correlation_id(request))


# ----------------------------------------------------------------- closure
@router.post("/businesses/{business_id}/closure/propose", status_code=201)
async def propose_closure(request: Request, business_id: str,
                          body: S.ClosureProposeIn,
                          principal=Depends(WRITE)):
    _check(request, principal, business_id)
    result = _svc(request).closure.propose(
        principal, business_id, body.reason)
    return ok(result, correlation_id(request))


@router.get("/businesses/{business_id}/closure/reviews")
async def list_closure_reviews(request: Request, business_id: str,
                               limit: int = Query(50, ge=1, le=500),
                               offset: int = Query(0, ge=0),
                               principal=Depends(READ)):
    _check(request, principal, business_id)
    rows, total = _svc(request).closure.list_reviews(
        business_id=business_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/closure/reviews/{review_id}")
async def get_closure_review(request: Request, review_id: str,
                             principal=Depends(READ)):
    review = _svc(request).closure.get_review(review_id)
    _check(request, principal, review["business_id"])
    return ok(review, correlation_id(request))


@router.post("/closure/reviews/{review_id}/advance")
async def advance_closure(request: Request, review_id: str,
                          principal=Depends(WRITE)):
    review = _svc(request).closure.get_review(review_id)
    _check(request, principal, review["business_id"])
    return ok(_svc(request).closure.advance(principal, review_id),
              correlation_id(request))


@router.post("/closure/reviews/{review_id}/execute")
async def execute_closure(request: Request, review_id: str,
                          body: S.ClosureExecuteIn,
                          principal=Depends(APPROVE)):
    review = _svc(request).closure.get_review(review_id)
    _check(request, principal, review["business_id"])
    return ok(await _svc(request).closure.execute_closure(
        principal, review_id, body.approval_id), correlation_id(request))


# --------------------------------------------------------------- forecasts
@router.post("/businesses/{business_id}/forecasts", status_code=201)
async def create_forecast(request: Request, business_id: str,
                          body: S.ForecastCreateIn,
                          principal=Depends(WRITE)):
    _check(request, principal, business_id)
    result = _svc(request).forecasting.create_forecast(
        principal, business_id, body.model_dump())
    return ok(result, correlation_id(request))


@router.get("/businesses/{business_id}/forecasts")
async def list_forecasts(request: Request, business_id: str,
                         limit: int = Query(50, ge=1, le=500),
                         offset: int = Query(0, ge=0),
                         principal=Depends(READ)):
    _check(request, principal, business_id)
    rows, total = _svc(request).forecasting.list_forecasts(
        business_id=business_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/forecasts/{forecast_id}/vs-actual")
async def forecast_vs_actual(request: Request, forecast_id: str,
                             principal=Depends(READ)):
    result = _svc(request).forecasting.forecast_vs_actual(
        principal, forecast_id)
    _check(request, principal, result["forecast"]["business_id"])
    return ok(result, correlation_id(request))


# ---------------------------------------------------------------- outcomes
@router.post("/businesses/{business_id}/outcomes", status_code=201)
async def record_outcome(request: Request, business_id: str,
                         body: S.OutcomeRecordIn,
                         principal=Depends(WRITE)):
    _check(request, principal, business_id)
    result = _svc(request).forecasting.record_outcome(
        principal, business_id, body.model_dump())
    return ok(result, correlation_id(request))


@router.get("/businesses/{business_id}/outcomes")
async def list_outcomes(request: Request, business_id: str,
                        limit: int = Query(50, ge=1, le=500),
                        offset: int = Query(0, ge=0),
                        principal=Depends(READ)):
    _check(request, principal, business_id)
    rows, total = _svc(request).forecasting.list_outcomes(
        business_id=business_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


# --------------------------------------------------------------- portfolio
@router.get("/portfolio/overview")
async def portfolio_overview(request: Request,
                             currency: str = Query("INR"),
                             principal=Depends(READ)):
    return ok(_svc(request).portfolio.overview(currency),
              correlation_id(request))


@router.get("/portfolio/concentration")
async def portfolio_concentration(request: Request,
                                  currency: str = Query("INR"),
                                  principal=Depends(READ)):
    return ok(_svc(request).portfolio.concentration(currency),
              correlation_id(request))


@router.post("/portfolio/allocations", status_code=201)
async def propose_allocations(request: Request,
                              body: S.AllocationProposeIn,
                              principal=Depends(WRITE)):
    for entry in body.requests:
        _check(request, principal, entry.business_id)
    result = _svc(request).portfolio.propose_allocations(
        principal, body.model_dump())
    return ok(result, correlation_id(request))


@router.get("/portfolio/allocations")
async def list_allocations(request: Request,
                           business_id: str | None = None,
                           limit: int = Query(50, ge=1, le=500),
                           offset: int = Query(0, ge=0),
                           principal=Depends(READ)):
    if business_id:
        _check(request, principal, business_id)
    rows, total = _svc(request).portfolio.list_allocations(
        business_id=business_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/businesses/{business_id}/resources", status_code=201)
async def propose_resources(request: Request, business_id: str,
                            body: S.ResourceProposeIn,
                            principal=Depends(WRITE)):
    _check(request, principal, business_id)
    result = _svc(request).portfolio.propose_resources(
        principal, business_id, body.model_dump())
    return ok(result, correlation_id(request))


@router.get("/businesses/{business_id}/resources")
async def list_resources(request: Request, business_id: str,
                         limit: int = Query(50, ge=1, le=500),
                         offset: int = Query(0, ge=0),
                         principal=Depends(READ)):
    _check(request, principal, business_id)
    rows, total = _svc(request).portfolio.list_resource_proposals(
        business_id=business_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


# ----------------------------------------------------------------- analyst
@router.post("/analyst/query")
async def analyst_query(request: Request, body: S.AnalystQueryIn,
                        principal=Depends(READ)):
    if body.business_id:
        _check(request, principal, body.business_id)
    return ok(_svc(request).analyst.answer(body.model_dump()),
              correlation_id(request))
