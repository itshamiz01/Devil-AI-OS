# Security Operations Guide (P-10)

Day-to-day operation of the governance layer (owner):

## Daily / weekly

- `GET /api/v1/security/status` — mode, open alerts/incidents,
  pending approvals, audit-chain verification result.
- `POST /api/v1/security/alerts/evaluate` — run the alert rules;
  acknowledge or resolve what they raise.
- Review pending P-01 approvals; expire anything stale.

## Policy changes

- All changes go through `PUT /api/v1/security/policies` (or the
  emergency endpoints for mode/suspension) — every change is a
  new version with a reason; rollback posts the older settings
  as a new version, history is never rewritten.
- Never edit `system_config` rows by hand: a hand-edit bypasses
  versioning and will surface as an unexplained chain/settings
  mismatch.

## Capabilities

- Issue narrowly (one permission, resource-scoped where
  possible, short expiry). Revoke on any doubt — re-issuing is
  cheap.
- A capability is never a substitute for a Level-3 approval.

## Secrets

- Register metadata before first use; rotate by updating the
  value in the vault/environment and the rotation timestamp in
  the registry; revoke immediately on suspected exposure.
- If a value ever appears in a log or message: treat it as
  exposed — revoke, rotate, and open an incident.

## Backups

- `POST /api/v1/security/backups` then `.../verify`; copy the
  backup file off-host. Rehearse the restore procedure
  (INCIDENT_RESPONSE_PLAYBOOK.md) — the restore is manual by
  design in this phase.

## Drills

- Monthly: safe_mode drill (set, confirm agent writes stop,
  resume), emergency_stop drill, chain verification.
- The P-10 smoke script can be re-run against any staging copy
  as a 33-check regression of the live surface.
