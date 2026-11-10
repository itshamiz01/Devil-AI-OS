"""P-16 unit tests: the pure economic mathematics (scoring.py).

No application, no database — the formulas are pinned directly so a
weight change or an inversion mistake fails loudly here rather than
silently misranking opportunities in production.
"""
from __future__ import annotations

from app.economy import scoring
from tests.p16_support import strong_factors


# ------------------------------------------------------------ §4.3
def test_score_uses_prompt_weights():
    # All factors 80 with risk 20 (=> attractiveness 80): the
    # weighted total must be exactly 80 regardless of weights.
    factors = {k: 80 for k in
               ("market_demand", "profitability_potential",
                "competitive_advantage", "scalability",
                "capital_efficiency", "operational_feasibility",
                "revenue_diversification", "strategic_compatibility")}
    factors["risk_profile"] = 20
    result = scoring.score_opportunity(factors)
    assert result["total_score"] == 80.0
    assert result["band"] == "strong_candidate"
    assert result["missing_factors"] == []


def test_risk_is_inverted():
    low_risk = scoring.score_opportunity(strong_factors(risk_profile=10))
    high_risk = scoring.score_opportunity(strong_factors(risk_profile=90))
    # Risk carries 5% weight: an 80-point risk swing moves the
    # total by exactly 4 points, downward.
    assert low_risk["total_score"] - high_risk["total_score"] == 4.0


def test_missing_factors_score_zero_and_are_reported():
    result = scoring.score_opportunity({"market_demand": 100})
    assert result["total_score"] == 20.0  # only the 20% factor counts
    assert "scalability" in result["missing_factors"]
    assert result["band"] == "reject_or_archive"


def test_band_boundaries():
    assert scoring.band_for(39.9) == "reject_or_archive"
    assert scoring.band_for(40) == "research_further"
    assert scoring.band_for(60) == "controlled_experimentation"
    assert scoring.band_for(75) == "strong_candidate"
    assert scoring.band_for(90) == "strategic_candidate"
    assert scoring.band_for(100) == "strategic_candidate"


def test_confidence_from_evidence():
    assert scoring.confidence_from_evidence([]) == 0
    assert scoring.confidence_from_evidence(
        [{"source_backed": True}]) == 22
    assert scoring.confidence_from_evidence(
        [{"source_backed": True}] * 2) == 44  # below the 50 gate
    assert scoring.confidence_from_evidence(
        [{"source_backed": True}] * 3) == 76  # 66 + corroboration 10
    assert scoring.confidence_from_evidence(
        [{"source_backed": False}] * 2) == 16
    assert scoring.confidence_from_evidence(
        [{"source_backed": True}] * 10) == 100  # capped


# ------------------------------------------------------------ §5/§6
def test_hhi_and_largest_share():
    assert scoring.hhi({"a": 100}) == 1.0
    assert scoring.hhi({"a": 50, "b": 50}) == 0.5
    assert scoring.hhi({"a": 25, "b": 25, "c": 25, "d": 25}) == 0.25
    assert scoring.hhi({}) is None
    assert scoring.hhi({"a": 0}) is None
    key, share = scoring.largest_share({"a": 30, "b": 70})
    assert key == "b" and share == 0.7
    assert scoring.largest_share({}) == (None, None)


def test_diversification_insufficient_data():
    result = scoring.diversification_score({"net_collected_minor": 0})
    assert result["score"] is None
    assert result["status"] == "INSUFFICIENT_DATA"


def test_diversification_formula():
    metrics = {"net_collected_minor": 100_00,
               "by_channel_minor": {"web": 50_00, "store": 50_00},
               "by_product_minor": {"only": 100_00},
               "by_category_minor": {"product_sale": 100_00},
               "mrr_minor": 0}
    result = scoring.diversification_score(metrics)
    # channel spread 0.5 * 0.4 + product spread 0 * 0.3 + recurring 0
    assert result["score"] == 20.0
    assert result["top_channel_share"] == 0.5
    assert result["streams_present"]["channels"] == 2


# ------------------------------------------------------------ gate
def _row(bid, *, profile=True, collected=0, profit=None):
    return {"business_id": bid, "has_profile": profile,
            "verified_collected_revenue_minor": collected,
            "net_profit_minor": profit}


def test_gate_closed_without_profiles():
    gate = scoring.profitability_gate([_row("a", profile=False)])
    assert gate["state"] == "closed"


def test_gate_closed_without_revenue():
    gate = scoring.profitability_gate([_row("a", collected=0, profit=0)])
    assert gate["state"] == "closed"


def test_gate_closed_on_nonpositive_profit():
    gate = scoring.profitability_gate(
        [_row("a", collected=100_00, profit=-1)])
    assert gate["state"] == "closed"
    assert gate["total_net_profit_minor"] == -1


def test_gate_closed_on_indeterminate_profit():
    gate = scoring.profitability_gate(
        [_row("a", collected=100_00, profit=None)])
    assert gate["state"] == "closed"


def test_gate_open_on_verified_profit():
    gate = scoring.profitability_gate([
        _row("a", collected=100_00, profit=25_00),
        _row("b", collected=50_00, profit=-10_00)])
    assert gate["state"] == "open"
    assert gate["total_net_profit_minor"] == 15_00


# ------------------------------------------------------------ §14
def test_country_score_weighted_mean():
    criteria = {k: 50 for k in
                ("demand", "purchasing_power", "regulation", "tax",
                 "payments", "language", "currency_risk", "competition",
                 "distribution_cost", "data_protection",
                 "ip_protection")}
    result = scoring.country_score(criteria)
    assert result["total_score"] == 50.0
    assert result["missing_criteria"] == []
    partial = scoring.country_score({"demand": 100})
    assert partial["total_score"] < 20  # demand counts double of 12
    assert "tax" in partial["missing_criteria"]


# ------------------------------------------------------------ §12
def test_stress_scenarios_cover_the_ten_and_do_arithmetic():
    rows = [{"business_id": "b1", "name": "One", "currency": "INR",
             "net_collected_minor": 1000_00, "expenses_minor": 400_00,
             "net_profit_minor": 600_00,
             "by_channel_minor": {"ads": 700_00, "web": 300_00}}]
    scenarios = scoring.stress_scenarios(rows, 500_00)
    assert [s["key"] for s in scenarios] == [
        "revenue_drop_10", "revenue_drop_25", "revenue_drop_50",
        "major_customer_disappears", "ad_platform_suspended",
        "cloud_provider_unavailable", "costs_up_20",
        "major_business_unprofitable", "international_entry_fails",
        "simultaneous_disruption"]
    by_key = {s["key"]: s for s in scenarios}
    assert by_key["revenue_drop_50"]["portfolio_net_profit_after_minor"] \
        == 600_00 - 500_00
    assert by_key["costs_up_20"]["portfolio_net_profit_after_minor"] \
        == 600_00 - 80_00
    assert by_key["ad_platform_suspended"][
        "portfolio_net_profit_after_minor"] == 600_00 - 700_00
    assert by_key["major_customer_disappears"][
        "portfolio_net_profit_after_minor"] == 600_00 - 700_00
    assert all(s["label"] == "SIMULATION" for s in scenarios)
    assert "50000" in by_key["international_entry_fails"]["notes"]
