# Expansion Feature 1 — Identity & Device Security: Architecture

Status: built under the owner's Gate 2 go-ahead (2026-11-10), as
feature 1 of 11 in the Post-Completion Expansion Pack's dependency
order. This document records the architecture decisions taken
inside the build (the pack's internal approval steps are handled
P-14-style: architecture first, conservative minimal options,
reported in the gate summary).

## 1. What exists already (the starting map)

From the Gate 2 readiness review (§4, §7.1) and a fresh inspection:

- **P-01 owns identity and sessions**: owner account (scrypt
  password hash in `system_config`), hashed bearer sessions in
  `app_sessions` (12 h expiry), `AuthService.login /
  resolve_bearer`, the deny-by-default `PermissionEngine`, and the
  hash-bound `ApprovalService`.
- **P-10 owns security governance over that substrate**:
  `PermissionBroker`, capability tokens, the metadata-only secrets
  registry, `SessionService` (owner-only session list/revoke),
  `LoginGuard` (throttling, wired into `AuthService` through the
  optional `login_guard` hook), a stdlib TOTP verifier (enrolment
  REQUIRES OWNER CONFIGURATION), the append-only `audit_events`
  trail, and the deterministic alert monitor that reads it.
- **The two gaps this feature closes** (review §7.1): (a) no device
  concept exists anywhere in the 223 metadata tables; (b) MFA
  recovery codes were never implemented (the standing P-10
  limitation "MFA PARTIAL — recovery codes NOT IMPLEMENTED").

## 2. Decisions (conservative minimal options)

1. **Extend P-10 in place.** A new module `app/security/devices.py`
   (`DeviceService`, `RecoveryCodeService`) wired into the
   `SecurityService` facade as `.devices` / `.recovery_codes`;
   models in `app/database/models/security.py`; repositories in
   `app/database/repositories/security.py`. No new package, no
   second auth/session/permission/audit system (§4.2 inheritance
   contract, points 1–8, is followed for every new route).
2. **Device identity is a server-issued credential, not a hardware
   claim.** At enrolment the server generates a 256-bit random
   device secret (`secrets.token_urlsafe(32)`), returns it exactly
   once, and stores only its SHA-256 hash — the same pattern P-01
   uses for session tokens. Label / platform / device-name are
   owner-supplied descriptive metadata, explicitly self-declared:
   the pack (§2 of the feature prompt) forbids relying on easily
   spoofed hardware identifiers, so identity rests on possession
   of the credential, and metadata never gates anything.
3. **Trust lifecycle**: `untrusted` (at enrolment) → `trusted`
   (explicit owner action) → `revoked` (terminal; a revoked device
   can never return — re-enrolment creates a new device with a new
   credential). `untrust` returns a trusted device to `untrusted`.
   Only `trusted` devices may bind sessions. Untrust, revocation
   and secret rotation each **sweep** (revoke) every session bound
   to the device, and `resolve_bearer` additionally refuses a
   session whose device is not currently trusted (defence in
   depth: the sweep makes revocation immediate; the resolution
   check makes it structural).
4. **Session binding is additive and fail-closed when claimed.**
   `app_sessions.device_id` is a new nullable indexed column
   referencing the device (plain reference, the P-18 cross-module
   pattern; the P-04 additive-column precedent covers altering
   `app_sessions`). `POST /auth/login` accepts optional
   `device_id` + `device_secret`: when either is presented, both
   are required and verification is mandatory — an unknown,
   untrusted, revoked or bad-secret device refuses the whole login
   (and is recorded as a failed login for throttling/alerts). When
   neither is presented, login behaves exactly as before (the
   Command Center and API clients hold no device credential;
   making device presentation mandatory would be a breaking
   change, which the pack forbids). This boundary is stated
   plainly in the limitations: device binding governs sessions
   that claim a device; it is not yet a mandatory login gate.
   Wiring follows the existing `login_guard` precedent: an
   optional, late-attached `device_hook` on `AuthService`, set by
   `Application.startup` after P-10 is built. With no hook wired,
   P-01 behaviour is byte-identical to before — except that
   presenting device fields with no hook wired fails closed.
5. **Recovery codes close the P-10 gap on the TOTP pattern.**
   P-10's TOTP is a verify-primitive endpoint, not a login gate;
   recovery codes follow the identical posture. Generation is
   owner-only: 10 codes by default (1–20 per call), 12 characters
   from an unambiguous 31-symbol alphabet in 4-4-4 groups
   (~59 bits each), shown exactly once in the generation response.
   Only scrypt hashes are stored (P-01's `hash_password` — a slow
   hash, because a recovery code is a lower-entropy secret than a
   session token). Codes are single-use; regeneration invalidates
   every unused code of prior batches (rows are kept, status
   flipped to `invalidated`, so the audit story survives). The
   status surface exposes counts only — codes are never
   retrievable after generation.
6. **All events flow through the existing audit machinery.**
   Every enrolment, trust change, revocation, rotation, credential
   refusal, device-bound login and recovery-code event is written
   to the P-01 `audit_events` table through the facade's `_audit`
   (actions under the `security.device_*` / `security.recovery_*`
   names), so P-10's monitor, audit query and hash chain see them
   with no parallel log. No secret value or hash is ever written
   to an audit detail.
7. **No money surface, no governance change.** The feature adds no
   money column anywhere (schema-asserted by test), touches no
   P-07 table, decides no approval, and changes no policy
   semantics. Article 0 holds: `app/security` still never calls
   `ApprovalService.decide` (the standing structural test covers
   the new module automatically).

## 3. Data model (additive migration `85b7a9805207`)

- `security_devices`: id, principal_type/principal_id (the owner
  identity the device belongs to), label, platform, device_name
  (self-declared), secret_hash (SHA-256 of the device credential),
  trust_status (`untrusted` | `trusted` | `revoked`),
  last_seen_at, revoked_at, revoked_by, timestamps.
- `security_recovery_codes`: id, principal_type/principal_id,
  batch_id, code_hash (scrypt), status (`unused` | `used` |
  `invalidated`), used_at, timestamps.
- `app_sessions.device_id`: nullable indexed reference to
  `security_devices.id` (plain column, the P-18 cross-module
  reference pattern — no FK, so model import order can never
  break mapper resolution; the binding is enforced in code).

Physical tables 224 → 226; metadata tables 223 → 225. Downgrade
restores 224/223 and drops the column. Cycle-tested.

## 4. API surface (all on the existing security router)

| Route | Guard | Purpose |
|---|---|---|
| `POST /security/devices` (201) | `modify_system_config` + owner check | enrol; returns the device secret once |
| `GET /security/devices` | `read_system_data` + owner check | list devices (no secrets, no hashes) |
| `GET /security/devices/{id}` | `read_system_data` + owner check | one device |
| `PATCH /security/devices/{id}` | `modify_system_config` + owner check | relabel / update self-declared metadata |
| `POST /security/devices/{id}/trust` | `modify_system_config` + owner check | mark trusted |
| `POST /security/devices/{id}/untrust` | `modify_system_config` + owner check | mark untrusted; sweeps sessions |
| `POST /security/devices/{id}/revoke` | `modify_system_config` + owner check | revoke (terminal); sweeps sessions |
| `POST /security/devices/{id}/rotate-secret` | `modify_system_config` + owner check | new secret once; sweeps sessions |
| `POST /security/auth/recovery-codes/generate` (201) | `modify_system_config` + owner check | new batch; codes shown once |
| `GET /security/auth/recovery-codes` | `read_system_data` + owner check | counts/status only |
| `POST /security/auth/recovery-codes/verify` | authenticated principal + owner check | consume one code (single-use) |
| `POST /auth/login` (extended) | public (existing) | optional `device_id`/`device_secret` binding |

Session listings (`GET /security/auth/sessions`) now include
`device_id` per session, so bound sessions are visible in the
Command Center.

## 5. Frontend

The Security & Governance view gains two panels on real endpoints:
**Devices** (list with trust badges and last-seen; enrol form; the
enrolment secret displayed exactly once with explicit copy;
trust / untrust / revoke / rotate actions with confirmation for
revoke) and **MFA recovery codes** (status counts; generate —
codes displayed exactly once; verify form). The sessions table
gains a Device column. No fake data: empty states are the true
zero states of a fresh system.

## 6. What is deliberately NOT built

- **Passkeys/WebAuthn** — nothing exists to build on in staging
  (no library, no browser ceremony testable here); recorded as a
  limitation, not faked.
- **Login-time MFA enforcement** (password + TOTP/code as a login
  gate) — P-10's TOTP was never wired as a login gate either;
  changing the login contract is a separate, owner-visible
  decision. Recovery codes are delivered as the governed
  verify-and-consume primitive, exactly like TOTP verify.
- **Mandatory device presentation at login** — see decision 4.
- **Device attestation / hardware signals** — unverifiable from
  this Linux staging VM (DEF-A1) and spoofable by design warning.
