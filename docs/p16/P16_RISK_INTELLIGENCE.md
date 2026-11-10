# P-16 — Risk Intelligence (§12)

**Module:** `app/economy/risk.py` · **Table:** `risk_assessments`

## Detectors

Computed from P-07/P-13 reads at assessment time; each finding
names the business and the figure behind it:

- `loss_making_business` — verified net profit < 0;
- `revenue_concentration` — one business above the owner's share
  threshold of portfolio collected revenue;
- `platform_dependency` — one channel above the threshold of a
  business's collected revenue;
- `no_recurring_revenue` — positive collections, zero MRR;
- `unmeasurable_business` — a business whose P-07 summary cannot
  be produced (named, never silently skipped).

Not implemented: a *declining* profitability trend detector.
A decline is a statement about two periods; P-16 does not yet
compute period-over-period profit movement, so it reports the
level (loss-making) and leaves trend claims unmade.

Earlier drafts named the loss-maker finding
`declining_profitability`; the live smoke caught the mismatch with
§12's vocabulary and the detector was renamed to what it actually
detects.

## Stress scenarios — SIMULATION, always labelled

Ten scenarios computed arithmetically from current P-07 figures:
revenue −10% / −25% / −50%; removal of the largest channel
(labelled in the output as the mechanical proxy for losing a major
customer); removal of advertising channels; cloud-provider
unavailability (non-quantifiable from ledger data — reported as a
note, never assigned invented numbers); costs +20%; the largest
business turning unprofitable (modelled as its profit removed);
international entry failure (exposure = the recorded estimates of
open market-entry pipeline items, labelled PROPOSED); and the
combined −25% revenue / +20% cost case.

Every scenario block carries
`scenarios_label: "SIMULATION — arithmetic on current P-07
figures, not a forecast"`. Scenario outputs show the portfolio
net profit after the shock and the count of businesses
loss-making after it. They inform decisions; they are never
presented as predictions (§19).

## Persistence

Assessments are stored (`risk_assessments`) with their inputs
snapshot; `GET /economy/risk/latest` returns the newest, or an
honest `none_computed` state — the Command Center renders exactly
that.
