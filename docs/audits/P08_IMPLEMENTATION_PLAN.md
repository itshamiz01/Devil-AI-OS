# P-08 IMPLEMENTATION PLAN — Survival and Scaling Engine

Derived from `docs/prompts/P08_PROMPT.md` (§29 stage order) and the
Stage-1 audit (`P08_PRE_IMPLEMENTATION_AUDIT.md`). Where the prompt
and the existing code conflict, the audit's smallest-safe-change
mapping governs and is disclosed in the implementation report.

## 1. Package layout (repo conventions: one service package per phase)

```
backend/app/survival/
  __init__.py
  constants.py   — settings key/defaults, classifications, decision
                   types + autonomy levels, overlay states, criteria
                   sets per business category, event source name
  monitoring.py  — §6: indicator collection (P-07 only), commercial
                   observations with provenance, monitoring events
  health.py      — §7: seven dimensions, hard gates, weighted score,
                   classification, snapshot persistence
  decisions.py   — §8/§20: decision records, alternatives, scoring,
                   approval flow (P-01 hash-bound), idempotent
                   execution, autonomy enforcement
  experiments.py — §9: pre-declared experiments, stop-loss engine,
                   evaluation + learning records
  scaling.py     — §10/§11/§12: readiness assessments, incremental
                   scaling plans, growth + cost proposals
  recovery.py    — §13/§14: recovery plans, pause, closure workflow
  portfolio.py   — §15/§16/§17: portfolio overview, concentration,
                   capital-allocation proposals, resource proposals
  forecasting.py — §18: P-07-consuming survival/growth forecasts,
                   scenario records, forecast-vs-actual learning
  analyst.py     — §19: deterministic structured query interface
  service.py     — SurvivalService facade (settings, access control,
                   emergency pause, lifecycle overlay, engine status)
backend/app/database/models/survival.py        — 13 tables (§2)
backend/app/database/repositories/survival.py  — repositories
backend/app/api/routes/survival.py             — /api/v1/survival/...
backend/app/api/schemas/survival.py            — request schemas
backend/app/database/migrations/versions/<rev>_p08_survival_scaling_engine.py
```

Wiring: `Application.survival` built after `financial` (needs
business + financial + agents + execution + intelligence recorder);
new `EventType`s appended additively; models registered in
`models/__init__.py`.

## 2. Data model (ONE additive migration; §22 adapted)

All P-08 tables are append-only history or proposal records; no
table stores a financial amount that P-08 computed (amounts stored
are *copies of P-07-returned figures inside snapshots/proposals*,
labelled with source + timestamp, or owner/agent-declared proposal
amounts — never ledger facts).

1. `survival_settings` — not a table: owner-governed `system_config`
   key `survival.settings` (weights, thresholds, criteria sets,
   increment cap, autonomy policy) — Article 0 pattern.
2. `business_health_snapshots` — per evaluation: classification,
   score, currency, indicator payload (P-07 verbatim), hard gates,
   explanation, overlay state, confidence.
3. `business_health_dimensions` — per snapshot × 7 dimensions:
   status, score, evidence refs, freshness, confidence, missing.
4. `business_monitoring_events` — monitoring findings (kind,
   severity, payload, provenance).
5. `business_observations` — commercial/operational observations with
   provenance + reliability + vanity flag (§6.2/§6.3).
6. `business_decisions` — §8.1 record (type, trigger, evidence,
   metrics, risk, benefit, cost, downside, confidence, reversibility,
   horizon, autonomy level, approval ref, expiry, review conditions,
   status, execution idempotency + outcome).
7. `business_decision_alternatives` — ≥3 where safe (§8.3).
8. `business_lifecycle_overlays` — P-08 overlay transitions (§5.3
   history: from/to, decision ref, evidence, approval ref, actor).
9. `business_experiments` — §9.2 pre-declaration (all 16 fields),
   lifecycle status, linked P-07 budget id, P-06 declaration ref.
10. `experiment_evaluations` — §9.5 outcome classification, actuals
    (P-07 readings), lessons, next step. Immutable once written.
11. `scaling_assessments` — §10.3 readiness report (stage, satisfied/
    unsatisfied conditions, confidence reductions e.g. recon).
12. `scaling_plans` — incremental plan (current → proposed budget as
    P-07 figures, increment ratio, success/stop conditions, approval).
13. `recovery_plans` — §13 assessment + plan + outcome classification.
14. `closure_reviews` — §14 workflow stages + obligation inventory
    (P-07 figures), owner approval ref, wind-down record.
15. `capital_allocation_proposals` — §16 proposals (source of figures
    = P-07; status proposal-only; protected-reserve flag → blocked).
16. `resource_allocation_proposals` — §17 workload-based proposals.
17. `survival_forecasts` — §18 forecasts (frozen at creation;
    assumptions, scenario kind, P-07 forecast ref).
18. `decision_outcomes` — §21 learning records (expected vs actual,
    quality judgement vs evidence-at-the-time, lesson; P-09-ready).
19. `business_pause_controls` — emergency/operational pause flags
    (§25.2: reason, actor, lifted_by, timestamps).

(19 logical stores; settings live in system_config per convention.
The migration creates the 18 tables above excluding settings.)

## 3. Stage order (§29)

1. Audit + plan (these documents) + baseline run. ✔
2. Monitoring: indicator collection via `p08_indicators` +
   `business_summary`; observations; monitoring events.
3. Health engine: dimensions, hard gates, scoring, snapshots.
4. Decision engine: records, alternatives, approvals, idempotent
   execution, autonomy levels.
5. Experiments: pre-declaration, budget link, stop-loss, evaluation.
6. Scaling/growth: readiness, incremental plans, growth + cost
   proposals (P-03 referenced for market research, never duplicated).
7. Recovery/closure: at-risk flow, recovery plans, pause, closure
   workflow with obligation inventory.
8. Portfolio/capital/resource: P-07 consolidated reads, concentration
   from P-07 channel shares + P-06 channels, allocation proposals,
   P-04-backed resource proposals.
9. Forecasting/learning: P-07 forecast consumption, frozen P-08
   forecasts, forecast-vs-actual via P-07, decision outcomes.
10. Frontend: none (API-only) — recorded, not built.
11. Integration + audit: full suite, security suite, scenarios,
    smoke, reports, tracker, zip.

## 4. Hard-gate catalogue (health + scaling)

- `cash_below_obligations`: P-07 available_cash < 0 or obligations >
  cash balance → classification at least AT_RISK; scaling blocked.
- `unresolved_reconciliation`: P-07 unresolved recon items > 0 →
  confidence reduced; **material** allocation/scaling blocked (§7.3).
- `compliance_violation`: recorded governance observation of kind
  compliance_violation (provenance required) → scaling blocked,
  classification at most WATCH.
- `security_incident`: pause control active → classification CRITICAL
  overlay + execution blocked.
- `unverified_revenue_only`: collected revenue == 0 while projected/
  booked > 0 → financial dimension cannot exceed INSUFFICIENT_DATA;
  vanity observations never validate (§3.1/§6.2).
- `loss_making`: P-07 profitability is_loss → scaling recommendation
  prohibited; INVESTIGATE + REDUCE_COSTS decisions generated.
- `protected_reserve`: any proposal whose source includes protected
  reserves → BLOCKED status, owner policy change is the only path.

## 5. Scaling criteria sets (configuration, per P-06 category)

Seeded in settings for `digital_products`, `software` (SaaS),
`content`, `services` with different thresholds (e.g. SaaS requires
MRR presence + subscription retention evidence; content requires
repeat-purchase/audience-conversion observations; all require:
verified collected revenue > 0, non-negative contribution (P-07
gross profit ≥ 0 where computable), ≥2 health snapshots showing
demand, refund rate below threshold, no hard gate, available capital
≥ proposed increment). Criteria are data, owner-editable via
settings; changing them is a governance write (owner-only).

## 6. Incremental scaling rule (§10.4)

`max_increment_ratio` default **0.5** (a plan may propose at most
+50% over the current P-07 budget figure per step) and never more
than available capital (P-07). A request beyond the cap is clamped
in the proposal with the clamp disclosed, or refused if the caller
demands the uncapped figure. ₹10,000 → ₹50,000 (5×) is therefore
structurally impossible in one step.

## 7. Structural proofs (tests)

- **No competing financials:** static test scans `app/survival/*.py`
  source: no references to ledger/journal/revenue/expense
  repositories or models; no `float(` for money (ratios use Decimal
  over P-07-returned ints); P-08 tables contain no column named
  `*_revenue`/`*_profit`/`*_collected` of its own computation —
  snapshot payloads are verbatim P-07 dicts (asserted by comparing a
  snapshot's figures to a fresh `p08_indicators` call).
- **No deletion:** experiments/evaluations/outcomes/snapshots expose
  no DELETE route and the service has no delete method (route-table
  assertion).
- **Level 4 structural:** agent principal attempting CLOSE decision
  approval/execution → refusal even with a self-created approval
  object (approval approver must be owner + binding verified).

## 8. Smoke (real uvicorn, `docs/reports/P08_SMOKE_EVIDENCE.txt`)

Honesty check on a real staging fixture business FIRST, then
S1, S2, S4, S5, S7, S9, S12, S15 per the gate brief, seeded only
through P-07's authorised paths (provider-report revenue, paid
expenses, opening balances, budgets, reserves, reconciliation
imports) and P-08's own observation/decision APIs.
