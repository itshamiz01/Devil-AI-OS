# P-16 ARCHITECTURE AND INTEGRATION REPORT

**Phase 1 deliverable (§20 Phase 1 / §24 Steps 1–7).** Written from a
direct inspection of the staging repository on 2026-11-10, on top of
the verified P-15 close-out state: backend 812 passed / 0 failed,
frontend 43/43, live smoke 25/25, migration head `d12e4d6cf5ef`,
177 physical tables, classification READY FOR CONTROLLED PILOT
(DEF-A1 Windows UNVERIFIED and DEF-A2 no real LLM remain open
owner-machine items; P-16 does not touch either and claims neither).

## 1. What already exists (inspected, not assumed)

| Concern | Owner today | P-16 relationship |
|---|---|---|
| Business identity + lifecycle | P-06 `BusinessCreationService`; `businesses` table (18-state machine, `is_fixture` labelled) | Read-only consumer. P-16 never creates a business; creation stays on the governed P-03 → P-06 path. |
| All money | P-07 `FinancialService` — `business_summary()`, `p08_indicators()` (verified collected revenue, actual expenses, net profit, available capital, runway), `revenue.metrics()` (net/gross collected, MRR/ARR, by_channel / by_product / by_category) | **Only** source of financial figures. P-16 stores no ledger data and computes no competing totals. |
| Portfolio grouping, relationships, concentration settings, venture proposals | P-13 `PortfolioService` (registry, finance read-model, planning/venture handoff to P-03) | Reused for grouping and the relationship map. P-16 does not duplicate the registry, the venture flow, or P-13's internal allocations. |
| Opportunity research substrate | P-03 `OpportunityService` — opportunities, evidence records, market analyses, per-opportunity competitors, scores, validations | P-16's economic pipeline *references* P-03 opportunities; market/competitor depth for a specific opportunity stays in P-03. P-16 adds the economy-level pipeline, scoring (§4.3 weights differ from P-03's), and portfolio-driven discovery. |
| Experiments with real budget enforcement | P-08 `ExperimentService` — pre-declared experiments bound to a real P-07 budget, mechanical stop-loss, evaluations | P-16 experiment *proposals* hand off to P-08 on approval when a business is attached. P-16 builds no second experiment engine and no second stop-loss. |
| Approvals | P-01 `ApprovalService` — hash-bound, single-use, owner-decided | Every P-16 approval (allocation, reinvestment, strategy, handoff) is a P-01 approval; P-16 stores only the approval id reference. |
| Memory / learning | P-09 `MemoryService.ingestion.ingest()` (wired into P-05/P-06/P-07 in P-14 I6) | P-16 feeds *verified outcomes only* (experiment evaluations, decision outcomes) through the same ingestion path, best-effort. Memory remains data, never authority (Article 0). |
| Governance | P-10 PermissionBroker, owner-only policy writes, emergency modes | P-16 adds no authority. Writes are owner-gated in-service (P-13 pattern); economy pause/freeze flags compose with P-10 modes, never replace them. |
| Reliability | P-15 `ReliabilityService` + readiness snapshots | Untouched; P-16 registers no scheduler, sampler or breaker. |
| Command Center | P-11 SPA (Vite + React 19 + TS), views per engine on real endpoints | One new view, "AI Economy & Expansion Center" (§15), on `/economy/*` endpoints, existing design system. |
| Settings | `SystemConfig` via `ConfigRepository` (P-13/P-15 `seed_settings()` pattern) | P-16 settings (scoring gate thresholds, autonomy level, pause/freeze flags, reinvestment defaults) live under one config key. No settings table. |

## 2. What P-16 adds (and only this)

A new package `app/economy/` (constants, pure scoring/diversification/
stress math, service built from mixins — the P-13 shape), models in
`app/database/models/economy.py`, routes in `app/api/routes/economy.py`
under `/api/v1/economy`, one additive migration, one frontend view.

Thirteen new tables, all P-16-owned state that no earlier phase owns:

`market_reports`, `economic_opportunities`, `expansion_strategies`,
`business_classifications`, `commercial_assets`,
`commercialization_proposals`, `customer_segments`,
`allocation_recommendations`, `reinvestment_plans`,
`experiment_proposals`, `competitor_profiles`, `country_assessments`,
`economic_decisions`, `risk_assessments` — fourteen with
`risk_assessments` counted; each is a proposal, record or snapshot,
never an execution record.

### Money discipline (structural, test-pinned)

- P-16 tables contain **no ledger, balance or account columns**.
  Amount fields that do exist are *proposal data* (a recommended
  allocation, an experiment budget ceiling) in integer minor units,
  labelled `PROPOSED` in every response, following the P-13
  INTERNAL_ALLOCATION precedent: management proposals that provably
  leave P-07's consolidated output byte-equal (a named test asserts
  this before/after every P-16 write flow).
- P-16 has no transfer, payment, spend or execution method. Approved
  allocations are recommendations the owner may act on through P-07's
  own governed paths; the recommendation itself moves nothing.
- Every figure P-16 displays is either (a) read live from P-07 at
  request time, or (b) a labelled estimate/proposal/simulation.
  Collected and projected are never blended (P-13 rule, inherited).

## 3. The owner's strategic priority, encoded mechanically

The owner's appended directive — *profitability before new
businesses, then diversification, then capital efficiency; more
businesses do not automatically mean more wealth* — is not a comment
in the code; it is enforced by a **profitability gate**:

- `portfolio_profitability()` is computed live from P-07: the set of
  businesses with financial profiles, their verified collected
  revenue and verified net profit (`p08_indicators` contract).
- The gate is **CLOSED** when no business has verified collected
  revenue, or when aggregate verified net profit across profiled
  businesses is ≤ 0, or when profitability is indeterminate
  (INSUFFICIENT_DATA — the P-08 honesty posture).
- While the gate is closed:
  - new-business and market-entry strategies are created flagged
    `blocked_by_profitability_gate` and **cannot be approved**;
  - economic opportunities of kind `new_business` cannot advance
    past `financial_evaluation` in the pipeline;
  - the `growth` capital-allocation scenario is refused;
  - strategic recommendations (§15 Panel I) are ordered
    improvement → diversification → capital efficiency → new
    opportunity, and lead with the gate's reason.
- The owner — and only the owner — may record an explicit
  **gate override** (reason required, audited, stored on the
  strategy/opportunity it applies to). Human authority is preserved;
  the system never overrides itself.
- Experiment proposals for *existing* businesses (pricing, segment,
  channel tests) are **not** blocked by the gate: controlled
  experimentation aimed at making existing businesses profitable is
  the priority's first instrument, and P-08's budget/stop-loss
  discipline governs them.

## 4. §24 Step 8 handling (approval before structural changes)

Per the owner's standing one-by-one instruction (2026-11-10), the
internal approval wait is handled P-14-style: this architecture was
produced first, the **conservative minimal option** was taken at each
discretion point, and each choice is reported in the gate summary:

1. *Experiments*: reuse P-08 (handoff), not a new engine. ✔ minimal.
2. *Approvals*: reuse P-01 hash-bound approvals, no P-16 approval
   store. ✔ minimal.
3. *Portfolio scope*: economy reads span all P-06 businesses;
   P-13 portfolios are an optional lens, not a second registry. ✔.
4. *Country/competitor/market data*: records with mandatory source
   references, entered through governed writes — **no scraping, no
   fabricated market data**; the machinery ships with true zero
   states. ✔ (DEF-A2 posture: no real external research is claimed.)
5. *Schema*: one additive migration, fourteen tables, cycle-tested.
   No existing table altered. ✔.

## 5. Autonomy (§18) as implemented

Economy autonomy level 1–4 in owner-governed settings, **default 2
(Recommendation)**. Level 1 permits research records only; Level 2
adds proposals and pipeline movement short of experimentation;
Level 3 permits handoff of pre-approved, budget-limited experiments
to P-08 (P-08's own approval still applies); Level 4 changes nothing
about capital: new capital commitments, contracts and ownership
changes always require owner approval at every level. Owner-only
`expansion_paused` and `capital_commitments_frozen` flags refuse the
relevant transitions while set. The OS mode (simulation/supervised/
controlled) continues to govern as before; P-16 introduces no
self-promotion path.

## 6. Scoring (§4.3) as implemented

Exact prompt weights (demand 20, profitability 15, competitive
advantage 15, scalability 15, capital efficiency 10, feasibility 10,
diversification 5, strategic fit 5, risk 5). Factor inputs are
attractiveness scores 0–100 **except risk**, which is entered as a
risk level and inverted (`100 − risk`) before weighting — higher
risk mechanically lowers the total. Confidence is computed
separately from evidence: a deterministic function of evidence item
count and the source-backed share, 0–100. **Evidence gate:** an
opportunity cannot enter `approval_pending` with confidence < 50 or
fewer than 2 evidence items, whatever its score — a 95-point score
on weak evidence stays in research. Bands are the prompt's
(0–39 reject/archive, 40–59 research, 60–74 experiment, 75–89
strong, 90–100 strategic) and are labelled prioritisation, never
success probabilities.

## 7. Honest limits carried into this build

- No real market data exists in staging: market reports, competitor
  profiles and country assessments are governed records whose
  machinery is fully tested on labelled fixtures; their *content*
  awaits real research (P-03 path / owner input).
- No real LLM is exercised (DEF-A2 stands). All P-16 intelligence
  is deterministic: scoring math, HHI concentration, detectors over
  P-07 figures, stress arithmetic. Nothing is presented as AI
  judgement.
- Windows remains UNVERIFIED (DEF-A1 stands).
- Fixture businesses in staging carry `is_fixture=true` end-to-end;
  P-16 responses surface that label wherever fixture data feeds a
  figure.
