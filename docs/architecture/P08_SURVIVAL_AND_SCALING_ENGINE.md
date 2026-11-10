# P-08 — Survival and Scaling Engine: Architecture

Status: BUILT IN STAGING, awaiting owner gate (9 Nov 2026). Prompt:
`docs/prompts/P08_PROMPT.md`. Stage-1 audit:
`docs/audits/P08_PRE_IMPLEMENTATION_AUDIT.md`; plan:
`docs/audits/P08_IMPLEMENTATION_PLAN.md`; delivery report:
`docs/audits/P08_IMPLEMENTATION_REPORT.md`.

## 1. Architecture (§28.1)

`backend/app/survival/` — nine modules over the P-01 substrate and
the P-06/P-07 engines. One facade (`SurvivalService`, constructed in
`Application.startup` after `financial`) wires:

| Module | Responsibility |
|---|---|
| `monitoring.py` | P-07 readings collection, provenance-carrying observations, bounded event checks |
| `health.py` | 7-dimension health computation, hard gates, snapshot persistence |
| `decisions.py` | §8 decision records, hash-bound approval flow, idempotent execution |
| `experiments.py` | §9 pre-declared experiments, P-07 budget link, mechanical stop-loss |
| `scaling.py` | §10 readiness assessments + incremental plans |
| `recovery.py` | §13 recovery plans; `ClosureService` (§14 workflow) |
| `portfolio.py` | §15 overview/concentration, §16 capital proposals, §17 resource proposals |
| `forecasting.py` | §18 frozen forecasts, §21 decision outcomes |
| `analyst.py` | §19 deterministic structured analyst (13 intents) |
| `service.py` | facade: settings, pause controls, lifecycle overlay/history, `evaluate` |

**The five structural locks** (build brief) are enforced in code,
not convention:

1. **P-07 is the only financial source.** Every figure P-08 reads
   arrives through `FinancialService` (`p08_indicators`,
   `business_summary`, `revenue.metrics`, `budgets.available_cash`,
   `budgets.budget_utilisation`, `analytics.*`, `forecasting.*`).
   P-08 contains no ledger/journal access and no float arithmetic —
   proven by structural tests (`test_no_financial_calculation_primitives_in_survival_package`,
   `test_no_revenue_or_profit_columns_on_survival_models`). Ratios
   P-08 reports (refund rate, concentration share, health score)
   are Decimal ratios of two P-07 figures, labelled as such.
2. **One lifecycle.** P-06's 18-state machine is authoritative
   (§2 below). P-08 stores overlay *readings* on snapshots, never a
   second state of truth.
3. **Experiments are pre-declared; stop-loss is hard** (§6 below).
4. **Governance is structural.** Autonomy levels are enforced in
   the service layer; Level 4 has no agent path (§7 below).
5. **Staging honesty.** A business with no verified revenue
   evaluates to INSUFFICIENT_DATA / NOT_READY — demonstrated first
   in the smoke (`docs/reports/P08_SMOKE_EVIDENCE.txt`).

## 2. Business lifecycle model (§28.2, prompt §5)

P-06 states remain the only machine. P-08's 17 operational states
map as follows (audit §4): PROPOSED, READY_FOR_LAUNCH (as
LAUNCH_READY reading) and ARCHIVED map directly onto P-06 states;
VALIDATING is the ELIGIBILITY_REVIEW overlay; BUILDING covers
BLUEPRINTING…IN_DEVELOPMENT; PAUSED is the P-06 PAUSED state
pre-operationally and a P-08 pause-control flag once OPERATIONAL
(P-06's machine cannot pause an OPERATIONAL business — recorded
honestly in the audit); LAUNCHED, EARLY_OPERATIONS, GROWING,
STABLE, SCALING, OPTIMIZING, AT_RISK, RECOVERY, CLOSURE_REVIEW and
CLOSED are P-08 overlay readings recorded on health snapshots and
in `business_lifecycle_overlays`.

Overlay rules: GROWING requires verified collected revenue > 0 in
≥ 2 snapshots plus a HEALTHY-or-better classification; SCALING can
never be recorded directly (assessment + plan + Level-3 approval
only); CLOSED is reachable only through the §14 closure workflow.
Lifecycle history merges P-06 `lifecycle_events` (read, never
duplicated) with P-08 overlay records, time-ordered.

## 3. Business health methodology (§28.3, prompt §7)

Seven dimensions — financial (25), market (15), commercial (15),
operational (15), product (10), strategic (10), governance (10) —
owner-governed weights in `system_config` key `survival.settings`.
Each dimension carries evidence (with sources), freshness,
confidence and explicit `missing` lists. Dimension scoring is
deterministic (status → basis points); the weighted score is a
secondary summary. Classifications: EXCELLENT ≥ 0.85, HEALTHY
≥ 0.70, STABLE ≥ 0.55, WATCH ≥ 0.40, AT_RISK ≥ 0.25, else CRITICAL
(owner-governed bands).

The financial dimension is a **pass-through of P-07's own health
status** — P-08 does not re-derive it. If the financial dimension
is INSUFFICIENT_DATA, the overall classification is
INSUFFICIENT_DATA regardless of other dimensions.

**Hard gates override any score** (§7.3): `cash_below_obligations`
(available cash < 0 → cap CRITICAL), `obligations_exceed_cash`
(cap AT_RISK), `loss_making` (blocks scaling), 
`unverified_revenue_only` (blocks scaling),
`unresolved_reconciliation` (blocks scaling + material allocation,
reduces confidence), `channel_concentration` (share > threshold),
`compliance_violation` (cap WATCH, blocks scaling; requires a
verified/corroborated observation), `security_incident` (emergency
pause active → cap CRITICAL, blocks scaling). Every classification
is explained in text assembled from the dimension states and gate
details — a developer can see *why* without asking an LLM (§28).

## 4. Evidence confidence methodology (§28.4, prompt §6)

Observations (`business_observations`) are the only home for
commercial/operational facts P-07/P-06 do not hold (traffic,
delivery, satisfaction, market signals, compliance). Each carries
`source`, `reliability` (tentative / supporting / corroborated /
verified) and `evidence_refs`. **Vanity kinds** (traffic, social,
impressions, downloads and vanity-only metric keys) are forced to
`reliability = tentative` and flagged `is_vanity` at write time —
they can never validate a business, improve a dimension beyond
evidence, or move an overlay to GROWING. Snapshot confidence is
derived from how many dimensions carry data (≥6 high, ≥4 moderate)
and is reduced by the reconciliation gate. Customer counts are
**counts only** derived from P-07's `revenue.list_revenue` read API
(audit gap G-1); period change is detected by differencing
successive snapshot readings, never by summing records (gap G-2).

## 5. Decision engine (§28.5, prompt §8)

`business_decisions` record the §8.2 ten questions (trigger,
evidence, metrics, risk, expected benefit/cost/downside,
confidence, reversibility, horizon, expiry, review conditions)
with ≥ 3 alternatives (§8.3) — defaults maintain / improve /
expand are supplied when the caller provides fewer, and for CLOSE
the third default is pause-and-review, never "expand". Every
decision also writes a P-02 `DecisionRecord` (the id is stored as
`intelligence_record_id`) — P-08 references P-02, it does not copy
it. A score (`score_bps`) is recorded as support only; it is never
consulted as permission (§8.4).

Approval: Level ≥ 3 decisions require a P-01 hash-bound approval
(action `survival.decision`, or `survival.close` for CLOSE) that
`review()` verifies — binding intact, status approved, and for
Level ≥ 3 the approver id must be `owner:*` (an agent deciding its
own request fails verification; §26.3 test). Execution is
idempotent: the first execution's key and timestamp stand; any
repeat — same key or a different one — is a replay that changes
nothing.

## 6. Experiment management + stop-loss (§28.6/7, prompt §9)

Creation validates all §9.2 fields (hypothesis, problem, target
customer, expected outcome, success/failure metrics, minimum
evidence, max duration, approved budget, maximum acceptable loss,
evaluation schedule) **before** anything is recorded; an incomplete
declaration records nothing. `declaration_id` may reference the
business's approved P-06 declaration (reconciled, not duplicated).
Owner approval creates the linked P-07 budget (scope `experiment`)
— the budget is the enforcement surface. `authorise_spend` is the
gate in front of P-07 spend: stopped/concluded/not-running
experiments and over-remaining amounts are refused with
`PermissionDeniedError`.

Stop-loss is mechanical (`check_stop_loss`): spent + committed
(P-07 `budget_utilisation`) ≥ approved budget → `budget_exhausted`;
≥ maximum acceptable loss → `max_loss_reached`; past the declared
deadline → `time_limit`. Tripping sets the experiment STOPPED with
the reason recorded. Evaluations (§9.5) classify by evidence:
VALIDATED additionally requires the observed success-metric value
and spend within cap. Failed experiments are permanent records —
no delete route or repository delete exists for experiments,
evaluations, snapshots, decisions, forecasts or outcomes (§9.5,
§32 rule 18). Sunk cost is never read by any continuation path.

## 7. Scaling readiness rules (§28.8, prompt §10)

Criteria sets are configuration, seeded per P-06 template category
(`digital_products`, `software`, `content`, `services`) in
`survival.settings.scaling_criteria` — a SaaS business (requires
MRR > 0; P-07 exposes MRR, not a subscription count — audit gap
note) is not judged by content rules. Base criteria: verified
collected revenue > 0; revenue in ≥ 2 snapshots (sustained demand);
≥ 3 distinct customers; ≥ 1 repeat customer; non-negative P-07
gross profit; refund rate ≤ 0.10; chargeback rate ≤ 0.02; delivery
evidence (operations observation ≥ 0.8 completion, or P-07
collected volume); available capital > 0; health classification
STABLE or better; no blocking hard gates. The report lists
satisfied AND unsatisfied conditions with sources, a downside
scenario, capacity requirements and approval requirements. Stages
0–6 are computed from which conditions hold. Status: READY /
NOT_READY / BLOCKED (blocking gates).

Plans (§10.3/§10.4) reference a real P-07 budget and must increase
it: the proposal is clamped to `current + current ×
max_increment_ratio` (default 0.5) **and** to `current + P-07
available capital`; `strict` mode refuses instead of clamping. A
₹10,000 budget can therefore never become ₹50,000 in one step.
Plan approval is owner-only (Level 3, hash-bound approval created
and verified in P-01) and changes no P-07 budget — applying a plan
is an owner action in P-07 (§16.4).

## 8. Growth strategy evaluation (§28.9, prompt §11/§12)

Growth and cost proposals are decision records (EXPAND_MARKET,
EXPAND_PRODUCT, OPTIMIZE, REDUCE_COSTS) carrying current-vs-proposed
figures as declared expectations with the P-07 readings attached as
evidence; market research routes to P-03 (no second discovery
engine). Nothing is auto-cancelled or auto-spent: material or
irreversible changes are Level 3 decisions requiring the approval
flow above (§12.3).

## 9. Recovery methodology (§28.10, prompt §13)

Plans require a finite budget, a finite timeline (review date is
computed at creation) and declared success AND failure thresholds
— an open-ended plan is rejected at validation, so recovery can
never become an indefinite subsidy. Root cause and failure kind
(operational / market / product / financial / temporary /
structural vocabulary) are recorded with the P-07 readings frozen
as evidence. Conclusion is once-only with outcomes RECOVERED /
IMPROVING / NO_SIGNIFICANT_CHANGE / DETERIORATING /
RECOVERY_FAILED; a concluded plan's outcome is history and cannot
be rewritten.

## 10. Portfolio management + capital allocation (§28.12/13, prompt §15/§16)

Consolidated figures are P-07's `consolidated` output verbatim
(internal transfers already excluded by P-07). Concentration
combines P-06 channel records (platform dependency: ≥ 2 businesses
on one platform is named a risk — record count is explicitly not
diversification) with per-business dominant-channel shares from
P-07 `revenue.metrics` against the owner-governed threshold
(default 0.6). Capital allocation produces **proposals only**
(§16.4): each is capped by the business's own P-07 available
capital and the per-business share cap (default 0.5), carries the
health classification/score as its risk adjustment with the full
rationale, and totals never exceed available capital. A proposal
sourced from `protected_reserves` is recorded **BLOCKED** — the
record is the audit trail of the refusal; only an owner policy
change inside P-07's own governance could alter reserves.

## 11. Agent and resource allocation (§28.14, prompt §17)

Resource proposals measure first: assigned agents (P-06
assignments) with P-04 `agent_metrics` (completed/failed), plus the
owner's hardware profile from settings (max 4 concurrent agents,
1 inference slot — the P-00 CPU-only verdict). Reassignment,
workflow-optimisation and pause-idle alternatives are always
listed before any creation recommendation; with no measured
workload the recommendation is 0 new agents. P-08 creates no
agents: creation remains P-04's reuse-first flow.

## 12. Forecasting methodology (§28.15, prompt §18)

P-08 forecasts are **frozen at creation and never rewritten**
(§18.4 — the service exposes no update path). Inputs freeze the
current P-07 readings with the record; `expected` values are
declared scenario expectations (conservative / base / optimistic,
each with its assumption set), labelled `classification:
"forecast"` in every payload. Forecast-vs-actual delegates the
error computation to P-07's `forecasting.forecast_vs_actual` when
the forecast references a P-07 forecast; otherwise it reports the
variance between the frozen expectation and the current P-07
reading — both reproduced verbatim. §21 decision outcomes record
expected vs actual, cost, forecast error, and a `decision_quality`
judged against the evidence available when the decision was made —
a good outcome does not retroactively make a bad decision good.

## 13. Decision approval model + AI decision boundaries (§28.16/17, prompt §20/§3)

Autonomy levels: 0 CONTINUE/MONITOR (routine), 1 INVESTIGATE /
REVIEW_FOR_CLOSURE, 2 OPTIMIZE / REDUCE_COSTS / PAUSE, 3
RUN_EXPERIMENT / INCREASE_RESOURCES / SCALE / EXPAND_MARKET /
EXPAND_PRODUCT / CHANGE_STRATEGY / RECOVER (owner approval
required), 4 CLOSE (**owner-only; agents cannot even originate a
CLOSE decision** — they may recommend REVIEW_FOR_CLOSURE). No LLM
exists in staging and none is consulted: every rule above is
deterministic code, every figure traceable to a P-07 reading or a
labelled declaration. The analyst (§19) is a deterministic
structured interface over P-02's pattern with 13 intents; every
figure it returns is classified verified_fact / calculated_metric
/ forecast / assumption / missing. The natural-language layer is
NOT IMPLEMENTED (see implementation report §20).

## 14. API documentation (§28.19, prompt §23)

`/api/v1/survival/...` — 59 routes: engine status/settings;
per-business reading, observations, monitoring events, checks,
evaluate, health (latest + history + one snapshot), lifecycle
(view + history + overlay), pause/resume, decisions (create, list,
get, approval, review, execute), experiments (declare, list, get,
approve, start, spend, stop-loss, stop, evaluate, evaluations),
scaling (assess, assessments, plans, plan approve), recovery
(plans, conclude), closure (propose, reviews, get, advance,
execute), forecasts (create, list, vs-actual), outcomes (record,
list); portfolio overview/concentration/allocations/resources;
analyst query. Permissions mirror P-07 (`read_business_data` /
`modify_business_data` / `approve_actions`) with per-business
access mirroring P-07's `assert_business_access`. No DELETE route
exists for any permanent record.

## 15. Database schema (§28.20, prompt §22)

One additive migration `99902c03a197` (revises `c3b5cdba2559`):
18 tables — business_health_snapshots, business_health_dimensions,
business_monitoring_events, business_observations,
business_decisions, business_decision_alternatives,
business_lifecycle_overlays, business_experiments,
experiment_evaluations, scaling_assessments, scaling_plans,
recovery_plans, closure_reviews, capital_allocation_proposals,
resource_allocation_proposals, survival_forecasts,
decision_outcomes, business_pause_controls. 90 → 108 tables at
head; downgrade/re-upgrade verified exactly. History tables are
append-only by API design. Amount columns on P-08 tables are
declared proposal/declaration amounts only; reported figures live
in verbatim P-07 payload JSON.

## 16. Monitoring schedules (§28.21, prompt §6.3)

Event-driven plus on-demand: `evaluate` runs one bounded pass
(collect → checks against the previous snapshot's readings →
snapshot). Checks emit monitoring events for loss-making,
collected-revenue decline (a comparison of two P-07 readings),
unresolved reconciliation and short runway. No polling daemon was
added; a scheduler outside P-08 may call `evaluate` on whatever
cadence the owner configures.

## 17. P-09 integration requirements (§28.24)

P-09 consumes: `decision_outcomes` (structured learning records
with references to P-02/P-08 records — never copies of financial
data), health snapshot history, experiment evaluations and
forecast-vs-actual records. Memory must reference P-07 ledger
records, never mirror them; Article 0 applies — memory is data,
never authority (see tracker notes for P-09 Stage 1).
