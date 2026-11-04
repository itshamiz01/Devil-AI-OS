# P-01 Permission and Approval System

Principals: owner, system, agent, service, external integration. Permissions are stored as definitions and assignments with allow/deny effect and resource scope. Authorization is deny-by-default; inactive/unknown principals fail closed. Denials are audited.

Owner bootstrap creates an owner principal with Argon2id password hash and owner permission assignments. Sessions are opaque bearer tokens stored as SHA-256 hashes with expiry and revocation.

Approvals store requester, action, resource, risk, reason, requested permissions, canonical payload hash, status, approver, expiry and decision notes. Creating a request does not authorize execution. Decisions are validated; high/critical self-approval is forbidden. Changing action parameters changes the canonical hash and requires a new approval.

## Emergency stop permission

`system.emergency` (20 permissions total) gates `POST /api/v1/system/emergency/activate` and `/clear`. `OWNER_PERMISSIONS` is derived from the permission list, so the owner receives it automatically; `SYSTEM_PERMISSIONS` is enumerated explicitly as `system.read`, `tasks.read`, `events.read` and deliberately omits it, so the system principal can never halt or un-halt the application on its own authority. This enforces Constitution §12, which reserves emergency shutdown to the human owner.

Emergency state is durable runtime state in `system_configurations`, not configuration: it survives restart and no automatic path clears it (ADR-0013).

P-01 does not implement financial execution or automatic tool authorization from approvals.
