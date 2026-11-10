# P-18 Test Plan

## Suites (backend, `backend/tests/`)

| File | Covers |
|---|---|
| `test_p18_unit.py` (13) | pure scoring: priority floors/bands/breakdown, SLA states, metrics refusing missing data, health bands + insufficient-data refusal, KB matching thresholds, quality aggregation with missing dimensions |
| `test_p18_integration.py` (19) | engine status/authorities, onboarding (system default + business template + dedupe + dashboard), fulfilment flows/acceptance, SLA NOT_AVAILABLE → configured → breach, idempotent evaluation, ticket lifecycle/reopen, P-12 escalation, grounded assistant (draft doesn't ground; edit un-approves), high-impact review, communications (dedupe/consent/sensitive approval/no refund-promise kind), feedback→metrics→health, quality reviews, refund + goodwill resolutions through P-07, success task via P-12, customer 360, improvement insights, HTTP round trip |
| `test_p18_security.py` (7) | agent refusal on writes **and** customer reads, system-read/service-refusal split, cross-business invisibility (5 surfaces), foreign template refusal, refund approval-bypass impossibility, schema guards (no money columns; no second customer store), settings bounds, role capability audit |
| `test_p18_scenarios.py` (5) | full journeys: physical product, SaaS access recovery, education stall→assistance, complaint→refund→insight (portfolio rollup), nothing-is-sent honesty scenario |

P-18 tests: **44**. Seeding is governed-paths only
(`tests/p18_support.py`): P-06 fixture businesses, P-17
customers, P-07 verified revenue; time-based detection uses a
labelled test-only timestamp backdate helper — no sleeping.

## Cross-suite obligations

- Alembic head pins in P-02/P-03/P-04/P-05 suites and table
  counts in P-13/P-15/P-16 suites advanced to `218ddd92a0aa` /
  224 with P-18 disclosure comments (house pattern); no other
  earlier test modified.
- Migration cycle test: 209 → 224 → 209 → 224 physical tables.
- Full regression on final code: see the release readiness
  report for the recorded counts.

## Frontend

`Experience.test.tsx` (3): authorities + never-sent posture with
CSAT sample size; SLA NOT_AVAILABLE honesty on the Support tab;
metrics/health labelling (insufficient data shown, no sentiment
claims). Strict TypeScript build clean; full suite 52/52.

## Live smoke

`backend/scripts/p18_smoke.py`: real uvicorn, readiness-gated
login (attempts recorded — the P-17 boot-window observation),
27 checks over HTTP. Evidence:
`docs/reports/P18_SMOKE_EVIDENCE.txt`.

## QA review method (§9)

Quality reviews are manual sample reviews: a reviewer scores a
recorded ticket on any subset of the ten documented dimensions
(0–5); aggregation reports scored vs missing dimensions and is
never presented as customer satisfaction.
