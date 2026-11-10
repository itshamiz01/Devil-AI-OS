# P-16 — Revenue Diversification (§6)

**Module:** `app/economy/risk.py` (diversification reads) ·
**Routes:** `/economy/diversification`, `/economy/diversification/{business_id}`

## The index

Per business, diversification is scored 0–100 from P-07's real
breakdowns:

```
score = 100 × ( 0.4 × (1 − HHI(channels))
              + 0.3 × (1 − HHI(products))
              + 0.3 × ARR / (ARR + net collected) )
```

HHI is the Herfindahl concentration over the recorded channel and
product shares. When net collected revenue is ≤ 0 the index is
`INSUFFICIENT_DATA` — a number would be fiction.

## Warnings (§6)

Computed per business from the same figures:

- `single_channel_dependency` — the top channel's share of
  collected revenue exceeds the owner's concentration threshold;
- `single_product_dependency` — the same test on the top product;
- `no_recurring_revenue` — positive collected revenue with zero
  MRR (revenue is entirely one-time; fragile quality);
- `revenue_without_profit` — the business collects revenue but is
  loss-making ("revenue is not profitability", §3 principle 8).

Not implemented: a single-geography warning — P-16 records segment
geography but does not yet join it to revenue, and no warning is
claimed without that join.

## Portfolio level

The portfolio view aggregates the per-business indices, the
channel/product totals, and the concentration block (HHI, top
share, threshold flag). Projected revenue is shown beside
collected revenue, in its own field, never blended.

Diversification is the owner's **second** priority: warnings are
surfaced in recommendations only after profitability findings.
