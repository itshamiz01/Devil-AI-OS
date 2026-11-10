"""Shared fixtures and seeding helpers for the P-16 test suite.

Seeding goes through governed paths only: businesses from the P-06
fixture path (labelled fixtures), money from P-07's authorised
record paths (verified revenue, paid expenses, opening balances),
and economy state through the P-16 service itself.
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


@pytest.fixture
async def app_eco(tmp_path):
    """Controlled-mode application (same posture as P-06–P-15)."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


@pytest.fixture
def client_eco(tmp_path):
    app = create_app(make_settings(tmp_path, mode="controlled"))
    with TestClient(app) as client:
        yield client


async def profitable_business(application, *, name: str,
                              revenue: str = "10000.00",
                              expense: str = "2000.00",
                              opening: str = "5000.00",
                              channel: str | None = None) -> str:
    """Fixture business whose P-07 books show verified collected
    revenue well above paid expenses (positive net profit)."""
    business_id, _profile = await business_with_profile(
        application, name=name)
    if opening and float(opening) > 0:
        opening_balance(application, business_id, opening)
    await verified_revenue(application, business_id, revenue,
                           channel=channel)
    if expense:
        await paid_expense(application, business_id, expense)
    return business_id


async def lossmaking_business(application, *, name: str,
                              revenue: str = "1000.00",
                              expense: str = "4000.00") -> str:
    """Fixture business whose verified expenses exceed its verified
    collected revenue (negative net profit)."""
    business_id, _profile = await business_with_profile(
        application, name=name)
    await verified_revenue(application, business_id, revenue)
    await paid_expense(application, business_id, expense)
    return business_id


def strong_factors(**overrides) -> dict:
    """A complete §4.3 factor set scoring in the strong band."""
    factors = {"market_demand": 85, "profitability_potential": 80,
               "competitive_advantage": 75, "scalability": 80,
               "capital_efficiency": 70, "operational_feasibility": 75,
               "revenue_diversification": 60,
               "strategic_compatibility": 80, "risk_profile": 30}
    factors.update(overrides)
    return factors


def strong_evidence() -> list:
    """Three source-backed evidence items (confidence 76)."""
    return [{"summary": f"evidence {i}", "source_backed": True,
             "source_ref": f"fixture-source-{i}"} for i in range(3)]
