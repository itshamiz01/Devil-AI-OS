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


---

## Addendum — P-01 continuation run (2026-11-03)

`SECURITY_FOUNDATION.md:142` sets the P-01 minimum security gate as: *owner
authentication; safe local binding/IPC; policy/approval schema; durable audit;
**secret-store design; emergency-state foundation; migration/backup tests***.
The first four were already met and were re-verified by execution. The last three
were **unmet** — recorded as `L-22` / `D-16` during the P-00 re-audit. All three
are now closed.

### 1. Emergency-state foundation — IMPLEMENTED

`backend/app/core/emergency.py`, wired into the task engine, lifecycle, health
and API (ADR-0013).

- **Durable:** state lives in `system_configurations`, so it survives restart.
  Proven by `test_emergency_survives_restart_and_never_auto_clears`, which builds
  a second application instance over the same data directory and asserts the halt
  is still active, the lifecycle comes up `DEGRADED`, and non-essential submission
  is still refused.
- **Never cleared automatically:** no timer, health-check or startup path calls
  `deactivate`. Only `POST /api/v1/system/emergency/clear` does.
- **Owner-only:** the new `system.emergency` permission is derived into
  `OWNER_PERMISSIONS` and deliberately omitted from `SYSTEM_PERMISSIONS`, so the
  application can never halt or un-halt itself. Constitution §12 reserved this to
  the human owner. A non-owner principal is refused with 403 (tested).
- **Essential paths preserved:** `system.noop` (essential) still executes during a
  halt, so audit, recovery and owner-control paths stay available as §10 requires.
- **In-flight work controlled, not killed:** RUNNING non-essential tasks receive a
  cooperative cancellation request; QUEUED/RETRY_PENDING non-essential work is
  PAUSED. No task is hard-killed, satisfying P-01 §10.2.
- **Reason is mandatory and never logged:** it is persisted and audited but is not
  formatted into any log message, so it cannot smuggle a value past redaction.
- **Upgrade path fixed:** `grant_owner_permissions` previously ran only during
  `bootstrap_owner`, so an owner whose database predated `system.emergency` would
  have been permanently locked out of the control they are supposed to wield.
  `seed_core_data` now reconciles owner assignments at startup, audited as
  `permission.owner_reconciled`, and only for `kind == "owner"` — verified never
  to widen an agent principal.

**Deliberate narrowing, flagged for owner review:** §10 says "cancel eligible
work"; queued non-essential work is **paused**, not cancelled, because every P-01
handler is side-effect free (ADR-0011), so cancelling would destroy recoverable
owner work for no safety gain. See ADR-0013 consequences.

### 2. Backup and restore — IMPLEMENTED

`backend/app/database/backup.py` plus `autonomus backup` / `list-backups` /
`restore` CLI commands (ADR-0014).

- Snapshots use the **SQLite online backup API**, never a file copy: under
  `journal_mode=WAL` a copy can miss committed transactions still in `-wal`.
- A backup is reported successful only after the **copy** passes
  `PRAGMA integrity_check` *and* contains the nine required core tables. An
  unverifiable snapshot is deleted rather than left to be mistaken for a good one.
- **Restore is CLI-only and is not an HTTP endpoint.** P-01 §12 forbids exposing
  dangerous internal functions over HTTP; an owner-authenticated HTTP restore
  would still sit one leaked session token away from erasing the audit trail —
  exactly the "audit evasion" threat `SECURITY_FOUNDATION.md:38` assigns to P-01.
- Restore requires typing `RESTORE`, preserves the displaced database as
  `.pre-restore-<timestamp>.db`, strips stale `-wal`/`-shm` sidecars, refuses to
  run while a live backend pid is detected, and rolls back if the restored file
  fails verification.

**Tamper-resistance limitation, stated because §11 requires it:** backups are
ordinary files on the same host. They protect against accidental corruption and
application-level mistakes. They are **not** cryptographically immutable and give
no protection against a host administrator.

### 3. Secret store — DESIGN DELIVERED, NOT IMPLEMENTED

`docs/architecture/SECRET_STORE_DESIGN.md` (ADR-0012). The gate asks for
*design*, and P-01 holds **no plaintext secret** — owner passwords are Argon2id
hashes and session tokens are stored as SHA-256 hashes, both verified by
inspection. Implementing a store now would create a module with nothing to
protect, which P-01 §3 and Rule 3 forbid.

`keyring` was **not** added to `requirements.txt`: `TECHNOLOGY_VALIDATION.md:37`
records it as "candidate only", `D-05` is still pending, and its Windows
Credential Manager / DPAPI backend cannot be verified from this Linux workspace.
The design specifies fail-closed behaviour with **no plaintext fallback**, and
seven acceptance criteria the implementing phase (P-05/P-07) must satisfy.

Recorded as **PLANNED, not IMPLEMENTED**. No test in this repository exercises
secret storage and none claims to.

### Re-verified unchanged

- Zero `subprocess` / `os.system` / `shell=True` / `eval(` / `exec(` in
  `backend/app/` — re-grepped after these changes.
- The handler allowlist is still exactly `system.noop`, `system.echo`,
  `system.wait`, enforced by a Pydantic `Literal`, so an arbitrary command is
  rejected with 422 before it can be queued (Rule 4).
- Loopback-only binding and the phase-flag refusals still fail startup.
- No hardcoded credentials were introduced; `.env.example` remains free of real
  secrets and now labels the inert `AUTONOMUS_OPERATING_MODE` as inert.

### New residual risk

The emergency `reason` and backup paths are owner-supplied strings that reach the
database and API responses. They are length-bounded and validated, and the reason
is excluded from logs, but they are not otherwise sanitized. If a future frontend
renders them, it must treat them as untrusted text.
