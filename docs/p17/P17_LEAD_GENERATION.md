# P-17 — Lead Generation (§8)

**Surface:** `/api/v1/growth/businesses/{id}/leads` (+ `/import`),
`/api/v1/growth/leads/{id}/…`, suppressions list.

## Authorised sources only

`source_kind` is validated against a closed authorised set
(website form, product registration, free trial, inbound inquiry,
newsletter, referral, authorised B2B prospecting, public business
contact, approved integration, manual entry). Purchased lists,
purchased databases, scraped contacts, third-party databases,
leaked data and unknown bulk sources are **refused outright and
audited** — the system never buys, scrapes or brokers contact
data.

## Consent and suppression

`consent_status ∈ {granted, withdrawn, unknown, not_required}` plus
a `lawful_basis` note are recorded at creation, before any
communication may be queued. Deduplication is by a normalised
`dedupe_key` (email → phone digits → name+company slug), unique per
business: re-importing the same contact returns the existing lead
flagged `deduplicated`, never a second row.

Suppression writes a per-business suppression record
(`opt_out | unsubscribed | do_not_contact | hard_bounce |
complaint`), sets the lead's consent to withdrawn, and hard-blocks
both re-creation of the contact and any future queueing — *never
contacted again* is enforced, not advisory.

## Import

Batch import reports per-row outcomes: created, deduplicated and
refused (with reasons) — refused rows are never silently dropped.
