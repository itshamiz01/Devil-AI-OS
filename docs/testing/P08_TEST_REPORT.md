# P-08 Test Report (§28.23 / §31 items 24–25)

Run environment: Linux staging sandbox, SQLite, Python 3.12,
`.venv` in `backend/`. All figures below are from runs actually
executed in this environment on 9 Nov 2026.

## Final full-suite result

**450 passed, 0 failed, 0 errors in 266.65 s — one run:**
404 P-01–P-07 regression + 46 new P-08 tests.

| Category | File | Count |
|---|---|---|
| P-08 unit | `tests/test_p08_unit.py` | 12 |
| P-08 scenarios (§26.4, all 15) | `tests/test_p08_scenarios.py` | 15 |
| P-08 integration | `tests/test_p08_integration.py` | 6 |
| P-08 security (§26.3) | `tests/test_p08_security.py` | 13 |
| **New total** | | **46** |
| Regression (P-01–P-07) | all other test files | 404 |
| **Suite total** | | **450** |

Baseline before P-08 code: 404 passed (re-run at Stage 1). The
four P-08 files standalone: 46 passed.

## Real-uvicorn smoke

`backend/scripts/p08_smoke.py` — **34 passed, 0 failed**
(transcript: `docs/reports/P08_SMOKE_EVIDENCE.txt`). Order:
HONESTY CHECK FIRST (a staging fixture business as it actually
exists → INSUFFICIENT_DATA, scaling NOT_READY stage 0, allocation
0/BLOCKED), then S1, S2, S4, S5 (readiness READY with 11 satisfied
conditions; ₹10,000 → ₹50,000 refused in strict mode; non-strict
plan clamped to exactly ₹15,000; owner approval; the P-07 budget
itself verified unchanged), S7 (platform dependency named), S9
(closure refused before OWNER_APPROVAL; owner flow → CLOSED; P-06
business ARCHIVED; history preserved), S12 (protected-reserve
allocation BLOCKED; ₹5,000 reserve verified intact), S15 (pause →
decision execution HTTP 403; history readable; security-incident
gate present; owner resume → ACTIVE). All smoke financial history
was seeded exclusively through P-07's authorised paths (signed
fake-provider webhooks for verified revenue; HTTP API for
profiles/balances/expenses/budgets) — never by writing ledger rows.

## §26.4 scenario mapping (tests/test_p08_scenarios.py)

S1 growth-without-profit → deterioration flag + cost investigation
decision + scaling NOT_READY · S2 vanity metrics → NOT validated,
NOT scaling-ready · S3 validated experiment within budget, no
open-ended spend · S4 stop-loss (max loss) blocks further spend ·
S5 ready business → READY + incremental plan + approval enforced ·
S6 profitable-but-illiquid → liquidity blocked from P-07 available
cash vs obligations · S7 platform concentration named · S8
declining business → finite recovery plan, conclude-once · S9
unviable → closure review with inventory, owner flow required ·
S10 three businesses → risk-adjusted proposals, totals ≤ available,
P-07 budgets untouched · S11 ten-agent request → measure first,
0 new agents without workload · S12 protected reserves → BLOCKED ·
S13 unresolved reconciliation → confidence reduced, scaling BLOCKED ·
S14 forecast vs actual decline → error against the FROZEN forecast ·
S15 emergency pause → execution blocked, records preserved.

## §26.3 security mapping

See `docs/security/P08_SURVIVAL_SECURITY.md` — all items are real,
named tests in `tests/test_p08_security.py` (plus unit-level
idempotency and structural proofs).

## Structural proofs (in the unit file)

- No `float(`, no journal/ledger access anywhere in
  `backend/app/survival/*.py` (P-07 is the only financial source).
- No revenue/profit/collected columns on any P-08 model.
- No protected-reserve mutation path in the survival package.

## Migration cycle (integration)

90 → 108 → 90 → 108 tables (counting `alembic_version`; 89 → 107
excluding it) with the head pinned at `99902c03a197`.

## Disclosed changes to pre-existing tests (strictness preserved)

1. Migration-head pins `c3b5cdba2559` → `99902c03a197` in eight
   assertion sites across `test_p02_integration.py`,
   `test_p03_integration.py`, `test_p04_integration.py`,
   `test_p05_integration.py`, `test_p06_integration.py` — each with
   a `# P-08 disclosure` comment (standing precedent from P-03–P-07).
2. `test_p07_integration.py::test_p07_migration_cycle` retargeted
   from `"head"` to the P-07 head `c3b5cdba2559` explicitly (its
   63→90→63→90 assertions unchanged) — required because P-08 adds
   tables above that head.
3. `test_p06_integration.py::test_p06_migration_cycle` retargeted
   from `"head"` to the P-06 head `a8d7e0c717b4` explicitly and its
   two version pins reverted to that head, because P-08's nine new
   `business_*` tables broke its naive table-prefix count
   (`len(business_tables) == 18`). P-06's own assertions are
   unchanged in kind and strictness.

## Environment incident (disclosed, not a code result)

Two full-suite attempts during verification reported 378 passed /
1 failed / 71 errors. Root cause was environmental, not code:
this VM's `/tmp` is a 512 MB tmpfs and a single full run's pytest
temp dirs fill it (~511 MB), producing `database or disk is full`
fixture errors. The one genuine failure in those runs (the P-06
migration-cycle count above) was fixed properly. The final run
used the tmpfs basetemp with a background pruner deleting test
dirs older than 90 s (finished tests only), holding `/tmp` at
~45 %, and completed 450/450 in one run. A disk-backed basetemp
was measured and rejected: very high SQLite fsync latency on this
VM (~11 min for 16 % of the suite).
