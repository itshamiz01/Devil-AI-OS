# P-17 — CRM Integration (§11)

**Position:** AUTONOMUS had no CRM before P-17 (P-06's
`BusinessCampaign` is a draft-only creation-time stub with no send
path — a different object, not a duplicate). P-17 builds the CRM
layer as growth-owned state; it integrates *with* P-07 rather
than duplicating it.

**Surface:** `/api/v1/growth/businesses/{id}/customers`,
`/api/v1/growth/customers/{id}` (+ `/interactions`, `/health`),
`POST /api/v1/growth/leads/{id}/convert`.

## What the CRM row holds — and what it never holds

A customer row holds relationship state only: display name,
contact, per-business dedupe key, segment, lifecycle stage
(onboarding/active/engaged/at_risk/dormant/churned/renewed),
consent status, preferences, acquisition campaign/channel, source
lead, and computed health (score + factor breakdown + timestamp).
**Purchase facts are never copied**: payment history is a live
read of P-07 revenue records filtered by `p07_customer_ref`,
verified and collected/recognised only.

## Conversion

Only a lead in the `converted` stage converts; withdrawn contacts
are refused. Conversion records `source_lead_id`, sets the lead's
`converted_customer_id`, assigns the deterministic P-07 ref
`p17-cust-<email-or-key>`, and starts the lifecycle at
`onboarding`. Converting twice returns the existing customer.

## Isolation

Customers belong to exactly one business. There is no copy,
merge or cross-reference function; the list endpoint states the
isolation rule in its response. (Tested: the same contact in two
businesses yields two independent rows; suppression in one does
not leak into the other.)
