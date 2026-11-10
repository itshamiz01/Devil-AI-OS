"""P-02 unit tests: plan schemas, baseline templates, identical validation,
model router matrix, result verifier, decision recorder, context isolation,
honest provider probing."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from tests.conftest import EXTERNAL, OWNER

from app.intelligence.planner import (
    BaselinePlanner, PlanRejectedError, PlanValidator, parse_proposal,
)
from app.intelligence.providers import FakeProvider, OllamaProvider
from app.intelligence.schemas import PlanProposal
from app.intelligence.verifier import ResultVerifier


# ------------------------------------------------------------ plan schemas
def test_plan_schema_rejects_empty_tool_name():
    with pytest.raises(Exception):
        PlanProposal(steps=[{"tool_name": "", "payload": {}}])


def test_parse_proposal_rejects_non_dict_and_bad_shape():
    with pytest.raises(PlanRejectedError):
        parse_proposal("not a plan")
    with pytest.raises(PlanRejectedError):
        parse_proposal({"steps": "nope"})
    with pytest.raises(PlanRejectedError):
        parse_proposal({"steps": []})


def test_parse_proposal_accepts_valid_shape():
    proposal = parse_proposal({"steps": [{"tool_name": "core.noop", "payload": {}}],
                               "rationale": "ok"})
    assert proposal.steps[0].tool_name == "core.noop"


# -------------------------------------------------------- baseline planner
def test_baseline_health_template_decomposition():
    matched = BaselinePlanner().plan(
        "Check system health and report whether the task system is working")
    assert matched is not None
    name, proposal = matched
    assert name == "system_health_check"
    assert [s.tool_name for s in proposal.steps] == ["core.health_snapshot", "core.echo_check"]
    assert proposal.steps[1].expectation.fields == {"echo.message": "task system self-test"}


def test_baseline_wait_template_parses_duration():
    matched = BaselinePlanner().plan("Please wait 2 seconds and then report back")
    assert matched is not None
    name, proposal = matched
    assert name == "wait_and_report"
    assert proposal.steps[0].tool_name == "core.wait"
    assert proposal.steps[0].payload == {"milliseconds": 2000}
    assert proposal.steps[0].expectation.fields == {"waited_ms": 2000}
    assert proposal.steps[1].payload["message"] == "wait complete"


def test_baseline_echo_template_and_no_match():
    planner = BaselinePlanner()
    matched = planner.plan("Echo: the depot is clear")
    assert matched is not None and matched[0] == "echo_message"
    assert matched[1].steps[0].payload["message"] == "the depot is clear"
    assert planner.plan("Investigate quarterly market trends for umbrellas") is None
    assert planner.match_name("Investigate quarterly market trends") is None


# -------------------------------------------------------------- validation
async def test_validator_rejects_unregistered_tool(application):
    validator = PlanValidator(application.intelligence.tools, application.permissions)
    proposal = parse_proposal({"steps": [{"tool_name": "os.system",
                                          "payload": {"command": "calc"}}]})
    with pytest.raises(PlanRejectedError) as exc:
        validator.validate(proposal, OWNER)
    assert "unregistered tool" in str(exc.value)


async def test_validator_rejects_invalid_payload(application):
    validator = PlanValidator(application.intelligence.tools, application.permissions)
    proposal = parse_proposal({"steps": [{"tool_name": "core.echo_check",
                                          "payload": {"data": {}}}]})  # message missing
    with pytest.raises(PlanRejectedError):
        validator.validate(proposal, OWNER)


async def test_validator_rejects_when_permission_denied(application):
    validator = PlanValidator(application.intelligence.tools, application.permissions)
    proposal = parse_proposal({"steps": [{"tool_name": "core.noop", "payload": {}}]})
    with pytest.raises(PlanRejectedError) as exc:
        validator.validate(proposal, EXTERNAL)  # EXTERNAL role has no permissions
    assert "denied at plan time" in str(exc.value)


async def test_validator_accepts_baseline_health_plan(application):
    validator = PlanValidator(application.intelligence.tools, application.permissions)
    _, proposal = BaselinePlanner().plan("Check system health and report")
    validated = validator.validate(proposal, OWNER)
    assert [s.tool_name for s in validated] == ["core.health_snapshot", "core.echo_check"]


# ---------------------------------------------------------------- verifier
def _task(status="completed", result=None, error=None):
    return SimpleNamespace(status=status, result=result, error=error)


def test_verifier_matrix():
    verifier = ResultVerifier()
    assert verifier.verify(
        {"require_ok": True, "fields": {"waited_ms": 250}},
        _task(result={"ok": True, "waited_ms": 250}))[0] == "verified"
    assert verifier.verify(
        {"require_ok": True, "fields": {"waited_ms": 500}},
        _task(result={"ok": True, "waited_ms": 250}))[0] == "failed"
    assert verifier.verify(
        {"require_ok": True, "fields": {}},
        _task(result={"ok": False}))[0] == "failed"
    assert verifier.verify(
        {"require_ok": True, "fields": {}},
        _task(status="failed", error={"kind": "timeout"}))[0] == "failed"
    # field absent from result -> cannot confirm -> UNVERIFIED, never verified
    assert verifier.verify(
        {"require_ok": True, "fields": {"not_in_result": 1}},
        _task(result={"ok": True}))[0] == "unverified"
    # no machine-checkable expectation -> UNVERIFIED
    assert verifier.verify(
        {"kind": "none"}, _task(result={"ok": True}))[0] == "unverified"
    # dotted path lookup
    assert verifier.verify(
        {"require_ok": True, "fields": {"echo.message": "hi"}},
        _task(result={"ok": True, "echo": {"message": "hi"}}))[0] == "verified"


# ------------------------------------------------------------------ router
async def test_router_defaults_to_baseline_without_profiles(application):
    decision = await application.intelligence._router.select("planning")
    assert decision.kind == "baseline"
    assert any("no enabled model profile" in r for r in decision.reasons)


async def test_router_selects_available_fake_profile(application):
    intel = application.intelligence
    intel.providers["fake"] = FakeProvider(raw_output={"steps": []})
    intel.upsert_profile(OWNER, "fake-std", {
        "task_classes": ["planning"], "provider": "fake",
        "model_id": "fake-1", "enabled": True, "limits": {"size_rank": 1}})
    decision = await intel._router.select("planning")
    assert decision.kind == "llm"
    assert decision.profile_name == "fake-std"
    assert decision.model_id == "fake-1"


async def test_router_never_selects_cloud_stub(application):
    intel = application.intelligence
    intel.upsert_profile(OWNER, "cloud-std", {
        "task_classes": ["planning"], "provider": "cloud",
        "model_id": "cloud-1", "enabled": True, "limits": {"size_rank": 1}})
    decision = await intel._router.select("planning")
    assert decision.kind == "baseline"  # cloud disabled by default -> stub unavailable
    assert any("cloud" in r for r in decision.reasons)


async def test_router_skips_unavailable_provider(application):
    intel = application.intelligence
    intel.providers["fake"] = FakeProvider(available=False)
    intel.upsert_profile(OWNER, "fake-off", {
        "task_classes": ["planning"], "provider": "fake",
        "model_id": "fake-1", "enabled": True, "limits": {"size_rank": 1}})
    decision = await intel._router.select("planning")
    assert decision.kind == "baseline"


async def test_router_defers_headroom_profile_under_resource_pressure(application):
    intel = application.intelligence
    intel.providers["fake"] = FakeProvider(raw_output={"steps": []})
    intel.upsert_profile(OWNER, "fake-big", {
        "task_classes": ["planning"], "provider": "fake", "model_id": "fake-1",
        "enabled": True, "limits": {"size_rank": 1, "requires_headroom": True}})
    application.monitor.threshold_violations = lambda: [
        {"resource": "memory", "value": 99.0, "threshold": 90.0}]
    decision = await intel._router.select("planning")
    assert decision.kind == "baseline"
    assert any("resource pressure" in r for r in decision.reasons)


# ------------------------------------------------- recorder / context / misc
async def test_decision_recorder_and_context_isolation(application):
    intel = application.intelligence
    m1 = await intel.create_mission(OWNER, "Check system health and report")
    m2 = await intel.create_mission(OWNER, "Echo: second mission")
    intel.recorder.record("plan_created", actor="rule-engine", reason="ctx test",
                          mission_id=m1.id)
    ctx1 = intel.context.build_context(m1.id)
    ctx2 = intel.context.build_context(m2.id)
    assert ctx1["mission"]["id"] == m1.id
    assert any(d["type"] == "plan_created" for d in ctx1["decisions"])
    assert not any(d["type"] == "plan_created" for d in ctx2["decisions"])
    assert all(d["reason"] != "ctx test" for d in ctx2["decisions"])


async def test_ollama_probe_is_honest_when_server_absent():
    provider = OllamaProvider("http://127.0.0.1:1", timeout_seconds=0.5)
    available, detail = await provider.probe()
    assert available is False
    assert "unavailable" in detail


async def test_seeded_profiles_have_no_invented_model(application):
    profiles = application.intelligence.list_profiles()
    assert len(profiles) == 4
    assert all(p.model_id == "" and p.enabled is False for p in profiles)
