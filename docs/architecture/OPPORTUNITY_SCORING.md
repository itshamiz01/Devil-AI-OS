# P-03 — Opportunity Scoring (§16) — scoring-v1

Decision record: **ADR-005** (`docs/decisions/ADR-005-opportunity-scoring-v1.md`) adopts the prompt's §16 weights as the configurable scoring-v1 set, superseding the Blueprint's illustrative weights.

## Configuration, not constants

Weights live in `system_config` under `opportunities.scoring_weights`, seeded at startup only if absent, versioned (`scoring-v1`), readable via `GET /opportunities/scoring-config`, and editable **only by the owner principal** (HTTP route requires `modify_system_config` permission *and* the owner actor type; service layer enforces the same). Every stored score records the scoring version used, so rankings are reproducible against the exact configuration (§16.11 test: same evidence re-scored under the same configuration produces identical output).

## Dimensions (0–5 each, reason recorded per dimension)

| Dimension | Weight | Primary inputs |
|---|---|---|
| Verified demand | 20% | Demand stage derived from evidence (attention never counts as intent) |
| Problem importance | 10% | Problem evidence strength |
| Competitive opportunity | 10% | Saturation level (unknown ≠ empty) |
| Revenue model viability | 10% | Model clarity + pricing-evidence presence |
| Profit potential | 15% | Commercial scenarios, margin, break-even |
| Budget compatibility | 10% | Startup class vs owner budget |
| Distribution feasibility | 10% | Declared channel realism; evidence-supported channels score higher |
| Operational simplicity | 5% | System-capability fit (§7.5) |
| Strategic fit | 5% | Brief category/geography alignment |
| Evidence quality | 5% | The standalone evidence-quality value |

**Evidence quality is also reported standalone** (§16.3) next to every score, ranking and report. §16.3 cap: a high attractiveness score with weak evidence cannot become a recommendation (see below).

## Hard rejection rules (§16.10) — override any score

Prohibited category (screening) · illegal/unlawful model · minimum viable cost above budget · negative unit economics in all scenarios · required capability unavailable (incl. licence/credential dependencies the system cannot hold) · essential evidence contradicted · spam/fake-engagement distribution dependency. A hard rejection stores the rule and reason on the score row and the opportunity lifecycle, and emits `OpportunityHardRejected`.

## Recommendation mapping (§23H)

| Condition | Label |
|---|---|
| hard rejection | REJECTED |
| evidence quality < 2.5 or validation < 2 | REQUIRES MORE RESEARCH |
| weighted ≥ 4.2 and validation ≥ 3 and EQ ≥ 3.5 | STRONG CANDIDATE FOR VALIDATION |
| weighted ≥ 3.4 and validation ≥ 2 and EQ ≥ 3.0 | CANDIDATE FOR FURTHER VALIDATION |
| weighted ≥ 2.6 and validation ≥ 1 | REQUIRES MORE RESEARCH |
| otherwise | NOT RECOMMENDED AT THIS TIME |

No staging investigation reached a candidate label — the evidence base (labelled fixtures + one live pricing page) does not justify it, and the engine said so. That is the scoring system working as specified, not a scoring failure.
