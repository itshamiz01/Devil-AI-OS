"""P-03 unit tests: lifecycle, compliance, commercial math, evidence
discipline, scoring rules, validation gates, source extraction/SSRF."""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from app.opportunities import analysis as analysis_mod
from app.opportunities import commercial as commercial_mod
from app.opportunities import compliance as compliance_mod
from app.opportunities import scoring as scoring_mod
from app.opportunities import validation as validation_mod
from app.opportunities.evidence import (
    apply_corroboration, evidence_gaps, evidence_quality, freshness_for,
)
from app.opportunities.lifecycle import can_transition, slugify_opportunity
from app.opportunities.sources import (
    TransportError, assert_url_allowed, extract_price_mentions, html_to_text, parse_feed,
)


def rec(**kw):
    base = dict(id=kw.pop("id", "e1"), claim="", category="demand",
                classification="UNVERIFIED", evidence_kind="source_claim",
                topic_key="", independence_group="", source_id=None,
                source_url=None, retrieval_timestamp=object(), recorded_by="opportunity-engine")
    base.update(kw)
    return NS(**base)


# ---------------------------------------------------------------- lifecycle
def test_lifecycle_happy_path_and_terminal_states():
    assert can_transition("DISCOVERED", "INITIAL_SCREENING")
    assert can_transition("INITIAL_SCREENING", "RESEARCHING")
    assert can_transition("RESEARCHING", "EVIDENCE_REVIEW")
    assert can_transition("EVIDENCE_REVIEW", "COMMERCIAL_ANALYSIS")
    assert can_transition("COMMERCIAL_ANALYSIS", "VALIDATION_PENDING")
    assert can_transition("VALIDATION_PENDING", "VALIDATED")
    assert can_transition("VALIDATED", "RECOMMENDED")
    assert not can_transition("DISCOVERED", "RECOMMENDED")
    assert not can_transition("ARCHIVED", "RESEARCHING")
    assert not can_transition("REJECTED", "RESEARCHING")
    assert can_transition("NEEDS_MORE_EVIDENCE", "RESEARCHING")
    assert can_transition("OUTDATED", "RESEARCHING")


def test_slugify_dedup_key_normalises_case_and_punctuation():
    a = slugify_opportunity("Printable Weekly Planner Templates", "digital_products", "global")
    b = slugify_opportunity("Printable weekly planner templates", "digital_products", "Global")
    assert a == b
    c = slugify_opportunity("Printable Weekly Planner Templates", "content", "global")
    assert a != c


# --------------------------------------------------------------- compliance
def _opp(**kw):
    base = dict(name="", description="", problem_statement="", proposed_solution="",
                revenue_model="", category="content")
    base.update(kw)
    return NS(**base)


def test_compliance_prohibited_fake_reviews():
    result = compliance_mod.screen(_opp(
        name="Paid Fake-Review Writing Service",
        description="selling paid fake reviews", proposed_solution="post fake reviews"))
    assert result["verdict"] == "prohibited"
    assert any(r["rule"] == "fake_reviews" for r in result["matched_rules"])


def test_compliance_prohibited_guaranteed_income():
    result = compliance_mod.screen(_opp(
        name="Income system", description="a guaranteed income program"))
    assert result["verdict"] == "prohibited"


def test_compliance_high_risk_flag_not_prohibited():
    result = compliance_mod.screen(_opp(
        name="Clinic reminders", description="processing patient contact data for clinics"))
    assert result["verdict"] == "flagged"
    assert result["requires_professional_review"] is True
    assert any(f["flag"] == "personal_data_processing" for f in result["flags"])


def test_compliance_clear_business():
    result = compliance_mod.screen(_opp(
        name="Planner templates", description="printable weekly planners",
        category="digital_products"))
    assert result["verdict"] == "clear"


# ---------------------------------------------------------------- commercial
def test_commercial_break_even_and_scenarios():
    out = commercial_mod.compute_commercial(
        startup_costs=[{"name": "domain", "amount": 12, "classification": "estimate"}],
        recurring_costs_monthly=[{"name": "hosting", "amount": 10, "classification": "estimate"}],
        variable_costs_per_sale=[{"name": "delivery", "amount": 1, "classification": "estimate"}],
        price={"amount": 20, "classification": "estimate", "basis": "test"},
        platform_fee_pct=10, payment_fee_pct=0,
        scenario_sales={"base": {"sales_per_month": 10, "assumptions": ["stated"]}},
        budget_amount=50)
    # contribution/sale = 20 - 1 - 2 = 17; break-even = ceil(10/17) = 1
    assert out["break_even"]["feasible"] is True
    assert out["break_even"]["break_even_sales_per_month"] == 1
    base = out["scenarios"]["base"]
    assert base["revenue"] == 200 and base["contribution_margin"] == 170
    assert base["operating_profit"] == 160
    assert out["budget"]["compatible"] is True


def test_commercial_unknown_costs_are_not_zero_costs():
    out = commercial_mod.compute_commercial(
        startup_costs=[{"name": "licence", "amount": None, "classification": "unknown"}],
        recurring_costs_monthly=[], variable_costs_per_sale=[],
        price=None, budget_amount=None)
    assert out["totals"]["startup_total_known"] == 0
    assert out["totals"]["startup_has_unknown"] is True
    assert out["scenarios"] == {} and out["scenario_notes"]  # no invented price
    assert out["budget"]["compatible"] is None  # not assumed


def test_commercial_negative_contribution_cannot_break_even():
    out = commercial_mod.compute_commercial(
        startup_costs=[], recurring_costs_monthly=[{"name": "h", "amount": 5, "classification": "estimate"}],
        variable_costs_per_sale=[{"name": "v", "amount": 30, "classification": "estimate"}],
        price={"amount": 20, "classification": "estimate"},
        scenario_sales={"base": {"sales_per_month": 5, "assumptions": []}},
        budget_amount=1000)
    assert out["break_even"]["feasible"] is False


def test_commercial_budget_incompatible():
    out = commercial_mod.compute_commercial(
        startup_costs=[{"name": "inventory", "amount": 900, "classification": "estimate"}],
        recurring_costs_monthly=[{"name": "ads", "amount": 200, "classification": "estimate"}],
        variable_costs_per_sale=[], price={"amount": 10, "classification": "estimate"},
        budget_amount=50)
    assert out["budget"]["compatible"] is False
    assert out["budget"]["budget_amount"] == 50  # never raised


# ------------------------------------------------------------------ evidence
def test_freshness_unknown_without_publication_date():
    assert freshness_for(None) == "unknown"
    assert freshness_for("not a date") == "unknown"
    assert freshness_for("2019-03-01") == "stale"


def test_corroboration_requires_independent_groups():
    same_group = [
        rec(id="a", topic_key="fee", classification="SUPPORTING", independence_group="g1"),
        rec(id="b", topic_key="fee", classification="SUPPORTING", independence_group="g1"),
    ]
    changes = apply_corroboration(same_group, {})
    assert changes == []  # syndicated copies do not count twice

    independent = [
        rec(id="a", topic_key="fee", classification="SUPPORTING", independence_group="g1"),
        rec(id="b", topic_key="fee", classification="SUPPORTING", independence_group="g2"),
    ]
    changes = apply_corroboration(independent, {})
    assert {c["to"] for c in changes} == {"CORROBORATED"}
    assert all(r.classification == "CORROBORATED" for r in independent)


def test_contradiction_outlier_flagged_majority_stands():
    records = [
        rec(id="a", topic_key="fee", claim="fee is $0.20", classification="SUPPORTING", independence_group="g1"),
        rec(id="b", topic_key="fee", claim="fee is $0.20", classification="SUPPORTING", independence_group="g2"),
        rec(id="c", topic_key="fee", claim="fee is $0.50", classification="UNVERIFIED", independence_group="g3"),
    ]
    apply_corroboration(records, {})
    by_id = {r.id: r.classification for r in records}
    assert by_id["c"] == "CONTRADICTED"
    assert by_id["a"] == "CORROBORATED" and by_id["b"] == "CORROBORATED"


def test_contradiction_tie_flags_both():
    records = [
        rec(id="a", topic_key="fee", claim="price $10", classification="SUPPORTING", independence_group="g1"),
        rec(id="b", topic_key="fee", claim="price $30", classification="SUPPORTING", independence_group="g2"),
    ]
    apply_corroboration(records, {})
    assert all(r.classification == "CONTRADICTED" for r in records)


def test_evidence_quality_zero_without_evidence():
    score, breakdown = evidence_quality([])
    assert score == 0.0 and breakdown["records"] == 0


def test_evidence_quality_rewards_verified_independent_coverage():
    records = [
        rec(category="demand", classification="VERIFIED", independence_group="g1", source_id="s1"),
        rec(category="problem", classification="CORROBORATED", independence_group="g2", source_id="s2"),
        rec(category="pricing", classification="SUPPORTING", independence_group="g3", source_id="s3"),
    ]
    score, _ = evidence_quality(records)
    assert score > 3.0


def test_evidence_gaps_report_missing_demand_and_market_size():
    gaps = evidence_gaps([], has_commercial=False, competitor_count=0)
    text = " ".join(gaps)
    assert "demand" in text and "market-size" in text


# ------------------------------------------------------------------- scoring
def _scoring_ctx(**over):
    opp = NS(name="X", category="digital_products", revenue_model="marketplace_sales",
             capability_fit={}, compliance={"verdict": "clear"})
    ctx = {"opportunity": opp, "records": [], "market": None, "commercial": None,
           "competitors": [], "capability_fit": {"required": [], "missing": [], "coverage": None},
           "compliance": {"verdict": "clear"}}
    ctx.update(over)
    return ctx


def test_scoring_no_evidence_scores_demand_zero():
    dims, _ = scoring_mod.derive_dimensions(_scoring_ctx())
    assert dims["verified_demand"] == 0.0
    assert dims["profit_potential"] == 0.0  # no base scenario = no evidence


def test_scoring_search_interest_cannot_fake_demand():
    # A demand record that is merely UNVERIFIED (e.g. view counts) caps low.
    records = [rec(category="demand", classification="UNVERIFIED")]
    dims, _ = scoring_mod.derive_dimensions(_scoring_ctx(records=records))
    assert dims["verified_demand"] <= 1.0


def test_scoring_weighted_total_uses_config_weights():
    dims = {k: 5.0 for k in scoring_mod.SCORING_V1_WEIGHTS}
    assert scoring_mod.weighted_total(dims, scoring_mod.SCORING_V1_WEIGHTS) == 5.0
    assert abs(sum(scoring_mod.SCORING_V1_WEIGHTS.values()) - 1.0) < 1e-9


def test_hard_rejection_prohibited_overrides_score():
    ctx = _scoring_ctx(compliance={"verdict": "prohibited",
                                   "matched_rules": [{"rule": "fraud"}]})
    rejection = scoring_mod.hard_rejection(ctx)
    assert rejection and rejection["rule"] == "prohibited_category"


def test_hard_rejection_impossible_budget():
    commercial = NS(budget={"compatible": False}, distribution={"legitimate_channel_count": 2},
                    scenarios={}, break_even={}, price_assumption={})
    rejection = scoring_mod.hard_rejection(_scoring_ctx(commercial=commercial))
    assert rejection and rejection["rule"] == "impossible_budget"


def test_recommendation_capped_by_weak_evidence():
    # Attractive numbers + weak evidence must not look strong (§16.3).
    label = scoring_mod.recommendation_for(4.8, 1.0, None, 3, False)
    assert label == "REQUIRES MORE RESEARCH"
    label = scoring_mod.recommendation_for(4.8, 3.5, None, 3, False)
    assert label == "STRONG CANDIDATE"


# ---------------------------------------------------------------- validation
def _validation_ctx(**over):
    ctx = {"records": [], "sessions_completed": False, "has_market": False,
           "competitor_count": 0, "commercial": None}
    ctx.update(over)
    return ctx


def test_validation_level_zero_without_research():
    level, _met, missing = validation_mod.assess_level(_validation_ctx(), reviewer_is_owner=True)
    assert level == 0 and missing


def test_validation_level_two_needs_independent_corroborated_evidence():
    records = [
        rec(category="problem", classification="SUPPORTING", independence_group="g1"),
        rec(category="demand", classification="CORROBORATED", independence_group="g2"),
    ]
    ctx = _validation_ctx(records=records, sessions_completed=True, has_market=True)
    level, _met, _missing = validation_mod.assess_level(ctx, reviewer_is_owner=True)
    assert level == 2


def test_validation_level_four_impossible_from_search_volume():
    # Even maximal source_claim evidence cannot reach Level 4 (§18.3).
    records = [
        rec(category="demand", classification="VERIFIED", independence_group="g1"),
        rec(category="problem", classification="CORROBORATED", independence_group="g2"),
    ]
    commercial = NS(scenarios={"base": {}}, break_even={"feasible": True}, distribution={"x": 1})
    ctx = _validation_ctx(records=records, sessions_completed=True, has_market=True,
                          commercial=commercial)
    level, _met, missing = validation_mod.assess_level(ctx, reviewer_is_owner=True)
    assert level == 3
    assert any("Level 4" in m for m in missing)


def test_validation_level_five_needs_owner_payment_and_owner_reviewer():
    records = [
        rec(category="problem", classification="CORROBORATED", independence_group="g1"),
        rec(category="demand", classification="SUPPORTING", independence_group="g2"),
        rec(category="demand", classification="VERIFIED", evidence_kind="owner_real_world",
            independence_group="owner"),
    ]
    commercial = NS(scenarios={"base": {}}, break_even={"feasible": True}, distribution={"x": 1})
    ctx = _validation_ctx(records=records, sessions_completed=True, has_market=True,
                          commercial=commercial)
    level, _m, _x = validation_mod.assess_level(ctx, reviewer_is_owner=True)
    assert level == 4  # no payment evidence yet
    records.append(rec(category="purchasing_intent", classification="VERIFIED",
                       evidence_kind="owner_payment", independence_group="owner"))
    level, _m, _x = validation_mod.assess_level(ctx, reviewer_is_owner=False)
    assert level == 4  # non-owner reviewer cannot confer Level 5
    level, _m, _x = validation_mod.assess_level(ctx, reviewer_is_owner=True)
    assert level == 5


# ------------------------------------------------------------------- sources
def test_ssrf_guard_blocks_private_and_loopback():
    for url in ("http://127.0.0.1:8000/admin", "http://localhost/x",
                "https://169.254.169.254/latest/meta-data", "file:///etc/passwd",
                "ftp://example.com/x", "https://10.0.0.5/"):
        with pytest.raises(TransportError):
            assert_url_allowed(url)
    assert assert_url_allowed("https://example.com/pricing") == "https://example.com/pricing"


def test_html_to_text_strips_scripts():
    title, text = html_to_text(
        "<html><head><title>Prices</title><script>evil()</script></head>"
        "<body><p>Plan costs $39 per month</p></body></html>")
    assert title == "Prices"
    assert "evil" not in text and "$39" in text


def test_price_extraction_is_verbatim():
    mentions = extract_price_mentions("Basic is $39 per month, Pro is $99 per month, and a book costs $5.")
    amounts = {(m["amount"], m["currency"], m["per_month"]) for m in mentions}
    assert (39.0, "USD", True) in amounts
    assert (99.0, "USD", True) in amounts
    assert (5.0, "USD", False) in amounts


def test_parse_feed_rss_items():
    xml = """<rss><channel>
      <item><title>Post One</title><link>https://example.com/1</link>
      <description>Summary</description><pubDate>Mon, 03 Nov 2026 00:00:00 GMT</pubDate></item>
    </channel></rss>"""
    items = parse_feed(xml)
    assert len(items) == 1 and items[0]["title"] == "Post One"
    assert items[0]["published"].startswith("Mon, 03 Nov 2026")


def test_market_size_cannot_be_established_without_evidence():
    size = analysis_mod.market_size_from_evidence([])
    for level in ("tam", "sam", "som"):
        assert size[level]["value_text"] is None
        assert "cannot be established" in size[level]["note"]


def test_saturation_unknown_without_competitors():
    result = analysis_mod.saturation_assessment([], [])
    assert result["level"] == "unknown"
