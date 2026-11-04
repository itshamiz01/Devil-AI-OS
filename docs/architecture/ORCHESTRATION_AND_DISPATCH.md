# Orchestration, Capability Registry and Dispatch (P-02 §11)

## 1. No autonomous agents

The orchestrator coordinates a validated plan to a terminal state. It does not spawn agents, hold long-lived loops, or decide on its own initiative what to do next. Autonomous agents are **P-04**; nothing here anticipates them beyond the interfaces they will need.

## 2. Capability registry (§11.2)

`CapabilityRegistry` holds `Capability` records: `capability_id`, description, `risk`, `required_permission`, whether the capability is `executable` (dispatched as a task) or in-process (resolved by code), its `task_handler`, and `available`.

`default_capabilities()` registers **7** capabilities:

| Capability | Kind | Handler |
|---|---|---|
| `task.echo` | executable | `system.echo` |
| `task.noop` | executable | `system.noop` |
| `task.wait` | executable | `system.wait` |
| `analyze.text` | in-process | — |
| `plan.generate` | in-process | — |
| `compute.deterministic` | in-process | — |
| `evaluate.decision` | in-process | — |

`REAL_HANDLERS = {system.noop, system.echo, system.wait}` — exactly the three handlers P-01 registers (ADR-0011). `register()` **refuses** any capability naming a handler outside that set, so the engine cannot advertise a capability without a working implementation. `UnknownCapabilityError` is raised for lookups of an unregistered id.

In-process capabilities are resolved by deterministic code and never queued: they consume no worker slot and create no task row.

## 3. Dispatch (§11.3) — only through P-01

`TaskDispatcher.dispatch(step, mission=..., plan=..., principal_id=..., correlation_id=..., db=...)` builds a `TaskSubmitRequest` and calls `TaskManager.submit`. That is the same entry point an owner uses, so the same permission checks, the same approval gate and the same idempotency handling apply. The intelligence layer has no other way to cause work to happen.

`DispatchPolicy` bounds what the orchestrator will do:

| Field | Default | Purpose |
|---|---|---|
| `max_concurrent_per_mission` | 2 (configurable, 1–8) | One mission cannot monopolise the P-01 queue (§18) |
| `default_priority` | 5 | Intelligence work is not privileged over owner work |
| `default_timeout_seconds` | 30.0 | Bounded step duration |
| `approval_required_at` | `HIGH` | Steps at or above this risk carry an approval gate |
| `dispatch_in_process_capabilities` | `True` | In-process work resolves without queueing |

`execute_plan` dispatches only steps whose dependencies have completed, and enforces the concurrency cap itself rather than leaving it to the queue. Only a `VALIDATED` or `ACTIVE` plan may be dispatched; a `REJECTED` plan raises `DispatchRefusedError`.

**Idempotency.** The key is `f"{plan.plan_id}:{step.step_id}"[:128]`. Re-dispatching the same plan returns the *same* task ids rather than creating new work, because the key collides with the original row. A test dispatches twice and asserts both the returned ids and the persisted task count are unchanged. This is what prevents the duplicate execution §9.3 forbids.

**Provenance.** `TaskSubmitRequest` has a fixed shape, so mission, plan, step, capability and expected output travel in `description` (bounded to 2000 characters): `mission=<id> plan=<id> v<n> step=<id> capability=<id> expected=<...>`. A dispatched task is always traceable to the reasoning that produced it.

**Payloads** are built per handler: `system.echo` gets `message`, `system.wait` gets `seconds` bounded to ≤5.0. A payload for an unknown handler is refused rather than passed through.

**Refusals are audited, not raised silently.** A step the dispatcher will not submit produces a `DispatchRecord` with `refused_reason` set and `task_id=None`, and is written to the audit log. `DispatchRefusedError` is raised only for plan-level refusals.

At `0_advisory` the dispatcher submits nothing: every record carries a refusal reason and no task id.

## 4. Progress (§11.4) — from real task states only

`ProgressMonitor.task_states(task_ids)` reads the persisted `tasks` rows. `apply_task_states(plan, states)` projects them onto steps via `_map_task_status`:

| P-01 task status | Step status |
|---|---|
| `COMPLETED` | `COMPLETED` |
| `FAILED` | `FAILED` |
| `CANCELLED` | `CANCELLED` |
| `RUNNING` | `RUNNING` |
| `QUEUED` | `DISPATCHED` |
| `RETRY_PENDING`, `CREATED`, `VALIDATING` | `PENDING` |
| `PAUSED` | `BLOCKED` |
| `WAITING_FOR_APPROVAL` | `AWAITING_APPROVAL` |
| anything else | `BLOCKED` |

The fallback is `BLOCKED`, never `COMPLETED`. An unknown status is a reason to stop, not a reason to report success.

Three rules make the projection trustworthy:

- **A missing task row is `BLOCKED`.** An absent task is not a finished one.
- **A terminal step is never re-projected.** Once `COMPLETED`, `CANCELLED` or `SKIPPED`, a later state read cannot reopen it.
- **Failure propagates.** `blocked_by_failure` marks everything transitively downstream of a failed or cancelled step as `BLOCKED`.

`progress(mission, plan)` computes `percent_complete = round(100 * completed / total, 2)` from step states alone. No model contributes to it, and no narration can inflate it. A plan with no steps, or no plan at all, sets `incomplete_data=True` rather than reporting 100%.

## 5. Failure handling (§11.5)

`completion_state(plan, mission)` decides the mission's terminal state:

| Step states | Mission state |
|---|---|
| any `FAILED` | `FAILED` |
| any `BLOCKED` (and none failed) | `BLOCKED` |
| all in {`COMPLETED`, `SKIPPED`, `CANCELLED`} with any `CANCELLED` | `CANCELLED` |
| all `COMPLETED`/`SKIPPED` | `COMPLETED` |
| no steps | `BLOCKED` |
| otherwise | `EXECUTING` |

**A failed mission can never read `COMPLETED`**, and cancelled work is not finished work. This is the guard against §11.5's central prohibition.

`assess_failure(step, plan)` returns a `FailureAssessment`: `recoverable`, `retry_permitted`, `affected_dependents`, `replan_recommended`, `reason`, and the task's recorded `error_details`.

Retry permission is decided from the **task's** recorded state and the autonomy level, never from the orchestrator's preference. P-01 already classifies which errors are retryable; `NON_RETRYABLE = {VALIDATION_ERROR, PERMISSION_DENIED, APPROVAL_REJECTED, APPROVAL_EXPIRED, APPROVAL_BINDING_MISMATCH, SECURITY_VIOLATION}`. Retrying a permission denial cannot succeed, so it is never attempted. `retry_permitted` additionally requires `autonomy.may_retry_autonomously()`, which is false at `0_advisory`.

Dependents are resolved against a projection of the plan in which *the step being assessed* has failed. Reading them from stale step states under-reported the blast radius unless the caller had refreshed first — a defect found and fixed by test.

`replan_recommended` is true when dependents are stuck and retry is not permitted. Recovery then follows `BLOCKED -> PLANNING`, the only replanning path in the state machine.

## 6. Audit

`audit_progress` writes the real numbers — percent complete, completed, failed, blocked, total steps — to the P-01 audit log under the mission id. Dispatch, refusal and failure are audited under their own event types.

## 7. Verification status

| Claim | Evidence |
|---|---|
| Dispatch through P-01, provenance, idempotency, concurrency cap | `tests/test_intelligence_orchestration.py` |
| Advisory level submits nothing | Tested at unit and API level |
| Status mapping covers every P-01 state; unknown → `BLOCKED` | Tested exhaustively |
| Missing row → `BLOCKED`; terminal steps not reopened | Tested |
| Failed mission never `COMPLETED`; cancelled ≠ completed | Tested |
| Non-retryable codes never retried (all six) | Parametrised test |
| Replanning recovery preserves versions | Tested end to end through the API |
| In-process capabilities never queued | Tested |
