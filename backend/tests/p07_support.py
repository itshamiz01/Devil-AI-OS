"""Shared fixtures for the P-07 test suite.

Businesses are real P-06 fixture businesses (levels computed by
P-03). Financial records are currency-explicit: the scenario suite
runs in INR (the prompt's ₹ figures) regardless of the fixture
profile's base currency, because P-07 metrics are always computed
per currency and never mixed (§14).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.application import Application
from app.main import create_app
from app.permissions.models import Principal, PrincipalType
from tests.conftest import OWNER, make_settings
from tests.p06_support import DECLARATION, make_fixture_business

AGENT = Principal(PrincipalType.AGENT, "agent-1")
EXTERNAL = Principal(PrincipalType.EXTERNAL, "ext-1")


@pytest.fixture
async def app_fin(tmp_path):
    """Controlled-mode application (same posture as the P-06 suite)."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


@pytest.fixture
def client_fin(tmp_path):
    app = create_app(make_settings(tmp_path, mode="controlled"))
    with TestClient(app) as client:
        yield client


def owner_http_headers(client) -> dict:
    """Plain login helper (conftest's auth_headers is a fixture and
    cannot be called directly)."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "test-owner-password-123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def business_with_profile(application, *, name="Beginner Fitness Ebook",
                                template="ebook_digital_product",
                                category="digital_products"):
    """P-06 fixture business → declaration → blueprint → P-07 profile.
    Returns (business_id, profile dict)."""
    svc = application.business
    _opp_id, business = await make_fixture_business(
        application, name=name, template=template, category=category)
    business_id = business["id"]
    # The blueprint currency is the owner-governed P-06 business
    # setting; the owner's home currency is INR, so the P-06 -> P-07
    # bridge payload — and therefore the profile and chart — are INR.
    svc.update_settings(OWNER, {"default_currency": "INR"})
    await svc.create_declaration(OWNER, business_id, DECLARATION)
    await svc.generate_blueprint(OWNER, business_id)
    profile = await application.financial.ensure_profile(OWNER, business_id)
    return business_id, profile


def money(application, amount: str, currency: str = "INR"):
    from app.financial.money import parse_amount
    return parse_amount(amount, currency, application.financial.registry)


async def verified_revenue(application, business_id: str, amount: str,
                           *, currency: str = "INR",
                           date: str = "2026-11-05",
                           category: str = "product_sale",
                           external_ref: str | None = None,
                           channel: str | None = None):
    """A collected, verified revenue record through the authorised
    provider-report path (the same internal path verified webhooks
    and reconciliation land on)."""
    fin = application.financial
    return fin.revenue.create_revenue(
        OWNER, business_id,
        {"category": category, "amount": money(application, amount, currency),
         "transaction_date": date, "source": "authorized_provider_report",
         "initial_status": "PAYMENT_SETTLED", "external_ref": external_ref,
         "channel": channel, "creation_method": "provider_report"},
        verified=True)


async def paid_expense(application, business_id: str, amount: str, *,
                       currency: str = "INR", date: str = "2026-11-06",
                       category: str = "operational",
                       directness: str = "indirect",
                       cost_behavior: str = "variable",
                       vendor: str | None = None,
                       budget_id: str | None = None,
                       recurrence_type: str = "one_time"):
    fin = application.financial
    return fin.expenses.create_expense(
        OWNER, business_id,
        {"category": category, "amount": money(application, amount, currency),
         "expense_date": date, "directness": directness,
         "cost_behavior": cost_behavior, "vendor": vendor,
         "budget_id": budget_id, "recurrence_type": recurrence_type,
         "payment_status": "paid"})
