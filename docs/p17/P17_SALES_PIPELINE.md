# P-17 — Sales Pipeline (§10)

**Surface:** `/api/v1/growth/businesses/{id}/opportunities`,
`/api/v1/growth/opportunities/{id}/transition`,
`/api/v1/growth/businesses/{id}/pipeline`.

## Model

A sales opportunity is one prospective deal with one lead/customer
of one business — not a P-03 business opportunity and not a P-16
economic opportunity. Eight stages (new, discovery, qualification,
demonstration, proposal, negotiation, closed_won, closed_lost)
with default win probabilities expressed as declared percents
(5/10/25/40/60/80/100/0), overridable per deal within 0–100.

## Discipline

- `estimated_value_minor` is labelled ESTIMATE in every response;
  the probability-weighted pipeline total is a forecast, never
  revenue. Realised revenue exists only in P-07.
- Closing as lost **requires** a `lost_reason`.
- The pipeline summary aggregates per stage (count, estimated
  value, weighted value) and repeats the ESTIMATE label on the
  whole view.
