# P-01 Test Report

**Date:** 2026-11-03  
**Environment:** Arena Linux sandbox, Python 3.13.16  
**Result:** 32 passed, 0 failed, 0 skipped  
**Evidence:** `docs/reports/P01_TEST_RESULTS.xml`

## Test categories

- Configuration validation: loopback default, remote host/flag rejection, phase execution flag rejection.
- Authentication/API: public liveness, protected endpoints, login/logout/me, invalid login/token.
- Tasks: submit/complete, echo, invalid payload, unknown handler, idempotency, cancellation, timeout retry, queue capacity, pause/resume, resource protection.
- Permissions/approvals: approval create/decision, self-approval restriction, payload binding, agent permission denial.
- Events/monitoring: persisted events/audit, system status/resources, readiness.
- Unit: redaction, task state machine, priority queue ordering/capacity.
- Recovery: restart marks RUNNING task INTERRUPTED; event subscriber failure isolated.

## Live smoke test

The backend was started with `python3 -m app.cli serve` on 127.0.0.1:8000. `/health/live` returned alive, `/health/ready` returned ready=true, and unauthenticated `/system/status` returned 401. Lifecycle events ApplicationStarted/Ready/Stopping/Stopped were persisted. The process was stopped after the smoke test.

## Warnings

One Starlette/httpx deprecation warning remains. It does not indicate a failed test. Windows execution, Tauri, frontend, model inference and external side effects were not tested.


---

## Addendum — P-01 continuation run (2026-11-03)

The figures above are the historical record of the original P-01 run and are
preserved unmodified. Note that its environment line ("Python 3.13.16") describes
the sandbox used then; the current workspace runs **Python 3.11.2** (see
`P00_REAUDIT_ENVIRONMENT.md` and `D-11`).

**Current result: 67 passed, 0 failed, 0 skipped** (from a 43-test baseline).
**Evidence:** `docs/reports/P01_CONTINUATION_TEST_RESULTS.xml` (`tests="67"`).
The historical `P01_TEST_RESULTS.xml` (`tests="32"`) is left byte-identical.

24 tests were added, in two new files:

- `tests/test_emergency_stop.py` (11) — non-essential admission blocked while
  essential work still executes; a reason is mandatory; health reports
  `degraded` with `ready: true`; clearing restores admission; activation is
  idempotent and preserves the original reason; activation and clearing are
  audited; a non-owner principal is refused; queued non-essential work is paused
  while essential work is untouched; **state survives a full application restart
  and is never cleared automatically**; and an owner whose database predates the
  `system.emergency` permission regains it at startup without any non-owner
  principal being widened.
- `tests/test_backup_restore.py` (13) — a backup produces a snapshot that passes
  `PRAGMA integrity_check` and contains the required schema; backing up with no
  database fails loudly; a corrupt file and a valid-but-wrong-schema SQLite file
  are both rejected; restore recovers the backed-up state and discards later
  writes; the displaced database is preserved and is itself valid; an
  unverified backup is refused and leaves the live database untouched; restore
  refuses while a live backend pid exists, tolerates a provably dead pid, and
  honours an explicit override; retention prunes to the configured count.

No existing assertion was weakened, removed or relaxed. The 43 prior tests pass
unchanged.

Still not tested, and not claimed: Windows execution, Tauri, frontend, model
inference, external side effects, and real OS credential storage.
