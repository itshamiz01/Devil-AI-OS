# Market and Competitor Analysis (P-03)

Covers `backend/app/opportunities/analysis.py` — §9.

## 1. The rule this module exists to enforce

An analysis module is where a system is most tempted to be helpful by guessing. Every analyser here is written so that **the absence of evidence produces a named absence**, not a plausible number.

The five `MarketAssessment.verdict` values make this explicit: `demand_demonstrated`, `demand_plausible`, `demand_unproven`, `demand_contradicted`, `insufficient_data`. There is no default that implies demand was found. With no admissible evidence the verdict is `insufficient_data` and TAM/SAM/SOM are `None` — not zero, because zero is a claim that the market is empty.

## 2. Evidence type routing

Each analyser only reads the evidence types that can actually support its question.

| Constant | Evidence types | Used by |
|---|---|---|
| `DEMAND_TYPES` | `search_volume`, `keyword_trend`, `marketplace_listing`, `official_statistic`, `social_signal` | `MarketAnalyser` |
| `PROBLEM_TYPES` | `forum_post`, `marketplace_review`, `competitor_review` | `MarketAnalyser` |
| `PRICING_TYPES` | `competitor_pricing`, `vendor_price_quote` | `CompetitorAnalyser` |

A `forum_post` cannot size a market and a `search_volume` cannot establish that a problem matters. Routing by type is what stops a volume of weak signals from being read as strong evidence of something else.

## 3. Reliability → provenance

`PROVENANCE_FROM_RELIABILITY` converts a record's reliability into the `Provenance` vocabulary that appears on every derived number:

| `EvidenceReliability` | `Provenance` |
|---|---|
| `authoritative` | `quoted` |
| `trusted` | `quoted` |
| `plausible` | `estimate` |
| `untrusted` | `estimate` |
| `model_generated` | `unknown` |

**Nothing maps to `verified` or `historical`.** Those two `Provenance` values exist in the vocabulary but no reliability level can produce them automatically. `verified` would require an independent confirmation the pipeline cannot perform in this phase, and `historical` requires a dated publication the extraction path does not establish. Leaving them unreachable is more honest than mapping `authoritative` to `verified` and implying a check that never happened.

## 4. `MarketAnalyser`

`analyse(evidence, *, geography=(), segments=(), buying_trigger=None, alternatives=())` → `MarketAssessment`.

`MarketAssessment`: `customer_description`, `data_gaps`, `demand_evidence_level`, `problem_importance`, `problem_importance_basis`, `reasons`, `signals`, `sizing`, `verdict`, `willingness_indicators`. **No field is required**, so an assessment of nothing is representable — that is the point.

`MarketSizing`: `tam`, `sam`, `som`, `geography`, `customer_segments`, `buying_trigger`, `existing_alternatives`, `data_gaps`. Each of TAM/SAM/SOM is a `SizedMarket`, whose only required field is `label`, so a market can be *named* as unsizeable rather than silently omitted.

### Problem importance is derived, never declared

`problem_importance` is computed from admissible `PROBLEM_TYPES` records and their strength:

| Admissible problem records | Result |
|---|---|
| 0 | `unknown` |
| 1 weak | `trivial` |
| 2 | `minor` |
| 3 | `moderate` |
| 1 strong | `significant` |
| ≥ 2 strong | `acute` |

`problem_importance_basis` is **required whenever importance is not `unknown`** — a model validator refuses an importance rating with no stated basis. This is one of two validators that caught a defect in the test suite rather than in the code, which is the behaviour wanted: the fix is to supply the justification, never to weaken the validator.

### Market saturation counts what was observed

| Observed competitors | Result |
|---|---|
| 0 | `empty` — **and `unknown` when nothing was observed at all** |
| ≤ 2 | `sparse` |
| ≤ 5 | `moderate` |
| ≤ 12 | `crowded` |
| > 12 | `saturated` |

The zero case splits deliberately. "We looked and found nobody" is `empty`; "we never looked" is `unknown`. Collapsing them would turn an unexamined market into a blue-ocean claim.

## 5. `CompetitorAnalyser`

`analyse(evidence, *, competitors=(), gaps=(), differentiation_basis=None)` → `CompetitorAssessment`: `competitors`, `data_gaps`, `differentiation_available`, `differentiation_basis`, `gaps_identified`, `inspected_count`, `market_saturation`, `price_range_low`, `price_range_high`, `reasons`, `verdict`.

`CompetitorProfile` (18 fields) requires only `name`. It carries `rating`, `review_count`, `price_points`, `pricing_provenance`, `rating_provenance`, `strengths`, `weaknesses`, `complaint_themes`, `identified_gaps`, `inspected`, `url`, `evidence_ids`, `offering`, `positioning`, `observed_at`, `price_currency`, `competitor_id`.

`rating_provenance` defaults to `unknown`, and a validator **requires it to be stated whenever a `rating` or `review_count` is supplied**. An unsourced star rating is exactly the kind of number that looks authoritative and is not.

`inspected` distinguishes a competitor the system actually looked at from one merely named. `inspected_count` in the assessment counts only the former, so a saturation verdict rests on inspected competitors rather than on how many names appeared in the input.

### Price selection uses the lower median

The price range is taken from `PRICING_TYPES` evidence. The central figure is the **lower median** of quoted prices: for an even number of observations it takes the lower of the two middle values, via index `(len - 1) // 2`.

This is a design choice, listed for owner ratification. It biases cost and revenue estimates **downward**, which is the conservative direction for a feasibility judgement: a business that survives a low price estimate has more margin than one tuned to a high estimate. It is not presented as the market's true average price.

## 6. `BusinessModelAnalyser`

Produces `BusinessModelAnalysis`, whose two required fields are `model_type` (one of 10 `BusinessModelType` values) and `revenue_mechanism`.

`one_time_sale`, `subscription`, `usage_based`, `freemium`, `marketplace_fee`, `service_retainer`, `ad_supported`, `affiliate`, `licensing`, `hybrid`.

The remaining thirteen fields — `billing_period`, `churn_assumption`, `expected_conversion_basis`, `fee_provenance`, `lifetime_value`, `ltv_provenance`, `payment_processor`, `price_point`, `price_provenance`, `processor_fee_fixed`, `processor_fee_pct`, `evidence_ids`, `weaknesses` — are optional, and **no business model is invented when there is no evidence for one**. With no admissible evidence the engine leaves `business_model` unset rather than defaulting to `subscription` because that is the common case.

Every derived money figure carries its own provenance field (`price_provenance`, `fee_provenance`, `ltv_provenance`), so a lifetime value can be read as an estimate without the reader having to trace how it was produced.

## 7. `DistributionAnalyser`

Produces `DistributionAssessment`: `channels`, `data_gaps`, `estimated_time_to_first_customer`, `platform_dependency_risk`, `reachable_without_paid_ads`, `reasons`, `verdict`.

`DistributionChannel` requires `channel` and carries `kind`, `startup_cost`, `recurring_cost`, `cost_provenance`, `feasible_without_ad_spend`, `platform_controlled`, `dependency_risk`, `time_to_first_customer`, `evidence_ids`, `notes`.

Two questions matter more than the channel list itself, and both are answered with a boolean that defaults pessimistically:

* **`reachable_without_paid_ads`** — can a customer be reached at all without spending money on acquisition? In P-03, where spending is prohibited (§26), a channel that requires ad spend is not merely expensive, it is **unusable**, and the assessment must say so.
* **`platform_controlled` / `platform_dependency_risk`** — how much of the channel's existence depends on a third party's continued permission. A marketplace listing is fast and cheap and can be removed without notice.

`feasible_without_ad_spend` is recorded per channel so the aggregate can be audited channel by channel rather than taken on trust.
