# P-15 PHASE 1 — ARCHITECTURE & PERFORMANCE ASSESSMENT

**Phase:** P-15 Performance, Reliability & Production Readiness Engine
**Stage:** Phase 1 inspection only — no production code was modified in
this phase. **Date:** 2026-11-10. **Baseline:** P-14 closed (backend
781/781, frontend 40/40, smoke 13/13, §18 READY FOR CONTROLLED PILOT,
migration head `4d41d6a6a605`, 172 metadata tables / 173 physical).

## 1. What already exists (reuse — do NOT rebuild)

| Capability (P-15 §) | Existing owner | Evidence |
|---|---|---|
| System metrics (§4.1) | P-01 `app/monitoring/` — `metrics.resource_snapshot` (psutil: CPU/RAM/disk/process count), `SystemMonitor` (thresholds, admission guard, queue stats, DB health, P-14 provider probe feed), `diagnostics` | `backend/app/monitoring/*.py` |
| Health endpoints | P-01 `GET /health/live`, `/health/ready`, `/health`; `GET /system/status`, `/system/resources` | `api/routes/health.py`, `system.py` |
| Task queue + scheduler | P-01 `TaskManager`/`TaskQueue` (capacity, concurrency, retry with backoff settings, `recover_interrupted()` pauses interrupted tasks for operator review, queue `snapshot()` by status) | `app/tasks/` |
| Circuit breakers (§4.4C) | P-12 `operations/recovery.CircuitBreaker` (closed/open/half-open, threshold + cooldown), failure classification + retry eligibility/delay in the same module | `app/operations/recovery.py` |
| Dead letters (§5) | P-12 `OperationsDeadLetter` + P-14 durable `EventDeadLetter` (event bus) | models/operations.py, models/core.py |
| Recovery | P-05 `recover_interrupted()` (marks INTERRUPTED, never blindly repeats), P-12 `recover_interrupted()` (parks workflows RECOVERY_PENDING), P-01 task recovery | application.py startup |
| Backup (§6.2) | P-10 `security/backup.BackupService` — create/verify/list, SHA-256, table inventory; guarded restore **preview** (P-14 A4; execution is the owner's manual step) | `app/security/backup.py` |
| Emergency controls (§9.3/§14I) | P-10 `security/emergency.EmergencyService` — operating mode, financial suspension, event history; audit chain (`security/audit_chain.verify()`) | `app/security/` |
| Ledger integrity (§9) | P-07 `financial/ledger.verify_integrity(business_id)`, `reports.reconciliation_report` | `app/financial/` |
| Monitoring UI (§14 partial) | P-11 Operations view (`/system/status`, execution health, backups, audit) + P-14 System Health panel in dashboard `system_health()` (checks, resources, per-module states, dead-letter count) | `frontend/src/views/Operations.tsx`, `app/dashboard/service.py` |
| Provider status | P-02 `IntelligenceService.models_status()` / `cached_models_status()` (ollama + cloud stub) | `app/intelligence/` |
| Settings pattern | `SystemConfig` table + `ConfigRepository` (P-13/P-12 seed/get/update settings, owner-gated writes) | models/core.py |
| Benchmark baseline | P-14 volume run: 100 businesses / 10k journal entries / 10k memory records — overview 32.6 ms, system_health 8.3 ms, financial consolidated 23.6 ms, business list p50 2.2 ms, memory search 147.5 ms, journal page 1.2 ms (median of 3, SQLite on this Linux VM) | `docs/p14/P14_BENCHMARK_RESULTS.json` |

## 2. Gaps P-15 must fill (nothing above provides these)

1. **No performance history.** Metrics are on-demand snapshots only;
   nothing samples or persists them, so trends, growth and degradation
   over time are invisible. → P-15 sampler + `performance_samples`.
2. **No incident register.** P-10 has *security* alerts/incidents;
   there is no operational incident record (P0–P3 per §10) tying
   detection → response → recovery → resolution for reliability
   events (threshold breaches, open breakers, dead-letter growth).
   → P-15 `reliability_incidents`, detection evaluator, lifecycle.
3. **No Production Readiness Score.** P-14 produced a one-off audit
   classification, not a computed, evidence-based score (§13 weights).
   → P-15 readiness engine + `readiness_snapshots`.
4. **No repeatable benchmark harness in code.** P-14 benchmarks were
   an audit script + JSON artefact. → P-15 benchmark runner +
   `benchmark_runs` (baseline/load/stress-lite/recovery probes).
5. **No long-duration stability harness.** 24h/72h/7d runs have never
   been executed. → the sampler doubles as the harness; a stability
   report computes coverage/growth/stuck-work from real samples and
   reports INCOMPLETE until real elapsed coverage exists (§11.5/§20).
6. **No unified reliability read-model for the Command Center §14
   panels A–H** (live health, AI infra, agents, businesses, queues,
   reliability, data protection, readiness in one place).
   → `ReliabilityService.overview()` + new frontend section.
7. **Backup staleness is unmonitored** (backups exist; nobody notices
   if they stop). → evaluator raises an incident past the policy
   window; readiness data-protection category consumes backup state.

## 3. Design decisions (bounded, reuse-first)

- **One new package** `app/reliability/` (constants, readiness
  scoring as pure functions, benchmarks, service). No new scheduler:
  the sampler runs as an asyncio task beside the P-12 operations loop
  and feeds nothing into queues. No new circuit breakers: P-12's are
  read. No new backup system: P-10's is driven and monitored.
- **Four new tables only** (additive migration, cycle-tested):
  `performance_samples`, `reliability_incidents`,
  `readiness_snapshots`, `benchmark_runs`. **No money columns.**
  Settings via the existing `SystemConfig` pattern (owner-gated).
- **Readiness scoring (§13 weights)** computed from live evidence
  only: resources/thresholds, component checks, incident register,
  breaker states, startup-recovery records, DB integrity check
  (`PRAGMA integrity_check`), P-10 backup state + audit-chain
  verification, P-07 ledger integrity on fixture/business scope,
  observability self-checks, and in-system validation self-checks.
  Pytest results are reported in the readiness *report document* as
  external evidence — the in-app score never claims test results it
  cannot observe. Critical gate: DB unhealthy/integrity failure,
  audit-chain failure, or an open P0 incident caps classification at
  NOT PRODUCTION READY regardless of score. Standing external
  blockers (Windows unverified DEF-A1, no real LLM DEF-A2) are
  surfaced and cap the *effective* classification at controlled
  pilot, consistent with P-14 §18.
- **Controls (§14I)** delegate, never duplicate: financial suspension
  and mode changes stay P-10 endpoints; P-15 adds incident resolve,
  owner-triggered backup (via P-10 service), sampling and benchmark
  runs — all behind existing permissions, owner-only for writes.
- **Financial reliability (§9)** is a read-model over P-07
  `verify_integrity` + P-10 suspension state. No trading exists in
  the platform; broker/order items are NOT APPLICABLE and are stated
  as such — nothing is invented.

## 4. Honest constraints carried into the build

- Long-duration tests (24h/72h/7d) **cannot complete in this
  session** → harness + INCOMPLETE verdicts (§20 rule).
- Windows behaviour **UNVERIFIED** from Linux staging (DEF-A1).
  §7 Windows service management is delivered as design + the
  platform-agnostic supervision that exists (lifecycle, recovery);
  no Windows service is installed or claimed.
- No real LLM has ever been exercised (DEF-A2): model panels show
  provider probe truth (ollama not running in staging → unavailable;
  deterministic planner noted), never fabricated latency.
- GPU telemetry does not exist (P-14 finding stands): shown
  unavailable, never invented.
