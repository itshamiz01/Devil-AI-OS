# P-06 Test Report — Business Creation Engine

**Result: 348 passed, 1 warning in 156.69s — one run, full suite.**
300 pre-existing tests (P-01–P-05 regression) + **48 new P-06 tests**:
16 unit, 6 integration, 10 acceptance scenarios, 16 security
(§29.3's fifteen, with test 1 split into HTTP and service parts).
The single warning is the pre-existing Starlette TestClient/httpx
deprecation warning, unchanged since P-01.

Smoke: `docs/reports/P06_SMOKE_EVIDENCE.txt` (real uvicorn) — Scenario D
first, then A, F, G, J. All assertions in the smoke script passed.

## Disclosed changes to pre-existing tests

Migration-head pins only (the standing P-03→P-05 precedent; each carries
an in-code "P-06 disclosure" comment; strictness unchanged — exact head
still asserted):

- `tests/test_p02_integration.py`, `tests/test_p03_integration.py`,
  `tests/test_p04_integration.py` (×2), `tests/test_p05_integration.py`
  (×2): head `6ffcc7e899fa` → `a8d7e0c717b4` (the additive P-06
  migration). The P-05 migration-cycle test's exact downgrade table
  comparison still passes unchanged.

One additive change to pre-existing **code** (not a test): P-05's
`WorkflowRunIn` gained an optional `business_ref` (default `None`),
propagated via the run checkpoint to step execution requests. Without
it, P-05 workflows cannot write to `businesses` workspaces at all (the
workspace policy requires a `business_ref` the engine never set). All
300 regression tests pass with it; behaviour for runs that do not set
it is byte-identical.

## §29.3 security tests — mapping (all real, named tests in
`tests/test_p06_security.py`)

| # | §29.3 requirement | Test |
|---|---|---|
| 1 | Unauthorised user cannot access business data | `test_security_01_unauthorised_user_cannot_access_business_data` (401s) + `test_security_01b_external_principal_denied_at_service` |
| 2 | Businesses cannot access each other's data/workspaces | `test_security_02_cross_business_data_and_workspace_isolation` (+ persisted `BusinessIsolationViolation` event asserted) |
| 3 | Unvalidated opportunities cannot create businesses | `test_security_03_unvalidated_opportunity_cannot_create_business` |
| 4 | Agents cannot approve their own launches | `test_security_04_agent_cannot_approve_own_launch` (agent-decided approval → launch refused) |
| 5 | Businesses cannot launch without readiness + owner approval | `test_security_05_launch_blocked_without_readiness_or_declaration` |
| 6 | Unapproved templates cannot bypass validation | `test_security_06_unapproved_template_cannot_bypass_validation` |
| 7 | Secrets never appear in generated business documents | `test_security_07_secrets_never_appear_in_generated_documents` (scans every generated file; redaction asserted) |
| 8 | Prompt injection in opportunity text cannot alter gates | `test_security_08_prompt_injection_in_opportunity_text` |
| 9 | External publishing cannot occur without platform authorisation | `test_security_09_no_external_publishing_path` (all channels refuse; no publish route exists) |
| 10 | Pricing cannot be misrepresented as verified revenue | `test_security_10_pricing_cannot_be_reclassified_as_revenue` |
| 11 | Fake revenue/profit cannot be recorded | `test_security_11_no_path_can_record_collected_revenue` (schema-level proof) |
| 12 | Legal documents cannot be fabricated | `test_security_12_legal_documents_cannot_be_fabricated` |
| 13 | Asset copyright/rights uncertainty is flagged | `test_security_13_uncertain_asset_rights_are_flagged` (readiness C blocker) |
| 14 | Creation cannot exceed owner-declared budget limits | `test_security_14_creation_judged_against_declared_budget` (readiness H blocker against the declaration) |
| 15 | Business actions are fully audited | `test_security_15_business_actions_fully_audited` |

## §29.4 acceptance scenarios — mapping (`tests/test_p06_scenarios.py`)

| Scenario | Test | Evidence |
|---|---|---|
| A digital product end-to-end | `test_scenario_a_digital_product_business_end_to_end` | fixture L3 → blueprint → 10 hash-verified assets → KDP gate `REQUIRES_HUMAN_ACTION` → readiness READY-family |
| B software tool | `test_scenario_b_saas_tool_creation` | SaaS template; `verify_prototype` code step completed under P-05 process controls |
| C content, no auto-posting | `test_scenario_c_content_business_no_autoposting` | sample content asset; Substack gate; campaign stays draft |
| D low-validation blocked | `test_scenario_d_real_low_validation_opportunity_blocked` | REAL seed e-book investigation; computed level < 3; decision REQUIRES_MORE_RESEARCH/VALIDATION; zero businesses. Smoke shows level **1** |
| E invalid transitions rejected | `test_scenario_e_invalid_transitions_rejected` | skips/reversals/artefact-free advances all 409 |
| F readiness blocks launch | `test_scenario_f_readiness_blocks_unready_business` | NOT_READY with dimension-B blockers; READY_FOR_LAUNCH refused |
| G workspace isolation | `test_scenario_g_cross_business_isolation` | probe denied; critical event persisted |
| H mode discipline | `test_scenario_h_modes_respected` | simulation: run cannot complete (BLOCKED); emergency: creation halted |
| I existing agents reused | `test_scenario_i_existing_agents_reused` | identical agent sets across two businesses (factory reuse-first) |
| J launch needs owner approval | `test_scenario_j_launch_requires_owner_approval` | pending/wrong approvals refused; owner approval → OPERATIONAL (local package only) |

## Unit/integration coverage highlights

Lifecycle transition table (incl. pause-returns-to-origin), template
validation (unknown/disabled tools, money keys, orphan assets),
financial values + the revenue-key rejection, redaction, the full
eligibility decision matrix, readiness precedence (BLOCKED > NOT_READY
> OWNER_REVIEW_REQUIRED > warnings > READY), the migration cycle
(18 tables; exact downgrade), settings governance, the complete HTTP
flow, duplicate-business conflict, and the P-07 payload arithmetic
(startup 15.0 / recurring 5.0 / price 19 from the fixture's P-03
commercial analysis).
