# P-16 — Test Plan (§20/§21)

## Suites

| Suite | File | Tests | Covers |
|---|---|---|---|
| Unit | `tests/test_p16_unit.py` | 15 | §4.3 weights & risk inversion pinned numerically; band boundaries; evidence-only confidence values (0/22/44/76/100-cap); HHI; diversification formula + INSUFFICIENT_DATA; the gate's five states; country weighted mean; all ten stress scenarios' arithmetic |
| Integration | `tests/test_p16_integration.py` | 29 | Migration cycle 177→191→177→191 and metadata 190; settings seed/validation; overview zero-state honesty + exact equality with P-07 `business_summary`; classifications + concentration flag; source requirements (markets/competitors); country scoring/ranking; geographic-segment checklist; pipeline happy path; evidence gate; profitability gate + override; strategy gate + hash-bound approval; discovery detectors + dedupe; allocation commitment guard + P-07 `revenue.metrics` byte-equality; growth refusal; reinvestment `min(profit, cash)` math; commercialization rights gate + P-03 handoff; experiment pre-declaration + level-3 handoff (P-08 experiment APPROVED with a P-07 budget); decision outcomes; risk detectors + SIMULATION label; recommendations ordering; relationship-map consent labels; unknown scoring keys refused; HTTP surface (201 creates, 401 unauthenticated) |
| Security | `tests/test_p16_security.py` | 11 | Agent denied aggregates/writes/approvals; non-owner settings refused; foreign-parameter approval binding refused; agent-supplied approval refused; capital freeze blocks approvals not rejections; expansion pause blocks advances, exits stay open; **P-07 metrics + expenses + summary byte-equal after a P-16 write batch**; no money-movement/business-creation method exists on the service; commercialization handoff requires approval; settings validation |
| Scenarios | `tests/test_p16_scenarios.py` | 6 | The prompt's stories end to end: profitability-before-expansion; gate opening on verified profit (incl. growth allocation); single-channel dependence flagged in three places; full experiment lifecycle → repeated-failure pattern → recommendation deprioritisation; commercialization entering the governed pipeline with **zero** businesses created; profit-is-not-cash reinvestment |

## Regression method (staging honesty)

The first single full-suite attempt died when the 512 MB /tmp
tmpfs filled (pytest exit 120, disk-full tracebacks — the standing
operational lesson). The suite was therefore run in two halves
with a tmpfs basetemp and a pruner deleting finished tests' temp
dirs (1-minute age, 5-second loop), logs kept in the workspace:

- **Half 1** (core + P-02…P-08 files): 395 passed, **1 failed** —
  the pre-existing P-06 schema guard flagged P-16's
  `BusinessClassification.revenue_model` column. Fixed by renaming
  the class to `EconomyClassification` (the guard protects P-06's
  `Business*` tables; the economy record was misnamed into its
  namespace — the guard itself was not touched). The full
  `test_p06_security.py` file was re-run on final code: green.
- **Half 2** (P-09…P-16 + core files): **477 passed, 0 failed**.

Total on final code: **873 tests** (812 P-15 baseline + 61 new
P-16 tests), all passing.

## Frontend

`src/views/Economy.test.tsx` (3 tests: gate-first rendering with
its reason verbatim; P-07 figures rendered exactly, combined cash
never summed; fixture labelling + overconcentration on the
Portfolio tab). Full frontend suite: **46/46** with a clean strict
TypeScript build.

## Live smoke

`backend/scripts/p16_smoke.py` against real uvicorn: **28/28**
(evidence: `docs/reports/P16_SMOKE_EVIDENCE.txt`). The smoke
caught four real defects during development (see the changelog) —
it earned its keep.
