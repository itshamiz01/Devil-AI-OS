AUTONOMUS P-11: PREMIUM COMMAND CENTER

Master Development Prompt | Version 1.0

---

1. ROLE AND MISSION

Act as a principal product architect, senior UI/UX designer, frontend architect, backend integration engineer, dashboard specialist, data visualization engineer, and enterprise software designer.

Your mission is to design, implement, test, and integrate the AUTONOMUS Premium Command Center (P-11) into the existing AUTONOMUS AI Operating System.

AUTONOMUS is a Windows-first, hybrid-AI autonomous business operating system.

It coordinates multiple intelligent agents and specialized engines to:

- Discover business opportunities.
- Research and validate markets.
- Create digital businesses.
- Build products and services.
- Execute digital operations.
- Manage financial performance.
- Monitor business survival.
- Learn from outcomes.
- Coordinate multiple businesses.
- Operate within strict security and governance boundaries.

P-11 must provide one unified interface through which the owner can understand and control the entire system.

The Command Center must feel like a professional operating environment, not a generic SaaS admin template.

Primary mission

Build a premium, intelligent, real-time operational interface that answers these questions:

1. What is AUTONOMUS doing right now?
2. Which agents are working?
3. What are they working on?
4. Why are they performing those tasks?
5. What has been completed?
6. What has failed?
7. Which businesses are operating?
8. Which businesses are profitable?
9. How much money has actually been collected?
10. What is the actual financial position?
11. Which decisions require my approval?
12. Are there security risks?
13. Is the system healthy?
14. What should I focus on next?
15. Can I safely pause, stop, or redirect operations?

The Command Center must make this information understandable without requiring the owner to inspect logs, databases, or individual agent interfaces.

---

2. NON-NEGOTIABLE DEVELOPMENT RULES

Before implementation:

1. Inspect the complete existing AUTONOMUS repository.
2. Audit the actual implementation of P-01 through P-10.
3. Preserve existing working backend functionality.
4. Do not rebuild AUTONOMUS from scratch.
5. Do not replace the existing frontend without a documented technical reason.
6. Do not create duplicate business, financial, agent, memory, or security systems.
7. Reuse existing APIs and data models wherever possible.
8. Maintain the existing authentication and authorization architecture.
9. Every sensitive action must continue to use P-10 authorization and approval mechanisms.
10. Do not fabricate operational data or display fake metrics as real.
11. Do not create buttons that appear functional but have no actual action.
12. Do not use hardcoded dashboard values as substitutes for backend integration.
13. Do not introduce mandatory paid APIs or services.
14. Preserve local-first functionality.
15. Design for Windows desktop first, while maintaining responsive layouts.
16. Keep components modular and maintainable.
17. Test all critical interactions.
18. Document all modifications.

The frontend must never become an alternative authority for permissions or security.

All authorization decisions remain enforced by the backend.

---

3. PRE-IMPLEMENTATION AUDIT

Before writing code, inspect P-01 through P-10.

3.1 Inspect existing frontend

Identify:

- Current frontend framework.
- Existing routing.
- Component architecture.
- Styling system.
- State management.
- API client.
- Authentication flow.
- Existing dashboard components.
- Existing navigation.
- Existing responsive behavior.
- Existing charts and visualization libraries.
- Existing error handling.
- Existing loading states.

Determine whether the existing frontend should be extended or reorganized.

Do not discard a working frontend merely because a new design is desired.

3.2 Inspect backend capabilities

Inspect the actual APIs and data models for:

- System status.
- Master Intelligence Engine.
- Opportunity Discovery.
- Agent Factory.
- Digital Execution Engine.
- Business Creation.
- Financial Intelligence.
- Survival and Scaling.
- Memory and Learning.
- Security and Governance.
- Scheduled operations.
- Task queues.
- Approval requests.
- Audit events.

Create a frontend-to-backend integration map.

3.3 Identify missing APIs

For every proposed dashboard feature, identify whether the required backend endpoint already exists.

Classify each feature as:

- Fully supported.
- Partially supported.
- Backend integration required.
- Backend capability missing.
- Blocked by dependency.

Do not simulate missing functionality as if it were live.

If backend work is necessary, implement the smallest required API extension and document it.

3.4 Produce an implementation plan

Before modifying the application, deliver:

- Existing frontend architecture.
- Existing backend integration map.
- Component reuse strategy.
- Proposed navigation structure.
- Design system proposal.
- Data requirements.
- API requirements.
- Implementation stages.
- Risks and dependencies.

Only proceed after the audit is documented.

---

4. PRODUCT DESIGN PHILOSOPHY

The Command Center should combine the visual clarity of a professional financial terminal, the control structure of an operating system, and the accessibility of a modern desktop application.

Avoid generic dashboard design.

4.1 Visual identity

Create a premium visual language using:

- Deep charcoal or near-black surfaces.
- Warm white or soft neutral backgrounds where appropriate.
- Restrained gold or olive accents.
- Subtle borders.
- Clear typography.
- Consistent spacing.
- Refined charts.
- Controlled visual hierarchy.
- Purposeful animation.

Suggested design direction:

Premium dark operational interface with warm metallic accents.

Use color to communicate meaning:

- Green: healthy, verified, successful.
- Amber: warning, pending, attention.
- Red: critical, blocked, failed.
- Blue: informational or active processing.
- Neutral: inactive, historical, or unknown.

Do not use colors merely for decoration.

4.2 Avoid visual clutter

Do not place every available metric on the homepage.

Prioritize:

1. System health.
2. Active operations.
3. Business performance.
4. Financial position.
5. Pending owner decisions.
6. Security status.
7. Important alerts.

Detailed information belongs in dedicated views.

4.3 Information hierarchy

Every screen should make the following clear:

- What is happening?
- What matters?
- What requires attention?
- What can the owner do?

4.4 Typography

Use a readable professional font system.

Create a consistent hierarchy for:

- Page titles.
- Section headings.
- Metric values.
- Supporting labels.
- Metadata.
- Logs.
- Tables.
- Status indicators.

Use tabular numerals for financial and numerical data where appropriate.

4.5 Motion and interaction

Use subtle animation for:

- Agent state transitions.
- Task progress.
- Notifications.
- Chart transitions.
- Panel opening and closing.
- Loading states.

Avoid distracting animations and excessive movement.

Respect reduced-motion preferences.

---

5. GLOBAL APPLICATION LAYOUT

Build a consistent application shell.

The main layout should contain:

1. Left navigation sidebar.
2. Top system status bar.
3. Main content area.
4. Optional contextual side panel.
5. Notification and approval layer.
6. Global command interface.

5.1 Sidebar

Include these primary navigation sections:

- Overview.
- Intelligence.
- Opportunities.
- Agents.
- Execution.
- Businesses.
- Finance.
- Survival & Scaling.
- Memory & Learning.
- Security.
- Approvals.
- Operations.
- Settings.

Organize sections logically.

Allow navigation expansion and collapse.

Display relevant counters, such as pending approvals or critical alerts.

Do not show unnecessary counters when no data exists.

5.2 Top status bar

Display:

- AUTONOMUS identity.
- Current system state.
- Local operating time.
- AI provider/model status.
- Active agent count.
- Active task count.
- Pending approval count.
- Critical alert indicator.
- Owner profile and session controls.

The displayed time must use the configured local timezone.

5.3 Global command interface

Provide a command/search interface that allows the owner to:

- Search businesses.
- Search agents.
- Search tasks.
- Search opportunities.
- Search reports.
- Search memory records.
- Navigate to a module.
- Submit an instruction to the Master Intelligence Engine.

The command interface must distinguish between:

- Navigation queries.
- Information queries.
- Action requests.
- Sensitive operations requiring approval.

Never execute a sensitive action merely because it was entered into a search field.

5.4 Global notification center

Provide notifications for:

- Task completion.
- Task failures.
- Agent failures.
- Business milestones.
- Financial events.
- Approval requests.
- Security alerts.
- Scheduled operations.
- System health problems.

Support:

- Read/unread status.
- Filtering.
- Dismissal.
- Related resource navigation.
- Severity indicators.

Critical security and financial alerts must not be silently dismissed without appropriate handling.

---

6. OVERVIEW DASHBOARD

The Overview screen is the primary landing page.

It must provide an accurate snapshot of the entire AUTONOMUS environment.

6.1 Welcome and operating state

Display:

- Current date.
- System operating status.
- Current operating mode.
- Active business count.
- Active agents.
- Active tasks.
- Pending approvals.

Show whether the system is:

- Operational.
- Operational with warnings.
- Restricted.
- In safe mode.
- Paused.
- Emergency stopped.
- Starting.
- Recovering.
- Offline.

Use actual backend status.

6.2 Key performance indicators

Display cards for:

- Active businesses.
- Validated opportunities.
- Active agents.
- Running tasks.
- Collected revenue.
- Actual expenses.
- Net profit or loss.
- Available cash balance, if supported.

Every metric must include:

- Value.
- Measurement period.
- Data source.
- Last updated timestamp.
- Appropriate explanation.

Do not confuse forecast revenue with collected revenue.

Do not label a projected profit as actual profit.

If a metric is unavailable, display an explicit unavailable state.

6.3 Operational activity

Create a live activity feed showing:

- Agent started task.
- Research completed.
- Opportunity validated.
- Business created.
- Product generated.
- Content published.
- Payment verified.
- Task failed.
- Approval requested.
- Security restriction triggered.

Each event must be linked to its source record.

6.4 System health

Show:

- Backend status.
- Database status.
- AI provider status.
- Local model availability.
- Task queue status.
- Memory system status.
- Browser automation status.
- Security subsystem status.
- Background worker status.

Use actual health checks.

Do not infer that the system is healthy merely because the frontend loaded.

6.5 Attention required

Create a dedicated section showing the highest-priority items:

- Pending approvals.
- Failed critical tasks.
- Business survival warnings.
- Budget threshold warnings.
- Security incidents.
- Unresolved integration errors.

Sort by severity and urgency.

---

7. MASTER INTELLIGENCE INTERFACE

Create a dedicated interface for interacting with the Master Intelligence Engine.

This is the primary conversational control surface for AUTONOMUS.

7.1 Chat interface

Provide:

- Message history.
- Streaming responses where supported.
- Task creation from instructions.
- Context-aware responses.
- Agent handoff visibility.
- Source references.
- Execution summaries.
- Error reporting.

7.2 Message types

Visually distinguish:

- Owner messages.
- Master Intelligence responses.
- Agent messages.
- System notifications.
- Execution results.
- Approval requests.
- Security warnings.

7.3 Action transparency

When the Master Intelligence Engine proposes or executes an action, display:

- Objective.
- Reason.
- Relevant business.
- Selected agents.
- Tools involved.
- Required permissions.
- Approval requirements.
- Current status.
- Expected result.

Do not show an LLM-generated plan as proof that an operation actually occurred.

7.4 Task execution cards

When a chat instruction creates a task, display:

- Task ID.
- Objective.
- Assigned agents.
- Execution stages.
- Current stage.
- Progress.
- Start time.
- Estimated completion only when supported.
- Actual completion.
- Output.
- Errors.
- Approval dependencies.

7.5 Chat controls

Provide:

- Stop generation.
- Cancel task where supported.
- Pause task where supported.
- View execution details.
- Open associated business.
- Review output.
- Approve requested action.

All controls must call real backend functionality.

---

8. AGENT COMMAND CENTER

Create a dedicated control center for all AI agents.

8.1 Agent overview

Display:

- Total agents.
- Active agents.
- Idle agents.
- Paused agents.
- Failed agents.
- Suspended agents.
- Agents awaiting review.

8.2 Agent directory

Each agent card should display:

- Agent name.
- Agent ID.
- Role.
- Purpose.
- Parent agent, if applicable.
- Assigned business.
- Current task.
- Status.
- Model/provider.
- Resource usage, if available.
- Last activity.

8.3 Agent statuses

Support clear states:

- Created.
- Pending approval.
- Idle.
- Running.
- Waiting.
- Paused.
- Failed.
- Restricted.
- Suspended.
- Revoked.
- Archived.

8.4 Agent detail page

Provide:

Identity

- Name.
- Purpose.
- Role.
- Creation date.
- Lifecycle state.

Current assignment

- Business.
- Project.
- Task.
- Objective.
- Assigned supervisor.

Permissions

- Available tools.
- Filesystem scope.
- Network scope.
- Data-access scope.
- Financial permissions.
- Approval restrictions.

Performance

- Tasks completed.
- Tasks failed.
- Average duration.
- Success rate, if meaningfully measurable.
- Resource consumption.
- Recent activity.

Memory

- Accessible memory categories.
- Relevant learning records.
- Shared memory permissions.

History

- Task history.
- Permission changes.
- Errors.
- Suspension events.
- Approval requests.

8.5 Agent controls

Where supported, allow the owner to:

- Pause an agent.
- Resume an agent.
- Suspend an agent.
- Revoke permissions.
- Assign a task.
- Review output.
- Inspect logs.
- Archive an agent.

Permission changes and other sensitive operations must use P-10.

8.6 Agent relationship visualization

Create an interactive hierarchy showing:

- Master Intelligence.
- Supervisory agents.
- Specialized agents.
- Sub-agents.
- Task relationships.

Do not invent agent relationships.

Use actual parent/child and assignment data.

---

9. OPPORTUNITY INTELLIGENCE DASHBOARD

Integrate P-03 Opportunity Discovery.

9.1 Opportunity overview

Display:

- Total discovered opportunities.
- Researching opportunities.
- Validated opportunities.
- Rejected opportunities.
- Opportunities awaiting owner review.
- Active experiments.

9.2 Opportunity cards

Each card should include:

- Opportunity name.
- Category.
- Target customer.
- Problem addressed.
- Business model.
- Evidence quality.
- Opportunity score.
- Estimated startup cost.
- Estimated revenue potential.
- Risk level.
- Validation status.
- Last researched date.

Clearly distinguish estimates from verified facts.

9.3 Opportunity detail

Provide tabs for:

- Overview.
- Market research.
- Customer analysis.
- Competitor analysis.
- Evidence.
- Business model.
- Financial feasibility.
- Risks.
- Validation history.
- Decisions.

9.4 Opportunity comparison

Allow the owner to compare multiple opportunities using:

- Evidence quality.
- Market demand.
- Competition.
- Startup cost.
- Revenue model.
- Profit potential.
- Distribution feasibility.
- Operational complexity.
- Risk.
- Strategic fit.

Do not automatically rank an opportunity above another solely because of its numerical score.

Hard rejection rules from P-03 must remain authoritative.

9.5 Actions

Where supported:

- Request additional research.
- Create a validation experiment.
- Reject an opportunity.
- Save for later.
- Approve progression to business creation.

Business creation must continue to follow P-06 eligibility rules.

---

10. BUSINESS PORTFOLIO COMMAND CENTER

Integrate P-06 Business Creation and P-08 Survival and Scaling where implemented.

This section must provide visibility into every business operated by AUTONOMUS.

10.1 Portfolio overview

Display:

- Total businesses.
- Active businesses.
- Businesses in development.
- Businesses in validation.
- Paused businesses.
- At-risk businesses.
- Closed businesses.

10.2 Business cards

Each business should show:

- Business name.
- Business ID.
- Category.
- Lifecycle stage.
- Launch date.
- Operating status.
- Revenue.
- Expenses.
- Actual profit/loss.
- Available cash, where supported.
- Risk level.
- Current objective.
- Latest important event.

Only show actual financial values when supported by verified financial records.

10.3 Business lifecycle

Display lifecycle states such as:

- Proposed.
- Researching.
- Validating.
- Approved.
- In development.
- Ready for launch.
- Operational.
- Paused.
- At risk.
- Blocked.
- Failed.
- Archived.

Use the actual state machine implemented by the backend.

10.4 Business detail page

Create tabs for:

1. Overview.
2. Strategy.
3. Product or service.
4. Operations.
5. Agents.
6. Tasks.
7. Customers.
8. Distribution.
9. Marketing.
10. Finance.
11. Risks.
12. Documents.
13. Memory.
14. History.

Do not create unsupported data fields simply to fill these tabs.

10.5 Business performance

Show:

- Revenue trends.
- Expense trends.
- Profit/loss.
- Customer acquisition.
- Customer retention, where tracked.
- Conversion metrics, where tracked.
- Operational costs.
- Cash runway, if reliably calculable.
- Performance against business targets.

Clearly label each metric's period and definition.

10.6 Business controls

Allow the owner to:

- Pause a business.
- Resume a business.
- Change approved objectives.
- Review business plans.
- Inspect assigned agents.
- Review spending requests.
- Approve operational changes.
- Request a performance review.
- Initiate a controlled shutdown.

All critical actions must pass through backend policies.

---

11. FINANCIAL COMMAND CENTER

Integrate P-07 Financial Intelligence.

This section must prioritize financial truth over attractive but misleading charts.

11.1 Financial overview

Display:

- Verified collected revenue.
- Confirmed expenses.
- Gross profit, where applicable.
- Net profit/loss.
- Cash balance.
- Outstanding receivables.
- Liabilities.
- Refunds.
- Business-level financial position.

Use the authoritative financial records.

Do not invent balances.

11.2 Financial classification

Separate:

- Forecast revenue.
- Booked or invoiced revenue.
- Collected revenue.
- Refunded revenue.
- Gross profit.
- Operating expenses.
- Net profit.
- Available cash.
- Reserved funds.
- Outstanding liabilities.

Never combine these into a single vague "earnings" metric.

11.3 Financial charts

Provide:

- Revenue over time.
- Expense over time.
- Profit/loss over time.
- Business-level comparison.
- Budget utilization.
- Cash flow.
- Spending categories.

Every chart must identify:

- Currency.
- Time period.
- Data source.
- Actual versus forecast status.

11.4 Business financial comparison

Allow comparison of businesses by:

- Collected revenue.
- Operating expenses.
- Net profit.
- Profit margin.
- Cash consumption.
- Budget utilization.
- Return on investment where properly supported.

Do not compare incompatible periods or accounting definitions.

11.5 Financial transactions

Display:

- Transaction ID.
- Date.
- Business.
- Category.
- Amount.
- Currency.
- Status.
- Verification status.
- Source.
- Associated record.

Do not allow the frontend to directly execute transfers.

Financial operations must go through the P-07 and P-10 controlled authorization architecture.

11.6 Financial approvals

Display pending requests with:

- Requesting agent.
- Business.
- Purpose.
- Amount.
- Recipient.
- Budget impact.
- Risk.
- Approval status.

Approval actions must be bound to the exact transaction details.

11.7 Financial warnings

Display:

- Spending-limit warnings.
- Budget overruns.
- Unverified payments.
- Duplicate transaction warnings.
- Cash runway concerns.
- Unusual expenses.
- Negative profit trends.

Do not present a forecast as a confirmed financial event.

---

12. SURVIVAL AND SCALING DASHBOARD

Integrate P-08.

This module must make business survival decisions understandable.

12.1 Survival overview

Display:

- Businesses at risk.
- Cash runway warnings.
- Budget consumption.
- Loss-making businesses.
- Declining performance.
- Experiments near loss limits.
- Businesses ready for scaling review.

12.2 Business health indicators

Show:

- Revenue consistency.
- Profitability.
- Customer demand.
- Cash position.
- Operational costs.
- Customer acquisition efficiency.
- Delivery capacity.
- Dependency risk.

Use actual available metrics.

12.3 Scaling recommendations

Display proposed actions such as:

- Increase marketing investment.
- Expand a distribution channel.
- Improve pricing.
- Reduce operating costs.
- Increase automation.
- Improve customer retention.
- Expand product features.

Each recommendation must include:

- Supporting evidence.
- Expected benefits.
- Expected costs.
- Risks.
- Assumptions.
- Confidence.
- Approval requirements.

12.4 Survival decisions

Display recommended actions:

- Continue.
- Optimize.
- Reduce spending.
- Pause.
- Pivot.
- Scale.
- Close.

Do not automatically execute high-impact survival decisions from a dashboard recommendation.

Owner approval and the P-08 policy must govern such decisions.

---

13. DIGITAL EXECUTION CENTER

Integrate P-05.

The owner must be able to understand what the execution engine is doing across businesses.

13.1 Execution overview

Display:

- Running tasks.
- Queued tasks.
- Completed tasks.
- Failed tasks.
- Cancelled tasks.
- Tasks awaiting approval.

13.2 Task directory

Each task should include:

- Task ID.
- Objective.
- Description.
- Business.
- Project.
- Assigned agent.
- Priority.
- Status.
- Creation time.
- Start time.
- Completion time.
- Output references.
- Error details.

13.3 Task detail

Display execution stages.

Example:

1. Request received.
2. Objective analyzed.
3. Plan generated.
4. Permissions checked.
5. Agents assigned.
6. Execution started.
7. Results collected.
8. Results validated.
9. Final output generated.

Only display stages that are genuinely implemented and observable.

13.4 Execution controls

Provide:

- Pause.
- Resume.
- Cancel.
- Retry.
- Inspect output.
- View logs.
- Reassign, where supported.

Every control must have a real backend action and appropriate authorization.

13.5 Failure analysis

For failed tasks, show:

- Failure stage.
- Error category.
- Responsible component.
- Retry eligibility.
- Suggested remediation.
- Related logs.
- Whether manual intervention is required.

Do not automatically retry dangerous or non-idempotent operations.

---

14. MEMORY AND LEARNING CENTER

Integrate P-09.

Create an interface that makes AUTONOMUS's knowledge and learning inspectable.

14.1 Memory overview

Display:

- Total memory records.
- Recent memories.
- Learning records.
- Knowledge categories.
- Contradictions.
- Records awaiting validation.
- Archived memories.

14.2 Memory categories

Provide filters for:

- Working memory.
- Episodic memory.
- Semantic memory.
- Procedural memory.
- Owner preferences and instructions.
- Organizational knowledge.
- Business knowledge.
- Technical knowledge.
- Experiment outcomes.

14.3 Memory detail

Display:

- Memory ID.
- Category.
- Content summary.
- Source.
- Confidence.
- Evidence.
- Creation date.
- Last validated date.
- Scope.
- Access restrictions.
- Related records.

14.4 Learning performance

Show:

- Completed experiments.
- Expected outcomes.
- Actual outcomes.
- Confirmed lessons.
- Uncertain lessons.
- Contradictions.
- Revalidated knowledge.

14.5 Owner controls

Where supported:

- Inspect memory.
- Correct information.
- Revalidate a record.
- Archive a record.
- Request deletion.
- Inspect source provenance.
- Review memory access history.

Do not allow an ordinary agent to modify owner-controlled instructions or security policies.

---

15. SECURITY AND GOVERNANCE CENTER

Integrate P-10.

The Security Center must give the owner a clear view of system protection.

15.1 Security overview

Display:

- Current security mode.
- Authentication status.
- Active sessions.
- Active agent permissions.
- Pending approvals.
- Critical alerts.
- Recent security events.
- Secret vault status.
- Backup status.
- Financial execution status.

15.2 Permission management

Allow inspection of:

- Human identities.
- Agent identities.
- Roles.
- Permissions.
- Business scopes.
- Tool access.
- Temporary capabilities.
- Revoked permissions.

All changes must be executed through P-10.

15.3 Approval center

Create a unified approval interface for:

- Financial operations.
- External publishing.
- Sensitive browser actions.
- System configuration changes.
- Agent privilege requests.
- High-impact file operations.
- Other restricted actions.

Display the exact action parameters and consequences.

15.4 Security event explorer

Allow filtering by:

- Severity.
- Event type.
- Agent.
- Business.
- Project.
- Date.
- Authorization result.
- Status.

15.5 Emergency controls

Provide:

- Pause autonomous operations.
- Disable external actions.
- Suspend transaction execution.
- Enter safe mode.
- Revoke temporary capabilities.
- Resume after owner verification.

Critical controls must be clearly distinguished from ordinary navigation.

Never let frontend-only state pretend that an emergency action succeeded.

---

16. SYSTEM OPERATIONS CENTER

Build a view for the health and performance of the AUTONOMUS infrastructure.

16.1 System status

Display:

- Backend health.
- Frontend health.
- Database health.
- Task queue health.
- Agent worker health.
- Memory store health.
- Local AI model health.
- Cloud AI provider health.
- Browser automation health.
- Security service health.

16.2 Hardware and resource monitoring

Where available, display:

- CPU usage.
- RAM usage.
- GPU usage.
- Disk utilization.
- Model memory consumption.
- Active processes.
- Background worker count.
- Queue depth.

Use reliable local telemetry.

Do not claim that a metric is available when the platform cannot retrieve it.

16.3 AI model management

Display:

- Configured provider.
- Active model.
- Available local models.
- Provider health.
- Model availability.
- Model response status.
- Inference latency, if measured.
- Resource usage, if available.

Allow authorized model configuration changes.

Do not expose API keys.

16.4 Task scheduler

Display:

- Scheduled tasks.
- Recurring workflows.
- Next run time.
- Last run time.
- Execution status.
- Associated business.
- Assigned agent.

Allow authorized controls for:

- Pause schedule.
- Resume schedule.
- Edit schedule.
- Cancel schedule.
- Inspect history.

16.5 Logs

Provide searchable views for:

- System logs.
- Agent logs.
- Execution logs.
- API errors.
- Security logs.
- Financial events.

Respect the access restrictions established in P-10.

Never expose secret values in log views.

---

17. AUTONOMOUS OPERATIONS CENTER

Create a unified view of ongoing autonomous activity.

17.1 Live operation feed

Show:

- Current objective.
- Active business.
- Current agents.
- Execution stage.
- Recent decisions.
- Tool activity.
- Approval dependencies.
- Errors.
- Completion status.

17.2 Operation detail

Each operation should show:

- Trigger.
- Objective.
- Plan.
- Assigned agents.
- Business scope.
- Permission checks.
- Approval events.
- Execution history.
- Output.
- Result verification.

17.3 Owner intervention

Allow the owner to:

- Pause.
- Stop.
- Redirect.
- Request explanation.
- Request a progress report.
- Review the plan.
- Approve a pending action.

These controls must integrate with the existing orchestration engine.

17.4 Transparency

The system must distinguish:

- Planned.
- Requested.
- Authorized.
- Executing.
- Completed.
- Verified.
- Failed.

A task being marked completed does not automatically mean its business result has been verified.

---

18. UNIFIED APPROVAL INBOX

Build one approval inbox across the operating system.

Do not force the owner to visit separate modules to discover critical pending decisions.

18.1 Approval categories

- Financial.
- Publishing.
- Browser actions.
- File operations.
- System changes.
- Agent permissions.
- Business lifecycle decisions.
- External communications.

18.2 Approval card

Each item should show:

- Request ID.
- Requesting agent.
- Business.
- Action.
- Exact parameters.
- Risk level.
- Reason.
- Consequences.
- Expiry.
- Related evidence.

18.3 Approval actions

Support:

- Approve once.
- Reject.
- Request modification.
- Open full details.

Where policies support limited standing authorization, make its scope and expiry explicit.

18.4 Approval safety

- Never approve automatically because an item has been pending for a long time.
- Never convert a rejected request into an approved one without a new decision.
- Never reuse an expired approval.
- Never approve an action whose parameters have changed.
- Never let an agent approve its own request.

---

19. REPORTING AND ANALYTICS CENTER

Create a unified reporting interface.

19.1 Report categories

- System performance.
- Agent performance.
- Opportunity research.
- Business performance.
- Financial performance.
- Survival and scaling.
- Execution history.
- Memory and learning.
- Security events.

19.2 Report filters

Support:

- Date range.
- Business.
- Project.
- Agent.
- Category.
- Status.
- Metric type.

19.3 Report generation

Where supported, allow:

- Generate report.
- Preview.
- Export PDF.
- Export CSV.
- Export JSON.
- Save report.
- Compare reporting periods.

Use existing backend data and reporting services.

Never fabricate data to fill report templates.

19.4 Report integrity

Each report must contain:

- Generation timestamp.
- Reporting period.
- Data sources.
- Metric definitions.
- Actual versus forecast labels.
- Known limitations.

---

20. GLOBAL SEARCH AND COMMAND PALETTE

Implement a fast global search experience.

Search across:

- Businesses.
- Opportunities.
- Agents.
- Tasks.
- Projects.
- Reports.
- Memory records.
- Security events.

Provide filters and useful result previews.

20.1 Command palette

Allow keyboard access through a configurable shortcut.

Suggested commands:

- Open Overview.
- Open Businesses.
- Open Agents.
- Search Opportunities.
- View Pending Approvals.
- Open Finance.
- View Security Alerts.
- Pause Autonomous Operations.
- Open System Health.

Sensitive commands must require backend authorization and any required confirmation.

---

21. DESIGN SYSTEM AND COMPONENT LIBRARY

Create reusable components instead of designing every page independently.

Suggested components:

- AppShell.
- Sidebar.
- TopStatusBar.
- PageHeader.
- MetricCard.
- StatusBadge.
- AlertCard.
- AgentCard.
- BusinessCard.
- OpportunityCard.
- TaskCard.
- ApprovalCard.
- ActivityFeed.
- DataTable.
- FilterBar.
- SearchPanel.
- ChartPanel.
- EmptyState.
- ErrorState.
- LoadingState.
- ConfirmationDialog.
- DetailDrawer.
- ContextPanel.
- Timeline.
- ProgressIndicator.

Create consistent:

- Color tokens.
- Typography tokens.
- Spacing tokens.
- Border tokens.
- Radius tokens.
- Shadows.
- Interaction states.
- Responsive breakpoints.

Use a consistent chart library if one is already installed and suitable.

Do not add multiple competing visualization libraries without justification.

---

22. REAL-TIME DATA AND STATE MANAGEMENT

The Command Center should display timely information without creating unnecessary load.

22.1 Data retrieval

Reuse existing APIs.

Create a centralized frontend API client with:

- Authentication handling.
- Error handling.
- Request cancellation.
- Timeout handling.
- Response validation.
- Retry policies where safe.

22.2 Real-time updates

Use existing WebSocket or server-sent event infrastructure if available.

If unavailable, introduce a suitable mechanism based on actual requirements.

Use:

- WebSockets for bidirectional real-time interaction where justified.
- Server-sent events for server-to-client streaming where suitable.
- Polling for low-frequency or non-critical updates.

Do not introduce a complex real-time architecture unnecessarily.

22.3 State management

Use the existing state management system if it is suitable.

Separate:

- Server state.
- Local interface state.
- Authentication state.
- Approval state.
- Global notifications.
- Live operational events.

Avoid duplicated state that can become inconsistent with the backend.

22.4 Freshness indicators

Display:

- Last updated.
- Connection status.
- Stale data warning.
- Loading state.
- Error state.

If the backend disconnects, do not silently display old data as current.

22.5 Data consistency

For important financial and security data:

- Use authoritative backend responses.
- Respect server-side timestamps.
- Avoid optimistic UI updates that imply a critical action succeeded before confirmation.
- Refresh after successful operations.
- Handle conflicts and stale data explicitly.

---

23. RESPONSIVE AND DESKTOP EXPERIENCE

AUTONOMUS is Windows-first, but the interface must remain usable on smaller screens.

23.1 Desktop

Optimize for:

- 1366×768.
- 1440×900.
- 1920×1080.
- Larger monitors.

Use available screen space intelligently.

23.2 Tablet

Adapt:

- Sidebar.
- Tables.
- Charts.
- Detail panels.
- Approval cards.

23.3 Mobile

Provide practical access to:

- System status.
- Pending approvals.
- Critical alerts.
- Business overview.
- Agent status.
- Emergency controls.

Do not attempt to squeeze the entire desktop interface onto a mobile screen.

23.4 Keyboard accessibility

Support:

- Keyboard navigation.
- Visible focus states.
- Escape-to-close behavior where appropriate.
- Logical tab order.
- Accessible labels.

23.5 Accessibility

Use semantic HTML and accessible interaction patterns.

Support:

- Screen readers.
- Adequate contrast.
- Reduced motion.
- Clear status text in addition to color.
- Appropriate keyboard access.

---

24. SETTINGS AND PERSONALIZATION

Create a centralized settings area.

Potential sections:

General

- Application appearance.
- Language, where supported.
- Timezone.
- Date format.
- Number format.
- Currency display.

Interface

- Theme.
- Sidebar behavior.
- Dashboard layout.
- Visible widgets.
- Default landing page.

Notifications

- Notification categories.
- Alert severity.
- Sound settings.
- Delivery preferences.

AI configuration

- Default provider.
- Model selection.
- Local/cloud preference.
- Inference limits.
- Resource controls.

Security

- Session settings.
- Authentication options.
- Active sessions.
- Security preferences.
- Approval policies.

Operations

- Default task settings.
- Background processing.
- Scheduling preferences.
- Resource limits.

Security settings must be governed by P-10.

Do not expose restricted configuration to ordinary agents.

---

25. DATABASE AND API REQUIREMENTS

Inspect existing schemas and endpoints first.

P-11 should primarily consume existing data.

Do not duplicate authoritative records for:

- Agents.
- Businesses.
- Opportunities.
- Tasks.
- Financial transactions.
- Memory.
- Security events.

If dashboard-specific preferences or layouts need storage, create only the minimum additional entities.

Potential entities:

- "dashboard_preferences"
- "dashboard_widget_layouts"
- "user_notification_preferences"
- "dashboard_saved_filters"
- "dashboard_report_preferences"

Potential API groupings:

GET  /api/dashboard/overview
GET  /api/dashboard/system-health
GET  /api/dashboard/activity
GET  /api/dashboard/attention

GET  /api/dashboard/agents/summary
GET  /api/dashboard/businesses/summary
GET  /api/dashboard/opportunities/summary
GET  /api/dashboard/execution/summary
GET  /api/dashboard/finance/summary
GET  /api/dashboard/security/summary

GET  /api/dashboard/notifications
POST /api/dashboard/notifications/{id}/read

GET  /api/dashboard/search
GET  /api/dashboard/approvals/summary

GET  /api/dashboard/preferences
PUT  /api/dashboard/preferences

These are suggested endpoints.

Reuse existing endpoints when appropriate.

If aggregation endpoints are needed, implement them efficiently and enforce backend authorization.

Do not create one oversized endpoint that returns every sensitive record to every frontend screen.

---

26. ERROR HANDLING AND EMPTY STATES

Every module must handle incomplete or unavailable data gracefully.

Create consistent states for:

- Loading.
- Empty.
- No results.
- Offline.
- Unauthorized.
- Forbidden.
- Backend unavailable.
- Partial data.
- Stale data.
- Failed operation.

Examples:

If no business exists, show a useful explanation and a link to the authorized business creation workflow.

If no agents are active, show the actual agent status rather than a fake active-agent card.

If financial data is unavailable, explain that it is not connected or verified.

If the AI provider is offline, make that status visible.

Do not use fabricated sample metrics in production views.

Sample/demo data must be explicitly identified and separated from actual operating data.

---

27. PERFORMANCE AND RESOURCE OPTIMIZATION

The Command Center must remain efficient on modest hardware.

Requirements:

- Avoid loading every business record on initial page load.
- Use pagination for large tables.
- Use lazy loading for secondary modules.
- Cache safe, non-sensitive summary data appropriately.
- Avoid duplicate API requests.
- Debounce search input.
- Virtualize large activity feeds where useful.
- Optimize chart rendering.
- Avoid unnecessary full-page rerenders.
- Use bounded real-time subscriptions.
- Clean up event listeners and connections.
- Avoid continuously polling inactive pages.

The system should remain usable even when local inference is running.

Do not use an LLM to calculate ordinary dashboard totals.

Perform calculations through deterministic backend services.

---

28. TESTING AND QUALITY ASSURANCE

Create comprehensive frontend and integration tests.

28.1 Navigation tests

Verify:

- Every primary route loads.
- Navigation works.
- Sidebar collapse works.
- Browser back/forward behavior works.
- Deep links work where supported.

28.2 Data tests

Verify:

- Real backend values are displayed.
- Currency is formatted correctly.
- Dates use the configured timezone.
- Forecast and actual values are distinguished.
- Empty data is handled correctly.
- Stale data is identified.
- Unauthorized records are not displayed.

28.3 Interaction tests

Verify:

- Agent controls call the correct APIs.
- Task controls call the correct APIs.
- Business actions use the correct workflows.
- Approval actions preserve exact parameters.
- Notifications update correctly.
- Search returns scoped results.
- Filters work.
- Export functions produce valid files.

28.4 Security tests

Verify:

- Unauthenticated users cannot access protected pages or APIs.
- Hidden UI elements do not substitute for backend authorization.
- Restricted users cannot execute sensitive actions.
- Business data does not leak across scopes.
- Financial actions require appropriate approval.
- Security controls remain functional.
- Direct API calls cannot bypass permissions.

28.5 Responsive tests

Test at:

- 1920×1080.
- 1440×900.
- 1366×768.
- Tablet-sized viewport.
- Mobile-sized viewport.

28.6 Performance tests

Measure:

- Initial load.
- Dashboard data retrieval.
- Navigation.
- Large-table rendering.
- Activity-feed rendering.
- Real-time update overhead.

28.7 Acceptance scenarios

Scenario 1: System overview

The owner opens AUTONOMUS.

Expected: Actual system health, agent activity, business metrics, pending approvals, and critical alerts are displayed.

Scenario 2: Agent inspection

The owner opens an active agent.

Expected: Identity, assigned task, permissions, current status, and recent activity are visible.

Scenario 3: Business monitoring

The owner opens a business.

Expected: Business status, operational activity, financial records, and risks are visible according to authorization.

Scenario 4: Financial accuracy

The dashboard displays financial performance.

Expected: Forecast, invoiced, collected, refunded, and actual profit figures are correctly distinguished.

Scenario 5: Pending approval

An agent requests a sensitive action.

Expected: The request appears in the unified approval inbox with exact parameters and consequences.

Scenario 6: Approval execution

The owner approves a valid request.

Expected: The backend validates approval and permission before execution. The UI reports success only after receiving confirmation.

Scenario 7: Security alert

A security event is generated.

Expected: It appears in the security dashboard with appropriate severity and source.

Scenario 8: Backend disconnect

The backend becomes unavailable.

Expected: The interface displays connection failure and does not represent stale data as live.

Scenario 9: Agent pause

The owner pauses an agent.

Expected: The backend confirms the state transition and the interface updates accordingly.

Scenario 10: Emergency stop

The owner activates emergency stop.

Expected: The request goes through P-10, and the UI displays the confirmed emergency state only after backend confirmation.

Scenario 11: Mobile access

The owner opens the application on a mobile-sized screen.

Expected: Critical information, alerts, approvals, and essential controls remain accessible.

Scenario 12: No-data environment

A fresh installation has no businesses, opportunities, or financial records.

Expected: Useful empty states are displayed without fabricated metrics.

Scenario 13: Cross-business restriction

An agent or restricted user attempts to view another business.

Expected: The backend denies access and the frontend displays an appropriate error.

Scenario 14: Long-running task

An operation remains active for an extended period.

Expected: Its actual status and latest progress are displayed without falsely marking it completed.

---

29. IMPLEMENTATION SEQUENCE

Implement P-11 in stages.

Stage 1: Audit and foundation

- Audit P-01 through P-10.
- Inspect existing frontend.
- Map backend APIs.
- Define navigation.
- Create design tokens.
- Create application shell.
- Establish API integration strategy.

Stage 2: Overview and global navigation

- Sidebar.
- Top status bar.
- Overview dashboard.
- System health.
- Global activity feed.
- Notifications.
- Attention-required section.

Stage 3: Operational interfaces

- Master Intelligence interface.
- Agent Command Center.
- Execution Center.
- Opportunity Intelligence.

Stage 4: Business and financial interfaces

- Business Portfolio.
- Business detail views.
- Financial Command Center.
- Survival and Scaling dashboard.

Stage 5: Intelligence and security interfaces

- Memory and Learning Center.
- Security Center.
- Unified Approval Inbox.

Stage 6: Operations and analytics

- System Operations.
- Autonomous Operations.
- Reporting Center.
- Global search.
- Command palette.

Stage 7: Personalization and polish

- Settings.
- Responsive layouts.
- Keyboard accessibility.
- Loading and empty states.
- Error handling.
- Animation refinement.

Stage 8: Testing and final audit

- Run frontend tests.
- Run backend integration tests.
- Run authorization tests.
- Run responsive tests.
- Verify real data integration.
- Verify all controls.
- Verify performance.
- Document remaining limitations.

Do not implement all screens as disconnected mockups and call the product complete.

---

30. DEFINITION OF DONE

P-11 is complete only when the following criteria are met.

Application shell

- [ ] Premium application shell implemented.
- [ ] Navigation works.
- [ ] Top status bar uses actual backend data.
- [ ] Global notification system works.
- [ ] Global search works.
- [ ] Responsive layout works.

Overview

- [ ] System health is accurate.
- [ ] Active agents are accurate.
- [ ] Task metrics are accurate.
- [ ] Business metrics are accurate.
- [ ] Financial metrics use authoritative records.
- [ ] Attention-required items are correctly prioritized.

Operational interfaces

- [ ] Master Intelligence interface works.
- [ ] Agent Command Center works.
- [ ] Execution Center works.
- [ ] Opportunity interface works.
- [ ] Business Portfolio works.
- [ ] Financial Command Center works.
- [ ] Survival and Scaling interface works.
- [ ] Memory and Learning interface works.
- [ ] Security Center works.
- [ ] Approval Inbox works.
- [ ] Operations Center works.

Data integrity

- [ ] No fake production metrics.
- [ ] Actual and forecast data are separated.
- [ ] Unavailable data is identified.
- [ ] Stale data is identified.
- [ ] Backend remains the source of truth.

Security

- [ ] Authentication is enforced.
- [ ] Backend authorization remains authoritative.
- [ ] P-10 approval workflows are respected.
- [ ] Financial actions cannot bypass P-07 and P-10.
- [ ] Business isolation is preserved.
- [ ] Sensitive data is not exposed through frontend state or APIs.

Quality

- [ ] Existing functionality preserved.
- [ ] Critical interactions work.
- [ ] Tests pass.
- [ ] Responsive layouts pass.
- [ ] Accessibility checks completed.
- [ ] Performance is acceptable.
- [ ] Documentation updated.

Any feature that is only a visual mockup must be marked as a mockup, not as implemented functionality.

---

31. FINAL IMPLEMENTATION REPORT

Create:

"docs/command-center/P11_IMPLEMENTATION_REPORT.md"

Include:

1. Executive summary.
2. Initial frontend audit.
3. Existing backend integration map.
4. Final navigation architecture.
5. Design system.
6. Screens and modules implemented.
7. Components created.
8. Existing components reused.
9. APIs integrated.
10. APIs added or modified.
11. Database changes.
12. Real-time data architecture.
13. Authentication and authorization integration.
14. Approval integration.
15. Financial data integrity checks.
16. Responsive testing.
17. Accessibility testing.
18. Performance results.
19. Test results.
20. Known limitations.
21. Features not yet implemented.
22. Manual configuration required.
23. Recommended next actions.

Clearly distinguish between:

- Fully implemented and tested.
- Implemented but partially tested.
- Visual prototype only.
- Backend dependency missing.
- Not implemented.

Do not hide incomplete features.

---

32. STRICT DEVELOPMENT STOP CONDITION

After completing P-11:

1. Run the complete relevant test suite.
2. Inspect every changed file.
3. Verify all major routes.
4. Verify backend data integration.
5. Verify sensitive action authorization.
6. Verify financial accuracy.
7. Verify security integration.
8. Verify responsive behavior.
9. Generate the final implementation report.
10. Present the results to the owner.

STOP.

Do not automatically start P-12.

Do not implement autonomous operations beyond the scope of P-11.

Do not redesign backend intelligence or execution engines.

Do not modify the master constitution without owner approval.

Wait for explicit owner approval before proceeding to P-12.

---

33. FINAL DIRECTIVE

Build the AUTONOMUS Premium Command Center as the primary control interface for the entire operating system.

It must give the owner:

- Visibility into every important operation.
- Control over agents and tasks.
- A truthful picture of business performance.
- Accurate financial information.
- Clear approval workflows.
- Security awareness.
- Operational transparency.
- Fast access to critical decisions.

Remember:

A beautiful dashboard that displays false information is worse than no dashboard.

A button that does not perform its advertised action is not a feature.

A green status indicator is not proof of system health.

A planned operation is not an executed operation.

A completed task is not necessarily a verified business outcome.

The Command Center must show reality, explain activity, and give the owner control.

Build the interface on top of the existing AUTONOMUS architecture. Preserve working systems. Integrate real data. Respect P-10 security boundaries. Test every important interaction.

Complete P-11, document the result, and wait for approval before moving forward.

END OF P-11 DEVELOPMENT PROMPT
