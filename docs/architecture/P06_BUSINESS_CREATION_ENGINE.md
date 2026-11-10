# P-06 Business Creation Engine — Architecture

**Status:** built and verified in staging (awaiting owner gate).
**Package:** `backend/app/business/` · **API:** `backend/app/api/routes/business.py`
under `/api/v1/business/...` · **Migration:** `a8d7e0c717b4` (additive,
revises `6ffcc7e899fa`) · **Tables:** 18 new (63 total at head).

## Position in the system

P-06 converts P-03-validated opportunities into structured, launch-ready
**local business packages**. It is an orchestration layer only:

| Concern | Owner | P-06's use |
|---|---|---|
| Approvals | P-01 `ApprovalService` (hash-bound) | creation, declaration, blueprint, launch approvals — no `business_approvals` table (audit §5) |
| Permissions/audit/events | P-01 engine, `audit_events`, event bus | route guards + service audits; business events join the persisted critical set where §28 demands |
| Opportunities + validation levels | P-03 | the ONLY input source; levels are computed by `OpportunityService.validate()`, never asserted |
| Agents | P-04 factory | reuse-first portfolio staff; business binding lives in `business_agent_assignments` |
| Execution | P-05 `ExecutionService` + `WorkflowEngine` + managed workspaces | EVERY creation step; templates ARE workflow definitions |
| Financial truth | P-07 (future) | P-06 prepares validated financial inputs only |

One additive extension to P-05 was required and made (disclosed in the
implementation report): `WorkflowRunIn.business_ref`, propagated through
the run checkpoint to step requests. Without it, P-05 workflows could not
write to `businesses` workspaces at all (their policy requires a
`business_ref` on the request, and the engine never set one). Default
`None` preserves P-05 behaviour exactly for all pre-existing runs.

## Modules

- `constants.py` — settings key/defaults, §6 decisions, §8.5 assumption
  statuses, §20 results, denylists, approval action names.
- `lifecycle.py` — §19 states/transitions + pause semantics (pure data).
- `eligibility.py` — §6 evaluator (pure function over P-03 facts).
- `templates.py` — seed template definitions + validation against the
  live P-05 tool registry.
- `platform_gates.py` — §14 gate catalogue + deterministic evaluation.
- `financial.py` — §9 financial values, deterministic arithmetic, the
  P-07 payload builder with the revenue/profit rejection boundary.
- `blueprint.py` — deterministic document generation from stored data,
  with the secret-redaction pass.
- `readiness.py` — §20 dimensions A–H (pure function over facts).
- `service.py` — `BusinessCreationService`: settings, templates,
  eligibility, creation, lifecycle, declarations, blueprint, creation
  runs, channels/gates, readiness, launch, isolation, evidence,
  assumptions, campaigns (draft-only), financial inputs, engine status.
- `fixtures.py` — fixture-opportunity builder driving P-03's machinery
  (used by tests and labelled everywhere).

## Creation flow

1. **Eligibility** (§6): fresh evaluation over the P-03 report + a
   `validate()` call; persisted; six possible decisions.
2. **Creation approval**: hash-bound P-01 approval for
   (opportunity, template, template version), decided by an owner
   principal (an agent can never approve, §21).
3. **Business row** created in `PROPOSED` → `ELIGIBILITY_REVIEW` →
   `BLUEPRINTING`; the template version is pinned; `is_fixture` is
   derived from the opportunity's FIXTURE labelling and stored.
4. **Pre-declaration** (Constitution gate): success criteria, budget
   cap, duration, minimum test volume. No approved declaration → the
   creation workflow cannot start.
5. **Blueprint** (§8): deterministic 16-section blueprint, assumption
   register, product + requirements, financial inputs.
6. **Agents**: factory reuse-first (portfolio staff model), governed
   capability grants performed under the creation approver (the owner).
7. **Creation run**: the pinned template's workflow executes through
   P-05 into the business's own workspace (`business:<id>`); assets are
   registered and hash-verified through execution reads; a quality
   review is recorded by the QA assignment.
8. **Channels**: evaluated with §14 platform gates recorded as business
   evidence; publish attempts return gate outcomes, never publish.
9. **Readiness** (§20) and **launch** (§19/§21): readiness READY-family +
   hash-bound owner launch approval + declaration → `OPERATIONAL`,
   which in staging records `deployment_state=local_package_only`,
   `public_availability=false`, and asserts no revenue.

## Modes (§24)

- **Simulation:** blueprint/declaration work proceeds; the creation
  workflow's side-effecting steps are refused by the P-05 policy, the
  run cannot complete, and the business is marked BLOCKED (Scenario H).
- **Supervised/Controlled:** the flow above (controlled in staging).
- **Emergency:** creation and creation runs are halted at the P-06 gate.

## What does not exist (by design)

No payment/purchase/wallet code; no sending or posting path; no
deployment adapter; no frontend (P-11); no LLM calls; no direct
file/subprocess/HTTP access from P-06 services.
