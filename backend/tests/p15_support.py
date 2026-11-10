"""Shared fixtures for the P-15 test suite.

The application fixture mirrors P-13's controlled-mode posture.
OWNER/AGENT principals come from the shared conftest / P-09 support.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.application import Application
from app.main import create_app
from tests.conftest import OWNER, make_settings  # noqa: F401
from tests.p09_support import AGENT, SERVICE  # noqa: F401
from tests.p12_support import owner_http_headers  # noqa: F401


@pytest.fixture
async def app_rel(tmp_path):
    """Controlled-mode application with the P-15 service assembled."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


@pytest.fixture
def client_rel(tmp_path):
    app = create_app(make_settings(tmp_path, mode="controlled"))
    with TestClient(app) as client:
        yield client
