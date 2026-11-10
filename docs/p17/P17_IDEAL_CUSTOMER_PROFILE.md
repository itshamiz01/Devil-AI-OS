# P-17 — Ideal Customer Profile (§4.2)

**Surface:** `POST/GET /api/v1/growth/businesses/{id}/icps`.

## Model

One ICP per segment per business, `kind ∈ {b2b, b2c}`:

- **B2B criteria:** industry, company size, business model,
  operational challenges, technology requirements, purchasing
  capacity, decision-maker roles, procurement requirements, sales
  cycle.
- **B2C criteria:** needs, product preferences, motivations, price
  sensitivity, purchase frequency, expectations, retention potential.

Criteria are held as a declared dict; the record does not pretend
to be a market measurement.

## Priority scoring

`scoring.icp_priority(factor_scores, weights)` — weighted mean over
the six factors with weights `product_fit 3, demand 3,
commercial_potential 3, acquisition_feasibility 2,
retention_potential 2, strategic_fit 2` (owner-editable in growth
settings). Unknown factor keys are refused at the service layer so
the vocabulary stays closed and auditable.

The list endpoint orders by priority score and returns a plain
recommendation ("prioritise segment X first") or, with no ICPs, an
explicit statement that no evidence-based recommendation exists.
