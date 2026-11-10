# Business Model Framework (P-06 §9 context)

P-06 is compatible with every §9 model (digital products, services,
content, commerce, software…) because a business model enters the
engine as **template data + opportunity data**, not as code. The seed
registry ships four templates; their honest support levels are:

| Template | Category | Support |
|---|---|---|
| `ebook_digital_product` | digital_products | **Operational** — exercised end-to-end (Scenario A) |
| `saas_micro_tool` | software | **Operational** — exercised (Scenario B, incl. a verified prototype execution step) |
| `content_publication` | content | **Operational** — exercised (Scenario C) |
| `productized_service` | services | **Prepared-only** — registered and validated, not exercised end-to-end |

"Operational" means: the template's workflow executes through P-05 and
produces a verified local package in staging. It does not mean a live
business exists.

## Money rules (§9/§27) — the framework's hard edge

- Pricing is **data**: a financial value {amount|range, currency,
  source, classification, confidence, date, assumptions}.
- Classifications are `estimate` or `verified`; `verified` is permitted
  only for cost-side facts the owner/source actually verified.
- **Collected revenue and profit cannot be recorded at all** — no
  schema field exists, the financial builder rejects those keys, and
  security tests 10–11 prove both layers.
- Subscriptions, pricing experiments and revenue *tracking* belong to
  P-07/P-08. P-06 emits the validated P-07 input payload
  (`financial_inputs`) and nothing else financial.

## What a model must supply

Required information per template (target customer, problem, solution,
price estimate), a distribution approach recorded in the P-03
commercial analysis, and channels whose platform gates are known —
unknown platforms fail their gate closed (`BLOCKED`).
