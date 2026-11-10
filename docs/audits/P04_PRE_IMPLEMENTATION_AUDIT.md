# P-04 PRE-IMPLEMENTATION AUDIT — Dynamic Agent Factory

**Stage 1 of P-04 (§3 / §24). Produced BEFORE any P-04 implementation code.**
Baseline test run at audit time (9 Nov 2026, staging, `.venv/bin/python -m pytest -q`):
**172 passed, 0 failed, 1 warning in 30.61s** (P-01: 76, P-02: 35, P-03: 61).
The warning is the pre-existing Starlette `TestClient` deprecation notice.

---

## 1. What already exists

| Area | State of the code (verified by inspection) |
|---|---|
| Backend | FastAPI app (`backend/app/main.py`), prefix `/api/v1`, uniform success/error envelope, correlation-ID middleware, typed `AutonomusError` hierarchy (`app/core/exceptions.py`). |
| Persistence | SQLAlchemy 2.x + Alembic. Three migrations form one linear chain: `b36fd80092d2` (P-01, 9 tables) → `c7a21f9e04b3` (P-02, +5 tables) → `a8ddb3e7260d` (P-03, +11 tables) = **26 tables at head**. Tests run with `auto_migrate=False` (`Base.metadata.create_all`); production/staging startup runs Alembic. |
| P-01 Core OS | Task engine (persistence-first bounded queue, handler registry — tasks execute ONLY through named handlers, retry/backoff, startup recovery), event bus with persistence of critical events to `system_events`, deny-by-default `PermissionEngine` (DB rules → role defaults → deny; every check audited), hash-bound `ApprovalService` (SHA-256 of action+resource+parameters), append-only `audit_events` (no update/delete API), `SystemMonitor` (psutil resources + threshold violations + admission block), scrypt owner auth + service token, `Settings` with modes `simulation/supervised/controlled/emergency`. |
| Agent registry (P-01) | `agents` table + `AgentRepository` + read-only `GET /agents`, `GET /agents/{id}`. Columns: id, name, role, parent_agent_id, business_ref, objective, model_profile, status (free string, default `"created"`), budget (JSON), timestamps. Docstring is explicit: *"registration metadata + lifecycle status only; no autonomous creation in P-01."* |
| P-02 Intelligence | `IntelligenceService` on the P-01 substrate: baseline planner + provider interface (Ollama adapter / disabled cloud stub / FakeProvider), `ModelRouter` (records reasons, resource-aware), decision records, verifier, `model_profiles` (owner/governance-editable only). Mode enforcement: plan execution refused in `simulation`/`emergency`. |
| P-03 Opportunities | `OpportunityService`: deterministic discovery/scoring (weights in owner-governed `system_config` via `ConfigRepository`, ADR-005), lifecycle state machine, evidence discipline, research executed ONLY as P-01 tasks via the registered `opportunity.research` handler, SSRF-guarded transports. |
| Config store | `system_config` table + `ConfigRepository.get/set` — the established home for owner-governed runtime configuration (P-03 scoring precedent). |
| Tests | 15 test files, 172 tests: unit / integration / security / failure per phase (`test_p02_*`, `test_p03_*` …), shared `conftest.py` with `Application` fixture (real startup, `create_all` schema), owner/service principals, `wait_for_status` helper. |
| Docs | `docs/architecture/` (21 docs), `docs/decisions/` ADR-001…005, phase reports for P-01…P-03, `docs/PHASE_TRACKER.md`, README with phase status. `docs/audits/` exists and is empty. |

## 2. What is operational

- Task submission/execution/cancellation/recovery through the handler registry, with permission checks and audit on every check.
- Permission enforcement (deny-by-default) and hash-bound approvals end-to-end (proven by P-01/P-02 security suites).
- P-02 planning with recorded decisions; P-03 research pipeline with real (if partial) live-source behaviour.
- Resource monitoring with real measured host CPU/RAM/disk (psutil) and threshold-based admission blocking.
- Event bus + persisted critical events; mode field on `Settings` honoured by P-02/P-03.

## 3. What is partially implemented

- **`agents` table**: identity + parent + business_ref + objective + model_profile + budget exist; there is **no** agent_type, description, template link, configuration version, creator record, security classification, last-activity or retirement timestamp; `status` is an unconstrained string with a P-01 vocabulary (`created`), not the §11 state machine.
- **Approvals**: the framework is complete, but no factory-specific actions (`agent_factory.create_agent`, `agent_factory.grant_capability`) exist yet.
- **Permissions**: the engine enforces arbitrary permission *strings* (DB rules are matched by string equality; role defaults only cover the 12 P-01 `Permission` values). There is no capability catalogue, no per-agent grant ledger (grants would be bare `permissions` rows with no expiry/revocation/status metadata).
- **Monitoring**: host-level only. No per-agent health, metrics, or failure accounting.
- **Model routing**: shared and provider-independent, but nothing enforces an inference-concurrency gate at factory level, and no code prevents a future feature from instantiating per-agent providers (convention only).

## 4. What is missing (P-04 must build)

- Agent template system (templates, versions, validation, publish/deprecate/clone/compare/restore) — nothing exists.
- Dynamic creation pipeline + deterministic creation decisions + creation requests — nothing exists.
- Capability registry (catalogue with risk/approval level/scope/action class/supported flag) — nothing exists.
- Agent grant ledger (grants with approval reference, expiry, revocation, status) — nothing exists.
- Agent↔task assignment records with the §9.1 fields, §9.2 validation, delegation chains and §9.4 output contracts — `tasks.assigned_agent_id` exists but carries none of this.
- Agent lifecycle state machine (§11), health model (§12.3), per-agent metrics with measured/estimated/unavailable labelling (§12), configuration history + rollback (§13), scaling policy (§14), backpressure ladder (§10.4), emergency stop (§16.5), factory settings, and the P-09 memory interface (§15).
- All §19 write/management endpoints (the agents API is read-only today).
- Frontend: **none exists anywhere in staging** — §20 work is conditional on an existing screen; there is none (see §9 of this audit).

## 5. Components to reuse (do NOT rebuild)

| P-04 need (§17/§19) | Reuse decision |
|---|---|
| `agent_registry` | **Extend the existing `agents` table** (it IS the registry; P-01 docstring + `tasks.assigned_agent_id` FK + `AgentRepository` all build on it). Add columns additively; do not create a parallel registry table. |
| `agent_events` | **No new table.** `audit_events` (append-only, actor/target indexed by action) + persisted `system_events` already carry every §16.4 record. `GET /agents/{id}/events` is served from the audit trail filtered by actor/target = agent id. |
| `agent_factory_settings` | **No new table.** `system_config` + `ConfigRepository` is the established owner-governed settings store (P-03 scoring precedent). Factory settings live under one namespaced key. |
| Permission enforcement | **P-01 `PermissionEngine`, unchanged.** Capability grants are mirrored into `permissions` as DB allow rules (principal_type=`agent`, permission=<capability name>), so capability checks at assignment/tool-use time go through the same deny-by-default engine as everything else; revocation writes an explicit deny (deny always wins in the engine). |
| Approvals | **P-01 `ApprovalService`, unchanged.** Factory approvals are hash-bound to exact parameters (creation: request id + template id/version + sorted capabilities; grant: agent id + capability + scope). |
| Audit | **`audit_events` via `AuditRepository`** for every §16.4 item; factory also emits bus events persisted via the existing critical-event subscriber. |
| Task execution | **P-01 `TaskManager` + handler registry.** An assignment submits a real task with `assigned_agent_id`; the factory adds NO second queue. |
| Model inference | **P-02 `ModelRouter` via `application.intelligence`** — one shared router for all logical agents; the factory only adds a concurrency gate counter. |
| Resources | **P-01 `SystemMonitor`** (`resources()`, `threshold_violations()`, `admission_block_reason()`, queue stats). |
| Research capability backing | **P-03 `opportunity.research` handler** is the real execution path behind the `web_research` capability. |

## 6. Genuinely new tables (justified — no existing home)

One additive migration revising `a8ddb3e7260d`:

| New table | Why it cannot reuse an existing table |
|---|---|
| `agent_templates` | No template concept exists anywhere. |
| `agent_template_versions` | Immutable version snapshots of template configuration; `system_config` is mutable key/value and cannot hold per-version validation state/history. |
| `agent_capabilities` | The catalogue (risk, approval level, action class, supported flag, resource requirements) has no existing representation; `permissions` rows are grants, not a catalogue. |
| `agent_permissions` | Grant *ledger*: approval reference, expiry, revocation, status. The P-01 `permissions` table has none of these columns; the ledger is the lifecycle record, the `permissions` mirror is the enforcement artefact. |
| `agent_assignments` | §9.1 assignment fields (required capabilities, output schema, quality requirements, delegation parent/depth, business ref, contract verdict) do not fit `tasks` without polluting the P-01 engine's table. |
| `agent_health` | Point-in-time health snapshots per agent; no per-agent monitoring store exists. |
| `agent_metrics` | Per-agent metric series with mandatory `measurement_type` (measured/estimated/unavailable) labelling. |
| `agent_configuration_history` | §13 versioned config snapshots with change reason/author/approval reference + rollback source. |
| `agent_creation_requests` | The §7.3 deterministic decision record (requirement, decision, reasons, approval binding) — approvals alone do not record REJECT/QUEUE/REUSE decisions. |

Plus **additive columns on `agents`**: `agent_type`, `description`, `template_id` (FK), `template_version`, `configuration_version`, `created_by_type`, `created_by_id`, `security_classification`, `last_activity_at`, `retired_at`. No column is renamed, retyped or dropped; `status` keeps its type — only its vocabulary is governed for factory-managed agents.

## 7. Interfaces requiring extension

- `EventType` (+ P-04 agent events) and `CRITICAL_EVENT_TYPES` (+ state-changed, permission-changed, emergency-stop) in `app/events/events.py` — additive enum members.
- `Application` assembly: construct `AgentFactoryService`, seed capability catalogue + starter templates (same pattern as P-02 profiles / P-03 sources). **No new task handlers are registered** (see breakage risk R2).
- `app/api/routes/agents.py`: extended with the §19 management endpoints (the existing GETs stay byte-compatible); new `app/api/routes/agent_factory.py` for templates/factory/capabilities/admin. `AgentOut` gains optional fields (additive).
- `Settings`: no new env settings required; factory limits are runtime settings in `system_config` (owner-governed), not env.

## 8. Breakage risks (verified in the test suite)

- **R1 — migration-head assertions.** `tests/test_p02_integration.py:200` and `tests/test_p03_integration.py:84` assert the Alembic head is exactly `a8ddb3e7260d`. The P-04 migration necessarily advances the head. Both assertions must be updated to the new revision id with strictness preserved (exact head equality), and the change disclosed in the P-04 test report — the same disclosed-maintenance standard P-03 applied.
- **R2 — handler-registry set assertion.** `tests/test_p02_security.py:69` asserts the task handler registry contains an exact set. Registering any new handler would break it. **Mitigation by design: P-04 registers no new task handlers** — assignments execute through the existing handlers (`core.*`, `opportunity.research`). No test change needed.
- **R3 — legacy agent statuses.** The `agents.status` default is `"created"` (P-01 vocabulary). The §11 machine has no `CREATED` state. Mitigation: factory code always sets status explicitly; the transition graph includes a documented legacy bridge `created → initializing/retiring` so pre-P-04 registry rows can be adopted without a data rewrite. No existing test asserts agent status values (verified by grep).
- **R4 — `AgentOut` shape.** P-01 clients/tests read the existing fields; new fields are additive with defaults, existing fields unchanged.
- **R5 — startup time / seeding.** Seeding must be idempotent (P-02/P-03 pattern: seed-if-absent) so the 172 existing tests that boot the full application are unaffected.

## 9. Architectural conflicts

- **§20 frontend**: the prompt conditions UI work on an existing agent-management screen. **No frontend exists in staging** (no web app was ever built; P-11 owns the Command Center). Resolution (per tasking): expose all §20 operational data through the API (`/agent-factory/status`, `/resources`) and build no UI. Recorded as a deliberate, documented deviation.
- **§18 module tree** shows a deep `backend/agents/…` hierarchy; the repo convention (P-02 `app/intelligence/`, P-03 `app/opportunities/`) is one flat package of focused modules per phase. Resolution: follow the repo convention — `backend/app/agents/` with separated modules (constants, lifecycle, validation, templates, capabilities, resources, scaling, memory interface, service) + models/repositories in the established `app/database/` locations.
- **§17 table list vs §17's own caveat** ("not permission to create duplicate versions of existing tables"): resolved by the reuse matrix in §5 above — 3 of the 12 concepts are served by existing tables, 9 are genuinely new, and `agents` is extended rather than duplicated.
- **Capability `memory_write`, `file_*`, `api_*`, `code_generation`, `sandboxed_code_execution`, `browser_interaction`, `external_communication`**: no backing module exists (P-05 owns execution; P-09 owns the memory engine). Per §8.1 and Rule 14 they are catalogued with `supported = false` — requestable through the approval flow for the record, **never grantable** in P-04 — instead of being simulated.

## 10. Security gaps found in the existing system (relevant to P-04)

- The agents API being read-only meant no write-side agent attack surface existed; P-04 creates one, so every new endpoint must be permission-gated server-side (`manage_agents` for administration; owner-only for settings/approvals/emergency stop) — the P-01 `require_permission` dependency and principal checks provide this.
- `ROLE_DEFAULTS[agent]` includes `execute_tools`/`submit_tasks` by role default. Capability checks therefore must NOT rely on the 12 P-01 permission names for factory governance; they use capability names (absent from role defaults), so an agent has **zero** factory capabilities until an explicit grant exists. Verified in `policies.py`.
- Audit is append-only *by API* (no update/delete endpoints), not cryptographically tamper-proof — unchanged P-01 limitation, carried honestly (P-10 scope).
- No rate limiting exists on P-01 endpoints generally; the factory enforces its own creation-rate limit in the decision engine (setting, default 10/hour) rather than at HTTP level.

## 11. Hardware / resource limitations

- Target machine (owner-provided, P-04 prompt §2; `docs/reports/AI_HARDWARE_FEASIBILITY.md` verdict): i7-4712HQ (Haswell 4C/8T), 16 GB RAM, Quadro K1100M 2 GB — **compute capability 3.0, below Ollama's 5.0 minimum → CPU-only inference**. Consequences baked into the design: agents are pure configuration rows (no process per agent — §10), default `max_concurrent_inference_requests = 1`, conservative default agent ceilings (12 total / 8 active), and all factory logic is deterministic Python with no model dependency.
- This sandbox has **no LLM at all** (Ollama absent; cloud disabled). The factory must be — and is designed to be — fully functional without one; an LLM may only ever *recommend*, deterministic policy decides (P-02/P-03 pattern).

## 12. Audit conclusion

The P-01 substrate (tasks, permissions, approvals, audit, events, monitoring, config store) plus the P-02 router and P-03 handler give P-04 everything it needs without new frameworks, new dependencies, or schema rewrites. The build is: extend `agents`, add 9 tables in one migration, add one domain package + two route modules, wire one service into startup. Proceed to `P04_IMPLEMENTATION_PLAN.md`.
