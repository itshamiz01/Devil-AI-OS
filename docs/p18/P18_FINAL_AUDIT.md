# P-18 Final Audit

Build: P-18 Customer Experience, Service Delivery & Customer
Success Engine, on the verified P-17 stack, under the owner's
standing one-by-one instruction (P-15 → P-16 → P-17 → P-18).
P-18 is the last phase of that run; the STOP rule was honoured
— no Expansion Pack work was started.

## Architecture-stage decisions (P-14 style, recorded first)

D1 package `app/experience/` with `ExperienceService` composed
of four mixins + pure `scoring.py`; `Cx*` model prefix (the
P-06 schema guard owns `Business*`). D2 no money columns and no
stored amounts — amounts are owner-supplied at execution and
pass straight into P-07. D3 SLA targets owner-configured or
absent; evaluation is a deterministic on-demand pass, no new
scheduler. D4 the support assistant is deterministic and
extractive over APPROVED articles only — no LLM is faked
(DEF-A2 stands). D5 health is a service-health classification
from recorded signals with persisted factors/evidence, never a
churn prediction. D6 metrics computed live with sample sizes or
INSUFFICIENT_DATA/NOT_AVAILABLE. D7 autonomy levels 0–3 in
settings (default 1); writes owner-gated, customer reads
owner/system-only. D8 escalations are P-12 DRAFT workflows,
idempotency-keyed per ticket+level.

## Defects found and fixed during the build

1. Route `/experience/agent-roles` called the service without
   its principal argument (HTTP 500 in the live smoke's first
   run; in-process tests called the service directly and so did
   not catch it). Fixed; the smoke's end-to-end HTTP coverage is
   what caught it — recorded here as the reason the live smoke
   is a gate, not a formality.
2. Refund execution passed a `date` object where P-07's ledger
   expects an ISO string; fixed to `date.today().isoformat()`.
3. Metrics mixed naive DB datetimes with aware parsed times
   (TypeError on subtraction); all timestamps now normalised
   through `scoring.parse_time`.

## Verification

- Backend: 44 new P-18 tests (unit 13, integration 19,
  security 7, scenarios 5). Full regression on final code: see
  P18_RELEASE_READINESS_REPORT.md for the recorded totals.
- Migration cycle: 209 → 224 → 209 → 224 physical tables;
  head `218ddd92a0aa`.
- Frontend: 52/52 with clean strict TypeScript build.
- Live smoke: 27/27 over real uvicorn (evidence:
  docs/reports/P18_SMOKE_EVIDENCE.txt). Login succeeded on
  attempt 1 behind the /health/ready gate; the P-17 boot-window
  observation did not recur in this run but the gate and the
  patient-retry loop remain in the smoke.

## Honest limitations

- No support channel, logistics, delivery, scheduling or survey
  integration is connected (all `not_configured`); communications
  queue and are blocked at dispatch; fulfilment states are
  operator-recorded with source labels.
- No real LLM has ever been exercised (DEF-A2): the assistant
  is keyword-grounded and extractive by design.
- Windows remains UNVERIFIED (DEF-A1); all verification ran in
  this Linux staging cell.
- Health weights, stall thresholds and frequency limits are
  owner-governed defaults, never calibrated against a real
  business (DEF-A8); all smoke/test data are labelled fixtures.
- Classification remains **READY FOR CONTROLLED PILOT** —
  production stays barred while DEF-A1/DEF-A2 stand.
