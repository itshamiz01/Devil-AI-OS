"""Shared fixtures and seeding helpers for the P-12 test suite.

Seeding goes through governed paths: agents are P-01 rows (the
p09_support helper), businesses come from the P-06 fixture path,
budgets/cash through P-07's authorised paths (p07_support), and
capability grants through the P-04 CapabilityService.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.application import Application
from app.main import create_app
from app.permissions.models import Principal, PrincipalType
from tests.conftest import OWNER, make_settings  # noqa: F401
from tests.p09_support import (  # noqa: F401
    AGENT, AGENT2, EXTERNAL, SERVICE, register_agent,
)
from tests.p06_support import make_fixture_business  # noqa: F401
from tests.p07_support import business_with_profile, money  # noqa: F401

SYSTEM = Principal(PrincipalType.SYSTEM, "system")


@pytest.fixture
async def app_ops(tmp_path):
    """Controlled-mode application (same posture as P-06–P-11)."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


@pytest.fixture
def client_ops(tmp_path):
    app = create_app(make_settings(tmp_path, mode="controlled"))
    with TestClient(app) as client:
        yield client


def owner_http_headers(client) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "test-owner-password-123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def grant_capability(application, agent_id: str, capability: str):
    return application.agents.capabilities.grant(
        agent_id, capability, granted_by=OWNER)


def grant_permission(application, principal, permission: str,
                     resource: str | None = None):
    """An explicit P-01 allow rule — the governed grant path the
    permission engine evaluates (an owner's grant, recorded as a
    rule, exactly as P-04 capability grants mirror theirs)."""
    from app.database.models.core import Permission as PermissionRow
    from app.database.repositories.core import PermissionRepository
    session = application.session_factory()
    try:
        PermissionRepository(session).add(PermissionRow(
            principal_type=principal.type.value,
            principal_id=principal.id, permission=permission,
            effect="allow", resource=resource))
    finally:
        session.close()


def echo_step(step_key: str = "work", *, action_class: str = "business.read",
              message: str = "done", **extra) -> dict:
    step = {"step_key": step_key, "name": step_key, "kind": "task_handler",
            "action_class": action_class,
            "substrate": {"handler": "core.echo_check",
                          "payload": {"message": message}},
            "acceptance_criteria": {"task_status": "completed"}}
    step.update(extra)
    return step


def make_workflow(application, principal=OWNER, *, steps=None,
                  name: str = "Test workflow", business_id=None,
                  autonomy_level: int = 2, **overrides) -> dict:
    """Create + validate a workflow; returns the READY view."""
    data = {"name": name, "business_id": business_id,
            "objective": "test objective",
            "definition": {"steps": steps or [echo_step()]},
            "autonomy_level": autonomy_level}
    data.update(overrides)
    ops = application.operations
    created = ops.create_workflow(principal, data)
    return ops.validate_workflow(principal, created["id"])


async def run_workflow(application, principal, workflow_id: str) -> dict:
    return await application.operations.start_workflow(principal,
                                                       workflow_id)
