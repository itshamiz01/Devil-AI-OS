# P-01 Permission and Approval System

Principals: owner, system, agent, service, external integration. Permissions are stored as definitions and assignments with allow/deny effect and resource scope. Authorization is deny-by-default; inactive/unknown principals fail closed. Denials are audited.

Owner bootstrap creates an owner principal with Argon2id password hash and owner permission assignments. Sessions are opaque bearer tokens stored as SHA-256 hashes with expiry and revocation.

Approvals store requester, action, resource, risk, reason, requested permissions, canonical payload hash, status, approver, expiry and decision notes. Creating a request does not authorize execution. Decisions are validated; high/critical self-approval is forbidden. Changing action parameters changes the canonical hash and requires a new approval.

P-01 does not implement financial execution or automatic tool authorization from approvals.
