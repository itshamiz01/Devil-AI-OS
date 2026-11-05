# P-05 Implementation Plan: Universal Digital Execution Engine

Companion to `P05_PRE_IMPLEMENTATION_AUDIT.md`. **Refreshed 2026-11-05** at
`3bc19ed`: the owner chose Option A (P-05 first, then P-06 in full), and P-04
Stages 1–6 are delivered, so the capability registry, agent lifecycle, versioned
templates and assignment ledger this plan integrates with all exist as tested code.
Counts below are the post-Stage-6 baseline, re-verified live rather than carried over
from the 2026-11-04 draft.

## 0. Unresolved contract inputs (blocking Stage 2)

This plan was written from the P-05 brief, which is **not in the repository** —
`docs/prompts/` holds only `P-00_EXECUTION_CONTRACT.md`. Several enumerations the
plan depends on are therefore referenced by section number without their contents,
and Stage 2 cannot be written honestly until they are supplied. What follows is the
exact gap, itemised, with what *is* recoverable so the ask is as small as possible.

**Recoverable from this plan and the audit — no input needed:**

* The nine tables and the two deliberately not created (§3).
* Risk mapping: Risk 0→`LOW`, 1→`MODERATE`, 2→`HIGH` (approval via `approvals`),
  3→`CRITICAL` (hard reject, no approval path), over the existing
  `app.intelligence.engine.RiskLevel` — verified live as exactly those four members.
* The seven permission codes (§4) and the API operation counts: requests 5, tools 5,
  files 6, code 3, api 1, workflows 8, monitoring/evidence/audit 4.
* The staging order and which stages are disabled with reasons (§8).
* The security controls (§6) and the adapter re-check list (§5).
* The gating flags, verified live: `external_execution_enabled` and
  `financial_execution_enabled`, both default `False`.

**Not recoverable — required before Stage 2 can be written:**

| Missing | Where it is referenced | Why it blocks |
|---|---|---|
| **The 14 execution outcomes.** Only three are named anywhere: `UNSUPPORTED_BY_ENVIRONMENT`, `COMPLETED_WITH_WARNINGS`, `REQUIRES_RECONCILIATION`. Eleven are not. | §1 (`schemas.py` — "request/run/outcome models, the 14 outcomes"), §2 | This is the return contract every adapter, every run row, every test and every API response carries. Inventing eleven status names would propagate through all eleven stages and every later phase that reads an execution result. |
| **The tool lifecycle states** after `REGISTERED → AVAILABLE → …` | §1 (`registry.py`) | The registry's CHECK constraint and its health gates are built from this vocabulary. |
| **The content of the 17-step execution lifecycle.** Only the step *boundaries* are recoverable (submit 1–9, scheduler 10–11, adapter 11–12, evidence 13, verify 14–16, audit 17), not what each step requires. | §2 | `requests.submit` must implement steps 1–9 in order; without them the ordering of validation, capability, risk and approval checks is a guess. |
| **The 18 security assertions of §25.3** | §7 ("each map to a named test") | Stage 11's security test module is specified as one named test per assertion. |
| **§26's performance rules** | audit §5.4 cites them as the reason browser automation is heavyweight | Needed to justify the concurrency caps and the disabled browser adapter with the brief's own rule rather than only mine. |

**Deliberate decision:** Stage 2 will not proceed by inventing these. The P-04
precedent is recorded in `docs/architecture/AGENT_ASSIGNMENTS.md` §1, where the nine
assignment rules were missing from the repository: they were reconstructed from
documented sources *and each rule was made to name its source*, so a difference from
the owner's list is a visible documentation fix rather than a buried assumption. That
worked because the governance document and the schema supplied enough evidence to
derive nine defensible rules. Here the evidence supplies three outcome names out of
fourteen, which is not enough to derive the rest — a guessed outcome vocabulary is
worse than a stated gap, because every adapter and test would then encode the guess.

## 1. Architecture

`backend/app/execution/` flat modules: `schemas.py` (request/run/outcome models, the 14 outcomes), `policy.py` (deterministic Risk 0–3 evaluation over `RiskLevel`, prohibition list, standing-authorization checks), `registry.py` (tool lifecycle REGISTERED→AVAILABLE→… with health gates), `requests.py` (request manager: validate → capability → risk → approval → queue), `adapters_fs.py`, `adapters_code.py`, `adapters_api.py` (each a thin class behind one `ExecutionAdapter` protocol), `workflows.py` (definitions, runs, checkpoints, compensation), `scheduler.py` (semaphores over `SystemMonitor` pressure), `evidence.py` (hashes, screenshots-by-reference, verification status), `recovery.py` (restart scan, `REQUIRES_RECONCILIATION`), `governance.py` (approval + emergency + audit wiring). Browser/desktop: protocol definitions plus a `DisabledAdapter` that reports `UNSUPPORTED_BY_ENVIRONMENT` — no new dependencies this phase.

## 2. Execution lifecycle and policy

The 17-step lifecycle of §4 maps onto: `requests.submit` (steps 1–9) → `scheduler` (10–11) → adapter (11–12) → `evidence` (13) → `policy.verify_outcome` (14–16) → audit (17). Risk mapping: Risk 0→`LOW`, 1→`MODERATE`, 2→`HIGH` (approval via `approvals`), 3→`CRITICAL` (hard reject; no approval path). `external_execution_enabled` gates every adapter whose effect leaves the machine; `financial_execution_enabled` gates anything touching money (none in P-05). Completion requires `verify_outcome` to pass against the expected-output schema — a tool returning without exception yields `COMPLETED_WITH_WARNINGS` at best until verified.

## 3. Database changes

Additive migration after **`d577d056a63b`** (the P-04 Stage 6 head; the chain is nine revisions deep and becomes ten): `execution_requests`, `execution_tools`, `execution_runs`, `execution_evidence`, `execution_workspaces`, `browser_sessions`, `workflow_definitions`, `workflow_runs`, `workflow_step_runs`. **Not created:** `execution_approvals` (→ `approvals`), `execution_audit_events` (→ `audit_events`/`system_events`). Constraints: unique idempotency keys, CHECK on status enums, FKs to `tasks`/`agents`/`approvals`, indexes on request/run/agent, `server_default` on new NOT NULL columns, populated-DB round-trip test, implemented `downgrade()`.

## 4. API surface

Under `/api/v1/execution/…` per the brief's list, trimmed to what adapters actually support this phase: requests (5 ops), tools (5), files (6), code (3), api (1), workflows (8), monitoring/evidence/audit (4). Browser and desktop routes are **not registered** while their adapters are disabled — an endpoint that cannot work must not exist. New permission codes (add-only, catalog + owner): `execution.read`, `execution.submit`, `execution.files.write`, `execution.code.run`, `execution.api.call`, `execution.workflows.write`, `execution.admin`.

## 5. Permission and approval checks

Every adapter entry point re-checks: agent identity from the authenticated principal (never client-supplied), agent status, task linkage, capability/permission code, requested scope against `execution_workspaces.permission_scope`, tool status, risk, approval validity (not expired, not self-approved), resource headroom, and the prohibition list — in backend code, before dispatch. Standing authorizations live in `system_configurations` with explicit scope, limit, expiry and revocation fields.

## 6. Security controls before enablement

Path validation by resolved-path containment (not prefix strings), symlink/junction/UNC/ADS/Drive-letter cases tested on both OSes where runnable; atomic writes via temp-file + replace; deletes go to a quarantine workspace with reversible semantics; code adapter: allow-listed interpreter, controlled env, output caps, process-tree kill on timeout, and an explicit `isolation_strength` field reporting *what was verified*, defaulting to "subprocess-with-timeout (weak)" until a stronger mechanism is proven on Windows; API adapter: host allowlist, post-redirect destination revalidation, private/loopback SSRF block, response caps, no blind retry of non-idempotent methods; secrets never in logs, responses, evidence or tables.

## 7. Testing strategy

New modules `test_execution_requests.py`, `test_execution_policy.py`, `test_execution_fs.py`, `test_execution_code.py`, `test_execution_api.py`, `test_execution_workflows.py`, `test_execution_security.py`, `test_execution_api_routes.py`. Deterministic: `NoRuntimeProvider`, local `httpx.MockTransport`-style stubs or a loopback `uvicorn` test server for the API adapter, `tmp_path` workspaces. The 18 security assertions of §25.3 each map to a named test; symlink and traversal tests create real links in `tmp_path`; timeout test runs a sleeper and asserts termination. **838** pre-existing tests stay green at every stage commit (verified by collection).

## 8. Migration, rollback, staging

One additive revision; rollback = `downgrade()` + feature flags (`external_execution_enabled=false` restores today's behaviour exactly since no adapter is reachable). Stages follow §29: 2 core → 3 fs → 4 code → 7 api/documents → 8 workflows → 9 integration (P-04-dependent) → 11 tests/report; Stages 5, 6 and 10 are **reported as disabled/deferred with reasons** (no browsers, no Windows UI Automation, no frontend exist in this environment). Windows setup and startup-health-report documentation land with Stage 11. **P-06 does not begin (§33).**
