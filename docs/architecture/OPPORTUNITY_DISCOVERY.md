# Opportunity Discovery (P-03)

Covers `backend/app/opportunities/discovery.py` — §7 and §8 of the phase brief.

## 1. The input contract

`DiscoveryContext` is the only thing the discovery engine reads. It carries no credentials, no host names and no network configuration, so discovery cannot cause egress by construction.

| Field | Type | Purpose |
|---|---|---|
| `owner_capabilities` | sequence of str | What the owner says they can do |
| `budget` | `BudgetConstraint \| None` | The owner's stated capital. Read-only downstream |
| `jurisdictions` | sequence of str | Where the owner may operate |
| `stated_problems` | sequence of str | Problems the owner has observed first hand |
| `stated_trends` | sequence of str | Trends the owner has observed |
| `preferred_categories` | sequence of `BusinessCategory` | Narrows generation; never overrides the compliance screen |
| `competitor_gaps` | sequence of str | Gaps the owner has identified in existing offerings |
| `competitor_complaints` | sequence of str | Complaints the owner has observed about competitors |
| `evidence` | sequence of `SourceEvidence` | Admissible evidence gathered by the research layer |
| `existing_titles` | sequence of str | Titles already in the system, for duplicate suppression |
| `max_candidates_per_method` | int, default `5` | Hard cap on output per method |

`context.admissible_evidence()` returns only evidence whose classification is in `ADMISSIBLE_CLASSIFICATIONS` — `verified`, `corroborated`, `supporting`, `tentative`. Contradicted and outdated records are excluded, so a superseded observation cannot seed a candidate.

## 2. The six generation methods

`DiscoveryEngine.generate(context)` runs all six and reports each one separately.

| `DiscoveryMethod` | Engine method | Input it needs | Produces with no evidence? |
|---|---|---|---|
| `customer_problem` | `from_customer_problems` | admissible problem evidence | No |
| `demand_driven` | `from_demand_signals` | admissible demand evidence | No |
| `competitor_gap` | `from_competitor_gaps` | `competitor_gaps` / `competitor_complaints` | No |
| `emerging_trend` | `from_trends` | `stated_trends` | No |
| `skill_capability` | `from_capabilities` | `owner_capabilities` | No |
| `budget_driven` | `from_budget_band` | `budget` | **Yes** |

Only `budget_driven` can produce candidates with no evidence at all, because it derives from the owner's own stated capital rather than from any observation about a market. That is why a context carrying only a budget yields candidates while the five evidence-dependent methods stay empty.

**Budget-driven candidates assert affordability only.** They carry no demand claim, no market size and no competitive assessment, and they start at validation level 0. They are a starting point for research, not a recommendation.

## 3. Budget archetypes

`BUDGET_ARCHETYPES` maps a `BudgetBand` to a fixed tuple of `(title, category, rationale)`. The bands come from `BAND_UPPER_BOUNDS`, which is **half-open `[lower, upper)`**:

| Band | Upper bound | Archetype count |
|---|---|---|
| `under_10` | 10 | 2 |
| `10_to_50` | 50 | 3 |
| `50_to_100` | 100 | 3 |
| `100_to_500` | 500 | 3 |
| `500_to_1000` | 1000 | 3 |
| `over_1000` | unbounded | 3 |
| `custom` | n/a | 0 |

The half-open partition is why exactly 50 falls in `50_to_100` and not `10_to_50`. `custom` deliberately has no archetypes: an owner-set band is a statement about their own number, not a category the system may guess at.

Every archetype rationale names what the band actually covers — hosting, a domain, a payment processor, working capital — so the owner can check the claim against their own costs rather than accept it.

## 4. Duplicate suppression

`_dedupe(raw, existing_titles)` collapses candidates that differ only in surface form. Titles are compared through `normalise_title(title)`, and anything already present in `existing_titles` is suppressed too, so re-running discovery over the same context does not accumulate near-identical candidates.

Suppressed candidates are **counted and reported**, not silently dropped. `DiscoveryReport.duplicates_suppressed` is the number removed. A report that hid this would make a re-run look like fresh discovery.

## 5. The output contract

`DiscoveryReport`:

| Field | Meaning |
|---|---|
| `candidates` | The kept candidates |
| `duplicates_suppressed` | How many were collapsed |
| `empty_methods` | Methods that produced nothing |
| `inputs_available` | Which context inputs were actually present |
| `notes` | Plain-language explanation of every gap |
| `per_method` | Kept count per method |

Two invariants make the report non-vacuous:

1. **`per_method` is counted after deduplication**, so it always sums to `len(candidates)`. Counting what was generated would make the report describe work it then threw away.
2. **`notes` explains every empty method.** A context with no inputs at all yields zero candidates and six entries in `empty_methods`, with a note saying why. Discovery never returns an empty list without saying what was missing.

## 6. What discovery deliberately refuses

* It does not search the web. Discovery reads the context; acquisition is a separate stage behind [RESEARCH_SOURCE_ACCESS.md](RESEARCH_SOURCE_ACCESS.md).
* It does not estimate market size. That is `MarketAnalyser`, and it requires evidence.
* It does not score or rank. Candidates leave discovery unscored; `OpportunityScorer` runs later.
* It does not screen for compliance. That happens in `OpportunityEngine.screen` immediately after `open`, so a prohibited candidate is blocked **before** any acquisition stage runs.
* `OpportunityCandidate.generated_by` is a `Literal['deterministic_rule', 'owner_supplied', 'model']` and every archetype candidate is `deterministic_rule`. No candidate in this phase is attributed to a model, because no model produced one.
