# P-17 — Partnership Growth (§18)

**Surface:** `/api/v1/growth/businesses/{id}/partnerships`,
`/api/v1/growth/partnerships/{id}/transition`.

## Pipeline

Eight kinds (strategic, referral, affiliate, reseller,
distribution, integration, co-marketing, industry collaboration)
move through ten stages (discovered → researched → qualified →
proposal_drafted → approval_pending → negotiation →
agreement_approved → active → performance_review → closed).
Evaluation is a declared dict (strategic fit, audience
compatibility, commercial value, reputation, legal requirements,
revenue-share structure, operational dependencies, brand risks);
declared terms, if any, are stored inside the evaluation as text.

## Governance and honesty

- Moving to `agreement_approved` or `active` requires a hash-bound
  owner approval (P-01 pattern).
- The record is **internal only**: every response carries
  "the system never enters a binding agreement". Nothing is
  signed, sent or committed by the engine.
- Referral attribution joins P-07 revenue by the channel tag
  `partner-<referral_code>` and is labelled ATTRIBUTED verified
  collected revenue — explicitly *not guaranteed partner
  earnings*.
