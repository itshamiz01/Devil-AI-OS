# P-16 — Business Portfolio (§5)

**Module:** `app/economy/service.py` · **Table:** `business_classifications`

## Classification (§5.1)

P-16 stores one owner-declared classification per P-06 business:
industry, business model, revenue model, recurring-revenue model,
market, customer type, geography, digital/physical, product/service
mix and strategic importance. Classification is declaration, not
inference — the system never guesses an industry.

## Lifecycle (§5.2) — derived, never stored

The nine lifecycle labels (`Idea, Validation, Launch, Early
Revenue, Growth, Established, Optimisation, Declining, Exit
Candidate`) are derived at read time: P-13's `portfolio_stage()`
over the business's P-06 status, mapped through P-16's label map.
P-16 keeps no lifecycle state machine of its own — P-06 owns
lifecycle, P-13 owns portfolio stage.

## Relationship map

`GET /economy/relationship-map` reads P-13 portfolios and
relationships (as a system principal) and enriches them with
owner-declared P-16 classifications. Cross-selling candidates —
businesses sharing a declared market or revenue model — are
returned with the label "candidate synergy only — shared
audiences, customer data and resources require consent,
contractual rights and privacy protection before any use (§5)".
The map enables analysis; it moves no data, customers or money
between businesses (P-13 §11 isolation holds).

## Concentration

Per-business revenue share of verified collected revenue is
computed on every classifications read; businesses above the
owner's threshold (default 60%) are listed in
`overconcentration_flags` and feed the risk detectors (§12).
