"""Shared fixtures and seeding helpers for the P-13 test suite.

Seeding goes through governed paths only: businesses come from the
P-06 fixture path (labelled fixtures), money from P-07's authorised
record paths, agents are P-01 rows, and portfolio state is created
through the P-13 service itself. OWNER is the P-01 owner principal;
AGENT/AGENT2 are P-09's registered agent principals.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.application import Application
from app.main import create_app
from app.permissions.models import Principal, PrincipalType
from tests.conftest import OWNER, make_settings  # noqa: F401
from tests.p09_support import (  # noqa: F401
    AGENT, AGENT2, EXTERNAL, SERVICE, register_agent,
)
from tests.p06_support import make_fixture_business  # noqa: F401
from tests.p07_support import (  # noqa: F401
    business_with_profile, money, verified_revenue,
)
from tests.p12_support import owner_http_headers  # noqa: F401

SYSTEM = Principal(PrincipalType.SYSTEM, "system")


@pytest.fixture
async def app_portfolio(tmp_path):
    """Controlled-mode application (same posture as P-06–P-12)."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


@pytest.fixture
def client_portfolio(tmp_path):
    app = create_app(make_settings(tmp_path, mode="controlled"))
    with TestClient(app) as client:
        yield client


def future_iso(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def past_iso(days: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


async def make_business(application, *, name: str,
                        template: str = "ebook_digital_product",
                        category: str = "digital_products") -> str:
    _opp, business = await make_fixture_business(
        application, name=name, template=template, category=category)
    return business["id"]


async def make_portfolio(application, *, name: str = "Owner Portfolio",
                         business_ids: list[str] | None = None,
                         priorities: dict | None = None) -> dict:
    """A portfolio with the given businesses registered as members."""
    svc = application.portfolio
    portfolio = svc.create_portfolio(OWNER, {"name": name})
    for bid in business_ids or []:
        svc.register_business(OWNER, portfolio["id"], {
            "business_id": bid,
            "strategic_priority": (priorities or {}).get(bid, 50)})
    return portfolio


async def business_with_collected(application, *, name: str,
                                  amount: str,
                                  template: str = "ebook_digital_product",
                                  category: str = "digital_products",
                                  channel: str | None = None) -> str:
    """Fixture business + P-07 profile + verified collected revenue."""
    business_id, _profile = await business_with_profile(
        application, name=name, template=template, category=category)
    await verified_revenue(application, business_id, amount,
                           channel=channel)
    return business_id


def make_service_with_access(application, *, name: str = "Shared Analytics",
                             kind: str = "analytics",
                             business_ids: list[str],
                             capacity_units: int = 100) -> dict:
    """A shared service with ACTIVE access for each business."""
    svc = application.portfolio
    service = svc.create_service(OWNER, {
        "name": name, "kind": kind, "capacity_units": capacity_units})
    for bid in business_ids:
        access = svc.request_access(OWNER, service["id"],
                                    {"business_id": bid})
        svc.decide_access(OWNER, access["id"], True)
        svc.activate_access(OWNER, access["id"])
    return service
