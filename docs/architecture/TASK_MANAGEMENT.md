# P-01 Task Management

Implemented task states: CREATED, VALIDATING, QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED, PAUSED, WAITING_FOR_APPROVAL, RETRY_PENDING. Transitions are validated by `ALLOWED_TRANSITIONS`.

## Queue and execution

- Bounded in-memory priority queue backed by persistent task records.
- FIFO within equal priority via sequence counter.
- Configurable capacity and worker concurrency.
- Only registered safe handlers execute: `system.noop`, `system.echo`, `system.wait`.
- Handler payloads are validated with Pydantic.
- Timeout, cancellation, retry backoff and execution history are implemented.

## Recovery

On startup, RUNNING/VALIDATING tasks are marked FAILED with `INTERRUPTED` error details. QUEUED tasks are re-enqueued. Due RETRY_PENDING tasks are promoted. Idempotency keys prevent duplicate submissions with the same payload.

## Limitations

`WAITING_FOR_APPROVAL` is stored but not automatically released by approval decisions in P-01. Approval framework is independent; no external side-effect handlers exist. Manual retry is allowed only for FAILED tasks within retry limits.
