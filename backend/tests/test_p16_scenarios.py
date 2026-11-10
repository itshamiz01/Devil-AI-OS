"""P-16 scenario tests: the prompt's end-to-end stories, named for
the sections they prove — profitability before expansion (§owner
priority), the gate opening on verified profit, single-channel
dependence (§6/§12), the full experiment lifecycle into §17 pattern
learning, commercialization into the governed pipeline (§7), and
profit-versus-cash in reinvestment (§10).
"""
from __future__ import annotations

import pytest

from app.core.exceptions import PermissionDeniedError
from tests.conftest import OWNER
from tests.p16_support import (
    app_eco, lossmaking_business, profitable_business, strong_evidence,
    strong_factors,
)


async def test_scenario_profitability_before_expansion(app_eco):
    """The owner's rule end to end: while the portfolio loses
    money, new-business work is blocked everywhere it matters and
    the system's first recommendation is fixing what exists."""
    await lossmaking_business(app_eco, name="Anchor Loser",
                              revenue="2000.00", expense="6000.00")
    await profitable_business(app_eco, name="Small Winner",
                              revenue="1500.00", expense="500.00",
                              opening="0.00")
    svc = app_eco.economy
    gate = svc.engine_status(OWNER)["profitability_gate"]
    assert gate["state"] == "closed"  # aggregate profit is negative

    strategy = svc.create_strategy(OWNER, {
        "title": "Second business", "horizon": "medium",
        "kind": "new_business"})
    with pytest.raises(PermissionDeniedError):
        svc.approve_strategy(OWNER, strategy["id"])

    improvement = svc.create_strategy(OWNER, {
        "title": "Fix the anchor", "horizon": "short",
        "kind": "improve_existing"})
    assert svc.approve_strategy(OWNER, improvement["id"])["status"] \
        == "approved"

    discovery = svc.run_discovery(OWNER)
    assert any(o["kind"] == "existing_business_expansion"
               for o in discovery["created"])
    recs = svc.strategic_recommendations(OWNER)
    assert recs["items"][0]["kind"] == "improve_existing"


async def test_scenario_gate_opens_on_verified_profit(app_eco):
    """With a verifiably profitable portfolio the same machinery
    opens: new-business opportunities advance past financial
    evaluation and growth allocations become creatable."""
    business_id = await profitable_business(app_eco, name="Earner")
    svc = app_eco.economy
    assert svc.engine_status(OWNER)["profitability_gate"]["state"] \
        == "open"
    opp = svc.create_opportunity(OWNER, {
        "title": "Second venture", "kind": "new_business",
        "factor_scores": strong_factors(),
        "evidence": strong_evidence()})
    for target in ("under_research", "market_validation",
                   "financial_evaluation", "risk_assessment",
                   "approval_pending"):
        result = svc.advance_opportunity(OWNER, opp["id"], target)
    assert result["stage"] == "approval_pending"
    growth = svc.create_allocation(OWNER, {
        "scenario": "growth", "business_id": business_id,
        "proposed": {"amount_minor": 100_00, "purpose": "expand",
                     "target_kind": "business"}})
    assert svc.decide_allocation(OWNER, growth["id"],
                                  approve=True)["status"] == "approved"


async def test_scenario_single_channel_dependence(app_eco):
    """§6/§12: a business living on one advertising channel is
    flagged everywhere — diversification warnings, portfolio
    concentration and the risk detectors agree."""
    business_id = await profitable_business(
        app_eco, name="Ads Dependent", revenue="8000.00",
        expense="1000.00", opening="0.00", channel="ads-network")
    svc = app_eco.economy
    div = svc.business_diversification(OWNER, business_id)
    kinds = {w["kind"] for w in div["warnings"]}
    assert "single_channel_dependency" in kinds
    assert "no_recurring_revenue" in kinds
    portfolio = svc.portfolio_diversification(OWNER)
    assert portfolio["concentration"]["overconcentrated"] is True
    risk = svc.compute_risk_assessment(OWNER)
    assert "platform_dependency" in {d["kind"] for d in risk["detectors"]}


async def test_scenario_experiment_lifecycle_and_pattern(app_eco):
    """§11 → §17: two pre-declared experiments in one market run
    through P-08, fail on P-08's evidence, and the pattern engine
    learns to deprioritise that market — from recorded outcomes,
    not vibes."""
    business_id = await profitable_business(app_eco, name="Lab")
    svc = app_eco.economy
    svc.update_settings(OWNER, {"autonomy_level": 3})
    for index in range(2):
        proposal = svc.create_experiment_proposal(OWNER, {
            "title": f"Ads test {index}", "hypothesis": "ads lift "
            "sales", "business_id": business_id,
            "market_tag": "paid-ads",
            "budget_ceiling_minor": 200_00, "duration_days": 14,
            "success_metrics": ["sales +10%"],
            "failure_metrics": ["sales flat"],
            "stop_conditions": ["budget exhausted"],
            "problem": "flat sales", "target_customer": "readers",
            "expected_outcome": "sales +10%",
            "minimum_evidence": "100 sessions",
            "evaluation_schedule": "day 14"})
        svc.approve_experiment_proposal(OWNER, proposal["id"])
        handed = svc.handoff_experiment_proposal(OWNER, proposal["id"])
        app_eco.survival.experiments.evaluate_experiment(
            OWNER, handed["p08_experiment_id"],
            {"classification": "FAILED",
             "actual_outcome": "no measurable lift"})
        synced = svc.sync_experiment_outcome(OWNER, proposal["id"])
        assert synced["status"] == "evaluated"
        assert synced["outcome"]["result"] == "failure"
    patterns = svc.market_patterns(OWNER)
    repeated = [p for p in patterns["patterns"]
                if p["market_tag"] == "paid-ads"]
    assert repeated and repeated[0]["pattern"] == "repeated_failure"
    assert repeated[0]["failures"] == 2
    # And the pattern is consumed, not just reported: a strong new
    # opportunity in the same market is deprioritised in the
    # recommendations, with the reason on the item (§17).
    from tests.p16_support import strong_factors
    opp = svc.create_opportunity(OWNER, {
        "title": "More ads", "kind": "new_revenue_stream",
        "market_tag": "paid-ads", "factor_scores": strong_factors(),
        "evidence": strong_evidence()})
    svc.advance_opportunity(OWNER, opp["id"], "under_research")
    svc.advance_opportunity(OWNER, opp["id"], "market_validation")
    recs = svc.strategic_recommendations(OWNER)
    mine = [r for r in recs["items"]
            if r.get("opportunity_id") == opp["id"]]
    assert mine and "deprioritised" in mine[0]["rationale"]
    assert mine[0]["priority"] == 7  # base 4 + 3 pattern penalty


async def test_scenario_commercialization_enters_governed_pipeline(app_eco):
    """§7: an approved commercialization becomes a P-03
    opportunity — and nothing more. P-06's gates still decide
    whether a business ever exists; P-16 created none."""
    svc = app_eco.economy
    _rows, before = app_eco.business.list_businesses()
    asset = svc.create_asset(OWNER, {
        "name": "Prompt pack library", "kind": "template",
        "ownership_status": "verified_owner",
        "commercial_use_permitted": True,
        "assessment": {"demand": "fixture-declared interest"}})
    proposal = svc.create_commercialization(OWNER, {
        "asset_id": asset["id"], "pricing_model": "one_time"})
    svc.decide_commercialization(OWNER, proposal["id"], approve=True)
    handed = svc.handoff_commercialization(OWNER, proposal["id"])
    _rows, after = app_eco.business.list_businesses()
    assert after == before  # no business was created by P-16
    opp = app_eco.opportunities.get_opportunity(
        handed["p03_opportunity_id"])
    assert opp is not None


async def test_scenario_reinvestment_profit_is_not_cash(app_eco):
    """§10: distributable cash is the *lesser* of accounting
    profit and real available cash, less owner-declared
    adjustments — a profitable business with thin cash cannot
    distribute its paper profit."""
    business_id = await profitable_business(
        app_eco, name="Paper Rich", revenue="10000.00",
        expense="2000.00", opening="20000.00")
    svc = app_eco.economy
    summary = app_eco.financial.business_summary(business_id)
    profit = summary["profitability"]["net_profit_minor"]
    cash = summary["available_cash"]["available_cash_minor"]
    plan = svc.create_reinvestment_plan(OWNER, {
        "business_id": business_id, "adjustments_minor": 100_00})
    figures = plan["figures_snapshot"]
    assert figures["distributable_cash_minor"] == \
        max(min(profit, cash) - 100_00, 0)
    total_amounts = sum(plan["amounts_minor"].values())
    assert total_amounts <= figures["distributable_cash_minor"]
    assert total_amounts > figures["distributable_cash_minor"] - 100
