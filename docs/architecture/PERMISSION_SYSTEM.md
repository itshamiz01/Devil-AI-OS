# Permission & Approval System (P-01 §9, §13) — as implemented

## Principals & categories

Principal types: Owner, System, Agent, Service, External. Permission categories (§9.2): read_system_data, write_system_data, submit_tasks, cancel_tasks, execute_tools, read_business_data, modify_business_data, access_sensitive_data, request_financial_operations, approve_actions, modify_system_config, manage_agents.

## Engine (deny-by-default)

`PermissionEngine.check` evaluates, in order: (1) explicit DB deny for the principal/role → deny; (2) explicit DB allow (resource must match when set) → allow; (3) role default policy → allow if granted; (4) deny. If permission data cannot be loaded, the check fails safely to deny. Role defaults: Owner = all; System = system/task/business data + tools (no approvals, no config); Service = read_system_data + submit_tasks; Agent = read/submit/cancel tasks + execute_tools + read_business_data; External = nothing. Grants for `request_financial_operations`, `modify_system_config` and `access_sensitive_data` additionally return `requires_approval=True`. **Every check is written to `audit_events`** with actor, permission, decision and reason.

## Approvals

Requests carry requester, action, resource, risk class, reason, requested permissions, parameters, and a **SHA-256 binding hash** of action+resource+parameters. States: pending → approved/rejected/expired/cancelled (terminal states cannot transition; deciding twice is a 409). Expiry is enforced on read/decide. `verify_binding` fails when parameters differ from what was approved — changing the action requires a new approval. Creating a request authorizes nothing. For task-gating approvals, the decision endpoint re-verifies the binding against the task's current handler+payload before releasing it.

## Authentication (one coherent scheme)

1. **Owner password login** — `POST /api/v1/auth/login`; the password arrives only via `AUTONOMUS_ADMIN_PASSWORD`, is scrypt-hashed at first startup, and only the hash is stored (`system_config`). Login issues a random session token; only its SHA-256 hash is stored (`app_sessions`) with expiry (default 12 h).
2. **Service token** — `AUTONOMUS_SERVICE_TOKEN` as Bearer → limited Service principal.
3. **Local-dev token** — with no admin password configured, `AUTONOMUS_DEV_TOKEN` as Bearer → Owner principal (documented local-dev mode). With neither configured, the API is *locked*: every protected endpoint returns 401.

No hardcoded/default credentials exist. Passwords are never stored or logged in plaintext (scrypt via `hashlib`, constant-time comparisons via `hmac.compare_digest`).

## Audit honesty

Audit rows live in the same SQLite database as everything else: they are append-only *by API design* (no update/delete endpoints exist), but a local SQLite file is **not** cryptographically tamper-proof against someone with filesystem access — stated plainly per §11, not dressed up.
