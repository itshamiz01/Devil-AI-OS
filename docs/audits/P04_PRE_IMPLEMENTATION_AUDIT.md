# P-04 Pre-Implementation Audit: Dynamic Agent Factory

**Branch:** `arena/ca116d44-devil-ai-os` (from `main` @ `b90402e`) · **Date:** 2026-11-04
**Method:** every figure below was read from the live checkout by introspection (`Base.metadata`, `model_fields`, `dir()`, `openapi()`), not from memory or documentation. Where something is inferred it is labelled as such.

---

## 1. What already exists

| Area | Reality |
|---|---|
| Modules | `backend/app/{api, core, database, events, intelligence, monitoring, opportunities, permissions, tasks}` |
| Database | **34 tables** across four migrations: `03efdae6e24a` (P-01) → `2a904ceb99c4` (P-02) → `5953caf8f23e` → `72ee9705e18f` (P-03) |
| **Agents** | An `agents` table **already exists**: `id, principal_id, name, role, status, metadata_json, created_at, updated_at`, with `AgentRepo` (list/get) and a read-only API `GET /api/v1/agents`, `GET /api/v1/agents/{agent_id}` guarded by `agents.read` |
| Identity | `principals` (`id, kind, name, active, …`); agents hang off principals |
| Permissions | `permissions` + `permission_assignments` (`principal_id, permission_code, resource_scope, effect`); catalog `PERMISSIONS` = **28 codes**; `OWNER_PERMISSIONS` = 28; `SYSTEM_PERMISSIONS` = `events.read, system.read, tasks.read` |
| Approvals | `approvals` table (`requester_id, action, resource, risk, requested_permissions, payload_hash, status, approver_id, expires_at, …`) + `ApprovalService.create/decide/get/verify_binding`; tasks carry `approval_required` and gate on approval |
| Task queue | `tasks` (24 columns incl. `assigned_agent_id`, `idempotency_key`, `retry_count`, `max_retries`, `timeout_seconds`, `deadline`, `cancellation_requested`, `essential`) + `task_executions`; `TaskManager.submit/cancel/pause/resume/retry/apply_emergency_stop/promote_due_retries/expire_stale_approvals/recover_interrupted/health`; handlers registered: `research.sweep, system.echo, system.noop, system.wait` |
| Events | `EVENT_TYPES` = **41 strings** on one auditable bus (`EventBus`), persisted to `system_events` (`source, severity, task_id, correlation_id, payload`); security-grade audit in `audit_events` (`principal_id, resource, action, outcome, correlation_id, payload`) |
| Intelligence (P-02) | `IntelligenceEngine`, **`ModelRouter`**, **`CapabilityRegistry`**, `Orchestrator`, `Planner`, `Replanner`, `DecisionEngine`, `AutonomyController`, `ContextManager`, `MissionInterpreter`, `StructuredOutputParser` in `intelligence/engine.py` (827 lines) |
| Providers | `intelligence/providers.py`: `ModelProvider` protocol, `OllamaProvider` (local, loopback), `NoRuntimeProvider` (deterministic fallback), `GenerationRequest/Result`, `TokenUsage`, `ModelCapabilities`, `ModelHealth` |
| Model registry | `registered_models` (`provider, local, context_window, min_ram_gb, cost_per_1k_tokens, healthy, …`) + `model_usage` (`duration_ms, prompt_tokens, completion_tokens, estimated_cost, success, purpose, correlation_id`) |
| Monitoring | `SystemMonitor.snapshot / resource_pressure / admission_allowed`; `Metrics.increment/snapshot`; `diagnostics` |
| Emergency | `core/emergency.py`: `EmergencyController`, persisted config key, activation/deactivation audit + events (ADR-0013) |
| Config | **57 Settings fields**, prefix built at runtime; resource keys already present: `task_queue_capacity, task_max_concurrency, task_default_timeout, task_max_retries, memory_percent_max, cpu_percent_max, disk_percent_max, inference_max_concurrent, inference_timeout_seconds, mission_max_concurrent_tasks` |
| API | **53 paths / 58 operations**, uniform `envelope()` responses, `require_permission(...)` dependencies, pagination via `limit/offset` |
| Tests | **521 collected**, all passing at this commit |
| Docs | `docs/architecture` 33 files, `docs/decisions` 23 ADRs, `docs/audits` 5 files, `docs/KNOWN_LIMITATIONS.md` 53 rows |
| Deployment | Optional external Postgres behind `AUTONOMUS_DATABASE_URL` (ADR-0023); Vercel builds the FastAPI app via its `fastapi` preset; production currently deployed from `main` |

## 2. What is operational

Task submission → approval gating → execution → retry → audit, end to end (P-01). Mission interpretation → planning → orchestrated execution with model routing and prompt-injection detection (P-02). Opportunity discovery with evidence, scoring and governed rejection (P-03). Owner authentication, session TTL, login rate limiting. Emergency stop that does not consult any model. Resource admission based on live CPU/RAM/disk percentages.

## 3. What is partially implemented (P-04-relevant)

- **Agent registry**: table, repo and read API exist; there is **no creation, update, suspension, retirement, or lifecycle state machine**. `agents.status` is an unvalidated string and `metadata_json` is an unvalidated blob.
- **Permissions**: principal-level grants with scope and effect exist, and the approval workflow is real — but there is **no capability concept** and nothing agent-scoped. `CapabilityRegistry` in P-02 is an in-engine construct, not a persisted, governable registry.
- **Resource management**: system-wide ceilings and admission exist; **per-agent budgets do not**. `inference_max_concurrent` bounds model concurrency globally, which is the hook P-04 needs.
- **Orchestration**: P-02's `Orchestrator` coordinates missions and steps; `tasks.assigned_agent_id` is the only agent↔task link. There is **no assignment ledger, no delegation-depth control, no output contract enforcement at the agent boundary**.
- **Metrics**: `model_usage` measures inference per request; **nothing measures or labels per-agent health or quality**, and nothing distinguishes measured from estimated values.

## 4. What is missing

Agent templates and template versions; capability catalog and agent↔capability grants; creation requests and deterministic creation decisions; lifecycle state machine; assignment ledger; agent health and labelled metrics; configuration history and rollback; factory settings (reusable via `system_configurations`, which exists but is unused by any agent code); delegation limits; backpressure policy for agent creation; any frontend at all (the repository top level is `backend, config, docs, scripts, shared` — there is no React/TypeScript application to extend).

## 5. Reuse decisions (do not duplicate)

| P-04 need | Reuse | Not built |
|---|---|---|
| Agent registry | extend existing `agents` table + `AgentRepo` | a second `agent_registry` table |
| Audit trail | `audit_events` (security-grade) + `system_events` (operational, `source`=agent id) | an `agent_events` table |
| Factory settings | `system_configurations` (key/value, already migrated) | an `agent_factory_settings` table |
| Approvals (Level 2) | `approvals` + `ApprovalService` + `approval_required` task gating | a parallel approval system |
| Emergency stop | `EmergencyController` + `TaskManager.apply_emergency_stop` | a factory-only stop that models could evade |
| Shared inference | `ModelRouter` + `ModelProvider` providers + `registered_models`/`model_usage` | per-agent model processes |
| Task execution | `TaskManager` + `tasks`/`task_executions` | a factory task queue |
| Resource pressure | `SystemMonitor.resource_pressure/admission_allowed` | new psutil polling |
| Prompt-injection defence | P-02 detection + `PromptInjectionDetected`/`SourceRefused` events | a second filter |

## 6. Interfaces requiring extension

1. `agents` table: additive columns (`template_id`, `template_version`, `configuration_version`, `parent_agent_id`, `business_id`, `retired_at`, plus a constrained lifecycle status). Existing columns and the two read endpoints must keep working unchanged.
2. `PERMISSIONS` catalog: new agent codes (`agents.write`, `agents.admin`, template/factory/approval codes). **Note the existing inconsistency in §9.**
3. `EVENT_TYPES`: new agent lifecycle/factory event strings must join the set, or the bus rejects them.
4. `Settings`: new factory limits; every new key must appear in `.env.example` and `CONFIGURATION_REFERENCE.md` because `scripts/audit_config_docs.py` fails the build otherwise.
5. `repositories.py` (150 lines, one class per entity): new repos in the same style.
6. OpenAPI surface: 53 paths today; P-04 adds roughly 30 operations under the existing `/api/v1` prefix and conventions.

## 7. Changes that could break existing functionality

- **Schema**: any non-additive change to `agents` breaks `AgentView`/`AgentRepo` and the two live endpoints. Mitigation: additive migration only, `server_default` on new NOT NULL columns (the P-03 lesson), populated-database round-trip test, implemented `downgrade()`.
- **Permission seeding**: adding codes to `OWNER_PERMISSIONS` changes what a fresh owner bootstrap grants; removing or renaming existing codes would break the 521-test suite's permission tests. Add-only.
- **Event bus**: publishing an event type absent from `EVENT_TYPES` is a defect, not a warning; the set must grow atomically with the code that publishes.
- **Config**: `extra="ignore"` means a typo'd factory key silently does nothing — the same trap that made `AUTONOMUS_DATABASE_URL_direct` inert in production. Every new key gets a test.
- **ModelRouter concurrency**: if P-04 wraps inference in its own semaphore without consulting the router's, the two limits can disagree. Stage 7 must read the router's actual behaviour first.

## 8. Architectural conflicts

- The brief's `agent_registry` / `agent_events` / `agent_factory_settings` tables **conflict with existing tables** (`agents`, `system_events`+`audit_events`, `system_configurations`). Resolution: extend/reuse, per §5, and document the mapping in the implementation report.
- The brief assumes a frontend to extend (Stage 9). **None exists.** Stage 9 is therefore reported as *deferred with reason*, not silently skipped.
- The brief's "approval levels" map cleanly onto the existing `approvals.risk` + `requested_permissions` model; inventing a second risk taxonomy would conflict. Map P-04 levels onto the existing risk field.

## 9. Security gaps found

1. **`agents.read` is in `OWNER_PERMISSIONS` but not in `PERMISSIONS`.** The two live endpoints demand a code that the master catalog does not contain, so it cannot be granted to any non-owner principal through the normal assignment path. P-04 Stage 5 must add agent codes to the catalog (add-only) and test both sets.
2. `agents.metadata_json` accepts arbitrary JSON with no schema — a configuration smuggled in there would be invisible to policy code. P-04 must validate configuration payloads against template schemas before persisting.
3. No capability enforcement exists at any tool boundary, because no tool boundary exists yet. The moment agents execute anything, `require_permission`-style checks must sit in backend code, not prompts (brief §8.2). P-04 introduces the registry and the check point.
4. No secret broker exists. Acceptable today (nothing executes); P-04 must not introduce credential plumbing and must record the constraint (brief §16.3).

## 10. Hardware and resource limitations

- **Target machine (brief):** i7-4712HQ, 16 GB RAM, Quadro K1100M 2 GB, pre-modern CUDA. No CUDA acceleration may be assumed; local inference is CPU-bound and Ollama-loopback only (`ollama_base_url` must stay loopback).
- **This sandbox (where tests run):** 2 CPUs, 3.85 GiB RAM, no GPU. Tests therefore exercise policy logic and the deterministic `NoRuntimeProvider`, never real inference.
- `inference_max_concurrent` and `inference_timeout_seconds` already bound model concurrency globally; per-agent budgets must be ceilings *within* those, never additional parallelism.
- Deployed runtime is Vercel (Python 3.14, region iad1) against a Singapore Postgres when `AUTONOMUS_DATABASE_URL` is set (L-51, L-52); the factory must not assume a writable filesystem or a warm process (L-48).

---

**Conclusion.** The foundation for P-04 is materially stronger than the brief assumes: identity, approvals, task queue, audit bus, emergency stop, model routing and resource admission all exist and are tested. P-04's job is to add the *agent-specific* layer — templates, capabilities, lifecycle, creation governance, assignment, labelled metrics — on top of them, with roughly eight new tables rather than the brief's fourteen logical entities, and to fix the permission-catalog inconsistency it inherits.

---

## Stage 1 verification: compatibility probe

Run against the live checkout after both documents were drafted. **25 assertions, 25 passed, 0 failed.**

- Reuse symbols the plan names all exist and are callable: `AgentRepo`; `ApprovalService.create/decide`; `TaskManager.submit/apply_emergency_stop`; `SystemMonitor.resource_pressure/admission_allowed`; `EmergencyController`; `ModelRouter`; `CapabilityRegistry`; `Orchestrator`; `NoRuntimeProvider`/`OllamaProvider`; `envelope`; `require_permission`.
- `EVENT_TYPES` = 41 members; `Settings` = 57 fields; existing tables = 34; `agents` and `system_configurations` present.
- The nine planned table names have **zero overlap** with the 34 existing tables.
- `agents.read` is absent from `PERMISSIONS` and present in `OWNER_PERMISSIONS` (the gap Stage 5 fixes); the ten planned new permission codes are all currently unused.
- Resource keys the plan relies on exist: `inference_max_concurrent`, `inference_timeout_seconds`, `memory_percent_max`, `cpu_percent_max`, `task_max_concurrency`.
- Note discovered while probing: `PERMISSIONS` is a **list**, not a set — membership tests in P-04 code must not assume set semantics.

No implementation code was written in Stage 1, per the brief's first rule.
