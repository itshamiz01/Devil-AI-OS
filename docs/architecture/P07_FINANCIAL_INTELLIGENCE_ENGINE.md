# P-07 Financial Intelligence Engine — Architecture

**Status: BUILT AND VERIFIED IN STAGING (404 tests, one run).**
Methodology (every formula): `FINANCIAL_METHODOLOGY.md`.
Security controls: `docs/security/P07_FINANCIAL_SECURITY.md`.
Operations: `docs/operations/P07_FINANCIAL_OPERATIONS.md`.

## 1. Purpose and boundary

P-07 is the portfolio's financial memory and conscience: accounting,
verification and governance over P-06 businesses. It **never moves
money** (§23.2): there is no transfer, wallet, payout or spend
execution path anywhere in the package. Spending *decisions*
(authorisation checks against budgets, reserves and available cash)
exist; execution does not, and Level-3 actions are structurally
blocked (see `FINANCIAL_METHODOLOGY.md` §6).

## 2. Package layout (`backend/app/financial/`)

| Module | Responsibility |
|---|---|
| `money.py` | `Money` (integer minor units), `CurrencyRegistry`, decimal-string parsing/formatting (INR Indian grouping) |
| `constants.py` | §3.1 classifications, verified sources, lifecycle, §5.2 chart template, budget scopes, reserve types, Level-3 kinds, ISO exponents, owner-governed default settings |
| `ledger.py` | Chart seeding (per business+currency), periods, balanced posting, reversals, balances, integrity verification |
| `revenue.py` | Revenue lifecycle + classification gating, invoices, orders, subscriptions (MRR/ARR), refunds, disputes |
| `expenses.py` | Expense records (§8.2 fields), kinds, P&L totals, recurring detection |
| `budgets.py` | Budgets, reserves, cash balances, §9.4 available cash, spend authorisation Levels 0–3 |
| `payments.py` | Provider adapters (fake / Stripe interface / CSV), webhook pipeline, statement parsing |
| `reconciliation.py` | Sessions, deterministic matching ladder, §13.3 classifications, owner-reviewed resolution |
| `analytics.py` | Profitability + unit economics, cash flow, runway, health, deterministic risk scan → alerts |
| `forecasting.py` | Frozen forecasts (average / moving average / trend), variance, scenarios |
| `reports.py` | P&L, balance sheet, cash-flow statement, budget utilisation, reconciliation report; CSV/JSON export |
| `analyst.py` | Deterministic query interface (§17): 11 intents, §17.2 provenance contract |
| `service.py` | `FinancialService` facade: settings/currencies, isolation guard, profiles from the P-06 bridge, opening balances, internal transfers, FX, tax records, task costs, assumption comparison, P-08 indicators, consolidation, engine status |

Models: `app/database/models/financial.py` (27 tables);
repositories: `app/database/repositories/financial.py`;
API: `app/api/routes/financial.py` (83 routes),
`app/api/schemas/financial.py` (amounts are decimal strings).

## 3. Reuse of P-01–P-06 (no parallel systems)

- **Approvals:** P-01 `ApprovalService`, hash-bound. Financial
  actions: `financial.budget_approve`, `financial.spend_approve`,
  `financial.adjustment_approve`, `financial.revenue_verify`.
  There is deliberately **no** `financial_approvals` table.
- **Audit:** P-01 `audit_events` (append-only by API). Financial
  actions include `financial.journal_posted`,
  `financial.revenue_verified`, `financial.spend_decided`,
  `financial.level3_blocked`, `financial.isolation_violation`,
  `financial.webhook_forged`, `financial.webhook_replay`, …
- **Settings:** owner-governed `system_config` keys
  `financial.settings` / `financial.currencies` (spending limits per
  currency, health thresholds, replay window, currency exponents).
  Agents cannot write them (Article 0).
- **Businesses:** FK to P-06 `businesses.id`; profiles are created
  from the P-06 financial-inputs bridge payload; its estimates stay
  labelled estimates forever and are never posted as actuals.
- **Agents/tasks/execution:** referenced by plain ids for cost
  attribution (§19); P-04's registry defines agent→business scoping
  for the isolation guard; P-05 execution records link via
  `execution_request_id` on task-cost records.

## 4. Database schema (27 tables, migration `c3b5cdba2559`)

financial_profiles (per-business identity: base/reporting currency,
business model, P-06 estimates, fixture flag) · financial_accounts
(chart, unique per business+code+currency) · financial_periods
(monthly, open/closed) · journal_entries (immutable, idempotency
key, reversal links, internal-transfer flag) · journal_lines
(debit/credit minor units) · revenue_records (classification,
lifecycle, verification, evidence) · invoices · orders ·
subscriptions · refunds · disputes (independent records linked to
the original) · expense_records · budgets · spending_requests
(authorisation decisions — not executions) · financial_reserves ·
cash_balances (snapshots feeding §9.4) · payment_providers (status,
env-var NAME for secrets — never values) · payment_events (every
delivery: signature validity, payload hash, status) ·
provider_payouts · reconciliation_sessions · reconciliation_items ·
exchange_rates (provenance + timestamp) · financial_forecasts
(frozen) · financial_scenarios · financial_alerts · tax_records ·
task_cost_records. **Every amount column is `*_minor` BigInteger
with a currency column; there is no float column anywhere.**

## 5. Provider interface (§7.1)

Adapters implement: health, sign/verify (HMAC), timestamp, parse
(provider payload → normalised event). Normalised event types:
payment_settled / payment_failed / refund_issued / dispute_opened /
payout_paid. The webhook pipeline is: provider status gate →
signature verification → replay window → idempotency (unique
provider+event id; concurrent duplicates suppressed by constraint)
→ processing → audit. Every delivery is persisted as a
payment_event, including forged and replayed ones (as rejected).

## 6. API surface

All routes under `/api/v1/financial/...` with the repo's auth model
(READ / WRITE / APPROVE permission dependencies) and the standard
`{success, data, error}` envelope. Writes are idempotent where the
domain requires it (postings, webhook deliveries, statement
imports). Governance writes are owner-only inside the services as
well as at the route layer. No response contains a secret value
(proven by the secret-exposure scan test).

## 7. Permission and approval model (§15/§23/§25)

- Owner: unrestricted. System: internal posting paths only.
- Agent: reaches **only** the business it is registered to (P-04
  registry `business_ref`); the guard audits violations. Agents may
  *request* spends and *report* revenue (unverified); they cannot
  create budgets/reserves, change limits, verify revenue, complete
  approvals, or touch the ledger directly. Budget-aware permission
  checks for agents go through the P-01 permission engine + the
  budget service — never direct ledger access.
- External: no financial access.
- Approval *decisions* over HTTP require `Permission.APPROVE_ACTIONS`
  (agents do not hold it); spend *completion* is owner-only in the
  service and bound to the exact approval hash.

## 8. Integration contracts (§25)

- **P-02** queries the analyst + read models; it can never modify
  the ledger (no write path is exposed to it).
- **P-03:** `assumption_comparison` confronts P-03/P-06 estimates
  with actuals; originals are never edited.
- **P-04:** budget checks via permission engine + budget service.
- **P-05:** task-cost records (§19) link business/project/agent/
  task/execution ids with estimated vs approved-limit vs actual.
- **P-06:** profiles auto-created from the bridge payload.
- **P-08 (NOT built):** stable read-only indicators endpoint —
  verified collected revenue, actual expenses, profitability, cash
  flow, available capital, runway, risk, budget utilisation,
  reconciliation status.
