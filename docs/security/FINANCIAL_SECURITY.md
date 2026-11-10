# Financial Security (P-10)

P-07 remains the only financial authority. P-10 adds a guard in
front of it; it keeps no ledger, stores no amounts of its own in
any P-10 table, and never executes a transaction.

## View / approve / execute separation (§16.2)

| Action | Permission | Approval needed |
|--------|-----------|-----------------|
| view | `read_business_data` | no |
| approve (record a decision) | `request_financial_operations` | no |
| execute_transfer | `request_financial_operations` | owner-decided, hash-bound, single-use |

An *approve-shaped* authorization never substitutes for an
*execute* one: the guard classifies the action first, and
execution always requires the approval path.

## Execution authorization, step by step

1. Mode gate and financial-suspension gate (suspension blocks
   everything except `view`).
2. The P-01 permission engine must grant the mapped permission.
3. The approval must exist, be `approved`, be **decided by the
   owner**, and `verify_binding` must match the canonical
   parameters `{business_id, amount_minor, currency, recipient}`
   under action `financial.transfer`.
4. The amount must be within P-07's configured
   `spending_limits[currency].max_single_transaction`; an
   unconfigured currency denies (fail closed).
5. On success the guard records the consumption in
   `security_broker_decisions`; a second execute with the same
   approval is refused — approvals are single-use for execution.

Only then may the caller proceed to P-07's own API, which
re-applies its own governance (attestation, evidence, journal
rules). P-10's ALLOW is an authorization, never a transfer.

## Webhooks and providers

Unchanged from P-07: signed webhooks, idempotency, forged
signatures rejected (Scenario 10 re-verifies end-to-end). Stripe
remains REQUIRES OWNER CONFIGURATION.
