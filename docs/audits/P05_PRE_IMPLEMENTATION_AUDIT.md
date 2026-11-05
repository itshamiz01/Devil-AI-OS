# P-05 Pre-Implementation Audit: Universal Digital Execution Engine

**Branch:** `arena/ca116d44-devil-ai-os` · **Date:** 2026-11-04 · **Method:** introspection of the live checkout; every claim below was checked, not assumed.

## 0. Sequencing finding (read first)

**Superseded 2026-11-05.** This finding was true when the audit was written and is
no longer. P-04 Stages 1–6 are implemented at `862bd70`: the agent registry with an
11-state lifecycle, versioned templates with validation verdicts, a creation engine
with six deterministic decisions, a 29-entry capability catalog across four authority
levels with governed grants, and an assignment ledger whose nine rules gate work
before it is handed to an agent. **P-05's capability-validation component therefore
has a real registry to consult** — `CapabilityService.check()` — and assignment rule 7
already calls it, so the seam P-05's adapters need exists and is tested.

What is still absent from P-04: Stage 7 (`resources.py` — budgets, the shared
inference semaphore, backpressure) and Stage 8 (`monitoring.py`, `versioning.py` —
health observation, metrics, suspension, configuration rollback). P-05's `scheduler.py`
can use P-01's `SystemMonitor` directly, so Stage 7 is not a blocker for it; L-66/L-67
record that nothing observes agent health or sets `IDLE` yet.

**Owner decision 2026-11-05: build P-05 first, then P-06 in full.** That is §11's
Option A with P-04 Stages 1–6 already in place, so capability checks consult a real
registry and Stage 9 integration is genuine rather than stubbed.

## 1. Existing execution capabilities

**None that execute.** Verified: zero occurrences of `subprocess`, `os.system`, `shell=True`, `eval(` or `exec(` in `backend/app` (the single grep hit is a prose comment in `orchestrator.py`). `httpx` appears only in `intelligence/providers.py`, talking to loopback Ollama. `opportunities/sources.py` has an `HttpSourceAdapter` that parses URLs (`urlparse`) but real egress is deny-all (§35, ADR-0021), surfacing as `SourceRefused`. The only genuine filesystem writer is `database/backup.py` (`create_backup`/`verify_backup`/restore, hash-verified, confined to `backup_dir`, ADR-0014). There is no browser, desktop, sandbox, or generic API executor, and no dependency for any of them in `requirements.txt`/`pyproject.toml`.

## 2. Reusable components

| P-05 need | Existing component |
|---|---|
| Risk classification | `intelligence.engine.RiskLevel` = `LOW, MODERATE, HIGH, CRITICAL` — maps 1:1 onto the brief's Risk 0–3 |
| Approval for Risk-2 actions | `approvals` table + `ApprovalService.create/decide/verify_binding` + `tasks.approval_required` gating |
| Execution gating flags | `external_execution_enabled` / `financial_execution_enabled`, **default False** (P-01 phase flags) — the switches P-05 adapters must hang behind |
| Work queue & idempotency | `TaskManager.submit…`, `tasks.idempotency_key`, `task_executions` |
| Workflow schema precedent | `plans` / `plan_steps` with `depends_on`, `parallel_group`, `capability_id`, `risk`, `completion_criteria`, `validation_errors`, `supersedes_plan_id` |
| Audit & events | `audit_events` (security-grade), `system_events` + **58**-member `EVENT_TYPES` bus |
| Emergency stop | `EmergencyController.activate/deactivate/is_active/load/state` + `TaskManager.apply_emergency_stop` |
| Resource pressure | `app.monitoring.system_monitor.SystemMonitor` — verified to expose exactly `snapshot`, `resource_pressure`, `admission_allowed`; ceilings `inference_max_concurrent` (1) and `task_max_concurrency` (2) |
| File integrity patterns | `backup.py` hashing/verification; atomic-ish snapshot-then-verify flow |
| API conventions | `envelope()`, `require_permission`, `limit/offset`, structured errors subclassing `AppError` with a class-level `code`; **83 paths / 91 operations** |

## 3. Missing execution capabilities

Tool registry; execution policy engine; execution request/run/evidence records; managed workspaces; path-validated filesystem adapter; code execution adapter and any isolation mechanism; browser adapter and sessions; desktop adapter; generic API executor and credential broker; workflow run/checkpoint/recovery state; execution scheduler. All are greenfield.

## 4. Existing security controls

Loopback-only bind with startup validation (`host`, `allow_remote_access`); owner authentication with session TTL and login rate limiting; server-side `require_permission` on every route; approval gating before sensitive tasks; deterministic emergency stop; prompt-injection detection (`PromptInjectionDetected`, `SourceRefused`); deny-all egress; no credential columns anywhere in the **43**-table schema; phase flags defaulting to disabled (`external_execution_enabled` and `financial_execution_enabled` both verified `False`).

## 5. Vulnerabilities and limitations

1. ~~`agents.read` absent from the `PERMISSIONS` catalog~~ **WITHDRAWN (corrected 2026-11-04):** `agents.read` is present; P-04 audit §9.1 tested a string against a list of `(code, category, description)` tuples. The residual lesson for P-05 stands: permission-catalog membership must be tested on the code element.
2. No secret broker exists; any API adapter needing credentials has nowhere safe to put them. P-05 must implement a minimal broker (reference-only, values never returned) or keep credentialled integrations disabled.
3. No OS-level sandbox is verifiable here (Linux container, no Docker/Windows Sandbox) and none is confirmed on the target Windows machine. Per §30 rule 22, the code adapter must be **labelled weak-isolation and disabled for untrusted code** until a mechanism is verified on the real machine.
4. Browser automation would add Playwright plus browser binaries — a heavyweight dependency on a 2 GB-GPU CPU-bound machine, against §26's own performance rules; sessions must cap at one and the adapter may legitimately ship disabled.
5. The deployed Vercel instance has an ephemeral, largely read-only filesystem and no process guarantees: **the execution engine must remain disabled there** (`external_execution_enabled=false`), and P-05 must not assume it runs only on Windows-desktop.

## 6. Existing agent-to-tool interfaces

No tool dispatch, but the agent→work path is no longer absent. Agents are created
through `AgentFactory`, hold governed capability grants, and receive work through
`AssignmentService.assign`, whose nine rules validate the task, the agent's state,
delegation depth, business scope, held capabilities, template escalation and
concurrency budget before a ledger row is written. P-02's `Orchestrator` converts
plans into `TaskManager` submissions.

So P-05 sits behind **two** existing seams, not beside either: an execution request
should be tied to a task, and work reaching an agent has already passed assignment
validation. What is still missing is the last hop — nothing turns an assignment into
a tool invocation, because no adapter exists. `filesystem.read`, `filesystem.write`,
`code.execute`, `execution.tool`, `external.network`, `browser.control` and
`distribution.publish` are declared in the capability catalog and **disabled** pending
this phase, which is the catalog already saying what P-05 owes.

## 7. Database requirements

The brief's ten logical tables reduce to **eight new tables**: `execution_requests`, `execution_tools`, `execution_runs`, `execution_evidence`, `execution_workspaces`, `browser_sessions`, `workflow_definitions`+`workflow_runs`+`workflow_step_runs` (nine rows of logic, but `workflow_step_runs` folds into `execution_runs` references) — while `execution_approvals` is **not created** (reuse `approvals`) and `execution_audit_events` is **not created** (reuse `audit_events`/`system_events`). Final count to be fixed in the plan after Stage 2 schema design.

## 8. Required integrations

P-01 tasks/approvals/emergency/permissions; P-02 `RiskLevel` (verified in `app.intelligence.engine` as `LOW, MODERATE, HIGH, CRITICAL`), `ModelRouter`, prompt-injection handling; P-03 `HttpSourceAdapter` URL-validation precedent; **P-04 (present through Stage 6)** capability catalog and `CapabilityService.check()`, agent lifecycle, versioned templates, creation decisions and the assignment ledger — so Stage 9 integration is genuine. Still absent: P-04 Stage 7 resource budgets and Stage 8 health observation.

## 9. Resource constraints

Sandbox (where tests run): 2 CPUs, 3.85 GiB RAM, no GPU. Target (brief): i7-4712HQ, 16 GB, Quadro K1100M 2 GB, pre-modern CUDA. Concurrency ceilings already configured; browser sessions capped at 1; subprocess count bounded by a semaphore; no adapter may spawn per-request processes.

## 10. Compatibility risks

Introducing `subprocess` is the first untrusted-process code in the codebase and must not weaken loopback/auth guarantees. New tables additive-only with `downgrade()`; `EVENT_TYPES` grows atomically; every new Settings key must pass `scripts/audit_config_docs.py`; the **838** existing tests must stay green (verified by collection at `3bc19ed`); nothing may write outside managed workspace roots; and the deliberately brittle chain-depth tripwire (`test_the_chain_is_nine_revisions_deep`) must be hand-bumped with the new revision's DDL review recorded in its docstring, never derived.

## 11. Proposed architecture and sequencing options

`backend/app/execution/` as flat modules mirroring repository convention: `requests.py`, `policy.py`, `registry.py`, `adapters_fs.py`, `adapters_code.py`, `adapters_api.py`, `workflows.py`, `scheduler.py`, `evidence.py`, `recovery.py`, `schemas.py`; browser and desktop ship as **interface-only, disabled, documented** until verified on real hardware.

- **Option A (recommended):** finish P-04 first, then P-05 — its capability checks
  then consult a real registry and Stage 9 is genuine.
- **Option B:** build P-05 Stages 2–4 against P-01 permission codes now, deferring
  Stage 9 and all agent-capability integration; risk: two permission models to
  reconcile later.
- **Option C:** P-05 fully now with stubbed P-04 seams — rejected: it would fake an
  integration, violating §30 and this project's evidence rules.

**Chosen 2026-11-05: Option A**, and better than recommended — P-04 Stages 1–6 are
already delivered, so Option A's benefit (a real capability registry) is available
now without waiting for Stages 7–8, which P-05 does not need. Option B's risk of two
permission models to reconcile does not arise: P-05 adds its seven codes to the same
35-member catalog P-04 extended, add-only, owner-bootstrap, never in
`SYSTEM_PERMISSIONS`.
