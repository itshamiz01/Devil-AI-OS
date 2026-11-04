"""The agent lifecycle state machine (P-04 §11).

The graph below is the single source of truth for permitted transitions.
The database enforces the *state set* through a CHECK constraint; this module
enforces the *edges*, so an invalid transition is rejected in Python before it
can ever reach a column, and the migration and the services cannot drift apart.

    PROPOSED ──▶ PENDING_APPROVAL ──▶ INITIALIZING ──▶ ACTIVE
       │                │                   │            │  ▲
       │                │                   ▼            ▼  │
       │                │                FAILED ◀── BUSY ─  │
       │                │                   │       │  ▲     │
       │                │                   │       ▼  │     │
       │                │                   │     DEGRADED   │
       │                │                   │       │        │
       │                ▼                   │       ▼        │
       │             RETIRED ◀── SUSPENDED ◀┴── ACTIVE/IDLE ──┘
       │                ▲            │
       └────────────────────────────┘  (abandoned proposals close as RETIRED)

RETIRING sits between any live state and RETIRED so that in-flight work can be
drained before the identity is closed. RETIRED is terminal: history is kept,
the agent simply stops receiving work.
"""
from __future__ import annotations

from enum import Enum


class AgentStatus(str, Enum):
    PROPOSED = "PROPOSED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    INITIALIZING = "INITIALIZING"
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    BUSY = "BUSY"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"
    FAILED = "FAILED"
    RETIRING = "RETIRING"
    RETIRED = "RETIRED"


#: The state set, in declaration order. The migration's CHECK constraint is
#: generated from this tuple, so adding a state here is a schema change too.
STATES: tuple[str, ...] = tuple(s.value for s in AgentStatus)

ALLOWED_TRANSITIONS: dict[AgentStatus, frozenset[AgentStatus]] = {
    AgentStatus.PROPOSED: frozenset({AgentStatus.PENDING_APPROVAL, AgentStatus.INITIALIZING, AgentStatus.RETIRED}),
    AgentStatus.PENDING_APPROVAL: frozenset({AgentStatus.INITIALIZING, AgentStatus.RETIRED}),
    AgentStatus.INITIALIZING: frozenset({AgentStatus.ACTIVE, AgentStatus.FAILED}),
    AgentStatus.ACTIVE: frozenset({AgentStatus.IDLE, AgentStatus.BUSY, AgentStatus.DEGRADED, AgentStatus.SUSPENDED, AgentStatus.FAILED, AgentStatus.RETIRING}),
    AgentStatus.IDLE: frozenset({AgentStatus.ACTIVE, AgentStatus.BUSY, AgentStatus.SUSPENDED, AgentStatus.RETIRING}),
    AgentStatus.BUSY: frozenset({AgentStatus.ACTIVE, AgentStatus.IDLE, AgentStatus.DEGRADED, AgentStatus.FAILED}),
    AgentStatus.DEGRADED: frozenset({AgentStatus.ACTIVE, AgentStatus.SUSPENDED, AgentStatus.FAILED, AgentStatus.RETIRING}),
    AgentStatus.SUSPENDED: frozenset({AgentStatus.ACTIVE, AgentStatus.RETIRED}),
    AgentStatus.FAILED: frozenset({AgentStatus.INITIALIZING, AgentStatus.RETIRED}),
    AgentStatus.RETIRING: frozenset({AgentStatus.RETIRED}),
    AgentStatus.RETIRED: frozenset(),
}


class LifecycleTransitionError(ValueError):
    """Raised when a transition is not an edge of the graph."""


def can_transition(current: AgentStatus | str, target: AgentStatus | str) -> bool:
    cur = AgentStatus(current)
    return AgentStatus(target) in ALLOWED_TRANSITIONS[cur]


def transition(current: AgentStatus | str, target: AgentStatus | str) -> AgentStatus:
    """Return the new state, or raise. Never mutate a column directly."""
    cur, nxt = AgentStatus(current), AgentStatus(target)
    if nxt not in ALLOWED_TRANSITIONS[cur]:
        raise LifecycleTransitionError(
            f"{cur.value} -> {nxt.value} is not a permitted lifecycle transition"
        )
    return nxt


def is_terminal(state: AgentStatus | str) -> bool:
    return not ALLOWED_TRANSITIONS[AgentStatus(state)]
