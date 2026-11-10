# P-16 — Autonomy and Approvals (§18)

**Module:** `app/economy/service.py` (settings + `_owner_approval`) ·
**Settings:** SystemConfig key `economy.settings`

## Autonomy levels

Levels 1–4 follow the Constitution's P-12 mode ladder
(Simulation → Supervised → Controlled → Emergency posture);
**the default is 2**. The level gates exactly one P-16 action:
experiment handoff to P-08 requires level ≥ 3, mirroring P-08's
own approval threshold. Raising the level is an owner settings
change, audited; P-16 cannot raise its own level, and no code path
lets an agent principal touch settings at all.

## The two owner switches

- `expansion_paused` — pipeline advances and experiment handoffs
  are refused. Exits (archive/reject) remain available: pausing
  must never trap work in place.
- `capital_commitments_frozen` — allocation and reinvestment
  **approvals** are refused; rejections remain available.

Both are settings the owner flips; both are checked at decision
time, not creation time, so a freeze bites immediately on work
already proposed.

## Hash-bound approvals (P-01 pattern, as in P-08)

Actions `economy.allocation`, `economy.reinvestment`,
`economy.experiment`, `economy.strategy` are approved through
`_owner_approval`:

- an owner caller may pass an existing P-01 approval id — it must
  be owner-decided and **binding-verified** against the exact
  parameters (action, resource, amounts); any mismatch is refused;
- an owner caller without one gets a create+decide in one step
  (the standing P-08 pattern);
- any non-owner caller is refused outright, approval id or not.

Approvals are single-use in P-01; P-16 consumes the verification,
it does not re-implement it.

## The profitability gate override

The one deliberate exception path: the owner may override the
profitability gate **per item** (one opportunity advance, one
strategy approval), with a **mandatory reason**, recorded on the
item and in the audit log. There is no global "gate off" switch —
an override is a decision, and decisions are recorded (§16).
