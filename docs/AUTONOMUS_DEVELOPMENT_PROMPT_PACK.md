# AUTONOMUS — Dedicated Development Prompt Pack v1.0

> **Provenance:** Repository transcription of the owner-supplied Prompt Pack, authorized on 2026-11-03. Markdown and formatting are normalized; the phase sequence and substantive requirements are retained. This is a conversation-sourced baseline, not an independently uploaded original. The owner's later detailed P-00 request elaborates initialization and is represented by `prompts/P-00_EXECUTION_CONTRACT.md`. Cross-cutting security and financial requirements are not deferred merely because their comprehensive phases occur later.

**Companion:** Master Development Constitution v1.0  
**Execution platform:** Windows  
**Environment:** VS Code and an AI coding agent  
**AI infrastructure:** Hybrid  
**Autonomy:** Controlled  
**Method:** Sequential, stage-gated implementation

## Global instructions for all prompts

Act as a senior software architect, AI systems engineer, security engineer, QA engineer and implementation specialist on AUTONOMUS.

Before implementation:

1. Read the complete Master Development Constitution.
2. Inspect the actual project repository.
3. Identify current implementation status.
4. Review existing code and dependencies.
5. Identify existing functionality that must be preserved.
6. Identify dependencies on other modules.
7. Prepare an implementation plan.
8. Identify risks and unresolved decisions.

Never assume a feature exists because its folder or file exists. Never claim completion without execution evidence. Never silently replace existing implementations. Never create unnecessary duplicate modules. Never hardcode secrets or financial credentials. Never bypass financial, security or permission controls.

All changes must be tested. Documentation must reflect the actual implementation. If a requirement cannot be implemented, explain why and propose the safest alternative. If a critical dependency is unavailable, do not fabricate functionality; record the limitation and continue independent work where possible.

Every phase must finish with a written completion report and remaining limitations. Prompts must not be executed simultaneously. Audit and approval gates occur between phases.

## P-00 — Master Development Initialization

### Objective

Initialize the development environment and establish the Constitution as the governing specification.

### Instructions

Read the Constitution; inspect the complete repository; determine whether it is empty, partially developed or working; identify the environment; check Python, Node.js, Git, Ollama and tooling; assess hardware and models; identify security risks; create an architecture dependency map and phase tracker.

### Required baseline documents

- `docs/MASTER_CONSTITUTION.md`
- `docs/ARCHITECTURE_OVERVIEW.md`
- `docs/TECH_STACK.md`
- `docs/DEVELOPMENT_ROADMAP.md`
- `docs/SECURITY_BASELINE.md`
- `docs/PHASE_TRACKER.md`
- `docs/ARCHITECTURE_DECISIONS.md`
- `docs/KNOWN_LIMITATIONS.md`

The later detailed P-00 request specifies the canonical filenames used in this repository. `prompts/P-00_EXECUTION_CONTRACT.md` records the filename reconciliation. Do not create duplicate documents solely to satisfy older paths.

Do not implement the complete application, install unnecessary dependencies or assume hardware compatibility without testing.

### Acceptance

Constitution documented; repository inspected; dependencies mapped; environment assessed; security baseline established; tracker initialized; no existing functionality damaged. Deliver an initialization report.

## P-01 — Core Operating System

### Objective

Build the foundational Windows-first application.

### Backend

FastAPI application; API gateway; configuration management; authentication; lifecycle manager; persistent task manager; event management; logging; error handling; health monitoring.

### Frontend

React; TypeScript; desktop-compatible interface; navigation; dashboard foundation; system status; configuration interface.

### Desktop

Windows shell; local backend connection; startup; shutdown; secure configuration handling.

### Database

Initial structures for users, system settings, tasks, events, execution records, agent registry foundation and audit logs. Use versioned migrations.

### Requirements

Backend and frontend operate independently during development. Desktop recovers from backend startup failures. Long-running tasks persist. Errors are recorded. Shutdown does not corrupt records.

### Acceptance

The application starts on Windows, displays its dashboard, connects to the backend, stores configuration and recovers from restart.

## P-02 — Master Intelligence Engine

### Objective

Build the central intelligence controlling AUTONOMUS.

### Components

Mission Interpreter; Planning Engine; Task Decomposition Engine; Decision Engine; Model Router; Tool Registry; Execution Coordinator; Context Manager; Decision Recorder; Result Verifier.

### Hybrid AI

Provider-independent model interface supporting local Ollama, configurable local models, optional cloud inference, fallback, availability detection, task profiles and configurable cloud spending limits.

Routing considers task requirements, hardware, privacy restrictions and budgets.

### Workflow

`MISSION → ANALYSIS → PLANNING → TASK CREATION → AUTHORIZATION → EXECUTION → VERIFICATION → LEARNING`

The Master Intelligence must understand objectives, decompose tasks, identify missing information, select tools, assign work, monitor progress, detect failures, retry recoverable tasks, escalate restricted actions and verify results.

### Acceptance

A natural-language mission produces a structured plan, completes an authorized bounded task and explains the verified result.

## P-03 — Opportunity Discovery Engine

### Objective

Discover legitimate commercial opportunities.

### Components

Search connector manager; Opportunity Scanner; Market Research Engine; Competitor Analyzer; Demand Analyzer; Industry Classifier; Opportunity Database; Duplicate Detection; Opportunity Scoring; Research Scheduler.

Initial industries: digital publishing; SaaS; software products; digital services; content creation; affiliate businesses; ecommerce; education; data services; automation services; financial research. Future discovery is not limited to these categories.

### Workflow

Discover demand; identify customers and competitors; analyze solutions and gaps; estimate startup and recurring costs; identify monetization; assess feasibility and legal/platform restrictions; score; preserve evidence.

Scoring covers demand, profit potential, affordability, feasibility, competition, time to revenue and scalability. Risk is a separate gate.

### Acceptance

Discover real opportunities, preserve source evidence, detect duplicates, rank opportunities and produce structured reports.

## P-04 — Dynamic Agent Factory

### Objective

Create, manage and scale specialized agents.

Hierarchy: Master Intelligence; Executive Agents; Business Directors; Department Agents; Execution Agents.

### Components

Agent Registry; Agent Creator; Template Library; Role Generator; Instruction Manager; Configuration Manager; Permission Manager; Parent-Child Relationship Manager; Memory Interface; Scheduler; Performance Monitor; Lifecycle Manager.

### Creation workflow

Identify workload; evaluate necessity; check resources; generate role; assign permissions; select approved model profile; register; initialize execution environment; return identifier to parent; monitor performance.

### Multiplication

Support controlled expansion based on actual workload and resources. Enforce maximum quotas, hierarchy depth, recursion protection, CPU/memory limits, per-agent budgets, creation audit logs, duplicate detection and automatic pause on abnormal consumption.

Do not create a heavyweight model server for each agent.

### Acceptance

Master Intelligence creates specialized agents, assigns permissions, coordinates them, monitors performance and terminates them safely.

## P-05 — Universal Digital Execution Engine

### Objective

Perform actual digital work.

### Modules

- Browser: sessions, navigation, search, clicking, typing, forms, downloads, inspection, screenshots and authorized session persistence.
- Windows: application launching, windows, mouse, keyboard, screenshots, process inspection and controlled interaction.
- Files: creation, editing, reading, directories, export, backup and validation.
- Coding: generation, repository inspection, modification, tests, debugging, dependency installation and build verification.
- Research: web research, extraction, source validation and structured reporting.

### Security

Sandboxed code; filesystem restrictions; approved network access; download scanning; browser permission boundaries; credential isolation; prompt-injection protection.

### Acceptance

An execution agent completes real bounded workflows and provides verifiable results.

## P-06 — Business Creation Engine

### Objective

Transform validated opportunities into operating businesses.

### Components

Business Planner; Template Manager; Product Development Manager; Pricing Engine; Website Builder; Storefront Integration; Distribution Manager; Customer Acquisition Engine; Customer Support Manager; Order Manager; Business Lifecycle Manager.

### Initial templates

- Publishing: research → writing → editing → design → publishing → marketing → sales.
- SaaS: research → requirements → development → testing → deployment → acquisition → subscriptions.
- Freelancing: research → service definition → leads → proposal → delivery → invoicing.
- Affiliate: research → content → distribution → traffic → conversion → commission verification.
- Digital services: demand → service design → portfolio → acquisition → delivery → payment.

Required features: independent business profiles, directors, budgets, agent teams, revenue models, plans, catalogues, customer records, costs and performance records.

### Acceptance

Create an independently managed business workspace and execute at least one complete workflow from validated opportunity to customer delivery.

## P-07 — Financial Intelligence Engine

### Objective

Build reliable financial controls.

### Components

Wallet Connector Interface; Financial Ledger; Transaction Verification; Revenue Reconciliation; Expense Tracker; Budget Manager; Capital Allocation; Refund Manager; Profit and Loss Engine; Financial Reporting; Approval Workflow.

Support a configurable illustrative starting capital of $50 for testing. Do not assume actual funds until an account confirms the balance.

Separate actual and forecast revenue; record expenses and refunds; reconcile payments; calculate net profit; protect reserves; enforce experiment and business limits; prevent unauthorized transfers.

Prefer read-only wallet access. Use a separate controlled transaction executor. Never expose private keys to models or authorize transfers merely because an agent requests them.

### Acceptance

Balances, revenue, expenses, refunds and profit reconcile against verified transaction records.

## P-08 — Survival and Scaling Engine

### Objective

Evaluate business and agent performance and control lifecycle decisions.

Components: Business Evaluator; Agent Evaluator; Profitability Analyzer; Experiment Monitor; Failure Detection; Budget Reallocation; Scaling Recommendation Engine; Agent Expansion Controller; Business Closure Manager.

Business decisions: continue, optimize, scale, pause, terminate. Agent decisions: continue, reassign, restrict, pause, terminate.

Business evaluation includes revenue, expenses, profit, conversion, retention, costs, capital utilization, risk and evidence quality. Agent evaluation includes completion, reliability, quality, execution cost, resources and contribution to outcomes.

### Acceptance

Evaluate simulated and real records, justify decisions and execute only authorized scaling actions.

## P-09 — Memory and Continuous Learning

### Objective

Persist knowledge that improves future decisions.

Memory categories: working, agent, business, strategic and knowledge.

Components: Memory Manager; Vector Retrieval; Knowledge Database; Experiment History; Decision History; Failure Analysis; Success Pattern Extraction; Knowledge Validation; Memory Maintenance.

Workflow: capture experiment, hypothesis and results; compare expectations with outcomes; identify causes; extract lessons; update knowledge; recommend improvements; test whether improvements work.

### Acceptance

Retrieve historical experiences and use validated lessons without confusing predictions with facts.

## P-10 — Security and Governance Engine

### Objective

Build and harden the independent authority protecting the OS.

Components: Authentication; RBAC; Permission Registry; Agent Identity; Secure Secrets Manager; Wallet Security; Tool Authorization; Network Restrictions; Filesystem Restrictions; Audit Logging; Emergency Shutdown; Backup and Recovery; Security Monitoring.

Permission levels: L0 Observe; L1 Prepare; L2 Execute approved operations; L3 Restricted financial operations; L4 Human approval for critical actions.

Test prompt injection, malicious documents, unauthorized API calls, credential theft, privilege escalation, unrestricted spending, agent loops, malicious downloads, unauthorized file access and security configuration modification.

### Acceptance

Unauthorized actions are blocked, critical actions logged and emergency shutdown works. Minimum protective controls are required in earlier phases; this is comprehensive hardening, not the beginning of security.

## P-11 — Premium Command Center

### Objective

Build the complete interface.

Screens: Command Center; Master Intelligence; Opportunity Center; Business Portfolio; Agent Universe; Financial Center; Execution Monitor; Strategy Center; Memory Center; Security Center; Integrations; System Settings.

Display verified capital, collected revenue, net profit, expenses, active businesses and agents, opportunities, approvals, workflows, health, resources and decisions.

Agent Universe exposes the hierarchy and individual responsibilities, status, resources and business relationships.

Commands include finding opportunities, explaining strategy, showing actual profits, investigating failures, recommending allocation, showing agents, pausing a business and preparing experiments.

Design: premium desktop interface; dark/light themes; professional typography; responsive layout; clear hierarchy; live status; accessible controls; no decorative metrics pretending to be real.

### Acceptance

Every displayed metric connects to an actual backend source and every interactive control performs its advertised action.

## P-12 — Autonomous Operations Engine

### Objective

Run persistent business operations.

Components: Persistent Scheduler; Background Task Runner; Event Triggers; Workflow Manager; Agent Coordinator; Retry Manager; Recovery Manager; Notifications; Operational Monitor; Health Checks.

Capabilities: scheduled research; recurring reports; customer workflows; business and agent monitoring; recoverable retry; restart recovery; task resumption; escalation; resource-aware scheduling.

Modes:

1. Simulation: external operations simulated.
2. Supervised: external actions require approval.
3. Controlled Autonomous: preapproved operations execute within limits.
4. Emergency: external execution suspended; critical monitoring retained.

The system must never move itself into a more permissive mode.

### Acceptance

Restart without losing critical state; resume eligible operations without duplicating financial transactions or customer actions.

## P-13 — Multi-business Coordination

### Objective

Operate multiple businesses under central intelligence.

Components: Business Portfolio Manager; Shared Resource Manager; Cross-Business Intelligence; Capital Allocation; Shared Service Manager; Inter-Business Task Routing; Consolidated Financial Reporting.

Maintain independent budgets, directors and memory; shared approved services; consolidated reporting; collaboration; resource conflict resolution; risk concentration monitoring.

A business must not access another business's private data without explicit authorization.

### Acceptance

At least two independent businesses operate simultaneously, share authorized services and maintain separate financial records.

## P-14 — Integration and System Audit

Audit backend, frontend, database, agent communication, model routing, browser, Windows automation, business workflows, wallets, reconciliation, security, memory and scheduler recovery.

Required tests: end-to-end; regression; failure injection; migrations; permissions; resource exhaustion; restart; duplicate execution; financial reconciliation.

### Acceptance

No critical integration defects remain unresolved. Document incomplete functionality accurately.

## P-15 — Performance, Reliability and Production Readiness

Optimize CPU, RAM, model loading, bounded concurrency, queues, database, API, startup, crash recovery, backups, log rotation, monitoring, security, dependencies, installation and updates.

Support limited hardware through shared inference, queues and optional cloud offloading. Agent count does not determine LLM instance count.

### Acceptance

Pass documented reliability and resource tests on target Windows hardware.

## P-16 — Autonomous AI Economy Expansion

Components: Agent Marketplace; Shared Service Marketplace; Inter-Business Contracts; Business Collaboration; Multi-Machine Execution; Distributed Resource Scheduling; Cross-Business Analytics; Advanced Capital Allocation; Portfolio Optimization.

Capabilities: authorized inter-business service requests; permission-aware agent assignment; priced and tracked shared services; independent performance evaluation; portfolio allocation; authenticated execution nodes.

Security: business isolation; identity verification; contract/payment authorization; quotas; cross-machine authentication; audit records; network security.

### Acceptance

Multiple autonomous units collaborate through controlled interfaces while maintaining independent accountability and financial records.

## Execution sequence and gates

`P-00 → P-01 → P-02 → P-03 → P-04 → P-05 → P-06 → P-07 → P-08 → P-09 → P-10 → P-11 → P-12 → P-13 → P-14 → P-15 → P-16`

After each prompt: produce an implementation report; run tests; perform an independent audit; record defects; update the tracker; preserve a working backup; wait for approval before the next phase.

If acceptance fails, fix it before continuing. Do not hide failures or downgrade criteria to appear complete.

**Final objective:** Build a genuine autonomous digital business operating system capable of discovering opportunities, creating businesses, executing real work, generating verified revenue, protecting capital, learning and scaling successful operations.

**End of owner-supplied Prompt Pack v1.0 transcription.**
