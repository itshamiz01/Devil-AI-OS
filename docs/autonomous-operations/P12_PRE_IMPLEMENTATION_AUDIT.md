# P-12 Pre-Implementation Audit — Autonomous Operations Engine

Implements Stage 1 of the P-12 master prompt (`docs/prompts/P12_PROMPT.md`,
§2) on top of the accepted P-01–P-11 staging stack (backend 602/602 tests,
frontend 30/30, 139 tables, migration head `193731df4c37`). Every claim
below was verified against the live code on 9 Nov 2026, not against
earlier reports.

## 1. Existing capabilities (verified in code)

### 1.1 Execution substrates — two, deliberately different levels

- **P-01 TaskManager** (`app/tasks/manager.py`): the `tasks` table IS a
  persistent, priority-ordered bounded queue. A single async worker loop
  claims due tasks (`next_attempt_at`), executes them ONLY through the
  named-handler registry (payloads can never carry code), applies
  exponential backoff (`app/tasks/scheduler.py` is the *retry policy*
  module — see §2.1), honours idempotency keys, approval-gated tasks
  (`requires_approval` → WAITING_FOR_APPROVAL), cancellation, and
  startup recovery (RUNNING → PAUSED + `recovery_required`, never
  blindly re-executed). Concurrency is a single global cap
  (`max_concurrency`, default 4) with an admission guard fed by the
  system monitor.
- **P-05 ExecutionService** (`app/execution/service.py`): governed tool
  execution (filesystem/documents/api operational, code = process
  controls only, browser partial, desktop disabled) with its own
  policy engine, approval binding, standing authorizations, per-resource
  semaphores, verification (`_verify`), emergency stop/resume and
  restart recovery. Its `WorkflowEngine` (`app/execution/workflows.py`)
  runs *tool-step* workflows (multi-step tool chains inside one
  execution request graph) — a lower level than P-12's business
  workflows. P-12 must not confuse or replace it: P-12 workflow tasks
  that need tool work dispatch through `ExecutionService.submit_and_execute`;
  P-12 tasks that need queue work dispatch through the TaskManager.

### 1.2 Intelligence (P-02)

`IntelligenceService` offers missions → plans (deterministic
`BaselinePlanner`, 3 templates; LLM path only behind a provider
interface, exercised in staging solely via FakeProvider — **no real LLM
has ever run in this staging environment**), hash-bound plan approvals,
plan execution through the TaskManager, and a `ResultVerifier` whose
vocabulary (verified / failed / **unverified — never reported as
success**) P-12 adopts for its own verification gate.

### 1.3 Agents (P-04)

`AgentFactoryService`: agent registry rows are P-01 `agents` (with
`business_ref` scoping), a capability catalogue (risk level +
approval level per capability), governed creation, business
assignments (`assign()` with rule checks), metrics and health
(`agent_metrics`, `compute_health`), config governance, and an
emergency stop. Agent *selection evidence* (capabilities, metrics,
health, business assignment) is all readable through the service —
P-12's selection layer consumes it; it does not re-implement it.

### 1.4 Businesses (P-06) and survival (P-08)

`BusinessCreationService` owns business records and the lifecycle
state machine. `SurvivalService` overlays health evaluation,
decisions, pre-declared experiments with mechanical stop-loss, and
`BusinessPauseControl` (`pause_business` / `is_paused`) — P-12's
business operating cycle consults (never duplicates) these.

### 1.5 Finance (P-07)

`FinancialService` + `BudgetService` own the only ledger, budgets,
reserves, verified available cash, and the spending-authorisation
flow: `request_spend` persists a `SpendingRequest` in P-07's tables
and *decides* it (Level 1 auto within rules / Level 2 held for owner /
Level 3 structurally blocked). `budget_utilisation` and
`available_cash` are the authoritative read models. There is no
reservation API as such; the SpendingRequest lifecycle *is* the
commitment mechanism (§10 rules 2–7 map onto it — see §4.3).

### 1.6 Memory and learning (P-09)

`MemoryService` composes `store` (classified, provenance-carrying
records; Article 0 write gate — memory is data, never authority),
`ingestion`, `retrieval`, and `learning` (`LearningService.analyze`
requires BOTH expected and actual outcomes, mechanically caps
confidence; VERIFIED needs ≥3 observations + owner review). P-12
records workflow outcomes only through `learning.analyze` and only
for independently verified completions.

### 1.7 Security and governance (P-10) — the authority P-12 composes

- `PermissionBroker.authorize` evaluates, in order: security mode →
  agent restriction overlay → business scope → P-01 permission engine →
  risk gates (Level 0/1 automatic within grants; Level 2 capability or
  approval; Level 3 owner-decided hash-bound approval only). It never
  raises; a broker error is a recorded **deny** (fail closed).
  `broker.request_escalation` creates a P-01 approval request and
  authorizes nothing by itself.
- Action risk comes from `security/policy.classify_action` over a
  fixed vocabulary (`ACTION_RISK`); **unknown action names classify at
  RISK_CRITICAL (3)**. P-12 therefore maps every step kind onto an
  existing classified action name (see §4.2) instead of inventing
  unclassified ones.
- `EmergencyService`: modes `normal` / `safe_mode` / `emergency_stop`
  (owner-only, versioned, event-recorded) plus a separate financial
  suspension flag. `FinancialGuard.authorize` authorizes financial
  actions (view/approve/execute separation); P-07 executes.
- P-01 `ApprovalService`: SHA-256 hash-bound to exact action +
  parameters; `decide` enforces `approve_actions` and refuses
  non-owner self-approval at the service level (P-10 residual, closed).
  Approvals are the single approval store — P-12 creates **no**
  approvals table (§20's "approval_requests" is satisfied by a
  reference-only link table, §4.4).

### 1.8 Events (P-01)

`EventBus`: in-process async pub/sub with per-subscriber failure
isolation, correlation propagation, recursion-depth and flood guards;
`CRITICAL_EVENT_TYPES` are also persisted to `system_events`.
`Event` carries id, type, timestamp, source, correlation id, payload.
P-12 adds its workflow event types to this enum (house precedent:
every phase appends its types) and publishes through the same bus —
no new event infrastructure. Duplicate protection: consumers key on
`event_id` / workflow idempotency keys (§21).

### 1.9 Command Center (P-11)

Vite + React 19 + TypeScript SPA (`frontend/`), hash router, shared
component library + design tokens, typed API client, visible-only
bounded polling. Navigation is a static `NAV_ITEMS` list in
`components/shell.tsx`; views switch in `App.tsx`. The existing
"Operations" view is §16 *System* Operations — P-12 adds a distinct
**Autonomous Operations** section (§19 of the P-12 prompt) as a new
view + nav item, reusing the components; the app is not redesigned.

### 1.10 Modes (Constitution)

`Settings.mode` ∈ `simulation | supervised | controlled | emergency`
(env-level, owner-set) already governs P-02 behaviour. P-12's autonomy
caps compose with it (§4.1) — modes are read, never written, by P-12,
and can never be raised by any agent path.

## 2. Missing capabilities (the gaps P-12 fills)

1. **No time/event/threshold trigger system exists.** The only
   "scheduler" in the codebase is P-01's retry-backoff policy module.
   Nothing evaluates recurring schedules, detects missed runs, or
   fires workflows from events/thresholds. §8's system must be built —
   as a *trigger layer over* the existing substrates (§4.5), not a
   second task scheduler: execution still happens only through the
   TaskManager and P-05.
2. **No business-workflow orchestration.** P-05's WorkflowEngine runs
   tool-step chains; nothing models a business objective decomposed
   into a DAG of agent tasks with budgets, approvals, verification and
   recovery. That is P-12's core (§5/§6).
3. **No autonomy policy framework.** Levels exist as *risk* levels in
   P-10 and *approval* levels in P-04/P-07, but no per-business /
   per-agent / per-workflow autonomy configuration. §4's framework is
   new (stored as P-12 policy rows + owner-governed settings).
4. **No operational decision engine** of the §12 kind (EXECUTE /
   EXECUTE_WITH_LIMITS / REQUEST_APPROVAL / DEFER / RESEARCH_MORE /
   PAUSE / ESCALATE / REJECT with recorded evidence) — P-02 decides
   plans, P-08 decides business survival; neither prioritizes
   operational work. New, deterministic, in P-12.
5. **No recovery machinery at workflow level**: no checkpoints,
   circuit breakers, or dead-letter store for workflows (P-01/P-05
   have task/request-level recovery only). New in P-12 (§13).
6. **No operational observability rollups** (§18) or operational
   reports — new, computed live from authoritative rows (derive,
   don't store; report snapshots are the only stored artifact).

## 3. Architectural conflicts — and their resolutions

1. **§5 workflow states vs two existing state machines.** P-01 tasks
   and P-05 runs keep their own states untouched; P-12 workflows get
   their own state machine (the §5 lifecycle) enforced in the P-12
   service layer. A workflow task *references* its substrate execution
   (task id / execution request id); states are never written across
   boundaries.
2. **§10 budget declarations vs "no money in P-12".** The prompt
   requires workflows to declare budgets; the Constitution/houserule
   (P-07 sole financial authority; P-10 precedent: no money columns)
   forbids a second store of monetary truth. Resolution: a workflow
   references a P-07 `budget_id`; amounts (limits, utilisation,
   proposed spend) are read from / decided by P-07 at runtime and any
   spend flows through `BudgetService.request_spend`, which persists
   in P-07's tables. P-12 tables carry **no monetary columns**;
   amounts appear only inside decision/evidence JSON as clearly
   labelled P-07-sourced snapshots (the P-08/P-09 precedent).
3. **§20 "approval_requests" entity vs the single approval store.**
   Creating a second approvals table would fork the authority P-10
   just unified. Resolution: `operations_approval_links` — reference
   rows (workflow/task ↔ P-01 approval id + parameters hash) only.
4. **§9 resource telemetry.** CPU/RAM come from the P-01 monitor
   (psutil); **GPU telemetry does not exist** (target hardware is
   CPU-only per the P-04 verdict) and model-server workload is the
   P-02 router's view. P-12 tracks what exists (concurrency, queue
   depth, task durations) and reports the rest as unavailable —
   never invented (§27 rule 7).
5. **§8 "use the existing scheduler".** There is none to use (§2.1);
   building the trigger layer is therefore not a violation but the
   mandated work. The justification is recorded here and in
   `P12_ARCHITECTURE.md`.

## 4. Proposed implementation architecture

Package `backend/app/operations/` (constants, pure state machine,
pure planner/DAG, autonomy resolution, decision engine, scheduler
math, recovery classification, verification, service facade,
repository in `app/database/repositories/operations.py`, models in
`app/database/models/operations.py`, routes
`app/api/routes/operations.py` + schemas). Wired into `Application`
as `self.operations` after P-10 (it composes security), with a
background trigger/drive loop started and stopped alongside the
TaskManager. Frontend: one new view + nav item.

### 4.1 Autonomy resolution (§4)

Effective level for (business, agent, workflow, action) =
**min** of: global default → business policy → agent-in-business
policy → workflow declared level → action-category cap → mode caps.
Mode caps: Constitution `simulation` → 1 (prepare only; the drive
loop will not execute), `supervised` → 2 with approval required for
Level ≥ 2 steps, `controlled` → policy value, `emergency` → 0 and
running work is stopped. P-10 security mode caps independently:
`safe_mode` → observation only for non-owners; `emergency_stop` →
no autonomous execution at all. **Level 4 is propose-only**: it can
generate decisions, recommendations and approval requests; it never
raises an execution ceiling. No path lets an agent write policy:
policy rows are owner-writable only (service-level owner check).

### 4.2 The execution pipeline (§22) — the only path

For every workflow task step, in order, stopping at the first
failure: (1) **Proposal** — the step definition (from an owner, a
P-02 plan import, or a deterministic decomposition template);
(2) **Structured validation** — strict schema, known substrate +
handler/tool, DAG position, capability requirements;
(3) **Policy evaluation** — autonomy resolution (§4.1) + §12 decision
engine outcome; (4) **Authorization** — `broker.authorize` with the
step's action mapped to the P-10 vocabulary (observe→`business.read`,
draft→`draft.create`, report→`report.generate`, write→
`filesystem.write`, publish→`content.publish`, send→
`message.send_external`, tool steps→the P-05 action's own class via
P-05's policy at submit time, financial→`FinancialGuard`);
(5) **Approval if required** — P-01 approval via escalation, exact
parameters hash, workflow waits; (6) **Execution adapter** — P-01
TaskManager (registered handlers only) or P-05
`submit_and_execute`; (7) **Independent verification** —
deterministic acceptance-criteria checks against the substrate
result (adopting P-02's verified/failed/unverified vocabulary);
(8) **Audit record** — P-01 audit event + P-12 operational decision
row + workflow event. A named security test proves there is no
service method that executes a step without stages 2–5.

### 4.3 Budget enforcement (§10)

At workflow validation and again before any expense-bearing step:
read the P-07 budget (limit + utilisation) and verified available
cash; if the workflow's declared spend path would exceed the budget
or the step's category is Level 2/3 in P-07 terms, route through
`request_spend` — a `blocked_level3` or over-limit decision BLOCKS
the workflow (Scenario 7) and a held decision parks it in
WAITING_FOR_APPROVAL. Protected reserves are never touched: P-07's
`available_cash` already excludes them, and P-12 moves no money at
all (it holds no execution mechanism — §23.2's P-07 rule stands).

### 4.4 Tables (additive migration from `193731df4c37`)

`autonomous_workflows`, `operations_workflow_versions`,
`operations_workflow_tasks`, `operations_workflow_executions`,
`operations_workflow_checkpoints`, `operations_workflow_events`,
`operations_triggers`, `operations_assignments`,
`operations_approval_links`, `operations_recovery_records`,
`operations_dead_letter`, `operations_autonomy_policies`,
`operations_decisions`, `operations_reports` — 14 tables, all
P-12-owned operational state; **no monetary columns, no approval
store, no ledger**. Dependencies live as a validated `depends_on`
JSON list on each task row (the graph is intrinsic to the plan
snapshot; a separate edge table would duplicate it — §20's list is
explicitly "proposed logical entities, not mandatory").

### 4.5 Scheduler / triggers (§8)

`OperationsScheduler`: trigger rows (time / event / threshold /
owner / agent-proposed) with timezone-aware next-fire computation,
missed-run detection (fires once, counts the miss), duplicate
prevention via a unique fire key per (trigger, scheduled instant),
and a tick loop (started by `Application`, interval from settings)
that fires due triggers, starts SCHEDULED workflows whose time has
come, and processes due recovery retries. Event triggers subscribe
to the existing bus; threshold triggers evaluate deterministic
predicates over P-07/P-08 read models at tick time. Agent-proposed
triggers create workflows in DRAFT only — validation + authorization
still stand between proposal and execution.

### 4.6 Recovery (§13)

Failure taxonomy = the §13 categories; retry only for transient
classes with exponential backoff + jitter (P-01's `backoff_delay`
is reused; jitter added locally); per-target circuit breakers
(open after N consecutive failures, half-open probe); checkpoints
written at every step settle (resume replays from the checkpoint —
completed steps are skipped by idempotency key, so a resumed
workflow cannot double-execute, Scenario 9); exhausted or
non-retryable failures go to the dead-letter store with the full
context for owner investigation. Authorization is re-checked before
every retry (a retry is a new pipeline pass).

### 4.7 Command Center (§19)

One new view, "Autonomous Operations", with tabbed panels A–I
(Overview, Workflows, Agent Operations, Approvals, Business
Operations, Scheduler, Recovery, Safety, Reports) built from the
existing components and fed by scoped `/api/v1/operations/*`
endpoints. Workflow controls (pause/resume/cancel) call the real
service; the view shows state only from backend responses.

## 5. Risks and limitations (stated up front)

- **No real LLM** exists in staging (P-02's position, unchanged):
  decomposition uses deterministic templates + P-02 plan import;
  "Master Intelligence generates a structured plan" (Scenario 2) is
  exercised through the deterministic planner path and labelled as
  such. The LLM-provider path remains interface-only.
- **In-process loop**: the trigger/drive loop shares the single
  FastAPI process (the deployment reality of every prior phase);
  missed-run detection covers restarts, at-least-once firing with
  idempotency keys prevents duplicates.
- **Concurrency** is enforced at workflow level by counting live
  substrate executions; the TaskManager's own global cap remains
  the hard backstop.
- **P-05 execution honesty carries over**: code execution is process
  controls, not a strong sandbox; browser is partial; desktop is
  disabled. P-12 inherits, and repeats, those labels.
- Windows verification remains carried from P-00 (all staging work
  is Linux-verified only).

## 6. Files and modules requiring modification

New: `app/operations/*`, `app/database/models/operations.py`,
`app/database/repositories/operations.py`,
`app/api/routes/operations.py`, `app/api/schemas/operations.py`,
one additive migration, `tests/p12_support.py` + five P-12 test
files, `scripts/p12_smoke.py`, frontend `views/Autonomy.tsx` +
tests. Modified: `app/core/application.py` (wire + loop),
`app/main.py` (router), `app/events/events.py` (P-12 event types,
append-only), `app/database/models/__init__.py` (exports),
`frontend/src/components/shell.tsx` (nav item),
`frontend/src/App.tsx` (route), `docs/PHASE_TRACKER.md`, `README.md`.
No existing service's behaviour is modified.
