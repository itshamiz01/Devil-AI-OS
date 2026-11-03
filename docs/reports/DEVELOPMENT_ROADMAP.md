# AUTONOMUS Development Roadmap Validation

**Phase:** P-00 · **Status:** Proposed validation for owner review  
**Execution authority:** P-00–P-16 Prompt Pack, with cross-cutting constitutional controls  
**Rule:** Preserve the prompt sequence; do not begin a later phase without the prior gate and owner approval.

## 1. Sequence interpretation

The Constitution uses conceptual phases 0–11; the Prompt Pack uses P-00–P-16. They are not numerically interchangeable. D-02 proposes using P-IDs as execution identifiers while retaining the Constitution unchanged.

Conceptual phases 0–9 broadly correspond to P-00–P-09. Autonomous operation is expanded in P-12; multi-business coordination/economy appears in P-13/P-16. P-10 is comprehensive security hardening, P-11 the full interface, and P-14/P-15 integration/readiness gates. This mapping is proposed, not a silent constitutional amendment.

## 2. Phase dependency and acceptance map

| Phase | Prerequisites | Expected deliverables | Critical risks | Required testing | Exit criterion |
|---|---|---|---|---|---|
| **P-00 Foundation** | Owner vision, source documents, repository access | Audits, architecture, data/agent/security designs, ADRs, safe scaffolding, tracker | Treating Linux evidence as Windows readiness; unresolved authority/accounting definitions | Document/structure checks, source verification, preservation checks, critical review | Required evidence complete, limitations disclosed, independent review and owner gate; Windows may remain explicitly pending but blocks Windows readiness |
| **P-01 Core OS** | P-00 approval; Windows audit; approved toolchain | Local backend, owner auth, configuration, migrations, durable tasks/events, basic dashboard, desktop shell, minimum policy/audit/approval foundations | Host exposure, corrupt state, unsupported desktop prerequisites, premature live capabilities | Unit/API/migration/auth tests; Windows startup/shutdown/restart; task recovery; denied-action tests | Application runs on target Windows and recovers state; no live financial/external authority enabled |
| **P-02 Master Intelligence** | P-01; approved model/runtime policy | Mission interpreter, planner, model router, typed tool registry, decision/result records | Hallucinated completion, prompt injection, silent cloud spend, unsafe tool proposals | Provider contract tests; bounded mission E2E; unavailable-model tests; policy/privacy/budget tests | Completes and verifies one authorized bounded digital task with evidence |
| **P-03 Opportunity Discovery** | P-02; authorized read-only sources | Scanner, evidence database, competitor/demand analysis, scoring, dedupe, scheduler | Fabricated demand, stale sources, injection, unlawful collection | Source/provenance fixtures; live authorized-source sample; duplicate/scoring/risk-gate tests | Real opportunities ranked with traceable evidence and declared coverage |
| **P-04 Agent Factory** | P-02/P-03; identity and quota foundations | Registry, templates, creation gate, hierarchy, scoped memory/tools, lifecycle and performance | Recursive creation, privilege inheritance errors, resource exhaustion | Quota/depth/cycle, isolation, approval, pause/terminate and shared-inference tests | Supervised specialized agents can be created, coordinated and retired safely |
| **P-05 Digital Execution** | P-01/P-04; verified isolation design; channel permissions | Browser, file, coding, research and limited Windows adapters; artifact verification | Host compromise, session leakage, malicious downloads, duplicate side effects | Sandbox escape negative tests; path/network/command tests; bounded workflows; cancellation/recovery | Real bounded workflows complete with verifiable artifacts and enforced boundaries |
| **P-06 Business Creation** | P-03/P-05; budget/obligation foundations | Business templates, plans, products, pricing, authorized distribution, customers, orders and support | Product without demand, unauthorized publication, customer-data leakage | Business isolation; template/workflow tests; complete simulated customer journey; authorized delivery test | One independently managed workflow reaches customer delivery; real-revenue claim not yet implied |
| **P-07 Financial Intelligence** | Early financial foundations; P-06; approved accounting definitions/account access | Verified ledger, reconciliation, budgets, refunds, reporting, approvals and controlled executor | Double counting, duplicate payment, forecast-as-cash, reserve violation | Ledger invariants; provider-event verification; atomic reservation; replay/refund/chargeback tests; emergency payment stop | Balances/profit views reconcile to verified records; restricted execution passes approval tests |
| **P-08 Survival/Scaling** | P-07 and reliable business/agent metrics | Evaluators, experiment monitor, allocation and lifecycle controllers | Killing useful support roles, scaling noise, deleting obligations | Simulated and real-record decision tests; reserve/obligation checks; authorized scaling only | Justified continue/optimize/scale/pause/close decisions within authority |
| **P-09 Memory/Learning** | Durable evidence and experiment history; retrieval decision | Scoped memory, experiment history, validation, retrieval and measured improvement | Memory poisoning, private-data leakage, treating predictions as facts | Provenance/isolation/retention tests; retrieval benchmark; before/after decision evaluation | Validated historical lessons improve a measured decision without factual confusion |
| **P-10 Security Hardening** | All earlier minimum controls; implemented threat surfaces | Comprehensive RBAC, secrets, isolation, network, audit, recovery and monitoring hardening | Assuming earlier phases were secure without tests; local-host compromise | Adversarial injection/escalation/exfiltration/resource tests; independent security review | Unauthorized actions blocked, critical actions logged, emergency controls verified; residual risks accepted explicitly |
| **P-11 Command Center** | Backend sources and controls from prior phases | Complete accessible dashboard, hierarchy, financial views, approvals and commands | Fake metrics, controls that only change UI state, privilege bypass | Backend-source mapping; accessibility; action E2E; approval/denial tests | Every metric has a real source and every control performs its advertised authorized action |
| **P-12 Autonomous Operations** | Stable execution/finance/security; recovery foundations | Scheduler, workflow coordinator, retries, monitoring, notifications and operating modes | Duplicate effects, self-elevation, stale workers, restart corruption | Crash/restart, lease fencing, duplicate delivery, mode-transition and emergency persistence tests | Continuous bounded operation resumes safely without duplicate customer/financial actions |
| **P-13 Multi-business Coordination** | P-06/P-07/P-12; isolation and shared-service contracts | Portfolio manager, shared resources, inter-business routing and consolidated reporting | Cross-business leakage, internal revenue double counting, resource conflict | Two-business isolation/collaboration tests; consolidation/elimination; allocation tests | Two independent units operate simultaneously with separate accountable records |
| **P-14 Integration Audit** | Implemented intended scope | Cross-module audit, defect register and evidence | Hidden incomplete integrations and untested failure paths | E2E, regression, migration, permission, exhaustion, restart and reconciliation suites | No unresolved critical integration defects; incomplete scope documented |
| **P-15 Production Readiness** | P-14; target hardware and deployment plan | Performance/reliability evidence, backups, updates, monitoring, installer and dependency review | Unsupported performance claims, unsafe updates, unrecoverable backups | Load/soak/resource tests; restore drills; install/update/rollback; security/license review | Documented reliability/resource criteria pass on target Windows hardware |
| **P-16 AI Economy** | P-13–P-15; explicit distributed authority design | Shared service/agent marketplace, contracts, multi-machine nodes and portfolio optimization | Unauthenticated nodes, uncontrolled contracts, systemic resource/financial risk | Node identity/replay/isolation; contract authorization; distributed failure and consolidation tests | Multiple units collaborate through controlled interfaces with independent accountability |

## 3. Cross-cutting gates

These requirements apply throughout rather than waiting for their comprehensive phase:

- **Security:** owner authority, least privilege, audit, secret isolation and emergency controls before relevant capabilities.
- **Financial governance:** no live financial action before verified accounting, atomic budgets, bound approvals and reconciliation.
- **Persistence:** durable IDs, migrations, idempotency and recovery before long-running/external workflows.
- **UI:** a basic functional interface begins in P-01; P-11 completes it. No decorative production metrics.
- **Memory:** working state and evidence begin early; P-09 adds validated long-term learning.
- **Testing:** every feature has a requirement, implementation reference, executable test and observed result.
- **Documentation:** planned, implemented, verified and owner-approved are distinct statuses.

D-03 requests approval for the early financial/security slices. They do not authorize live trading, spending or autonomous publication.

## 4. Dependency spine

```text
P-00 → P-01 → P-02 → P-03 → P-04 → P-05 → P-06 → P-07
  → P-08 → P-09 → P-10 → P-11 → P-12 → P-13 → P-14 → P-15 → P-16

Security / audit / owner authority ───────────────────────────────→
Durable state / evidence ────────────────────────────────────────→
Financial limits before financial effects ───────────────────────→
Basic UI from P-01; complete UI at P-11
```

The owner's requested order is retained. Comprehensive audits at the end do not replace earlier phase tests.

## 5. Milestones

- **Foundation:** approved architecture and verified target environment.
- **First reliable intelligence:** one bounded task planned, authorized, executed and verified.
- **First real evidence:** traceable opportunity research, not invented market demand.
- **First controlled delivery:** complete business workflow to a customer within authorized channels.
- **First verified financial cycle:** authorized payment, delivery, reconciliation and correct reporting.
- **First justified scale decision:** evidence-backed resource change within limits.
- **Continuous safe operation:** restart/retry without duplicate external effects.
- **Master acceptance:** the Constitution's full real business cycle, not a simulation.

## 6. Immediate next gate

P-00 is being delivered for review, not marked fully approved. Before P-01:

1. Review the completion report and open decisions.
2. Run the Windows audit and resolve the target OS/toolchain.
3. Approve the phase interpretation and early control foundations.
4. Approve the candidate dependency baseline and a separate independent review.
5. Explicitly authorize P-01.

No later-phase implementation is authorized by this roadmap.
