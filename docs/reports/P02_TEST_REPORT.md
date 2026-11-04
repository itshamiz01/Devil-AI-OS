# P-02 Test Report — Master Intelligence Engine

- **Phase:** P-02
- **Date:** 2026-11-03
- **Branch:** `arena/0a4e9e66-devil-ai-os`
- **Evidence file:** [`P02_TEST_RESULTS.xml`](P02_TEST_RESULTS.xml) (JUnit, generated this run)
- **Interpreter:** Python 3.11.2 (CPython), virtual environment rebuilt for this run at `/tmp/venv-p00`

## 1. Headline result

```
405 passed, 0 failed, 0 errors, 0 skipped in 266.936s
```

Read from the JUnit `<testsuite>` element, not counted by hand:
`tests="405" failures="0" errors="0" skipped="0" time="266.936"`.

There are **377 test functions**; the suite reports 405 test cases because parametrised tests expand into one case per parameter. Both numbers are given so neither can be mistaken for the other.

The environment is ephemeral and has no lockfile. These results are reproducible by rebuilding the virtual environment from `backend/requirements.txt` (12 pinned packages) and running `pytest` from `backend/`. They are **not** reproducible from the repository alone without that step — this is pre-existing decision `D-12`, unchanged by P-02.

## 2. Suite composition

| File | Test functions | Area (§19) | New in P-02 |
|---|---:|---|---|
| `test_decisions_context_security.py` | 72 | §19.4 decisions, §19.6 context security, §13 output, §8 reasoning | Yes |
| `test_intelligence_api.py` | 54 | §19.7 end to end, §14 API, §20 scenarios A–G | Yes |
| `test_planning.py` | 50 | §19.3 planning | Yes |
| `test_mission_interpreter.py` | 45 | §19.2 interpretation | Yes |
| `test_model_router.py` | 35 | §19.1 routing | Yes |
| `test_intelligence_orchestration.py` | 28 | §19.5 orchestration | Yes |
| `test_intelligence_persistence.py` | 26 | §17 persistence, §19.5 recovery | Yes |
| **P-02 subtotal** | **310** | | |
| `test_backup_restore.py` | 13 | P-01 | No |
| `test_approval_task_release.py` | 11 | P-01 | No |
| `test_emergency_stop.py` | 11 | P-01 | No |
| `test_tasks_api.py` | 10 | P-01 | No |
| `test_auth_api.py` | 5 | P-01 | No |
| `test_config.py` | 4 | P-01 | No |
| `test_permissions_approvals.py` | 4 | P-01 | No |
| `test_unit_core.py` | 4 | P-01 | No |
| `test_events_monitoring.py` | 3 | P-01 | No |
| `test_recovery_events.py` | 2 | P-01 | No |
| **P-01 subtotal** | **67** | | |
| **Total** | **377** | | |

## 3. Regression position

The 67 P-01 test functions all still pass. P-02 modified five files shared with P-01 — `core/config.py`, `core/application.py`, `permissions/policies.py`, `events/events.py` and `database/models.py` — and every one of those edits is additive. A full-suite run was executed immediately after the shared-file edits and again after the persistence wiring; both were green.

No assertion was weakened, deleted or skipped to obtain a passing suite. `skipped="0"` in the JUnit evidence.

One test was deliberately **un-skipped** during this phase. `test_advisory_level_approves_but_dispatches_nothing` originally skipped when a plan did not require approval, because the approve route refused any state other than `AWAITING_APPROVAL`. The route was fixed to accept `PLANNING` as well, the skip was removed, and the test now asserts both that `dispatched == []` and that the P-01 task list is empty.

## 4. §20 acceptance scenarios

All seven scenarios are exercised through the real HTTP API against the real Core OS — real task manager, real permission engine, real database. Only the inference provider is absent, because this machine genuinely has none; that absence is itself what Scenarios A and E assert.

| Scenario | Test | Result |
|---|---|---|
| A — simple conversation | `test_scenario_a_*` (2) | Pass. No mission created; honest unavailability |
| B — planning request | `test_scenario_b_*` (4) | Pass. 5-step plan; nothing launched; no task row created |
| C — complex $50 mission | `test_scenario_c_*` (4) | Pass. Budget extracted as `owner_stated`; capabilities identified; no research claimed |
| D — prohibited action | `test_scenario_d_*` (4) + `test_a_polite_financial_request_is_still_gated` | Pass. Blocked, `policy_unchanged=True`, no mission, no task, security event raised |
| E — local model unavailable | `test_scenario_e_*` (3) | Pass. Limitation reported; no paid fallback; no cloud model present |
| F — failed execution | `test_a_failed_step_blocks_every_dependent`, `test_a_failed_mission_is_never_reported_completed`, `test_a_full_round_trip_failure_is_visible_through_the_api`, `test_a_mission_can_be_recovered_by_replanning_after_a_failure` | Pass. Dependents blocked transitively; mission never `COMPLETED`; replanning recovers |
| G — prompt injection | `test_scenario_g_*` (5) | Pass. Analysed as data; findings reported; no secret disclosed; event published |

Scenario D is additionally tested with **polite** phrasing (`"Please transfer $40 of the budget to the supplier account."`), so refusal does not depend on hostile wording alone.

## 5. Mock providers

Per §19.1, deterministic tests use mock providers. They appear **only** in `backend/tests/`. No mock, stub or fake provider exists anywhere in `backend/app/`; the production default is `NoRuntimeProvider`, which reports unavailability rather than simulating a model.

## 6. What is NOT verified by these tests

Stated explicitly, because §24 forbids marking an item complete without evidence:

| Item | Status | Reason |
|---|---|---|
| `OllamaProvider` against a live Ollama server | **NOT VERIFIED** | No runtime installed; `ollama.com` unreachable from this host |
| Local model latency | **NOT MEASURED** | No model could be run; no figure is reported anywhere |
| Local model memory consumption | **NOT MEASURED** | As above |
| Token throughput | **NOT MEASURED** | As above |
| Quality of model-generated interpretation enrichment | **NOT VERIFIED** | Requires a real model; the code path is tested only with mocks |
| Windows behaviour | **NOT VERIFIED** | Development host is Linux; P-02 is backend-only |
| Concurrent multi-mission load | **NOT VERIFIED** | Bounds are unit-tested; no load test was run |

See [`P02_MODEL_AVAILABILITY_REPORT.md`](P02_MODEL_AVAILABILITY_REPORT.md) for the hardware evidence behind the first four.

## 7. Defects found by these tests

Every one of the following was found by a failing test and fixed in the implementation. None was resolved by weakening an assertion.

| Defect | Found by | Fix |
|---|---|---|
| `DEFAULT_WEIGHTS` used the key `expected_benefit` while the field is `estimated_benefit`; `getattr` returned `None` and **benefit contributed nothing to any score in the system**, silently | `test_scoring_is_transparent_about_its_contributions` | Renamed the criterion and added a construction guard validating every weight name against `DecisionOption.model_fields` |
| A money-moving instruction with no stated amount scored `HIGH` instead of `CRITICAL`, inverting the risk | `test_money_plus_an_action_verb_is_critical_risk` | Added a financial-action rule that does not require a numeric amount |
| `Replanner.revise` re-executed completed steps unless the caller passed `completed_step_ids` | `test_completed_steps_are_not_re_executed_after_a_revision` | Derive the completed set from the previous plan when the argument is omitted |
| `assess_failure` resolved dependents from stale step states, under-reporting the blast radius | `test_a_failure_recommends_replanning_when_dependents_are_stuck` | Project the assessed step's failure before resolving dependents |
| An illegal mission transition surfaced as an unhandled `500` | `test_a_cancelled_mission_cannot_be_reopened` | `_transition` helper converts `ValueError` into `409 Conflict` |
| A plan requiring no approval could not be authorized or executed through the API at all | `test_an_approved_plan_dispatches_through_the_p01_task_manager` | Approve accepts `PLANNING` as well as `AWAITING_APPROVAL` |
| `factory` assigned `router.usage_listener` after construction, but the router reads `self._usage_listener` set only from the constructor — usage would never have been persisted | `test_the_factory_wires_a_usage_listener` | Pass the listener to the `ModelRouter` constructor |
| `Mission.available_resources` and `Mission.dependencies` had no columns, so a persist/reload round trip silently dropped them | `test_available_resources_and_dependencies_are_not_lost` | Added both columns to the ORM and to the (still uncommitted) P-02 migration |

## 8. Reproducing

```bash
python3 -m venv /tmp/venv-p02
/tmp/venv-p02/bin/pip install -r backend/requirements.txt
cd backend && /tmp/venv-p02/bin/python -m pytest -q
```

Do not point `--junitxml` at an existing tracked evidence file; it overwrites without warning.
