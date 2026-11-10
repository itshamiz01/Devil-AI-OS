# Secrets Management (P-10)

## The rule

AUTONOMUS stores **metadata about secrets, never secret values**.

- Registry rows (`security_secret_metadata`) hold: name, purpose,
  classification, lifecycle status, rotation metadata, and a
  reference in one of two forms only: `env:NAME` or
  `windows-vault:NAME`. The API returns a masked hint
  (`env:***`) — the raw reference is never returned, never
  logged, and never appears in errors.
- Registration and checks never resolve the value.

## The broker

- `execute_with_secret(principal, name, callback, purpose)` is
  the only value-touching path: it runs the full broker decision
  (mode, restrictions, business scope, the owner-only
  `access_sensitive_data` permission, risk gates), records the
  access event (granted/denied, purpose — never the value), and
  hands the value only to the caller's in-process callback. It is
  **not exposed over HTTP**.
- `check_access` makes the same decision without resolving
  anything (this is what the API exposes).
- Backends: `env` reuses P-05's `EnvCredentialBroker`;
  `windows-vault` (DPAPI / Windows Credential Manager) is an
  interface whose backend reports unavailable on non-Windows
  hosts — **REQUIRES OWNER CONFIGURATION**.

## Leakage defences

- P-09's pipeline screening (reused) rejects secret-shaped values
  before they are stored as memory; P-10's outbound screen applies
  the same detector to tool-bound content.
- Security events record **pattern names only** (e.g.
  `openai_style_key`), never the matched text — the P-09
  Scenario-12 precedent, kept.
- Tests use synthetic values (`sk-` + repeated characters,
  injected through monkeypatched environment variables) and
  assert the value appears in no API surface, event, decision or
  report.
- Lifecycle: register → rotate (metadata) → revoke. A revoked
  secret denies all further access checks.
