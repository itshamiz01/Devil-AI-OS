# P-09 Security Notes

## Article 0 boundary (memory is data, never authority)

- Every write passes one gate (`app/memory/policy.py`): secret
  screen, governance-claim screen, truth-class/category restrictions
  for agents, and scope checks.
- The memory package holds **no reference** to the approvals service,
  the permission engine, or any grant path — verified by a structural
  test that inspects the package source and the facade's attributes.
  There is no code path from a memory record to permissions,
  approvals, spending limits or governance settings.
- Retrieved content is returned as data with provenance. A poisoned
  document stored as evidence changes no setting, preference or rule
  (Scenario 5 test).
- Memory settings are owner-governed in `system_config`; agent
  updates are refused.

## Secrets (§7.4, §18.2)

- Passwords, API keys, tokens, private keys and credential
  assignments are detected by pattern and **rejected before storage**
  — from records, ingestion and learning alike, and therefore from
  the vector index too.
- The security event records only the pattern name, source type and
  content length. The value appears in no table, log or event
  (Scenario 12 test scans all three stores).

## Access control (§14)

- Read visibility is a hard filter applied before ranking: OWNER_ONLY
  and GOVERNANCE records are owner-only; PRIVATE_AGENT records belong
  to one agent; business/project scoping binds agents to their P-01
  `business_ref`; external/unauthenticated principals receive
  nothing (route-level permission + service-level checks).
- Agents cannot verify, delete, or modify other principals' records,
  cannot mark anything `verified_fact`, and cannot store owner
  instructions or governance claims.
- Owner preferences: an INFERRED preference never overrides an
  EXPLICIT owner instruction (§17).

## Auditability

All memory mutations write `memory.*` events to the P-01 audit trail
(`memory.record_created`, `memory.secret_blocked`,
`memory.learning_verified`, `memory.record_deleted`,
`memory.exported`, …). Retrieval is logged with the query stored as
a SHA-256 digest + length only, so the log cannot leak query text.
