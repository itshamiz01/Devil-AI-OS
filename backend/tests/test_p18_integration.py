"""P-18 integration tests: the experience lifecycle end to end
on governed paths — onboarding, fulfilment, SLA, tickets, the
grounded assistant, communications, feedback/metrics, health,
quality, resolutions executed through P-07, success tasks and
the customer 360.
"""
from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.database.models.experience import CxOnboarding
from tests.conftest import OWNER
from tests.p18_support import (
    app_experience, backdate, client_experience, customer_revenue,
    fixture_business, make_customer,
)  # noqa: F401


@pytest.mark.asyncio
async def test_engine_status_reports_authorities(app_experience):
    svc = app_experience.experience
    status = svc.engine_status(OWNER)
    assert status["customer_authority"].startswith("P-17")
    assert status["financial_authority"] == "P-07"
    assert status["workflow_authority"] == "P-12"
    assert "sends nothing" in status["execution_capability"]
    integrations = svc.integrations(OWNER)
    assert integrations["count"] == 8
    assert all(i["status"] == "not_configured"
               for i in integrations["items"])


@pytest.mark.asyncio
async def test_onboarding_from_system_default_and_dashboard(
        app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    customer = make_customer(app_experience, business_id)
    onboarding = svc.start_onboarding(OWNER, business_id, {
        "customer_id": customer["id"], "business_model": "saas",
        "is_fixture": True})
    assert onboarding["template_source"] == "system_default"
    assert onboarding["already_existed"] is False
    kinds = {s["kind"] for s in onboarding["steps"]}
    assert kinds <= {"purchase", "onboarding", "verification"}
    again = svc.start_onboarding(OWNER, business_id, {
        "customer_id": customer["id"], "business_model": "saas"})
    assert again["already_existed"] is True
    for step in onboarding["steps"]:
        svc.update_onboarding_step(OWNER, onboarding["id"],
                                   step["key"], "completed")
    dashboard = svc.onboarding_dashboard(OWNER, business_id)
    assert dashboard["completed"] == 1
    assert dashboard["success_rate_percent"] == 100.0


@pytest.mark.asyncio
async def test_business_template_overrides_system_default(app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    svc.create_template(OWNER, business_id, {
        "business_model": "saas", "name": "SaaS fast track",
        "is_default": True,
        "stages": [{"key": "purchase_completed", "label": "Paid",
                    "kind": "purchase"},
                   {"key": "account_setup", "label": "Account setup",
                    "kind": "onboarding"}]})
    customer = make_customer(app_experience, business_id)
    onboarding = svc.start_onboarding(OWNER, business_id, {
        "customer_id": customer["id"], "business_model": "saas"})
    assert onboarding["template_source"] == "business_template"
    assert [s["key"] for s in onboarding["steps"]] == [
        "purchase_completed", "account_setup"]


@pytest.mark.asyncio
async def test_fulfillment_flow_and_acceptance(app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    customer = make_customer(app_experience, business_id)
    fulfil = svc.create_fulfillment(OWNER, business_id, {
        "customer_id": customer["id"], "kind": "digital",
        "title": "Ebook delivery", "is_fixture": True})
    assert fulfil["status"] == "received"
    with pytest.raises(ValidationError):
        svc.transition_fulfillment(OWNER, fulfil["id"],
                                   {"status": "shipped"})
    svc.transition_fulfillment(OWNER, fulfil["id"],
                               {"status": "preparing"})
    done = svc.transition_fulfillment(OWNER, fulfil["id"],
                                      {"status": "delivered"})
    assert done["delivered_at"]
    accepted = svc.set_acceptance(OWNER, fulfil["id"], "accepted")
    assert accepted["acceptance"] == "accepted"


@pytest.mark.asyncio
async def test_sla_not_configured_then_breach(app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    compliance = svc.sla_compliance(OWNER, business_id)
    assert compliance["status"] == "NOT_AVAILABLE"
    ticket = svc.create_ticket(OWNER, business_id, {
        "category": "technical_issue", "subject": "App crashes",
        "priority_factors": {"customer_impact": 2}})
    assert svc.get_ticket(OWNER, ticket["id"])["sla"]["status"] == \
        "not_configured"
    svc.upsert_sla_policy(OWNER, business_id, {
        "category": "*", "first_response_minutes": 60,
        "resolution_minutes": 480})
    assert svc.sla_compliance(OWNER, business_id)["status"] == \
        "computed"
    from app.database.models.experience import CxTicket
    backdate(app_experience, CxTicket, ticket["id"], hours=3)
    state = svc.get_ticket(OWNER, ticket["id"])["sla"]
    assert state["status"] == "breached"
    assert state["first_response_breached"] is True


@pytest.mark.asyncio
async def test_evaluation_flags_stalled_onboarding_idempotently(
        app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    customer = make_customer(app_experience, business_id)
    onboarding = svc.start_onboarding(OWNER, business_id, {
        "customer_id": customer["id"], "business_model": "saas"})
    backdate(app_experience, CxOnboarding, onboarding["id"],
             hours=100)
    first = svc.evaluate(OWNER, business_id)
    kinds = {i["kind"] for i in first["created"]}
    assert "onboarding_stalled" in kinds
    listing = svc.list_onboardings(OWNER, business_id)
    assert listing["items"][0]["status"] == "stalled"
    second = svc.evaluate(OWNER, business_id)
    assert second["count"] == 0  # idempotent: no duplicate incident


@pytest.mark.asyncio
async def test_ticket_lifecycle_priority_and_reopen(app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    customer = make_customer(app_experience, business_id)
    ticket = svc.create_ticket(OWNER, business_id, {
        "customer_id": customer["id"], "category": "account_access",
        "subject": "Locked out", "priority_factors": {}})
    assert ticket["priority"] == "high"  # category floor
    assert ticket["priority_factors"]["floor_applied"] is True
    svc.add_ticket_message(OWNER, ticket["id"], {
        "author_kind": "owner", "body": "Looking into it now"})
    view = svc.get_ticket(OWNER, ticket["id"])
    assert view["first_response_at"]
    assert len(view["messages"]) == 1
    svc.transition_ticket(OWNER, ticket["id"], "in_progress")
    svc.transition_ticket(OWNER, ticket["id"], "resolved")
    reopened = svc.transition_ticket(OWNER, ticket["id"],
                                     "in_progress")
    assert reopened["reopened_count"] == 1
    assert reopened["resolved_at"] is None
    with pytest.raises(ValidationError):
        svc.transition_ticket(OWNER, ticket["id"], "new")


@pytest.mark.asyncio
async def test_escalation_creates_p12_workflow(app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    ticket = svc.create_ticket(OWNER, business_id, {
        "category": "technical_issue", "subject": "Data loss"})
    escalated = svc.escalate_ticket(OWNER, ticket["id"],
                                    {"reason": "needs engineering"})
    assert escalated["status"] == "escalated"
    assert escalated["escalation_level"] == 1
    workflow = app_experience.operations.get_workflow(
        OWNER, escalated["workflow_id"])
    assert workflow["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_grounded_assistant_verified_insufficient_high_impact(
        app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    customer = make_customer(app_experience, business_id)
    # No knowledge at all: honest refusal + a ticket records it.
    answer = svc.ask_support(OWNER, business_id, {
        "customer_id": customer["id"],
        "question": "How do I reset my password?"})
    assert answer["confidence_class"] == "insufficient_information"
    assert answer["escalated"] is True
    assert answer["ticket_id"]
    # A draft article does NOT ground answers.
    article = svc.create_article(OWNER, business_id, {
        "title": "Reset your password",
        "content": "To reset your password open account settings "
                   "and choose reset password to set a new password.",
        "category": "account"})
    still = svc.ask_support(OWNER, business_id, {
        "question": "How do I reset my password?"})
    assert still["confidence_class"] == "insufficient_information"
    # Approved: verified, extractive, cited with pinned version.
    svc.approve_article(OWNER, article["id"])
    grounded = svc.ask_support(OWNER, business_id, {
        "customer_id": customer["id"],
        "question": "How do I reset my password?"})
    assert grounded["confidence_class"] == "verified"
    assert grounded["escalated"] is False
    assert grounded["article_refs"][0]["article_id"] == article["id"]
    assert grounded["article_refs"][0]["version"] == 1
    assert "reset your password" in grounded["answer_text"].lower()
    # Editing an approved article returns it to draft (version 2).
    edited = svc.update_article(OWNER, article["id"],
                                {"content": "New reset guidance."})
    assert edited["version"] == 2
    assert edited["approval_status"] == "draft"


@pytest.mark.asyncio
async def test_assistant_high_impact_requires_human_review(
        app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    article = svc.create_article(OWNER, business_id, {
        "title": "Refund policy",
        "content": "Our refund policy explains refunds for damaged "
                   "items and how a refund is requested.",
        "category": "billing"})
    svc.approve_article(OWNER, article["id"])
    answer = svc.ask_support(OWNER, business_id, {
        "question": "What is your refund policy for a broken item?"})
    assert answer["confidence_class"] == "human_review_required"
    assert answer["escalated"] is True


@pytest.mark.asyncio
async def test_communications_queue_block_consent_and_dedupe(
        app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    customer = make_customer(app_experience, business_id)
    queued = svc.queue_communication(OWNER, business_id, {
        "customer_id": customer["id"], "kind": "welcome",
        "body": "Welcome aboard"})
    assert queued["status"] == "queued"
    assert queued["sent"] is False
    with pytest.raises(ValidationError):  # duplicate refused
        svc.queue_communication(OWNER, business_id, {
            "customer_id": customer["id"], "kind": "welcome",
            "body": "Welcome aboard"})
    blocked = svc.attempt_dispatch(OWNER, queued["id"])
    assert blocked["status"] == "dispatch_blocked"
    assert "NOT been sent" in blocked["dispatch_note"]
    # Sensitive kinds carry an owner approval.
    sensitive = svc.queue_communication(OWNER, business_id, {
        "customer_id": customer["id"], "kind": "service_announcement",
        "body": "Maintenance window on Sunday"})
    assert sensitive["requires_approval"] is True
    assert sensitive["approval_id"]
    # Unknown consent never receives communications.
    unknown = make_customer(app_experience, business_id,
                            email="other@example.com", consent="unknown")
    with pytest.raises(ValidationError):
        svc.queue_communication(OWNER, business_id, {
            "customer_id": unknown["id"], "kind": "welcome",
            "body": "Hi"})
    # There is no refund-promise kind at all.
    with pytest.raises(ValidationError):
        svc.queue_communication(OWNER, business_id, {
            "customer_id": customer["id"], "kind": "refund_promise",
            "body": "We promise a refund"})


@pytest.mark.asyncio
async def test_feedback_metrics_and_health(app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    customer = make_customer(app_experience, business_id)
    svc.record_feedback(OWNER, business_id, {
        "customer_id": customer["id"], "kind": "csat", "score": 5})
    svc.record_feedback(OWNER, business_id, {
        "customer_id": customer["id"], "kind": "csat", "score": 4})
    svc.record_feedback(OWNER, business_id, {
        "customer_id": customer["id"], "kind": "nps", "score": 9})
    metrics = svc.experience_metrics(OWNER, business_id)
    assert metrics["csat"]["value"] == 4.5
    assert metrics["csat"]["sample_size"] == 2
    assert metrics["nps"]["value"] == 100.0
    assert metrics["customer_effort"]["status"] == "INSUFFICIENT_DATA"
    health = svc.compute_health(OWNER, business_id, customer["id"])
    assert health["classification"] == "healthy"
    assert health["score"] == 100
    latest = svc.latest_health(OWNER, business_id, customer["id"])
    assert latest["classification"] == "healthy"
    # An open critical case flips the classification.
    svc.create_ticket(OWNER, business_id, {
        "customer_id": customer["id"], "category": "technical_issue",
        "subject": "Total outage",
        "priority_factors": {"security": 3, "service_disruption": 3,
                             "customer_impact": 3, "financial": 3,
                             "business_impact": 3, "contractual": 3,
                             "time_sensitivity": 3}})
    health2 = svc.compute_health(OWNER, business_id, customer["id"])
    assert health2["classification"] == "critical"
    overview = svc.health_overview(OWNER, business_id)
    assert overview["distribution"].get("critical") == 1


@pytest.mark.asyncio
async def test_quality_review_and_summary(app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    ticket = svc.create_ticket(OWNER, business_id, {
        "category": "general_inquiry", "subject": "Hours?"})
    review = svc.create_quality_review(OWNER, business_id, {
        "ticket_id": ticket["id"],
        "dimensions": {"accuracy": 5, "clarity": 4, "timeliness": 3}})
    assert review["aggregate"]["value"] == 4.0
    assert "empathy" not in review["dimensions"]
    summary = svc.quality_summary(OWNER, business_id)
    assert summary["reviews"] == 1
    assert summary["average_score"] == 4.0
    with pytest.raises(ValidationError):
        svc.create_quality_review(OWNER, business_id, {
            "ticket_id": ticket["id"],
            "dimensions": {"empathy": 5}})


@pytest.mark.asyncio
async def test_refund_resolution_executes_only_through_p07(
        app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    customer = make_customer(app_experience, business_id,
                             p07_customer_ref="cust-refund-1")
    revenue = await customer_revenue(
        app_experience, business_id, "500.00",
        customer_ref="cust-refund-1")
    case = svc.create_resolution(OWNER, business_id, {
        "customer_id": customer["id"], "problem_class": "product",
        "root_cause_group": "product",
        "action_kind": "refund_recommendation", "basis": "partial",
        "revenue_id": revenue["id"],
        "rationale": "Item arrived damaged; partial refund agreed"})
    assert case["status"] == "recommended"
    with pytest.raises(ValidationError):  # not approved yet
        svc.execute_resolution(OWNER, case["id"],
                               {"amount_minor": 20000})
    svc.approve_resolution(OWNER, case["id"], {})
    executed = svc.execute_resolution(OWNER, case["id"], {
        "amount_minor": 20000, "currency": "INR"})
    assert executed["status"] == "executed"
    assert executed["p07_refund_id"]
    rows, _ = app_experience.financial.revenue.list_revenue(
        business_id, limit=10)
    row = next(r for r in rows if r["id"] == revenue["id"])
    assert row["lifecycle_status"] == "PARTIALLY_REFUNDED"
    verified = svc.verify_resolution(OWNER, case["id"], {
        "outcome": "customer confirmed satisfied", "verified": True})
    assert verified["status"] == "verified"
    # Refund above the original payment is refused by P-07 itself.
    case2 = svc.create_resolution(OWNER, business_id, {
        "customer_id": customer["id"], "problem_class": "product",
        "action_kind": "refund_recommendation",
        "revenue_id": revenue["id"], "rationale": "second case"})
    svc.approve_resolution(OWNER, case2["id"], {})
    with pytest.raises(ValidationError):
        svc.execute_resolution(OWNER, case2["id"],
                               {"amount_minor": 99999999})


@pytest.mark.asyncio
async def test_goodwill_resolution_prepares_p07_spend(app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    customer = make_customer(app_experience, business_id)
    case = svc.create_resolution(OWNER, business_id, {
        "customer_id": customer["id"], "problem_class": "delivery",
        "root_cause_group": "fulfillment_provider",
        "action_kind": "goodwill_recommendation",
        "rationale": "Delivery was a week late"})
    svc.approve_resolution(OWNER, case["id"], {})
    executed = svc.execute_resolution(OWNER, case["id"], {
        "amount_minor": 5000, "currency": "INR"})
    assert executed["p07_spending_request_id"]
    assert "P-07" in executed["execution_note"]


@pytest.mark.asyncio
async def test_success_task_with_p12_workflow(app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    customer = make_customer(app_experience, business_id)
    task = svc.create_success_task(OWNER, business_id, {
        "customer_id": customer["id"],
        "kind": "onboarding_assistance", "title": "Help with setup",
        "via_workflow": True})
    assert task["workflow_id"]
    workflow = app_experience.operations.get_workflow(
        OWNER, task["workflow_id"])
    assert workflow["status"] == "DRAFT"
    done = svc.complete_success_task(OWNER, task["id"])
    assert done["status"] == "done"


@pytest.mark.asyncio
async def test_customer_detail_reads_p07_purchases_live(app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    customer = make_customer(app_experience, business_id,
                             p07_customer_ref="cust-360-1")
    await customer_revenue(app_experience, business_id, "250.00",
                           customer_ref="cust-360-1")
    await customer_revenue(app_experience, business_id, "250.00",
                           customer_ref="cust-360-1")
    detail = svc.customer_detail(OWNER, business_id, customer["id"])
    assert detail["purchase_count"] == 2
    assert detail["customer"]["id"] == customer["id"]
    assert "p17_crm_customers" in detail["customer_source"]


@pytest.mark.asyncio
async def test_improvement_insights_from_recorded_cases(app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    customer = make_customer(app_experience, business_id)
    for _ in range(2):
        svc.create_resolution(OWNER, business_id, {
            "customer_id": customer["id"], "problem_class": "delivery",
            "root_cause_group": "fulfillment_provider",
            "action_kind": "redelivery",
            "rationale": "parcel lost by courier"})
    insights = svc.improvement_insights(OWNER, business_id)
    patterns = {i["pattern"] for i in insights["items"]}
    assert "recurring root cause: fulfillment_provider" in patterns
    assert all(i["evidence_count"] >= 2 for i in insights["items"])


def test_http_surface_round_trip(client_experience):
    from tests.p18_support import owner_http_headers
    headers = owner_http_headers(client_experience)
    resp = client_experience.get("/api/v1/experience/status",
                                 headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["financial_authority"] == "P-07"
    resp = client_experience.get("/api/v1/experience/overview",
                                 headers=headers)
    assert resp.status_code == 200
    assert "businesses" in resp.json()["data"]
