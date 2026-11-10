# P-03 — Market & Customer Analysis Engine (§10, §11)

Implemented in `app/opportunities/analysis.py`; market rows persist in `market_analyses`.

## Demand derivation (evidence-capped)

Demand stage is *derived from evidence categories*, never asserted:

| Evidence available | Derived stage |
|---|---|
| none | none |
| problem mentions only | problem_recognition |
| + demand mentions (problem-focused content) | active_problem_awareness |
| + comparison/evaluation behaviour | product_evaluation |
| + purchasing-intent records | purchasing_intent |

**Search volume, page views and social engagement are recorded as attention, not purchasing intent** (§10.3) — only evidence explicitly categorised as purchasing intent moves the stage there. Customer segments are derived only from brief/opportunity-stated targeting; personas are only created when grounded in evidence (§10.6) — in staging, segments come from the opportunity definition and are labelled as such.

## Market size (§10.5)

TAM/SAM/SOM are emitted **only** when corroborated market-size evidence exists, in which case the stored figure is the corroborated value with the method "corroborated published estimate (bottom-up verification not performed by P-03)". In all other cases the analysis states **"cannot be established from available verified evidence"** — the state of every staging investigation today. The system never invents a market size.

## Saturation (§10.4, §11)

Saturation is derived from competitor records: 0 recorded → **unknown** (absence of research is not an empty market); 1–2 → low; 3–5 → moderate; 6+ → high. A dedicated test proves a saturated market (8 competitors) drags the competitive-opportunity score down versus the same market with 1 competitor.

## Competitor analysis (§11)

`competitors` rows carry name, offer, audience, price, strengths/weaknesses, distribution, differentiation and the evidence each item came from. The competitor-gap report (`GET /opportunities/{id}/competitor-analysis`) computes: evidence gaps (competitor claims with no corroboration — explicitly listed as gaps, §11.4), unserved audiences, common weaknesses, common complaints, price range from recorded competitor prices only, and distribution channels in use. It never fabricates competitor facts: a competitor analysis with zero recorded competitors says so.

## Distribution analysis (§14)

Channels are assessed for realism only: the analysis never assumes organic traffic will arrive or that paid ads will be profitable. Spam, fake reviews, fake engagement and misleading advertising are hard-rejected at scoring (§16.10) and prohibited at screening. Smoke finding recorded per investigation: e.g. the e-book's distribution note states KDP discovery is competitive and no traffic is assumed.
