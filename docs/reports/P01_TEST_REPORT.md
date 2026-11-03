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
