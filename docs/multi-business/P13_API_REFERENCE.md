# P-13 API Reference — /api/v1/portfolio

All endpoints use the standard envelope (`{success, data, error,
correlation_id, meta}`) and house permission mapping: reads require
`read_business_data`, writes `modify_business_data`, decisions and
governance `approve_actions`. Service-layer rules are stricter
than route permissions (owner-only decisions; agent aggregate
blindness; §20 isolation) and are the real boundary. Errors:
house `AutonomusError` mapping (ValidationError 422, NotFound 404,
PermissionDenied 403, InvalidStateTransition 409).

## Engine & settings

| Method | Path | Notes |
|---|---|---|
| GET | `/portfolio/status` | engine status + authority map |
| GET | `/portfolio/settings` | concentration threshold, share cap, capacities |
| PATCH | `/portfolio/settings` | owner-governed; thresholds/capacities only |

## Portfolios & membership

| Method | Path | Notes |
|---|---|---|
| POST | `/portfolio/portfolios` | create (owner) |
| GET | `/portfolio/portfolios` | list (owner/system) |
| GET | `/portfolio/portfolios/{id}` | one portfolio |
| POST | `/portfolio/portfolios/{id}/archive` | archive |
| POST | `/portfolio/portfolios/{id}/survival-mode` | `{enabled}` — advisory §12 mode |
| GET | `/portfolio/portfolios/{id}/overview` | counts, stage counts, members with live P-06/P-08 summaries |
| GET | `/portfolio/portfolios/{id}/members` | memberships + business summaries |
| POST | `/portfolio/portfolios/{id}/members` | register a P-06 business (no duplication) |
| PATCH | `/portfolio/portfolios/{id}/members/{business_id}` | priority, group labels, notes |
| POST | `/portfolio/portfolios/{id}/members/{business_id}/status` | ACTIVE / PAUSED / REMOVED |
| GET | `/portfolio/portfolios/{id}/objectives` | list objectives |
| POST | `/portfolio/portfolios/{id}/objectives` | create objective (horizon enum) |

## Businesses

| Method | Path | Notes |
|---|---|---|
| GET | `/portfolio/businesses/{id}/profile` | P-06 identity + lifecycle + derived stage; per-business access rule |
| GET | `/portfolio/businesses/{id}/finance` | live P-07 summary, or an honest no-profile response |
| GET | `/portfolio/compare?ids=a,b&currency=INR` | 2–6 businesses, own figures side by side |

## Relationships

| Method | Path | Notes |
|---|---|---|
| POST | `/portfolio/relationships` | propose (grants nothing) |
| GET | `/portfolio/relationships?portfolio_id=&business_id=&status=` | list/filter |
| POST | `/portfolio/relationships/{id}/transition` | governed state machine |

## Intelligence

| Method | Path | Notes |
|---|---|---|
| POST | `/portfolio/portfolios/{id}/analyze` | deterministic detectors; idempotent |
| GET | `/portfolio/portfolios/{id}/opportunities` | list (status filter) |
| POST | `/portfolio/portfolios/{id}/opportunities` | submit through the evidence gate |
| POST | `/portfolio/opportunities/{id}/decision` | VALIDATED/ACCEPTED/REJECTED/DISMISSED; speculative cannot be accepted |
| GET | `/portfolio/portfolios/{id}/recommendations` | list |
| POST | `/portfolio/recommendations/{id}/decision` | ACCEPTED/REJECTED/DISMISSED |
| GET | `/portfolio/portfolios/{id}/concentration` | verified-collected shares vs threshold |
| POST | `/portfolio/portfolios/{id}/risk/assess` | compute + persist assessment |
| GET | `/portfolio/portfolios/{id}/risk` | latest assessment |

## Shared services & allocations

| Method | Path | Notes |
|---|---|---|
| POST | `/portfolio/services` | register service |
| GET | `/portfolio/services` | list |
| POST | `/portfolio/services/{id}/status` | AVAILABLE/DEGRADED/UNAVAILABLE |
| GET | `/portfolio/services/{id}/access` | access rows |
| POST | `/portfolio/services/{id}/access` | request access for a business |
| POST | `/portfolio/services/access/{id}/decision` | approve/deny |
| POST | `/portfolio/services/access/{id}/activate` | APPROVED → ACTIVE |
| POST | `/portfolio/services/access/{id}/revoke` | immediate effect |
| POST | `/portfolio/services/{id}/usage` | record usage (ACTIVE access only) |
| GET | `/portfolio/services/{id}/usage` | per-business usage totals |
| POST | `/portfolio/allocations` | compute internal allocation (batch) |
| GET | `/portfolio/allocations?service_id=&portfolio_id=` | allocation rows (labelled) |
| POST | `/portfolio/allocations/{id}/decision` | decide the whole batch |

## Resources

| Method | Path | Notes |
|---|---|---|
| GET | `/portfolio/portfolios/{id}/resources` | capacities, allocated/available, quotas |
| POST | `/portfolio/portfolios/{id}/quotas` | set/upsert a business quota |
| POST | `/portfolio/portfolios/{id}/resource-allocations` | propose (quota/capacity/cap + survival-mode checks) |
| POST | `/portfolio/resource-allocations/{id}/decision` | approve/deny |
| POST | `/portfolio/resource-allocations/{id}/activate` | APPROVED → ACTIVE |
| POST | `/portfolio/resource-allocations/{id}/release` | frees capacity |
| POST | `/portfolio/portfolios/{id}/resources/reclaim` | revoke allocations of departed members |

## Cross-business access (§20)

| Method | Path | Notes |
|---|---|---|
| POST | `/portfolio/access/grants` | scoped grant; categories validated; expiry mandatory |
| GET | `/portfolio/access/grants?agent_id=&business_id=` | list |
| POST | `/portfolio/access/grants/{id}/revoke` | immediate effect |
| POST | `/portfolio/access/assignments` | BUSINESS or PORTFOLIO scope (portfolio = aggregate categories only) |
| GET | `/portfolio/access/assignments?agent_id=` | list |
| POST | `/portfolio/access/assignments/{id}/revoke` | immediate effect |
| POST | `/portfolio/access/check` | caller's own checked data access `{business_id, category}` → `{allowed, reason, via}` |
| POST | `/portfolio/access/check-service` | caller's own checked service access `{service_id}` |

## Portfolio workflows (§13)

| Method | Path | Notes |
|---|---|---|
| POST | `/portfolio/portfolios/{id}/workflows` | draft with per-business contributions (shareable categories only) |
| GET | `/portfolio/portfolios/{id}/workflows` | list with participations |
| POST | `/portfolio/workflows/{id}/authorize` | authorize one business's contribution |
| POST | `/portfolio/workflows/{id}/start` | all authorized → creates P-12 sub-workflows |
| POST | `/portfolio/workflows/{id}/refresh` | sync statuses from P-12 |

## Ventures, finance views, strategy, reports

| Method | Path | Notes |
|---|---|---|
| POST | `/portfolio/portfolios/{id}/ventures` | propose (creates no business) |
| GET | `/portfolio/portfolios/{id}/ventures` | list |
| POST | `/portfolio/ventures/{id}/decision` | approve/reject |
| POST | `/portfolio/ventures/{id}/handoff` | APPROVED → P-03 opportunity; P-06 decides creation |
| GET | `/portfolio/portfolios/{id}/finance` | analytical layer over P-07; cash never combined |
| GET | `/portfolio/portfolios/{id}/strategy` | ten §16 areas, INSUFFICIENT_DATA where evidence is missing |
| POST | `/portfolio/portfolios/{id}/reports` | generate SNAPSHOT/FINANCIAL/COMPARISON/RISK/STRATEGIC |
| GET | `/portfolio/portfolios/{id}/reports` | list |
| GET | `/portfolio/reports/{id}` | one report (stored snapshot + sources) |
| GET | `/portfolio/reports/{id}/export` | JSON export; `pdf: NOT IMPLEMENTED` |
