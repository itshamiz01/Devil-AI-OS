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

On startup, RUNNING/VALIDATING tasks are marked FAILED with `INTERRUPTED` error details. QUEUED tasks are re-enqueued. Due RETRY_PENDING tasks are promoted. Approval-gated tasks are reconciled against their approval record. Idempotency keys prevent duplicate submissions with the same payload.

## Approval gating

A task submitted with `approval_required=true` is gated instead of queued:

- The task and its approval are created in **one transaction**, so a task in
  `WAITING_FOR_APPROVAL` always has a decisionable approval. Its `resource` is
  the task id and its `action` is `task.execute`.
- The approval is bound to a canonical hash of the task's handler, name and
  payload. A gate whose hash no longer matches the task never releases it.
- Risk is `medium`, deliberately below the `high`/`critical` band that blocks
  self-approval: in P-01 the owner is both submitter and the only holder of
  `approvals.decide`, so a higher band would make every gate undecidable.
  Raising it requires a second approver principal to exist first.
- `ApprovalGranted` releases the task to `QUEUED`; `ApprovalRejected` cancels it.
  Both are also applied by a periodic sweep and at startup, so a decision is
  honoured even if its event was lost or made while the process was down.
- Gates that are expired, missing or no longer matching close the task with
  `APPROVAL_EXPIRED`, `APPROVAL_MISSING` or `APPROVAL_BINDING_MISMATCH` in
  `error_details`. The TTL is `AUTONOMUS_TASK_APPROVAL_TTL_SECONDS`.
- A closed gate always ends in `CANCELLED`, never `FAILED`: `FAILED -> QUEUED`
  is a legal transition, so a rejected or expired gate must not be retryable
  into execution without a fresh approval.

Approvals still do not authorize external side effects; no external execution
handler exists in P-01.

## Limitations

Manual retry is allowed only for FAILED tasks within retry limits. A cancelled
gate cannot be retried; resubmit the task to obtain a new approval. If the owner
cancels a gated task directly, its approval is left to expire by TTL rather than
being withdrawn; a later decision on it is a safe no-op.
