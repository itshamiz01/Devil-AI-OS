# ADR-005 — Opportunity Scoring v1: weights adopted from the P-03 specification

**Status:** Accepted (9 Nov 2026, P-03 build, per the owner's P-03 prompt §16 and the PHASE_TRACKER note recorded when the prompt was received)
**Context:** The Master Blueprint carried illustrative opportunity-scoring weights. The owner's issued P-03 prompt (§16.1) specifies a concrete weight table and requires the weights to remain configurable. Two different weight sets must never silently coexist.

## Decision

P-03 adopts the P-03 prompt §16.1 weights as **scoring-v1**, superseding the Blueprint's illustrative weights:

| Dimension | Weight |
|---|---|
| Verified demand strength | 20% |
| Profit potential | 15% |
| Customer problem importance | 10% |
| Competitive opportunity | 10% |
| Revenue model viability | 10% |
| Startup budget compatibility | 10% |
| Distribution feasibility | 10% |
| Operational simplicity | 5% |
| Strategic fit | 5% |
| Evidence quality | 5% |

Rules that travel with this decision:

1. Each dimension is scored **0–5 deterministically** from stored evidence/analysis inputs — never assigned by an LLM.
2. Weights live in the `system_config` table under key `opportunities.scoring_weights` (seeded at startup as scoring-v1), **not** in code constants. Changing them requires the Owner principal (permission `modify_system_config` + owner check, the Article-0 governance pattern used for P-02 model profiles) and creates a new scoring version; existing score rows keep the version and inputs they were computed with, so rankings remain reproducible.
3. **Evidence quality is also reported as a separate standalone value** on every score, independent of its 5% weight in the total — an attractive opportunity with weak evidence must look weak.
4. **Hard rejection rules override any weighted total** (prohibited categories, impossible budget, no legitimate distribution path, unavailable essential licence). A rejected opportunity's stored score carries the rejection rule and reason.

## Consequences

- The Blueprint's illustrative weights are retired; any document quoting them is superseded by this ADR.
- Score comparability across time requires the version label; the ranking endpoint reports the scoring version alongside results.
- Future weight changes are governance events (owner-only, audited), never agent actions — an agent must not be able to tune scoring to favour an opportunity.
