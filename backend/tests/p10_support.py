"""Shared fixtures and seeding helpers for the P-10 test suite.

Seeding goes through governed paths wherever one exists: agents are
registered as P-01 rows (mirroring how P-01 registers an agent with
a business_ref — the same helper P-09 used), businesses come from
the P-06 fixture path (via p09_support), approvals are created and
decided through the P-01 ApprovalService, and financial state is
seeded through P-07's authorised paths (via p07_support helpers).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.application import Application
from app.main import create_app
from app.permissions.models import Principal, PrincipalType
from tests.conftest import OWNER, make_settings  # noqa: F401
from tests.p09_support import AGENT, AGENT2, EXTERNAL, SERVICE, register_agent  # noqa: F401
from tests.p06_support import make_fixture_business  # noqa: F401

SYSTEM = Principal(PrincipalType.SYSTEM, "system")


@pytest.fixture
async def app_sec(tmp_path):
    """Controlled-mode application (same posture as P-06–P-09)."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


@pytest.fixture
def client_sec(tmp_path):
    app = create_app(make_settings(tmp_path, mode="controlled"))
    with TestClient(app) as client:
        yield client


def owner_http_headers(client) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "test-owner-password-123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def service_http_headers() -> dict:
    return {"Authorization": "Bearer service-token-for-tests"}


def audit_events(application, action_prefix: str | None = None) -> list:
    """All P-01 audit events (optionally filtered by action prefix),
    newest first — the shared evidence reader for the P-10 suites."""
    from app.database.repositories.security import SecurityAuditQuery
    session = application.session_factory()
    try:
        rows, _total = SecurityAuditQuery(session).list_events(
            action_prefix=action_prefix, limit=500)
        return rows
    finally:
        session.close()
