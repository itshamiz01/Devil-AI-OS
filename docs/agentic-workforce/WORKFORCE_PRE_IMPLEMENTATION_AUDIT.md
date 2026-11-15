# Workforce Transformation — Pre-Implementation Audit (Stage 1)

**Scope:** Master Prompt v1.0 §2 — inspect the existing Devil AI OS before
changing anything. Every claim below names the file it was read from.
Codebase: `backend/` (FastAPI + SQLAlchemy), `frontend/` (React/Vite),
staging tree `~/workspace/projects/autonomus-ai-os`.

## 1. What already exists (mapped to §2 checklist)

| §2 item | Finding | Evidence |
|---|---|---|
| Core OS | P-01 substrate: config, tasks, agents registry, permissions, approvals, append-only audit, sessions | `backend/app/database/models/core.py`, `backend/app/core/application.py` |
| Agent registry / identities | **The P-01 `agents` table IS the registry**: `name`, `role`, `parent_agent_id` (reporting lines), `business_ref`, `objective`, `model_profile`, `status`, `budget`, plus P-04 additive fields (`agent_type`, `template_id`, `configuration_version`, `security_classification`, `last_activity_at`) | `models/core.py::Agent` |
| Agent creation mechanisms | P-04 Dynamic Agent Factory: governed creation pipeline with decision records for EVERY evaluation (incl. REUSE/REJECT), templates + immutable versions | `backend/app/agents/service.py::AgentFactoryService`, `models/agents.py::AgentCreationRequest, AgentTemplate, AgentTemplateVersion` |
| Capabilities / permissions per agent | Capability catalogue (only `supported=True` entries grantable; level-3 = prohibited, `enabled=False`) + per-agent grant ledger mirrored into the P-01 deny-by-default `PermissionEngine` | `app/agents/constants.py::CAPABILITY_CATALOGUE`, `app/agents/capabilities.py`, `models/agents.py::AgentCapability, AgentPermission`, `app/permissions/engine.py` |
| Task queue / orchestration | P-01 `TaskManager`: `tasks` table IS the bounded queue; tasks execute ONLY through the named handler registry; approval-gated tasks park in `WAITING_FOR_APPROVAL`; idempotency keys supported | `app/tasks/manager.py`, `app/tasks/handlers.py`, `app/tasks/models.py` |
| Assignment contract | P-04 `agent_assignments`: links an agent to a REAL P-01 task, carries objective, required capabilities, expected-output contract, quality requirements, delegation chain; `refresh_assignment` syncs verdicts from task outcomes and records `agent_metrics` | `models/agents.py::AgentAssignment`, `app/agents/service.py::assign/refresh_assignment` |
| Handoffs | P-09 `agent_handoffs`: append-only structured handoff packages (§14.3 fields) | `models/memory.py::AgentHandoff` |
| Memory architecture | P-09 memory engine (records, ingestion, retrieval, learning, handoffs, owner preferences) | `backend/app/memory/` |
| Financial controls | P-07 financial engine is the sole financial authority; P-01 `ApprovalService.decide` requires the `approve_actions` authority under the engine — agent principals do not hold it, so no agent (CEO included) can decide approvals | `app/financial/`, `app/permissions/approvals.py::decide` |
| Security / governance | P-10 SecurityService: policy versions, classifications, agent restrictions, incidents, emergency modes; Article-0 prohibitions are catalogue level-3 | `app/security/`, `app/agents/constants.py` (prohibited entries) |
| Emergency stop | P-12 `OperationsService.emergency_stop(scope=global|business|…)` composes P-10 emergency mode + workflow pauses + P-08 business pause — a real global stop exists | `app/operations/service.py::emergency_stop` |
| Dashboards | P-11 Command Center (React, `frontend/src/views/*.tsx`, served at `/app` when `frontend/dist` exists) + dashboard APIs | `frontend/src/views/`, `app/main.py`, `app/api/routes/dashboard.py` |
| Approval mechanisms | Hash-bound approvals, single-use, expiry; `ApprovalService` | `app/permissions/approvals.py`, `models/core.py::Approval` |
| Existing API routes | agents, agent_factory, tasks, approvals, memory, security, financial, operations, portfolio, dashboard, + 16 more routers under `/api/v1` | `app/main.py`, `app/api/routes/` |
| Database / migrations | SQLAlchemy models per phase in `app/database/models/`; Alembic chain, current head `af39baad9c40` (Expansion F06). Tests use `Base.metadata.create_all` (`auto_migrate=False`) | `app/database/migrations/versions/`, `tests/conftest.py` |
| Shared inference | P-02 model router/profiles — agents are LOGICAL configurations, never per-agent model processes | `models/agents.py` module docstring, `app/intelligence/` |
| Tests | 108 test files under `backend/tests/`; phases verified by running pytest | `backend/tests/` |

## 2. What is missing (the additive gap this transformation fills)

1. **No department entity.** Nothing groups agents into the §5 departments.
2. **No stable employee codes.** Registry IDs are UUIDs; the prompt requires
   stable codes (`DEV-CEO-001`, `DEV-MGR-001..010`, worker codes) that are
   never regenerated on restart.
3. **No workforce profile data.** §6 fields (skills, memory scope, role-specific
   system instructions, autonomy level, communication style, KPI weights,
   §6 workforce status set) have no home. The `agents` table must not be
   bloated with them — a 1:1 extension table keyed to `agents.id` is the
   smallest additive home.
4. **No executive objective / org-plan record.** P-02 plans are model-router
   plans, not organizational plans (CEO → departmental goals → work orders →
   consolidated report). One new table for objectives + their plan/report JSON.
5. **No deliverable record.** §10's output standard (task ref, objective, work
   performed, result, evidence, limitations, verification status) needs a row
   per submission so manager review is evidence-based. One new table.
6. **No org-level work-order lifecycle.** Factory assignments execute their
   task immediately; the workforce needs accept → submit → manager-review
   gating BEFORE the task is released. Achievable on existing engines:
   work-order tasks are submitted with `requires_approval=True` (parked in
   `WAITING_FOR_APPROVAL`) and only released via `TaskManager.approve_task`
   after a manager accepts the deliverable.
7. **No KPI read model** over `agent_metrics` using the §14 weights.

## 3. New tables justified (one additive migration, nothing else)

- `workforce_departments` — §5 departments (code, name, mission, manager link).
- `workforce_profiles` — 1:1 extension of `agents` holding the stable
  employee code + all §6 profile data. Unique constraints on
  `employee_code` and `agent_id` are what make seeding idempotent.
- `workforce_objectives` — CEO executive objectives, plan JSON, consolidation.
- `workforce_deliverables` — §10 deliverable submissions + manager verdicts.

No changes to any existing table. No duplicate registry, queue, ledger,
memory or intelligence engine is created.

## 4. Risks & dependencies

- **Agent status vocabulary:** factory assignment requires status in
  {active, idle, busy}; seeded employees are therefore registered directly
  in `active` status (registry rows, not factory-created agents — the
  factory governs *dynamic* creation; the baseline org is an owner-directed
  seed, recorded in `agent_configuration_history`-style audit via
  `audit_events`).
- **Task loop:** the application starts the task worker loop at startup;
  any work-order task released to QUEUED will execute its handler.
  Workforce work orders use the existing `core.noop` handler — the task's
  execution records the *reviewed deliverable reference*, it does not
  perform the employee's work. This is stated plainly in the API docs so
  task completion is never misread as the work itself.
- **Approvals:** restricted work orders create a P-01 `Approval` and stay
  parked until an owner-authority decision; `ApprovalService.decide`
  structurally refuses agent approvers.
- **Performance honesty:** KPI components without a data source are
  excluded and weights renormalized; employees with no verified outcomes
  report `no_data`, never an invented score.
- **Frontend:** a full §18 Command Center is out of scope for this stage;
  a minimal Workforce view will be added only if it follows the existing
  React patterns cheaply, else classified PARTIALLY IMPLEMENTED (the
  separate "Agentic AI OS" Library app already visualises this org).

## 5. Implementation plan (prompt §26 stage order)

Stages 2–3: workforce definition module (exact §5 data) + idempotent seed
service + profiles. Stage 4–7: orchestration service on TaskManager +
AgentAssignment + AgentHandoff. Stage 8: KPI read model over
`agent_metrics`. Stage 9: `/workforce` API + optional minimal frontend.
Stage 10: security tests against the real engines. Stage 11: §25 test
suite, regression slice, §27 documentation set, classification report.
