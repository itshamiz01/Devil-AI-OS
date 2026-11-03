# P-01 Security Report

**Status:** Partial verification; not a security certification

## Implemented controls

- Loopback-only binding; remote access and non-loopback hosts rejected by configuration validation.
- Owner identity bootstrap with Argon2id password hashing; no plaintext password storage.
- Opaque bearer sessions stored as SHA-256 hashes, with expiry and revocation.
- Deny-by-default permission engine with resource scopes and explicit deny precedence.
- Protected administrative endpoints; unauthenticated requests return 401, forbidden requests 403.
- Approval requests bound to canonical action/parameter hash; high/critical self-approval blocked.
- Task handlers restricted to registered safe internal operations; arbitrary command execution rejected.
- Structured log redaction for bearer tokens and secret-like key/value patterns.
- Audit records for auth, permission denial, task lifecycle administrative actions and approval decisions.
- External, financial and cloud AI execution flags rejected if enabled.

## Verified by tests

Unauthorized/forbidden access, invalid credentials/token, approval misuse, permission denial, unsafe handler rejection, idempotency conflict, secret redaction, resource admission protection.

## Findings and limitations

- Local SQLite audit storage is not cryptographically immutable against a compromised host administrator.
- Login rate limiting is in-memory and per client key; it is not a distributed abuse protection system.
- No HTTPS is configured; P-01 is loopback-only. Remote access requires a later approved design.
- Approval decisions do not yet automatically authorize external tools or release WAITING_FOR_APPROVAL tasks.
- Windows-specific ACL/DPAPI/Credential Manager integration is not implemented or verified.
- Stale PID files can remain after forced termination; graceful console shutdown is preferred.
- Independent external security audit remains pending.
