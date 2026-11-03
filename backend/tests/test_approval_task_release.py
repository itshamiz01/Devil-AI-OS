"""Approval-gated task lifecycle.

Covers the fix for the P-01 dead end where a task submitted with
approval_required=true parked in WAITING_FOR_APPROVAL with no approval record,
no subscriber able to release it, and cancellation as the only exit.
"""
import asyncio
from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.application import create_app
from app.database.connection import Database
from app.database.models import utcnow
from app.database.repositories import ApprovalRepo, PrincipalRepo, TaskRepo
from app.permissions.models import canonical_payload_hash
from app.tasks.manager import TASK_APPROVAL_ACTION, TASK_APPROVAL_PERMISSIONS
from conftest import _bootstrap, wait_task


def submit_gated(client, name="gated", **kwargs):
    body = {"name": name, "handler": "system.noop", "payload": {}, "approval_required": True}
    body.update(kwargs)
    resp = client.post("/api/v1/tasks", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def gate_for(client, task_id):
    """The approval that gates this task, as the owner sees it through the API."""
    resp = client.get("/api/v1/approvals", params={"limit": 200})
    assert resp.status_code == 200
    matches = [a for a in resp.json()["data"] if a["resource"] == task_id and a["action"] == TASK_APPROVAL_ACTION]
    return matches


def decide(client, approval_id, decision, notes=""):
    resp = client.post(f"/api/v1/approvals/{approval_id}/decision", json={"decision": decision, "notes": notes})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def mutate_approval(settings, approval_id, **fields):
    """Direct DB write, to simulate expiry, tampering and a lost release event."""
    async def run():
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                approval = await ApprovalRepo(session).get(approval_id)
                for key, value in fields.items():
                    setattr(approval, key, value)
                await session.commit()
        finally:
            await db.dispose()
    asyncio.run(run())


def test_gated_task_creates_one_decisionable_approval(client: TestClient):
    task = submit_gated(client)
    assert task["status"] == "WAITING_FOR_APPROVAL"
    assert task["approval_required"] is True

    gates = gate_for(client, task["id"])
    assert len(gates) == 1, f"expected exactly one gate, got {gates}"
    gate = gates[0]
    assert gate["status"] == "pending"
    # The gate must be bound to what will actually execute.
    expected = canonical_payload_hash(
        TASK_APPROVAL_ACTION, task["id"], list(TASK_APPROVAL_PERMISSIONS),
        {"handler": task["handler"], "name": task["name"], "payload": task["payload"]},
    )
    assert gate["payload_hash"] == expected
    assert gate["risk"] == "medium"


def test_gated_task_does_not_execute_before_approval(client: TestClient):
    task = submit_gated(client, handler="system.echo", payload={"message": "must not run"})
    status = client.get(f"/api/v1/tasks/{task['id']}").json()["data"]
    assert status["status"] == "WAITING_FOR_APPROVAL"
    assert status["result"] is None
    history = client.get(f"/api/v1/tasks/{task['id']}/history").json()["data"]
    assert history == [], "gated task must not have any execution attempt"


def test_owner_can_approve_own_gated_task(client: TestClient):
    """Regression guard: the gate must stay decidable in P-01, where the owner is
    both requester and the only holder of approvals.decide. A high/critical risk
    level would trip the self-approval block and recreate the dead end."""
    task = submit_gated(client)
    gate = gate_for(client, task["id"])[0]
    decided = decide(client, gate["id"], "approved", "owner released it")
    assert decided["status"] == "approved"
    finished = wait_task(client, task["id"], {"COMPLETED"})
    assert finished["result"] == {"ok": True, "handler": "system.noop"}
    history = client.get(f"/api/v1/tasks/{task['id']}/history").json()["data"]
    assert len(history) == 1


def test_rejection_cancels_without_executing(client: TestClient):
    task = submit_gated(client, handler="system.echo", payload={"message": "must not run"})
    gate = gate_for(client, task["id"])[0]
    decide(client, gate["id"], "rejected", "not authorised")

    cancelled = wait_task(client, task["id"], {"CANCELLED"})
    assert cancelled["result"] is None
    assert cancelled["error_details"]["code"] == "APPROVAL_REJECTED"
    assert client.get(f"/api/v1/tasks/{task['id']}/history").json()["data"] == []


def test_rejected_gate_cannot_be_retried_into_execution(client: TestClient):
    """CANCELLED is terminal by design: FAILED -> QUEUED would let a rejected
    task be retried straight into execution with no approval at all."""
    task = submit_gated(client)
    gate = gate_for(client, task["id"])[0]
    decide(client, gate["id"], "rejected")
    wait_task(client, task["id"], {"CANCELLED"})

    assert client.post(f"/api/v1/tasks/{task['id']}/retry").status_code == 409
    assert client.post(f"/api/v1/tasks/{task['id']}/resume").status_code == 409
    assert client.get(f"/api/v1/tasks/{task['id']}").json()["data"]["status"] == "CANCELLED"


def test_expired_approval_cancels_task(client: TestClient, settings):
    task = submit_gated(client, handler="system.echo", payload={"message": "must not run"})
    gate = gate_for(client, task["id"])[0]
    mutate_approval(settings, gate["id"], expires_at=utcnow() - timedelta(seconds=1))

    cancelled = wait_task(client, task["id"], {"CANCELLED"}, timeout=10)
    assert cancelled["error_details"]["code"] == "APPROVAL_EXPIRED"
    assert client.get(f"/api/v1/tasks/{task['id']}/history").json()["data"] == []
    refreshed = client.get(f"/api/v1/approvals/{gate['id']}").json()["data"]
    assert refreshed["status"] == "expired"


def test_binding_mismatch_never_releases_task(client: TestClient, settings):
    task = submit_gated(client, handler="system.echo", payload={"message": "original"})
    gate = gate_for(client, task["id"])[0]
    # Simulate a tampered or stale gate: the hash no longer matches the task.
    mutate_approval(settings, gate["id"], payload_hash=canonical_payload_hash(
        TASK_APPROVAL_ACTION, task["id"], list(TASK_APPROVAL_PERMISSIONS),
        {"handler": task["handler"], "name": task["name"], "payload": {"message": "tampered"}},
    ))

    decide(client, gate["id"], "approved")
    cancelled = wait_task(client, task["id"], {"CANCELLED"}, timeout=10)
    assert cancelled["error_details"]["code"] == "APPROVAL_BINDING_MISMATCH"
    assert cancelled["result"] is None
    assert client.get(f"/api/v1/tasks/{task['id']}/history").json()["data"] == []


def test_decision_applied_even_when_release_event_is_lost(client: TestClient, settings):
    """The periodic sweep must reach the same outcome as the live event path."""
    task = submit_gated(client)
    gate = gate_for(client, task["id"])[0]
    owner_id = task["creator_id"]
    # Record the decision directly, bypassing the event bus entirely.
    mutate_approval(settings, gate["id"], status="approved", approver_id=owner_id, decided_at=utcnow())

    finished = wait_task(client, task["id"], {"COMPLETED"}, timeout=10)
    assert finished["result"] == {"ok": True, "handler": "system.noop"}


def test_idempotent_resubmit_does_not_duplicate_gate(client: TestClient):
    key = "gated-idem-1"
    first = submit_gated(client, name="gated-a", idempotency_key=key)
    second = submit_gated(client, name="gated-a", idempotency_key=key)
    assert first["id"] == second["id"]
    assert len(gate_for(client, first["id"])) == 1


def test_startup_reconciles_gated_task_left_offline(settings, owner_credentials):
    """A gate that expired while the process was down must be closed on startup
    rather than stranding the task forever."""
    asyncio.run(_bootstrap(settings, *owner_credentials))

    async def insert_gated_with_expired_approval():
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                owner = await PrincipalRepo(session).by_name(owner_credentials[0])
                task = await TaskRepo(session).create(
                    name="offline-gated", handler="system.noop", status="WAITING_FOR_APPROVAL",
                    creator_id=owner.id, payload={}, approval_required=True,
                )
                await ApprovalRepo(session).create(
                    requester_id=owner.id, action=TASK_APPROVAL_ACTION, resource=task.id,
                    risk="medium", reason="offline gate", requested_permissions=list(TASK_APPROVAL_PERMISSIONS),
                    payload_hash=canonical_payload_hash(TASK_APPROVAL_ACTION, task.id, list(TASK_APPROVAL_PERMISSIONS),
                                                        {"handler": task.handler, "name": task.name, "payload": task.payload}),
                    status="pending", expires_at=utcnow() - timedelta(seconds=30),
                )
                await session.commit()
                return task.id
        finally:
            await db.dispose()

    task_id = asyncio.run(insert_gated_with_expired_approval())

    with TestClient(create_app(settings)) as c:
        login = c.post("/api/v1/auth/login", json={"username": owner_credentials[0], "password": owner_credentials[1]})
        token = login.json()["data"]["access_token"]
        resp = c.get(f"/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        task = resp.json()["data"]
        assert task["status"] == "CANCELLED"
        assert task["error_details"]["code"] == "APPROVAL_EXPIRED"
        assert c.get(f"/api/v1/tasks/{task_id}/history", headers={"Authorization": f"Bearer {token}"}).json()["data"] == []


def test_ungated_tasks_are_unaffected(client: TestClient):
    """The wiring must not change ordinary submissions."""
    resp = client.post("/api/v1/tasks", json={"name": "plain", "handler": "system.noop", "payload": {}})
    assert resp.status_code == 201
    task_id = resp.json()["data"]["id"]
    assert gate_for(client, task_id) == []
    assert wait_task(client, task_id, {"COMPLETED"})["result"]["ok"] is True
