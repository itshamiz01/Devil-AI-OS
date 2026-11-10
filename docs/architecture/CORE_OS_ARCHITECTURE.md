# Core OS Architecture (P-01) — as implemented

## Package map (`backend/app/`)

- `main.py` — FastAPI factory: lifespan wiring, correlation-ID middleware, error-envelope handlers, versioned routers under `/api/v1`.
- `core/` — `config.py` (validated Pydantic Settings), `logging.py` (JSON logs, redaction, rotation), `exceptions.py` (typed errors → envelope), `lifecycle.py` (state machine: starting/ready/degraded/stopping/stopped/failed with validated transitions), `health.py` (liveness vs readiness semantics), `auth.py` (owner password login w/ scrypt, session tokens stored SHA-256-hashed, service token, local-dev token — see PERMISSION_SYSTEM.md), `application.py` (assembly + startup/shutdown sequences).
- `database/` — SQLAlchemy 2.x engine/session management (SQLite WAL + FK pragmas), models, repositories (all SQL lives in repositories/services), Alembic migrations (`app/database/migrations/`, revision `b36fd80092d2`).
- `tasks/` — the universal task engine (TASK_MANAGEMENT.md).
- `events/` — in-process async event bus (EVENT_SYSTEM.md).
- `permissions/` — deny-by-default engine + approvals (PERMISSION_SYSTEM.md).
- `monitoring/` — psutil resources, thresholds, diagnostics (LOGGING_AND_MONITORING.md).
- `integrations/interfaces/` — the adapter ABC later phases plug into; no concrete integrations in P-01.

## Startup sequence (implemented in `Application.startup`)

Config load/validate → logging → data dir + engine → Alembic migrations → logging re-asserted (Alembic's `fileConfig` must not clobber the app pipeline — regression-tested) → DB connectivity verify → permission engine + approvals → event bus + critical-event persistence → monitoring → task manager → interrupted-task recovery → auth seeding (scrypt hash from env, first run only) → worker start → state READY, or DEGRADED when resource thresholds are already exceeded, or FAILED on any critical error (readiness then reports not-ready; the app never claims healthy on a broken foundation).

## Shutdown sequence

State STOPPING → ApplicationStopping event → task manager stops accepting, bounded wait for running tasks (default 10 s), remaining executions cancelled without DB verdicts (their rows stay RUNNING so the next startup's recovery marks them interrupted) → ApplicationStopped event → engine dispose → STOPPED. Verified live via SIGTERM in the smoke run.

## Recovery

On startup, RUNNING tasks become PAUSED with `progress.recovery_required=true` and their open attempts are closed as `interrupted`; VALIDATING tasks (no side effects yet) are re-queued. Nothing is blindly re-executed. Recovery is covered by an integration test that simulates a crash mid-task.
