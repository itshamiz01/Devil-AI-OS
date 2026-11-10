# P-14 DEFECT REGISTER — Stage A (Prioritized)

**Rules applied:** every entry is reproduced or evidenced in Stage A;
nothing here was repaired (repairs are Stage B, after owner review).
Severity per P-14 §17. IDs: **I** = integration, **D** = data,
**F** = financial, **S** = security, **E** = end-to-end gaps,
**A** = audit-level findings, **C** = carried-forward limitations
from P-01–P-13 gates, each re-verified against current code in
Stage A.

## Totals

| Severity | Count | IDs |
|---|---|---|
| **P0 CRITICAL** | **0** | — (no unauthorized financial activity, no cross-business leakage, no credential exposure, no security bypass, no destructive unauthorized execution was found by any probe) |
| **P1 HIGH** | **5** | I1, I2, D2, A1, A2 |
| **P2 MEDIUM** | **17** | I3, I4, I5, I6, I7, D1, D3, D4, F1, E1, E2, A3, A4, A5, A7, A8, C1 |
| **P3 LOW** | **19** | I8, I9, I10, I11, D5, D6, D7, D8, S1, S2, E3, E4, A6, C2, C3, C4, C5, C6, C7 |

---

## P1 — HIGH

### P14-DEF-I1 — Security and portfolio-risk events do not exist on the bus
- **Modules:** P-10, P-13 → P-01 EventBus consumers (incl. P-12 event triggers).
- **Evidence:** no `SecurityIncidentDetected` or `PortfolioRiskDetected` EventType and no publish site (P14_INTEGRATION_MATRIX.md §3); incidents and risk findings are database rows only.
- **Impact:** the two highest-signal safety events in the system are invisible to event-driven consumers; a P-12 trigger can never react to a security incident.
- **Proposed minimal repair (Stage B):** add both EventTypes, publish at incident creation (`security/service.py`) and P-13 risk creation, add both to `CRITICAL_EVENT_TYPES`.

### P14-DEF-I2 — Event envelope is missing 5 of 10 §6 fields
- **Modules:** P-01 EventBus (all publishers).
- **Evidence:** envelope has event_id, type, source, timestamp (aware UTC); correlation_id is optional and the bus never auto-populates it; **business_id, workflow_id, payload schema version, authorization context and processing status do not exist** (P14_INTEGRATION_MATRIX.md §3).
- **Impact:** §14's traceability chain (USER REQUEST → WORKFLOW → TASK → AGENT → TOOL → RESULT) cannot be reconstructed from events alone for business-scoped activity.
- **Proposed minimal repair:** extend the `Event` dataclass with optional `business_id`, `workflow_id`, `schema_version=1`, `actor`; stamp correlation ID from the existing contextvar when unset.

### P14-DEF-D2 — Timestamp schema/runtime mismatch (320 naive columns)
- **Modules:** platform-wide (all `TimestampMixin` tables).
- **Evidence:** 320 `DateTime(timezone=False)` columns vs 64 timezone-aware, while the runtime's `utcnow()` is aware UTC (P14_DATA_ARCHITECTURE.md). P-12 already needed re-attachment shims (`operations/scheduling.py:27-36`) after a real defect of this class at its gate.
- **Impact:** any module comparing a DB-read datetime against `utcnow()` without a shim risks naive/aware `TypeError` or silent mis-ordering; P-12 is patched, others are exposed by inspection.
- **Proposed minimal repair:** audit every datetime comparison at repository reads and standardise on re-attaching UTC there (as P-12 does). A schema flip to `timezone=True` is cosmetic on SQLite and must not be mistaken for the fix.

### P14-DEF-A1 — Windows compatibility is UNVERIFIED
- **Modules:** platform (P-00 carry-over).
- **Evidence:** the locked primary platform has never run the system; PowerShell launchers never executed on Windows; DPAPI/Credential Manager interface-only. All Stage A verification is Linux staging.
- **Impact:** blocks any production readiness classification (§18 rule) and the owner's actual deployment.
- **Proposed minimal repair:** owner-machine activity, not code: run the P-00 environment audit + scripts on the target Windows machine, then a Windows smoke pass. Stage B cannot close this from staging.

### P14-DEF-A2 — No real LLM has ever been exercised
- **Modules:** P-02 (and every consumer of its LLM path).
- **Evidence:** Ollama probe-tested only against an absent server (P-02); cloud adapter is an inert stub; all intelligence tests use FakeProvider/deterministic planner; P-14 orchestration probes re-confirm (dead-provider → baseline fallback works; no live-provider behaviour exists to test).
- **Impact:** the "hybrid AI" half of the locked architecture is an unproven interface; model failure modes, output quality, latency and cost are all unknown.
- **Proposed minimal repair:** owner decision + configuration: run a real local Ollama model on the target machine (CPU-tier per the P-04 feasibility verdict) and execute the P-02 acceptance set against it; optionally configure one cloud provider. Not a code repair.

---

## P2 — MEDIUM

### P14-DEF-F1 — Portfolio gross collected revenue always reports 0 *(real bug, reproduced)*
- **Module:** P-13 (`app/portfolio/finance.py`, `FinanceMixin.portfolio_finance`).
- **Evidence:** `tests/test_p14_financial.py::test_p14_f2_portfolio_gross_collected_traceable` (**xfail**, strict=False). A business with ₹4,000 verified collected revenue shows `collected_minor == 0` in portfolio rows/totals; `net_collected_minor` is correct.
- **Root cause:** the code reads `revenue.get("collected_minor")` from P-07 metrics, which has no such key — the gross figure is `collected_gross_minor`; the fallback silently yields 0.
- **Impact:** P-13 presentation only — gross-vs-net/refund inference from portfolio finance would be wrong. P-07 books, net figures, projected figures and concentration are unaffected. P-13's own Scenario suite never asserted gross, which is how it survived three gates.
- **Proposed minimal repair:** read `collected_gross_minor`; add a P-13 regression asserting gross ≥ net and > 0 with verified revenue. No migration.

### P14-DEF-I3 — Financial events are never persisted
- **Modules:** P-07 → P-01. `FINANCIAL_JOURNAL_POSTED` / `FINANCIAL_REVENUE_VERIFIED` are excluded from `CRITICAL_EVENT_TYPES`, so the closest events to §6 `FinancialTransactionRecorded` never reach `system_events`. **Repair:** add both to the critical set (one line, additive).

### P14-DEF-I4 — Event bus has no retry and no dead-letter
- **Module:** P-01. Subscriber failures and flood/depth drops are count-and-forget. (P-12's dead-letter queue covers workflow tasks, not events.) **Repair:** record failed deliveries (event_id, handler, error) to a small dead-letter table, or persist dropped/failed critical events synchronously in the persistence path.

### P14-DEF-I5 — P-10 PermissionBroker is directly consumed only by P-12
- **Modules:** P-10 → P-02…P-08. Other modules enforce via the P-01 PermissionEngine + P-10 policy settings, so §5's "enforce across every module" holds only indirectly; broker-only gates do not apply outside P-12. Enforcement itself was probed and holds — this is an architecture-conformance gap, not a bypass. **Repair:** owner decision — document the two-path model as accepted design, or route P-05 execution submission through the broker. Do not rebuild.

### P14-DEF-I6 — No direct outcome feed from P-05/P-06/P-07 into P-09
- **Modules:** P-05, P-06, P-07 → P-09. Learning depends on ingestion jobs and the single P-12 `learning.analyze` call site (`operations/service.py:2235`). **Repair:** add outcome-ingestion calls at execution/business/financial completion points, reusing the existing ingestion service (no new store).

### P14-DEF-I7 — `BusinessUpdated` event missing
- **Module:** P-06 → bus. Generic business mutations are not observable; the lifecycle event covers status changes only. **Repair:** add a `BUSINESS_UPDATED` type for non-status mutations, or formally map §6 → `BUSINESS_LIFECYCLE_CHANGED` in docs.

### P14-DEF-D1 — Two float money columns outside the integer-minor discipline
- **Modules:** P-06/P-03. `business_declarations.budget_cap_amount`, `research_briefs.budget_amount` are floats. Both are pre-P-07 declaration/estimate caps; the P-07 ledger itself is uniformly `amount_minor BIGINT` + currency (verified). **Repair:** add `*_minor BIGINT` columns + currency, backfill `round(amount*100)`, deprecate the floats in one additive migration.

### P14-DEF-D3 — ≈59 genuine entity references without foreign keys
- **Modules:** platform data layer. Worst cases are money-adjacent: `journal_entries.counterpart_business_id` / `approval_id`, `expense_records.*_id`, `spending_requests.*_id` (≈45 polymorphic principal refs and ≈12 correlation/external IDs are FK-less **by design** and excluded from this count). **Repair:** add FKs in one additive migration for the width-matching subset first; document the rest as intentional soft references.

### P14-DEF-D4 — Reference-width mismatches and free-text business references
- **Modules:** P-04/P-08/P-12/P-13 data. Several refs declare widths mismatched vs their target PKs; `business_ref` VARCHAR(200) free text in 4 modules cannot be validated against `businesses.id`. **Repair:** constrain new writes to canonical IDs in service validation; column changes only in a planned migration. Report, never silently rewrite stored refs.

### P14-DEF-E1 — P-02 has no interface consuming P-03 opportunities (§11 Scenario 1 gap)
- **Modules:** P-02 ↔ P-03. Opportunity evaluation is P-03's own score/report, pulled by P-06; the §11 chain step "P-02 evaluates it" cannot be driven as literally specified — asserted structurally in `test_p14_e2e.py`. **Repair (Stage B decision):** either accept the P-03/P-06 path as the design, or build a thin P-02 assessment call over P-03 reports. Do not fabricate the link in docs meanwhile.

### P14-DEF-E2 — P-02 planning never retrieves P-09 memory
- **Modules:** P-02 ↔ P-09. `IntelligenceService` holds no memory handle; its ContextManager reads only P-02 tables. §11 Scenario 2's retrieval step is test choreography today. (Contrast: P-12 → P-09 learning **is** a real interface.) **Repair:** wire `MemoryService` retrieval into mission context building, scoped by the existing classification rules.

### P14-DEF-A3 — §14 unified monitoring dashboard does not exist
- **Module:** P-11 (Stage B build item, per the Stage A brief). System/module health, provider status, DB status and resource utilization are spread across Operations/Security/Overview views; there is no single §14 monitoring surface. **Repair:** Stage B build — one monitoring view over the existing health/diagnostics/operations APIs (all data sources already exist).

### P14-DEF-A4 — Backups can be created and verified but never restored in-app
- **Module:** P-10. Restore is a documented manual owner procedure. **Repair:** add a guarded restore endpoint (owner-only, hash-bound approval, pre-restore snapshot) or formally accept the manual procedure with a rehearsed drill on the owner's machine.

### P14-DEF-A5 — No standing AI-provider health monitoring
- **Modules:** P-01 monitoring / P-02. Provider failure is detected at call time only. **Repair:** periodic provider probe feeding SystemMonitor + dashboard `ai_provider` state (the dashboard already renders the state when a failure has occurred — E2E Scenario 5).

### P14-DEF-A7 — No volume/load baseline exists
- **Modules:** platform. All performance evidence is empty/fixture-scale (see P14_PERFORMANCE_REPORT.md). **Repair:** Stage B benchmark with seeded volume (e.g. 100 businesses, 10k journal entries, 10k memory records) on staging; Windows numbers remain an owner-machine activity.

### P14-DEF-A8 — No real-world data validation (P-03/P-06)
- **Modules:** P-03, P-06. Discovery has never scored a real opportunity from a live source; business creation from real evidence has never happened (the single real evidence item is Level 1 vs the Level-3 minimum — the gate honestly blocks). **Repair:** owner-supervised pilot input: one real opportunity carried through the governed path. Not a code defect; a verification absence.

### P14-DEF-C1 — Carried P2 limitations, re-verified still true in Stage A
Grouped because each was disclosed at its own gate and remains open:
- **PDF export NOT IMPLEMENTED** (P-07 `financial/reports.py` raises a plain-language refusal; P-13 export marks `"pdf": "NOT IMPLEMENTED"`; P-11 UI discloses). 
- **P-05 code execution is process controls, not a strong sandbox** (self-labelled in code; browser adapter partial, desktop disabled).
- **ChromaDB vector store NOT IMPLEMENTED** (P-09 ships a SQLite adapter + deterministic hash embedder substitute; semantic retrieval quality unproven beyond a small labelled corpus).
- **Encryption at rest is partial** (no encryption layer in code; mitigations are scrypt password hashes, SHA-256 session-token hashes, secrets never stored — P-14 security audit).
- **Stripe REQUIRES OWNER CONFIGURATION** (interface + fake only; webhook path refuses for `interface_only` — owner action, not a code repair).

---

## P3 — LOW

| ID | Finding | Proposed handling |
|---|---|---|
| P14-DEF-I8 | No retention policy for `system_events` (unbounded growth); non-critical events untraceable after delivery | Scheduled prune via existing P-12 time triggers; document volatility |
| P14-DEF-I9 | Package-level import graph *looks* cyclic (core⇄substrate); `execution→opportunities` inverts layering. File-level: **zero real cycles** | Documentation note; optional future `core/primitives` move — no Stage B action required |
| P14-DEF-I10 | Duplicate read path in P-11 (direct DB + services); 4 assignment stores / 3 workflow stacks lack a shared contract doc | Canonical stores documented in P14_DATA_ARCHITECTURE.md (done, Stage A); consolidation is a Stage B *decision*, not a repair |
| P14-DEF-I11 | Agent-execution events use task/execution proxy IDs inconsistently — one agent execution cannot be followed on the bus under a single identity | Convention: include `agent_id` + originating assignment/task ID in EXECUTION_* payloads |
| P14-DEF-D5 | Memory dedupe exact-hash, application-level; no DB uniqueness on `memory_records.content_hash` (concurrent-ingest race, near-duplicate blindness) | Unique index on live rows in an additive migration, or accept + document (owner decision) |
| P14-DEF-D6 | No unique natural key on `expense_records`/`spending_requests`/`task_cost_records` — duplicates possible upstream of the (protected) journal | Mirror the journal/tasks idempotency-key pattern at creation |
| P14-DEF-D7 | Temporal data stored as VARCHAR(40) strings (`businesses.launched_at`, `memory_records.expires_at/verified_at`, several P-08/P-13 timestamps) — sort/compare hazards | Convert in a future migration; treat as display-only until then |
| P14-DEF-D8 | "All assignments/workflows for business X" has no single query path (4 stores / 3 stacks) | Canonical query paths documented in P14_DATA_ARCHITECTURE.md §3 |
| P14-DEF-S1 | Local-dev token is owner-equivalent *whenever configured*, including password mode (`app/core/auth.py`) — intentional and documented in code; verified live by P-14 probe | Optional hardening: ignore dev token when a password hash exists, or refuse production startup with one set |
| P14-DEF-S2 | `GET /security/secrets` needs only `read_system_data`; the limited service token can enumerate secret *metadata* (values do not exist in the store; hints masked `env:***`) | Optional hardening: require `modify_system_config`/owner for the list route |
| P14-DEF-E3 | No pre-creation opportunity feasibility in P-07/P-08 (both are business-keyed); pre-creation feasibility is P-03 commercial analysis via P-06 eligibility only | Document as the accepted design |
| P14-DEF-E4 | P-06 creation does not auto-register businesses into P-13 portfolios (a `BusinessCreated` event type exists; no portfolio subscriber); registration is a manual governed owner call | Accept, or subscribe P-13 registration to the event in Stage B — decision item |
| P14-DEF-A6 | No HTTP rate limiting on the API surface (login throttling exists via P-10's guard; event bus has a rate setting). Local loopback single-user deployment mitigates | Note for pilot hardening |
| P14-DEF-C2 | MFA recovery codes NOT IMPLEMENTED (TOTP verifier present, RFC 6238-tested; enrolment via env var only; unconfigured verifier fails closed — re-probed) | Stage B or owner-accepted limitation |
| P14-DEF-C3 | Audit hash chain is tamper-EVIDENT, not tamper-proof (single host; deletion of a sealed row *is* detected — new P-14 probe) | Accepted design; off-host anchoring would be a future phase |
| P14-DEF-C4 | Dependency vulnerability scan has never run (no pip-audit/safety/bandit in the environment; requirements fully pinned) | Run a scanner in Stage B prep; do not claim a result until run |
| P14-DEF-C5 | P-11 rendered-viewport responsive checks NOT EXECUTED (no headless browser in staging); combined historical comparison reports and chat streaming NOT IMPLEMENTED (disclosed in UI) | Owner-machine or Stage B tooling item |
| P14-DEF-C6 | P-12 EXECUTE_WITH_LIMITS caps are recorded decision evidence, not enforced quotas; circuit breakers in-memory per process | Disclosed design limits; enforcement is a Stage B candidate |
| P14-DEF-C7 | P-13 capacities are owner-declared, not telemetry; portfolio risk scores uncalibrated; P-08 scaling thresholds likewise uncalibrated | Calibration requires real operating data (pilot) |

## What is NOT in this register — and why

- **No P0 entries.** 23 new adversarial security probes, 13 financial
  invariant tests, 6 end-to-end scenarios and 10 system probes found
  no unauthorized financial activity, no cross-business leakage, no
  credential exposure, no approval bypass and no destructive
  unauthorized execution. Absence here is evidence-based (probe
  list in P14_REGRESSION_TEST_REPORT.md), not assumed.
- **P-14's own probe-writing errors are not defects.** Four of the
  coordinator's initial audit probes failed on wrong assumptions
  (response-envelope keys, route prefixes, OpenAPI expansion) and
  were corrected against the code; the system behaved correctly in
  each case. They are recorded in the regression report for
  transparency.
