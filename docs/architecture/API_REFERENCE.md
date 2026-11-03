# API Reference (P-01 + P-02 + P-03)

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
