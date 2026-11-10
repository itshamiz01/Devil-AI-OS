# P-16 — Capital Allocation (§9)

**Module:** `app/economy/capital.py` · **Table:** `allocation_recommendations`

## What an allocation is — and is not

An allocation recommendation is a **labelled proposal** (amount,
purpose, target) recorded against a business. Approving one moves
**no money**: there is no transfer, spend or payment method
anywhere on `EconomyService` (a security test asserts the absence
of the whole surface). Execution, if the owner wants it, happens
through P-07's governed flows, outside P-16.

## Scenarios (§9)

`conservative`, `balanced`, `growth`, `opportunistic` and
`custom` framings, each producing the same proposal shape with the
scenario's rationale template. Scenario generation only proposes
amounts within the business's P-07 available capital.

## The double-commitment guard

A proposal is refused when `proposed + open commitments` (other
P-16 proposals in `proposed`/`approved` state for the same
business) would exceed the business's P-07 **available capital**.
Two approved proposals can therefore never silently promise the
same money twice. Amounts are P-16 proposal data, following the
P-13 `INTERNAL_ALLOCATION` precedent — P-07 remains the only
ledger.

## Gates on approval

- **Growth scenario** creation is refused while the owner's
  profitability gate is closed.
- **Any** allocation approval is refused while
  `capital_commitments_frozen` is set (rejection stays available —
  stopping is always safe).
- Approval runs through the hash-bound P-01 pattern
  (`economy.allocation`): a supplied approval id must be
  owner-decided and binding-verified against the exact parameters;
  a mismatched approval is refused (security-tested).

## Invariant, proven

A backend test and the live smoke both assert P-07's revenue
metrics, expense totals and business summary are **byte-equal**
before and after a batch of P-16 writes including an approved
allocation and an approved reinvestment plan.
