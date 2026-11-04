# P-05 Pre-Implementation Audit: Universal Digital Execution Engine

**Branch:** `arena/ca116d44-devil-ai-os` · **Date:** 2026-11-04 · **Method:** introspection of the live checkout; every claim below was checked, not assumed.

## 0. Sequencing finding (read first)

**P-04 is not implemented.** It exists only as `docs/audits/P04_PRE_IMPLEMENTATION_AUDIT.md` and `P04_IMPLEMENTATION_PLAN.md` (commit `e17dbeb`, Stage 1 of 10). P-05 §2 and Stage 9 depend on P-04's agent registry extensions, capability registry, templates and lifecycle — **none of which exist as code**. Consequently P-05's capability-validation component has no persisted capability registry to consult today. This audit therefore plans P-05 against what exists (P-01–P-03) and marks every P-04 dependency explicitly; the owner must choose the sequencing (see §11).

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
| Audit & events | `audit_events` (security-grade), `system_events` + 41-member `EVENT_TYPES` bus |
| Emergency stop | `EmergencyController.activate/deactivate/is_active/load/state` + `TaskManager.apply_emergency_stop` |
| Resource pressure | `SystemMonitor.snapshot/resource_pressure/admission_allowed`; ceilings `inference_max_concurrent`, `task_max_concurrency` |
| File integrity patterns | `backup.py` hashing/verification; atomic-ish snapshot-then-verify flow |
| API conventions | `envelope()`, `require_permission`, `limit/offset`, structured errors; 53 paths / 58 ops today |

## 3. Missing execution capabilities

Tool registry; execution policy engine; execution request/run/evidence records; managed workspaces; path-validated filesystem adapter; code execution adapter and any isolation mechanism; browser adapter and sessions; desktop adapter; generic API executor and credential broker; workflow run/checkpoint/recovery state; execution scheduler. All are greenfield.

## 4. Existing security controls

Loopback-only bind with startup validation (`host`, `allow_remote_access`); owner authentication with session TTL and login rate limiting; server-side `require_permission` on every route; approval gating before sensitive tasks; deterministic emergency stop; prompt-injection detection (`PromptInjectionDetected`, `SourceRefused`); deny-all egress; no credential columns anywhere in the 34-table schema; phase flags defaulting to disabled.

## 5. Vulnerabilities and limitations

1. `agents.read` absent from the `PERMISSIONS` catalog (P-04 audit §9.1) — unresolved; P-05 permission codes must not repeat the mistake.
2. No secret broker exists; any API adapter needing credentials has nowhere safe to put them. P-05 must implement a minimal broker (reference-only, values never returned) or keep credentialled integrations disabled.
3. No OS-level sandbox is verifiable here (Linux container, no Docker/Windows Sandbox) and none is confirmed on the target Windows machine. Per §30 rule 22, the code adapter must be **labelled weak-isolation and disabled for untrusted code** until a mechanism is verified on the real machine.
4. Browser automation would add Playwright plus browser binaries — a heavyweight dependency on a 2 GB-GPU CPU-bound machine, against §26's own performance rules; sessions must cap at one and the adapter may legitimately ship disabled.
5. The deployed Vercel instance has an ephemeral, largely read-only filesystem and no process guarantees: **the execution engine must remain disabled there** (`external_execution_enabled=false`), and P-05 must not assume it runs only on Windows-desktop.

## 6. Existing agent-to-tool interfaces

None. Agents today are rows in `agents` with a read-only API; nothing dispatches tools. P-02's `Orchestrator` converts plans into `TaskManager` submissions — that is the only agent→work path, and it is the seam P-05 should sit behind, not beside.

## 7. Database requirements

The brief's ten logical tables reduce to **eight new tables**: `execution_requests`, `execution_tools`, `execution_runs`, `execution_evidence`, `execution_workspaces`, `browser_sessions`, `workflow_definitions`+`workflow_runs`+`workflow_step_runs` (nine rows of logic, but `workflow_step_runs` folds into `execution_runs` references) — while `execution_approvals` is **not created** (reuse `approvals`) and `execution_audit_events` is **not created** (reuse `audit_events`/`system_events`). Final count to be fixed in the plan after Stage 2 schema design.

## 8. Required integrations

P-01 tasks/approvals/emergency/permissions; P-02 `RiskLevel`, `ModelRouter`, prompt-injection handling; P-03 `HttpSourceAdapter` URL-validation precedent; **P-04 (absent)** capability registry, agent lifecycle, templates — Stage 9 cannot complete without it.

## 9. Resource constraints

Sandbox (where tests run): 2 CPUs, 3.85 GiB RAM, no GPU. Target (brief): i7-4712HQ, 16 GB, Quadro K1100M 2 GB, pre-modern CUDA. Concurrency ceilings already configured; browser sessions capped at 1; subprocess count bounded by a semaphore; no adapter may spawn per-request processes.

## 10. Compatibility risks

Introducing `subprocess` is the first untrusted-process code in the codebase and must not weaken loopback/auth guarantees. New tables additive-only with `downgrade()`; `EVENT_TYPES` grows atomically; every new Settings key must pass `scripts/audit_config_docs.py`; the 521 existing tests must stay green; nothing may write outside managed workspace roots.

## 11. Proposed architecture and sequencing options

`backend/app/execution/` as flat modules mirroring repository convention: `requests.py`, `policy.py`, `registry.py`, `adapters_fs.py`, `adapters_code.py`, `adapters_api.py`, `workflows.py`, `scheduler.py`, `evidence.py`, `recovery.py`, `schemas.py`; browser and desktop ship as **interface-only, disabled, documented** until verified on real hardware.

- **Option A (recommended):** finish P-04 Stages 2–10 first, then P-05 — its capability checks then consult a real registry and Stage 9 is genuine.
- **Option B:** build P-05 Stages 2–4 (core, policy, filesystem, code) against P-01 permission codes now, deferring Stage 9 and all agent-capability integration until P-04 lands; risk: two permission models to reconcile later.
- **Option C:** P-05 fully now with stubbed P-04 seams — rejected: it would fake an integration, violating §30 and this project's evidence rules.
