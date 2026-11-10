# P-07 Implementation Plan — Financial Intelligence Engine

Derived from `docs/audits/P07_PRE_IMPLEMENTATION_AUDIT.md` and the
P-07 prompt's §29 stage order. Baseline before code: **348/348 green**
(158.52 s). One additive migration; no existing table altered.

## Package layout (flat, repo convention — audit §8.2)

`backend/app/financial/`
- `constants.py` — vocabularies (truth classifications, revenue
  lifecycle, account types, reserve types, alert types, approval
  levels), default chart of accounts, default settings, INR formatter.
- `money.py` — `Money` (integer minor units + currency), currency
  registry (configurable exponents), Decimal parsing/formatting,
  Indian digit grouping. No float anywhere.
- `ledger.py` — chart seeding, journal posting (balanced, idempotent,
  transactional), reversal/adjustment, account balances, integrity
  verification.
- `revenue.py` — revenue records + lifecycle, invoices, orders,
  subscriptions, refunds, disputes, revenue metrics (incl. MRR/ARR).
- `expenses.py` — expense records (§8.2 fields, expense-vs-other
  kinds), recurring detection + owner confirm/correct.
- `budgets.py` — budget hierarchy, spending limits, reserves,
  available-cash formula, spend authorisation (levels 0–3, level 3
  structurally blocked), commitment recording.
- `payments.py` — provider registry + adapter interface, FakeProvider,
  Stripe interface-only adapter, webhook pipeline (HMAC, replay
  window, idempotency, dead-letter), CSV statement importer.
- `reconciliation.py` — sessions, deterministic matching ladder,
  discrepancy classification, owner-reviewed resolution via audited
  adjustment.
- `analytics.py` — profitability + model-specific unit-economics
  profiles, cash flow (actual vs forecast separated), runway, health
  classification (hard risks override), risk/alert engine.
- `forecasting.py` — frozen deterministic forecasts, conservative/
  base/optimistic scenarios, forecast-vs-actual variance.
- `analyst.py` — §17 deterministic structured query interface with
  §17.2 provenance classification (NL layer NOT IMPLEMENTED).
- `reports.py` — P&L, balance sheet, cash-flow statement, budget
  utilisation, reconciliation report, business comparison,
  forecast-vs-actual; CSV/JSON export with methodology metadata.
- `service.py` — `FinancialService` facade: settings seeding, profile
  creation from the P-06 bridge payload, business-isolation guard,
  P-03 assumption comparison, P-05/P-04 task-cost records (§19),
  internal transfers (§18), tax records (§15), P-08 indicators (§25).

`backend/app/database/models/financial.py` — 27 tables:
financial_profiles, financial_accounts, financial_periods,
journal_entries, journal_lines, revenue_records, invoices, orders,
subscriptions, refunds, disputes, expense_records, budgets,
spending_requests, financial_reserves, cash_balances,
payment_providers, payment_events, provider_payouts,
reconciliation_sessions, reconciliation_items, exchange_rates,
financial_forecasts, financial_scenarios, financial_alerts,
tax_records, task_cost_records.

API: `backend/app/api/routes/financial.py` +
`backend/app/api/schemas/financial.py`, registered in `app/main.py`;
service constructed in `app/core/application.py` (seed settings +
provider registry at startup). New `Financial*` event types in
`app/events/events.py` (isolation violation + blocked transfer in the
critical set).

## Stage mapping (§29)

1. **Audit** — the audit doc + this plan; baseline recorded. ✔
2. **Financial core** — money.py, currency registry, periods, chart,
   journal + validator, immutability, migration, unit tests.
3. **Revenue & expenses** — lifecycle, refunds/disputes, evidence
   classification, business integration, recurring detection.
4. **Budgets & capital** — hierarchy, limits, reserves, available
   cash, approval workflow (P-01 references), P-04/P-05 hooks.
5. **Payments foundation** — adapter interface, FakeProvider, Stripe
   interface-only, webhook pipeline, CSV import.
6. **Reconciliation** — imports, matching ladder, discrepancies,
   reviewed resolution.
7. **Profitability & forecasting** — unit economics per model
   profile, break-even, frozen forecasts, scenarios, variance.
8. **Risk & intelligence** — health classification, anomaly alerts,
   analyst query interface (P-02 read-only).
9. **Frontend** — N/A in staging (no frontend exists; P-11 owns the
   Command Center). API responses carry the §22 view models.
10. **Integration & independent audit** — full suite, scenario map,
    smoke on real uvicorn, §31 implementation report, tracker +
    README + transfer zip.

## Test plan (target: 348 regression + ~55 new)

- `test_p07_unit.py` — money/currency precision (JPY 0-dp, KWD 3-dp),
  Decimal-only arithmetic (float inputs rejected), journal balancing,
  available-cash formula (no double count), budget utilisation,
  MRR/ARR methodology (annual plan not double-counted), break-even,
  runway, refund math, FX conversion + pending state.
- `test_p07_integration.py` — migration cycle (upgrade/downgrade/
  re-upgrade, exact table count), profile auto-creation from a real
  P-06 fixture business payload, HTTP surface, webhook end-to-end via
  FakeProvider, CSV import + re-import dedupe, reconciliation flow,
  reports + exports, analyst queries, P-08 indicators, P-03
  assumption-vs-actual view.
- `test_p07_scenarios.py` — §26.4 Scenarios 1–14 as named tests
  (Scenario 11 with two real threads; Scenario 12 with a posting
  forced to fail mid-transaction).
- `test_p07_security.py` — §26.3: unauthorised access, cross-business
  leakage (denied + critical event), unauthorised budget change,
  unauthorised spend, secret-exposure scan (responses + DB rows),
  forged webhook, replay attack, duplicate events, posted-record
  tampering (no mutation path + integrity detection), invalid
  currency/amount, prompt injection via imported descriptions,
  agent self-approval of a spend (impossible), level-3 structural
  block, limits not writable by agents.

## Smoke plan (real uvicorn, transcript saved)

Scenarios 1, 3, 5+6, 8, 9, 10, 14 demonstrated over HTTP against a
booted server with a fixture business: projected vs collected
separation; the same signed webhook delivered ×3 → one posting;
₹20,000 cash / ₹5,000 reserve / ₹3,000 committed → available cash and
a ₹2,500 spend against a ₹2,000 experiment budget held + audited;
₹1,000-vs-₹900 reconciliation mismatch flagged with neither value
overwritten; internal transfer excluded from consolidated revenue;
projected-only business → INSUFFICIENT_DATA; agent transfer attempt
blocked + audited.

## Explicit non-goals (honesty register)

- No transaction execution of any kind (§23.2) — no transfer, wallet,
  payout or spend *execution* code path exists.
- No live provider integration; Stripe = interface + mapping,
  REQUIRES OWNER CONFIGURATION.
- No natural-language analyst (no LLM in staging).
- No PDF export; no frontend (P-11).
- P-08 is not built; only its read-only indicator interface is
  exposed and documented.
