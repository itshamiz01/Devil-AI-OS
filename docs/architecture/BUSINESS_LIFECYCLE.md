# Business Lifecycle (P-06 §19)

States: `PROPOSED`, `ELIGIBILITY_REVIEW`, `BLUEPRINTING`,
`BLUEPRINT_READY`, `APPROVAL_PENDING`, `PRODUCT_PLANNING`,
`IN_DEVELOPMENT`, `INTERNAL_TESTING`, `DISTRIBUTION_PREPARATION`,
`LAUNCH_REVIEW`, `READY_FOR_LAUNCH`, `LAUNCH_APPROVAL_PENDING`,
`LAUNCHING`, `OPERATIONAL`, `PAUSED`, `BLOCKED`, `FAILED`, `ARCHIVED`.

The transition table lives in `app/business/lifecycle.py` as data;
every accepted transition writes a `business_lifecycle_events` row with
actor, reason and approval reference, and publishes
`BusinessLifecycleChanged`. Invalid transitions are rejected with 409
and audited (Scenario E).

## Guarded transitions (the §19 distinctions, enforced)

- `BLUEPRINT_READY` — requires a stored blueprint. A business is not
  blueprint-ready before one exists, and `BLUEPRINT_READY` does **not**
  mean a product exists.
- `READY_FOR_LAUNCH` — requires the latest readiness review to be
  `READY` or `READY_WITH_WARNINGS` (§20 hard blockers override).
- `LAUNCHING` / `OPERATIONAL` — reachable **only** through the launch
  flow: readiness READY-family + approved pre-declaration + a
  hash-bound owner launch approval verified against the *current*
  review and declaration ids (drift fails closed).
- `PAUSED` — from any active working state; returns only to the state
  it was entered from (recorded as `paused_from`).

## What OPERATIONAL means in staging

Reaching `OPERATIONAL` (Scenario J, owner-approved, fixture business)
records `deployment_state=local_package_only`,
`public_availability=false`, `launched_at`, and the transition detail
`revenue_asserted=false`. It asserts: a local package exists, was
verified, passed readiness, and was owner-approved. It does **not**
assert deployment, public availability, customers, or revenue — those
words would be false, and the state machine has no path that could
make them true in this phase.
