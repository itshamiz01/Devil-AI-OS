"""P-12 unit tests: the pure modules (planner, state machine,
autonomy resolution, decision engine, scheduling, recovery,
verification) plus schema-level invariants."""
from __future__ import annotations

import datetime as dt

import pytest

from app.core.exceptions import InvalidStateTransitionError, ValidationError
from app.operations import (
    autonomy as autonomy_mod, decisions, planner, recovery, scheduling,
    verification,
)
from app.operations.state_machine import (
    validate_task_transition, validate_workflow_transition,
)

NOW = dt.datetime(2026, 11, 9, 12, 0, tzinfo=dt.timezone.utc)


# ---------------------------------------------------------------- planner
def test_planner_accepts_valid_dag():
    steps = planner.validate_definition({"steps": [
        {"step_key": "a", "kind": "task_handler", "action_class": "read",
         "substrate": {"handler": "core.noop", "payload": {}}},
        {"step_key": "b", "kind": "internal", "action_class": "draft.create",
         "substrate": {"runner": "record_note"}, "depends_on": ["a"]},
    ]})
    assert [s["step_key"] for s in steps] == ["a", "b"]


def test_planner_rejects_cycle():
    with pytest.raises(ValidationError):
        planner.validate_definition({"steps": [
            {"step_key": "a", "kind": "internal",
             "substrate": {"runner": "record_note"}, "depends_on": ["b"]},
            {"step_key": "b", "kind": "internal",
             "substrate": {"runner": "record_note"}, "depends_on": ["a"]},
        ]})


def test_planner_rejects_unknown_dependency_and_duplicate_keys():
    with pytest.raises(ValidationError):
        planner.validate_definition({"steps": [
            {"step_key": "a", "kind": "internal",
             "substrate": {"runner": "record_note"}, "depends_on": ["zzz"]},
        ]})
    with pytest.raises(ValidationError):
        planner.validate_definition({"steps": [
            {"step_key": "a", "kind": "internal",
             "substrate": {"runner": "record_note"}},
            {"step_key": "a", "kind": "internal",
             "substrate": {"runner": "record_note"}},
        ]})


def test_planner_rejects_code_payloads_and_unclassified_actions():
    with pytest.raises(ValidationError):
        planner.validate_definition({"steps": [
            {"step_key": "a", "kind": "task_handler",
             "substrate": {"handler": "core.echo_check",
                           "payload": {"code": "print(1)"}}},
        ]})
    with pytest.raises(ValidationError):
        planner.validate_definition({"steps": [
            {"step_key": "a", "kind": "task_handler",
             "action_class": "shell.exec",
             "substrate": {"handler": "core.noop", "payload": {}}},
        ]})


def test_definition_hash_is_stable_and_sensitive():
    a = planner.definition_hash({"steps": [1, 2]})
    b = planner.definition_hash({"steps": [1, 2]})
    c = planner.definition_hash({"steps": [1, 3]})
    assert a == b and a != c and len(a) == 64


# ---------------------------------------------------------------- state machine
def test_workflow_state_machine():
    validate_workflow_transition("DRAFT", "VALIDATING")
    validate_workflow_transition("RUNNING", "VERIFYING")
    validate_workflow_transition("VERIFYING", "COMPLETED")
    with pytest.raises(InvalidStateTransitionError):
        validate_workflow_transition("DRAFT", "COMPLETED")
    with pytest.raises(InvalidStateTransitionError):
        validate_workflow_transition("COMPLETED", "RUNNING")
    with pytest.raises(InvalidStateTransitionError):
        validate_workflow_transition("ARCHIVED", "DRAFT")


def test_task_state_machine():
    validate_task_transition("PENDING", "RUNNING")
    validate_task_transition("RUNNING", "VERIFYING")
    validate_task_transition("VERIFYING", "COMPLETED")
    validate_task_transition("FAILED", "DEAD_LETTER")
    with pytest.raises(InvalidStateTransitionError):
        validate_task_transition("COMPLETED", "RUNNING")
    with pytest.raises(InvalidStateTransitionError):
        validate_task_transition("DEAD_LETTER", "READY")


# ---------------------------------------------------------------- autonomy
def _resolve(policies, **kw):
    base = dict(business_id=None, agent_id=None, workflow_id=None,
                workflow_declared_level=1, action_class="business.read",
                default_level=1, constitution_mode="controlled",
                security_mode="normal", declared_by_owner=False)
    base.update(kw)
    return autonomy_mod.resolve_autonomy(policies, **base)


def test_autonomy_minimum_of_ceilings():
    policies = [
        {"scope_type": "global", "scope_ref": "", "agent_ref": None,
         "level": 3, "action_caps": {}},
        {"scope_type": "business", "scope_ref": "biz-a", "agent_ref": None,
         "level": 2, "action_caps": {}},
    ]
    out = _resolve(policies, business_id="biz-a",
                   workflow_declared_level=3, declared_by_owner=True)
    assert out["effective_level"] == 2
    assert "business_policy" in out["binding_constraints"]


def test_autonomy_business_scope_never_leaks():
    """The named §4 invariant: a Level 3 row for Business A is not
    even a candidate when resolving for Business B."""
    policies = [
        {"scope_type": "business", "scope_ref": "biz-a", "agent_ref": None,
         "level": 3, "action_caps": {}},
    ]
    in_a = _resolve(policies, business_id="biz-a",
                    workflow_declared_level=3, declared_by_owner=True,
                    action_class="content.publish")
    in_b = _resolve(policies, business_id="biz-b",
                    workflow_declared_level=3, declared_by_owner=True,
                    action_class="content.publish")
    assert in_a["effective_level"] == 3 and in_a["may_execute"]
    assert in_b["effective_level"] == 3  # declared ceiling only...
    # ...but the business A row is absent from B's trace entirely.
    assert "business_policy" not in in_b["ceilings"]
    assert in_a["ceilings"].get("business_policy") == 3


def test_autonomy_agent_declaration_capped_by_default():
    out = _resolve([], workflow_declared_level=4, declared_by_owner=False,
                   action_class="filesystem.write")
    assert out["effective_level"] == 1  # seeded default caps agents
    assert out["approval_required"] is True


def test_autonomy_owner_declaration_governs_own_workflow():
    out = _resolve([], workflow_declared_level=2, declared_by_owner=True,
                   action_class="filesystem.write")
    assert out["effective_level"] == 2
    assert out["may_execute"] is True


def test_autonomy_risk3_and_financial_always_need_approval():
    out = _resolve([], workflow_declared_level=4, declared_by_owner=True,
                   action_class="financial.transfer")
    assert out["approval_required"] is True and out["may_execute"] is False


def test_autonomy_mode_caps():
    sim = _resolve([], workflow_declared_level=3, declared_by_owner=True,
                   constitution_mode="simulation",
                   action_class="filesystem.write")
    assert sim["effective_level"] == 1 and sim["may_execute"] is False
    stopped = _resolve([], workflow_declared_level=3,
                       declared_by_owner=True, security_mode="emergency_stop",
                       action_class="business.read")
    assert stopped["may_execute"] is False
    safe = _resolve([], workflow_declared_level=3, declared_by_owner=True,
                    security_mode="safe_mode", action_class="business.read")
    assert safe["may_execute"] is True  # observation survives safe mode


def test_autonomy_action_category_cap():
    policies = [
        {"scope_type": "business", "scope_ref": "biz-a", "agent_ref": None,
         "level": 3, "action_caps": {"content.publish": 1}},
    ]
    out = _resolve(policies, business_id="biz-a",
                   workflow_declared_level=3, declared_by_owner=True,
                   action_class="content.publish")
    assert out["effective_level"] == 1
    assert out["approval_required"] is True


# ---------------------------------------------------------------- decisions
def test_decision_budget_block_rejects():
    out = decisions.decide_step({"budget": {"status": "exceeded"},
                                 "autonomy": {"may_execute": True,
                                              "approval_required": False,
                                              "effective_level": 3}})
    assert out["category"] == "REJECT"


def test_decision_emergency_pauses_before_money():
    out = decisions.decide_step({"security_mode": "emergency_stop",
                                 "budget": {"status": "exceeded"},
                                 "autonomy": {}})
    assert out["category"] == "PAUSE"


def test_decision_held_budget_requests_approval():
    out = decisions.decide_step({"budget": {"status": "held"},
                                 "autonomy": {"may_execute": True,
                                              "approval_required": False}})
    assert out["category"] == "REQUEST_APPROVAL"


def test_decision_clean_context_executes():
    out = decisions.decide_step({
        "budget": {"status": "ok", "utilisation_pct": 10},
        "autonomy": {"may_execute": True, "approval_required": False,
                     "effective_level": 2}})
    assert out["category"] == "EXECUTE"


def test_decision_high_utilisation_limits():
    out = decisions.decide_step({
        "budget": {"status": "ok", "utilisation_pct": 90},
        "autonomy": {"may_execute": True, "approval_required": False,
                     "effective_level": 2}})
    assert out["category"] == "EXECUTE_WITH_LIMITS"
    assert out["limits"]["max_concurrent_tasks"] == 1


def test_decision_missing_inputs_and_unhealthy_agent():
    out = decisions.decide_step({"inputs_complete": False,
                                 "autonomy": {"may_execute": True,
                                              "approval_required": False}})
    assert out["category"] == "RESEARCH_MORE"
    out = decisions.decide_step({"agent_required": True,
                                 "agent_available": True,
                                 "agent_healthy": False,
                                 "autonomy": {"may_execute": True,
                                              "approval_required": False}})
    assert out["category"] == "ESCALATE"
    out = decisions.decide_step({"business_paused": True,
                                 "autonomy": {"may_execute": True,
                                              "approval_required": False}})
    assert out["category"] == "PAUSE"


# ---------------------------------------------------------------- scheduling
def test_schedule_once_and_interval():
    once = {"kind": "once", "at": "2026-11-10T09:00:00+00:00"}
    assert scheduling.next_fire(once, NOW, None) == dt.datetime(
        2026, 11, 10, 9, 0, tzinfo=dt.timezone.utc)
    assert scheduling.next_fire(once, NOW, NOW) is None  # already fired
    interval = {"kind": "interval", "every_seconds": 3600,
                "start_at": "2026-11-09T10:00:00+00:00"}
    nxt = scheduling.next_fire(interval, NOW, None)
    assert nxt == dt.datetime(2026, 11, 9, 13, 0, tzinfo=dt.timezone.utc)


def test_schedule_daily_timezone():
    daily = {"kind": "daily", "time": "09:30", "timezone": "Asia/Kolkata"}
    nxt = scheduling.next_fire(daily, NOW, None)  # NOW = 12:00 UTC = 17:30 IST
    assert nxt == dt.datetime(2026, 11, 10, 4, 0, tzinfo=dt.timezone.utc)


def test_schedule_missed_runs_counted_once():
    interval = {"kind": "interval", "every_seconds": 600}
    stored = NOW - dt.timedelta(seconds=2000)
    instant, missed = scheduling.pending_instant(interval, NOW, None, stored)
    assert instant == stored and missed == 3
    assert scheduling.fire_key("t1", instant) == scheduling.fire_key(
        "t1", instant)


def test_schedule_validation():
    with pytest.raises(ValidationError):
        scheduling.validate_schedule({"kind": "interval", "every_seconds": 5})
    with pytest.raises(ValidationError):
        scheduling.validate_schedule({"kind": "daily", "time": "25:99"})
    with pytest.raises(ValidationError):
        scheduling.validate_schedule({"kind": "yearly"})


# ---------------------------------------------------------------- recovery
def test_failure_classification():
    assert recovery.classify_failure(permission_denied=True) == \
        "permission_failure"
    assert recovery.classify_failure(budget_status="exceeded") == \
        "budget_failure"
    assert recovery.classify_failure(
        error={"message": "rate limit exceeded"}) == "rate_limit"
    assert recovery.classify_failure(
        error={"message": "connection timeout"}) == \
        "temporary_network_failure"
    assert recovery.classify_failure(
        verification_status="failed") == "invalid_output"
    assert recovery.classify_failure(substrate_status="failed") == \
        "tool_failure"
    assert recovery.classify_failure() == "unknown_failure"


def test_retry_eligibility_rules():
    assert recovery.retry_eligible("rate_limit", 1, 3)
    assert recovery.retry_eligible("tool_failure", 3, 3)
    assert not recovery.retry_eligible("tool_failure", 4, 3)
    assert not recovery.retry_eligible("permission_failure", 1, 3)
    assert not recovery.retry_eligible("budget_failure", 1, 3)
    assert not recovery.retry_eligible("policy_violation", 1, 3)
    assert not recovery.retry_eligible("unknown_failure", 1, 3)
    assert not recovery.retry_eligible("invalid_output", 1, 3)


def test_retry_backoff_grows_and_is_capped():
    import random
    rng = random.Random(42)
    d1 = recovery.retry_delay(1, base=1.0, cap=60.0, rng=rng)
    d5 = recovery.retry_delay(5, base=1.0, cap=60.0, rng=rng)
    assert 1.0 <= d1 <= 2.6 and d5 >= d1


def test_circuit_breaker_opens_and_half_opens():
    breaker = recovery.CircuitBreaker("tool:x", threshold=2,
                                      cooldown_seconds=10)
    assert breaker.allow(now=100.0)
    breaker.record_failure(now=100.0)
    assert breaker.allow(now=101.0)
    assert breaker.record_failure(now=101.0) == "opened"
    assert not breaker.allow(now=105.0)
    assert breaker.allow(now=111.0)  # half-open probe after cooldown
    assert breaker.record_success() == "closed"
    assert breaker.allow(now=112.0)


# ---------------------------------------------------------------- verification
def test_verification_vocabulary():
    ok = verification.evaluate({"task_status": "completed"},
                               substrate_status="completed",
                               result={"ok": True})
    assert ok["status"] == "verified"
    bad = verification.evaluate({"result_has": ["report"]},
                                substrate_status="completed", result={})
    assert bad["status"] == "failed"
    unknown = verification.evaluate({}, substrate_status="running",
                                    result={})
    assert unknown["status"] == "unverified"  # never promoted to success
    bare = verification.evaluate({}, substrate_status="completed",
                                 result={})
    assert bare["status"] == "verified"
    eq = verification.evaluate({"result_equals": {"ok": True}},
                               substrate_status="completed",
                               result={"ok": False})
    assert eq["status"] == "failed"
