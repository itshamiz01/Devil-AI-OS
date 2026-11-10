from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("TMPDIR", str(BACKEND.parent / ".tmp"))

import pytest
from fastapi.testclient import TestClient

from app.core.application import Application
from app.core.config import Settings
from app.main import create_app
from app.permissions.models import Principal, PrincipalType

OWNER = Principal(PrincipalType.OWNER, "owner")
AGENT = Principal(PrincipalType.AGENT, "agent-1")
SERVICE = Principal(PrincipalType.SERVICE, "service-api")
EXTERNAL = Principal(PrincipalType.EXTERNAL, "ext-1")


def make_settings(tmp_path: Path, **overrides) -> Settings:
    kwargs = dict(
        environment="test",
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{tmp_path}/test.db",
        admin_password="test-owner-password-123",
        dev_token="dev-token-for-tests",
        service_token="service-token-for-tests",
        log_file=str(tmp_path / "logs" / "test.log"),
        auto_migrate=False,
        # Host load on the shared test VM must not gate submissions; the
        # threshold mechanism itself is tested with forced values.
        block_nonessential_on_threshold=False,
        retry_base_delay_seconds=0.01,
        retry_max_delay_seconds=0.05,
    )
    kwargs.update(overrides)
    return Settings(**kwargs)


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture()
async def application(settings) -> Application:
    app_core = Application(settings)
    await app_core.startup()
    yield app_core
    await app_core.shutdown()


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client) -> dict:
    resp = client.post("/api/v1/auth/login",
                       json={"username": "owner", "password": "test-owner-password-123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def service_headers() -> dict:
    return {"Authorization": "Bearer service-token-for-tests"}


async def wait_for_status(manager, task_id: str, statuses: set[str], timeout: float = 5.0) -> str:
    import asyncio
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = manager.get(task_id).status
        if status in statuses:
            return status
        await asyncio.sleep(0.02)
    raise AssertionError(f"task {task_id} did not reach {statuses}; last={manager.get(task_id).status}")
