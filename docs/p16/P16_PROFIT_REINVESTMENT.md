# P-16 — Profit Reinvestment (§10)

**Module:** `app/economy/capital.py` · **Table:** `reinvestment_plans`

## Profit is not cash

The prompt's central §10 rule is implemented literally:

```
distributable = max( min(accounting net profit, available cash)
                     − owner-declared adjustments, 0 )
```

- *Accounting net profit* and *available cash* both come from
  P-07's `business_summary` at plan creation and are frozen into
  the plan's `figures_snapshot`, so a plan can always be audited
  against the figures it was made from.
- *Owner-declared adjustments* stand for taxes payable,
  liabilities and contractual restrictions; the snapshot's note
  says plainly that P-07's tax records remain the authoritative
  detail. P-16 does not compute tax.

A profitable business with thin cash cannot distribute its paper
profit; a cash-rich business with no profit distributes nothing.
A scenario test pins both directions of the `min()`.

## Distribution (§10 example shares)

Default shares are the prompt's worked example — growth 40%,
resilience/reserve 25%, product improvement 15%, marketing 10%,
owner reserve 10% — recorded in settings as **illustrative
defaults the owner may change**, never as advice. Integer minor
units: per-category amounts are floored, so the plan total never
exceeds the distributable amount (asserted in tests).

## Approval

Plans are decided under the same hash-bound P-01 pattern
(`economy.reinvestment`) and the same freeze rule as allocations.
Approval records the decision; it executes nothing.
