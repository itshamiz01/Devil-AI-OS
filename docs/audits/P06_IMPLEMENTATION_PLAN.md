# P-06 Implementation Plan — Business Creation Engine

Companion to `docs/audits/P06_PRE_IMPLEMENTATION_AUDIT.md`. Follows the
P-06 prompt §32 stage order 1→12. All identifiers below were verified
against the P-01–P-05 code during the Stage-1 audit.

## Stage map (§32)

| §32 stage | Work | Where |
|---|---|---|
| 1 Audit + plan | Baseline 300/300 recorded; audit + this plan | `docs/audits/P06_*` |
| 2 Business registry + lifecycle | Models, repositories, lifecycle state machine + guards, business CRUD service | `app/business/{lifecycle,service}.py`, `app/database/models/business.py`, `app/database/repositories/business.py` |
| 3 Eligibility + templates | §6 evaluator (persisted), template registry + validation against P-05 tool registry, seed templates | `app/business/{eligibility,templates}.py` |
| 4 Blueprint, assumptions, evidence, financial interface | Deterministic blueprint generation, assumption register, business evidence, §9 financial values + P-07 payload | `app/business/{blueprint,financial}.py` |
| 5 Product creation + dev coordination | Product + requirements, agent assignment via P-04 factory (reuse-first), creation workflow = template `WorkflowEngine` definition driven through P-05 | `app/business/service.py` (`run_creation`) |
| 6 Asset management | Asset registration from workflow step results, hash verification via execution reads, rights/quality states | service + `business_assets` |
| 7 Website + distribution prep | Website state fields (never collapsed), channel evaluation, §14 platform gates | `app/business/platform_gates.py`, service |
| 8 Acquisition/support/playbook prep | Draft-only campaign records, support docs + operational playbook as workflow-generated assets | templates + service |
| 9 Readiness engine | §20 dimensions A–H, five results, blocker override, declaration comparison | `app/business/readiness.py` |
| 10 API | Router + schemas, application wiring, events | `app/api/routes/business.py`, `app/api/schemas/business.py`, `app/core/application.py`, `app/main.py`, `app/events/events.py` |
| 11 Testing | Unit / integration / security (15 named §29.3) / scenarios A–J / resource-mode checks | `tests/test_p06_*.py` |
| 12 Docs + migration + smoke + gate | §31 documents, one additive migration, uvicorn smoke, tracker, zip | `docs/**`, `alembic/versions/` |

## Data model (one additive migration, down_revision `6ffcc7e899fa`)

New tables (logical §23 entities; approvals/opportunities/workspaces/evidence
patterns reuse existing homes per the audit):

`business_templates`, `business_template_versions`, `businesses`,
`business_blueprints`, `business_declarations`, `business_assumptions`,
`business_products`, `product_requirements`, `business_assets`,
`business_channels`, `business_campaigns`, `business_playbooks`,
`business_readiness_reviews`, `business_lifecycle_events`,
`business_evidence`, `business_eligibility_evaluations`,
`business_creation_runs`, `business_agent_assignments`.

Invariants enforced in schema/service: businesses pin
`template_id + template_version`; `is_fixture` is stored and surfaced in
every serialisation; **no revenue/profit columns exist anywhere**;
`website_states` is a JSON object with five separate boolean fields.

## Service surface (`BusinessCreationService`)

- Templates: `seed_templates`, `list_templates`, `get_template`,
  `create_template_version` (owner-only; validation = workflow-definition
  validation + registry resolution + denylist).
- Settings: `get_settings` / `update_settings` (owner-only;
  `business.settings` in `system_config`).
- Eligibility: `evaluate_eligibility(principal, opportunity_id, approval_id=None)`
  → persisted evaluation with the six §6 decisions.
- Creation: `create_business` (fresh eligibility + verified owner creation
  approval required), `get_business`, `list_businesses`, `transition`
  (guard-checked), `request_pause/resume/block/fail/archive` via transition.
- Declaration: `create_declaration` (draft by any authorised principal;
  owner-created = approved), `approve_declaration` (P-01 approval binding).
- Blueprint: `generate_blueprint` (deterministic, redaction pass),
  `approve_blueprint` (P-01 approval binding).
- Run: `ensure_business_agents` (P-04 factory reuse-first + governed
  grants executed under the creation approver), `run_creation` (builds the
  `WorkflowEngine` definition from the pinned template version, drives it,
  registers assets, verifies hashes, advances lifecycle).
- Distribution: `evaluate_channels` (platform gates recorded as business
  evidence), `record_publish_attempt` (always refused/draft in staging —
  returns the gate outcome, never publishes).
- Readiness: `evaluate_readiness` (A–H), `get_readiness`.
- Launch: `request_launch` (creates hash-bound approval, state →
  `LAUNCH_APPROVAL_PENDING`), `launch` (owner principal + verified binding
  + readiness READY-family + declaration present → `LAUNCHING` →
  `OPERATIONAL` with staging truth fields).
- Isolation: `assert_business_access`, `probe_workspace_access`
  (denial ⇒ persisted critical event), used by every business-scoped read
  and by the creation run.
- Evidence/assumptions: `add_evidence`, `list_evidence`,
  `add_assumption`, `review_assumption`.
- Financial: `financial_inputs(business_id)` → validated P-07 payload.

## API surface (`/api/v1/business...`)

Templates (list/get/create-version), settings (get/put, owner),
eligibility evaluate, businesses CRUD + lifecycle transition, declaration
create/approve, blueprint generate/get/approve, creation run,
channels evaluate + publish-attempt, readiness evaluate/get, launch
request/launch, evidence + assumptions, assignments, financial inputs,
workspace-access probe, engine status. Route guards mirror P-03/P-05:
`read_business_data` for reads, `modify_business_data` for writes,
`approve_actions` where an approval decision is taken; owner-only checks
live in the service (house pattern).

## Templates (seed data, `app/business/templates.py`)

1. `ebook_digital_product` (digital_products) — **end-to-end**: workflow
   steps = mkdir §18 tree → documents for blueprint, product spec,
   manuscript outline, brand guide, listing copy (DRAFT), FAQ/support,
   playbook, legal templates (placeholder-marked), website `index.html`;
   channels: direct-download (gate PASS, prepared-only) + KDP (gate
   `REQUIRES_HUMAN_ACTION`); Scenario A.
2. `saas_micro_tool` (software) — validated definition exercised in
   Scenario B: PRD/architecture docs + a `code_python.run` verification
   step + landing page.
3. `content_publication` (content) — validated definition exercised in
   Scenario C: editorial plan, brand guide, sample article draft,
   publishing-infrastructure requirements (no auto-posting).
4. `productized_service` (services) — registered, validated,
   **unexercised**; labelled prepared-only in the report.

Template validation rejects: unknown tools/actions, disabled tools
(desktop), interactive browser actions, money-moving parameter keys,
`external_communication`, > 50 steps, missing required sections.

## Testing plan

- `tests/p06_support.py` — app/client fixtures (controlled mode), fixture
  opportunity builder driving P-03's real service/API machinery.
- `tests/test_p06_unit.py` — lifecycle transition table, template
  validation, financial values + arithmetic, redaction, eligibility
  decision matrix, readiness precedence.
- `tests/test_p06_integration.py` — HTTP flows: template/settings CRUD,
  eligibility persistence, creation happy path (fixture), declaration
  gate, blueprint approval drift, readiness, launch approval flow,
  migration cycle (head pin updated with disclosure, per P-03–P-05
  precedent).
- `tests/test_p06_security.py` — the 15 §29.3 tests as named tests.
- `tests/test_p06_scenarios.py` — §29.4 Scenarios A–J mapped by name.
- Full suite must pass in one run; counts reported exactly.

## Smoke plan (`scripts/p06_smoke.py` → `docs/reports/P06_SMOKE_EVIDENCE.txt`)

Real uvicorn, controlled mode, throwaway data dir. Order: **D first**
(real P-03 e-book opportunity recreated through the P-03 API at Level 1 →
eligibility `REQUIRES_MORE_RESEARCH`, zero businesses), then A (fixture
ebook business end-to-end incl. KDP gate), F (NOT_READY + refused
transition), G (cross-business denial + persisted event), J (READY fixture
→ `LAUNCH_APPROVAL_PENDING` → launch refused without approval → owner
approval → `OPERATIONAL` labelled staging demonstration).

## Rollback

One additive migration: `alembic downgrade 6ffcc7e899fa` removes exactly
the P-06 tables (verified in the migration-cycle test). No existing table,
route, or service contract changes; removing the router include reverts
the API surface.
