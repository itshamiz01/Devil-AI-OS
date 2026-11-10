"""Shared fixtures and seeding helpers for the P-08 test suite.

Financial history is seeded ONLY through P-07's authorised paths:
verified revenue through the provider-report path (the same
internal path verified webhooks and reconciliation land on), paid
expenses through the expense service, opening balances, budgets and
reserves through their P-07 services. No test writes a ledger row
directly and nothing unverified is marked verified (§32 rule 3 /
P-08 structural lock 1).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.application import Application
from app.main import create_app
from app.permissions.models import Principal, PrincipalType
from tests.conftest import OWNER, make_settings
from tests.p06_support import make_fixture_business, run_full_creation
from tests.p07_support import money, paid_expense  # noqa: F401  (re-export)

AGENT = Principal(PrincipalType.AGENT, "agent-1")
EXTERNAL = Principal(PrincipalType.EXTERNAL, "ext-1")

EXPERIMENT = {
    "name": "landing-page-test",
    "hypothesis": "A clearer offer page converts more visitors",
    "problem": "Visitors leave without buying",
    "target_customer": "beginner fitness readers",
    "expected_outcome": "at least 5 verified sales attributable to "
                        "the experiment window",
    "success_metric": "verified_sales_count >= 5",
    "failure_metric": "verified_sales_count < 2",
    "minimum_evidence": "P-07 verified collected revenue records",
    "max_duration_days": 14,
    "approved_budget_minor": 200_000,      # ₹2,000
    "max_acceptable_loss_minor": 100_000,  # ₹1,000
    "evaluation_schedule": "daily",
    "currency": "INR",
}


@pytest.fixture
async def app_surv(tmp_path):
    """Controlled-mode application (same posture as P-06/P-07)."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


@pytest.fixture
def client_surv(tmp_path):
    app = create_app(make_settings(tmp_path, mode="controlled"))
    with TestClient(app) as client:
        yield client


def owner_http_headers(client) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "test-owner-password-123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def operational_business(application, *, name="Beginner Fitness Ebook",
                               template="ebook_digital_product",
                               category="digital_products"):
    """P-06 fixture business taken through the full validated path
    to OPERATIONAL (staging demonstration semantics: local package
    only, no deployment, no revenue), with an INR P-07 profile.
    Returns (business_id, profile dict)."""
    svc = application.business
    _opp_id, business = await make_fixture_business(
        application, name=name, template=template, category=category)
    business_id = business["id"]
    svc.update_settings(OWNER, {"default_currency": "INR"})
    await run_full_creation(application, business_id)
    await svc.evaluate_readiness(OWNER, business_id)
    await svc.transition_business(OWNER, business_id, "READY_FOR_LAUNCH",
                                  reason="readiness passed")
    request = await svc.request_launch(OWNER, business_id)
    application.approvals.decide(request["approval_id"], OWNER, True)
    launched = await svc.launch(OWNER, business_id,
                                request["approval_id"])
    assert launched["status"] == "OPERATIONAL"
    profile = await application.financial.ensure_profile(
        OWNER, business_id)
    return business_id, profile


async def profile_only_business(application, *, name="Profile Only Ebook"):
    """Fixture business with declaration+blueprint and a P-07
    profile, but NOT launched (pre-operational lifecycle states)."""
    from tests.p07_support import business_with_profile
    return await business_with_profile(application, name=name)


def opening_balance(application, business_id: str, amount: str, *,
                    verified: bool = True):
    return application.financial.record_opening_balance(
        OWNER, business_id, {
            "amount": money(application, amount),
            "entry_date": "2026-11-01", "account_ref": "bank:primary",
            "source": "bank_statement",
            "verification_status": "verified" if verified
            else "reported"})


def verified_sale(application, business_id: str, amount: str, *,
                  customer: str, date: str = "2026-11-05",
                  channel: str | None = None,
                  category: str = "product_sale"):
    """A collected, verified sale through the authorised
    provider-report path, attributed to a customer reference."""
    fin = application.financial
    return fin.revenue.create_revenue(
        OWNER, business_id,
        {"category": category,
         "amount": money(application, amount),
         "transaction_date": date,
         "source": "authorized_provider_report",
         "initial_status": "PAYMENT_SETTLED",
         "customer_ref": customer, "channel": channel,
         "creation_method": "provider_report"},
        verified=True)


def seed_repeat_customers(application, business_id: str, *,
                          sales: int = 4):
    """≥3 distinct customers with ≥1 repeat, all verified collected
    sales through the provider-report path."""
    customers = ["cust-a", "cust-b", "cust-c", "cust-a"]
    for index in range(sales):
        verified_sale(application, business_id, "2500.00",
                      customer=customers[index % len(customers)],
                      date=f"2026-11-0{3 + index}")


def create_budget(application, business_id: str, amount: str, *,
                  scope_type: str = "business", name: str = "Operations",
                  scope_ref: str | None = None):
    return application.financial.budgets.create_budget(OWNER, {
        "scope_type": scope_type, "business_id": business_id,
        "scope_ref": scope_ref, "name": name,
        "amount": money(application, amount),
        "period_start": "2026-11-01", "period_end": "2026-11-30",
        "approval_requirement": "level_1"})


def healthy_snapshot(application, business_id: str):
    """Evaluate once and return the snapshot dict."""
    result = application.survival.evaluate(OWNER, business_id)
    return result["snapshot"]
