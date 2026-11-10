"""P-17 unit tests: the deterministic scoring mathematics (§4.2,
§4.3, §9, §13, §14, §17, §27). Pure functions only — no application
boot — so every number here can be re-derived by hand.
"""
from __future__ import annotations

from app.growth import constants as C
from app.growth import scoring


def test_icp_priority_weighted_and_explained():
    result = scoring.icp_priority(
        {"product_fit": 100, "demand": 50},
        C.DEFAULT_SETTINGS["icp_weights"])
    # missing factors score 0 and are reported, never hidden
    assert result["score"] == 30.0  # (100*3 + 50*3) / 15
    assert result["contributions"]["product_fit"] == 20.0
    assert "commercial_potential" in result["missing_factors"]
    assert len(result["missing_factors"]) == 4


def test_channel_value_uses_declared_weights():
    full = {key: 100 for key in C.CHANNEL_FACTOR_KEYS}
    result = scoring.channel_value(full, C.DEFAULT_SETTINGS["channel_weights"])
    assert result["score"] == 100.0
    assert result["missing_factors"] == []


def test_lead_score_bands():
    assert scoring.band_for(10) == "low_priority"
    assert scoring.band_for(50) == "potential"
    assert scoring.band_for(75) == "qualified_prospect"
    assert scoring.band_for(95) == "high_priority"
    # partial factor sets score against the full vocabulary: missing
    # factors count 0, so a thin assessment can never look complete
    thin = scoring.lead_score(
        {"product_interest": 90, "purchase_intent": 90},
        C.DEFAULT_SETTINGS["lead_score_weights"])
    assert thin["score"] == 29  # (90*18 + 90*14) / 100
    assert thin["band"] == "low_priority"
    assert thin["missing_factors"]
    full = scoring.lead_score(
        {key: 90 for key in C.LEAD_SCORE_FACTORS},
        C.DEFAULT_SETTINGS["lead_score_weights"])
    assert full["score"] == 90
    assert full["band"] == "high_priority"


def test_cac_insufficient_data_discipline():
    assert scoring.cac(None, 5)["status"] == "INSUFFICIENT_DATA"
    assert scoring.cac(1000, 0)["status"] == "INSUFFICIENT_DATA"
    result = scoring.cac(100000, 4)
    assert result["status"] == "computed"
    assert result["cac_minor"] == 25000


def test_ltv_actual_vs_projected_split():
    unprojectable = scoring.ltv(
        actual_collected_minor=50000, contribution_margin_ratio=None,
        expected_periods=None)
    assert unprojectable["actual_collected_minor"] == 50000
    assert unprojectable["projected_ltv_minor"] is None
    assert unprojectable["status"] == "INSUFFICIENT_DATA"
    projected = scoring.ltv(
        actual_collected_minor=50000, contribution_margin_ratio=0.5,
        expected_periods=2)
    assert projected["projected_ltv_minor"] == 50000
    assert projected["status"] == "ESTIMATE"
    assert "contribution" in projected["methodology"]


def test_retention_and_churn():
    assert scoring.retention_rate(0, 0, 0)["status"] == "INSUFFICIENT_DATA"
    result = scoring.retention_rate(10, 12, 5)
    assert result["rate"] == 70.0  # (12 - 5) / 10 x 100
    assert scoring.churn_rate(10, 3)["rate"] == 30.0


def test_funnel_rates_and_bottleneck():
    ordered = [("awareness", 1000), ("interest", 400),
               ("consideration", 100), ("intent", 90),
               ("conversion", 80), ("onboarding", 70),
               ("retention", 40), ("expansion", 20)]
    rates = scoring.funnel_rates(ordered)
    assert rates["steps"][0]["rate"] == 0.4
    # bottleneck = lowest rate with a non-noise base (>= 10)
    assert rates["bottleneck"]["from"] == "interest"
    assert rates["bottleneck"]["rate"] == 0.25
    small = scoring.funnel_rates([("awareness", 5), ("interest", 1)])
    assert small["bottleneck"] is None  # below the evidence floor


def test_ab_result_minimum_evaluation_discipline():
    below = scoring.ab_result({"n": 10, "successes": 9},
                              {"n": 10, "successes": 1},
                              min_per_variant=100)
    assert below["verdict"] == "insufficient_data"
    clear = scoring.ab_result({"n": 200, "successes": 20},
                              {"n": 200, "successes": 60},
                              min_per_variant=100)
    assert clear["verdict"] == "test"
    assert clear["statistically_significant_95"] is True
    flat = scoring.ab_result({"n": 200, "successes": 40},
                             {"n": 200, "successes": 42},
                             min_per_variant=100)
    assert flat["statistically_significant_95"] is False


def test_customer_health_explained():
    health = scoring.customer_health(
        days_since_interaction=None, days_since_purchase=None,
        open_support_issues=3, lifecycle_stage="at_risk")
    assert health["score"] < 50
    factors = [f["factor"] for f in health["factors"]]
    assert "open_support" in factors
    assert "deterministic estimate" in health["note"]


def test_catalogues_are_closed_and_consistent():
    assert len(C.AGENT_ROLES) == 17  # §12 lists seventeen roles
    assert all(role["agent_type"] for role in C.AGENT_ROLES)
    assert "purchased_list" in C.FORBIDDEN_LEAD_SOURCES
    assert "purchased_list" not in C.LEAD_SOURCES
    assert set(C.RECOMMENDATION_KIND_RANK) == {
        "improve", "diversify", "capital_efficiency", "expansion"}
    assert len(C.INTEGRATIONS) == 8
    assert all(set(entry) == {"key", "label", "needed_for"}
               for entry in C.INTEGRATIONS)
