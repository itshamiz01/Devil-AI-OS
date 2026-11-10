# Agent Lifecycle (§11)

Implemented in `backend/app/agents/lifecycle.py`; every transition is
validated server-side, persisted, audited
(`agent_factory.lifecycle_transition`) and published as
`AgentStateChanged`. Invalid transitions raise
`LifecycleTransitionInvalidError` (`LIFECYCLE_TRANSITION_INVALID`) and
are audit-logged as denials.

## States

`PROPOSED`, `PENDING_APPROVAL`, `INITIALIZING`, `ACTIVE`, `IDLE`,
`BUSY`, `DEGRADED`, `SUSPENDED`, `FAILED`, `RETIRING`, `RETIRED`.

(`agent_creation_requests` carry PROPOSED/PENDING_APPROVAL semantics
before an agent row exists; the registry row is born `INITIALIZING`.)

## Transition graph (as built)

| From | Allowed to |
|---|---|
| proposed | pending_approval, initializing, retiring |
| pending_approval | initializing, retiring |
| initializing | active, failed, retiring |
| active | idle, busy, degraded, suspended, retiring |
| idle | active, busy, suspended, retiring |
| busy | active, degraded, suspended |
| degraded | active, suspended, failed, retiring |
| suspended | active, retiring |
| failed | initializing, retiring |
| retiring | retired |
| retired | — (terminal) |
| created *(P-01 legacy)* | initializing, retiring |

Assignable states (may receive work): `active`, `idle`, `busy`.
Fleet-counted "active" states: `initializing`, `active`, `idle`,
`busy`, `degraded`.

## Rules

- **Busy discipline:** configuration updates on a `BUSY` agent fail
  with `CONFIGURATION_VERSION_CONFLICT`; the assignment refresh moves
  `busy → active` when the agent's last running task settles.
- **Degraded reconciliation:** maintenance deterministically moves
  `degraded ↔ active` from measured health (failure-rate thresholds);
  `FAILED` health is only *reported* while the agent is busy/initializing
  — health never silently rewrites lifecycle outside the graph.
- **Idle suspension:** maintenance suspends agents idle longer than
  `idle_suspend_seconds` (owner-configurable) under the §10.4 ladder.
- **Retirement preserves everything:** `retire` transitions through
  `retiring → retired`, stamps `retired_at`, and deletes nothing —
  identity, configuration history, assignments, metrics and the audit
  trail remain readable (Scenario I, smoke-verified). Retired agents
  reject new assignments (rule `agent_active`) and capability requests.
- **Legacy bridge:** P-01 created registry rows with status `created`,
  which is not a §11 state. The graph admits exactly two exits from it
  (`initializing`, `retiring`) so pre-P-04 rows can be governed or
  retired without a data migration; no existing test asserted agent
  status values, and no new agent is ever created in that state.
- **Emergency stop** uses the same graph (suspend via valid
  transitions only) — it cannot force an illegal state.
