# P-14 Integration Matrix — AUTONOMUS (Stage A, Audit Only)

> **Scope/method.** Stage A is inspection only: no code was changed and no tests were created by this audit.
> Every link below is classified under P-14 §21 rule 14 — a link is **REAL** only with (a) a constructor/wiring
> reference in `backend/app/core/application.py` or a service `__init__`, (b) a grep-verified call site, or
> (c) a passing integration test that exercises it. Classifications: **WIRED-AND-EXERCISED**,
> **WIRED-NOT-EXERCISED**, **TEST-CHOREOGRAPHY-ONLY**, **ABSENT**.
> Module key: P-01 Core substrate (`core/permissions/tasks/events/monitoring`, assembly `app/core/application.py`),
> P-02 `intelligence`, P-03 `opportunities`, P-04 `agents`, P-05 `execution`, P-06 `business`, P-07 `financial`,
> P-08 `survival`, P-09 `memory`, P-10 `security`, P-11 `dashboard` + `frontend/` SPA, P-12 `operations`, P-13 `portfolio`.
> HTTP surface: `app/main.py` registers all routers under `/api/v1` (20 files in `app/api/routes/`, incl. `__init__.py`;
> 19 router modules), SPA served from the built `frontend/dist` at `/app`.

## 1. Import / wiring dependency graph (§5)

Method: AST scan of every `app/**/*.py` file distinguishing **top-level** imports from **function-local (lazy)**
imports, resolved for relative imports (`from ..x`, `from .x`). Package-level top-level imports (aggregated,
self-imports excluded; `integrations` is a leaf provider-stub package):

| Package | Top-level imports of other `app` packages | Lazy (function-local) imports |
|---|---|---|
| `agents` (P-04) | core, database, events, permissions, tasks | core, database |
| `api` | core, dashboard, database, events, execution, monitoring, opportunities, permissions, tasks | core, database, financial, security |
| `business` (P-06) | core, database, events, permissions | database, execution |
| `core` (P-01) | database, events, monitoring, permissions, tasks | **agents, business, database, execution, financial, intelligence, memory, operations, opportunities, portfolio, security, survival** |
| `dashboard` (P-11) | core, database, permissions | — |
| `events` (P-01) | core, database | — |
| `execution` (P-05) | agents, core, database, events, opportunities, permissions | agents, database |
| `financial` (P-07) | core, database, events, permissions | core, database |
| `intelligence` (P-02) | core, database, events, integrations, permissions, tasks | database |
| `memory` (P-09) | core, database, permissions | agents, core, database |
| `monitoring` (P-01) | core, database | — |
| `operations` (P-12) | core, database, events, permissions, security, tasks | database, execution, financial, security |
| `opportunities` (P-03) | core, database, events, permissions | intelligence |
| `permissions` (P-01) | core, database | core |
| `portfolio` (P-13) | core, database, permissions | database |
| `security` (P-10) | core, database, execution, memory, permissions | core, database, permissions |
| `survival` (P-08) | core, database, events, permissions | core, database, events, financial |
| `tasks` (P-01) | core, database, events, permissions | core |
| `database` | (model/repository aggregation only — see §2 of the Data Architecture doc) | — |

### 1.1 Circular dependencies — verdict

- **True file-level circular imports: 0.** A naive package-level scan shows apparent 2-cycles
  `core↔permissions`, `core↔tasks`, `core↔events`, `core↔monitoring`. File-level inspection dissolves all four:
  the P-01 sub-packages import only *leaf* core modules — `permissions/approvals.py:24` imports
  `core.exceptions`; `tasks/manager.py:16,20` imports `core.exceptions`/`core.logging`; `events/bus.py:16`
  imports `core.logging`; `monitoring/system_monitor.py:4` imports `core.config` — while the only core file
  importing them back is `core/application.py:12-18` (the assembly root, which nothing in those packages imports).
  No cycle exists at module granularity; the package graph is cyclic only because `core` is both the leaf-utility
  package and the assembly package. Recorded as a maintainability observation, not a defect (P14-DEF-I9, P3).
- **Service-level cycles are deliberately broken by lazy imports in `Application.startup()`**
  (`core/application.py`): all twelve P-02…P-13 service classes are imported *inside* `startup()`, never at
  module top level, so services may hold constructor references to each other (e.g. P-12↔P-08/P-10) without any
  import cycle. Other cycle-breaking lazy imports: `opportunities → intelligence` (recorder is passed in, the
  import is local), `memory/service.py:126-127` (`wire_agent_memory()` locally imports
  `agents.memory_interface` and `memory.knowledge`), `security` and `operations` local imports of
  execution/financial collaborators.
- **One genuine upward dependency:** `execution/adapters/api.py` imports `opportunities.sources` at top level —
  P-05 (lower layer) depends on P-03's source catalogue. It works, but inverts the assembly order (P-03 is built
  before P-05, so no runtime failure). P14-DEF-I9 (P3).

### 1.2 Duplicate integrations (two paths between the same pair / same concept)

| # | Duplication | Evidence | Assessment |
|---|---|---|---|
| D1 | **Three workflow stacks**: P-05 `execution_workflow_*`, P-12 `autonomous_workflows`/`operations_workflow_*`, P-13 `portfolio_workflows` | models `execution.py`, `operations.py`, `portfolio.py`; P-12 calls P-05 (`operations/service.py:2030-2051`), P-13 delegates to P-12 | Deliberate layering, but three state machines for "workflow"; `business_creation_runs.workflow_*_id` are FK-less VARCHAR(36) pointing at the P-05 stack (see Data doc) |
| D2 | **Four agent-assignment stores**: `agent_assignments` (P-04), `business_agent_assignments` (P-06), `operations_assignments` (P-12), `portfolio_agent_assignments` (P-13) | `grep ^TABLE` over Base.metadata | Scope-specific by design; no shared assignment contract — a reader must know which store a given assignment lives in |
| D3 | **Dashboard bypasses service APIs**: P-11 `dashboard/service.py:78` holds the whole `Application` and reads tables directly via SQLAlchemy (`select(func.count())…`, `dashboard/service.py:98-103`) in parallel with calling services (`app.security.monitor.status()`, `:94`) | Two read paths (direct DB + service) to the same data; risk of divergence from service-level rules |
| D4 | **Multiple event/audit logs**: `system_events` (bus persistence), `audit_events`, `security_audit_chain`, `business_lifecycle_events`, `operations_workflow_events` | models `core.py`, `security.py`, `business.py`, `operations.py` | Distinct purposes, overlapping content; no unified trace view (correlation IDs are the only join, and are FK-less strings) |
| D5 | **Two memory interfaces**: P-04 `P04MemoryInterface` remains live, wrapped by P-09 `P09MemoryInterface` in `memory/service.py:121-129` (`wire_agent_memory`) | Intentional completion of the P-04 seam, but callers see the P-04 object identity replaced at startup — order-dependent |

### 1.3 Unnecessary / questionable dependencies

- `security → memory`: only `security/ai_security.py:29` (`from ..memory.policy import detect_secrets`) — a single
  helper reuse; P-10's own design note (`security/service.py:14`) states the broker/governance path reads *nothing*
  from memory, and the import is of a pure pattern function, not memory content. Acceptable, flagged for clarity.
- `operations → memory`: exactly one call site (`operations/service.py:2235`, `self._memory.learning.analyze(...)`).
  Real but thin; if P-09 is absent the constructor still requires the argument (no `None` default in
  `operations/service.py:69-71` signature usage in assembly — assembly always passes it).
- `api → execution` at top level plus lazy `api → financial/security`: route modules resolve services through
  `request.app.state`/application in `api/dependencies.py:16-46`; the lazy imports are the assembly-avoidance
  pattern, not a defect.

## 2. Integration matrix (§5)

Common columns, stated once: **AuthN** = bearer/session principal resolved in `api/dependencies.py:28`
(`get_principal`); **AuthZ** = `require_permission(...)` dependency (`api/dependencies.py:38-46`) + in-service
`PermissionEngine`/`ApprovalService` checks; service-to-service calls are **in-process direct method calls**
(no HTTP, no serialisation, no network timeout) — timeout/retry therefore only exist where a substrate provides
them: P-01 `TaskManager` (per-task `timeout_seconds`, exponential backoff `retry_base_delay=0.5s`→`retry_max_delay=30s`,
`tasks/manager.py:310-361`) and P-05 execution retry policies. **Logging**: every service audits to `audit_events`
via its `_audit()` helper and logs via `core.logging.get_logger`. **Error handling**: domain exceptions from
`core.exceptions`; event-bus subscriber failures are isolated and counted (`events/bus.py:67-69`).

| Source → Dest | Interface | Input → Output | Evidence (wiring / call site / test) | Class |
|---|---|---|---|---|
| P-01 → all | Constructor injection in `Application.startup()` (session_factory, bus, permissions, approvals, tasks, monitor) | Settings → service instances | `core/application.py` startup sequence; `tests/test_p14_audit.py` MODULE_SERVICES assembly probe; per-phase `test_pXX_integration.py` | WIRED-AND-EXERCISED |
| P-02 → P-01 | Service object: TaskManager registry, PermissionEngine, ApprovalService, EventBus | Mission/plan dicts → plan + decision records | `intelligence/service.py:81-102`; `tests/test_p02_integration.py` | WIRED-AND-EXERCISED |
| P-03 → P-02 | `recorder` object (`intelligence.recorder` passed as `recorder=`) | Research outcome → DecisionRecord | `application.py` (OpportunityService construction); `opportunities/service.py:73-80` (`_recorder`, 3 refs) | WIRED-AND-EXERCISED |
| P-03 → P-01 | RESEARCH_HANDLER task closure over OpportunityService | `{session_id}` payload → research result dict | `application.py` (`_research_handler`, `tasks.registry.register(RESEARCH_HANDLER, …)`) | WIRED-AND-EXERCISED |
| P-04 → P-02 | Shared ModelRouter: `agents.resources.bind_router(intelligence._router)` | Agent inference request → model response | `agents/service.py:90-93`; `application.py` passes `intelligence=self.intelligence` | WIRED-AND-EXERCISED |
| P-05 → P-04 | `capabilities=self.agents.capabilities` (same CapabilityService instance) | Capability name → validation/grant state | `application.py`; `execution/service.py:128-132` | WIRED-AND-EXERCISED |
| P-06 → P-03 | Direct calls: `get_opportunity`, `validate`, `latest_score`, `report` | opportunity_id → opportunity/score/report dicts | `business/service.py:320,341-344,491-492,816-817,1584` | WIRED-AND-EXERCISED |
| P-06 → P-04 | `agents` service object (assignments during creation runs) | Business spec → agent assignments | `business/service.py` (19 `agents` refs); `tests/test_p06_integration.py`, `test_p06_scenarios.py` | WIRED-AND-EXERCISED |
| P-06 → P-05 | `execution.registry`, `workflows.create_definition/start_run/drive`, `submit_and_execute`, `evidence_for_request`, `workspaces.root` | Blueprint steps → execution runs + evidence | `business/service.py:169,229,1013,1122-1140,1268,1290` | WIRED-AND-EXERCISED |
| P-07 → P-06 | `business.financial_inputs(business_id)` bridge + business registry reads | business_id → financial-input payload | `financial/service.py:72-79` (`business=`), call site `financial/service.py:247`; `tests/test_p07_integration.py` | WIRED-AND-EXERCISED |
| P-08 → P-07 | FinancialService read calls (sole financial source; P-08 holds no money columns) | business_id → verified revenue/summary | `survival/service.py:39-64` sub-services receive `financial`; `tests/test_p08_integration.py` | WIRED-AND-EXERCISED |
| P-08 → P-06/P-04/P-05/P-01/P-02 | Constructor bundle: business, agents, execution, tasks, `intelligence.recorder` | Health/decision inputs → decisions, experiments, scaling assessments | `application.py` SurvivalService construction; `survival/service.py:39-41` | WIRED-AND-EXERCISED |
| P-09 → P-04 | `wire_agent_memory()`: replaces `agents.memory` with `P09MemoryInterface(P04MemoryInterface, memory_service)` | Agent memory read/write → P-09 records | `memory/service.py:43-55,121-129`; `application.py` calls `wire_agent_memory()`; `tests/test_p09_integration.py` | WIRED-AND-EXERCISED |
| P-10 → P-01 | `auth.login_guard = security.login_guard` (post-construction wiring) | Login attempt → throttling decision | `application.py`; `security/service.py:51-76` | WIRED-AND-EXERCISED |
| P-10 → P-07 | Read-only: `financial.get_settings()` via `_financial_settings()` callback into FinancialGuard | — → financial settings dict | `security/service.py:57,82-84,203-206` | WIRED-AND-EXERCISED |
| P-10 → all | PermissionBroker `authorize(...)` — consumed directly by P-12; other modules use P-01 PermissionEngine + P-10 policy settings rather than the broker object | Principal+action+resource → allow/deny + gates | `operations/service.py:1390` (`self._security.broker.authorize`); no broker call sites in P-02…P-08 service code (grep) | WIRED-AND-EXERCISED for P-12; **WIRED-NOT-EXERCISED (broker) / indirect-only for P-02…P-08** — see P14-DEF-I5 |
| P-12 → P-01 | TaskManager (trigger/scheduled work feeds the P-01 queue; no second scheduler) + ApprovalService | Workflow task → P-01 task | `operations/service.py:69-89`; `tests/test_p12_integration.py`, `test_p12_recovery.py` | WIRED-AND-EXERCISED |
| P-12 → P-05 | `execution.submit / link_workflow / execute / emergency_stop / emergency_resume` | Workflow task payload → execution request/result | `operations/service.py:2030-2051,2674,2724` | WIRED-AND-EXERCISED |
| P-12 → P-07 | `financial.budgets.get_budget / budget_utilisation / get_request / request_spend / approve_spend`, `business_summary` | budget_id → utilisation; spend request → approval-gated spend | `operations/service.py:495,1541-1585,1815,2540,2845` | WIRED-AND-EXERCISED |
| P-12 → P-08 | `survival.is_paused / pause_business / resume_business` | business_id → pause state | `operations/service.py:1338,2643,2712,2851` | WIRED-AND-EXERCISED |
| P-12 → P-10 | `security.broker.authorize`, `security.emergency.current_mode / financial_suspended / set_mode / set_financial_suspension` | Action context → authorization; emergency state | `operations/service.py:696,1332-1390,2623-2746` | WIRED-AND-EXERCISED |
| P-12 → P-09 | `memory.learning.analyze(SYSTEM_PRINCIPAL, {...})` | Workflow outcome → learning record id (stored FK-less on `autonomous_workflows.learning_record_id`) | `operations/service.py:2235` (sole call site) | WIRED-AND-EXERCISED (single call site) |
| P-12 → P-06 | `business.get_business(business_id)` existence/summary checks | business_id → business dict | `operations/service.py:288,2831` | WIRED-AND-EXERCISED |
| P-12 → events | Trigger engine: subscribes `"*"` on the bus, matches active `operations_triggers` rows of type `event` | Any non-operations Event → `_fire_trigger(fire_key=f"event:{row.id}:{event.event_id}")` | `operations/service.py:2387-2416` (`_subscribe_triggers`); note: there is **no `TriggerService` class** — triggers live in `OperationsService` + `operations/scheduling.py` + `TriggerRepository` | WIRED-AND-EXERCISED |
| P-13 → P-06 | `business.get_business`, `get_business_channels` | business_id → business/channels | `portfolio/service.py:213`; `portfolio/intelligence.py:289,522` | WIRED-AND-EXERCISED |
| P-13 → P-07 | `financial.business_summary`, `financial.revenue.metrics` (live-read analytics only; no writes, no transfers — no transfer method exists) | business_id → summary/metrics dicts | `portfolio/finance.py:30,49`; `portfolio/intelligence.py:513`; `tests/test_p13_integration.py` | WIRED-AND-EXERCISED |
| P-13 → P-12 | Constructor holds `operations`; portfolio workflows are executed via P-12 | Portfolio workflow → P-12 workflow | `portfolio/service.py:55-66` (wiring); call sites are in portfolio sub-services; exercised in `tests/test_p13_integration.py`/`test_p13_scenarios.py` | WIRED-AND-EXERCISED |
| P-13 → P-09 | Memory crosses businesses only for `ORGANIZATION_SHARED` records (service-level rule in portfolio/memory code) | business pair → shared records or refusal | `portfolio/service.py:55-66`; `tests/test_p13_security.py` (isolation) | WIRED-AND-EXERCISED |
| P-13 → P-03/P-04/P-08 | Constructor holds `discovery=opportunities`, `agents`, `survival` | — → cross-business opportunities, agent assignments, risk inputs | `portfolio/service.py:55-66`; sub-service call sites in `portfolio/*.py` | WIRED-AND-EXERCISED |
| P-11 → all | DashboardService(application) direct DB reads + service calls; SPA fetches `/api/v1/dashboard/*` | HTTP GET → JSON aggregates (byte-compared to P-07 totals in P-11 verification) | `dashboard/service.py:78-103`; `api/routes/dashboard.py`; `frontend/src/views/*.tsx` (one view per module); `tests/test_p11_integration.py` | WIRED-AND-EXERCISED |
| Frontend → backend | Fetch to `/api/v1/*` with session/bearer principal; backend serves `frontend/dist` at `/app` | JSON schemas in `app/api/schemas/` | `app/main.py:68`; `frontend/src/lib/` | WIRED-AND-EXERCISED |
| Any module → P-09 (learning from outcomes) | Only P-08 (via `recorder` is P-02, not P-09), P-12 (one call site) and P-13 (shared-memory reads) consume P-09; P-05/P-06/P-07 outcomes reach memory only via P-09 ingestion jobs, not direct calls | Execution/business/financial outcome → memory record | grep: no `memory.` call sites in `execution/`, `business/`, `financial/` service code | **WIRED-NOT-EXERCISED** (indirect via ingestion) — P14-DEF-I6 |
| Any module → P-10 broker (except P-12) | See P-10 row above | — | grep over `app/*/service.py` | **WIRED-NOT-EXERCISED** — P14-DEF-I5 |
| P-02 → P-03…P-13 (intelligence consuming other engines) | P-02 receives only substrate + providers at construction; cross-engine intelligence flows run the other way (P-03/P-08 consume `intelligence.recorder`; P-04 consumes the router) | — | `intelligence/service.py:81-102` | **ABSENT** as a direct link (by design; recorded, not a defect per se) |

### 2.1 §5 required-relationships checklist — verdicts

| §5 requirement | Verdict | Basis |
|---|---|---|
| P-01 coordinates shared infrastructure & lifecycle | PASS | Single assembly root, lifecycle FAILED-on-error, readiness gating (`application.py`) |
| P-02 receives authorized info from other engines & produces structured outputs | PARTIAL | Outputs are structured (plans/decisions); *inbound* cross-engine flow is indirect (recorder/router consumed by others), no direct P-03…P-13 → P-02 feed |
| P-03 communicates validated opportunities to business/planning engines | PASS | P-06 call sites (§2); planning (P-02) receives only recorder entries |
| P-04 creates/registers/assigns/monitors/retires agents via controlled interfaces | PASS | AgentFactoryService + CapabilityService shared instance into P-05 |
| P-05 executes authorized actions & reports results to orchestration | PASS | P-06 and P-12 both consume submit/execute/evidence |
| P-06 receives approved proposals & manages creation workflows | PASS | Opportunity + approval-gated creation (`business/service.py`) |
| P-07 provides authoritative analytics without conflicting records | PASS | Sole ledger; P-08/P-12/P-13 read-only (see Data doc §3) |
| P-08 coordinates survival/recovery/growth recommendations | PASS | Wired to P-06/P-07/P-04/P-05/P-01/P-02; consumed by P-12/P-13 |
| P-09 preserves scoped knowledge & learns from verified outcomes | PARTIAL | Scoping verified; direct outcome feeds from P-05/P-06/P-07 absent (ingestion only) — I6 |
| P-10 enforces permissions/authorization/policies/audit across **every** module | PARTIAL | Broker directly consumed only by P-12; elsewhere enforcement is P-01 PermissionEngine + P-10 settings/login-guard — effective but not the single broker path §5 implies — I5 |
| P-11 accurate operational interface for the complete system | PASS (with D3 caveat) | Live aggregates; direct-DB read path is a divergence risk |
| P-12 coordinates approved tasks/workflows/agents/scheduling/execution | PASS | §2 rows; trigger engine on the shared bus + P-01 queue |
| P-13 manages relationships/shared services/resource allocation/portfolio intelligence | PASS | §2 rows; finance strictly read-only |

## 3. Event architecture audit (§6)

Source files: `app/events/events.py` (101 `EventType` members), `app/events/bus.py`, `app/events/subscribers.py`,
plus P-12's trigger subscription in `app/operations/service.py:2387-2416`.

### 3.1 §6 category mapping — **exact 10/21, partial/proxy 8/21, missing 3/21**

| §6 category | Actual EventType | Verdict |
|---|---|---|
| BusinessCreated | `BUSINESS_CREATED` | Exact |
| BusinessUpdated | — (no update event; mutations surface only as lifecycle/readiness events) | **MISSING** |
| BusinessStatusChanged | `BUSINESS_LIFECYCLE_CHANGED` (+ P-08 overlay events) | Partial (name/semantics differ) |
| AgentCreated | `AGENT_CREATED` | Exact |
| AgentAssigned | `AGENT_ASSIGNED` | Exact |
| AgentExecutionStarted | — (proxies: `TASK_STARTED`, `EXECUTION_SUBMITTED`, `OPERATIONS_TASK_STARTED`) | Partial (no agent-scoped type) |
| AgentExecutionCompleted | — (proxies: `TASK_COMPLETED`, `EXECUTION_COMPLETED`, `OPERATIONS_TASK_COMPLETED`) | Partial |
| AgentExecutionFailed | — (proxies: `TASK_FAILED`, `EXECUTION_FAILED`, `OPERATIONS_TASK_FAILED`) | Partial |
| OpportunityDiscovered | `OPPORTUNITY_DISCOVERED` | Exact |
| OpportunityValidated | `OPPORTUNITY_VALIDATED` | Exact |
| ApprovalRequested | `APPROVAL_REQUESTED` | Exact |
| ApprovalGranted | `APPROVAL_GRANTED` | Exact |
| ApprovalRejected | `APPROVAL_REJECTED` | Exact |
| FinancialTransactionRecorded | — (proxy: `FINANCIAL_JOURNAL_POSTED`; also `FINANCIAL_REVENUE_VERIFIED`) | Partial — and see I3: neither proxy is in `CRITICAL_EVENT_TYPES`, so neither is persisted |
| BudgetThresholdReached | — (proxies: `FINANCIAL_ALERT_RAISED`, `OPERATIONS_BUDGET_BLOCKED`) | Partial (blocked ≠ threshold-reached; no utilisation-% event) |
| WorkflowCreated | `OPERATIONS_WORKFLOW_CREATED` (P-12 only; P-05 stack has `WORKFLOW_STARTED` but no Created) | Partial |
| WorkflowCompleted | `WORKFLOW_COMPLETED`, `OPERATIONS_WORKFLOW_COMPLETED` | Exact |
| WorkflowFailed | `WORKFLOW_FAILED`, `OPERATIONS_WORKFLOW_FAILED` | Exact |
| SecurityIncidentDetected | — (incidents are DB rows `security_incidents`, created in `security/service.py:369`, with **no** EventType) | **MISSING** |
| ResourceLimitReached | `RESOURCE_THRESHOLD_EXCEEDED` (+ `OPERATIONS_*` breaker events) | Partial (threshold-exceeded ≈ limit-reached) |
| PortfolioRiskDetected | — (risk is a DB row `portfolio_risk_assessments`; no EventType, no publish site) | **MISSING** |

### 3.2 Event envelope (§6) — field by field from the `Event` dataclass (`events.py:155-164`)

| §6 field | Present? | Evidence |
|---|---|---|
| Unique event ID | YES | `event_id: str = uuid4` |
| Event type | YES | `event_type: EventType` |
| Source module | YES | `source: str` (free-text, e.g. `"core.application"`, `"operations"` — no enum/registry) |
| Timestamp | YES | `timestamp` = aware UTC `datetime.now(timezone.utc)` |
| Correlation ID | PARTIAL | `correlation_id: str \| None = None` — the bus does **not** auto-populate it; publishers must pass it, many publish sites pass none |
| Business ID | **NO** | No field; business identity exists only ad-hoc inside `payload` dicts on some events |
| Workflow ID | **NO** | No field; `task_id` exists (extra field, not in §6) but is not a workflow ID |
| Payload schema version | **NO** | No field; `payload: dict` is unversioned and unschema'd |
| Authorization context | **NO** | No principal/permission field on the event |
| Processing status | **NO** | No field; delivery outcome exists only as bus counters (`published_count`, `dropped_count`, `subscriber_error_count`) |

**Coverage: 4 full + 1 partial of 10 required fields.**

### 3.3 Reliability — verified from `bus.py` / `subscribers.py`

- **In-process only — stated plainly:** `EventBus` is a single-process, in-memory `dict[str, list[Handler]]`
  (`bus.py:25`). There is no broker, no cross-process delivery, no persistence of non-critical events. Events do
  not survive a restart except the critical subset written to `system_events`. `publish_sync_safe` silently
  drops the event when no event loop is running.
- Duplicate protection: **persistence subscriber only** — `subscribers.py` checks
  `session.query(SystemEvent).filter_by(event_id=…).first()` before inserting. In-memory subscribers have no
  dedupe; a re-published event is re-delivered.
- Idempotent processing: **not a bus property.** One consumer achieves it downstream: P-12 triggers use
  `fire_key=f"event:{trigger_id}:{event.event_id}"` (`operations/service.py`). Other subscribers must self-guard.
- Retry: **none in the bus.** A failing subscriber is logged, counted (`subscriber_error_count`), and skipped
  (failure isolation, `bus.py:67-69`); the event is not redelivered. (Task/execution retries live in P-01/P-05/P-12,
  not in event delivery.)
- Dead-letter handling: **none for events.** `OperationsDeadLetter` (P-12) dead-letters *workflow tasks*, not bus
  events; dropped events (flood limit 200/s, recursion depth 3, `bus.py`) are only counted in `dropped_count`.
- Retention: **none.** No purge/TTL/retention code exists for `system_events` (grep over `events/` and the core
  repository finds none); the table grows unboundedly.
- Traceability: partial — persisted critical events keep `event_id`, `correlation_id`, `task_id`, `severity`,
  `payload`; non-critical events leave no trace after delivery.
- §6 safety rule ("never rely on event delivery as the only enforcement of financial/security authorization"):
  **held** — spend/authorization paths are synchronous service calls (P-12 → P-07 budgets, P-12 → P-10 broker),
  not event-driven.

## 4. Integration defects (§17 severities)

| ID | Sev | Defect | Minimal proposed repair (Stage B) |
|---|---|---|---|
| P14-DEF-I1 | P1 | `SecurityIncidentDetected` and `PortfolioRiskDetected` have no EventType and no publish site — security/portfolio risk signals are invisible to bus consumers (incl. P-12 event triggers and the persistence subscriber) | Add two EventTypes, publish at `security/service.py` incident creation and P-13 risk-assessment creation, add both to `CRITICAL_EVENT_TYPES` |
| P14-DEF-I2 | P1 | Event envelope lacks business ID, workflow ID, payload schema version, authorization context, processing status (5/10 §6 fields missing, correlation ID optional and often unset) | Extend `Event` dataclass with optional `business_id`, `workflow_id`, `schema_version=1`, `actor` fields; have the bus stamp correlation ID from the existing contextvar when unset |
| P14-DEF-I3 | P2 | `FINANCIAL_JOURNAL_POSTED` / `FINANCIAL_REVENUE_VERIFIED` are **not** in `CRITICAL_EVENT_TYPES` — the closest events to §6 `FinancialTransactionRecorded` are never persisted to `system_events` | Add both to the critical set (one-line change, additive) |
| P14-DEF-I4 | P2 | Bus has no retry and no event dead-letter; subscriber failures and flood/depth drops are count-and-forget | Record failed deliveries (event_id, handler, error) to a small dead-letter table or, minimally, persist dropped/failed critical events synchronously in the persistence subscriber path |
| P14-DEF-I5 | P2 | P-10 PermissionBroker is directly consumed only by P-12; P-02…P-08 enforce via P-01 PermissionEngine + P-10 settings. §5's "enforce across every module" is therefore indirect, and broker-only gates (capability/task checks) do not apply outside P-12 | Document the two-path model as the accepted design **or** route P-05 execution submission through the broker; do not rebuild — a decision item for the owner |
| P14-DEF-I6 | P2 | No direct outcome feed from P-05/P-06/P-07 into P-09; learning depends on ingestion jobs and the single P-12 `learning.analyze` call site | Add outcome-ingestion calls at execution/business/financial completion points, reusing the existing ingestion service (no new store) |
| P14-DEF-I7 | P2 | `BusinessUpdated` missing and `BusinessStatusChanged` is named/scoped as lifecycle-only; generic business mutations are not observable on the bus | Publish lifecycle event for status changes (already done) and add a `BUSINESS_UPDATED` type for non-status mutations, or formally map §6→`BUSINESS_LIFECYCLE_CHANGED` in docs |
| P14-DEF-I8 | P3 | No retention policy for `system_events` (unbounded growth); non-critical events are untraceable after delivery | Add a scheduled prune (keep N days) via the existing P-12 time-trigger machinery; document non-critical volatility |
| P14-DEF-I9 | P3 | Package-level import graph looks cyclic (core⇄substrate packages) and `execution→opportunities` inverts layering; both are benign today but confuse future audits/tooling | Note in architecture docs that leaf modules (`core.exceptions/logging/config`) are the shared base; optionally move leaf utilities to a `core/primitives` namespace in a future refactor — no Stage B action required |
| P14-DEF-I10 | P3 | Duplicate read path in P-11 (direct DB + services, D3) and four assignment stores / three workflow stacks (D1/D2) with no shared contract documentation | Document the canonical store per concept in the Data Architecture doc (done, Stage A); any consolidation is a Stage B decision, not a repair |
| P14-DEF-I11 | P3 | Agent-execution §6 categories exist only as task/execution proxies with different IDs (`task_id` vs execution request id), so an "agent execution" cannot be followed on the bus under one identity | When publishing EXECUTION_* events, include `agent_id` and the originating assignment/task ID consistently in payload (convention change only) |

*End of P-14 Stage A integration audit. No code was modified.*
