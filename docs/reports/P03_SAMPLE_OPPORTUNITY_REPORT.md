# P-03 Sample Opportunity Report

> ## ⚠️ SYNTHETIC TEST DATA — NOT REAL MARKET RESEARCH
>
> **Every figure, listing, price and observation in this document is a mock fixture.**
> Nothing here was acquired from a live source. Nothing here describes a real market,
> a real product, a real competitor or a real price. No part of this document may be
> used as market research, and no number in it may be quoted as an observation.
>
> This file exists to demonstrate **what the reporting layer produces and how it
> labels its own uncertainty** — not to demonstrate a business opportunity.

## Why this file exists

§21 requires a sample opportunity report. Producing one honestly in this environment
means producing one from fixtures, because no live market source is reachable — see
[ADR-0018](../decisions/ADR-0018-NO-INVENTED-MARKET-DATA.md) and
[`P03_SOURCE_ACCESS_PROBE.txt`](P03_SOURCE_ACCESS_PROBE.txt).

`ReportGenerator.generate` therefore takes `is_test_data=True` **by default**, and
this report was generated with that default left in place. The notice at the top of
the rendered report is produced by the code, not added by hand.

## How it was generated

By running the real pipeline against three `SourceEvidence` fixtures. No module was
stubbed and no output was edited. The fixtures are:

| id | source_id | evidence_type | reliability | claim | value |
|---|---|---|---|---|---|
| `e1` | `mock-marketplace` | `marketplace_listing` | `plausible` | TEST FIXTURE 42 listings observed for a monthly planning template | 42 count |
| `e2` | `mock-forum` | `forum_post` | `plausible` | TEST FIXTURE two threads describing the same scheduling problem | 2 threads |
| `e3` | `mock-pricing` | `competitor_pricing` | `plausible` | TEST FIXTURE competitor lists a comparable template at 19 USD | 19 USD |

All three are classification `supporting`, `trust_domain` `external`, and each carries
a distinct `independence_group` so that `EvidenceStore.corroborate` has something real
to consider. Every claim string is prefixed `TEST FIXTURE `, which is
`EvidenceExtractor.mock_claim_prefix` — the convention that makes fixture data
identifiable in any downstream output.

The pipeline calls, in order: `MarketAnalyser.analyse`, `CompetitorAnalyser.analyse`,
`BusinessModelAnalyser.derive`, `DistributionAnalyser.analyse`,
`CommercialFeasibilityEngine.assess`, `RiskEngine.assess`,
`ValidationEngine.determine`, `OpportunityScorer.score`,
`OpportunityLifecycle.open_opportunity`, `ReportGenerator.generate`,
`ReportGenerator.to_markdown`.

Two `SourceRefusal` fixtures were supplied to the report so that section I shows what
a refusal looks like when rendered: one `host_not_permitted` (the allowlist is empty by
default) and one `not_configured`.

## What the output demonstrates

| Observation | Value | Why it matters |
|---|---|---|
| Final classification | `not_recommended` | Attractiveness **2.9500** against `MIN_RECOMMEND_ATTRACTIVENESS = 3.0000`. The system declines to recommend on a near miss rather than rounding up |
| Coverage | **95.00%** | `strategic_fit` is the one unscored dimension, because no `stated_capabilities` were supplied. Coverage reports the gap instead of awarding a neutral score |
| Validation level | **2** | Three admissible records satisfy level 2 (`LEVEL_EVIDENCE_TYPES` demand types) but not level 3, which needs two commercial-evidence records |
| Market verdict | `demand_plausible` | Not `demand_demonstrated` — three `plausible`-reliability records cannot demonstrate demand |
| Problem importance | `trivial` | One weak problem record. The mapping is mechanical, not impressionistic |
| Competitors inspected | **1** | `inspected_count` counts only competitors actually inspected, not names mentioned |
| Commercial verdict | `viable`, affordable | 19 price against 0 variable cost, 29 recurring, 150 capital |
| Risk verdict | `acceptable`, not blocked, 1 finding | A finding is reported without blocking — risk and prohibition are different questions |
| Acquisition refusals | **2** | Rendered in section I as findings, not hidden |
| `budget_was_modified` | **no** | The owner's stated capital is never adjusted to make an opportunity fit |
| Sections | **9** | All present, always |

## A refusal the generator produced on the first run

The first attempt passed `units_provenance=Provenance.UNKNOWN` for the expected monthly
volume. The commercial engine **refused to complete**, and the report said so:

> `commercial feasibility could not be determined: commercial analysis could not be
> completed; unknown inputs: units_provenance`

That produced final classification `insufficient_evidence`, attractiveness `1.7000`,
coverage `70.00%`, and three unscored dimensions (`profit_potential`,
`budget_compatibility`, `strategic_fit`) — with the hard rejection naming the missing
input.

**This is the intended behaviour and is the reason the report is reproduced here with
`estimate` provenance rather than `unknown`.** A volume figure with no stated origin is
not accepted as an input to a financial projection. The system does not proceed on an
unstated number, does not substitute a default, and does not report a projection it
could not compute; it names the missing input and scores what it can.

## Reproducing it

```bash
cd backend
python -m pytest tests/test_opportunities_engine.py tests/test_opportunities_api.py -q
```

The two P-03 test modules exercise the same components over HTTP and directly. The
rendered report below is the verbatim output of `ReportGenerator.to_markdown`.

---

# Opportunity report: TEST FIXTURE monthly planning template for solo consultants

Report id: `rpt-c39824d98fc3`  
Opportunity id: `opp-38735ca59fac`  
Generated: 2026-11-03T22:53:38.569845+00:00  
Final classification: **NOT RECOMMENDED**

> SYNTHETIC TEST DATA - NOT REAL MARKET RESEARCH.
> Every figure, listing, price and observation in this report comes from mock fixtures built to exercise the pipeline.
> None of it was acquired from a live source and none of it describes a real market.

## Headline metrics

- **final classification:** not_recommended
- **lifecycle state:** discovered
- **attractiveness:** 2.9500
- **evidence quality:** 1.38
- **evidence coverage pct:** 95.00
- **validation level:** 2
- **evidence records:** 3
- **acquisition refusals:** 2
- **commercial verdict:** viable
- **risk verdict:** acceptable
- **market verdict:** demand_plausible
- **competitive verdict:** differentiation_required
- **distribution verdict:** plausible_path
- **budget was modified:** no

---

# A. Executive summary

**Opportunity:** TEST FIXTURE monthly planning template for solo consultants
**Category:** digital product
**Discovery method:** demand driven
**Lifecycle state:** discovered

**Final classification:** NOT RECOMMENDED
**Recommendable:** no
**Attractiveness (0-5, weighted):** 2.9500
**Evidence quality (0-5, reported separately):** 1.38
**Evidence coverage of the scoring dimensions:** 95.00%
**Validation level reached:** 2 (LEVEL_2_DEMAND_EVIDENCE)

**Reasoning:**
- attractiveness 2.9500 is below the 3.0000 recommendation threshold
- note: 1 dimension(s) unscored (strategic_fit); coverage 95.00%

---

# B. Opportunity description

**Title:** TEST FIXTURE monthly planning template for solo consultants
**Description:** TEST FIXTURE a downloadable monthly planning template aimed at solo consultants who track billable hours
**Business category:** digital product
**Discovery method:** demand driven
**Derived from:** not recorded
**Generated by:** deterministic_rule
**Target customer:** not established
**Problem addressed:** not established
**Proposed offering:** not established

**Owner budget constraint:**
- available capital: 150 USD
- band: 100_to_500
- stated by owner: yes

---

# C. Market analysis

**Verdict:** demand plausible
**Demand evidence level:** supporting
**Problem importance:** trivial - a single weakly classified problem observation

**Basis:**
- demand supported but not corroborated: TEST FIXTURE 42 listings observed for a monthly planning template

**Market sizing (TAM / SAM / SOM):**
- TAM: unknown - no admissible evidence carries a figure
- SAM: unknown - no admissible evidence carries a figure
- SOM: unknown - no admissible evidence carries a figure
- geography: US
- customer segments: not supplied

**Demand signals observed:**
- TEST FIXTURE 42 listings observed for a monthly planning template [42 count; provenance estimate; evidence e1]

**Data gaps:**
- TAM could not be sized: no admissible evidence record carries a TAM figure
- SAM could not be sized: no admissible evidence record carries a SAM figure
- SOM could not be sized: no admissible evidence record carries a SOM figure

---

# D. Competitive analysis

**Verdict:** differentiation required
**Market saturation:** sparse
**Competitors observed:** 1 (1 inspected)
**Observed price range:** 19 to 19

**Competitors:**
- TEST FIXTURE competitor lists a comparable template at 19 USD (19; provenance estimate; inspected yes)

**Gaps identified:**
- TEST FIXTURE no observed template targets a solo consultant's billable-hour schedule

**Differentiation available:** TEST FIXTURE narrower audience than the single observed competitor

**Basis:**
- 1 competitors observed; 1 gap(s) to differentiate on

---

# E. Business model

**Model type:** one time sale
**Revenue mechanism:** TEST FIXTURE direct sale of a downloadable template
**Billing period:** once
**Price point:** 19 USD (provenance: estimate)
**Payment processor fee:** unknown

**Model weaknesses:**
- the price point rests on an estimate rather than a quote

**Evidence:** e3

---

# F. Commercial feasibility

**Verdict:** viable
**Viable:** yes
**Affordable within the owner's stated budget:** yes

**Cost structure:**
- startup total: 0 USD
- recurring monthly total: 29 USD
- variable cost per unit: 0 USD
- cost lines: 2
- provenance breakdown: estimate=2

**Cost lines:**
- TEST FIXTURE storefront subscription: 29 USD (recurring, monthly, provenance estimate, assumption: TEST FIXTURE assumed entry-tier monthly storefront fee; not verified against any vendor price list)
- TEST FIXTURE template production: 0 USD (startup, once, provenance estimate, assumption: TEST FIXTURE assumed the owner's existing tools cover production; no cash outlay)

**Scenarios (only volume varies; costs and price are held constant):**

| scenario | volume factor | units | revenue | variable cost | gross profit | contribution margin | operating profit | net cash flow |
|---|---|---|---|---|---|---|---|---|
| conservative | 0.5 | 10.00 | 190.00 | 0.00 | 190.00 | 1.0000 | 161.00 | 161.00 |
| base | 1.0 | 20.00 | 380.00 | 0.00 | 380.00 | 1.0000 | 351.00 | 351.00 |
| optimistic | 1.75 | 35.00 | 665.00 | 0.00 | 665.00 | 1.0000 | 636.00 | 636.00 |

**Break-even:**
- contribution per unit: 19.00
- monthly break-even units: 2
- units to recover startup: 2
- months to recover startup: 1
- achievable: yes

**Budget compatibility:**
- owner's stated capital: 150 USD
- required startup: 0.00 USD
- required first-period cash: 29.00 USD
- verdict: compatible
- shortfall: 0 USD
- **the owner's budget was modified: no**

**Reasoning:**
- price and/or volume rest on estimates rather than quoted or verified figures
- break-even at 2 unit(s)/month, startup recovered in about 1 month(s), conservative operating profit 161.00 USD

**Assumptions:**
- unit price of 19 USD is an estimate, not a quoted or verified figure (basis: estimate, sensitivity: high)
- monthly volume of 20 units is an estimate, not observed demand (basis: estimate, sensitivity: high)

---

# G. Distribution and acquisition

**Verdict:** plausible path
**Reachable without paid advertising:** yes
**Platform dependency risk:** high

**Channels:**
- TEST FIXTURE existing marketplace storefront (marketplace, platform-controlled yes, dependency high, cost provenance estimate)

**Basis:**
- 1 channel(s) reachable without advertising spend: TEST FIXTURE existing marketplace storef

---

# H. Risk and compliance

**Verdict:** acceptable
**Blocked:** no
**Highest severity:** low
**Jurisdictions considered:** US

**Findings:**
- [LOW] (platform policy) platform 'mock-marketplace' has no policy rules modelled; its restrictions were not checked | mitigation: verify the platform's acceptable-use policy manually | platform: mock-marketplace

**Reasoning:**
- no prohibited category, regulated area or platform restriction matched for US

---

# I. Evidence and validation

**Validation level reached:** 2 - LEVEL_2_DEMAND_EVIDENCE
**What that level requires:** at least 1 admissible record of demand: search volume, keyword trend, marketplace listings, or an official statistic
**Next level:** 3 - LEVEL_3_COMMERCIAL_EVIDENCE
**What it would require:** at least 2 admissible records establishing that money changes hands in this market: competitor pricing and/or verified vendor cost quotes

**Inputs that satisfied the level:**
- level_1_problem_evidence_evidence:1
- level_2_demand_evidence_evidence:1

**Evidence records: 3**
- by classification: supporting=3

| id | type | classification | reliability | source | claim |
|---|---|---|---|---|---|
| e1 | marketplace_listing | supporting | plausible | mock-marketplace | TEST FIXTURE 42 listings observed for a monthly planning template |
| e2 | forum_post | supporting | plausible | mock-forum | TEST FIXTURE two threads describing the same scheduling problem |
| e3 | competitor_pricing | supporting | plausible | mock-pricing | TEST FIXTURE competitor lists a comparable template at 19 USD |

**Acquisition refusals: 2**

These are the sources that were asked and could not answer. They are listed because an absence of evidence is only interpretable when the reason for the absence is known.

| source | operation | category | detail |
|---|---|---|---|
| mock-marketplace | search | host_not_permitted | host is not on research_permitted_hosts; the allowlist is empty by default |
| mock-search-engine | search | not_configured | source is registered but its status is not_configured, so no operation is authorized |

**Scoring dimensions:**

| dimension | weight | score | scorable | justification / gap |
|---|---|---|---|---|
| verified_demand | 20 | 3 | yes | demand plausible but not demonstrated: demand supported but not corroborated: TEST FIXTURE 42 listings observe |
| problem_importance | 10 | 1 | yes | problem importance rated trivial: a single weakly classified problem observation |
| competitive_opportunity | 10 | 4 | yes | differentiation required: 1 competitors observed; 1 gap(s) to differentiate on |
| revenue_model_viability | 10 | 1 | yes | price provenance is estimate; discounted for 1 model weakness(es) |
| profit_potential | 15 | 5 | yes | viable at base volume; contribution margin 1.0000; profitable even at half the expected volume |
| budget_compatibility | 10 | 5 | yes | uses 19.3300% of stated capital |
| distribution_feasibility | 10 | 3 | yes | plausible path: 1 channel(s) reachable without advertising spend: TEST FIXTURE existing marketplace storef |
| operational_simplicity | 5 | 4 | yes | 2 cost line(s); high platform dependency |
| strategic_fit | 5 | 0 | NO | owner capabilities or required capabilities were not stated |
| evidence_quality | 5 | 1.38 | yes | 3 evidence record(s); 3 admissible; 0 contradicted; reliability-weighted mean 0.2750 |

- attractiveness (weighted, excludes evidence quality): 2.9500
- evidence quality (reported separately): 1.38
- coverage of the scoring dimensions: 95.00%
- unscored dimensions: strategic_fit

