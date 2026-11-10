# P-17 — Test Plan (§28)

## Suites

| Suite | File | Tests | Covers |
|---|---|---:|---|
| Unit | `tests/test_p17_unit.py` | 10 | Pure scoring mathematics: ICP/channel weighted scores with missing-factor honesty, lead bands, CAC INSUFFICIENT_DATA discipline, LTV actual/projected split, retention/churn formulas, funnel bottleneck noise floor, A/B minimum-evaluation discipline, explained customer health, closed catalogues |
| Integration | `tests/test_p17_integration.py` | 17 | Governed flows: template seeding + honest integrations, intelligence scoring, gate-blocked expansion strategy + override, improve approval under a closed gate, campaign spend through P-07 with attribution, ceiling refusal, content workflow + mechanical brand block, lead dedupe/consent/suppression, deceptive-template refusal, CRM conversion + P-07 purchases + LTV + health, funnel declared-vs-system, SEO source honesty, experiment pre-declaration + P-08 handoff + insufficient-data conclusion, attribution methods, auto-pause below level 4, recommendation ordering, HTTP surface + auth |
| Security | `tests/test_p17_security.py` | 7 | No money columns in any P-17 table; P-07 books byte-equal after P-17 writes; cross-business isolation (leads, suppression, templates); agent refusal; emergency controls bite; frequency cap; unknown consent never messaged |
| Scenarios | `tests/test_p17_scenarios.py` | 2 | Full acquisition lifecycle end-to-end on a profitable fixture business; partnership referral attribution |
| Frontend | `frontend/src/views/Growth.test.tsx` | 3 | Gate rendered first with reason; P-07 spend + ATTRIBUTED revenue rendered as labelled; honest integration states |

**P-17 total: 36 backend + 3 frontend tests.**

## Regression method

The full backend suite (909 tests on final code = 873 baseline +
36 new) was run in two halves over a C-locale-sorted file list
with a tmpfs basetemp plus a file-activity pruner, because this
VM's /tmp is a 512 MB tmpfs that fills during single full runs
(the standing P-15/P-16 lesson). First half 466 passed, second
half 443 passed, **0 failed**; static collection is 909, matching
exactly. (An unattributed "484 passed" delivery arrived during
the run window from a stale background process; it matched no
invocation of this build and was not used — both halves' figures
above come from their identified runs and agree with their own
collections.)

Earlier-phase pins updated with P-17 disclosure comments (the
P-15/P-16 precedent): physical table count 191 → 209 and metadata
190 → 208 in the P-11…P-16 suites; alembic head pins advanced to
`afe062122eb5` in the P-02…P-05 suites. Strictness preserved
(exact counts).

## Migration cycle

Verified on a scratch database before the build proceeded:
upgrade 191 → 209 → downgrade 191 → upgrade 209 physical tables
(metadata 190 → 208). The P-13/P-15/P-16 cycle tests re-verify the
head on final code.

## Live smoke

`backend/scripts/p17_smoke.py` — real uvicorn boot on a governed
fixture seed; transcript at `docs/reports/P17_SMOKE_EVIDENCE.txt`.
