# P-15 IMPLEMENTATION CHANGELOG (§19 record)

## Existed before P-15 (unchanged, now observed)

P-01 monitor/queue/lifecycle/logging; P-02 provider probes; P-05
and P-12 startup recovery; P-12 circuit breakers, retry policy and
dead letters; P-10 backups, emergency controls, audit chain,
security monitoring; P-07 ledger integrity and reconciliation;
P-11/P-14 dashboard system-health aggregation. See
P15_PERFORMANCE_ASSESSMENT.md for the full reuse map.

## Added

- `backend/app/reliability/` — `constants.py` (§13 weights/bands,
  §4.2 priority classes, settings defaults, P-14 baselines,
  external blockers), `readiness.py` (pure §13 scorer with the
  critical gate), `benchmarks.py` (§11 suite: baseline timings,
  read-path load probe, functional recovery probes, observed
  stress surface), `service.py` (sampler, incident evaluator +
  register lifecycle, evidence assembly, readiness persistence,
  benchmark runs, delegated backups, financial read-model,
  stability report, §14 overview).
- `backend/app/database/models/reliability.py` — four tables:
  `performance_samples`, `reliability_incidents`,
  `readiness_snapshots`, `benchmark_runs`. No money columns.
- Migration `d12e4d6cf5ef` (down_revision `4d41d6a6a605`),
  additive, cycle-tested.
- `backend/app/api/routes/reliability.py` — `/reliability/*`
  (overview, samples, evaluate, incidents CRUD/lifecycle,
  readiness + compute, benchmarks, backups, financial, stability,
  settings).
- Frontend: `views/Performance.tsx` (§14 panels A–I), route
  `performance`, nav item "Performance & Reliability"
  (Governance), `views/Performance.test.tsx` (3 tests).
- Tests: `tests/p15_support.py`, `test_p15_unit.py` (10),
  `test_p15_integration.py` (15), `test_p15_security.py` (6) —
  31 new backend tests.
- Smoke: `backend/scripts/p15_smoke.py` (25 checks) →
  `docs/reports/P15_SMOKE_EVIDENCE.txt`.
- Docs: this set under `docs/p15/` (14 documents per §19).

## Modified (each with its justification)

- `backend/app/core/application.py` — assemble ReliabilityService
  after P-13, seed its settings, start/stop the sampler loop
  beside the P-12 loop (non-test environments). *Justification:
  the sampler must share the application lifecycle; no existing
  behaviour changes.*
- `backend/app/main.py` — register the reliability router.
  *Justification: new API surface only.*
- `backend/app/database/models/__init__.py` — register the four
  new models. *Additive.*
- `backend/app/dashboard/service.py` — **one-line defect repair**:
  `agents_summary` counted `AgentCreationRequest.status`, a column
  that does not exist (the model carries `decision`; the same file
  already uses `.decision` correctly elsewhere). The endpoint
  would have raised AttributeError on first real use; no earlier
  test ever called it (P-11's test asserts route existence only).
  Found by P-15's agent-monitoring panel, fixed minimally to
  `.decision`, output key unchanged for frontend compatibility,
  now covered by the P-15 overview test. *This is the same class
  of repair as P-14's F1: a latent bug surfaced by a new consumer.*
- Earlier-phase tests (`test_p11_integration.py`,
  `test_p12_integration.py`, `test_p13_integration.py`,
  `test_p14_audit.py`) — exact table-count assertions updated
  172 → 176 (physical 173 → 177) with P-15 disclosure comments,
  following the established P-13/P-14 disclosure pattern. No
  assertion was weakened; counts remain exact.
- Earlier-phase tests (`test_p02/03/04/05_integration.py`) — the
  exact alembic-head assertions advanced `4d41d6a6a605` →
  `d12e4d6cf5ef` with P-15 disclosure lines appended to the
  existing disclosure chain (the same update every phase since
  P-03 has made). Strictness unchanged.

## Not implemented (explicit, per §20)

- Long-duration 24h/72h/7d runs — harness live, verdicts
  INCOMPLETE until real coverage exists.
- Windows service packaging/auto-start — owner-machine pilot
  (DEF-A1); design documented.
- Dynamic concurrency mutation of the live TaskManager —
  governance-sensitive; reported as a limitation with the safe
  path (owner-set P-01 settings).
- Automatic worker restarts and automatic backup restore
  execution — deliberately owner/operator actions (§4.5).
- Real LLM performance figures — no provider has ever been
  exercised (DEF-A2); panels show probe truth only.
- PDF export (carried platform gap from P-07/P-11) — untouched.
