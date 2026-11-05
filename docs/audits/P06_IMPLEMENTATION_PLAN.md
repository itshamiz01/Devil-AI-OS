# P-06 Business Creation Engine — Implementation Plan

**Date:** 2026-11-05 · **Baseline:** `862bd70` (P-04 Stage 6, 838 tests passing)
**Companion:** [P06_PRE_IMPLEMENTATION_AUDIT.md](P06_PRE_IMPLEMENTATION_AUDIT.md)

This plan is written against the audit's findings, not against the brief alone. Where
the brief and the repository disagree, the repository wins and the disagreement is
recorded.

## 0. Resolved conflicts between brief and repository

| Brief says | Repository says | Resolution |
|---|---|---|
| §24 `backend/business_creation/…` | Convention is `backend/app/<subsystem>/`; §24 also says follow existing conventions | **`backend/app/business/`** |
| §25 `/api/businesses` | Uniformly `/api/v1/…`; §25 says adapt where equivalents exist | **`/api/v1/businesses`** |
| §23 create `business_approvals` if the central service cannot carry business references | `approvals.action` and `.resource` are free strings, `payload_hash` binds the payload, self-approval is already blocked, P-04 already opens approvals for agent grants | **Do not create it.** Reuse `ApprovalService` |
| §24 "do not put all functionality in one large service" | P-04's `app/agents/` is 11 focused modules | Same shape: one module per concern, thin `subsystem.py` |
| §26 frontend integration | No frontend directory exists | **Stage 11 blocked**, reported not skipped |
| §6 store "opportunity version" | `opportunities` has no version column | Store `opportunity_updated_at` + a content fingerprint; never invent a version number |

## 1. Proposed architecture

`backend/app/business/`, import-light `__init__.py` (P-04's circular-import lesson),
one module per concern:

| Module | Responsibility | Explicitly NOT |
|---|---|---|
| `schemas.py` | Vocabularies, lifecycle graph, template/product/asset models, views | Behaviour |
| `lifecycle.py` | The 18-state transition graph; rejects invalid transitions | Deciding *why* (callers own policy) |
| `registry.py` | Business identity, slugs, opportunity linkage, workspace path derivation | Creating directories (needs P-05) |
| `eligibility.py` | The §6 gate over P-03 records; six verdicts; structured refusals | Writing to `opportunities` |
| `templates.py` | Versioned business templates, validation gate, cloning | Executing anything |
| `blueprint.py` | Identity, customer definition, value proposition, positioning | Inventing market evidence |
| `assumptions.py` | The assumption register with five statuses and evidence links | Presenting assumptions as facts |
| `models.py` *(business models)* | The 15-component business model, pricing structure | Inventing competitor prices; arithmetic as financial truth |
| `products.py` | Product registry, PRD, MVP classification | Building the product |
| `assets.py` | Asset registry, versions, usage-rights metadata | Generating asset files (needs P-05) |
| `channels.py` | Channel evaluation and preparation states | Connecting or publishing (needs P-05 + approval) |
| `acquisition.py` | Acquisition strategy and campaign plans | Sending anything |
| `support.py` | Support, onboarding, refund and escalation procedures | Handling real customers (P-12) |
| `playbooks.py` | Versioned operating playbook | Claiming operations are running |
| `readiness.py` | The A–H launch-readiness evaluation; hard blockers override score | Certifying legal compliance |
| `orchestration.py` | Stage plans over `plans`/`plan_steps` and `AssignmentService` | A new agent or task framework |
| `evidence.py` | Links business decisions to `source_evidence` | Hashing content (needs P-05) |
| `financial.py` | The P-07 interface: structured estimates, always labelled | Accounting, revenue, profit, spending |
| `subsystem.py` | Assembly, degraded-mode notes, startup reconciliation | Policy |

Every module that needs an execution capability takes an injected adapter and, when
none is present, returns a typed `REQUIRES_P05` result. **No module may simulate
success.** That is the single rule that keeps this phase honest while P-05 is absent.

## 2. Business lifecycle

The 18 states of §19, as a validated graph in `lifecycle.py` following
`app/agents/lifecycle.py`:

```
PROPOSED → ELIGIBILITY_REVIEW → APPROVAL_PENDING → BLUEPRINTING → BLUEPRINT_READY
  → PRODUCT_PLANNING → IN_DEVELOPMENT → INTERNAL_TESTING → DISTRIBUTION_PREPARATION
  → LAUNCH_REVIEW → READY_FOR_LAUNCH → LAUNCH_APPROVAL_PENDING → LAUNCHING → OPERATIONAL
Overlays from any non-terminal state: PAUSED, BLOCKED, FAILED
PAUSED → the state it paused from · BLOCKED → the state it blocked from
Any state → ARCHIVED (terminal) · FAILED → ARCHIVED
```

Rules:

* Transitions are validated in backend code against a literal graph. **No
  transition may be requested by model output** (§19).
* `LAUNCH_APPROVAL_PENDING → LAUNCHING` requires a granted, unexpired approval whose
  requester is not the approver.
* `→ OPERATIONAL` requires a readiness result of `READY` or `READY_WITH_WARNINGS`
  *and* the launch approval. A website existing is not sufficient (§33 rule 23).
* Every transition writes a `business_lifecycle_events` row (`previous_status`,
  `new_status`, `reason`, `actor_type`, `actor_id`, `approval_reference`) and emits
  an event — following `opportunity_history` and `mission_history`.
* The §19 distinctions are enforced by *what each transition requires*, not by
  prose: `BLUEPRINT_READY` requires only a validated blueprint; `IN_DEVELOPMENT`
  requires an approved product spec; `INTERNAL_TESTING` requires recorded tests;
  `READY_FOR_LAUNCH` requires the readiness engine.

## 3. Business templates

Categories A–G of §7 as code-defined data in a `catalog.py`, reconciled at startup
into `business_templates` — the pattern P-04 Stage 5 proved for capabilities:
code-defined, reconciled, **no endpoint that can add or edit an entry**, because a
template that could be edited over HTTP could quietly change what every business of
that type requires.

Each template carries: category, description, required business information,
required agent roles, required capabilities (keys from the existing catalog),
product development stages, asset requirements, distribution requirements,
acquisition requirements, operational requirements, approval gates, resource
estimates and launch-readiness criteria.

Versioning follows `agent_template_versions`: a stored `configuration_json`, a
`validation_status` verdict, and the rule that **changing a template never modifies
an existing business** — a business pins `template_id` + `template_version`, exactly
as `agents` does.

Extensibility (§7's "support additional categories") is a code change plus a
reconciliation, not a runtime write.

## 4. Business model framework

The 15 components of §9 as a validated structure, plus the revenue-model vocabulary
(one-time, subscription, freemium, usage-based, licensing, productized service,
consulting, digital download, advertising-supported, marketplace commission, B2B
contract, hybrid).

Pricing is **structure, never invention**:

* Competitor prices are read from `competitor_records.price_points` with their
  `pricing_provenance` and `observed_at`, and are refused when provenance is absent
  or the observation is stale. §9's "do not invent competitor prices" is enforced by
  requiring a provenance reference, not by asking a model to be careful.
* Willingness-to-pay comes from `market_analyses.willingness_indicators` and is
  labelled with its `demand_evidence_level`.
* Every proposed price carries amount or range, currency, source, estimate-vs-
  verified, confidence, date and assumptions (§27).
* "Lower price is an advantage" is never inferred; it must be an assumption in the
  register with a validation method.

Financial boundary: `financial.py` emits the §27 input structure for P-07 and stops.
No accounting, no revenue recognition, no profit, no spending, no wallets (§36).

## 5. Product creation architecture

`products.py` owns the product registry, the PRD structure of §10.2 and MVP
classification (MUST/SHOULD/COULD/NOT IN MVP). All three are validated structured
data.

Development coordination reuses what exists:

1. Product spec approved → `orchestration.py` writes a `plan` with `plan_steps`
   carrying `depends_on`, `capability_id`, `expected_output` and `completion_criteria`.
2. Steps needing an agent go through `AgentFactory` (which may answer
   `ASSIGN_EXISTING`) and then `AssignmentService.assign`, so the nine assignment
   rules gate every business task — including rule 7's capability check and rule 8's
   no-escalation check.
3. Steps needing execution go to the P-05 adapter interface and return
   `REQUIRES_P05` today.
4. Test results are recorded as evidence and as `product_requirements.status`.

Software, content and service workflows (§11) are three stage lists in the template,
not three engines. Existing projects are never touched: P-06 has no filesystem
access, so §11's "never overwrite unrelated user projects" holds trivially today and
becomes a real control when P-05's workspace scoping lands.

## 6. Asset generation architecture

`assets.py` is a **registry with rights metadata**, not a generator. Every asset row
carries asset type, name, version, file reference, creation method, creator agent,
approval status, usage-rights status and timestamps.

What P-06 can do: record an asset *brief* (a logo brief, copy, a colour palette as
data, a typography specification as data, a page plan) and track its approval and
rights status. What it cannot do: produce image, document or screenshot files — no
image or document library is installed and §33 rule 25 forbids adding unnecessary
dependencies. An asset row whose `file_reference` points nowhere would be a lie, so
**`file_reference` stays null and `creation_method` says `brief_only`** until P-05's
filesystem adapter exists.

Copyright and originality (§12): sources are recorded, uncertain licensing is
flagged, unclear rights require review, and **no claim of copyright safety or
guaranteed originality is ever emitted** — the brief forbids it and nothing here can
verify it.

## 7. Website and distribution integration

**Website.** `WebsitePlanningService` produces the §13.2 plan (purpose, audience,
pages, navigation, content structure, primary conversion action, contact method,
legal pages required by the business model, accessibility and SEO requirements) as
validated data, and §13.3 page types as a vocabulary. Implementation (§13.4) and
verification (§13.5) are **blocked**: they need `adapters_fs`, `adapters_code` and a
browser, and the P-05 plan permanently disables the browser adapter as
`UNSUPPORTED_BY_ENVIRONMENT`. So §13.5's checks — pages load, links work, forms
behave, responsive layouts, images load — cannot be performed here at all, and must
be reported as unperformed rather than passed. The distinction §13.5 ends on is
enforced by state: `generated_locally` ≠ `deployed` ≠ `public`, and P-06 can only
ever reach the first, later.

Legal pages: content is generated as *templates requiring jurisdiction review*, and
never includes a company address, registration number, licence, certification or
testimonial (§13.3, §33 rules 10–11).

**Distribution.** `channels.py` implements the 11 preparation states of §14
(`DISCOVERED` … `ACTIVE`, plus `PAUSED`, `REJECTED`) and the evaluation dimensions.
States up to `READY_FOR_APPROVAL` are reachable today. `APPROVED` needs an owner
approval; `CONNECTED` and `ACTIVE` need P-05's API adapter **and** an approval, and
are refused until then. No account creation, no verification bypass, no OTP/MFA
circumvention, no credentials in prompts (§14) — and the level-3 catalog
prohibitions already make several of these ungrantable.

## 8. Operational readiness

`readiness.py` evaluates the eight dimensions A–H deterministically over recorded
rows, never over model opinion. Each check produces `{dimension, check, passed,
evidence_reference, requirement}`.

* **Hard blockers override any score** (§20). A blocker is a check whose failure is
  declared blocking in the template; the result is `BLOCKED` regardless of how many
  checks passed.
* Results: `READY`, `READY_WITH_WARNINGS`, `NOT_READY`, `BLOCKED`,
  `OWNER_REVIEW_REQUIRED`.
* A score is emitted **only** when the weighting is defined in the template, and the
  weighting is stored with the review so a later reader can see what produced it.
* Dimensions that depend on P-05 (product exists, website verified, channel
  connected) evaluate to `NOT_READY` with the requirement named, never to `READY` on
  absence of evidence.
* No claim of independently certified legal compliance (§20 G) and no invented
  profitability (§20 H).

Every review is versioned in `business_readiness_reviews` with its blockers,
warnings and evidence references.

## 9. Approval gates

Reuse `ApprovalService`; never a second approval system (§33 rule 20).

| Gate | Risk | Approver |
|---|---|---|
| Business creation from an eligible opportunity | `high` | Owner |
| Blueprint approval | `moderate` | Owner |
| Product spec approval before development | `moderate` | Owner |
| Asset with unclear usage rights | `high` | Owner |
| Any external publishing or channel connection | `critical` | Owner, and blocked until P-05 |
| Launch (`LAUNCH_APPROVAL_PENDING → LAUNCHING`) | `critical` | Owner |

Rules carried over from P-04 because they were learned there:

* **The requester is never the approver.** `ApprovalService.decide` already refuses
  `requester_id == approver_id` at high/critical risk, and only the owner holds
  `approvals.decide`. When P-06 opens an approval on behalf of a business, the
  requester must be a principal that is not the deciding owner — P-04 Stage 5 deadlocked
  exactly here (the L2 requester was the actor, so the approval could never be decided).
* An agent cannot approve its own critical deliverable (§21, §28.6).
* Approvals expire; an expired approval authorizes nothing (§29.3 test 14).
* `payload_hash` binds the approved payload, so an altered payload is rejected.

## 10. Database design

**Fourteen new tables**, additive, one hand-written revision:

`businesses`, `business_templates`, `business_template_versions`,
`business_blueprints`, `business_assumptions`, `business_products`,
`product_requirements`, `business_assets`, `business_channels`,
`business_campaigns`, `business_playbooks`, `business_readiness_reviews`,
`business_lifecycle_events`, `business_evidence`.

Not created: `business_approvals` (§0).

Field lists follow §23, with three deliberate deviations, each because the
repository already solves the problem better:

* `business_evidence` **links** to `source_evidence` rather than duplicating it —
  that table already carries reliability, trust domain, independence group,
  `supersedes`, `contradicts` and `stale_after_days`, which exceed §22's list.
  Duplicating it would create two evidence truths (§23: "do not duplicate
  information unnecessarily").
* `businesses` stores `opportunity_id`, `opportunity_updated_at` and
  `opportunity_fingerprint` instead of a nonexistent `opportunity_version`.
* Every CHECK, UNIQUE and FK is **named in `models.py`** (ADR-0024). P-04 Stage 6
  could not drop an unnamed UNIQUE and had to design around it; P-06 will not repeat
  that.

Existing tables: add a nullable FK from `agents.business_id` and
`agent_creation_requests.business_id` to `businesses.id`, **normalizing first** (any
value with no matching business becomes NULL) because a FK existing rows violate
fails partway through SQLite's non-transactional batch rebuild. Indexes on every
`business_id`, and on `businesses.lifecycle_status`.

## 11. API design

Under `/api/v1`, following the brief's list with the prefix adapted. Roughly 45
operations across: registry (6), eligibility (2), templates (5), blueprint (5),
products (7), assets (4), channels (4), playbook (3), readiness (3), lifecycle (2),
evidence (2), orchestration (5), administration (2).

Every endpoint: validated pydantic input with `extra="forbid"` on new payloads;
`require_permission(...)`; **server-side business scoping on every query**;
pagination via the existing `envelope(data, limit=, offset=, total=)`; audit rows for
state changes; structured errors subclassing `AppError` with a typed `code`;
idempotency keys on creation, following `tasks.idempotency_key` and
`agent_creation_requests.idempotency_key`.

New permission codes, add-only, owner-bootstrap, never in `SYSTEM_PERMISSIONS`:
`business.read`, `business.write`, `business.templates.read`,
`business.templates.write`, `business.launch.approve`, `business.admin`.

Deliberately absent endpoints: anything that would publish, connect a channel,
spend, or edit a template entry. An endpoint that cannot work must not exist — the
rule P-05's plan states and P-04 Stage 5 applied to capability editing.

## 12. Testing strategy

Deterministic, no runtime model provider, no paid API, no network — the pattern the
existing 838 tests use.

* **Unit:** eligibility verdicts (all six) and each §6 check by name; opportunity
  linkage and fingerprint change detection; template versioning and the
  cannot-silently-modify rule; blueprint/assumption/customer/model validation;
  MVP classification; lifecycle graph (every valid edge, every invalid edge);
  readiness including hard-blocker-overrides-score; financial estimate labelling;
  workspace path derivation; asset rights metadata.
* **Integration:** P-01 task creation through `TaskManager`; P-03 opportunity reads;
  P-04 `AgentFactory` + `AssignmentService` for business work; approval flow
  end-to-end including the self-approval block and expiry; migration up/down/re-up on
  a populated database; the P-07 interface shape.
* **Security (§29.3, all 15):** a rejected opportunity cannot enter creation; an
  unauthorized agent cannot create a business; cross-business reads are refused
  server-side and audited; an agent cannot approve its own launch; spending cannot be
  authorized (level-3 prohibition); external publishing is refused without approval;
  no secret appears in generated content; external text cannot drive a transition; an
  unapproved asset cannot enter a launch workflow; `OPERATIONAL` is unreachable
  without launch checks; no verified-revenue claim is expressible; unauthorized access
  is refused; invalid transitions are rejected; an expired approval authorizes
  nothing; no unverified legal or trademark claim is emitted as verified.
* **Scenarios A–J** of §29.4, with D, F, G, H, I and J fully testable now, and A, B,
  C, E testable up to the point where execution is required — at which point the test
  asserts the typed `REQUIRES_P05` result rather than a simulated success.
* **Schema tests** in the P-04 style: upgrade with rows present, normalization proven
  by a seeded violating row, every CHECK bitten, server defaults exercised by an
  insert that omits the column, downgrade exactness, re-upgrade cleanliness, and an
  offline Postgres render of the whole chain.

The chain-depth tripwire (`test_the_chain_is_nine_revisions_deep`) will fail when
P-06 adds a revision. It is **hand-bumped with the DDL review recorded in its
docstring**, never derived — deriving it would defeat the only assertion that
notices a revision added without review.

## 13. Migration and rollback strategy

One additive revision, hand-written because autogenerate renders neither CHECK
additions nor `server_default` changes (L-56). Normalization statements run **before**
constraints are added. `downgrade()` removes exactly what `upgrade()` added and is
proven by test; normalizations are documented as irreversible where they are.

Rollback = `alembic downgrade -1` plus a feature flag. P-06 is gated behind
`AUTONOMOUS_BUSINESS_CREATION_ENABLED` (default **false**), so a deployment that does
not set it behaves exactly as it does today — the pattern P-04 used with
`AUTONOMOUS_AGENTS_ENABLED`, where every agent group answers 409 naming the setting.

## 14. Staging

§32's twelve stages, with what is actually deliverable:

| Stage | Scope | Status |
|---|---|---|
| 1 | Repository audit + this plan | **Deliverable now** |
| 2 | Business registry, opportunity linkage, lifecycle, workspace *paths* | Deliverable now (workspace enforcement blocked) |
| 3 | Eligibility gate, templates, versioning, approval gates | Deliverable now |
| 4 | Blueprint, customer definition, value proposition, business model, assumptions, evidence links | Deliverable now |
| 5 | Product registry, PRD, MVP scope, development plans, agent assignment integration | Deliverable now; development *execution* blocked on P-05 |
| 6 | Asset registry, brand/content metadata, usage rights | Registry deliverable; **asset files blocked** on P-05 |
| 7 | Website planning, channel evaluation, publishing preparation, approval integration | Planning deliverable; **build, verification and connection blocked** on P-05 (browser permanently) |
| 8 | Acquisition plans, support materials, playbooks, delivery procedures | Deliverable now |
| 9 | Readiness checks, blockers, warnings, evidence-based evaluation, owner approval | Deliverable now |
| 10 | Financial integration interface | Deliverable now (P-07 does not exist; interface only) |
| 11 | Frontend integration | **Blocked — no frontend exists** |
| 12 | Testing, independent audit, final report | Deliverable for everything above |

§32 says do not skip stages. Stages 6, 7 and 11 are therefore **reported as blocked
with their reasons**, in the deliverables and in `KNOWN_LIMITATIONS.md`, rather than
passed over — the same treatment the P-05 plan gives its own disabled stages.

## 15. What this plan deliberately does not do

* Does not create a business without the eligibility gate (§33 rule 6).
* Does not treat generated assumptions as market evidence (rule 7) — assumptions and
  evidence are different tables with different statuses and a link between them.
* Does not claim profitability (rule 8), fabricate testimonials, registrations or
  certifications (rules 10–11), or claim trademark availability (rule 12).
* Does not publish externally (rule 14), spend (rule 15), store raw credentials in
  agent instructions (rule 16) or bypass platform verification (rule 17).
* Does not build P-07 accounting (rule 21) or start P-07 (§36).
* Does not mark a business operational because a website exists (rule 23) or a
  product operational before its tests (rule 22).
* Does not create duplicate task, agent, workflow, approval or execution systems
  (rule 20).
* Does not install dependencies (rule 25) — nothing in this plan needs one.
* Does not delete data (rule 26); every migration is additive with a proven
  downgrade.
