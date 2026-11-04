# P-04 Implementation Plan: Dynamic Agent Factory

Companion to `P04_PRE_IMPLEMENTATION_AUDIT.md`. Every named symbol below was verified to exist in the checkout before being written into this plan; the compatibility probe at the end of Stage 1 re-asserts them.

## 1. Proposed module structure

Follows the repository's flat-module convention (`opportunities/` is 17 flat files; there are no nested sub-packages anywhere in `backend/app`).

```
backend/app/agents/
    __init__.py        public surface, explicit exports
    templates.py       template CRUD, validation, versioning, clone/publish/deprecate/restore/compare
    capabilities.py    capability catalog, risk + approval levels, L3 prohibition list, check point
    lifecycle.py       validated state machine (11 states), policy-driven suspension/recovery
    factory.py         creation requests, deterministic creation decision, template selection, limits
    assignments.py     assignment validation, delegation depth, output-contract enforcement
    resources.py       per-agent budgets, shared inference semaphore, backpressure policy
    monitoring.py      health states, labelled metrics (measured / estimated / unavailable)
    versioning.py      configuration snapshots, history, deferred safe update, rollback
    governance.py      approval-level mapping onto approvals.risk, audit helpers, emergency wiring
    schemas.py         typed request/response schemas, error categories
backend/app/database/repositories.py    new repos appended in existing style
backend/app/api/routes/agents.py          extended (write ops, lifecycle ops)
backend/app/api/routes/agent_templates.py new
backend/app/api/routes/agent_factory.py   new
```

Business rules live in `agents/`, HTTP in `routes/`, SQL in repositories. No service exceeds ~400 lines; nothing goes into one large file.

## 2. Component responsibilities

| Component | Responsibility | Explicitly NOT |
|---|---|---|
| `templates.py` | version-controlled template definitions; validation gate before any agent exists | executing anything |
| `capabilities.py` | the only place a capability is granted or denied; L3 denials are unconditional | storing secrets, calling tools |
| `lifecycle.py` | the transition graph; rejects invalid transitions | deciding *why* (policy lives in callers) |
| `factory.py` | turns a requirement into CREATE/REUSE/ASSIGN/QUEUE/APPROVAL/REJECT via deterministic checks | trusting an LLM recommendation as a decision |
| `assignments.py` | validates the nine assignment rules; returns structured refusal reasons | running tasks (TaskManager does) |
| `resources.py` | budgets and backpressure over `SystemMonitor` + the shared inference semaphore | measuring what cannot be measured (labels estimates) |
| `monitoring.py` | health states with thresholds; labelled metrics | inventing quality percentages |
| `versioning.py` | snapshots, history, deferred update until a safe state | mutating a busy agent |
| `governance.py` | maps P-04 approval levels onto `approvals`; emits audit + events | bypassing `ApprovalService` |

## 3. Database changes

**Extend (additive only):** `agents` gains `template_id`, `template_version`, `configuration_version`, `parent_agent_id`, `business_id`, `retired_at`, and a CHECK-constrained `status` drawn from the lifecycle states. Existing columns and both live endpoints keep working; new NOT NULL columns get `server_default` (the P-03 lesson) and a populated-database test.

**Nine new tables** (the brief's fourteen logical entities, after removing four that duplicate existing tables):

1. `agent_templates` — identity + current version + status
2. `agent_template_versions` — immutable per-version configuration, `validation_status`, unique `(template_id, version)`
3. `agent_capabilities` — catalog with `risk_level`, `approval_level`, read/write/execute class, `enabled`
4. `agent_permissions` — agent↔capability grants with scope, approval reference, expiry, revocation
5. `agent_assignments` — assignment ledger referencing `tasks.id`, with delegation depth and structured failure reasons
6. `agent_health` — one row per agent, health state + last check + details
7. `agent_metrics` — labelled values: `measurement_type ∈ {measured, estimated, unavailable}`
8. `agent_configuration_history` — snapshots with change reason, author, approval reference
9. `agent_creation_requests` — justification, requested capabilities, resource estimate, decision + reason, approval link

**Deliberately NOT created:** `agent_registry` (→ `agents`), `agent_events` (→ `system_events` with `source` = agent id, plus `audit_events` for security-grade records), `agent_factory_settings` (→ `system_configurations`), and any duplicate of `tasks`/`approvals`.

Foreign keys, unique constraints, indexes on `agent_id`/`task_id`/`template_id`, CHECK constraints on enums, JSON validation in schemas, and transaction boundaries per repository method.

## 4. API changes

Existing conventions: `/api/v1` prefix, `envelope()`, `require_permission`, `limit/offset` pagination, structured errors.

| Brief path | Implemented as | Permission |
|---|---|---|
| registry read/write/lifecycle | `/api/v1/agents…` (extend existing; add POST, PATCH, `/suspend`, `/resume`, `/retire`) | `agents.read` / `agents.write` / `agents.retire` |
| templates | `/api/v1/agent-templates…` incl. `/clone`, `/validate`, `/publish`, `/versions` | `agents.templates.*` |
| factory | `/api/v1/agent-factory/evaluate`, `/create`, `/requests…`, `/approve`, `/reject`, `/status`, `/resources`, `/settings`, `/emergency-stop` | `agents.factory.*` |
| capabilities & permissions | `/api/v1/agent-capabilities`, `/api/v1/agents/{id}/permissions…` | `agents.capabilities.read`, `agents.permissions.grant` |
| assignment & monitoring | `/api/v1/agents/{id}/assign`, `/assignments`, `/health`, `/metrics`, `/events` | `agents.read` + `agents.metrics.read` |

Idempotency keys on creation and assignment (the `tasks.idempotency_key` precedent). Approve/reject endpoints commit the approval row **before** reporting success. No endpoint returns secrets; error payloads carry the §21 categories only.

## 5. Integration points

- **P-01:** `TaskManager.submit` executes assigned work; `approval_required` gating reused for Level-2 creations; `EmergencyController` + `apply_emergency_stop` extended so factory emergency stop is one deterministic call.
- **P-02:** `ModelRouter` is the only inference path (no per-agent processes); `CapabilityRegistry` informs but does not govern — governance lives in `agents/capabilities.py`; `PromptInjectionDetected` handling reused for untrusted content.
- **P-03:** creation requests may cite an `opportunities.id` as their business justification; nothing in P-03 is modified.
- **Events:** new strings added to `EVENT_TYPES` atomically with the code that publishes them.

## 6. Permission model

Add-only catalog changes: `agents.read` (fixes the audit §9.1 inconsistency), `agents.write`, `agents.retire`, `agents.templates.read`, `agents.templates.write`, `agents.capabilities.read`, `agents.permissions.grant`, `agents.factory.read`, `agents.factory.approve`, `agents.factory.admin`, `agents.metrics.read`. Owner bootstrap gains them; system principals do not.

Approval levels map onto `approvals.risk`: **L0** autonomous (policy allows, audit records), **L1** conditional (policy conditions checked in code, ceiling values from settings), **L2** owner approval (an `approvals` row must reach `granted` before the capability exists), **L3** prohibited (hard deny list in `capabilities.py`; no approval code path can reach it). Checks happen in backend policy code at grant time *and* at every tool boundary in Stage 6.

## 7. Resource management strategy

One shared `asyncio.Semaphore`, sized `min(settings.inference_max_concurrent, factory ceiling)`, wraps `ModelRouter` calls; logical agents are configurations, never processes. Per-agent budgets (concurrent tasks, task duration, retries, inference requests per task, child agents, queue occupancy) come from the template and are enforced in `resources.py` and `assignments.py`. Backpressure: when `SystemMonitor.resource_pressure` reports pressure, nonessential creation is refused, low-priority assignments queue, eligible idle agents suspend, and a `ResourceThresholdExceeded` event reaches the owner. Values that cannot be measured per agent are stored with `measurement_type='estimated'`.

## 8. Testing strategy

New modules: `test_agents_templates.py`, `test_agents_factory.py`, `test_agents_lifecycle.py`, `test_agents_permissions.py`, `test_agents_assignments.py`, `test_agents_resources.py`, `test_agents_monitoring.py`, `test_agents_api.py`, `test_agents_security.py`. Inference is deterministic via the existing `NoRuntimeProvider`; the suite never needs a paid API or a GPU. The 521 pre-existing tests must stay green at every stage commit. Security tests implement the brief's ten prohibitions verbatim; resource tests cover caps, backpressure, duplicate-initialisation prevention, idle suspension and failed-initialisation recovery; acceptance scenarios A–J each map to at least one named test.

## 9. Migration and rollback strategy

One additive Alembic revision per schema stage, chained after `72ee9705e18f`, authored with the `portable_alter_table` shim and dialect-conditional batch mode (ADR-0023). Every revision implements `downgrade()`. Verification per revision: offline Postgres DDL render (35→N CREATE TABLE, zero SQLite-isms), SQLite round trip on a **populated** database, byte-identical schema hash where applicable. Pushed revisions are never amended. Rollback = `alembic downgrade` plus the feature flags, since all new behaviour is behind new tables and new permission codes that old code ignores.

## 10. Stage → commit map

Stage 2 schema + schemas · Stage 3 registry + templates · Stage 4 creation engine · Stage 5 permissions + governance · Stage 6 assignment + orchestration · Stage 7 resources · Stage 8 lifecycle + monitoring · Stage 9 reported as deferred (no frontend exists) · Stage 10 full suite + security + resource tests + reports. Each stage is one commit pushed to this branch; documentation is written from observed behaviour, never from intent. **P-05 does not begin (§28).**
