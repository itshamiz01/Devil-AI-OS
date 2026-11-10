# The Permission Broker (P-10)

`app/security/broker.py` — the single evaluation path for
governed authorization in P-10. It never replaces the P-01 engine;
it composes it.

## Gate order (first denial wins; every outcome is recorded)

1. **Mode gate** — emergency_stop denies all non-owner actions;
   safe_mode allows owner everything, agents read-only (Level 0),
   services read + heartbeat. Unknown mode values fail closed as
   safe_mode.
2. **Restriction overlay** — a banned/suspended agent is denied;
   a read-only agent is denied non-read permissions.
3. **Business scope** — an agent registered with a `business_ref`
   may not act on another business (checked against the target's
   business id, and for stored resources, the resource's owner).
4. **P-01 engine** — the caller's role rules and explicit grants
   decide the base permission. Unknown principal or permission →
   deny.
5. **Risk gates** — the action is classified (§ below):
   - Level 0/1: an engine grant suffices.
   - Level 2: a valid, unexpired, unrevoked **capability token**
     for (holder, permission) OR a valid hash-bound approval.
   - Level 3: only an **owner-decided** hash-bound approval bound
     to the exact parameters. Capabilities never suffice.

Fail-closed contract: `authorize` never raises into the product —
an internal error (e.g. a settings store that fails to read)
returns a deny decision with `broker_error` recorded, and a
Level ≥ 2 allow that cannot be recorded (for single-use approval
consumption) is denied instead.

## Risk classification (deterministic, `policy.py`)

Action-prefix table: governance and financial execution are
Level 3; approvals, publishing, sending, configuration and
database writes are Level 2; ordinary tool use and writes are
Level 1; reads are Level 0. **Unknown actions default to
Level 3** — an unclassified action is treated as maximally
dangerous, never as safe.

## Capability tokens

`security_capabilities` rows are authorization metadata (holder,
permission, optional resource/business scope, expiry, revocation)
— they carry no secret value. Lifecycle: issue (delegation rules
apply: the issuer must hold the permission; owner-only
permissions are refused for non-owner holders), verify (lazy
expiry), revoke (immediate). Every transition is audited.

## Escalation (§7.3)

When an agent lacks standing authorization, the broker creates a
**P-01 approval request** (`request_escalation`) with a TTL and
the action's canonical parameters; an owner decides it through
the normal approval flow. The broker then requires
`verify_binding` to match before the approval authorizes anything
(see APPROVAL_POLICIES.md).
