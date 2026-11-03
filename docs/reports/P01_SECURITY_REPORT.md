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

## Addendum 2026-11-03 — approval-gated task release

The finding above that approval decisions "do not yet ... release
WAITING_FOR_APPROVAL tasks" is superseded. The original text is preserved as the
record of what was true at review time.

Now implemented and tested:

- `approval_required=true` creates the gating approval in the same transaction
  as the task, so a gated task can never wait on an approval that does not exist.
- The gate is bound to a canonical hash of the task's handler, name and payload;
  a hash mismatch refuses release and cancels the task
  (`APPROVAL_BINDING_MISMATCH`).
- `ApprovalGranted` releases to `QUEUED`; `ApprovalRejected` cancels. Both are
  also applied by a periodic sweep and at startup, so a decision survives a lost
  event or an offline period.
- Expired, missing or unmatched gates close the task with an explicit
  `error_details` code instead of leaving it stranded — removing the silent
  dead end.
- Closed gates always end in `CANCELLED`, never `FAILED`, because
  `FAILED -> QUEUED` is a legal transition and must not become a route into
  execution without a fresh approval.
- Gate risk stays `medium`: the owner is the only holder of `approvals.decide` in
  P-01, and `high`/`critical` would block self-approval and make every gate
  undecidable. Raising it requires a second approver principal first.

Still true and unchanged: approvals do not authorize external tools or any
external side effect, because no external execution handler exists in P-01.
