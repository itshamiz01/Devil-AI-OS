# Opportunity Scoring and Ranking (P-03)

Covers `backend/app/opportunities/scoring.py` — §16 and §17.

## 1. Design constraints

Three constraints determined the shape of this module:

1. **Deterministic.** The same inputs must produce the same score, byte for byte, on every run. Ranking is reproducible across two identical calls.
2. **Explainable.** Every dimension reports its own score, weight, justification and the evidence it rests on. A total with no breakdown is not a recommendation.
3. **Honest about absence.** An unscoreable dimension is reported as unscoreable. It is never filled with a neutral value that quietly inflates coverage.

## 2. The ten dimensions

`DEFAULT_WEIGHTS` sums to **exactly 100**, asserted at import:

| `WeightKey` | Weight |
|---|---|
| `verified_demand` | 20 |
| `profit_potential` | 15 |
| `problem_importance` | 10 |
| `competitive_opportunity` | 10 |
| `revenue_model_viability` | 10 |
| `budget_compatibility` | 10 |
| `distribution_feasibility` | 10 |
| `operational_simplicity` | 5 |
| `strategic_fit` | 5 |
| `evidence_quality` | 5 |

`ATTRACTIVENESS_KEYS` is the nine-key subset **excluding `evidence_quality`**. Attractiveness answers "how good is this opportunity"; evidence quality answers "how sure are we". Mixing them would let a well-documented bad opportunity outrank a poorly-documented good one, or vice versa. `evidence_quality` is still scored and still reported — separately.

§16 of the brief describes the scoring criteria narratively rather than as a weight table. **Rendering it as ten weighted dimensions summing to 100, with evidence quality also reported separately, is a design decision** and is listed for owner ratification.

## 3. `ScoreDimension`

Each dimension is a record, not a bare number:

| Field | Meaning |
|---|---|
| `key` | The `WeightKey` |
| `weight` | Its share of 100 |
| `score` | 0–5, or `None` when unscoreable |
| `scorable` | Whether a score exists at all |
| `justification` | Why this score, in words |
| `gap` | What is missing, when something is |
| `evidence_ids` | Which records support it |
| `computed_by` | Which component produced it |

`scorable=False` with a populated `gap` is the honest representation of "we could not assess this". `strategic_fit` is the dimension that most often takes this form: **it is unscored unless the owner states their capabilities**, so with no `stated_capabilities` supplied, coverage is typically 95% rather than 100%. That is a design decision listed for ratification — the alternative would be to award a neutral score, which would make coverage 100% by pretending a comparison happened.

## 4. Evidence quality

`OpportunityScorer.evidence_quality_dimension(...)` scores the evidence base using two multiplier tables.

`RELIABILITY_MULTIPLIER` — how much a source's standing is worth:

| `EvidenceReliability` | Multiplier |
|---|---|
| `authoritative` | 1.00 |
| `trusted` | 0.80 |
| `plausible` | 0.50 |
| `untrusted` | 0.20 |
| `model_generated` | 0.10 |

`CLASSIFICATION_VALUE` — how much a classification is worth:

| `EvidenceClassification` | Value |
|---|---|
| `verified` | 1.00 |
| `corroborated` | 0.85 |
| `supporting` | 0.55 |
| `tentative` | 0.30 |
| `unverified` | 0.05 |
| `contradicted` | 0.00 |
| `outdated` | 0.00 |

Contradicted and outdated evidence is worth exactly zero. It is retained in the store so the report can describe it, but it contributes nothing to a score. Model-generated evidence is worth a tenth of authoritative — enough to matter when corroborated by something real, never enough to carry a recommendation alone.

**Both tables are design choices with no external authority.** So are the two thresholds below. All four are listed for owner ratification.

## 5. `OpportunityScore`

| Field | Meaning |
|---|---|
| `attractiveness` | `Decimal` quantised to **4 dp** |
| `evidence_quality` | Reported separately, per §2 |
| `coverage_pct` | Share of weight that was actually scoreable |
| `scorable_count` | How many dimensions scored |
| `dimensions` | The per-dimension records |
| `unscored_dimensions` | Which ones could not be scored |
| `weights_sum` | Always 100; asserted |
| `ranking_key` | A `tuple[str, ...]` for total ordering |
| `computed_at` | When |

`attractiveness` is a 4-dp `Decimal`, so a zero score compares equal to `Decimal("0")` and **not** to the string `"0"` — a distinction that caught a defect in the test suite. `ranking_key` is a tuple of strings so that ordering is stable and reproducible regardless of how the underlying decimals are formatted.

With **no admissible evidence at all**, the score is not merely low: `attractiveness == 0`, `scorable_count == 0`, and the record says so rather than returning a small positive number that could be misread as a weak signal.

## 6. Hard rejections override the score

`ScoringOutcome`: `score`, `recommendable`, `rejected`, `rejection_classification`, `hard_rejections`, `reasons`, `minimum_validation_level_required`, `final_classification`, `weights_fingerprint`.

`MIN_EVIDENCE_COVERAGE_PCT = 60` and `MIN_RECOMMEND_ATTRACTIVENESS = Decimal("3.0000")` are the two recommendation gates. Failing either produces a **hard rejection** naming the criterion — for example a rejection whose reason contains `coverage`.

The key behaviour, and the one tested explicitly: **a hard rejection overrides a high score, but the score is retained.** `rejected=True` with a strong `attractiveness` is a meaningful state — it says "this looks good and we still cannot recommend it, here is why". Discarding the score would hide the reason; keeping only the score would hide the rejection.

`weights_fingerprint` is a **16-character** digest of the weight table in force. Two runs under the same weights carry the same fingerprint, so a change in ranking between runs is attributable either to the inputs or to a weight change — never to an unexplained difference.

## 7. Final classification

Six `FinalClassification` values, reached by a fixed precedence rather than a score band:

| Classification | Reached when |
|---|---|
| `rejected_compliance` | A prohibited category matched. Overrides everything |
| `incompatible_with_constraints` | The budget cannot cover it |
| `insufficient_evidence` | Coverage below the minimum, or no admissible evidence |
| `not_recommended` | Scored, and below the attractiveness threshold |
| `promising_needs_validation` | Attractive, but below the required validation level |
| `recommended` | Passes every gate |

The precedence matters: compliance beats evidence beats affordability beats score. An opportunity that is prohibited is `rejected_compliance` even if it would have scored 4.8, and one with no evidence is `insufficient_evidence` even if it is free.

`minimum_validation_level_required` comes from configuration — `opportunity_minimum_validation_level`, default **3** — and the scorer's own parameter defaults to `ValidationLevel.LEVEL_3_COMMERCIAL_EVIDENCE`.

## 8. Ranking

`OpportunityEngine.rank(records=None)` sorts by `(score.ranking_key, opportunity_id)` and then reverses, placing **unscored opportunities last**.

Two properties are deliberate:

* Ties break on `opportunity_id`, so the order is total and reproducible. Two opportunities with identical scores cannot swap places between runs.
* Unscored records sort last rather than being treated as zero. An opportunity that could not be scored is not the same as one that scored zero, and ranking it as though it were would be a false statement about it.
