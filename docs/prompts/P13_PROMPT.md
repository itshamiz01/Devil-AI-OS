AUTONOMUS AI BUSINESS OPERATING SYSTEM

P-13: MULTI-BUSINESS COORDINATION ENGINE

Master Development and Implementation Prompt v1.0

---

1. ROLE AND MISSION

Act as a Principal AI Systems Architect, Multi-Tenant Platform Architect, Enterprise Portfolio Management Engineer, AI Orchestration Specialist, Financial Systems Architect, and Senior Full-Stack Developer.

Your mission is to design, develop, integrate, test, and document:

P-13: Multi-business Coordination Engine

inside the existing AUTONOMUS AI Business Operating System.

P-13 will transform AUTONOMUS from a system capable of managing individual businesses into a unified platform capable of coordinating, monitoring, evaluating, and optimizing a portfolio of multiple independent businesses.

The system must support:

- Multiple businesses operating simultaneously.
- Independent business identities and configurations.
- Centralized portfolio intelligence.
- Business-specific operational autonomy.
- Shared agent infrastructure with strict permissions.
- Controlled resource allocation.
- Cross-business opportunity discovery.
- Portfolio-level financial intelligence.
- Business performance comparisons.
- Shared services and infrastructure.
- Business-specific and portfolio-wide risk management.
- Coordinated strategic planning.
- Owner-controlled expansion and restructuring.

The objective is to create a central intelligence layer that understands the entire business ecosystem while preserving the independence of every business.

Do not rebuild AUTONOMUS. Extend the existing P-01 through P-12 architecture.

---

2. PRE-IMPLEMENTATION AUDIT

Before implementation, audit the existing system.

Review:

- P-01 Core Operating System.
- P-02 Master Intelligence Engine.
- P-03 Opportunity Discovery Engine.
- P-04 Dynamic Agent Factory.
- P-05 Universal Digital Execution Engine.
- P-06 Business Creation Engine.
- P-07 Financial Intelligence Engine.
- P-08 Survival and Scaling Engine.
- P-09 Memory and Continuous Learning Engine.
- P-10 Security and Governance Engine.
- P-11 Premium Command Center.
- P-12 Autonomous Operations Engine.

Inspect:

1. Business entity models.
2. Business lifecycle management.
3. Business-level data isolation.
4. Agent ownership and permissions.
5. Shared agent infrastructure.
6. Workflow ownership.
7. Financial ledgers and reporting.
8. Business budgets and financial controls.
9. Portfolio-level reporting capabilities.
10. Memory scopes.
11. Resource management.
12. Approval mechanisms.
13. Existing event and orchestration infrastructure.
14. Command Center navigation and dashboards.
15. Existing APIs and database relationships.

Preservation requirements

- Preserve all functioning modules.
- Do not create duplicate business records.
- Do not create a second financial ledger.
- Do not merge independent business data.
- Do not weaken existing security policies.
- Do not allow cross-business access without explicit authorization.
- Reuse existing services and APIs.
- Do not introduce unnecessary paid infrastructure.
- Avoid unnecessary database and architectural complexity.

Produce:

"docs/multi-business/P13_PRE_IMPLEMENTATION_AUDIT.md"

Document the existing architecture, gaps, conflicts, risks, integration plan, and implementation strategy.

---

3. CORE CONCEPT: AUTONOMUS BUSINESS ECOSYSTEM

Build P-13 around three organizational levels.

Level 1: Individual Business

Every business operates independently.

Each business has:

- Unique business ID.
- Name and identity.
- Business category.
- Business model.
- Products and services.
- Customers.
- Revenue streams.
- Expenses.
- Financial records.
- Budget.
- Assigned agents.
- Workflows.
- Operational memory.
- Performance metrics.
- Risk profile.
- Autonomy policy.
- Growth objectives.

Level 2: Business Portfolio

The portfolio represents the collection of businesses managed by AUTONOMUS.

It provides:

- Combined portfolio visibility.
- Business comparisons.
- Strategic priorities.
- Resource utilization.
- Portfolio risk analysis.
- Capital allocation recommendations.
- Shared infrastructure management.
- Cross-business opportunities.

Level 3: AUTONOMUS Master Intelligence

The Master Intelligence layer evaluates the portfolio as a complete ecosystem.

It should understand:

- Which businesses are performing.
- Which businesses are underperforming.
- Which businesses are profitable.
- Which businesses are consuming resources.
- Which businesses have high growth potential.
- Which businesses are exposed to significant risk.
- Where operational synergies exist.
- Which expansion opportunities are justified.

The portfolio intelligence layer must not override the financial, security, or business-level authority of existing modules.

---

4. BUSINESS PORTFOLIO MANAGEMENT

Build a central portfolio management service.

Portfolio capabilities

- Create a portfolio.
- Register existing businesses.
- Remove a business from active portfolio management without deleting its records.
- Archive a business.
- Activate or pause a business.
- Inspect business details.
- Compare businesses.
- Group businesses by category.
- Define strategic priorities.
- Set portfolio-level objectives.
- Monitor business health.
- Generate portfolio reports.

Portfolio structure

Support logical grouping by:

- Business category.
- Industry.
- Revenue model.
- Operational status.
- Strategic priority.
- Risk category.
- Development stage.
- Geographic market.
- Shared infrastructure.

Allow businesses to belong to multiple analytical groups without duplicating their underlying records.

Business lifecycle

Support:

"IDEA → VALIDATING → APPROVED → BUILDING → LAUNCHING → OPERATIONAL → OPTIMIZING → SCALING"

Additional states:

- PAUSED
- AT_RISK
- BLOCKED
- RESTRUCTURING
- CLOSING
- ARCHIVED

State transitions must be governed by P-06, P-08, P-10, and owner policies.

A business must not be marked profitable or operational merely because its creation workflow completed.

---

5. BUSINESS REGISTRY AND IDENTITY MANAGEMENT

Create a unified business registry.

Every business must have an authoritative identity.

Business profile

Store or reference:

- Business ID.
- Business name.
- Legal or operating identity where applicable.
- Business category.
- Description.
- Business model.
- Target customers.
- Geographic markets.
- Products and services.
- Revenue streams.
- Cost structure.
- Launch date.
- Operational status.
- Owner.
- Assigned agents.
- Business objectives.
- Autonomy level.
- Risk classification.
- Financial configuration.
- Data-access policies.

Business identity isolation

A business must maintain independent:

- Customer records.
- Product records.
- Operational history.
- Credentials.
- Platform accounts.
- Financial records.
- Marketing assets.
- Business-specific memory.
- Access permissions.

Do not assume that two businesses owned by the same person are legally the same entity.

Support explicit relationships between businesses without automatically combining their accounts or obligations.

---

6. CENTRAL PORTFOLIO INTELLIGENCE

Build the portfolio-level intelligence service.

Its purpose is to evaluate the business ecosystem and generate evidence-based strategic recommendations.

Intelligence capabilities

1. Portfolio health analysis.
2. Business performance comparison.
3. Growth opportunity detection.
4. Operational bottleneck detection.
5. Resource utilization analysis.
6. Risk concentration analysis.
7. Financial performance analysis.
8. Shared infrastructure optimization.
9. Cross-business collaboration discovery.
10. Strategic portfolio recommendations.

Example analysis

Suppose the portfolio contains:

- Business A: Digital publishing.
- Business B: AI SaaS platform.
- Business C: Content production agency.
- Business D: Online education platform.

The intelligence engine may discover:

- Business A can distribute content through Business C's authorized marketing infrastructure.
- Business B could provide software infrastructure to Business D.
- Business C may provide content services to Business A.
- Business D could create educational products based on validated audience demand.

These must be evaluated as potential business relationships, not automatically executed.

Recommendation format

Every portfolio recommendation must include:

- Recommendation ID.
- Affected businesses.
- Strategic objective.
- Supporting evidence.
- Expected benefit.
- Estimated cost.
- Potential revenue impact.
- Operational requirements.
- Financial implications.
- Legal and contractual considerations.
- Risks.
- Assumptions.
- Confidence level.
- Approval requirements.
- Proposed next steps.

Never present speculative synergy as verified revenue or guaranteed savings.

---

7. CROSS-BUSINESS OPPORTUNITY DISCOVERY

Integrate P-03.

Build a cross-business opportunity discovery service.

The engine should identify opportunities arising from relationships between businesses.

Opportunity categories

A. Shared Audience Opportunities

Identify audiences that may have legitimate overlapping needs.

B. Shared Infrastructure Opportunities

Identify tools, systems, or infrastructure that multiple businesses can use efficiently.

C. Complementary Product Opportunities

Identify products or services that naturally complement existing business offerings.

D. Cross-Promotion Opportunities

Identify suitable cross-promotion possibilities where customer consent, platform rules, and commercial agreements permit.

E. Shared Knowledge Opportunities

Identify knowledge that can improve multiple businesses without exposing restricted data.

F. Shared Service Opportunities

Identify services that one business may legitimately provide to another.

G. New Venture Opportunities

Identify new businesses that could emerge from validated capabilities, customer problems, and market demand.

Opportunity evaluation

Evaluate:

- Customer demand.
- Market evidence.
- Strategic compatibility.
- Financial feasibility.
- Operational complexity.
- Legal structure.
- Data-sharing restrictions.
- Customer consent.
- Conflict of interest.
- Brand impact.
- Risk exposure.

Do not create artificial opportunities merely to increase the number of businesses in the portfolio.

---

8. SHARED AGENT INFRASTRUCTURE

Integrate P-04 and P-12.

Build a controlled shared-agent coordination layer.

Agents may serve multiple businesses where appropriate, but their access must remain explicitly scoped.

Agent operating models

Support:

1. Business-exclusive agents.
2. Shared service agents.
3. Portfolio intelligence agents.
4. Temporary project agents.
5. Specialist agents.
6. Independent audit agents.

Examples

Agent| Possible responsibility
Portfolio Analyst| Analyze authorized portfolio-level metrics
Financial Analyst| Analyze approved financial data
Research Agent| Conduct authorized market research
SEO Agent| Support approved businesses
Development Agent| Work within assigned repositories
Content Agent| Produce business-specific content
Security Agent| Audit authorized systems
Operations Agent| Coordinate approved workflows

Agent assignment requirements

Every assignment must specify:

- Agent ID.
- Business ID or approved portfolio scope.
- Task ID.
- Required capabilities.
- Allowed tools.
- Allowed data.
- Budget scope.
- Permission level.
- Expiration or completion conditions.

Critical access rules

- Shared agents must not receive unrestricted portfolio access.
- An agent assigned to Business A must not automatically read Business B's customer information.
- Credentials must remain isolated.
- Business-specific memory must remain scoped.
- Portfolio-level agents may only access approved aggregate or explicitly authorized data.
- Agent access must be revocable.
- Every cross-business handoff must be audited.

---

9. SHARED SERVICES AND INFRASTRUCTURE

Build a shared services management layer.

The objective is to prevent unnecessary duplication across businesses.

Potential shared services include:

- AI model infrastructure.
- Research infrastructure.
- Content production tools.
- Development environments.
- Analytics infrastructure.
- Monitoring.
- Backup systems.
- Notification services.
- Document processing.
- Approved automation adapters.
- Internal operational services.

Shared service registry

Each shared service must have:

- Service ID.
- Name.
- Description.
- Provider.
- Supported business types.
- Availability.
- Capacity.
- Cost model.
- Security classification.
- Access policy.
- Service-level expectations.
- Usage records.

Service allocation

Allow businesses to request shared services.

Evaluate:

- Business eligibility.
- Available capacity.
- Expected cost.
- Security requirements.
- Performance impact.
- Priority.
- Resource limits.

Internal service charges

Where cost allocation is useful, maintain internal management accounting records.

Clearly distinguish:

- Actual external expense.
- Internal cost allocation.
- Intercompany invoice.
- Actual payment.
- Consolidated portfolio expense.

An internal allocation must never be treated as a real external cash payment.

Do not automatically create legal invoices or tax obligations from management-accounting allocations.

---

10. RESOURCE AND CAPACITY ALLOCATION

Build a portfolio-level resource planning engine.

Track shared resources such as:

- CPU.
- RAM.
- GPU.
- Storage.
- AI inference capacity.
- Agent availability.
- Development capacity.
- API quotas.
- Shared service capacity.
- Operational time.
- Approved budgets.

Resource allocation process

1. Identify resource requirements.
2. Retrieve current utilization.
3. Evaluate business priorities.
4. Check security and access constraints.
5. Check available capacity.
6. Estimate operational cost.
7. Evaluate the impact on other businesses.
8. Recommend allocation.
9. Obtain approval when required.
10. Allocate and monitor resources.
11. Reassess utilization.

Allocation principles

- Critical operational services receive appropriate protection.
- Resource allocation must be fair and configurable.
- Higher-revenue businesses must not automatically receive every resource.
- Strategic importance and survival needs must be considered.
- Prevent one business from monopolizing shared infrastructure.
- Use configurable quotas and concurrency limits.
- Reclaim idle resources safely.
- Preserve owner-defined reserves.

Resource scarcity

When resources are insufficient:

- Queue lower-priority work.
- Defer nonessential tasks.
- Reduce concurrency.
- Recommend infrastructure optimization.
- Present resource allocation alternatives.

Never silently exceed hard resource or financial limits.

---

11. PORTFOLIO FINANCIAL INTELLIGENCE

Integrate P-07.

Do not build a duplicate financial ledger.

Create a portfolio-level analytical layer over authoritative business financial records.

Financial visibility

Show:

- Revenue by business.
- Verified collected revenue.
- Expenses by business.
- Gross profit.
- Net profit.
- Cash balances where verified and authorized.
- Outstanding receivables.
- Outstanding liabilities.
- Budget utilization.
- Cash burn.
- Profitability trends.
- Portfolio concentration.
- Financial risk.

Critical financial distinctions

The system must distinguish:

1. Projected revenue.
2. Booked or invoiced revenue.
3. Collected revenue.
4. Refunded revenue.
5. Gross profit.
6. Net profit.
7. Cash balance.
8. Internal management allocations.
9. Actual intercompany transactions.

Never sum cash balances across unrelated legal entities and present the result as freely available portfolio cash.

Consolidated reporting

Support:

- Business-level reports.
- Portfolio-level management reports.
- Currency-normalized analytical views.
- Intercompany transaction adjustments where verified.
- Period comparisons.
- Scenario analysis.

Preserve original transaction currencies and exchange-rate evidence.

Clearly label estimates and converted figures.

Capital allocation recommendations

The engine may recommend:

- Increasing an approved business budget.
- Reducing unnecessary expenditure.
- Funding a validated experiment.
- Protecting working capital.
- Pausing a loss-making activity.
- Investing in shared infrastructure.

Actual movement of funds between businesses requires appropriate legal, financial, and owner authorization.

P-13 must never transfer money simply because its portfolio analysis recommends doing so.

---

12. PORTFOLIO RISK AND SURVIVAL MANAGEMENT

Integrate P-08 and P-10.

Evaluate both individual business risks and portfolio-wide exposure.

Business-level risk

- Financial instability.
- Customer concentration.
- Revenue volatility.
- Platform dependency.
- Technical instability.
- Legal exposure.
- Operational dependency.
- Security vulnerabilities.

Portfolio-level risk

- Excessive reliance on one revenue source.
- Excessive reliance on one platform.
- Shared infrastructure failure.
- Concentrated customer exposure.
- Correlated market risks.
- Excessive agent or resource dependency.
- Insufficient available capital.
- Cross-business security exposure.

Risk management actions

The system may recommend:

- Diversification.
- Cost reduction.
- Additional validation.
- Infrastructure separation.
- Business-specific autonomy reduction.
- Workflow suspension.
- Contingency planning.
- Business restructuring.

High-impact actions require appropriate authorization.

Portfolio survival mode

Implement a configurable survival mode.

When activated:

1. Identify financially or operationally endangered businesses.
2. Protect authorized reserves.
3. Prioritize essential business operations.
4. Defer discretionary spending.
5. Reduce unnecessary compute consumption.
6. Identify avoidable expenses.
7. Review outstanding liabilities.
8. Present recovery plans.
9. Request owner decisions where needed.

Do not automatically shut down businesses or redirect their funds.

---

13. CROSS-BUSINESS WORKFLOW COORDINATION

Integrate P-12.

Build a portfolio workflow coordination service.

Support workflows involving multiple businesses.

Example workflow

Objective: Launch a new educational digital product using existing portfolio capabilities.

Possible stages:

1. Business A supplies authorized research.
2. Business B supplies approved software infrastructure.
3. Business C supplies content production.
4. Business D supplies distribution through its authorized channels.
5. P-12 coordinates tasks.
6. P-13 manages cross-business scope and resource relationships.
7. P-07 records actual financial transactions.
8. P-10 enforces permissions and approvals.

Workflow requirements

Each cross-business workflow must define:

- Parent portfolio workflow.
- Participating businesses.
- Business-specific sub-workflows.
- Shared services.
- Assigned agents.
- Data-sharing agreements or permissions.
- Resource allocations.
- Budget responsibilities.
- Deliverables.
- Ownership of generated assets.
- Approval requirements.
- Success criteria.

Isolation

A portfolio workflow must not create unrestricted access between participating businesses.

Every business must explicitly authorize the information and resources it contributes.

---

14. BUSINESS RELATIONSHIP AND DEPENDENCY GRAPH

Build a relationship graph for the portfolio.

Represent relationships such as:

- Business owns product.
- Business uses service.
- Business provides service to another business.
- Business shares authorized infrastructure.
- Business has an approved partnership.
- Business serves an overlapping audience.
- Business depends on a platform.
- Business shares a resource.

Relationship attributes

- Relationship ID.
- Source business.
- Target business.
- Relationship type.
- Description.
- Status.
- Start date.
- End date.
- Agreement reference.
- Access scope.
- Financial implications.
- Risk classification.
- Approval status.

Support relationship states:

- PROPOSED
- UNDER_REVIEW
- APPROVED
- ACTIVE
- SUSPENDED
- TERMINATED
- EXPIRED

Do not infer legal ownership or contractual obligations from technical relationships.

---

15. CROSS-BUSINESS KNOWLEDGE AND MEMORY

Integrate P-09.

Build portfolio-level knowledge access without destroying business-level memory isolation.

Memory scopes

1. Global AUTONOMUS memory.
2. Portfolio memory.
3. Business memory.
4. Workflow memory.
5. Agent memory.
6. Shared service memory.

Knowledge-sharing rules

Information may move between scopes only when permitted.

Examples:

- Generalized lessons may be shared across businesses.
- Public market research may be reused where licensing permits.
- Business-specific customer records remain restricted.
- Credentials never enter shared memory.
- Confidential commercial information remains scoped.
- Financial details are exposed only to authorized roles.

Learning from portfolio outcomes

Learn from:

- Successful business launches.
- Failed experiments.
- Customer acquisition performance.
- Operational efficiency.
- Agent performance.
- Shared service utilization.
- Resource allocation outcomes.
- Risk incidents.

Record:

- Source business.
- Evidence.
- Context.
- Confidence.
- Applicability.
- Limitations.
- Permission scope.

Do not assume a strategy that worked in one business will work in every business.

---

16. PORTFOLIO STRATEGIC PLANNING

Build a strategic planning service.

Allow the owner to define:

- Portfolio mission.
- Long-term objectives.
- Business priorities.
- Risk tolerance.
- Capital constraints.
- Growth targets.
- Time horizons.
- Resource constraints.
- Businesses to develop or maintain.

Planning horizons

Support:

- Immediate operational planning.
- 30-day planning.
- 90-day planning.
- Annual planning.
- Long-term strategic planning.

Portfolio strategy outputs

Generate:

- Portfolio health assessment.
- Business priority ranking.
- Growth opportunities.
- Capital allocation proposals.
- Resource allocation proposals.
- Risk reduction strategies.
- New venture recommendations.
- Business restructuring proposals.

Strategic decision rules

Do not prioritize businesses solely by projected revenue.

Consider:

- Verified profitability.
- Cash requirements.
- Market evidence.
- Strategic value.
- Risk.
- Operational sustainability.
- Customer value.
- Owner priorities.

Every strategic plan must distinguish facts, estimates, assumptions, and recommendations.

---

17. BUSINESS EXPANSION AND NEW VENTURE MANAGEMENT

Integrate P-03, P-06, and P-08.

P-13 may recommend creating new businesses when justified by evidence.

Expansion workflow

1. Detect opportunity.
2. Gather market evidence.
3. Evaluate portfolio compatibility.
4. Check for existing business overlap.
5. Evaluate cannibalization risk.
6. Estimate capital requirements.
7. Evaluate operational requirements.
8. Evaluate legal and platform requirements.
9. Compare alternatives.
10. Prepare a business proposal.
11. Request owner approval.
12. Pass approved opportunities to P-06.
13. Monitor launch and performance through P-12.

Anti-duplication rule

Before creating a new business, determine whether the opportunity can be served through an existing business.

Avoid creating multiple businesses with indistinguishable products, audiences, or operations without a defensible strategic reason.

New venture proposal

Include:

- Business concept.
- Target customer.
- Customer problem.
- Market evidence.
- Business model.
- Competitive position.
- Expected costs.
- Funding requirements.
- Revenue scenarios.
- Risk analysis.
- Portfolio synergy.
- Cannibalization risk.
- Recommended validation experiment.
- Owner approval requirements.

P-13 recommends and coordinates. P-06 remains responsible for business creation.

---

18. PORTFOLIO COMMAND CENTER INTEGRATION

Extend P-11.

Do not redesign the existing Command Center unnecessarily.

Add a dedicated Business Portfolio section.

A. Portfolio Overview

Display:

- Total businesses.
- Active businesses.
- Businesses under development.
- Businesses at risk.
- Paused businesses.
- Verified portfolio revenue.
- Verified portfolio expenses.
- Portfolio profitability.
- Pending strategic decisions.

B. Business Portfolio Map

Show business relationships and dependencies.

Allow the owner to inspect each business and its authorized relationships.

C. Business Comparison

Compare:

- Revenue.
- Profitability.
- Expenses.
- Cash flow.
- Growth.
- Customer acquisition.
- Operational efficiency.
- Risk.
- Resource consumption.

Use consistent definitions and reporting periods.

D. Portfolio Intelligence

Show:

- Strategic insights.
- Cross-business opportunities.
- Risk concentration.
- Operational synergies.
- Resource bottlenecks.
- Recommendations.

E. Resource Allocation

Show:

- Available capacity.
- Current allocation.
- Business-level quotas.
- Shared infrastructure usage.
- Proposed reallocations.

F. Portfolio Finance

Show:

- Business-level financial summaries.
- Consolidated management views.
- Currency information.
- Intercompany adjustments where verified.
- Budget status.

G. Shared Services

Show:

- Registered services.
- Participating businesses.
- Service capacity.
- Usage.
- Costs.
- Service health.

H. Portfolio Risk Center

Show:

- Individual business risks.
- Shared infrastructure risks.
- Concentration risks.
- Cross-business dependencies.
- Recommended mitigation.

I. Strategic Planning

Allow the owner to:

- Define objectives.
- Review recommendations.
- Approve portfolio plans.
- Compare scenarios.
- Inspect business expansion proposals.

J. Portfolio Reports

Generate:

- Daily portfolio snapshots.
- Weekly business comparison reports.
- Monthly financial summaries.
- Quarterly strategic reviews.
- Risk reports.

All data must come from real backend services.

Never use fabricated portfolio metrics.

---

19. DATABASE AND BACKEND IMPLEMENTATION

Inspect existing database schemas before introducing new entities.

Potential logical entities include:

- "business_portfolios"
- "portfolio_business_memberships"
- "portfolio_objectives"
- "portfolio_strategies"
- "business_relationships"
- "cross_business_opportunities"
- "shared_services"
- "shared_service_access"
- "resource_quotas"
- "resource_allocations"
- "portfolio_workflows"
- "portfolio_workflow_memberships"
- "cross_business_permissions"
- "portfolio_risk_assessments"
- "portfolio_reports"
- "portfolio_decisions"
- "portfolio_scenarios"

These are proposed logical models, not mandatory duplicate table names.

Data requirements

- Referential integrity.
- Business-level isolation.
- Portfolio-level authorization.
- Transaction safety.
- Database migrations.
- Indexing.
- Audit history.
- Versioning where necessary.
- Explicit relationship states.
- Retention policies.

API requirements

Portfolio management

- Create portfolio.
- Retrieve portfolio.
- Update portfolio.
- Add business.
- Remove business from active membership.
- Archive portfolio.
- Retrieve portfolio history.

Business management

- Retrieve business profile.
- Compare businesses.
- Retrieve business relationships.
- Retrieve business health.

Portfolio intelligence

- Analyze portfolio.
- Generate recommendations.
- Retrieve cross-business opportunities.
- Generate risk assessment.

Resource management

- Retrieve shared capacity.
- Request allocation.
- Approve allocation.
- Revoke allocation.
- Retrieve usage.

Shared services

- Register service.
- Request access.
- Approve access.
- Revoke access.
- Retrieve utilization.

Strategic planning

- Create objective.
- Generate strategy.
- Compare scenarios.
- Submit proposal.
- Approve or reject proposal.

Reporting

- Generate portfolio report.
- Retrieve historical report.
- Export authorized portfolio data.

All APIs must enforce authentication, authorization, business scope, and audit requirements.

---

20. SECURITY, PRIVACY AND GOVERNANCE

Integrate P-10.

This is one of the most important parts of P-13.

Business isolation

Enforce isolation across:

- Database access.
- API requests.
- Agent context.
- Filesystem access.
- Credentials.
- Browser sessions.
- Financial records.
- Memory retrieval.
- External integrations.

Cross-business access

Every cross-business operation must specify:

- Source business.
- Target business.
- Purpose.
- Authorized data.
- Permitted actions.
- Expiration.
- Approval reference where required.

Data-sharing policies

Support:

- No sharing.
- Aggregate-only sharing.
- Specific record sharing.
- Read-only sharing.
- Controlled operational sharing.
- Time-limited access.

Security requirements

- Least privilege.
- Explicit authorization.
- Secret isolation.
- Secure credential storage.
- Audit logging.
- Prompt injection protection.
- Data export restrictions.
- Access revocation.
- Permission expiration.
- Secure backup and recovery.

Never allow portfolio intelligence to bypass business-level data permissions.

Never expose confidential customer information merely because businesses belong to the same portfolio.

---

21. TESTING AND VALIDATION

Implement unit, integration, security, performance, and end-to-end tests.

A. Portfolio tests

- Create portfolio.
- Register multiple businesses.
- Retrieve portfolio data.
- Compare businesses.
- Archive a business.
- Preserve historical records.
- Validate lifecycle transitions.

B. Isolation tests

- Business A cannot read Business B's restricted data.
- Shared agent cannot access unauthorized records.
- Portfolio reports respect access scope.
- Credentials remain isolated.
- Memory retrieval respects scope.
- Revoked permissions take effect.

C. Financial tests

- Portfolio reports use authoritative financial records.
- Internal allocations are not treated as cash payments.
- Separate entity cash balances remain distinguishable.
- Currency conversion retains original values and rates.
- Unverified revenue is excluded from collected revenue.
- Cross-business transfers require authorization.

D. Resource tests

- Enforce business quotas.
- Prevent resource monopolization.
- Reclaim eligible idle resources.
- Respect concurrency limits.
- Handle resource saturation.

E. Cross-business workflow tests

- Execute an authorized multi-business workflow.
- Reject unauthorized data sharing.
- Prevent unauthorized agent reassignment.
- Validate business-level approvals.
- Preserve workflow audit history.

F. Intelligence tests

- Detect valid shared-service opportunities.
- Detect potential business duplication.
- Identify concentration risks.
- Produce evidence-based recommendations.
- Distinguish speculation from verified evidence.

G. Failure tests

- Business becomes unavailable.
- Shared service becomes unavailable.
- Agent becomes unavailable.
- Cross-business workflow fails.
- Financial source becomes unavailable.
- Portfolio report contains incomplete data.

Mandatory acceptance scenarios

1. Register at least three independent businesses in one portfolio.
2. View their combined portfolio status.
3. Compare their performance.
4. Inspect each business independently.
5. Detect a legitimate cross-business opportunity.
6. Reject an unsupported synergy recommendation.
7. Allocate an authorized shared service.
8. Reject unauthorized shared service access.
9. Execute a multi-business workflow through P-12.
10. Prevent unauthorized cross-business data access.
11. Produce a portfolio financial report using verified data.
12. Distinguish internal cost allocation from external payment.
13. Identify portfolio-level concentration risk.
14. Generate a new venture proposal without automatically creating it.
15. Revoke shared agent permissions and verify access termination.
16. Generate a portfolio strategic report.
17. Confirm that P-11 accurately displays portfolio information.

Do not claim a test passed unless the test was actually executed and evidence is available.

---

22. IMPLEMENTATION STRATEGY

Implement P-13 in controlled stages.

Stage 1: Architecture Audit

- Inspect P-01 through P-12.
- Audit business identity models.
- Audit isolation mechanisms.
- Define portfolio boundaries.
- Prepare integration architecture.

Stage 2: Portfolio Foundation

- Implement portfolio registry.
- Implement business membership.
- Implement portfolio objectives.
- Implement lifecycle and relationship management.

Stage 3: Portfolio Intelligence

- Integrate P-02.
- Integrate P-03.
- Implement performance analysis.
- Implement cross-business opportunity discovery.
- Implement evidence-based recommendations.

Stage 4: Shared Agent and Service Management

- Integrate P-04.
- Implement scoped agent assignments.
- Implement shared service registry.
- Implement service permissions.
- Implement revocation.

Stage 5: Resource and Financial Coordination

- Integrate P-07.
- Integrate P-12.
- Implement capacity management.
- Implement resource quotas.
- Implement portfolio financial analytics.
- Implement capital allocation recommendations.

Stage 6: Risk and Memory Integration

- Integrate P-08.
- Integrate P-09.
- Integrate P-10.
- Implement risk concentration analysis.
- Implement controlled knowledge sharing.

Stage 7: Cross-business Workflow Coordination

- Implement portfolio workflows.
- Implement business participation.
- Implement approved data sharing.
- Implement workflow dependencies.
- Implement audit trails.

Stage 8: Command Center Integration

- Extend P-11.
- Implement portfolio dashboards.
- Implement business comparison.
- Implement resource views.
- Implement strategic planning.
- Implement portfolio reporting.

Stage 9: Validation and Audit

- Run all tests.
- Conduct security audit.
- Validate financial reporting.
- Test business isolation.
- Test multi-business workflows.
- Produce final implementation report.

Do not skip validation stages.

---

23. DOCUMENTATION REQUIREMENTS

Create:

"docs/multi-business/P13_IMPLEMENTATION_REPORT.md"

Include:

1. Executive summary.
2. Pre-implementation audit.
3. Architecture implemented.
4. Portfolio data model.
5. Business isolation architecture.
6. Shared agent architecture.
7. Shared services.
8. Resource allocation.
9. Portfolio intelligence.
10. Financial reporting.
11. Risk management.
12. Cross-business workflows.
13. Security controls.
14. APIs and database changes.
15. Command Center integration.
16. Tests executed.
17. Acceptance scenario results.
18. Performance findings.
19. Known limitations.
20. Unresolved risks.
21. Recommended next steps.

Also create:

- "docs/multi-business/P13_ARCHITECTURE.md"
- "docs/multi-business/P13_BUSINESS_ISOLATION.md"
- "docs/multi-business/P13_PORTFOLIO_FINANCE.md"
- "docs/multi-business/P13_SHARED_SERVICES.md"
- "docs/multi-business/P13_SECURITY_MODEL.md"
- "docs/multi-business/P13_API_REFERENCE.md"

Update the main architecture documentation and diagrams.

---

24. DEFINITION OF DONE

P-13 is complete only when:

- Multiple independent businesses can be registered and managed.
- Portfolio-level intelligence works.
- Business isolation is enforced.
- Cross-business relationships are supported.
- Shared agents operate with scoped permissions.
- Shared services can be managed.
- Resource allocation is controlled.
- Portfolio financial reports use authoritative data.
- Cross-business opportunities are evidence-based.
- Portfolio risks can be identified.
- Cross-business workflows integrate with P-12.
- Memory sharing respects business boundaries.
- P-10 governance cannot be bypassed.
- P-11 displays accurate portfolio information.
- Relevant automated tests pass.
- Documentation is complete.

Any incomplete capability must be explicitly identified.

Do not mark P-13 production-ready if critical isolation, financial, or security tests fail.

---

25. STRICT DEVELOPMENT RULES

1. Preserve all existing AUTONOMUS functionality.
2. Do not rebuild the system.
3. Do not merge independent business identities.
4. Do not duplicate authoritative financial records.
5. Do not expose business credentials across businesses.
6. Do not provide unrestricted portfolio access to agents.
7. Do not automatically transfer money between businesses.
8. Do not assume common ownership means common legal identity.
9. Do not fabricate portfolio metrics.
10. Do not treat projected revenue as collected revenue.
11. Do not treat internal accounting allocations as actual payments.
12. Do not automatically create new businesses from recommendations.
13. Do not allow unauthorized cross-business data sharing.
14. Do not bypass P-10.
15. Do not bypass P-07.
16. Maintain auditability.
17. Use modular, maintainable, typed code.
18. Test before declaring completion.
19. Document architectural decisions.
20. Preserve owner authority over strategic and financial decisions.

---

26. FINAL EXECUTION INSTRUCTION

Begin by auditing the existing AUTONOMUS codebase and modules P-01 through P-12.

Prepare the implementation architecture.

Implement P-13 through the stages defined above.

Integrate the new portfolio capabilities with existing modules.

Run the relevant tests after every major implementation stage.

Produce the complete P-13 implementation report with evidence.

Classify every requirement as:

- IMPLEMENTED AND VERIFIED
- IMPLEMENTED BUT NOT FULLY VERIFIED
- PARTIALLY IMPLEMENTED
- NOT IMPLEMENTED
- BLOCKED

Do not hide incomplete functionality or unresolved risks.

Do not claim production readiness without passing the critical security and isolation tests.

FINAL STOP CONDITION:

After P-13 implementation, integration, testing, documentation, and final audit, stop.

Do not begin P-14 automatically.

Present the complete implementation report and wait for explicit owner approval before proceeding to:

P-14: INTEGRATION AND SYSTEM AUDIT.

The ultimate objective is to build a unified AI-managed business ecosystem in which independent businesses can collaborate, share approved resources, benefit from common intelligence, and grow strategically without sacrificing financial integrity, data isolation, operational independence, or owner control.

P-13 COMPLETION MEANS ONE INTELLIGENT BUSINESS ECOSYSTEM, NOT ONE GIANT SHARED BUSINESS ACCOUNT.
