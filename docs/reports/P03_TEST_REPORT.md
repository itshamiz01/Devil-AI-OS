# P-03 Test Report

- **Phase:** P-03 — Opportunity Discovery, Research and Analysis
- **Run date:** 2026-11-03 (UTC)
- **Command:** `python -m pytest -q --junitxml=…` from `backend/`
- **Result:** **504 passed, 0 failed, 0 errors, 0 skipped** in 323.17 s
- **Machine-readable evidence:** [`P03_TEST_RESULTS.xml`](P03_TEST_RESULTS.xml) — `tests="504" errors="0" failures="0" skipped="0"`
- **Environment:** Python 3.11.2, 2 CPUs, 3.85 GiB RAM, no swap, no GPU, SQLite 3.40.1

## 1. Suite composition

| Module | Tests | Phase |
|---|---|---|
| `test_decisions_context_security` | 84 | P-02 |
| `test_intelligence_api` | 65 | P-02 |
| **`test_opportunities_engine`** | **59** | **P-03** |
| `test_planning` | 50 | P-02 |
| `test_mission_interpreter` | 45 | P-02 |
| `test_model_router` | 35 | P-02 |
| `test_intelligence_orchestration` | 33 | P-02 |
| `test_intelligence_persistence` | 26 | P-02 |
| **`test_opportunities_api`** | **24** | **P-03** |
| **`test_opportunities_persistence`** | **16** | **P-03** |
| `test_backup_restore` | 13 | P-01 |
| `test_approval_task_release` | 11 | P-01 |
| `test_emergency_stop` | 11 | P-01 |
| `test_tasks_api` | 10 | P-01 |
| `test_auth_api` | 5 | P-01 |
| `test_config` | 4 | P-01 |
| `test_permissions_approvals` | 4 | P-01 |
| `test_unit_core` | 4 | P-01 |
| `test_events_monitoring` | 3 | P-01 |
| `test_recovery_events` | 2 | P-01 |
| **Total** | **504** | |

**P-03 contributes 99 tests.** P-02's 405 pass unchanged, so nothing in this phase
regressed an earlier one. There is no `pytest-asyncio` in the dependency set; async
code is driven with `asyncio.run()`.

## 2. What the three P-03 modules cover

### `test_opportunities_engine.py` — 59 tests, direct

The invariants behind the HTTP layer, exercised against the modules themselves.

* **Network egress.** `NetworkPolicy.host_permitted` allows an explicitly permitted
  host and a subdomain of it, never the parent; denies non-HTTP schemes and an empty
  host. `SourceRegistry.fetch` raises on an unknown source while `fetch_many` returns a
  per-source refusal, so one bad source cannot destroy a batch.
* **Evidence epistemics.** Model-generated evidence can never be `verified` or
  `corroborated`; a record with no `source_id` cannot rise above `tentative`;
  `corroborated` requires an `independence_group`; `contradicted` must name its target.
* **`RetrievedContent` refuses a non-`external` trust domain outright** — stronger than
  a coercion, and asserted as a `ValueError`.
* **Corroboration versus contradiction.** A \$19-versus-\$29 disagreement is never
  promoted, and `contradictions()` reports the pair. Two records from the same source
  do not corroborate.
* **Staleness** requires both `stale_after_days` and `collected_at`; aged records gain
  an auditable `marked outdated at …` note.
* **Commercial arithmetic.** The three scenarios' revenue and variable cost, monthly
  break-even as ceiling-rounded whole units over the recurring fixed cost, and startup
  payback including the recurring cost of the month it lands in.
* **Budget compatibility** reports a shortfall and never repairs it;
  `budget_was_modified` stays `False` and `available_capital` is unchanged.
* **Scoring** is deterministic across repeated runs, a hard rejection overrides a high
  score while the score is retained, and the 16-character weights fingerprint is stable.
* **Lifecycle** transitions return a new object, `discovered` cannot jump to
  `researching`, and terminal states can be archived but never resume active work.
* **`GovernanceGate.authorize` accepts no `autonomy_level` parameter at all** — the
  signature is inspected, so §26's prohibition is verified structural rather than
  configurable.

### `test_opportunities_api.py` — 24 tests, over HTTP

The §29 acceptance scenarios A–I driven through `TestClient` against a real principal
built with `PrincipalRepo`, `SessionRepo` and `token_hash`. Covers discovery with and
without inputs, source-access refusals, zero-evidence classification, prohibited
candidates, unaffordable candidates, report generation, ranking reproducibility,
governance counts, status, source registration, and the full permission matrix.

Two findings from this module are worth recording because they were **defects in the
product, not in the test**:

1. `GET /{id}` omitted `business_model` and `distribution`, so report sections E and G
   described data the API would not return. Both were added.
2. Section C renders its real `MarketAssessment` (verdict `insufficient data`, `no
   admissible demand evidence`, `could not be sized`) rather than the generic
   `NO_EVIDENCE_STATEMENT`; only a section with no assessment object at all falls back
   to the generic text. The test initially asserted the generic string everywhere and
   was wrong.

### `test_opportunities_persistence.py` — 16 tests

Own `migrated` fixture via `run_migrations_sync(settings)`. Asserts the twelve P-03
tables exist, the revision chain is `2a904ceb99c4 → 5953caf8f23e → 72ee9705e18f`,
decimal text round-trips byte-identically, foreign keys are enforceable, no credential
column exists, and — the test added after a real failure — **the migration is safe on a
populated database**.

## 3. How the 59 engine tests reached green

The first run was **39 passed / 20 failed**. Every one of the 20 failures was an
invented name in the test file, not a defect in the product:

| Invented | Real |
|---|---|
| `EvidenceType.MODEL_INFERENCE` | `EvidenceType.MODEL_GENERATED` |
| `NetworkPolicy.permits(url)` | `NetworkPolicy.host_permitted(url)` |
| `registry.fetch(…, query="q")` | `registry.fetch(…, params={"query": "q"})` |
| `ScenarioProjection.revenue` | `ScenarioProjection.projection.revenue` |
| `projection.variable_costs` | `projection.variable_cost` |
| `BreakEvenResult.reachable` / `.units` | `.achievable` / `.monthly_break_even_units` |
| `BudgetCompatibility.affordable` | `.compatible` |
| `outcome.score.weights_fingerprint` | `outcome.weights_fingerprint` |
| `store.corroborate` marks contradictions | `store.contradictions()` is a separate query |
| `authorize(action, autonomy_level=…)` | `authorize(action, *, detail=None)` |
| `HistoryEntry(opportunity_id=…)` | `entry_id` is required |
| `RetrievedContent(trust_domain=OWNER)` coerced | it is **refused** |

Each was corrected by introspecting `model_fields`, `Enum.__members__` and
`inspect.signature` before rewriting the assertion. **No assertion was weakened, and
two became stronger:** the `RetrievedContent` test now asserts a refusal rather than a
coercion, and the break-even test now pins three derived figures
(`monthly_break_even_units == 2`, `units_to_recover_startup == 7`,
`months_to_recover_startup == 4`) where it previously pinned one.

Three further failures were the test being wrong about the *domain*:

* Terminal states are not edge-free. They may be `archived`; what they may not do is
  resume active work. The test now asserts the real invariant.
* `discovered → researching` is illegal by design; screening is mandatory.
* A `CostItem` with `provenance=estimate` and no `assumption` is refused by a
  validator. The fixture now states the assumption.

## 4. Ad-hoc module smokes run during development

These are not in the suite; they were per-module assertion scripts run before
dependents were written.

| Module | Result |
|---|---|
| `commercial.py` | 68 assertions, 0 failures |
| `risk.py` | 57 / 0 |
| `scoring.py` | 58 / 0 |
| `validation.py` | 42 / 0 |
| `evidence.py` | 63 / 0 |
| `lifecycle.py` + `discovery.py` | 26 / 26 |
| `governance.py` | 40 / 40 (after a `.value`-versus-`.name` fix) |
| `analysis.py` | 73 assertions |
| §29 scenarios A–I | 29 / 29, then 20 / 20 over live HTTP |
| `EvidenceExtractor` | 15 / 15 |

## 5. Static audits

| Audit | Result |
|---|---|
| `scripts/audit_p03_persistence.py` | exit 0 — no invented ORM attribute, no unsupplied required field |
| `scripts/audit_config_docs.py` | OK — 54 settings fields / 54 documented / 47 `.env.example` keys / 1 inert |
| `app.opportunities.__all__` | 124 exports, **0 unresolvable** |
| `app.openapi()` | 53 paths / 58 operations, consistent with `shared/openapi-p03.json` |
| §26 surface scan | no path or summary contains any spending verb |

## 6. What is not tested, and why

* **No live network access is tested**, because none is available. `HttpSourceAdapter`
  is exercised through an injected transport. Whether it works against a real host is
  **not verified** and is labelled as such throughout.
* **No performance figure is reported.** No latency, throughput, memory or token
  measurement was taken, and none may be inferred from these timings — the 323 s
  total is wall-clock on a 2-CPU sandbox running 504 tests, not a benchmark.
* **No model-generated evidence exists anywhere in the suite.** Every fixture is
  `deterministic_rule` or an explicit `TEST FIXTURE` record.
