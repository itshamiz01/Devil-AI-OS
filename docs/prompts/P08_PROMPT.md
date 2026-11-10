AUTONOMUS P-08: SURVIVAL AND SCALING ENGINE

Master Implementation Prompt | Phase 8

---

1. ROLE AND MISSION

Act as a Principal Autonomous Systems Architect, Chief Strategy Officer, Business Operations Architect, Financial Risk Analyst, Growth Systems Engineer, Portfolio Management Specialist, and AI Decision Intelligence Engineer.

Your mission is to inspect, design, implement, test, and integrate the Survival and Scaling Engine (P-08) into the existing AUTONOMUS AI Business Operating System.

You are not building a simple business dashboard, a collection of business tips, or an AI chatbot that recommends whether a business should grow.

You are building a decision-making and business lifecycle management system that continuously evaluates the performance, sustainability, risks, and growth opportunities of every business managed by AUTONOMUS.

The engine must help AUTONOMUS determine:

1. Which businesses should continue operating?
2. Which businesses need immediate intervention?
3. Which businesses should receive additional resources?
4. Which businesses are consuming resources without producing sufficient results?
5. Which experiments should continue, change, or stop?
6. When should a business increase its marketing budget?
7. When should a business expand into another market?
8. When should a business introduce new products or services?
9. When should a business hire or deploy additional agents?
10. When should a business reduce operating costs?
11. When should a business pause operations?
12. When should a business be permanently closed?
13. How much capital can safely be allocated to each business?
14. How should AUTONOMUS distribute limited resources across multiple businesses?
15. How can the system identify a business that appears successful but is financially unstable?
16. How can it distinguish temporary growth from sustainable growth?
17. How can it learn from failed businesses without repeating the same mistakes?

The engine must convert verified operational and financial evidence into controlled business decisions.

Core principle: AUTONOMUS must optimize for sustainable, risk-adjusted business performance, not vanity metrics, uncontrolled expansion, or short-term revenue.

---

2. DEVELOPMENT CONTEXT AND LOCKED ARCHITECTURE

AUTONOMUS is a Windows-first AI Business Operating System.

The following architecture decisions are locked:

- Platform: Windows-first.
- AI infrastructure: Hybrid, local AI by default, optional cloud AI.
- Mandatory paid AI APIs: Not permitted.
- Backend: Python + FastAPI.
- Frontend: React + TypeScript.
- Desktop direction: Tauri.
- Initial database: SQLite.
- Future database scalability: PostgreSQL.
- Local AI: Ollama and compatible GGUF models.
- Vector memory: ChromaDB or replaceable alternative.
- Browser automation: Playwright.
- Source control: Git and GitHub.
- Agent architecture: Shared, resource-aware AI infrastructure.
- Autonomy model: Controlled autonomy.
- Human owner: Ultimate decision authority.

The system must be designed for modest hardware and must not assume unlimited processing capacity, cloud resources, or financial capital.

2.1 Previous-phase dependencies

Before making any changes, inspect the actual implementations of:

- P-01: Core Operating System.
- P-02: Master Intelligence Engine.
- P-03: Opportunity Discovery Engine.
- P-04: Dynamic Agent Factory.
- P-05: Universal Digital Execution Engine.
- P-06: Business Creation Engine.
- P-07: Financial Intelligence Engine.

Read the existing documentation, code, tests, database schema, API contracts, and integration interfaces.

Verify that the following capabilities actually exist:

- Business identity and lifecycle management.
- Opportunity evidence and validation.
- Agent management and task execution.
- Digital execution and operational monitoring.
- Business performance records.
- Financial ledger and verified revenue records.
- Actual expenses and cash-flow reporting.
- Budget enforcement and protected reserves.
- Reconciliation and financial health.
- Approval and permission controls.
- Audit logging.
- Memory and historical decision records.

Do not assume that previous phases are complete simply because their development prompts were executed.

2.2 Preservation rules

- Do not rebuild AUTONOMUS.
- Do not replace working modules unnecessarily.
- Do not create a competing financial intelligence engine.
- Do not duplicate the business lifecycle system.
- Do not bypass existing permission controls.
- Do not create a second agent management system.
- Do not modify previous-phase interfaces without documenting the change.
- Preserve existing functionality.
- Reuse existing services and data models.
- Record significant architectural changes using ADRs.

If a dependency is missing or incomplete, document it and implement only the minimum safe integration required.

---

3. THE SURVIVAL AND SCALING CONSTITUTION

The following rules govern every business decision.

3.1 Survival before expansion

AUTONOMUS must protect the long-term survival of the business portfolio.

It must not:

- Scale an unvalidated business.
- Spend money merely because a business has cash available.
- Increase advertising budgets based only on impressions or clicks.
- Hire additional agents without a verified workload requirement.
- Expand into a new market without evaluating its economics and risks.
- Continue a failing experiment indefinitely.
- Hide poor performance by changing historical metrics.
- Use projected revenue as proof of business sustainability.
- Treat a high opportunity score as proof of profitability.
- Risk protected capital to rescue an unviable business.
- Continue spending simply because resources have already been invested.

Sunk costs must not determine future decisions.

Decisions must be based on future expected value, evidence, risk, and available resources.

3.2 Growth must be earned

A business may receive additional capital or operational resources only when it satisfies defined readiness criteria.

Growth readiness must consider:

- Verified demand.
- Collected revenue.
- Actual profitability or defensible contribution economics.
- Customer retention.
- Refund and dispute rates.
- Operational capacity.
- Customer satisfaction.
- Financial health.
- Cash-flow sustainability.
- Legal and platform compliance.
- Delivery reliability.
- Evidence quality.
- Scalability of the operating model.

No single metric can override a critical failure in another area.

3.3 Human ownership

The human owner retains ultimate authority.

AUTONOMUS may independently perform explicitly authorized, reversible, low-risk operational actions.

However, the following require owner approval:

- Major capital allocation.
- Increasing business spending limits.
- Material changes to business strategy.
- Entering high-risk markets.
- Taking on substantial financial obligations.
- Permanently closing a business.
- Transferring business ownership.
- Changing protected reserves.
- Disabling governance controls.
- Any irreversible or legally significant action.

An AI agent cannot authorize itself to perform a restricted action.

---

4. SURVIVAL AND SCALING ENGINE ARCHITECTURE

Build P-08 as a modular subsystem.

Suggested logical structure:

survival_scaling/

- core/
  - decision_engine.py
  - lifecycle_manager.py
  - policy_engine.py
  - decision_registry.py
- monitoring/
  - business_monitor.py
  - performance_monitor.py
  - financial_monitor.py
  - operational_monitor.py
- health/
  - business_health.py
  - sustainability_score.py
  - risk_assessment.py
  - stability_analysis.py
- experiments/
  - experiment_manager.py
  - hypothesis_tracker.py
  - experiment_evaluator.py
  - stop_loss_manager.py
- growth/
  - growth_readiness.py
  - scaling_planner.py
  - market_expansion.py
  - product_expansion.py
  - customer_acquisition.py
- optimization/
  - cost_optimizer.py
  - conversion_optimizer.py
  - retention_optimizer.py
  - operational_optimizer.py
- portfolio/
  - portfolio_manager.py
  - capital_allocator.py
  - resource_allocator.py
  - concentration_analyzer.py
- forecasting/
  - survival_forecast.py
  - growth_forecast.py
  - risk_scenarios.py
- interventions/
  - intervention_manager.py
  - recovery_planner.py
  - pause_manager.py
  - closure_manager.py
- learning/
  - outcome_analyzer.py
  - decision_evaluator.py
  - strategy_memory.py
- reporting/
  - survival_reports.py
  - growth_reports.py
  - portfolio_reports.py
- api/
- models/
- services/
- tests/

This is a logical architecture, not permission to duplicate existing modules.

Use existing project conventions and reuse previous-phase components.

---

5. BUSINESS LIFECYCLE MANAGEMENT

Implement an evidence-based lifecycle management system.

The engine must understand that a business progresses through different operational states.

5.1 Business lifecycle states

Support the following states, integrating with P-06 rather than creating a conflicting state machine:

1. PROPOSED
2. VALIDATING
3. APPROVED
4. BUILDING
5. LAUNCH_READY
6. LAUNCHED
7. EARLY_OPERATIONS
8. GROWING
9. STABLE
10. SCALING
11. OPTIMIZING
12. AT_RISK
13. RECOVERY
14. PAUSED
15. CLOSURE_REVIEW
16. CLOSED
17. ARCHIVED

Not every business must pass through every state.

5.2 State transition rules

Every transition must define:

- Previous state.
- Target state.
- Required evidence.
- Eligibility conditions.
- Risk checks.
- Required permissions.
- Approval requirements.
- Responsible actor.
- Transition timestamp.
- Reason.
- Resulting actions.

Examples:

A business cannot move from LAUNCH_READY to GROWING merely because its website has been deployed.

It must demonstrate operational activity and sufficient evidence of customer demand.

A business cannot move from GROWING to SCALING solely because its revenue increased for one week.

It must satisfy the configured growth readiness criteria.

A business entering AT_RISK must trigger investigation and a recovery assessment.

A business entering CLOSURE_REVIEW must undergo a structured evaluation before permanent closure.

5.3 Lifecycle history

Maintain an immutable history of important state transitions.

Store:

- Business ID.
- Previous state.
- New state.
- Decision ID.
- Evidence references.
- Decision explanation.
- Approval record.
- Timestamp.
- Responsible actor.

Do not silently rewrite historical business lifecycle records.

---

6. CONTINUOUS BUSINESS MONITORING ENGINE

Create a monitoring system that tracks business performance over time.

The system must not depend entirely on manual requests.

It should collect available evidence from existing AUTONOMUS services and authorized integrations.

6.1 Financial monitoring

Use P-07 as the authoritative source for financial data.

Monitor:

- Verified collected revenue.
- Actual expenses.
- Gross profit.
- Net profit, where sufficiently supported.
- Contribution margin.
- Available cash.
- Protected reserves.
- Cash-flow trends.
- Operating burn.
- Outstanding liabilities.
- Refund rates.
- Chargeback rates.
- Budget utilization.
- Recurring commitments.
- Financial health.
- Reconciliation discrepancies.

Never recreate financial calculations independently if P-07 already provides them.

6.2 Commercial monitoring

Monitor:

- Qualified leads.
- Customers acquired.
- Conversion rate.
- Average order value.
- Repeat purchases.
- Customer retention.
- Churn.
- Customer acquisition cost.
- Customer lifetime value estimates.
- Sales pipeline.
- Revenue concentration.
- Channel performance.
- Customer complaints.
- Refund requests.

Do not treat traffic, impressions, followers, or downloads as proof of commercial success.

6.3 Operational monitoring

Monitor:

- Product availability.
- Service uptime.
- Website health.
- Delivery completion.
- Task success rate.
- Failed automation runs.
- Customer support response times.
- Agent task completion.
- Operational backlog.
- Infrastructure reliability.
- Third-party dependency failures.
- Recurring maintenance workload.

6.4 Strategic monitoring

Monitor:

- Market changes.
- Competitor activity.
- Customer demand changes.
- Product relevance.
- Distribution channel risk.
- Platform policy changes.
- Market saturation.
- Legal or regulatory changes.
- Emerging opportunities.
- Business model weaknesses.

Use authorized information sources and preserve source provenance.

Do not treat an unverified market rumor as a confirmed business risk.

6.5 Monitoring frequency

Support configurable schedules:

- Near-real-time event-driven monitoring where available.
- Hourly checks for critical system signals.
- Daily operational summaries.
- Weekly business reviews.
- Monthly financial and strategic reviews.
- Quarterly portfolio reviews.

Do not use unnecessary continuous polling.

Use event-driven updates and bounded scheduled jobs.

---

7. BUSINESS HEALTH AND SUSTAINABILITY ENGINE

Develop a comprehensive business health assessment.

The system must evaluate a business using multiple dimensions.

7.1 Health dimensions

Evaluate:

A. Financial health

- Cash availability.
- Actual profitability.
- Cash-flow sustainability.
- Debt and liabilities.
- Budget compliance.
- Refund exposure.

B. Market health

- Customer demand.
- Purchase intent.
- Competitive pressure.
- Market relevance.
- Customer acquisition feasibility.

C. Commercial health

- Collected revenue.
- Conversion.
- Customer retention.
- Repeat sales.
- Pricing viability.
- Revenue concentration.

D. Operational health

- Delivery capability.
- Reliability.
- Support workload.
- Automation stability.
- Infrastructure capacity.

E. Product health

- Product quality.
- Customer satisfaction.
- Product usage.
- Defect rates.
- Value delivery.
- Retention.

F. Strategic health

- Competitive advantage.
- Business model resilience.
- Distribution diversity.
- Platform dependency.
- Ability to adapt.

G. Governance and compliance health

- Legal and regulatory risks.
- Platform policy compliance.
- Data protection.
- Financial authorization compliance.
- Security incidents.

7.2 Business health classification

Create configurable statuses:

- EXCELLENT.
- HEALTHY.
- STABLE.
- WATCH.
- AT_RISK.
- CRITICAL.
- INSUFFICIENT_DATA.

The system must explain every classification.

7.3 Health scoring

A configurable weighted scoring model may be used as a secondary summary.

Proposed initial weights:

Dimension| Weight
Financial health| 25%
Market health| 15%
Commercial health| 15%
Operational health| 15%
Product health| 10%
Strategic health| 10%
Governance and compliance| 10%

Weights must be configurable by business model.

However, hard risk gates must override the numerical score.

Examples:

- A confirmed serious compliance violation blocks scaling.
- A critical security incident may force a pause.
- Insufficient cash to meet known obligations may trigger AT_RISK.
- Unverified revenue cannot improve the verified financial health assessment.
- An unresolved critical reconciliation discrepancy may block material capital allocation.

7.4 Evidence confidence

Every health dimension must include:

- Score or classification.
- Evidence references.
- Data freshness.
- Confidence level.
- Missing information.
- Key assumptions.

A high score based on poor evidence must not be presented as a reliable result.

---

8. BUSINESS DECISION ENGINE

This is the central decision-making module.

The engine must transform monitoring results into specific, explainable business decisions.

8.1 Supported decision types

- CONTINUE.
- MONITOR.
- INVESTIGATE.
- IMPROVE.
- OPTIMIZE.
- RUN_EXPERIMENT.
- REDUCE_COSTS.
- INCREASE_RESOURCES.
- SCALE.
- EXPAND_MARKET.
- EXPAND_PRODUCT.
- CHANGE_STRATEGY.
- RECOVER.
- PAUSE.
- REVIEW_FOR_CLOSURE.
- CLOSE.

Each decision must include:

- Decision ID.
- Business ID.
- Decision type.
- Trigger.
- Supporting evidence.
- Relevant metrics.
- Risk assessment.
- Expected benefit.
- Estimated cost.
- Expected downside.
- Confidence.
- Reversibility.
- Time horizon.
- Required approval.
- Expiration date.
- Review conditions.

8.2 Decision quality

Every recommendation must explain:

1. What is happening?
2. Why does it matter?
3. What evidence supports the conclusion?
4. What are the available options?
5. What is the recommended action?
6. What could go wrong?
7. What will the action cost?
8. What result is expected?
9. How will success be measured?
10. When should the decision be reviewed?

Do not produce generic recommendations such as "increase marketing" without explaining the underlying problem, budget requirement, and expected result.

8.3 Decision alternatives

Where appropriate, compare at least three alternatives:

- Maintain current operations.
- Improve the existing business.
- Invest in expansion.

Other options may include reducing costs, changing the product, pausing, or closing.

Do not force three alternatives when some are clearly unsafe or prohibited.

8.4 Decision scoring

Implement a configurable decision evaluation framework considering:

- Expected financial outcome.
- Risk-adjusted return.
- Cash requirements.
- Evidence confidence.
- Strategic importance.
- Operational feasibility.
- Reversibility.
- Time to results.
- Opportunity cost.
- Downside exposure.

Numerical scores are decision-support tools, not automatic permission.

Hard governance rules always take precedence.

---

9. EXPERIMENT MANAGEMENT AND VALIDATION

AUTONOMUS must treat business experiments as controlled investments.

This is essential for preventing endless spending on unproven ideas.

9.1 Experiment lifecycle

Support:

- PROPOSED.
- DESIGNED.
- APPROVED.
- RUNNING.
- OBSERVING.
- SUCCESSFUL.
- INCONCLUSIVE.
- FAILED.
- STOPPED.
- ARCHIVED.

9.2 Experiment specification

Every experiment must define:

- Business ID.
- Experiment ID.
- Hypothesis.
- Problem being investigated.
- Target customer.
- Expected outcome.
- Success metric.
- Failure metric.
- Minimum evidence requirement.
- Maximum duration.
- Approved budget.
- Maximum acceptable loss.
- Operational requirements.
- Required agents.
- Data sources.
- Evaluation schedule.
- Owner approval status.

9.3 Experiment examples

Examples:

- Testing two product prices.
- Testing a new landing page.
- Testing a new customer acquisition channel.
- Testing a new product feature.
- Testing a new target audience.
- Testing a subscription offer.
- Testing an alternative content format.

9.4 Experiment stop-loss protection

Every paid experiment must have:

- Approved spending cap.
- Maximum acceptable loss.
- Time limit.
- Performance threshold.
- Stop conditions.

Stop or pause an experiment when:

- Its approved budget is exhausted.
- Its maximum acceptable loss is reached.
- A serious compliance or security risk emerges.
- Its underlying hypothesis becomes invalid.
- Required evidence cannot be obtained.
- It violates the owner's authorization policy.

An experiment must not continue merely because it has already consumed money.

9.5 Experiment evaluation

At completion, classify the result:

- VALIDATED.
- PARTIALLY_VALIDATED.
- INCONCLUSIVE.
- INVALIDATED.
- FAILED.

Store:

- Original hypothesis.
- Actual outcome.
- Costs.
- Results.
- Evidence.
- Unexpected findings.
- Lessons.
- Recommended next step.

Preserve failed experiments as learning records.

Do not delete them to make the business appear successful.

---

10. SCALING READINESS ENGINE

Build a dedicated engine to determine whether a business is ready to scale.

Scaling is a controlled increase in resources, capacity, distribution, customers, or market reach.

It must not be treated as a reward for good-looking dashboard metrics.

10.1 Scaling readiness requirements

Evaluate:

Demand validation

- Verified paying customers.
- Consistent purchase demand.
- Repeat demand where relevant.
- Evidence of customer value.

Financial validation

- Verified collected revenue.
- Contribution margin.
- Actual expenses.
- Cash-flow sustainability.
- Available capital.
- Protected reserves.
- Budget compliance.

Operational readiness

- Reliable delivery.
- Stable product or service.
- Documented processes.
- Support capacity.
- Infrastructure capacity.
- Manageable failure rate.

Commercial readiness

- Customer acquisition economics.
- Conversion stability.
- Retention.
- Refund levels.
- Pricing validation.
- Distribution channel performance.

Risk readiness

- Legal and compliance status.
- Platform dependency.
- Security.
- Revenue concentration.
- Supplier dependency.
- Financial downside.

10.2 Scaling stages

Support progressive scaling:

Stage 0: Unvalidated

- No proven customer demand.
- No material expansion.

Stage 1: Initial validation

- Initial evidence of demand.
- Small controlled experiments.

Stage 2: Repeatable acquisition

- Consistent acquisition and conversion.
- Controlled incremental growth.

Stage 3: Operational stability

- Reliable product delivery.
- Defensible unit economics.
- Repeatable operating processes.

Stage 4: Controlled scaling

- Gradual increase in budget, capacity, or distribution.

Stage 5: Multi-channel expansion

- Diversified acquisition and distribution.
- Greater operational capacity.

Stage 6: Mature operation

- Stable operating model.
- Strong reporting.
- Sustainable profitability or another explicitly defined strategic objective.

These stages must be configurable and business-model aware.

A content business and a SaaS business should not have identical scaling requirements.

10.3 Scaling gate

Before recommending scale, generate a formal readiness report.

It must show:

- Readiness status.
- Satisfied conditions.
- Unsatisfied conditions.
- Financial impact.
- Expected capacity requirements.
- Operational risks.
- Proposed scaling amount.
- Downside scenario.
- Owner approval requirements.

If critical conditions are unsatisfied, scaling must be blocked or limited to a specifically approved experiment.

10.4 Incremental scaling

Prefer small, measurable increments.

For example:

A business has an approved marketing budget of ₹10,000.

The system must not automatically increase it to ₹50,000 because a campaign appears successful.

Instead:

1. Review verified campaign results.
2. Evaluate customer acquisition cost.
3. Evaluate contribution margin.
4. Evaluate available capital.
5. Propose a limited budget increase.
6. Define success and stop conditions.
7. Obtain approval where required.
8. Measure actual results before proposing another increase.

---

11. GROWTH STRATEGY ENGINE

Develop a growth strategy system that evaluates multiple ways to increase business value.

11.1 Growth pathways

Support:

A. Customer acquisition

- New acquisition channels.
- Conversion improvements.
- Referral programs.
- Partnerships.
- Search and content distribution.
- Compliant advertising.

B. Customer retention

- Better onboarding.
- Customer support improvements.
- Product quality.
- Membership or subscription retention.
- Repeat purchase programs.

C. Product expansion

- New products.
- Product upgrades.
- Additional features.
- Premium offerings.
- Bundles.

D. Market expansion

- New geographic markets.
- New customer segments.
- New industries.
- New languages.
- New distribution channels.

E. Revenue optimization

- Pricing experiments.
- Subscription models.
- Product bundles.
- Upsells.
- Cross-sells.
- Licensing.

F. Operational leverage

- Process automation.
- Improved agent workflows.
- Reduced delivery costs.
- Better infrastructure utilization.
- Standard operating procedures.

11.2 Growth opportunity evaluation

Each growth opportunity must be assessed for:

- Customer demand.
- Market size and accessibility.
- Revenue potential.
- Contribution margin.
- Implementation cost.
- Time to value.
- Operational complexity.
- Competition.
- Legal and platform risks.
- Strategic fit.
- Confidence in the evidence.

Use P-03 for market and opportunity research.

Do not build a duplicate opportunity discovery engine.

11.3 Growth experiment plans

Every proposed growth action should contain:

- Objective.
- Hypothesis.
- Target customer.
- Required work.
- Required agents.
- Budget.
- Duration.
- Success metrics.
- Failure thresholds.
- Expected results.
- Risk controls.
- Review date.

---

12. COST OPTIMIZATION AND OPERATIONAL EFFICIENCY

Build a cost optimization system.

The goal is not to reduce every expense indiscriminately.

The goal is to eliminate unnecessary costs while preserving the quality and reliability of the business.

12.1 Cost analysis

Evaluate:

- Hosting costs.
- Software subscriptions.
- AI inference costs.
- API usage.
- Advertising expenditure.
- Contractor costs.
- Content production costs.
- Operational overhead.
- Unused services.
- Duplicate subscriptions.
- Inefficient automation workflows.

Use P-07 for authoritative expense and budget data.

12.2 Cost optimization recommendations

Examples:

- Replace an unnecessary paid service with a suitable free alternative.
- Reduce unused hosting resources.
- Consolidate duplicate tools.
- Optimize local AI usage.
- Reduce repeated LLM calls.
- Automate repetitive operational tasks.
- Improve conversion to reduce wasted acquisition spend.
- Eliminate unproductive campaigns.

Every recommendation must include:

- Current cost.
- Proposed cost.
- Expected savings.
- Implementation cost.
- Risks.
- Service quality impact.
- Reversibility.

12.3 Cost reduction restrictions

Never automatically cancel a service if doing so could:

- Cause data loss.
- Interrupt customer delivery.
- Break production infrastructure.
- Violate a contractual obligation.
- Cause loss of access.
- Create security vulnerabilities.

Require approval for material or irreversible changes.

---

13. BUSINESS RECOVERY ENGINE

A business may become unhealthy without being immediately worthless.

Create a structured recovery process.

13.1 Recovery triggers

Examples:

- Falling revenue.
- Negative contribution margin.
- High customer churn.
- Increasing refunds.
- Excessive operating costs.
- Poor conversion.
- Declining demand.
- Operational failures.
- Cash-flow deterioration.
- Platform dependency risks.

13.2 Recovery assessment

Identify:

1. Root cause.
2. Financial impact.
3. Operational impact.
4. Customer impact.
5. Market impact.
6. Recoverability.
7. Required resources.
8. Expected recovery time.
9. Probability of recovery.
10. Maximum acceptable recovery cost.

Distinguish temporary problems from structural business model failures.

13.3 Recovery plan

Generate a controlled recovery plan containing:

- Priority problems.
- Corrective actions.
- Responsible agents.
- Budget.
- Timeline.
- Expected outcomes.
- Monitoring schedule.
- Success thresholds.
- Failure thresholds.
- Escalation rules.

A recovery plan must have a finite budget and review period.

Do not allow an unprofitable business to consume resources indefinitely under the label of recovery.

13.4 Recovery outcomes

Classify:

- RECOVERED.
- IMPROVING.
- NO_SIGNIFICANT_CHANGE.
- DETERIORATING.
- RECOVERY_FAILED.

Use these results to inform future decisions.

---

14. BUSINESS PAUSE AND CLOSURE ENGINE

Implement a structured process for pausing and closing businesses.

14.1 Pause conditions

A business may need to pause because of:

- Temporary market conditions.
- Operational problems.
- Security incidents.
- Legal uncertainty.
- Insufficient resources.
- Infrastructure failure.
- Owner instruction.
- A failed experiment requiring redesign.

Pausing must preserve business records and learning history.

14.2 Closure evaluation

Before recommending permanent closure, assess:

- Historical financial performance.
- Outstanding liabilities.
- Unpaid invoices.
- Customer obligations.
- Refund obligations.
- Active subscriptions.
- Contracts.
- Data retention requirements.
- Intellectual property.
- Domain and hosting dependencies.
- Platform obligations.
- Potential recovery value.
- Remaining asset value.

Do not automatically abandon a business that still has customers, obligations, or assets.

14.3 Closure workflow

Implement:

PROPOSED_CLOSURE
→ RISK_REVIEW
→ FINANCIAL_REVIEW
→ CUSTOMER_OBLIGATION_REVIEW
→ OWNER_APPROVAL
→ WIND_DOWN
→ CLOSED
→ ARCHIVED

The exact stages may be adapted to existing architecture.

14.4 Wind-down procedure

Where applicable:

- Stop new customer acquisition.
- Disable new sales.
- Resolve customer orders.
- Process authorized refunds.
- Resolve outstanding obligations.
- Export required records.
- Preserve financial history.
- Preserve relevant business assets.
- Cancel services only after dependency checks.
- Record final financial position.
- Archive the business.

Permanent closure requires explicit owner approval.

The system must not delete the underlying business history.

---

15. MULTI-BUSINESS PORTFOLIO MANAGEMENT

AUTONOMUS is intended to manage multiple businesses.

P-08 must therefore evaluate the portfolio as a whole rather than optimizing every business independently.

15.1 Portfolio overview

Monitor:

- Number of active businesses.
- Number of businesses in validation.
- Number of growing businesses.
- Number of stable businesses.
- Number of at-risk businesses.
- Number of paused businesses.
- Total verified collected revenue.
- Total actual expenses.
- Consolidated profitability.
- Available portfolio capital.
- Protected reserves.
- Outstanding obligations.
- Capital committed to experiments.
- Business concentration.
- Portfolio risk.

Use P-07 for authoritative consolidated financial information.

15.2 Portfolio risk

Evaluate:

- Revenue concentration.
- Customer concentration.
- Platform dependency.
- Geographic concentration.
- Supplier concentration.
- Infrastructure dependency.
- Shared agent dependency.
- Shared technology dependency.
- Correlated market risks.
- Liquidity risk.

A portfolio with ten businesses dependent on the same platform must not be treated as diversified merely because it has ten business records.

15.3 Portfolio diversification

Recommend diversification when it meaningfully reduces risk.

Evaluate:

- Different customer segments.
- Different distribution channels.
- Different revenue models.
- Different markets.
- Different product categories.
- Different infrastructure dependencies.

Do not diversify merely to increase the number of businesses.

Diversification must have a defensible strategic and financial purpose.

---

16. CAPITAL ALLOCATION ENGINE

Build a controlled capital allocation framework.

The objective is to allocate limited capital toward businesses and experiments with defensible expected value while protecting the owner's capital.

16.1 Capital allocation inputs

Use:

- Available cash from P-07.
- Protected reserves.
- Existing commitments.
- Approved budgets.
- Business health.
- Growth readiness.
- Expected return.
- Risk exposure.
- Evidence quality.
- Cash-flow needs.
- Opportunity cost.
- Portfolio concentration.

Never treat total cash balance as unrestricted capital.

16.2 Allocation categories

Support:

- Business operating capital.
- Experiment capital.
- Growth capital.
- Emergency capital.
- Recovery capital.
- Reserve capital.

Each allocation must have:

- Source.
- Destination.
- Amount.
- Currency.
- Purpose.
- Expected result.
- Maximum loss.
- Approval status.
- Allocation date.
- Review date.

16.3 Capital allocation methodology

Implement explainable methods such as:

- Rule-based allocation.
- Risk-adjusted opportunity scoring.
- Scenario comparison.
- Capital efficiency.
- Marginal return analysis.
- Portfolio concentration limits.

Do not implement complex financial optimization algorithms without sufficient reliable data.

Do not treat predicted return as guaranteed return.

16.4 Capital allocation rules

- Protected reserves cannot be allocated automatically.
- Existing business obligations take priority according to owner-approved policy.
- No business may exceed its approved budget.
- No agent may increase its own allocation.
- No capital may be allocated to a prohibited business activity.
- No new allocation may bypass required owner approval.
- Capital allocation decisions must be auditable.

The engine may recommend allocations independently, but actual financial movement is outside this phase.

---

17. RESOURCE AND AGENT ALLOCATION

Integrate with P-04 Dynamic Agent Factory.

A growing business may need more operational capacity.

However, creating more agents does not automatically create more productivity.

17.1 Resource requirements

Evaluate:

- Current workload.
- Task backlog.
- Task completion rate.
- Agent utilization.
- Failure rate.
- Required skills.
- Processing capacity.
- Hardware availability.
- AI inference demand.
- Operational costs.
- Business priorities.

17.2 Agent scaling decisions

The engine may recommend:

- Reassigning existing agents.
- Changing task priorities.
- Improving workflows.
- Creating a specialized agent.
- Increasing task concurrency within limits.
- Reducing unnecessary agents.
- Pausing idle workloads.

New agent creation must use P-04.

Task execution must use P-05.

Do not create independent agent spawning or execution infrastructure.

17.3 Resource limits

Respect:

- Maximum concurrent tasks.
- CPU limits.
- Memory limits.
- Model availability.
- Queue limits.
- Cost limits.
- Agent permissions.
- Business priority.

Never overload the machine simply because several businesses request resources simultaneously.

Implement fair scheduling and priority rules.

---

18. SURVIVAL AND GROWTH FORECASTING

Create a forecasting layer for business sustainability.

18.1 Survival forecasts

Estimate:

- Expected cash requirements.
- Operating burn.
- Revenue stability.
- Expense trends.
- Upcoming obligations.
- Expected liquidity.
- Potential financial stress.
- Break-even timing.

Use P-07 for financial calculations and historical financial records.

18.2 Growth forecasts

Estimate:

- Customer acquisition.
- Conversion.
- Revenue growth.
- Operating cost growth.
- Delivery capacity.
- Staffing or agent requirements.
- Infrastructure requirements.
- Capital requirements.

18.3 Scenario analysis

Provide:

Conservative scenario

- Demand falls.
- Conversion decreases.
- Costs rise.
- Churn increases.
- Acquisition becomes more expensive.

Base scenario

- Performance follows the most defensible available assumptions.

Optimistic scenario

- Demand improves.
- Retention increases.
- Acquisition becomes more efficient.
- Operations scale successfully.

Each scenario must identify:

- Assumptions.
- Forecast period.
- Evidence.
- Expected financial impact.
- Operational requirements.
- Downside risk.
- Confidence.

Do not present forecasts as facts.

18.4 Forecast versus actual

Compare previous forecasts with actual outcomes.

Track:

- Revenue forecast accuracy.
- Expense forecast accuracy.
- Growth forecast accuracy.
- Customer forecast accuracy.
- Cash requirement accuracy.
- Scaling outcome accuracy.

Preserve previous forecasts so the system cannot rewrite its historical predictions to improve its reported accuracy.

---

19. GROWTH AND SURVIVAL INTELLIGENCE AGENT

Integrate the P-08 decision engine with P-02 Master Intelligence.

The AI component should act as a business strategy analyst.

It must interpret structured evidence and explain recommended decisions.

Example questions:

- Which business is most financially stable?
- Which business requires immediate attention?
- Which business should receive more resources?
- Which business should reduce costs?
- Is this business ready to scale?
- Should the system run another experiment?
- Which acquisition channel is performing best?
- Is the current business model sustainable?
- Should this business enter a new market?
- What is the maximum safe experiment budget?
- Which business should be paused?
- What is the biggest portfolio risk?
- Which business is consuming resources without sufficient results?

19.1 AI decision boundaries

The LLM may:

- Explain business performance.
- Compare strategic alternatives.
- Summarize risk.
- Generate recovery plans.
- Propose experiments.
- Interpret forecasts.
- Recommend scaling strategies.
- Explain why a business should continue or pause.

The LLM must not:

- Invent performance data.
- Change financial records.
- Modify approved budgets.
- Approve its own actions.
- Override risk gates.
- Change owner permissions.
- Permanently close businesses.
- Execute financial transfers.
- Rewrite historical decision outcomes.

Use deterministic services for calculations and rule enforcement.

The LLM is an analyst, not the authority controlling the business.

19.2 Explainable recommendations

Every recommendation must cite the underlying data records, metrics, evidence, and calculation timestamps wherever possible.

Label:

- Verified facts.
- Calculated metrics.
- Forecasts.
- Assumptions.
- Uncertain findings.
- Recommendations.

If the data is insufficient, the system must say so.

---

20. DECISION EXECUTION AND CONTROLLED AUTONOMY

P-08 must connect decisions to the existing P-04 and P-05 execution infrastructure.

It must not build a separate execution engine.

20.1 Decision-to-action workflow

Implement:

1. Detect a business condition.
2. Collect relevant evidence.
3. Calculate business health.
4. Identify possible interventions.
5. Evaluate financial and operational risks.
6. Generate a recommendation.
7. Check permissions.
8. Determine approval requirements.
9. Request approval where required.
10. Create an authorized execution plan.
11. Execute through P-05.
12. Monitor results.
13. Record outcomes.
14. Update business health.
15. Learn from the result.

20.2 Autonomy levels

Level 0: Observation

- Collect data.
- Calculate metrics.
- Generate reports.
- Identify risks.

Level 1: Recommendation

- Propose actions.
- Generate plans.
- Suggest experiments.
- Compare alternatives.

Level 2: Pre-authorized execution

- Execute reversible, low-risk actions already covered by an explicit owner-approved policy.
- Operate within predefined budgets and permissions.

Level 3: Approval-required execution

- Material spending changes.
- New recurring commitments.
- Major product changes.
- Market expansion.
- Significant infrastructure changes.

Level 4: Restricted owner-only decisions

- Permanent business closure.
- Major capital decisions outside approved policy.
- Changes to protected reserves.
- Legal ownership changes.
- Changes to security and governance rules.
- Irreversible financial actions.

The autonomy level must be configurable, permission-aware, and auditable.

---

21. BUSINESS LEARNING AND STRATEGY MEMORY

Integrate P-08 with the existing P-02 and memory architecture.

Every important business decision should become a learning record.

Store:

- Original problem.
- Business condition.
- Evidence used.
- Decision.
- Alternatives considered.
- Expected outcome.
- Actual outcome.
- Cost.
- Risk.
- Decision quality.
- Lessons learned.
- Future implications.

21.1 Learning from failures

When an experiment or business fails, identify:

- Incorrect assumptions.
- Weak market validation.
- Poor customer targeting.
- Pricing problems.
- Operational bottlenecks.
- Acquisition problems.
- Excessive costs.
- Platform risks.
- Poor execution.
- External market changes.

Do not assume that every failed business was caused by poor execution.

Distinguish between:

- Bad opportunity selection.
- Bad business model.
- Bad implementation.
- Bad distribution.
- External conditions.
- Insufficient evidence.
- Incorrect timing.

21.2 Reusable strategic knowledge

Build a structured strategy library containing:

- Successful growth patterns.
- Failed experiment patterns.
- Customer acquisition lessons.
- Pricing lessons.
- Market expansion lessons.
- Operational optimization lessons.
- Business closure lessons.

Do not generalize a single business outcome into a universal rule.

Record context and confidence.

21.3 Decision performance

Measure:

- Recommendation accuracy.
- Forecast accuracy.
- Decision outcome.
- Cost of incorrect decisions.
- Avoided losses.
- Successful interventions.
- Scaling success rate.
- Recovery success rate.

Avoid rewarding agents for activity volume.

Reward measured business outcomes and reliable execution.

---

22. DATABASE AND DATA MODEL DESIGN

Design the database using existing AUTONOMUS conventions.

Suggested logical entities:

- business_health_snapshots
- business_health_dimensions
- business_monitoring_events
- business_decisions
- business_decision_evidence
- business_decision_alternatives
- business_decision_approvals
- business_lifecycle_history
- business_interventions
- recovery_plans
- scaling_assessments
- scaling_plans
- growth_opportunities
- growth_experiments
- experiment_hypotheses
- experiment_results
- experiment_evidence
- experiment_budgets
- portfolio_snapshots
- portfolio_risk_assessments
- capital_allocation_proposals
- resource_allocation_plans
- survival_forecasts
- growth_forecasts
- decision_outcomes
- strategy_learning_records
- business_closure_reviews

These are logical entities, not a requirement to create duplicate or unnecessary tables.

Use:

- Foreign keys.
- Database constraints.
- Indexes.
- Transaction-safe operations.
- Migration support.
- Timestamp consistency.
- Business-level access controls.
- Historical records.

All material decisions and lifecycle changes must be traceable.

---

23. BACKEND API DESIGN

Create API endpoints following existing project conventions.

Suggested route groups:

Business health

- GET /api/survival/businesses/{business_id}/health
- GET /api/survival/businesses/{business_id}/health/history
- GET /api/survival/businesses/{business_id}/risks

Business decisions

- GET /api/survival/decisions
- GET /api/survival/decisions/{decision_id}
- POST /api/survival/decisions/{decision_id}/review
- POST /api/survival/decisions/{decision_id}/approval

Lifecycle

- GET /api/survival/businesses/{business_id}/lifecycle
- GET /api/survival/businesses/{business_id}/lifecycle/history
- POST /api/survival/businesses/{business_id}/lifecycle/transition

Experiments

- GET /api/survival/experiments
- POST /api/survival/experiments
- GET /api/survival/experiments/{experiment_id}
- POST /api/survival/experiments/{experiment_id}/start
- POST /api/survival/experiments/{experiment_id}/evaluate
- POST /api/survival/experiments/{experiment_id}/stop

Scaling

- GET /api/survival/businesses/{business_id}/scaling-readiness
- POST /api/survival/businesses/{business_id}/scaling-assessment
- POST /api/survival/businesses/{business_id}/scaling-plan

Recovery

- GET /api/survival/businesses/{business_id}/recovery
- POST /api/survival/businesses/{business_id}/recovery-plan

Portfolio

- GET /api/survival/portfolio/overview
- GET /api/survival/portfolio/health
- GET /api/survival/portfolio/risks
- GET /api/survival/portfolio/allocation-proposals

Forecasting

- GET /api/survival/businesses/{business_id}/forecasts
- POST /api/survival/businesses/{business_id}/forecasts

Reporting

- GET /api/survival/reports/business-health
- GET /api/survival/reports/growth
- GET /api/survival/reports/portfolio-performance
- GET /api/survival/reports/decision-outcomes

These routes are proposed examples. Adapt them to the existing authentication, routing, and API conventions.

Every write endpoint must enforce authorization, validation, audit logging, and idempotency where appropriate.

---

24. SURVIVAL AND SCALING COMMAND CENTER INTERFACE

Integrate P-08 into the existing AUTONOMUS frontend.

Do not build the complete P-11 Command Center prematurely.

Create functional business management and decision views that can later be integrated into P-11.

24.1 Portfolio overview

Display:

- Total businesses.
- Active businesses.
- Growing businesses.
- Stable businesses.
- At-risk businesses.
- Businesses requiring review.
- Paused businesses.
- Closed businesses.
- Portfolio health.
- Major portfolio risks.
- Capital allocation summary.

24.2 Business health dashboard

Each business should display:

- Health status.
- Financial health.
- Commercial health.
- Market health.
- Operational health.
- Product health.
- Strategic health.
- Governance status.
- Current lifecycle stage.
- Recent performance changes.
- Outstanding risks.

24.3 Decision center

Display:

- New recommendations.
- Pending decisions.
- Approval-required actions.
- Active interventions.
- Blocked actions.
- Decision history.
- Decision outcomes.

Each recommendation must show its evidence and expected impact.

24.4 Experiment center

Display:

- Active experiments.
- Approved budgets.
- Spending consumed.
- Remaining budget.
- Time remaining.
- Hypothesis.
- Performance against targets.
- Stop conditions.
- Experiment outcome.

24.5 Scaling center

Display:

- Scaling readiness.
- Readiness blockers.
- Proposed growth actions.
- Expected costs.
- Downside scenarios.
- Required resources.
- Approval requirements.

24.6 Recovery center

Display:

- At-risk businesses.
- Root causes.
- Recovery plans.
- Recovery budgets.
- Progress.
- Expected recovery date.
- Recovery outcome.

24.7 Business lifecycle view

Provide a visual lifecycle history and current status.

The owner must be able to understand why a business entered a particular state and what evidence supports its current classification.

---

25. SECURITY, GOVERNANCE AND RISK CONTROLS

P-08 has the ability to influence business operations and resource allocation.

Security and governance must therefore be enforced at the service and execution layers.

Implement:

- Role-based access.
- Business-level permissions.
- Decision authorization.
- Approval workflows.
- Audit logs.
- Budget checks.
- Action idempotency.
- Execution boundaries.
- Emergency stop integration.
- Secure agent communication.
- Prompt injection defenses.
- Input validation.
- Data provenance.
- Backup and recovery.

25.1 Non-overridable controls

The following rules must remain outside the authority of the LLM:

- Financial spending limits.
- Protected reserves.
- Owner permissions.
- Security rules.
- Legal and compliance restrictions.
- Maximum experiment losses.
- Permanent closure authorization.
- Emergency shutdown.

The AI may recommend changes to a policy, but only the owner can authorize a permitted change through the appropriate secure process.

25.2 Emergency intervention

Support an emergency business-level pause.

Possible triggers:

- Critical security incident.
- Unauthorized spending attempt.
- Serious legal or compliance concern.
- Production system compromise.
- Critical financial discrepancy.
- Unexpected uncontrolled agent behavior.

Emergency pause must:

- Prevent new controlled execution actions.
- Preserve financial records.
- Preserve customer obligations.
- Preserve logs.
- Notify the owner.
- Allow safe inspection and recovery.

It must not blindly terminate critical services that are necessary to protect customer data or complete already-authorized obligations.

---

26. TESTING AND VALIDATION

P-08 must be tested against realistic business scenarios.

26.1 Unit tests

Test:

- Business health calculation.
- Evidence confidence.
- Risk classification.
- Decision scoring.
- Lifecycle transitions.
- Scaling readiness.
- Experiment evaluation.
- Stop-loss logic.
- Recovery classification.
- Capital allocation calculations.
- Resource allocation limits.
- Forecast comparisons.

26.2 Integration tests

Test:

- P-07 financial data integration.
- P-06 business lifecycle integration.
- P-03 opportunity evidence integration.
- P-04 agent allocation integration.
- P-05 execution integration.
- P-02 intelligence integration.
- Approval workflows.
- Decision history.
- Strategy memory.

26.3 Security tests

Test:

- Unauthorized business closure.
- Unauthorized scaling.
- Budget bypass attempts.
- Protected reserve modification.
- Agent self-approval.
- Cross-business data access.
- Prompt injection through imported market data.
- Unauthorized lifecycle transitions.
- Execution without approval.
- Repeated decision execution.
- Emergency pause behavior.

26.4 Critical acceptance scenarios

Scenario 1: Revenue growth without profitability

A business increases collected revenue from ₹10,000 to ₹30,000, but its expenses increase from ₹8,000 to ₹35,000.

Expected result:

- The system identifies that revenue increased while profitability deteriorated.
- It does not automatically recommend scaling.
- It investigates cost structure and contribution economics.

Scenario 2: Unvalidated business

A business has a polished website, high traffic, and many social media followers but no verified paying customers.

Expected result:

- The business is not classified as validated or scaling-ready.
- The system recommends demand validation.

Scenario 3: Successful experiment

An approved experiment generates verified customer demand within its budget and achieves its defined success criteria.

Expected result:

- The experiment is classified according to its evidence.
- The system evaluates the next controlled step.
- It does not automatically authorize unlimited spending.

Scenario 4: Failed experiment

An experiment consumes its maximum approved loss without achieving its success criteria.

Expected result:

- Further spending is blocked.
- The experiment is marked STOPPED or FAILED.
- The system preserves its findings.
- A future experiment requires a new justification and authorization.

Scenario 5: Scaling readiness

A business has repeat customers, verified collected revenue, stable delivery, defensible contribution margin, and sufficient approved capital.

Expected result:

- The system generates a scaling readiness report.
- It proposes an incremental scaling plan.
- Required approvals are enforced.

Scenario 6: Cash-flow crisis

A profitable business has insufficient available cash to meet upcoming obligations.

Expected result:

- The system detects the liquidity problem.
- It does not rely solely on accounting profit.
- It proposes cash preservation and risk reduction.

Scenario 7: Excessive platform dependency

Several businesses rely on one external platform for most of their revenue.

Expected result:

- The portfolio risk engine identifies concentration.
- It recommends appropriate diversification.
- It does not assume that separate businesses automatically mean diversified risk.

Scenario 8: Recovery decision

A business experiences a temporary decline caused by an operational problem that can be repaired within a controlled budget.

Expected result:

- The system generates a recovery plan.
- It defines a finite budget and review period.
- It monitors recovery against measurable criteria.

Scenario 9: Structurally unviable business

A business repeatedly fails to acquire customers, has weak demand evidence, and cannot demonstrate a defensible recovery path.

Expected result:

- The system recommends closure review.
- It identifies outstanding obligations.
- It does not permanently close the business without owner approval.

Scenario 10: Multiple competing businesses

Three businesses request additional resources, but available capital and hardware capacity are limited.

Expected result:

- The system compares risk-adjusted priorities.
- It considers existing commitments.
- It avoids over-allocation.
- It generates an explainable resource allocation proposal.

Scenario 11: Agent multiplication

A business requests ten additional agents because its workload has increased.

Expected result:

- The system measures actual workload and resource constraints.
- It checks whether existing agents can be reassigned or workflows optimized.
- It does not create unnecessary agents.

Scenario 12: Protected reserve violation

A scaling proposal requires spending protected emergency capital.

Expected result:

- The allocation is blocked.
- The owner must explicitly authorize any permitted policy change.
- The LLM cannot bypass the restriction.

Scenario 13: Conflicting evidence

A business dashboard shows growth, but payment reconciliation reveals missing or disputed transactions.

Expected result:

- The system reduces confidence in the growth assessment.
- It blocks material scaling recommendations until the discrepancy is resolved.

Scenario 14: Incorrect forecast

A previous forecast predicted 30% growth, but actual results show a decline.

Expected result:

- Forecast error is recorded.
- The original forecast remains unchanged.
- Future decisions account for the demonstrated uncertainty.

Scenario 15: Emergency pause

A critical security incident occurs in a business.

Expected result:

- New controlled business execution is paused.
- Relevant records and logs are preserved.
- The owner is notified.
- Recovery requires appropriate authorization.

---

27. PERFORMANCE AND RESOURCE OPTIMIZATION

AUTONOMUS must run on modest Windows hardware.

Requirements:

- Use deterministic Python logic for calculations.
- Avoid unnecessary LLM calls.
- Use event-driven monitoring where practical.
- Use bounded background jobs.
- Avoid launching heavyweight models per agent.
- Use shared model infrastructure.
- Cache suitable health summaries.
- Use incremental updates.
- Prevent duplicate scheduled tasks.
- Paginate historical records.
- Avoid unnecessary frontend polling.
- Use efficient database indexes.
- Prioritize critical business tasks.
- Respect CPU, memory, and inference limits.

The system must remain useful even when the local LLM is unavailable.

Business health calculations, budget checks, lifecycle rules, and emergency restrictions must work without an LLM.

---

28. DOCUMENTATION REQUIREMENTS

Create or update documentation covering:

1. P-08 architecture.
2. Business lifecycle model.
3. Business health methodology.
4. Evidence confidence methodology.
5. Decision engine.
6. Experiment management.
7. Stop-loss controls.
8. Scaling readiness rules.
9. Growth strategy evaluation.
10. Recovery methodology.
11. Pause and closure workflow.
12. Portfolio management.
13. Capital allocation.
14. Agent and resource allocation.
15. Forecasting methodology.
16. Decision approval model.
17. AI decision boundaries.
18. Security and emergency pause.
19. API documentation.
20. Database schema.
21. Monitoring schedules.
22. Test instructions.
23. Known limitations.
24. P-09 integration requirements.

All important scoring formulas and decision rules must be documented.

A developer must be able to understand why a business received a particular recommendation without asking an LLM to explain its own decision.

---

29. IMPLEMENTATION SEQUENCE

Implement P-08 in controlled stages.

Stage 1: Repository and dependency audit

- Inspect P-01 through P-07.
- Verify existing interfaces.
- Identify missing dependencies.
- Map the business lifecycle.
- Map financial and operational data sources.
- Produce an implementation plan.

Stage 2: Business monitoring

- Implement financial monitoring using P-07.
- Implement commercial monitoring.
- Implement operational monitoring.
- Implement strategic evidence ingestion.
- Implement monitoring event records.

Stage 3: Business health engine

- Implement health dimensions.
- Implement evidence confidence.
- Implement configurable scoring.
- Implement hard risk gates.
- Implement health history.

Stage 4: Decision engine

- Implement decision types.
- Implement decision evidence.
- Implement alternative comparison.
- Implement approval requirements.
- Implement decision history.

Stage 5: Experiment management

- Implement experiment lifecycle.
- Implement hypotheses.
- Implement budgets.
- Implement stop-loss.
- Implement evaluation and learning records.

Stage 6: Scaling and growth

- Implement scaling readiness.
- Implement growth strategy evaluation.
- Implement incremental scaling plans.
- Implement cost optimization.
- Implement market and product expansion proposals.

Stage 7: Recovery and closure

- Implement at-risk detection.
- Implement recovery planning.
- Implement business pause.
- Implement closure review.
- Implement safe wind-down procedures.

Stage 8: Portfolio and capital allocation

- Implement portfolio health.
- Implement concentration analysis.
- Implement allocation proposals.
- Implement resource allocation.
- Integrate with P-04 and P-05.

Stage 9: Forecasting and learning

- Implement survival forecasts.
- Implement growth scenarios.
- Implement forecast-versus-actual.
- Implement decision outcome tracking.
- Integrate with P-02 memory.

Stage 10: Frontend integration

- Implement portfolio overview.
- Implement business health views.
- Implement decision center.
- Implement experiments.
- Implement scaling and recovery views.
- Implement lifecycle history.

Stage 11: Integration and independent audit

- Run all unit tests.
- Run integration tests.
- Run security tests.
- Validate financial and authorization boundaries.
- Validate resource limits.
- Verify existing features.
- Fix critical defects.
- Produce the final report.

Do not skip stages merely to produce a visually complete dashboard.

---

30. ACCEPTANCE CRITERIA

P-08 is complete only when the following conditions are satisfied.

Business monitoring

- [ ] Financial metrics come from P-07.
- [ ] Commercial metrics have clear definitions.
- [ ] Operational monitoring works.
- [ ] Strategic evidence includes provenance.
- [ ] Monitoring frequency is configurable.
- [ ] Missing data is identified.

Business health

- [ ] All required health dimensions are supported.
- [ ] Health classifications are explainable.
- [ ] Evidence confidence is recorded.
- [ ] Hard risk gates override numerical scores.
- [ ] Health history is preserved.

Decision intelligence

- [ ] Decisions include evidence and alternatives.
- [ ] Expected cost and downside are evaluated.
- [ ] Approval requirements are enforced.
- [ ] Historical decisions remain traceable.
- [ ] Recommendations do not invent data.

Experiments

- [ ] Experiments have explicit hypotheses.
- [ ] Experiments have approved budgets.
- [ ] Stop-loss rules are enforced.
- [ ] Outcomes are evaluated.
- [ ] Failed experiments remain available for learning.

Scaling

- [ ] Scaling readiness is measurable.
- [ ] Financial and operational requirements are evaluated.
- [ ] Growth proposals include risk analysis.
- [ ] Incremental scaling is supported.
- [ ] Scaling cannot bypass approval requirements.

Survival

- [ ] At-risk businesses are identified.
- [ ] Recovery plans have finite budgets and timelines.
- [ ] Pause procedures preserve records and obligations.
- [ ] Permanent closure requires owner approval.
- [ ] Closure procedures account for customers and liabilities.

Portfolio management

- [ ] Multiple businesses can be evaluated together.
- [ ] Concentration risk is identified.
- [ ] Capital allocation proposals are explainable.
- [ ] Protected reserves are respected.
- [ ] Agent resource allocation respects hardware limits.

Engineering quality

- [ ] Database migrations are tested.
- [ ] API permissions are tested.
- [ ] Unit tests pass.
- [ ] Integration tests pass.
- [ ] Security tests pass.
- [ ] Existing P-01 through P-07 functionality remains operational.
- [ ] Documentation is updated.
- [ ] No unimplemented feature is falsely marked complete.

Any critical failure in financial protection, authorization, lifecycle integrity, or emergency controls blocks completion.

---

31. FINAL AUDIT AND DELIVERY REPORT

At the end of P-08, produce a comprehensive report containing:

1. Initial repository condition.
2. P-01 through P-07 integration audit.
3. Existing capabilities reused.
4. Missing capabilities identified.
5. Architecture changes.
6. Files created.
7. Files modified.
8. Database migrations.
9. Monitoring capabilities.
10. Business health methodology.
11. Decision engine implementation.
12. Experiment management implementation.
13. Stop-loss implementation.
14. Scaling readiness implementation.
15. Growth strategy capabilities.
16. Recovery and closure workflows.
17. Portfolio management.
18. Capital allocation controls.
19. Resource allocation controls.
20. AI integration.
21. Security and governance controls.
22. API endpoints.
23. Frontend functionality.
24. Tests executed.
25. Test results.
26. Performance observations.
27. Known limitations.
28. Unresolved risks.
29. Manual configuration requirements.
30. P-09 integration readiness.

Use explicit implementation statuses:

- COMPLETED AND TESTED.
- IMPLEMENTED BUT NOT FULLY TESTED.
- PARTIALLY IMPLEMENTED.
- BLOCKED.
- NOT IMPLEMENTED.
- REQUIRES OWNER CONFIGURATION.

Do not mark a feature complete simply because its database table, API endpoint, or UI component exists.

---

32. STRICT DEVELOPMENT RULES

1. Inspect before implementing.
2. Preserve all working previous phases.
3. Use P-07 as the authoritative financial source.
4. Use P-03 for market and opportunity research.
5. Use P-04 for agent management.
6. Use P-05 for digital execution.
7. Use P-06 for business creation and identity.
8. Use P-02 for intelligence and memory integration.
9. Never invent business performance data.
10. Never scale an unvalidated business.
11. Never spend outside authorized budgets.
12. Never use protected reserves without owner authorization.
13. Never allow an LLM to override governance controls.
14. Never permanently close a business without owner approval.
15. Never allow failed experiments to continue beyond approved stop-loss conditions.
16. Never create unnecessary agents to simulate productivity.
17. Never confuse revenue growth with profit growth.
18. Never conceal business failures.
19. Never rewrite historical forecasts or decisions.
20. Never claim a business is sustainable without sufficient evidence.
21. Test critical lifecycle and financial boundaries.
22. Document all material architecture changes.
23. Do not automatically start the next phase.

If a requirement conflicts with an existing architecture, explain the conflict and propose the smallest safe change.

If evidence is insufficient for a business decision, classify the result as INSUFFICIENT_DATA rather than inventing certainty.

---

33. FINAL EXECUTION BOUNDARY

Your responsibility is to complete P-08: Survival and Scaling Engine only.

After implementation:

- Integrate P-08 with P-01 through P-07.
- Verify all business lifecycle transitions.
- Verify financial and operational decision boundaries.
- Verify experiment stop-loss controls.
- Verify scaling readiness.
- Verify recovery and closure approval requirements.
- Verify portfolio and capital allocation logic.
- Run the complete test suite.
- Conduct an independent audit.
- Produce the final completion report.
- Clearly identify incomplete capabilities and remaining risks.

STOP AFTER P-08.

Do not automatically begin P-09: Memory and Continuous Learning.

Wait for explicit approval from the human owner.

The final objective is to make AUTONOMUS capable of protecting, improving, and responsibly scaling its businesses through evidence-based decisions.

A successful system must know when to grow, when to improve, when to wait, when to stop spending, and when to walk away.

END OF P-08 MASTER IMPLEMENTATION PROMPT