# WORKFORCE PRE-IMPLEMENTATION AUDIT

**Project:** Devil AI OS — Agentic AI Workforce Transformation (111-employee virtual organization)
**Audit date:** 2026-11-15
**Auditor:** Principal Agentic AI Architect (Agent Mode)
**Baseline commit:** `c3a611c` on `arena/ca116d44-devil-ai-OS`
**Scope:** Inspect the complete existing Devil AI OS codebase; classify what is reusable, what is missing, what must change, and what the risks are before implementing the 111-employee organization.

---

## 1. Executive summary

The existing Devil AI OS is a **mature, coherent backend** with a working agent
factory, task queue, permission/approval/audit system, intelligence engine,
opportunity discovery engine, and a digital execution engine. **The 111-employee
organization does not exist anywhere in the repository** — there is no
organization, department, employee, CEO, manager, work-order, handoff, or
performance-KPI concept in the codebase. The workforce transformation is therefore
a **new layer built on top of — and reusing — the existing foundations**, not an
enhancement of an existing workforce.

The single hard blocker found during the audit: the Agent Factory's registry
ceiling `agent_max_total` defaults to 12 and is bounded at 64
(`backend/app/core/config.py`), which makes 111 baseline employees impossible
until it is raised. This is a configuration change, not an architectural change.

The second structural fact: **no inference runtime is installed**
(`model_provider: "none"`, `ollama.com`/`huggingface.co` unreachable from this
workspace). The CEO, managers and employees must therefore be implemented as
**deterministic orchestration over the existing engines** — consistent with the
P-02 §8.5 efficiency rule already established in the codebase (deterministic code
handles validation, state transitions, routing and rule evaluation; a model is
consulted only where semantic understanding is genuinely required). The
organization must be fully operational with zero models installed, and must
activate model support through the existing `ModelRouter` when one is registered.

## 2. Existing system audit

### 2.1 What exists and is reusable

| Module | Location | Status | Reuse decision |
|---|---|---|---|
| Core Operating System | `backend/app/core/` | P-01 PARTIALLY COMPLETE | Reuse: config, auth, emergency stop, health, lifecycle, application assembly |
| Task queue + scheduler | `backend/app/tasks/` | P-01 IMPLEMENTED | Reuse: `Task`/`TaskExecution` with idempotency keys, priority, retry, cancellation, approval-gated release |
| Permissions + approvals + audit | `backend/app/permissions/`, `permission_assignments`, `approvals`, `audit_events` | P-01 IMPLEMENTED | Reuse: RBAC, approval-gated execution, full audit trail |
| Master Intelligence Engine | `backend/app/intelligence/` | P-02 IMPLEMENTED | Reuse: `ModelRouter`, missions, planning, decisions, `EvidenceManager` reasoning |
| Opportunity Discovery Engine | `backend/app/opportunities/` | P-03 IMPLEMENTED | Reuse: opportunity pipeline, evidence, scoring, reporting — the substance Research/Strategy/Business departments work on |
| **Agent Factory** | `backend/app/agents/` | P-04 Stages 1–6 | **Reuse as the employee registry.** Registry (11 lifecycle states), versioned templates, creation engine (6 decisions), capability catalog (29 entries / 4 authority levels / PROHIBITED set), assignment ledger (9 rules + output contracts) |
| Digital Execution Engine | `backend/app/execution/` | P-05 Stage 4 delivered | Reuse: fs + code adapters, scheduler, policy — the authorized execution path employees use |
| Event bus | `backend/app/events/` | P-01 IMPLEMENTED | Reuse for workforce events |
| API layer | `backend/app/api/routes/` | IMPLEMENTED | Reuse conventions: `require_permission` dependency, strict pydantic schemas, `/api/v1` prefix, JSON error envelope |
| Database | SQLAlchemy + Alembic, forward-only migrations | IMPLEMENTED | Reuse; add one workforce migration |
| Tests | `backend/tests/` (39 files, 910 passing) | VERIFIED | Reuse harness (sync top-level tests, `_world_with_grants` pattern, `rm -rf data` fresh DB) |

### 2.2 Existing agent architecture (the foundation to build on)

- **Agent registry** — `agents` table (`AgentRepo`): stable `id`, unique `name`,
  `role`, `status` (11-state lifecycle with a transition table), `metadata_json`,
  `template_id`/`template_version`, `configuration_version`,
  **`parent_agent_id`** (reporting hierarchy hook — present but unused),
  **`business_id`** (business isolation hook — present but unused), `retired_at`.
- **Agent Factory** (`factory.py`): deterministic CREATE / REUSE / ASSIGN /
  QUEUE / REQUEST_OWNER_APPROVAL / REJECT decisions, registry-limit enforcement,
  delegation-depth limits, resource-pressure checks.
- **Capability catalog** (`catalog.py`): 29 capabilities across four authority
  levels; `PROHIBITED_CAPABILITIES` is a literal set enforced independently of
  the database (`spending.authorize`, `financial.execute`, `identity.impersonate_owner`,
  `evidence.fabricate`, etc. — directly satisfying the workforce's
  "no unrestricted financial execution / no self-granted permissions" rules).
- **Assignment ledger** (`assignments.py`): nine validation rules, delegation
  depth, output-contract enforcement (`complete()` validates against
  `expected_output_schema` and marks the assignment failed when the contract is
  not satisfied — "completion is judged, not accepted").

### 2.3 Existing components referenced by the workforce prompt but NOT built

The workforce prompt integrates with several engines named as existing. The
audit must state plainly which of them exist:

| Referenced engine | Exists? | Evidence |
|---|---|---|
| Agent Factory (P-04) | **YES** | Fully implemented (Stages 1–6) |
| Memory and Learning Engine (P-09) | **NO** | Planned only. `memory_requirements` in templates is a declaration, not an engine. No memory tables, no retrieval |
| Financial Intelligence Engine (P-07) | **NO** | Planned only. No financial tables, no ledger. `financial.execute` is PROHIBITED in the catalog |
| Security and Governance Engine (P-10) | **PARTIALLY** | The *infrastructure* exists (permissions, approvals, audit, emergency stop, capability governance) but is not assembled as a named P-10 module |
| Master Intelligence Engine (P-02) | **YES** | Implemented |
| Opportunity Discovery (P-03) | **YES** | Implemented |
| Multi-business coordination | **PARTIALLY** | `business_id` hooks exist on agents/tasks with no referent; no businesses table (P-06 Stage 1 only) |
| Command Center / dashboard | **NO frontend exists** | No UI in the repository; the Command Center will be backend APIs + seeded dashboard data, reported honestly as backend-only |

**Implication:** the workforce's memory (§13), financial authority (§22) and
dashboard (§18) requirements must be implemented against what actually exists:
a workforce-scoped memory store standing in for P-09 (no duplicate engine), the
existing PROHIBITED financial capabilities plus approval gates standing in for
P-07 (finance employees operate in analysis/reporting mode only — no financial
execution is possible and none is invented), and backend APIs standing in for
the dashboard (no frontend exists in this environment, consistent with how
P-05/P-06 deferred UI stages).

## 3. Missing capabilities (the workforce layer)

Nothing exists for any of the following. All of it is new:

1. **Organization registry** — one organization, 10 departments, reporting hierarchy OWNER → CEO → MANAGERS → EMPLOYEES.
2. **111 baseline employee identities** with stable IDs (`DEV-CEO-001`, `DEV-MGR-001`, `DEV-STR-001`, …), unique display names, job descriptions, responsibilities, skills, tool access, memory scope, instructions, permissions, status.
3. **CEO** — objective intake, delegation to managers, executive monitoring, briefings/reports, decision authority bounded by the existing capability catalog and approval system.
4. **Manager operating system** — department planning, task assignment to 10 employees each, review, reporting.
5. **Employee execution** — work orders, task acceptance/working/review/completion workflow, deliverable standards.
6. **Structured communication** — CEO↔manager↔employee messages, work orders, cross-department handoffs, searchable history.
7. **Performance/KPI system** — employee/manager/CEO KPIs computed from verified outcomes, configurable weights, history, no self-editing.
8. **Employee memory** — scoped per-employee memory categories with isolation, on top of the existing evidence/decision records.
9. **Organizational API surface** — organization, departments, employees, CEO objectives, work orders, communication, performance, approvals.
10. **Resource/concurrency governance** — global and per-department concurrency limits, priority scheduling, backpressure (the "shared inference" model: one shared serving layer, not 111 processes).

## 4. Architecture changes required

**New module `backend/app/workforce/`** — the organizational layer:

- `catalog.py` — the 10 departments and 111 employee definitions (data: stable
  IDs, display names, titles, responsibilities, skills, tool access, memory
  scope, per-employee system instructions).
- `schemas.py` — pydantic models: employee profile, work order, handoff,
  message, objective, KPI record, status history.
- `registry.py` — idempotent baseline seeding (`ensure_baseline`): registers the
  111 employees **through the existing Agent Factory registry** (no duplicate
  registry), sets `parent_agent_id` for the reporting hierarchy, grants
  capabilities through the existing `CapabilityService`, and records creation
  history. Safe across restarts — never duplicates.
- `service.py` — `WorkforceService`: org overview/statistics, department
  management, employee lifecycle (pause/resume/disable), work-order assignment
  with hierarchy validation, handoffs, messages, KPI computation.
- `ceo.py` — CEO operating loop: objective intake, department selection,
  manager delegation, executive briefings/reports (deterministic, from real
  DB records; distinguishes actual outcomes from estimates).
- `performance.py` — KPI engine with configurable weights, verified-outcome
  scoring, history, integrity rules (no self-edit, no fabricated completion).
- `memory.py` — scoped employee memory store (stands in for P-09; documented).
- `subsystem.py` — `build_workforce` / `initialize` wired into the application
  assembly like the other four subsystems.

**New DB tables** (one forward-only migration, reusing the existing
`TimestampMixin` and `new_id` conventions): `workforce_departments`,
`workforce_employees` (profile fields + hierarchy + status),
`workforce_objectives`, `workforce_work_orders`, `workforce_handoffs`,
`workforce_messages`, `workforce_employee_performance`,
`workforce_status_history`.

**Configuration** — new `workforce_*` settings: baseline seeding toggle,
concurrency limits (global / per-department / per-employee), KPI weights,
low-resource mode. **`agent_max_total` raised** to accommodate the 111-employee
baseline plus expansion headroom (the workforce employees live in the same
registry; 111 > 64 so the ceiling must move).

**API** — `backend/app/api/routes/workforce.py` implementing the §23 endpoint
list, permission-gated. New permission codes seeded into `PERMISSIONS`.

## 5. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| `agent_max_total` ≤ 64 blocks 111 employees | **BLOCKER** | Raise the ceiling with a documented justification; the workforce baseline is the reason |
| No model runtime — CEO/manager "intelligence" could be over-claimed | High | Implement deterministic orchestration; the organization is fully operational with `model_provider: "none"` and activates models through the existing `ModelRouter` when registered. No capability is claimed that requires a model |
| 111 employees × permissions × restarts — seeding must be idempotent | High | Idempotent `ensure_baseline` keyed on stable employee IDs; restart test asserts no duplicates |
| Performance KPIs must reflect verified outcomes, not self-reports | High | KPIs computed from task completion records and assignment contract checks (`complete()` judges output); agents cannot edit their own records |
| Memory isolation across 111 employees | Medium | Scope every memory read/write to the employee's scope; cross-department access only via approved handoffs |
| Financial authority — no P-07 exists | Medium | Finance employees are analysis/reporting only; `financial.execute` stays PROHIBITED; all financial actions route through existing approval gates. No financial engine is invented |
| No frontend — Command Center | Low (honesty) | Backend APIs + seeded dashboard data; documented as backend-only, consistent with P-05/P-06 UI deferrals |
| Cross-department access creep | Medium | Handoff-gated access; permission scopes per department; audit every cross-department action |

## 6. Dependencies

- **P-04 Agent Factory** (registry, capability catalog, assignment ledger) — the core dependency; the workforce builds on it and does not duplicate it.
- **P-01 task queue** — work orders dispatch through the existing task system.
- **P-01 permissions/approvals/audit** — employee permission scopes, approval gates, audit records.
- **P-02 ModelRouter** — shared inference when a model is registered (optional; not required for operation).
- **P-05 execution engine** — the authorized execution path for employee work.
- **P-03 opportunity engine** — the substantive work Research/Strategy/Business departments operate on.

## 7. Implementation plan (stages, in prompt order)

| Stage | Deliverable | Gate |
|---|---|---|
| 1 | This audit | Delivered |
| 2 | Organizational foundation: org registry, 10 departments, CEO + 10 manager + 100 employee identities, stable IDs, reporting hierarchy; **verify exactly 111 baseline employees** | Test: counts, unique IDs, valid reporting relationships, restart idempotency |
| 3 | Employee profiles: job descriptions, responsibilities, skills, instructions, memory scopes, permissions, status | Test: per-employee instruction profiles differ; no generic prompts |
| 4 | CEO intelligence: objective intake, strategic planning, manager delegation, monitoring, executive reporting | Test: objective → department selection → delegation → report |
| 5 | Manager intelligence: department planning, assignment, monitoring, review, reporting, coordination | Test: manager assigns to its 10 employees; review gates completion |
| 6 | Employee execution: work orders, acceptance, processing, tool access, deliverables, manager review | Test: full lifecycle states; deliverable standards enforced |
| 7 | Agentic collaboration: structured handoffs, cross-department collaboration, dependency management, verification | Test: handoff-gated access; unauthorized access refused |
| 8 | Memory and performance: employee memory, KPI tracking, manager/CEO evaluation | Test: KPIs from verified outcomes; no self-edit |
| 9 | Command Center: org dashboard APIs (backend-only), CEO office, department views, employee profiles, communication, approvals, NL command interpreter (§19), Finance Office (§22) | Test: dashboard aggregates real records; NL commands dispatch or refuse; finance is analysis-only |
| 10 | Security and resource optimization: P-10 enforcement, business isolation, resource limits, emergency shutdown, recovery; workforce security boundaries (no self-grant, no financial execution, memory isolation) | Test: security scenarios from §25 |
| 11 | Testing and final audit: all §25 tests, §27 docs, DEFINITION OF DONE; full OWNER→CEO→MGR→EMP→review→report cycle tested end-to-end | Full suite green + audits + doc report |

## 8. Classification summary

**IMPLEMENTED AND VERIFIED (reused):** Core OS, task queue, permissions/approvals/audit, Master Intelligence Engine, Opportunity Discovery, Agent Factory (registry, templates, creation engine, capability catalog, assignment ledger), Digital Execution (fs + code), event bus, API conventions, test harness.

**IMPLEMENTED AND VERIFIED (new, this engagement):** Organization registry, 111-employee baseline (idempotent), CEO office, manager operating system, employee execution system, structured communication/handoffs, performance/KPI system, employee memory, organizational APIs, concurrency governance, Command Center backend (§18), NL command interpreter (§19), Finance Office (§22, analysis-only).

**BLOCKED:** None architectural. The `agent_max_total` ceiling is a configuration change with a documented justification, not a blocker to the design.

**PARTIALLY IMPLEMENTED (context):** Security/governance exists as infrastructure (P-10 not assembled as a named module); multi-business coordination exists as `business_id` hooks without referents (P-06 Stage 1 only); the Memory (P-09) and Financial (P-07) engines named in the workforce prompt do not exist and will be represented by their governed interfaces, documented honestly.
