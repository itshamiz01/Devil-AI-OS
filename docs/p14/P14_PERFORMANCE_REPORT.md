# P-14 PERFORMANCE REPORT — Stage A (Audit Only)

**Measurement environment (read this first):** Linux staging VM,
shared vCPU (1.5 vCPU allocation), SQLite database, FastAPI
TestClient in-process. These numbers describe **this VM only**. They
are **not** measurements of the owner's Windows machine (Intel
i7-4712HQ, 16 GB RAM) and no performance target is set or implied —
per §13, targets without the real hardware baseline would be
invented. Raw data: `docs/p14/P14_PERF_MEASUREMENTS.json`, produced
by `backend/tests/test_p14_audit.py::test_p14_api_latency_measurements`
(5 samples per endpoint, fresh-install database, owner-authenticated).

## 1. API response times (measured)

| Endpoint | Median | Max | Notes |
|---|---|---|---|
| GET /api/v1/health/live | 2.8 ms | 27 ms | unauthenticated liveness |
| GET /api/v1/business/businesses | 7.7 ms | 16 ms | empty list |
| GET /api/v1/agents | 6.4 ms | 39 ms | empty list |
| GET /api/v1/financial/overview | 9.4 ms | 36 ms | zero-state consolidated read |
| GET /api/v1/portfolio/portfolios | 11.9 ms | 130 ms | empty list |
| GET /api/v1/operations/overview | 12.2 ms | 41 ms | zero-state |
| GET /api/v1/dashboard/finance/summary | 12.4 ms | 51 ms | P-07-backed aggregation |
| GET /api/v1/dashboard/security/summary | 13.6 ms | 42 ms | P-10-backed aggregation |
| GET /api/v1/memory | 14.5 ms | 46 ms | empty list |
| GET /api/v1/dashboard/overview | 20.3 ms | 824 ms | heaviest read: multi-module aggregation; the 824 ms sample is a cold first hit (import/JIT warm-up on a shared VM), steady-state ≈ 20 ms |

Interpretation: on an empty/fixture database every representative
read is comfortably interactive. **No load or volume testing exists**
— behaviour with thousands of businesses, journal entries or memory
records is UNMEASURED (P2 finding; the schema has indexes per model
definitions but no query-plan audit was performed at scale).

## 2. Test-suite performance (measured)

| Suite | Result | Wall time |
|---|---|---|
| Backend full suite (713 pre-existing + P-14 audit tests) | see P14_REGRESSION_TEST_REPORT.md | see report (single run, tmpfs basetemp + pruner) |
| P-13 gate reference (713 tests) | 713 passed | 492 s at the P-13 gate on this same VM |
| Frontend suite | see P14_REGRESSION_TEST_REPORT.md | — |

The backend suite's ~8-minute wall time on this VM is dominated by
per-test application startup (full service assembly + schema
creation per test). That is a developer-experience cost, not a
runtime property of the product.

## 3. Resource protection — what exists (§13)

| Control | Status |
|---|---|
| Concurrency limits | TaskManager `max_concurrency` + queue `capacity` settings; admission guard blocks non-essential work on resource thresholds (SystemMonitor) |
| Queue limits | Queue capacity enforced in P-01 TaskManager |
| Agent execution timeouts | Per-adapter/process timeouts in P-05 (process controls); workflow-level deadlines in P-12 |
| Memory limits | **No hard process memory limit** — monitoring + admission thresholds only (P3 observation for the owner's 16 GB machine) |
| Model context limits | Profile-level settings in P-02; untestable against a real model (no real LLM) |
| API rate limits | EventBus rate limit per second (setting); HTTP API has **no per-client rate limiting** (P2 finding — local single-user deployment mitigates, but the login endpoint relies on P-10's login guard throttling instead, which does exist and is tested) |
| Resource monitoring | SystemMonitor: CPU/memory/disk via stdlib, threshold violations feed readiness + admission |

## 4. AI infrastructure efficiency — NOT MEASURABLE

Local vs cloud vs hybrid routing efficiency, fallback overhead,
inference cost and model latency **cannot be measured**: no real LLM
provider has ever run in this system (Ollama absent in staging,
cloud adapter is an inert stub, tests use FakeProvider /
deterministic planner). Any numbers here would be fabricated. This
section's honest content is the gap itself (defect register, P1:
no-real-LLM verification gap). On the owner's hardware, prior
feasibility analysis (`docs/reports/AI_HARDWARE_FEASIBILITY.md`)
establishes CPU-only inference with 1–3B Q4 models as the
interactive tier — unmeasured in-product to this day.

## 5. GPU utilization

Not applicable in staging (no GPU visible to this VM) and not
applicable on the owner's machine for inference (Quadro K1100M is
below Ollama's CUDA minimum — P-04 feasibility verdict). The
dashboard honestly reports GPU as `unavailable`.

## 6. Findings

1. **P2** — No volume/load baseline exists for any module; database
   behaviour at realistic data volumes is unverified.
2. **P2** — No HTTP rate limiting on the API surface (login
   throttling exists via P-10's guard; the rest of the surface
   relies on loopback single-user deployment).
3. **P3** — Dashboard overview is the heaviest read (~20 ms
   steady-state empty; grows with module data since it aggregates
   live). No caching layer; acceptable at current scale, watch item.
4. **P3** — No hard memory ceiling for the single process on a
   16 GB target machine; monitoring-only mitigation.

---

## Stage B addendum (2026-11-10) — DEF-A7 volume baseline EXECUTED

Finding 1 above is closed for staging. `scripts/p14_volume_benchmark.py`
seeded a scratch instance with 100 businesses, 10,000 journal
entries (20,000 lines) and 10,000 memory records (direct ORM
inserts, labelled fixtures; this measures read paths at volume, not
workflow throughput) and timed the hot reads, median of 3, SQLite on
this Linux VM:

| Operation | Median |
|---|---|
| Dashboard overview | 32.6 ms |
| Dashboard system health | 8.3 ms |
| Financial consolidated (INR) | 23.6 ms |
| Business list (page 50) | 2.2 ms |
| Journal page query (50) | 1.2 ms |
| Memory search | 147.5 ms |

Notes: the memory-search figure exercises the governed keyword/scan
path — directly seeded rows bypass ingestion, so the semantic
candidate set is empty; treat 147.5 ms as the scan-path ceiling at
10k records, not a vector-search measurement. Seed time for the full
volume was 2.41 s. Raw results: `P14_BENCHMARK_RESULTS.json`.
Windows numbers remain an owner-machine activity (DEF-A1); the
dashboard-overview watch item (finding 3) stands — 32.6 ms at this
volume is acceptable, and the figure now exists to watch against.
