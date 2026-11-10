# Expansion Feature 2 — Universal Integration Framework: Architecture

Status: built under the owner's Gate 2 go-ahead (2026-11-10), as
feature 2 of 11 in the Post-Completion Expansion Pack's dependency
order (the pack's roadmap table lists it as Extra Feature 4; the
dependency order in the Gate 2 readiness review §7 governs). This
document records the architecture decisions taken inside the build
(the pack's internal approval steps are handled P-14-style:
architecture first, conservative minimal options, reported in the
gate summary).

## 1. What exists already (the starting map)

From the Gate 2 readiness review (§1.2, §2, §7.2) and a fresh
inspection:

- **`app/integrations/` is a seed**: one abstract contract
  (`IntegrationAdapter` with `health()` / `close()`, 27 lines), no
  registry, no concrete connector. Its one live consumer is P-02's
  `ModelProvider`, which subclasses `IntegrationAdapter` — the
  contract must therefore grow **additively**, never break.
- **P-10 owns credentials**: the metadata-only secrets registry
  (`security_secret_metadata` — names and `env:NAME` /
  `windows-vault:NAME` references, never values) and
  `SecretService.execute_with_secret` (§9.4: agents request an
  operation, not the secret; the value is handed only to the
  operation callback). P-05's credential broker resolves references
  at use time.
- **P-10 owns authorization**: the `PermissionBroker` (mode gates,
  restrictions, business scope, engine check, risk gates —
  capability token at Level 2, owner-decided hash-bound approval
  at Level 3) over the P-01 deny-by-default engine. Risk
  classification lives in P-10's `ACTION_RISK` table; unknown
  actions classify CRITICAL (fail closed).
- **Ad-hoc honest states exist per engine**: P-07's Stripe adapter
  reports `interface_only` / REQUIRES OWNER CONFIGURATION; P-17
  growth and P-18 experience each publish an `INTEGRATIONS`
  catalogue whose items are stamped `not_configured` /
  "REQUIRES OWNER CONFIGURATION" at response time. Each engine
  invented its own surface; there is no shared registry, lifecycle
  or vocabulary.
- **§4.2 inheritance contract** (review §4.2) binds every new
  route: principal from `get_principal`, enum permission gates,
  broker for governed execution, `ApprovalService` for Level 3,
  shared audit facade, secrets as metadata references only,
  additive tables, money in P-07.

## 2. Decisions (conservative minimal options)

1. **Grow the seed package in place.** The framework lives in
   `app/integrations/` (contract, constants, validation, registry,
   service, adapters, test harness, catalogue), models in
   `app/database/models/integrations.py`, repositories in
   `app/database/repositories/integrations.py`, routes in
   `app/api/routes/integrations.py`, wired on the `Application`
   object as `application.integrations` after P-18 (it consumes
   P-10, which is built earlier; the P-16+ `Service(application)`
   pattern). No new top-level package, no second secrets store,
   permission system, audit log or scheduler.

2. **The capability contract.** A connector is described by a
   `ConnectorDescriptor`: key, name, provider, version, kind (the
   pack §2 types: rest_api, webhook, oauth, local_app, browser,
   database, filesystem, email_calendar, productivity, ecommerce,
   payment, trading, custom), description, `requires_credential`
   flag, and a list of `Capability` declarations. A `Capability`
   declares: name, description, the **P-01 permission** a caller
   must hold (validated against the `Permission` enum),
   a **risk action** that must already exist in P-10's
   `ACTION_RISK` table (risk classification stays P-10's
   authority — a descriptor naming an unclassified action is
   refused at registration, not silently reclassified), JSON
   input/output schemas (validated by a small self-contained
   subset validator — no new dependency), an optional
   per-minute rate limit, and whether it is a sync (its success
   advances `last_sync_at`).

3. **One state vocabulary, two axes.** Lifecycle (registry-owned):
   `registered → configured → enabled ⇄ disabled`. Reported state
   (the single vocabulary every framework surface uses):
   - `configured` — enabled, adapter present, credential
     requirement satisfied, no standing error;
   - `not_configured` — known to the framework but not enabled /
     not yet configured;
   - `requires_owner_configuration` — no adapter code exists, or
     a required credential is not registered/active in P-10 —
     only an owner configuration act can advance it;
   - `error` — the last health check or invocation failed at the
     adapter.
   The seeded P-07/P-17/P-18 surfaces are registered with
   `source` attribution, and where they surface **through the
   framework** they use exactly this vocabulary (their own engine
   endpoints keep their existing labels — no breaking change; the
   legacy label "REQUIRES OWNER CONFIGURATION" maps 1:1 onto
   `requires_owner_configuration`).

4. **Credentials are references, resolved by P-10 at use time.**
   A registry row stores only `credential_secret_name` — the NAME
   of a P-10 secrets-registry entry. The framework never stores,
   logs or returns a value (schema-asserted: no value-shaped
   column exists in the framework's tables). At invocation, if
   the descriptor requires a credential, the adapter call runs
   inside `SecretService.execute_with_secret`, so the value
   exists only within that callback; a missing/revoked/unresolv-
   able secret fails the invocation honestly as
   `requires_owner_configuration`.

5. **Invocation discipline.** Every invocation, in order:
   connector exists → capability declared → lifecycle enabled +
   adapter present + credential satisfied (else an honest
   `not_configured` / `requires_owner_configuration` refusal,
   recorded) → payload validated against the capability's input
   schema → idempotency replay check (a repeated
   `idempotency_key` returns the recorded result, never
   re-executes) → rate limit (per capability, from recorded
   invocation history) → **P-10 broker authorization**
   (permission = the capability's declared permission, action =
   its declared risk action, resource = `integration:<key>`,
   parameters bound to connector + capability + SHA-256 of the
   canonical payload — so a Level-3 approval binds the exact
   call) → adapter execution inside the credential callback when
   required → outcome recorded. Every attempt — success, error,
   denied, refused, rate-limited, duplicate — is written to
   `integration_invocations` and the P-01 audit trail. A connector
   that is not configured **fails honestly**; nothing in the
   framework fabricates a success.

6. **Exactly one reference connector, genuinely real.**
   `local_echo` (provider "AUTONOMUS (local)", kind `custom`):
   no network, no credential; capability `echo` (permission
   `read_system_data`, risk action `read` — Level 0) validates
   `{message: string}` and returns it with a server timestamp.
   It proves registration → configuration → enablement → health →
   broker-authorized invocation end to end. All real external
   services (Stripe, the P-17 platforms, the P-18 channels) are
   seeded as descriptors **without adapters**: registered,
   honestly `requires_owner_configuration`, invocable by nobody —
   per the pack, no provider is claimed supported until its
   connector is implemented and tested. A documented developer
   template (`adapters/template.py`, never registered) and a mock
   adapter test harness (`testing.py` — auth failure, timeout,
   error, rate-limit behaviours) complete the developer framework
   the pack §5 asks for.

7. **Webhooks: contract here, routing stays with the owner
   engine.** The adapter contract gains an optional
   `verify_webhook_signature(secret_value, body, headers)` hook
   and the service exposes brokered verification, but **no new
   public inbound route is added**: P-07's existing payments
   webhook remains the single inbound webhook surface (adding a
   generic public webhook endpoint would widen the attack surface
   the review counted at exactly 3 public operations).
   Disposition recorded in the implementation report.

8. **The four API inconsistencies (review §2) — fixed or
   dispositioned, none ignored:**
   1. *Permission names invisible in OpenAPI* — **FIXED,
      additively.** `require_permission` now marks its dependency
      with the permission name; `create_app` decorates every
      operation with `x-required-permission` and
      `x-authorization-depth` OpenAPI extensions, and the
      framework serves a machine-readable **API catalogue**
      (`GET /integrations/api-catalogue`) built from the live app:
      path, method, required permission (or none declared),
      authorization depth (`route` / `authenticated` /
      `public`). No route behaviour changes.
   2. *Two permission-binding conventions (enum vs literals)* —
      **DISPOSITIONED with a guard.** New framework code binds
      permissions from the `Permission` enum exclusively (§4.2
      point 2). Existing literal call sites are not churned (a
      wholesale edit across 23 router modules is exactly the
      breaking-change risk the pack forbids); instead a test now
      scans every route module and **fails if any literal passed
      to `require_permission` is not a `Permission` enum value** —
      the silent-typo failure mode the review identified is now
      test-detectable, and the values are proven to agree.
   3. *Two authorization depths* — **DISPOSITIONED, now
      machine-readable.** The catalogue (fix 1) exposes each
      operation's depth honestly instead of letting a framework
      consumer assume route metadata describes access. The
      framework's own standard is both depths, deliberately:
      route gate for the coarse permission, broker authorization
      in the service layer for governed execution.
   4. *API version frozen at `0.1.0` since P-01* — **FIXED.**
      The version now lives in one place (`app/core/version.py`)
      and is bumped to **1.2.0** under a recorded rule: 1.0.0 =
      the completed P-01→P-18 roadmap, minor increments per
      expansion feature (F01 = 1.1.0 retroactively, F02 = 1.2.0),
      patches for fixes. `main.py` and the framework status
      surface read the same constant.

9. **No money surface, no governance change.** The framework
   moves no money, places no orders and executes no business
   action — it is plumbing. Its tables hold no money column
   (schema-asserted) and no secret value (schema-asserted).
   Article 0 holds: no governance, safety or financial-authority
   code is modified; P-10's risk table, broker and secrets
   registry are consumed, never edited. (The one additive touch
   inside `app/api/dependencies.py` marks the permission name on
   the dependency closure for OpenAPI — metadata only, no
   decision logic changes.)

## 3. Data model (additive migration, down_revision `85b7a9805207`)

- `integration_connectors`: id, key (unique), name, provider,
  version, kind, description, source (which engine's surface this
  registers, e.g. `framework`, `p07`, `p17`, `p18`, `owner`),
  descriptor (JSON snapshot of the declared capabilities +
  required permissions — declarations, not code), adapter_key
  (nullable; which in-code adapter implements it — null means no
  implementation exists), requires_credential,
  credential_secret_name (nullable; the NAME of a P-10 registry
  entry — a reference, never a value), settings (JSON, non-secret
  configuration only), lifecycle_status, health_state (last
  computed reported state), health_detail, last_health_at,
  last_sync_at, last_invoked_at, last_error, error_count,
  registered_by, timestamps.
- `integration_invocations`: id, connector_key, capability,
  principal_type/principal_id, idempotency_key (nullable),
  broker_decision_id (nullable), outcome (`success` | `error` |
  `denied` | `not_configured` | `requires_owner_configuration` |
  `rate_limited` | `invalid_request` | `duplicate`), result
  (JSON, on success — adapter results are data; a credential
  value can never be part of one by contract), error_detail,
  duration_ms, correlation_id, created_at. Append-only.

Physical tables: 226 → 228; metadata 225 → 227. Exact head/count
pins in earlier suites advance with F02 disclosure comments,
strictness preserved (the F01 precedent).

## 4. Command Center

A new **Integrations** view (Governance section): framework
status (API version, counts by reported state, the vocabulary),
the registry table (connector, provider, kind, lifecycle,
reported state, last health / last sync, error count) with
owner actions — configure (credential secret NAME + non-secret
settings), enable / disable, health check — an end-to-end invoke
panel for the reference connector, and the invocation history for
a selected connector. All on real endpoints; the view holds no
connector state of its own.
