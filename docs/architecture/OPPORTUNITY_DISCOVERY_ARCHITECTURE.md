# P-03 — Opportunity Discovery Architecture

**Status:** Implemented in staging (P-03 build, 9 Nov 2026). Discovers and evaluates; never launches, spends, registers accounts or sends messages (§26/§33).

## Shape

```
Owner brief (budget, geography, categories, optional P-02 mission link)
  -> discovery (seed candidate library = hypotheses, validation level 0)
  -> initial screening (duplicate -> DUPLICATE; compliance prohibited ->
     BLOCKED_BY_COMPLIANCE; startup class > owner budget -> INCOMPATIBLE)
  -> research sessions (P-01 tasks, handler `opportunity.research` only)
       -> registered sources via adapters -> injection scan -> evidence
       -> corroboration / contradiction pass
  -> market analysis -> competitor analysis -> commercial analysis
  -> deterministic scoring (scoring-v1 config, ADR-005) + hard rejections
  -> validation levels 0-5 (computed from evidence, never asserted)
  -> structured report (facts / estimates / recommendations separated)
```

## Modules (`backend/app/opportunities/`)

| Module | Responsibility |
|---|---|
| `service.py` | `OpportunityService` — orchestration, lifecycle, research execution, scoring/validation entry points, reporting |
| `constants.py` | Categories (§6), evidence vocabularies (§9), revenue models (§12), system capabilities (§7.5) |
| `lifecycle.py` | §17 state machine + duplicate slug key |
| `sources.py` | Transports + adapters (§8) — see RESEARCH_SOURCE_ARCHITECTURE |
| `seed_data.py` | Candidate library, source catalogue, owner-provided fixture documents (labelled) |
| `evidence.py` | Corroboration, contradiction, freshness, evidence quality, gaps (§9/§19) |
| `analysis.py` | Market / competitor / distribution derivations (§10/§11/§14) |
| `commercial.py` | Deterministic finance (§13) |
| `compliance.py` | Prohibited + high-risk screening (§15) |
| `scoring.py` | §16 dimensions, hard rules, recommendations (ADR-005) |
| `validation.py` | §18 levels 0–5 evidence gates |
| `schemas.py` | Research task payload, capability assessment |

Persistence: `app/database/models/opportunities.py` (11 tables, migration `a8ddb3e7260d`), repositories in `app/database/repositories/opportunities.py`. API: `app/api/routes/opportunities.py` + `app/api/schemas/opportunities.py`.

## Integration boundaries (§25)

- **P-01** provides task execution (research runs only as tasks via the registered handler), permissions (deny-by-default; API gates `read_business_data` / `modify_business_data` / `modify_system_config`), approvals infrastructure, audit events, system events, monitoring.
- **P-02** provides mission intake and decision records. A brief may link a `mission_id`; P-03 writes `opportunity_discovery` / `opportunity_scored` / `opportunity_validated` decision records against it. **Known boundary (Stage-1 audit finding):** P-02's baseline planner cannot plan research missions (no template; no LLM configured), so P-03 does not depend on plan execution — extending the planner was judged P-02 scope creep and not done.
- **Modes:** emergency blocks research submission; simulation restricts research to seed/owner sources (no live fetching); supervised/controlled allow live fetching of registered public sources.

## Discovery methods (§7)

The candidate library is tagged by discovery method (problem-driven, demand-driven, competitor-gap, trend, capability-fit, budget-driven). Candidates are *hypotheses*: every candidate starts at validation level 0 with zero evidence, and the screening pipeline — not the generator — decides what survives. The library deliberately includes a case-variant duplicate, two budget-incompatible models, and one prohibited model so the rejection paths are exercised by real data, not just unit fixtures.

## Monitoring foundation (§24)

`schedule_recheck` registers a duplicate-prevented pending recheck session per opportunity, visible in `/opportunities/research-queue`. It does **not** auto-execute: recurring autonomous operations are P-12 scope. Freshness is otherwise handled by evidence freshness classification and explicit re-research.
