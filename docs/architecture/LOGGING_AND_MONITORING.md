# P-01 Logging and Monitoring

Structured JSON logs include timestamp, level, logger, message and optional correlation/task/component fields. Rotating file handler writes to `logs/autonomus.log`. Redaction removes bearer tokens and password/token/secret-like values.

Monitoring uses psutil for CPU, memory, disk and process RSS/thread count. Resource pressure blocks nonessential task admission and emits `ResourceThresholdExceeded`. Essential `system.noop` tasks may still be admitted. Health distinguishes liveness, readiness and degraded status.

Monitoring does not automatically kill active tasks or optimize CPU/RAM. It reports and applies admission control only.
