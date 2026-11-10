"""P-18 security tests: owner-only writes, owner/system-only
customer reads, cross-business isolation, the impossibility of
bypassing P-07 for money, the no-second-customer-store and
no-money-column schema guards, and agent-principal refusal.
"""
from __future__ import annotations

import pytest

from app.core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from app.database.models.base import Base
from app.permissions.models import Principal, PrincipalType
from tests.conftest import OWNER
from tests.p09_support import AGENT, SERVICE
from tests.p18_support import (
    app_experience, fixture_business, make_customer,
)  # noqa: F401


@pytest.mark.asyncio
async def test_agent_cannot_write_or_read_customer_data(app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    customer = make_customer(app_experience, business_id)
    with pytest.raises(PermissionDeniedError):
        svc.create_ticket(AGENT, business_id, {
            "category": "general_inquiry", "subject": "x"})
    with pytest.raises(PermissionDeniedError):
        svc.list_tickets(AGENT, business_id)
    with pytest.raises(PermissionDeniedError):
        svc.customer_detail(AGENT, business_id, customer["id"])
    with pytest.raises(PermissionDeniedError):
        svc.queue_communication(AGENT, business_id, {
            "customer_id": customer["id"], "kind": "welcome",
            "body": "hi"})
    with pytest.raises(PermissionDeniedError):
        svc.portfolio_overview(AGENT)
    with pytest.raises(PermissionDeniedError):
        svc.ask_support(AGENT, business_id, {"question": "hours?"})
    # The system principal may read (engine internals), never write.
    system = Principal(PrincipalType.SYSTEM, "system")
    assert svc.list_tickets(system, business_id)["count"] == 0
    with pytest.raises(PermissionDeniedError):
        svc.create_ticket(system, business_id, {
            "category": "general_inquiry", "subject": "x"})
    # A generic service principal gets neither.
    with pytest.raises(PermissionDeniedError):
        svc.list_tickets(SERVICE, business_id)


@pytest.mark.asyncio
async def test_cross_business_customer_is_invisible(app_experience):
    svc = app_experience.experience
    business_a = await fixture_business(app_experience, name="Biz A")
    business_b = await fixture_business(app_experience, name="Biz B")
    customer_a = make_customer(app_experience, business_a)
    with pytest.raises(NotFoundError):
        svc.start_onboarding(OWNER, business_b, {
            "customer_id": customer_a["id"]})
    with pytest.raises(NotFoundError):
        svc.create_ticket(OWNER, business_b, {
            "customer_id": customer_a["id"],
            "category": "general_inquiry", "subject": "x"})
    with pytest.raises(NotFoundError):
        svc.customer_detail(OWNER, business_b, customer_a["id"])
    with pytest.raises(NotFoundError):
        svc.queue_communication(OWNER, business_b, {
            "customer_id": customer_a["id"], "kind": "welcome",
            "body": "hi"})
    with pytest.raises(NotFoundError):
        svc.record_feedback(OWNER, business_b, {
            "customer_id": customer_a["id"], "kind": "csat",
            "score": 5})


@pytest.mark.asyncio
async def test_template_of_other_business_refused(app_experience):
    svc = app_experience.experience
    business_a = await fixture_business(app_experience, name="Biz A2")
    business_b = await fixture_business(app_experience, name="Biz B2")
    template = svc.create_template(OWNER, business_a, {
        "business_model": "saas", "name": "A template",
        "stages": [{"key": "s1", "label": "S1", "kind": "onboarding"}]})
    customer_b = make_customer(app_experience, business_b)
    with pytest.raises(ValidationError):
        svc.start_onboarding(OWNER, business_b, {
            "customer_id": customer_b["id"],
            "template_id": template["id"]})


@pytest.mark.asyncio
async def test_refund_cannot_bypass_approval_or_p07(app_experience):
    svc = app_experience.experience
    business_id = await fixture_business(app_experience)
    customer = make_customer(app_experience, business_id)
    case = svc.create_resolution(OWNER, business_id, {
        "customer_id": customer["id"], "problem_class": "product",
        "action_kind": "refund_recommendation",
        "rationale": "try to skip approval"})
    # An agent cannot approve; execution before approval is refused.
    with pytest.raises(PermissionDeniedError):
        svc.approve_resolution(AGENT, case["id"], {})
    with pytest.raises(ValidationError):
        svc.execute_resolution(OWNER, case["id"], {"amount_minor": 100})
    # Even approved, a refund with no P-07 revenue reference and no
    # owner-supplied amount is refused — P-18 invents neither.
    svc.approve_resolution(OWNER, case["id"], {})
    with pytest.raises(ValidationError):
        svc.execute_resolution(OWNER, case["id"], {})


def test_schema_guards_no_money_columns_no_second_customer_store():
    cx_tables = {t.name: t for t in Base.metadata.tables.values()
                 if t.name.startswith("cx_")}
    assert len(cx_tables) == 15
    banned = ("amount", "minor", "currency", "price", "balance",
              "cost", "fee", "charge")
    reference_columns = {"revenue_id"}  # a P-07 reference, not money
    for name, table in cx_tables.items():
        for column in table.columns:
            if column.name in reference_columns:
                continue
            assert not any(b in column.name for b in banned), \
                f"{name}.{column.name} looks like a money column"
    # P-18 creates no customer store: no cx table is one, and the
    # one record-level customer table remains P-17's.
    assert not any("customer" in name for name in cx_tables)
    assert "crm_customers" in Base.metadata.tables


@pytest.mark.asyncio
async def test_settings_autonomy_bounds(app_experience):
    svc = app_experience.experience
    with pytest.raises(ValidationError):
        svc.update_settings(OWNER, {"autonomy_level": 9})
    updated = svc.update_settings(OWNER, {"autonomy_level": 2})
    assert updated["autonomy_level"] == 2
    with pytest.raises(PermissionDeniedError):
        svc.update_settings(AGENT, {"autonomy_level": 1})


@pytest.mark.asyncio
async def test_agent_roles_have_no_send_or_financial_capability(
        app_experience):
    svc = app_experience.experience
    roles = svc.agent_roles(OWNER)
    assert roles["count"] == 10
    for role in roles["items"]:
        assert "external_communication" not in role["capabilities"]
        assert not any("financ" in cap or "payment" in cap
                       for cap in role["capabilities"])
