# P-06 Business Creation Engine — Pre-Implementation Audit

**Date:** 2026-11-05 · **Repository HEAD:** `862bd70` (P-04 Stage 6) · **Branch:** `arena/ca116d44-devil-ai-os`

Every number in this document was read back from the repository at the commit above
— table and column lists from `Base.metadata`, the API surface from
`create_app(Settings()).openapi()`, counts from the live modules — not recalled from
an earlier phase's documentation. Where a thing is absent, the absence was verified
by looking, and is stated as absence rather than inferred.

## 0. Headline finding

**P-05 (Universal Digital Execution Engine) does not exist as code.**
`backend/app/execution/` is absent; the phase has two planning documents
(`P05_PRE_IMPLEMENTATION_AUDIT.md`, `P05_IMPLEMENTATION_PLAN.md`) and zero modules.
The P-05 plan itself ends with "**P-06 does not begin (§33)**".

P-06's brief lists P-05 as a required dependency for filesystem operations,
controlled code execution, browser automation, API adapters, document processing,
workflow execution, evidence collection and execution recovery. Those are precisely
the capabilities that separate *creating business infrastructure* from *writing
documents about a business* — which the brief identifies as the whole point:

> "The system must create real business infrastructure, not merely generate
> attractive documents."

The brief also gives the rule for exactly this situation (§33):

> "If a dependency from an earlier phase is missing, document the blocker and
> implement only the safe portion."

So this audit separates P-06 into a **safe portion** that depends only on phases
that exist (P-01 tasks/approvals, P-02 planning/models, P-03 opportunities, P-04
agents through Stage 6) and a **blocked portion** that cannot be honestly
implemented until P-05 lands. §4 and §7 draw that line; the implementation plan
turns it into stages.

Two further sequencing facts the owner should see before implementation starts:

* **P-04 is not finished.** Stages 7 (`resources.py` — budgets, the shared
  inference semaphore, backpressure) and 8 (`monitoring.py`, `versioning.py`) are
  unwritten. `app/monitoring/` is 82 lines across 4 files. P-06 §30 requires
  bounded agent concurrency and shared model inference, which is Stage 7's
  deliverable, and L-66/L-67 record that nothing observes agent health or sets
  `IDLE` today.
* **There is no frontend.** No `frontend/`, `web/`, `ui/` or `client/` directory
  exists. P-06 §26 and Stage 11 cannot be executed; the P-05 plan already records
  the same finding for its own Stage 10.

`docs/PHASE_TRACKER.md` is stale and contradicts all of the above: it lists P-04,
P-05 and P-06 as `PLANNED`. P-04 is in fact delivered through Stage 6.

## 1. Existing architecture

| Area | What exists | Evidence |
|---|---|---|
| HTTP | FastAPI, **83 paths / 91 operations**, all under `/api/v1` | `create_app(Settings()).openapi()` |
| Persistence | SQLAlchemy 2.1.6 async, **43 tables**, **9** Alembic revisions ending `d577d056a63b`; SQLite and Postgres both render clean | `Base.metadata`, `alembic heads` |
| Configuration | `Settings`, **63** fields, env prefix `AUTONOMUS_` | `app/core/config.py` |
| Events | **58** event types, bus rejects unknown types | `app/events/events.py` |
| Authorization | **35** permission codes, `principals` / `permissions` / `permission_assignments`, owner bootstrap, system principal deliberately excluded from owner-only codes | `app/permissions/policies.py` |
| Approvals | Central `ApprovalService` + `approvals` table (`requester_id`, `action`, `resource`, `risk`, `reason`, `requested_permissions`, `payload_hash`, `status`, `approver_id`, `expires_at`, `decided_at`), self-approval block | `app/permissions/approvals.py` |
| Tasks | `TaskManager` with 10 states, workers, retries, cancellation, pause/resume, approval gating, stale-approval expiry, interrupted-task recovery | `app/tasks/manager.py` |
| Planning | `missions`, `plans`, `plan_steps` with `depends_on`, `capability_id`, `expected_output`, `completion_criteria`, `parallel_group`, `estimated_duration_seconds`, `risk` | table columns |
| Intelligence | 18 modules / 7,469 lines; model registry with `min_ram_gb`, `available`, `healthy`, `supports_structured_output`, `supports_tool_calling`, `cost_per_1k_tokens`; `model_usage` records tokens, duration, estimated cost | `app/intelligence/`, `registered_models` |
| Agents | 11 modules / 4,168 lines: registry, templates + versions, creation engine (6 decisions), capability catalog (29 entries, 4 levels), grants, assignment ledger with nine rules | `app/agents/` |
| Opportunities | 17 modules / 9,743 lines; discovery, screening, scoring, market/competitor/commercial/risk analysis, evidence, reporting | `app/opportunities/` |
| Tests | **838 passing** at `862bd70`; 5 audit scripts exit 0 | full-suite run |
| Dependencies | **13**, all version-pinned; no image, browser, document or filesystem library among them | `backend/requirements.txt` |

## 2. Existing business-related functionality

Almost none, and what exists is a placeholder rather than a system:

* **No `businesses` table.** None of the 43 tables models a business.
* **No business API.** Zero paths contain `business`.
* **Two bare `business_id` columns** — on `agents` and `agent_creation_requests` —
  both nullable strings with **no foreign key and no referent**. P-04 lets an agent
  be scoped to a business that cannot exist. Assignment rule 6
  (`business_scope_matches`) compares these strings, and when a task declares no
  business the rule reports that isolation "could not be checked".
* **`opportunities.business_model`** — a free-text field describing the revenue
  model, not a business record.

This is the single clearest argument for P-06: the identifier that P-04 already
depends on has nothing behind it.

## 3. Reusable modules

P-06 must reuse these and must not rebuild them (§33 rule 20).

| P-06 requirement | Reuse | Why it fits |
|---|---|---|
| §6 eligibility evidence | `opportunities`, `opportunity_scores` | Already carry `validation_level`, `validation_satisfied`, `validation_blocking`, `validation_next_requirement`, `hard_rejections`, `rejected`, `recommendable`, `evidence_quality`, `evidence_coverage_pct`, `evidence_ids`, `rejection_reasons`, `assumptions`, `business_model`, `distribution`, `risk_assessment` |
| §6 "hard rejection rules from P-03 remain authoritative" | `opportunity_scores.hard_rejections`, `risk_findings.blocks_recommendation`, `prohibited_category_matched` | The veto already exists and is deterministic |
| §8.2 customer definition | `market_analyses` | `demand_evidence_level`, `problem_importance`, `problem_importance_basis`, `customer_description`, `sizing`, `signals`, `willingness_indicators`, `data_gaps` |
| §9 pricing research, "do not invent competitor prices" | `competitor_records` | `price_points`, `price_currency`, **`pricing_provenance`**, `rating_provenance`, `identified_gaps`, `evidence_ids`, `observed_at`, `inspected` |
| §27 financial inputs for P-07 | `commercial_analyses` | `verdict`, `viable`, `affordable`, `costs`, `scenarios`, `break_even`, `budget_compatibility`, `unpriced_cost_items`, `assumptions` |
| §8.5 assumption register | `hypotheses` (pattern) | `statement`, `supporting_evidence`, `contradicting_evidence`, `confidence`, `confidence_basis`, `validation_requirement`, `status` |
| §22 evidence repository | `source_evidence` | `evidence_type`, `classification`, `claim`, `observed_value`, `numeric_value`, `unit`, `source_url`, `publication_date`, `reliability`, `trust_domain`, **`independence_group`**, **`supersedes`**, **`contradicts`**, **`stale_after_days`** — already exceeds §22's field list |
| §6 legal/platform risk | `risk_findings` | `category`, `severity`, `jurisdiction`, `platform`, `mitigation`, `evidence_ids` |
| §7 versioned templates | `agent_templates` + `agent_template_versions` | `current_version`, `status`, per-version `configuration_json` and `validation_status` |
| §19 lifecycle event log | `opportunity_history`, `mission_history` | `from_state`, `to_state`, `reason`, `actor`, `recorded_at`, `metadata` |
| §19 state machine | `app/agents/lifecycle.py` | A validated transition graph that rejects invalid transitions — the pattern P-06 needs |
| §21 orchestration | `plans` / `plan_steps`, `TaskManager`, `AgentFactory`, `AssignmentService` | Dependency edges, capability-gated steps, task dispatch and the nine assignment rules already exist |
| §28.6 approval integrity | `ApprovalService` | Explicit, authenticated, scoped, expiring, self-approval-blocking |
| §3 shared inference | `registered_models`, `model_usage` | Provider-independent routing with RAM floors already recorded |

**`business_approvals` must not be created.** §23 allows it only "if the existing
approval architecture cannot support business-related approval references". It can:
`approvals.action` and `approvals.resource` are free strings, `payload_hash` binds
the payload, and P-04 already opens approvals for agent capability grants. Reusing
the central service keeps one approval queue for the owner, which is the property
§28.6 is protecting.

## 4. Missing functionality

### 4.1 Missing and safe to build now

Business registry and identity; eligibility evaluation over P-03 records; business
templates with versioning; blueprint, customer definition, value proposition and
positioning as validated structured data; assumption register with evidence links;
business model framework; pricing *structure* (not price invention); product
registry, PRD and MVP scope; lifecycle state machine and event log; launch-readiness
evaluation over recorded facts; orchestration *planning*; the P-07 financial
interface; operating playbooks as versioned structured data; server-side business
isolation as policy.

### 4.2 Missing and blocked on P-05

| P-06 requirement | Blocked by | Consequence if built anyway |
|---|---|---|
| §12 asset **files** (logos, covers, graphics, screenshots) | `adapters_fs`; no image library in `requirements.txt` | Would record assets that do not exist |
| §13.4 website **implementation** | `adapters_fs`, `adapters_code` | Would emit files nothing can run or serve |
| §13.5 website **verification** (pages load, links work, forms behave, responsive) | Browser adapter — which the P-05 plan permanently disables as `UNSUPPORTED_BY_ENVIRONMENT` | Would report verification that never happened |
| §14 channel **connection** and publishing | `adapters_api`, `external_execution_enabled` | Would claim connections that do not exist |
| §18 workspace **enforcement** | `execution_workspaces.permission_scope` (P-05 table) | Isolation would be a convention, not a control |
| §11 development **execution** | `adapters_code` | Would assign coding work nothing can perform |
| §21 orchestration **execution** | `workflows.py`, checkpoints, compensation | Would duplicate the P-01 task engine |
| §22 evidence **hashing / screenshots** | `evidence.py` | Would fabricate content hashes |
| §29 Scenario I recovery | `recovery.py`, `REQUIRES_RECONCILIATION` | Would claim safe resume it cannot guarantee |

### 4.3 Missing and blocked on P-04 Stages 7–8

§30's bounded concurrency, backpressure and shared-inference semaphore are Stage 7
(`resources.py`). Health observation, metrics and suspension are Stage 8
(`monitoring.py`, `versioning.py`); L-66 and L-67 record that nothing observes
health or sets `IDLE` today. P-06 can *record* resource estimates but cannot
*enforce* pressure until Stage 7 exists.

### 4.4 Missing entirely

Frontend (§26, Stage 11). Windows-specific behaviour cannot be verified here: the
workspace is Linux (`uname` 6.1.158+, x86_64, 2 logical CPUs, 3.85 GiB RAM, no
GPU), so Windows-first claims must be documented as untested on target.

### 4.5 Missing data P-06's brief assumes

* **`opportunity_version` does not exist.** §6 requires every business to store the
  originating opportunity's version, and §6 requires reevaluation "if the
  opportunity changes materially". `opportunities` has no version column;
  `opportunity_history` records transitions but not versions. P-06 must therefore
  capture a *content fingerprint plus `updated_at`* at creation and compare on
  reevaluation, or P-03 must add versioning. Recording a version number that does
  not exist would be fabrication.
* **No project/workspace record.** §18's `businesses/business_001/…` tree has no
  managing module; nothing in the repository creates or scopes directories.

## 5. Integration requirements

* **P-01** — create business work as `tasks` through `TaskManager.submit`; never
  spawn a parallel queue. Record lifecycle changes as events and audit rows.
* **P-02** — planning through `missions`/`plans`/`plan_steps`; model calls through
  the existing router so `model_usage` keeps recording tokens and cost. No new
  provider stack.
* **P-03** — read-only. P-06 must never write to `opportunities`; eligibility reads
  and records a decision against the opportunity id.
* **P-04** — agents via `AgentFactory` (which already emits `ASSIGN_EXISTING`) and
  work via `AssignmentService.assign`, so the nine rules gate every business task.
  Capabilities via `CapabilityService.check()`. Business creation must not mint
  agents directly.
* **P-05** — absent. Every call site must be behind an interface that reports
  `UNSUPPORTED_BY_ENVIRONMENT` or `REQUIRES_P05` rather than pretending to succeed.
* **P-07** — do not build. Emit structured estimates with amount/range, currency,
  source, estimate-vs-verified, confidence, date and assumptions (§27), labelled as
  estimates, and never as collected revenue.

## 6. Database changes required

Additive only, one revision, hand-written (autogenerate renders neither CHECK
additions nor `server_default` changes — L-56). Thirteen tables from §23 minus
`business_approvals`, which §3 shows the central service can carry:

`businesses`, `business_templates`, `business_template_versions`,
`business_blueprints`, `business_assumptions`, `business_products`,
`product_requirements`, `business_assets`, `business_channels`,
`business_campaigns`, `business_playbooks`, `business_readiness_reviews`,
`business_lifecycle_events`, `business_evidence`.

Two changes to existing tables, both additive:

* Give `agents.business_id` and `agent_creation_requests.business_id` a real
  referent. Adding a foreign key over existing rows needs normalization first —
  the pattern Stage 4 established and Stages 5 and 6 repeated, because a CHECK or
  FK that existing rows violate fails partway through SQLite's non-transactional
  batch rebuild.
* Nothing else. Existing columns and all 91 operations must keep working.

Constraints must be **named** in `models.py` (ADR-0024: an unnamed constraint cannot
be dropped later — P-06 Stage 6 hit this exactly, when `drop_constraint(None,
type_='unique')` failed on `agent_assignments.task_id`).

## 7. Execution adapter availability

**None.** There is no adapter layer of any kind in this repository:

| Capability P-06 needs | Available today |
|---|---|
| Filesystem read/write | No — `filesystem.read` / `filesystem.write` exist as **disabled** capability catalog entries pending P-05 |
| Controlled code execution | No — `code.execute`, `execution.tool` disabled pending P-05 |
| Browser automation | No — `browser.control` disabled; P-05 plans it as `DisabledAdapter` |
| Outbound API calls | No — `external.network` disabled pending P-05 |
| Document processing | No library present |
| Image generation | No library present; §33 rule 25 forbids unnecessary dependencies |
| Workflow execution | P-01 `TaskManager` + `plan_steps` only; no P-05 workflow runs |
| Evidence hashing | `source_evidence` stores references and classifications; no content-hash pipeline |
| Human approval | **Yes** — central `ApprovalService`, fully working |
| Execution recovery | `TaskManager.recover_interrupted` for tasks; nothing for external side effects |

The eight disabled capability entries are the honest signal: the catalog already
declares these authorities and already refuses them.

## 8. Security and approval requirements

* **Isolation must be server-side.** §28.1 forbids relying on frontend filtering —
  and there is no frontend, so every check is server-side by construction. Until
  `execution_workspaces.permission_scope` exists, isolation can be enforced for
  *database reads* (every query scoped by a validated `business_id`) but not for
  *files*, because no file access exists to scope. That limit must be stated, not
  implied away.
* **Reuse the self-approval block.** §21 and §28.6 forbid an agent approving its own
  critical deliverable. `ApprovalService.decide` already refuses
  `requester_id == approver_id` at high/critical risk, and only the owner holds
  `approvals.decide`. P-04 Stage 5 hit a deadlock here (L2 requester must be the
  beneficiary's principal, not the actor); P-06 must not repeat it.
* **New permission codes are add-only**, owner-bootstrap, never in
  `SYSTEM_PERMISSIONS` — so the application can never create, launch or publish a
  business on its own authority.
* **Prohibited by catalog already:** `spending.authorize`, `financial.execute`,
  `secrets.store_raw`, `distribution.publish_unauthorized`, `governance.bypass`,
  `identity.impersonate_owner`, `approval.self_grant`, `evidence.fabricate` are
  level-3 prohibitions enforced from a code literal before any row lookup, so no
  P-06 code path can grant them. §28.2's forbidden agent actions map onto these.
* **Prompt injection:** external content is already treated as untrusted
  (`evidence_records.trust_domain`, `source_evidence.trust_domain`,
  `independence_group`). P-06 must not let opportunity or web text drive a lifecycle
  transition; §19 requires deterministic backend validation.
* **No secrets in generated documents** (§28.3) — enforceable only over content P-06
  itself generates, since P-06 cannot read files yet.

## 9. Resource constraints

Target hardware is an i7-4712HQ, ~16 GB RAM, Quadro K1100M 2 GB. The **development**
workspace is smaller: 2 logical CPUs, 3.85 GiB RAM, no GPU, no `/dev/nvidia*` or
`/dev/dri`. Consequences:

* No model can be run here, so every P-06 test must be deterministic with no runtime
  provider — the pattern P-02/P-03/P-04 tests already use.
* `registered_models.min_ram_gb` already exists to keep heavy models off small
  machines; P-06 must read it rather than assume capacity.
* §30's bounded concurrency cannot be enforced until P-04 Stage 7 delivers the
  semaphore and backpressure. P-06 should record resource estimates and refuse to
  start work whose estimate exceeds configured bounds, which is enforceable today.
* The full test suite already takes ~15 minutes on 2 CPUs. P-06 must not add
  per-test application bootstraps beyond what the existing fixtures provide.

## 10. Compatibility risks

| Risk | Assessment |
|---|---|
| Breaking P-01…P-04 | Low if changes stay additive. 838 tests are the guard, plus 5 audit scripts. |
| Module placement conflict | §24 proposes `backend/business_creation/…`; the repository convention is `backend/app/<subsystem>/` (`app/agents`, `app/opportunities`). §24 also says "follow the existing repository conventions". **Resolution: `backend/app/business/`**, with the service names §24 lists. |
| API prefix conflict | §25 proposes `/api/…`; the repository is uniformly `/api/v1/…` and §25 says to adapt. **Resolution: `/api/v1/businesses`, `/api/v1/business-templates`, …** |
| Duplicate infrastructure | High if ignored: §33 rule 20 forbids new task/agent/workflow/approval/execution systems, and P-01/P-04 already provide all five. Every P-06 service must call them. |
| FK over existing rows | Medium. Adding a `businesses` FK to `agents.business_id` needs normalization first (Stage 4's lesson). |
| Unnamed constraints | Medium. ADR-0024 — name everything, or it cannot be dropped later. |
| Chain-depth tripwire | Certain and deliberate: `test_the_chain_is_nine_revisions_deep` fails when P-06 adds a revision. It must be hand-bumped with the DDL review recorded in its docstring, not derived. |
| Stale phase tracker | Certain: `PHASE_TRACKER.md` says P-04 is `PLANNED`. Should be corrected in the same commit as the plan. |
| Frontend expectations | Certain: §26 cannot be delivered. Must be reported as blocked, not skipped silently. |
| Windows claims | Certain: cannot be verified on Linux. Must be labelled untested-on-target. |
| Overstating readiness | The dominant risk. A blueprint is not a product, a recorded channel is not a connection, and a readiness score is not a launch. Every P-06 output must carry the distinction §19 lists. |

## 11. Recommendation

Proceed with **Stage 1 only** — this audit and the implementation plan — then stop
for an owner decision, because the choice is consequential and is not P-06's to
make:

1. **Build P-05 first** (its plan is written and staged), then P-06 in full. This is
   the order the P-05 plan itself specifies and the only order in which P-06 can
   create infrastructure rather than records.
2. **Finish P-04 Stages 7–8 first**, then P-05, then P-06. Smallest total risk;
   §30's resource controls exist before anything depends on them.
3. **Build P-06's safe portion now** under §33's rule, with every blocked capability
   reporting `REQUIRES_P05` rather than simulating success. Delivers the registry,
   eligibility gate, templates, blueprint, business model, product specification,
   lifecycle, readiness engine and financial interface — and gives the two existing
   `business_id` columns a referent — while explicitly not creating assets,
   websites, products or channel connections.

Option 3 is defensible and is what §33 authorizes, but the owner should choose it
knowing that until P-05 exists, P-06 can decide what a business should be and
cannot build it.
