# P-16 — Opportunity Discovery (§4.2)

**Module:** `app/economy/opportunities.py` · **Table:** `economic_opportunities`

## Sources of opportunities

1. **Owner-recorded** opportunities (manual entry, any §4.1 kind).
2. **Governed evaluation of P-03 opportunities** — an existing P-03
   opportunity can be referenced (`p03_opportunity_id`); P-16 adds
   economic scoring and the pipeline, it does not fork P-03's data.
3. **Internal detectors** (`POST /economy/discovery/run`), each
   grounded in recorded evidence, deduplicated on a stable
   `market_tag`:
   - `loss_making` — a profiled business with negative verified
     net profit → an `existing_business_expansion` improvement
     opportunity (the owner's priority, mechanised);
   - `no_recurring` — a business with verified collections but
     zero recurring revenue → a `new_revenue_stream` opportunity
     (§6 diversification warning, mechanised);
   - `concentration` — one business above the owner's share of
     portfolio collected revenue → a `new_revenue_stream`
     opportunity to reduce single-business concentration;
   - `asset` — a registered commercial asset with no
     commercialization proposal yet → an
     `asset_commercialization` opportunity (§7).
4. **Approved commercialization handoffs** (§7) enter as P-03
   opportunities, not P-16 rows.

Detectors never invent market demand: there is no external data
feed in staging, so no detector claims one. Market-level discovery
begins from owner-recorded market reports with mandatory evidence
sources (§4 preamble: no claim without a source).

## The pipeline (§4.2)

`discovered → under_research → market_validation →
financial_evaluation → risk_assessment → approval_pending →
approved | rejected | archived | merged` — forward-only, one step
at a time; exits (`rejected`, `archived`, `merged`) are always
available, including while expansion is paused.

Two gates guard the road to `approval_pending`:

- the **evidence gate** (§4.3): confidence — computed only from
  attached evidence — must meet the owner's minimum (default 50)
  with at least the owner's minimum evidence items (default 2);
- the **owner's profitability gate**: `new_business` and
  `market_entry` opportunities cannot advance past
  `financial_evaluation` while the portfolio is not verifiably
  profitable. The owner may override per item, with a mandatory
  recorded reason.
