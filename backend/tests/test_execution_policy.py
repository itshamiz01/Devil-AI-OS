"""P-05 Stage 2: the ten policy checks of §8.1, and the risk model of §8.

These tests are about a refusal coming from the *right* check. A policy engine
that refuses everything passes a naive "unauthorized work is refused" test
while being useless, so every refusal test asserts which check refused and
that every earlier check passed - order is part of the contract, because the
checks are listed in the brief in an order and a caller acts on the first
failure.

Policy is evaluated against stand-in rows: it takes rows as inputs rather
than loading them, so these tests need no database for the checks themselves.
The capability authority, monitor and emergency controller are stubs with the
same shapes as the real services.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.core.config import Settings
from app.execution.policy import (
    POLICY_CHECKS,
    ExecutionPolicy,
    RequestFacts,
    approval_required,
    classify_risk,
    find_standing_authorization,
)
from app.execution.schemas import (
    EXECUTION_OUTCOMES,
    OUTCOME_TRANSITIONS,
    TERMINAL_OUTCOMES,
    TOOL_STATES,
    TOOL_STATE_TRANSITIONS,
)

NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
def test_the_fourteen_outcomes_are_the_briefs_list_in_the_briefs_order():
    assert EXECUTION_OUTCOMES == (
        "ACCEPTED", "VALIDATING", "AWAITING_APPROVAL", "QUEUED", "RUNNING",
        "COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED", "REJECTED",
        "CANCELLED", "TIMED_OUT", "INTERRUPTED", "REQUIRES_HUMAN_ACTION",
        "REQUIRES_RECONCILIATION",
    )


def test_every_outcome_is_reachable_and_terminal_means_terminal():
    for outcome in EXECUTION_OUTCOMES:
        assert outcome in OUTCOME_TRANSITIONS
        for target in OUTCOME_TRANSITIONS[outcome]:
            assert target in EXECUTION_OUTCOMES
    for terminal in TERMINAL_OUTCOMES:
        assert OUTCOME_TRANSITIONS[terminal] == frozenset()


def test_available_is_reachable_only_through_validating():
    """§7: a tool must not become AVAILABLE until its checks pass, so no state
    except VALIDATING may transition to it."""
    for state, targets in TOOL_STATE_TRANSITIONS.items():
        if "AVAILABLE" in targets:
            assert state in ("VALIDATING", "DEGRADED"), state
    assert set(TOOL_STATE_TRANSITIONS) == set(TOOL_STATES)


# --------------------------------------------------------------------------- #
# Risk classification (§8)
# --------------------------------------------------------------------------- #
def test_a_prohibited_action_is_risk_3_whatever_the_tool_declares():
    """A tool registered as safe cannot launder a prohibited action."""
    assert classify_risk(0, "audit.delete") == 3
    assert classify_risk(1, "mfa.bypass") == 3
    assert classify_risk(3, "files.read") == 3
    assert classify_risk(2, "files.publish") == 2
    assert classify_risk(0, "files.read") == 0


def test_approval_is_required_at_risk_2_or_when_a_tool_demands_it():
    tool = SimpleNamespace(required_approval_level=0)
    assert not approval_required(1, tool)
    assert approval_required(2, tool)
    assert approval_required(1, SimpleNamespace(required_approval_level=2))


# --------------------------------------------------------------------------- #
# Standing authorizations (§17)
# --------------------------------------------------------------------------- #
def _standing(**over):
    entry = {"id": "sa-1", "agent_id": "a-1", "tool_id": "t-1",
             "action_name": "publish", "scope": "workspace:reports",
             "max_uses": 3, "revoked": False,
             "expires_at": (NOW + timedelta(days=1)).isoformat()}
    entry.update(over)
    return {"authorizations": [entry]}


def _find(entries, **over):
    facts = {"agent_id": "a-1", "tool_id": "t-1", "action_name": "publish",
             "scope": "workspace:reports/daily", "now": NOW}
    facts.update(over)
    return find_standing_authorization(entries, **facts)


def test_standing_authorization_matches_agent_tool_action_and_scope():
    assert _find(_standing())["id"] == "sa-1"
    assert _find(_standing(), agent_id="a-2") is None
    assert _find(_standing(), action_name="delete") is None
    assert _find(_standing(), scope="workspace:other") is None


def test_standing_authorization_fails_closed_when_revoked_expired_or_malformed():
    assert _find(_standing(revoked=True)) is None
    assert _find(_standing(expires_at=(NOW - timedelta(days=1)).isoformat())) is None
    assert _find(_standing(expires_at="not-a-date")) is None
    assert _find({"authorizations": "nope"}) is None
    assert _find(None) is None
    assert _find({"authorizations": [42]}) is None


# --------------------------------------------------------------------------- #
# The ten checks
# --------------------------------------------------------------------------- #
class _Capabilities:
    def __init__(self, verdicts):
        self.verdicts = verdicts

    async def check(self, agent_id, key, *, scope=""):
        allowed, reason = self.verdicts.get(key, (True, "granted"))
        return SimpleNamespace(allowed=allowed, reason=reason)


class _Monitor:
    def __init__(self, pressure):
        self._pressure = pressure

    def resource_pressure(self):
        return self._pressure


class _Emergency:
    def __init__(self, active):
        self._active = active

    async def is_active(self):
        return self._active


def _agent(**over):
    row = SimpleNamespace(id="a-1", name="worker", principal_id="p-1", status="ACTIVE")
    for k, v in over.items():
        setattr(row, k, v)
    return row


def _tool(**over):
    row = SimpleNamespace(id="t-1", name="fs.publish", status="AVAILABLE",
                          adapter_type="filesystem", risk_level=0,
                          required_approval_level=0, supported_actions=["publish"],
                          capability_requirements=[], disabled_reason=None)
    for k, v in over.items():
        setattr(row, k, v)
    return row


def _policy(**over):
    collaborators = {"capabilities": _Capabilities({}), "monitor": _Monitor([]),
                     "emergency": _Emergency(False)}
    collaborators.update(over)
    return ExecutionPolicy(None, Settings(), **collaborators)


async def _evaluate(policy=None, **over):
    facts = {"principal_id": "p-1", "agent": _agent(),
             "task": SimpleNamespace(id="task-1", name="job"),
             "tool": _tool(),
             "facts": RequestFacts(task_id="task-1", tool_id="t-1",
                                   action_name="publish",
                                   requested_scope="workspace:reports"),
             "assignment_evidence": "the task's assignment pointer names this agent",
             "now": NOW}
    facts.update(over)
    return await (policy or _policy()).evaluate(**facts)


def _failed(evaluation):
    return [c.name for c in evaluation.checks if not c.passed]


def test_all_ten_checks_pass_in_the_briefs_order():
    import asyncio
    evaluation = asyncio.run(_evaluate())
    assert evaluation.allowed
    assert [c.name for c in evaluation.checks] == list(POLICY_CHECKS)
    assert all(c.passed for c in evaluation.checks)


def test_check_1_refuses_an_agent_not_bound_to_the_principal():
    import asyncio
    evaluation = asyncio.run(_evaluate(agent=None))
    assert _failed(evaluation) == ["agent_identity"]
    evaluation = asyncio.run(_evaluate(agent=_agent(principal_id="somebody-else")))
    assert _failed(evaluation) == ["agent_identity"]


def test_check_2_refuses_an_agent_that_cannot_accept_work():
    import asyncio
    evaluation = asyncio.run(_evaluate(agent=_agent(status="SUSPENDED")))
    assert _failed(evaluation) == ["agent_status"]


def test_check_3_refuses_work_the_agent_does_not_hold():
    import asyncio
    evaluation = asyncio.run(_evaluate(assignment_evidence=None))
    assert _failed(evaluation) == ["assigned_task"]
    evaluation = asyncio.run(_evaluate(task=None))
    assert _failed(evaluation) == ["assigned_task"]


def test_check_4_refuses_a_missing_capability_and_fails_closed_without_authority():
    import asyncio
    tool = _tool(capability_requirements=["filesystem.write"])
    policy = _policy(capabilities=_Capabilities(
        {"filesystem.write": (False, "the capability is disabled")}))
    evaluation = asyncio.run(_evaluate(policy=policy, tool=tool))
    assert _failed(evaluation) == ["required_capabilities"]
    assert "filesystem.write" in evaluation.reason

    policy = _policy(capabilities=None)
    evaluation = asyncio.run(_evaluate(policy=policy, tool=tool))
    assert _failed(evaluation) == ["required_capabilities"]
    assert "cannot be verified" in evaluation.reason


def test_check_5_refuses_an_unrestricted_or_missing_scope():
    import asyncio
    facts = RequestFacts(task_id="task-1", tool_id="t-1", action_name="publish",
                         requested_scope="*")
    evaluation = asyncio.run(_evaluate(facts=facts))
    assert _failed(evaluation) == ["requested_scope"]

    facts = RequestFacts(task_id="task-1", tool_id="t-1", action_name="publish",
                         requested_scope="")
    evaluation = asyncio.run(_evaluate(facts=facts, tool=_tool(risk_level=1)))
    assert _failed(evaluation) == ["requested_scope"]


def test_check_6_refuses_tools_that_cannot_be_routed():
    import asyncio
    evaluation = asyncio.run(_evaluate(tool=_tool(status="DISABLED",
                                                  disabled_reason="validation failed")))
    assert _failed(evaluation) == ["tool_status"]
    assert "validation failed" in evaluation.reason

    evaluation = asyncio.run(_evaluate(tool=_tool(adapter_type="browser")))
    assert _failed(evaluation) == ["tool_status"]
    assert "unsupported" in evaluation.reason

    evaluation = asyncio.run(_evaluate(tool=_tool(supported_actions=["read"])))
    assert _failed(evaluation) == ["tool_status"]
    assert "does not support" in evaluation.reason


def test_check_7_refuses_a_prohibited_action_with_no_approval_path():
    import asyncio
    tool = _tool(risk_level=0, supported_actions=["audit.delete"])
    facts = RequestFacts(task_id="task-1", tool_id="t-1", action_name="audit.delete",
                         requested_scope="workspace:reports")
    evaluation = asyncio.run(_evaluate(tool=tool, facts=facts))
    assert _failed(evaluation) == ["risk_category"]
    assert evaluation.risk == 3
    assert not evaluation.requires_approval  # prohibited is not "awaiting approval"
    assert "no approval can authorize" in evaluation.reason


def test_check_8_holds_risk_2_for_approval_and_honours_a_standing_authorization():
    import asyncio
    tool = _tool(risk_level=2, required_approval_level=2)
    evaluation = asyncio.run(_evaluate(tool=tool))
    assert not evaluation.allowed and evaluation.requires_approval
    assert _failed(evaluation) == []  # held, not refused: no check failed

    evaluation = asyncio.run(_evaluate(
        tool=tool, standing_entries=_standing(), standing_uses={"sa-1": 1}))
    assert evaluation.allowed
    assert evaluation.standing_authorization_id == "sa-1"

    evaluation = asyncio.run(_evaluate(
        tool=tool, standing_entries=_standing(), standing_uses={"sa-1": 3}))
    assert not evaluation.allowed and evaluation.requires_approval
    assert "limit is 3" in evaluation.reason


def test_check_8_refuses_an_expired_or_mismatched_approval():
    import asyncio
    tool = _tool(risk_level=2, required_approval_level=2)
    facts = RequestFacts(task_id="task-1", tool_id="t-1", action_name="publish",
                         requested_scope="workspace:reports", request_id="req-1")
    expired = SimpleNamespace(id="ap-1", status="approved",
                              expires_at=NOW - timedelta(minutes=1))
    evaluation = asyncio.run(_evaluate(tool=tool, facts=facts, approval=expired))
    assert _failed(evaluation) == ["approval_status"]
    assert "expired" in evaluation.reason

    rejected = SimpleNamespace(id="ap-1", status="rejected",
                               expires_at=NOW + timedelta(hours=1))
    evaluation = asyncio.run(_evaluate(tool=tool, facts=facts, approval=rejected))
    assert _failed(evaluation) == ["approval_status"]


def test_check_9_queues_only_essential_work_under_resource_pressure():
    import asyncio
    policy = _policy(monitor=_Monitor(["memory"]))
    evaluation = asyncio.run(_evaluate(policy=policy))
    assert _failed(evaluation) == ["resource_limits"]

    facts = RequestFacts(task_id="task-1", tool_id="t-1", action_name="publish",
                         requested_scope="workspace:reports", priority=10)
    evaluation = asyncio.run(_evaluate(policy=policy, facts=facts))
    assert evaluation.allowed


def test_check_10_refuses_during_an_emergency_and_behind_the_external_gate():
    import asyncio
    policy = _policy(emergency=_Emergency(True))
    evaluation = asyncio.run(_evaluate(policy=policy))
    assert _failed(evaluation) == ["policy_restrictions"]
    assert "emergency stop" in evaluation.reason

    # The api adapter's effects leave the machine; external execution is
    # locked off in this build, so policy refuses rather than an adapter
    # discovering it later.
    tool = _tool(adapter_type="api", risk_level=1)
    evaluation = asyncio.run(_evaluate(tool=tool))
    assert _failed(evaluation) == ["policy_restrictions"]
    assert "external execution is disabled" in evaluation.reason


def test_priority_never_lowers_a_classification():
    """§8: a high-priority task must never override risk classification."""
    import asyncio
    tool = _tool(risk_level=2, required_approval_level=2)
    facts = RequestFacts(task_id="task-1", tool_id="t-1", action_name="publish",
                         requested_scope="workspace:reports", priority=10)
    evaluation = asyncio.run(_evaluate(tool=tool, facts=facts))
    assert evaluation.risk == 2 and evaluation.requires_approval
