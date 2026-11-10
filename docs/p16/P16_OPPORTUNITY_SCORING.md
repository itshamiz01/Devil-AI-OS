# P-16 — Opportunity Scoring (§4.3)

**Module:** `app/economy/scoring.py` (pure functions, unit-pinned)

## The §4.3 model, exactly as specified

| Factor | Weight |
|---|---|
| Market demand | 20 |
| Profitability potential | 15 |
| Competitive advantage | 15 |
| Scalability | 15 |
| Capital efficiency | 10 |
| Operational feasibility | 10 |
| Revenue diversification | 5 |
| Strategic compatibility | 5 |
| Risk profile | 5 |

Risk is entered as a *level* and inverted (`100 − risk`) so a
higher score always means a better opportunity. Weights are
owner-governed settings; the defaults above are the prompt's.

**Bands (code tokens):** `reject_or_archive` (0–39) ·
`research_further` (40–59) · `controlled_experimentation` (60–74) ·
`strong_candidate` (75–89) · `strategic_candidate` (90–100).

## What a score is not

The prompt is explicit and the implementation follows it: a score
is prioritisation, never a probability of success, never a revenue
forecast. Nothing in P-16 converts a score into money.

## Confidence — from evidence only

Confidence is computed mechanically from the attached evidence
list, never supplied by a caller:

- 22 points per source-backed evidence item (an item with a
  `source_ref`), 8 per unbacked item;
- +10 corroboration bonus at ≥3 source-backed items;
- capped at 100.

Three source-backed items → 76. Zero evidence → 0, and the
evidence gate (default: confidence ≥ 50 **and** ≥2 items) blocks
`approval_pending` regardless of score.

## Integrity details

- Unknown factor keys are **refused** with the valid vocabulary in
  the error (a mistyped key must never change a score invisibly) —
  regression-tested after the live smoke caught silent dropping.
- Missing factors **score 0** and are reported in
  `missing_factors` — a thin assessment can never look complete;
  there is no renormalisation.
- Every scoring run is reproducible: same factors + same weights →
  same score (unit-pinned, including the risk-inversion constant).
