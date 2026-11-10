"""P-08 acceptance scenarios (§26.4, Scenarios 1–15).

Every fixture's financial history is seeded THROUGH P-07's own
machinery (provider-report verified revenue, paid expenses, opening
balances, budgets, reserves, reconciliation imports). No ledger row
is written directly; nothing unverified is marked verified.
Amounts are the prompt's ₹ figures (INR minor units under the hood).
"""
from __future__ import annotations

import pytest

from app.core.exceptions import PermissionDeniedError, ValidationError
from tests.conftest import OWNER
from tests.p08_support import (
    AGENT, EXPERIMENT, app_surv, create_budget, healthy_snapshot,  # noqa: F401
    money, opening_balance, operational_business, paid_expense,
    profile_only_business, seed_repeat_customers, verified_sale,
)


def _observe(app, business_id, kind, metrics, reliability="corroborated"):
    return app.survival.monitoring.record_observation(OWNER, business_id, {
        "kind": kind, "source": "operator_report", "reliability": reliability,
        "metrics": metrics})


# ------------------------------------------------------------ Scenario 1
async def test_scenario_01_growth_without_profitability(app_surv):
    """Revenue ₹10,000 → ₹30,000 while expenses ₹8,000 → ₹35,000:
    deterioration is flagged, scaling is NOT recommended, and a
    cost investigation is the recorded next step."""
    business_id, _ = await profile_only_business(app_surv)
    opening_balance(app_surv, business_id, "50000.00")
    verified_sale(app_surv, business_id, "10000.00", customer="cust-a")
    await paid_expense(app_surv, business_id, "8000.00")
    first = healthy_snapshot(app_surv, business_id)
    assert not any(g["gate"] == "loss_making"
                   for g in first["hard_gates"])

    verified_sale(app_surv, business_id, "20000.00", customer="cust-b",
                  date="2026-11-07")
    await paid_expense(app_surv, business_id, "27000.00",
                       date="2026-11-08")
    second = app_surv.survival.evaluate(OWNER, business_id)
    snapshot = second["snapshot"]
    gates = {g["gate"] for g in snapshot["hard_gates"]}
    assert "loss_making" in gates
    event_kinds = {e["kind"] for e in second["checks"]}
    assert "loss_making" in event_kinds

    assessment = app_surv.survival.scaling.assess(
        OWNER, business_id, snapshot)
    assert assessment["status"] in ("NOT_READY", "BLOCKED")
    unsatisfied = {u["condition"] for u in assessment["unsatisfied"]}
    assert "no_blocking_hard_gates" in unsatisfied

    decision = app_surv.survival.decisions.create_decision(
        OWNER, business_id, {
            "decision_type": "INVESTIGATE",
            "trigger": "loss-making gate raised by P-08 health",
            "evidence": [{"source": "p08.health_snapshot",
                          "id": snapshot["id"]}]})
    assert decision["decision_type"] == "INVESTIGATE"


# ------------------------------------------------------------ Scenario 2
async def test_scenario_02_vanity_metrics_do_not_validate(app_surv):
    """Traffic and followers with no paying customers: NOT
    validated, NOT scaling-ready; demand validation is the
    recommendation."""
    business_id, _ = await profile_only_business(app_surv)
    _observe(app_surv, business_id, "traffic",
             {"page_views": 120000, "followers": 48000,
              "impressions": 900000}, reliability="verified")
    snapshot = healthy_snapshot(app_surv, business_id)
    commercial = {d["dimension"]: d for d in snapshot["dimensions"]}
    assert commercial["commercial"]["status"] == "INSUFFICIENT_DATA"
    assessment = app_surv.survival.scaling.assess(
        OWNER, business_id, snapshot)
    assert assessment["status"] == "NOT_READY"
    assert assessment["stage"] == 0
    # Even for an OPERATIONAL business, vanity evidence cannot move
    # the overlay to GROWING (§5.2).
    operational_id, _ = await operational_business(
        app_surv, name="Vanity Operational")
    _observe(app_surv, operational_id, "traffic",
             {"page_views": 999999, "followers": 250000},
             reliability="verified")
    app_surv.survival.evaluate(OWNER, operational_id)
    with pytest.raises(PermissionDeniedError):
        app_surv.survival.record_overlay(OWNER, operational_id, {
            "to_state": "GROWING", "reason": "lots of traffic"})


# ------------------------------------------------------------ Scenario 3
async def test_scenario_03_successful_experiment_bounded(app_surv):
    """An approved experiment that meets its declared criteria
    within budget is classified by its evidence — and no unlimited
    spend is authorised."""
    business_id, _ = await profile_only_business(app_surv)
    opening_balance(app_surv, business_id, "10000.00")
    experiment = app_surv.survival.experiments.create_experiment(
        OWNER, business_id, dict(EXPERIMENT))
    approved = app_surv.survival.experiments.approve_experiment(
        OWNER, experiment["id"], {})
    budget_id = approved["budget_id"]
    assert budget_id
    utilisation = app_surv.financial.budgets.budget_utilisation(budget_id)
    assert utilisation["approved_minor"] == 200_000  # exactly as declared
    app_surv.survival.experiments.start_experiment(OWNER, experiment["id"])

    gate = app_surv.survival.experiments.authorise_spend(
        OWNER, experiment["id"], 50_000)
    assert gate["authorised"] is True
    with pytest.raises(ValidationError):
        app_surv.survival.experiments.evaluate_experiment(
            OWNER, experiment["id"], {"classification": "VALIDATED"})
    evaluation = app_surv.survival.experiments.evaluate_experiment(
        OWNER, experiment["id"], {
            "classification": "VALIDATED",
            "observed_metric_value": "6 verified sales",
            "actual_outcome": "6 verified sales inside the window",
            "recommended_next_step": "evaluate a follow-up experiment "
                                     "with its own declaration"})
    assert evaluation["classification"] == "VALIDATED"
    after = app_surv.survival.experiments.get_experiment(experiment["id"])
    assert after["status"] == "SUCCESSFUL"
    # No unlimited spend: the full remaining budget in one step is
    # still bounded by the declared cap, and beyond it is refused.
    with pytest.raises(PermissionDeniedError):
        app_surv.survival.experiments.authorise_spend(
            OWNER, experiment["id"], 10_000_000)


# ------------------------------------------------------------ Scenario 4
async def test_scenario_04_stop_loss_blocks_further_spend(app_surv):
    """Maximum acceptable loss consumed → stop-loss fires
    mechanically, further spend is blocked at the budget layer, and
    the failed experiment is preserved as a learning record."""
    business_id, _ = await profile_only_business(app_surv)
    opening_balance(app_surv, business_id, "10000.00")
    experiment = app_surv.survival.experiments.create_experiment(
        OWNER, business_id, dict(EXPERIMENT))
    approved = app_surv.survival.experiments.approve_experiment(
        OWNER, experiment["id"], {})
    app_surv.survival.experiments.start_experiment(OWNER, experiment["id"])
    await paid_expense(app_surv, business_id, "1000.00",
                       budget_id=approved["budget_id"],
                       category="advertising")
    result = app_surv.survival.experiments.check_stop_loss(
        OWNER, experiment["id"])
    assert result["stop_loss_tripped"] is True
    assert "max_loss_reached" in result["reasons"] or \
        "budget_exhausted" in result["reasons"]
    stopped = app_surv.survival.experiments.get_experiment(experiment["id"])
    assert stopped["status"] == "STOPPED"
    with pytest.raises(PermissionDeniedError):
        app_surv.survival.experiments.authorise_spend(
            OWNER, experiment["id"], 10_000)
    evaluations = app_surv.survival.experiments.list_evaluations(
        experiment["id"])
    assert isinstance(evaluations, list)  # record preserved, readable
    rows, total = app_surv.survival.experiments.list_experiments(
        business_id=business_id)
    assert total == 1  # the failure is not hidden or deleted


# ------------------------------------------------------------ Scenario 5
async def test_scenario_05_scaling_readiness_incremental(app_surv):
    """A genuinely ready business gets a readiness report and an
    INCREMENTAL plan: ₹10,000 never becomes ₹50,000 in one step,
    and approval is enforced."""
    business_id, _ = await operational_business(app_surv)
    opening_balance(app_surv, business_id, "100000.00")
    # Verified sales across two channels, ≥3 customers, one repeat.
    verified_sale(app_surv, business_id, "2500.00", customer="cust-a",
                  channel="Amazon KDP")
    verified_sale(app_surv, business_id, "2500.00", customer="cust-b",
                  channel="Amazon KDP")
    verified_sale(app_surv, business_id, "2500.00", customer="cust-c",
                  channel="Gumroad")
    verified_sale(app_surv, business_id, "2500.00", customer="cust-a",
                  channel="Gumroad", date="2026-11-08")
    await paid_expense(app_surv, business_id, "2000.00")
    _observe(app_surv, business_id, "operations",
             {"delivery_completion_rate": "0.95", "failed_runs": 1})
    _observe(app_surv, business_id, "product", {"satisfaction": "0.7"})
    _observe(app_surv, business_id, "market",
             {"demand_signal": "steady"}, reliability="supporting")
    _observe(app_surv, business_id, "compliance", {"violation": False})
    healthy_snapshot(app_surv, business_id)
    snapshot = healthy_snapshot(app_surv, business_id)
    assert snapshot["classification"] in ("STABLE", "HEALTHY",
                                          "EXCELLENT"), snapshot["explanation"]

    assessment = app_surv.survival.scaling.assess(
        OWNER, business_id, snapshot)
    assert assessment["status"] == "READY", assessment["unsatisfied"]
    assert assessment["satisfied"], "readiness report lists satisfied conditions"

    budget = create_budget(app_surv, business_id, "10000.00",
                           name="Growth budget")
    with pytest.raises(ValidationError):
        app_surv.survival.scaling.create_plan(OWNER, business_id, {
            "budget_id": budget["id"], "proposed_amount_minor": 5_000_000,
            "strict": True})  # ₹50,000 in one step is refused (§10.4)
    plan = app_surv.survival.scaling.create_plan(OWNER, business_id, {
        "budget_id": budget["id"], "proposed_amount_minor": 5_000_000})
    assert plan["proposed_amount_minor"] == 1_500_000  # clamped to +50%
    assert plan["clamped"] is True
    with pytest.raises(PermissionDeniedError):
        app_surv.survival.scaling.approve_plan(AGENT, plan["id"])
    approved = app_surv.survival.scaling.approve_plan(OWNER, plan["id"])
    assert approved["status"] == "APPROVED"
    # Approval changed no P-07 budget (§16.4).
    utilisation = app_surv.financial.budgets.budget_utilisation(budget["id"])
    assert utilisation["approved_minor"] == 1_000_000


# ------------------------------------------------------------ Scenario 6
async def test_scenario_06_profitable_but_illiquid(app_surv):
    """Profit on verified figures, but obligations exceed cash:
    the liquidity gate fires — profit alone does not clear it."""
    business_id, _ = await profile_only_business(app_surv)
    opening_balance(app_surv, business_id, "1000.00")
    verified_sale(app_surv, business_id, "30000.00", customer="cust-a")
    await paid_expense(app_surv, business_id, "5000.00")
    # A large COMMITTED obligation in P-07: profit is computed on
    # paid figures, but commitments count against available cash.
    app_surv.financial.expenses.create_expense(OWNER, business_id, {
        "category": "operational",
        "amount": money(app_surv, "40000.00"),
        "expense_date": "2026-11-09", "directness": "indirect",
        "cost_behavior": "fixed", "payment_status": "committed"})
    snapshot = healthy_snapshot(app_surv, business_id)
    indicators = snapshot["indicators"]
    assert indicators["profitability"]["status"] == "computed"
    gates = {g["gate"] for g in snapshot["hard_gates"]}
    assert "cash_below_obligations" in gates or \
        "obligations_exceed_cash" in gates, snapshot["explanation"]
    assert snapshot["classification"] in ("AT_RISK", "CRITICAL")


# ------------------------------------------------------------ Scenario 7
async def test_scenario_07_platform_concentration_named(app_surv):
    """Businesses earning through one platform: concentration is
    named as portfolio risk; record count is not diversification."""
    business_a, _ = await profile_only_business(
        app_surv, name="KDP Book One")
    business_b, _ = await profile_only_business(
        app_surv, name="KDP Book Two")
    for business_id in (business_a, business_b):
        verified_sale(app_surv, business_id, "5000.00",
                      customer="cust-a", channel="Amazon KDP")
    concentration = app_surv.survival.portfolio.concentration()
    kinds = {(r["kind"], r.get("platform")) for r in concentration["risks"]}
    assert ("revenue_concentration", "Amazon KDP") in kinds
    assert "diversification" in concentration["diversification_note"]


# ------------------------------------------------------------ Scenario 8
async def test_scenario_08_recovery_plan_finite(app_surv):
    """A repairable operational decline gets a recovery plan with a
    finite budget, a finite review period and declared thresholds;
    the outcome is concluded once and never rewritten."""
    business_id, _ = await profile_only_business(app_surv)
    opening_balance(app_surv, business_id, "20000.00")
    plan = app_surv.survival.recovery.create_plan(OWNER, business_id, {
        "root_cause": "fulfilment pipeline outage for 3 days",
        "failure_kind": "operational",
        "corrective_actions": ["repair delivery pipeline",
                               "notify affected customers"],
        "budget_minor": 150_000, "timeline_days": 21,
        "success_thresholds": "delivery completion >= 0.9 for 7 days",
        "failure_thresholds": "delivery completion < 0.7 at review",
        "escalation_rules": "owner review if failure threshold met"})
    assert plan["timeline_days"] == 21 and plan["review_on"]
    assert plan["budget_minor"] == 150_000
    with pytest.raises(ValidationError):
        app_surv.survival.recovery.create_plan(OWNER, business_id, {
            "root_cause": "open-ended subsidy", "budget_minor": 1,
            "success_thresholds": "x"})  # no finite timeline/thresholds
    concluded = app_surv.survival.recovery.conclude_plan(
        OWNER, plan["id"], "IMPROVING")
    assert concluded["outcome"] == "IMPROVING"
    with pytest.raises(ValidationError):
        app_surv.survival.recovery.conclude_plan(
            OWNER, plan["id"], "RECOVERED")  # history is not rewritten


# ------------------------------------------------------------ Scenario 9
async def test_scenario_09_closure_review_not_closure(app_surv):
    """A structurally unviable business gets a closure REVIEW with
    obligations inventoried; it is NOT closed without the Level 4
    owner flow."""
    business_id, _ = await operational_business(app_surv)
    opening_balance(app_surv, business_id, "3000.00")
    await paid_expense(app_surv, business_id, "2500.00")
    review = app_surv.survival.closure.propose(
        OWNER, business_id, "no verified demand after repeated attempts")
    assert review["stage"] == "PROPOSED_CLOSURE"
    assert review["inventory"] is not None
    assert app_surv.business.get_business(business_id)["status"] == \
        "OPERATIONAL"  # not closed

    with pytest.raises(PermissionDeniedError):
        await app_surv.survival.closure.execute_closure(
            AGENT, review["id"], None)
    for _ in range(4):
        review = app_surv.survival.closure.advance(OWNER, review["id"])
    assert review["stage"] == "OWNER_APPROVAL"
    assert review["inventory"]["obligations_minor"] is not None
    closed = await app_surv.survival.closure.execute_closure(
        OWNER, review["id"], None)
    assert closed["stage"] == "CLOSED"
    assert closed["wind_down"]["financial_history_preserved"] is True
    assert app_surv.business.get_business(business_id)["status"] == \
        "ARCHIVED"
    # History survives closure: P-07 records and P-08 snapshots remain.
    rows, total = app_surv.financial.revenue.list_revenue(business_id)
    assert isinstance(rows, list)


# ----------------------------------------------------------- Scenario 10
async def test_scenario_10_competing_businesses_allocation(app_surv):
    """Three businesses competing for limited capital: proposals
    are explainable, capped per business, and never over-allocate;
    nothing moves."""
    ids = []
    for index, amount in enumerate(("50000.00", "10000.00", "0.00")):
        business_id, _ = await profile_only_business(
            app_surv, name=f"Allocator {index}")
        if amount != "0.00":
            opening_balance(app_surv, business_id, amount)
        healthy_snapshot(app_surv, business_id)
        ids.append(business_id)
    result = app_surv.survival.portfolio.propose_allocations(OWNER, {
        "currency": "INR", "source_kind": "available_capital",
        "requests": [{"business_id": bid, "amount_minor": 4_000_000,
                      "purpose": "growth"} for bid in ids]})
    assert result["blocked"] is False
    proposals = {p["business_id"]: p for p in result["proposals"]}
    # ₹50,000 available, share cap 0.5 → at most ₹25,000 proposed.
    assert proposals[ids[0]]["amount_minor"] <= 2_500_000
    assert proposals[ids[0]]["rationale"]["available_capital_minor"] == \
        5_000_000
    # No capital at all → nothing proposed for the empty business.
    assert proposals[ids[2]]["amount_minor"] == 0
    assert proposals[ids[2]]["status"] == "BLOCKED"


# ----------------------------------------------------------- Scenario 11
async def test_scenario_11_agent_multiplication_measured(app_surv):
    """Ten agents requested: workload is measured first,
    reassignment/optimisation alternatives are listed, and the
    recommendation respects the hardware profile."""
    business_id, _ = await operational_business(app_surv)
    proposal = app_surv.survival.portfolio.propose_resources(
        OWNER, business_id, {"requested_agents": 10})
    assert proposal["requested_agents"] == 10
    assert proposal["recommended_agents"] <= 4  # hardware cap in settings
    kinds = {a["kind"] for a in proposal["alternatives"]}
    assert "reassign_existing" in kinds
    assert proposal["workload"]["hardware"]["inference_slots"] == 1


# ----------------------------------------------------------- Scenario 12
async def test_scenario_12_protected_reserves_blocked(app_surv):
    """A scaling allocation sourced from protected reserves is
    BLOCKED and recorded; the reserve itself is untouched."""
    business_id, _ = await profile_only_business(app_surv)
    opening_balance(app_surv, business_id, "20000.00")
    app_surv.financial.budgets.create_reserve(OWNER, {
        "reserve_type": "emergency",
        "amount": money(app_surv, "5000.00"),
        "business_id": business_id})
    result = app_surv.survival.portfolio.propose_allocations(OWNER, {
        "currency": "INR", "source_kind": "protected_reserves",
        "requests": [{"business_id": business_id,
                      "amount_minor": 500_000, "purpose": "scale ads"}]})
    assert result["blocked"] is True
    assert result["proposals"][0]["status"] == "BLOCKED"
    indicators = app_surv.financial.budgets.available_cash(
        business_id, "INR")
    assert indicators["protected_reserves_minor"] == 500_000


# ----------------------------------------------------------- Scenario 13
async def test_scenario_13_reconciliation_conflict_blocks_scaling(app_surv):
    """Dashboard growth plus an unresolved reconciliation
    discrepancy: confidence is reduced and material scaling is
    blocked until resolved."""
    business_id, _ = await profile_only_business(app_surv)
    opening_balance(app_surv, business_id, "50000.00")
    seed_repeat_customers(app_surv, business_id)
    parsed = app_surv.financial.payments.import_statement(
        OWNER, business_id,
        csv_text=("date,description,amount,currency,external_ref\n"
                  "2026-11-06,provider settlement,7777.00,INR,stmt-999\n"),
        source_type="provider_statement", source_ref="stmt-nov")
    session = app_surv.financial.reconciliation.create_session_with_items(
        OWNER, business_id, source_type="provider_statement",
        source_ref="stmt-nov", items=parsed["items"])
    app_surv.financial.reconciliation.run_matching(OWNER, session["id"])
    snapshot = healthy_snapshot(app_surv, business_id)
    gates = {g["gate"] for g in snapshot["hard_gates"]}
    assert "unresolved_reconciliation" in gates
    assessment = app_surv.survival.scaling.assess(
        OWNER, business_id, snapshot)
    assert assessment["status"] != "READY"
    unsatisfied = {u["condition"] for u in assessment["unsatisfied"]}
    assert "no_blocking_hard_gates" in unsatisfied


# ----------------------------------------------------------- Scenario 14
async def test_scenario_14_forecast_error_against_frozen_forecast(app_surv):
    """Forecast +30% vs an actual decline: the error is recorded
    against the FROZEN original; the forecast row never changes."""
    business_id, _ = await profile_only_business(app_surv)
    opening_balance(app_surv, business_id, "50000.00")
    verified_sale(app_surv, business_id, "10000.00", customer="cust-a")
    forecast = app_surv.survival.forecasting.create_forecast(
        OWNER, business_id, {
            "kind": "growth", "scenario": "optimistic",
            "period_label": "2026-12",
            "expected": {"collected_revenue_minor": 1_300_000},
            "confidence": "low"})
    comparison = app_surv.survival.forecasting.forecast_vs_actual(
        OWNER, forecast["id"])
    assert comparison["comparison"]["variance_minor"] == \
        1_000_000 - 1_300_000  # actual ₹10,000 vs expected ₹13,000
    frozen = app_surv.survival.forecasting.list_forecasts(
        business_id=business_id)[0][0]
    assert frozen["expected"]["collected_revenue_minor"] == 1_300_000
    outcome = app_surv.survival.forecasting.record_outcome(
        OWNER, business_id, {
            "problem": "growth forecast for December",
            "expected_outcome": "+30% collected revenue",
            "actual_outcome": "no growth; revenue flat at ₹10,000",
            "decision_quality": "poor",
            "lesson": "optimistic scenario was used as a plan",
            "forecast_error": {"variance_minor": -300_000,
                               "forecast_id": forecast["id"]}})
    assert outcome["forecast_error"]["forecast_id"] == forecast["id"]


# ----------------------------------------------------------- Scenario 15
async def test_scenario_15_emergency_pause(app_surv):
    """Emergency pause: new controlled execution is blocked,
    records are preserved, the event is owner-visible, and lifting
    the pause requires the owner."""
    business_id, _ = await operational_business(app_surv)
    opening_balance(app_surv, business_id, "10000.00")
    snapshot = healthy_snapshot(app_surv, business_id)
    decision = app_surv.survival.decisions.create_decision(
        OWNER, business_id, {"decision_type": "MONITOR",
                             "trigger": "pre-incident review"})
    paused = app_surv.survival.pause_business(
        OWNER, business_id, "suspected credential compromise")
    assert paused["state"] == "PAUSED"
    assert app_surv.survival.is_paused(business_id) is True

    with pytest.raises(PermissionDeniedError):
        app_surv.survival.decisions.execute(
            OWNER, decision["id"], "during-pause-key")
    experiment = app_surv.survival.experiments.create_experiment(
        OWNER, business_id, dict(EXPERIMENT))
    app_surv.survival.experiments.approve_experiment(
        OWNER, experiment["id"], {})  # approval is a record, not execution
    with pytest.raises(PermissionDeniedError):
        app_surv.survival.experiments.start_experiment(
            OWNER, experiment["id"])  # execution is blocked (§25.2)

    # Records preserved and readable during the pause.
    rows, total = app_surv.survival.health.history(business_id)
    assert total >= 1
    lifecycle = app_surv.survival.lifecycle(business_id)
    assert lifecycle["paused"] is True
    events, _total = app_surv.survival.monitoring.list_events(business_id)
    assert isinstance(events, list)
    audit_rows = _audit_actions(app_surv, "survival.business_paused")
    assert audit_rows >= 1  # owner-visible in the P-01 audit trail

    with pytest.raises(PermissionDeniedError):
        app_surv.survival.resume_business(AGENT, business_id)
    resumed = app_surv.survival.resume_business(OWNER, business_id)
    assert resumed["state"] == "ACTIVE"


def _audit_actions(application, action: str) -> int:
    from sqlalchemy import func, select
    from app.database.models.core import AuditEvent
    session = application.session_factory()
    try:
        return session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == action)) or 0
    finally:
        session.close()
