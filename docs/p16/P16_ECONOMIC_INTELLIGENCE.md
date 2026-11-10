# P-16 — Economic Intelligence (§3)

**Module:** `app/economy/` (`service.py` core) · **Routes:** `/api/v1/economy/*`

## Principle

P-16 makes no economic claim of its own. Every figure it presents
is read live from P-07 (`FinancialService.p08_indicators` and
`business_summary`); every lifecycle fact comes from P-06/P-13;
the only stored state is owner-declared analysis, classifications,
proposals and recorded decisions. Projected revenue is never
blended with collected revenue anywhere in the module.

## The global economic overview (§3)

`GET /economy/overview` returns, per business and in total:

- verified collected revenue (net, P-07) and projected revenue as
  **separate fields, never blended**;
- actual expenses (P-07 P&L paid) and verified net profit — `None`,
  never zero, when no business has a financial profile;
- recurring revenue (MRR/ARR from P-07) and the recurring share of
  collected revenue;
- revenue concentration: HHI over per-business collected shares,
  top share, and the overconcentration flag against the owner's
  threshold.

`combined_available_cash` is structurally `null` with the standing
note: cash balances of separate businesses are never summed
(P-13 §11 rule). Available capital is always per business.

## §21 KPIs

`overview.kpis` reports total realised (verified collected)
revenue, net operating profit, recurring revenue ARR and its
share of collected revenue, the revenue-concentration block, and
business survival counts (operating vs total) — with the standing
note that counts of businesses or opportunities are inventory,
never success metrics. KPIs that would require data no engine
records (e.g. customer counts — P-17's territory) are absent
rather than estimated.

## Honesty rules enforced in code

- No profile → profitability `None`, gate CLOSED with the reason
  stated; never a zero presented as a measurement.
- Fixture businesses carry `is_fixture: true` from P-06 through
  every P-16 view.
- Every aggregate is owner/system-only (§19); agents and external
  principals are refused at the service layer and audited.
