# P-15 PRODUCTION READINESS REPORT (§13, §18, §20)

## 1. What was built

P-15 adds the **Performance, Reliability & Production Readiness
Engine** on top of the completed P-14 stack, reusing existing
infrastructure throughout (no second scheduler, monitoring stack,
circuit-breaker system, backup system or health page — see the
reuse map in `P15_PERFORMANCE_ASSESSMENT.md`):

- **Schema:** one additive migration `d12e4d6cf5ef` (revises
  `4d41d6a6a605`) adding four governance tables —
  `performance_samples`, `reliability_incidents`,
  `readiness_snapshots`, `benchmark_runs` (176 metadata tables /
  177 physical; upgrade/downgrade cycle-tested; **no money
  columns**; P-07 remains the sole financial authority).
- **Backend package `app/reliability/`:** resource sampler
  (background loop beside the P-12 scheduler, owner settings via
  the existing configuration system), an incident register with
  condition evaluation/deduplication/auto-resolution for
  auto-detected conditions only, the deterministic Production
  Readiness Scorer (§13 weights, critical-issue gate, external-
  blocker withholding), an in-code benchmark suite (baseline
  timing comparisons against the P-14 volume baseline, a
  concurrent read-load probe, functional recovery probes on the
  real P-12 breaker/retry classes and the P-01 dead-letter path),
  stale-backup detection with owner-initiated backup delegated to
  the P-10 service, a financial-reliability read model over P-07
  (trading: **NOT APPLICABLE** — no trading engine exists), a
  stability report computed from real samples only, and the §14
  overview read-model. API: 16 routes under `/reliability/*`.
- **Command Center:** the "Performance & Reliability" section
  (panels A–I) on real endpoints, built to the P-11/P-14 frontend
  patterns; emergency suspend/resume reuses the P-10 endpoints
  with confirmation; no simulated data anywhere.
- **One latent pre-existing defect repaired** (disclosed in the
  changelog and security review): the P-11 dashboard
  `agents_summary()` counted a nonexistent
  `AgentCreationRequest.status` column (the model field is
  `decision`, used correctly elsewhere in the same file) — it
  would have raised on first real use. Fixed minimally, with an
  exact regression test pinning the true counts.

## 2. Verification (final code)

| Suite | Result |
|---|---|
| Backend full regression | **812 passed / 0 failed** in 585.33s (781 P-14 baseline + 31 new P-15 tests); log: `docs/p15/P15_FULL_RUN_LOG.txt` |
| Frontend vitest | **43/43 passed** (40 + 3 new) |
| TypeScript / build | `tsc --noEmit` clean; `npm run build` clean (bundle ships the new view) |
| Live smoke (real uvicorn, controlled mode) | **25 passed / 0 failed** — `docs/reports/P15_SMOKE_EVIDENCE.txt` |
| Migration cycle | upgrade 173→177 physical tables, downgrade restores 173, re-upgrade clean |

An intermediate full run scored 808 passed / 4 failed; all four
failures were the earlier phases' exact alembic-head assertions,
updated to the new head with P-15 disclosure lines in the
established pattern and re-verified before the final run.

## 3. Production Readiness Score (§13)

Two genuine computations from live evidence (raw evidence:
`docs/p15/P15_READINESS_EVIDENCE.json`; benchmark detail:
`P15_BENCHMARK_RESULTS.md`):

- **Live smoke boot (auto-migrated database): overall 85.8** —
  band *Limited production candidate*, critical gate **passed**.
- **In-process evidence run: overall 81.8** — same band and gate.
  Category breakdown of that run:

| Category (weight) | Score | Failed checks and why |
|---|---|---|
| Performance (15) | 80.0 | `resources_under_thresholds` — host memory at 95.7% on the shared staging VM at sample time |
| Reliability (20) | 56.2 | `components_healthy` (Ollama/GPU/browser genuinely unavailable in staging), `no_major_open_incidents` (one real P2 threshold incident open), `task_failure_ratio` neutral (no finished tasks in a fresh app) |
| Fault tolerance & recovery (15) | 70.5 | `circuit_breakers_present` neutral (no breaker exercised yet in a fresh app), `incident_recovery_rate` 0.50 on a two-incident sample |
| Data integrity & backup (15) | **100.0** | ledger integrity + audit chain + verified fresh backup all pass |
| Security & governance (15) | **100.0** | no open security incidents, emergency controls armed, suspended state consistent |
| Observability (10) | **100.0** | monitor, diagnostics, audit chain and sample retention all present |
| Testing & validation (10) | 80.0 | `migration_at_head` — this run's database was created via `create_all` (test harness), so it carries no alembic revision row; the check reported exactly that. On the auto-migrated smoke database the same check passed |

The difference between the two runs is explained by database
creation method and host load at sample time — the scorer
reported what it measured in both cases.

## 4. Classification (§13, §18)

> **READY FOR CONTROLLED PILOT** — production classification
> withheld while external blockers stand.

Justification: both measured scores fall in the 75–89 band
("Limited production candidate") and the critical-issue gate
passes (database healthy, ledger integrity verified, audit chain
verified, no open P0). The §13 withholding rule then applies:
two external blockers — **Windows UNVERIFIED (DEF-A1)** and **no
real LLM ever exercised (DEF-A2)**, both owner-machine items
carried from P-14 — cap the classification at controlled pilot
regardless of score. This is the same classification P-14
reached; P-15's contribution is that it is now *computed*
continuously from evidence instead of asserted once.

Acceptance criteria (§18 of the prompt): every criterion is met
by the evidence above except those that are impossible inside
this staging session, which are reported honestly rather than
passed: long-duration stability windows (24h/72h/7-day) —
**INCOMPLETE**, harness live and running; Windows reliability —
**UNVERIFIED** (owner machine); real-LLM behaviour —
**UNEXERCISED** (owner machine).

## 5. Honest limitations (§20)

- Long-duration tests: INCOMPLETE by design of time; the sampler
  and stability report are live and will complete windows only
  with genuine recorded coverage.
- Windows: design documented (`P15_WINDOWS_OPERATIONS.md`),
  behaviour UNVERIFIED from this Linux staging.
- No real LLM has ever been exercised; provider panels and the
  scorer report probe truth only.
- The load probe is an in-process read-path probe on a shared
  VM — not a production throughput claim. Destructive stress
  (resource exhaustion, crash injection on live processes) is
  deliberately not performed on shared staging.
- No dynamic runtime mutation of production concurrency; queue
  and cache observations are reported, and the one warranted
  code change (the dashboard defect) is disclosed. Optimisation
  claims are limited to "no regression beyond tolerance" —
  P-15's near-empty-database timings are **not** improvements
  over the P-14 volume baseline (see the benchmark report's
  volume caveat).
- No automatic restart or restore automation was added; the
  case for both is argued in the recovery documents, and the
  decision is left to the owner.
- PDF export remains a carried P-11/P-13 gap, unchanged.
- Coverage tooling is not configured in this repository (a P-14
  finding), so no coverage percentage is claimed; the
  testing category scores suite/benchmark/migration evidence
  instead.

## 6. Package

Staging tree packaged as `AUTONOMUS-P15-Staging.zip` (excluding
`.venv` and `node_modules`). Migration head: **`d12e4d6cf5ef`**.
