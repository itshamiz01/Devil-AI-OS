# P-10 — Security and Governance Engine Architecture

P-10 turns the P-01 security primitives into a governed system.
It is a layer, not a replacement: identities, permissions,
sessions, approvals and the audit trail remain P-01's; money
remains P-07's; memory remains P-09's.

## Components (`backend/app/security/`)

| Module | Responsibility |
|--------|----------------|
| `constants.py` | settings key/defaults, risk levels, owner-only permission set, modes, classifications, protected roots, threat-register seed |
| `policy.py` | pure rules: action risk classification, mode matrix, delegation violations, policy-patch validation |
| `broker.py` | PermissionBroker: gated authorization, capability lifecycle, escalation via P-01 approvals |
| `identity.py` | session list/revoke/logout over P-01 sessions; login guard (throttling); RFC 6238 TOTP verifier |
| `emergency.py` | owner-only mode + financial-suspension transitions |
| `audit_chain.py` | SHA-256 hash chain over the P-01 audit trail (seal/verify/status) |
| `secrets.py` | metadata registry, brokered access decisions, backend adapters (env / windows-vault interface) |
| `guards.py` | filesystem, command and download decision guards |
| `network.py` | egress/SSRF validator, redirect chains, browser domain checks |
| `ai_security.py` | trust hierarchy, injection screening, outbound secret screening, handoff validation |
| `financial_guard.py` | view/approve/execute separation over P-07 limits with approval binding + consumption |
| `monitoring.py` | status aggregation, deterministic alert rules |
| `backup.py` | SQLite backup + manifest + verification (restore = owner procedure) |
| `service.py` | SecurityService facade: settings/versioning, threats, classifications, restrictions, incidents, views |

Plus P-01 changes: `ApprovalService.decide` service-level role
check + non-owner self-approval refusal; `AuthService.login`
optional login-guard hook (fail closed).

## Data (migration `e37d00443d20`, 14 new tables, 137 total)

`security_capabilities`, `security_broker_decisions`,
`security_policy_versions`, `security_secret_metadata`,
`security_secret_access_events`, `security_emergency_events`,
`security_alerts`, `security_incidents`,
`security_backup_records`, `security_threat_register`,
`security_audit_chain`, `security_login_attempts`,
`security_agent_restrictions`, `security_data_classifications`.

No users/roles/permissions/sessions/approvals/audit tables were
created (P-01's are used), and no P-10 table carries a money
column (structurally tested).

## API

`/api/v1/security/...`: status; permissions check/escalate;
capabilities; policies (+versions, rollback); emergency mode and
financial suspension; auth sessions/logout; secrets (+backends,
access-check, rotate, revoke); guards (filesystem, command,
download); network egress; content screen/screen-outbound;
financial authorize; audit (list, seal, verify); alerts;
incidents; threats; classifications; agent restrictions;
identities; backups. Login is NOT duplicated — P-01's `/auth`
endpoints remain the only login surface.

## Design invariants

- Fail closed at every gate, including inside error handlers.
- Deterministic decisions only; no LLM in any security path.
- Owner is never locked out by modes or throttles meant for
  agents.
- Governance material (settings, policy, approvals) is writable
  only through owner-checked paths — Article 0, tested via
  service, API, memory and injection attacks.
