# P-03 Commercial Validation Report (§13, §31)

**Date:** 9 November 2026 · All figures below are computed by `app/opportunities/commercial.py` from **stated-assumption inputs** (labelled estimates) during the staging smoke run. They validate the *calculation engine*, not any real business.

## Worked examples (smoke)

### 1. Beginner fitness e-book series (KDP)
Inputs: price $4.99 (estimate), platform fee 30%, variable $0.30, recurring $5/mo, startup $20 (estimate class), volumes 3/10/30.
→ Effective price $3.493 · unit contribution $3.193 · margin **63.99%** · **break-even 2 sales/month ($9.98 revenue)** · base monthly profit $26.93 · first-year (base) $303.16 · **within $50 budget: yes**.

### 2. Printable Weekly Planner Templates
Inputs: price $12 (estimate), fees 6.5% + 3%, variable $0.45, recurring $2/mo, startup $15 (estimate), volumes 4/12/40.
→ Effective price $10.86 · margin **86.75%** · **break-even 1 sale/month** · **within budget: yes**.

### 3. GST Invoice Generator for Indian Freelancers
Inputs: price $2/month (estimate), payment fee 2%, variable $0.06, recurring $6/mo, startup $20 (estimate), volumes 5/20/60.
→ Positive unit economics; **within budget: yes**; demand unproven (validation Level 1) — commercial plausibility is not demand validation, and the reports keep the two separate.

## Negative cases (engine refusals, all test/smoke-verified)

| Case | Engine behaviour |
|---|---|
| Print-on-demand store, $120 startup class vs $50 budget | Screening → **INCOMPATIBLE**; budget never raised |
| Inventory e-commerce, $2,000 class | **INCOMPATIBLE** |
| Negative unit economics (price < fees + variable) | Scenario flagged loss-making; scoring hard rule fires when negative in all scenarios |
| Unknown costs | Minimum viable cost reported as "cannot be established" where composition is unknown; unknown components flagged, never treated as verified zero |
| Price basis | Stored per analysis (`estimate` in all smoke cases); an estimate is never presented as verified |

## Method notes

- Margin % is volume-independent in this linear model (identical across conservative/base/optimistic); volumes change profit, not margin. Recorded here so nobody misreads the three identical percentages as a copy error.
- Break-even uses ceiling division on monthly recurring ÷ unit contribution; when contribution ≤ 0 the result is explicitly "cannot break even at any volume" rather than a number.
- Budget compatibility compares against the **owner's stated budget from the brief** — there is no code path that adjusts the budget to fit a model (§13.9).
