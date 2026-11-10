# AUTONOMUS P-01 — TEST REPORT

**Suite:** `backend/tests/` (pytest 9.2.0, pytest-asyncio 1.4.1), run on the build VM (Linux, Python 3.12.3, venv inside the project).

**Totals: 76 tests — 76 passed, 0 failed, 0 skipped.** Runtime ≈ 50 s. One non-blocking warning: Starlette's TestClient deprecation notice about httpx (cosmetic, upstream).

## Coverage by area

| Area | Tests | What is proven |
|---|---|---|
| Unit — config/lifecycle/logging | 12 | validation failures (port, mode, concurrency>capacity, production without credential), secret redaction in dumps and log text, lifecycle transition legality |
| Unit — task state machine & retry | 12 | valid/invalid transitions (incl. completed→running, cancelled→completed), exponential backoff + cap, retry eligibility (invalid_input/permission/security never retried) |
| Unit — tasks engine | 14 | echo completion, unknown handler & invalid payload rejected at submission, permission-denied submission, idempotency dedupe, queue-capacity backpressure, priority ordering, transient retry to success (3 attempts recorded), no-retry on invalid input, timeout → failed/timeout, cancel queued, approval-gated task waits then runs |
| Unit — approvals/permissions | 6 | lifecycle + parameter binding (changed params invalidate), expiry, hash stability, role defaults, explicit DB deny wins, DB allow grants |
| Unit — events/monitoring | 7 | multi-subscriber delivery, subscriber failure isolation, flood limit drops, recursion depth guard, critical-event persistence with correlation ID, resource snapshot + threshold detection |
| Integration — API | 11 | live public vs ready authenticated, task submit→execute→complete over HTTP with execution history, cancel, retry, approval workflow (double-decision 409), approval-gated task release, agents read-only (POST → 404/405), persisted events listing, pagination meta |
| Integration — persistence | 3 | tasks/history survive restart; crashed RUNNING task recovered as PAUSED + recovery_required, attempt marked interrupted, **not** re-executed; Alembic upgrade head on fresh DB creates all tables |
| Security | 13 | 401 unauthenticated on all protected routes, invalid token, wrong password, Service principal 403 on approval decision + task cancel, double-decision misuse, malformed inputs 422, code/command smuggling via handler name 422, path-traversal probe 404 without leakage, scrypt hashing/verification, secrets absent from the log file, agent/external permission-bypass attempts denied, permission checks audited |
| Failure | 7 | DB-unavailable startup → lifecycle FAILED (no false health), DB death flips readiness, queue-full backpressure, threshold admission block (essential still admitted), timeout history, shutdown stops acceptance, live vs ready distinction |
| Regression | 1 | logging survives programmatic Alembic migration (post-migration + shutdown lines present in the log file, secrets absent) |

## Live smoke run (real uvicorn, loopback :8137–8139, temp SQLite DB)

1. `GET /health/live` → 200 `{"status":"alive","lifecycle_state":"degraded"}` (degraded: build-VM host memory 94.2% ≥ 90% threshold).
2. `GET /health/ready` without credentials → **401**; with login token → 200 `degraded`, `database_healthy:true`, violations `[{memory 94.2 ≥ 90}]`.
3. `POST /auth/login` (owner) → session token issued.
4. Nonessential `core.echo_check` submission → **429 `resource_blocked`** (the §10.2 admission control firing on real host load).
5. Same task with `essential:true` → created → **completed**, result `{"ok":true,"echo":{"message":"smoke-hello"}}`, 1 execution row `completed`.
6. `core.wait` (8 s) task → cancel while running → response `cancellation_requested:true` → final status **cancelled**.
7. SIGTERM → port closed; after the logging fix, the app log shows `application ready → graceful shutdown initiated → application stopped`.

## Defects found by testing and fixed (not hidden)

1. Detached-instance errors on `task.executions` after session close → eager loading in the repository.
2. `app_sessions.created_at` missing default → login inserts failed; default added (+ same hardening on audit/system events).
3. Admission guard bound at construction time → late-bound closure so threshold state is read live.
4. Worker cancellation wrote a spurious FAILED verdict → cancellation now leaves the row RUNNING for startup recovery (crash-recovery integration test written for exactly this).
5. Alembic `fileConfig` clobbered app logging (post-migration INFO logs lost) → env fix + re-assertion + regression test.
