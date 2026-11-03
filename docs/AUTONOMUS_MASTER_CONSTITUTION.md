# AUTONOMUS — Master Development Constitution v1.0

> **Provenance:** Transcribed from the owner-supplied Constitution in this conversation. Markdown has been normalized. On 2026-11-03 the owner explicitly authorized using the supplied text as the repository baseline. This is not an independently uploaded or cryptographically signed original. Ambiguities are recorded in `OPEN_DECISIONS.md`; this transcription does not silently resolve them.
>
> **Project:** Autonomous AI Business Operating System · **Platform:** Windows-first · **AI:** Hybrid local + optional cloud · **Autonomy:** Controlled · **Status:** Foundational specification

## 1. Project identity

### 1.1 Project definition

AUTONOMUS is an autonomous AI Business Operating System designed to discover, evaluate, create, operate, manage and scale legitimate digital businesses.

It is not a conventional chatbot, coding assistant, workflow automation application or collection of disconnected AI agents. It is a coordinated operating environment containing central intelligence, specialized agents, autonomous business units, opportunity discovery, digital execution tools, financial intelligence, capital allocation, persistent memory, business performance evaluation, dynamic agent creation, continuous learning, and security and governance.

Its ultimate purpose is to generate sustainable, verifiable economic value through independently operating digital businesses.

### 1.2 Primary mission

The system must:

1. Discover legitimate revenue-generating opportunities.
2. Evaluate commercial feasibility.
3. Select opportunities using evidence and measurable criteria.
4. Design and launch business experiments.
5. Execute complete digital business workflows.
6. Acquire customers through permitted methods.
7. Deliver products and services.
8. Receive and verify revenue.
9. Calculate actual profitability.
10. Improve successful operations.
11. Close consistently unsuccessful experiments.
12. Reinvest available capital responsibly.
13. Expand operational capacity when justified.
14. Learn from historical outcomes.

### 1.3 Long-term vision

The final system should support a network of interconnected autonomous businesses operated by specialized AI teams. It should eventually manage multiple industries, business models, revenue streams, AI departments, hundreds of specialized agents where infrastructure permits, multiple execution environments and distributed business operations.

This vision must be achieved through incremental, verified development.

## 2. Locked architectural decisions

These decisions are mandatory unless the project owner explicitly approves a formal architecture revision.

### 2.1 AI infrastructure: Hybrid

Local AI is the default operating mode.

Primary infrastructure: Ollama; local GGUF models; self-hosted inference where practical; local model routing; task-specific model profiles.

Optional cloud capabilities: external reasoning models; cloud-based coding models; specialized generation services; additional inference capacity.

Rules:

1. Cloud APIs must remain optional.
2. No essential function may silently depend on an unavailable paid API.
3. The system must detect model availability.
4. Model providers must be replaceable.
5. Every cloud request must respect configured privacy and spending permissions.
6. The owner must be able to disable cloud inference.
7. Cloud usage and costs must be recorded.

### 2.2 Autonomy: Controlled

The system should achieve maximum operational independence within defined boundaries.

It must support autonomous research, planning, task creation, agent creation within quotas, product development, authorized publishing, authorized customer communication, approved business operations, automated performance evaluation and bounded capital allocation.

Restricted operations include unapproved financial transfers; unlimited purchases; borrowing and leverage; irreversible account ownership changes; legal commitments; accessing or extracting unauthorized information; modifying security policies; disabling monitoring; self-authorizing elevated permissions.

A human owner retains ultimate administrative authority.

### 2.3 Platform: Windows first

The first release must run on Windows.

Requirements: desktop interface; local backend; local database; local AI model integration; browser automation; Windows computer control; persistent background services; local file management; restart recovery.

Future architecture must support remote monitoring, cloud services and additional machines without requiring a complete rebuild.

## 3. Fundamental operating principles

1. **Revenue over activity:** Measure economic results, not merely the quantity of completed tasks.
2. **Evidence over assumptions:** An AI prediction does not validate an opportunity.
3. **Complete workflows over isolated tasks:** Prioritize complete revenue-generating operations.
4. **Capital preservation:** Protect available funds and maintain reserves.
5. **Controlled multiplication:** Create agents and businesses only when justified by demand, workload, capacity and resources.
6. **Continuous improvement:** Every experiment must contribute useful information to learning.
7. **Recoverability:** Critical tasks, transactions and operations must survive restarts and recover from failures.
8. **Auditability:** Important decisions and actions must have traceable records.
9. **Modular independence:** Modules must be independently testable and replaceable.
10. **Human ownership:** Never transfer ultimate ownership or administrative control away from the human owner.

## 4. System architecture

AUTONOMUS must use a modular architecture with clearly defined boundaries.

### A. Core Operating System

Responsible for application lifecycle, configuration, authentication, backend API, persistent task management, system events and monitoring.

### B. Master Intelligence

Responsible for mission interpretation, strategic planning, decision-making, task decomposition, agent coordination and business portfolio supervision.

### C. Opportunity Discovery

Responsible for market scanning, demand discovery, competitor analysis, opportunity classification, feasibility assessment and opportunity ranking.

### D. Agent Factory

Responsible for agent creation, templates, role definitions, permissions, parent-child relationships and lifecycle management.

### E. Digital Execution Engine

Responsible for browser automation, desktop control, coding, research, file management, document production, content creation and approved external integrations.

### F. Business Creation Engine

Responsible for business planning, product development, pricing, publishing, distribution, customer acquisition, customer support and order management.

### G. Financial Intelligence

Responsible for wallet connectivity, the financial ledger, revenue verification, expense tracking, budget allocation, profit calculations and reconciliation.

### H. Survival and Scaling Engine

Responsible for business and agent performance evaluation, resource optimization, business expansion, experiment termination and agent scaling.

### I. Memory and Learning Engine

Responsible for working memory, agent memory, business memory, strategic memory, knowledge retrieval and experiment analysis.

### J. Security and Governance

Responsible for authentication, authorization, tool permissions, financial limits, security monitoring, audit trails and emergency shutdown.

## 5. Agent governance

### 5.1 Agent hierarchy

- Level 0: Master Intelligence.
- Level 1: Executive Agents.
- Level 2: Business Directors.
- Level 3: Department Agents.
- Level 4: Execution Agents.

### 5.2 Agent identity

Every agent must have a unique ID, name, role, parent agent, assigned business, objective, model profile, tool permissions, resource budget, execution history, performance records, memory reference and lifecycle status.

### 5.3 Agent lifecycle

`CREATED → CONFIGURED → ACTIVE → PAUSED → REASSIGNED → TERMINATED`

Every transition must be recorded.

### 5.4 Agent multiplication

The Agent Factory may create specialized agents when a validated workload exists; existing agents are approaching capacity; additional agents can improve execution; sufficient computing resources are available; the business budget supports expansion; permissions permit the proposed activity.

Agent count is not a proxy for productivity. Agent creation must have quotas, recursion limits, resource ceilings and approval policies. Agents cannot change their own permission levels or create unrestricted descendants.

## 6. Business governance

Every business must operate as an independently identifiable unit.

Each business requires a business ID, business director, business plan, market research, product or service definition, customer segment, revenue model, operating budget, financial ledger, agent team, performance targets, risk register and operational status.

### 6.1 Business lifecycle

`DISCOVERED → EVALUATED → EXPERIMENT → VALIDATED → ACTIVE → SCALING`

Alternative outcomes: `PAUSED`, `REJECTED`, `FAILED`, `CLOSED`.

### 6.2 Business closure

Closing a business must not delete customer records that must legally be retained, outstanding obligations, transaction history, financial records, product assets, research history or audit logs.

The system must account for refunds, warranties, subscriptions and other outstanding obligations before closure.

## 7. Financial constitution

Financial correctness is a foundational requirement.

### 7.1 Financial truth

The system must distinguish forecast revenue, booked revenue, invoiced revenue, collected revenue, refunded revenue, gross profit, net operating profit and available cash.

Only verified financial events may be classified as collected revenue.

### 7.2 Financial formulas

- Net Profit = Collected Revenue − Refunds − Total Expenses.
- ROI = Net Profit / Invested Capital × 100.
- Cash Balance = Verified Opening Balance + Deposits + Collected Payments − Withdrawals − Expenses.

The ledger must support reconciliation and must not allow ordinary agents to overwrite historical financial events.

### 7.3 Capital controls

The financial engine must support initial capital, protected reserves, experiment budgets, business budgets, operating expenses, emergency reserves, profit reinvestment, spending limits, exposure limits and transaction approval.

Every experiment must have a maximum permitted loss.

### 7.4 Wallet security

- Never expose private keys to language models.
- Never put credentials in prompts.
- Use secure credential storage.
- Prefer read-only wallet connectivity.
- Use a controlled transaction executor.
- Require explicit approval for restricted financial actions.
- Maintain transaction audit records.
- Support emergency payment suspension.

## 8. Opportunity discovery constitution

The system must discover opportunities across multiple digital industries.

Initial categories:

1. Digital publishing.
2. Software and SaaS.
3. Digital services.
4. Content and media.
5. Ecommerce.
6. Affiliate businesses.
7. Educational products.
8. Data and research services.
9. Automation services.
10. Financial research and approved trading experiments.

New categories may be added dynamically.

Each opportunity must contain evidence of demand, target audience, competitor landscape, monetization mechanism, startup costs, recurring costs, time-to-revenue estimate, execution difficulty, risk assessment, legal and platform eligibility, and confidence level.

The system must not claim to have searched the entire internet or global economy when it has only inspected a limited set of sources.

## 9. Digital execution constitution

Preferred execution order:

1. Official APIs and dedicated integrations.
2. Structured automation interfaces.
3. Browser automation.
4. Desktop interaction as a fallback.

Required capabilities: browser navigation; search; clicking and typing; file operations; code execution; application interaction; document generation; spreadsheet processing; content production; authorized communication; website deployment; workflow scheduling.

Execution environments must be isolated. Untrusted web content must never be allowed to override system instructions.

## 10. Memory and learning constitution

Maintain five memory categories: working memory, agent memory, business memory, strategic memory and knowledge memory.

Every experiment must record the original hypothesis, available evidence, planned expenditure, actual expenditure, expected results, actual results, success or failure, root-cause analysis, lessons learned and future recommendations.

Memory updates must preserve the distinction between facts, assumptions, predictions and unverified claims.

## 11. Security and safety constitution

The security layer has authority over every module.

It must enforce role-based access control, least-privilege permissions, agent identity, secure secrets storage, sandboxed code execution, filesystem restrictions, network controls, tool authorization, financial controls, audit logging, backup and recovery, and emergency shutdown.

The system must defend against prompt injection, malicious websites, fraudulent instructions, credential theft, malicious files, unauthorized spending and runaway agent loops.

No business objective may override security restrictions. No agent may modify the security constitution.

## 12. Technical standards

Initial preferred stack:

- Backend: Python and FastAPI.
- Frontend: React and TypeScript.
- Desktop: Windows-first desktop shell, with Tauri as a preferred candidate.
- AI: Ollama, GGUF and optional cloud inference.
- Database: SQLite initially, PostgreSQL when required.
- Vector memory: ChromaDB or a compatible replaceable vector database.
- Browser automation: Playwright.
- Windows automation: PyAutoGUI and appropriate Windows APIs.
- Testing: Pytest and frontend testing tools.
- Source control: Git and GitHub.

The technology stack may be changed only through a documented architecture decision.

### 12.1 Coding standards

Type hints; structured error handling; clear module boundaries; explicit interfaces; configuration-driven behavior; no hardcoded secrets; no silent exceptions; no unnecessary duplicate implementations; automated tests; dependency documentation; versioned database migrations; structured logging.

### 12.2 Performance standards

Support constrained local hardware through shared model servers, model routing, task queues, bounded concurrency, memory-aware scheduling, lightweight agents, resource monitoring and optional cloud offloading.

Creating an agent must not automatically create a separate heavyweight model process.

## 13. User interface constitution

Required sections:

1. Command Center.
2. Master Intelligence.
3. Opportunity Center.
4. Business Portfolio.
5. Agent Universe.
6. Financial Center.
7. Execution Monitor.
8. Strategy Center.
9. Memory Center.
10. Security Center.
11. Integrations.
12. System Settings.

The user must be able to inspect what the AI is doing, why, which tools it uses, how much it spends, what revenue is verified, which agents are active, which businesses are performing and which actions need approval.

Visual design must be professional, premium, responsive and information-dense without becoming cluttered.

## 14. Development governance

Development must follow stage-gated implementation.

Every phase must include repository inspection, architecture review, implementation plan, dependency review, implementation, unit tests, integration tests, security tests, regression tests, documentation and an independent completion audit.

No phase may be marked complete solely because code has been generated.

### 14.1 Preservation rule

If a working codebase already exists: inspect before editing; identify existing capabilities; preserve verified functionality; reuse working modules; avoid unnecessary rewrites; create backups before risky changes; document breaking changes; obtain approval for major architecture changes.

### 14.2 Completion rule

Every implemented feature must have a clear requirement, implementation reference, test, verifiable result, documentation and known limitations.

Features that are only planned must be labelled **PLANNED**, not **IMPLEMENTED**.

## 15. Development phases

- Phase 0: Foundation and feasibility.
- Phase 1: Core AI Operating System.
- Phase 2: Master Intelligence.
- Phase 3: Opportunity Discovery.
- Phase 4: Agent Factory.
- Phase 5: Digital Execution Engine.
- Phase 6: Business Creation Engine.
- Phase 7: Financial Intelligence.
- Phase 8: Survival and Scaling Engine.
- Phase 9: Memory and Continuous Learning.
- Phase 10: Autonomous Operations.
- Phase 11: Multi-business AI Economy.

Each phase has separate acceptance criteria and must pass an independent audit.

**Transcription note:** These are the Constitution's conceptual phase numbers, not the P-00–P-16 prompt IDs. The later Prompt Pack and the owner's detailed P-00 request use a different numbering scheme. The mapping requires explicit approval; see `OPEN_DECISIONS.md`, D-02.

## 16. Master acceptance test

AUTONOMUS cannot be considered a completed autonomous business operating system until it demonstrates:

1. Discover a legitimate market opportunity.
2. Gather and evaluate supporting evidence.
3. Estimate commercial feasibility.
4. Create a business plan.
5. Allocate an approved experimental budget.
6. Build a digital product or service.
7. Publish through an authorized channel.
8. Acquire a real customer.
9. Deliver the promised value.
10. Receive payment through an authorized payment system.
11. Verify the collected payment.
12. Reconcile expenses and refunds.
13. Calculate actual net profit.
14. Evaluate business performance.
15. Decide whether to optimize, scale, pause or close.
16. Record the outcome in persistent memory.
17. Allocate resources to the next justified opportunity.

All steps must be demonstrated using actual execution evidence, not simulated claims.

## 17. Final authority

The human project owner retains ultimate control over system ownership, administrative access, financial permissions, security policies, external integrations, legal commitments, critical configuration and emergency shutdown.

AUTONOMUS is designed to become increasingly independent in business execution, not independent of accountability.

## 18. Constitutional change management

This constitution is versioned.

Any change affecting core architecture, financial permissions, agent authority, security controls, data ownership, model-provider requirements or platform support must be documented in an Architecture Decision Record.

Development agents cannot silently amend this constitution.

**End of owner-supplied Constitution v1.0 transcription.**
