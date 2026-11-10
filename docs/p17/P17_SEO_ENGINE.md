# P-17 — SEO Engine (§15)

**Surface:** `POST /api/v1/growth/businesses/{id}/seo-records`,
`GET …/seo`.

## Records, not a crawler

Four record kinds — `keyword_set`, `technical_audit`,
`content_plan`, `performance_snapshot` — each with a mandatory
source label: `declared | imported | owner_attested`. Any other
source claim (e.g. "live_search_console") is refused: AUTONOMUS
has no crawler, no search feed and no search-console connection,
and the summary response repeats that label.

Keyword sets must declare their keywords, search intent and
competition level. Technical audits can carry an `issue_count`;
the summary computes the delta between the two most recent audits
so improvement is shown from records, not asserted.

## Guardrails

No black-hat or manipulative tactic exists anywhere in the
engine: there is no link scheme, cloaking, keyword-stuffing or
scraping function to call. SEO work product is research records
and content plans that flow into the §6 content workflow with its
fact/brand/copyright/quality reviews.
