from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.application import create_app, seed_core_data
from app.core.auth import AuthService
from app.core.config import Settings
from app.database.connection import Database


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        task_queue_capacity=5,
        task_max_concurrency=1,
        task_default_timeout=2,
        retry_base_delay=0.01,
        retry_max_delay=0.05,
        scheduler_poll_interval=0.01,
        shutdown_timeout=1,
        login_rate_limit=20,
    )


async def _bootstrap(settings: Settings, username: str = "owner", password: str = "correct horse battery staple") -> str:
    db = Database(settings)
    try:
        await db.initialize()
        await seed_core_data(db, settings)
        return await AuthService(settings, db).bootstrap_owner(username, password)
    finally:
        await db.dispose()


@pytest.fixture()
def owner_credentials() -> tuple[str, str]:
    return "owner", "correct horse battery staple"


@pytest.fixture()
def client(settings: Settings, owner_credentials: tuple[str, str]):
    asyncio.run(_bootstrap(settings, *owner_credentials))
    app = create_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/v1/auth/login", json={"username": owner_credentials[0], "password": owner_credentials[1]})
        assert resp.status_code == 200, resp.text
        token = resp.json()["data"]["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


def wait_task(client: TestClient, task_id: str, statuses: set[str], timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200
        task = resp.json()["data"]
        if task["status"] in statuses:
            return task
        time.sleep(0.03)
    raise AssertionError(f"Task {task_id} did not reach {statuses}; last={task}")
