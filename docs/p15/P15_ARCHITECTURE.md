# P-15 ARCHITECTURE

## Position in the system

P-15 is reliability *infrastructure* over P-01–P-14, not a new
engine. It introduces exactly one new backend package
(`app/reliability/`), one new API router, four new tables and one
new Command Center section. It owns **no** queue, scheduler,
circuit breaker, backup system, approval store or ledger —
rule §3.5 of the prompt (no duplicate infrastructure) is enforced
by construction and by the P-15 security tests.

## Components

| Component | File | Responsibility |
|---|---|---|
| Constants | `app/reliability/constants.py` | §13 weights, bands, severity scale, priority classes (§4.2), seeded settings defaults, the P-14 baseline medians used for tolerance comparison, standing external blockers (DEF-A1/A2) |
| Readiness engine | `app/reliability/readiness.py` | Pure functions: evidence dict → per-category checks/scores → weighted score, band, critical gate, blockers, recommendations. No I/O — fully unit-tested |
| Benchmark suite | `app/reliability/benchmarks.py` | §11 baseline timings (same read paths P-14 measured), a concurrent read-path load probe, functional recovery probes against the real P-12 breaker/retry classes and a throwaway P-01 bus, and the observed (never induced) stress surface |
| Service | `app/reliability/service.py` | Sampling + persistence, incident detection/lifecycle, evidence assembly, readiness computation/persistence, benchmark runs, delegated backup creation (P-10), the §9 financial read-model, the long-duration stability report, and the §14 overview read-model |
| API | `app/api/routes/reliability.py` | `/reliability/*` — reads under `read_system_data`, writes under `modify_system_config` + in-service owner gates |
| UI | `frontend/src/views/Performance.tsx` | "System Performance & Reliability" (route `performance`, Governance nav section), panels A–I per §14 |
| Sampler loop | `Application.startup` | An asyncio task beside the P-12 operations loop (non-test environments only): record sample → evaluate incidents on the configured cadence. It is the §11.5 long-duration harness. It feeds no queue and controls nothing |

## Data (additive migration `d12e4d6cf5ef`, cycle-tested)

- `performance_samples` — persisted metric samples (resources,
  queue, DB latency/health + full payload JSON).
- `reliability_incidents` — the operational incident register
  (P0–P3): severity, component, kind, lifecycle, root cause,
  response, recovery actions, prevention, evidence.
- `readiness_snapshots` — each computed score with categories,
  failed checks, blockers, recommendations and the full evidence.
- `benchmark_runs` — benchmark executions with raw results.

Settings live in the existing `system_config` table
(`p15_reliability_settings`, P-13 pattern). **No monetary columns
exist in any P-15 table** (asserted by test).

## Reuse map (what P-15 reads or drives, and who still owns it)

| Concern | Owner | P-15 relationship |
|---|---|---|
| Metrics/thresholds/admission | P-01 SystemMonitor | sampled, persisted, reported |
| Task queue | P-01 TaskManager | snapshot read; stuck-task detection |
| Circuit breakers, retry policy | P-12 operations/recovery | states read; classes probed functionally |
| Dead letters | P-12 operations + P-14 event bus | counts read; growth becomes incidents |
| Backups | P-10 BackupService | created/verified through delegation; staleness monitored |
| Emergency controls | P-10 EmergencyService | state read; UI controls call P-10 endpoints directly |
| Audit chain | P-10 AuditChainService | verified as readiness evidence + critical gate |
| Ledger integrity | P-07 LedgerService.verify_integrity | read-only per-business verification |
| Component checks | P-11/P-14 dashboard system_health | consumed as the component-health feed |
| Provider status | P-02 cached probe | displayed as-is; never fabricated |

## Rollback

- Code: remove the package, router registration, assembly block and
  frontend view/nav entry; no earlier module depends on P-15.
- Data: `alembic downgrade 4d41d6a6a605` drops exactly the four
  P-15 tables (cycle-tested both directions).
- The one cross-module repair (dashboard `agents_summary` column)
  is a one-line change documented in the changelog; reverting it
  restores the prior (broken) behaviour without side effects.
