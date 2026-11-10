"""Shared fixtures and helpers for the Expansion Feature 2
(Universal Integration Framework) suites.

Posture mirrors f01_support: a controlled-mode application, owner
HTTP login through the real P-01 path, and the shared audit reader.
Credentials in helpers are registered through the real P-10
``SecretService`` (metadata references only) with values supplied
through the process environment — exactly the production shape.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.application import Application
from app.main import create_app
from tests.conftest import AGENT, EXTERNAL, OWNER, SERVICE, make_settings  # noqa: F401
from tests.p10_support import audit_events  # noqa: F401

PASSWORD = "test-owner-password-123"


@pytest.fixture
async def app_f02(tmp_path):
    """Controlled-mode application (same posture as P-10/F01)."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


@pytest.fixture
def client_f02(tmp_path):
    app = create_app(make_settings(tmp_path, mode="controlled"))
    with TestClient(app) as client:
        yield client


def owner_http_headers(client) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def service_http_headers() -> dict:
    return {"Authorization": "Bearer service-token-for-tests"}


def register_secret(application, name: str, env_name: str) -> dict:
    """Register a P-10 secret METADATA entry pointing at
    ``env:<env_name>``. The value itself lives only in the process
    environment (set by the test), never in the registry."""
    return application.security.secrets.register(OWNER, {
        "name": name, "reference": f"env:{env_name}",
        "purpose": "F02 test credential", "classification": 4})


def attach_mock(application, *, behaviour: str = "ok",
                requires_credential: bool = False,
                rate_limit_per_minute: int | None = None,
                key: str = "mock_connector", enable: bool = True):
    """Attach a MockConnectorAdapter through the framework's real
    developer flow and (by default) enable it as the owner."""
    from app.integrations.testing import MockConnectorAdapter
    adapter = MockConnectorAdapter(
        behaviour=behaviour, requires_credential=requires_credential,
        rate_limit_per_minute=rate_limit_per_minute, key=key)
    svc = application.integrations
    svc.attach_adapter(OWNER, adapter)
    if requires_credential:
        svc.configure_connector(OWNER, key, {
            "credential_secret_name": "mock_api_key"})
    if enable:
        svc.set_enabled(OWNER, key, True)
    return adapter
