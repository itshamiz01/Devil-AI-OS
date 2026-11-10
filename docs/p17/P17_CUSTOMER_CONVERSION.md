# P-17 — Customer Conversion (§10/§11/§13)

## The conversion path

Lead (authorised source, consent recorded) → scored (§9) →
pipeline stages → `converted` → CRM customer → P-07 purchases by
customer ref → health and LTV read models. Each step is a governed
service call; nothing converts automatically.

## Funnel (§13)

`POST /api/v1/growth/businesses/{id}/funnel-events` records
stage counts for the eight-stage funnel (awareness, interest,
consideration, intent, conversion, onboarding, retention,
expansion). Counts must carry a period and a source label —
`declared | imported`. The summary keeps three things visibly
separate:

- **declared counts** (labelled DECLARED — owner/imported figures,
  not measured by AUTONOMUS, which operates no website);
- **system counts** (leads recorded, qualified leads, converted
  customers — counted from the engine's own records);
- **conversion rates + bottleneck** computed by
  `scoring.funnel_rates` over the declared counts, where the
  bottleneck ignores drops whose base is under 10 (noise floor)
  and a rate is `null`, never invented, when its base is zero.
