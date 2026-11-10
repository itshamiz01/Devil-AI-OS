# P-13 Shared Services (§9)

Shared services are the portfolio's answer to duplicated
infrastructure: one registered service, many businesses using it —
each under its own governed, revocable access.

## Registry

`shared_services` rows carry: name, kind (ai_model_infrastructure,
research_infrastructure, content_production,
development_environment, analytics, monitoring, backup,
notifications, document_processing, automation_adapter,
internal_service), provider, supported categories, capacity
units, cost model, security classification, access policy, SLA
and status (AVAILABLE / DEGRADED / UNAVAILABLE). Registration is
owner-only. A service's status feeds portfolio risk: a
non-AVAILABLE service used by two or more businesses is a
single-point-of-failure finding.

## Access lifecycle

Per (service, business) — unique by constraint:

```
REQUESTED ──owner decide──▶ APPROVED ──activate──▶ ACTIVE
    │                          │                     │
    └──owner decide──▶ DENIED  └──revoke──▶ REVOKED ◀┘
```

Re-request after DENIED/REVOKED reopens the same row as REQUESTED.
Only ACTIVE access permits usage. Agents reach a service only
through their home business's ACTIVE access
(`check_service_access`).

## Usage

`shared_service_usage` rows (access id, service, business, units,
note, recorder) are append-only records of authorized use.
Recording usage without ACTIVE access is refused and audited as
an isolation violation. Usage totals per business feed the
`usage_based` cost allocation.

## Cost allocation

See `P13_PORTFOLIO_FINANCE.md`: four split methods, one row per
charged business, batch-decided, permanently labelled
INTERNAL_ALLOCATION, invisible to P-07.

## Failure behaviour

If a service becomes UNAVAILABLE, existing access rows are not
silently changed — the risk engine flags the SPOF and the owner
decides. Revoking access is immediate for usage and agent checks;
historical usage records remain (they document authorized use at
the time).
