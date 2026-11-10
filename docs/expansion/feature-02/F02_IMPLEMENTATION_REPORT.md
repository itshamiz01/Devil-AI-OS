# Expansion Feature 2 — Universal Integration Framework: Implementation Report

Companion to `F02_ARCHITECTURE.md` (the design, written first).
Gate 2 readiness input: `docs/expansion/EXPANSION_READINESS_REVIEW.md`
§7.2 (feature 4 in the pack's numbering = recommended-sequence
feature 2) — "READY … the registry, the capability contract and
the §2 fixes are the work." That is what was built.

## What was built

**Framework core (`app/integrations/`)**, grown in place from the
27-line P-02 seed contract:

- `base.py` (extended additively) — `Capability`,
  `ConnectorDescriptor`, `ConnectorContext`, `ConnectorAdapter`
  (with optional `verify_webhook_signature`); the seed
  `IntegrationAdapter` / `IntegrationHealth` are unchanged and
  P-02's `ModelProvider` still subclasses them untouched.
- `constants.py` — the ONE state vocabulary (reported states
  `configured` / `not_configured` / `requires_owner_configuration`
  / `error`; lifecycle `registered → configured → enabled ⇄
  disabled`), outcome vocabulary, audit action names.
- `validation.py` — a small self-contained JSON-schema-subset
  validator (no new dependency): descriptors and invocation
  payloads are checked against it.
- `registry.py` — adapter factories (exactly one built in:
  `local_echo`), descriptor builders for the 18 seeded
  connectors (Stripe descriptor projected from P-07's own
  `StripeAdapter.capabilities`; the 16 P-17/P-18 surfaces seeded
  by importing the engines' own `INTEGRATIONS` constants so the
  registry cannot drift from the engines).
- `service.py` — `IntegrationService`: seeding, lifecycle,
  configure (P-10 secret-name validation), health, the
  broker-authorized `invoke` pipeline, idempotent replay, rate
  limiting, webhook verification, `attach_adapter` (the
  developer/test wiring flow), the framework status read model.
- `catalogue.py` — the API catalogue: every route with its
  required permission and authorization depth, built from
  FastAPI's effective route candidates.

**Persistence** — migration `3f7a1c9e52b4` (revises
`85b7a9805207`), additive only, cycle-tested (226 ⇄ 228 physical
tables): `integration_connectors` (registry rows; the only
credential-related column is `credential_secret_name`, a NAME)
and `integration_invocations` (the invocation ledger).

**Routes** — 11 new operations under `/integrations` (framework
status, API catalogue, list/register/get connectors, configure,
enable, disable, health, invoke, per-connector and global
invocation history), bound from the `Permission` enum.
**Frontend** — an Integrations view in the Command Center
(Governance section): framework status, the registry table with
health/enable/disable, a configure panel that carries a P-10
secret NAME only, an invoke panel for the reference connector,
and invocation history.

**The seeded registry (18)**: `local_echo` — the one genuinely
real reference connector (local, no network, no credential,
enabled at seed time so the framework is provable immediately) —
plus Stripe and the 16 P-17/P-18 surfaces, all honestly
`requires_owner_configuration` with NO adapter: registered
declarations nobody can invoke. Registering a custom connector
behaves the same way, and enabling an adapter-less connector is
refused outright — a declaration can never masquerade as a
working connector.

## Credential, permission and audit discipline (measured)

- Credentials resolve ONLY inside `SecretService.execute_with_secret`
  (P-10, §9.4); the value exists only inside the broker callback.
  The security suite proves the resolved value appears in NO
  framework table, NO audit detail and NO secrets-metadata row,
  and that revoking the P-10 entry turns invocation into an
  honest `requires_owner_configuration`.
- Every invocation passes the P-10 broker with the capability's
  declared permission and P-10-classified risk action; at Level 3
  the approval binds connector + capability + payload hash
  (mis-bound approval denied, exactly-bound approval succeeds —
  tested). Every attempt is recorded in the invocation ledger
  AND the P-01 audit trail (`integration.*` actions); lifecycle
  changes are owner-only at route AND service layer.
- Schema guards assert: no money columns, no secret-value
  columns in framework tables; a structural test asserts the
  framework sources contain no financial-service or
  approval-decision machinery. P-07 untouched; Article 0 held.

## The four review §2 inconsistencies — dispositions

1. **Permission names invisible in OpenAPI — FIXED (additively).**
   `require_permission` marks its dependency closure; OpenAPI now
   carries `x-required-permission` + `x-authorization-depth` on
   gated operations, and `GET /integrations/api-catalogue` serves
   the machine-readable catalogue. Verified in tests and smoke.
2. **Two permission-binding conventions — DISPOSITIONED with a
   guard.** F02 routes bind from the enum only. Churning ~750
   existing literal call sites was rejected as pure risk with no
   behavioural gain; instead a unit test scans every route module
   and fails if any literal binding is not a `Permission` value,
   so the two conventions can never silently diverge in meaning.
   New modules follow the enum convention (review §4.2 point 2,
   and the developer guide states it).
3. **Two authorization depths — DISPOSITIONED, now explicit.**
   Both depths are legitimate (cheap route gate vs service-layer
   decisions that need context); the catalogue labels every
   operation `route` / `authenticated` / `public` so the depth is
   a published fact rather than tribal knowledge. F02 itself uses
   both deliberately: route gate for API access, broker
   authorization inside the service for every invocation.
4. **Version frozen at 0.1.0 — FIXED.** `app/core/version.py`
   defines `APP_VERSION = "1.2.0"` (version history rule
   recorded there: 1.0.0 = completed roadmap, 1.1.0 = F01,
   1.2.0 = F02, patch for fixes); the app, OpenAPI and framework
   status all read it.

**Webhooks disposition**: the adapter contract supports
signature verification and the service exposes it brokered, but
F02 adds NO public inbound route — inbound webhooks stay with
the owning engine (P-07's payments webhook). The public surface
remains exactly the 3 operations the review counted (asserted by
test and by smoke).

## Results

- New F02 tests: 34 (unit 12, integration 11, security 11) —
  registry lifecycle, capability-contract enforcement, payload
  validation, credential non-storage, honest not-configured
  failure, broker denial + Level-3 approval binding, rate limit,
  idempotency, catalogue/OpenAPI metadata, migration cycle.
- Full backend regression on final code: **1017 passed / 0
  failed** (983 baseline + 34 new; see `F02_TEST_REPORT.md` and
  `REGRESSION_EVIDENCE.txt` — the first pass surfaced 15 exact
  migration-head/table-count pins in earlier suites; all advanced
  with F02 disclosure comments, strictness preserved, affected
  files re-run green). Frontend: **58/58** + clean strict
  TypeScript build. Live smoke over real uvicorn: **27/27**
  (`docs/reports/F02_SMOKE_EVIDENCE.txt`), owner login on
  attempt 1.

## Honest limitations

- **Exactly one working connector exists** — the local reference
  connector. Every external service (Stripe, the 16 marketing/
  experience surfaces, anything registered later) remains
  honestly `requires_owner_configuration` until a real adapter is
  built and the owner configures a credential. The framework is
  plumbing, proven end to end; it is not 18 integrations.
- No outbound network code ships in F02 at all; retry policy is
  declared metadata (the mock harness simulates failures, real
  retry execution arrives with the first real network adapter).
- Rate limiting counts recorded invocations (durable, simple);
  it is per capability per connector, not a distributed limiter.
- Scheduled/background invocation is not added: P-12 remains the
  scheduler; the framework is invoked synchronously by callers.
- DEF-A1 (Windows unverified) and DEF-A2 (no real LLM) stand,
  untouched by this feature. Classification unchanged: READY FOR
  CONTROLLED PILOT.

## Rollback

Feature 2 is additive end to end. Rollback = downgrade
`3f7a1c9e52b4 → 85b7a9805207` (drops the two framework tables;
cycle-tested), remove the integrations router include and the
`APP_VERSION` wiring, and the seeded registry disappears with
the tables. No P-01→F01 data is touched by the migration.
