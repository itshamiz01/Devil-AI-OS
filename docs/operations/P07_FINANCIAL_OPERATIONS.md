# P-07 Financial Operations

Running the Financial Intelligence Engine day to day. Staging is a
Linux sandbox; production placement is the owner's Windows machine
(verification carried — see limitations).

## 1. Startup behaviour

On application startup the `FinancialService` seeds, idempotently:
owner-governed settings (`financial.settings`), currency exponents
(`financial.currencies`), and the three provider records
(`fake-provider` = active_fake, `stripe` = interface_only,
`csv-import` = configured). Seeding never overwrites owner edits.

## 2. Configuring a real provider (owner only) — Stripe

Stripe ships as **interface + event mapping only** and refuses
webhooks until configured. To configure it (owner, in the owner's
own Stripe dashboard and server environment — never in chat, never
in the database):

1. In Stripe, create a webhook endpoint pointing at
   `POST /api/v1/financial/payments/webhooks/stripe`.
2. Put the signing secret in the environment variable named by the
   provider record: `AUTONOMUS_STRIPE_WEBHOOK_SECRET`. Only the
   variable NAME is stored in the system.
3. Flip the provider status from `interface_only` to active
   (owner action).
4. **Verify against Stripe's test environment** (test-mode events,
   signature checks, refund/dispute/payout mappings) before any
   live reliance — §29 Stage 5: an integration is not complete
   until tested against the provider's real interface or verified
   test environment. That verification has NOT happened yet.

The FakeProvider remains available for deterministic end-to-end
exercises without any real provider.

## 3. Offline imports (§7.4)

Bank/provider statements are CSV with columns
`date, description, amount, currency, external_ref` (amounts are
decimal strings). Import via `POST /api/v1/financial/reconciliation/import`.
Re-importing the same statement is duplicate-safe: rows whose
external reference already exists for the business+source are
skipped and counted in the session summary.

## 4. Reconciliation workflow

1. Import the authoritative statement (provider or bank).
2. Run matching (`POST /financial/reconciliation/{id}/run`).
3. Review items: MATCHED items need nothing; AMOUNT_MISMATCH /
   DATE_MISMATCH / missing-side items need an owner-reviewed
   resolution — `create_adjustment` (posts an audited adjustment
   journal; evidence + reason required), `accept`, or `ignore`
   (reason required). Neither side's value is ever overwritten.
4. The reconciliation report (`GET /financial/reports/reconciliation`)
   summarises session states for the P-08 interface and audits.

## 5. Periods and corrections

Periods are monthly and open automatically on first posting.
Corrections to posted entries are reversals
(`POST /financial/ledger/journals/{id}/reverse`, reason required);
there is no edit/delete path for posted entries, by design.
Run `GET /financial/ledger/integrity?business_id=...` after any
incident or restore: it recomputes all balances from stored lines
and reports any tampering or imbalance.

## 6. Settings the owner may change (API, owner-only)

`PUT /api/v1/financial/settings`: per-currency spending limits
(max single transaction / daily / weekly / monthly, max experiment
loss, max campaign expenditure, max recurring commitment), health
thresholds, webhook replay window, manual-revenue policy, and the
optional electricity cost estimate used for local-inference task
costs. Defaults ship for INR and USD. A currency with no configured
limits fails safe to Level-2 (owner approval) for every spend.

## 7. Backup and recovery (§28.17)

Financial data lives in the application database (SQLite in
staging). Recovery procedure: restore the database file from
backup, start the application (migrations are additive and
idempotent at head), then run the ledger integrity check per
business (§5) and the reconciliation report; any imbalance is
reported, never silently repaired. Journal history is append-only,
so a restored backup replays deterministically. A rehearsed
backup/restore drill remains an owner-side launch condition
(carried from the P-06/ClipOS readiness work) — it has not been
rehearsed for this staging database.

## 8. Testing instructions (§28.18)

```bash
cd backend
.venv/bin/python -m pytest tests/test_p07_unit.py tests/test_p07_scenarios.py \
    tests/test_p07_security.py tests/test_p07_integration.py   # 55 tests
.venv/bin/python -m pytest tests/                              # full suite: 403
.venv/bin/python ../.tmp/p07_smoke.py                          # real-uvicorn smoke
```

The smoke boots a real uvicorn server on port 8797 against a fresh
migrated database under `.tmp/p07_smoke_data/` and writes its
transcript to `docs/reports/P07_SMOKE_EVIDENCE.txt`.

## 9. Known limitations (§28.19)

- Stripe: interface only, REQUIRES OWNER CONFIGURATION (§2).
- §17 natural-language analyst layer: NOT IMPLEMENTED (no LLM in
  staging); the deterministic structured query interface is the
  delivered contract.
- PDF export: NOT IMPLEMENTED (stdlib-only); CSV/JSON only.
- Audit append-only by API, not cryptographically tamper-proof.
- Windows verification not yet performed (owner machine evidence
  outstanding since P-00).
- Tax module tracks and estimates only; it never claims compliance
  or certification; professional review is required.

## 10. Future integration requirements for P-08 (§28.20)

P-08 (Survival and Scaling Engine — NOT started; begins only on the
owner's explicit order) must consume
`GET /api/v1/financial/businesses/{id}/indicators` and the
consolidated `GET /api/v1/financial/overview?currency=...` rather
than computing its own financial figures. The indicators contract:
verified collected revenue, actual expenses, profitability
(status/net/is_loss), cash flow + available capital, runway
(months + status), financial risk (health status), maximum budget
utilisation, reconciliation status — all per business, in the
profile's base currency, with insufficient-data states preserved
(never coerced to zero or invented values).
