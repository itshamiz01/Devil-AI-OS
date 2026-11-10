# Approval Policies (P-10)

Approvals remain P-01's `approval_requests` — SHA-256 hash-bound
to their exact parameters. P-10 governs how they are *used*.

## Binding rules (all enforced and tested)

- **Parameter binding** — an approval authorizes only a request
  whose parameters hash identically (P-01 `verify_binding`).
  Changing amount, recipient, business or resource invalidates
  it (Scenario 3).
- **Expiry** — expired approvals refuse; TTLs are set at creation
  (`default_approval_ttl_minutes`, default 60).
- **Single owner decision** — an approval is decided once; a
  second decision is refused (P-01).
- **No self-approval** — since P-10, `ApprovalService.decide`
  enforces this at the **service level**: the decider must hold
  `approve_actions` through the P-01 engine, and a non-owner may
  never decide a request they created. (The owner deciding an
  owner-initiated governed step — e.g. approving their own plan
  draft — remains by design: the owner is root authority and
  every such decision is audited. All escalation-shaped cases,
  where a subordinate requests and would decide, are refused.)
- **Single use for financial execution** — the financial guard
  consumes an approval on an authorized execute: a broker-decision
  row records the consumption, and any replay is refused
  (Scenario 2; smoke §4).
- **Owner decision required at Level 3** — approvals decided by
  non-owners never authorize Level-3 actions or transfers.

## What P-10 deliberately did not change

- The hash scheme, the request schema, pending-decision lists and
  the approval API are P-01's, untouched except for the decide
  service-level checks above.
- P-08 and P-09 keep their own approver re-verification (defence
  in depth); it is now redundant with, not a substitute for, the
  service-level check.
