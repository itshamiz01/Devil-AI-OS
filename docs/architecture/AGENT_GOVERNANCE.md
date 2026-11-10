# P-00 Deliverable F — Agent Governance Blueprint

## Hierarchy (Constitution §5)

Level 0 Master Intelligence → Level 1 Executive Directors (Strategy, Finance, Risk, Operations, Intelligence, Technology) → Level 2 Business Directors (one per unit) → Level 3 Department Agents (Research, Product, Marketing, Sales, Operations, Finance) → Level 4 Execution Agents.

P-00 reference roles (proposed responsibilities, **none are created in P-00**): Master Orchestrator, Research, Opportunity Analyst, Market Validation, Business Strategist, Product Creation, Coding, Marketing, Customer Operations, Financial Analyst, Security Guardian, Independent Reviewer.

## Identity (every agent, no exceptions)

Unique ID · name · role · parent · assigned business · objective · model profile · tool permissions · resource budget · execution history · performance record · memory reference · lifecycle status. An agent without a registry entry does not run.

## Task lifecycle

Mission → plan → task (persistent ID) → **Policy Layer check** (identity, role, tool, business, budget, approval level) → execution in sandbox → result verification by the assigning agent → outcome recorded (task, tool executions, cost) → memory update. Progress is reported up the parent chain; failures retry only if recoverable, escalate otherwise; duplicate work is prevented by task ownership + idempotency keys on external/financial effects.

## Permission model

Levels L0 Observe · L1 Prepare · L2 Execute (pre-approved scope) · L3 Restricted financial (via Financial Engine only) · L4 Owner approval always. Permissions are granted by governance, checked deterministically on **every** call, and can be revoked instantly. **Agents cannot change their own permission levels, create unrestricted descendants, or edit governance artefacts (Article 0).**

## Creation & multiplication (Agent Factory, P-04)

A new agent requires ALL of: validated workload evidence · existing capacity demonstrably insufficient · expected value stated · compute available · business budget supports it · permissions permit it. Enforced by: per-business and global quotas · maximum hierarchy depth · recursion protection · per-agent budgets · CPU/memory ceilings · creation audit log · duplicate-role detection · automatic pause on abnormal resource use. Agent count is never a success metric; profit and verified outcomes per agent are. **Closed role templates only until the P-04 gate** — LLM-generated roles are a later, separately approved capability.

## Performance measurement

Per agent: task completion rate · output quality (reviewer sampling) · reliability · execution cost (model + tools + time) · resource consumption · measured contribution to business outcomes. Support agents (research, security, audit) are judged on contribution, never on direct revenue — and infrastructure/security agents are exempt from revenue-based termination (Constitution §7.4 analogue).

## Pause, reassignment, termination

Any agent may be paused by its parent, its business director, governance, or the owner; termination preserves its records, memory and audit trail. Runaway behaviour (loops, abnormal spend/resource use) triggers automatic pause + owner alert — designed here, implemented in P-04/P-12, tested in P-10.
