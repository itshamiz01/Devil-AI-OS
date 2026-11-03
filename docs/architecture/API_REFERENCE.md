# P-01 API Reference

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

Pagination uses `limit` and `offset`. Task submission supports only `system.noop`, `system.echo`, and `system.wait`; arbitrary commands are rejected.
