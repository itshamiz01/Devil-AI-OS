# Identity and Access Control (P-10)

## One identity system: P-01

P-10 adds **no** identity store. Principals are P-01's: owner
(user), agents, external accounts, services. Roles and permission
rules are P-01's; P-10 reads them through the permission engine
and presents governed views (`GET /security/identities`,
`/security/agents/{id}/permissions`).

Owner-only permissions — `approve_actions`,
`modify_system_config`, `access_sensitive_data` — can never be
delegated, granted or handed off to a non-owner (enforced in the
broker's delegation check, capability issuance and handoff
validation).

## Sessions (P-01 storage, P-10 controls)

- `GET /security/auth/sessions` lists the caller's sessions.
- `POST /security/auth/sessions/{id}/revoke` revokes one session.
- `POST /security/auth/logout` revokes the current session
  (verified in smoke: the revoked token then gets 401).
- Sessions expire per P-01 policy; revocation is immediate in the
  shared session table, so it applies to every phase.

## Login protection

P-01's `AuthService.login` consults the P-10 `LoginGuard` when
wired (it is, at application startup): attempts are recorded in
`security_login_attempts`; after `login_max_failures` (default
10) failures within `login_window_minutes` (default 15) from the
same account/source, further logins are refused before the
password is checked, until the window passes. The guard fails
closed: an error inside the guard denies the login attempt.
P-01's own per-account lockout is unchanged — the guard
complements it with source-aware counting.

## Multi-factor authentication — PARTIALLY IMPLEMENTED

- `TotpVerifier` implements RFC 6238 TOTP (HMAC-SHA-1, 30-second
  step, ±1 step drift) with the standard library only; verified
  against the RFC test vectors in `test_p10_unit.py`.
- The shared secret is resolved through the secret broker
  reference `env:AUTONOMUS_TOTP_SECRET`; when unset, MFA reports
  **not configured** and verification fails closed.
- Enrolment (generating and storing the owner's TOTP secret) is
  an owner configuration step: REQUIRES OWNER CONFIGURATION.
- Recovery codes: NOT IMPLEMENTED.

## Account lifecycle

Registration, password change and account disabling remain P-01
operations; P-10 adds the restriction overlay for agents
(`security_agent_restrictions`: active / suspended / banned /
read-only) enforced by the broker ahead of the permission engine.
