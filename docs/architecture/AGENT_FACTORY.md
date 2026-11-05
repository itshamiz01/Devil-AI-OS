# The Agent Creation Engine (P-04)

**Phase:** P-04 Stage 4 · **Status:** Implemented and tested · **Companion:** [ADR-0024](../decisions/ADR-0024-EXTEND-AGENTS-NOT-A-SECOND-REGISTRY.md) · **Depends on:** [AGENT_TEMPLATES.md](AGENT_TEMPLATES.md)

Stage 4 turns a requirement into one of six decisions and, for the decisions that have an execution path in this stage, carries it out. It is the first part of P-04 that writes to the `agents` table: before this stage the registry could be read but nothing could populate it.

The design principle is the same one Stage 3 applied to validation — **the decision is code, not a prompt**. Nothing in `app/agents/factory.py` or `app/agents/creation.py` calls a model. A recommendation from a model would be an opinion; a decision that mints an identity has to be reproducible, and the only way to make it reproducible is not to ask anything that can answer differently twice.

The code is split in two, and the split is not cosmetic:

| Module | Lines | Responsibility |
|---|---:|---|
| `app/agents/factory.py` | 470 | Decides. Pure with respect to writes: `evaluate()` reads the database and configuration and returns checks plus a decision |
| `app/agents/creation.py` | 519 | Acts. Records the decision, mints identities, opens approval gates, drains the queue, emits events |

A decision is testable without a single write, while execution needs its own transaction, audit record and event for everything it touches. Keeping them in one class would have made the safe half as hard to test as the dangerous half.

## 1. The check order

`evaluate()` runs eight checks in a fixed order and **stops at the first one that forces a decision**. Order is policy, not decoration:

| # | Check | Refuses with | Why it sits here |
|---:|---|---|---|
| 1 | `emergency_stop_clear` | `REJECT` | Nothing about capacity or templates matters while the owner has halted the system |
| 2 | `template_resolved` | `REJECT` | Every later check reads the template's configuration, so there is nothing to check without one |
| 3 | `capabilities_within_template` | `REJECT` | A capability cannot be granted by asking for it |
| 4 | `delegation_within_limit` | `REJECT` | Depth is a property of the request, not of the registry's current fill |
| 5 | `no_reusable_agent_exists` | `REUSE_EXISTING` | **Before** the limits, so a full registry still answers "use the agent you already have" instead of queueing work that need not exist |
| 6 | `registry_within_limits` | `QUEUE`, or `REJECT` when the queue is full | |
| 7 | `resources_available` | `QUEUE`, or `REJECT` when the queue is full | Waits for the template checks so a request that would be refused anyway is not queued |
| 8 | `approval_not_required` | `REQUEST_OWNER_APPROVAL` | **Last**, so an owner is never asked to approve a creation that would be refused regardless |

Two more checks can be appended during execution rather than evaluation: `requester_holds_deciding_authority` (§4) and `approval_gate_satisfied` (§4).

`passed` means the same thing on every check: **false means this check forced the decision**. That is why the reuse check is named for the condition that lets creation proceed rather than for the outcome it produces — a reader scanning for `false` should find exactly one, and it should explain the answer.

## 2. Template resolution

An explicit `template_id` must exist, be `published`, and point at a current version whose stored verdict is `valid`. Any of those failing is a `REJECT` naming which.

Without an explicit id the engine matches the requested role **case-insensitively and exactly** against a published template's `name` or `category`:

* exactly one match → that template;
* no match → `REJECT`, "pass `template_id` explicitly";
* more than one → `REJECT`, naming every candidate.

Ambiguity is refused rather than resolved. Fuzzy-matching a free-text role against a free-text `role_definition` would make the decision depend on string similarity, and picking the first of two matches would make it depend on ordering — neither is a reason anyone can audit afterwards.

## 3. The six decisions

`CreationDecision` is a closed set of six, and the database CHECK agrees with it because both are derived from the same enum rather than retyped.

| Decision | Executed in Stage 4? | What happens |
|---|---|---|
| `CREATE_AGENT` | Yes | Principal, agent row and configuration snapshot in one transaction (§5) |
| `REUSE_EXISTING` | Yes | The existing agent's id is returned; nothing is written except the ledger row |
| `ASSIGN_EXISTING` | **No** | Declared in the vocabulary, never emitted: assignment validation is Stage 6 |
| `QUEUE` | Yes | The request stays open (`completed_at` NULL) until an owner drains it (§6) |
| `REQUEST_OWNER_APPROVAL` | Yes | An approval is opened at risk `high`; the agent is created only if it is granted (§4) |
| `REJECT` | Yes | Terminal, recorded with its reason |

`ASSIGN_EXISTING` is the honest gap. A caller can rely on the six-value vocabulary without the engine silently inventing an execution path for one of them, and `GET /agent-factory/status` reports `assignment_supported: false` with a note naming Stage 6.

## 4. The approval gate

A template requires owner approval to instantiate when either is true:

* its `approval_requirements` list contains `agent_creation`;
* its `security_classification` is `restricted`.

The approval is opened through the **central** approval service — action `agent.create`, resource = the creation request id, **risk `high`**. Risk is not decorative: `high` engages the existing self-approval block, so the principal that asked for an agent cannot be the principal that authorizes it. An agent approving its own creation is the specific failure the phase forbids, and `test_the_self_approval_block_bites_if_a_requester_later_gains_authority` proves the rule still bites when the requester is granted `approvals.decide` *after* asking.

When the owner grants it, the request is **re-evaluated** rather than executed on the strength of the earlier decision, because the registry may have filled while the approval was pending. Approval is authority to create, not a guarantee that creation is still possible. A re-evaluation that returns `QUEUE` leaves the request queued with `approval_status: granted`; one that returns `REJECT` closes it. A re-evaluation that asks for owner approval *again* is asking for the approval that was just granted, so the gate counts as satisfied — treating that as "still gated" would leave the request open forever with a granted approval attached to it.

**One case does not open an approval at all.** An approval records its requester, and risk `high` forbids that requester from deciding it. When the requester is the owner — the only principal that holds `approvals.decide` — the approval would be unanswerable by anyone, which is a deadlock rather than a control. The owner asking for an agent *is* the owner deciding about it, so `_resolve_gate` asks the permission engine, read-only, whether the requester holds `approvals.decide`, and if so creates the agent directly. The response still reports `approval_required: true`, because that is a property of the template and it did not change; the appended check and the reason text say how the gate was resolved. Without the permission engine assembled, every gated creation stays gated — the check that could shorten a gate is the thing that is missing.

## 5. Minting an identity

`agents.principal_id` is **unique**, so an agent *is* a principal, and creating one writes both rows in a single transaction:

1. `principals` row, `kind = "agent"`;
2. `agents` row at `PROPOSED`, carrying `template_id`, `template_version`, `configuration_version = 1`, optional `parent_agent_id` and `business_id`;
3. the lifecycle **walked** — `PROPOSED → INITIALIZING → ACTIVE` — through the same `transition()` the rest of the system uses, so an agent cannot appear in a state the graph does not permit;
4. one `agent_configuration_history` row at version 1 holding the template configuration it was built from, with the creating principal and any approval id;
5. the ledger row closed and an `agent.created` audit record written.

`metadata_json` records provenance — template id, version and name, the request that produced it, the stored `configuration_fingerprint`, and the `essential` claim — rather than a copy of the configuration, which already lives immutably in `agent_template_versions`.

Names are unique in both `agents` and `principals`. A requested name that collides is retried up to three times with a random suffix rather than failing the request; a generated name is `agent-<role-slug>-<8 hex>`. The *decision* is deterministic; the *identifier* need not be, and deriving it from a counter would let two concurrent requests read the same value.

**No health check is claimed.** Bringing the agent to `ACTIVE` means its principal, registry row and configuration snapshot exist. Nothing has observed it doing work, which is what Stage 8's health states are for, and `agent_health` stays empty until then.

## 6. The queue

A creation that hits a ceiling or resource pressure is queued rather than refused, and queuing is bounded: with `AUTONOMUS_AGENT_MAX_CREATION_QUEUE` already reached, the answer is `REJECT` with the queue depth in the reason. Queuing without a bound is refusing slowly and without telling anyone.

The queue is drained **only** by `POST /agent-factory/queue/drain`. Nothing here runs on a timer, because autonomous scheduling is P-12. A drain re-evaluates each request from scratch, oldest first, and restores `essential` and `allow_reuse` from the stored row: re-evaluating a *different* request — one that silently became reusable, or lost an essentiality claim — is not re-evaluating the request. Every outcome is returned, so a drain that created nothing is visibly a drain that created nothing.

## 7. Idempotency

`idempotency_key` is unique and nullable. A repeated key returns the **recorded outcome** with `replayed: true` and writes nothing; two requests that claimed no key never collide, because the constraint allows any number of NULLs. A replayed rejection is still a rejection — the ledger answers, the engine does not decide twice.

The request row is written **before** execution, so a decision that fails halfway is still on the record. The one crash window this leaves is a request recorded as awaiting approval with no approval id, meaning the approval was never created. `sweep_expired()` closes such a request; it never creates the agent, because an ungated creation is exactly what the gate exists to prevent. The same sweep closes requests whose approval expired or was rejected while they waited.

## 8. Authorization

Two new permission codes, both enforced by a route in this stage:

| Code | Grants |
|---|---|
| `agents.factory.read` | Evaluate, read the ledger, read status |
| `agents.factory.admin` | Create an agent, drain the queue |

`PERMISSIONS` is now **32** codes. Both derive into `OWNER_PERMISSIONS` and neither is in `SYSTEM_PERMISSIONS`, so the application can evaluate a creation but cannot authorize one for itself. Splitting read from admin means a principal can be given the ability to *ask* what a creation would decide without the ability to make one happen.

No `agents.factory.approve` was added. A gated creation is decided through `POST /approvals/{id}/decision` under the pre-existing `approvals.decide`, so the owner has one approval surface for every gated action in the system instead of a second one only agents know about.

## 9. Events

Five new types, source `agent_factory`, bringing `EVENT_TYPES` to **52**:

`AgentCreationRequested` · `AgentCreated` · `AgentCreationQueued` · `AgentCreationApprovalRequested` · `AgentCreationRejected`

Every creation request publishes `AgentCreationRequested` carrying the decision, and a rejection or a queued request publishes its own type as well, because what the system decided **not** to do is what an owner audits afterwards. `REUSE_EXISTING` publishes only `AgentCreationRequested`: reusing an agent creates nothing, and a creation event for it would inflate every downstream count of agents that were made.

## 10. Configuration

Five new `Settings` fields, bringing the total to **62**. All are documented in [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md) and present in `.env.example`, which `scripts/audit_config_docs.py` enforces.

| Setting | Default | Bounds |
|---|---:|---|
| `AUTONOMUS_AGENTS_ENABLED` | `true` | — |
| `AUTONOMUS_AGENT_MAX_TOTAL` | `12` | 1–64 |
| `AUTONOMUS_AGENT_MAX_PER_TEMPLATE` | `4` | 1–32 |
| `AUTONOMUS_AGENT_MAX_CREATION_QUEUE` | `20` | 1–200 |
| `AUTONOMUS_AGENT_MAX_DELEGATION_DEPTH` | `2` | 0–4 |

`AUTONOMUS_AGENTS_ENABLED` closes **L-62**: `Services.agents` is now assembled only when it is true, and all three route groups answer `409` naming the setting rather than `500` from a half-built engine. `GET /agents/status` is exempt, because it is the endpoint that reports the phase is disabled.

Every ceiling except `RETIRED` counts against `agent_max_total` — a suspended or failed agent still exists and still holds its identity and permissions.

## 11. Migration and verification

Revision **`d0db25c9da23`** (down_revision `e4817dfb6c0c`) is the seventh in the chain. It adds `idempotency_key` with a **named** unique constraint, both decision-vocabulary CHECKs, and the `not_required` server default Stage 2's revision did not emit.

Autogenerate detected only the column and the unique constraint — it renders neither a CHECK addition nor a `server_default` change on an existing column (L-56) — so those three operations were written by hand. The first generated revision was **deleted rather than patched** because it emitted an unnamed unique constraint, which autogenerates into `drop_constraint(None, ...)` and cannot run (ADR-0024).

**Legacy values are normalized before the CHECKs are added.** Stage 2 created both columns without a vocabulary, so a database that ran Stages 2–3 may hold a value the new CHECKs would reject. Adding such a constraint does not merely fail: on SQLite it fails *during* the batch rebuild, partway through a non-transactional DDL sequence, which is how a database ends up half-migrated. The upgrade therefore maps every unrecognized `approval_status` to `not_required` and clears every unrecognized `decision` to NULL — the honest value for a decision this system cannot produce. This is one-way, and the downgrade does not attempt to undo it. `test_a_legacy_value_outside_the_vocabulary_does_not_block_the_upgrade` proves the row survives rather than being dropped to satisfy the constraint.

Verification performed for this stage:

* a **populated** SQLite database upgraded across the revision — rows preserved, `PRAGMA foreign_key_check` empty, both CHECKs and the unique constraint refusing bad values by insertion, NULL keys coexisting, the server default applying to a row that omits the column;
* **downgrade then re-upgrade** over the same rows;
* an **offline Postgres render** of all seven revisions — 44 `CREATE TABLE`, 8 `ADD CONSTRAINT`, 9 `CHECK` clauses, both normalization statements, zero SQLite-isms;
* `tests/test_migration_portability.py`, whose shim-coverage guard scans every revision for `batch_op.<method>(` and asserts the portable shim implements it. That guard was added because `create_unique_constraint` was missing and the failure surfaced **partway through** a revision.

## 12. What is deliberately not here

| Absent | Owner |
|---|---|
| `ASSIGN_EXISTING` execution, assignment rules, output contracts | Stage 6 |
| Budgets, the shared inference semaphore, backpressure | Stage 7 |
| Health states, idle detection, metrics, suspension and retirement endpoints, configuration rollback | Stage 8 |

Two rows that used to be in this table are not, because Stage 5 delivered them: the capability catalog cross-check on requested capabilities, and approval levels 0–3 with prohibited actions and self-grant prevention. A creation decision now runs a `capabilities_governed` check after the template subset check, refusing a prohibited, unknown or disabled key outright and sending a level-2 key to `REQUEST_OWNER_APPROVAL`. See [AGENT_CAPABILITIES.md](AGENT_CAPABILITIES.md). What Stage 5 did **not** deliver is enforcement at a tool boundary: nothing calls `CapabilityService.check()` yet, because adapters are P-05 and assignment output contracts are Stage 6.

Two consequences are worth stating plainly. **`REUSE_EXISTING` can only trigger on an agent that is already `ACTIVE` or `IDLE`**, and nothing sets `IDLE` until Stage 8 — so until then reuse matches agents that were created and left active. And **a creation decision cannot see a capability's approval level**, because no capability has one yet: the catalog is empty. `GET /agent-factory/status` reports `capability_catalog_checked: false` with a note naming Stage 5, so no decision can be read as a broader clearance than it is.
