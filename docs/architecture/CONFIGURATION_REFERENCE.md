# P-01 Configuration Reference

Configuration is centralized in `backend/app/core/config.py` using Pydantic Settings. Environment variables use the `AUTONOMUS_` prefix. Secrets are not stored in configuration tables or logs.

| Variable | Default | Meaning |
|---|---:|---|
| `AUTONOMUS_ENVIRONMENT` | `development` | `development`, `test`, or `production` |
| `AUTONOMUS_HOST` | `127.0.0.1` | Loopback only in P-01 |
| `AUTONOMUS_PORT` | `8000` | Local API port |
| `AUTONOMUS_ALLOW_REMOTE_ACCESS` | `false` | Must remain false; remote access is not implemented |
| `AUTONOMUS_DATA_DIR` | `<repo>/data` | SQLite database and runtime files |
| `AUTONOMUS_LOG_DIR` | `<repo>/logs` | Rotating JSON logs |
| `AUTONOMUS_LOG_LEVEL` | `INFO` | Log level |
| `AUTONOMUS_LOG_MAX_BYTES` | `1048576` | Size at which `autonomus.log` rotates (min 1024) |
| `AUTONOMUS_LOG_BACKUP_COUNT` | `3` | Rotated log files retained |
| `AUTONOMUS_BACKUP_DIR` | `<repo>/backups` | Verified database snapshots; restore is CLI-only (ADR-0014) |
| `AUTONOMUS_BACKUP_RETENTION_COUNT` | `7` | Newest backups kept before pruning (1-100) |
| `AUTONOMUS_TASK_QUEUE_CAPACITY` | `100` | Maximum active task records admitted |
| `AUTONOMUS_TASK_MAX_CONCURRENCY` | `2` | Worker concurrency |
| `AUTONOMUS_TASK_DEFAULT_TIMEOUT` | `30` | Default handler timeout seconds |
| `AUTONOMUS_TASK_MAX_RETRIES` | `3` | Default retry limit |
| `AUTONOMUS_SCHEDULER_POLL_INTERVAL` | `0.1` | Seconds between retry-promotion and approval-expiry sweeps |
| `AUTONOMUS_TASK_APPROVAL_TTL_SECONDS` | `3600` | Lifetime of the approval gating an `approval_required` task (60-86400). On expiry the task is cancelled by the sweep, never left waiting |
| `AUTONOMUS_RETRY_BASE_DELAY` | `0.1` | Exponential backoff base seconds |
| `AUTONOMUS_RETRY_MAX_DELAY` | `5` | Maximum retry delay seconds |
| `AUTONOMUS_SHUTDOWN_TIMEOUT` | `10` | Graceful cleanup window seconds |
| `AUTONOMUS_MEMORY_PERCENT_MAX` | `90` | Nonessential task admission threshold |
| `AUTONOMUS_DISK_PERCENT_MAX` | `90` | Nonessential task admission threshold |
| `AUTONOMUS_CPU_PERCENT_MAX` | `95` | Reported in resource snapshots and thresholds |
| `AUTONOMUS_DOCS_ENABLED` | `true` | Serves `/docs` and `/openapi.json`; disable in hardened deployments |
| `AUTONOMUS_SESSION_TTL_MINUTES` | `60` | Owner session expiry |
| `AUTONOMUS_LOGIN_RATE_LIMIT` | `5` | Login attempts per minute per client key |
| `AUTONOMUS_EXTERNAL_EXECUTION_ENABLED` | `false` | Must remain false in P-01 |
| `AUTONOMUS_FINANCIAL_EXECUTION_ENABLED` | `false` | Must remain false in P-01 |
| `AUTONOMUS_CLOUD_AI_ENABLED` | `false` | Must remain false in P-01 |

Invalid critical settings fail startup. Remote binding, remote access and phase-execution flags are rejected by validators.

## Emergency stop

The owner's emergency stop is **not** an environment variable. It is durable runtime state, persisted in the `system_configurations` table so that it survives restart and can never be cleared by editing configuration or by any automatic path (ADR-0013). It is controlled only through:

```
POST /api/v1/system/emergency/activate   # permission: system.emergency (owner-only)
POST /api/v1/system/emergency/clear      # permission: system.emergency (owner-only)
GET  /api/v1/system/emergency            # permission: system.read
```

Both write operations require a non-empty `reason`, which is persisted and audited but never written to log messages.

## Not a setting: `AUTONOMUS_OPERATING_MODE`

`.env.example` still carries `AUTONOMUS_OPERATING_MODE=simulation` for historical compatibility. It is **inert**: it is not a `Settings` field and `extra="ignore"` discards it. P-01 does not implement operating modes and the four modes P-12 requires are not named in any approved document, so no semantics have been invented here. Tracked as `D-15`; the owner must decide whether to wire it or remove it.

## Coverage check

Every `Settings` field is documented above. Verify with:

```
python -c "import sys;sys.path.insert(0,'backend');from app.core.config import Settings;print(len(Settings.model_fields))"
```

and compare against the `AUTONOMUS_*` entries in this file.
