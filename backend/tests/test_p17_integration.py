"""P-17 integration tests: the growth engine's governed flows —
intelligence records, gate-respecting decisions, campaign spend
through P-07, content workflow, lead discipline, CRM conversion and
P-07-backed customer facts, communications that never pretend to
send, and experiments handed to P-08.
"""
from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from tests.p17_support import (  # noqa: F401
    AGENT, OWNER, app_growth, campaign_payload, client_growth,
    customer_revenue, lead_payload, lossmaking_business,
    marketing_expense, owner_http_headers, profitable_business,
    verified_revenue,
)

FULL_FACTORS = {"product_interest": 90, "requirements_fit": 85,
                "budget_compatibility": 80, "business_fit": 85,
                "engagement": 70, "purchase_intent": 80,
                "decision_authority": 60, "timing": 75}


@pytest.mark.asyncio
async def test_engine_status_templates_and_honest_integrations(
        app_growth):
    svc = app_growth.growth
    status = svc.engine_status(OWNER)
    assert status["profitability_gate"]["state"] in ("open", "closed")
    assert status["financial_authority"] == "P-07"
    assert "counts" in status
    integrations = svc.integrations(OWNER)
    assert all(i["state"] == "not_configured"
               for i in integrations["items"])
    roles = svc.agent_roles(OWNER)
    assert roles["count"] == 17
    assert all(r["template_status"] == "published" for r in roles["items"])
    assert all("none" in r["external_send_capability"]
               for r in roles["items"])


@pytest.mark.asyncio
async def test_intelligence_records_score_from_declared_inputs(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="Intel Biz")
    svc.set_brand_profile(OWNER, business_id, {
        "brand_name": "Intel Biz", "tone_of_voice": "plain and honest",
        "prohibited_claims": ["guaranteed results"]})
    persona = svc.create_persona(OWNER, business_id, {
        "segment": "solo founders", "budget_sensitivity": "medium",
        "evidence": [{"kind": "assumption", "note": "from owner notes"}]})
    assert persona["segment"] == "solo founders"
    with pytest.raises(ValidationError):
        svc.create_persona(OWNER, business_id, {
            "segment": "x", "evidence": [{"kind": "scraped"}]})
    icp = svc.create_icp(OWNER, business_id, {
        "kind": "b2b", "segment": "agencies",
        "factor_scores": {"product_fit": 90, "demand": 80}})
    assert icp["priority_score"] > 0
    assert len(icp["scoring"]["missing_factors"]) == 4
    channel = svc.create_channel_evaluation(OWNER, business_id, {
        "channel_key": "seo",
        "factor_scores": {"audience_fit": 90, "economics": 80}})
    assert channel["expected_value_score"] > 0
    ranking = svc.channel_ranking(OWNER, business_id)
    assert ranking["items"][0]["channel_key"] == "seo"
    assert "paid_social" not in ranking  # not a channel key at all
    assert "search_ads" in ranking["not_evaluated"]


@pytest.mark.asyncio
async def test_expansion_strategy_blocked_by_gate_until_override(
        app_growth):
    svc = app_growth.growth
    business_id = await lossmaking_business(app_growth, name="Gate Biz")
    strategy = svc.create_strategy(OWNER, business_id, {
        "title": "Expand into paid ads", "kind": "expansion",
        "approach": "performance"})
    with pytest.raises(ValidationError) as exc:
        svc.decide_strategy(OWNER, strategy["id"], "approve")
    assert "profitability gate" in str(exc.value)
    decided = svc.decide_strategy(
        OWNER, strategy["id"], "approve",
        gate_override_reason="owner accepts the risk for a bounded test")
    assert decided["status"] == "approved"
    assert decided["gate_override"]["reason"].startswith("owner accepts")


@pytest.mark.asyncio
async def test_improve_strategy_approves_with_gate_closed(app_growth):
    svc = app_growth.growth
    business_id = await lossmaking_business(app_growth, name="Improve Biz")
    strategy = svc.create_strategy(OWNER, business_id, {
        "title": "Fix the landing page", "kind": "improve",
        "approach": "content"})
    decided = svc.decide_strategy(OWNER, strategy["id"], "approve")
    assert decided["status"] == "approved"
    assert decided["gate_override"] is None


@pytest.mark.asyncio
async def test_campaign_spend_flows_through_p07_and_attributes(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="Campaign Biz")
    campaign = svc.create_campaign(OWNER, business_id, campaign_payload())
    assert campaign["attribution_channel"] == "p17-launch-week-push"
    approved = svc.approve_campaign(OWNER, campaign["id"])
    assert approved["status"] == "approved"
    assert approved["approval_id"]
    prepared = svc.prepare_spend_request(
        OWNER, campaign["id"], {"amount_minor": 100000})
    request = prepared["spending_request"]
    assert request["project_ref"] == f"p17-campaign:{campaign['id']}"
    # the request alone is not spend; recording the expense in P-07 is
    await marketing_expense(app_growth, business_id, "750.00",
                            campaign_id=campaign["id"])
    await verified_revenue(app_growth, business_id, "3000.00",
                           channel="p17-launch-week-push")
    metrics = svc.campaign_metrics(OWNER, campaign["id"])
    assert metrics["spend"]["actual_spend_minor"] == 75000
    assert metrics["attributed_revenue_minor"] == 300000
    assert "ATTRIBUTED" in metrics["attributed_revenue_label"]
    assert metrics["contribution_minor"] == 225000
    budget = svc.budget_view(OWNER, business_id)
    row = budget["campaigns"][0]
    assert row["budget_ceiling_minor"] == 500000
    assert row["actual_spend_minor"] == 75000
    assert row["remaining_minor"] == 425000


@pytest.mark.asyncio
async def test_campaign_spend_beyond_ceiling_refused(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="Ceiling Biz")
    campaign = svc.create_campaign(
        OWNER, business_id, campaign_payload(budget_ceiling_minor=1000))
    svc.approve_campaign(OWNER, campaign["id"])
    with pytest.raises(ValidationError):
        svc.prepare_spend_request(OWNER, campaign["id"],
                                  {"amount_minor": 1001})


@pytest.mark.asyncio
async def test_content_workflow_and_brand_block(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="Content Biz")
    svc.set_brand_profile(OWNER, business_id, {
        "brand_name": "Content Biz",
        "prohibited_claims": ["guaranteed results"]})
    bad = svc.create_content(OWNER, business_id, {
        "kind": "landing_copy", "title": "Landing",
        "body": "Get guaranteed results in 7 days!"})
    reviewed = svc.review_content(OWNER, bad["id"], "brand_consistency",
                                  "pass")
    assert reviewed["brand_check"] == "failed_mechanically"
    assert reviewed["review"]["brand_consistency"]["status"] == "fail"
    good = svc.create_content(OWNER, business_id, {
        "kind": "blog_article", "title": "Honest guide",
        "body": "A practical guide with realistic expectations."})
    for section in ("fact_check", "brand_consistency",
                    "copyright_licensing", "quality"):
        svc.review_content(OWNER, good["id"], section, "pass")
    approved = svc.approve_content(OWNER, good["id"])
    assert approved["status"] == "approved"
    released = svc.release_content(
        OWNER, good["id"], "owner published at example.com/guide")
    assert released["status"] == "released"
    assert "posted nothing" in released["release_label"]


@pytest.mark.asyncio
async def test_lead_discipline_dedupe_consent_suppression(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="Lead Biz")
    with pytest.raises(ValidationError):
        svc.create_lead(OWNER, business_id,
                        lead_payload(source="purchased_list"))
    with pytest.raises(ValidationError):
        svc.create_lead(OWNER, business_id,
                        lead_payload(source="scraped"))
    lead = svc.create_lead(OWNER, business_id, lead_payload())
    assert lead["deduplicated"] is False
    again = svc.create_lead(OWNER, business_id, lead_payload())
    assert again["deduplicated"] is True
    assert again["id"] == lead["id"]
    scored = svc.score_lead(OWNER, lead["id"], FULL_FACTORS)
    assert scored["score_band"] in ("qualified_prospect", "high_priority")
    with pytest.raises(ValidationError):
        svc.score_lead(OWNER, lead["id"], {"purchase_history": 50})
    template = svc.create_template(OWNER, {
        "name": "Welcome", "kind": "welcome", "business_id": business_id,
        "subject": "Welcome", "body": "Thanks for your interest."})
    queued = svc.queue_message(OWNER, {"template_id": template["id"],
                                       "lead_id": lead["id"]})
    assert queued["status"] == "queued"
    assert "no email/SMS/social transport" in queued["dispatch_note"]
    dispatched = svc.dispatch_message(OWNER, queued["id"])
    assert dispatched["dispatched"] is False
    assert dispatched["status"] == "dispatch_blocked"
    svc.suppress_lead(OWNER, lead["id"], "opt_out")
    with pytest.raises(ValidationError):
        svc.queue_message(OWNER, {"template_id": template["id"],
                                  "lead_id": lead["id"]})
    with pytest.raises(ValidationError):
        svc.create_lead(OWNER, business_id, lead_payload())


@pytest.mark.asyncio
async def test_deceptive_template_refused(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="Pushy Biz")
    with pytest.raises(ValidationError):
        svc.create_template(OWNER, {
            "name": "Pushy", "kind": "sales_outreach",
            "business_id": business_id, "subject": "Act now or lose it",
            "body": "Guaranteed results if you act now or lose out!"})


@pytest.mark.asyncio
async def test_crm_conversion_purchases_ltv_and_health(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="CRM Biz")
    lead = svc.create_lead(OWNER, business_id, lead_payload())
    svc.transition_lead(OWNER, lead["id"], "converted")
    customer = svc.convert_lead(OWNER, lead["id"])
    assert customer["lifecycle_stage"] == "onboarding"
    assert customer["source_lead_id"] == lead["id"]
    ref = customer["p07_customer_ref"]
    await customer_revenue(app_growth, business_id, "1200.00",
                           customer_ref=ref)
    await customer_revenue(app_growth, business_id, "800.00",
                           customer_ref=ref)
    detail = svc.customer_detail(OWNER, customer["id"])
    assert detail["purchases"]["count"] == 2
    assert detail["purchases"]["total_minor"] == 200000
    assert detail["ltv"]["actual_collected_minor"] == 200000
    assert detail["ltv"]["projected_ltv_minor"] is None
    svc.record_interaction(OWNER, customer["id"], {
        "kind": "support", "summary": "login problem"})
    health = svc.recompute_customer_health(OWNER, customer["id"])
    assert health["health"]["score"] is not None
    assert health["health_factors"]["factors"]


@pytest.mark.asyncio
async def test_funnel_declared_vs_system_counts(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="Funnel Biz")
    svc.record_funnel_event(OWNER, business_id, {
        "stage": "awareness", "count": 1000, "source": "declared",
        "period_start": "2026-11-01", "period_end": "2026-11-07"})
    svc.record_funnel_event(OWNER, business_id, {
        "stage": "interest", "count": 250, "source": "imported",
        "period_start": "2026-11-01", "period_end": "2026-11-07"})
    svc.create_lead(OWNER, business_id, lead_payload())
    summary = svc.funnel_summary(OWNER, business_id)
    assert summary["declared_counts"]["awareness"] == 1000
    assert "DECLARED" in summary["declared_label"]
    assert summary["system_counts"]["leads_recorded"] == 1
    assert summary["conversion_rates"][0]["rate"] == 0.25
    with pytest.raises(ValidationError):
        svc.record_funnel_event(OWNER, business_id, {
            "stage": "awareness", "count": 5, "source": "measured",
            "period_start": "2026-11-01", "period_end": "2026-11-07"})


@pytest.mark.asyncio
async def test_seo_records_require_honest_sources(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="SEO Biz")
    with pytest.raises(ValidationError):
        svc.create_seo_record(OWNER, business_id, {
            "kind": "keyword_set", "source": "live_search_console",
            "title": "Keywords",
            "data": {"keywords": ["x"], "search_intent": "buy",
                     "competition": "low"}})
    svc.create_seo_record(OWNER, business_id, {
        "kind": "keyword_set", "source": "declared",
        "title": "Core keywords",
        "data": {"keywords": ["beginner fitness plan"],
                 "search_intent": "informational",
                 "competition": "medium"}})
    summary = svc.seo_summary(OWNER, business_id)
    assert summary["by_kind"]["keyword_set"] == 1
    assert "no live third-party" in summary["label"]


@pytest.mark.asyncio
async def test_experiment_predeclared_handoff_and_conclusion(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="Exp Biz")
    with pytest.raises(ValidationError):
        svc.create_experiment(OWNER, business_id, {
            "title": "Vague test", "hypothesis": "",
            "primary_metric": "signup_rate", "minimum_evaluation": {},
            "duration_days": 14})
    experiment = svc.create_experiment(OWNER, business_id, {
        "title": "Headline test", "hypothesis": "clearer headline "
        "lifts signups", "primary_metric": "signup_rate",
        "minimum_evaluation": {"min_observations_per_variant": 100},
        "duration_days": 14, "budget_ceiling_minor": 50000,
        "control_description": "old headline",
        "test_description": "new headline"})
    svc.approve_experiment(OWNER, experiment["id"])
    svc.update_settings(OWNER, {"autonomy_level": 3})
    handed = svc.handoff_experiment(OWNER, experiment["id"])
    assert handed["p08_experiment_id"]
    p08 = app_growth.survival.experiments.get_experiment(
        handed["p08_experiment_id"])
    assert p08["business_id"] == business_id
    svc.record_observations(OWNER, experiment["id"], {
        "control": {"n": 40, "successes": 4},
        "test": {"n": 40, "successes": 12}})
    concluded = svc.conclude_experiment(OWNER, experiment["id"])
    assert concluded["result"]["verdict"] == "insufficient_data"


@pytest.mark.asyncio
async def test_attribution_methods_and_labels(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="Attr Biz")
    svc.create_customer(OWNER, business_id, {
        "contact": {"email": "sam@example.com", "name": "Sam"},
        "acquisition_channel": "seo"})
    await verified_revenue(app_growth, business_id, "500.00",
                           channel="p17-launch")
    view = svc.attribution(OWNER, business_id)
    assert view["methods"]["multi_touch"]["status"] == "not_available"
    assert view["methods"]["last_touch"]["status"] == "not_available"
    assert view["methods"]["first_touch"]["customer_counts"]["seo"] == 1
    assert "never accounting revenue" in view["label"]


@pytest.mark.asyncio
async def test_auto_pause_not_applied_below_level_4(app_growth):
    svc = app_growth.growth
    result = svc.evaluate_auto_pause(OWNER)
    assert result["status"] == "not_applied"
    assert "level 4" in result["reason"]


@pytest.mark.asyncio
async def test_recommendations_ordering_and_gate(app_growth):
    svc = app_growth.growth
    await lossmaking_business(app_growth, name="Rec Biz")
    view = svc.recommendations(OWNER)
    kinds = [r["kind"] for r in view["items"]]
    assert kinds == sorted(
        kinds, key=lambda k: {"improve": 0, "diversify": 1,
                              "capital_efficiency": 2,
                              "expansion": 3}[k])
    expansion = [r for r in view["items"] if r["kind"] == "expansion"]
    assert expansion and expansion[0]["gate_blocked"] is True


def test_growth_http_surface(client_growth):
    headers = owner_http_headers(client_growth)
    status = client_growth.get("/api/v1/growth/status", headers=headers)
    assert status.status_code == 200
    data = status.json()["data"]
    assert data["financial_authority"] == "P-07"
    roles = client_growth.get("/api/v1/growth/agent-roles",
                              headers=headers)
    assert roles.status_code == 200
    assert roles.json()["data"]["count"] == 17
    overview = client_growth.get("/api/v1/growth/overview",
                                 headers=headers)
    assert overview.status_code == 200
    unauthenticated = client_growth.get("/api/v1/growth/status")
    assert unauthenticated.status_code in (401, 403)
