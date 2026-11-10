# Audit and Monitoring (P-10)

## One trail: P-01 `audit_events`

P-10 writes every governance decision to the existing trail
(permission checks, policy updates, capability lifecycle,
emergency transitions, secret access, guard blocks, financial
guard decisions, backup operations). There is no second log.
The audit API is **read-only** — no create/update/delete route
exists (verified in tests, Scenario 18).

## Hash chain (tamper-evidence)

`audit_chain.py` seals the trail incrementally: each seal links
new events (in canonical `(created_at, id)` order) with
`SHA-256(previous_head || event canonical form)` into
`security_audit_chain`. `verify` recomputes from genesis and
reports the first mismatch or missing event.

**Honest scope:** the chain makes edits and deletions
*detectable* by anyone who verifies against a head they trust.
On a single host, an attacker who can rewrite the database can
also rewrite the chain — the chain's value is detection of
accidental corruption, partial tampering, and silent in-app
mutation (the app's own code paths cannot alter a sealed event
without detection), plus a verifiable anchor the owner can copy
off-host. It is tamper-EVIDENT, not tamper-proof, and no P-10
document claims otherwise.

## Alerts (deterministic rules)

`POST /security/alerts/evaluate` runs three rules over recent
audit data: repeated denials per actor, denied policy-change
attempts, repeated failed logins. Alerts deduplicate against
open alerts for the same rule+subject. Rules are code and
thresholds are owner policy — no ML, no model judgement.

## Status surface

`GET /security/status` aggregates: mode, suspension, session and
approval counts, open alerts/incidents, registered secrets,
active capabilities, and the audit chain's verification result.
This is the API the P-11 Command Center will render; the
dashboard itself is P-11 scope.
