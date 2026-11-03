# P-01 Database Implementation

SQLite via SQLAlchemy 2 async + aiosqlite. Alembic migration `03efdae6e24a` creates the core schema. Connection pragmas enable foreign keys, WAL and busy timeout. Repositories isolate persistence from API/business logic.

Tables: principals, owner_credentials, auth_sessions, system_configurations, agents, permissions, permission_assignments, approvals, tasks, task_executions, audit_events, system_events, alembic_version.

Timestamps are UTC. Secrets are not stored in ordinary tables; owner passwords are Argon2 hashes and session tokens are SHA-256 hashes. Audit records are append-only through application APIs but local SQLite is not cryptographically immutable.

## Backup and restore

`app/database/backup.py` snapshots through the SQLite **online backup API** (`sqlite3.Connection.backup`), never by copying the file: under `journal_mode=WAL` a plain copy can miss committed transactions still resident in `-wal` and produce a torn snapshot.

A backup is reported successful only after the *copy* passes `PRAGMA integrity_check` **and** contains the nine required core tables; an unverifiable snapshot is deleted rather than left to be mistaken for a good one. Retention is bounded by `AUTONOMUS_BACKUP_RETENTION_COUNT` so backups cannot consume the disk the monitor watches.

**Restore is CLI-only** (`autonomus restore --from <path>`, confirm by typing `RESTORE`) and is deliberately not exposed over HTTP — P-01 §12 forbids dangerous internal functions as endpoints, and an HTTP restore would sit one leaked session token away from erasing the audit trail (ADR-0014). Restore preserves the displaced database as `<name>.pre-restore-<timestamp>.db`, removes stale `-wal`/`-shm` sidecars first, refuses to run while a live backend pid is detected, and rolls back if the restored file fails verification. `--assume-stopped` bypasses only the liveness check, never integrity verification, because a `backend.pid` file can survive a hard kill.

Backups are ordinary files on the same host: they protect against accidental corruption and application-level mistakes, and are **not** cryptographically immutable against a host administrator. Secrets are outside SQLite (ADR-0012), so no backup contains them.

PostgreSQL migration path: keep repository interfaces, avoid SQLite-specific service logic, test dialect differences, use controlled cutover. SQLite WAL is not a network/multi-machine database.
