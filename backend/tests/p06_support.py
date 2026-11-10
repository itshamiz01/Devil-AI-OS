"""Shared fixtures for the P-06 test-suite.

The app runs in *controlled* mode (P-05 precedent: simulation refuses
side-effecting execution at a policy check by design, and P-06 creation
runs are side-effecting inside managed workspaces). Fixture
opportunities are built exclusively through P-03's own machinery via
``app.business.fixtures`` — their validation levels are computed by
P-03, never asserted.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.business.fixtures import build_fixture_opportunity
from app.core.application import Application
from app.main import create_app
from app.permissions.models import Principal, PrincipalType
from tests.conftest import make_settings

OWNER = Principal(PrincipalType.OWNER, "owner")
AGENT_EXT = Principal(PrincipalType.AGENT, "agent-ext")
SERVICE = Principal(PrincipalType.SERVICE, "service-api")
EXTERNAL = Principal(PrincipalType.EXTERNAL, "ext-1")

DECLARATION = {
    "success_criteria": [
        "prepared package exists and hash-verifies",
        "at least 10 reader tests at the declared price point"],
    "budget_cap_amount": 50, "budget_currency": "USD",
    "duration_days": 30, "min_test_volume": 10,
}


@pytest.fixture
async def app_rw(tmp_path):
    """Controlled-mode application (creation runs execute for real
    inside throwaway managed workspaces)."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


@pytest.fixture
def client_rw(tmp_path):
    app = create_app(make_settings(tmp_path, mode="controlled"))
    with TestClient(app) as client:
        yield client


async def approver_owner(application) -> Principal:
    return OWNER


async def make_fixture_business(application, *, name="Beginner Fitness Ebook",
                                template="ebook_digital_product",
                                category="digital_products",
                                description_extra=""):
    """Fixture opportunity (P-03 machinery) → owner creation approval →
    business. Returns (opportunity_id, business dict)."""
    svc = application.business
    opp_id = await build_fixture_opportunity(
        application, name=name, category=category,
        description_extra=description_extra)
    request = await svc.request_creation_approval(
        OWNER, opp_id, template, reason="P-06 test fixture creation")
    application.approvals.decide(request["approval_id"], OWNER, True)
    business = await svc.create_business(
        OWNER, {"opportunity_id": opp_id, "template_name": template,
                "approval_id": request["approval_id"]})
    return opp_id, business


async def run_full_creation(application, business_id: str) -> dict:
    """Declaration → blueprint → creation run → channels. Returns the
    creation-run result."""
    svc = application.business
    await svc.create_declaration(OWNER, business_id, DECLARATION)
    await svc.generate_blueprint(OWNER, business_id)
    result = await svc.run_creation(OWNER, business_id)
    await svc.evaluate_channels(OWNER, business_id)
    return result
