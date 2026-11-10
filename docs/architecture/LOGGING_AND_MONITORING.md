# Logging & Monitoring (P-01 §10–11) — as implemented

## Logging

Structured JSON records (timestamp, level, component, message, correlation_id, task_id) to console and a rotating file (`log_max_bytes` / `log_backup_count`). A redaction filter masks configured secret values and secret-looking patterns (`password=…`, `api_key=…`, `Bearer …`, `sk-…`) in every record — verified by tests that read the actual log file after authenticated API use and assert none of the configured secrets appear. Passwords, API keys, private keys, tokens and cookies are never logged by design; the startup configuration dump is redacted.

Two logging defects were found and fixed during P-01 verification: (1) Alembic's `fileConfig` re-leveled the root logger during programmatic migrations, silently swallowing post-migration INFO logs — fixed in `migrations/env.py` + a post-migration logging re-assertion, with a regression test; (2) audit vs ordinary logs: audit records are **database rows** (`audit_events`), not log lines, and are distinguishable by design.

## Monitoring

`SystemMonitor` (psutil): CPU %, memory %/available/total, disk %/free/total for the data volume, process count, DB connectivity (SELECT 1), queue snapshot (capacity/depth/running/by-status). Thresholds (CPU 90 / memory 90 / disk 95 by default) produce violations that: mark the app DEGRADED at startup or in readiness, are returned by `/health/ready` and `/system/*`, and — when `block_nonessential_on_threshold` is on — block nonessential task admissions with 429 while essential tasks still run. This fired for real in the P-01 smoke run on the build VM (host memory 94.2% ≥ 90%): the nonessential submission was rejected `resource_blocked`, the essential one completed.

The monitor reports facts only; it does not claim to optimize CPU/RAM (per §10.2) — admission control is the only automatic action, and it is implemented and tested.
