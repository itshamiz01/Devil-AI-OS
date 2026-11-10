# P-17 — Marketing Strategy (§5)

**Surface:** `POST /api/v1/growth/businesses/{id}/strategies`,
`GET /api/v1/growth/strategies`, `POST /api/v1/growth/strategies/{id}/approve|reject`.

## Structure

A strategy carries the fifteen §5 sections as a structured dict
(business positioning, product positioning, target segments, value
proposition, brand messaging, differentiation, objectives,
channels, content strategy, campaign strategy, budget assumptions,
conversion targets, performance metrics, risk assessment, execution
timeline); unknown section keys are refused. Approaches follow the
prompt's ten (educational, content, performance, product-led,
community-led, partnership, referral, B2B, local, international).

## Kinds and the owner's ordering

Every strategy has a `kind` from the owner's mechanical ordering —
`improve | diversify | capital_efficiency | expansion` — shared
with the §19 recommendation ordering and P-16.

## Decisions and the profitability gate

Approval/rejection is an owner decision bound to a hash-checked
P-01 approval (the P-08/P-16 pattern; an agent cannot approve).
**Expansion-kind approval additionally respects the live P-16
profitability gate**: while the gate is closed it is refused unless
the owner records a per-item override with a mandatory reason,
stored on the strategy row (`gate_override: {by, reason, at,
gate_reason}`). There is no global off-switch. The list endpoint
flags draft/proposed expansion strategies as
`blocked_by_profitability_gate` so the state is visible before a
decision is attempted.
