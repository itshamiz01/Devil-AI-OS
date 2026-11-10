# P-17 — Marketing Attribution (§22)

**Surface:** `GET /api/v1/growth/businesses/{id}/attribution`,
campaign metrics, partnership list.

## The one rule

Attributed revenue is **P-07 verified collected revenue grouped by
channel tag** — campaigns under `p17-<code>`, partners under
`partner-<code>` — read live from P-07 revenue metrics
(`by_channel_minor`). It is labelled ATTRIBUTED in every response,
with the standing note: *attribution associates revenue with a
channel; it does not prove the channel caused it, and attributed
totals are never accounting revenue.*

## Methods

- **First-touch:** available — CRM customers counted by their
  recorded acquisition channel.
- **Last-touch:** `not_available` — no last-touch channel is
  captured per customer (only the acquisition channel is), and the
  engine says so rather than inventing a journey.
- **Multi-touch:** `not_available` — no journey-level touchpoint
  capture exists; any weighting would be fabricated.

## What attribution never does

It never writes to P-07, never reclassifies revenue, and never
feeds the profitability gate (the gate reads P-07's own profit
figures via P-16, untouched by attribution). Projected or
simulated figures are never mixed into attributed totals.
