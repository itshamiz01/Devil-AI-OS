# P-14 REPAIR LOG — STAGE B (CONTROLLED REPAIRS)

**Status: COMPLETE — Stage B closed 2026-11-10.** Stage A audit completed and
owner review held; the owner approved Stage B on 2026-11-10, including
the auditor's minimal conservative options for DEF-I5 (permission
wiring) and DEF-E1 (evaluation path). Repairs were applied in severity
order per P-14 §17 (reproduce → root cause → minimal repair →
regression evidence). This log records, per defect ID from
P14_DEFECT_REGISTER.md: outcome, the minimal repair applied, and
evidence. Items verified against the landed code by file inspection
are marked **REPAIRED (code-verified)**; full-suite regression
evidence is appended at the end of this log when the completion run
finishes. Migration for this stage (additive only):
`4d41d6a6a605_p14_stage_b_repairs.py` (down_revision `d02b4208d228`).

---

## P1 — HIGH

### P14-DEF-I1 — Security / portfolio-risk events on the bus — REPAIRED (code-verified)
- Added `SECURITY_INCIDENT_DETECTED` and `PORTFOLIO_RISK_DETECTED`
  EventTypes (`backend/app/events/events.py:128-129`), both added to
  `CRITICAL_EVENT_TYPES` (events.py:162).
- Publish sites: incident creation in `backend/app/security/service.py`;
  portfolio risk creation in `backend/app/portfolio/intelligence.py`.

### P14-DEF-I2 — Event envelope completed — REPAIRED (code-verified)
- `Event` dataclass extended with optional `business_id`,
  `workflow_id`, `schema_version=1`, `actor`
  (`backend/app/events/events.py`, `bus.py`); the bus stamps the
  correlation ID from the ambient contextvar when unset, and the HTTP
  middleware sets that contextvar from the request correlation ID
  (`backend/app/main.py`).
- Persisted envelope: `system_events` gains `business_id`,
  `workflow_id`, `processing_status` (migration 4d41d6a6a605);
  exposed by the events API (`backend/app/api/routes/events.py`).

### P14-DEF-D2 — Timestamp naive/aware mismatch — REPAIRED (code-verified, per register's minimal proposal)
- Standardised on the register's proposed repair — re-attach UTC at
  repository reads — NOT a schema flip (which the register notes is
  cosmetic on SQLite). Single shim `as_utc()` in
  `backend/app/database/models/base.py`, applied at the audited
  comparison sites: `permissions/approvals.py` (approval expiry),
  `core/auth.py` (session expiry), `agents/capabilities.py`, and the
  P-12 site that originated the pattern.

### P14-DEF-A1 — Windows compatibility UNVERIFIED — BLOCKED (owner machine)
- Not repairable from Linux staging. Remains an owner-machine item:
  run the P-00 environment audit + PowerShell launchers on the target
  Windows machine, then a Windows smoke pass. Carried into the
  production readiness report as an open critical-path item.

### P14-DEF-A2 — No real LLM exercised — BLOCKED (owner machine / decision)
- Not a code repair. Requires the owner's machine (local Ollama,
  CPU-tier per the P-04 feasibility verdict) running the P-02
  acceptance set against a real model, and/or configuring one cloud
  provider. Carried into the readiness report.

## P2 — MEDIUM

### P14-DEF-F1 — Portfolio gross collected revenue reported 0 — REPAIRED (code-verified)
- Root cause (Stage A): `portfolio/finance.py` read
  `revenue.get("collected_minor")`, a key P-07 never returns; the
  fallback silently yielded 0.
- Repair: reads P-07's `collected_gross_minor` key
  (`backend/app/portfolio/finance.py`, with the audit comment inline).
  P-07 books and semantics untouched (P-07 remains sole financial
  authority). The Stage A xfail in
  `backend/tests/test_p14_financial.py` was removed — the test must
  now PASS in the full regression.

### P14-DEF-I3 — Financial events persisted — REPAIRED (code-verified)
- `FINANCIAL_JOURNAL_POSTED` and `FINANCIAL_REVENUE_VERIFIED` added
  to `CRITICAL_EVENT_TYPES` (`events/events.py`); publish sites in
  `financial/ledger.py`, `financial/revenue.py`,
  `financial/service.py`.

### P14-DEF-I4 — Event-bus dead letter — REPAIRED (code-verified)
- New `event_dead_letters` table (migration 4d41d6a6a605; model in
  `database/models/core.py`, exported in `models/__init__.py`).
  Failed subscriber deliveries and dropped critical events are
  recorded durably by `events/bus.py` / `events/subscribers.py`
  instead of count-and-forget.

### P14-DEF-I5 — PermissionBroker consumed only by P-12 — REPAIRED (completion run)
- Owner-approved option: permission wiring (not merely documenting
  the two-path model). Wiring P-05 execution submission through the
  P-10 PermissionBroker via a late-attached broker handle (the same
  late-attach pattern Stage B used for DEF-I6/E1/E2, since P-10 is
  assembled after P-05). Full details in the completion-run addendum
  below (hard gates enforced, risk gates consulted/recorded —
  evidence-based semantics decision documented there).

### P14-DEF-I6 — Outcome feed into P-09 — REPAIRED (code-verified)
- Outcome-ingestion calls added at completion points, reusing the
  existing P-09 ingestion service (no new store):
  `execution/service.py` (completed executions, late-attached
  `outcome_ingestor`, best-effort — feeding failures are logged,
  never raised into the execution path), `business/service.py`,
  `financial/revenue.py`, `financial/service.py`; assembly wiring in
  `core/application.py`.

### P14-DEF-I7 — BusinessUpdated event — REPAIRED (code-verified)
- `BUSINESS_UPDATED` EventType added (`events/events.py`); published
  for non-status business mutations from `business/service.py`.

### P14-DEF-D1 — Float money columns — REPAIRED (code-verified)
- Additive migration 4d41d6a6a605: `research_briefs.budget_minor` and
  `business_declarations.budget_cap_minor` (BIGINT) added and
  backfilled with `round(amount * 100)`; Float columns retained as
  deprecated; models updated (`database/models/opportunities.py`,
  `database/models/business.py`) and readers/writers prefer the
  `*_minor` values (`opportunities/service.py`,
  `business/service.py`). P-07 ledger untouched.

### P14-DEF-D3 — Missing foreign keys — REPAIRED (width-matching subset, code-verified)
- Migration 4d41d6a6a605 adds canonical FKs where widths match:
  `journal_entries.counterpart_business_id` → `businesses.id`,
  `journal_entries.approval_id`, `expense_records.approval_id`,
  `spending_requests.approval_id` → `approvals.id` (model change in
  `database/models/financial.py`). Remaining FK-less references are
  the documented intentional soft references (polymorphic principals,
  correlation/external IDs) per P14_DATA_ARCHITECTURE.md.

### P14-DEF-D4 — Free-text business references — REPAIRED (write-side validation, code-verified)
- Per the register (constrain new writes; never silently rewrite
  stored refs): service-layer validation now requires a supplied
  `business_ref` to reference an existing business (canonical IDs
  only) at agent requirement creation/update
  (`agents/service.py`) and the corresponding security-layer write
  path (`security/service.py`). Stored historical refs untouched.

### P14-DEF-E1 — P-02 consumes P-03 opportunities — REPAIRED (code-verified)
- Owner-approved option: the thin evaluation path.
  `IntelligenceService.assess_opportunity()` consumes P-03's own
  evaluation report + latest score (scoring stays in P-03 — no
  duplicated engine), records a P-02 decision record and publishes a
  decision event (`intelligence/service.py`); P-03 handle
  late-attached by the assembly (`core/application.py`), exposed via
  `api/routes/intelligence.py`. Unattached handle fails with a
  plain-language error (honest degradation).

### P14-DEF-E2 — P-02 planning retrieves P-09 memory — REPAIRED (code-verified)
- `MemoryService` wired into mission context building:
  `intelligence/context.py` gains `attach_memory(...)`;
  `IntelligenceService.attach_memory()` delegates; assembly attaches
  the handle post-construction (`core/application.py`). Retrieval
  remains scoped by the existing P-09 classification rules.

### P14-DEF-A3 — §14 unified monitoring view — REPAIRED (completion run)
- Backend: `DashboardService.system_health()` now also returns
  `resources` (CPU/memory/disk utilisation + threshold violations,
  sourced from the P-01 system monitor), `modules` (per-module health
  derived mechanically from the checks' P-xx source tokens, worst
  state wins) and `event_dead_letters` (the DEF-I4 durable count).
- Frontend: the Overview System-health panel renders a resource
  utilization line, the per-module health list, and a dead-letter
  warning when the count is non-zero
  (`frontend/src/views/Overview.tsx`, types in `lib/types.ts`).
  Verified live in the completion-run smoke.

### P14-DEF-A4 — In-app backup restore — REPAIRED (guarded preview; execution stays the documented manual procedure)
- Guarded restore preview added (`security/service.py`
  `restore_preview`, route + schema in `api/routes/security.py`,
  `api/schemas/security.py`): owner-only; backup must verify (hash +
  inventory + integrity); requires an approved, hash-bound P-01
  approval for `security.restore_backup` (verified read-only through
  the existing binding check — the facade never decides approvals);
  a fresh pre-restore snapshot is taken first; the plan is audited.
- `executed` is always False: the application never overwrites a
  live database; the file swap remains the owner's manual step per
  the incident-response playbook §5. This is the register's guarded
  endpoint option, with execution deliberately retained as the
  rehearsed manual procedure.

### P14-DEF-A5 — AI-provider health monitoring — REPAIRED (code-verified)
- Provider probe with a 60-second cache in
  `intelligence/service.py` (`models_status` path); the cached probe
  result feeds `monitoring/system_monitor.py` via the assembly
  (`core/application.py`), so the dashboard `ai_provider` state
  reflects standing provider health, not only call-time failures.

### P14-DEF-A7 — No volume/load baseline — REPAIRED (completion run)
- Seeded-volume benchmark executed on staging:
  `scripts/p14_volume_benchmark.py` (100 businesses, 10,000 journal
  entries / 20,000 lines, 10,000 memory records; direct ORM seeding,
  honestly labelled as measuring read paths, not workflow
  throughput). Results: `docs/p14/P14_BENCHMARK_RESULTS.json`,
  summarised in the completion-run addendum. Windows numbers remain
  an owner-machine activity (DEF-A1).

### P14-DEF-A8 — No real-world data validation — BLOCKED (owner-supervised pilot)
- Not a code defect; a verification absence. Requires one real
  opportunity carried through the governed path under owner
  supervision (pilot activity). Carried into the readiness report.

### P14-DEF-C1 — Carried P2 limitations — CARRIED (accepted, re-verified still true)
- PDF export NOT IMPLEMENTED (P-07/P-13/P-11 disclosures unchanged).
- P-05 code execution remains process controls, not a strong sandbox
  (self-labelled in code).
- ChromaDB NOT IMPLEMENTED — P-09's SQLite adapter + local-hash
  embedder remain the shipped substitute.
- Encryption at rest remains partial (no encryption layer; scrypt
  hashes, hashed session tokens, secrets never stored).
- Stripe REQUIRES OWNER CONFIGURATION (interface + fake only) —
  owner action, not a code repair.
- None of these were silently "fixed"; each remains disclosed in
  product UI/code exactly as at its own gate.

## P3 — LOW

| ID | Outcome |
|---|---|
| I8 | ACCEPTED/documented — no retention policy added; `system_events` volatility documented here and in the readiness report (scheduled prune via P-12 time triggers remains a pilot-hardening candidate). |
| I9 | ACCEPTED — documentation note only (Stage A verified zero file-level cycles); no Stage B action per register. |
| I10 | ACCEPTED — canonical stores documented in P14_DATA_ARCHITECTURE.md (Stage A); consolidation is a future decision, not a repair. |
| I11 | REPAIRED (code-verified) — EXECUTION_* event payloads now carry `agent_id` + originating `task_id` (`execution/service.py`). |
| D5 | ACCEPTED/documented — application-level exact-hash dedupe retained; no DB uniqueness added (register: unique index *or* accept + document, owner decision). Concurrent-ingest race remains a documented limitation. |
| D6 | ACCEPTED/documented (completion-run decision) — no upstream idempotency keys added: the P-07 journal (the financial authority) already enforces idempotency via its hash chain + duplicate detection, covered by P-07/P-14 financial tests. Adding creation-path keys would modify P-07-adjacent paths during a repair stage, against §17 minimality. Residual risk low, recorded here. |
| D7 | ACCEPTED/documented — VARCHAR temporal fields treated as display-only until a future planned migration. |
| D8 | ACCEPTED — canonical query paths documented in P14_DATA_ARCHITECTURE.md §3 (Stage A). |
| S1 | REPAIRED (code-verified) — dev token honoured ONLY when no admin password hash exists (`core/auth.py`); previously it was silently accepted in password mode too. |
| S2 | ACCEPTED/documented (completion-run decision) — no permission change: secret *values* never enter this store; the listing exposes only masked hints on an owner-gated surface. Tightening the route permission was judged riskier than the residual exposure (could break the Operations view's service-token contexts). Recorded as a P-15 hardening candidate. |
| E3 | ACCEPTED — documented as the accepted design (pre-creation feasibility is P-03 commercial analysis via P-06 eligibility). |
| E4 | ACCEPTED — no auto-registration subscriber added (register decision item); P-13 portfolio registration remains a manual governed owner call. |
| A6 | ACCEPTED — no HTTP rate limiting added; login throttling via P-10 stands. Noted for pilot hardening in the readiness report. |
| C2 | CARRIED — MFA recovery codes NOT IMPLEMENTED (accepted limitation from P-10 gate). |
| C3 | CARRIED — audit hash chain tamper-EVIDENT, not tamper-proof (accepted design). |
| C4 | CLOSED (completion run) — dependency vulnerability scan RUN: pip-audit 2.10.1 over `backend/requirements.txt` (34 packages): **no known vulnerabilities found**. Raw output: `docs/p14/P14_PIP_AUDIT.json`. |
| C5 | CARRIED — rendered-viewport responsive checks NOT EXECUTED (no headless browser in staging); owner-machine/tooling item. |
| C6 | CARRIED — EXECUTE_WITH_LIMITS caps remain recorded decision evidence, not enforced quotas; circuit breakers in-memory per process (disclosed design limits). |
| C7 | CARRIED — capacities/risk scores/scaling thresholds uncalibrated; calibration requires real operating data (pilot). |

---

## Completion-run addendum

### DEF-I5 — wiring and the semantics decision (evidence-based)

Implementation: `ExecutionService` gained a late-attached
`permission_broker` handle (`backend/app/execution/service.py`,
`_broker_gate()`), wired by the assembly immediately after the
security subsystem is seeded (`backend/app/core/application.py`:
`self.execution.permission_broker = self.security.broker`) — the
same late-attach pattern used for I6/E1/E2, because P-10 is
assembled after P-05.

Semantics, decided from evidence rather than preference: the broker
returns a composed decision with two gate families. The **hard
gates** (operating mode, agent restriction, business scope,
permission-engine verdict, internal checks) are *enforced* — a
failure rejects the submission with the broker's reason, and the
broker's decision id is recorded on the execution audit. The **risk
gates** (capability/approval classification) are *consulted and
recorded* in the broker's decision ledger but do not themselves
hold or deny: P-05's own §8 risk table plus the hash-bound P-01
approval machinery remains the approval authority for tool actions.

Why: a live probe (throwaway script, since removed) proved the
alternative deadlocks the system. The broker's ACTION_RISK table
classifies P-12 *action classes*; unlisted P-05 tool actions default
to CRITICAL, so enforcing broker risk gates made even
`filesystem.mkdir` demand a Level-3 owner approval and parked the
P-06 business-creation workflow at AWAITING_APPROVAL — a repair
that breaks a verified workflow is not a repair. Extending the
broker's risk table to cover tool actions was rejected as an
Article 0 security-policy change, out of scope for a repair stage.
Regression evidence: `tests/test_p14_stageb_repairs.py` — a
suspended agent's submission is REJECTED through the broker
restriction gate; a legitimate submission is QUEUED with an
allowed, ledgered broker decision. The full P-05/P-06 suites pass
unchanged.

### Defects introduced by the earlier Stage B run — found and fixed here

The earlier run was never regression-tested; the completion run
found five defects in its landed code and fixed each minimally:

1. `intelligence/service.py` — the constructor assignments for
   `_baseline/_validator/_router` had been swallowed into
   `attach_memory()`, so application startup crashed
   (AttributeError from `agents/service.py`). Restored to
   `__init__` against the P-13 baseline.
2. `financial/ledger.py`, `financial/revenue.py` — missing
   `EventType` import; every journal post raised NameError at the
   I3 publish site. Import added.
3. `intelligence/context.py` — `_recall` read a non-existent
   `summary` key from P-09 result rows (recall always failed).
   Now derives the summary from `content`.
4. `intelligence/service.py` — `assess_opportunity` read
   `score.overall_score`; P-03's field is `weighted_score` (the
   report maps it to "overall_score"). Fixed.
5. Migration-head pins in pre-existing tests
   (test_p02/test_p03/test_p04/test_p05) still pointed at the P-13
   head; updated to `4d41d6a6a605` with P-14 disclosure comments,
   per project convention. The P-05 migration-cycle test
   (upgrade → head → downgrade → exact table set → upgrade) passes
   against the Stage B migration — the cycle evidence for this
   stage's one additive migration.

### Stage A probe tests updated for repaired behaviour

- `tests/test_p14_e2e.py` scenario_01 §1c now exercises
  `IntelligenceService.assess_opportunity()` (E1) and asserts the
  decision record cites P-03's own score; scenario_02 now exercises
  real memory recall through `build_context()` (E2). Both carry
  Stage B disclosure comments; no assertion was weakened.
- Five exact table-count pins (P-11/P-12/P-13 metadata counts,
  P-13 migration cycle, P-14 audit metadata count) were made stale
  by the single new `event_dead_letters` table; each was updated by
  exactly +1 with a P-14 Stage B disclosure comment, strictness
  preserved. The P-13 migration-cycle test doubles as this stage's
  full-chain cycle evidence (173 physical tables at head).

### DEF-A7 — benchmark results

`scripts/p14_volume_benchmark.py` → `P14_BENCHMARK_RESULTS.json`:
100 businesses, 10,000 journal entries / 20,000 lines, 10,000
memory records; median-of-3 read timings — dashboard overview
32.6 ms, system health 8.3 ms, financial consolidated 23.6 ms,
business list (50) 2.2 ms, journal page (50) 1.2 ms, memory search
147.5 ms (governed scan path; see the results file's honesty
notes). Addendum also appended to P14_PERFORMANCE_REPORT.md.

### DEF-C4 — dependency scan

pip-audit 2.10.1 over `backend/requirements.txt` (34 packages):
**no known vulnerabilities found** (`P14_PIP_AUDIT.json`).

### Regression and smoke (final code)

- First Stage B full run: **776 passed, 5 failed** — all five the
  exact-count pins described above. After the pin updates, the
  final confirmation run on final code: **781 passed, 0 failed,
  0 xfailed in 561.68s** (`P14_STAGE_B_FINAL_RUN_LOG.txt`) — the
  Stage A baseline (774 passed + 1 xfailed) is beaten on both axes:
  more tests, and the F1 xfail is now an outright pass.
- Frontend: **40/40** passed; strict build clean.
- Live smoke (real uvicorn, controlled mode): **13/13**
  (`P14_SMOKE_EVIDENCE.txt`), including portfolio finance gross ==
  net == ₹10,000 over HTTP (the F1 proof; the P-13 smoke showed
  gross 0) and the built Command Center serving the Stage B
  System-health surface.

**Status: STAGE B COMPLETE** (2026-11-10). Final regression:
backend 781 passed / 0 failed / 0 xfailed, frontend 40/40, live
smoke 13/13. §18 classification: READY FOR CONTROLLED PILOT
(`P14_PRODUCTION_READINESS_REPORT.md`).
