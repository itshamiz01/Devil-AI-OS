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
| `AUTONOMUS_TASK_QUEUE_CAPACITY` | `100` | Maximum active task records admitted |
| `AUTONOMUS_TASK_MAX_CONCURRENCY` | `2` | Worker concurrency |
| `AUTONOMUS_TASK_DEFAULT_TIMEOUT` | `30` | Default handler timeout seconds |
| `AUTONOMUS_TASK_MAX_RETRIES` | `3` | Default retry limit |
| `AUTONOMUS_RETRY_BASE_DELAY` | `0.1` | Exponential backoff base seconds |
| `AUTONOMUS_RETRY_MAX_DELAY` | `5` | Maximum retry delay seconds |
| `AUTONOMUS_SHUTDOWN_TIMEOUT` | `10` | Graceful cleanup window seconds |
| `AUTONOMUS_MEMORY_PERCENT_MAX` | `90` | Nonessential task admission threshold |
| `AUTONOMUS_DISK_PERCENT_MAX` | `90` | Nonessential task admission threshold |
| `AUTONOMUS_SESSION_TTL_MINUTES` | `60` | Owner session expiry |
| `AUTONOMUS_LOGIN_RATE_LIMIT` | `5` | Login attempts per minute per client key |
| `AUTONOMUS_EXTERNAL_EXECUTION_ENABLED` | `false` | Must remain false in P-01 |
| `AUTONOMUS_FINANCIAL_EXECUTION_ENABLED` | `false` | Must remain false in P-01 |
| `AUTONOMUS_CLOUD_AI_ENABLED` | `false` | Must remain false in P-01 |

Invalid critical settings fail startup. Remote binding, remote access and phase-execution flags are rejected by validators.
