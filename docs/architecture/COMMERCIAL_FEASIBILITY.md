# P-03 — Commercial Feasibility Engine (§13)

Implemented in `app/opportunities/commercial.py` — pure deterministic arithmetic; every figure traceable to a stated input. Persisted in `commercial_analyses`.

## Inputs and cost classification (§13.8)

Caller-supplied inputs: startup cost, monthly recurring cost, variable cost per sale, product price, price basis (verified/quoted/historical/**estimate**), platform fee %, payment fee %, expected sales per month (conservative/base/optimistic), owner hours (implementation/weekly). Cost classification is mandatory: costs are `verified | quoted | historical | estimate | unknown`. **An unknown cost is never treated as a verified zero**: when the minimum-viable-cost composition is wholly unknown the analysis says "cannot be established"; unknown components are flagged in the stored JSON rather than silently dropped.

## Computations (per scenario)

- effective price = price × (1 − platform fee% − payment fee%)
- unit contribution = effective price − variable cost
- **break-even sales/month = ceil(monthly recurring ÷ unit contribution)** (and break-even revenue)
- monthly profit at scenario volume; contribution margin %
- first-year profit = 12 × monthly − startup
- **negative-unit-economics detection**: unit contribution ≤ 0 marks the scenario loss-making and feeds the §16.10 hard rejection ("negative unit economics across all scenarios")
- startup within budget / recurring within 10%-of-budget monthly guard — **budget compatibility is checked against the owner's stated budget; the system never silently raises it** (§13.9). An incompatible result is data for the INCOMPATIBLE decision, computed at screening from the candidate startup class and re-checkable from the full analysis.

## Worked staging examples (smoke, 9 Nov 2026)

All prices below are **labelled estimates supplied as stated assumptions** — no live price for these products was verified (see P03_RESEARCH_QUALITY_REPORT).

| | E-book (KDP) | Planner templates | GST invoice tool (India) |
|---|---|---|---|
| Price (estimate) | $4.99 | $12.00 | $2.00/month |
| Fees | 30% platform | 6.5% + 3% | 2% payment |
| Variable cost | $0.30 | $0.45 | $0.06 |
| Contribution margin | 63.99% | 86.75% | (high; SaaS) |
| Recurring | $5/mo | $2/mo | $6/mo |
| Break-even | 2 sales/mo ($9.98) | 1 sale/mo | small |
| Startup (estimate class) | $20 | $15 | $20 |
| Within $50 budget | yes | yes | yes |

Note: contribution margin % is volume-independent in this linear model, so it is identical across the three scenarios of one analysis; volumes and profits differ. A negative-margin or over-budget case is exercised in tests (print-on-demand store $120 class and inventory e-commerce $2,000 class → INCOMPATIBLE at screening).

## What the engine refuses to do

Invent a price, a fee, a sales volume or a cost (§32); treat attention as sales; present an estimate as verified; or raise the budget to make a model fit. Missing inputs produce "cannot be established", not a guess.
