# P-03 — §35 Example Investigations (staging smoke, 9 Nov 2026)

**Source-access statement (read first).** These investigations were executed by the real pipeline in this sandbox (`docs/reports/P03_SMOKE_EVIDENCE.txt` is the unedited transcript; machine-readable reports in `docs/reports/investigations/`). Source access in this sandbox is **partial**, and the investigations reflect that honestly:

- **Live web**: fetched through the sandbox egress proxy. Shopify pricing was genuinely fetched (HTTP 200) and produced 8 provenance-carrying price-mention evidence records for the print-on-demand investigation. Etsy and NPCI returned **HTTP 403** (bot protection — recorded as unavailable, **not bypassed**); KDP and Gumroad **timed out** (recorded unavailable).
- **Everything else** comes from the build's **clearly labelled seed fixture documents** (owner-notes / industry-blog / community-forum fixtures). Fixture corroboration demonstrates the corroboration machinery; it is **not** real-world verification, and no investigation below claims otherwise.

**No investigation reached a candidate recommendation or a validation level above 1.** The evidence base does not justify more, and the engine refused to inflate. That refusal is itself a §35 result.

---

## Investigation 1 — Beginner fitness e-book series (KDP)

- **Brief**: $50 budget, global. Discovery method: capability-fit (owner's existing KDP/fitness context).
- **Evidence**: 5 records from 4 sources; the KDP 70%-royalty-under-conditions claim reached **CORROBORATED** (two independent fixture sources). Live KDP page: **timeout → unavailable**. One forum fixture document contained an embedded instruction injection → **quarantined**, `PromptInjectionDetected` event emitted, audit + history records written; none of its claims entered the evidence store.
- **Commercial (stated assumptions)**: price $4.99 (estimate), fees 30%, variable $0.30, recurring $5/mo, startup $20 (estimate) → margin 63.99%, **break-even 2 sales/month**, within budget.
- **Result**: score **2.42/5**, evidence quality **3.46/5**, validation **Level 1**, recommendation **REQUIRES MORE RESEARCH**. A claimed Level 4 validation was **refused (HTTP 422)** — no owner-recorded real-world evidence exists.
- **Key uncertainties**: demand stage derived as *none* (0 demand records at SUPPORTING+); KDP royalty terms unverified live; market size cannot be established.

## Investigation 2 — Printable Weekly Planner Templates

Full sample report: `P03_SAMPLE_OPPORTUNITY_REPORT.md`. Score **3.17/5**, EQ **3.33/5**, validation **Level 1**, **REQUIRES MORE RESEARCH**. Fee contradiction resolved by clustering (6.5% corroborated; forum 0.5% claim CONTRADICTED). Live Etsy 403 / Gumroad timeout recorded. Break-even 1 sale/month on stated assumptions. Saturation **unknown** (no competitors recorded).

## Investigation 3 — GST Invoice Generator for Indian Freelancers (India)

- **Brief**: $50 budget, geography **India** (acceptance scenario B path). 
- **Evidence**: 2 records from 2 sources (problem evidence at SUPPORTING from one group only). Live NPCI page: **HTTP 403 → unavailable**.
- **Commercial (stated assumptions)**: $2/month price (estimate), 2% payment fee, variable $0.06, recurring $6/mo, startup $20 (estimate) → within budget; break-even small but **demand unproven**.
- **Result**: score **3.14/5**, evidence quality **2.86/5**, validation **Level 1**, **REQUIRES MORE RESEARCH**. Level 2 was not met because problem evidence lacks a second independent source — recorded as an explicit gap, not filled.
- **Key uncertainties**: no verified UPI/payment-cost evidence (NPCI unreachable here); no competitor evidence; market size cannot be established.

## Supporting demonstrations in the same run

- **Print-on-Demand Mugs and Tees Store**: screened **INCOMPATIBLE** ($120 startup class > $50 budget; the budget was never raised). Its research session performed the run's one fully live fetch — Shopify pricing (HTTP 200) → 8 price-mention evidence records (SUPPORTING, source URL + retrieval timestamps in the transcript). Live pricing evidence did not and cannot change the budget arithmetic.
- **Paid Fake-Review Writing Service**: **BLOCKED_BY_COMPLIANCE** at screening and **REJECTED** at scoring (prohibited category — fake reviews/deceptive claims).
- **AI Astrology Subscription** (manual, zero evidence): score 1.0, evidence quality **0.0** → **NEEDS_MORE_EVIDENCE** (acceptance scenario D behaviour).
- **Inventory phone-accessories e-commerce**: **INCOMPATIBLE** ($2,000 class).
- **Case-variant planner duplicate**: **DUPLICATE** of the planner opportunity.
- **P-02 mission link**: the owner's $50 instruction was also submitted as a P-02 mission; planning returned **HTTP 422** (baseline planner has no research template, no LLM configured) — recorded in the transcript; the brief links the mission id for traceability instead of depending on the planner.
