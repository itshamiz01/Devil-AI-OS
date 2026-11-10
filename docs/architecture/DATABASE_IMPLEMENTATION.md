# Database Implementation (P-01 §6) — as implemented

SQLAlchemy 2.x over SQLite (WAL mode, foreign keys enforced via pragma). Repositories (`app/database/repositories/`) own all SQL; services and routes never build queries directly. Alembic migration `b36fd80092d2` creates the full P-01 schema; verified `upgrade head` on a fresh database (automated test asserts every table). All timestamps are UTC; explicit PKs, FKs and indexes as modeled.

## Tables created (9 application tables + `alembic_version`)

| Table | Purpose |
|---|---|
| `system_config` | Validated non-secret settings + hashed credential material (key/value, unique key) |
| `tasks` | Task records (see TASK_MANAGEMENT.md) with unique idempotency key |
| `task_executions` | One row per attempt: status, duration, result/error |
| `agents` | Agent **registration metadata + lifecycle status only** — no autonomous creation in P-01 |
| `permissions` | Principal/role permission rules (allow/deny, optional resource), unique per principal+permission+resource |
| `approvals` | Approval requests with parameter binding hash and decision fields |
| `audit_events` | Append-only audit records (actor, action, target, decision, reason, correlation) |
| `system_events` | Persisted critical internal events |
| `app_sessions` | Session tokens — SHA-256 hashes only, with expiry and revocation flag |

Only the §6.1 P-01 entities exist. Business, financial, opportunity and memory entities from the P-00 database blueprint are deliberately **not** implemented yet.

## PostgreSQL migration path & limitations

Models use portable types (JSON, not SQLite-specific types); migrations are versioned from day one; the data layer is the only place with engine specifics. Known limitations when moving: SQLite's permissive typing vs PostgreSQL strictness, single-writer WAL semantics vs MVCC, and `render_as_batch` ALTER patterns — a PostgreSQL move must be rehearsed upgrade/downgrade/re-upgrade on a copy first (the standard proven in the owner's ClipOS Phase 11 audit).
