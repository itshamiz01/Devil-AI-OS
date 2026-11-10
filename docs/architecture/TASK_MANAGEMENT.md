# Task Management (P-01 §7) — as implemented

## Model

The durable `tasks` table is the queue. Fields per §7.2: UUID, name, description, category, handler name, validated payload (JSON), priority (0–100), status, creator principal, optional assigned agent, timestamps (UTC), deadline, retry count/max, timeout, progress/result/error (JSON), cancellation flag, approval requirement, essential flag, approval link, unique idempotency key, next-attempt time. Every attempt writes a `task_executions` row (attempt number, status, duration, result/error).

## State machine

`created → validating → queued → running → completed`, with `failed / cancelled / paused / waiting_for_approval / retry_pending`. Transitions are whitelisted (`tasks/models.TRANSITIONS`) and enforced in `TaskManager.transition` — e.g. completed→running, cancelled→completed and failed→completed all raise `InvalidStateTransitionError` (409). `running → paused` exists solely for startup recovery.

## Execution — governed handlers only (Rule 4)

Tasks execute **only** through `HandlerRegistry` names. Payloads can never carry code, commands or callables; unknown handlers and schema-invalid payloads are rejected at submission (422). Built-ins: `core.noop`, `core.echo_check` (typed echo), `core.health_snapshot` (monitor resources + DB health), `core.wait` (bounded 0–10 s sleep; exists so timeout/cancellation are testable through the same governed path).

## Queue semantics

Due tasks are claimed in priority order (higher first), FIFO within equal priority, up to `max_concurrency`. Capacity counts queued+retry_pending+validating+waiting_for_approval; submission beyond `queue_capacity` fails with 429 `queue_full` (backpressure — nothing accumulates unboundedly in RAM; the DB is the queue). When resource thresholds are exceeded, nonessential submissions fail with 429 `resource_blocked`; essential tasks are still admitted.

## Retry

Exponential backoff `min(base · 2^(attempt-1), max)`. Error classification: invalid_input / permission_denied / security are **never** auto-retried; timeout / transient / unknown are retried while `retry_count < max_retries`, via `retry_pending` with `next_attempt_at`. Manual retry from FAILED resets the cycle. Owner-rejected and permission-denied work is never retried.

## Cancellation, pause, approval gating

Cancelling a queued task cancels it immediately; cancelling a running task sets `cancellation_requested` and the execution ends `cancelled` when the handler returns (handlers are bounded; cooperative cancellation is the P-01 model). Pause works from queued/retry_pending; resume re-queues. `requires_approval` tasks park in `waiting_for_approval`; the API opens a parameter-bound approval and only a verified approval releases them to queued.

## Persistence & recovery

All state is in SQLite; a restart preserves completed/failed history exactly. Recovery (see CORE_OS_ARCHITECTURE.md) marks interrupted RUNNING tasks PAUSED + `recovery_required` and never blindly re-executes them; submission idempotency keys prevent duplicate effects from client retries.
