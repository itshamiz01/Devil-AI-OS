"""Shared fixtures and seeding helpers for the P-17 test suite.

Seeding goes through governed paths only: businesses from the P-06
fixture path (labelled fixtures), money from P-07's authorised
record paths (verified revenue — including channel-tagged and
customer-referenced records — and paid marketing expenses carrying
the campaign project_ref link), and growth state through the P-17
service itself.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.application import Application
from app.main import create_app
from tests.conftest import OWNER, make_settings  # noqa: F401
from tests.p09_support import AGENT, AGENT2, EXTERNAL, SERVICE  # noqa: F401
from tests.p07_support import (  # noqa: F401
    business_with_profile, money, paid_expense, verified_revenue,
)
from tests.p08_support import opening_balance  # noqa: F401
from tests.p12_support import owner_http_headers  # noqa: F401
from tests.p16_support import (  # noqa: F401
    lossmaking_business, profitable_business,
)


@pytest.fixture
async def app_growth(tmp_path):
    """Controlled-mode application (same posture as P-06–P-16)."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


@pytest.fixture
def client_growth(tmp_path):
    app = create_app(make_settings(tmp_path, mode="controlled"))
    with TestClient(app) as client:
        yield client


async def marketing_expense(application, business_id: str, amount: str, *,
                            campaign_id: str | None = None,
                            category: str = "marketing",
                            date: str = "2026-11-06"):
    """A paid P-07 marketing expense; with a campaign_id it carries
    the P-17 campaign project_ref linkage (§21)."""
    fin = application.financial
    data = {"category": category,
            "amount": money(application, amount),
            "expense_date": date, "directness": "direct",
            "cost_behavior": "variable", "vendor": "Fixture Ads",
            "recurrence_type": "one_time", "payment_status": "paid"}
    if campaign_id:
        data["project_ref"] = f"p17-campaign:{campaign_id}"
    return fin.expenses.create_expense(OWNER, business_id, data)


async def customer_revenue(application, business_id: str, amount: str, *,
                           customer_ref: str, channel: str | None = None,
                           date: str = "2026-11-05"):
    """Verified collected revenue recorded against a CRM customer's
    P-07 ref (the §11 payment-history source)."""
    fin = application.financial
    return fin.revenue.create_revenue(
        OWNER, business_id,
        {"category": "product_sale",
         "amount": money(application, amount),
         "transaction_date": date,
         "source": "authorized_provider_report",
         "initial_status": "PAYMENT_SETTLED",
         "channel": channel, "customer_ref": customer_ref,
         "creation_method": "provider_report"},
        verified=True)


def lead_payload(**overrides) -> dict:
    payload = {"source": "website_form",
               "contact": {"email": "priya@example.com",
                           "name": "Priya Nair"},
               "consent_status": "granted",
               "lawful_basis": "website form opt-in"}
    payload.update(overrides)
    return payload


def campaign_payload(**overrides) -> dict:
    payload = {"name": "Launch Week Push", "objective": "first sales",
               "purpose": "acquisition", "channel_key": "seo",
               "budget_ceiling_minor": 500000, "currency": "INR",
               "expected_results": {"max_cac_minor": 20000}}
    payload.update(overrides)
    return payload
