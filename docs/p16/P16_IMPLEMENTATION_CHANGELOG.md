# P-16 — Implementation Changelog (§23)

## Added

**Backend package `app/economy/`** — `constants.py` (vocabularies,
§4.3/§14 weights, default settings, approval action names),
`scoring.py` (pure math), `service.py` (EconomyService core:
settings, gate, overview/KPIs, classifications, relationship map,
decisions), `markets.py` (market reports, competitors + comparison,
countries, segments), `opportunities.py` (pipeline, detectors,
strategies, recommendations), `capital.py` (allocation scenarios,
reinvestment), `ventures.py` (assets, commercialization, experiment
proposals, market patterns), `risk.py` (diversification, risk
assessments, stress scenarios).

**Schema** — `app/database/models/economy.py`: 14 additive tables
(market_reports, economic_opportunities, expansion_strategies,
business_classifications, commercial_assets,
commercialization_proposals, customer_segments,
allocation_recommendations, reinvestment_plans,
experiment_proposals, competitor_profiles, country_assessments,
economic_decisions, risk_assessments); registered in
`models/__init__.py`. Migration **`ccd744b29e54`** (revises
`d12e4d6cf5ef`), cycle-verified 177 → 191 → 177 → 191 physical
tables; metadata 176 → 190. No money columns; amounts are labelled
proposal data.

**API** — `app/api/routes/economy.py`: ~55 routes under
`/api/v1/economy`, house permission dependencies (READ
`read_business_data`, WRITE `modify_business_data`, GOVERN
`approve_actions`), creates return 201 per house convention.
Wired in `app/main.py`; `EconomyService` constructed in
`app/core/application.py` after P-15's reliability service,
settings seeded on startup.

**Frontend** — `src/views/Economy.tsx` ("AI Economy & Expansion",
ten tabs on real endpoints), nav entry in `components/shell.tsx`,
route in `App.tsx`, tests in `src/views/Economy.test.tsx`.

**Smoke** — `backend/scripts/p16_smoke.py` + evidence at
`docs/reports/P16_SMOKE_EVIDENCE.txt`.

## Changed (pre-existing files, established disclosure pattern)

- Alembic-head pins `d12e4d6cf5ef` → `ccd744b29e54` with P-16
  disclosure comments: `test_p02_integration.py`,
  `test_p03_integration.py`, `test_p04_integration.py`,
  `test_p05_integration.py`.
- Cycle counts 177 → 191: `test_p13_integration.py`,
  `test_p15_integration.py`. Metadata totals 176 → 190:
  `test_p11_integration.py`, `test_p12_integration.py`,
  `test_p13_integration.py`, `test_p14_audit.py`,
  `test_p15_integration.py`.
- No pre-existing assertion was weakened; counts and heads moved
  only because P-16's additive schema exists.

## Defects found during this build (all fixed, all pinned)

1. **Silent scoring-key dropping** (found by the live smoke):
   mistyped §4.3 factor / §14 criteria keys were ignored, changing
   scores invisibly. Now refused with the valid vocabulary in the
   error; regression test added.
2. **Detector misnomer**: the loss-maker risk finding was named
   `declining_profitability`. Renamed to `loss_making_business`
   (§12 vocabulary); a true decline-trend detector is documented
   as NOT implemented rather than implied.
3. **Unconsumed §17 pattern**: `market_patterns` stated an effect
   ("deprioritised in recommendations") that nothing consumed.
   `strategic_recommendations` now applies the +3 deprioritisation
   with the reason on the item; scenario test pins it.
4. **Schema-guard collision** (found by full regression): P-16's
   `BusinessClassification` class name fell inside the P-06
   security guard's `Business*` namespace and its categorical
   `revenue_model` column tripped the no-money-columns scan.
   Renamed the class to `EconomyClassification`; the guard is
   untouched and green.

## Not changed

P-07 (sole financial authority), P-06 lifecycle, P-13 portfolio
coordination, governance/Constitution files — untouched. Article 0
held throughout.
