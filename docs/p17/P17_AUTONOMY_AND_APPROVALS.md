# P-17 — Autonomy and Approvals (§24)

## Autonomy levels

Growth settings carry the owner's autonomy level (default **2 —
recommendation**):

1. **Research only** — intelligence records and analysis.
2. **Recommendation** — strategies, campaigns and experiments are
   drafted and decided by the owner (staging default).
3. **Controlled execution of approved activities** — approved
   growth experiments may be handed to P-08 (which binds the real
   P-07 budget and enforces the stop-loss). Nothing external
   exists to execute: no platform is connected.
4. **Controlled autonomous growth within pre-approved rules** —
   additionally enables campaign auto-pause, only inside
   explicitly approved per-campaign rules.

Level changes are owner-only settings writes, validated 1–4.

## Approvals

Every consequential decision (strategy approval, campaign
approval, experiment approval, partnership agreement/active) uses
the P-08/P-16 hash-bound P-01 approval pattern: a supplied
approval must bind exactly these parameters and be owner-decided;
an owner caller without one gets a created-and-decided approval
(the call is the decision, bound and audited); an agent can never
approve its own proposals. Expansion approvals additionally pass
the P-16 profitability gate or record a per-item owner override
with a mandatory reason — there is no global off-switch, and P-17
cannot modify the gate (it consumes P-16's `engine_status` live).

## Emergency controls (owner flags, enforced in-service)

- `all_campaigns_paused` — campaign activation refused.
- `marketing_spend_frozen` — P-07 spend-request preparation
  refused.
- `communications_stopped` — message queueing refused.
- `outreach_suspended` — recorded posture flag for outreach
  surfaces (all outreach is draft-only in this phase).

These compose with P-10's modes; P-17 adds no authority of its
own and cannot lift a P-10 restriction.
