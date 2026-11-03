# P-01 Database Implementation

SQLite via SQLAlchemy 2 async + aiosqlite. Alembic migration `03efdae6e24a` creates the core schema. Connection pragmas enable foreign keys, WAL and busy timeout. Repositories isolate persistence from API/business logic.

Tables: principals, owner_credentials, auth_sessions, system_configurations, agents, permissions, permission_assignments, approvals, tasks, task_executions, audit_events, system_events, alembic_version.

Timestamps are UTC. Secrets are not stored in ordinary tables; owner passwords are Argon2 hashes and session tokens are SHA-256 hashes. Audit records are append-only through application APIs but local SQLite is not cryptographically immutable.

PostgreSQL migration path: keep repository interfaces, avoid SQLite-specific service logic, test dialect differences, use controlled cutover. SQLite WAL is not a network/multi-machine database.
