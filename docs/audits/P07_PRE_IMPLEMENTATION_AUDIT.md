# P-07 Pre-Implementation Audit — Financial Intelligence Engine

Stage 1 of P-07 (§2.1 / §29 of the P-07 prompt): inspect the ACTUAL
P-01–P-06 implementations before writing code. Nothing in this audit is
assumed from the phase prompts; every claim below was verified in the
repository on 2026-11-09.

## 0. Baseline

- Full suite re-run before any P-07 change: **348 passed, 1 warning in
  158.52s** (the warning is the pre-existing Starlette TestClient/httpx
  deprecation notice, unchanged since P-01). This is the regression
  floor for P-07.
- Migration head at audit time: `a8d7e0c717b4` (P-06), 63 tables.
- Previous-phase tests pin the migration head in five files
  (`test_p02_integration.py`, `test_p03_integration.py`,
  `test_p04_integration.py` ×2, `test_p05_integration.py` ×2,
  `test_p06_integration.py` ×2). Standing precedent (P-04/P-05/P-06):
  when P-07 adds its migration, those pins move to the new head with an
  in-code disclosure comment; assertion strictness is unchanged.

## 1. What already exists (verified in code)

### P-01 Core OS — the substrate P-07 must reuse
- **Approvals**: `ApprovalService` (`app/permissions/approvals.py`)
  binds every approval to action + resource + parameters via SHA-256;
  `verify_binding` fails closed on drift; statuses are a validated
  state machine. P-04/P-05/P-06 all reference it — there is **no**
  per-phase approvals table anywhere.
- **Audit**: `audit_events` is append-only by API (no update/delete
  path); every permission check writes a row. Services write domain
  audit rows via `AuditRepository` (see `BusinessCreationService._audit`).
- **Permissions**: deny-by-default `PermissionEngine`; role defaults in
  `app/permissions/policies.py`. OWNER holds all permissions; AGENT
  holds `read_business_data` but NOT `modify_business_data`,
  `approve_actions` or `request_financial_operations` (the last is in
  `APPROVAL_REQUIRED_PERMISSIONS` — a grant alone never executes it).
- **Config**: owner-governed settings live as JSON in `system_config`
  (P-03 scoring, P-04 factory settings, P-06 `business.settings`).
  Writes are owner-only at the service layer (`_require_owner`).
- **Events**: `EventType` enum + `CRITICAL_EVENT_TYPES` persistence set
  in `app/events/events.py`; each phase appends its own event types.
- **Money today**: amounts in P-01–P-06 are floats in JSON payloads
  (e.g. P-06 declaration `budget_cap_amount: Float`). **No ledger, no
  decimal money type, no journal exists.** P-07 is the first financial
  system; §2.2's "do not introduce a second financial system" is
  satisfied because there is no first one to conflict with.

### P-02 Master Intelligence
- `IntelligenceService` with a decision recorder, provider interface
  (Ollama probe + disabled cloud stub + FakeProvider in tests) and a
  validation gate. **No real LLM has ever been exercised in staging**
  (P-02 gate limitation, carried). §17's conversational analyst
  therefore cannot be honestly built as a natural-language layer; see
  §6 of this audit for the landing decision.

### P-03 Opportunity Discovery
- Opportunities carry commercial analysis and validation records;
  assumptions are labelled estimates. P-07's §25 contract (assumption
  vs actual comparison) reads P-03/P-06 estimate data; it must never
  rewrite it.

### P-04 Dynamic Agent Factory
- `agents` table is the registry (P-01 table, P-04 columns); agents
  have `business_ref`, budgets as JSON config and capability grants
  mirrored into the permission engine. `financial_transaction_request`
  is a catalogued capability that **records requests only** — no money
  movement exists (P-04 gate). P-07 spending authorisation plugs into
  this: agents request, P-07 decides, nothing executes.

### P-05 Universal Digital Execution Engine
- Execution requests/runs carry cost-relevant references (agent, task,
  workspace `business:<id>`); adapters never move money. P-07 §19 cost
  records link to execution request ids as plain references.

### P-06 Business Creation Engine — the direct predecessor
- `businesses` table (id, opportunity FK, category, status,
  `is_fixture`, currency only inside blueprint JSON).
- **The §27 bridge exists and is tested**: `BusinessCreationService
  .financial_inputs(business_id)` → `app/business/financial.py::
  build_p07_payload` returns `{business_id, business_name, is_fixture,
  currency, startup_costs[], recurring_costs[], startup_total_estimate,
  recurring_monthly_estimate, pricing, revenue_recognition: "none…"}`.
  Every value is a financial-value object (amount/range + currency +
  source + classification + confidence + date + assumptions) and the
  builder **rejects revenue/profit keys outright**
  (`FORBIDDEN_FINANCIAL_KEYS`, security-tested in P-06). Route:
  `GET /api/v1/business/businesses/{id}/financial-inputs`.
- P-06 has **no revenue/profit/collected column anywhere** (schema
  proof in the P-06 gate) — P-07 owns that truth from zero.
- P-06 amounts are floats inside JSON. P-07 converts bridge estimates
  to integer minor units at ingestion via `Decimal(str(x))` — the
  float never participates in P-07 arithmetic (documented at the
  conversion point).

## 2. Missing capabilities P-07 must create

Everything in §20 of the prompt is absent: chart of accounts,
double-entry journal, revenue/expense records with evidence metadata,
budgets/reserves, provider adapters + webhook pipeline, reconciliation,
exchange rates, forecasts/scenarios, profitability/health analytics,
alerts, tax tracking, per-business financial profiles, and the P-08
read-only indicator interface. No frontend exists (P-11 owns it), so
§22 lands as API responses shaped for the future Command Center.

## 3. Reuse decisions (no duplicates, §2.2)

| Need | Decision |
|---|---|
| Financial approvals | **Reuse P-01 `ApprovalService`.** Actions `financial.budget_approve`, `financial.spend_approve`, `financial.adjustment_approve` with hash-bound parameters. No `financial_approvals` table; P-07 rows store the `approval_id` reference (§21 approvals endpoints list/decide P-01 approvals filtered to financial actions). |
| Financial audit log | **Reuse `audit_events`** (prompt §20's `financial_audit_logs` is satisfied by the existing append-only log; P-07 writes `financial.*` actions there, mirroring P-06). |
| Financial limits & currency exponents | **Owner-governed `system_config`** key `financial.settings` (+ `financial.currencies`), seeded by P-07, writable only by the Owner principal. Agents have no write path (Article 0: the system never modifies its own limits). |
| Business identity | FK to `businesses.id`; profiles are 1:1 children, never a second business table. |
| Agent/task identity | Plain id references to `agents`/`tasks`/`execution_requests` rows (the P-05 precedent for cross-phase references). |
| Events | New `Financial*` event types appended to the P-01 enum; isolation violations and blocked transfers join the critical persistence set. |
| API | `/api/v1/financial/...` (the prompt's `/api/financial/...` adapted to the repo's versioned prefix, exactly as P-06 adapted its routes); envelope/pagination from `app/api/schemas/common.py`; route permission deps from the P-01 catalogue. |

## 4. Money representation decision (§5.1)

- **Integer minor units** (`BigInteger`) in every amount column, plus
  an explicit `currency` column on every amount-bearing row. No float
  column exists in any P-07 table.
- API amounts are **decimal strings** (`"10000.00"`); pydantic schemas
  type them as `str`, so a JSON number (which would arrive as a float)
  is rejected with 422 before any arithmetic. Parsing is
  `Decimal` → quantised to the currency exponent → minor units.
- Currency exponents come from a registry seeded with ISO 4217 values
  (INR/USD/EUR/GBP 2, JPY/KRW 0, KWD/BHD 3), extendable through
  owner-governed config — configurable, not hardcoded (§5.1).
- P-06 bridge floats are converted once, at ingestion, through
  `Decimal(str(value))`; the conversion is labelled `estimate` forever.
- INR display uses Indian digit grouping (₹12,34,567.89) in formatted
  outputs; currency codes stay explicit everywhere.

## 5. Ledger design (§5)

- Chart of accounts is **per business**, seeded at profile creation
  from a template chart covering §5.2 (asset/liability/equity/income/
  expense with the named sub-accounts); businesses may add accounts;
  mappings differ per business type via the seed template key.
- Posting is a single DB transaction: validate balance
  (Σdebits = Σcredits in minor units), validate accounts belong to the
  business, insert entry + lines, mark posted. Any failure rolls the
  whole posting back (Scenario 12). Duplicate protection: unique
  `idempotency_key` on journal entries and unique
  `(provider_id, external_event_id)` on payment events (Scenario 11).
- Posted entries are immutable through every service/API path: no
  update or delete operation exists; corrections are reversal entries
  (`reversal_of_id`) or adjustment entries, each requiring actor +
  reason, adjustments above zero requiring a hash-bound owner approval
  reference. A `verify_ledger_integrity()` recomputation detects
  out-of-band tampering and reports it (defence in depth; the
  append-only-by-API limitation carried since P-01 still applies).

## 6. §17 AI analyst — honest landing

No LLM exists in staging (carried P-02 limitation) and §17.1 forbids
the analyst from inventing figures. P-07 therefore lands:

- A **deterministic structured query interface** (`FinancialAnalyst`)
  over the same calculation services the reports use. Each answer
  classifies every figure as `verified_fact` / `calculated_metric` /
  `forecast` / `assumption` / `missing` and cites the underlying
  records (journal ids, revenue ids, reconciliation session ids) and
  the calculation timestamp — the §17.2 provenance contract.
- P-02 may call it read-only; there is **no path from the analyst (or
  P-02) to any ledger write** (§25).
- The natural-language conversational layer is **NOT IMPLEMENTED**
  (no model to run it) and will be reported as such in §31 terms.

## 7. Provider framework — honest landing (§7, §29 Stage 5)

- A provider-independent adapter interface (events / verification /
  settlements / refunds / disputes / balances / payouts / health).
- **FakeProvider**: a deterministic in-repo test double implementing
  the full interface + HMAC-signed webhooks — the webhook pipeline
  (signature, timestamp window, replay protection, idempotency,
  duplicate suppression, provenance, audit, dead-letter status) is
  proven against it end-to-end.
- **Stripe adapter**: interface + Stripe-shaped event mapping only,
  seeded with status `interface_only` and **REQUIRES OWNER
  CONFIGURATION**. The owner's Stripe is a connected Muse *service*,
  not reachable from this codebase, and §29 Stage 5 forbids claiming
  an integration not tested against the provider's real interface.
  No real keys, no real account data, no live calls exist or are
  implied. Webhook secrets are referenced by **environment-variable
  name only** (`webhook_secret_env`), never stored as values.
- **CSV/bank-statement import** (§7.4 offline-first): deterministic
  parser, duplicate-safe on re-import (content hash + external ref
  uniqueness), feeds reconciliation.

## 8. Conflicts & ambiguities resolved (documented, §32)

1. Prompt §21 routes (`/api/financial/...`) vs repo convention
   (`/api/v1/...`): repo convention wins (P-06 precedent); route
   shapes otherwise follow the prompt.
2. Prompt §4's nested `financial/core|ledger|...` tree vs the repo's
   flat per-phase package (`app/business/` is flat modules): P-07
   follows the repo — one flat `app/financial/` package with modules
   named for the prompt's subsystems. The prompt itself permits this
   ("adjusted to the existing repository").
3. Prompt §20 lists ~29 entities "to consider", explicitly not a
   requirement to create each: P-07 creates 27 tables (see the
   implementation plan) and folds `forecast_assumptions` into the
   forecast row's JSON, `spending_limits` into owner-governed settings
   + per-budget caps, `financial_transactions` into a composed view
   over journal lines, `financial_approvals`/`financial_audit_logs`
   into P-01 reuse (§3 above).
4. §9.5 Level 1 "pre-authorised" spending: implemented as an
   authorisation *decision* recorded against a budget — it creates a
   commitment record, never a payment. There is no execution step
   anywhere in P-07 (§23.2); "authorised" in P-07 always means
   "authorised to record the obligation", and the API names it so.
5. §24 PDF export: stdlib-only PDF (the P-05 precedent deferred PDF
   for documents) — P-07 exports CSV + JSON with full methodology
   metadata; PDF is **NOT IMPLEMENTED** and reported as such.

## 9. Risks recorded before building

- SQLite concurrency (Scenario 11): the engine runs WAL mode
  (`app/database/connection.py`); the webhook processor treats a
  unique-constraint collision on a racing duplicate as a duplicate
  acknowledgement, not an error.
- Test-suite runtime is already ~160 s; P-07 must stay deterministic
  and avoid sleeps/polling in tests.
- Migration-head pins in five earlier test files must move (disclosed
  above, §0) — the only pre-existing test changes P-07 permits itself.
