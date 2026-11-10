# P-15 BENCHMARK RESULTS (§11)

Two measured runs of the in-code suite (`benchmark_runs` table;
runner: `app/reliability/benchmarks.py`):

- **Run A — live smoke** (real uvicorn boot, auto-migrated DB, one
  governed fixture business with ₹10,000 verified revenue):
  transcript `docs/reports/P15_SMOKE_EVIDENCE.txt`.
- **Run B — readiness evidence run** (in-process controlled-mode
  app, fresh DB, one verified backup): raw JSON
  `docs/p15/P15_READINESS_EVIDENCE.json`.

## Baseline timings (median of 3, ms)

| Read path | P-14 baseline (at volume) | Run A | Run B |
|---|---|---|---|
| dashboard_overview | 32.61 | 12.31 | 21.68 |
| dashboard_system_health | 8.27 | 8.48 | 8.32 |
| financial_consolidated | 23.61 | 2.94 | 0.23 |
| journal_page_query_50 | 1.17 | 0.21 | 0.22 |
| memory_search | 147.45 | 3.65 | 3.18 |
| memory_records_page_50 | — (new in P-15) | 0.24 | 0.25 |

**Volume caveat (read before comparing):** the P-14 baseline was
measured against a database seeded to volume (100 businesses,
10,000 journal entries, 10,000 memory records). Runs A and B ran
against near-empty staging databases, so their lower numbers are
**not** performance improvements and are not claimed as such.
What the comparison does establish — and all the readiness
tolerance check asserts — is the absence of *regression*: every
comparable median is within the 2.0× tolerance of the P-14
baseline (worst ratio: system_health at 1.01×). The P-14 volume
run remains the at-scale baseline; re-running the suite against a
volume-seeded database is the correct way to extend it, and the
suite is built to do exactly that unchanged.

## Load probe (§11.2)

24 concurrent in-process dashboard-overview reads (Run B):
p50 7.9 ms, p95 8.3 ms, max 8.83 ms. This is a read-path
concurrency probe on a shared staging VM — evidence that the
aggregation path does not serialise pathologically, **not** a
production throughput claim. Task-queue load behaviour remains
characterised by the P-01/P-12 suites' own tests.

## Recovery probes (§11.4) — all pass, both runs

| Probe | Result | Detail |
|---|---|---|
| Circuit breaker (real P-12 class) | PASS | opens at threshold, half-opens after cooldown, closes on success |
| Retry policy (real P-12 functions) | PASS | classify(timeout) → `temporary_network_failure`; backoff [0.5, 1.0, 2.0, 8.0] monotonic and capped |
| Event-bus dead letter (throwaway P-01 bus) | PASS | a failing handler is recorded as a dead letter, never silently lost |

## Stress surface (§11.3) — observed, not induced

Resource exhaustion is **not induced** on the shared staging VM.
Run B observed: CPU 12.5%, memory 95.7% (host-level, shared VM —
the same pressure that opened a real threshold incident during
the smoke), disk 38.3% used. Provider condition (a genuine outage
condition in staging): Ollama unreachable (connection refused),
cloud disabled — the system reports both unavailable and the
deterministic planner remains the operating path, which is the
§4.4E degradation behaviour working as designed.

## Long-duration (§11.5)

24h / 72h / 7-day windows: **INCOMPLETE** — the sampler harness is
live (proven in a real boot by the smoke: sampler-source samples
exist), and the stability report computes coverage, growth and
stuck tasks from real samples only. No window is claimed until
recorded coverage genuinely spans it.
