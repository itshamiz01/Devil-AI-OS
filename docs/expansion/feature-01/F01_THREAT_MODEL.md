# Expansion Feature 1 — Threat Model (Identity & Device Security)

Scope: the device registry, session↔device binding, and MFA
recovery codes added by this feature. Method: STRIDE-informed,
consistent with the P-10 threat register. The register itself is
owner-governed seed data and is NOT modified by this feature;
entries below are candidates the owner may adopt into it.

## Assets

- The owner password (unchanged: scrypt hash in `system_config`).
- Session tokens (unchanged: SHA-256 hashes in `app_sessions`).
- **Device secrets** (new): 256-bit random credentials; only
  SHA-256 hashes stored (`security_devices.secret_hash`).
- **Recovery codes** (new): ~59-bit codes; only scrypt hashes
  stored (`security_recovery_codes.code_hash`).

## Threats and controls

| # | Threat | Control (as built) |
|---|---|---|
| T1 | Stolen device secret used to bind a session from elsewhere | The secret alone is never sufficient: a device-bound login still requires the owner password (tested: valid device + wrong password fails). Rotation immediately invalidates the old secret and revokes bound sessions; revocation is terminal. |
| T2 | Stolen session token from a bound device | Revoking or untrusting the device revokes its sessions (sweep) AND resolution refuses bound sessions while the device is not trusted (structural backstop). Session expiry (12 h) unchanged. |
| T3 | Attacker enrols a rogue device | Enrolment is owner-only, enforced at the route guard (`modify_system_config`) and again in the service layer; non-owner attempts are refused (tested for agent/service/external, service-level and HTTP). New devices start UNTRUSTED, so even an enrolment made during a hijacked owner session cannot hold a session until a separate trust act. |
| T4 | Privilege escalation: agent acts on devices/codes | Agents hold neither `modify_system_config` nor owner identity; every device/recovery operation checks `is_owner` in the service layer. Devices cannot be issued to, or managed by, agent principals — the registry belongs to the owner identity only. |
| T5 | Recovery-code brute force | Codes are ~59 bits, scrypt-hashed (slow verify), single-use, and verification requires an authenticated owner session (the TOTP-verify posture). Every attempt, success or failure, is audited (`security.recovery_code_used` / `security.recovery_code_refused`). A failed guess consumes nothing but also learns nothing (uniform `{"verified": false}`). |
| T6 | Recovery-code leakage from storage | Plaintext exists only in the single generation response. Database rows hold scrypt hashes (tested: no plaintext or normalised form appears in any stored column); audit details never contain codes (tested). Regeneration invalidates all unused predecessors. |
| T7 | Device-secret leakage from storage/logs | Hash-only storage (tested: list/detail/session surfaces never expose the secret or its hash); audit details carry labels and reason categories only (tested: attempted and real secrets absent from refusal events). |
| T8 | Spoofed hardware identity | Not relied upon at all: label/platform/device-name are self-declared descriptive metadata and gate nothing (the pack's explicit warning). Identity = possession of the server-issued credential + the owner password. |
| T9 | Login brute force via the device path | Device refusals return through the same `AuthService.login` failure path, so the P-10 `LoginGuard` records them as failed attempts and the existing throttling + alert rules apply unchanged (tested: failure rows recorded). Throttling state uncertain → fail closed, as before. |
| T10 | Fail-open on device-state errors | The device gate and the resolution-time trust check fail closed: any exception or missing hook refuses the device claim (and only the device claim — legacy password login semantics are untouched). Service-layer state machine errors surface as 409, never as silent no-ops. |
| T11 | Governance self-amendment via the new surface | The feature exposes no policy, permission or approval write path; the standing structural test (security package never calls `ApprovalService.decide`) covers the new module. Article 0 surfaces are untouched. |
| T12 | Denial of service via batch generation | Code generation is owner-only and capped at 20 codes per call; scrypt cost per code is bounded and paid only by the owner's own request. Device enrolment is owner-only; no unauthenticated surface was added (the only public route touched, `/auth/login`, gained optional fields, not a new path). |

## Residual risks (honest)

- **The owner session that enrols/trusts devices is itself
  unbound** until a device login occurs (bootstrap). A hijacked
  owner session could enrol + trust a rogue device; the audit
  trail records both acts, and the two-step enrol→trust split
  means a single accidental call cannot create a working device.
  Mandatory device presentation at login would close this fully
  but is a breaking change (see architecture decision 4) and
  remains an owner decision.
- **Device secrets are bearer credentials**: a copied secret +
  the owner password = a working device identity until rotation
  or revocation. This is inherent to the credential model and is
  why the password is always also required.
- **Recovery codes shift risk to wherever the owner stores
  them** (by design — they are an offline fallback). The UI copy
  says to store them offline; the system cannot enforce that.
