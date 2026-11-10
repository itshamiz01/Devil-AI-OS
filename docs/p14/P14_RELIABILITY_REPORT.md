# P-14 RELIABILITY REPORT — Stage A (Audit Only)

**Environment warning:** every measurement and behaviour below was
observed on the Linux staging VM (shared vCPU, SQLite). Windows
startup/shutdown behaviour is **UNVERIFIED** (§5 of the architecture
audit). "Crash" tests are process-lifecycle tests (shutdown +
restart on the same database, interrupted-work recovery scans), not
power-loss tests.

## 1. Health and monitoring surface — VERIFIED PRESENT

| Capability (§12) | Status | Evidence |
|---|---|---|
| Service health checks | Implemented | `GET /api/v1/health/live` (unauthenticated, minimal), `/health/ready`, `/health` (permission-gated, includes diagnostics + recovered-task count) — probed live in `test_p14_health_endpoints` |
| Dependency health checks | Partial | Database health is checked (`database_healthy` in readiness + diagnostics); AI-provider health is not part of readiness (no real provider exists to check) |
| Background worker monitoring | Implemented (in-process) | SystemMonitor exposes queue stats; P-12 operations overview surfaces workflow/dead-letter state |
| Queue monitoring | Implemented | TaskManager queue stats wired into SystemMonitor at assembly |
| Database health monitoring | Implemented | `check_database` at startup + monitor `database_healthy()` |
| Agent heartbeat monitoring | Implemented at P-04 level | Agent health states + `AgentHealthChanged` events; agents are logical configurations, so "heartbeat" is execution-outcome based, not a process ping |
| Model availability monitoring | **Not implemented as monitoring** | Provider failure is handled at call time (fallback/fail-safe — see orchestration probes); no standing provider-health probe exists. P2 finding |
| Workflow recovery | Implemented | P-12: interrupted workflows park in RECOVERY_PENDING at startup, never blindly re-run; resume is idempotent (substrate execution count exactly 1 — P-12 scenario, re-verified in P-14 orchestration probes) |
| Graceful shutdown | Implemented | Lifecycle transitions + "graceful shutdown initiated" log sequence observed in probe runs |
| Safe restart | **Verified by new P-14 probe** | `test_p14_safe_restart_preserves_state_without_duplicate_seeds`: business created under lifecycle 1 is intact under lifecycle 2 on the same DB; startup seeding is idempotent (no duplicate businesses, financial-account count unchanged) |
| Backup validation | Create + checksum-verify implemented and probed (`test_p14_backup_create_and_verify`); **in-app restore does NOT exist** — restore is a documented manual owner procedure (P-10 design). Registered as a P2 finding: a backup that has never been restore-drilled inside the product is weaker than §12's "Backup validation" implies |
| Execution recovery | Implemented | P-05 startup recovery scan marks interrupted execution requests INTERRUPTED — never blindly repeated (`application.execution_recovery`) |
| Task recovery | Implemented | P-01 TaskManager recovery at startup; recovered IDs surfaced in `/health` (`recovered_tasks`) |

## 2. Crash-recovery requirements (§12) — point by point

| Requirement | Verdict |
|---|---|
| Preserve task state | HOLDS — persistent queue; state survives restart (probe §1) |
| Preserve financial transaction state | HOLDS — journal is append-only DB state; no in-memory money |
| Prevent duplicate actions | HOLDS — idempotency keys (tasks, workflows, postings); P-12 crash-resume execution count exactly 1 |
| Recover eligible interrupted workflows | HOLDS — RECOVERY_PENDING + governed resume |
| Revalidate permissions before resuming | HOLDS — resume travels the same broker/permission path as a fresh start (P-12 design, scenario-tested) |
| Require fresh approval when previous authorization expired | HOLDS — approvals are single-use and expiry-bound (P-10); an expired approval cannot be consumed by a resumed workflow (security probes re-verify expiry refusal) |
| Report unresolved operations | HOLDS — dead-letter queue with owner-only resolution; RECOVERY_PENDING workflows are visible in the operations views |

## 3. Windows startup and shutdown — UNVERIFIED

Controlled startup, dependency readiness, shutdown order, process
cleanup, database consistency and background-task handling on
Windows have never been executed. The PowerShell scripts exist
(P-00) and no hidden persistence mechanism exists in code
(inspection: no registry, scheduled-task or service-install code).
This remains an owner-machine activity and a Stage B / pilot
precondition.

## 4. Reliability gaps carried into the defect register

1. **No in-app restore** for backups (P2) — create/verify only.
2. **No standing model/provider health monitoring** (P2).
3. **Circuit breakers are in-memory per process** (carried P-12) —
   a restart resets breaker state; acceptable for single-process
   local-first, recorded (P3).
4. **Single-process shared fate** (architectural observation, P3):
   one crash stops API + workers + scheduler together; recovery is
   restart-based by design.
5. **Backup/recovery for P-09 memory was PARTIAL at its gate** and
   remains so: memory tables are inside the same SQLite backup, but
   no memory-specific restore drill exists (P3).
6. **Event bus is in-process** — events published during a crash
   window before persistence can be lost; critical types persist via
   subscriber, but the bus offers no durable queue semantics
   (details in P14_INTEGRATION_MATRIX.md).
