# P-16 — Global Expansion (§14)

**Module:** `app/economy/markets.py` · **Tables:** `country_assessments`,
`customer_segments`

## Country assessment

Each assessment scores a country on the prompt's criteria —
demand, purchasing power, regulation, tax, payments, language,
currency risk, competition, distribution cost, data protection,
IP protection — as a weighted mean (demand double-weighted by
default; weights are owner settings). Recorded facts that are not
scores — payment methods present, tax points, language notes —
live in the assessment's **entry checklist**, so the score and the
facts are never confused.

Unknown criteria keys are refused (same silent-drop regression
class as §4.3 factors).

`GET /economy/countries/ranking` orders assessed countries by
score and states its methodology in the response: scores compare
**owner-recorded assessments only**; an unscored country is
absent, not zero.

## Segments and the international rule

Customer segments (§8) are owner-recorded (B2B/B2C, individual/
company size, geography, industry, price sensitivity, …). A
segment of kind **geographic** cannot be recorded without the
§8 international checklist (tax, regulations, payments, currency,
consumer protection, privacy, localization, distribution) — the
§14 rule that international expansion is a checklist, not a mood,
enforced at creation.

## What P-16 does not do

No country is entered, no entity registered, no payment rail
connected. Market-entry *strategies* are additionally blocked by
the profitability gate while the portfolio is unprofitable — the
owner's priority order applied to geography.
