# API Reference (P-01 + P-02)

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

Pagination uses `limit` and `offset`. Task submission supports only `system.noop`, `system.echo`, and `system.wait`; arbitrary commands are rejected.

### Intelligence endpoints (P-02)

All fourteen require authentication; unauthenticated requests return `401`. The four `intelligence.*` permissions are owner-only and deliberately absent from `SYSTEM_PERMISSIONS`, so the application can never reason about, re-plan or re-authorize itself on its own authority. An agent principal receives `403` on every one.

Two disclosure rules shape every response (§14): no provider credentials, and no unrestricted provider configuration. `GET /intelligence/models` omits the `configuration` dict, which is where a base URL or API key would live; tests assert the provider port appears in neither the `/models` nor the `/status` body.

`POST /intelligence/missions/{id}/approve` separates authorization from execution. Approval authorizes; the autonomy level permits. At the default `0_advisory` level the response returns `dispatched: []` and says plainly that nothing was submitted, rather than implying work has started (§15, §16).

`POST /intelligence/autonomy` derives `authorized_by_owner=True` **only** from the passed `intelligence.autonomy` permission check, never from the request body, and request schemas use `extra="forbid"` so the field cannot be smuggled in. Autonomy levels 3 and 4 are rejected with `422`.

An illegal mission state transition returns `409 Conflict` naming the permitted targets, not an unhandled `500`. An unknown `state` filter value returns `404` so a typo is visible rather than silently matching nothing.

When `intelligence_enabled` is false every intelligence route returns `409` rather than pretending to work.

OpenAPI snapshot: [`shared/openapi-p02.json`](../../shared/openapi-p02.json) — 38 paths, 41 operations. The P-01 snapshot [`shared/openapi-p01.json`](../../shared/openapi-p01.json) is retained unchanged as historical evidence.

Architecture: [INTELLIGENCE_ENGINE.md](INTELLIGENCE_ENGINE.md) · [AUTONOMY_LEVELS.md](AUTONOMY_LEVELS.md) · [CONTEXT_AND_PROMPT_SECURITY.md](CONTEXT_AND_PROMPT_SECURITY.md)
