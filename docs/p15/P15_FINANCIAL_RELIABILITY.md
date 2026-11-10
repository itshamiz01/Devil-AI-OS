# P-15 FINANCIAL RELIABILITY (§9)

## Scope honesty

The platform has **no trading integration**: no broker, no order
path, no positions. §9.2's trading items (order acknowledgment,
position reconciliation, stale price feeds) are therefore **NOT
APPLICABLE** — the P-15 financial read-model says so verbatim in
its output (`trading: NOT APPLICABLE — …`) rather than inventing
telemetry. If a trading experiment is ever approved separately
(Constitution: owner approval per experiment), its reliability
surface must be built with that integration, against its real
acknowledgment/reconciliation semantics.

## What exists and is monitored

| §9 item | Mechanism | P-15 surface |
|---|---|---|
| Unique transaction ID / status / audit | P-07 journal entries + P-01 approvals/audit | consumed via integrity verification |
| Ledger consistency | P-07 double-entry, integer minor units | `verify_integrity` per business in the read-model + readiness evidence |
| Reconciliation | P-07 reconciliation report (existing endpoint) | unchanged; integrity result summarised in panel I |
| Duplicate execution prevention | P-07 idempotency + single-use approval consumption (P-10/P-14 verified) | asserted unchanged; P-15 writes nothing to P-07 (proven by test: journal count identical before/after evidence collection) |
| Emergency suspension | P-10 EmergencyService financial suspension | state shown in panels H/I; the suspend/resume controls in panel I call the P-10 endpoint directly with confirmation |
| Risk limits | P-07/P-08/P-10 limits | consumed, never invented or altered (§9.3 rule) |

## Failure semantics preserved

- An API timeout is never treated as proof of failure by P-15 —
  P-15 performs no financial operations at all, so it cannot
  create the duplicate-on-retry failure mode §9.1 warns about.
- If ledger integrity verification fails for any business, the
  read-model reports `integrity_ok: false` per business with the
  P-07 detail attached; the owner acts through P-07/P-10 paths.
- Financial incidents raised by P-10's own monitoring remain
  P-10 records; P-15's register covers reliability scope and does
  not fork the financial incident trail.

## Evidence

- Integration test: a governed fixture business (P-06/P-07 paths)
  verifies `integrity_ok: true` through the read-model.
- Security test: evidence collection leaves the P-07 journal
  byte-count identical (observation never mutates).
- Live smoke: the seeded business (₹10,000 verified revenue)
  verifies over HTTP; suspension controls return P-10's confirmed
  state.
