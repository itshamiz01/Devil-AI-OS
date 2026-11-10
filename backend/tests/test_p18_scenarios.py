"""P-18 scenario tests: complete customer journeys across
business models, run end to end on governed paths — the §24
release scenarios in executable form.
"""
from __future__ import annotations

import pytest

from app.database.models.experience import CxOnboarding
from tests.conftest import OWNER
from tests.p18_support import (
    app_experience, backdate, customer_revenue, fixture_business,
    make_customer,
)  # noqa: F401


@pytest.mark.asyncio
async def test_scenario_physical_product_journey(app_experience):
    """Purchase -> onboarding -> shipped/delivered -> accepted ->
    feedback -> healthy customer, complaint-free metrics."""
    svc = app_experience.experience
    business_id = await fixture_business(app_experience,
                                         name="Physical Shop")
    customer = make_customer(app_experience, business_id,
                             p07_customer_ref="cust-phys-1")
    await customer_revenue(app_experience, business_id, "999.00",
                           customer_ref="cust-phys-1")
    onboarding = svc.start_onboarding(OWNER, business_id, {
        "customer_id": customer["id"],
        "business_model": "physical_product"})
    for step in onboarding["steps"]:
        svc.update_onboarding_step(OWNER, onboarding["id"],
                                   step["key"], "completed")
    fulfil = svc.create_fulfillment(OWNER, business_id, {
        "customer_id": customer["id"], "kind": "physical",
        "title": "Running shoes", "assigned_to": "owner"})
    for status in ("preparing", "shipped", "delivered"):
        svc.transition_fulfillment(OWNER, fulfil["id"],
                                   {"status": status})
    svc.set_acceptance(OWNER, fulfil["id"], "accepted")
    svc.record_feedback(OWNER, business_id, {
        "customer_id": customer["id"], "kind": "csat", "score": 5})
    svc.record_feedback(OWNER, business_id, {
        "customer_id": customer["id"], "kind": "effort", "score": 1})
    detail = svc.customer_detail(OWNER, business_id, customer["id"])
    assert detail["purchase_count"] == 1
    assert detail["csat"]["value"] == 5.0
    health = svc.compute_health(OWNER, business_id, customer["id"])
    assert health["classification"] in ("healthy", "stable")
    metrics = svc.experience_metrics(OWNER, business_id)
    assert metrics["complaint_rate"]["value"] == 0.0


@pytest.mark.asyncio
async def test_scenario_saas_access_problem_recovery(app_experience):
    """Locked-out SaaS customer: grounded KB answer attempt,
    high-priority ticket, escalation, account restoration,
    verified resolution."""
    svc = app_experience.experience
    business_id = await fixture_business(app_experience,
                                         name="SaaS Co")
    customer = make_customer(app_experience, business_id)
    article = svc.create_article(OWNER, business_id, {
        "title": "Reset your password",
        "content": "To reset your password open account settings "
                   "and choose reset password.",
        "category": "account"})
    svc.approve_article(OWNER, article["id"])
    answer = svc.ask_support(OWNER, business_id, {
        "customer_id": customer["id"],
        "question": "How do I reset my password?"})
    assert answer["confidence_class"] == "verified"
    ticket = svc.create_ticket(OWNER, business_id, {
        "customer_id": customer["id"], "category": "account_access",
        "subject": "Reset link never arrives",
        "priority_factors": {"customer_impact": 3}})
    assert ticket["priority"] == "high"
    svc.escalate_ticket(OWNER, ticket["id"], {"reason": "vip blocked"})
    case = svc.create_resolution(OWNER, business_id, {
        "customer_id": customer["id"], "ticket_id": ticket["id"],
        "problem_class": "account", "root_cause_group": "technical",
        "action_kind": "account_restoration",
        "rationale": "Manually restore access and verify login"})
    svc.approve_resolution(OWNER, case["id"], {})
    svc.execute_resolution(OWNER, case["id"], {})
    verified = svc.verify_resolution(OWNER, case["id"], {
        "outcome": "customer logged in successfully"})
    assert verified["status"] == "verified"
    svc.transition_ticket(OWNER, ticket["id"], "in_progress")
    svc.transition_ticket(OWNER, ticket["id"], "resolved")
    overview = svc.business_overview(OWNER, business_id)
    assert overview["counts"]["tickets_open"] == 0


@pytest.mark.asyncio
async def test_scenario_education_stall_and_assistance(app_experience):
    """Stalled enrolment is detected, an incident opens, a
    success task follows up, and onboarding completes."""
    svc = app_experience.experience
    business_id = await fixture_business(app_experience,
                                         name="Course Co")
    customer = make_customer(app_experience, business_id)
    onboarding = svc.start_onboarding(OWNER, business_id, {
        "customer_id": customer["id"], "business_model": "education"})
    backdate(app_experience, CxOnboarding, onboarding["id"],
             hours=100)
    result = svc.evaluate(OWNER, business_id)
    assert any(i["kind"] == "onboarding_stalled"
               for i in result["created"])
    incidents = svc.list_incidents(OWNER, business_id)
    incident = incidents["items"][0]
    svc.transition_incident(OWNER, incident["id"], "acknowledged")
    task = svc.create_success_task(OWNER, business_id, {
        "customer_id": customer["id"],
        "kind": "onboarding_assistance",
        "title": "Unblock enrolment", "source": "incident"})
    svc.complete_success_task(OWNER, task["id"])
    svc.transition_incident(OWNER, incident["id"], "resolved")
    current = svc.list_onboardings(OWNER, business_id)["items"][0]
    for step in current["steps"]:
        if step["status"] != "completed":
            svc.update_onboarding_step(OWNER, onboarding["id"],
                                       step["key"], "completed")
    dashboard = svc.onboarding_dashboard(OWNER, business_id)
    assert dashboard["completed"] == 1


@pytest.mark.asyncio
async def test_scenario_complaint_to_refund_to_insight(app_experience):
    """A delivery complaint becomes a ticket, a root-caused
    resolution, a P-07 refund, and — repeated — an improvement
    insight for the portfolio."""
    svc = app_experience.experience
    business_id = await fixture_business(app_experience,
                                         name="Complaint Co")
    for idx in range(2):
        customer = make_customer(
            app_experience, business_id,
            email=f"buyer{idx}@example.com",
            p07_customer_ref=f"cust-complaint-{idx}")
        revenue = await customer_revenue(
            app_experience, business_id, "300.00",
            customer_ref=f"cust-complaint-{idx}")
        ticket = svc.create_ticket(OWNER, business_id, {
            "customer_id": customer["id"],
            "category": "service_quality_complaint",
            "subject": "Parcel never arrived",
            "priority_factors": {"customer_impact": 2}})
        case = svc.create_resolution(OWNER, business_id, {
            "customer_id": customer["id"], "ticket_id": ticket["id"],
            "problem_class": "delivery",
            "root_cause_group": "fulfillment_provider",
            "action_kind": "refund_recommendation", "basis": "full",
            "revenue_id": revenue["id"],
            "rationale": "Parcel lost by courier; full refund"})
        svc.approve_resolution(OWNER, case["id"], {})
        executed = svc.execute_resolution(OWNER, case["id"], {
            "amount_minor": 30000, "currency": "INR"})
        assert executed["p07_refund_id"]
        svc.verify_resolution(OWNER, case["id"], {
            "outcome": "refund received, customer confirmed"})
    metrics = svc.experience_metrics(OWNER, business_id)
    assert metrics["complaint_rate"]["value"] == 100.0
    insights = svc.improvement_insights(OWNER, business_id)
    assert any("fulfillment_provider" in i["pattern"]
               for i in insights["items"])
    portfolio = svc.portfolio_overview(OWNER)
    assert any(b["business_id"] == business_id
               for b in portfolio["businesses"])


@pytest.mark.asyncio
async def test_scenario_no_channel_means_nothing_is_sent(
        app_experience):
    """The honesty scenario: a full communication cycle still
    sends nothing, and the integrations surface says why."""
    svc = app_experience.experience
    business_id = await fixture_business(app_experience,
                                         name="Quiet Co")
    customer = make_customer(app_experience, business_id)
    for kind in ("purchase_confirmation", "delivery_notification",
                 "resolution_notification", "feedback_request"):
        queued = svc.queue_communication(OWNER, business_id, {
            "customer_id": customer["id"], "kind": kind,
            "body": f"{kind} body", "related_ref": kind})
        attempted = svc.attempt_dispatch(OWNER, queued["id"])
        assert attempted["sent"] is False
        assert attempted["status"] == "dispatch_blocked"
    listing = svc.list_communications(OWNER, business_id)
    assert listing["count"] == 4
    assert all(i["sent"] is False for i in listing["items"])
    transport = next(i for i in svc.integrations(OWNER)["items"]
                     if i["key"] == "communication_transport")
    assert transport["status"] == "not_configured"
