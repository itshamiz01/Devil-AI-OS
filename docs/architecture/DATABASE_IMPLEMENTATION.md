# Database Implementation (P-01 + P-02)

SQLite via SQLAlchemy 2 async + aiosqlite. Alembic migration `03efdae6e24a` creates the core schema. Connection pragmas enable foreign keys, WAL and busy timeout. Repositories isolate persistence from API/business logic.

**P-01 tables** (migration `03efdae6e24a`): principals, owner_credentials, auth_sessions, system_configurations, agents, permissions, permission_assignments, approvals, tasks, task_executions, audit_events, system_events.

**P-02 tables** (migration `2a904ceb99c4`, 10 entity groups per §17): missions, mission_history, plans, plan_steps, intelligence_decisions, evidence_records, hypotheses, registered_models, model_usage, intelligence_executions.

Plus `alembic_version`. 22 mapped table classes; 23 SQLite tables after both migrations.

## P-02 intelligence schema

The P-02 migration is **forward-only and additive**. Its `upgrade()` contains ten `create_table` calls, **zero** drops and **zero** alters, and references no P-01 table beyond the foreign keys it needs. `downgrade()` drops the ten P-02 tables and nothing else. The round trip was verified: upgrade → 23 tables, downgrade → 13 (P-01 intact), re-upgrade → an identical set. No record was destroyed at any point.

Foreign keys: `missions.owner_principal_id → principals.id`; `mission_history.mission_id`, `plans.mission_id`, `intelligence_decisions.mission_id`, `evidence_records.mission_id`, `hypotheses.mission_id` and `intelligence_executions.mission_id → missions.id`; `plan_steps.plan_id → plans.id` and `plan_steps.task_id → tasks.id`. `registered_models` and `model_usage` have none.

Design points worth recording:

- **`evidence_records.content_reference` stores a reference, never the artefact.** Retrieved external content is not copied into the database (§12.4, §17).
- **`hypotheses.confidence_basis` defaults to `unvalidated_estimate`**, so a persisted confidence can never be read back as a measured probability (§8.3).
- **`missions.model_interpreted`** records whether a model contributed to the interpretation, keeping model output attributable rather than indistinguishable from owner-stated fact.
- **`model_usage` is operational accounting, not a financial ledger.** It is never summed into business revenue or expenses (§17). Local inference is recorded at cost `0.0`.
- **`registered_models.configuration`** is where a provider base URL or key would live. It is stored but never returned by the API (§14).
- `missions.available_resources` and `missions.dependencies` exist because the pydantic contract carries them; without columns a persist/reload round trip silently dropped both. They were added to this migration before it was committed, so no deployed database was affected.

Persistence is implemented in `app/intelligence/repository.py`: upsert by natural key, **never delete**, with `mission_history` append-only so re-saving a mission cannot duplicate or rewrite its audit trail. Recovery after a restart restores visibility only — nothing is re-planned, re-dispatched or re-authorized (§15). Verified by `tests/test_intelligence_persistence.py` (26 tests).

Timestamps are UTC. Secrets are not stored in ordinary tables; owner passwords are Argon2 hashes and session tokens are SHA-256 hashes. Audit records are append-only through application APIs but local SQLite is not cryptographically immutable.

## Backup and restore

`app/database/backup.py` snapshots through the SQLite **online backup API** (`sqlite3.Connection.backup`), never by copying the file: under `journal_mode=WAL` a plain copy can miss committed transactions still resident in `-wal` and produce a torn snapshot.

A backup is reported successful only after the *copy* passes `PRAGMA integrity_check` **and** contains the nine required core tables; an unverifiable snapshot is deleted rather than left to be mistaken for a good one. Retention is bounded by `AUTONOMUS_BACKUP_RETENTION_COUNT` so backups cannot consume the disk the monitor watches.

**Restore is CLI-only** (`autonomus restore --from <path>`, confirm by typing `RESTORE`) and is deliberately not exposed over HTTP — P-01 §12 forbids dangerous internal functions as endpoints, and an HTTP restore would sit one leaked session token away from erasing the audit trail (ADR-0014). Restore preserves the displaced database as `<name>.pre-restore-<timestamp>.db`, removes stale `-wal`/`-shm` sidecars first, refuses to run while a live backend pid is detected, and rolls back if the restored file fails verification. `--assume-stopped` bypasses only the liveness check, never integrity verification, because a `backend.pid` file can survive a hard kill.

Backups are ordinary files on the same host: they protect against accidental corruption and application-level mistakes, and are **not** cryptographically immutable against a host administrator. Secrets are outside SQLite (ADR-0012), so no backup contains them.

PostgreSQL migration path: keep repository interfaces, avoid SQLite-specific service logic, test dialect differences, use controlled cutover. SQLite WAL is not a network/multi-machine database.
