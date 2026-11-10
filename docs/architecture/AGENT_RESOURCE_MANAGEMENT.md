# Agent Resource Management (§10)

Implemented in `backend/app/agents/resources.py`. Sized for the
owner's verified hardware (Intel i7-4712HQ, 16 GB RAM, Quadro K1100M
2 GB — **GPU inference impossible**, CUDA CC 3.0 < Ollama's 5.0
minimum; see `docs/reports/AI_HARDWARE_FEASIBILITY.md`): one shared
CPU inference path, tight concurrency, honest metrics.

## Shared infrastructure (§10.1/§10.2)

- Agents are logical configurations. There is exactly **one** P-02
  `ModelRouter` instance; the factory binds it by reference
  (`router_bindings == 1`, asserted by test, object identity asserted
  against `application.intelligence._router`).
- `run_shared_inference` gates concurrent selections with
  `max_concurrent_inference_requests` (factory default **1** for this
  hardware); excess callers get `RESOURCE_LIMIT_EXCEEDED` — they are
  never silently queued onto a second model instance, because none
  exists.

## Per-agent budgets

From the pinned template's `resource_budget`, clamped by factory
ceilings (the stricter value wins): `max_concurrent_tasks`,
`max_task_seconds`, `max_retries`, `max_inference_requests_per_task`,
`max_child_agents`, `max_queue_occupancy`, `memory_budget_mb`.
Enforced at assignment (concurrency/queue), at creation (approval
determination for resource-intensive budgets) and in scaling.

## Pressure + backpressure ladder (§10.4)

Pressure derives from the P-01 `SystemMonitor` threshold violations
plus task-queue saturation: level 0 (none), 1 (one class), 2 (multiple
classes / near-full queue). Ladder actions, in order: stop
nonessential creation → queue low-priority assignments → reduce
effective concurrency → suspend eligible idle agents → report to
owner. Essential work is never blocked by the ladder.

**Blocking follows the P-01 operational switch**
(`Settings.block_nonessential_on_threshold`, the same switch
`SystemMonitor.admission_block_reason` honours for task admission:
enabled in production configuration, disabled in the test harness).
Pressure is always *reported* (`GET /agent-factory/resources` includes
level, violations, host snapshot and `blocking_enabled`) regardless of
the switch — the factory never hides real pressure; it only follows
the owner's configured admission policy about acting on it. This
parity with P-01 was a deliberate build decision after the sandbox VM's
genuine memory pressure (>90%) queued every creation in early P-04
test runs.

## Metrics honesty (§12)

Every metric carries a mandatory `measurement_type`:
`tasks_assigned/completed/failed` and latency aggregates are
**measured** from assignment/task records; `inference_requests` are
**estimated** (router selections counted, tokens unknown);
`accuracy_percent`, `token_usage`, `memory_mb` (per-agent attribution)
and `human_acceptance_rate` are **unavailable** with a stated basis —
the factory never invents an accuracy percentage or a token count.
