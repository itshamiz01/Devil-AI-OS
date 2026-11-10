# P-10 Implementation Plan (Stage 1 output, §31 sequence)

**Date:** 2026-11-09 · Built on the Stage 1 audit
(`docs/audits/P10_PRE_IMPLEMENTATION_AUDIT.md`). Baseline: 509
tests, migration head `7b13db7e9bfa`, 123 tables.

## Design summary

One new package `backend/app/security/` (flat modules, house
style), one facade `SecurityService` (`Application.security`,
constructed after P-09), routes under `/api/v1/security/...`
(project convention adapting §26.1's `/api/security/...`), schemas
in `app/api/schemas/security.py`, repositories in
`app/database/repositories/security.py`, models in
`app/database/models/security.py`, **14 new tables, one additive
migration** chained from `7b13db7e9bfa` (123 → 137 tables).

Everything P-10 enforces is built **on** P-01 (engine, approvals,
audit, sessions, config), P-05 (path validator, credential broker,
browser sessions), P-07 (financial settings, read-only) and P-09
(secret patterns) — no parallel auth, permission, approval, audit
or ledger system is created.

### New tables (all `security_`-prefixed, additive only)

| Table | § | Purpose |
|---|---|---|
| `security_capabilities` | 7.2 | Task-scoped, expiring, revocable capability tokens |
| `security_broker_decisions` | 7.1/25 | Broker authorization decision ledger (domain record; the cross-system audit trail remains P-01 `audit_events`) |
| `security_policy_versions` | 23.3 | Versioned history of `security.settings` changes |
| `security_secret_metadata` | 9/25 | Secret registry — metadata only, never values |
| `security_secret_access_events` | 9.5/25 | Value-free secret access events |
| `security_emergency_events` | 20/25 | Security-mode transitions |
| `security_alerts` | 19.5/25 | Deterministic monitoring alerts |
| `security_incidents` | 25 | Incident records |
| `security_backup_records` | 20.4/25 | Backup manifests + verification results |
| `security_threat_register` | 4.3/25 | Living threat register (seeded from §4.3) |
| `security_audit_chain` | 19.3 | Hash-chain seals over P-01 `audit_events` |
| `security_login_attempts` | 5.2 | Login throttling evidence (username + outcome only) |
| `security_agent_restrictions` | 15.4 | Agent restriction overlay (factory lifecycle untouched) |
| `security_data_classifications` | 17.1/25 | Resource classification registry (levels 1–5) |

Explicitly **not** created (would duplicate P-01): `security_users`,
`security_identities`, `security_roles`, `security_permissions`,
`security_sessions`, `security_approval_requests`,
`security_approval_decisions`, `security_audit_events`.

### Modules

- `constants.py` — settings key/defaults, risk levels, modes,
  owner-only permissions, classification levels, threat seed.
- `policy.py` — pure functions: action risk classification (§8.1),
  settings-patch validation (§23.5), delegation rules (§7.3/§15.3),
  mode effects (§20.2).
- `broker.py` — Permission Broker (§7): `authorize()` (mode →
  restriction → business scope → P-01 engine → level gates:
  capability for L2, owner-decided hash-bound approval for L3),
  capability issue/verify/revoke, escalation requests via P-01
  approvals. Fails closed on any internal error.
- `identity.py` — session listing/revocation over P-01
  `app_sessions` (§5.4), login throttle guard (§5.2, wired into
  `AuthService` as an optional hook), stdlib TOTP verifier (§5.3,
  REQUIRES OWNER CONFIGURATION).
- `secrets.py` — secret metadata registry + brokered use (§9):
  values resolved only through P-05's credential broker into a
  caller-supplied operation; Windows vault backend = interface +
  unavailable-on-Linux stub (REQUIRES OWNER CONFIGURATION).
- `guards.py` — filesystem guard (§10: P-05 path validation +
  protected roots + classification), command guard (§11:
  allowlist, denylist patterns, argv validation — evaluates only,
  never executes), download guard (§12.5).
- `network.py` — egress policy + SSRF validator (§13: scheme,
  credentials-in-URL, resolved-IP ranges incl. metadata/loopback/
  private/link-local, redirect-chain re-validation; resolver
  injectable for tests), browser domain validation (§12.2).
- `ai_security.py` — content trust levels (§14.1), deterministic
  injection screening (pattern names only), agent-handoff envelope
  validation (§14.4), outbound secret screen (reuses P-09 patterns).
- `financial_guard.py` — transaction authorization evaluation
  (§16): action separation, P-07 limits read-only, exact-parameter
  approval binding, approval-consumption (replay) record,
  financial-suspension gate. **Authorizes; never executes, never
  writes P-07.**
- `emergency.py` — security mode service (§20): owner-only
  transitions, event records, mode gate helper.
- `audit_chain.py` — seal/verify over `audit_events` (§19.3).
- `monitoring.py` — status aggregation (§19.4 data API), filtered
  event views, deterministic alert rules (§19.5).
- `backup.py` — SQLite backup create/verify (§20.4); other
  dialects recorded REQUIRES OWNER CONFIGURATION.
- `service.py` — facade: settings lifecycle (owner-only, versioned,
  rollback), threat register, classifications, incidents,
  restrictions, browser-session access check (§12/Scenario 17),
  wiring of all sub-services.

### P-01 change (the carried residual)

`ApprovalService.decide`: engine-backed `approve_actions`
authority check + non-owner self-approval refusal (audit doc §4).
One P-08 test updated with a P-10 disclosure comment, strictness
preserved.

## Stage mapping (§31)

- **Stage 1** — this audit + plan. ✔
- **Stage 2** — identity/authorization: identity.py, broker core,
  capability tokens, P-01 `decide` fix.
- **Stage 3** — approvals: broker L3 gate on P-01 hash-bound
  approvals, risk classification, consumption/replay records.
- **Stage 4** — secrets + execution security: secrets.py,
  guards.py (filesystem/command) over P-05.
- **Stage 5** — browser/network/AI: network.py, browser-session
  check, ai_security.py.
- **Stage 6** — financial + data: financial_guard.py over P-07,
  classifications, P-09 Article-0 proofs.
- **Stage 7** — monitoring/recovery: audit_chain.py,
  monitoring.py, emergency.py, backup.py.
- **Stage 8** — full suite + 18 acceptance scenarios + smoke +
  docs (§30 set) + §33 report + tracker/README + zip.

## Test plan (~62 new)

- `test_p10_unit.py` (~20): risk classification, policy validation,
  SSRF validator (fake resolver: loopback/private/metadata/
  rebinding/redirect), command guard, filesystem guard, content
  screening, handoff validation, TOTP vectors, chain hashing,
  capability expiry, mode effects.
- `test_p10_scenarios.py` (18): one named test per §28.10
  scenario (`test_scenario_01_…` … `test_scenario_18_…`).
- `test_p10_security.py` (~13): `decide` role check + self-approval,
  Article 0 (policy manipulation, memory poisoning, prompt
  injection — named tests), secret-value absence (responses, audit,
  events), fail-closed broker, audit append-only structure,
  capability revoked/expired, settings owner-only.
- `test_p10_integration.py` (~11): migration cycle 123→137→123→137,
  HTTP flows (status, policy versioning, capability lifecycle,
  emergency pause/resume, secret metadata, chain seal/verify API),
  backup/restore drill, financial guard against real P-07 approval,
  forged-webhook via P-07.

## Honest-status commitments (pre-registered)

- Frontend / Security Command Center (§24): **NOT IMPLEMENTED**
  (no frontend in staging; P-11). Status APIs delivered instead.
- DPAPI / Windows Credential Manager (§9.2): **REQUIRES OWNER
  CONFIGURATION** — interface + fake-tested only.
- MFA (§5.3): **PARTIALLY IMPLEMENTED** — TOTP verifier implemented
  and vector-tested; enrolment requires an owner-set env secret
  (REQUIRES OWNER CONFIGURATION); recovery codes NOT IMPLEMENTED.
- Encryption at rest (§17.3): **PARTIALLY IMPLEMENTED** — no crypto
  library in the stack; platform protection is owner configuration.
- Audit hash chain (§19.3): tamper-**evident**, not tamper-proof —
  stated everywhere it is described.
- P-05 code execution remains **process controls, not a strong
  sandbox** — P-10's command guard does not change that claim.
- Live dependency vulnerability scanning (§22.2): tools absent
  from the venv; inventory documented, scan NOT RUN, not faked.
