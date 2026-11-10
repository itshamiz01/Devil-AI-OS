# P-10 Pre-Implementation Audit (Stage 1, §3)

**Date:** 2026-11-09 · **Scope:** the actual P-01–P-09 implementations
in staging, inspected in code before any P-10 code was written.
Baseline: **509 tests green**, migration head `7b13db7e9bfa`,
**123 tables** (122 application tables + `alembic_version`).
Nothing below was assumed from documentation; every claim was
verified in source.

## 1. Component-by-component classification (§3.2/§3.3)

### P-01 Core OS — the security substrate P-10 extends

| Component | State | Evidence / weakness |
|---|---|---|
| Owner authentication | Implemented and verified | `app/core/auth.py`: scrypt password hashing, session tokens stored only as SHA-256 hashes, expiry enforced in `resolve_bearer`. Password comes only from env; hash seeded once into `system_config`. |
| Login throttling / lockout | **Missing** | `AuthService.login` has no attempt counting, no lockout, no audit event for attempts (§5.2 gap). |
| Session revocation / logout | **Partially implemented** | `app_sessions.revoked` flag exists and is honoured in `resolve_bearer`, but **no logout endpoint, no session listing, no revocation path exists anywhere** (§5.4 gap). |
| MFA | **Missing** | No TOTP/recovery-code support (§5.3). No TOTP library in the venv; RFC 6238 is implementable on stdlib `hmac`/`hashlib`. |
| Permission engine | Implemented and verified | `app/permissions/engine.py`: deny-by-default, explicit deny > explicit allow > role default, **fails closed** when permission data is unavailable, every check written to `audit_events`. This is the one authorization authority; P-10 consumes it, never replaces it. |
| Roles | Implemented but coarse | `ROLE_DEFAULTS` over 5 principal types (owner/system/service/agent/external) in `app/permissions/policies.py`. §6.1's finer roles (security administrator, read-only auditor…) do not exist as principals; P-10 maps its role vocabulary onto principal types + DB rules rather than inventing a second role system. |
| Approvals | Implemented, **one known insufficiency** | `app/permissions/approvals.py`: SHA-256 hash-bound to action+resource+parameters, expiry enforced lazily, state machine refuses re-decision. **Residual carried since P-07: `ApprovalService.decide` performs NO service-level role check and NO self-approval check** — any principal object handed to it can decide. Today only the API route (`require_permission("approve_actions")`) gates it, and P-08/P-09 defensively re-verify approver identity themselves. **P-10 closes this in `decide` itself (see §4 below).** |
| Audit log | Implemented but not tamper-evident | `audit_events` is append-only *by API* (`AuditRepository` exposes `add` only — no update/delete path exists), but rows are ordinary mutable/deletable table rows at the database level: **no hash chain, no integrity verification** (§19.3 gap; the same residual P-06–P-09 recorded). P-10 adds a hash-chain seal/verify layer over it — detection, honestly not prevention. |
| Event bus | Implemented and verified | `app/events/` with persistence subscribers; P-09 precedent (no new bus types; the audit log is the durable record) is followed by P-10. |
| system_config governance | Implemented and verified | Owner-governed settings pattern (`financial.settings`, `survival.settings`, `memory.settings`); agents have no write path (Article 0). P-10 adds `security.settings` the same way. |
| Emergency stop | **Partially implemented, fragmented** | P-05's execution policy has its own execution emergency stop (policy check #10); P-08 has business pause controls. **No system-wide security mode** (normal / safe mode / emergency stop / financial suspension) exists (§20 gap). P-10 adds the security-layer mode; it does not rewrite P-05's internal stop. |
| Backup / recovery | **Partially implemented** | No backup tooling, no restore drill anywhere in P-01–P-09 (P-09 report §23 recorded the same). |

### P-02 Master Intelligence

Deterministic-first planner; model outputs validated identically
whether from the baseline planner or an LLM provider; plan approvals
use P-01 hash-bound approvals. Weakness for P-10: the intelligence
layer consumes retrieved memory and tool output without a dedicated
**content-trust classification or injection screening** surface (§14
gap) — screening exists only inside P-09's memory write gate for
governance-shaped text. P-10 adds the §14 screening/trust module as a
deterministic library other layers can call.

### P-03 Opportunity Discovery

External research is ingested as untrusted evidence with provenance;
sources are SSRF-guarded in the research layer. No general egress
policy or SSRF validator exists as a shared control (§13 gap) — the
guards are local to P-03/P-05. P-10 adds one deterministic egress/SSRF
validator; it does not rip out the existing local guards.

### P-04 Dynamic Agent Factory

Creation is gated (reuse-first evaluation, explicit capability
assignment, no automatic inheritance of creator permissions);
lifecycle includes `suspended`; capability catalogue is the single
grant vocabulary. Gaps for P-10: no **security-layer restriction
overlay** (a way for the security engine to bar an agent at
authorization time without editing its factory lifecycle), and no
delegation rule enforcement at a broker — P-04 governs creation, but
nothing brokers *runtime* tool authorization (§7 gap).

### P-05 Universal Digital Execution

The strongest existing enforcement layer: deterministic 10-check
policy engine (identity → status → task → capabilities → scope →
tool → risk → approval → limits → mode), Risk 3 rejected outright,
standing authorizations with exclusions, Windows-first path
validation (`app/execution/paths.py`: lexical rules + resolved
containment, symlink/junction escape refused), credential broker
(`env:NAME` references; values never returned, logged or stored),
per-adapter honesty (filesystem/documents/api operational, **code =
process controls only, NOT a strong sandbox**, browser partial,
desktop disabled). Gaps for P-10: the policy engine is internal to
P-05 — there is no cross-cutting **permission broker** (§7) other
modules can call; no protected-directory classification above
workspace containment (§10.3); no central command allowlist guard
surface (§11) outside execution requests; browser sessions
(`execution_browser_sessions`) bind to agents but carry **no
business scope check** at access time (§12/Scenario 17 gap).

### P-06 Business Creation

Business isolation is enforced via agent `business_ref` checks in
P-07/P-08/P-09; P-06 itself verifies hash-bound approvals before
lifecycle transitions. No P-10 change needed beyond the broker's
business-scope gate reusing the same `business_ref` resolution.

### P-07 Financial Intelligence — the ONLY financial authority

Double-entry ledger, integer minor units, owner-governed limits in
`financial.settings` (agents cannot write — Article 0), spending
approvals verified by exact-parameter hash binding (drift fails
closed), webhook processing with HMAC signature verification →
timestamp/replay window → idempotency → status machine (forged
events are recorded, never confirmed). **P-10 creates no ledger, no
money columns, no execution path.** Its financial guard is an
authorization *evaluation* layer that reads P-07 settings read-only
and verifies P-01 approval bindings; P-07 remains the executor of
record for everything it already governs (§16).

### P-08 Survival and Scaling

Pre-declared experiments with mechanical stop-loss; Level ≥3
approvals owner-verified by P-08 itself (defence in depth around the
P-01 `decide` residual); agents cannot originate CLOSE decisions.
No change needed; P-08's self-verification stays (it becomes
redundant once `decide` is fixed, not wrong).

### P-09 Memory and Continuous Learning

Article 0 write gate (memory is data, never authority — structurally
enforced and grep-tested), secrets blocked before storage with
value-free events, P-07 referenced never copied, hard scope filters
before ranking. P-10 relies on these: the memory-poisoning acceptance
test for P-10 asserts that poisoned memory content cannot move
P-10's policy, broker or financial guard — there is no code path
from memory to any of them.

## 2. Cross-cutting findings

- **No frontend exists in staging** (repository root: `backend/`,
  `docs/`, `scripts/`, `config/` only). §24's Security Command
  Center UI and §19.4's dashboard views are therefore **NOT
  IMPLEMENTED** (P-11), per the P-05–P-09 precedent; P-10 delivers
  the status/aggregation **APIs** those views will consume.
- **No duplicate-system traps sprung:** §25's suggested
  `security_users` / `security_sessions` / `security_roles` /
  `security_approval_requests` tables would duplicate P-01's
  principals, `app_sessions`, permission rules and `approvals`.
  They are **not created** (§2 rule 4 wins over §25's "potential
  entities"). P-10 tables cover only what P-01–P-09 lack.
- **Windows mechanisms:** staging runs on Linux. DPAPI / Windows
  Credential Manager (§9.2, §21) cannot be exercised here — design
  + interface + fake-tested, status **REQUIRES OWNER
  CONFIGURATION**. The working secret backend remains P-05's
  `env:` broker.
- **Encryption at rest:** no cryptography library in the venv and
  none added (house rule: no unnecessary dependencies). Protection
  at rest = OS file permissions + platform mechanisms (owner
  configuration). Status **PARTIALLY IMPLEMENTED**, documented, not
  claimed.
- **Dependency scan tooling:** no pip-audit/bandit in the venv;
  §22 is delivered as documentation + a generated dependency
  inventory from the installed environment, with scanner runs
  recorded as not available rather than faked.

## 3. Integration map (§3.4) — one authority per concern

| Concern | Authoritative source (unchanged) | P-10's role |
|---|---|---|
| User identity / sessions | P-01 `AuthService` + `app_sessions` | Adds revocation/listing surface + login throttling hook |
| Agent identity | P-01 `agents` rows + P-04 factory | Adds restriction overlay consulted at authorization time |
| Permissions | P-01 `PermissionEngine` + `permissions` rules + role defaults | Broker *consumes* engine decisions; never stores parallel rules |
| Approvals | P-01 `ApprovalService` (hash-bound) | `decide` hardened in place; broker verifies bindings before authorizing |
| Security policy | `system_config` key `security.settings` (owner-only writes) | Versioned change history in `security_policy_versions` |
| Financial records / limits | P-07 (ledger, `financial.settings`) | Read-only evaluation; no writes, no money columns |
| Business ownership/scope | P-06 businesses + P-01 agent `business_ref` | Broker enforces scope using the same resolution as P-07–P-09 |
| Memory access | P-09 policy gates | Unchanged; P-10 proves memory cannot reach governance |
| Audit events | P-01 `audit_events` | Hash-chain seal/verify layer + security views over the same log |
| Execution enforcement | P-05 policy engine + path validator + credential broker | Guards wrap/reuse them; broker is the cross-module authorization entry point |
| Emergency state | **New:** `security.settings` mode + `security_emergency_events` | Enforced at the P-10 layer (broker, capabilities, secrets, financial guard, policy writes) |

There is exactly **one policy enforcement mechanism** for
authorization decisions: the P-01 engine, reached directly or via
the P-10 broker. The broker records richer decision context; it
never invents a second rule store.

## 4. The carried residual — disposition

`ApprovalService.decide` gains, in P-01 itself:

1. an **authority check** — the decider must hold `approve_actions`
   under the P-01 engine (owner by role default, or an explicit DB
   grant), evaluated through `PermissionEngine` with the decision
   audited like every other check;
2. a **self-approval refusal** — a non-owner approver may never
   decide a request it originated. The owner deciding an
   owner-initiated governed step (P-02 plan approval, P-06
   declaration/blueprint) remains by design: the owner is the root
   authority and gains nothing they do not already hold; every
   escalation-shaped case (agent or delegate approving its own
   request) is refused. This reasoning is stated here and in the
   implementation report — not left silent.

One pre-existing test pins the old behaviour
(`test_p08_security.py::test_agent_cannot_approve_own_decision`,
whose own comment names this residual): it is updated with a
**P-10 disclosure** comment; its invariant (an agent-approved P-08
decision never becomes APPROVED; the owner path works) is preserved
and now enforced one layer earlier.

## 5. Security invariants for P-10 (Stage 1 output)

1. Deny by default; unknown principal/permission/action/mode →
   deny. Unknown broker actions classify at the highest risk level.
2. Article 0: no agent path — direct, via memory, or via injected
   content — can amend policy, limits, approvals or security state.
   Only the owner principal can write `security.settings`, and only
   through the versioned policy path.
3. Approvals authorize exactly one bound action+parameters;
   replay, expiry, tampering and (non-owner) self-approval refused.
4. Secret values never persist in P-10 tables, never appear in API
   responses, audit details, logs or test fixtures; only pattern
   names, metadata and value-free events.
5. Every P-10 enforcement point fails closed, including when its
   own storage is unavailable.
6. No LLM participates in any P-10 decision; all controls are
   deterministic code.
