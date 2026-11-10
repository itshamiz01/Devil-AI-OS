# P-12 Workflow Lifecycle

The state machines are enforced in `OperationsService` via
`app/operations/state_machine.py`; no route or caller writes states
directly.

## Workflow states

```
DRAFT → VALIDATING → READY → SCHEDULED → RUNNING → VERIFYING → COMPLETED
                     │          │           │  │
                     │          │           │  ├→ WAITING_FOR_APPROVAL → RUNNING
                     │          │           │  ├→ PAUSED → RUNNING (resume)
                     │          │           │  ├→ BLOCKED → RUNNING (resume)
                     │          │           │  ├→ RECOVERY_PENDING → RUNNING
                     │          │           │  └→ FAILED
                     │          │           └→ CANCELLED
                     │          └→ (invalid) DRAFT
                     └→ INVALID (validation failed; problems listed)
```

- **DRAFT** — created (manually, by template, by trigger, by agent,
  or imported from a P-02 plan). Definitions are data; nothing runs.
- **VALIDATING → READY / INVALID** — structural + policy validation
  (DAG, vocabulary, registry, budget rules). INVALID carries the
  problem list; a corrected definition returns the workflow to DRAFT.
- **SCHEDULED** — carries a future `not_before` in its execution
  policy; the tick starts it when due.
- **RUNNING** — the drive loop is executing ready steps in
  dependency waves (global concurrency ceiling applies).
- **WAITING_FOR_APPROVAL** — at least one step is parked on a P-01
  approval (step approval, spend approval, or a P-05 approval).
  Processing resumes through the approvals pass, which re-verifies
  the parameter binding before releasing anything.
- **PAUSED** — decision-engine pause (emergency modes, paused
  business) or an explicit owner pause. Resume re-runs the pipeline;
  authorization is never inherited across an interruption.
- **BLOCKED** — a step lacks required inputs (RESEARCH_MORE). Resume
  after the inputs are supplied.
- **RECOVERY_PENDING** — a step is waiting out retry backoff, or the
  workflow was interrupted (startup recovery parks RUNNING/VERIFYING
  workflows here rather than assuming their state).
- **VERIFYING** — all steps finished; the workflow completes only
  when every completed step's verification status is `verified`.
- **COMPLETED** — terminal; `verified_outcome = "verified"`. Only
  this state feeds P-09 learning.
- **FAILED** — terminal; carries the failure reason. Dependents of a
  failed step are SKIPPED, never executed.
- **CANCELLED** — terminal; owner/agent-creator act, recorded.

## Task (step) states

```
PENDING → READY → RUNNING → COMPLETED
   │         │        ├→ WAITING_FOR_APPROVAL → READY (on approval)
   │         │        ├→ RECOVERY_PENDING → READY (backoff elapsed)
   │         │        ├→ FAILED
   │         │        └→ DEAD_LETTER (retries exhausted, retryable class)
   │         ├→ BLOCKED (missing inputs)
   │         └→ SKIPPED (a dependency failed)
   ├→ WAITING_FOR_APPROVAL (pre-assignment approval paths)
   └→ CANCELLED
```

Attempts increment only when a step enters RUNNING. A step's
substrate (P-01 task / P-05 request) is created at most once per
attempt and carries the step's idempotency key, so a resumed attempt
reuses — never duplicates — finished substrate work.

## Verification

Each step declares acceptance criteria. After execution, the
verifier produces **verified**, **failed**, or **unverified**:

- substrate must reach the declared status (default `completed`);
- `result_contains` / `result_equals` check the actual result;
- money steps require `financial_state == "reconciled"` in the
  result — a spend P-07 has not recorded is never "verified";
- an execution that cannot be checked is **unverified**, and
  unverified is never promoted to success: the step fails as
  invalid output and the workflow cannot complete.

## Checkpoints

Whenever a drive settles, a checkpoint records the workflow's
completed steps (step keys + idempotency keys + substrate refs) and
the full task-status map. Startup recovery and manual resumes read
the same state the drive loop uses — completed steps are skipped by
construction, not by assumption (Scenario 9 proves the substrate
execution count stays at 1 across an interruption).
