# P-14 Stage A — §11 End-to-End Scenario Evidence Notes

**Scope:** P-14 §11, six end-to-end scenarios, audit only.
**Deliverable under test:** `backend/tests/test_p14_e2e.py` (new file; no production code, no existing test, and no migration was modified).
**Run (own, final):** `cd backend && .venv/bin/python -m pytest tests/test_p14_e2e.py -q`
→ **6 passed, 0 failed, 0 xfailed, 0 skipped** in 15.79s (1 Starlette deprecation warning, pre-existing). `/tmp` checked before the run: 472 MB available of 512 MB.
**Fixtures only.** Businesses are created exclusively through the governed P-06 fixture path (`build_fixture_opportunity` / `make_fixture_business`); money only through P-07's authorised paths; agents through P-01 rows / the P-04 factory.

**Verdict summary**

| # | Scenario | Verdict |
|---|----------|---------|
| 1 | Opportunity → business | PARTIALLY EXECUTED — full chain executed; P-02 step is a documented integration gap (GAP-1); P-07/P-08 steps necessarily run post-creation (GAP-3) |
| 2 | Autonomous task | PARTIALLY EXECUTED — all steps executed; P-09→P-02 wiring is test choreography, not a real interface (GAP-2) |
| 3 | Financial distress | FULLY EXECUTED |
| 4 | Multi-business collaboration | FULLY EXECUTED |
| 5 | Infrastructure failure | FULLY EXECUTED (provider kill injected at the adapter seam — see note) |
| 6 | Security incident | FULLY EXECUTED |

**Defects:** none found. No test is marked `xfail`; no `P14-DEF-E#` entries were required. Every assertion of correct behaviour passed on the real system.

---

## Scenario 1 — Opportunity → business (`test_scenario_01_opportunity_to_business_end_to_end`)

Steps executed on the real chain:

1. **Real-evidence path (asserted BLOCKED, as required):** a real P-03 investigation (brief → discover → research → validate) computed **Validation Level < 3**; `business.evaluate_eligibility` returned `REQUIRES_MORE_RESEARCH`/`REQUIRES_MORE_VALIDATION`; `create_business` raised `InvalidStateTransitionError`; zero businesses exist for that opportunity.
2. **Fixture path (labelled):** `build_fixture_opportunity` drove P-03's own evidence/research/market/commercial/score/validate machinery; P-03 computed Level ≥ 3 (business later shows `validation_level_at_creation == 3`, `is_fixture is True`).
3. **P-06 eligibility (real P-06→P-03 interface):** `evaluate_eligibility` internally calls P-03 `validate()`, `latest_score()`, `report()` and the stored commercial analysis — this is also the only pre-creation *financial feasibility* surface that exists (see GAP-3).
4. **Owner approval (P-01, hash-bound):** `request_creation_approval` → creation with the *undecided* approval was refused (exception) → `approvals.decide(OWNER, True)` → `create_business` succeeded.
5. **P-07 (real interface):** declaration → blueprint → `business.financial_inputs(bid)` (the §9 P-06→P-07 payload; asserts P-07 owns collected-revenue truth) → `financial.ensure_profile` → creation run `COMPLETED` → channel evaluation.
6. **P-08:** `survival.evaluate` produced a snapshot for the new business (no revenue yet — honest early classification, not a fabricated "healthy").
7. **P-10:** `security.broker.authorize` allowed the homed agent's read of its own business and denied a foreign business.
8. **P-13:** portfolio created and the business registered; membership listing contains it (manual registration — see GAP-4).
9. **P-04:** the P-06 creation run's assignments are real factory agents (`agents.get_agent` resolves them; ≥1 assignment).
10. **P-12:** an owner workflow scoped to the business completed with `verified_outcome == "verified"`.
11. **P-05:** direct execution read `blueprint/blueprint.md` from the business workspace via `execution.submit_and_execute` → `COMPLETED`.
12. **P-11:** `DashboardService.businesses_summary()` contains the business; **real HTTP** `GET /api/v1/dashboard/businesses/summary` (shared-DB `client_ops`) contains it and `GET /api/v1/dashboard/overview` returns 200 with `businesses_total ≥ 1`.

Blocked / gap steps:

- **GAP-1 (P-02 ⇏ P-03):** P-02 has *no* interface that consumes a P-03 opportunity. Asserted structurally in the test: no public `IntelligenceService` method name references opportunities. A P-02 mission/plan was created in the same test to prove P-02's real surface works — but it does **not** read the opportunity; presenting it as "P-02 evaluated the opportunity" would be choreography masquerading as integration (§21 rule 14). Opportunity evaluation in the real system is done by P-03 (score/report) and read by P-06 (eligibility).
- **GAP-3 (ordering constraint):** P-07 profiles and P-08 evaluations are keyed by `business_id`; neither can evaluate an opportunity *before* a business exists. Pre-creation feasibility is therefore P-03's commercial analysis via P-06 eligibility; the P-07/P-08 steps run immediately after creation/blueprint. This is a design property, not a failure — but any claim of a pre-creation "P-07 feasibility check" would be false.

## Scenario 2 — Autonomous task (`test_scenario_02_autonomous_task_end_to_end`)

Steps executed on the real chain:

1. **P-09 → planning context (choreography — GAP-2):** a runbook record was stored via `memory.store.create` and retrieved via `memory.retrieval.search` before planning. See gap below.
2. **P-02 plan:** mission "Check system health…" → deterministic baseline plan (`planner == "rule-engine"`, status `draft`, ≥1 step).
3. **P-10 validation:** `security.broker.authorize` allowed the registered agent's `read_system_data`.
4. **Approval + execution:** `intelligence.approve_plan` (hash-bound approval inside P-02) → `execute_plan` → plan `completed`; every step `completed` with a real P-01 `task_id`.
5. **P-12 workflow with a P-04 agent:** agent created through the P-04 factory (`tests/p05_support.make_agent`), assigned to the workflow step; workflow `COMPLETED`, task `verification_status == "verified"`.
6. **Verification gate → learning:** `learning_record_id` set by P-12 itself; exactly **one** `LearningRecord` row with `source_ref == workflow_id`, confidence mechanically capped at `LOW` by P-09. A second workflow with failing acceptance criteria ended `FAILED` with `learning_record_id is None` and no learning row — learning happens **only** for verified outcomes. The P-12→P-09 link is a **real interface** (`OperationsService._record_learning` calls `self._memory.learning.analyze`), not choreography.
7. **Reporting:** `operations.overview` shows ≥1 COMPLETED and ≥1 FAILED workflow; dashboard `execution_summary` reflects task rows.

Gap:

- **GAP-2 (P-09 ⇏ P-02):** `IntelligenceService` holds no P-09 handle (asserted: `not hasattr(app.intelligence, "memory")`), and P-02's `ContextManager.build_context` reads only P-02's own mission/plan/decision-record tables. Nothing in `create_plan` retrieves P-09 memory. The retrieval step above is test choreography wiring two real APIs in sequence — recorded here as a gap, not claimed as integration.

## Scenario 3 — Financial distress (`test_scenario_03_financial_distress_end_to_end`)

Fully executed on the real chain:

1. Fixture business + P-07 profile (INR); opening balance ₹50,000; revenue ₹10,000 vs expenses ₹8,000 → P-08 snapshot with **no** `loss_making` gate.
2. Deterioration (revenue +₹20,000, expenses +₹27,000, all through P-07 authorised paths): **P-07 detection** — `business_summary` shows collected ₹30,000 vs paid expenses ₹35,000; `financial.consolidated("INR")` per-business `net_profit_minor == -500000` (−₹5,000).
3. **P-08 detection** — re-evaluation raises the `loss_making` hard gate and a matching monitoring check; scaling assessment is `NOT_READY`/`BLOCKED`.
4. **P-13 impact view** — `portfolio_finance` shows the same per-business P-07 figure (net collected ₹30,000, live-read, not copied); `assess_risk` returns a per-business row for the distressed business. (Precision note: the test asserts the risk row's presence and the finance figures; it does not assert a distress-specific P-13 risk *signal* — P-13 risk signals derive from P-08 overlay/pause and P-06 state via the business summary, and no signal text was pinned in this scenario.)
5. **Owner-decision surface** — P-08 `RECOVER` decision created (Level 3); dashboard `survival_overview` lists the decision and the business's latest health snapshot.
6. **Governed execution** — `decisions.execute` *before* approval raised `PermissionDeniedError`; `request_approval` → owner `approvals.decide` → `decisions.review` → `APPROVED` → `execute` → `EXECUTED`; replay with the same execution key returned `idempotent_replay is True`.

No blocked steps, no gaps beyond GAP-3's general note (all surfaces here are business-keyed by design).

## Scenario 4 — Multi-business collaboration (`test_scenario_04_multi_business_collaboration`)

Fully executed on the real chain (extends the proven P-13 §21.9/§21.12 patterns into one chain):

1. Two businesses with verified collected revenue (₹4,000 / ₹2,000) in one portfolio.
2. **Shared service:** one service with active access for both; usage 75/25; usage-based internal allocation split ₹75/₹25-equivalent minor units (7500/2500) with `kind == "INTERNAL_ALLOCATION"`; after approval, `financial.consolidated("INR")` is **byte-identical** to before — internal allocations move no P-07 money.
3. **Per-business P-07 truth:** a ₹500 paid expense recorded only on Business A appears in A's `business_finance` summary (expenses 500_00) and not B's (0); revenues stay 4000_00 / 2000_00 respectively.
4. **Cross-business workflow:** `create_portfolio_workflow` → `start_portfolio_workflow` refused (`ValidationError`) with zero and with only one authorization → after **both** `authorize_participation` calls, start succeeded (`ACTIVE`); each participation's P-12 sub-workflow is scoped to its *own* business (`business_id` asserted per sub-workflow, distinct workflow ids); both sub-workflows were validated and run through P-12; `refresh_portfolio_workflow` → `COMPLETED`.
5. **Zero cross-access:** after participation, Business A's agent is still denied Business B (`check_agent_access` → `allowed is False`), the denial incremented the `portfolio.isolation_violation` audit count by exactly 1, and `business_finance(AGENT, B)` raised `PermissionDeniedError`.
6. **Outcome display:** `portfolio_finance` totals net collected 6000_00 with `combined_available_cash is None` (cash never combined); dashboard `businesses_summary` total == 2.

## Scenario 5 — Infrastructure failure (`test_scenario_05_ai_provider_failure_fallback`)

Fully executed. **Method note (honesty):** the "kill" is injected at the provider-adapter seam — after a P-12 workflow completed, the test replaces `intelligence.providers["ollama"]` with an `OllamaProvider` pointed at a dead endpoint (`http://127.0.0.1:9`, 0.5s timeout) and enables an owner model profile selecting it. Cloud is disabled by default settings. This is the same seam P-02's own suites use (FakeProvider injection precedent); no production code was changed.

Evidence:

1. **Detection:** `intelligence.models_status()` reports `ollama.available is False` and `cloud.available is False`.
2. **Fallback engages:** a template-matched mission is still planned — by the deterministic baseline (`planner == "rule-engine"`) — and the P-02 decision recorder's `router_selection` record names the baseline fallback and the unavailable ollama provider.
3. **No fabricated success:** an unplannable mission ("underwater basket weaving championship tour") raised `ValidationError`; its mission status is honestly `planning_failed` with a `plan_failed` decision record.
4. **State preserved:** the pre-kill P-12 workflow still reads `COMPLETED` afterwards; a *new* post-kill P-12 workflow also completes with `verified_outcome == "verified"` (deterministic task-handler path has no LLM dependency).
5. **Visibility:** P-11 `system_health()` (async service behind the dashboard route) reports the `ai_provider` check as `unavailable` with ollama named in the detail.

## Scenario 6 — Security incident (`test_scenario_06_security_incident_end_to_end`)

Fully executed on the real chain:

1. **Attempt 1 — cross-business portfolio read:** Business A's agent → `portfolio.check_agent_access(B)` denied; `portfolio.isolation_violation` audit count incremented by exactly 1.
2. **Attempt 2 — cross-business broker read:** `security.broker.authorize(AGENT, read_business_data, business_ref=B)` denied with "cross-business" in the reason (agent holds the role permission; the business-scope gate is what denies).
3. **Attempt 3 — protected file read:** `security.filesystem_guard.evaluate(AGENT, read, credentials/prod-api-keys.txt)` denied, no content returned, denial present in the P-01 audit trail (`security.filesystem_guard`, decision `deny`, actor = the agent).
4. **Attempt 4 — policy manipulation:** `security.update_settings(AGENT, …)` raised `PermissionDeniedError`; `monitor.evaluate_alerts()` raised a **critical** `policy_change_attempt` alert, visible via `monitor.list_alerts(status="open")`.
5. **Incident surface:** owner created a P-10 incident record for the attempts; it appears in `list_incidents(status="open")`.
6. **Dashboard security surface (service + HTTP):** `DashboardService.security_summary()` shows ≥1 open alert and ≥1 open incident; `attention()` contains a `security_alert` item; **real HTTP** `GET /api/v1/dashboard/security/summary` (shared-DB client) shows ≥1 open alert.
7. **Non-dismissible critical (§5.4):** the critical security notification has `dismissible is False`; service-level `dismiss_notification` raised `ValidationError`, and HTTP `POST /dashboard/notifications/{id}/dismiss` returned **422** with "cannot be dismissed".

---

## Integration gap register (consolidated)

| ID | Gap | Evidence | Severity |
|----|-----|----------|----------|
| P14-GAP-1 | P-02 Intelligence has no interface consuming P-03 opportunities; opportunity evaluation lives in P-03 (score/report) and is *pulled* by P-06 eligibility. No P-03→P-02 or P-02→P-03 call exists. | Structural assertion in Scenario 1 (no opportunity-referencing method on `IntelligenceService`); code inspection of `app/intelligence/*` (only an `opportunity.research` *tool name* in the P-01 task registry, unrelated to P-03 records). | P2 — the §11 Scenario-1 chain cannot be driven as literally specified; the working substitute (P-03 evaluation + P-06 pull) is real but differently shaped. |
| P14-GAP-2 | P-02 planning does not retrieve P-09 memory. `create_plan` never calls P-09; P-02's `ContextManager` reads only P-02's own tables. The §8 orchestration stage "CONTEXT RETRIEVAL" is not wired to the memory engine. | Structural assertion in Scenario 2 (`not hasattr(intelligence, "memory")`); `app/intelligence/context.py` reads mission/plan/decision repositories only. Contrast: P-12→P-09 learning *is* a real interface (Scenario 2, step 6). | P2 — autonomous tasks plan without learned context; memory influences operations only after completion (learning), never before planning. |
| P14-GAP-3 | P-07 and P-08 are business-keyed: no pre-creation feasibility/survival evaluation of an *opportunity* exists. Pre-creation feasibility = P-03 commercial analysis via P-06 eligibility only. | Scenario 1 ordering (profile/snapshot only creatable post-blueprint/post-creation); `ensure_profile`/`survival.evaluate` signatures take `business_id`. | P3 — design property; only a defect if documentation claims a pre-creation P-07 check. |
| P14-GAP-4 | P-06 business creation does not auto-register the business in any P-13 portfolio; registration is a separate manual owner call (`portfolio.register_business`). A `BusinessCreated` event type exists in `app/events/events.py`, but no portfolio subscriber performs registration. | Scenario 1 step 8 required an explicit `make_portfolio`/`register_business` call; no registration code path in `app/business/*` or subscriber in `app/portfolio/*`. | P3 — orchestration completeness; manual registration is governed and audited, so this is a missing convenience/automation link, not a correctness or security issue. |

## Defect register

**None.** No behaviour asserted in the six scenarios deviated from the correct/expected behaviour, so no `xfail` markers and no `P14-DEF-E#` entries were created. (Two harness-side mistakes during development — a wrong `operations.overview` key and a convoluted assertion expression — were fixed in the test file itself before the final run; they were test bugs, not system defects, and are not recorded as defects.)

## Method notes

- Dashboard assertions use `DashboardService(application)` — the exact object the P-11 routes construct per request (`app/api/routes/dashboard.py:_svc`) — plus real HTTP in Scenarios 1 and 6 via the `client_ops` fixture, which shares the same SQLite file as `app_ops` through the common `tmp_path` (the established P-11 integration-test pattern). No dashboard figure was taken from a mock.
- Choreography disclosure: where this file calls two module APIs in sequence (P-09 retrieval before P-02 planning; P-13 registration after P-06 creation), the notes above say so explicitly. All other cross-module steps in these scenarios run through the modules' own internal interfaces (P-06→P-03, P-06→P-07 payload, P-12→P-09 learning, P-13→P-07 live finance reads, P-13→P-12 sub-workflows, P-02→P-01 tasks, P-12→P-05/P-01 substrates).
