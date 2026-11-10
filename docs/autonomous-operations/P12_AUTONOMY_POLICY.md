# P-12 Autonomy Policy

## Levels (§4)

| Level | Name | Meaning |
|---|---|---|
| 0 | Observation Only | Read/observe; nothing executes. |
| 1 | Assisted Operations | Low-risk work may run; anything above risk 0 needs approval. |
| 2 | Controlled Autonomy | Risk-1 work may run inside policy; risk 2+ needs approval. |
| 3 | Expanded Autonomy | Risk-2 work may run when the P-10 broker also allows it (capability or standing rules still apply). |
| 4 | High Autonomy (Reserved) | No additional execution rights over Level 3 in this build: financial actions and risk-3 actions always require owner approval at every level. Level 4 exists so policy can express intent without silently widening execution. |

Financial actions (`financial.*`) and risk-3 actions require the
owner's hash-bound approval **at every level**. Autonomy never
widens the P-10 broker: the broker's deny is final, and its
capability/approval gates apply unchanged.

## Resolution: minimum of ceilings

For a prospective step, the effective level is the minimum of every
applicable ceiling, and the full trace is recorded on the decision
record:

- **global policy row** (owner-set) — or, when no row exists, the
  seeded settings default *for non-owner declarations*;
- **business policy row** for the workflow's business;
- **agent policy row** for the acting agent;
- **agent-in-business policy row**;
- **workflow policy row** — supersedes the workflow's creation-time
  declaration (the owner's current instruction wins), while all
  other scopes still cap;
- **action-category caps** on the matched rows;
- **Constitution mode cap** — simulation → 1, supervised → 2,
  controlled → 4, emergency → 0;
- **P-10 security mode cap** — safe mode / emergency stop → 0 for
  execution (risk-0 observation remains possible in safe mode,
  never in emergency stop).

Two properties are proven by named tests:

1. **No cross-business leakage** (Scenario 5): a Level-3 policy for
   Business A does not appear in Business B's ceiling trace, and B's
   effective level is unchanged.
2. **Declarations are not self-grants**: an agent-declared level is
   capped by the settings default (Level 1) unless the owner sets
   rows. An owner's declaration on their own workflow *is* their
   grant for that workflow (bounded by explicit rows and mode caps)
   — Scenario 15 raises one workflow by row and shows the sibling
   unchanged.

## Who may set policy

Owner only. `set_autonomy_policy` rejects every non-owner principal:
agents can never modify the rules that govern them (Article 0).
Changes are versioned rows with the setter and reason recorded.

## Interaction with modes

Autonomy levels sit *below* the Constitution and security modes.
Emergency (Constitution) or emergency_stop (P-10) collapses every
effective level to 0 for execution, regardless of rows. Modes never
self-promote anywhere in this system; returning from a stop is an
explicit owner act (see the Recovery Guide).
