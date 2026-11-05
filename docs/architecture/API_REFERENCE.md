# API Reference (P-01 + P-02 + P-03 + P-04 + P-05 Stage 3)

Base URL: `http://127.0.0.1:8000/api/v1` unless configured otherwise. OpenAPI snapshot: `shared/openapi-p01.json`.

## Authentication

`POST /auth/login` with JSON username/password returns a bearer token. Send `Authorization: Bearer <token>`. Sessions expire and can be revoked with `POST /auth/logout`. `GET /auth/me` returns the current principal.

## Response structure

Success: `{ "data": ..., "meta": ... }`. Error: `{ "error": { "code", "message", "details" }, "correlation_id" }`. Responses include `x-correlation-id`.

## Endpoints

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/health/live` | public minimal | Process liveness |
| GET | `/health/ready` | public minimal | Readiness boolean |
| GET | `/health` | `system.read` | Detailed health |
| GET | `/system/status` | `system.read` | Lifecycle, queue, diagnostics, metrics |
| GET | `/system/resources` | `system.read` | CPU/memory/disk snapshot |
| GET | `/system/emergency` | `system.read` | Emergency stop state |
| POST | `/system/emergency/activate` | `system.emergency` | Owner-only global halt; requires `reason` |
| POST | `/system/emergency/clear` | `system.emergency` | Owner-only release; requires `reason` |
| POST | `/tasks` | `tasks.submit` | Submit safe internal task |
| GET | `/tasks` | `tasks.read` | List/filter tasks |
| GET | `/tasks/{id}` | `tasks.read` | Task detail |
| GET | `/tasks/{id}/history` | `tasks.read` | Execution attempts |
| POST | `/tasks/{id}/cancel` | `tasks.cancel` | Cancel eligible task |
| POST | `/tasks/{id}/retry` | `tasks.retry` | Retry failed task |
| POST | `/tasks/{id}/pause` | `tasks.pause` | Pause queued/retry task |
| POST | `/tasks/{id}/resume` | `tasks.pause` | Resume paused task |
| GET | `/agents` | `agents.read` | Agent metadata only |
| GET | `/agents/{id}` | `agents.read` | Agent metadata only |
| POST | `/approvals` | `approvals.request` | Create approval request |
| GET | `/approvals` | `approvals.request` | List approvals |
| GET | `/approvals/{id}` | `approvals.request` | Approval detail |
| POST | `/approvals/{id}/decision` | `approvals.decide` | Approve/reject |
| GET | `/events` | `events.read` | Persisted system events |
| GET | `/audit` | `audit.read` | Audit events |
| POST | `/intelligence/chat` | `intelligence.use` | Interpret a request; conversational answer, plan, clarification or refusal |
| POST | `/intelligence/analyze` | `intelligence.use` | Analyse untrusted external content as data (§12.4) |
| POST | `/intelligence/missions` | `intelligence.use` | Create a mission from a request |
| GET | `/intelligence/missions` | `intelligence.read` | List missions, paginated, scoped to the caller |
| GET | `/intelligence/missions/{id}` | `intelligence.read` | Mission, plan versions and transition history |
| GET | `/intelligence/missions/{id}/progress` | `intelligence.read` | Progress computed from persisted task states |
| POST | `/intelligence/missions/{id}/plan` | `intelligence.use` | Generate a plan for review; launches nothing |
| POST | `/intelligence/missions/{id}/approve` | `intelligence.manage` | Owner approval; dispatches only if the autonomy level permits |
| POST | `/intelligence/missions/{id}/pause` | `intelligence.manage` | Pause the mission and its dispatched tasks |
| POST | `/intelligence/missions/{id}/cancel` | `intelligence.manage` | Cancel the mission and its dispatched tasks |
| POST | `/intelligence/missions/{id}/replan` | `intelligence.manage` | Revise a plan; requires a reason, preserves the prior version |
| GET | `/intelligence/models` | `intelligence.read` | Registered models; `configuration` deliberately omitted |
| GET | `/intelligence/status` | `intelligence.read` | Engine status, model health, autonomy, configuration notes |
| POST | `/intelligence/autonomy` | `intelligence.autonomy` | Change autonomy level; owner-only |

Emergency control is owner-only: `system.emergency` is granted to the owner and deliberately withheld from the system principal, so the application can never halt or un-halt itself (Constitution §12). While active, non-essential task submission returns `503` with error code `emergency_stop_active`; essential handlers remain admissible.

Backup and restore are **not** HTTP endpoints. Restore is destructive and CLI-only by design (ADR-0014): `autonomus backup`, `autonomus list-backups`, `autonomus restore --from <path>`.

Pagination uses `limit` and `offset`. Task submission supports only the four registered handlers — `system.noop`, `system.echo`, `system.wait` and `research.sweep`; arbitrary commands are rejected.

### Intelligence endpoints (P-02)

All fourteen require authentication; unauthenticated requests return `401`. The four `intelligence.*` permissions are owner-only and deliberately absent from `SYSTEM_PERMISSIONS`, so the application can never reason about, re-plan or re-authorize itself on its own authority. An agent principal receives `403` on every one.

Two disclosure rules shape every response (§14): no provider credentials, and no unrestricted provider configuration. `GET /intelligence/models` omits the `configuration` dict, which is where a base URL or API key would live; tests assert the provider port appears in neither the `/models` nor the `/status` body.

`POST /intelligence/missions/{id}/approve` separates authorization from execution. Approval authorizes; the autonomy level permits. At the default `0_advisory` level the response returns `dispatched: []` and says plainly that nothing was submitted, rather than implying work has started (§15, §16).

`POST /intelligence/autonomy` derives `authorized_by_owner=True` **only** from the passed `intelligence.autonomy` permission check, never from the request body, and request schemas use `extra="forbid"` so the field cannot be smuggled in. Autonomy levels 3 and 4 are rejected with `422`.

An illegal mission state transition returns `409 Conflict` naming the permitted targets, not an unhandled `500`. An unknown `state` filter value returns `404` so a typo is visible rather than silently matching nothing.

When `intelligence_enabled` is false every intelligence route returns `409` rather than pretending to work.

OpenAPI snapshot: [`shared/openapi-p02.json`](../../shared/openapi-p02.json) — 38 paths, 41 operations. The P-01 snapshot [`shared/openapi-p01.json`](../../shared/openapi-p01.json) is retained unchanged as historical evidence.

Architecture: [INTELLIGENCE_ENGINE.md](INTELLIGENCE_ENGINE.md) · [AUTONOMY_LEVELS.md](AUTONOMY_LEVELS.md) · [CONTEXT_AND_PROMPT_SECURITY.md](CONTEXT_AND_PROMPT_SECURITY.md)

### Opportunity endpoints (P-03)

All seventeen operations live under `/api/v1/opportunities` and require authentication; unauthenticated requests return `401` and a principal without the relevant permission receives `403` on every one. The four `opportunities.*` permissions are owner-only and deliberately absent from `SYSTEM_PERMISSIONS`, so no internal component can discover, research, analyse or transition an opportunity on its own authority.

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `opportunities.read` | List opportunities |
| POST | `` | `opportunities.manage` | Open an opportunity from a candidate |
| GET | `/status` | `opportunities.read` | Engine status, allowlist, scheduler state |
| GET | `/governance` | `opportunities.read` | The 12 permitted and 13 prohibited actions |
| GET | `/sources` | `opportunities.read` | Registered sources and the egress allowlist |
| POST | `/sources` | `opportunities.sources` | Register a source descriptor |
| GET | `/ranked` | `opportunities.read` | Ranked list, reproducible ordering |
| POST | `/discover` | `opportunities.research` | Generate candidates from a discovery context |
| GET | `/{opportunity_id}` | `opportunities.read` | Full detail, including business model and distribution |
| POST | `/{opportunity_id}/screen` | `opportunities.manage` | Compliance and budget screening |
| POST | `/{opportunity_id}/research` | `opportunities.research` | Run the research workflow synchronously |
| POST | `/{opportunity_id}/enqueue-research` | `opportunities.research` | Submit one research stage to the task queue |
| POST | `/{opportunity_id}/analyse` | `opportunities.manage` | Run the analysis chain |
| POST | `/{opportunity_id}/transition` | `opportunities.manage` | Move the lifecycle state |
| GET | `/{opportunity_id}/report` | `opportunities.read` | The nine-section report |
| GET | `/{opportunity_id}/evidence` | `opportunities.read` | Evidence records and quality statistics |
| GET | `/{opportunity_id}/history` | `opportunities.read` | Transition history, persisted and in memory |

Literal paths are declared before `/{opportunity_id}`, so `/status` is never captured as an identifier. Every request model uses `extra="forbid"`; an unexpected body field is a `422`, not a silently ignored hint.

Four behaviours are deliberate and are worth stating because they differ from the obvious implementation:

* **`POST /{id}/enqueue-research` schedules nothing.** §24 defers autonomous scheduling to P-12, so this is an owner-requested immediate submission. The response carries a real boolean `dispatched`, a `reason` when it is `false`, and `autonomous_scheduling: false`. An undispatched task is never presented as queued. `ResearchSweepCompleted` is published only when a task was actually submitted.
* **`POST /sources` does not permit the host.** Registration records the descriptor, its licence and its supported operations; the response states explicitly that the host is *not* placed on the egress allowlist, and `meta.allowlist` remains `[]`. "What is this source" and "may we contact it" are two separate owner decisions.
* **`GET /{id}/report` returns `409` when the opportunity has not been analysed.** Nine sections of absence presented as a deliverable would be misleading.
* **`GET /{id}/history` returns `persisted` and `in_memory` separately**, each with its own count, rather than merging two sources of truth into one list.

An illegal state transition returns `409 Conflict` naming the permitted targets, not an unhandled `500`. An unknown identifier returns `404`. An empty `reason` on a transition is a `422`. An unrecognised `state` filter or research `stage` is a `422`.

No endpoint in this group — or anywhere in the API — can spend money. A test asserts that no path or operation summary in the entire OpenAPI document contains `purchase`, `buy`, `order`, `pay`, `checkout`, `invoice`, `subscribe`, `contract`, `campaign`, `advert` or `domain`. There is no permission code and no configuration key for expenditure either (ADR-0020).

OpenAPI snapshot: [`shared/openapi-p03.json`](../../shared/openapi-p03.json) — 53 paths, 58 operations. The P-01 and P-02 snapshots are retained unchanged as historical evidence.

Architecture: [OPPORTUNITY_PIPELINE.md](OPPORTUNITY_PIPELINE.md) · [RESEARCH_SOURCE_ACCESS.md](RESEARCH_SOURCE_ACCESS.md) · [OPPORTUNITY_LIFECYCLE_AND_REPORTING.md](OPPORTUNITY_LIFECYCLE_AND_REPORTING.md) · [OPPORTUNITY_RISK_AND_GOVERNANCE.md](OPPORTUNITY_RISK_AND_GOVERNANCE.md)

### Agent template endpoints (P-04 Stage 3)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/agent-templates` | `agents.templates.read` | List templates; `status` and `category` filters, `total` in `meta` |
| POST | `/agent-templates` | `agents.templates.write` | Create a draft template holding version 1 (`201`) |
| GET | `/agent-templates/{id}` | `agents.templates.read` | Template detail |
| GET | `/agent-templates/{id}/versions` | `agents.templates.read` | Versions, newest first |
| POST | `/agent-templates/{id}/versions` | `agents.templates.write` | Append the next version (`201`); never edits one |
| GET | `/agent-templates/{id}/versions/{version}` | `agents.templates.read` | One stored version, with its verdict |
| GET | `/agent-templates/{id}/compare` | `agents.templates.read` | Deterministic field diff; requires `left` and `right` |
| POST | `/agent-templates/{id}/validate` | `agents.templates.write` | Judge a version and persist the verdict with its evidence |
| POST | `/agent-templates/{id}/publish` | `agents.templates.write` | Publish at a version whose verdict is `valid` |
| POST | `/agent-templates/{id}/deprecate` | `agents.templates.write` | Withdraw a template; requires a non-empty `reason` |
| POST | `/agent-templates/{id}/restore` | `agents.templates.write` | Bring a deprecated template back **as a draft** |
| POST | `/agent-templates/{id}/clone` | `agents.templates.write` | Copy a version into a new unvalidated draft (`201`) |

Both codes are derived into `OWNER_PERMISSIONS` and absent from `SYSTEM_PERMISSIONS`, so the application can never define, validate or publish the template that governs its own agents. `GET /agents` and `GET /agents/{id}` are unchanged and still guarded by the pre-existing `agents.read`; the agent payload now also carries the registry columns Stage 2 added (`template_id`, `template_version`, `configuration_version`, `parent_agent_id`, `business_id`, `retired_at`), each optional.

Four behaviours are deliberate and differ from the obvious implementation:

* **An unknown field is a `422`, at both levels.** All five request models are `extra="forbid"`, and so is `TemplateConfiguration` with its nested `ResourceBudget` and `RetryPolicy`. A misspelled `allowed_capabilitys` that was quietly dropped would leave a template granting nothing, and the omission would read as a decision. The error names the offending key.
* **Publishing an unvalidated or invalid version is a `409` that carries the reasons.** The response `details` include the stored `validation_status` and the recorded `issues`. "Rejected" without a reason is not an answer an owner can act on.
* **A verdict states what it did not check.** Every validation response reports `capability_catalog_checked: false` with a note naming P-04 Stage 5, because the capability catalog is empty until then. A verdict that quietly implied more checking than happened would be a false claim.
* **`restore` returns a draft, not a published template.** Resuming the authority to govern agent creation takes a deliberate second act — validate, then publish.

An illegal template transition returns `409` with code `invalid_template_transition`, naming the permitted targets. An unknown template or version returns `404`. A configuration that does not parse returns `422` with code `template_configuration_invalid` and every issue listed; nothing is stored. A duplicate template name returns `409`.

No endpoint in this group can create an agent, grant a capability, assign work or execute anything. Creation is Stage 4 and lives in its own group below; capability governance, assignment, resources and monitoring are Stages 5 to 8, and `GET /agents/status` reports each of them as `false` with a note naming the stage that owns it, rather than implying they exist.

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/agents/status` | `agents.read` | What the P-04 subsystem has assembled, and what it has not |

It is declared **before** `/agents/{agent_id}`, so the literal path is never captured as an identifier — the same ordering rule the opportunity routes depend on. As of Stage 4 it reports `templates: true` and `factory: true`, with `capabilities`, `assignments`, `resources` and `monitoring` still `false`.

### Agent factory endpoints (P-04 Stage 4)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/agent-factory/evaluate` | `agents.factory.read` | Preview a decision. Runs the same checks as `/create`, writes nothing, returns `recorded: false` |
| POST | `/agent-factory/create` | `agents.factory.admin` | Evaluate, record the decision and carry it out (`201`) |
| GET | `/agent-factory/requests` | `agents.factory.read` | The creation ledger, newest first; `decision` and `approval_status` filters, `total` in `meta` |
| GET | `/agent-factory/requests/{id}` | `agents.factory.read` | One recorded decision, including the reason for it |
| POST | `/agent-factory/queue/drain` | `agents.factory.admin` | Re-evaluate queued requests, oldest first; owner-invoked, never scheduled |
| GET | `/agent-factory/status` | `agents.factory.read` | Registry and queue counts against the configured ceilings |

Both codes derive into `OWNER_PERMISSIONS` and neither is in `SYSTEM_PERMISSIONS`. Splitting read from admin means a principal can be given the ability to *ask* what a creation would decide without the ability to make one happen. There is deliberately **no** `agents.factory.approve`: a gated creation is decided through the central `POST /approvals/{id}/decision` under the pre-existing `approvals.decide`, so the owner has one approval surface rather than a second one only agents know about.

`GET /agents` and `GET /agents/{id}` are unchanged and still guarded by `agents.read`; as of Stage 4 they can return rows, because `/agent-factory/create` writes them. All three groups — `/agents`, `/agent-templates` and `/agent-factory` — answer **`409` naming `AUTONOMUS_AGENTS_ENABLED`** when the subsystem is not assembled, rather than a `500` from a half-built engine. `GET /agents/status` is the one exemption: it is the endpoint that reports the phase is disabled, so it must keep answering.

Five behaviours are deliberate and differ from the obvious implementation:

* **No model is consulted.** Every decision is the output of an ordered list of checks against the database, the configured ceilings and the resource monitor. A recommendation from a model would be an opinion; a decision that mints an identity has to be reproducible.
* **A `REJECT`, a `QUEUE` and a `REQUEST_OWNER_APPROVAL` are all `201`.** The resource created is the *recorded decision*, and those three are outcomes rather than failures. Reporting a refusal as an error would train a caller to treat a decision as a bug.
* **The request is recorded before it is executed**, so a decision that fails halfway is still on the ledger instead of having silently not happened.
* **A repeated `idempotency_key` replays the recorded outcome** (`replayed: true`) rather than deciding twice. Requests without a key never collide: the unique constraint allows any number of NULLs.
* **The response states what it did not check.** `capability_catalog_checked: true` since Stage 5, carrying the catalog size, the prohibition list, and a note naming what the check does *not* cover — no tool boundary calls `CapabilityService.check()` yet, because adapters are P-05 and assignment output contracts are Stage 6. `assignment_supported: false` because `ASSIGN_EXISTING` is declared in the vocabulary but never emitted — assignment validation is Stage 6.

Architecture: [AGENT_TEMPLATES.md](AGENT_TEMPLATES.md) · [AGENT_FACTORY.md](AGENT_FACTORY.md) · [ADR-0024](../decisions/ADR-0024-EXTEND-AGENTS-NOT-A-SECOND-REGISTRY.md)

### Agent capability endpoints (P-04 Stage 5)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/agent-capabilities/status` | `agents.capabilities.read` | Catalog size, counts by approval level, the prohibition list, the per-agent ceiling, and what is not enforced yet |
| GET | `/agent-capabilities` | `agents.capabilities.read` | The catalog, most-restrictive level first; `category`, `risk_level`, `approval_level` and `enabled` filters |
| GET | `/agent-capabilities/{capability_key}` | `agents.capabilities.read` | One entry, including why a prohibited one is prohibited |
| GET | `/agents/{agent_id}/permissions` | `agents.capabilities.read` | What one agent holds. Nothing is implicit: an unlisted capability is not held, whatever the agent's template allows |
| POST | `/agents/{agent_id}/permissions` | `agents.permissions.grant` | Grant one capability, or refuse and say why (`201`) |
| POST | `/agents/{agent_id}/permissions/{permission_id}/revoke` | `agents.permissions.grant` | Revoke one grant, with a reason |

Both codes derive into `OWNER_PERMISSIONS` and neither is in `SYSTEM_PERMISSIONS`, so the application cannot widen its own authority. Reading is separated from granting for the same reason as the factory split: an agent may need to know what a capability costs without being able to hold one, and granting does not imply reading — a principal holding only `agents.permissions.grant` gets `403` from the catalog endpoints. `/agent-capabilities/status` is declared before `/{capability_key}` so the literal path is never captured as a key.

Deciding a level-2 grant is **not** here. It goes through the central `POST /approvals/{id}/decision` under the pre-existing `approvals.decide`, so the owner has one approval queue for every gated action rather than one per subsystem.

Five behaviours are deliberate:

* **The catalog is read-only over HTTP, and that is asserted.** A test walks the OpenAPI document and requires every `/agent-capabilities` path to expose `GET` only. A capability that could be added over HTTP could be added at level 0 by whoever holds the grant permission, and then the level a capability carries would depend on who asked. The catalog is code, reconciled at startup.
* **A refusal is an error, not a `200` with a sad field in it.** `404 capability_not_found`, `403 capability_prohibited` (carrying the reason), `409 capability_disabled`, `409 agent_not_grantable`, `409 capability_conditions_unmet`, `403 capability_denied` for a self-grant. A caller must not be able to ignore a prohibition by not reading a field.
* **A level-2 grant is `201` and `pending`.** The resource created is the grant record; the authority does not exist until the owner decides. `200` with an active grant would claim an authority nobody had approved.
* **Granting is idempotent on agent, capability and scope**, returning `replayed: true`. Two rows for one authority is two authorities.
* **The emergency stop blocks granting and never blocks revoking.** Removing authority is what an emergency calls for; a stop that prevented it would make the system less safe while stopped.

Architecture: [AGENT_CAPABILITIES.md](AGENT_CAPABILITIES.md) · [AGENT_GOVERNANCE.md](AGENT_GOVERNANCE.md)

### Agent assignment endpoints (P-04 Stage 6)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/api/v1/agents/{agent_id}/assign` | `agents.write` | Run the nine assignment rules; `201` records the work |
| GET | `/api/v1/agents/{agent_id}/assignments` | `agents.read` | That agent's ledger rows |
| GET | `/api/v1/assignments` | `agents.read` | The ledger, filterable by `status` and `agent_id` |
| GET | `/api/v1/assignments/status` | `agents.read` | Counts by status, the rule list, and what is not observed |
| GET | `/api/v1/assignments/{assignment_id}` | `agents.read` | One row, with the task's state resolved beside it |
| POST | `/api/v1/assignments/{assignment_id}/start` | `agents.write` | `assigned` to `in_progress`; records that work began |
| POST | `/api/v1/assignments/{assignment_id}/complete` | `agents.write` | Judge the result against the output contract and close it |
| POST | `/api/v1/assignments/{assignment_id}/cancel` | `agents.write` | Release the hold so the task can be given to somebody else |

Five behaviours are deliberate and visible in the responses:

* **A refusal is a `409`, not a `200` with a sad field in it**, and its
  `details.evaluation` carries every rule that ran, which one refused, and why.
* **A refusal creates nothing.** The `201` on `assign` always means a ledger row
  exists, so the ledger reads as a list of work somebody was actually given.
* **Completion is judged.** A reported success whose result breaks the contract
  produces `status: failed`, `accepted: false` and the violations listed; an
  assignment carrying no contract produces a reason saying the result was recorded
  *unjudged* rather than a silent pass.
* **`agents.write` is new in Stage 6** because assigning work changes what the
  system will do next, and `agents.read` has only ever looked at the registry.
* **`GET /assignments/status` reports `progress_observed: false`.** Nothing watches
  task progress yet, so an assignment can sit in `assigned` after its task has run;
  the endpoint says so instead of letting a healthy-looking count imply otherwise.

See [AGENT_ASSIGNMENTS.md](AGENT_ASSIGNMENTS.md).

The live surface after Stage 6 is **83 paths and 91 operations** (75 and 83 after Stage 5; 70 and 77 after Stage 4; 64 and 71 after Stage 3; 53 and 58 at the end of P-03). A `shared/openapi-p04.json` snapshot is written when the phase completes at Stage 10; the P-01, P-02 and P-03 snapshots are retained unchanged as historical evidence.

### Execution endpoints (P-05 Stage 3)

Architecture: [EXECUTION_POLICY_MODEL.md](EXECUTION_POLICY_MODEL.md)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/api/v1/execution/requests` | `execution.submit` | Run §8.1's ten policy checks; `201` admits (QUEUED or AWAITING_APPROVAL) |
| GET | `/api/v1/execution/requests` | `execution.read` | The request ledger, filterable by `status`, `agent_id`, `tool_id` |
| GET | `/api/v1/execution/requests/{request_id}` | `execution.read` | One request, with its recorded classification and approval reference |
| POST | `/api/v1/execution/requests/{request_id}/retry` | `execution.submit` | Re-run policy after an owner decision or human intervention |
| POST | `/api/v1/execution/requests/{request_id}/cancel` | `execution.submit` | Withdraw an admitted request; terminal states refuse |
| GET | `/api/v1/execution/tools` | `execution.read` | Tool discovery (§7); never configuration references |
| GET | `/api/v1/execution/tools/{tool_id}` | `execution.read` | One tool's contract, risk and health |
| POST | `/api/v1/execution/tools/register` | `execution.admin` | Declare a tool; lands REGISTERED, never AVAILABLE |
| POST | `/api/v1/execution/tools/{tool_id}/validate` | `execution.admin` | Run the five validation gates; AVAILABLE only if all pass |
| POST | `/api/v1/execution/tools/{tool_id}/disable` | `execution.admin` | Take a tool out of routing, with the reason recorded |
| GET | `/api/v1/execution/status` | `execution.read` | Subsystem stage, registry and request counts, and what cannot run yet |
| GET | `/api/v1/execution/files/list?workspace=&path=` | `execution.submit` | Directory listing inside a workspace; runs synchronously |
| GET | `/api/v1/execution/files/read?workspace=&path=` | `execution.submit` | File contents, hash-evidenced; runs synchronously |
| POST | `/api/v1/execution/files/write` | `execution.submit` | Atomic write (temp + replace); runs synchronously |
| POST | `/api/v1/execution/files/create_dir` | `execution.submit` | Create a directory inside a workspace |
| POST | `/api/v1/execution/files/move` | `execution.submit` | Move a file within the workspace |
| POST | `/api/v1/execution/files/delete` | `execution.submit` | Quarantine-reversible delete |

Deliberate behaviours:

* **Identity comes from the principal, never the payload.** The submit body has
  no agent field; the agent is resolved from the authenticated principal. The
  owner holds `execution.submit` (OWNER_PERMISSIONS is derived) and still gets
  `403 execution_identity_required`, because no agent is bound to the owner
  principal.
* **A policy refusal is a `409 execution_refused`** whose `details.evaluation`
  carries every check that ran, which one refused, and why. Unlike an assignment
  refusal, an execution refusal *leaves a row*, at REJECTED with its reason:
  §6.1 makes REJECTED an outcome of a request, and `GET` on it stays readable.
* **`QUEUED` does not mean running.** Stage 2 admitted and queued nothing
  drained; Stage 3 runs *filesystem* requests before returning (the route
  submits, drains, and returns the final outcome), so a file op's result is
  visible in one call. Requests for adapters that do not exist yet (code,
  api) still stay QUEUED, and `/execution/status` reports which are which.
* **Every file operation is an execution request.** The six file routes do not
  shortcut the request machinery: each builds an `ExecutionRequestInput` and
  goes through the same ten policy checks, audit trail and run row as any
  other tool. A file operation with a policy refusal is a `409` with the
  evaluation, and a failed run is a recorded `FAILED` row - never a silent
  200.
* **Containment is resolved-path containment.** A `..` segment, an absolute
  path, a drive letter, a symlink escaping the root, or a symlinked *parent*
  of a new file is refused with `FAILED` / `workspace_escape`. The boundary
  is the realpath'd workspace root, not a prefix string.
* **Browser and desktop routes are not registered.** Their adapters cannot run
  in this environment; an endpoint that cannot work must not exist. The tools
  are in the registry, DISABLED, with the reasons recorded.
* **`AUTONOMUS_EXECUTION_ENABLED=false` answers `409 execution_disabled`** naming
  the setting, rather than a 500 from a half-built engine.

