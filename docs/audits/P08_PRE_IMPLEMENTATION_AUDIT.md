# P-08 PRE-IMPLEMENTATION AUDIT — Survival and Scaling Engine

Stage 1 of the P-08 prompt (§2.1 / §29): inspect the ACTUAL P-01–P-07
implementations before writing implementation code. Every claim below
was verified against the staging code on 2026-11-09, not against the
phase prompts.

## 1. Baseline

- Full suite re-run before any P-08 change: **see §10 of this audit**
  (recorded after the run completes; the gate baseline is 404 tests
  from the P-07 gate: 348 P-01–P-06 regression + 56 P-07).
- Migration head at audit time: `c3b5cdba2559` (P-07), 90 tables.
- Environment hygiene applied: `df -h /tmp` checked (512 MB tmpfs,
  1% used); test TMPDIR is the project `.tmp` directory (conftest).

## 2. What exists and will be reused (never duplicated)

| Need (P-08 §) | Existing implementation | Location |
|---|---|---|
| Approvals (§8/§14/§20) | P-01 hash-bound `ApprovalService.create/get/decide/verify_binding`; approval drift fails closed | `app/permissions/approvals.py` |
| Audit trail | P-01 `AuditRepository` / `AuditEvent` (append-only by API) | `app/database/repositories/core.py` |
| Owner-governed config | `system_config` via `ConfigRepository`; P-06/P-07 settings pattern (owner-only writes) | `app/business/service.py`, `app/financial/service.py` |
| Events | P-01 `EventBus` + `EventType` enum; P-06/P-07 added their types additively | `app/events/events.py` |
| Business identity + lifecycle (§5) | P-06 `BusinessCreationService`: registry, validated `transition_business`, `lifecycle_events`, declarations, readiness reviews, channels, assumptions, evidence | `app/business/service.py`, `app/business/lifecycle.py` |
| Financial truth (§6.1) | P-07 `FinancialService` with sub-services: `revenue.metrics`, `expenses.totals`, `budgets.available_cash/budget_utilisation/list_budgets`, `analytics.profitability/health/runway`, `forecasting.create_forecast/forecast_vs_actual/create_scenario`, `reports.reconciliation_report`, `analyst.answer`, and the stable **`p08_indicators(business_id)`** contract (P-07 §25) | `app/financial/service.py:652` |
| Opening cash / reserves / budgets | P-07 `record_opening_balance`, `budgets.create_budget/create_reserve/record_cash_balance`, spend-request flow (`request_spend` decides at budget layer; Level 3 structurally blocked) | `app/financial/budgets.py` |
| Verified revenue seeding (tests/smoke) | P-07 authorised provider-report path (`revenue.create_revenue(..., verified=True)`, the same internal path verified webhooks and reconciliation land on) and the signed FakeProvider webhook pipeline | `tests/p07_support.py`, `app/financial/payments.py` |
| Agent factory (§17) | P-04 `AgentFactoryService.create_agent` (9-gate, reuse-first), `agent_metrics` (measured, honestly labelled) | `app/agents/service.py` |
| Execution (§20) | P-05 `ExecutionService.submit_and_execute` with idempotency keys, business_ref workspaces, policy modes (simulation/supervised/controlled/emergency) and a **global, owner-only emergency stop** | `app/execution/service.py`, `app/execution/policy.py` |
| Intelligence (§19/§21) | P-02 `DecisionRecorder.record/list` — decision records are first-class and referenceable | `app/intelligence/recorder.py` |
| Opportunity/market evidence (§11.2) | P-03 opportunities + evidence with provenance and reliability ceilings | `app/opportunities/` |
| Resource admission | P-01 `SystemMonitor.admission_block_reason` + thresholds (CPU-only hardware profile: 1 inference slot) | `app/monitoring/` |

## 3. The P-07 → P-08 indicator contract: coverage and gaps

`FinancialService.p08_indicators()` returns, per business, in the
profile's base currency: `verified_collected_revenue_minor` (net
collected), `actual_expenses_minor`, `profitability{status,
net_profit_minor, is_loss}`, `cash_flow{available_cash_minor,
cash_balance_minor}`, `available_capital_minor`, `runway_months`,
`runway_status`, `financial_risk` (P-07 health status),
`budget_utilisation_max_ratio`, `reconciliation_status{
unresolved_items, sessions}`.

Richer per-business reads exist through `business_summary()` and the
sub-services (all P-07-computed): revenue metrics (projected / booked
/ invoiced / collected gross / recognized / refunds / chargebacks /
disputed-open / outstanding receivables / MRR / AOV / **by_channel /
by_product / by_category** collected shares), expense totals (paid,
direct/indirect, fixed/variable, committed, by category),
`available_cash` components (cash, verified cash, **protected
reserves, committed, obligations**), profitability (gross profit,
gross margin ratio, contribution-margin break-even, unit economics),
health (status + reasons + hard overrides), runway (burn, months,
preliminary flag), forecasts and **forecast_vs_actual** (P-07 computes
the error against the frozen forecast).

**P-08 consumes exactly these. It sums no monetary amounts itself.**
Ratios P-08 needs (refund rate, concentration share, utilisation) are
either returned by P-07 (margin ratio, utilisation ratio) or computed
as *dimensionless ratios of two P-07-returned figures* in the health
scoring layer — the same pattern P-07's own health engine uses
internally. No P-08 code produces a new currency amount from raw
records. This is verified by a structural test (see plan §7).

**Gaps found (recorded, worked around without computing money):**

1. **Distinct / repeat customer counts are not in the indicators
   contract.** `RevenueRecord` carries `customer_ref`, and
   `revenue.list_revenue` is an existing P-07 read API. P-08 derives
   *commercial counts only* (distinct customers, repeat customers,
   collected-record count) from that read API — counts, never amounts.
   Recorded as contract gap G-1 for a future P-07 contract v2.
2. **No period-split revenue metrics.** `revenue.metrics` is
   cumulative (expenses.totals accepts a date range; revenue does
   not). P-08 therefore detects *change* by comparing successive
   health snapshots of cumulative P-07 figures (monitoring by
   differencing readings), never by summing records into periods.
   Gap G-2.
3. **Commercial/operational observations have no home.** Traffic,
   leads, delivery reliability, satisfaction (§6.2/§6.3) are not
   financial data and P-07 rightly does not hold them. P-08 adds a
   provenance-carrying **observation** record (source, reliability,
   evidence refs) — observations are evidence, never financial truth,
   and vanity metrics (traffic/followers/impressions/downloads) are
   structurally barred from validating a business (§6.2). This is the
   smallest safe integration §2.2 permits.
4. **P-06 lifecycle has no CLOSED state and OPERATIONAL exits only to
   ARCHIVED; PAUSED is not reachable from OPERATIONAL.** See §4.

## 4. Lifecycle mapping (§5.1) — ONE lifecycle, P-06-owned

P-06's machine (18 states, validated transitions, `paused_from`
semantics) remains the only business state machine. P-08's 17
operational states map as follows:

| P-08 state (§5.1) | Mapping |
|---|---|
| PROPOSED | P-06 `PROPOSED` (direct) |
| VALIDATING | P-06 `ELIGIBILITY_REVIEW` (overlay name; P-06 state unchanged) |
| APPROVED | P-06 creation-approval fact (overlay; business exists post-approval) |
| BUILDING | P-06 `BLUEPRINTING`…`IN_DEVELOPMENT` (overlay range) |
| LAUNCH_READY | P-06 `READY_FOR_LAUNCH` (direct; requires passing P-06 readiness) |
| LAUNCHED | P-06 `OPERATIONAL` with `deployment_state != not_deployed` (overlay) |
| EARLY_OPERATIONS / GROWING / STABLE / SCALING / OPTIMIZING | **P-08 operational overlays** recorded on health snapshots, gated by evidence rules (§5.2); the P-06 state stays `OPERATIONAL`. GROWING requires verified collected revenue > 0 across ≥2 snapshots and no hard gate; SCALING additionally requires a passing scaling assessment + owner approval |
| AT_RISK / RECOVERY | P-08 overlays driven by health classification / active recovery plan; entering AT_RISK opens an INVESTIGATE decision automatically |
| PAUSED | P-06 `PAUSED` via `transition_business` where the machine allows it; for OPERATIONAL businesses P-06 cannot pause, so P-08 records a **business-level emergency/operational pause flag** (P-08 table) that blocks all P-08-originated execution and spend paths — the honest limit of the existing machine, recorded here rather than patched silently |
| CLOSURE_REVIEW | P-08 overlay + closure-review record (§14 workflow lives in P-08) |
| CLOSED | P-08 overlay terminal; reached only after owner approval + wind-down; the P-06 business is then moved to `ARCHIVED` through the validated path (`OPERATIONAL → ARCHIVED`, or via `BLOCKED → ARCHIVED` for non-operational states) |
| ARCHIVED | P-06 `ARCHIVED` (direct) |

P-08 lifecycle history = P-06 `BusinessLifecycleEvent` rows (read via
`business.lifecycle_events`) **plus** P-08 overlay-transition records
in the P-08 lifecycle table, each carrying decision ID, evidence refs,
approval ref, actor, reason (§5.3). Nothing rewrites P-06 history.

## 5. Experiments and P-06 declarations (lock 3)

P-06 declarations are per-business pre-declarations (success criteria,
budget cap, duration, min test volume) judged at creation/readiness.
P-08 experiments are per-experiment pre-declarations (§9.2's 16
fields). They are different scopes, so P-08 keeps its own experiment
records — but an experiment may reference the business's approved
P-06 declaration (`declaration_id`), and experiment budgets are
**P-07 budgets** (scope `experiment`): spend flows through P-07's
spend-request machinery, so stop-loss blocks at the budget layer —
when the stop-loss trips, P-08 freezes the linked P-07 budget
(owner-governed status change via the budget service is not exposed,
so P-08 enforces by (a) marking the experiment STOPPED, (b) rejecting
further P-08 spend authorisations for it, and (c) recording the
block; any *new* spend request against the exhausted budget is in any
case refused by P-07's own utilisation checks). The audit records
this precisely: the mechanical block is P-07 budget exhaustion +
P-08 experiment state, not a new money path.

## 6. Governance pattern (lock 4)

Precedents verified in code: P-04 prohibits approval Level 3
structurally (no code path); P-07 spend Level 3 returns
`blocked_level3` (no execution path exists); P-01 approvals are
hash-bound and an approver is checked to be the owner for
business-critical kinds (P-06 `_verify_creation_approval`). P-08
adopts the same shape: autonomy levels 0–4 are a property of the
*decision type*, enforced in the P-08 service; Level 4 types
(CLOSE, protected-reserve-affecting allocations, governance changes)
accept **only** an owner principal plus a hash-bound P-01 approval,
and agents receive a structural refusal (no approval object an agent
can create satisfies the check). Decision execution is idempotent:
an `executed_at` marker + idempotency key; a second execution returns
the original outcome unchanged.

## 7. Emergency pause (§25.2)

P-05's emergency stop is **global and owner-only** — it is not a
per-business control and P-08 must not widen it. P-08 therefore
implements the business-level pause as a P-08 control record checked
by every P-08 execution/spend path for that business (decision
execution, experiment start/spend, scaling-plan activation), emits a
critical event (owner-visible), preserves all records, and requires
an owner decision to lift. Where the P-06 machine allows
(PAUSABLE states), it also drives the business to P-06 `PAUSED`.

## 8. Frontend

No frontend exists in staging (P-06/P-07 audits concur). P-08 is
API-only under `/api/v1/survival/...` (the repo's `/api/v1` prefix
convention); §24's Command Center views are P-11 scope and are
recorded NOT IMPLEMENTED in the implementation report.

## 9. Analyst (§19)

No LLM exists in staging. Following the P-07 §17 resolution, P-08
delivers a deterministic structured query interface (intents over
health/decisions/portfolio data) with per-figure provenance labels;
the natural-language layer is NOT IMPLEMENTED. All P-08 logic is
deterministic and works with no model available (§27).

## 10. Baseline test run

*(Recorded on completion of the pre-build run — see the P-08
implementation report for the final numbers.)*
