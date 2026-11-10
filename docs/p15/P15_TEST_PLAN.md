# P-15 TEST PLAN (§11 / §18)

## Suites

| Suite | File | Covers |
|---|---|---|
| Unit | `tests/test_p15_unit.py` | §13 scorer as pure functions: weights total 100, band boundaries, healthy evidence, each critical-gate condition (DB down, integrity fail, audit-chain fail, open P0), missing-evidence docking (never inflation), recovery probes |
| Integration | `tests/test_p15_integration.py` | Migration cycle (177 ↔ 173 physical), metadata (+4 tables exactly), sampling persistence, settings seed/update/validation, incident detection dedup + auto-resolution via a real P-10 backup, manual incident lifecycle + validation, readiness compute/persist/history + docking without benchmarks, benchmark run (timings, probes, load, observed stress), stability honesty (windows INCOMPLETE, no stuck tasks), financial read-model on a governed fixture business, overview panels, full HTTP round-trip |
| Security | `tests/test_p15_security.py` | Owner gates (agent/service denied on every write), unauthenticated HTTP (401s), no money columns in P-15 tables, P-07 journal untouched by observation, snapshot gate/blocker recording |
| Frontend | `frontend/src/views/Performance.test.tsx` | All nine §14 panels render the API's values verbatim; INCOMPLETE windows and unavailable providers are never upgraded; external blockers surface; trading NOT APPLICABLE renders |
| Live smoke | `backend/scripts/p15_smoke.py` → `docs/reports/P15_SMOKE_EVIDENCE.txt` | Real uvicorn boot: auth boundary, 177-table schema, zero state, sampler live in a real boot, incident open → backup → auto-resolve, benchmarks, readiness persistence + pilot cap, 403 governance boundary, built bundle contains the new view |

## §18 acceptance mapping

| Requirement | Evidence |
|---|---|
| Monitoring | Sampler + samples table + panels A–E; integration + smoke |
| Resource management | Priority classes + admission/backpressure read-model (P-01 guard reused); overview test |
| Agent reliability | Failed/stuck work visible (panels C/F, stability); P-12 isolation unchanged and regression-green |
| Model reliability | Provider probe truth in panel B; fallback is P-02's existing behaviour; no real LLM claim (DEF-A2 stands) |
| Queue reliability | Recovery probes + P-01/P-12 recovery regression; dedup/idempotency untouched |
| Financial integrity | Read-model verification + non-mutation test + smoke |
| Database reliability | Integrity check in evidence + critical gate; backup create/verify via delegation (test + smoke) |
| Recovery | Benchmark recovery probes against the real classes; startup recovery regression (P-01/P-05/P-12 suites) |
| Windows operation | **UNVERIFIED** — owner-machine pilot item (DEF-A1); design in P15_WINDOWS_OPERATIONS.md |
| Observability | Samples, incidents, dead-letter visibility, structured logs (existing) — observability category self-checks |
| Security | Owner gates + 401/403 tests; §15 review |
| Command Center | Frontend tests + bundle check in smoke |
| Long-duration stability | Harness live (sampler in real boot — smoke-proven); 24h/72h/7d windows **INCOMPLETE** by the §20 rule |
| Production readiness | Score computed from evidence with the critical gate; classification capped at controlled pilot while A1/A2 stand |

## Method notes

- Full-suite runs use a tmpfs basetemp + pruner (the VM's /tmp is
  a 512 MB tmpfs; a full run's temp data exceeds it — see the
  standing operational lesson). Mass fixture errors are checked
  against `df -h /tmp` before being treated as code failures.
- Benchmarks compare against the P-14 baseline with a 2.0×
  tolerance (owner-tunable setting), per §18's "thresholds from
  the actual baseline" rule.
