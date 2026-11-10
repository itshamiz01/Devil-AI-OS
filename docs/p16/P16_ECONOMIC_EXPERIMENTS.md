# P-16 — Economic Experiments (§11)

**Module:** `app/economy/ventures.py` · **Table:** `experiment_proposals`

## Pre-declaration is mandatory

Following the Constitution's standing rule (locked 2026-11-09),
no experiment exists without its declaration **before** it runs:
hypothesis, budget ceiling, duration, success metrics, failure
metrics, stop conditions — plus the P-08 set: problem, target
customer, expected outcome, minimum evidence and evaluation
schedule. Creation refuses any proposal missing a field; the live
smoke verifies the refusal over HTTP (422).

## Two-layer governance

P-16 proposals are the *economic* layer. On approval, a proposal
may be handed off (owner, autonomy level ≥ 3) to **P-08's
ExperimentService**, which creates the experiment under its own
pre-declaration rules and, on approval there, a real **P-07
budget** with a mechanical stop-loss. P-16 re-implements none of
that machinery.

## Outcomes flow back

`sync_experiment_outcome` reads the P-08 experiment's evaluation:
`VALIDATED` → success; `FAILED`/`INVALIDATED` → failure;
`INCONCLUSIVE` → inconclusive. The outcome is stored on the
proposal and — on verified completion — fed to P-09 memory
(§17). P-16 never evaluates an experiment itself; P-08's
evaluation, on P-08's evidence, is the only verdict.

## Pattern learning (§17)

`GET /economy/patterns` aggregates evaluated proposals by
`market_tag`: two or more failures in one market produce a
`repeated_failure` pattern, labelled correlation, not causation.
The pattern is **consumed**, not just reported:
`strategic_recommendations` pushes opportunities carrying a
repeated-failure market tag down its ordering (+3 priority) and
says why on the item itself. Patterns are counts of recorded
outcomes — nothing is inferred from a single result, and no
pattern is claimed from projections.
