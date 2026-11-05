# Agent Templates and the Validation Gate (P-04)

**Phase:** P-04 Stage 3 · **Status:** Implemented and tested · **Companion:** [ADR-0024](../decisions/ADR-0024-EXTEND-AGENTS-NOT-A-SECOND-REGISTRY.md)

A template is the definition an agent is built from. Stage 3 implements the registry of those definitions and the gate that decides whether one is fit to govern an agent. **No agent can be created through this subsystem yet** — the creation engine is Stage 4 — so what exists here is the part that has to be right before anything is built on top of it.

The design principle is that the gate is code, not a prompt. Nothing in `app/agents/templates.py` calls a model, so a verdict cannot be negotiated with, and a template cannot talk its way past a check.

## 1. Data model

Two tables, both created by migration `3013ebdd2699` (Stage 2) and extended by `e4817dfb6c0c` (Stage 3). Columns below were read back from the mapped metadata, not copied from a design note.

**`agent_templates`** — identity and current state:

| Column | Type | Notes |
|---|---|---|
| `id` | VARCHAR(36) | primary key |
| `name` | VARCHAR(128) | **unique**; a duplicate name is a `409`, not a second row |
| `category` | VARCHAR(64) | indexed |
| `description` | TEXT | |
| `current_version` | INTEGER | server default `'0'`; the version that governs, set only by publish |
| `status` | VARCHAR(32) | server default `'draft'`, indexed, CHECK `ck_agent_templates_status` |
| `created_at` / `updated_at` | DATETIME | |

**`agent_template_versions`** — the immutable documents:

| Column | Type | Notes |
|---|---|---|
| `id` | VARCHAR(36) | primary key |
| `template_id` | VARCHAR(36) | FK → `agent_templates.id`, indexed |
| `version` | INTEGER | unique together with `template_id` |
| `configuration_json` | JSON | written once, never edited |
| `validation_status` | VARCHAR(32) | server default `'unvalidated'`, CHECK `ck_agent_template_versions_validation_status` |
| `validation_details_json` | JSON, nullable | the verdict's evidence: issues, warnings, fingerprint, and what was *not* checked |
| `created_by` | VARCHAR(36), nullable | the principal that wrote the version |
| `created_at` / `updated_at` | DATETIME | |

The separation is the point: a version row is a document plus a verdict *about* that document. The only write ever applied to an existing version is its verdict, and it lands in its own columns, so an agent created from version 3 stays explainable by version 3 for as long as it exists.

## 2. Status graph

```
draft ──publish(valid version)──▶ published ──deprecate──▶ deprecated
  ▲                                                             │
  └────────────────────────restore──────────────────────────────┘
```

`draft` may also be deprecated directly. There are no other edges, and the graph is enforced twice: `TEMPLATE_TRANSITIONS` in the service raises `TemplateTransitionError` (HTTP `409`, code `invalid_template_transition`, naming the permitted targets), and `ck_agent_templates_status` refuses any value outside the vocabulary at the column.

`restore` deliberately returns a **draft**, never a published template. A deprecated template has been withdrawn from governing agent creation; handing that authority back as a side effect of one call is not a decision an owner would expect to have made.

`validation_status` is a separate vocabulary — `unvalidated`, `valid`, `invalid` — and it belongs to the version, not the template.

## 3. The validation gate

Validation is two layers, and both are deterministic.

**Structure** (`TemplateConfiguration`, `app/agents/schemas.py`): required `role_definition` and `mission`, bounded `system_instruction`, typed input/output schemas, capability lists, tool/model/memory requirements, a `ResourceBudget` whose six ceilings are bounded (`max_concurrent_tasks` 1–16, `max_task_seconds` 1–86400, `max_retries` 0–10, `max_inference_requests` 1–256, `max_child_agents` 0–8, `max_queue_occupancy` 1–64), a `RetryPolicy`, `timeout_seconds` (default 300), quality criteria, evaluation rules, approval requirements and a `security_classification` of `internal`, `confidential` or `restricted`. A model validator refuses a configuration that both allows and restricts the same capability.

Every one of these models is `extra="forbid"`. An unknown key is a `422` naming the key, not a silently dropped hint — a misspelled `allowed_capabilitys` that vanished would leave a template granting nothing, and the omission would read as a decision.

**Policy** (`TemplateService._policy_check`) — what a parse cannot express:

| Check | Result |
|---|---|
| `role_definition`, `mission`, `system_instruction` non-blank | issue |
| `expected_output_schema` a non-empty object | issue — assignment enforcement validates results against it, so without it no result can be checked |
| duplicate keys inside either capability list | issue |
| no allowed capabilities at all | **warning**, not an issue: such a template can only be assigned work that requires none |

**Capability keys are cross-checked against the catalog** (added in Stage 5; Stage 3 did not check them, because the catalog was empty until then and a check against an empty catalog would either refuse every template or pass every one). `templates.py::_catalog_check` reads the code-defined catalog rather than the table, so validation does not depend on a startup reconciliation having run:

| Key in the configuration | Verdict |
|---|---|
| Prohibited (level 3) under `allowed_capabilities` | **issue** — a template may not ask for what no agent can ever hold, so it cannot reach a `valid` verdict or be published |
| Not in the catalog, under either list | **issue** — the catalog is closed and defined in code, so an unknown key is a mistake to name rather than a new capability to accept |
| Disabled in the catalog | **warning** — a template may legitimately be written ahead of the subsystem that will use it; it simply cannot be granted yet |
| Prohibited under `restricted_capabilities` | neither — forbidding a prohibited capability is redundant, not wrong |

Every verdict carries `capability_catalog_checked: true`, the catalog size, and a note saying the check is about *definitions*: it does not mean any agent holds any of these keys, because grants are separate and governed by `CapabilityService`. A verdict stored before Stage 5 still says `false`, and nothing re-validates published templates at startup — L-72.

A verdict is persisted with a `configuration_fingerprint`: the project's canonical SHA-256 (`canonical_payload_hash`, the same function the approval subsystem uses, so there is one canonicalisation and not two) over the exact document judged. If a document ever differs from that hash, the verdict does not apply to it.

## 4. Publishing

`publish` requires a version whose stored verdict is `valid`. Publishing an `unvalidated` or `invalid` version returns `409` with the recorded issues in `details`, so the refusal carries its reasons. Publishing sets `status='published'` and `current_version` to the chosen version in one transaction.

Revising a published template appends a version and **does not** move `current_version`: a new document does not take effect by being written, only by being validated and published.

Cloning copies a version's configuration into a new draft template whose version 1 is `unvalidated`, even when the source was `valid`. A verdict is evidence about one document under one template id; it is not transferable by assertion.

`compare` returns a deterministic top-level field diff (`added`, `removed`, `changed`, `identical`) of two versions, plus each side's verdict. Nested values are compared as wholes: a partial structural diff of an arbitrary JSON schema is harder to read than the two values side by side. No model is involved.

## 5. Authorization

Two permission codes were added to the catalog, add-only (`PERMISSIONS` 28 → 30; `OWNER_PERMISSIONS` is derived from the same list, so the owner receives both automatically and the P-01 startup reconciliation grants them to an owner whose database predates the change):

| Code | Grants |
|---|---|
| `agents.templates.read` | list and read templates, versions and diffs |
| `agents.templates.write` | create, revise, validate, publish, deprecate, restore, clone |

`SYSTEM_PERMISSIONS` is unchanged at `system.read`, `tasks.read`, `events.read` and contains neither code, so the application can never define, validate or publish the template that governs its own agents. A principal without the codes receives `403` on all twelve operations; that is asserted per operation in `tests/test_agents_templates.py`.

`agents.read` and `agents.manage` already existed before P-04 and are not re-added. An earlier audit claimed otherwise; the claim was withdrawn (see L-60 — `PERMISSIONS` holds `(code, category, description)` tuples, so a bare-string membership test reports absence for a code the catalog contains).

## 6. Events

Six types were added to `EVENT_TYPES` (41 → 47) in the same commit as the code that publishes them: `AgentTemplateCreated`, `AgentTemplateRevised`, `AgentTemplateValidated`, `AgentTemplatePublished`, `AgentTemplateDeprecated`, `AgentTemplateRestored`. Source is `agent_templates`.

An **invalid** verdict is published too, with its issue count. "This template was refused, and why" is precisely the record an owner needs after the fact, and a bus that only carried successes would be a log of what went right.

## 7. Endpoints

Twelve operations under `/api/v1/agent-templates`, listed with their permissions in [API_REFERENCE.md](API_REFERENCE.md), plus `GET /api/v1/agents/status` (`agents.read`), which reports what the subsystem has assembled and what it has not — `templates: true`, and `factory`, `capabilities`, `assignments`, `resources` and `monitoring` all `false`, with notes naming the stages that own them. It is declared before `/agents/{agent_id}` so the literal path is never captured as an identifier.

The API surface is now **64 paths and 71 operations**, up from 53 and 58 at the end of P-03.

## 8. Migration and verification

Revision `e4817dfb6c0c` is the sixth in the chain (`03efdae6e24a → 2a904ceb99c4 → 5953caf8f23e → 72ee9705e18f → 3013ebdd2699 → e4817dfb6c0c`). It adds one column, two named CHECK constraints and the two server defaults that Stage 2's revision did not emit.

Autogenerate detected **only the new column** — it renders neither a CHECK addition nor a `server_default` change on an existing column (L-56) — so the four constraint and default operations were written by hand and then proven rather than assumed:

* On SQLite these run through batch mode, which **rebuilds** `agent_templates`, a table referenced by `agent_template_versions`, `agents` and `agent_creation_requests`. Verified against a database holding a row in each: all rows survive, `PRAGMA foreign_key_check` is empty, and every reference still resolves (`tests/test_agents_schema_stage3.py`).
* Both CHECKs were proven by inserting and updating invalid values (`'banana'`, `'retired'`, `'maybe'`, `'approved'`), each raising an integrity error.
* The downgrade drops the column and both constraints, preserves the rows and the references, and the revision can be applied again afterwards.
* The whole chain renders offline against `postgresql+psycopg://` with no SQLite-only statement: 44 `CREATE TABLE`, 17 `ALTER TABLE`, 5 `ADD CONSTRAINT`, 7 `CHECK` clauses, 84 `CREATE INDEX` (`tests/test_migration_portability.py`). That test exists because SQLite always takes the batch path, so a keyword batch mode accepts and Postgres rejects is invisible to every other test in the suite — it already caught one such bug in Stage 2.

## 9. What is deliberately not here

* **No creation engine.** Nothing turns a template into an agent; that is Stage 4, and `AgentServices.status()` reports `factory: false` rather than implying otherwise.
* **No capability catalog governance in this module.** Stage 5 added the cross-check described above, but validation only judges *definitions*. Granting, refusing and checking authority lives in `CapabilityService` — see [AGENT_CAPABILITIES.md](AGENT_CAPABILITIES.md).
* **No assignment, resource, health or metric behaviour** (Stages 6–8). The tables exist from Stage 2 and hold no rows.
* **No phase flag of its own.** `Services.agents` is always assembled, unlike `intelligence` and `opportunities`: Stage 3 stores and validates definitions, which cannot execute anything. The creation engine that does change system behaviour is what gets a flag, so a deployment can hold definitions it is not yet allowed to act on. Until then `GET /api/v1/agents/status` is the honest answer to "what can this do", and `GET /api/v1/agents` returns an empty list because nothing can create a row.
* **No frontend.** The repository contains none (Stage 9 is reported as deferred, not skipped).
