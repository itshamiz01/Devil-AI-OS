# Workflow Execution Engine (P-05, §§15–16)

`execution/workflows.py` — orchestration over the same ExecutionService
submit/execute path as standalone requests. A workflow is **not** a side
door: every step passes the same policy, approvals, verification, and
audit as a direct request.

## Definitions are data (§15.1)

```json
{
  "steps": [
    {"id": "write", "tool": "documents", "action": "create_text",
     "parameters": {"workspace": "agent:<id>", "path": "note.txt",
                    "content": "from {{input.channel}}"},
     "expected_outcome": {"file": {"workspace": "agent:<id>", "path": "note.txt"}},
     "on_failure": "stop",
     "compensation": {"tool": "filesystem", "action": "delete",
                      "parameters": {"workspace": "agent:<id>", "path": "note.txt"}}}
  ]
}
```

Validation (`validate_definition`): non-empty steps (≤ 50), unique ids,
tool+action present, `on_failure ∈ {stop, continue, retry}`, compensation
shape. Definitions are versioned rows; an invalid definition is stored
with its errors and `status = invalid` and cannot run. Step parameters
support `{{input.<key>}}` string substitution from run inputs — data
substitution only, never code evaluation.

## Run states (§15.3)

DRAFT, VALIDATING, APPROVED, QUEUED, RUNNING, PAUSED, AWAITING_APPROVAL,
AWAITING_HUMAN, COMPLETED, FAILED, CANCELLED, RECOVERY_REQUIRED —
transitions enforced by `WORKFLOW_TRANSITIONS`; illegal transitions raise
`WorkflowStateError`.

## Checkpoints (§16.1)

After every step the run's `checkpoint` JSON is rewritten:
`completed_steps`, `step_outputs` (step → execution request id),
`compensated_steps`, `failed_steps`. Each step has a `WorkflowStepRun`
row linked to its execution request.

## Idempotency (§16.2)

Every step submission carries idempotency key `wf:<run_id>:<step_id>`
(compensations: `…:<step>:compensation`); resubmission returns the
original request. Retries (`on_failure: retry`, and manual re-execution)
are permitted only for actions whose registry spec is idempotent, with
bounded attempts — a failed non-idempotent action cannot be re-executed
through the engine at all.

## Blocking and resume

A step at AWAITING_APPROVAL moves the run to AWAITING_APPROVAL; a step
requiring human authentication moves it to AWAITING_HUMAN. `resume`
re-drives the run: the blocked step's request passes through the
execution approval gate (approved → executes; still pending → the run
re-blocks). A CANCELLED run is terminal: driving it changes nothing and
launches no steps (tested, §25.3 #13).

## Compensation (§16.3) — honestly labelled

On failure with `on_failure: stop`, completed steps that declared a
compensation are compensated in reverse order through the normal
execution path (e.g. a created file is quarantined via `filesystem
delete`). If a compensation cannot execute, the run goes to
RECOVERY_REQUIRED instead of FAILED. Compensation is **not** called
"rollback": external effects (an HTTP POST already sent) may be
irreversible, and the checkpoint records exactly what was and was not
compensated.

## Concurrency (§18)

Workflow runs share the execution scheduler's ceilings; the settings key
`max_workflow_concurrency` is owner-governed alongside the other
ceilings (see EXECUTION_ENGINE_OPERATIONS.md).
