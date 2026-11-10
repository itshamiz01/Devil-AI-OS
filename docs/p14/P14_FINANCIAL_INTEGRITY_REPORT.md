# P-14 Stage A — Financial Integrity Report (§10)

**Scope:** Audit only. No production code, existing test, or migration was modified.
New files only: `backend/tests/test_p14_financial.py`, `backend/tests/test_p14_orchestration.py`, this report.
**Fixtures only** — no live money, accounts, or provider credentials.
**Run (own, 2026-11-10):**
```
cd backend && .venv/bin/python -m pytest tests/test_p14_financial.py tests/test_p14_orchestration.py -q
22 passed, 1 xfailed
  test_p14_financial.py:     12 passed, 1 xfailed (13 tests)
  test_p14_orchestration.py: 10 passed           (10 tests)
df -h /tmp before run: 512M tmpfs, 1% used (no fake mass failures)
```

## Method

- Businesses seeded only through governed paths: P-06 fixture businesses (`make_fixture_business` / `business_with_profile`), P-07 verified-revenue path (`verified_revenue`, `authorized_provider_report`), P-07 paid expenses, P-13 portfolio service for allocations.
- Every figure asserted in integer minor units against P-07 service APIs (`revenue.metrics`, `analytics.profitability/health`, `budgets.available_cash`, `ledger.*`, `reports.*`, `consolidated`) and, for portfolio claims, against P-13 `portfolio_finance` read live from P-07.
- Traceability recomputed independently from journal entries (`list_entries`, `account_balances`, `verify_integrity`, `reports.profit_loss`) rather than trusting summary dicts alone.
- Multi-currency: a USD-profile business was created by the governed manual path (set P-06 `default_currency=USD` before declaration→blueprint→`ensure_profile`); the p07 helper forces INR, so it was not used for that business. Evidence below.

## Per-simulation results (§10)

| Sim | Scenario | Result |
|---|---|---|
| (a) | Profitable: ₹10,000 collected − ₹3,000 paid expenses | PASS — net profit ₹7,000 (700000 minor), `is_loss=False`, consolidated row matches, ledger integrity ok |
| (b) | Loss-making: ₹5,000 in, ₹8,000 out | PASS — net profit −₹3,000, `is_loss=True`, health ≠ HEALTHY with a "loss" reason |
| (c) | Newly launched, profile only, zero transactions | PASS — metrics 0/0, profitability `insufficient_data` with `net_profit_minor=None`, health `INSUFFICIENT_DATA`, 0 journal entries, available cash 0 — nothing fabricated |
| (d) | Outstanding liabilities: ₹5,000 opening cash, ₹6,000 AP obligation (Dr 5060 / Cr 2000) | PASS — `obligations_minor=600000`, available = −₹1,000, health AT_RISK/CRITICAL, balance sheet `balanced=True` with liabilities ≥ ₹6,000 |
| (e) | Zero-revenue businesses in a portfolio | PASS — portfolio totals net/projected = 0, `combined_available_cash=None` with "never summed" note; no cash invented |
| (f) | Multi-currency portfolio (INR business + USD business) | PASS (separation) — see Multi-currency finding. One related defect: P14-DEF-F1 (gross collected in portfolio view) |
| (g) | Interrupted transaction: journal post failing mid-operation (line missing currency, key `p14:doomed`) | PASS — 0 entries persist after failure, integrity ok; safe retry with same idempotency key posts exactly 1 entry; second retry returns `duplicate=True`, same id, balance counted once |

## Per-invariant verdicts

| # | Invariant | Verdict | Evidence (test) |
|---|---|---|---|
| 1 | No double-count on duplicate submission (idempotency) | **HOLDS** | `test_p14_invariant_no_double_count_duplicates`: duplicate `external_ref` → `ValidationError`; duplicate fake webhook → `processed` then `duplicate`, metrics count each once. Also (g) ledger idempotency key. |
| 2 | Internal allocation leaves P-07 consolidated byte-equal | **HOLDS** | `test_p14_invariant_internal_allocation_byte_equal`: `json.dumps(consolidated, sort_keys=True)` identical before/after an approved P-13 allocation; independent of P-13 Scenario 12 (new amounts/business names, byte-JSON comparison in addition to dict equality). All allocation rows labelled `INTERNAL_ALLOCATION`, `is_external_payment=False`. |
| 3 | Projected ≠ collected, never summed | **HOLDS** | `test_p14_invariant_projected_never_summed`: projected 5000000 vs net collected 1000000 kept separate in metrics, profitability uses only collected, analyst figures classify them `forecast` vs `verified_fact`. |
| 4 | Unauthorized principal cannot record verified revenue / spend | **HOLDS** | `test_p14_invariant_unauthorized_principal`: EXTERNAL + unregistered AGENT denied by `assert_business_access`; agent-reported settled payment stays `unverified`/`booked`, collected = 0; EXTERNAL spend request → `PermissionDeniedError`; agent transfer → `blocked_level3`; agent settings update + journal reversal → `PermissionDeniedError`. |
| 5 | Reversal-only correction (original unchanged) | **HOLDS** | `test_p14_invariant_reversal_only_and_traceability`: original entry's lines/totals byte-identical after reversal, reversal is a new entry (`kind=reversal`, `reversal_of_id` set), second reversal refused (`InvalidStateTransitionError`). No edit/delete path was used. |
| 6 | Every figure traceable to journal entries | **HOLDS** (with F1 exception in the P-13 gross-collected *presentation* field) | Same test: every entry balanced (debit=credit, >0), `verify_integrity ok`, P&L recomputed from journal lines: after reversing the ₹10,000 sale, journal income = 0, expenses = ₹3,000, net = −₹3,000; cash balance −₹3,000 matches. Net-collected / profitability / consolidated figures in all other tests were cross-checked against metrics + ledger. Exception: portfolio `collected_minor` does not trace to any journal/metric value — it is always 0 (F1). |
| 7 | Multi-currency never summed without a documented rate (§14) | **HOLDS** | (f): consolidated INR contains only the INR business (₹10,000), consolidated USD only the USD business ($100); per-business metrics in the other currency = 0. |
| 8 | Conversion only via P-07's own mechanism | **HOLDS** | (f): `convert_amount` with no rate → `status=pending, converted_minor=None` (original preserved); after owner `add_exchange_rate` USD→INR 83.25 (`manual_owner`) → 832500 minor with rate id/timestamp. Unknown currency `XXX` → `ValidationError` from the registry. |

## Multi-currency finding

**Supported, with evidence.** The currency registry (`app/financial/constants.py: DEFAULT_CURRENCIES`) seeds INR, USD, EUR, GBP, AED, SGD, AUD, CAD (exponent 2), JPY, KRW (0), KWD, BHD (3); unknown codes are refused. Businesses can carry different base currencies (USD profile proven in-test), revenue can be recorded per currency, and all reporting is per-currency: `RevenueService.metrics` filters by currency and lists `other_currencies` without summing; `FinancialService.consolidated(currency)` includes only businesses whose profile base currency equals the requested currency; `PortfolioService.portfolio_finance(currency)` sums only rows whose currency matches. Conversion is explicit-only through `FinancialService.convert_amount` + owner-recorded `ExchangeRate` rows; a missing rate yields `pending`, never an invented rate. **No defect in separation/conversion.** The one multi-currency-adjacent defect is F1 below, which affects single-currency portfolios equally.

## Traceability check

Recomputed in `test_p14_invariant_reversal_only_and_traceability` and in simulations (a)/(d)/(g): (1) `ledger.verify_integrity(business)` recomputes all lines and returned `ok=True` in every test that called it; (2) every listed journal entry is balanced; (3) `reports.profit_loss` (pure journal-line aggregation, internal transfers excluded) matched the independently expected income/expense/net figures, including after a reversal; (4) `reports.balance_sheet` returned `balanced=True` with the AP liability present in (d); (5) account balances (`account_balances`) matched hand-computed cash. Figures that are *not* journal-derived by design — projected revenue, analyst forecasts, portfolio internal allocations — are labelled as such and were verified never to enter collected/profit totals.

## Defect list

### P14-DEF-F1 — Portfolio gross collected is always reported as 0 — Severity: P2 (medium)

- **Module:** `app/portfolio/finance.py`, `FinanceMixin.portfolio_finance` (lines ~44, 63).
- **Reproduction:** `test_p14_f2_portfolio_gross_collected_traceable` (xfail, strict=False): business with ₹4,000 verified collected revenue in a portfolio → `portfolio_finance` row `collected_minor == 0` and `totals["collected_minor"] == 0`; expected 400000. Direct probe (pre-test) confirmed the same for INR ₹10,000 + USD $100 businesses: both rows and both currency totals showed `collected_minor: 0` while `net_collected_minor` was correct.
- **Root cause:** The code reads `revenue.get("collected_minor")` from the P-07 summary's revenue dict, but `RevenueService.metrics` has never returned a `collected_minor` key — the gross figure is named `collected_gross_minor`. The `.get(..., 0)`-style fallback silently yields 0 instead of failing.
- **Cross-module impact:** P-13 portfolio finance only (API + any Command Center surface rendering that field). Net collected, projected, per-business cash, concentration (which correctly uses `net_collected_minor` in `intelligence.py`) and all P-07 figures are unaffected. Risk is misreporting: a reader comparing gross vs net (e.g. inferring refunds = gross − net) would compute  −net or conclude nothing was ever collected gross.
- **Proposed minimal repair (Stage B, not applied):** In `portfolio/finance.py`, change the row construction to `"collected_minor": int(revenue.get("collected_gross_minor") or 0)` (or rename the portfolio field to `collected_gross_minor` for clarity and update consumers). Add a regression assertion in P-13 Scenario 13/16 that gross ≥ net and gross > 0 when verified revenue exists. No schema/migration change needed.
- **Status in this suite:** Test asserts correct behaviour and is marked `@pytest.mark.xfail(strict=False, reason="P14-DEF-F1: …")`.

No other financial defects were found. In particular, no P0/P1 defect: no double-count, no partial posting, no projected/collected blending, no unauthorized verified recording, and no non-reversal correction path was observed.

## Carried-forward P-07 limitations — re-verified from code (2026-11-10)

| Limitation | Verdict | Code evidence |
|---|---|---|
| Stripe: interface-only / REQUIRES OWNER CONFIGURATION, fake-only end-to-end | **CONFIRMED still true** | `app/financial/payments.py`: module docstring "only the deterministic FakeProvider is exercised end-to-end. The Stripe adapter is interface + event mapping, status `interface_only` / REQUIRES OWNER CONFIGURATION — it has never been tested against Stripe's real interface"; `StripeAdapter.health()` returns `interface_only`; `seed_providers` seeds `("stripe", "stripe", "interface_only", "AUTONOMUS_STRIPE_WEBHOOK_SECRET")`; `PaymentsService.process_webhook` raises `ValidationError` for `interface_only`/`disabled` providers before any processing. |
| §17 natural-language analyst NOT IMPLEMENTED | **CONFIRMED still true** | `app/financial/analyst.py`: module docstring "The natural-language conversational layer is NOT IMPLEMENTED"; every answer's provenance carries `"natural_language_layer": "NOT IMPLEMENTED — no LLM exists in staging"`. What exists is a deterministic structured-intent interface (`INTENTS` set, classified figures with sources) — no LLM, no prose generation, no ledger write path. |
| PDF export NOT IMPLEMENTED | **CONFIRMED still true** | `app/financial/reports.py`: docstring "PDF is NOT IMPLEMENTED (stdlib-only constraint)"; `ReportService.export(..., "pdf")` raises `ValidationError("PDF export is NOT IMPLEMENTED in P-07 …; use CSV or JSON (§24)")`. JSON + CSV exports are implemented. P-13 corroborates: `app/portfolio/planning.py` report export returns `"pdf": "NOT IMPLEMENTED"`, and P-13 Scenario 16 asserts `exported["pdf"] == "NOT IMPLEMENTED"`. |

## NOT EXECUTED

- Live Stripe / any real provider, real bank statements, real money: **NOT EXECUTED** by design (fixtures-only rule; Stripe is interface-only per above).
- Multi-currency *portfolio* finance with mixed-currency members in a single `portfolio_finance` call beyond the two-business INR+USD case, and FX conversion inside portfolio totals: **NOT EXECUTED as a separate test** — portfolio totals are per-currency by construction and conversion is a P-07 function already asserted in (f); no portfolio-level FX conversion mechanism exists to test.
- Concurrent duplicate webhook race (threads): covered by P-07 Scenario 11 in the existing suite; this suite re-verified sequential duplicate idempotency independently and did not re-run the threaded race.
