"""P-12 security tests (§22 pipeline enforcement, Article 0).

The named properties: no direct LLM-to-executor path exists; only
registered handlers and P-10-vocabulary action classes validate;
approval parameter drift fails closed; the global emergency stop
blocks execution and only the owner restarts; cross-business access
is denied by default; agents never set the rules that govern them.
"""
from __future__ import annotations

import pytest

from app.core.exceptions import (
    PermissionDeniedError, ValidationError)
from app.permissions.models import Permission
from tests.p12_support import (
    AGENT, AGENT2, OWNER, app_ops, client_ops, echo_step,
    grant_permission, make_workflow, register_agent)
from tests.p06_support import make_fixture_business

pytestmark = pytest.mark.asyncio


def test_unregistered_handler_is_rejected_at_validation(app_ops):
    """Arbitrary code/handlers can never enter a workflow: the
    substrate handler must exist in the P-01 registry."""
    with pytest.raises(ValidationError):
        make_workflow(app_ops, steps=[{
            "step_key": "x", "name": "x", "kind": "task_handler",
            "action_class": "business.read",
            "substrate": {"handler": "os.system",
                          "payload": {"message": "rm -rf"}},
            "acceptance_criteria": {"task_status": "completed"}}])


def test_unclassified_action_is_rejected_at_validation(app_ops):
    with pytest.raises(ValidationError):
        make_workflow(app_ops, steps=[echo_step(
            "x", action_class="totally.made_up")])


def test_raw_llm_instruction_kind_is_rejected(app_ops):
    """There is no 'just do what the text says' step kind: proposals
    must be structured, validated definitions."""
    with pytest.raises(ValidationError):
        make_workflow(app_ops, steps=[{
            "step_key": "x", "name": "x", "kind": "llm_instruction",
            "action_class": "business.read",
            "substrate": {"instruction": "email everyone"},
            "acceptance_criteria": {}}])


def test_workflow_payload_cannot_carry_code(app_ops):
    with pytest.raises(ValidationError):
        make_workflow(app_ops, steps=[{
            "step_key": "x", "name": "x", "kind": "task_handler",
            "action_class": "business.read",
            "substrate": {"handler": "core.echo_check",
                          "payload": {"code": "import os"}},
            "acceptance_criteria": {}}])


async def test_approval_parameter_drift_fails_closed(app_ops):
    """Approving parameters P and executing P' is impossible: if the
    stored step is tampered with after approval, the binding check
    fails and the step dies as a policy violation — nothing runs."""
    from app.database.repositories.operations import (
        WorkflowTaskRepository)
    register_agent(app_ops, AGENT.id)
    grant_permission(app_ops, AGENT, Permission.MODIFY_BUSINESS_DATA)
    ops = app_ops.operations
    view = make_workflow(app_ops, steps=[{
        "step_key": "publish", "name": "Publish", "kind": "task_handler",
        "action_class": "content.publish",
        "substrate": {"handler": "core.echo_check",
                      "payload": {"message": "original"}},
        "acceptance_criteria": {"task_status": "completed"}}],
        autonomy_level=2)
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "WAITING_FOR_APPROVAL"
    # Tamper with the stored substrate after the approval was bound.
    session = app_ops.session_factory()
    try:
        repo = WorkflowTaskRepository(session)
        task = repo.get_by_step(view["id"], "publish")
        task.substrate = {"handler": "core.echo_check",
                          "payload": {"message": "TAMPERED"}}
        repo.save(task)
        task_id = task.id
    finally:
        session.close()
    from tests.test_p12_scenarios import _link
    approval_id = _link(app_ops, view["id"])
    app_ops.approvals.decide(approval_id, OWNER, True)
    outcome = await ops.check_approvals(OWNER)
    assert any(r["outcome"] == "drift_rejected"
               for r in outcome["resolved"])
    session = app_ops.session_factory()
    try:
        task = WorkflowTaskRepository(session).get(task_id)
        assert task.status == "FAILED"
        assert task.substrate_ref is None  # never executed
    finally:
        session.close()


async def test_global_emergency_stop_blocks_and_only_owner_resumes(app_ops):
    register_agent(app_ops, AGENT.id)
    ops = app_ops.operations
    await ops.emergency_stop(OWNER, "global", None)
    view = make_workflow(app_ops, steps=[echo_step("work")])
    blocked = await ops.start_workflow(OWNER, view["id"])
    assert blocked["status"] == "PAUSED"
    detail = ops.get_workflow(OWNER, view["id"])
    assert detail["tasks"][0]["substrate_ref"] is None
    with pytest.raises(PermissionDeniedError):
        await ops.emergency_resume(AGENT, "global", None)
    await ops.emergency_resume(OWNER, "global", None)
    resumed = await ops.resume_workflow(OWNER, view["id"])
    assert resumed["status"] == "COMPLETED"


async def test_cross_business_read_is_denied(app_ops):
    """An agent scoped to Business A cannot read Business B's
    workflow — isolation is enforced at the service boundary."""
    _o1, biz_a = await make_fixture_business(app_ops, name="Biz A")
    _o2, biz_b = await make_fixture_business(app_ops, name="Biz B")
    register_agent(app_ops, AGENT.id, business_ref=biz_a["id"])
    ops = app_ops.operations
    view_b = make_workflow(app_ops, steps=[echo_step("b")],
                           business_id=biz_b["id"])
    with pytest.raises(PermissionDeniedError):
        ops.get_workflow(AGENT, view_b["id"])
    # The owner reads both, of course.
    assert ops.get_workflow(OWNER, view_b["id"])["id"] == view_b["id"]


async def test_agent_cannot_modify_workflow_it_does_not_own(app_ops):
    register_agent(app_ops, AGENT.id)
    register_agent(app_ops, AGENT2.id)
    ops = app_ops.operations
    view = ops.create_workflow(AGENT, {
        "name": "agent one's workflow",
        "definition": {"steps": [echo_step("x")]}})
    ops.validate_workflow(AGENT, view["id"])
    with pytest.raises(PermissionDeniedError):
        ops.cancel_workflow(AGENT2, view["id"])


def test_settings_writes_are_owner_only(app_ops):
    ops = app_ops.operations
    with pytest.raises(PermissionDeniedError):
        ops.update_settings(AGENT, {"max_concurrent_workflows": 99})
    updated = ops.update_settings(OWNER, {"tick_interval_seconds": 42})
    assert updated["tick_interval_seconds"] == 42


async def test_approval_is_single_use(app_ops):
    """A decided approval cannot be decided again (P-01 store), and
    P-12's check pass is idempotent over resolved links."""
    register_agent(app_ops, AGENT.id)
    grant_permission(app_ops, AGENT, Permission.MODIFY_BUSINESS_DATA)
    ops = app_ops.operations
    view = make_workflow(app_ops, steps=[{
        "step_key": "publish", "name": "Publish", "kind": "task_handler",
        "action_class": "content.publish",
        "substrate": {"handler": "core.echo_check",
                      "payload": {"message": "once"}},
        "acceptance_criteria": {"task_status": "completed"}}],
        autonomy_level=2)
    await ops.start_workflow(OWNER, view["id"])
    from tests.test_p12_scenarios import _link
    approval_id = _link(app_ops, view["id"])
    app_ops.approvals.decide(approval_id, OWNER, True)
    from app.core.exceptions import ApprovalError
    with pytest.raises(ApprovalError):
        app_ops.approvals.decide(approval_id, OWNER, True)
    await ops.check_approvals(OWNER)
    again = await ops.check_approvals(OWNER)
    assert again["resolved"] == []  # nothing left to resolve
    assert ops.get_workflow(OWNER, view["id"])["status"] == "COMPLETED"
