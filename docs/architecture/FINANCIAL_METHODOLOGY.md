# P-07 Financial Methodology

How every financial figure in AUTONOMUS is produced. A developer must
be able to reproduce any figure from this document and the stored
records alone — no LLM explanation is involved anywhere (§28).

## 1. Money representation (§5.1)

- Every amount is an **integer count of minor units** (paise, cents)
  plus an explicit currency code. Per-currency exponents come from
  owner-governed configuration: INR/USD/EUR/GBP = 2, JPY = 0,
  KWD = 3, configurable.
- API amounts are **decimal strings** (`"50000.00"`). JSON numbers are
  rejected (422) so a float can never enter. Parsing rejects floats,
  booleans, bare integers (unit-ambiguous) and excess precision for
  the currency.
- There is no `float(` call anywhere in `app/financial/` — enforced
  by a structural test (`test_no_float_calls_in_financial_package`).
- Display: INR uses ₹ with Indian digit grouping (₹12,34,567.89);
  the currency code is always shown alongside.

## 2. Truth hierarchy (§3.1) — classifications never merge

Each revenue record carries exactly one current classification:

| Classification | Meaning |
|---|---|
| projected | Expected/forecast revenue (EXPECTED) |
| booked | Ordered or settled but **not verified** |
| invoiced | An invoice has been issued |
| collected | Settled **and verified** from an authorised source |
| refunded / disputed | Independent refund/dispute records exist |
| recognized | Verified and recognised per the lifecycle |

Lifecycle: EXPECTED → ORDER_CREATED → PAYMENT_PENDING →
PAYMENT_AUTHORIZED → PAYMENT_SETTLED → VERIFIED → RECOGNIZED, plus
CANCELLED / FAILED / PARTIALLY_REFUNDED / REFUNDED / DISPUTED /
CHARGEBACK / REVERSED. Not every record traverses every state.

**Collected rule (§7.3):** a record counts as collected only when
`verification_status = verified`, which requires evidence from an
authorised source: a signature-verified provider webhook, a
reconciled provider/bank statement, or owner attestation with
evidence through a hash-bound approval. A browser redirect, frontend
message, agent report, LLM response, unverified webhook, or order
creation can **never** verify a payment. A settled-but-unverified
record classifies as *booked*. Unverified records never count toward
collected figures, in any report, at any level of consolidation.

**Net collected** = Σ verified collected − Σ refunds − Σ chargebacks,
per currency. Projected/booked/invoiced figures are always reported
as separate lines, never added into collected.

## 3. Ledger and accounting (§5)

- Double-entry journal. Every posted entry: Σ debits = Σ credits,
  enforced before commit; multi-record postings are one DB
  transaction (a failure rolls back completely — no unbalanced or
  partial journal can remain).
- Chart of accounts: the 29-account §5.2 template, instantiated per
  (business, currency). Foreign-currency postings provision the
  template accounts in that currency on first use; codes come only
  from the template.
- Posted entries are immutable: no update, no delete. Corrections
  are **reversal entries** (mirror lines, `kind=reversal`, reason +
  actor + timestamp required), or audited adjustment entries
  (reconciliation resolutions).
- Duplicate protection: idempotency keys on postings; a unique
  external reference per business on revenue records.
- `verify_integrity(business_id)` recomputes every entry's balance
  and every account balance from the stored lines; a direct database
  edit of a posted line is detected (proven by test).
- Periods are monthly per business; postings into closed periods are
  refused.

## 4. Revenue metrics (§6)

- **MRR** = Σ monthly-normalised amounts of *active* subscriptions:
  monthly → amount; annual → amount ÷ 12 (Decimal division,
  half-even rounding to the minor unit, per subscription);
  cancelled/paused excluded. **ARR** = MRR × 12. Subscription
  *contract* value is reported separately from cash collections —
  an annual plan is never counted twelve times in collected revenue.
- Category accounts: each revenue category maps to its own income
  account in the chart (per-business mapping from the template), so
  the P&L by category is a ledger read, not a re-computation.
- Refunds post Dr refunds-contra / Cr processor and flip the original
  to PARTIALLY_REFUNDED / REFUNDED by cumulative amount; disputes
  post to the dispute liability path. Originals are never edited.

## 5. Expenses (§8)

Kinds distinguish P&L expenses from assets, deposits and transfers —
not every payment is an expense. P&L totals include only
`operating_expense`-kind records by payment status (paid / committed
/ due). Recurring detection groups by (normalised vendor, category),
requires ≥2 occurrences, infers cadence from average gaps
(monthly ≈ 28–32 days), flags amount changes, and computes the next
expected date. Detection is a **suggestion**; the owner confirms or
corrects (§8.3).

## 6. Budgets, reserves, available cash (§9)

- Budget utilisation: spent = paid expenses charged to the budget;
  committed = committed expenses + authorised-unrecorded spending
  requests; remaining = approved − spent − committed;
  utilisation = (spent + committed) ÷ approved (Decimal string,
  4 dp).
- **Available cash (§9.4)** = latest verified cash balance
  − protected reserves − committed − accounts-payable obligations
  (credit balance of AP accounts). Each term is computed once from
  its own source; no double-counting.
- Reserves (emergency / operational / tax / refund / continuity /
  owner-designated) are **never** spendable and are excluded from
  available cash by construction.
- Spend authorisation: Level 0 (recording), Level 1 (inside an
  active budget + configured per-currency limits + available cash),
  Level 2 (held for owner; completes only via a hash-bound P-01
  approval bound to the exact request id + amount + currency; drift
  fails closed; consumed once), Level 3 (transfer / wallet transfer /
  investment / reserve or policy change) — **structurally blocked**;
  there is no approval path and no execution mechanism (§23.2).

## 7. Reconciliation (§13)

Matching ladder, in order: (1) exact external ID, (2) payment
reference, (3) invoice reference, (4) amount + currency + date
window (±3 days). Fuzzy/similarity matches are recorded as
*suggestions* and are never auto-verified. Classifications (§13.3):
MATCHED, AMOUNT_MISMATCH, DATE_MISMATCH, MISSING_IN_INTERNAL_LEDGER,
MISSING_IN_PROVIDER_RECORDS, DUPLICATE_EXTERNAL, UNMATCHED.
A mismatch never overwrites either side; resolution is one of:
audited adjustment journal (with evidence + authorised review),
accept-with-note, or ignore-with-reason — all recorded.

## 8. Multi-currency (§14)

Transaction, base (profile) and reporting currencies are distinct
fields. Every metric is computed **per currency**; currencies are
never summed without conversion. Conversion requires a stored rate
(documented source or owner-entered manual rate) with provenance
and timestamp; a missing rate returns status `pending` with a null
converted amount — a rate is never invented. Converted figures cite
the rate record used.

## 9. Profitability (§10)

Per currency, from verified figures only:
gross profit = net collected − direct costs; net profit = gross −
indirect (operating) costs; margins are Decimal ratios of the same.
Break-even revenue = fixed costs ÷ contribution-margin ratio, where
CM ratio = (net collected − variable costs) ÷ net collected;
returned only when net collected > 0 and CM ratio > 0, else an
explicit `insufficient_data`/`not_applicable` status. Unit-economics
profiles differ by business model (SaaS: MRR/ARR/churn-shaped;
digital products: per-sale contribution; services: per-engagement) —
SaaS metrics are never applied to a services business. Missing
inputs produce `insufficient_data` with a `missing_data` list —
never an invented value. Losses are reported as losses.

## 10. Cash flow, runway, health (§12)

- Cash-flow statement separates **actual** (journal-derived) from
  **forecast** (forecast records) in distinct sections, always.
- Runway = available cash ÷ average monthly burn, where burn is the
  mean of monthly paid P&L expenses over the months with data.
  Zero or unknown burn → `insufficient_data` (runway is never
  reported as infinite). Fewer than 3 months of history marks the
  figure *preliminary*. Uncollected invoices are never treated as
  cash.
- Health classification: INSUFFICIENT_DATA when there is no verified
  collected revenue or no expense history (projected-only businesses
  land here — no profit is invented); otherwise HEALTHY / WATCH /
  AT_RISK / CRITICAL from runway thresholds (owner-configured:
  watch < 6 months, at-risk < 3, critical < 1), refund/chargeback
  rates, and loss state. **Hard conditions override favourable
  scores** (e.g. a current loss or critical runway caps the status).

## 11. Forecasting (§11)

Deterministic methods only: historical average, moving average
(last 3 periods), linear trend (least squares over monthly buckets,
projected one period), and assumption-driven scenarios
(conservative / base / optimistic) whose assumptions are stored
with the scenario. Every forecast stores its method, inputs window,
assumptions and confidence basis. **Forecasts are frozen at
creation** (§11.4): forecast-vs-actual variance is computed against
the frozen record; recording actuals never rewrites a forecast.
Optimistic scenarios are labelled optimistic and may never be
presented as expected income.

## 12. Analyst classifications (§17.2)

Every figure in an analyst answer is one of: `verified_fact`
(stored, verified records), `calculated_metric` (deterministic
formula over stored records — formula cited), `forecast`
(frozen forecast/scenario), `assumption` (P-03/P-06 estimate,
labelled), or `missing` (with the reason). Answers carry a
provenance block naming the engine and sources. The analyst is
deterministic; no LLM is involved, and the natural-language layer
is NOT IMPLEMENTED (see implementation report §20).
