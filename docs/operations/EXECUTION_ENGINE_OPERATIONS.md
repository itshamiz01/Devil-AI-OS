# Execution Engine Operations (P-05)

## Day-2 surface (all under `/api/v1`)

| Endpoint | Purpose |
|---|---|
| `GET /execution/health-report` | §27 startup health report: per-adapter truth for this environment |
| `GET /execution/status` | Measured metrics: requests by status, runs, avg duration, ceilings, sessions, standing authorizations |
| `GET /execution/tools` | Registry (discovery view; admin view for the owner) |
| `POST /execution/tools/{name}/validate` / `/disable` | Owner-only tool lifecycle |
| `GET/PATCH /execution/settings` | Owner-only execution settings |
| `POST /execution/emergency-stop` / `/emergency-resume` | Owner-only (§23.7) |
| `GET /execution/requests/{id}` (+ `/evidence`, `/audit`) | Per-request truth: four facts, runs, evidence, audit trail |

## Settings (`execution.settings`, owner-only)

| Key | Default | Meaning |
|---|---|---|
| `max_concurrent_runs` | 4 | Filesystem/browser-class runs in flight |
| `max_concurrent_subprocesses` | 2 | Code runs in flight |
| `max_browser_sessions` | 2 | Open sessions per agent |
| `max_api_concurrency` | 4 | API calls in flight |
| `max_workflow_concurrency` | 2 | Workflow runs in flight |
| `default_timeout_seconds` / `max_timeout_seconds` | 60 / 600 | Per-request timeout default and clamp |
| `max_input_bytes` / `max_output_bytes` | 5 MB / 1 MB | Payload and capture ceilings |
| `approval_expiry_minutes` | 30 | Engine-created approval lifetime |
| `emergency_stop` | false | The stop flag (use the endpoint, which also terminates work) |
| `code_execution_enabled` | true | Owner kill-switch for the code tool's availability reporting |
| `browser_allowlist` / `api_allowlist` | [] | Owner-governed host/domain allowlists — **empty means nothing external is reachable** |

## Workspaces

Root: `<data_dir>/execution_workspaces/` with `shared/ projects/
businesses/ agent_workspaces/<agent_id>/ temporary/ quarantine/`.
Quarantine holds reversible deletions (`<agent>__<timestamp>__<name>`);
review it periodically — permanent deletion is the Risk-2 governed
action `filesystem delete_permanent` on the `quarantine` workspace.
Overwrite snapshots accumulate under `temporary/snapshots/<request_id>/`
and code-run leftovers should not exist (runs clean up after
themselves); both are safe to prune when no run is active.

## Approvals operations

Engine approvals are ordinary P-01 approvals with action
`execution.execute`. Owners decide them through the standard approvals
API; an expired approval can be replaced via
`POST /execution/requests/{id}/request-approval`. A request whose
approval was denied finalizes as REJECTED/`APPROVAL_DENIED`.

## Emergency stop drill

1. `POST /execution/emergency-stop` (owner) — flag set, managed
   subprocesses terminated, browser sessions paused, report returned.
2. Verify: new submissions return REJECTED with the halt reason;
   `GET /execution/status` shows `emergency_stop: true`.
3. `POST /execution/emergency-resume` (owner) — flag cleared, paused
   sessions reactivated.

## Troubleshooting

- **Everything REJECTED "execution is halted"** — the stop flag or
  emergency mode is on; check `/execution/health-report`.
- **API/browser calls fail at policy scope** — the host is not on the
  owner allowlist (defaults are empty by design).
- **Request stuck AWAITING_APPROVAL** — decide the linked approval, or
  create a fresh one via `request-approval` if it expired.
- **Workflow RECOVERY_REQUIRED** — an interrupted non-idempotent step
  needs manual reconciliation of its real-world effect before resuming;
  the checkpoint names the step and request. Do not force it.
- **Code runs TIMED_OUT** — expected behaviour at the request's timeout;
  the process tree was killed and the run directory cleaned.
