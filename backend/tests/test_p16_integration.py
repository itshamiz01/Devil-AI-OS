"""P-16 integration tests: migration cycle, settings, overview and
classifications, market/competitor/country/segment records, the
opportunity pipeline and its two gates, strategies, discovery
detectors, capital allocation, reinvestment, commercialization,
experiment handoffs, decisions, risk and recommendations — all
through the service surface, with money seeded only through P-07's
authorised paths.
"""
from __future__ import annotations

import pytest

from app.core.exceptions import PermissionDeniedError, ValidationError
from tests.conftest import OWNER
from tests.p16_support import (
    app_eco, client_eco, lossmaking_business, owner_http_headers,
    profitable_business, strong_evidence, strong_factors,
)


# ------------------------------------------------------------ migration
def test_p16_migration_cycle(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    db = tmp_path / "p16_cycle.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")

    def count() -> int:
        with engine.connect() as conn:
            return conn.execute(text(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            )).scalar_one()

    def head() -> str:
        with engine.connect() as conn:
            return conn.execute(text(
                "SELECT version_num FROM alembic_version")).scalar_one()

    command.upgrade(config, "head")
    # P-17 disclosure: head advanced by the additive P-17 migration
    # (afe062122eb5 revises ccd744b29e54; eighteen growth tables).
    # P-18 disclosure: head advanced again by the additive P-18
    # migration (218ddd92a0aa revises afe062122eb5; fifteen
    # experience tables).
    # Expansion F01 disclosure: head advanced again by the additive
    # Expansion Feature 1 migration (85b7a9805207 revises
    # 218ddd92a0aa; two identity/device tables).
    # Expansion F02 disclosure: head advanced again by the additive
    # Expansion Feature 2 migration (3f7a1c9e52b4 revises 85b7a9805207);
    # same update, same strictness.
    # Expansion F03 disclosure: head/count advanced by the additive Expansion Feature 3 migration (c41f7a9d03e6 revises 3f7a1c9e52b4; +4 voice tables); same update, same strictness.
    # Expansion F06 disclosure: head/count advanced by the additive Expansion Feature 6 migration (af39baad9c40 revises c41f7a9d03e6; +3 knowledge tables); same update, same strictness.
    assert head() == "af39baad9c40"
    assert count() == 235  # 224 at P-18 head + 2 F01 + 2 F02 + 4 F03 + 3 F06 tables
    command.downgrade(config, "d12e4d6cf5ef")
    assert count() == 177
    command.upgrade(config, "head")
    assert count() == 235


def test_p16_metadata_registers_exactly_fourteen_new_tables():
    from app.database.models.base import Base
    import app.database.models  # noqa: F401

    # P-17 disclosure: P-17 added eighteen growth tables; the
    # exact total is now 208. The P-16 increment (14) is unchanged.
    # P-18 disclosure: P-18 added fifteen experience tables; the
    # exact total is now 223. The P-16 increment (14) is unchanged.
    # Expansion F01 disclosure: F01 added two identity/device tables;
    # the exact total is now 225. The P-16 increment (14) is unchanged.
    # Expansion F02 disclosure: F02 added two integration-framework tables;
    # the exact total is now 227. The P-16 increment (14) is unchanged.
    # Expansion F06 disclosure: F06 added three knowledge tables;
    # the exact total is now 234. The P-16 increment (14) is unchanged.
    assert len(Base.metadata.tables) == 234  # 223 pre-F01 + 2 F01 + 2 F02 + 4 F03 + 3 F06
    expected = {"market_reports", "economic_opportunities",
                "expansion_strategies", "business_classifications",
                "commercial_assets", "commercialization_proposals",
                "customer_segments", "allocation_recommendations",
                "reinvestment_plans", "experiment_proposals",
                "competitor_profiles", "country_assessments",
                "economic_decisions", "risk_assessments"}
    assert expected <= set(Base.metadata.tables)


# ------------------------------------------------------------- settings
async def test_settings_seeded_and_owner_updatable(app_eco):
    svc = app_eco.economy
    settings = svc.get_settings()
    assert settings["autonomy_level"] == 2
    assert settings["expansion_paused"] is False
    updated = svc.update_settings(OWNER, {"autonomy_level": 3})
    assert updated["autonomy_level"] == 3
    with pytest.raises(ValidationError):
        svc.update_settings(OWNER, {"autonomy_level": 9})
    with pytest.raises(ValidationError):
        svc.update_settings(OWNER, {"reinvestment_shares":
                                    {"a": 50, "b": 40}})


# ------------------------------------------------------------- overview
async def test_overview_zero_state_is_honest(app_eco):
    svc = app_eco.economy
    overview = svc.overview(OWNER)
    assert overview["businesses"]["total"] == 0
    assert overview["global_economic_overview"][
        "total_verified_collected_revenue_minor"] == 0
    assert overview["global_economic_overview"][
        "total_net_profit_minor"] is None
    assert overview["global_economic_overview"][
        "combined_available_cash"] is None
    assert overview["profitability_gate"]["state"] == "closed"


async def test_overview_matches_p07_exactly(app_eco):
    business_id = await profitable_business(app_eco, name="Books A")
    summary = app_eco.financial.business_summary(business_id)
    overview = app_eco.economy.overview(OWNER)
    kpis = overview["kpis"]
    assert kpis["total_realized_revenue_minor"] == \
        summary["revenue"]["net_collected_minor"]
    assert kpis["net_operating_profit_minor"] == \
        summary["profitability"]["net_profit_minor"]
    assert overview["profitability_gate"]["state"] == "open"
    row = overview["global_economic_overview"]["per_business"][0]
    assert row["net_collected_minor"] == \
        summary["revenue"]["net_collected_minor"]
    assert row["projected_minor"] == summary["revenue"]["projected_minor"]


# ------------------------------------------------------- classifications
async def test_classification_and_concentration_flag(app_eco):
    big = await profitable_business(app_eco, name="Big Books",
                                    revenue="9000.00", expense="100.00",
                                    opening="0.00")
    small = await profitable_business(app_eco, name="Small Books",
                                      revenue="1000.00", expense="100.00",
                                      opening="0.00")
    svc = app_eco.economy
    svc.set_classification(OWNER, big, {
        "industry": "publishing", "revenue_model": "digital_download",
        "market": "self-help ebooks", "strategic_importance": 80})
    listed = svc.list_classifications(OWNER)
    assert listed["total"] == 2
    big_row = next(i for i in listed["items"]
                   if i["business_id"] == big)
    assert big_row["classification"]["industry"] == "publishing"
    assert big_row["lifecycle_label"] in (
        "idea", "validation", "launch", "early_growth",
        "established_operation", "expansion", "maturity",
        "restructuring", "exit_or_closure")
    assert big_row["revenue_share"] == pytest.approx(0.9)
    flags = listed["overconcentration_flags"]
    assert [f["business_id"] for f in flags] == [big]


# ------------------------------------------------------------ markets
async def test_market_report_requires_sources(app_eco):
    svc = app_eco.economy
    with pytest.raises(ValidationError):
        svc.create_market_report(OWNER, {
            "title": "AI planners", "sector": "software_saas",
            "classification": "growing", "evidence_sources": []})
    report = svc.create_market_report(OWNER, {
        "title": "AI planners", "sector": "software_saas",
        "classification": "growing", "confidence": 40,
        "evidence_sources": [{"title": "fixture source",
                              "ref": "fixture://market/1"}]})
    assert report["figures_label"] == "estimates"
    listed = svc.list_market_reports(OWNER, classification="growing")
    assert listed["total"] == 1


async def test_competitor_requires_sources_and_comparison(app_eco):
    svc = app_eco.economy
    with pytest.raises(ValidationError):
        svc.create_competitor(OWNER, {"name": "Rival", "source_refs": []})
    svc.create_competitor(OWNER, {
        "name": "Rival", "market": "ebooks",
        "weaknesses": ["slow delivery"],
        "source_refs": ["https://example.com/public-page"]})
    comparison = svc.competitor_comparison(OWNER, market="ebooks")
    assert comparison["competitor_count"] == 1
    assert comparison["identified_gaps"][0]["recorded_weakness"] == \
        "slow delivery"


async def test_country_scoring_and_ranking(app_eco):
    svc = app_eco.economy
    low = svc.create_country_assessment(OWNER, {
        "country": "Lowland", "criteria_scores": {"demand": 20}})
    high = svc.create_country_assessment(OWNER, {
        "country": "Highland",
        "criteria_scores": {k: 90 for k in (
            "demand", "purchasing_power", "regulation", "tax",
            "payments", "language", "currency_risk", "competition",
            "distribution_cost", "data_protection", "ip_protection")}})
    assert high["total_score"] == 90.0
    assert low["total_score"] < high["total_score"]
    ranking = svc.rank_countries(OWNER)
    assert ranking["items"][0]["country"] == "Highland"


async def test_geographic_segment_requires_checklist(app_eco):
    svc = app_eco.economy
    with pytest.raises(ValidationError):
        svc.create_segment(OWNER, {"name": "EU readers",
                                   "kind": "geographic"})
    segment = svc.create_segment(OWNER, {
        "name": "EU readers", "kind": "geographic",
        "international_checklist": {"tax": "VAT MOSS applies",
                                    "privacy": "GDPR reviewed"}})
    assert segment["kind"] == "geographic"


# --------------------------------------------------------- opportunities
def _advance_chain(svc, opportunity_id, targets):
    result = None
    for target in targets:
        result = svc.advance_opportunity(OWNER, opportunity_id, target)
    return result


async def test_opportunity_pipeline_happy_path(app_eco):
    svc = app_eco.economy
    opp = svc.create_opportunity(OWNER, {
        "title": "Bundle the catalogue", "kind": "new_revenue_stream",
        "factor_scores": strong_factors(),
        "evidence": strong_evidence()})
    assert opp["total_score"] is not None
    assert opp["confidence"] == 76
    result = _advance_chain(svc, opp["id"], [
        "under_research", "market_validation", "financial_evaluation",
        "risk_assessment", "approval_pending"])
    assert result["stage"] == "approval_pending"


async def test_evidence_gate_blocks_weak_evidence(app_eco):
    svc = app_eco.economy
    opp = svc.create_opportunity(OWNER, {
        "title": "Viral app idea", "kind": "new_business",
        "factor_scores": strong_factors(market_demand=100),
        "evidence": [{"summary": "a hunch", "source_backed": False}]})
    assert opp["total_score"] > 60  # a good score…
    with pytest.raises(ValidationError):
        svc.advance_opportunity(OWNER, opp["id"], "approval_pending")
    # …but weak evidence keeps it in research (§4.3)


async def test_profitability_gate_blocks_new_business(app_eco):
    svc = app_eco.economy  # no businesses at all: gate closed
    opp = svc.create_opportunity(OWNER, {
        "title": "New venture", "kind": "new_business",
        "evidence": strong_evidence()})
    _advance_chain(svc, opp["id"], [
        "under_research", "market_validation", "financial_evaluation"])
    with pytest.raises(PermissionDeniedError):
        svc.advance_opportunity(OWNER, opp["id"], "risk_assessment")
    # An existing-business opportunity is not gate-blocked.
    other = svc.create_opportunity(OWNER, {
        "title": "Improve the store", "kind": "existing_business_expansion",
        "evidence": strong_evidence()})
    result = _advance_chain(svc, other["id"], [
        "under_research", "market_validation", "financial_evaluation",
        "risk_assessment"])
    assert result["stage"] == "risk_assessment"


async def test_gate_override_requires_reason_and_works(app_eco):
    svc = app_eco.economy
    opp = svc.create_opportunity(OWNER, {
        "title": "New venture", "kind": "new_business",
        "evidence": strong_evidence()})
    _advance_chain(svc, opp["id"], [
        "under_research", "market_validation", "financial_evaluation"])
    with pytest.raises(ValidationError):
        svc.record_opportunity_override(OWNER, opp["id"], "")
    svc.record_opportunity_override(
        OWNER, opp["id"], "owner accepts the risk explicitly")
    result = svc.advance_opportunity(OWNER, opp["id"], "risk_assessment")
    assert result["stage"] == "risk_assessment"
    assert result["gate_override"]["reason"].startswith("owner accepts")


# ------------------------------------------------------------ strategies
async def test_strategy_gate_block_and_override(app_eco):
    svc = app_eco.economy
    strategy = svc.create_strategy(OWNER, {
        "title": "Launch a second business", "horizon": "medium",
        "kind": "new_business", "objective": "expand"})
    view = svc.list_strategies(OWNER)["items"][0]
    assert view["blocked_by_profitability_gate"] is True
    with pytest.raises(PermissionDeniedError):
        svc.approve_strategy(OWNER, strategy["id"])
    svc.record_strategy_override(OWNER, strategy["id"],
                                 "strategic bet, owner accepts")
    approved = svc.approve_strategy(OWNER, strategy["id"])
    assert approved["status"] == "approved"
    assert approved["approval_id"]


async def test_improvement_strategy_approves_with_closed_gate(app_eco):
    svc = app_eco.economy
    strategy = svc.create_strategy(OWNER, {
        "title": "Cut churn in the existing store", "horizon": "short",
        "kind": "improve_existing", "objective": "profit first"})
    approved = svc.approve_strategy(OWNER, strategy["id"])
    assert approved["status"] == "approved"


# ------------------------------------------------------------- discovery
async def test_discovery_detectors_and_dedupe(app_eco):
    loser = await lossmaking_business(app_eco, name="Losing Books")
    winner = await profitable_business(app_eco, name="Winning Books")
    svc = app_eco.economy
    first = svc.run_discovery(OWNER)
    tags = {(o["market_tag"]) for o in first["created"]}
    assert f"detector:loss_making:{loser}" in tags
    assert f"detector:no_recurring:{winner}" in tags
    second = svc.run_discovery(OWNER)
    assert second["created_count"] == 0  # deduplicated


# --------------------------------------------------------------- capital
async def test_allocation_commitment_guard_and_approval(app_eco):
    business_id = await profitable_business(app_eco, name="Capital Books")
    svc = app_eco.economy
    scenarios = svc.allocation_scenarios(OWNER, business_id=business_id)
    available = scenarios["available_capital_minor"]
    assert available > 0
    metrics_before = app_eco.financial.revenue.metrics(business_id, "INR")
    rec = svc.create_allocation(OWNER, {
        "scenario": "balanced", "business_id": business_id,
        "proposed": {"amount_minor": 100_00, "purpose": "test",
                     "target_kind": "business"},
        "rationale": "small test"})
    with pytest.raises(ValidationError):
        svc.create_allocation(OWNER, {
            "scenario": "balanced", "business_id": business_id,
            "proposed": {"amount_minor": available, "purpose": "too big",
                         "target_kind": "business"}})
    decided = svc.decide_allocation(OWNER, rec["id"], approve=True)
    assert decided["status"] == "approved"
    assert decided["approval_id"]
    # The recommendation moved nothing in P-07.
    metrics_after = app_eco.financial.revenue.metrics(business_id, "INR")
    assert metrics_after == metrics_before


async def test_growth_allocation_refused_while_gate_closed(app_eco):
    winner = await profitable_business(app_eco, name="Winner")
    await lossmaking_business(app_eco, name="Big Loser",
                              revenue="1000.00", expense="9000.00")
    svc = app_eco.economy
    assert svc.engine_status(OWNER)["profitability_gate"]["state"] \
        == "closed"
    with pytest.raises(PermissionDeniedError):
        svc.create_allocation(OWNER, {
            "scenario": "growth", "business_id": winner,
            "proposed": {"amount_minor": 100_00, "purpose": "growth",
                         "target_kind": "business"}})


async def test_reinvestment_plan_math(app_eco):
    business_id = await profitable_business(app_eco, name="Reinvest Co")
    svc = app_eco.economy
    summary = app_eco.financial.business_summary(business_id)
    expected_distributable = max(min(
        summary["profitability"]["net_profit_minor"],
        summary["available_cash"]["available_cash_minor"]) - 500_00, 0)
    plan = svc.create_reinvestment_plan(OWNER, {
        "business_id": business_id, "adjustments_minor": 500_00})
    figures = plan["figures_snapshot"]
    assert figures["distributable_cash_minor"] == expected_distributable
    assert plan["amounts_minor"]["business_reinvestment"] == \
        int(expected_distributable * 40 / 100)
    decided = svc.decide_reinvestment_plan(OWNER, plan["id"],
                                           approve=True)
    assert decided["status"] == "approved"


# ------------------------------------------------------- commercialization
async def test_commercialization_rights_gate_and_handoff(app_eco):
    svc = app_eco.economy
    unverified = svc.create_asset(OWNER, {
        "name": "Draft tool", "kind": "software",
        "ownership_status": "unverified"})
    proposal = svc.create_commercialization(OWNER, {
        "asset_id": unverified["id"]})
    assert proposal["rights_warning"]
    with pytest.raises(PermissionDeniedError):
        svc.decide_commercialization(OWNER, proposal["id"], approve=True)

    verified = svc.create_asset(OWNER, {
        "name": "Owned tool", "kind": "software",
        "ownership_status": "verified_owner",
        "commercial_use_permitted": True})
    proposal2 = svc.create_commercialization(OWNER, {
        "asset_id": verified["id"], "title": "Sell the Owned tool"})
    svc.decide_commercialization(OWNER, proposal2["id"], approve=True)
    handed = svc.handoff_commercialization(OWNER, proposal2["id"])
    assert handed["status"] == "handed_off"
    assert handed["p03_opportunity_id"]
    opp = app_eco.opportunities.get_opportunity(
        handed["p03_opportunity_id"])
    assert opp is not None


# ------------------------------------------------------------ experiments
def _experiment_payload(business_id, **overrides):
    payload = {"title": "Pricing test", "hypothesis": "a bundle "
               "raises conversion", "business_id": business_id,
               "market_tag": "ebooks",
               "budget_ceiling_minor": 500_00, "duration_days": 30,
               "success_metrics": ["conversion +10%"],
               "failure_metrics": ["conversion -5%"],
               "stop_conditions": ["budget exhausted"],
               "problem": "low conversion",
               "target_customer": "existing readers",
               "expected_outcome": "conversion +10%",
               "minimum_evidence": "200 sessions",
               "evaluation_schedule": "day 30"}
    payload.update(overrides)
    return payload


async def test_experiment_predeclaration_enforced(app_eco):
    svc = app_eco.economy
    with pytest.raises(ValidationError):
        svc.create_experiment_proposal(OWNER, {
            "title": "Half-declared", "hypothesis": "x",
            "budget_ceiling_minor": 100, "duration_days": 7,
            "success_metrics": ["a"], "failure_metrics": ["b"],
            "stop_conditions": []})


async def test_experiment_handoff_requires_level_3(app_eco):
    business_id = await profitable_business(app_eco, name="Lab Books")
    svc = app_eco.economy
    proposal = svc.create_experiment_proposal(
        OWNER, _experiment_payload(business_id))
    svc.approve_experiment_proposal(OWNER, proposal["id"])
    with pytest.raises(PermissionDeniedError):
        svc.handoff_experiment_proposal(OWNER, proposal["id"])
    svc.update_settings(OWNER, {"autonomy_level": 3})
    handed = svc.handoff_experiment_proposal(OWNER, proposal["id"])
    assert handed["p08_experiment_id"]
    experiment = app_eco.survival.experiments.get_experiment(
        handed["p08_experiment_id"])
    assert experiment["status"] == "APPROVED"
    assert experiment["budget_id"]  # a real P-07 budget enforces it


# -------------------------------------------------------------- decisions
async def test_decision_record_and_outcome(app_eco):
    svc = app_eco.economy
    decision = svc.create_decision(OWNER, {
        "objective": "test a price rise",
        "supporting_evidence": [{"summary": "fixture"}],
        "confidence": 60, "recommended_action": "run the experiment"})
    assert decision["outcome"] is None
    recorded = svc.record_decision_outcome(OWNER, decision["id"], {
        "result": "failure", "notes": "conversion fell"})
    assert recorded["outcome"]["result"] == "failure"
    with pytest.raises(ValidationError):
        svc.record_decision_outcome(OWNER, decision["id"],
                                    {"result": "great"})


# ------------------------------------------------------------------ risk
async def test_risk_assessment_detectors_and_scenarios(app_eco):
    await profitable_business(app_eco, name="Ads Books",
                              revenue="8000.00", expense="1000.00",
                              opening="0.00", channel="ads-network")
    svc = app_eco.economy
    assessment = svc.compute_risk_assessment(OWNER)
    kinds = {d["kind"] for d in assessment["detectors"]}
    assert "platform_dependency" in kinds
    assert "revenue_concentration" in kinds
    assert len(assessment["scenarios"]) == 10
    assert assessment["scenarios_label"].startswith("SIMULATION")
    latest = svc.latest_risk_assessment(OWNER)
    assert latest["id"] == assessment["id"]


# ---------------------------------------------------------- recommendations
async def test_recommendations_lead_with_profitability(app_eco):
    await lossmaking_business(app_eco, name="Priority Loser")
    svc = app_eco.economy
    recs = svc.strategic_recommendations(OWNER)
    assert recs["items"]
    assert recs["items"][0]["kind"] == "improve_existing"
    assert recs["profitability_gate"]["state"] == "closed"


# --------------------------------------------------------- relationship map
async def test_relationship_map_candidates(app_eco):
    from tests.p13_support import make_portfolio
    first = await profitable_business(app_eco, name="Map One")
    second = await profitable_business(app_eco, name="Map Two")
    await make_portfolio(app_eco, business_ids=[first, second])
    svc = app_eco.economy
    for bid in (first, second):
        svc.set_classification(OWNER, bid, {
            "industry": "publishing", "market": "self-help ebooks",
            "revenue_model": "digital_download"})
    result = svc.relationship_map(OWNER)
    assert result["portfolios"]
    bases = {c["basis"] for c in result["cross_selling_candidates"]}
    assert "shared_market" in bases
    assert all("consent" in c["label"]
               for c in result["cross_selling_candidates"])


# ------------------------------------------------------------------- HTTP
def test_http_surface(client_eco):
    headers = owner_http_headers(client_eco)
    status = client_eco.get("/api/v1/economy/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["data"]["profitability_gate"]["state"] \
        == "closed"
    created = client_eco.post("/api/v1/economy/markets", headers=headers,
                              json={"title": "HTTP market",
                                    "sector": "education",
                                    "classification": "emerging",
                                    "evidence_sources": [
                                        {"ref": "fixture://http/1"}]})
    assert created.status_code == 201, created.text
    overview = client_eco.get("/api/v1/economy/overview",
                              headers=headers)
    assert overview.status_code == 200
    unauthenticated = client_eco.get("/api/v1/economy/overview")
    assert unauthenticated.status_code in (401, 403)


async def test_unknown_scoring_keys_refused(app_eco):
    """Regression (found by the P-16 live smoke): mistyped factor or
    criteria keys must be refused, never silently ignored — a silent
    drop changes a score invisibly."""
    svc = app_eco.economy
    with pytest.raises(ValidationError):
        svc.create_opportunity(OWNER, {
            "title": "Typo", "kind": "new_business",
            "factor_scores": {"demand_strength": 80}})
    with pytest.raises(ValidationError):
        svc.create_country_assessment(OWNER, {
            "country": "IN",
            "criteria_scores": {"market_size": 80}})
