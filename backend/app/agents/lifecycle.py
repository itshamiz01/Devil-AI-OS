"""Agent lifecycle state machine (P-04 §11).

States are stored lowercase in ``agents.status`` (P-01 column convention);
the §11 names are the uppercase forms. The graph below is the FINAL
transition graph (documented in docs/architecture/AGENT_LIFECYCLE.md).
Anything not listed is invalid and rejected — transitions are validated in
code, never inferred from prompts or model output.

Legacy bridge: P-01 registry rows carry status ``created``, which is not
a §11 state. ``created`` may move only to ``initializing`` (adoption by
the factory) or ``retiring`` (retire an unmanaged registration). This is
the smallest safe bridge: it rewrites no historical rows.
"""
from __future__ import annotations

import enum


class AgentState(str, enum.Enum):
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    DEGRADED = "degraded"
    SUSPENDED = "suspended"
    FAILED = "failed"
    RETIRING = "retiring"
    RETIRED = "retired"


TRANSITIONS: dict[str, set[str]] = {
    "proposed": {"pending_approval", "initializing", "retiring"},
    "pending_approval": {"initializing", "retiring"},
    "initializing": {"active", "failed", "retiring"},
    "active": {"busy", "idle", "degraded", "suspended", "retiring"},
    "busy": {"active", "idle", "degraded", "suspended", "failed", "retiring"},
    "idle": {"active", "busy", "suspended", "retiring"},
    "degraded": {"active", "suspended", "failed", "retiring"},
    "suspended": {"active", "retiring"},
    "failed": {"initializing", "retiring"},
    "retiring": {"retired"},
    "retired": set(),
    # Legacy P-01 bridge (see module docstring).
    "created": {"initializing", "retiring"},
}

# States in which an agent may receive new assignments (§9.2 rules 1/4),
# subject to its concurrency budget.
ASSIGNABLE_STATES = {"active", "idle", "busy"}

# States counted against max_active_agents.
ACTIVE_STATES = {"initializing", "active", "idle", "busy", "degraded"}

# Terminal for creation/assignment purposes.
TERMINAL_STATES = {"retired"}


def validate_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())
