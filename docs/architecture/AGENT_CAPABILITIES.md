# Agent Capabilities and Permission Governance

**Phase:** P-04 Dynamic Agent Factory, Stage 5
**Status:** Implemented, with one boundary deliberately not yet wired — see
[What is not true yet](#what-is-not-true-yet).
**Modules:** `backend/app/agents/catalog.py`, `backend/app/agents/capabilities.py`,
`backend/app/agents/governance.py`
**Tables:** `agent_capabilities`, `agent_permissions`
**Migration:** `e8b2ced758fc`

An agent in this system holds no authority by default. Nothing is implicit: not
its template's `allowed_capabilities`, not the role it was created for, not what
a previous version of it was allowed to do. Authority exists only as a row in
`agent_permissions`, and every row was written by one code path.

This document describes that code path. `capabilities.py` is the only place a
capability is granted, denied or checked, and a level-3 denial in it is
unconditional.

---

## The four approval levels

Every capability in the catalog carries an `approval_level`. The levels are the
contract; everything else in this document is how they are enforced.

| Level | Name | What it takes to hold one | Risk |
|---|---|---|---|
| 0 | `AUTONOMOUS` | Policy allows it. The grant is recorded and audited. | `low` |
| 1 | `CONDITIONAL` | Conditions are checked in code — a scope, and the ceilings in `Settings`. No human decides. | `medium` |
| 2 | `OWNER_APPROVAL` | An `approvals` row must reach `granted` first. The grant is `pending` until it does. | `high` |
| 3 | `PROHIBITED` | Nothing. No approval code path can reach it. | `critical` |

Risk is **derived from the level** in `catalog.py::_cap()` unless an entry
explicitly overrides it, so an entry cannot claim to be low-risk while needing an
owner's signature. Risk and level stay separate columns because they answer
different questions — risk describes harm, level describes the authority needed —
but in this catalog they move together.

Level 3 is not "level 2 with the volume turned up". It is a different kind of
statement: there is no owner, no approval, no configuration key and no code path
that makes `spending.authorize` grantable. The distinction matters because a
system that can be talked into anything by the right approver has no prohibitions,
only expensive permissions.

---

## The catalog is code

`BUILTIN_CATALOG` holds 29 entries: 7 at level 0, 4 at level 1, 10 at level 2 and
8 at level 3. Thirteen are enabled; sixteen are not — the eight prohibited ones,
plus eight that exist so the vocabulary is complete but cannot be granted until
the subsystem that would use them is built (`memory.write` is P-09;
`execution.tool`, `code.execute`, `browser.control`, `external.network`,
`filesystem.read`, `filesystem.write` and `distribution.publish` are P-05 and
P-06).

A prohibited entry is never enabled, and that is derived in `_cap()` rather than
typed per entry, for the same reason risk is derived: leaving it to each entry
would allow one to claim to be both prohibited and available, and would inflate
the `enabled` count a status endpoint reports as though it were authority the
system can hand out.

The catalog is reconciled into `agent_capabilities` at startup by
`CapabilityService.reconcile_catalog()`. Reconciliation is **additive and
corrective, never destructive**:

* a key that is missing is created;
* a key whose stored definition has drifted from the code is corrected, and the
  response names which fields changed;
* a key that exists in the table but not in the catalog is left alone.

It never deletes, because deleting a capability out from under an existing grant
would make that grant unreadable — a row pointing at nothing, which reads as a
bug rather than as a withdrawal of authority.

**There is no endpoint that creates or edits a catalog entry.** This is asserted
by a test that walks the OpenAPI document and requires every
`/agent-capabilities` path to expose `GET` only. The reason is that a capability
which could be added over HTTP could be added at level 0 by whoever holds
`agents.permissions.grant`, and then the level a capability carries would depend
on who asked. Editing the catalog is a code change, which means it is reviewed,
versioned and attributable.

---

## Level 3 cannot be lifted from the database

`PROHIBITED_CAPABILITIES` is a literal set of eight keys in `catalog.py`:

`secrets.store_raw`, `spending.authorize`, `financial.execute`,
`approval.self_grant`, `governance.bypass`, `identity.impersonate_owner`,
`distribution.publish_unauthorized`, `evidence.fabricate`.

`grant()` consults that set **before it looks the row up**. So:

* editing a row to say `approval_level = 0` and `enabled = true` still refuses
  with `403 capability_prohibited`;
* deleting the row still refuses with `403 capability_prohibited`, and does not
  degrade into `404 capability_not_found`.

Both are tested. The rows exist so an owner can *read* a prohibition and its
`prohibited_reason`; enforcement does not depend on them. `check()` refuses
prohibited keys the same way, so a boundary that is handed a key nobody can hold
answers "no" rather than "unknown".

Two of the eight duplicate guarantees that already exist elsewhere, and that is
deliberate. `approval.self_grant` restates the approval service's rule that a
requester cannot decide their own high or critical risk approval;
`spending.authorize` restates §26 of the phase brief. Putting them in the
capability vocabulary means an agent cannot be granted a capability whose name
implies the system has an ability it does not have.

---

## Granting

`POST /api/v1/agents/{agent_id}/permissions` with `agents.permissions.grant`.

A grant either succeeds or raises a typed error. There is no
`{"status": "refused"}` shape, because a caller must not be able to ignore a
prohibition by not reading a field.

| Situation | Response |
|---|---|
| Key not in the catalog | `404 capability_not_found` |
| Key is prohibited (level 3) | `403 capability_prohibited`, with the reason |
| Key exists but is disabled | `409 capability_disabled`, naming what has to exist first |
| Agent is `SUSPENDED`, `FAILED`, `RETIRING` or `RETIRED` | `409 agent_not_grantable` |
| Actor is the agent's own principal | `403 capability_denied` |
| A scope-requiring capability with no scope, or the ceiling is reached | `409 capability_conditions_unmet` |
| Level 2 with no approval service available | `403 capability_denied` — refused rather than granted ungated |
| Emergency stop active | `503 emergency_stop_active` |

Conditions are applied at **every** level, not only at level 1. A level-0
capability still cannot be granted to a suspended agent, still counts against the
per-agent ceiling, and still cannot be self-granted. If the conditions only bound
level 1, a lower level would be a way around them.

Three further properties:

* **Idempotent.** Granting the same agent, capability and scope twice returns the
  existing grant with `replayed: true`. Two rows for one authority is two
  authorities, and a retried request must not create one.
* **Scope is part of the identity.** The same capability at two scopes is two
  grants, because they are two different answers to two different requests.
* **The ceiling counts pending grants.** `AUTONOMUS_AGENT_MAX_ACTIVE_CAPABILITIES`
  (default 16) counts what is held *and* what is awaiting an owner's decision,
  because authority that is pending is authority somebody intends to give.

A refusal writes an audit row (`capability.denied`) and publishes
`AgentCapabilityDenied`. A denial is deliberately **not** a grant status: no row
is written, so the table cannot be read as a list that includes things that were
refused.

---

## Level 2, and who is recorded as the requester

A level-2 grant opens an approval through `governance.open_capability_approval()`
at risk `high`, action `agent.capability.grant`, with the capability, agent,
scope and level as parameters. The approval is opened **before** the grant row is
written, so a crash between the two leaves an approval with no grant rather than
a grant with no approval. Failing toward not-granting is the only safe direction.

The grant row is written `pending`, and `AgentCapabilityApprovalRequested` is
published. When the owner decides:

* `approved` → the row becomes `active` and `AgentCapabilityGranted` is published;
* `rejected` → the row becomes `revoked` and is **kept**. A request for authority
  that was refused is exactly what an owner wants to be able to see afterwards,
  and deleting it would make the audit trail describe only the decisions that
  went the requester's way.

**The requester recorded on the approval is the agent that would hold the
authority, not the actor who asked for it.** This is load-bearing rather than
cosmetic. The approval service forbids a requester deciding their own high or
critical risk approval, and only the owner holds `approvals.decide` — it is not a
system permission. So if the actor were recorded as the requester, an
owner-requested level-2 grant would be undecidable by anybody: pending forever,
with no way to reach it. The same deadlock was found and fixed in the Stage-4
creation gate.

The actor is not lost. It travels in the approval's parameters and so is bound
into its `payload_hash`; it is recorded on the grant's audit row; and it is
carried on the `AgentCapabilityApprovalRequested` event as `requested_by`,
because the `approvals` table stores no parameters column and the event is
otherwise the only place the request has an author. What an owner reads on the
approval itself is the `resource`, which encodes the agent, the capability and
the scope.

Deciding a capability approval is **not** exposed under `/agent-capabilities`. It
goes through `POST /api/v1/approvals/{id}/decision` under the pre-existing
`approvals.decide`, so the owner has one approval queue for every gated action in
the system rather than one per subsystem.

---

## Revocation, and the emergency stop

`POST /api/v1/agents/{agent_id}/permissions/{permission_id}/revoke` requires a
non-empty `reason`: taking authority away is an audit event, and an unexplained
revocation cannot be reviewed later. The path names the agent, so revoking
another agent's grant is `404` rather than a silent success.

Revocation sets `revoked` and keeps the row. It also frees room under the
per-agent ceiling, because the ceiling counts what is held, not what was ever
granted.

The emergency stop is deliberately asymmetric:

* `grant()` **is** blocked while it is active (`503`);
* `revoke()` **is not**.

Removing authority is what an emergency calls for. A stop that prevented taking
authority away would make the system less safe while it was stopped.

---

## `check()`: the boundary question

`CapabilityService.check(agent_id, capability_key, *, scope="")` answers "may this
agent exercise this capability at this scope?". It is the single enforcement point
that P-05 adapters and Stage-6 assignment output contracts will call.

It **never raises**. A denial is an ordinary answer with a reason, because a
boundary that had to handle an exception would be a boundary that could be
tempted to let the call through when one arrived.

It denies when:

* the capability is prohibited, unknown or disabled;
* the agent does not exist;
* the agent is `SUSPENDED`, `FAILED`, `RETIRING` or `RETIRED` — **a suspended
  agent holds no authority**, whatever its grant rows say;
* no active grant covers the requested scope;
* a grant had lapsed. Lapse is discovered here rather than by a timer: nothing in
  P-04 runs on a schedule, since autonomous scheduling is P-12. A lapsed grant is
  marked `expired` as it is found, and the answer says it lapsed rather than
  reporting that no grant ever existed, because the two need different responses
  — one is a missing grant, the other is a renewal with a history to look at.

Scope matching uses `fnmatch.fnmatchcase`, the same semantics as the P-01
permission engine, so a grant of `*` covers any scope and a grant of
`opportunity:12` covers exactly that. The caller names the scope it wants; the
grant holds the pattern.

`check()` deliberately does **not** consult the emergency stop. Task admission
owns that. Two mechanisms answering one question is two authorities, and the
first disagreement between them is an incident nobody can diagnose.

`sweep_expired()` marks lapsed grants in bulk for anything reading the table
directly, and audits `capability.expired`. It publishes no event: a grant running
out is not something that happened, it is something that stopped being true.

---

## Endpoints

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /api/v1/agent-capabilities/status` | `agents.capabilities.read` | Catalog size, counts by level, the prohibition list, the ceiling, and what is not enforced yet |
| `GET /api/v1/agent-capabilities` | `agents.capabilities.read` | The catalog, filterable by category, risk, level and enabled |
| `GET /api/v1/agent-capabilities/{capability_key}` | `agents.capabilities.read` | One entry, including why a prohibited one is prohibited |
| `GET /api/v1/agents/{agent_id}/permissions` | `agents.capabilities.read` | What one agent holds |
| `POST /api/v1/agents/{agent_id}/permissions` | `agents.permissions.grant` | Grant one capability, or refuse and say why |
| `POST /api/v1/agents/{agent_id}/permissions/{permission_id}/revoke` | `agents.permissions.grant` | Revoke, with a reason |

`/agent-capabilities/status` is declared before `/{capability_key}` so the literal
path is never captured as a key.

Reading the catalog is separated from granting against it for the same reason as
the factory's read/admin split: an agent may need to know what a capability costs
without being able to hold one. Neither code is in `SYSTEM_PERMISSIONS`, so the
application cannot widen its own authority, and granting does not imply reading —
a principal with only `agents.permissions.grant` gets `403` from the catalog
endpoints.

With `AUTONOMOUS_AGENTS_ENABLED=false` all six answer `409` naming the setting, so
a disabled phase reports that it is disabled instead of failing with a `500`.

---

## Events

Five types, all with source `agent_capabilities`:

`AgentCapabilityGranted`, `AgentCapabilityRevoked`, `AgentCapabilityDenied`,
`AgentCapabilityApprovalRequested`, `CapabilityCatalogChanged`.

Authority changing hands is the most governance-relevant thing an agent system
does, so grants, revocations and refusals are all published. A *denied*
capability is published for the same reason a refused approval is: an attempt to
widen authority that did not succeed is exactly what an owner wants to see
afterwards.

`CapabilityCatalogChanged` is published only when a reconciliation actually
changed something, so a normal startup stays quiet. An event that fires on every
boot is an event nobody reads.

---

## Configuration

| Setting | Default | Effect |
|---|---|---|
| `AUTONOMUS_AGENT_MAX_ACTIVE_CAPABILITIES` | `16` | Capabilities one agent may hold at once (1-64), counting pending grants. Enforced at every level |
| `AUTONOMUS_AGENTS_ENABLED` | `true` | When false, all six endpoints answer `409` |

There is no setting that enables a prohibited capability, and no setting that
lowers an approval level. A setting that could do either would be a way to spend,
or a way to self-approve, one environment variable away.

---

## Relationship to the template and factory checks

A template's `allowed_capabilities` and a creation request's
`requested_capabilities` are both cross-checked against this catalog, and both
checks read the code-level catalog rather than the table, so neither depends on a
reconciliation having already run.

* **Template validation** (`templates.py::_catalog_check`) makes a prohibited or
  unknown key an *issue*, which blocks the `valid` verdict and therefore blocks
  publishing. A disabled key is a *warning*: a template may legitimately be
  written ahead of the subsystem that will use it. The same key under
  `restricted_capabilities` is fine when prohibited — forbidding a prohibited
  capability is redundant, not wrong — and an issue when unknown.
* **The creation decision** (`factory.py::_catalog_findings`) refuses a request
  naming a prohibited, unknown or disabled capability outright, and sends a
  request naming a level-2 capability to `REQUEST_OWNER_APPROVAL`.

The two are defence in depth rather than duplication. Because validation now
refuses to judge such a template valid, a published template cannot normally
allow a prohibited capability at all — so the factory's own guard is reachable
only through a verdict recorded before the catalog was cross-checked, or a
configuration edited underneath one. That is precisely the situation a second
check exists for.

P-02's `CapabilityRegistry` describes what adapters can do. It informs this
catalog but does not govern it: a registry entry is not a grant, and nothing in
P-02 can widen an agent's authority.

---

## Verification

Migration `e8b2ced758fc` is hand-written. Autogenerate detected only the two
added columns: it renders neither a CHECK addition nor a `server_default` change
on an existing column (L-56), so all seven of those operations were written by
hand and then proved by insertion rather than by reading the diff.

`tests/test_agents_schema_stage5.py` (14 tests) runs every assertion against a
database that already holds rows, because an empty one proves nothing:

* a **populated** Stage-4 database upgraded to head — rows and foreign keys
  preserved (`PRAGMA foreign_key_check` empty), a grant still pointing at the
  agent and capability it pointed at before;
* a **legacy** Stage-4 database seeded with values the new CHECKs would reject
  (`risk_level='EXTREME'`, `access_class='destroy'`, grant `status='banana'`).
  The upgrade must succeed and normalize each to the safest member of its
  vocabulary — `medium`, `read`, `active` — keeping the rows. An unrecognized
  risk deliberately does **not** become `low`, and an unrecognized access class
  does **not** become `execute`;
* values already inside the vocabulary are left alone, so normalization corrects
  rather than overwrites;
* all four CHECKs and the unique `capability_key` refuse a bad value **by
  insertion**, not only in the ORM's opinion of itself;
* the server defaults fill a raw insert that omits them — `(approval_level 0,
  access_class 'read', description '', enabled 1, requires_scope 0,
  prohibited_reason '')` and `('', 0, 'active')` for a grant. This is the case
  the ORM hides: it supplies Python-side defaults, so a migration that added
  nothing would pass every ORM-level test while a restore or a script wrote empty
  strings into governed columns. `requires_scope` reading back as `0` rather than
  a truthy string is asserted explicitly, because a text default of `'0'` that
  came back truthy would invert the meaning of the column;
* the **downgrade** removes exactly what the upgrade added and no more: the two
  columns and three CHECKs go, `ck_agent_capabilities_approval_level` stays
  because it belongs to Stage 2, rows survive, and the returned schema really
  does accept the free text it used to;
* **re-upgrade** after that downgrade is clean.

An offline Postgres render of all eight revisions was read back and counted: 44
`CREATE TABLE`, 11 `ADD CONSTRAINT`, 12 `CHECK`, 9 `SET DEFAULT`, 12 `ADD
COLUMN`, the three normalization `UPDATE`s, one `INSERT` and seven `UPDATE`s
against `alembic_version`, and zero SQLite-isms. Every Stage-5 fragment — the
three new constraint names, both new columns, all three normalization statements
— appears exactly once.

`tests/test_migration_portability.py::test_the_chain_is_eight_revisions_deep` is
deliberately brittle: its hard-coded count is the assertion that notices a
revision was added without its DDL being reviewed. It was bumped by hand for this
revision, which is the review it exists to force.

## What is not true yet

* **No tool boundary calls `check()`, but assignment does.** Stage 6 gave the
  boundary its first caller: assignment rule 7 asks `check()` about every
  capability a task requires before the work is handed out, and a denial refuses
  the assignment. Adapters and the tool registry are still P-05, so a grant does
  not yet stop an adapter from doing something else.
  `GET /agent-capabilities/status` says this in its `enforcement_note` rather than
  leaving it to be inferred from a catalog that looks authoritative. See
  [AGENT_ASSIGNMENTS.md](AGENT_ASSIGNMENTS.md).
* **Eight capabilities are disabled pending the subsystems that would use them.**
  They are in the vocabulary so that a template or a request naming one gets a
  precise refusal instead of "unknown key".
* **No agent is granted anything at creation.** A newly created agent holds zero
  capabilities, and Stage 6 did **not** change that: it added verification at
  assignment time, not grants at creation time. Granting from a template's allowed
  set is still an explicit owner action, which means an `ASSIGN_EXISTING` decision
  naming required capabilities is refused at rule 7 until those grants exist
  (L-78).
* **Expiry is enforced on use, not on a clock.** There is no timer, because
  autonomous scheduling is P-12. A lapsed grant is discovered by `check()` or by
  `sweep_expired()`.
