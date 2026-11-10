# P-17 — Lead Scoring (§9)

**Surface:** `POST /api/v1/growth/leads/{id}/score`.

## Closed factor vocabulary

Scoring accepts exactly eight declared factors — product interest,
requirements fit, budget compatibility, business fit, engagement,
purchase intent, decision authority, timing — with owner-editable
weights (defaults 18/14/14/14/12/14/7/7). Any other key is refused
with the valid list, so the vocabulary cannot quietly grow.
Sensitive personal attributes are not in the vocabulary at all, by
construction.

## Semantics

`scoring.lead_score` computes a weighted 0–100 score and a band
(`high_priority ≥ 85`, `qualified_prospect ≥ 70`, `potential ≥ 50`,
`nurture ≥ 30`, else `low_priority`). Missing factors score 0 and
are listed in `missing_factors`, with the full contribution
breakdown stored on the lead row alongside the inputs — the score
is reproducible from what is stored. Every response states the
score is *a prioritisation estimate, not a guarantee or probability
of purchase*.
