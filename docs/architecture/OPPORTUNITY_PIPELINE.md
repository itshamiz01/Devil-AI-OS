# Opportunity Pipeline Architecture (P-03)

Status labels used throughout: **Implemented** (code exists and is tested), **Partially implemented**, **Planned** (designed, not built), **Not supported**, **Requires future phase**.

## 1. What this layer is

The Opportunity Pipeline sits on top of the P-02 Intelligence Engine. It takes what the owner has said about their capabilities, budget, jurisdiction and problems, and produces **ranked, evidence-backed business opportunities** — or an explicit statement that there is not enough evidence to produce any.

It does not buy anything, register anything, sign anything or spend anything. Phase 3 forbids all commercial commitment outright (§26); that prohibition is structural rather than configurable, and is recorded in [ADR-0020](../decisions/ADR-0020-NO-SPENDING-SURFACE.md).

It also does not invent market data. Where no admissible evidence exists, the pipeline says so in the exact section that would otherwise have carried a figure. That rule governs every module described below and is recorded in [ADR-0018](../decisions/ADR-0018-NO-INVENTED-MARKET-DATA.md).

> **Environment caveat that shapes this whole phase.** No live market source is reachable from this build environment. Every permitted host is a package registry or GitHub. The source access probe that established this is at [`docs/reports/P03_SOURCE_ACCESS_PROBE.txt`](../reports/P03_SOURCE_ACCESS_PROBE.txt). Consequently the default source catalog ships **empty** and the research egress allowlist defaults to **deny all**. This is not a stub — it is the honest configuration for an environment where acquiring real evidence is impossible. See [RESEARCH_SOURCE_ACCESS.md](RESEARCH_SOURCE_ACCESS.md).

## 2. Module map

All modules live in `backend/app/opportunities/`. The package is deliberately **flat** rather than the nested tree sketched in §4 of the phase brief; the mapping between the two is recorded in the module docstring of `__init__.py` and in [ADR-0019](../decisions/ADR-0019-FLAT-OPPORTUNITY-PACKAGE.md).

| Module | Lines | Responsibility | Spec | Status |
|---|---|---|---|---|
| `schemas.py` | 2091 | Enums, Pydantic contracts (`extra="forbid"`), the state machine, weights, budget bands | §6, §7, §9, §13, §16, §17, §18 | Implemented |
| `sources.py` | 666 | `SourceDescriptor`, `SourceRegistry`, `NetworkPolicy`, HTTP/mock/unreachable adapters, refusal taxonomy | §12 | Implemented (no live host reachable) |
| `evidence.py` | 541 | `SourceEvidence` store, corroboration, contradiction, staleness, quality statistics, `EvidenceExtractor` | §10, §11 | Implemented |
| `discovery.py` | 553 | `DiscoveryContext`, six generation methods, duplicate suppression, budget archetypes | §7, §8 | Implemented |
| `analysis.py` | 558 | `MarketAnalyser`, `CompetitorAnalyser`, `BusinessModelAnalyser`, `DistributionAnalyser`, reliability→provenance mapping | §9 | Implemented |
| `commercial.py` | 415 | `CostStructure` arithmetic, three scenarios, break-even, budget compatibility | §13 | Implemented |
| `risk.py` | 491 | `RiskEngine`, 13 prohibited categories, 6 regulated categories, 8 platform policy rules, `ComplianceScreen` | §14, §15 | Implemented |
| `governance.py` | 321 | `GovernanceGate` with 12 permitted and 13 prohibited actions | §15, §26 | Implemented |
| `scoring.py` | 567 | 10 weighted dimensions summing to 100, coverage, hard rejections, final classification | §16, §17 | Implemented |
| `validation.py` | 278 | The 0–5 validation ladder, admissible-evidence counts, permitted/prohibited inputs | §18 | Implemented |
| `lifecycle.py` | 241 | `OpportunityLifecycle`, transition recording, history entries, credential redaction | §17 | Implemented |
| `research.py` | 327 | 13-stage workflow, `ResearchScheduler`, `ResearchTaskSpec`, halt reasons | §22, §24 | Implemented (caller-timed only) |
| `reports.py` | 610 | Nine report sections, always all present, markdown rendering, test-data labelling | §19, §20, §21 | Implemented |
| `engine.py` | 582 | `OpportunityEngine` — the facade the API talks to; `OpportunityRecord`; crash recovery | §22 | Implemented |
| `repository.py` | 1094 | Persistence to the twelve P-03 tables | §23 | Implemented |
| `factory.py` | 190 | `build_opportunities` composition root, `OpportunityServices`, startup notes | §22 | Implemented |
| `__init__.py` | 218 | 124 re-exports, the flat↔nested package mapping | §4 | Implemented |

`scripts/audit_p03_persistence.py` statically checks that every ORM attribute `repository.py` touches actually exists and that no required field goes unsupplied. It exits non-zero on mismatch and is part of the commit gate.

## 3. Pipeline lifecycle

```
owner context (capabilities, budget, jurisdictions, stated problems/trends)
  -> DiscoveryEngine.generate        six methods; evidence-dependent methods stay
                                     empty with a note when there is no evidence
  -> duplicate suppression           normalise_title + existing_titles
  -> OpportunityEngine.open          candidate -> Opportunity at state DISCOVERED
  -> ComplianceScreen.scan_candidate prohibited category? -> blocked_by_compliance,
                                     workflow halts BEFORE any acquisition stage
  -> budget screening                unaffordable? -> INCOMPATIBLE_WITH_CONSTRAINTS;
                                     the owner's capital is never modified to fit
  -> SourceRegistry.fetch_many       every unpermitted/unregistered source produces a
                                     SourceRefusal, never a fabricated success
  -> EvidenceStore                   classify, corroborate, contradict, age out
  -> MarketAnalyser / CompetitorAnalyser / BusinessModelAnalyser / DistributionAnalyser
  -> CommercialFeasibilityEngine     costs, three scenarios, break-even, budget fit
  -> RiskEngine                      findings, highest severity, blocked verdict
  -> OpportunityScorer               10 dimensions, coverage, hard rejections,
                                     final classification, recommendable
  -> ValidationEngine.determine      walk 0->5, break at the first unsatisfied rung
  -> ReportGenerator                 all nine sections, always
  -> persist + publish events
```

Two exits happen before any research is attempted: **compliance** and **affordability**. Both are deliberate. A prohibited opportunity must never reach an acquisition stage, because acquiring evidence for something the system may not pursue is itself a step toward pursuing it.

## 4. The refusal-first contract

Every acquisition path returns a `FetchResult` carrying either `content` or a `refusal` — never both, never neither. The twelve `RefusalCategory` values are:

`not_configured`, `not_authorized`, `host_not_permitted`, `network_unreachable`, `timeout`, `rate_limited`, `authentication_failed`, `policy_forbidden`, `invalid_request`, `unsupported_operation`, `response_too_large`, `malformed_response`

A refusal is a **finding**, not an error. It is summarised into the report's evidence section so the owner can see exactly which sources were tried and why each declined. This is why a research sweep that reaches no source **completes** rather than fails — failing would make the task manager retry an outcome that is already correct. See [ADR-0021](../decisions/ADR-0021-RESEARCH-HANDLER-BACKEND-BINDING.md).

## 5. What this layer explicitly does not do

| Absent capability | Why | Where it returns |
|---|---|---|
| Buying a domain, subscription, dataset or ad | §26 prohibits all commercial commitment | No endpoint, no permission code, no config key exists |
| Registering a business or signing a contract | §26 | `PROHIBITED_REGISTER_BUSINESS`, `PROHIBITED_SIGN_CONTRACT` |
| Collecting or transferring funds | §26 | `PROHIBITED_COLLECT_PAYMENT`, `PROHIBITED_TRANSFER_FUNDS` |
| Deciding *when* to research autonomously | §24 defers scheduling to P-12 | `scheduler.autonomous_scheduling == False` |
| Reaching any live market source | Environment blocks all egress | Empty catalog, deny-all allowlist |
| Modifying the owner's stated budget to make an opportunity fit | The budget is the owner's constraint, not a variable | `budget_was_modified` is a literal `False` |

## 6. Persistence

Twelve tables, added by revision `5953caf8f23e` and extended by `72ee9705e18f`:

`opportunity_candidates`, `opportunities`, `opportunity_history`, `research_sources`, `research_sweeps`, `source_evidence`, `market_analyses`, `competitors`, `commercial_analyses`, `risk_findings`, `opportunity_scores`, `opportunity_reports`

Conventions inherited from P-01/P-02 and kept deliberately:

* `String(36)` primary keys generated by `new_id()`.
* `TimestampMixin` for `created_at` / `updated_at`, using `utcnow()`.
* **Monetary and decimal values are stored as `String(32)` text.** SQLite has no decimal type; a float round trip would silently corrupt a price or a margin. Recorded in [ADR-0022](../decisions/ADR-0022-MONETARY-VALUES-AS-DECIMAL-TEXT.md).
* Assessment-level summaries (`business_model`, `distribution`, `competitor_assessment`, `risk_assessment`) are stored as JSON **on the opportunity row**, independently of their child rows. Storing only the children loses the parent verdict: zero risk findings does not mean "nothing was blocked".
* `research_sources` has **no credential column**. A source descriptor may declare that it needs an `api_key`, but the key itself never enters this table. See [RESEARCH_SOURCE_ACCESS.md](RESEARCH_SOURCE_ACCESS.md).
* `OpportunityHistory.metadata_` maps to a column named `metadata`, because `metadata` is reserved on the SQLAlchemy declarative base.

## 7. HTTP surface

Fifteen paths, seventeen operations, all under `/api/v1/opportunities`. Full machine-readable contract: [`shared/openapi-p03.json`](../../shared/openapi-p03.json) (53 paths / 58 operations across the whole API). See [API_REFERENCE.md](API_REFERENCE.md).

Four permission codes gate them: `opportunities.read`, `opportunities.research`, `opportunities.manage`, `opportunities.sources`. All four go to the owner. **SYSTEM gets none of them**, so no internal component can drive the pipeline without acting as the owner. There is deliberately no permission code for spending, because there is no spending.

## 8. Related documents

* [OPPORTUNITY_DISCOVERY.md](OPPORTUNITY_DISCOVERY.md) — candidate generation
* [OPPORTUNITY_EVIDENCE_MODEL.md](OPPORTUNITY_EVIDENCE_MODEL.md) — evidence and provenance
* [RESEARCH_SOURCE_ACCESS.md](RESEARCH_SOURCE_ACCESS.md) — sources, network policy, refusals
* [MARKET_AND_COMPETITOR_ANALYSIS.md](MARKET_AND_COMPETITOR_ANALYSIS.md) — sizing and competition
* [COMMERCIAL_FEASIBILITY.md](COMMERCIAL_FEASIBILITY.md) — costs, scenarios, break-even
* [OPPORTUNITY_RISK_AND_GOVERNANCE.md](OPPORTUNITY_RISK_AND_GOVERNANCE.md) — risk engine and gate
* [OPPORTUNITY_SCORING.md](OPPORTUNITY_SCORING.md) — weights and classification
* [VALIDATION_LADDER.md](VALIDATION_LADDER.md) — levels 0–5
* [OPPORTUNITY_LIFECYCLE_AND_REPORTING.md](OPPORTUNITY_LIFECYCLE_AND_REPORTING.md) — states and reports
* [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md) — the nine P-03 settings
