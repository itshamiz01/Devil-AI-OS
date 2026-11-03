import asyncio

from fastapi.testclient import TestClient

from app.core.application import create_app
from app.database.connection import Database
from app.database.repositories import PrincipalRepo, TaskRepo
from app.events.bus import EventBus
from app.events.events import Event
from conftest import _bootstrap


def test_restart_marks_running_task_interrupted(settings, owner_credentials):
    asyncio.run(_bootstrap(settings, *owner_credentials))

    async def insert_running():
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                owner = await PrincipalRepo(session).by_name(owner_credentials[0])
                task = await TaskRepo(session).create(name="interrupted", handler="system.noop", status="RUNNING", creator_id=owner.id, payload={})
                await session.commit()
                return task.id
        finally:
            await db.dispose()

    task_id = asyncio.run(insert_running())
    with TestClient(create_app(settings)) as c:
        login = c.post("/api/v1/auth/login", json={"username": owner_credentials[0], "password": owner_credentials[1]})
        token = login.json()["data"]["access_token"]
        resp = c.get(f"/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        task = resp.json()["data"]
        assert task["status"] == "FAILED"
        assert task["error_details"]["code"] == "INTERRUPTED"


def test_event_subscriber_failure_isolated(settings):
    async def run():
        db = Database(settings)
        try:
            await db.initialize()
            bus = EventBus(db)
            received = []

            async def bad(event: Event):
                raise RuntimeError("subscriber failure")

            async def good(event: Event):
                received.append(event.event_type)

            bus.subscribe("SystemWarning", bad)
            bus.subscribe("SystemWarning", good)
            await bus.start()
            await bus.publish_new("SystemWarning", "test", {"x": 1})
            await bus.drain()
            await bus.stop()
            return received
        finally:
            await db.dispose()

    assert asyncio.run(run()) == ["SystemWarning"]
