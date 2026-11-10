# P-13 Business Isolation (§20)

Isolation is this phase's core requirement. The rule: **no
cross-business access — data, memory, credentials, files,
financial records — without explicit, scoped, time-limited
authorization governed under P-10's model**, and portfolio
intelligence must never become a back door around business-level
permissions.

## The enforcement layers

1. **Portfolio aggregates are owner/system-only.** Every
   portfolio-level read (overview, finance, concentration, risk,
   strategy, grants, assignments) calls
   `_require_portfolio_reader`; an agent principal is denied and
   the denial is audited (`portfolio.isolation_violation`).
2. **Per-business reads mirror P-07.** `business_finance` /
   `business_profile` admit owner/system, or an agent whose P-01
   Agent row is homed (`business_ref`) to that business — the same
   rule P-07 and P-08 enforce, so P-13 cannot widen it.
3. **Two checked surfaces for agents.** `check_agent_access`
   (data categories) and `check_service_access` (shared services)
   are the only agent-facing cross-business paths. Both fail
   closed; both audit denials. An allow requires exactly one of:
   the agent's home business, an ACTIVE unexpired grant naming
   (agent, source business, category), an ACTIVE unexpired scoped
   assignment covering the business/category, or — for services —
   the home business's ACTIVE service access.
4. **Never-grantable categories.** credentials, customer_records,
   financial_records, business_memory, secrets, platform_accounts
   are rejected at validation time on grants, assignments and
   workflow contributions (naming one is an error, never a silent
   no-op), and denied by the checked surface even for the home
   business.
5. **Relationships grant nothing.** An ACTIVE relationship with a
   SPECIFIC_RECORDS scope still yields a denial from the checked
   surface until a grant/assignment exists (named test).
6. **Memory boundary.** P-13 reads P-09 only through the store's
   own policy with a system principal and filters to
   `access_scope == ORGANIZATION_SHARED` in code. Business-scoped
   memory is structurally invisible to the portfolio layer
   (Scenario 5).
7. **Workflow participation grants nothing.** Starting a portfolio
   workflow creates P-12 workflows inside each business's own
   scope; a participant's agent gains no access to other
   participants (Scenario 9 asserts the denial after start).
8. **Usage gating.** Shared-service usage by a business without
   ACTIVE access is refused and audited as an isolation event.

## What a grant is

One row (`cross_business_permissions`): portfolio context, source
business (data owner), target business (context, defaulting to
the agent's home), grantee agent, `authorized_data` categories
from the closed grantable set, permitted actions, purpose,
mandatory future expiry, granter, status. Revocation flips the
status; the very next check denies (Scenario 15). Expiry is
evaluated at check time — a grant whose expiry passes stops
working with no further action (security suite).

## Audit

Every grant, revocation, assignment, access decision, usage
refusal and checked-surface denial writes a P-01 `AuditEvent`.
Denials use action `portfolio.isolation_violation` with the
principal, business and category in details — the isolation trail
is queryable in the same audit log as everything else.
