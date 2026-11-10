"""Shared fixtures and seeding helpers for the P-09 test suite.

Memory content is seeded only through the governed P-09 paths
(store.create / ingestion.ingest / learning.analyze) — no test writes
a memory table row directly except the agent-registration helper,
which mirrors how P-01 registers an agent with a business_ref.
Financial references point at REAL P-07 records seeded through
P-07's authorised paths (via tests.p07_support) — never at invented
ledger rows.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.application import Application
from app.main import create_app
from app.permissions.models import Principal, PrincipalType
from tests.conftest import OWNER, make_settings  # noqa: F401
from tests.p06_support import make_fixture_business  # noqa: F401

AGENT = Principal(PrincipalType.AGENT, "agent-1")
AGENT2 = Principal(PrincipalType.AGENT, "agent-2")
EXTERNAL = Principal(PrincipalType.EXTERNAL, "ext-1")
SERVICE = Principal(PrincipalType.SERVICE, "service-api")


@pytest.fixture
async def app_mem(tmp_path):
    """Controlled-mode application (same posture as P-06–P-08)."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


@pytest.fixture
def client_mem(tmp_path):
    app = create_app(make_settings(tmp_path, mode="controlled"))
    with TestClient(app) as client:
        yield client


def owner_http_headers(client) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "test-owner-password-123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def register_agent(application, agent_id: str, *, business_ref: str | None = None):
    """Register a P-01 Agent row so business_ref resolution works the
    same way P-07/P-08 access checks resolve it."""
    from app.database.models.core import Agent as AgentRow
    session = application.session_factory()
    try:
        if session.get(AgentRow, agent_id) is None:
            session.add(AgentRow(id=agent_id, name=agent_id, role="research",
                                 business_ref=business_ref, status="active"))
            session.commit()
    finally:
        session.close()


def make_record(application, principal=OWNER, **overrides) -> dict:
    data = {
        "layer": "semantic", "category": "TECHNICAL_KNOWLEDGE",
        "title": "Deployment runbook summary",
        "content": "Deploy the staging build by running the migration, "
                   "restarting the service and checking the health endpoint.",
        "subject": "deployment", "predicate": "procedure",
        "truth_class": "user_provided", "source_type": "user_input",
        "source_ref": "owner-note-1", "access_scope": "ORGANIZATION_SHARED",
    }
    data.update(overrides)
    return application.memory.store.create(principal, data)
