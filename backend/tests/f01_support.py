"""Shared fixtures and helpers for the Expansion Feature 1
(Identity & Device Security) suites.

The posture mirrors p10_support: a controlled-mode application,
owner HTTP login through the real P-01 path, and the shared audit
reader. Device enrolment in helpers goes through the real
``DeviceService`` (the governed path), never raw rows.
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
async def app_ids(tmp_path):
    """Controlled-mode application (same posture as P-10)."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


@pytest.fixture
def client_ids(tmp_path):
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


def login_with_device(application, device_id: str, device_secret: str):
    """A real P-01 password login presenting a device credential.
    Returns the session token, or None when refused."""
    return application.auth.login(
        "owner", PASSWORD, device_id=device_id, device_secret=device_secret)


def enrol_device(application, label: str = "Owner laptop", *, trust=False):
    """Enrol through the governed service path. Returns
    (device_dict, device_secret). With trust=True the owner also
    performs the explicit trust act."""
    svc = application.security.devices
    created = svc.enrol(OWNER, {"label": label, "platform": "windows",
                                "device_name": "test-host"})
    secret = created.pop("device_secret")
    created.pop("secret_shown_once")
    if trust:
        created = svc.set_trust(OWNER, created["id"], True)
    return created, secret
