# Expansion Feature 2 — Universal Integration Framework: Developer Guide

How to add a connector without touching the OS architecture
(the pack's acceptance criterion for this feature).

## The contract in one page

A connector is three things:

1. **A descriptor** (`ConnectorDescriptor`) — key, name, provider,
   version, kind, `requires_credential`, and `Capability`
   declarations. Each capability declares the P-01 **permission**
   a caller must hold, a **risk action P-10 has already
   classified** (`app/security/constants.py: ACTION_RISK`), JSON
   input/output schemas, and optionally a per-minute rate limit
   and `is_sync`.
2. **An adapter** (`ConnectorAdapter`) — `health()` and
   `invoke(capability, payload, context)`. Raise on failure; the
   framework records errors honestly. Never fabricate a result.
3. **A registry row** — created by seeding (built-ins) or by
   `IntegrationService.attach_adapter`, carrying lifecycle and
   the credential secret NAME (never a value).

## Steps

1. **Copy the template**: `app/integrations/adapters/template.py`
   is a skeleton with the full checklist in its docstring.
2. **Declare capabilities honestly.** If P-10 has not classified
   your risk action, registration refuses it — that is deliberate:
   risk classification is P-10's authority. Use the closest
   classified action (`network.fetch` for an outbound read,
   `message.send_external` for an outbound send, …) or take the
   new action to the security layer as its own governed change.
3. **Credentials**: set `requires_credential=True`. Read the value
   ONLY from `context.credential_value` inside `invoke` — the
   framework resolves it through P-10's
   `SecretService.execute_with_secret` for that single call,
   after the broker authorizes. Never store, log, return or cache
   it. The owner attaches the credential by registering a metadata
   entry in P-10 (an `env:NAME` / `windows-vault:NAME` reference)
   and naming it on the connector's Configure action.
4. **Register the adapter**: add a factory to
   `app/integrations/registry.py: ADAPTER_FACTORIES` (built-ins)
   or call `attach_adapter` (tests, dynamic wiring). Until an
   adapter exists, the registry row reports
   `requires_owner_configuration` and cannot be enabled — that is
   the framework's honesty guarantee, not a bug.
5. **Webhooks**: if the provider sends webhooks, implement
   `verify_webhook_signature(secret_value, body, headers)` on the
   adapter and keep inbound routing with the owning engine
   (P-07's payments webhook is the pattern). The framework adds
   NO public inbound route of its own.
6. **Test with the harness**: `app/integrations/testing.py`
   (`MockConnectorAdapter`) simulates auth failure, timeout,
   provider error and rate limiting. A real connector ships its
   own tests in the `tests/test_f02_*` pattern: registration
   validation, lifecycle, broker denial, credential revocation,
   adapter failure recording.
7. **Versioning**: bump the connector's descriptor `version` when
   its capability contract changes; removing or renaming a
   capability is a breaking change for callers and must be
   treated like one (the framework's catalogue is the contract
   consumers read).

## Version compatibility rules

- The API surface version lives in `app/core/version.py`
  (`APP_VERSION`): 1.0.0 = completed P-01→P-18 roadmap; minor per
  expansion feature; patch for fixes. The route prefix stays
  `/api/v1`; additive growth is the standing policy (paths are
  added, not changed).
- Every operation's required permission and authorization depth
  are published in OpenAPI (`x-required-permission`,
  `x-authorization-depth`) and via
  `GET /integrations/api-catalogue` — generate clients from those,
  not from route source.
- Permission bindings in new route modules use the `Permission`
  enum (review §4.2 point 2); a test enforces that every literal
  binding elsewhere still names a real enum value.

## What the framework does for every invocation

connector exists → capability declared → enabled + adapter +
credential present (else an honest recorded refusal) → payload
validated against the declared schema → idempotent replay →
rate limit → **P-10 broker authorization** (mode, restrictions,
business scope, engine grant, risk gates: capability token at
Level 2, owner-decided hash-bound approval at Level 3, parameters
bound to connector + capability + payload hash) → credential
resolved by P-10 inside the call → adapter executes → outcome,
duration and broker decision id recorded in
`integration_invocations` and the P-01 audit trail.
