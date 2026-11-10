# P-06 Implementation Report — Business Creation Engine

**Date:** 2026-11-09 · **Environment:** Linux staging VM (Windows
verification carried, as for P-01–P-05) · **Status: BUILT AND VERIFIED
IN STAGING — awaiting the owner gate. P-07 was not started (§36).**

## 1. Executive summary

P-06 turns P-03-validated opportunities into structured, launch-ready
**local business packages**: eligibility (§6) → hash-bound owner
creation approval → pre-declaration (Constitution gate) → deterministic
blueprint → product/assets created through the P-05 execution engine
inside an isolated per-business workspace → platform-gated distribution
preparation → §20 readiness → owner-approved launch decision.

**The central honesty result, stated plainly: with real evidence,
nothing in staging currently qualifies for business creation.** The
real P-03 e-book investigation computes to **Validation Level 1**; the
§6 gate (owner-governed minimum 3) blocks it —
`REQUIRES_MORE_RESEARCH`, creation refused with HTTP 409, zero
businesses created (smoke Scenario D, run first). All creation
machinery is proven with clearly-labelled **fixture** opportunities
whose evidence is stored through P-03's own machinery and whose levels
P-03 computes (Level 3 in the smoke/tests — computed, never asserted).

348/348 tests pass in one run (300 regression + 48 new). No business
was launched into the real world, nothing was published, deployed,
sold, or sent.

## 2. Initial repository condition

Baseline re-run before any P-06 code: **300 passed, 1 warning in
102.88s** (the pre-existing Starlette TestClient deprecation warning).
Stage-1 audit: `docs/audits/P06_PRE_IMPLEMENTATION_AUDIT.md`; plan:
`docs/audits/P06_IMPLEMENTATION_PLAN.md`. Prep-pack reconciliation
(audit §1): all nine prep-pack design decisions adopted; the minimum
validation level became owner-governed config per the prompt (default
3, the prep pack's substance); §20's five readiness results and §19's
full lifecycle adopted exactly; the fixture rule sharpened to
"computed, never asserted".

## 3. Existing functionality reused

P-01: hash-bound approvals (all four business approval kinds), permission
engine + existing business permissions, audit trail, event bus +
persisted critical events, owner-governed `system_config`, modes.
P-02: mission/decision-record traceability pattern (no planner changes;
P-06 is deterministic). P-03: opportunities, `validate()` (levels
computed), scoring/hard-rejections, commercial analyses, reports — the
only input source. P-04: agent factory (reuse-first, governed grants),
CapabilityService as the only capability oracle. P-05:
ExecutionService, WorkflowEngine, managed workspaces, adapters,
evidence. **No `business_approvals` table** — the audit (§5) proved the
central service carries business references; drift fails closed.

## 4. New components implemented

`backend/app/business/`: `constants`, `lifecycle`, `eligibility`,
`templates` (4 seed templates + registry validation), `platform_gates`,
`financial`, `blueprint` (deterministic generation + redaction),
`readiness`, `fixtures`, `service` (`BusinessCreationService`, ~1,900
lines). API: `app/api/routes/business.py` + `app/api/schemas/business.py`.
Models/repositories: `app/database/models/business.py`,
`app/database/repositories/business.py`. Events: 11 new `EventType`s,
6 added to the persisted critical set. Tests: `tests/p06_support.py`,
`tests/test_p06_{unit,integration,scenarios,security}.py`. Smoke:
`backend/scripts/p06_smoke.py`.

## 5. Existing modules modified

- `app/core/application.py`, `app/main.py` — additive wiring only.
- `app/events/events.py` — new event types + critical-set additions.
- `app/database/models/__init__.py` — new model exports.
- `app/execution/schemas.py` + `app/execution/workflows.py` — **one
  additive, disclosed extension**: `WorkflowRunIn.business_ref`
  (default `None`), propagated via the run checkpoint to step requests.
  Without it, P-05 workflows cannot write to `businesses` workspaces
  (policy requires a `business_ref` the engine never set). All 300
  regression tests pass; runs not setting it behave identically.
- Five pre-existing test files: migration-head pins updated to
  `a8d7e0c717b4` with in-code P-06 disclosure comments (strictness
  preserved) — see the test report.

## 6. Business categories supported

| Template | Category | Support |
|---|---|---|
| `ebook_digital_product` | digital_products | **Operational** (Scenario A, HTTP flow) |
| `saas_micro_tool` | software | **Operational** (Scenario B incl. verified prototype step) |
| `content_publication` | content | **Operational** (Scenario C) |
| `productized_service` | services | **Prepared-only** — registered + validated, not exercised |

## 7. Eligibility architecture

Pure evaluator over P-03 facts (`app/business/eligibility.py`): status,
hard rejection, budget compatibility → REJECTED paths; computed level
vs owner-governed minimum + supporting evidence + startup estimability
→ REQUIRES_MORE_RESEARCH (level ≤ 1) / REQUIRES_MORE_VALIDATION;
completeness (customer, problem, revenue model, commercial analysis,
distribution) → REQUIRES_MORE_VALIDATION; approval binding →
REQUIRES_OWNER_APPROVAL; compliance/professional-review and
all-unknown-costs → ELIGIBLE_WITH_CONDITIONS; else
ELIGIBLE_FOR_CREATION. Every evaluation is persisted with per-check
reasons; evaluations create nothing.

## 8. Business blueprint implementation

Deterministic 16-section blueprint (§8.2) from the P-03 report +
commercial analysis + pinned template; assumption register (§8.5,
five statuses); name check that explicitly does **not** claim legal
availability; owner hash-bound blueprint approval with drift detection;
secret redaction over all rendered documents. See
`docs/architecture/BUSINESS_BLUEPRINT_ARCHITECTURE.md`.

## 9. Business model framework

Models are template data + opportunity data, never code (§9). Pricing
is a financial value; arithmetic is deterministic code; the framework's
hard edge is §27: collected revenue/profit cannot be recorded at all.
See `docs/architecture/BUSINESS_MODEL_FRAMEWORK.md`.

## 10. Product creation capabilities

Specification-first (product + requirements at blueprint time);
creation exclusively as the pinned template's P-05 workflow (filesystem/
documents writes; `code_python.run` verification for SaaS under
process-controls-only isolation, labelled as such since P-05);
assets registered only after engine hash verification; quality review
by the QA assignment (asset hashes, secret scan property, no-fabricated
-claims property). See `docs/architecture/PRODUCT_CREATION_WORKFLOW.md`.

## 11. Asset management

Registry with type, storage reference, version, creation method,
creator agent, approval/rights/quality statuses, content hash, product
link. Rights uncertainty blocks readiness (test 13). Legal assets are
placeholder-marked templates. See
`docs/architecture/BUSINESS_ASSET_MANAGEMENT.md`.

## 12. Website creation capabilities

Static site package generated into `website/` and verified locally
through execution reads. Five separate state fields
(planned/generated/verified_locally/deployed/publicly_available);
staging can only ever set the first three — no deployment adapter
exists, and the generated page states that it is not deployed.

## 13. Distribution preparation

Channel evaluation from template data; every channel carries its §14
platform-gate outcome, recorded as business evidence. KDP →
`REQUIRES_HUMAN_ACTION` (Amazon blocks AI-agent sign-in, verified
2026-11-08); Gumroad/Substack/YouTube → human action; own website →
prepared-only. Publish attempts return gate outcomes and are recorded;
**no publishing path exists**. Unknown platforms fail closed.

## 14. Customer acquisition preparation

Plans and drafts only: listing copy (DRAFT) as an asset; campaign
records are draft-only by construction (no send/post code exists);
`external_communication` remains ungrantable and templates requiring
it are rejected at validation.

## 15. Customer support preparation

FAQ + support procedures generated into `customer_support/` and the
playbook (acknowledgement window, complaint logging/escalation, refund
path as an owner-confirmation placeholder — never an invented policy).
Readiness dimension E fails closed without them (Scenario F).

## 16. Operating playbook

Generated per business (§16 contents: daily/weekly operations, support,
quality control, incident response, escalation, backup/recovery,
indicators, known risks from the opportunity's evidence gaps,
improvement procedures) as both a structured row and
`operations/playbook.md`.

## 17. Business lifecycle

§19 states/transitions as data with guards (blueprint existence,
readiness gate, launch only via the approval flow, pause returns to
origin). Every transition is an event row with actor + approval
reference. `OPERATIONAL` in staging records
`deployment_state=local_package_only`, `public_availability=false`,
`revenue_asserted=false`. See `docs/architecture/BUSINESS_LIFECYCLE.md`.

## 18. Launch readiness

Eight deterministic dimensions (A–H), five results, blocker precedence
BLOCKED > NOT_READY > OWNER_REVIEW_REQUIRED > READY_WITH_WARNINGS >
READY; hard blockers override; the declaration comparison (incl. the
budget-cap test) is embedded in every review; the not-certified
disclaimer is stored on the review. See
`docs/architecture/LAUNCH_READINESS_ENGINE.md`.

## 19. Agent orchestration

Factory reuse-first portfolio staff (Scenario I: identical agent sets
across businesses); P-06 records per-business assignments; grants flow
through the factory's governed path under the creation approver (the
owner); an agent never approves its own deliverables (owner-only
approval checks on creation/launch, security test 4).

## 20. Approval and security controls

Four hash-bound approval kinds (create/declaration/blueprint/launch)
with drift detection; §28.1 isolation enforced at the P-06 service
layer (P-05's generic workspace rule is necessary but not sufficient —
audit §6) with persisted critical violation events; generated-content
redaction + scan; injection-bearing text treated as data (test 8);
template denylist (money keys, disabled tools, interactive browser,
external communication); mode discipline (simulation drafts-only,
emergency halt). All 15 §29.3 tests are real named tests — mapping in
the test report.

## 21. Database changes

One additive migration `a8d7e0c717b4` (revises `6ffcc7e899fa`): 18 new
tables — business_templates, business_template_versions, businesses,
business_blueprints, business_declarations, business_assumptions,
business_products, product_requirements, business_assets,
business_channels, business_campaigns, business_playbooks,
business_readiness_reviews, business_lifecycle_events,
business_evidence, business_eligibility_evaluations,
business_creation_runs, business_agent_assignments. 63 tables at head.
Upgrade/downgrade/re-upgrade verified on SQLite with an exact
table-set comparison on downgrade; no existing table altered.

## 22. API endpoints

All under `/api/v1/business`: status, settings (GET/PUT),
templates (GET list/one, POST version), creation-approvals (POST),
eligibility (POST), businesses (POST/GET list/one), transition,
lifecycle, declarations (POST/GET, approve), blueprint (POST/GET,
approve), creation-run (POST), product, assets, channels (evaluate/
list/publish-attempt), readiness (POST/GET), launch (request/launch),
assignments, workspace-access probe, evidence (POST/GET), assumptions
(POST/GET), campaigns (POST), financial-inputs (GET). Guards:
`read_business_data` / `modify_business_data` / `approve_actions` plus
service-level owner checks. **No frontend exists (P-11).**

## 23. P-07 integration interface

`GET .../financial-inputs` and `financial.build_p07_payload`: per-business
startup/recurring financial values (source + classification +
confidence + assumptions preserved from P-03), deterministic totals,
the product's pricing value, and the standing statement that P-06
records no revenue. The builder rejects revenue/profit keys, so the
interface cannot be abused to assert financial truth (tests 10–11).
Nothing is sent anywhere; P-07 does not exist yet.

## 24. Test results

**Tests executed: 348 · passed: 348 · failed: 0 · skipped: 0.**
Integration tests passed: 6 P-06 (+ all pre-existing integration
suites within the 300). Security tests passed: 16 (the 15 §29.3 items).
Known warnings: 1 — the pre-existing Starlette TestClient/httpx
deprecation warning (present since P-01). Outstanding blockers: none
for the staging gate. Smoke: real uvicorn run, Scenarios D/A/F/G/J,
transcript at `docs/reports/P06_SMOKE_EVIDENCE.txt`.

## 25. Windows setup

Documented in `docs/operations/BUSINESS_WORKSPACE_GUIDE.md`
(Python 3.12 venv, requirements, `AUTONOMUS_DATA_DIR`,
`alembic upgrade head`, uvicorn loopback). **Windows execution remains
unverified** — carried from P-00/P-01 and not claimed here.

## 26. Known limitations

1. **Real opportunities do not qualify.** Staging's real investigations
   sit at Validation Level 1; creation is proven with fixtures only.
2. **No live publishing or deployment exists** — by design (platform
   gates) and by environment (browser interactive actions unavailable,
   no deployment adapter).
3. **No LLM** — all generation is deterministic templating, labelled
   as such; copy quality is structural, not editorial.
4. Fixture evidence proves machinery, not market truth.
5. Audit is append-only via API, not cryptographically tamper-proof
   (carried since P-01).
6. Windows unverified (carried).
7. P-05 SSRF guard does no DNS resolution (carried; P-06 makes no
   outbound calls at all).

## 27. Deferred functionality

Financial truth/accounting (P-07), survival/scaling (P-08), memory
(P-09), hardening (P-10), frontend (P-11), autonomous scheduling of
rechecks/operations (P-12), real deployment adapters, real platform
integrations, PDF assets (no dependency), the `productized_service`
template's end-to-end exercise.

## 28. Outstanding risks

- The owner's target hardware is CPU-only (P-04 verdict): irrelevant
  to P-06 (deterministic, no inference), but it bounds P-12 ambitions.
- Host RAM pressure on this VM queues nonessential agent creation
  under the P-01 admission guard; tests/smoke use the established
  test-suite setting, disclosed in both.
- Template quality is only as good as the opportunity data; the
  eligibility gate is the control, and it is deliberately strict.

## 29. Files changed

New: `backend/app/business/` (11 modules), `backend/app/api/routes/
business.py`, `backend/app/api/schemas/business.py`,
`backend/app/database/models/business.py`,
`backend/app/database/repositories/business.py`,
`backend/app/database/migrations/versions/a8d7e0c717b4_*.py`,
`backend/scripts/p06_smoke.py`, `backend/tests/{p06_support,
test_p06_unit,test_p06_integration,test_p06_scenarios,
test_p06_security}.py`, 12 docs (audit ×2, architecture ×7, security
×1, operations ×2, testing ×1, this report, smoke transcript).
Modified: `app/core/application.py`, `app/main.py`,
`app/events/events.py`, `app/database/models/__init__.py`,
`app/execution/{schemas,workflows}.py` (additive, §5 above),
5 test files (head pins only), `docs/PHASE_TRACKER.md`, `README.md`.

## 30. Acceptance criteria evidence (§34)

Business foundation — audit ☑ (§2); P-03 integration ☑ (eligibility
consumes P-03 only; Scenario D); registry ☑; eligibility gate ☑
(matrix tests + D); templates ☑ (validation tests); lifecycle ☑
(Scenario E); workspace isolation ☑ (Scenario G, test 2).
Blueprint/strategy — generation ☑; customer definition ☑ (blueprint
section + readiness A); value proposition ☑; model framework ☑ (§9
doc + financial tests); assumption register ☑; evidence traceability
☑ (§22 rows + report separation inherited from P-03).
Product creation — registry ☑; PRD generation ☑ (product_spec asset);
MVP scope ☑ (spec core/excluded features + requirements); development
workflow ☑ (P-05 workflow runs); quality checks ☑ (§12 review);
service workflows — **partial**: `productized_service` is registered/
validated but not exercised end-to-end (declared prepared-only).
Assets — registry ☑; brand management ☑ (brand guide asset + dimension
C); usage-rights metadata ☑ (test 13); workspace integration ☑ (hash
verification); asset approval controls ☑ (draft status + governed
grants; no asset leaves draft in staging).
Website/distribution — planning ☑; creation "where adapters are
available" ☑ (local package via filesystem/documents adapters;
deployment adapter does not exist — stated, not hidden); verification
☑ (local, via execution reads); channel evaluation ☑; external
publishing approval enforced ☑ (gates + test 9).
Operations/launch — acquisition planning ☑ (drafts only); support
preparation ☑; playbook ☑; readiness engine ☑; hard blockers ☑
(Scenario F); owner launch approval ☑ (Scenario J, test 4);
transitions validated ☑ (Scenario E).
Integration/governance — P-01…P-05 integration ☑ (§3 + 300 regression
tests green); P-07 interface prepared ☑ (§23); security tests pass ☑
(16/16); existing tests pass ☑ (300/300); Windows documentation ☑
(§25, marked unverified); no critical unresolved regression ☑.

## 31. Recommended next development phase

**P-07: Financial Intelligence Engine** — only after the owner accepts
this gate. P-06 deliberately stops at the financial boundary: P-07
inherits the validated financial-input payloads and owns collected-
revenue truth.

## The three-way distinction (§35, explicit)

1. **Locally created business package** — ACHIEVED, for fixture
   businesses only: files in an isolated workspace, hash-verified,
   readiness-assessed, owner-approvable.
2. **Deployed business** — NOT achieved for anything: no deployment
   adapter exists; `deployed` and `publicly_available` are false
   everywhere, including for the Scenario J demonstration business.
3. **Operational business with revenue** — NOT achieved and NOT
   claimed: the one `OPERATIONAL` transition (Scenario J) is a labelled
   staging demonstration over a local package with
   `revenue_asserted=false`. No customer exists; no money moved; no
   revenue was recorded anywhere — the schema makes it impossible.

**No launch was fabricated. No real business was created.**
