# P-17 — Growth Analytics (§19/§20/§21/§23)

**Surface:** `/api/v1/growth/overview`, `/growth/businesses/{id}`,
`/growth/businesses/{id}/budget`, `/growth/portfolio`,
`/growth/recommendations`, and the Command Center's Acquisition &
Growth view (`frontend/src/views/Growth.tsx`, tabs matching the
§23 panels).

## Overview (§23A)

Portfolio totals (active campaigns, leads, customers, P-07 spend,
attributed revenue) plus a per-business table with leads, customers,
spend, attributed revenue and CAC — every money figure read live
from P-07 at request time. The gate panel (P-16, consumed live) is
rendered first, with the owner's emergency flags (campaigns paused,
communications stopped, outreach suspended, spend frozen) and the
standing execution-capability statement: *none — research,
preparation, governed approvals and measurement only*.

## Budget view (§21)

Per campaign: approved ceiling (proposal), actual spend (P-07),
committed spend, remaining, converted customers, CAC, and the P-07
spending-request ids prepared from the campaign. Portfolio actual
spend is the eligible-spend total (paid P&L expenses in the
configured marketing categories). The rules are printed on the
view: budgets are never increased beyond approved limits; new
expenditure goes through P-07's approval workflow.

## Recommendations (§19)

Mechanically ordered **improve → diversify → capital_efficiency →
expansion** (rank stored on every item): fix-conversion findings
from P-07 profit + spend/conversion evidence, thin-margin
capital-efficiency findings from P-07 margin over verified
collected revenue, owner-approved strategies awaiting execution,
and — while the gate is closed — an explicit "expansion held"
entry with `gate_blocked: true` and the gate's reason.

## Portfolio growth (§20)

Businesses ranked by attributed contribution (attributed revenue −
spend). Shared assets are stated precisely: methods and scores are
the shared playbook; **audiences, brand assets and customer data
are never shared across businesses**. Cross-promotion is
owner-governed only, as an approved partnership or campaign per
business. Portfolio profitability itself is judged in P-16/P-07,
never here.
