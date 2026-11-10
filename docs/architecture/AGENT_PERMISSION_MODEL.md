# Agent Permission Model (§8)

Capability-based, least-privilege, enforced by backend policy code at
every use — never by prompt text, never by role alone. Role is a
*description*; permission is a *grant*.

## Catalogue (`agent_capabilities`, seeded from `constants.py`)

Each capability declares: category, description, `approval_level`
(0–3), `supported` (does a real backing module exist *today*?), and
`enabled`. Supported in P-04 (backed by existing modules only, §8.1):

| Capability | Level | Backing |
|---|---|---|
| internal_reasoning | 0 | P-02 shared router (baseline path) |
| internal_database_read | 0 | internal records read |
| internal_database_write | 1 | internal records write |
| memory_read | 0 | §15 scoped interface (P-09 deferred scopes report unavailable) |
| financial_data_read | 1 | internal financial records read |
| web_research | 2 | P-03 `opportunity.research` handler |
| financial_transaction_request | 2 | REQUEST path only — records a request; no transaction execution exists anywhere in the system |

Catalogued but `supported=False` — requestable for the record, **never
grantable** until a real module exists: `memory_write` (P-09),
`file_read`, `file_write`, `api_read`, `api_write`, `code_generation`,
`sandboxed_code_execution`, `browser_interaction`,
`external_communication` (P-05/P-06 scope).

## Approval levels (§8.3)

- **Level 0** — granted on request / at creation.
- **Level 1** — granted when the capability is part of the agent's
  owner-published template; otherwise escalates to owner approval.
- **Level 2** — always a hash-bound owner approval (P-01
  `ApprovalService`, action `agent_factory.grant_capability`). The
  agent holds **nothing** while the approval is pending; only the
  owner principal may decide (an agent deciding its own grant gets
  `PermissionDeniedError`).
- **Level 3 — PROHIBITED.** `reveal_secrets`, `disable_security_controls`,
  `bypass_approvals`, `modify_audit_records`,
  `unrestricted_financial_authority`: `enabled=False` in the catalogue;
  requesting one raises `CapabilityProhibitedError`, records a **denied**
  ledger row, and audits the attempt. There is no approval path — not
  even for the owner through the agent flow (Constitution Article 0).

## Grant ledger + engine mirror

`agent_permissions` is the factory's grant ledger (status
granted/denied/revoked/expired, granter, approval reference, expiry,
revocation). Every grant/revoke is mirrored into the P-01 `permissions`
table as an allow/deny rule for `principal_type='agent'`, so the
existing `PermissionEngine.check` — deny always wins — is the single
enforcement point at use time. Expired grants are swept by maintenance
(mirror deny written) and never counted as held.

## Non-negotiables (all test-covered)

- No self-grants: an agent's request can only *ask*; Level ≥1 decisions
  belong to deterministic policy or the owner.
- No inheritance: a child agent receives nothing from its parent;
  delegation transfers no authority.
- No escalation via instructions: injected text in justifications,
  requirements or template `system_instruction`s cannot change a
  decision (security tests 05/09).
- No governance edits: factory settings (fleet limits, ceilings) are
  writable only by the owner principal server-side; agents and the
  service principal get `PermissionDeniedError` (security test 02).
- Agents never receive raw secrets; no API response contains credential
  material (security test 04b).
