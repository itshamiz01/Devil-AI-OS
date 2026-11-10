# P-17 — Customer Intelligence (§4.1/§4.2)

**Phase:** P-17 Customer Acquisition, Marketing & Revenue Growth Engine
**Surface:** brand profiles (§6), customer personas (§4.1), ideal
customer profiles (§4.2) — `app/growth/intelligence.py`,
`/api/v1/growth/businesses/{id}/brand|personas|icps`.

## What exists

- **Personas** are research records, not facts. Every persona carries
  an `evidence` list whose items are labelled with an honesty kind —
  `verified | public_research | assumption | hypothesis` — validated
  at creation; an unlabelled or invented kind (e.g. "scraped") is
  refused. Fields follow the prompt: segment, needs, problems,
  motivations, budget sensitivity, product category, objections,
  discovery channels, buying journey, demographics (owner-declared,
  lawfully available only).
- **ICPs** exist in B2B and B2C kinds with their respective criteria
  vocabularies (`constants.B2B_CRITERIA` / `B2C_CRITERIA`). Priority
  is computed by `scoring.icp_priority` from the six declared factors
  (product fit, demand, commercial potential, acquisition
  feasibility, retention potential, strategic fit) with owner-editable
  weights. Missing factors score 0 and are reported in
  `missing_factors` — a thin assessment can never look complete.
  Every response labels the score a *prioritisation estimate, not a
  demand measurement*.
- **Brand profiles** are one per business (unique on business_id)
  and never cross businesses: identity, tone of voice, colours,
  typography, logo refs, messaging guidelines, product information,
  assets, and the `prohibited_claims` list that the content workflow
  enforces mechanically (see P17_CONTENT_PRODUCTION).

## Honesty rules

- Nothing is scraped, purchased or inferred from third-party data;
  records exist only because the owner entered them.
- Scores are deterministic arithmetic over declared inputs, stored
  with the inputs, so any number can be re-derived.
