# P-04 Test Report

Final full-suite run (one run, staging, 2026-11-09):
**230 passed, 0 failed, 0 skipped** in 63.11s — 172 pre-existing
(P-01/P-02/P-03 regression) + 58 new P-04 tests. One warning: the
pre-existing Starlette TestClient deprecation warning (present since
P-01).

## New P-04 tests by category

| File | Category | Count |
|---|---|---|
| `tests/test_p04_unit.py` | unit (lifecycle graph, template validation, versioning/pinning, creation-decision matrix, capability levels, config history/rollback, scaling policy, backpressure ladder, hardware defaults) | 24 |
| `tests/test_p04_integration.py` | integration (migration cycle + legacy-row preservation, API creation/reuse, assignment via real task engine, output contract, delegation, shared router, P-03 linkage, emergency stop, audit trail, idempotency, settings endpoint) | 14 |
| `tests/test_p04_security.py` | security — the ten §22.3 tests plus two supporting tests | 12 |
| `tests/test_p04_resources.py` | resource (§22.4: fleet ceiling, per-agent concurrency, inference gate, single router, pressure ladder, idle suspension, failed-init cap) | 8 |
| **Total new** | | **58** |

## §22.5 acceptance scenarios A–J → evidence

| Scenario | Test(s) | Smoke |
|---|---|---|
| A — Create a Research Agent | `test_p04_integration.py::test_scenario_a_create_research_agent_via_api` | ✅ A |
| B — Reuse an Existing Agent | `test_p04_integration.py::test_scenario_b_reuse_existing_agent` | ✅ B |
| C — New Capability Request | `test_p04_unit.py::test_capability_level_rules`; `test_p04_security.py::test_01_*` | ✅ C |
| D — Excessive Agent Creation | `test_p04_resources.py::test_max_agent_count_enforced` | ✅ D |
| E — Resource Pressure | `test_p04_resources.py::test_resource_pressure_blocks_nonessential_creation`, `::test_resource_pressure_queues_low_priority_assignments`; `test_p04_unit.py::test_backpressure_ladder_actions` | — (resources endpoint shown live) |
| F — Failed Agent | `test_p04_resources.py::test_failed_initialization_cap_prevents_endless_replacements` | — |
| G — Prompt Injection | `test_p04_security.py::test_05_prompt_change_cannot_bypass_approval`, `::test_09_external_content_cannot_override_policy` | — |
| H — Emergency Stop | `test_p04_integration.py::test_scenario_h_emergency_stop_via_api` | ✅ H |
| I — Agent Retirement | `test_p04_security.py::test_10_retired_agent_cannot_receive_tasks` | ✅ I |
| J — Shared Model Infrastructure | `test_p04_integration.py::test_shared_router_inference_uses_single_router`; `test_p04_resources.py::test_single_shared_router_no_duplicate_instances`, `::test_model_concurrency_limit_enforced` | — |

Smoke transcript: `docs/reports/P04_SMOKE_EVIDENCE.txt` (real uvicorn,
supervised mode, fresh DB; Scenarios A, B, C, D, H, I + a live
assignment with output-contract verification).

## Disclosed changes to pre-existing tests (3, strictness preserved)

1. `tests/test_p02_integration.py` — migration-head assertion
   `a8ddb3e7260d` → `a694abea811f` (exact-head strictness unchanged;
   legitimate additive migration).
2. `tests/test_p03_integration.py` — same head-assertion update, same
   reason.
3. `tests/test_integration_api.py::test_agents_endpoints_are_read_only`
   — P-01's phase-boundary assertion (POST /agents → 404/405) is
   deliberately superseded by P-04 §19, which *requires* a governed
   POST /agents. The test now asserts POST with an empty body → 422,
   unauthenticated POST → 401, and keeps all original GET assertions.
   Renamed in place with an explanatory comment.

No other pre-existing test was modified. No assertion was weakened.

## Defects found and fixed during the build

1. **Backpressure vs environment:** the sandbox VM's genuine memory
   pressure (>90% threshold) queued every nonessential creation.
   Root-caused to the factory reading raw monitor violations instead
   of P-01's admission semantics; fixed by honouring
   `block_nonessential_on_threshold` exactly as
   `SystemMonitor.admission_block_reason` does (pressure still always
   reported). See `AGENT_RESOURCE_MANAGEMENT.md`.
2. Migration autogeneration emitted `configuration_version` without a
   server default (SQLite batch-copy NOT NULL failure with existing
   rows) — hand-fixed with `server_default=1`; legacy-row preservation
   through the full cycle is test-covered.
3. `AgentRepository` (P-01) has no `save()`; three factory call sites
   corrected to the session commit pattern.
4. Config overrides shallow-replaced nested sections (a partial
   `resource_budget` override failed validation); overrides now
   deep-merge and the merged result is re-validated.
5. Owner-approved creations did not grant the approved Level-2
   capabilities at materialization; the hash-bound approval's
   capability set is now passed as the grant basis with the approval
   recorded as the grant reference.

## Known warnings

- Starlette TestClient deprecation warning (pre-existing, 1).
- No tests were skipped; no test was marked xfail.
