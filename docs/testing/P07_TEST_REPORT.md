# P-07 Test Report — Financial Intelligence Engine

**Final full-suite run (one run, gate evidence): 404 passed,
1 warning in 203.78s** — 348 pre-existing regression tests
(P-01–P-06) + 56 new P-07 tests. The single warning is the
pre-existing Starlette TestClient/httpx deprecation, unchanged
since P-01. Baseline before any P-07 change: 348 passed (158.52s).

| File | Tests | Covers |
|---|---|---|
| `tests/test_p07_unit.py` | 17 | §26.1 unit: money, ledger, formulas |
| `tests/test_p07_scenarios.py` | 14 | §26.4 critical scenarios 1–14 |
| `tests/test_p07_security.py` | 14 | §26.3 security (12 items) + Article-0 limits + Stripe honesty |
| `tests/test_p07_integration.py` | 11 | §26.2 integration: migration cycle, bridge, HTTP, reports |
| **P-07 total** | **56** | |

Real-uvicorn smoke: `docs/reports/P07_SMOKE_EVIDENCE.txt` — 79
checks, all PASS (Scenarios 1, 3, 5+6, 8, 9, 10, 14 over HTTP).

## §26.4 scenario mapping (all 14, named tests)

| # | Scenario | Test |
|---|---|---|
| 1 | Projected ₹50,000 vs collected ₹10,000, never merged | `test_scenario_01_projected_vs_collected` (+ smoke) |
| 2 | Refund ₹200 of ₹1,000: original traceable, net reflects, balanced | `test_scenario_02_refund` |
| 3 | Same signed webhook ×3 → exactly one posting | `test_scenario_03_duplicate_webhook` (+ smoke) |
| 4 | Agent-reported ₹5,000 unverified → never collected | `test_scenario_04_unverified_payment` |
| 5 | ₹2,500 vs ₹2,000 experiment budget → held, audited, no obligation | `test_scenario_05_budget_restriction` (+ smoke) |
| 6 | ₹20,000 − ₹5,000 reserve − ₹3,000 committed − ₹2,000 obligations = ₹10,000 | `test_scenario_06_protected_reserves` (+ smoke, minus the obligation leg) |
| 7 | USD→INR conversion: original intact, rate+timestamp, missing rate → pending | `test_scenario_07_currency_conversion` |
| 8 | Provider ₹1,000 vs ledger ₹900: flagged, neither overwritten, audited adjustment | `test_scenario_08_reconciliation_mismatch` (+ smoke) |
| 9 | Internal transfer excluded from consolidated revenue | `test_scenario_09_consolidated_reporting` (+ smoke) |
| 10 | Projected-only → health INSUFFICIENT_DATA, no invented profit | `test_scenario_10_missing_financial_data` (+ smoke) |
| 11 | Concurrent duplicate payment events (two real threads) | `test_scenario_11_concurrent_payment_events` |
| 12 | Failed posting rolls back completely | `test_scenario_12_failed_posting_rolls_back` |
| 13 | ₹5,000 in / ₹8,000 out → loss reported as a loss | `test_scenario_13_negative_financial_outcome` |
| 14 | Agent transfer attempt → blocked, audited, no credentials exposed | `test_scenario_14_unauthorized_transfer_request` (+ smoke) |

## §26.3 security mapping (all 12 items)

| Item | Test |
|---|---|
| Unauthorized financial access | `test_unauthorised_access_denied` |
| Cross-business data leakage | `test_cross_business_leakage_blocked_and_audited` |
| Unauthorized budget changes | `test_unauthorised_budget_change_denied` |
| Unauthorized spending | `test_agent_self_approval_impossible` (+ Scenario 14) |
| Secret exposure | `test_secret_exposure_scan` |
| Forged webhook events | `test_forged_webhook_rejected` |
| Replay attacks | `test_replay_attack_rejected` |
| Duplicate events | `test_duplicate_event_protection` (+ Scenario 3/11) |
| Financial record tampering | `test_posted_record_tampering_detected` |
| Invalid currency and amount inputs | `test_invalid_currency_and_amount_rejected` |
| Unauthorized ledger modification | `test_unauthorised_ledger_modification_denied` |
| Prompt injection via imported descriptions | `test_prompt_injection_in_imported_data` |
| *Extra:* agents cannot write financial limits (Article 0) | `test_agent_cannot_write_financial_limits` |
| *Extra:* Stripe is interface-only, honestly labelled | `test_stripe_adapter_is_interface_only` |

## §26.1 / §26.2 highlights

- Money: JPY 0-dp / KWD 3-dp / INR 2-dp precision; floats and bare
  ints rejected; Decimal-exact arithmetic (0.10 + 0.20 = 0.30);
  Indian digit grouping (₹12,34,567.89); structural proof that no
  `float(` exists in the package.
- Ledger: balancing enforced; reversal is the only correction;
  idempotent reposting.
- Formulas: available cash (no double-counting), budget utilisation,
  MRR/ARR (annual ÷12 half-even), break-even, runway (zero burn →
  insufficient data, never infinite), FX pending state, recurring
  detection with amount-change flag, frozen forecasts + variance.
- Integration: migration cycle 63 → 90 → 63 → 90 tables; profile
  created from the real P-06 bridge payload (estimates labelled,
  zero expenses created); full HTTP flow (float amount → 422);
  webhook over HTTP (forged → rejected); CSV re-import dedupe;
  reports + CSV export carry methodology and the not-audited notice;
  PDF export raises NOT IMPLEMENTED; analyst classifies every
  figure; P-08 indicators; P-03 assumption comparison; free local
  inference recorded at exactly 0 (a nonzero invented cost is
  refused); Level-2 spend approval consumed exactly once.

## Defects the tests caught (fixed, disclosed)

1. Foreign-currency postings failed against a base-currency chart →
   per-(business, currency) charts with template provisioning.
2. Balance-sheet sections never populated → report always
   "unbalanced"; fixed.
3. Duplicate `external_ref` revenue accepted → guard added.
4. Unknown currency codes accepted → known-currency validation.
5. `verify_revenue` flagged verified before posting → reordered.
6. Ledger reversal lacked a service-level owner check → added
   (route already gated it).

## Not tested (honest)

- Stripe against Stripe's real interface or test environment —
  NOT tested (no access from this codebase); adapter is
  interface-only, REQUIRES OWNER CONFIGURATION.
- Windows behaviour — not tested (Linux sandbox; carried).
- Real LLM analyst behaviour — no LLM exists in staging; the
  deterministic interface is what is tested.
