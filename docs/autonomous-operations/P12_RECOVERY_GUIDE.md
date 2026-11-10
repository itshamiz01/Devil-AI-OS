# P-12 Recovery Guide

How autonomous work survives failure in this build — and what the
owner does when it cannot.

## Failure classification

Every step failure is classified before any recovery action
(`app/operations/recovery.py`): `validation_failure`,
`permission_failure`, `policy_violation`, `agent_unavailable`,
`tool_failure`, `external_service_unavailable`, `timeout`,
`resource_limit`, `budget_failure`, `financial_failure`,
`data_failure`, `invalid_output`, `conflict`,
`dependency_unavailable`, `business_paused`, `emergency_stop`,
`system_error`, `unknown`.

Non-retryable classes (validation, permission, policy, budget,
financial, invalid output) fail the step immediately — retrying a
denied or over-budget action would be a policy violation in itself.
Retryable classes follow the step's retry policy.

## Retry with backoff

A retryable failure moves the step to RECOVERY_PENDING with
`next_attempt_at` computed from P-01's shared backoff function
(exponential, capped). A retry is a **new pipeline pass**: decision,
authorization and approval checks all re-run — nothing about the
failed attempt's authorization is inherited. When attempts are
exhausted, the step moves to the dead-letter queue (below) if its
class is retryable, else FAILED.

## Dead-letter queue

`operations_dead_letter` holds exhausted steps with their failure
category, reason, and payload reference. The Recovery Center
(frontend and `GET /operations/recovery`) lists them. Resolution is
an owner act: `acknowledge` closes the entry; the workflow itself
remains FAILED — a dead letter is an investigation record, not a
rewind button. Re-running the work means a new workflow, whose
definition can reference what was learned.

## Circuit breakers

Per-target breakers (handler name / tool name / runner name) open
after the owner-governed failure threshold (default 3 consecutive
failures) and fail subsequent steps fast as
`external_service_unavailable` for the cooldown (default 300s),
then half-open for a probe. Breaker state is in-memory per process
— a restart closes all breakers (stated plainly: they are a
load-shedding device, not a record).

## Interruption and startup recovery

On startup the engine parks any workflow left RUNNING or VERIFYING
into RECOVERY_PENDING — it never assumes an interrupted workflow's
state. Resuming re-runs the pipeline per step; completed steps are
protected twice: by the checkpoint (completed step keys) and by
substrate idempotency keys (a re-submitted P-01 task returns the
original instead of executing again). Scenario 9 proves a substrate
execution count of exactly 1 across a crash + approval + resume.

## Emergency stop and restart

Stops compose the existing machinery — there is no P-12 stop of its
own:

- **Global** → P-10 security mode `emergency_stop` (+ P-05's engine
  stop); every workflow pauses at its next step boundary.
- **Financial** → P-10 financial suspension; non-financial work
  continues.
- **Business** → P-08 pause + that business's workflows paused;
  other businesses are untouched (Scenario 11).
- **Agent** → P-04 agent stop + reassignment of its pending steps.

**Restart is owner-only, always.** `emergency_resume` rejects
non-owner principals; resuming a business also requires the owner's
explicit act. Nothing in the engine resumes itself after a stop.

## Load deferrals

When the ResourceMonitor reports CPU or memory ≥ 95% *and* the
operational switch `block_nonessential_on_threshold` is on
(production default), the decision engine DEFERs new steps instead
of starting them into an overloaded host. Deferred steps re-check
on the next tick/drive — deferral is a pause with a reason on the
decision record, never a silent stall.
