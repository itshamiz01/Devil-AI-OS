# P-13 Architecture — Multi-business Coordination Engine

P-13 is a **coordination layer**, not a new authority. It sits on
top of P-01–P-12 and owns exactly one thing: portfolio state.

```
                        ┌────────────────────────────┐
                        │  Command Center (P-11)     │
                        │  + Business Portfolio view │
                        └─────────────┬──────────────┘
                                      │ /api/v1/portfolio/*
                        ┌─────────────▼──────────────┐
                        │  PortfolioService (P-13)   │
                        │  registry · relationships  │
                        │  intelligence · services   │
                        │  resources · access        │
                        │  coordination · finance    │
                        │  planning                  │
                        └──┬───┬───┬───┬───┬───┬─────┘
              reads/writes │   │   │   │   │   │ reads (scoped)
        ┌──────────────────▼┐ ┌▼─────────┐ ┌▼──────────┐ ┌▼────────┐
        │ P-06 businesses   │ │ P-07     │ │ P-08      │ │ P-12    │
        │ identity+lifecycle│ │ money    │ │ survival  │ │ execute │
        └───────────────────┘ └──────────┘ └───────────┘ └─────────┘
                        ┌──────────────┐  ┌──────────────┐
                        │ P-09 memory  │  │ P-01/P-10    │
                        │ (ORG_SHARED  │  │ audit,       │
                        │  only)       │  │ permissions  │
                        └──────────────┘  └──────────────┘
```

## Composition

`PortfolioService` (facade) is composed of nine mixins in
`backend/app/portfolio/`, one per prompt area, sharing facade
helpers: owner gates, a per-business read check mirroring P-07's
rule, a P-01 audit writer, and owner-governed settings stored in
P-01's `system_config` (`portfolio.settings`). It is constructed
in `Application.startup` after P-12 with references to the P-06,
P-07, P-08, P-12, P-09, P-04 and P-03 services — all calls go
through those services' public methods; P-13 never reaches into
another engine's tables for business/financial truth (its own
repositories serve only its own 19 tables).

## Authority map (unchanged by P-13)

| Concern | Authority | P-13's relationship |
|---|---|---|
| Business identity, lifecycle | P-06 (+ P-08 overlay readings) | references businesses; derives the §4 stage label at read time |
| Money, ledger, budgets | P-07 | reads summaries/metrics live; stores no financial records; never transfers |
| Opportunity pipeline | P-03 | venture handoff creates a level-0 opportunity |
| Agents | P-04/P-01 registry | scoped assignments reference agent ids |
| Execution | P-05/P-12 | portfolio workflows link P-12 sub-workflows |
| Memory | P-09 | reads ORGANIZATION_SHARED records only |
| Approvals, permissions, audit | P-01/P-10 | decisions are governed status fields on P-13 rows; every mutation audited via P-01 |
| Survival/scaling decisions | P-08 | concentration detector builds on P-07 figures under P-13 threshold config; P-08's own proposals untouched |

## Data

19 additive tables (migration `d02b4208d228`); see the
implementation report §4. Decisions live as status fields on the
rows they govern (opportunities, recommendations, access,
allocations, ventures) — there is deliberately no
`portfolio_decisions` table, and no `portfolio_scenarios` table
(strategic scenarios are computed views, not stored fictions).

## Lifecycle derivation (§4)

`constants.portfolio_stage(p06_state, overlay_state)`: non-
operational P-06 states map directly (PROPOSED→IDEA …
ARCHIVED→ARCHIVED); only when P-06 says OPERATIONAL may the P-08
overlay refine the label (GROWING→OPERATIONAL, OPTIMIZING,
SCALING, AT_RISK, RECOVERY→RESTRUCTURING…). The mapping is total
over P-06's 18 states and is unit-tested, including the honesty
cases (a building business can never be labelled operational).
