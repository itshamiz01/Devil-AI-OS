# P-18 Release Readiness Report

## Verdict

**READY FOR CONTROLLED PILOT** — unchanged from P-14→P-17.
Production remains barred while DEF-A1 (Windows UNVERIFIED)
and DEF-A2 (no real LLM exercised) stand; both are owner-side
items, not staging defects.

## Verification evidence (final code)

| Check | Result |
|---|---|
| Backend full regression | **953 passed / 0 failed** (909 P-17 baseline + 44 new P-18 tests), run in 14 chunks over a C-locale-sorted file list with per-chunk tmpfs basetemps — the 512 MB /tmp tmpfs cannot hold a single full run (two oversized attempts failed on disk-full fixture errors and were diagnosed as environment, not code; the one genuine failure found en route — stale 208 metadata pins in six earlier suites — was fixed with P-18 disclosures and its chunk re-run green) |
| P-18 suites | unit 13 · integration 19 · security 7 · scenarios 5 |
| Frontend | **52/52** (49 baseline + 3 new), strict TypeScript build clean |
| Live smoke | **27/27** over real uvicorn (`docs/reports/P18_SMOKE_EVIDENCE.txt`); login attempt 1 behind the /health/ready gate |
| Migration cycle | 209 → 224 → 209 → 224 physical tables; head `218ddd92a0aa`; 223 metadata tables (208 + 15 cx) |
| OpenAPI surface | 642 paths (589 + 53 experience routes) |

## What shipped

`app/experience/` (ExperienceService, four mixins, pure
scoring), 15 additive `cx_` tables, 53 `/experience/*` routes,
the Command Center "Customer Experience" section (7 tabs), the
10 §14 roles as P-04 templates, 10 documents under `docs/p18/`.

## Authority invariants (tested, not just claimed)

- Customers: P-17's `crm_customers` only — no second store
  (schema guard), cross-business customers invisible.
- Money: P-07 only — no money columns in any `cx_` table
  (schema guard); refunds execute solely as P-07 refunds
  against verified revenue after hash-bound owner approval;
  goodwill solely as P-07 spending requests.
- Workflows/scheduling: P-12/P-01 — escalations and follow-ups
  are P-12 DRAFT workflows; detection is an on-demand pass.
- Memory: P-09 — verified resolution patterns fed via
  ingestion, best-effort.
- Gate: P-16's profitability gate untouched; Article 0 held —
  no governance/safety/financial-authority code modified.

## Honest limitations

- No external channel connected (inbox, chat, messaging,
  logistics, delivery, scheduling, surveys, transport): all
  `not_configured`; communications never sent; fulfilment
  states operator-recorded with source labels.
- The support assistant is deterministic/extractive (no LLM —
  DEF-A2); Windows unverified (DEF-A1); thresholds and health
  weights are owner-governed defaults never calibrated on a
  real business (DEF-A8); all verification data are labelled
  fixtures.

## Standing owner items (unchanged by this phase)

P-00 Windows evidence + repo creation; a real pilot business
run; the ClipOS pilot boot + Google OAuth. P-18 was the last
phase of the one-by-one run — the Post-Completion Expansion
Pack starts only with its own readiness review (Gate 2) and
per-feature owner approval.
