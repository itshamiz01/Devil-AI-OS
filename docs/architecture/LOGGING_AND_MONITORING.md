# P-01 Logging and Monitoring

Structured JSON logs include timestamp, level, logger, message and optional correlation/task/component fields. Rotating file handler writes to `logs/autonomus.log`. Redaction removes bearer tokens and password/token/secret-like values.

Monitoring uses psutil for CPU, memory, disk and process RSS/thread count. Resource pressure blocks nonessential task admission and emits `ResourceThresholdExceeded`. Essential `system.noop` tasks may still be admitted. Health distinguishes liveness, readiness and degraded status.

Health distinguishes liveness (`/health/live`, process responding), readiness (`/health/ready`, critical dependencies operational) and degraded status (`/health`, reduced functionality).

During an active emergency stop the lifecycle reports `DEGRADED` and `/health` returns `status: degraded` with `checks.emergency_stop_active: true`, while `/health/ready` still returns `ready: true`. That is deliberate: an emergency is an owner-chosen state rather than a dependency failure, and reporting not-ready would hide the very control path the owner needs in order to clear it (ADR-0013).

Monitoring does not automatically kill active tasks or optimize CPU/RAM. It reports and applies admission control only. Emergency admission blocking is a separate, explicit human decision, not an automatic optimization.

The owner's emergency `reason` is persisted and returned to authorized callers but is never formatted into a log message, so it cannot be used to smuggle a value past redaction.
