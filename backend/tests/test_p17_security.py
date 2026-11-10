"""P-17 security tests: cross-business isolation, agent refusal,
Article 0 (no money columns outside P-07; P-07 totals untouched by
P-17 writes), consent/suppression enforcement and the emergency
controls.
"""
from __future__ import annotations

import pytest

from app.core.exceptions import PermissionDeniedError, ValidationError
from app.database import models as _models  # noqa: F401  (registers all)
from app.database.models.base import Base
from tests.p17_support import (  # noqa: F401
    AGENT, OWNER, app_growth, campaign_payload, lead_payload,
    lossmaking_business, profitable_business,
)

GROWTH_TABLES = [name for name in Base.metadata.tables
                 if name.startswith((
                     "growth_", "customer_personas",
                     "ideal_customer_profiles", "marketing_",
                     "content_items", "lead_suppressions",
                     "sales_opportunities", "crm_customers",
                     "funnel_events", "seo_records", "communication_",
                     "partnerships"))]


def test_no_money_columns_in_growth_tables():
    assert len(GROWTH_TABLES) == 18
    offenders = []
    for name in GROWTH_TABLES:
        for column in Base.metadata.tables[name].columns:
            lowered = column.name.lower()
            if any(token in lowered for token in (
                    "revenue", "profit", "journal", "ledger",
                    "collected")):
                offenders.append(f"{name}.{column.name}")
    assert offenders == [], offenders


@pytest.mark.asyncio
async def test_p17_writes_never_touch_p07_books(app_growth):
    """Article 0 / §21: after a full round of P-17 writes, P-07's
    figures are byte-identical — growth state is not money."""
    business_id = await profitable_business(app_growth, name="Books Biz")
    fin = app_growth.financial
    before_metrics = fin.revenue.metrics(business_id, "INR")
    before_expenses = fin.expenses.totals(business_id, "INR")
    before_summary = fin.business_summary(business_id)
    svc = app_growth.growth
    campaign = svc.create_campaign(OWNER, business_id, campaign_payload())
    svc.approve_campaign(OWNER, campaign["id"])
    lead = svc.create_lead(OWNER, business_id, lead_payload())
    svc.score_lead(OWNER, lead["id"], {"product_interest": 80})
    svc.transition_lead(OWNER, lead["id"], "converted")
    svc.convert_lead(OWNER, lead["id"])
    svc.create_strategy(OWNER, business_id, {
        "title": "Improve onboarding", "kind": "improve"})
    assert fin.revenue.metrics(business_id, "INR") == before_metrics
    assert fin.expenses.totals(business_id, "INR") == before_expenses
    assert fin.business_summary(business_id) == before_summary


@pytest.mark.asyncio
async def test_cross_business_isolation(app_growth):
    svc = app_growth.growth
    biz_a = await profitable_business(app_growth, name="Iso A")
    biz_b = await profitable_business(app_growth, name="Iso B")
    lead = svc.create_lead(OWNER, biz_a, lead_payload())
    assert svc.list_leads(OWNER, biz_b)["count"] == 0
    # the same contact may exist independently in business B
    other = svc.create_lead(OWNER, biz_b, lead_payload())
    assert other["id"] != lead["id"]
    # suppression in A does not leak into B, and B's lead stays usable
    svc.suppress_lead(OWNER, lead["id"], "opt_out")
    template = svc.create_template(OWNER, {
        "name": "Hello", "kind": "welcome", "business_id": biz_a,
        "body": "A straightforward introduction."})
    template_b = svc.create_template(OWNER, {
        "name": "Hello B", "kind": "welcome", "business_id": biz_b,
        "body": "A straightforward introduction."})
    queued = svc.queue_message(OWNER, {"template_id": template_b["id"],
                                       "lead_id": other["id"]})
    assert queued["business_id"] == biz_b
    # a template owned by A cannot message B's lead
    template_a = svc.create_template(OWNER, {
        "name": "A only", "kind": "welcome", "business_id": biz_a,
        "body": "For business A customers."})
    with pytest.raises(ValidationError):
        svc.queue_message(OWNER, {"template_id": template_a["id"],
                                  "lead_id": other["id"]})


@pytest.mark.asyncio
async def test_agent_cannot_govern_growth(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="Agent Biz")
    with pytest.raises(PermissionDeniedError):
        svc.create_campaign(AGENT, business_id, campaign_payload())
    with pytest.raises(PermissionDeniedError):
        svc.update_settings(AGENT, {"autonomy_level": 4})
    with pytest.raises(PermissionDeniedError):
        svc.growth_overview(AGENT)


@pytest.mark.asyncio
async def test_emergency_controls_bite(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="Stop Biz")
    campaign = svc.create_campaign(OWNER, business_id, campaign_payload())
    svc.approve_campaign(OWNER, campaign["id"])
    svc.update_settings(OWNER, {"all_campaigns_paused": True,
                                "marketing_spend_frozen": True,
                                "communications_stopped": True})
    with pytest.raises(ValidationError):
        svc.transition_campaign(OWNER, campaign["id"], "active")
    with pytest.raises(ValidationError):
        svc.prepare_spend_request(OWNER, campaign["id"],
                                  {"amount_minor": 100})
    lead = svc.create_lead(OWNER, business_id, lead_payload())
    template = svc.create_template(OWNER, {
        "name": "T", "kind": "product_update", "business_id": business_id,
        "body": "Plain update."})
    with pytest.raises(ValidationError):
        svc.queue_message(OWNER, {"template_id": template["id"],
                                  "lead_id": lead["id"]})


@pytest.mark.asyncio
async def test_frequency_limit_enforced(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="Freq Biz")
    svc.update_settings(OWNER, {"comm_frequency_limit_per_30d": 2})
    lead = svc.create_lead(OWNER, business_id, lead_payload())
    template = svc.create_template(OWNER, {
        "name": "News", "kind": "newsletter", "business_id": business_id,
        "body": "Monthly news."})
    svc.queue_message(OWNER, {"template_id": template["id"],
                              "lead_id": lead["id"]})
    svc.queue_message(OWNER, {"template_id": template["id"],
                              "lead_id": lead["id"]})
    with pytest.raises(ValidationError):
        svc.queue_message(OWNER, {"template_id": template["id"],
                                  "lead_id": lead["id"]})


@pytest.mark.asyncio
async def test_unknown_consent_cannot_be_messaged(app_growth):
    svc = app_growth.growth
    business_id = await profitable_business(app_growth, name="Consent Biz")
    lead = svc.create_lead(OWNER, business_id,
                           lead_payload(consent_status="unknown"))
    template = svc.create_template(OWNER, {
        "name": "T", "kind": "welcome", "business_id": business_id,
        "body": "Hello there."})
    with pytest.raises(ValidationError):
        svc.queue_message(OWNER, {"template_id": template["id"],
                                  "lead_id": lead["id"]})
