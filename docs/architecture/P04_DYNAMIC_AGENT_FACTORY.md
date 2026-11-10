# P-04 — Dynamic Agent Factory: Architecture

Status: built in staging (2026-11-09), awaiting owner gate. Package:
`backend/app/agents/`. Built strictly on top of P-01 (Core OS), P-02
(Master Intelligence) and P-03 (Opportunity Discovery) — no parallel
systems were created where an existing one carries the concept.

## 1. What the factory is

The factory turns a *requirement* ("we need research capacity for this
business") into a governed decision and, when justified, a registered
logical agent. Agents are **logical configurations** — a row in the
P-01 `agents` registry plus a pinned template version, a capability
grant ledger and a resource budget. They are never separate processes
and never own a model instance; all inference flows through the single
shared P-02 `ModelRouter` (§10 of the P-04 prompt).

## 2. Module map (`backend/app/agents/`)

| Module | Responsibility |
|---|---|
| `constants.py` | Role taxonomy (28 roles / 6 categories), capability catalogue with §8.3 approval levels, factory-setting defaults, 10 seed templates |
| `errors.py` | §21 structured error categories as typed exceptions |
| `lifecycle.py` | §11 state machine graph + validation (incl. the documented P-01 legacy bridge) |
| `validation.py` | Template-configuration validator; §9.4 output-contract validator |
| `templates.py` | Template service: versioned CRUD, clone, publish, deprecate, restore, compare |
| `capabilities.py` | Capability ledger + P-01 permission-engine mirror; hash-bound grant approvals; expiry sweep |
| `resources.py` | Per-agent budgets, host/queue pressure (§10.4 ladder), shared-inference gate |
| `scaling.py` | Deterministic §14 scaling policy |
| `memory_interface.py` | §15 scoped memory interface for P-09 (interface only) |
| `service.py` | `AgentFactoryService`: creation pipeline, lifecycle ops, assignment, metrics, health, emergency stop, maintenance |

Persistence: `backend/app/database/models/agents.py` (9 new tables) +
additive columns on the P-01 `Agent` model; repositories in
`backend/app/database/repositories/agents.py`. HTTP surface:
`backend/app/api/routes/agent_factory.py` (26 routes) and the extended
`backend/app/api/routes/agents.py` (18 new routes; the 2 pre-existing
P-01 GETs are byte-compatible).

## 3. Reuse decisions (Stage-1 audit, evidence-based)

| P-04 §17 concept | Decision |
|---|---|
| `agent_registry` | **Reused** — P-01 `agents` table extended additively (10 columns). It is already FK-referenced by `tasks.assigned_agent_id`. |
| `agent_events` | **Reused** — served from append-only `audit_events` (actor/target filters) + `system_events`; no new table. |
| `agent_factory_settings` | **Reused** — P-01 `system_config` via `ConfigRepository` (the P-03 scoring-config precedent), key `agent_factory.settings`, owner/governance-only writes. |
| Permission enforcement | **Reused** — P-01 `PermissionEngine`; factory grants are mirrored as DB allow rules (`principal_type='agent'`, permission = capability name); revocation writes an explicit deny (deny always wins). The factory's own ledger (`agent_permissions`) exists because the P-01 table has no approval-reference / expiry / revocation columns. |
| Approvals | **Reused** — P-01 `ApprovalService`, actions `agent_factory.create_agent` and `agent_factory.grant_capability`, parameters hash-bound (SHA-256) exactly like P-02 plan approvals. |
| Task execution | **Reused** — P-01 `TaskManager`; assignments submit real tasks. P-04 registers **no** new task handlers. |
| Inference | **Reused** — P-02 `ModelRouter` bound by reference into the resource manager; a test asserts object identity and exactly one binding. |
| Resources | **Reused** — P-01 `SystemMonitor`; pressure blocking honours the same `block_nonessential_on_threshold` switch as P-01 task admission. |
| `web_research` capability | Backed by the real P-03 `opportunity.research` handler (SSRF-guarded pipeline), reachable through assignment. |

New tables (each justified in `docs/audits/P04_PRE_IMPLEMENTATION_AUDIT.md`):
`agent_templates`, `agent_template_versions`, `agent_capabilities`,
`agent_permissions`, `agent_creation_requests`, `agent_assignments`,
`agent_health`, `agent_metrics`, `agent_configuration_history`.
Migration `a694abea811f` (revises `a8ddb3e7260d`); 35 tables at head.

## 4. Creation pipeline (§7)

`AgentFactoryService._decide` applies gates in a fixed order and every
outcome is a persisted, deterministic decision record:

0. Factory/mode stop (safe mode, creation disabled, emergency mode) → `QUEUE_FOR_LATER`
1. Unknown / prohibited (Level-3) / unsupported capability → `REJECT_CREATION`
2. Parent child-count or delegation-depth breach → `REJECT_CREATION`
3. Failed-initialization cap for the role (default 3) → `REJECT_CREATION`
4. **Reuse first** — a suitable existing agent yields `REUSE_EXISTING_AGENT`, or `ASSIGN_TO_EXISTING_AGENT` when the requirement carries a task (successes, not failures)
5. Template resolution — explicit template (must be published + valid), role→published template, or taxonomy role without a template → `REQUEST_OWNER_APPROVAL` (Mode C proposal); deprecated/unpublished/invalid → `REJECT_CREATION`
6. Approval determination — any Level-2 capability, resource-intensive budget, or a non-owner (agent/service) requester → `REQUEST_OWNER_APPROVAL` with a hash-bound P-01 approval
7. Fleet limits (total / active / per-business / creation rate) → `QUEUE_FOR_LATER`
8. Resource pressure (§10.4 ladder; essential work exempt; blocking follows the P-01 admission switch) → `QUEUE_FOR_LATER`

Otherwise `CREATE_AGENT`: the agent is materialized pinned to the
template's published version, initialization checks run (handlers
registered, model profile exists if named, merged configuration
re-validates), template/Level-0/approved capabilities are granted, a
configuration-history snapshot and a health row are written. A failed
initialization leaves the agent `FAILED` with the reason recorded —
never an endless replacement loop (Scenario F).

Creation is idempotent: a repeated `idempotency_key` returns the
original decision record.

Approval is drift-proof: `approve_creation` rebuilds the decision from
*current* facts and requires an exact hash match with the stored
approval parameters; if the template was re-published or the capability
set changed, the stale approval fails with `ApprovalError` and must be
re-requested.

## 5. Assignment (§9)

Assignments reuse the P-01 task engine. All nine §9.2 rules are
validated before a task is submitted (existence, assignable state,
governance/mode, permissions, resource budget incl. per-agent
concurrency and the §10.4 ladder, template responsibility, dependency
state, delegation depth/children/circularity, timeout vs budget).
Rejections are **persisted** as `status=rejected` assignment rows with
the failed rules, and audited. Results are checked against the §9.4
output contract on refresh: a task that completes without the required
output fields becomes `output_invalid`, never a success.

## 6. Events

New `EventType`s: `AgentCreated`, `AgentStateChanged`,
`AgentCreationDecided`, `AgentPermissionChanged`, `AgentAssigned`,
`AgentHealthChanged`, `AgentEmergencyStop`. State changes, permission
changes, creation decisions and emergency stops are in the persisted
critical set.

## 7. Modes

`simulation` / `supervised` / `controlled` behave identically for the
factory except that creation/assignment remain governed in all of them;
`emergency` mode (and the factory safe mode set by emergency stop)
blocks creation (queued) and assignment (rejected) deterministically.
No LLM participates in any of these decisions.
