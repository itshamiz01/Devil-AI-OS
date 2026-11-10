# P-04 IMPLEMENTATION PLAN — Dynamic Agent Factory

Companion to `P04_PRE_IMPLEMENTATION_AUDIT.md` (§24 Stage 1). Stage order follows
P-04 §24 stages 1→10; Stage 9 (frontend) is **not applicable** — no frontend exists
in staging (audit §9); §20 data is exposed via API for P-11.

## 1. Module structure (repo convention: one flat package per phase)

`backend/app/agents/`
- `__init__.py` — package marker + public names.
- `constants.py` — §5.2 role taxonomy (28 roles / 6 categories), capability catalogue
  seed (§8.1: name, category, risk, approval level 0–3, action class, mapped P-01
  permission, `supported` flag, resource requirements), factory setting defaults,
  health thresholds, backpressure thresholds, seed template definitions.
- `errors.py` — §21 error categories as `AutonomusError` subclasses:
  TEMPLATE_INVALID (422), AGENT_NOT_FOUND (404), AGENT_NOT_ACTIVE (409),
  CAPABILITY_NOT_AUTHORIZED (403), APPROVAL_REQUIRED (409),
  RESOURCE_LIMIT_EXCEEDED (429), CREATION_LIMIT_REACHED (429),
  ASSIGNMENT_REJECTED (409), LIFECYCLE_TRANSITION_INVALID (409),
  MODEL_PROVIDER_UNAVAILABLE (503), INITIALIZATION_FAILED (422),
  EXECUTION_TIMEOUT (408), CONFIGURATION_VERSION_CONFLICT (409),
  CAPABILITY_PROHIBITED (403), CAPABILITY_UNSUPPORTED (422).
- `lifecycle.py` — §11 state machine: states, transition graph (incl. documented
  legacy bridge from P-01 `created`), `validate_transition`.
- `validation.py` — template validation rules (§6): required fields, capability
  existence/level checks, restricted∩allowed = ∅, no Level-3 capability, budget
  within factory ceilings, model-profile existence, output-schema shape.
- `templates.py` — `TemplateService`: create/read/update(new draft version)/clone/
  publish/deprecate/validate/compare/restore; versions immutable once written.
- `capabilities.py` — `CapabilityService`: catalogue reads; grant / revoke /
  request flows; the grant ledger (`agent_permissions`) + mirror into the P-01
  `permissions` table (allow on grant, explicit deny on revoke); expiry sweep.
- `resources.py` — `AgentResourceManager`: budget checks against template/agent
  budgets, host pressure from `SystemMonitor`, §10.4 backpressure ladder
  evaluation, shared-inference concurrency gate (counter around the P-02 router).
- `scaling.py` — `ScalingPolicy`: deterministic §14.1 evaluation →
  KEEP_CURRENT_CAPACITY / REASSIGN_WORK / INCREASE_CONCURRENCY /
  CREATE_SPECIALIZED_AGENT / QUEUE_WORK / REDUCE_AGENT_COUNT /
  REQUEST_OWNER_APPROVAL, with recorded factors + economic-justification fields.
- `memory_interface.py` — §15 scoped interface for P-09 (`AgentMemoryInterface`
  protocol + `P04MemoryInterface`): serves only data P-04 legitimately owns
  (agent configuration history, previous task references for the SAME agent);
  contextual/business/lessons scopes return an explicit `unavailable` result
  labelled "P-09 not built" — no cross-agent data, ever.
- `schemas.py` — internal pydantic payloads (creation requirement, assignment
  request internals) where a typed model is needed.
- `service.py` — `AgentFactoryService`: registry operations, §7 creation pipeline
  (evaluate → decide → materialize / hold for approval), §9 assignment +
  delegation + output-contract validation, §12 health/metrics, §13 config
  versioning + rollback, §11.1 maintenance (idle suspension, expired-permission
  sweep, failed-agent recovery, health checks), §16.5 emergency stop + resume,
  factory settings (owner/governance only), status/resources aggregation,
  seeding. Every mutating operation writes `audit_events` and emits a bus event.

`backend/app/database/models/agents.py` — the 9 new tables; `agents` extension
columns added to `Agent` in `models/core.py` (additive only).
`backend/app/database/repositories/agents.py` — repositories for the new tables +
agent query helpers (by role/status/business, counts).
`backend/app/api/schemas/agent_factory.py` — request/response models.
`backend/app/api/routes/agents.py` — EXTENDED with §19 agent endpoints.
`backend/app/api/routes/agent_factory.py` — templates, factory, capabilities, admin.

## 2. Database changes

One Alembic migration, `down_revision = a8ddb3e7260d`:
- `batch_alter_table('agents')`: add 10 nullable columns + FK `template_id →
  agent_templates.id` (created first), index on `template_id`.
- Create 9 tables (see audit §6) with FKs, unique constraints
  (template name; template (id, version); capability name; assignment
  idempotency key), indexes (agent_id, status, recorded_at), JSON columns for
  configuration/snapshots/factors.
- Downgrade drops the 9 tables and the added `agents` columns (batch mode).
- Verified: upgrade → downgrade → re-upgrade on a scratch SQLite DB; row
  preservation for pre-existing `agents` rows checked in the migration test.

Rollback strategy: the migration is purely additive; downgrade returns the
schema to the exact P-03 head (`a8ddb3e7260d`) with all pre-P-04 data intact.
Factory data created under P-04 is discarded by downgrade by definition —
documented, and acceptable because P-04 tables have no writers outside P-04.

## 3. API changes (all under `/api/v1`, existing envelope/auth)

Agents (extend existing router): `POST /agents` (direct registration via the
creation pipeline in template mode), `PATCH /agents/{id}` (controlled config
update), `POST /agents/{id}/suspend|resume|retire`, `GET /agents/{id}/permissions`,
`POST /agents/{id}/permissions/request|revoke|approve`, `POST /agents/{id}/assign`,
`GET /agents/{id}/assignments|health|metrics|events`,
`POST /agents/{id}/config/rollback`. Existing `GET /agents`, `GET /agents/{id}`
unchanged in shape (additive fields only).
Templates: `GET/POST /agent-templates`, `GET/PATCH /agent-templates/{id}`,
`POST /agent-templates/{id}/clone|validate|publish|restore`,
`GET /agent-templates/{id}/versions`, `GET /agent-templates/{id}/compare`.
Factory: `POST /agent-factory/evaluate|create`,
`GET /agent-factory/requests`, `GET /agent-factory/requests/{id}`,
`POST /agent-factory/requests/{id}/approve|reject`,
`GET /agent-factory/status|resources|settings`, `PATCH /agent-factory/settings`,
`POST /agent-factory/emergency-stop|resume-operations|maintenance`,
`GET /agent-capabilities`.
Authorization: reads — any authenticated principal; mutations — `manage_agents`
permission (owner/system role defaults; agents do NOT have it); settings,
creation/grant approval decisions, emergency stop — **owner principal only**,
checked in the service layer as well as the route.

## 4. Integration points

- **P-01 tasks**: assignment → `TaskManager.submit(principal, assigned_agent_id=…)`;
  completion verdicts are read back from the task + its executions; cancellation
  via `TaskManager.cancel` with the system principal (emergency stop).
- **P-01 permissions**: capability checks at assignment time and grant time via
  `PermissionEngine.check(agent_principal, capability_name)` (mirror rules);
  route gating via `require_permission("manage_agents")` + service-layer checks.
- **P-01 approvals**: `ApprovalService.create/decide/verify_binding`; parameters
  are the exact creation/grant payload — any drift fails `verify_binding`.
- **P-01 audit/events**: `AuditRepository` writes; new `EventType` members;
  critical ones added to `CRITICAL_EVENT_TYPES` for persistence.
- **P-01 monitoring**: `SystemMonitor.resources()/threshold_violations()` feed
  the resource manager and `/agent-factory/resources`.
- **P-02**: `application.intelligence.router.select(task_class)` is THE shared
  inference path (Scenario J); factory never constructs providers. P-02
  `model_profiles` are referenced by name from templates and validated to exist.
- **P-03**: an assignment may carry `business_ref = <opportunity id>`; the
  `web_research` capability's execution path is the existing
  `opportunity.research` handler. Integration test exercises brief → opportunity
  → research-agent assignment referencing it.
- **Modes**: `Settings.mode == emergency` (or factory safe mode) blocks creation
  and assignment; `simulation` forbids grants of Level-2 capabilities from
  taking effect outside recorded approvals (approvals still recorded; no
  external capability is supported in P-04 anyway).

## 5. Permission model

- Capability ≠ role: templates *request* capabilities; grants are separate
  ledger rows decided by policy/owner.
- Approval levels (§8.3): L0 auto-grantable at creation when all other checks
  pass; L1 grantable when policy conditions hold (capability enabled, within
  ceilings, previously approved class) else escalated to owner approval;
  L2 always owner approval (hash-bound); L3 **prohibited** — refused at
  catalogue level, not requestable, not owner-approvable through the agent path.
- No self-grant (an agent principal can *request*, never decide), no inheritance
  (child agents start with zero grants; parent grants are never copied), no
  authority transfer (grants name exactly one agent id), no escalation via
  content (all decisions are deterministic code paths over stored records).
- Factory limits/settings: writable only by owner/governance principals;
  service-layer enforcement mirrors the P-02 profile / P-03 scoring pattern.

## 6. Resource management strategy

- Agents are rows + JSON configuration; **zero** per-agent processes/models.
- Per-agent budgets come from the pinned template version, overridable per
  agent within factory ceilings: max concurrent tasks, max task seconds,
  max retries, max inference requests/task, max child agents, max queue
  occupancy (assignments in non-terminal state).
- Backpressure (§10.4), evaluated deterministically from `SystemMonitor`
  violations + queue stats: pressure level 0 (none) → 1 (stop nonessential
  creation; queue low-priority assignments) → 2 (reduce effective concurrency
  to 1; suspend eligible idle agents via maintenance) → owner-visible warning
  in `/agent-factory/status` at every level ≥ 1. Critical/essential work is
  never blocked by the ladder.
- Metrics honesty: durations and task counts are **measured** (from
  `task_executions`); inference requests are **estimated** (counted at the
  factory gate, labelled estimated/shared); token usage and per-agent RAM are
  **unavailable** (no provider reports them in this build) — never fabricated.

## 7. Testing strategy

New files `tests/test_p04_unit.py`, `test_p04_integration.py`,
`test_p04_security.py`, `test_p04_resources.py`:
- Unit: lifecycle graph (valid + invalid), template validation matrix, version
  pinning/compare/restore, creation-decision matrix (§7.3 outcomes), capability
  level rules, output-contract validator, delegation depth/cycle checks,
  scaling decisions, config rollback, backpressure ladder.
- Integration: migration chain on a fresh DB (head, tables, downgrade/re-upgrade,
  legacy agent row preserved); full creation pipeline via API; assignment →
  real P-01 task completion; P-02 shared-router use; P-03 opportunity-linked
  assignment; audit rows generated; emergency stop end-to-end.
- Security: the 10 §22.3 tests, each named for its scenario.
- Resources: max agent count, per-agent concurrency cap, inference gate,
  resource-pressure behaviour (monitor stubbed to forced violations), duplicate
  model-instance prevention (single router), idle suspension, failed-init
  recovery cap.
- Acceptance scenarios A–J each map to a named test or smoke step; the mapping
  table goes in `docs/testing/P04_TEST_REPORT.md`.
- Regression: the whole suite must pass in ONE run; the only existing-test
  edits permitted are the two R1 migration-head assertions (strictness
  preserved, disclosed).

## 8. Migration & rollback strategy

As §2 above. Additionally: models and migration are written from the same
definitions and cross-checked by the fresh-DB integration test, which builds
the schema via Alembic (not `create_all`) and asserts all 9 tables + the new
`agents` columns exist.
