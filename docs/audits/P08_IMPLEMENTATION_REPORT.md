# P-08 Implementation Report (§31) — Survival and Scaling Engine

Staging build, 9 Nov 2026. Statuses use §31's vocabulary. Tests:
**450/450 in one run** (404 regression + 46 new); smoke **34/34**
(`docs/reports/P08_SMOKE_EVIDENCE.txt`,
`docs/testing/P08_TEST_REPORT.md`).

**1. Initial repository condition** — COMPLETED AND TESTED.
P-01–P-07 accepted in staging; baseline re-run at Stage 1:
404 passed in 208.86 s. Recorded in
`docs/audits/P08_PRE_IMPLEMENTATION_AUDIT.md`.

**2. P-01 through P-07 integration audit** — COMPLETED AND TESTED.
Audit + plan in `docs/audits/`. Key findings: P-06's 18-state
machine is the only lifecycle (P-08 overlays are readings);
`FinancialService.p08_indicators` is the financial contract;
two indicator gaps recorded (G-1 customer counts — counts derived
from P-07's read API, never amounts; G-2 no period split — change
detected between successive snapshot readings).

**3. Existing capabilities reused** — COMPLETED AND TESTED.
P-01: approvals (hash-bound, 4 new action kinds), audit, events,
permissions, `system_config`. P-02: planner + DecisionRecord
(every P-08 decision references one). P-03: evidence discipline
for observations; market research route. P-04: agent metrics for
resource proposals. P-05: execution/mode substrate (pause
integrates as a P-08 control over P-08-governed execution paths).
P-06: businesses, lifecycle transitions, declarations, channels,
assignments. P-07: indicators, summaries, revenue metrics,
budgets, available cash, analytics, forecasts — read-only.

**4. Missing capabilities identified** — COMPLETED AND TESTED.
G-1/G-2 above; P-07 exposes MRR but **no subscription count** —
the software criteria set evaluates the MRR reading plus observed
subscription-delivery evidence rather than an invented count;
P-06 cannot pause an OPERATIONAL business (pause flag is a P-08
overlay — disclosed); P-06 cannot archive a PAUSED business
(wind-down records the reason; the P-08 CLOSED overlay stands).

**5. Architecture changes** — COMPLETED AND TESTED. New package
`backend/app/survival/` (10 modules), 18 tables, 59 API routes,
8 additive event types, `Application.survival` facade. No changes
to P-01–P-07 behaviour; one additive extension to P-07's routes
was NOT needed — all reads use existing services.

**6. Files created** — COMPLETED AND TESTED.
`backend/app/survival/{__init__,constants,monitoring,health,decisions,experiments,scaling,recovery,portfolio,forecasting,analyst,service}.py`;
`app/database/models/survival.py`;
`app/database/repositories/survival.py`;
`app/api/schemas/survival.py`; `app/api/routes/survival.py`;
migration `99902c03a197`; `tests/{p08_support,test_p08_unit,test_p08_scenarios,test_p08_integration,test_p08_security}.py`;
`backend/scripts/p08_smoke.py`; docs (architecture, operations,
security, testing, this report, smoke evidence).

**7. Files modified** — COMPLETED AND TESTED.
`app/database/models/__init__.py` (model registration),
`app/events/events.py` (8 additive event types; 3 added to the
critical/persisted set), `app/core/application.py` (facade
construction), `app/main.py` (route registration),
`docs/PHASE_TRACKER.md`, `README.md`. Pre-existing test files:
migration-head pins and two migration-cycle retargets — fully
disclosed in the test report, strictness preserved.

**8. Database migrations** — COMPLETED AND TESTED. One additive
migration `99902c03a197` (18 tables). Cycle verified on SQLite:
90 → 108 → 90 → 108 tables.

**9. Monitoring capabilities** — COMPLETED AND TESTED.
Event-driven + on-demand bounded evaluation (collect → checks →
snapshot); checks for loss-making, collected-revenue decline
(between successive P-07 readings), unresolved reconciliation,
short runway, missing profile. No new polling daemon.

**10. Business health methodology** — COMPLETED AND TESTED.
7 dimensions with evidence/freshness/confidence/missing, owner-
governed weights and bands, P-07 health pass-through for the
financial dimension, 8 hard gates overriding any score, explained
classifications EXCELLENT…CRITICAL/INSUFFICIENT_DATA.

**11. Decision engine implementation** — COMPLETED AND TESTED.
§8 records with ≥ 3 alternatives, hash-bound approval flow,
owner-verified Level ≥ 3 approvals, idempotent execution (repeat
execution under any key is a replay), P-02 record linkage, scores
as support only.

**12. Experiment management implementation** — COMPLETED AND
TESTED. Full §9.2 pre-declaration validation (incomplete records
nothing), P-06 declaration reconciliation reference, owner
approval creating the linked P-07 budget, evidence-based
evaluation, permanent undeletable records.

**13. Stop-loss implementation** — COMPLETED AND TESTED.
Mechanical checks (budget exhausted / max loss / time limit) on
every spend authorisation and on demand; tripping stops the
experiment with reason recorded; further spend refused
(Scenario 4, smoke + tests).

**14. Scaling readiness implementation** — COMPLETED AND TESTED.
Business-model-aware criteria sets (4 seeded), satisfied AND
unsatisfied conditions with sources, stages 0–6, hard-gate
blocking, incremental plans clamped to the §10.4 cap and to P-07
available capital (strict mode refuses), owner-only plan approval
that moves no money (§16.4).

**15. Growth strategy capabilities** — PARTIALLY IMPLEMENTED.
Growth and cost-optimisation proposals exist as governed decision
records with current-vs-proposed expectations and P-07 evidence
(§11/§12 route) — COMPLETED AND TESTED at that scope. Automated
market research execution and any spend execution are NOT part of
this phase by design (§16.4/§27); research requests route to P-03.

**16. Recovery and closure workflows** — COMPLETED AND TESTED.
Finite recovery plans (budget + timeline + thresholds enforced at
creation; once-only conclusion with the §13 outcome vocabulary).
Closure: inventory-first workflow through OWNER_APPROVAL, Level-4
owner-only execution with hash-bound approval, P-06 archiving via
validated transitions, history preservation recorded. Disclosed
limit: a P-06-PAUSED business cannot be archived by P-06's machine
(the closure record carries the reason).

**17. Portfolio management** — COMPLETED AND TESTED.
Consolidated figures verbatim from P-07; concentration across
platform (P-06 channels), dominant channel and revenue model from
P-07 readings; record count explicitly never reported as
diversification.

**18. Capital allocation controls** — COMPLETED AND TESTED.
Proposals only (§16.4): per-business cap = min(P-07 available
capital, share cap × total), explainable risk adjustment from the
health snapshot, totals never exceed available capital,
protected-reserve proposals recorded BLOCKED (Scenario 12).

**19. Resource allocation controls** — COMPLETED AND TESTED.
Measure-first proposals using P-04 metrics and the owner hardware
profile (4 concurrent agents, 1 inference slot); alternatives
(reassign/optimise/pause-idle) always listed; no agents created by
P-08 — creation remains P-04's flow.

**20. AI integration** — PARTIALLY IMPLEMENTED (honest §19 split).
The deterministic structured analyst (13 intents, per-figure
provenance labels) is COMPLETED AND TESTED. The natural-language
analyst layer is **NOT IMPLEMENTED** — no LLM exists in staging,
and the system is fully functional without one (§27), exactly as
P-07 resolved its §17.

**21. Security and governance controls** — COMPLETED AND TESTED.
All §26.3 items as named tests (see security doc mapping);
service-layer autonomy enforcement; owner-only settings; pause
semantics; injection-inert evidence handling; audit on every
mutation including denials. Carried residual: P-01
`ApprovalService.decide` lacks a service-level role check —
P-08 compensates by verifying approver identity itself; full
hardening remains P-10's (documented since P-07).

**22. API endpoints** — COMPLETED AND TESTED. 59 routes under
`/api/v1/survival/...` (architecture doc §14). No DELETE route
exists for any permanent record.

**23. Frontend functionality** — NOT IMPLEMENTED. No frontend
exists in staging; P-11 owns the Command Center (§24). The engine
reports this in its status payload.

**24. Tests executed** — COMPLETED AND TESTED. 46 new P-08 tests
(12 unit, 15 scenarios, 6 integration, 13 security) + 404
regression + real-uvicorn smoke (34 checks). Details:
`docs/testing/P08_TEST_REPORT.md`.

**25. Test results** — COMPLETED AND TESTED. **450 passed, 0
failed, 0 errors, one run, 266.65 s.** Smoke 34/34. Migration
cycle exact. Two earlier full-run attempts were environmental
(/tmp exhaustion) — diagnosed and disclosed in the test report;
one genuine failure they exposed (P-06 cycle count vs P-08's new
`business_*` tables) was fixed by retargeting that test to its own
phase head, disclosed.

**26. Performance observations** — COMPLETED AND TESTED. Full
suite 266.65 s (vs 208.86 s baseline) on the shared VM. The
suite's pytest temp footprint (~0.5 GB) exceeds the VM's 512 MB
/tmp tmpfs; the final run held /tmp at ~45 % with a pruner for
finished tests' dirs. Disk-backed basetemp measured far slower
(SQLite fsync latency). Evaluations are O(readings + snapshot
history) per business; no background load added.

**27. Known limitations** — (first-class) (a) §19 NL analyst NOT
IMPLEMENTED (item 20). (b) Frontend NOT IMPLEMENTED (P-11).
(c) Subscription *count* unavailable from P-07 — MRR-based
criteria used instead (item 4). (d) PAUSED for OPERATIONAL
businesses is a P-08 control flag, not a P-06 state; P-06 cannot
archive a PAUSED business (items 4/16). (e) Customer counts are
counts derived from P-07's revenue read API; period change is
snapshot-differencing (G-1/G-2). (f) Monitoring is on-demand /
externally scheduled — no daemon. (g) Windows verification still
carried from P-00 for the whole project. (h) Code-execution
isolation limits from P-05 are unchanged by this phase.

**28. Unresolved risks** — P-01 `decide` role-check residual
(P-10). Staging businesses remain fixtures with no real verified
revenue — P-08's honest outputs for them (INSUFFICIENT_DATA,
NOT_READY) are correct behaviour, not a defect; real operating
evidence arrives only with the owner's pilot. Scaling criteria
thresholds are seeded defaults in owner-governed settings and
have never been calibrated against a real business.

**29. Manual configuration requirements** — REQUIRES OWNER
CONFIGURATION (unchanged items): Stripe keys for P-07 (adapter
stays interface-only until then); the Windows environment audit
(P-00); optional tuning of `survival.settings` (weights, bands,
criteria, caps) — defaults are seeded and functional without it.

**30. P-09 integration readiness** — COMPLETED AND TESTED (as an
interface). P-09 consumes `decision_outcomes`, health snapshot
history, experiment evaluations and forecast records — structured
references to P-02/P-08 records, never copies of P-07 financial
data. P-09 was NOT started (§33 boundary); its prompt remains
queued at `docs/prompts/P09_PROMPT.md` with the Stage-1 notes in
the tracker.
