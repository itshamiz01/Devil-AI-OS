# P-09 Test Report

**Final full run (one run, final code, tmpfs basetemp + pruner):**
**509 passed, 0 failed** in 344.85 s — the 450-test P-01–P-08
regression suite intact plus **59 new P-09 tests**:

| File | Tests | Covers |
|---|---|---|
| `tests/test_p09_unit.py` | 21 | §25.1 units + §22.3 retrieval evaluation |
| `tests/test_p09_scenarios.py` | 17 | all §25.4 acceptance scenarios, real named tests |
| `tests/test_p09_security.py` | 11 | §25.3 security suite |
| `tests/test_p09_integration.py` | 10 | §25.2 integration incl. migration cycle |

Plus a live-uvicorn smoke (`backend/scripts/p09_smoke.py`):
**30 passed, 0 failed** — transcript in
`docs/reports/P09_SMOKE_EVIDENCE.txt`, opening with the honesty
check (empty staging memory: zero records, local vector adapter
truthfully labelled, no LLM dependency).

## §22.3 retrieval evaluation (measured, not claimed)

Labelled mini-corpus (6 records, 4 judged queries) evaluated through
the real retrieval path in `test_retrieval_evaluation_measured`:
**recall@3 = 1.000, precision@1 = 1.000**. This is a small
deterministic check on the local hash embedder — it proves the
pipeline ranks judged-relevant records first on this corpus; it is
**not** a production retrieval benchmark and no broader quality is
claimed. No learning-improvement claim is made anywhere: the
confidence ceiling is mechanical and the evaluation measures
retrieval only.

## Scenario outcomes (§25.4)

All 17 pass, including: memory poisoning refused at three surfaces
(agent truth/category escalation, governance-claim ingestion, and
retrieved poison changing nothing); secret-bearing agent output
rejected with a value-free security event; single-observation
learning capped at LOW and never VERIFIED; deletion reported
complete only after index sync verified; vector-store loss degrading
to keyword search with records intact; LLM absence being a
non-event by construction; cross-business and cross-agent isolation;
contradictions preserving both records with the verified newer one
prioritised.

## Disclosed pre-existing test changes

Five earlier files were touched; every change preserves strictness
and carries a "P-09 disclosure" comment (details in
`docs/audits/P09_IMPLEMENTATION_REPORT.md`): migration head pins
advanced `99902c03a197` → `7b13db7e9bfa` (P-02–P-05 integration), the
P-08 migration cycle retargeted from `"head"` to the explicit P-08
revision, the P-04 unsupported-capability example switched from
`memory_write` (now genuinely backed) to `external_communication`,
one P-04 deferred-scope assertion updated now that P-09 serves it,
and one P-05 supported-flag assertion updated for the same flip.

## Environment note

The full run used the P-08-proven method for this VM's 512 MB /tmp
tmpfs (start empty + a pruner deleting finished tests' temp dirs).
An early baseline attempt was discarded as contaminated (mid-edit
files + /tmp exhaustion) and is not cited anywhere.
