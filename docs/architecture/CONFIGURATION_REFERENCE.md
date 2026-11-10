# Configuration Reference (P-01 §5) — as implemented

All configuration is centralized in `backend/app/core/config.py` (Pydantic Settings) and read from environment variables with the `AUTONOMUS_` prefix (or a local `.env`). Settings are validated at startup; invalid configuration fails startup loudly. Secrets are masked in every dump/log (`redacted_dict()` + the logging redaction filter).

| Variable | Default | Meaning |
|---|---|---|
| `AUTONOMUS_ENVIRONMENT` | `development` | `development` / `production` / `test`. Production requires an admin credential. |
| `AUTONOMUS_MODE` | `simulation` | Operating mode: simulation / supervised / controlled / emergency. |
| `AUTONOMUS_HOST` | `127.0.0.1` | Bind address. Loopback by default; remote exposure needs a later approved design. |
| `AUTONOMUS_PORT` | `8000` | API port (1–65535). |
| `AUTONOMUS_DATA_DIR` | `data` | Local data directory; default SQLite DB lives here. |
| `AUTONOMUS_DATABASE_URL` | derived | Full SQLAlchemy URL; overrides the derived SQLite path. |
| `AUTONOMUS_AUTO_MIGRATE` | `true` | Run Alembic `upgrade head` at startup. |
| `AUTONOMUS_LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR/CRITICAL. |
| `AUTONOMUS_LOG_FILE` | `<data_dir>/../logs/autonomus.log` | JSON log file (rotating). |
| `AUTONOMUS_LOG_MAX_BYTES` / `AUTONOMUS_LOG_BACKUP_COUNT` | `1000000` / `5` | Rotation policy. |
| `AUTONOMUS_QUEUE_CAPACITY` | `100` | Bounded queue capacity (backpressure beyond this). |
| `AUTONOMUS_MAX_CONCURRENCY` | `4` | Max simultaneous task executions (must be ≤ capacity). |
| `AUTONOMUS_SHUTDOWN_TIMEOUT_SECONDS` | `10` | Grace period for running tasks at shutdown. |
| `AUTONOMUS_RETRY_BASE_DELAY_SECONDS` / `AUTONOMUS_RETRY_MAX_DELAY_SECONDS` | `0.5` / `30` | Exponential backoff base and cap. |
| `AUTONOMUS_CPU_THRESHOLD_PERCENT` / `MEMORY_` / `DISK_` | `90` / `90` / `95` | Resource thresholds: warnings + nonessential admission blocking. |
| `AUTONOMUS_BLOCK_NONESSENTIAL_ON_THRESHOLD` | `true` | Enable admission blocking on threshold violations. |
| `AUTONOMUS_EVENT_RATE_LIMIT_PER_SECOND` | `200` | Event-bus flood limit. |
| `AUTONOMUS_EVENT_MAX_DEPTH` | `3` | Event recursion depth guard. |
| `AUTONOMUS_ADMIN_USERNAME` | `owner` | Owner admin identity. |
| `AUTONOMUS_ADMIN_PASSWORD` | — | Owner password, env-only; scrypt-hashed at first run, never stored/logged in plaintext. |
| `AUTONOMUS_DEV_TOKEN` | — | Local-dev fallback Bearer token (owner-equivalent) for when no password is configured. |
| `AUTONOMUS_SERVICE_TOKEN` | — | Limited Service-principal Bearer token (read + submit only). |
| `AUTONOMUS_SESSION_EXPIRY_HOURS` | `12` | Login session lifetime. |
| `AUTONOMUS_FEATURE_FLAGS` | `{}` | JSON dict of feature flags. |

No development-machine paths are hardcoded; every path derives from `data_dir` or an explicit variable.
