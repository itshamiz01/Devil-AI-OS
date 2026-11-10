# P-12 Implementation Report — Autonomous Operations Engine

Built in staging, 2026-11-09, on the accepted P-01–P-11 stack.
Status vocabulary: IMPLEMENTED AND VERIFIED / IMPLEMENTED BUT NOT
FULLY VERIFIED / PARTIALLY IMPLEMENTED / NOT IMPLEMENTED / BLOCKED.

## 1. Executive summary

P-12 adds the Autonomous Operations Engine: governed multi-step
workflows that run through a single authorization pipeline
(proposal → validation → decision → P-10 authorization → P-01
approval where required → P-01/P-05 execution → independent
verification → audit → P-09 learning from verified outcomes only).
It integrates every prior engine without duplicating any authority:
P-07 remains the only financial authority (no money columns exist
in P-12's schema), approvals remain P-01's (P-12 stores reference
links only), the scheduler extends the existing substrates with the
trigger layer the Stage-1 audit proved missing, and emergency stop
composes P-10/P-08/P-04/P-05 rather than replacing them. The P-11
Command Center gains an Autonomous Operations section (eighth view
area) driven entirely by the new API. **Not production-ready**: the
honest limitations in §19 stand (no real LLM, single-process
scheduler, inherited P-05 execution limits, Windows unverified).

## 2. Pre-implementation audit findings (Stage 1)

Full audit: `P12_PRE_IMPLEMENTATION_AUDIT.md`. Headlines:

- P-01's TaskManager is a real persistent execution substrate
  (bounded queue, worker loop, idempotency, approval parking,
  startup recovery). `app/tasks/scheduler.py` is only a retry-policy
  module — **no time/event/threshold trigger system existed**, so
  P-12 adds a TriggerService feeding the existing substrates (the
  §8 layer), not a second task scheduler.
- P-05's WorkflowEngine is a tool-step engine — a different level
  from P-12 business workflows; untouched. P-12 dispatches through
  `ExecutionService` per step.
- §20's "approval_requests" was NOT built as a store: approvals stay
  in P-01/P-10; `operations_approval_links` references them.
- Budget design: workflows reference a P-07 `budget_id`; amounts
  travel transiently through P-07's own API; P-12 persists budget
  references and enforcement outcomes only.
- Emergency stop composes existing machinery (P-10 modes, P-08
  pauses, P-04/P-05 stops) — no parallel stop system.

## 3. Architecture implemented

`P12_ARCHITECTURE.md`. Operations package
(`backend/app/operations/`): constants, planner (validation +
templates), state machines, autonomy resolver, decision engine,
scheduling, recovery, verification, and the OperationsService
(pipeline, drive loop, adapters, triggers/tick, approvals
processing, scoped stops, views, reports). Additive wiring in
`Application` (service built last, after security; loop started
outside the test environment) and one router in `app/main.py`.

## 4. Modules integrated

P-01 (tasks substrate, approvals, permissions, audit, event bus,
resource monitor), P-02 (plan import — deterministic baseline
planner only), P-04 (agent registry, capabilities, health, stops),
P-05 (execution adapter with its own policy/verification), P-06
(business registry + lifecycle), P-07 (budgets, spend gate,
approve_spend — the only money path), P-08 (pause state, access
checks), P-09 (learning from verified outcomes), P-10 (broker,
emergency modes, action risk classification), P-11 (frontend host).

## 5. New files and modified files

New: `backend/app/operations/` (10 modules),
`backend/app/database/models/operations.py`,
`backend/app/database/repositories/operations.py`,
`backend/app/database/migrations/versions/3a77efe78faa_*.py`,
`backend/app/api/routes/operations.py`,
`backend/app/api/schemas/operations.py`,
`backend/tests/{p12_support,test_p12_unit,test_p12_integration,
test_p12_scenarios,test_p12_security,test_p12_recovery}.py`,
`backend/scripts/p12_smoke.py`,
`frontend/src/views/Autonomy.tsx` + `Autonomy.test.tsx`,
`docs/autonomous-operations/` (7 documents),
`docs/reports/P12_SMOKE_EVIDENCE.txt`.

Modified: `app/events/events.py` (Operations* event types),
`app/database/models/__init__.py` (registration), `app/main.py`
(router), `app/core/application.py` (wiring + loop lifecycle),
`frontend/src/App.tsx`, `frontend/src/components/shell.tsx` (nav).
Pre-existing tests modified ONLY for migration-head pins, each with
a "P-12 disclosure" comment, strictness preserved: the two P-11
integration pins and the head pins in test_p02/p03/p04/p05
integration files (5 sites).

## 6. Database changes

One additive migration `3a77efe78faa` (down_revision
`193731df4c37`), 14 new tables (listed in the Architecture doc).
Cycle verified by test: 139 → 153 → 139 → 153. **No monetary
column exists in any P-12 table** (structurally checked during
development against the model definitions); amounts appear only
inside decision/evidence JSON as P-07-sourced snapshots, per house
precedent.

## 7. API endpoints

`P12_API_REFERENCE.md` — 30+ routes under `/api/v1/operations`:
status/settings, overview, safety, workflows CRUD + lifecycle,
approvals center + check, autonomy policies + resolve, triggers,
scheduler tick, recovery + dead-letter resolution, per-business
operations, agents, decisions, emergency stop/resume, reports.

## 8. Workflow lifecycle

`P12_WORKFLOW_LIFECYCLE.md` — workflow and task state machines
enforced in the service; VERIFYING gate before COMPLETED;
checkpoints on every settle; dependents of failed steps SKIPPED.

## 9. Autonomy framework

`P12_AUTONOMY_POLICY.md` — Levels 0–4 per global/business/agent/
agent-in-business/workflow scope + action-category caps; effective
level = minimum of ceilings incl. Constitution and P-10 mode caps;
full trace recorded per decision. Owner-only policy writes.
Financial and risk-3 actions require owner approval at every level;
Level 4 adds no execution rights over Level 3 in this build.

## 10. Agent orchestration

Selection is capability-filtered (P-04 catalogue), business-scoped,
active-status and per-agent-concurrency filtered, health-aware, and
recorded as assignment rows with evidence. Mid-workflow
unavailability triggers recorded reassignment (Scenario 6). Agents
act through their own P-01 principals — the broker sees the agent,
not the owner.

## 11. Trigger and scheduling system

Time (once/interval/daily with IANA timezone), event (P-01 bus;
operations-sourced events ignored to prevent feedback loops — a
documented limitation), and threshold triggers (budget utilisation
via P-07, queue depth, failed-workflow count). Fire keys dedupe;
missed runs counted, latest missed instant fires once. One tick
pass (approvals → triggers → scheduled starts → recovery resumes →
deferred re-drives) runs on a background loop outside tests and via
`POST /operations/scheduler/tick`.

## 12. Financial governance

Spend steps call P-07 `request_spend` with `Money` values: Level-1
authorised spends proceed; held spends park on the exact P-01
approval P-07 itself verifies (`financial.spend_approve`, exact
parameters), then complete through `approve_spend`; Level-3 kinds
are structurally rejected (Scenario 7). A budget violation blocks
execution before any substrate call. P-12 deliberately does NOT
call `mark_recorded` — recording the expense remains a finance-side
act in P-07. Projected figures are never read as collected anywhere
in this package.

## 13. Security controls

The §22 pipeline is the only execution path (no public direct-step
API — asserted by test). Definitions are validated against the P-10
action vocabulary and the P-01 handler registry; code-carrying
payloads are rejected. Approvals are hash-bound to exact step
parameters — post-approval tampering fails closed as a policy
violation (named test). Agents never approve their own restricted
actions (P-01 decide role check + self-approval refusal, tested),
never set autonomy policy, never modify others' workflows.
Cross-business reads/creates are denied at the service boundary.

## 14. Failure recovery

`P12_RECOVERY_GUIDE.md` — classification-driven recovery, retry
with P-01-shared backoff (retries are fresh pipeline passes),
dead-letter queue with owner-only resolution, per-target circuit
breakers, startup parking of RUNNING/VERIFYING workflows, and
checkpoint + substrate-idempotency protection against duplicate
execution (Scenario 9: substrate execution count stays 1). A
pipeline exception can no longer stall a workflow silently: the
drive loop converts it into a step failure through the normal
recovery path, with the exception on the audit record (defect
found and fixed during this build; see §20).

## 15. Emergency stop behavior

Scoped stops compose existing machinery: global → P-10
`emergency_stop` mode + P-05 engine stop; financial → P-10
suspension; business → P-08 pause + that business's workflows only
(Scenario 11 proves a second business runs unaffected); agent →
P-04 stop + reassignment. Resume is owner-only at every scope; the
system never restarts itself.

## 16. Command Center integration

New "Autonomous Ops" view (Operations section) with eight tabs —
Overview, Workflows, Agents, Approvals, Scheduler, Recovery,
Safety, Reports — on P-11's components and design tokens. Every
control calls a real endpoint; success renders only from backend
responses; destructive actions use the shared ConfirmationDialog.
The overview states plainly that workflow activity is not revenue.
Bundle: 345.77 kB JS / 99.99 kB gzip (P-11: 328/96).

## 17. Tests executed

Backend (pytest, one full run on final code; tmpfs basetemp +
file-mtime pruner; /tmp 12% before the gate run, 43% after — the
after figure includes earlier development runs' leftovers; the
gate run's own basetemp was pruned continuously and removed
afterwards): **666/666 passed in 538.02s** — 602 pre-existing +
64 new P-12 tests (`test_p12_*`: 29 unit, 6 integration incl. the
migration cycle and the HTTP surface, 15 scenarios, 10 security,
4 recovery).
Frontend (Vitest): **35/35** (30 pre-existing + 5 new Autonomy
tests) and `tsc --noEmit && vite build` clean. Live smoke (real
uvicorn + built frontend): **27/27** checks,
`docs/reports/P12_SMOKE_EVIDENCE.txt`, opening with the
fresh-install honesty check (zero state; 153 tables).

Development history, stated plainly: two earlier full runs on
near-final code ended 658 passed / 6 failed and 662 passed /
4 failed — every failure was a pre-existing migration-head pin
(the standard per-phase pin update; fixed with P-12 disclosure
comments, strictness preserved). Interim P-12-only runs exposed
four real defects, fixed and covered by tests (§20). The P-12
files passed 64/64 across three consecutive runs before the gate
run.

## 18. Test results

Backend gate run (final code): **666 passed, 0 failed, 538.02s**.
Frontend: **35/35**. Smoke: **27/27**. Migration cycle:
139 → 153 → 139 → 153 (test-verified).

## 19. Known limitations

- **No real LLM anywhere**: workflow sources are deterministic
  templates, structured definitions, and P-02 baseline-plan imports
  (FakeProvider-era honesty from P-02 carries over). Free-form text
  is never executed — by design and by test.
- Event triggers ignore operations-sourced bus events (feedback
  guard); an event source allowlist is future work.
- EXECUTE_WITH_LIMITS records its constraints as decision evidence;
  wave sizing honours the global concurrency ceilings, but
  per-decision numeric caps are not yet enforced as quotas.
- Circuit breakers are in-memory per process (a restart closes
  them); the scheduler is a single-process async loop — no
  multi-worker coordination exists anywhere in this stack.
- Spend completion stops at P-07 authorisation; expense recording
  (`mark_recorded`) is intentionally left to P-07-side flows.
- P-05's inherited limits stand: code execution is process
  controls, not a strong sandbox; browser is partial; desktop is
  disabled.
- The load-deferral gate follows
  `Settings.block_nonessential_on_threshold` (production default
  on) — the same switch P-01/P-04 honour.
- Windows behaviour unverified (P-00 carry-over); the target
  hardware is CPU-only (P-04 feasibility verdict stands).

## 20. Unresolved risks

- Defects found by P-12's own tests and fixed during the build:
  (1) an approved step re-parked forever because the decision
  engine didn't treat an existing approved link as satisfying the
  approval requirement; (2) the circuit-breaker refusal ran before
  the task entered RUNNING, so its failure path hit an illegal
  transition and stalled the workflow silently — breaker check
  moved after the RUNNING transition and the drive loop now
  converts pipeline exceptions into recorded step failures;
  (3) naive/aware datetime mixing on SQLite reads in scheduling —
  normalized; (4) the decision engine deferred work under host
  load without honouring the system's threshold switch — gated
  identically to P-01/P-04, and the tick now re-drives deferred
  workflows so a deferral is a pause, not a stall.
- Load sensitivity: this VM is a 1.5-CPU shared host; before the
  deferral fix, CPU saturation produced intermittent deferrals.
  The gate run is the evidence on final code; sustained-load
  behaviour on the owner's hardware is unmeasured.
- Single-process everything (bus, breakers, loop) — scaling beyond
  one host is out of scope for this stack's staging form.

## 21. Performance findings

No load testing was performed (none is meaningful on this host).
Observed: the full backend suite (666 tests) runs in 538s on this
VM; a single workflow drive adds milliseconds of service work per
step plus substrate time; the tick is O(due triggers + active
workflows) with bounded list limits (50). The frontend bundle grew
by ~18 kB JS (~4 kB gzip) for the new section.

## 22. Acceptance scenario results (§23, all 15)

All 15 are real named tests in `tests/test_p12_scenarios.py`:

| # | Scenario | Result |
|---|---|---|
| 1 | Scheduled recurring workflow | PASS — interval trigger fired by tick, completed + verified, fire-key dedupe on second tick |
| 2 | Intelligence plan → governed workflow | PASS — P-02 baseline plan steps imported faithfully; restricted publish step approved by owner |
| 3 | Unauthorized agent purchase attempt | PASS — agent's own approval attempt refused (P-01 role check); substrate untouched until owner approval |
| 4 | Two businesses concurrently | PASS — scoped agents, scoped totals, both verified |
| 5 | Different autonomy per business | PASS — Level 3 in A leaves B at Level 1; B's trace contains no business-policy ceiling |
| 6 | Agent fails mid-workflow | PASS — healthy eligible agent reassigned with a recorded recovery record |
| 7 | Budget would be exceeded | PASS — over-budget spend held for owner (P-07), Level-3 transfer rejected structurally; nothing executed pre-approval |
| 8 | External tool failure | PASS — P-05 failure classified, recorded, dead-lettered; never reported as success |
| 9 | Interruption during long workflow | PASS — crash simulated; recovery parks; resume completes with substrate execution count exactly 1 |
| 10 | Conflicting workflows | PASS — second contender DEFERRED with recorded decision; runs after incumbent; no duplicates |
| 11 | Emergency in one business | PASS — Business A paused (P-08), Business B completed unaffected; non-owner resume refused |
| 12 | Completion without verification | PASS — substrate completed but criteria failed → workflow FAILED, outcome "failed", no learning |
| 13 | Learning from outcomes | PASS — exactly one P-09 record (confidence LOW, mechanically capped) for the verified workflow; none for the failed one |
| 14 | Unauthorized autonomous action | PASS — cross-business create denied, policy write denied, raw-text definition rejected, rejected approval → step never executed |
| 15 | Owner raises autonomy (one workflow) | PASS — workflow-scope row lifts that workflow to Level 3; sibling and the agent's permissions unchanged |

## 23. Recommended next steps

1. Owner gate decision on P-12 (this report + gate summary).
2. P-13 (Multi-business Coordination) per the owner's sequencing
   instruction — its audit can now build on a real operations
   layer.
3. Before any production claim: Windows verification (P-00
   carry-over), a real-demand pilot workflow on a fixture business
   promoted through P-06/P-07 with real evidence, and an
   event-source allowlist for event triggers.
4. AUTONOMUS still has no GitHub repository (P-00 owner item);
   staging + this zip remain the transfer mechanism.
