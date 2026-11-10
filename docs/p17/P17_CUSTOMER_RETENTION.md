# P-17 — Customer Retention (§17)

**Surface:** `GET /api/v1/growth/businesses/{id}/retention`,
`POST /api/v1/growth/customers/{id}/health`.

## Retention mathematics (§27 definitions)

Computed over the recorded CRM base on a 90-day window:

- **Retention** = (customers at end − new in window) / customers
  at start × 100 (`scoring.retention_rate`), where start = recorded
  before the window, end = not recorded churned.
- **Churn** = start-cohort customers whose lifecycle is `churned`
  / start (`scoring.churn_rate`).
- Both return `INSUFFICIENT_DATA` — never a flattering zero — when
  the start cohort is empty.
- **Repeat purchase rate** from P-07 purchase counts per customer
  ref; **average actual LTV** is the mean of actual collected per
  customer (a fact). Projected LTV appears only in the per-customer
  view and only with stated contribution-margin and period
  assumptions (`scoring.ltv`); otherwise the projection is
  `INSUFFICIENT_DATA` with the reason.

## Customer health

`scoring.customer_health` is deterministic and fully explained:
deductions for interaction recency (none recorded −25; >90d −30;
>30d −15; >14d −5), purchase recency from P-07 (none −20; >180d
−25; >90d −12), open support issues (−7 each, capped −20) and
lifecycle (at_risk/dormant −15; churned −60). The factor list is
stored on the customer row (`health_factors`) with the computation
timestamp. It is an estimate from recorded signals — never a
satisfaction measurement; support/service *delivery* itself is
P-18's domain.
