# P-13 Security Model (§20 + Article 0)

## Principals and gates

- **Owner**: all writes, decisions, grants, settings. Enforced in
  the service (`_require_owner`), mirrored by route permissions
  (read_business_data / modify_business_data / approve_actions).
  Routes never widen service rules.
- **System**: read access to portfolio aggregates (internal
  composition); no decision rights.
- **Agents**: no portfolio aggregates; exactly two checked
  surfaces (`/portfolio/access/check`,
  `/portfolio/access/check-service`) evaluated against the
  caller's own token identity — an agent can only ever check
  itself, because the principal comes from authentication, never
  from a request parameter.
- **External/service principals**: denied portfolio reads and
  writes (security suite).

## Article 0

P-13 cannot modify its own safety, ownership or financial
authority rules, and neither can anything acting through it:

- Portfolio settings govern only concentration threshold, share
  cap and declared capacities. There is no settings key that
  touches approvals, permission policy or money (named test
  asserts no such key exists; unknown capacity kinds are
  rejected).
- Intelligence outputs (opportunities, recommendations) are
  records with statuses; accepting one changes nothing outside
  P-13 — execution always re-enters the owning engine's governed
  path (P-12 workflows, P-08 proposals, P-07 spend paths, P-06
  creation gates).
- Memory is data, never authority: P-13 reads ORGANIZATION_SHARED
  records as detector input only (a shared-lesson opportunity);
  nothing in memory can create a grant, an assignment or an
  allocation.
- The evidence gate is fail-closed: untrusted sources raise;
  speculative items cannot be accepted.

## Secrets and credentials

P-13 stores no credentials and no secret values — grants and
assignments name *categories* from a closed set, and the
never-grantable set (credentials, secrets, customer/financial
records, business memory, platform accounts) is rejected at
validation on every surface that could carry it.

## Audit coverage

P-01 audit events for: portfolio CRUD and survival mode,
membership changes, objectives, relationships, analysis runs,
opportunity/recommendation decisions, risk assessments, service
CRUD/access decisions/revocations, allocation creation, quotas,
resource proposals/releases/reclaims, grants and revocations,
assignments and revocations, workflow creation/authorization/
start, venture proposal/handoff, report generation, settings
updates — and every isolation denial
(`portfolio.isolation_violation`).

## Known limits

- Single-process staging: no rate limiting specific to P-13
  beyond the platform's existing controls.
- Grant target defaults to the agent's home at grant time;
  re-homing an agent does not rewrite grants (checks fail closed;
  owner should re-issue). Flagged for P-14.
- DPAPI/Windows credential storage remains a P-10 owner
  configuration item; P-13 adds no credential storage at all.
