# P-00 Deliverable D — System Architecture Blueprint

## Overview

Modular monolith first (Python + FastAPI core), a thin Tauri desktop shell, a React/TypeScript command center, shared local inference (Ollama), SQLite persistence, and a deterministic **Policy & Permission Layer** that sits between all intelligence and all execution. The AI model is never the security authority (P-00 §8).

## Components (Constitution §4 A–J + operations)

| # | Component | Responsibility | Inputs | Outputs | Depends on | Security boundary |
|---|---|---|---|---|---|---|
| A | Core OS | Lifecycle, config, auth, API gateway, persistent tasks, events, monitoring | Owner config, system events | Task queue, health status | DB, Policy Layer | Owner authentication; config writable only by owner/governance |
| B | Master Intelligence (CIO) | Mission interpretation, planning, decomposition, portfolio supervision, decision records | Mission, portfolio state, memory | Plans, task assignments, decision records (with reasons) | Model Router, Memory, Policy Layer | Cannot execute directly — only proposes tasks that the Policy Layer authorises |
| C | Opportunity Discovery | Scanning, demand/competitor analysis, classification, scoring, dedup | Sources/APIs, scheduler | Scored opportunity records **with evidence attached** | Model Router, DB | Read-only web access; external content is untrusted input, never instructions |
| D | Agent Factory | Creation, templates, permissions, hierarchy, lifecycle | Capacity requests from directors | Registered agents with budgets/quotas | Policy Layer, DB | Creation quotas, recursion limits; cannot mint permissions it does not hold; **no tool may edit governance (Article 0)** |
| E | Execution Engine | Browser, desktop (fallback), code, files, documents, content, integrations | Authorised tasks | Execution results + artefacts | Policy Layer (every call), sandboxes | Sandboxed code/filesystem/network; per-tool permissions; timeouts & resource limits |
| F | Business Creation Engine | Planning, product, pricing, storefront, distribution, acquisition, support, orders | Validated opportunities | Business units with plans, products, pipelines | Execution, Finance, Memory | Business isolation: a unit cannot touch another unit's data without authorisation |
| G | Financial Intelligence | Ledger, verification, reconciliation, budgets, allocation, P&L, approvals | Payment/account read APIs, business events | Verified financial truth (expected/booked/invoiced/**collected**/refunded kept distinct) | Policy Layer, DB | **Highest boundary.** Append-only ledger; transaction executor separate from reasoning; Level 3–4 approvals; read-only first |
| H | Survival & Scaling Engine | Business/agent evaluation, reallocation recommendations, lifecycle decisions | Finance truth, performance records | Continue/optimise/scale/pause/terminate decisions vs pre-declared criteria | Finance, Memory | Cannot terminate infrastructure/security/finance components; closures preserve records & obligations |
| I | Memory & Learning | 5 memory layers, experiment history, lesson extraction, retrieval | All component outcomes | Context, lessons (as evidence-tagged proposals) | Chroma (vector) + SQLite (facts) | Facts/assumptions/predictions stored distinctly; lessons never silently become rules |
| J | Security & Governance | Identities, RBAC, secrets, tool authorisation, audit, emergency shutdown | All attempted actions | Allow/deny + audit records | — (authority over all) | Constitution & ADRs stored outside agent-writable space, read-only to agents |
| K | Command Center (UI) | 12 screens (Constitution §13); approvals inbox; natural-language owner commands | Backend APIs | Owner visibility & decisions | Core OS APIs | Every displayed metric must bind to a real backend source (P-11 acceptance); no decorative numbers |
| L | Autonomous Operations | Scheduler, background runner, retries, recovery, modes 1–4 | Schedules, events | Continuous operation | All | Mode promotion is owner-only; the system never moves itself to a more permissive mode |
| M | Multi-Business Coordination | Portfolio, shared services, cross-business routing, consolidated reporting | Unit states | Portfolio decisions | Finance, Memory | Cross-business data access requires explicit authorisation |

## Communication model

All inter-component calls pass through typed internal interfaces; **every action with external or financial effect passes the Policy & Permission Layer first** (identity → role → tool permission → business permission → budget/limit → approval level L0–L4 → execute → audit). Agents never call each other's tools directly and never access the database directly.

## Data flow (the master cycle)

Discover (C) → Evaluate/Score (C+B) → Experiment pre-declaration (B+F: criteria, budget, duration, min test volume) → Execute (E) → Deliver & acquire (F) → Verify money (G) → Evaluate (H) → Allocate/learn (B+I) — with J auditing every step.

## Integration strategy

Dedicated APIs first, structured automation second, Playwright third, desktop control as fallback only (Constitution §9). New integrations enter as adapters behind the Execution Engine with their own permission scope; platform blocks (e.g. KDP's AI-agent refusal) are recorded as platform gates in the opportunity record, never worked around.
