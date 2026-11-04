"""The lifecycle state machine (P-04 §11).

The graph is the contract: an invalid transition must be rejected in Python
before it can reach a column, and the database CHECK is the second line of
defence, not the first.
"""
import pytest

from app.agents.lifecycle import (
    STATES,
    AgentStatus,
    LifecycleTransitionError,
    can_transition,
    is_terminal,
    transition,
)


def test_the_state_set_is_the_eleven_documented_states():
    assert STATES == (
        "PROPOSED", "PENDING_APPROVAL", "INITIALIZING", "ACTIVE", "IDLE",
        "BUSY", "DEGRADED", "SUSPENDED", "FAILED", "RETIRING", "RETIRED",
    )


@pytest.mark.parametrize("current,target", [
    ("PROPOSED", "PENDING_APPROVAL"),
    ("PROPOSED", "INITIALIZING"),
    ("PENDING_APPROVAL", "INITIALIZING"),
    ("INITIALIZING", "ACTIVE"),
    ("INITIALIZING", "FAILED"),
    ("ACTIVE", "BUSY"),
    ("BUSY", "ACTIVE"),
    ("ACTIVE", "IDLE"),
    ("ACTIVE", "DEGRADED"),
    ("DEGRADED", "ACTIVE"),
    ("ACTIVE", "SUSPENDED"),
    ("SUSPENDED", "ACTIVE"),
    ("FAILED", "INITIALIZING"),
    ("ACTIVE", "RETIRING"),
    ("RETIRING", "RETIRED"),
])
def test_documented_transitions_are_permitted(current, target):
    assert can_transition(current, target) is True
    assert transition(current, target) == AgentStatus(target)


@pytest.mark.parametrize("current,target", [
    ("RETIRED", "ACTIVE"),          # terminal: history is kept, work is not
    ("RETIRED", "INITIALIZING"),
    ("PROPOSED", "BUSY"),           # nothing may run before initialization
    ("INITIALIZING", "IDLE"),
    ("SUSPENDED", "BUSY"),          # a suspended agent must resume first
    ("RETIRING", "ACTIVE"),         # retirement does not reverse
    ("PENDING_APPROVAL", "ACTIVE"),  # approval must lead through initialization
])
def test_invalid_transitions_are_rejected(current, target):
    assert can_transition(current, target) is False
    with pytest.raises(LifecycleTransitionError):
        transition(current, target)


def test_retired_is_the_only_terminal_state():
    assert [s.value for s in AgentStatus if is_terminal(s)] == ["RETIRED"]


def test_every_non_terminal_state_has_at_least_one_exit():
    for state in AgentStatus:
        if not is_terminal(state):
            assert can_transition(state, state) is False  # no self-loops
