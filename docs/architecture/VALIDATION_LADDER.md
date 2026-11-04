# Validation Ladder (P-03)

Covers `backend/app/opportunities/validation.py` — §18.

## 1. What validation level means

A validation level answers one question: **what has actually been demonstrated about this opportunity?** Not how attractive it looks, not how well evidenced the analysis is — what real-world test has been passed.

`ValidationLevel` is an `IntEnum` with six members:

| Member | Value |
|---|---|
| `LEVEL_0_IDEA` | 0 |
| `LEVEL_1_PROBLEM_EVIDENCE` | 1 |
| `LEVEL_2_DEMAND_EVIDENCE` | 2 |
| `LEVEL_3_COMMERCIAL_EVIDENCE` | 3 |
| `LEVEL_4_WILLINGNESS_TO_PAY` | 4 |
| `LEVEL_5_ACTUAL_REVENUE` | 5 |

`LEVEL_REQUIREMENTS` states, per level, what must be true to claim it.

## 2. The walk

`ValidationEngine.determine(evidence, *, declared_inputs=())` → `ValidationAssessment`.

It walks **0 → 5 and breaks at the first unsatisfied rung.** There is no path that reaches level 4 without level 3 being satisfied first, and no amount of level-5-style input compensates for a missing level-2 observation. This is the single most important property of the module: the ladder is cumulative, and skipping a rung is structurally impossible rather than merely discouraged.

`ValidationAssessment`: `level`, `assessed_at`, `evidence_ids`, `satisfied_inputs`, `rejected_inputs`, `next_level`, `next_level_requirement`, `blocking_prohibition`.

When the walk stops at rung *n*, `next_level` names rung *n+1* and `next_level_requirement` states in words what is missing. **A level-5 claim resting on no evidence therefore cannot pass silently** — it comes back as `level == 0` with the gap named. The assessment reports the unmet requirement rather than recording a rejection of the declared input, because the rung was never reached.

## 3. Admissible evidence per level

`MIN_ADMISSIBLE_PER_LEVEL` — how many records from `ADMISSIBLE_CLASSIFICATIONS` each rung needs:

| Level | Minimum admissible records |
|---|---|
| 0 | 0 |
| 1 | 1 |
| 2 | 1 |
| 3 | **2** |
| 4 | 1 |
| 5 | 1 |

Level 3 requires two, and the rest require one. **This table is a design choice**, listed for owner ratification. The reasoning: level 3 is the first rung that makes a *commercial* claim (that a price and a cost structure exist in the world), and a single record cannot distinguish a real market price from one vendor's listing. Levels 4 and 5 rest on transaction records, which are self-authenticating in a way a price observation is not.

Only admissible classifications count — `verified`, `corroborated`, `supporting`, `tentative`. Contradicted and outdated records are in the store but contribute nothing here.

## 4. Which evidence types can satisfy which rung

`LEVEL_EVIDENCE_TYPES` restricts each rung to the observation types that could possibly demonstrate it:

| Level | Permitted evidence types |
|---|---|
| 0 | *(none required)* |
| 1 | `forum_post`, `marketplace_review`, `competitor_review`, `news_item`, `owner_statement` |
| 2 | `search_volume`, `keyword_trend`, `marketplace_listing`, `official_statistic`, `social_signal` |
| 3 | `competitor_pricing`, `competitor_feature_set`, `vendor_price_quote` |
| 4 | `transaction_record` |
| 5 | `transaction_record` |

A `search_volume` observation cannot establish that a problem matters, and a `forum_post` cannot size a market. Levels 4 and 5 admit **only** `transaction_record`, because willingness to pay and actual revenue are claims about money having moved, and nothing else observes that.

## 5. Declared inputs

`declared_inputs` are strings naming real-world validation the owner has performed. Two allowlists govern the top rungs.

`PERMITTED_LEVEL_4_INPUTS` (6) — evidence of willingness to pay:

`paid_preorder`, `paid_pilot`, `signed_letter_of_intent_with_deposit`, `completed_paid_engagement`, `verified_customer_payment`, `refundable_deposit_collected`

`PERMITTED_LEVEL_5_INPUTS` (3) — evidence of actual revenue:

`settled_payment_received`, `verified_bank_or_processor_receipt`, `revenue_recognised_from_delivered_sale`

Anything outside these lists is refused and recorded in `rejected_inputs`. **Both allowlists are design choices**, listed for owner ratification — §18 names the levels but not the exact input vocabulary.

### Prohibited inputs

`LEVEL_4_PROHIBITED_INPUTS` (7) may never establish willingness to pay:

`ai_persona_response`, `competitor_existence`, `hypothetical_survey`, `likes`, `model_generated_willingness_to_pay`, `search_volume`, `social_views`

`LEVEL_5_PROHIBITED_INPUTS` (5) may never establish actual revenue:

`forecast`, `generated_invoice`, `simulated_transaction`, `unpaid_order`, `unverified_screenshot`

Every one of these is something a system could plausibly produce on its own and then treat as validation. An AI persona saying it would buy is not a customer. A forecast is not a receipt. A generated invoice is not a settled payment. Naming them explicitly is what stops the ladder from being climbed with fabricated rungs.

A prohibited input sets `blocking_prohibition`, which is a stronger outcome than a mere rejection: the assessment records that someone attempted to validate with an input that may never count, not only that the input did not count this time.

## 6. The phase ceiling

**In P-03 no opportunity can reach level 4 or level 5.** Both rungs require a `transaction_record`, and §26 prohibits the system from collecting payment, placing an order or transferring funds. There is no permitted action that could produce one.

This is not a gap to be closed by inference. It is the correct state: the system may not spend money, so it may not observe money being spent on the owner's behalf, so it may not claim that anyone has paid.

The configuration key `opportunity_minimum_validation_level` defaults to **3**. A setting of 4 or 5 would make recommendation permanently unreachable in this phase, and `factory.py` records a startup note when the minimum is set to 5 so the owner is told rather than left wondering why nothing is ever recommended.

Consequently the realistic best outcome in P-03 is `promising_needs_validation` — an attractive, well-evidenced opportunity that has not been commercially validated, with the exact missing rung named in the report.
