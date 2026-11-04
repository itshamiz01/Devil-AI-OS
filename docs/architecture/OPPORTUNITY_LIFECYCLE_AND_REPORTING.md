# Opportunity Lifecycle and Reporting (P-03)

Covers `backend/app/opportunities/lifecycle.py` — §17 — and `reports.py` — §19, §20 and §21.

## 1. The state machine

`OpportunityState` has fifteen members. `OPPORTUNITY_TRANSITIONS` defines the permitted edges:

| From | To |
|---|---|
| `discovered` | `initial_screening`, `duplicate`, `archived` |
| `initial_screening` | `researching`, `needs_more_evidence`, `rejected`, `blocked_by_compliance`, `duplicate`, `archived` |
| `researching` | `evidence_review`, `needs_more_evidence`, `rejected`, `blocked_by_compliance`, `outdated`, `archived` |
| `evidence_review` | `commercial_analysis`, `researching`, `needs_more_evidence`, `rejected`, `blocked_by_compliance`, `archived` |
| `commercial_analysis` | `validation_pending`, `needs_more_evidence`, `rejected`, `incompatible`, `blocked_by_compliance`, `archived` |
| `validation_pending` | `validated`, `needs_more_evidence`, `rejected`, `incompatible`, `blocked_by_compliance`, `archived` |
| `validated` | `recommended`, `rejected`, `incompatible`, `blocked_by_compliance`, `outdated`, `archived` |
| `recommended` | `outdated`, `archived` |
| `needs_more_evidence` | `researching`, `rejected`, `outdated`, `archived` |
| `outdated` | `researching`, `archived` |
| `rejected` | `archived` |
| `incompatible` | `archived` |
| `blocked_by_compliance` | `archived` |
| `duplicate` | `archived` |
| `archived` | *(nothing)* |

Three properties are worth stating because they are easy to assume otherwise:

* **`discovered` cannot go straight to `researching`.** Screening is mandatory. An opportunity that skips `initial_screening` has never been checked against the prohibited categories.
* **`TERMINAL_STATES`** = `archived`, `blocked_by_compliance`, `duplicate`, `incompatible`, `recommended`, `rejected`. Terminal states may still be **archived** — that is a records action, not a resumption — but none of them can return to an active state. `recommended` and `outdated` are the exceptions to full stasis: a recommended opportunity can go stale, and an outdated one can be re-researched.
* **`archived` is the true end of the line**, with no outgoing edges at all.

An illegal transition raises `OpportunityTransitionError`, whose message names the attempted edge and lists what *was* permitted:

```
illegal opportunity transition discovered -> researching;
permitted: archived, duplicate, initial_screening
```

At the HTTP boundary this becomes a **409 Conflict**, never a 500. An unhandled `ValueError` from a domain state machine surfacing as a server error would tell the client the system broke, when what actually happened is that the request was invalid.

## 2. `OpportunityLifecycle`

| Method | Behaviour |
|---|---|
| `open_opportunity(candidate, *, budget=None, actor='system')` | Candidate → `Opportunity` at `discovered`, plus its first history entry |
| `record(opportunity, target, *, reason, actor='system', metadata=None)` | Returns `(moved_opportunity, HistoryEntry)` |
| `screen(...)` / `apply_screening(...)` | Compliance and budget screening |
| `history(opportunity_id)` | The recorded entries |
| `can_transition` / `permitted_next` / `is_terminal` / `snapshot` | Queries |

**`record` never mutates.** It returns a new `Opportunity` and leaves the original at its old state, so a caller holding a reference cannot be surprised by a transition that happened elsewhere. This is tested directly.

`reason` is required and may not be empty — at the HTTP boundary an empty reason is a **422**. A transition with no recorded reason is unauditable.

`HistoryEntry`: `entry_id`, `opportunity_id`, `from_state`, `to_state`, `reason`, `actor`, `recorded_at`, `metadata`. Both states are recorded, so a history reads as a sequence of edges rather than a list of destinations.

### History entries refuse credential text

A `HistoryEntry` whose `reason` or `metadata` contains credential-shaped text is rejected. The tested case is a reason reading `used api_key=sk-secret-123 to fetch`. A history table is a place operators read and paste from; it must not become a credential store by accident. This complements the structural rule that `SourceDescriptor` and the `research_sources` table have no credential column at all.

`OpportunityHistory.metadata_` maps to a database column named `metadata`, because `metadata` is reserved on the SQLAlchemy declarative base.

## 3. `OpportunityReport`

| Field | Meaning |
|---|---|
| `report_id`, `opportunity_id`, `title`, `generated_at` | Identity |
| `sections` | All nine, always |
| `headline_metrics` | The summary numbers |
| `score`, `final_classification`, `validation` | The verdicts |
| `evidence_index` | Every record cited, by id |
| `refusals` | A `tuple[dict, ...]` of what was tried and declined |
| `assumptions` | What was assumed rather than observed |
| `is_test_data` | **Defaults to `True`** |
| `test_data_notice` | The label that goes with it |

## 4. The nine sections

`ReportSection` values carry a **capital** letter prefix:

| Value | Section |
|---|---|
| `A_executive_summary` | Executive summary |
| `B_opportunity_description` | What the opportunity is |
| `C_market_analysis` | Market sizing, demand, problem importance |
| `D_competitive_analysis` | Competitors, saturation, differentiation |
| `E_business_model` | Model type and revenue mechanism |
| `F_commercial_feasibility` | Costs, scenarios, break-even, budget fit |
| `G_distribution_and_acquisition` | Channels and how a customer is reached |
| `H_risk_and_compliance` | Findings, severity, prohibited-category status |
| `I_evidence_and_validation` | The evidence base, its quality, refusals, validation level |

`ReportGenerator` exposes `generate(...)` plus one method per section (`section_a` … `section_i`) and a `to_markdown(report)` **static** method.

**All nine sections are always present.** A section with no data still renders, saying what could not be determined and why. Omitting a section would leave the reader unable to distinguish "we found nothing" from "we did not look", which is precisely the distinction this phase exists to preserve.

`NO_EVIDENCE_STATEMENT` is the fallback text:

> *"Insufficient verified evidence. No admissible evidence was obtained for this section, so nothing is asserted here."*

It is used **only when the section's assessment object is `None`**. Where an assessment exists, the section renders the real assessment — including its own honest verdict. So with no evidence at all, section C renders a genuine `MarketAssessment` saying the verdict is `insufficient data`, that there is `no admissible demand evidence`, and that the market `could not be sized`. Only a section with no assessment object (section F, before commercial analysis has run) falls back to the generic statement. This distinction was found by a test that initially asserted the generic string everywhere and was wrong.

## 5. Test-data labelling

`is_test_data` **defaults to `True`**, and `TEST_DATA_NOTICE` reads:

> *"SYNTHETIC TEST DATA - NOT REAL MARKET RESEARCH. Every figure, listing, price and observation in this report comes from mock fixtures built to exercise the pipeline. None of it was acquired from a live source and none of it describes a real market."*

The default is the safe direction. Producing a report requires an explicit `is_test_data=False` to claim the contents are real, and in this phase nothing can legitimately make that claim. A sample report is at [`docs/reports/P03_SAMPLE_OPPORTUNITY_REPORT.md`](../reports/P03_SAMPLE_OPPORTUNITY_REPORT.md).

## 6. `OpportunityEngine` and `OpportunityRecord`

`OpportunityEngine` is the facade the API talks to: `discover`, `open`, `screen`, `research`, `analyse`, `advance`, `report`, `rank`, `status`, `restore`, `get`. It also exposes `.lifecycle`, `.evidence`, `.scorer`, `.compliance_screen` and `.scheduler`.

`get(opportunity_id)` raises `KeyError` on an unknown id, which the route layer converts to a **404**.

`OpportunityRecord` bundles one opportunity with everything computed about it: `opportunity`, `market`, `competitors`, `business_model`, `commercial`, `distribution`, `risk`, `outcome`, `workflow`, `report`, `screening`. Constructing it needs only the opportunity; the rest are populated as the pipeline runs, so a record can be inspected at any point mid-flight.

`analyse(...)` takes the commercial inputs explicitly — `jurisdictions`, `platforms`, `costs`, `price_per_unit`, `price_provenance`, `base_units_monthly`, `units_provenance`, `competitor_gaps`, `differentiation_basis`, `channels`, `revenue_mechanism`, `declared_validation_inputs`, `stated_capabilities`, `required_capabilities`, `actor`. Nothing is inferred from nothing: the price and volume provenance are parameters, not defaults.

**Requesting a report before analysis returns 409** at the HTTP boundary. A report of an unanalysed opportunity would be nine sections of absence, and presenting that as a deliverable would be misleading.

## 7. Crash recovery

`engine.restore(opportunity)` reconstitutes in-memory state from persisted rows at startup. `factory.initialize(services)` reports `sources_loaded`, `sources_failed`, `opportunities_restored`, `opportunities_failed`.

**Recovery restores visibility only.** No research sweep is dispatched, nothing is re-scored and no state is advanced. An opportunity that was mid-workflow when the process died comes back at the state it was persisted in, and the owner decides what happens next. Auto-resuming research on boot would spend owner attention and network egress on work nobody asked to restart. Listed for owner ratification.
