# AUTONOMUS P-01 — SECURITY REPORT

**Security verification: PASSED (for the P-01 scope, on Linux).** Windows-specific execution is unverified (see limitations).

## Controls implemented and tested

- **Authentication:** owner password login; password only from env, scrypt-hashed at first run (hash-only storage), constant-time verification; session tokens random, stored SHA-256-hashed with expiry/revocation. Service token (limited principal) and local-dev token modes documented in PERMISSION_SYSTEM.md. **No hardcoded or default credentials anywhere.** Locked mode (no credential configured) rejects all protected requests.
- **Authorization:** deny-by-default permission engine in front of task submission/cancellation and sensitive routes; explicit DB deny rules override role grants; approval-required permissions flagged, never self-executing. Tests prove: unauthenticated → 401 on every protected route; wrong password → 401; Service principal → 403 (not 401) on approval decisions and task cancellation; Agent/External principals denied approve/config/sensitive/financial permissions both via API paths and direct engine calls.
- **Approval integrity:** decisions are one-shot (second decision → 409), expiry enforced, and approvals are bound to a SHA-256 hash of exact action+parameters — changed parameters invalidate the approval (unit-tested, and re-verified in the task-release path).
- **Execution safety (Rule 4):** tasks run only named registry handlers; a submission with handler `os.system` and a shell payload is rejected 422 at submission. No endpoint executes arbitrary code, commands or file paths; the only id-parameter file-adjacent probe (path traversal) returns a plain 404.
- **Input validation:** Pydantic schemas on every body; malformed/missing/out-of-range inputs → 422 in the standard envelope.
- **Secrets hygiene:** startup config dump redacted; logging redaction filter masks configured secrets + secret-shaped patterns; a test reads the real log file after authenticated traffic and asserts none of the configured secrets appear. `.env.example` contains no real secrets; `.gitignore` exclusions from P-00 remain in force.
- **Network exposure:** default bind is loopback (127.0.0.1) in settings and in both launch scripts; remote access is not implemented and requires a later approved design (§13.15).
- **Audit:** every permission check and every approval decision writes an `audit_events` row (actor, action, decision, reason, correlation ID). Audit rows have no update/delete API.

## Findings

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | Medium | Alembic's ini-driven `fileConfig` silently re-leveled app logging to WARN during programmatic migrations — security-relevant logs after migration would have been lost | **Fixed** (env `disable_existing_loggers=False` + post-migration logging re-assertion + regression test) |
| 2 | Low | Cancellation of a running task is cooperative: it takes effect when the handler returns (bounded by the task timeout). A handler that ignores its timeout context cannot be force-killed in-process | Accepted for P-01; bounded handlers + timeout cap (≤3600 s, built-ins ≤10 s) limit exposure; noted as technical debt |
| 3 | Info | Local SQLite audit storage is append-only by API design, not cryptographically tamper-proof against filesystem access | Documented honestly in PERMISSION_SYSTEM.md (per §11); cryptographic chaining is a P-10 hardening candidate |
| 4 | Info | `health/live` is unauthenticated by design and reveals only process liveness + lifecycle state (no versions, paths, or resource data) | Accepted; readiness/system detail all require auth |

No critical or high-severity findings remain open. No real financial access exists in P-01 (Rule 5): there is no wallet, payment or account code in the tree.
