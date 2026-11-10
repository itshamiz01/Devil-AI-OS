# Business Data Isolation (P-06 §28.1)

## The boundary

Each business has: its own rows (every P-06 table is keyed by
`business_id`), its own P-05 managed workspace (`business:<id>`, kind
`businesses`, rooted at `execution_workspaces/businesses/<id>/`), and
its own assignment set (`business_agent_assignments`).

## Enforcement layers

1. **P-05 substrate (inherited).** Workspace writes require a
   `business_ref` on the execution request (P-06 creation runs carry
   the business id, propagated to workflow steps); path validation
   confines all file operations to managed workspace roots; secrets in
   parameters are rejected.
2. **P-06 service layer (the per-business rule).** P-05's generic
   authorisation accepts *any* non-empty `business_ref` — it does not
   know which agent belongs to which business. P-06 therefore enforces
   the real rule itself: `assert_business_access` allows an agent
   principal only when an **active assignment** binds that agent to
   that business. Cross-business attempts are denied, audited, and
   published as `BusinessIsolationViolation` — a member of the
   persisted critical event set, so the denial lands in `system_events`
   (Scenario G, security test 2).
3. **API layer.** Business reads/writes require the P-01
   `read_business_data` / `modify_business_data` permissions;
   unauthenticated access is 401 (security test 1).

## Honest limits

- Portfolio staff agents are shared across businesses *by assignment*;
  isolation governs data/workspace access per business, not agent
  existence.
- Audit is append-only through the API, not cryptographically
  tamper-proof (carried limitation since P-01).
- Isolation is enforced for access *through the system's services*.
  Direct filesystem access to the host is an OS/operator concern, as in
  every prior phase.
