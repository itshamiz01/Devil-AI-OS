# P-13 Implementation Report — Multi-business Coordination Engine

**Status: BUILT AND VERIFIED IN STAGING (10 Nov 2026).** Backend
**713/713 tests in one run on final code** (666 P-01–P-12 regression
+ 47 new P-13), frontend **40/40** (35 + 5 new), live uvicorn smoke
**20/20**. P-13 is a coordination and intelligence layer over
P-01–P-12: it owns portfolio state only. Business identity and
lifecycle remain P-06's, money remains P-07's alone, execution
remains P-12's, memory remains P-09's, approvals/permissions remain
P-01/P-10's. **P-13 is NOT production-ready** (see §19/§20): it is
verified in Linux staging on labelled fixtures, with no real
businesses, no real LLM and no Windows run (P-00 still open).

## 1. Executive summary

AUTONOMUS can now coordinate several independent businesses as one
portfolio without ever merging them into one account. An owner can
register businesses into portfolios (a business keeps exactly one
P-06 record, however many portfolios group it), record governed
relationships between them, detect cross-business opportunities
with deterministic evidence-based detectors, share infrastructure
services under per-business revocable access, allocate finite
shared resources under quotas and an anti-monopolization cap,
grant agents scoped, expiring cross-business data access, run
cross-business workflows through P-12 with per-business authorized
contributions, and read portfolio finance/risk/strategy that is
computed live from P-07/P-08 — never stored, never combined where
combining would lie (cash is never summed across businesses;
internal cost allocations are labelled internal accounting and
provably move no P-07 money). Every §21 acceptance scenario is a
named, passing test.

## 2. Pre-implementation audit

`docs/multi-business/P13_PRE_IMPLEMENTATION_AUDIT.md`. Headlines:
the registry must reference P-06 businesses (no second business
table); the §4 lifecycle list is a **derived label** over P-06's
18-state machine + P-08's overlay (mapping table in the audit and
in `app/portfolio/constants.py`) — a business is never labelled
operational by P-13; P-08 already had a PortfolioService to build
on rather than duplicate; `portfolio_decisions` and
`portfolio_scenarios` tables were deliberately NOT built (decisions
are governed status fields on the rows they decide; scenarios are
computed on demand). 19 tables were built of the §19 list.

## 3. Architecture implemented

New backend package `backend/app/portfolio/` — a `PortfolioService`
facade composed of nine mixins, one per prompt area: `registry`,
`relationships`, `intelligence`, `shared_services`, `resources`,
`access`, `coordination`, `finance`, `planning`, sharing helpers
(owner gates, per-business read mirror of P-07, P-01 audit writes,
owner-governed settings in `system_config`). Repositories in
`app/database/repositories/portfolio.py`; models in
`app/database/models/portfolio.py`; routes in
`app/api/routes/portfolio.py` (73 endpoints under
`/api/v1/portfolio`); schemas in `app/api/schemas/portfolio.py`.
Wired in `Application.startup` after P-12, seeded settings, no new
background loop (coordination is on-demand; P-12's loop remains the
only scheduler).

## 4. Portfolio data model

Additive migration **`d02b4208d228`** (revises `3a77efe78faa`),
19 new tables, cycle **153 → 172 → 153 → 172** test-verified
(counts include `alembic_version`; model metadata 152 → 171):
`business_portfolios`, `portfolio_business_memberships`,
`portfolio_objectives`, `business_relationships`,
`cross_business_opportunities`, `portfolio_recommendations`,
`shared_services`, `shared_service_access`, `shared_service_usage`,
`internal_cost_allocations`, `resource_quotas`,
`resource_allocations`, `cross_business_permissions`,
`portfolio_agent_assignments`, `portfolio_workflows`,
`portfolio_workflow_participations`, `portfolio_risk_assessments`,
`portfolio_reports`, `new_venture_proposals`. **No P-13 table is a
ledger**: the only money-typed column is
`internal_cost_allocations.amount_minor` (management accounting,
precedent: P-08's allocation proposals), which P-07 never reads.

## 5. Business isolation architecture

See `P13_BUSINESS_ISOLATION.md`. Core: portfolio aggregates are
owner/system-only; per-business reads mirror P-07's rule (owner/
system, or the agent whose P-01 row is homed to that business);
agents reach foreign business data only through the two checked
surfaces (`check_agent_access`, `check_service_access`), which
fail closed and audit every denial as
`portfolio.isolation_violation`. Six categories are never
grantable anywhere (credentials, customer records, financial
records, business memory, secrets, platform accounts) — naming one
is a validation error on grants, assignments and workflow
contributions alike. Relationships grant nothing by themselves
(named test). Memory crosses businesses only when a P-09 record is
explicitly ORGANIZATION_SHARED (named test).

## 6. Shared agent architecture

Scoped assignments (BUSINESS scope with grantable categories;
PORTFOLIO scope restricted to aggregate categories —
aggregate_metrics, operational_status, service_utilization,
generalized_lessons), allowed tools, a P-07 budget *reference*
(never money), mandatory expiry, immediate revocation. Direct
grants name one agent, one source business, a target context,
categories, purpose and expiry. Revocation and expiry are both
verified end-to-end in Scenario 15 and the security suite.

## 7. Shared services

See `P13_SHARED_SERVICES.md`. Registry of shareable infrastructure
(11 kinds); per-business access REQUESTED → APPROVED → ACTIVE,
revocable; usage recorded only against ACTIVE access (refusals
audited); usage feeds cost allocation. Internal allocations are
computed four ways (equal, usage_based, fixed share_bps,
priority_weighted from membership strategic priority) and written
as one row per charged business in a decided-as-a-unit batch,
permanently `kind=INTERNAL_ALLOCATION`.

## 8. Resource allocation

Finite owner-configured capacities (settings: inference slots,
API quota units, storage, service capacity, agent hours — declared
capacities for the single-machine deployment, labelled as such,
not telemetry). Per-business quotas; proposal checks quota,
capacity and the anti-monopolization share cap (default 50%);
APPROVED and ACTIVE both count against capacity so approval cannot
over-commit; portfolio survival mode blocks discretionary
allocations; release/reclaim frees capacity, and reclamation
revokes allocations of businesses that left the portfolio.

## 9. Portfolio intelligence

Six deterministic detectors (shared channel, shared-service fit,
complementary operational businesses, duplicated product lines,
concentration, organization-shared lessons), signature-deduped so
re-analysis is idempotent. The **evidence gate**
(`validate_evidence`) is mechanical: evidence must cite trusted
system sources (p07.*, p08.*, p06.*, p03.*, p13.*, p09.*) or an
owner attestation supplied by the owner; anything else is rejected
(Scenario 6). Speculative items are stored SPECULATIVE and cannot
be accepted/validated. Recommendations carry evidence, rationale,
confidence and an owner-decision requirement. No LLM is used.

## 10. Financial reporting

See `P13_PORTFOLIO_FINANCE.md`. All figures are read live from
`FinancialService` at request time; nothing financial is copied
into P-13 storage. Collected/projected are separate fields
everywhere. Cash is per-business; `combined_available_cash` is
structurally `null` with the reason attached. Consolidated-style
totals are sums of the per-business P-07 flow figures shown, same
currency only, labelled as such (P-07's own consolidated view
excludes internal transfers). Scenario 12 proves an approved
internal allocation leaves P-07's consolidated output byte-equal.

## 11. Risk management

Concentration view (verified-collected shares vs the configured
60% threshold) and persisted risk assessments: per-business levels
from P-08 overlay readings, P-06 blocked/failed states, pause
state and concentration; portfolio findings add shared-service
single points of failure (a non-AVAILABLE service used by ≥2
businesses) and the survival-mode flag. Portfolio survival mode is
advisory: it flags and blocks discretionary P-13 allocations; it
pauses nothing and moves no money (pausing stays P-08's owner
path).

## 12. Cross-business workflows

Coordination records link one P-12 workflow per participating
business, created inside that business's own scope. Participation
starts PENDING; every business's contribution must be explicitly
authorized (per business, audited) before start; contribution
categories come from a closed shareable set. Participation status
derives from the linked P-12 workflow at read time; the roll-up
never changes a business's lifecycle (asserted in Scenario 9).

## 13. Security controls

See `P13_SECURITY_MODEL.md`. Owner-only writes and decisions
(service-enforced, route permissions mirror the house pattern:
read/modify/approve). Article 0 held: portfolio intelligence and
settings cannot touch P-10 policy, P-01 approvals or P-07 limits —
the settings surface governs portfolio thresholds and capacities
only (named test). Every mutation and every isolation denial is a
P-01 audit event. No new auth system; no secrets stored (grants
name categories, never values).

## 14. APIs and database changes

73 endpoints under `/api/v1/portfolio` — full list in
`P13_API_REFERENCE.md`. Database: one additive migration
(`d02b4208d228`), 19 tables, no changes to existing tables.
Frontend: one new view + nav entry + route. Pre-existing test
changes: exact-count pins in `test_p11_integration.py` (152→171)
and `test_p12_integration.py` (152→171 + cycle retargeted to stop
at the P-12 head explicitly) and migration-head pins in
`test_p02/p03/p04/p05_integration.py` (`3a77efe78faa` →
`d02b4208d228`) — each with a "P-13 disclosure" comment, strictness
preserved (exact counts both directions).

## 15. Command Center integration

The P-11 React app gains a **Business Portfolio** view (nav:
Portfolio section) with the ten §18 areas as tabs — Overview,
Map, Comparison, Intelligence, Resources, Finance, Services,
Risk, Strategy, Reports — built from the existing components and
design tokens, no redesign. Real API data only; the finance tab
shows "Not combined" for cash with the API's own explanation;
speculative opportunities render their SPECULATIVE badge; actions
show success only after backend confirmation (reload-on-success,
error surfaced on refusal). Bundle: 362 kB JS / 104 kB gzip
(was 328/96 at P-11, 337/99 at P-12 — the increment is the one new
view).

## 16. Tests executed

Backend (pytest, one full run on final code, tmpfs basetemp +
pruner; /tmp 2% before and after): **713 passed** = 666 regression
+ 47 new P-13: 10 unit (lifecycle derivation, evidence gate,
category/expiry validators), 13 integration (migration cycle
153→172→153→172, metadata exact count, registry, relationships,
service access flow, allocation maths for all four methods,
resource quota/capacity/cap, reclaim, HTTP round-trip + auth),
7 security (owner-only writes, agent aggregate blindness, grant
expiry, grant scoping, home-business surface, settings cannot
touch security/money, relationships grant nothing), **17 scenarios
(§21, named, below)**. Frontend (Vitest, one full run): **40
passed** = 35 regression + 5 new Portfolio tests. Live smoke
(real uvicorn + built frontend, seeded through governed paths):
**20/20** — transcript at `docs/reports/P13_SMOKE_EVIDENCE.txt`.
Two real defects were caught by P-13's own verification and fixed:
a variable-shadowing bug in `portfolio_finance` that replaced the
per-business rows with allocation rows once an allocation was
approved (broke report serialization; regression assertion added
to Scenario 12), and the smoke's initial 422 expectation (house
convention is ValidationError → 422; test corrected, code was
right). The first full-suite run additionally caught a missed
pre-existing pin — `test_p12_migration_cycle`'s first
upgrade-to-"head" step still expected the P-12 total of 153; it
now targets the P-12 head explicitly with a P-13 disclosure
comment (the P-13 cycle test asserts the true head, 172). The
final full run on final code is green: 713/713.

## 17. Acceptance scenario results (§21)

All 17 PASS as named tests in `tests/test_p13_scenarios.py`
(Scenario 17's UI half in `frontend/src/views/Portfolio.test.tsx`
+ smoke §7):

1. Independent operation of two businesses — PASS
2. Shared service reduces duplication — PASS
3. Cross-business opportunity detected — PASS
4. Unauthorized cross-business access blocked (+ audited) — PASS
5. Credentials never shared (grants, assignments, contributions,
   memory) — PASS
6. Unsupported synergy rejected; speculation labelled, never
   acceptable — PASS
7. Resource monopolization prevented (share cap + capacity) — PASS
8. Revoked business loses shared service (usage + agent check) — PASS
9. Cross-business workflow isolated (per-business authorization,
   P-12 sub-workflows in own scopes, no access created, lifecycle
   untouched) — PASS
10. Failing business contained (flagged, survival mode blocks
    discretionary allocations, healthy business untouched, no
    transfer capability exists) — PASS
11. Concentration risk detected (view, risk findings, analysis
    recommendation) — PASS
12. Internal allocations never external payments (P-07
    consolidated byte-equal) — PASS
13. Comparison without combining finances — PASS
14. Venture never auto-created (proposal → approval → P-03
    handoff; business count unchanged throughout) — PASS
15. Shared agent revocation (grant and assignment) — PASS
16. Report reflects actual state (totals equal live API; sources
    named) — PASS
17. Command Center displays portfolio accurately (API-value tests
    + frontend rendering tests + served-bundle smoke) — PASS

## 18. Performance findings

No load testing was performed (out of scope for staging). Observed:
full backend suite 713 tests in ≈4 min wall on the shared VM;
portfolio views compose live P-06/P-07/P-08 reads per member, so
overview/finance cost grows linearly with membership (fine at
portfolio scale; no caching layer was added, deliberately — cached
financial figures would risk staleness against P-07 truth).
Analysis is idempotent and detector cost is quadratic only in the
complementary/duplication pair checks, capped at 10 pairs.

## 19. Known limitations

- **No real businesses or real data**: everything is verified on
  labelled P-06 fixture businesses and P-07 fixture money paths.
- **No real LLM**: detectors are deterministic; §6's "intelligence"
  is rules over system evidence, honestly labelled.
- **Capacities are owner-declared**, not measured telemetry; the
  resource view says so.
- **Per-channel revenue attribution is not fabricated**: the
  concentration view lists channels present but attributes revenue
  shares per business only (P-07 has no per-channel collected
  split for multi-channel businesses).
- **Survival mode is advisory** (flags + allocation blocking). It
  does not pause businesses, stop workflows or redirect funds —
  those remain the P-08/P-12/P-10 owner paths.
- **PDF export NOT IMPLEMENTED** (JSON export only), consistent
  with P-07/P-11.
- **No headless browser in staging**: rendered-viewport checks of
  the new view were not executed (carried P-11 limitation); the
  view is component-tested with stubbed APIs and the built bundle
  is smoke-verified as served.
- **Windows unverified** (P-00): the target machine has never run
  the stack.
- Venture handoff creates a P-03 opportunity at validation level
  0; whether P-06 ever creates the business is governed entirely
  by the existing P-03→P-06 gates and owner approvals.

## 20. Unresolved risks

- Grant target semantics: a grant records source + target business
  (defaulting the target to the agent's home business at grant
  time). An agent re-homed to another business keeps grants whose
  target no longer matches its home — checks then deny (fail
  closed), but the owner should re-issue grants after re-homing;
  no UI warns about this yet.
- APPROVED-but-never-activated resource allocations hold capacity
  indefinitely (they count against it by design); reclamation only
  fires for departed members. An expiry for allocations is a
  sensible future addition.
- Risk scores are coarse signal counts (0–7 mapped to four
  levels), never calibrated against a real business.
- Detector quality is unproven on real portfolios: pair caps and
  the shared-channel detector will need owner feedback once real
  businesses exist.

## 21. Recommended next steps

1. Owner gate for P-11 + P-12 + P-13 (combined confirmation).
2. P-00 closure (Windows machine evidence + repo creation) —
  still the programme's oldest open item; recommended private repo
  now that P-10 has passed.
3. P-14 Integration Audit per the master plan — including the
  grant re-homing warning and allocation expiry noted above.
4. First real-business pilot through the existing gates (one
  business, real P-07 profile, real revenue) before trusting
  detector output for decisions.
