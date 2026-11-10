# P-13 Pre-Implementation Audit — Multi-business Coordination Engine

Stage 1 of the P-13 implementation strategy (§22), performed on the
accepted P-01–P-12 staging stack (backend 666/666, frontend 35/35,
153 database tables, migration head `3a77efe78faa`) before any
implementation code was written. Sources: direct inspection of the
P-04/P-06/P-07/P-08/P-09/P-10/P-12 code and models, the P-12
implementation report, and the phase tracker.

## 1. Existing architecture (what is already true)

### 1.1 Business identity and lifecycle (P-06)

- The authoritative business record is P-06's `businesses` table
  (name, slug, category, template, risk classification, eligibility,
  `is_fixture`, workspace, deployment truth fields). **P-13 must
  reference these rows, never copy them.**
- The only business state machine is P-06's
  (`app/business/lifecycle.py`): PROPOSED, ELIGIBILITY_REVIEW,
  BLUEPRINTING, BLUEPRINT_READY, APPROVAL_PENDING, PRODUCT_PLANNING,
  IN_DEVELOPMENT, INTERNAL_TESTING, DISTRIBUTION_PREPARATION,
  LAUNCH_REVIEW, READY_FOR_LAUNCH, LAUNCH_APPROVAL_PENDING,
  LAUNCHING, OPERATIONAL, PAUSED, BLOCKED, FAILED, ARCHIVED —
  transitions validated by `can_transition`, executed only through
  `BusinessCreationService.transition_business` behind P-01
  approvals. OPERATIONAL asserts nothing about customers or revenue.
- P-08 adds a *reading*, not a machine: overlay states
  (VALIDATING, BUILDING, LAUNCH_READY, EARLY_OPERATIONS, GROWING,
  STABLE, SCALING, OPTIMIZING, AT_RISK, RECOVERY, CLOSURE_REVIEW…)
  recorded on health snapshots, with `P06_TO_OVERLAY` as the base
  mapping, plus a pause control and closure flow (Level-4,
  owner-only). `SurvivalService.lifecycle()` already composes the
  two into one view.
- P-08 also already owns a `PortfolioService`
  (`app/survival/portfolio.py`): consolidated overview, channel/
  business concentration, **capital allocation proposals** and
  **resource allocation proposals** — proposals only, explainable,
  reserve-blocked. **P-13 must build on this, not re-implement it.**

### 1.2 Lifecycle mapping decision (§4 of the prompt vs reality)

The prompt's §4 lifecycle (IDEA → VALIDATING → APPROVED → BUILDING →
LAUNCHING → OPERATIONAL → OPTIMIZING → SCALING + PAUSED, AT_RISK,
BLOCKED, RESTRUCTURING, CLOSING, ARCHIVED) is a *portfolio-level
vocabulary*, not the implemented machine. Reconciliation (P-13
stores **no** lifecycle state of its own; the portfolio stage is a
pure derived label computed from P-06 status + P-08 overlay):

| P-13 §4 stage | Reality it derives from |
|---|---|
| IDEA | No business row exists — a P-03 opportunity / P-13 venture proposal |
| VALIDATING | P-06 ELIGIBILITY_REVIEW (overlay VALIDATING) |
| APPROVED | P-06 BLUEPRINT_READY / APPROVAL_PENDING (overlay APPROVED is a transient reading) |
| BUILDING | P-06 BLUEPRINTING…INTERNAL_TESTING (overlay BUILDING) |
| LAUNCHING | P-06 LAUNCH_REVIEW…LAUNCHING (overlay LAUNCH_READY/LAUNCHED) |
| OPERATIONAL | P-06 OPERATIONAL (overlay EARLY_OPERATIONS) |
| OPTIMIZING | P-08 overlay OPTIMIZING |
| SCALING | P-08 overlay SCALING (reachable only through P-08's evidence gates: verified collected revenue > 0 across ≥2 snapshots) |
| PAUSED | P-06 PAUSED and/or the P-08 pause control |
| AT_RISK | P-08 overlay AT_RISK (P-06 BLOCKED maps here at base) |
| BLOCKED | P-06 BLOCKED |
| RESTRUCTURING | P-08 overlay RECOVERY + P-08 recovery plans |
| CLOSING | P-08 overlay CLOSURE_REVIEW / CLOSED (owner-only closure flow) |
| ARCHIVED | P-06 ARCHIVED |

Consequence: a business can never appear "profitable" or "scaling"
in P-13 because a workflow finished — the labels derive from P-06
state and P-08 evidence-gated readings only.

### 1.3 Financial authority (P-07)

- `FinancialService` is the only ledger. Per business:
  `business_summary` (profile, revenue metrics with projected /
  booked / invoiced / **collected-verified** strictly separated,
  expenses, available cash, profitability, health, runway),
  `budgets.available_cash`, exchange rates with `convert_amount`
  preserving rate evidence.
- `FinancialService.consolidated(currency)` already sums *flow*
  measures (net collected, expenses, profit) across same-currency
  businesses and explicitly excludes internal transfers. It does
  **not** combine cash. P-13 portfolio finance = per-business
  `business_summary` rows + P-07 consolidated flows, with cash kept
  per-business and never summed (P-11 precedent: portfolio available
  cash renders "unavailable", never ₹0).
- P-07 already records *internal transfers* between a business's own
  accounts. P-13's internal cost allocations are a different thing —
  management accounting between businesses — and are stored P-13-side
  with `kind = INTERNAL_ALLOCATION`, following the P-08 precedent of
  amount-carrying *proposal* records (`CapitalAllocationProposal`
  has `amount_minor`). They are not journal entries, create no
  balances, and P-07 never reads them; a test proves P-07 totals are
  byte-identical before and after an allocation is recorded.
- P-07 `assert_business_access`: owner/system unrestricted; an agent
  reaches only the business its P-01 agent row is registered to;
  denials are audited. P-13 mirrors this semantics exactly.

### 1.4 Agents (P-04 / P-12)

- Agent identity is the P-01 `agents` row (`business_ref` = home
  business). P-04 owns creation/capabilities; P-06 has
  `business_agent_assignments` (business-internal roles); P-12 owns
  workflow assignments. **No scoped cross-business assignment record
  exists** — this is a genuine P-13 gap (§8): P-13 adds
  `portfolio_agent_assignments` and `cross_business_permissions` as
  coordination records; enforcement is by live status checks in
  P-13's access-check path, not by copying P-04 permissions.
- Credentials: P-05's credential broker + P-10's secret registry are
  metadata-only and business-scoped. P-13 never touches credential
  material; "credentials" is a *never-grantable* data category in
  every P-13 grant surface.

### 1.5 Memory (P-09)

- `memory_records` carry `business_id` + `access_scope`
  (OWNER_ONLY … ORGANIZATION_SHARED) + sensitivity, and retrieval
  is already principal-scoped (`policy.can_read` hard-filters before
  ranking). P-09 ingestion rejects secrets before storage.
- P-13 knowledge sharing therefore needs no new memory store: the
  shared-knowledge view exposes only `ORGANIZATION_SHARED` records,
  and promoting a lesson creates a *new* ORGANIZATION_SHARED record
  through `MemoryService.store.create` (owner-only, restricted /
  credential-like content refused by P-09's own gate and by P-13's
  category check).

### 1.6 Governance (P-01 / P-10)

- Approvals are P-01's hash-bound, single-use `ApprovalService`;
  authorization composition is P-10's `PermissionBroker.authorize`
  (mode → restriction → business-scope → engine gates). P-13 adds
  **no** approval store and **no** permission engine: portfolio
  decisions are recorded as status fields on P-13 rows, sensitive
  portfolio writes are owner-only at the service layer (the P-07
  pattern), and every mutation writes a P-01 `AuditEvent` row via
  `AuditRepository` (the house pattern).
- Emergency modes are P-10's; portfolio survival mode (§12) is an
  advisory P-13 state only — it flags, recommends and blocks new
  *discretionary P-13 allocations*; it cannot pause businesses
  (P-08), stop operations (P-10/P-12) or move funds (P-07).

### 1.7 Operations (P-12)

- `OperationsService.create_workflow(principal, data)` creates a
  governed workflow in one business (or business-less) from a
  structured definition; `drive_workflow` runs the full pipeline.
  P-13 portfolio workflows (§13) are coordination rows that create
  one P-12 sub-workflow per participating business and link them;
  execution truth stays in P-12.

### 1.8 Frontend (P-11)

- Vite + React 19 + TypeScript SPA in `frontend/`, hash router,
  shared components (`components/ui.tsx`, `cards.tsx`, `shell.tsx`),
  typed API client (`lib/api.ts`), views registered in `App.tsx`
  and nav in `shell.tsx`. P-12's `Autonomy.tsx` (tabbed section) is
  the pattern for the P-13 Portfolio section. Backend serves the
  built bundle at `/app`.

## 2. Gaps P-13 must fill (nothing else)

1. Portfolio registry: portfolios, business membership, analytical
   grouping, portfolio objectives — **none exist**.
2. Business relationship graph with governed states (§14) — none.
3. Cross-business opportunity detection + an evidence gate that
   rejects unsupported synergy (§6/§7) — none.
4. Shared service registry, scoped access grants, usage records
   (§9) — none.
5. Internal management-accounting allocations (§9/§11) — none
   (P-07 internal transfers are intra-business and different).
6. Portfolio resource quotas + capacity allocations with
   anti-monopolization (§10) — P-08 has *proposals* for capital/
   resources; enforceable quota/allocation records are new.
7. Cross-business permission grants + shared-agent assignments with
   expiry and verified revocation (§8/§20) — none.
8. Portfolio workflow coordination over P-12 (§13) — none.
9. Portfolio risk assessments, strategic plans and stored portfolio
   reports (§12/§16/§18J) — P-08 computes concentration live;
   persisted assessments/reports are new.
10. New-venture proposals with anti-duplication checks (§17) —
    none (P-03/P-06 keep their own authorities).

## 3. Conflicts and how they are resolved

- **§4 lifecycle vs P-06 machine** → derived-label mapping (§1.2);
  no parallel state stored, no P-06 writes from P-13.
- **§11 "consolidated reporting" vs the no-summed-cash lock** →
  flows (collected/expenses/profit) consolidate per currency via
  P-07; cash is listed per business and explicitly never combined.
- **§10 resource allocation vs P-08 resource proposals** → P-08
  proposals remain the recommendation path for agent/capital
  resources; P-13 quotas/allocations govern shared-infrastructure
  capacity units (inference slots, API quota, storage, service
  capacity) — a disjoint resource domain, documented as such.
- **§16 "business priority ranking" vs §16's own rule** (never by
  projected revenue alone) → ranking is owner-set
  `strategic_priority` on membership; intelligence *suggests*
  adjustments with verified-profitability evidence, never rewrites.
- **§19 entity list** is explicitly "proposed, not mandatory":
  19 tables are implemented (list in the implementation report);
  `portfolio_decisions` and `portfolio_scenarios` are **not** built —
  decisions live as governed status fields on the owning rows
  (recommendations, opportunities, ventures, allocations, access),
  and scenario comparison is computed on demand. This keeps one
  record per decision, on the row it decides.

## 4. Risks

- **Isolation theatre**: portfolio aggregates could leak business
  detail to agents. Mitigation: intelligence/finance/comparison
  service methods are owner/system-only; agent surfaces are exactly
  two checked functions (`check_agent_access`,
  `check_service_access`) that fail closed and audit denials.
- **Money creep**: any P-13 amount must stay management accounting.
  Mitigation: allocations are typed, excluded from every P-07 read,
  and a regression test pins P-07 totals around allocation writes.
- **Duplicate authority**: mitigated by §1/§3 decisions; structural
  tests assert P-13 tables hold no FK-free copies of business
  identity fields beyond `business_id` references, and that no
  P-13 table is named like a ledger/approval store.
- **Scale of suite**: full backend run is ~666 tests on a 512 MB
  tmpfs — the established basetemp + pruner method is mandatory.

## 5. Implementation strategy (§22 stages mapped)

Stages 1–9 as in the prompt. Build order: models + migration →
repositories → service modules (registry, relationships,
intelligence, shared services, resources, access, workflows,
finance views, planning/reports/ventures) → facade + wiring →
routes + schemas → frontend Portfolio section → tests per stage →
smoke → docs. Additive migration chained from `3a77efe78faa`;
all 666 backend + 35 frontend tests must stay green; pre-existing
test changes only for migration-head / table-count pins, each with
a "P-13 disclosure" comment.
