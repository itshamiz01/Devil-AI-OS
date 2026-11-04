# Secret Store Design (P-01 deliverable — DESIGN ONLY)

**Status:** DESIGN — **not implemented**. No secret-store code exists in `backend/`.
**Gate satisfied:** `SECURITY_FOUNDATION.md` §11 requires *"secret-store design"* of P-01. This document is that design. Implementation belongs to the phase that first holds a live external secret (P-05 browser sessions, P-07 wallet/payment credentials).
**Phase:** P-01 · **Date:** 2026-11-03 · **Related:** ADR-0012, `D-05`, `D-16`

---

## 1. Why P-01 delivers a design and not an implementation

Two independent reasons, either of which is sufficient:

1. **The gate asks for design.** `SECURITY_FOUNDATION.md:142` lists the P-01 security minimum as *"…durable audit; **secret-store design**; emergency-state foundation; migration/backup tests"*. The adjacent items are implementation obligations; this one is explicitly a design obligation.
2. **P-01 holds no plaintext secret to store.** Verified by inspection of `backend/app/`:
   - Owner passwords are stored as **Argon2id hashes** (`core/auth.py:hash_password`), never reversibly.
   - Session tokens are stored as **SHA-256 hashes** (`core/auth.py:token_hash`); the bearer value exists only in the owner's client.
   - No API key, wallet key, browser cookie or third-party credential is read, generated or persisted anywhere in P-01.

   Building a live secret store now would therefore be a module with nothing to protect — an empty placeholder, which P-01 §3 and Rule 3 forbid.

Consequence: **this is recorded as PLANNED, not IMPLEMENTED.** No test in this repository exercises secret storage, and none claims to.

## 2. Why `keyring` is not added as a dependency in P-01

`keyring` 25.7.0 (MIT, Python ≥3.9) is the validated candidate adapter — see `TECHNOLOGY_VALIDATION.md:37`, which records it as **"Candidate only; never a prompt-visible secret store."**

It is deliberately **not** in `backend/requirements.txt`, because:

- P-01 §2 forbids replacing or extending the approved technology stack without authorization, and `D-05` (toolchain approval) is still **Pending**.
- Its backend cannot be verified in this workspace: the OS credential store it targets (Windows Credential Manager / DPAPI) does not exist on the Linux sandbox used for P-01. Adding it would produce a dependency whose behavior is untested — precisely the "assume a feature exists because documentation describes it" failure P-01 §2 warns against.

Adding `keyring` requires an owner decision (`D-05`) and Windows verification. Recorded, not worked around.

## 3. Threat model

| Threat | Mitigation required of the store |
|---|---|
| Secret read by a compromised agent or prompt-injected model | Secrets are **never** placed in prompt context, model input, agent memory or task payloads. Retrieval is caller-scoped and audited. |
| Secret written to logs | Retrieval and use paths pass through `core/logging.py:redact()`; secret values are never formatted into log messages. The store API returns values that must not be logged, and the audit record stores only a **reference name**, never a value. |
| Secret committed to source control | `.gitignore` already excludes `.env`, `.env.*` (except `.env.example`), `secrets/`, `credentials/`, `*.pem`, `*.key`, `*.p12`, `*.pfx`. No secret may be written inside the repository tree. |
| Secret persisted in SQLite | Ordinary tables must not hold secret values (`DATABASE_IMPLEMENTATION.md`). The store is **outside** the application database. |
| Host administrator / offline disk theft | Out of scope for a local-first desktop app; documented as a residual limitation, not silently assumed away. See §8. |
| Silent fallback to plaintext | **Forbidden.** If no secure backend is available the store must fail closed. See §6. |

## 4. Required interface

The interface below is the contract P-05/P-07 must implement against. It is specified here so that no later phase has to invent it under time pressure, and so that the security review has a fixed target.

```python
class SecretStore(Protocol):
    async def get(self, name: str, *, principal_id: str, correlation_id: str | None = None) -> str: ...
    async def put(self, name: str, value: str, *, principal_id: str, correlation_id: str | None = None) -> None: ...
    async def delete(self, name: str, *, principal_id: str, correlation_id: str | None = None) -> None: ...
    async def exists(self, name: str) -> bool: ...
    def backend_name(self) -> str: ...
    def is_secure(self) -> bool: ...
```

Contract rules:

- **Every access is authorized and audited.** `get`/`put`/`delete` must pass a permission check (a new `secrets.read` / `secrets.write` pair, owner-scoped) and write an `audit_events` record containing the secret **name** and outcome — never the value.
- **`name` is a stable reference**, not a path. It must be validated against an allowlist pattern so a caller cannot address arbitrary OS credentials.
- **Values are returned in memory only.** No API may serialize a secret into a response body, event payload, task result or log line.
- **`is_secure()` is honest.** It reports whether the active backend is a genuine OS-backed store. Callers that require real protection must check it rather than assume.

## 5. Backend selection

| Backend | Platform | Assessment |
|---|---|---|
| Windows Credential Manager via `keyring` | Windows (production target) | **Preferred.** OS-managed, per-user, DPAPI-protected at rest. Requires the app to run under a consistent user account; behavior under a Windows service account differs and must be verified. |
| `keyring` SecretService backend | Linux desktop | Acceptable for development only; unavailable headless. |
| Environment variables | Any | **Not a store.** Acceptable only for a bootstrap token injected by the owner at launch, never for persisted credentials. |
| Encrypted file with app-held key | Any | **Rejected.** If the application holds the key, the key must be stored — an infinite regress that ends in plaintext on the same disk. |
| Plaintext file / SQLite column | Any | **Forbidden** by Constitution §10 and `SECURITY_FOUNDATION.md`. |

Wallet private keys additionally require the separation already mandated by standing policy: **read-only wallet access plus a separate approval-controlled executor**, with the private key never entering a prompt, config file or agent context.

## 6. Failure behavior — fail closed

There is **no plaintext fallback**. If no secure backend is available:

- `get`/`put`/`delete` raise a typed `SecretStoreUnavailableError`.
- `is_secure()` returns `False` and `backend_name()` names the null backend.
- Dependent subsystems (P-05 browser automation, P-07 payments) must refuse to start rather than degrade to insecure storage.
- Startup logs a single critical record naming the missing backend — without any secret value.

This mirrors the existing P-01 precedent: `Settings.validate_host` refuses to start on a non-loopback bind rather than warning and continuing.

## 7. Acceptance criteria for the implementing phase

The phase that implements this design is not complete until:

1. Secrets round-trip through the real OS backend on **Windows**, demonstrated by execution, not by code review.
2. A test proves that **no secret value appears in any log file** after authorized use (extending the existing `test_redaction` approach to a full log-body assertion).
3. A test proves that a **non-owner principal is denied** `secrets.read`.
4. A test proves the store **fails closed** when no secure backend exists.
5. A test proves secret values are **absent from the SQLite database** after use.
6. Audit records contain names and outcomes only — asserted, not assumed.
7. `keyring` (or its replacement) is added to `requirements.txt` **and** `pyproject.toml` under an approved `D-05` decision.

## 8. Documented limitations

- **Local storage is not tamper-proof.** A host administrator, or an attacker with equivalent privilege, can read the OS credential store, replace the binary, or attach a debugger to the running process. No local-first design removes this. This is the same limitation already recorded for the audit table (`L-16`) and it is **not** solved by this design.
- **Backups do not protect secrets.** Because secrets live outside the SQLite database, the P-01 backup/restore feature (`database/backup.py`) deliberately does **not** back them up. Losing the OS credential store is not recoverable from an application backup; re-authorization by the owner is.
- **No secret rotation or expiry** is designed here. Rotation policy belongs with the subsystem that owns each credential.
- **Windows behavior is unverified.** Nothing in this document has been executed against Windows Credential Manager or DPAPI. It must not be described as Windows-verified.
