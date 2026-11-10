"""P-14 Stage A §8 Orchestration Failure Scenarios — additive audit tests.

Traces REQUEST->CONTEXT->INTENT->POLICY->PLANNING->DECOMPOSITION->
ASSIGNMENT->APPROVAL->EXECUTION->VERIFICATION->MEMORY->REPORTING
as it actually exists: P-02 Intelligence (missions/plans) + P-12
Operations (workflows). Where a stage is not a distinct mechanism,
the test targets what does exist (see report for the stage map).
Fixtures only.
"""
from __future__ import annotations

import pytest

from app.core.exceptions import PermissionDeniedError, ValidationError
from app.intelligence.planner import PlanRejectedError, parse_proposal
from app.intelligence.providers import FakeProvider, OllamaProvider
from app.permissions.models import Permission
from tests.conftest import OWNER
from tests.p09_support import AGENT, register_agent
from tests.p12_support import app_ops, echo_step, grant_permission, make_workflow

pytestmark = pytest.mark.asyncio


def _link(application, workflow_id, purpose="task_step"):
    from app.database.repositories.operations import ApprovalLinkRepository
    session = application.session_factory()
    try:
        for link in ApprovalLinkRepository(session).list_for_workflow(workflow_id):
            if link.purpose == purpose and link.status == "pending":
                return link.approval_id
        return None
    finally:
        session.close()


def _task(application, workflow_id, step_key):
    detail = application.operations.get_workflow(OWNER, workflow_id)
    return next(t for t in detail["tasks"] if t["step_key"] == step_key)


# 1. Provider unavailable -> router falls back to baseline, no crash/fabrication
async def test_p14_orch_provider_unavailable_falls_back(application):
    intel = application.intelligence
    # Dead Ollama endpoint (verified honest probe in P-02 unit suite)
    intel.providers["ollama"] = OllamaProvider("http://127.0.0.1:1", timeout_seconds=0.5)
    available, detail = await intel.providers["ollama"].probe()
    assert available is False and "unavailable" in detail
    # Cloud stub disabled by default
    cavail, cdetail = await intel.providers["cloud"].probe()
    assert cavail is False
    # Enable a profile pointing at the dead ollama: router must skip it
    intel.upsert_profile(OWNER, "p14-dead-ollama", {
        "task_classes": ["planning"], "provider": "ollama",
        "model_id": "some-model", "enabled": True, "limits": {"size_rank": 1}})
    decision = await intel._router.select("planning")
    assert decision.kind == "baseline"
    assert any("ollama" in r or "unavailable" in r for r in decision.reasons)
    mission = await intel.create_mission(OWNER, "Check system health and report whether the task system is working")
    plan = await intel.create_plan(OWNER, mission.id)
    assert plan.planner == "rule-engine"  # deterministic baseline, not fabricated LLM
    assert plan.status == "draft"


# 2. Provider unavailable + no template -> fails safely, no fabricated plan
async def test_p14_orch_provider_unavailable_no_plan_no_fabrication(application):
    intel = application.intelligence
    intel.providers["ollama"] = OllamaProvider("http://127.0.0.1:1", timeout_seconds=0.5)
    intel.upsert_profile(OWNER, "p14-dead2", {
        "task_classes": ["planning"], "provider": "ollama",
        "model_id": "m", "enabled": True, "limits": {"size_rank": 1}})
    mission = await intel.create_mission(OWNER, "Investigate quarterly market trends for umbrellas in Lisbon")
    with pytest.raises(ValidationError):
        await intel.create_plan(OWNER, mission.id)
    assert intel.get_mission(mission.id).status == "planning_failed"
    # No plan rows exist for this mission
    from app.database.repositories.intelligence import PlanRepository
    session = application.session_factory()
    try:
        assert PlanRepository(session).count_for_mission(mission.id) == 0
    finally:
        session.close()


# 3. Invalid model output (garbage shape) -> recorded, falls back / fails safely
async def test_p14_orch_invalid_model_output_garbage(application):
    intel = application.intelligence
    intel.providers["fake"] = FakeProvider(raw_output={"steps": "not-a-list"})
    intel.upsert_profile(OWNER, "p14-fake-garbage", {
        "task_classes": ["planning"], "provider": "fake",
        "model_id": "fake-1", "enabled": True, "limits": {"size_rank": 1}})
    # Health mission has a baseline template -> fallback succeeds honestly
    mission = await intel.create_mission(OWNER, "Check system health and report")
    plan = await intel.create_plan(OWNER, mission.id)
    assert plan.planner == "rule-engine"
    decisions, _ = intel.recorder.list(mission_id=mission.id, limit=100)
    assert any(d.decision_type == "llm_plan_unusable" for d in decisions)
    # Direct parse gate also rejects garbage
    with pytest.raises(PlanRejectedError):
        parse_proposal("not a plan")
    with pytest.raises(PlanRejectedError):
        parse_proposal({"steps": []})


# 4. Invalid model output (impermissible tool) -> REJECTED outright, NO fallback
async def test_p14_orch_invalid_model_output_impermissible_rejected(application):
    intel = application.intelligence
    intel.providers["fake"] = FakeProvider(raw_output={
        "steps": [{"tool_name": "os.system", "payload": {"command": "calc"}}],
        "rationale": "malicious"})
    intel.upsert_profile(OWNER, "p14-fake-evil", {
        "task_classes": ["planning"], "provider": "fake",
        "model_id": "fake-1", "enabled": True, "limits": {"size_rank": 1}})
    # Mission text WOULD match a baseline template; fallback must NOT happen
    mission = await intel.create_mission(OWNER, "Check system health and report")
    with pytest.raises(PlanRejectedError) as exc:
        await intel.create_plan(OWNER, mission.id)
    assert "unregistered tool" in str(exc.value)
    # A rejected plan row is the security record
    from app.database.repositories.intelligence import PlanRepository
    session = application.session_factory()
    try:
        repo = PlanRepository(session)
        assert repo.count_for_mission(mission.id) == 1
    finally:
        session.close()
    decisions, _ = intel.recorder.list(mission_id=mission.id, limit=100)
    assert any(d.decision_type == "plan_rejected" for d in decisions)


# 5. Invalid payload from model -> rejected at same validation gate
async def test_p14_orch_invalid_model_payload_rejected(application):
    intel = application.intelligence
    intel.providers["fake"] = FakeProvider(raw_output={
        "steps": [{"tool_name": "core.echo_check", "payload": {"data": {}}}],
        "rationale": "missing required message"})
    intel.upsert_profile(OWNER, "p14-fake-badpayload", {
        "task_classes": ["planning"], "provider": "fake",
        "model_id": "fake-1", "enabled": True, "limits": {"size_rank": 1}})
    mission = await intel.create_mission(OWNER, "Echo: hello")
    with pytest.raises(PlanRejectedError):
        await intel.create_plan(OWNER, mission.id)


# 6. Execution handler failure -> workflow FAILED, never claimed success, DLQ
async def test_p14_orch_execution_failure_not_success(app_ops):
    from tests.p05_support import grant as p05_grant, make_agent
    agent_id = await make_agent(app_ops)
    await p05_grant(app_ops, agent_id, "file_read")
    ops = app_ops.operations
    step = {"step_key": "read-file", "name": "Read missing file",
            "kind": "execution", "action_class": "business.read",
            "substrate": {"tool": "filesystem", "action": "read",
                          "parameters": {"path": "p14-no-such-file.txt"}},
            "retry_policy": {"max_retries": 0},
            "acceptance_criteria": {"task_status": "completed"}}
    view = make_workflow(app_ops, steps=[step])
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "FAILED"
    assert result["verified_outcome"] != "verified"
    task = _task(app_ops, view["id"], "read-file")
    assert task["status"] in ("FAILED", "DEAD_LETTER")
    request = app_ops.execution.get_request(task["substrate_ref"])
    assert request.status == "FAILED"
    recovery = ops.recovery_center(OWNER)
    assert recovery["dead_letter_total"] >= 1


# 7. Unauthorized tool invocation -> rejected at validation (P-12 + P-02)
async def test_p14_orch_unauthorized_tool_rejected(app_ops, application):
    ops = app_ops.operations
    # (i) Non-vocabulary action class fails closed at create time
    with pytest.raises(ValidationError):
        ops.create_workflow(OWNER, {
            "name": "bad-class", "definition": {"steps": [
                {"step_key": "x", "name": "x", "kind": "task_handler",
                 "action_class": "totally.invented.action",
                 "substrate": {"handler": "core.echo_check", "payload": {"message": "hi"}}}]}})
    # (ii) Unregistered handler passes create (definition shape ok) but
    # fails workflow validation — never reaches execution
    created = ops.create_workflow(OWNER, {
        "name": "bad-handler", "definition": {"steps": [
            {"step_key": "x", "name": "x", "kind": "task_handler",
             "action_class": "business.read",
             "substrate": {"handler": "evil.unregistered", "payload": {}}}]}})
    with pytest.raises(ValidationError):
        ops.validate_workflow(OWNER, created["id"])
    assert ops.get_workflow(OWNER, created["id"])["status"] == "DRAFT"
    # (iii) Raw instruction text is not an executable definition
    with pytest.raises(ValidationError):
        ops.create_workflow(OWNER, {"name": "raw", "definition": {"instruction": "do anything"}})
    # (iv) No direct step execution bypass exists
    assert not hasattr(ops, "execute_step_directly")
    assert not hasattr(ops, "execute_step_direct")


# 8. Interrupted workflow -> RECOVERY_PENDING, substrate count exactly 1 on resume
async def test_p14_orch_interrupted_workflow_exactly_once(app_ops):
    from app.database.repositories.operations import WorkflowRepository
    register_agent(app_ops, AGENT.id)
    grant_permission(app_ops, AGENT, Permission.MODIFY_BUSINESS_DATA)
    ops = app_ops.operations
    steps = [echo_step("first", message="p14-step-one"),
             {"step_key": "publish", "name": "Publish", "kind": "task_handler",
              "action_class": "content.publish",
              "substrate": {"handler": "core.echo_check", "payload": {"message": "published"}},
              "depends_on": ["first"],
              "acceptance_criteria": {"task_status": "completed"}}]
    view = make_workflow(app_ops, steps=steps, autonomy_level=2)
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "WAITING_FOR_APPROVAL"
    first = _task(app_ops, view["id"], "first")
    assert first["status"] == "COMPLETED"
    substrate_id = first["substrate_ref"]
    # Simulate crash: leave workflow RUNNING mid-flight
    session = app_ops.session_factory()
    try:
        repo = WorkflowRepository(session)
        row = repo.get(view["id"]); row.status = "RUNNING"; repo.save(row)
    finally:
        session.close()
    assert ops.recover_interrupted() == 1
    assert ops.get_workflow(OWNER, view["id"])["status"] == "RECOVERY_PENDING"
    link = _link(app_ops, view["id"])
    assert link
    app_ops.approvals.decide(link, OWNER, True)
    resumed = await ops.check_approvals(OWNER)
    assert view["id"] in resumed["driven"]
    final = ops.get_workflow(OWNER, view["id"])
    assert final["status"] == "COMPLETED"
    assert len(app_ops.tasks.history(substrate_id)) == 1  # exactly once


# 9. Conflicting / duplicate submission -> idempotency (workflow create)
async def test_p14_orch_duplicate_submission_idempotent(app_ops):
    ops = app_ops.operations
    data = {"name": "P14 idempotent wf", "objective": "idem",
            "definition": {"steps": [echo_step("only")]},
            "autonomy_level": 2, "idempotency_key": "p14-idem-1"}
    first = ops.create_workflow(OWNER, data)
    second = ops.create_workflow(OWNER, dict(data))
    assert first["id"] == second["id"]
    assert ops.list_workflows(OWNER)["total"] == 1
    # Validating/starting the single workflow completes once
    view = ops.validate_workflow(OWNER, first["id"])
    result = await ops.start_workflow(OWNER, view["id"])
    assert result["status"] == "COMPLETED"
    task = _task(app_ops, view["id"], "only")
    assert len(app_ops.tasks.history(task["substrate_ref"])) == 1


# 10. Verification gate: completion != success + lifecycle trace + learning
async def test_p14_orch_verification_gate_and_lifecycle_trace(app_ops):
    register_agent(app_ops, AGENT.id)
    ops = app_ops.operations
    # --- verification gate ---
    bad_step = echo_step("check")
    bad_step["acceptance_criteria"] = {"result_equals": {"ok": False}}
    bad = make_workflow(app_ops, steps=[bad_step], name="p14 verify-fail")
    result = await ops.start_workflow(OWNER, bad["id"])
    assert result["status"] == "FAILED"
    assert result["verified_outcome"] == "failed"
    assert result["learning_record_id"] is None
    task = _task(app_ops, bad["id"], "check")
    assert task["verification_status"] == "failed"
    substrate = app_ops.tasks.get(task["substrate_ref"])
    assert substrate.status == "completed"  # substrate completed, verification failed it
    # --- full lifecycle trace on a good workflow ---
    good = make_workflow(app_ops, steps=[echo_step("ok")], name="p14 trace")
    good_result = await ops.start_workflow(OWNER, good["id"])
    assert good_result["status"] == "COMPLETED"
    assert good_result["verified_outcome"] == "verified"
    assert good_result["learning_record_id"]  # MEMORY stage: exactly one learning record
    history = ops.workflow_history(OWNER, good["id"])
    event_types = [e["event_type"] for e in history["events"]]
    assert "workflow.created" in event_types
    assert "workflow.validated" in event_types
    assert "workflow.started" in event_types
    assert "workflow.completed" in event_types
    # REPORTING: decisions recorded for validation + execution
    decisions = ops.list_decisions(OWNER, workflow_id=good["id"])["items"]
    assert any(d["category"] == "EXECUTE" for d in decisions)
