# Execution Recovery (P-05, §16.4 / §21)

## Principle

A restart never guesses. Work interrupted mid-flight is marked and
classified; only provably-safe work may resume automatically, and
anything uncertain goes to a human as REQUIRES_RECONCILIATION /
RECOVERY_REQUIRED. **An interrupted non-idempotent or external action is
never blindly repeated.**

## Startup recovery scan

`ExecutionService.recover_interrupted()` runs during application
startup (after seeding), and its result is kept on
`application.execution_recovery`:

1. **Execution runs** left `RUNNING` → `INTERRUPTED`; their requests
   (if still `RUNNING`) → `INTERRUPTED` with the summary
   *"interrupted by a restart; outcome not assumed"*.
2. **Workflow runs** left `RUNNING` are settled per step
   (`WorkflowEngine.recover_interrupted`):
   - The in-flight step's request is terminal → the run is requeued;
     the next drive settles the step from its recorded outcome.
   - The in-flight step's request is non-terminal/interrupted **and**
     its action is idempotent (registry spec) → run requeued (safe to
     resume).
   - Otherwise → run `RECOVERY_REQUIRED` with a checkpoint `recovery`
     record naming the step and request. Nothing is repeated.

## What recovery never does

- Never re-executes an interrupted request directly (requests become
  INTERRUPTED, a terminal outcome; a human decides next steps).
- Never repeats a non-idempotent workflow step.
- Never treats a half-finished external effect (an HTTP call whose
  response was lost) as either success or failure — it is
  reconciliation work.

## Cancellation semantics

Cancelling a QUEUED or AWAITING_APPROVAL request is immediate and
final. Cancelling a RUNNING request marks it CANCELLED; for code runs
the async cancel path terminates the managed process tree first, and the
executor honours the cancellation when the adapter returns (the run
record shows what actually happened). A cancelled workflow launches no
further steps, even if a pending approval is granted afterwards
(tested, §25.3 #13).

## Evidence after interruption

Runs, evidence rows, checkpoints, and audit entries written before the
interruption are untouched by recovery — recovery only appends status
truth. The audit trail is append-only through every P-05 interface
(there is no mutation route; §25.3 #16).
