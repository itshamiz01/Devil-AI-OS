# Expansion Feature 1 — Identity & Device Security: Implementation Report

Status: BUILT & VERIFIED IN STAGING (10 Nov 2026), awaiting the
owner's Gate 3 review. Classification unchanged: READY FOR
CONTROLLED PILOT. Companion documents: `F01_ARCHITECTURE.md`
(decisions), `F01_THREAT_MODEL.md`, `F01_TEST_REPORT.md`
(evidence). Smoke transcript: `docs/reports/F01_SMOKE_EVIDENCE.txt`.

## What was built

The two gaps named by the Gate 2 readiness review (§7.1), closed
by extending P-10 in place:

1. **A device registry** (`security_devices`): owner-labelled
   devices with a server-issued credential (SHA-256 hash stored,
   plaintext shown once at enrolment/rotation), a trust lifecycle
   (untrusted → trusted → revoked, terminal), last-seen tracking,
   and revocation. Label/platform/device-name are self-declared
   descriptive metadata — identity is the credential, never a
   hardware claim.
2. **Session↔device binding**: one additive nullable column
   (`app_sessions.device_id`). A password login that presents a
   device credential binds the session only when the device is
   trusted and the credential matches; untrust / revoke / rotate
   sweep (revoke) all bound sessions, and P-01's bearer
   resolution refuses bound sessions while the device is not
   trusted.
3. **MFA recovery codes** (`security_recovery_codes`), closing
   the standing P-10 limitation: batches of 10 (1–20) codes,
   ~59 bits each, shown exactly once, stored only as scrypt
   hashes, single-use, regeneration invalidating every unused
   predecessor. Status surfaces expose counts only.
4. **Audit through the existing machinery**: eleven new actions
   under `security.device_*` / `security.recovery_*` written to
   the P-01 `audit_events` trail via the P-10 facade — visible in
   the existing monitor, audit query and hash chain. No parallel
   log. Credential refusals at login also flow through the P-10
   login guard as failed attempts, so existing throttling and
   alert rules apply unchanged.
5. **Command Center surface**: the Security & Governance view
   gains a Devices panel (enrol, trust/untrust, rotate, revoke
   with confirmation; one-time secret display) and an MFA
   recovery codes panel (counts, generate-with-confirmation,
   one-time code display, verify), plus a Device column in the
   sessions table — all on the real endpoints.

## Permission matrix (as enforced and tested)

| Operation | Route guard | Service layer | Agent/Service/External |
|---|---|---|---|
| Enrol device | `modify_system_config` | owner-only | refused (403 / PermissionDenied) |
| List / get devices | `read_system_data` | owner-only | refused |
| Relabel | `modify_system_config` | owner-only | refused |
| Trust / untrust | `modify_system_config` | owner-only | refused |
| Revoke | `modify_system_config` | owner-only | refused |
| Rotate secret | `modify_system_config` | owner-only | refused |
| Generate recovery codes | `modify_system_config` | owner-only | refused |
| Recovery status | `read_system_data` | owner-only | refused |
| Verify recovery code | authenticated | owner-only | refused (and does not consume) |
| Device-bound login | public login route | device must be trusted + credential match + owner password | n/a (owner identity only) |

## §4.2 inheritance contract — compliance

1. Principals come from `get_principal` only; no token parsing
   was added. 2. Routes use `require_permission(Permission.X)`
   (enum values) AND the service layer re-checks owner-only
   operations. 3. No agent/tool execution surface was added, so
   no new broker path exists; the feature never calls the broker
   with fabricated principals. 4. No approvals are created,
   decided or consumed by this feature. 5. Audit via the shared
   facade callback; no cross-module internal calls (the auth hook
   is the established late-attachment pattern). 6. No secrets are
   stored as values anywhere: device secret → SHA-256 hash;
   recovery codes → scrypt hashes. 7. Tables are additive
   (migration `85b7a9805207`, cycle-tested 224 → 226 → 224 → 226);
   no money, customer, memory or scheduling store was touched.
   8. Tests ship in the established pattern, including the
   negative set (non-owner refused, untrusted/revoked/bad-secret
   logins refused, terminal-state transitions refused, code reuse
   refused).

## Files

- Backend: `app/security/devices.py` (new), `app/security/service.py`
  (facade wiring), `app/security/identity.py` (session dict gains
  `device_id`), `app/core/auth.py` (optional device gate +
  resolution check, hook pattern), `app/core/application.py`
  (hook wiring), `app/database/models/security.py` (2 models),
  `app/database/models/core.py` (`AppSession.device_id`),
  `app/database/repositories/security.py` (2 repositories),
  `app/api/routes/security.py` (9 routes), `app/api/routes/auth.py`
  (optional login fields), `app/api/schemas/security.py` (4 schemas),
  migration `85b7a9805207`.
- Frontend: `src/views/IdentityDevices.tsx` (new panels),
  `src/views/Security.tsx` (panels + Device column).
- Tests: `tests/f01_support.py`, `tests/test_f01_unit.py` (7),
  `tests/test_f01_integration.py` (10), `tests/test_f01_security.py`
  (13), `frontend/src/views/IdentityDevices.test.tsx` (3).
- Smoke: `backend/scripts/f01_smoke.py` → `docs/reports/F01_SMOKE_EVIDENCE.txt`.

## Rollback

- Code: the feature is additive. Reverting the listed files and
  running `alembic downgrade 218ddd92a0aa` restores the exact
  P-18 schema (226 → 224 tables, `device_id` column dropped) and
  behaviour; legacy sessions are unaffected because the column is
  nullable and unbound logins never consult the hook's verdict.
- Data: downgrading drops `security_devices` and
  `security_recovery_codes` (device enrolments and unused code
  hashes are lost — by design, since both are re-creatable by the
  owner and neither holds history the audit trail doesn't keep:
  every lifecycle event remains in `audit_events`).
- No other phase's data or behaviour depends on this feature.

## Honest limitations

- **Passkeys/WebAuthn NOT IMPLEMENTED** — nothing to build on in
  staging (no library, no testable browser ceremony); not faked.
- **Login-time MFA enforcement NOT IMPLEMENTED** — recovery codes
  (like P-10's TOTP before them) are a governed verify primitive,
  not a login gate; making MFA mandatory at login changes the
  login contract and is an owner decision, not a silent default.
- **Device presentation at login is optional** (architecture
  decision 4): binding governs sessions that claim a device.
  Mandatory presentation would break the Command Center and API
  clients, which hold no device credential; recorded here, not
  smoothed over.
- **Device trust is an owner-session act**: the bootstrap session
  that enrols/trusts is itself unbound (see threat model T3 /
  residual risks).
- **DEF-A1 / DEF-A2 stand**: nothing in this feature needs a real
  LLM; Windows verification remains an owner-machine item (no
  Windows-specific claim is made — device platform strings are
  self-declared labels).
- The P-17 boot-window login observation was handled as briefed:
  the smoke readiness-gates on `/health/ready` and retries login
  patiently (succeeded on attempt 1 in the final smoke run); no
  auth verification logic was modified to work around it.
