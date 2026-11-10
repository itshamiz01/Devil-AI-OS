# P-15 INCIDENT RESPONSE (§10)

## Severity scale

| Severity | Meaning | Examples in the register |
|---|---|---|
| P0 | Critical system or financial-integrity incident | Database connectivity failure; (gate conditions also include integrity-check and audit-chain failure) |
| P1 | Major service failure | Circuit breaker open on a dependency |
| P2 | Partial degradation | Resource threshold violation; operations dead letters open |
| P3 | Minor operational issue | No backups; stale backup; event dead letters on record |

P-10's *security* incidents keep their own register and severity
handling; P-15's register is reliability scope only and the two
never merge records.

## Lifecycle

`open → acknowledged → resolved`. Every incident records:
detection time, affected component, severity, root cause (on
resolution), immediate response, recovery actions, resolution
time (from timestamps) and preventive recommendations — the §10
field list maps one-to-one onto `reliability_incidents` columns.

## Response procedure

1. **Detect** — the evaluator (sampler cadence, or on demand from
   the Command Center) opens a deduplicated incident; P0/P1
   incidents also fail the readiness critical gate immediately.
2. **Acknowledge** — the owner acknowledges in the register
   (owner-gated), which starts the human response clock.
3. **Respond through the owning engine** — P-15 never reaches
   into another engine: database issues are operator/P-01 work,
   breaker issues are P-12 dependency work, backup posture is
   fixed by creating a verified backup (panel G), financial
   concerns go through P-07/P-10.
4. **Resolve with the record completed** — root cause, response,
   recovery actions and preventive notes are required fields of a
   good resolution; the API accepts them and the register keeps
   them permanently.
5. **Auto-resolution** applies only to auto-detected condition
   incidents (thresholds, breakers, backup posture, database
   connectivity) when the condition verifiably clears — the
   resolution entry says so and cites the cleared condition.
   Manual incidents always need a human resolution.

## Reporting

Incident counts by severity, recovery rate and the five most
recent incidents are in panel F; the full register is queryable
at `GET /reliability/incidents` with status/severity filters.
A formal incident *report document* is generated per phase (this
file + the readiness report's evidence), not per incident — with
the register as the durable record, a per-incident narrative is
the resolver's `response`/`preventive` fields.
