"""Shared fixtures and seeding helpers for the P-18 test suite.

Seeding goes through governed paths only: businesses from the
P-06 fixture path (labelled fixtures), customers from P-17's
``create_customer`` (the one customer store P-18 references),
money from P-07's authorised record paths, and experience state
through the P-18 service itself.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.application import Application
from app.main import create_app
from tests.conftest import OWNER, make_settings  # noqa: F401
from tests.p06_support import make_fixture_business  # noqa: F401
from tests.p09_support import AGENT, AGENT2, EXTERNAL, SERVICE  # noqa: F401
from tests.p07_support import (  # noqa: F401
    business_with_profile, money, paid_expense, verified_revenue,
)
from tests.p12_support import owner_http_headers  # noqa: F401
from tests.p16_support import (  # noqa: F401
    lossmaking_business, profitable_business,
)
from tests.p17_support import customer_revenue  # noqa: F401


@pytest.fixture
async def app_experience(tmp_path):
    """Controlled-mode application (same posture as P-06–P-17)."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


@pytest.fixture
def client_experience(tmp_path):
    app = create_app(make_settings(tmp_path, mode="controlled"))
    with TestClient(app) as client:
        yield client


async def fixture_business(application, *, name="Experience Fixture Biz"):
    _opp, business = await make_fixture_business(application, name=name)
    return business["id"]


def make_customer(application, business_id: str, *,
                  email="priya@example.com", name="Priya Nair",
                  consent="granted", preferences=None,
                  p07_customer_ref=None):
    """A P-17 CRM customer — the only customer record P-18 uses."""
    data = {"contact": {"email": email, "name": name},
            "consent_status": consent,
            "preferences": preferences or {},
            "is_fixture": True}
    if p07_customer_ref:
        data["p07_customer_ref"] = p07_customer_ref
    return application.growth.create_customer(OWNER, business_id, data)


def backdate(application, model, row_id: str, *, hours: float = 0,
             minutes: float = 0):
    """Move a row's created_at/updated_at into the past so
    time-based detection (stalls, SLA) can be exercised without
    sleeping. Test-only manipulation of recorded timestamps."""
    import datetime as dt

    from app.database.models.base import as_utc
    session = application.session_factory()
    try:
        row = session.get(model, row_id)
        delta = dt.timedelta(hours=hours, minutes=minutes)
        row.created_at = as_utc(row.created_at) - delta
        row.updated_at = as_utc(row.updated_at) - delta
        session.commit()
    finally:
        session.close()
