"""P-17 scenario tests: the full acquisition lifecycle end to end,
mirroring the phase prompt's operating story — research, strategy,
campaign, content, leads, conversion, attribution and the honest
limits at each step.
"""
from __future__ import annotations

import pytest

from tests.p17_support import (  # noqa: F401
    OWNER, app_growth, customer_revenue, lead_payload,
    marketing_expense, profitable_business, verified_revenue,
)


@pytest.mark.asyncio
async def test_full_acquisition_lifecycle(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(
        app_growth, name="Lifecycle Biz", revenue="20000.00",
        expense="3000.00", opening="8000.00")

    # research and positioning (§4/§6)
    svc.set_brand_profile(OWNER, business_id, {
        "brand_name": "Lifecycle Biz", "tone_of_voice": "direct",
        "prohibited_claims": ["guaranteed results", "miracle"]})
    svc.create_persona(OWNER, business_id, {
        "segment": "fitness beginners", "budget_sensitivity": "medium",
        "evidence": [{"kind": "hypothesis",
                      "note": "to be validated by first campaign"}]})
    icp = svc.create_icp(OWNER, business_id, {
        "kind": "b2c", "segment": "beginners 25-40",
        "factor_scores": {"product_fit": 90, "demand": 85,
                          "commercial_potential": 90,
                          "acquisition_feasibility": 80,
                          "retention_potential": 75,
                          "strategic_fit": 85}})
    assert icp["priority_score"] > 50
    svc.create_channel_evaluation(OWNER, business_id, {
        "channel_key": "seo", "status": "recommended",
        "factor_scores": {"audience_fit": 90, "economics": 95,
                          "conversion_potential": 60}})

    # strategy (§5) — improve kind, gate is open anyway
    strategy = svc.create_strategy(OWNER, business_id, {
        "title": "Organic content engine", "kind": "improve",
        "approach": "content",
        "sections": {"objectives": "first 10 customers",
                     "channels": ["seo"],
                     "performance_metrics": ["cac below 20000 minor"]}})
    svc.decide_strategy(OWNER, strategy["id"], "approve")

    # campaign (§7) with P-07 spend and attributed revenue (§21/§22)
    campaign = svc.create_campaign(OWNER, business_id, {
        "name": "Beginner Guide Launch", "purpose": "acquisition",
        "channel_key": "seo", "strategy_id": strategy["id"],
        "budget_ceiling_minor": 300000,
        "expected_results": {"max_cac_minor": 25000}})
    svc.approve_campaign(OWNER, campaign["id"])
    svc.transition_campaign(OWNER, campaign["id"], "active")
    svc.prepare_spend_request(OWNER, campaign["id"],
                              {"amount_minor": 120000})
    await marketing_expense(app_growth, business_id, "1200.00",
                            campaign_id=campaign["id"])
    await verified_revenue(app_growth, business_id, "4500.00",
                           channel="p17-beginner-guide-launch")

    # content (§6) through the full review workflow
    content = svc.create_content(OWNER, business_id, {
        "kind": "blog_article", "title": "Start in 7 days",
        "campaign_id": campaign["id"],
        "body": "A realistic starter plan."})
    for section in ("fact_check", "brand_consistency",
                    "copyright_licensing", "quality"):
        svc.review_content(OWNER, content["id"], section, "pass")
    svc.approve_content(OWNER, content["id"])
    svc.release_content(OWNER, content["id"],
                        "owner published on the business blog")

    # leads (§8/§9) → conversion (§10/§11)
    for index in range(3):
        lead = svc.create_lead(OWNER, business_id, lead_payload(
            contact={"email": f"user{index}@example.com",
                     "name": f"User {index}"},
            campaign_id=campaign["id"]))
        svc.score_lead(OWNER, lead["id"], {"product_interest": 85,
                                           "purchase_intent": 75})
    first = svc.list_leads(OWNER, business_id)["items"][0]
    svc.transition_lead(OWNER, first["id"], "converted")
    customer = svc.convert_lead(OWNER, first["id"])
    await customer_revenue(app_growth, business_id, "999.00",
                           customer_ref=customer["p07_customer_ref"],
                           channel="p17-beginner-guide-launch")

    metrics = svc.campaign_metrics(OWNER, campaign["id"])
    assert metrics["spend"]["actual_spend_minor"] == 120000
    assert metrics["attributed_revenue_minor"] == 549900
    assert metrics["leads"] == 3
    assert metrics["converted_customers"] == 1
    assert metrics["cac"]["cac_minor"] == 120000

    overview = svc.growth_overview(OWNER)
    assert overview["totals"]["customers"] == 1
    assert overview["profitability_gate"]["state"] == "open"

    attribution = svc.attribution(OWNER, business_id)
    assert attribution["campaigns"][0]["attributed_revenue_minor"] == 549900

    retention = svc.retention_analytics(OWNER, business_id)
    assert retention["customers_total"] == 1

    portfolio = svc.portfolio_growth(OWNER)
    assert portfolio["businesses"][0]["business_id"] == business_id
    assert portfolio["cross_promotion"]["status"] == "owner_governed"


@pytest.mark.asyncio
async def test_partnership_referral_attribution(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="Partner Biz")
    partner = svc.create_partnership(OWNER, business_id, {
        "partner_name": "Local Gym", "kind": "referral",
        "terms": {"basis": "owner-negotiated; recorded only"}})
    assert partner["referral_channel"] == "partner-local-gym"
    svc.transition_partnership(OWNER, partner["id"], "negotiation")
    svc.transition_partnership(OWNER, partner["id"], "agreement_approved")
    active = svc.transition_partnership(OWNER, partner["id"], "active")
    assert active["approval_id"]
    await verified_revenue(app_growth, business_id, "700.00",
                           channel="partner-local-gym")
    listed = svc.list_partnerships(OWNER, business_id)
    assert listed["items"][0]["attributed_revenue_minor"] == 70000
    assert "not guaranteed partner earnings" in \
        listed["items"][0]["attributed_revenue_label"]
