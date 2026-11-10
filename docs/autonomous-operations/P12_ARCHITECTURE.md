# P-12 Architecture — Autonomous Operations Engine

Status: as built and verified in staging, 2026-11-09. Companion to
`P12_PRE_IMPLEMENTATION_AUDIT.md` (the §2 audit that scoped this
design) and `P12_IMPLEMENTATION_REPORT.md`.

## Position in the system

P-12 is the operations layer above the accepted engines. It owns
**workflows** (governed, multi-step, multi-agent units of autonomous
work) and drives them through exactly one pipeline. It owns no
authority of its own: permissions, approvals, execution, money,
business lifecycle, survival state, memory and security modes all
remain with their owning phases.

```
        ┌────────────────────────────────────────────────────────┐
        │                P-12 Autonomous Operations               │
        │  workflows · triggers · autonomy policy · decisions ·   │
        │  recovery · scoped emergency stop · reports             │
        └──────┬───────┬────────┬────────┬────────┬───────┬───────┘
               │       │        │        │        │       │
        P-01 tasks  P-02     P-04     P-05     P-07    P-08/P-09/P-10
        (substrate) (plans)  (agents) (tools)  (money) (survival /
                                                        memory /
                                                        security)
```

## Components (`backend/app/operations/`)

| Module | Responsibility |
|---|---|
| `constants.py` | Status vocabularies, level names, action-class → P-01 permission map, default engine settings, spend-kind alignment with P-07. |
| `planner.py` | Definition validation (structure, DAG, cycle detection, payload-code rejection, action-class vocabulary, handler registry check, budget-reference rules), deterministic templates, plan import mapping, definition hashing. |
| `state_machine.py` | Workflow and task transition maps — the ONLY legal state moves, enforced in the service. |
| `autonomy.py` | Pure autonomy resolver: min-of-ceilings across scopes with the full trace. |
| `decisions.py` | Pure §12 decision engine: ordered rules → EXECUTE / EXECUTE_WITH_LIMITS / REQUEST_APPROVAL / PAUSE / DEFER / ESCALATE / RESEARCH_MORE / REJECT with evidence. |
| `scheduling.py` | Schedule computation (once / interval / daily with timezone), missed-run counting, fire keys. |
| `recovery.py` | Failure classification, retry eligibility, backoff (delegates to P-01's `backoff_delay`), circuit breaker. |
| `verification.py` | Acceptance-criteria evaluation producing verified / failed / unverified. |
| `service.py` | `OperationsService`: the pipeline, drive loop, adapters, triggers + tick + background loop, approvals processing, scoped emergency stop/resume, views (overview, businesses, agents, approvals, recovery, safety), reports, startup recovery. |

## The execution pipeline (§22) — the only path

```
Proposal (template / definition / P-02 plan import / trigger)
  → Structured validation (planner.py; definitions only, never raw text)
  → Agent selection (capability + business scope + health + concurrency,
    recorded as an assignment with evidence)
  → Decision engine (facts: security mode, business state, budget via
    P-07, agent health, load, conflicts, autonomy resolution)
  → Authorization (P-10 PermissionBroker; deny is final)
  → Approval if required (P-01 approvals, hash-bound to the exact
    step parameters; links recorded in operations_approval_links)
  → Execution adapter (P-01 TaskManager handlers / P-05
    ExecutionService / internal deterministic runners)
  → Independent verification (acceptance criteria; P-05's own
    verified outcome where it applies)
  → Audit + workflow event + checkpoint
  → Learning (P-09, verified outcomes only)
```

There is no other route to a substrate from this package: no public
method executes a step outside `_run_step`, and definitions are
validated before any of it. See `P12_WORKFLOW_LIFECYCLE.md` for the
state model and `P12_AUTONOMY_POLICY.md` for the level semantics.

## Persistence (14 tables, migration `3a77efe78faa`)

`autonomous_workflows`, `operations_workflow_versions`,
`operations_workflow_tasks`, `operations_workflow_executions`,
`operations_workflow_checkpoints`, `operations_workflow_events`,
`operations_triggers`, `operations_assignments`,
`operations_approval_links`, `operations_recovery_records`,
`operations_dead_letter`, `operations_autonomy_policies`,
`operations_decisions`, `operations_reports`.

Deliberately absent: any monetary column (money lives only in P-07;
P-12 stores budget references and enforcement outcomes), any approval
store (P-01's, referenced by `operations_approval_links`), any
scheduler table duplicating P-01's task store (triggers are P-12's
because no trigger concept existed — the audit documents this).

## Scheduling

A single async tick loop (started by `Application` outside the test
environment; interval from owner-governed settings, minimum 5s)
performs one pass: approval resolution → due time/threshold triggers
→ SCHEDULED starts → RECOVERY_PENDING resumes → RUNNING workflows
with deferred steps re-driven. Event triggers subscribe to the P-01
bus. The tick is also callable directly (`POST /operations/tick`) and
is idempotent: fire keys dedupe trigger fires; substrate idempotency
keys dedupe step execution.

## Frontend

`frontend/src/views/Autonomy.tsx` extends the P-11 Command Center
(nav: Operations → Autonomous Ops) with eight tabs — Overview,
Workflows, Agents, Approvals, Scheduler, Recovery, Safety, Reports —
on the existing components and design tokens. All controls call the
operations API; state shown comes from backend responses only.
