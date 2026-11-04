# P-05 Implementation Plan: Universal Digital Execution Engine

Companion to `P05_PRE_IMPLEMENTATION_AUDIT.md`. Conditional on the owner's sequencing choice (§11 of the audit); written so either Option A or B can proceed without rework.

## 1. Architecture

`backend/app/execution/` flat modules: `schemas.py` (request/run/outcome models, the 14 outcomes), `policy.py` (deterministic Risk 0–3 evaluation over `RiskLevel`, prohibition list, standing-authorization checks), `registry.py` (tool lifecycle REGISTERED→AVAILABLE→… with health gates), `requests.py` (request manager: validate → capability → risk → approval → queue), `adapters_fs.py`, `adapters_code.py`, `adapters_api.py` (each a thin class behind one `ExecutionAdapter` protocol), `workflows.py` (definitions, runs, checkpoints, compensation), `scheduler.py` (semaphores over `SystemMonitor` pressure), `evidence.py` (hashes, screenshots-by-reference, verification status), `recovery.py` (restart scan, `REQUIRES_RECONCILIATION`), `governance.py` (approval + emergency + audit wiring). Browser/desktop: protocol definitions plus a `DisabledAdapter` that reports `UNSUPPORTED_BY_ENVIRONMENT` — no new dependencies this phase.

## 2. Execution lifecycle and policy

The 17-step lifecycle of §4 maps onto: `requests.submit` (steps 1–9) → `scheduler` (10–11) → adapter (11–12) → `evidence` (13) → `policy.verify_outcome` (14–16) → audit (17). Risk mapping: Risk 0→`LOW`, 1→`MODERATE`, 2→`HIGH` (approval via `approvals`), 3→`CRITICAL` (hard reject; no approval path). `external_execution_enabled` gates every adapter whose effect leaves the machine; `financial_execution_enabled` gates anything touching money (none in P-05). Completion requires `verify_outcome` to pass against the expected-output schema — a tool returning without exception yields `COMPLETED_WITH_WARNINGS` at best until verified.

## 3. Database changes

Additive migration after `72ee9705e18f` (+ any P-04 revision if Option A): `execution_requests`, `execution_tools`, `execution_runs`, `execution_evidence`, `execution_workspaces`, `browser_sessions`, `workflow_definitions`, `workflow_runs`, `workflow_step_runs`. **Not created:** `execution_approvals` (→ `approvals`), `execution_audit_events` (→ `audit_events`/`system_events`). Constraints: unique idempotency keys, CHECK on status enums, FKs to `tasks`/`agents`/`approvals`, indexes on request/run/agent, `server_default` on new NOT NULL columns, populated-DB round-trip test, implemented `downgrade()`.

## 4. API surface

Under `/api/v1/execution/…` per the brief's list, trimmed to what adapters actually support this phase: requests (5 ops), tools (5), files (6), code (3), api (1), workflows (8), monitoring/evidence/audit (4). Browser and desktop routes are **not registered** while their adapters are disabled — an endpoint that cannot work must not exist. New permission codes (add-only, catalog + owner): `execution.read`, `execution.submit`, `execution.files.write`, `execution.code.run`, `execution.api.call`, `execution.workflows.write`, `execution.admin`.

## 5. Permission and approval checks

Every adapter entry point re-checks: agent identity from the authenticated principal (never client-supplied), agent status, task linkage, capability/permission code, requested scope against `execution_workspaces.permission_scope`, tool status, risk, approval validity (not expired, not self-approved), resource headroom, and the prohibition list — in backend code, before dispatch. Standing authorizations live in `system_configurations` with explicit scope, limit, expiry and revocation fields.

## 6. Security controls before enablement

Path validation by resolved-path containment (not prefix strings), symlink/junction/UNC/ADS/Drive-letter cases tested on both OSes where runnable; atomic writes via temp-file + replace; deletes go to a quarantine workspace with reversible semantics; code adapter: allow-listed interpreter, controlled env, output caps, process-tree kill on timeout, and an explicit `isolation_strength` field reporting *what was verified*, defaulting to "subprocess-with-timeout (weak)" until a stronger mechanism is proven on Windows; API adapter: host allowlist, post-redirect destination revalidation, private/loopback SSRF block, response caps, no blind retry of non-idempotent methods; secrets never in logs, responses, evidence or tables.

## 7. Testing strategy

New modules `test_execution_requests.py`, `test_execution_policy.py`, `test_execution_fs.py`, `test_execution_code.py`, `test_execution_api.py`, `test_execution_workflows.py`, `test_execution_security.py`, `test_execution_api_routes.py`. Deterministic: `NoRuntimeProvider`, local `httpx.MockTransport`-style stubs or a loopback `uvicorn` test server for the API adapter, `tmp_path` workspaces. The 18 security assertions of §25.3 each map to a named test; symlink and traversal tests create real links in `tmp_path`; timeout test runs a sleeper and asserts termination. 521 pre-existing tests stay green at every stage commit.

## 8. Migration, rollback, staging

One additive revision; rollback = `downgrade()` + feature flags (`external_execution_enabled=false` restores today's behaviour exactly since no adapter is reachable). Stages follow §29: 2 core → 3 fs → 4 code → 7 api/documents → 8 workflows → 9 integration (P-04-dependent) → 11 tests/report; Stages 5, 6 and 10 are **reported as disabled/deferred with reasons** (no browsers, no Windows UI Automation, no frontend exist in this environment). Windows setup and startup-health-report documentation land with Stage 11. **P-06 does not begin (§33).**
