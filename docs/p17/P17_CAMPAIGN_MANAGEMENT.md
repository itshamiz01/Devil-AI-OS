# P-17 — Campaign Management (§7)

**Surface:** `/api/v1/growth/businesses/{id}/campaigns`,
`/api/v1/growth/campaigns/{id}` (+ `/metrics`, `/transition`,
`/approve`, `/spend-requests`), `/api/v1/growth/campaigns/evaluate-auto-pause`.

## Lifecycle

Twelve states with an explicit transition map (`idea → research →
strategy → draft → approval_pending → approved → scheduled →
active → paused → completed → analyzed → archived`). Approval is
not a transition: it is a governed owner decision bound to a P-01
approval. **Expansion-purpose campaigns are gated at approval by
the live P-16 profitability gate**, with the same per-item,
reason-recorded owner override as strategies — and no other
bypass.

## Money discipline

`budget_ceiling_minor` is an approved ceiling (proposal data,
labelled as such in every response) — never spend. The only spend
path prepares a **P-07 spending request** carrying the campaign's
`project_ref = "p17-campaign:<id>"`; the request then lives
entirely inside P-07's approval workflow and P-17 stores only its
id. A request that would push recorded spend + amount past the
approved ceiling is refused (budgets are never increased beyond
approved limits). While the owner's `marketing_spend_frozen` flag
is set, preparation is refused; while `all_campaigns_paused` is
set, activation is refused.

## Metrics and alerts

Campaign metrics read P-07 live: actual spend (paid P&L expenses
with the campaign project_ref), attributed revenue (verified
collected revenue under the campaign's `p17-<code>` channel tag,
labelled ATTRIBUTED), contribution, lead/qualified/converted
counts, lead conversion rate and CAC. Alerts fire on spending
without conversions, budget exhaustion, CAC above the campaign's
declared maximum, and lead volume without conversion.

## Auto-pause

Auto-pause exists only inside explicitly approved per-campaign
rules (`auto_pause_rules: {enabled, max_spend_minor, max_cac_minor,
min_conversions}`) at **autonomy level 4**. Below level 4 the
evaluation endpoint returns `not_applied` with the reason and
changes nothing.
