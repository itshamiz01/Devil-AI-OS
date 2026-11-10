"""Shared fixtures/helpers for the P-05 suites.

P-05 execution tests run in ``controlled`` mode: the default test mode
(simulation) deliberately refuses side-effecting execution at policy
check 10, which the mode tests assert separately.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.application import Application
from app.main import create_app
from tests.conftest import OWNER, make_settings


@pytest.fixture()
async def app_rw(tmp_path):
    app_core = Application(make_settings(tmp_path, mode="controlled"))
    await app_core.startup()
    yield app_core
    await app_core.shutdown()


@pytest.fixture()
def client_rw(tmp_path):
    app = create_app(make_settings(tmp_path, mode="controlled"))
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def owner_headers(client_rw) -> dict:
    resp = client_rw.post("/api/v1/auth/login",
                          json={"username": "owner",
                                "password": "test-owner-password-123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def make_agent(application, role: str = "research_agent") -> str:
    created = await application.agents.create_agent({"role": role}, principal=OWNER)
    return created["created_agent_id"]


async def grant(application, agent_id: str, capability: str) -> None:
    """Grant through the governed P-04 flow (owner approval for Level 2)."""
    factory = application.agents
    out = await factory.request_capability(agent_id, capability, principal=OWNER)
    if out.get("status") == "approval_required":
        await factory.approve_capability(agent_id, out["approval_id"],
                                         approver=OWNER, approve=True)
    assert factory.capabilities.has_capability(agent_id, capability), out


def engine(application, **kwargs):
    """A second ExecutionService over the same substrate, with injectable
    transports/broker for deterministic network tests. Seeding is
    idempotent, so this never disturbs the application-level service."""
    from app.execution.service import ExecutionService
    service = ExecutionService(
        application.session_factory, settings=application.settings,
        permissions=application.permissions, approvals=application.approvals,
        capabilities=application.agents.capabilities, bus=application.bus, **kwargs)
    service.seed()
    return service


def grant_http(client, headers, agent_id: str, capability: str) -> None:
    resp = client.post(f"/api/v1/agents/{agent_id}/permissions/request",
                       headers=headers, json={"capability": capability})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    if data.get("status") == "approval_required":
        resp = client.post(f"/api/v1/agents/{agent_id}/permissions/approve",
                           headers=headers,
                           json={"approval_id": data["approval_id"], "approve": True})
        assert resp.status_code == 200, resp.text
    resp = client.get(f"/api/v1/agents/{agent_id}/permissions", headers=headers)
    assert capability in resp.json()["data"]["effective_capabilities"], resp.text


def create_agent_http(client, headers, role: str = "research_agent") -> str:
    resp = client.post("/api/v1/agent-factory/create", headers=headers,
                       json={"role": role})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["created_agent_id"]
