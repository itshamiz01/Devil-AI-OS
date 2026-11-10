# API Reference (P-01) — as implemented

Base: `/api/v1`. Every response uses the envelope `{success, data, error{code,message,details}, correlation_id, meta}`; errors are never bare strings. `x-correlation-id` is accepted inbound and always returned. Pagination: `limit` (1–200, default 50) + `offset`, with `meta{total,limit,offset}`.

**Auth:** all endpoints require `Authorization: Bearer <token>` except `GET /health/live` (intentionally minimal) and `POST /auth/login`. Tokens: session token from login (owner), `AUTONOMUS_SERVICE_TOKEN` (limited Service principal), or `AUTONOMUS_DEV_TOKEN` (local-dev owner-equivalent). Unauthenticated → 401; authenticated but not permitted → 403.

| Method & path | Permission | Notes |
|---|---|---|
| GET `/health/live` | public | `{status:"alive", lifecycle_state}` only |
| GET `/health/ready` | read_system_data | 200 ready/degraded, 503 not_ready; includes DB health + threshold violations |
| GET `/health` | read_system_data | readiness + diagnostics + auth mode + recovered-task count |
| GET `/system/status` | read_system_data | lifecycle, DB health, resources, violations, queue snapshot |
| GET `/system/resources` | read_system_data | psutil CPU/RAM/disk + violations |
| POST `/auth/login` | public (credentials) | `{username,password}` → session token; wrong credentials → 401 |
| GET `/auth/me` | any valid token | principal + auth mode |
| POST `/tasks` | (engine: submit_tasks) | 201; body per TaskSubmitRequest; unknown handler/invalid payload → 422; queue full / resource-blocked → 429; idempotency-key dedupes |
| GET `/tasks` | any valid token | filter `status`, paginated |
| GET `/tasks/{id}` | any valid token | task + execution history |
| POST `/tasks/{id}/cancel` | (engine: cancel_tasks) | running tasks get `cancellation_requested` and end `cancelled` |
| POST `/tasks/{id}/retry` | any valid token | only from FAILED; resets the attempt cycle |
| POST `/tasks/{id}/pause` / `/resume` | any valid token | validated transitions only (409 on invalid) |
| GET `/agents` · GET `/agents/{id}` | any valid token | **read-only**; no creation endpoint exists in P-01 (404/405 on POST) |
| POST `/approvals` | read_system_data | creates a pending request; creation authorizes nothing |
| GET `/approvals` · GET `/approvals/{id}` | read_system_data | status filter supported |
| POST `/approvals/{id}/decision` | approve_actions | body `{approve, notes}`; deciding twice → 409; approving a task-gating approval verifies the parameter binding before releasing the task |
| GET `/events` | read_system_data | persisted critical events only, paginated |

OpenAPI docs are served by FastAPI at `/docs` on the running server.
