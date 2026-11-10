AUTONOMUS P-07: FINANCIAL INTELLIGENCE ENGINE

Master Implementation Prompt | Phase 7

---

1. ROLE AND MISSION

Act as a Principal Financial Systems Architect, Senior FinTech Backend Engineer, Accounting Systems Engineer, Financial Data Engineer, Security Architect, and AI Systems Integration Specialist.

Your mission is to inspect, design, implement, test, and integrate the Financial Intelligence Engine (P-07) into the existing AUTONOMUS AI Business Operating System.

You are not building a simple income-expense tracker.

You are building a reliable financial intelligence infrastructure that enables AUTONOMUS to understand the financial condition of every business it manages, measure real commercial performance, control spending, detect financial risks, reconcile transactions, and make evidence-based financial recommendations.

The engine must answer questions such as:

1. How much money has each business actually received?
2. How much revenue is forecast, booked, invoiced, collected, refunded, or disputed?
3. What are the actual operating costs?
4. Which expenses are recurring?
5. What is the actual gross and net profit?
6. How much cash is available?
7. What financial obligations remain unpaid?
8. How much money is committed to ongoing experiments?
9. How much capital is protected and cannot be spent?
10. Which businesses are profitable, losing money, or financially unstable?
11. How long can a business continue operating with its current resources?
12. Which financial decisions require the owner's approval?
13. Are there discrepancies between recorded transactions and verified payment-provider records?
14. Is the system making decisions using verified financial data or merely projections?

The Financial Intelligence Engine must provide accurate, traceable, auditable financial information.

Core principle: AUTONOMUS must never confuse projected revenue with collected revenue, collected revenue with profit, or account balance with available spending capital.

---

2. DEVELOPMENT CONTEXT AND EXISTING ARCHITECTURE

AUTONOMUS is an existing project being developed through a sequential, phase-based architecture.

The locked architectural decisions are:

- Operating system: Windows-first.
- AI infrastructure: Hybrid, local AI by default, optional cloud AI.
- AI providers: Provider-independent architecture.
- Mandatory paid APIs: Not permitted.
- Backend: Python and FastAPI.
- Frontend: React and TypeScript.
- Desktop direction: Tauri.
- Database: SQLite initially, with a migration path to PostgreSQL.
- Local AI: Ollama and compatible GGUF models.
- Vector memory: ChromaDB or a replaceable alternative.
- Browser automation: Playwright.
- Testing: Pytest and appropriate frontend testing tools.
- Source control: Git and GitHub.
- Financial and security operations: Strictly permission-controlled.

The system is intended to operate on hardware with approximately:

- Intel i7-4712HQ processor.
- 16 GB RAM.
- NVIDIA Quadro K1100M 2 GB GPU.

Therefore, use lightweight deterministic financial computation rather than unnecessarily involving LLMs in accounting calculations.

2.1 Mandatory previous-phase inspection

Before writing or changing code, inspect the actual implementations of:

- P-01: Core Operating System.
- P-02: Master Intelligence Engine.
- P-03: Opportunity Discovery Engine.
- P-04: Dynamic Agent Factory.
- P-05: Universal Digital Execution Engine.
- P-06: Business Creation Engine.

Inspect the existing:

- Database schema and migrations.
- Business records and identifiers.
- Opportunity records and financial assumptions.
- Agent task and execution records.
- Event and notification systems.
- Permission and approval architecture.
- API structure.
- Authentication and authorization.
- Existing frontend components.
- Configuration and environment handling.
- Logging and audit systems.
- Existing tests.

Do not assume that previous phases were implemented exactly as originally specified.

Build against the actual repository.

Identify which existing capabilities can be reused and which are missing.

2.2 Architecture preservation rules

- Do not rebuild AUTONOMUS.
- Do not replace working modules unnecessarily.
- Do not create duplicate business, agent, task, or opportunity databases.
- Do not introduce a second financial system that conflicts with an existing ledger.
- Do not break existing APIs or interfaces without a documented migration.
- Do not remove existing functionality to simplify implementation.
- Use adapters and interfaces where existing modules need integration.
- Preserve backward compatibility wherever practical.
- Record architectural changes through Architecture Decision Records (ADRs).

If a required previous-phase component is missing, document the dependency and propose the smallest safe implementation or integration change.

Do not silently fabricate missing functionality.

---

3. FINANCIAL CONSTITUTION

The following rules are mandatory and cannot be overridden by an AI agent, opportunity score, business manager, or autonomous workflow.

3.1 Financial truth hierarchy

Every financial figure must have an explicit classification.

Use these categories:

1. Projected Revenue: Expected future income based on assumptions.
2. Booked Revenue: Commercially committed sales or orders, subject to their actual contractual and accounting status.
3. Invoiced Revenue: Amount billed to a customer.
4. Collected Revenue: Money confirmed as received through an authorized and verified source.
5. Refunded Revenue: Money returned to customers.
6. Disputed Revenue: Payments under dispute or chargeback.
7. Recognized Revenue: Revenue recognized according to the configured accounting policy.
8. Gross Profit: Revenue minus the applicable direct costs.
9. Net Operating Profit: Operating income minus applicable operating expenses.
10. Net Profit: Profit after the configured expenses and adjustments, subject to the selected accounting basis.
11. Cash Balance: Actual reported cash or account balance from an authoritative source.
12. Available Cash: Cash remaining after accounting for restrictions, committed payments, protected reserves, and applicable obligations.

These categories must never be merged into a single misleading revenue or profit figure.

Important:

- An invoice is not proof of payment.
- A payment authorization is not proof of settlement.
- A successful checkout screen is not sufficient proof of collected revenue.
- A projected sale is not collected revenue.
- A bank or payment-provider balance is not necessarily the business's available spending balance.
- Profit must not be calculated by simply subtracting estimated expenses from projected revenue and presenting the result as actual profit.

3.2 Financial evidence requirements

Every financial record must include appropriate evidence metadata:

- Source.
- Source record or external transaction ID.
- Business ID.
- Transaction date.
- Recording date.
- Currency.
- Amount.
- Financial classification.
- Verification status.
- Related invoice, order, customer, or expense when applicable.
- Supporting reference or evidence location.
- Creation method.
- Responsible actor or integration.
- Audit history.

Financial records must be traceable to their source.

If evidence is unavailable, label the record as unverified or estimated.

Never present unverified figures as verified financial facts.

3.3 Hard financial restrictions

AUTONOMUS must never:

- Access or control a wallet without explicit authorization.
- Expose private keys, seed phrases, bank credentials, or payment credentials to an LLM.
- Execute unrestricted financial transfers.
- Make autonomous investments.
- Perform cryptocurrency trading as part of this phase.
- Spend beyond configured budgets.
- Modify its own financial authorization limits.
- Delete financial history to hide losses.
- Manipulate accounting records to make a business appear profitable.
- Treat unpaid invoices as collected cash.
- Use unauthorized payment integrations.
- Claim tax compliance or accounting certification without qualified verification.

The human owner retains ultimate financial authority.

---

4. FINANCIAL INTELLIGENCE ARCHITECTURE

Build P-07 as a modular subsystem.

Recommended structure, adjusted to the existing repository:

financial/

- core/
  - money.py
  - currencies.py
  - accounting_rules.py
  - calculations.py
  - financial_periods.py
- ledger/
  - journal.py
  - journal_entries.py
  - accounts.py
  - ledger_validator.py
- revenue/
  - revenue_tracker.py
  - invoices.py
  - orders.py
  - subscriptions.py
- expenses/
  - expense_tracker.py
  - expense_categories.py
  - recurring_expenses.py
- payments/
  - payment_manager.py
  - provider_interfaces.py
  - webhook_processor.py
  - payment_verification.py
- reconciliation/
  - reconciliation_engine.py
  - reconciliation_rules.py
  - discrepancy_detector.py
- budgets/
  - budget_manager.py
  - spending_limits.py
  - reserve_manager.py
- forecasting/
  - revenue_forecaster.py
  - expense_forecaster.py
  - cash_flow_forecaster.py
  - scenario_engine.py
- profitability/
  - unit_economics.py
  - business_profitability.py
  - break_even.py
- risk/
  - financial_risk_engine.py
  - anomaly_detection.py
  - insolvency_warnings.py
- reporting/
  - financial_reports.py
  - business_statements.py
  - export_manager.py
- integrations/
  - adapters/
  - importers/
  - exchange_rates/
- api/
- models/
- services/
- tests/

This is a proposed logical structure, not permission to create duplicate directories or disregard existing architecture.

Separate deterministic financial calculations from AI interpretation.

---

5. FINANCIAL LEDGER AND ACCOUNTING FOUNDATION

This is the foundation of the entire phase.

Implement a ledger-based financial recording system.

5.1 Double-entry accounting foundation

Where appropriate, implement a double-entry journal with:

- Journal entries.
- Debit lines.
- Credit lines.
- Chart of accounts.
- Account types.
- Posting status.
- Transaction references.
- Reversal entries.
- Accounting periods.
- Audit history.

Every posted journal entry must satisfy:

Total Debits = Total Credits

Use decimal-safe arithmetic.

Never use binary floating-point arithmetic for financial amounts.

Use integer minor units or a suitable decimal implementation with explicit currency precision.

For example:

- INR: 2 decimal places.
- USD: 2 decimal places.
- JPY: 0 decimal places.

Currency precision must be configurable rather than hardcoded for all currencies.

5.2 Chart of accounts

Provide configurable account categories:

Assets

- Cash.
- Bank accounts.
- Payment processor balances.
- Accounts receivable.
- Other current assets.

Liabilities

- Accounts payable.
- Refund liabilities.
- Customer credits.
- Taxes payable.
- Subscription obligations.
- Other outstanding liabilities.

Equity

- Owner contributions.
- Retained earnings.
- Owner withdrawals.

Income

- Product sales.
- Service revenue.
- Subscription revenue.
- Affiliate income.
- Advertising income.
- Other operating income.

Expenses

- Software expenses.
- Hosting.
- Marketing.
- Advertising.
- Payment processing fees.
- Contractor costs.
- Operational expenses.
- Refund losses where applicable.
- Other business expenses.

Allow configurable account mappings for different business types.

Do not assume every business uses every account.

5.3 Immutable financial records

Once a transaction has been posted:

- Do not silently overwrite it.
- Do not permanently delete it.
- Correct errors through documented reversal or adjustment entries.
- Preserve the original source record.
- Preserve the correction history.
- Record the actor and timestamp.
- Record the reason for adjustment.

Financial history must remain auditable.

Implement protection against duplicate journal postings.

---

6. REVENUE INTELLIGENCE ENGINE

Build a revenue tracking system across all AUTONOMUS-managed businesses.

6.1 Supported revenue types

Support:

- One-time product sales.
- Digital downloads.
- Software subscriptions.
- SaaS plans.
- Service payments.
- Freelance projects.
- Consulting revenue.
- Affiliate commissions.
- Advertising revenue.
- Marketplace royalties.
- Licensing income.
- Recurring memberships.
- Other legitimate digital business income.

Use an extensible revenue category system.

6.2 Revenue record lifecycle

Implement a configurable lifecycle such as:

EXPECTED
→ ORDER_CREATED
→ PAYMENT_PENDING
→ PAYMENT_AUTHORIZED
→ PAYMENT_SETTLED
→ VERIFIED
→ RECOGNIZED

Additional states:

- CANCELLED.
- FAILED.
- PARTIALLY_REFUNDED.
- REFUNDED.
- DISPUTED.
- CHARGEBACK.
- REVERSED.

Do not force every payment through every state.

Use state transitions appropriate to the provider and business model.

6.3 Revenue metrics

Calculate and display:

- Total projected revenue.
- Total booked revenue.
- Total invoiced revenue.
- Total collected revenue.
- Total recognized revenue.
- Total refunds.
- Total chargebacks.
- Outstanding receivables.
- Recurring revenue.
- Monthly recurring revenue (MRR), where applicable.
- Annual recurring revenue (ARR), where applicable.
- Average order value.
- Customer lifetime value estimates, with assumptions.
- Revenue growth.
- Revenue concentration.
- Revenue per business.
- Revenue by channel.
- Revenue by product or service.

For subscription metrics:

- Separate active recurring contracts from actual cash collections.
- Handle cancellations.
- Handle upgrades and downgrades.
- Handle failed renewals.
- Handle trial subscriptions.
- Avoid double-counting annual subscriptions.
- Document the MRR and ARR calculation methodology.

6.4 Revenue evidence

Revenue must be supported by:

- Verified payment events.
- Authorized provider reports.
- Reconciled bank statements.
- Verified marketplace settlement records.
- Other approved authoritative evidence.

Manual entries may be permitted, but they must be labeled and approved according to the configured policy.

---

7. PAYMENT PROVIDER INTEGRATION FRAMEWORK

Build a provider-independent payment integration architecture.

Potential future providers include:

- Stripe.
- Razorpay.
- PayPal.
- Cashfree.
- Official marketplace payout systems.
- Bank statement imports.
- Other authorized providers.

Do not require every provider to be connected.

Do not assume API access is available for every service.

Use official APIs, documented webhook interfaces, or authorized exports only.

7.1 Adapter architecture

Define a common interface for:

- Payment event retrieval.
- Transaction verification.
- Settlement retrieval.
- Refund retrieval.
- Dispute retrieval.
- Balance retrieval, where supported.
- Payout retrieval.
- Provider health checks.

Provider-specific logic must remain isolated in adapters.

The core ledger must not depend directly on a particular provider.

7.2 Webhook security

Implement:

- Signature verification.
- Timestamp validation where supported.
- Idempotency keys.
- Replay protection.
- Duplicate-event protection.
- Event provenance.
- Safe event parsing.
- Rate limiting.
- Failure handling.
- Dead-letter or retry handling.
- Audit logging.

Never trust an incoming webhook solely because it contains a successful payment status.

Verify its authenticity according to the provider's official mechanism.

7.3 Payment confirmation

A payment must not be classified as collected solely from:

- A browser redirect.
- A frontend success message.
- An agent's report.
- An LLM response.
- An unverified webhook.
- An order creation event.

Require appropriate provider verification or reconciled financial evidence.

7.4 Offline-first operation

The system must continue working without internet connectivity.

Support:

- Manual transaction imports.
- CSV statement imports.
- Queued provider synchronization.
- Local financial reporting.
- Delayed reconciliation.
- Duplicate detection during synchronization.

When connectivity returns, synchronize safely without duplicating transactions.

---

8. EXPENSE INTELLIGENCE ENGINE

Build an expense tracking and classification system.

8.1 Expense categories

Support:

- Hosting and servers.
- Domain registration.
- Software subscriptions.
- AI inference costs.
- API costs.
- Advertising.
- Marketing.
- Payment processing.
- Contractors.
- Content production.
- Marketplace fees.
- Transaction fees.
- Maintenance.
- Operational expenses.
- Taxes and statutory obligations.
- Other configurable expenses.

8.2 Expense classification

Each expense should include:

- Business ID.
- Category.
- Amount.
- Currency.
- Date.
- Vendor.
- Description.
- Recurrence type.
- Payment status.
- Payment source.
- Supporting evidence.
- Verification status.
- Related project or experiment.
- Approval status.

Support:

- One-time expenses.
- Recurring expenses.
- Fixed expenses.
- Variable expenses.
- Direct expenses.
- Indirect expenses.
- Capital expenditures, where applicable.
- Operating expenditures.

Do not automatically assume every payment is an expense. Some payments may represent asset purchases, deposits, loans, transfers, or other accounting events.

8.3 Recurring expense detection

Detect:

- Monthly software charges.
- Annual subscriptions.
- Hosting renewals.
- Domain renewals.
- Recurring contractor payments.
- Advertising budgets.

Generate upcoming expense forecasts.

Detect unexpected changes in recurring costs.

Allow the owner to confirm or correct the classification.

---

9. BUDGET AND CAPITAL CONTROL ENGINE

This module must prevent uncontrolled spending.

9.1 Budget hierarchy

Support budgets at these levels:

- Overall AUTONOMUS budget.
- Individual business budget.
- Project budget.
- Experiment budget.
- Agent task budget.
- Marketing campaign budget.
- Integration or service budget.

Every budget must have:

- Budget owner.
- Budget period.
- Approved amount.
- Currency.
- Amount spent.
- Amount committed.
- Remaining amount.
- Approval requirements.
- Expiration or review date.

9.2 Spending controls

Implement configurable limits:

- Maximum daily spend.
- Maximum weekly spend.
- Maximum monthly spend.
- Maximum individual transaction.
- Maximum experiment loss.
- Maximum campaign expenditure.
- Maximum recurring commitments.
- Maximum business-level expenditure.

The system must check available budget before authorizing any controlled spending action.

9.3 Capital reserves

Implement protected reserves:

- Emergency reserve.
- Operational reserve.
- Tax reserve.
- Refund reserve.
- Business continuity reserve.
- Owner-designated protected capital.

Protected reserves must not be treated as freely available spending capital.

9.4 Budget enforcement

Example:

A business has:

- Total cash balance: ₹20,000.
- Protected reserve: ₹5,000.
- Existing committed expenses: ₹3,000.
- Other applicable obligations: ₹2,000.

The system must not treat the full ₹20,000 as available spending capital.

Available cash must account for all relevant restrictions and avoid double-counting commitments or liabilities.

Use deterministic formulas and explicit accounting rules.

9.5 Approval workflow

Define approval levels:

Level 0: Automatic

- Read-only analysis.
- Financial calculations.
- Report generation.
- Approved data synchronization.

Level 1: Pre-authorized

- Actions explicitly covered by an owner-approved budget and permission policy.
- Only within the approved limits.

Level 2: Owner approval

- New spending categories.
- New recurring commitments.
- Increased budgets.
- Material financial changes.
- Refunds or payouts where owner authorization is required.

Level 3: Restricted

- Bank transfers.
- Wallet transfers.
- Investments.
- High-value financial transactions.
- Changes to protected reserves.
- Changes to security or authorization policies.

These actions must remain blocked unless separately authorized through an appropriately secured execution mechanism.

An LLM cannot grant itself permission.

---

10. PROFITABILITY AND UNIT ECONOMICS ENGINE

Build deterministic profitability calculations.

10.1 Profitability metrics

Calculate:

- Gross revenue.
- Net revenue.
- Direct costs.
- Gross profit.
- Gross margin.
- Operating expenses.
- Operating profit.
- Net profit, where sufficient accounting data exists.
- Contribution margin.
- Break-even revenue.
- Break-even sales volume.
- Customer acquisition cost (CAC).
- Customer lifetime value (LTV).
- LTV-to-CAC ratio.
- Cost per acquisition.
- Cost per transaction.
- Average revenue per customer.
- Revenue per employee or contractor, where applicable.

Every metric must define its calculation method and required data.

If required data is missing, return an incomplete-data status rather than an invented value.

10.2 Business-specific economics

Different business models require different financial models.

Support separate calculation profiles for:

- SaaS.
- Digital products.
- Content and publishing.
- Freelance services.
- Productized services.
- Affiliate businesses.
- Advertising-supported platforms.
- Online education.
- E-commerce and distribution.
- B2B services.

Examples:

For SaaS:

- MRR.
- ARR.
- Churn.
- Expansion revenue.
- Gross margin.
- Customer acquisition cost.
- Payback period.

For digital products:

- Sales volume.
- Average selling price.
- Marketplace commission.
- Refund rate.
- Payment processing fees.
- Production cost.
- Contribution margin.

For services:

- Project revenue.
- Delivery cost.
- Contractor cost.
- Hours spent.
- Effective hourly margin.
- Customer retention.

Do not apply SaaS metrics blindly to a freelance business.

---

11. FINANCIAL FORECASTING AND SCENARIO ENGINE

Build a financial forecasting system that clearly distinguishes assumptions from verified results.

11.1 Forecasting capabilities

Support:

- Revenue forecasts.
- Expense forecasts.
- Cash-flow forecasts.
- Break-even forecasts.
- Runway estimates.
- Subscription forecasts.
- Customer growth forecasts.
- Experiment budget forecasts.

11.2 Forecasting methods

Start with deterministic, explainable methods:

- Historical averages.
- Moving averages.
- Trend-based estimates.
- Growth assumptions.
- Conversion-rate assumptions.
- Sales pipeline assumptions.
- Recurring revenue models.
- Scenario-based calculations.

Optional statistical models may be added if justified by data availability.

Do not use an LLM as the financial calculation engine.

11.3 Scenario planning

Every business should support:

Conservative scenario

- Lower customer acquisition.
- Lower conversion.
- Higher operating costs.
- Higher refunds or churn.

Base scenario

- Most defensible assumptions supported by available evidence.

Optimistic scenario

- Stronger conversion.
- Better retention.
- Increased demand.

Each scenario must show:

- Assumptions.
- Expected revenue.
- Expected expenses.
- Expected profit or loss.
- Cash requirements.
- Break-even point.
- Main risks.
- Confidence level.

Never label an optimistic forecast as expected income.

11.4 Forecast accuracy tracking

Compare historical forecasts with actual results.

Measure:

- Forecast error.
- Revenue variance.
- Expense variance.
- Cash-flow variance.
- Scenario accuracy.
- Assumption reliability.

Use the results to improve future forecasts.

Do not rewrite historical forecasts to make the system appear more accurate.

---

12. CASH FLOW AND FINANCIAL HEALTH ENGINE

Build an engine that measures financial sustainability.

12.1 Cash flow

Track:

- Opening cash balance.
- Cash inflows.
- Cash outflows.
- Net cash flow.
- Closing cash balance.
- Expected inflows.
- Expected outflows.
- Committed future payments.

Support configurable cash-flow periods:

- Daily.
- Weekly.
- Monthly.
- Quarterly.
- Custom date ranges.

Clearly distinguish actual and forecast cash flow.

12.2 Runway calculation

Calculate business runway using:

- Verified cash balance.
- Available cash.
- Average operating burn.
- Expected recurring expenses.
- Known liabilities.
- Reliable expected inflows.

Do not use uncollected invoices as guaranteed cash.

If there is insufficient historical data, mark runway as preliminary.

If the business has positive or irregular cash flow, explain the method used instead of producing misleading negative or infinite runway values.

12.3 Financial health classification

Create configurable statuses:

- HEALTHY.
- STABLE.
- WATCH.
- AT_RISK.
- CRITICAL.
- INSUFFICIENT_DATA.

Classification should consider:

- Available cash.
- Operating burn.
- Outstanding liabilities.
- Revenue stability.
- Profitability.
- Refunds and chargebacks.
- Recurring commitments.
- Budget utilization.
- Cash-flow projections.

Hard risk conditions must override favorable numerical scores.

For example, a business with high projected revenue but insufficient cash to meet known obligations must not be classified as financially healthy.

---

13. FINANCIAL RECONCILIATION ENGINE

Implement reconciliation between:

- Internal financial ledger.
- Payment providers.
- Bank statement imports.
- Marketplace payout records.
- Invoice and order records.
- Expense records.

13.1 Reconciliation workflow

1. Import or retrieve authoritative external records.
2. Validate their source and format.
3. Normalize currency, amount, date and transaction references.
4. Match transactions using deterministic matching rules.
5. Identify duplicate transactions.
6. Identify missing transactions.
7. Identify amount discrepancies.
8. Identify timing discrepancies.
9. Identify unmatched transactions.
10. Generate reconciliation reports.
11. Require authorized review for unresolved material discrepancies.
12. Record the final resolution.

13.2 Matching strategies

Support:

- Exact external transaction ID.
- Exact payment reference.
- Invoice reference.
- Amount and currency.
- Configurable date windows.
- Provider payout references.

Fuzzy matching may suggest potential matches but must never silently mark uncertain matches as verified.

13.3 Discrepancy classifications

- MATCHED.
- PARTIALLY_MATCHED.
- UNMATCHED.
- DUPLICATE.
- AMOUNT_MISMATCH.
- CURRENCY_MISMATCH.
- DATE_MISMATCH.
- SOURCE_MISMATCH.
- REQUIRES_REVIEW.

All material reconciliation decisions must be auditable.

---

14. MULTI-CURRENCY INTELLIGENCE

AUTONOMUS may manage businesses serving customers in different countries.

Implement multi-currency support.

Support:

- Transaction currency.
- Business base currency.
- Reporting currency.
- Exchange-rate source.
- Exchange-rate timestamp.
- Conversion method.
- Original amount.
- Converted amount.
- Rounding rules.

Do not convert amounts using an invented or undocumented exchange rate.

Use authorized, documented exchange-rate sources or manual rates with explicit provenance.

If exchange-rate data is unavailable, preserve the original currency and flag the conversion as pending.

Never combine different currencies into one total without a valid conversion method.

---

15. TAX AND COMPLIANCE SUPPORT

Implement tax-related tracking as an organizational and estimation feature, not as a tax certification system.

Support configurable fields for:

- Tax category.
- Jurisdiction.
- Estimated tax liability.
- Tax collected.
- Tax payable.
- Tax payment records.
- Filing period.
- Tax-related documents.
- Due dates.

The system must distinguish:

- Tax collected on behalf of authorities.
- Estimated tax obligations.
- Actual tax payments.
- Tax expenses, where applicable.

For India and international operations, design jurisdiction-aware configuration.

Do not hardcode tax rates or claim that a calculation is legally compliant.

Use official sources or owner-approved rates, with jurisdiction and effective date recorded.

Display clear notices when professional accounting or tax review is needed.

---

16. FINANCIAL RISK AND ANOMALY DETECTION

Build a financial risk engine that identifies suspicious or abnormal patterns.

Detect:

- Sudden expense increases.
- Duplicate charges.
- Unexpected recurring subscriptions.
- Repeated payment failures.
- High refund rates.
- High chargeback rates.
- Unusual transaction sizes.
- Revenue concentration.
- Declining contribution margin.
- Budget overruns.
- Cash-flow deterioration.
- Unexpected liabilities.
- Reconciliation discrepancies.
- Unusual agent spending behavior.

Use deterministic thresholds first.

Optional statistical anomaly detection may be introduced later.

Every alert must include:

- Severity.
- Affected business.
- Financial impact estimate.
- Evidence.
- Detection method.
- Recommended next action.
- Whether human review is required.

Do not automatically accuse a customer, vendor, or agent of fraud based on an anomaly.

Classify anomalies as signals requiring investigation.

---

17. AI FINANCIAL ANALYST

Integrate the financial engine with the existing P-02 Master Intelligence Engine.

The AI Financial Analyst must interpret verified financial data and generate useful explanations.

Example questions:

- Which business generated the highest collected revenue this month?
- Which business is losing money?
- Why did expenses increase?
- How much capital is committed?
- Which subscriptions should be reviewed?
- Which business is approaching a cash shortage?
- What is the break-even point for this product?
- Which experiment exceeded its approved budget?
- What would happen if customer acquisition fell by 30%?
- Which business deserves additional capital based on verified performance?

17.1 Strict AI boundaries

The LLM may:

- Explain financial reports.
- Summarize trends.
- Compare scenarios.
- Identify possible risks.
- Generate recommendations.
- Explain calculation methodology.
- Ask for missing information.

The LLM must not:

- Invent financial figures.
- Modify ledger entries directly.
- Approve its own spending.
- Override budgets.
- Execute transactions.
- Change financial permissions.
- Hide financial losses.
- Present estimates as verified data.

17.2 Financial answer provenance

Every AI-generated financial answer must distinguish:

- Verified facts.
- Calculated metrics.
- Forecasts.
- Assumptions.
- Missing information.
- Recommendations.

Where possible, provide references to the underlying report, ledger entries, reconciliation records, and calculation timestamp.

The financial engine must calculate the numbers. The LLM explains them.

---

18. BUSINESS-LEVEL FINANCIAL MANAGEMENT

Integrate P-07 with P-06 Business Creation Engine.

Every business must have a separate financial profile.

Include:

- Business ID.
- Business currency.
- Financial reporting period.
- Revenue records.
- Expense records.
- Ledger accounts.
- Budget.
- Reserves.
- Financial forecasts.
- Profitability.
- Cash flow.
- Financial health.
- Outstanding liabilities.
- Reconciliation status.

Support a consolidated AUTONOMUS financial view.

Important:

A consolidated view must not erase the individual financial identity of each business.

Support both:

1. Individual business financial statements.
2. Consolidated portfolio financial reports.

Transfers between businesses must be recorded as corresponding transactions and must not be counted as external portfolio revenue.

Prevent double-counting of internal transfers and inter-business transactions in consolidated reporting.

---

19. AGENT AND TASK FINANCIAL GOVERNANCE

Integrate P-07 with P-04 Agent Factory and P-05 Digital Execution Engine.

Every agent task that can create financial costs must declare:

- Business ID.
- Project ID.
- Agent ID.
- Task ID.
- Estimated cost.
- Approved cost limit.
- Cost category.
- Approval requirement.
- Actual cost, if measurable.

Examples:

- Hosting deployment.
- Domain purchase.
- Paid software subscription.
- Advertising campaign.
- API usage.
- Contractor engagement.
- Paid content production.

Agents must not independently create financial obligations outside their permission scope.

19.1 Resource-cost tracking

Where measurable, track:

- AI inference costs.
- Token usage.
- API consumption.
- Cloud compute.
- Storage.
- Hosting.
- Browser automation services.
- Third-party service usage.

For local inference, distinguish:

- Direct monetary cost.
- Estimated electricity cost.
- Hardware resource consumption.

Do not invent a monetary cost for free local software.

Use configurable electricity and hardware cost assumptions if the owner wants operational cost estimates.

---

20. FINANCIAL DATABASE DESIGN

Design the database based on the existing schema.

Avoid unnecessary duplication.

The following are logical entities to consider:

- financial_accounts
- journal_entries
- journal_lines
- financial_transactions
- revenue_records
- expense_records
- invoices
- orders
- subscriptions
- payment_providers
- payment_events
- provider_payouts
- refunds
- disputes
- reconciliation_sessions
- reconciliation_items
- budgets
- budget_allocations
- spending_limits
- financial_reserves
- cash_balances
- exchange_rates
- financial_forecasts
- forecast_assumptions
- financial_scenarios
- financial_alerts
- financial_approvals
- financial_audit_logs
- financial_periods
- tax_records

These are proposed logical entities, not a requirement to create every table independently.

Use foreign keys, appropriate constraints, indexes, timestamps, and migrations.

20.1 Required data integrity

Enforce:

- Valid business references.
- Valid currency codes.
- Valid amount precision.
- Unique external transaction identifiers within the relevant provider/account scope.
- Double-entry balance.
- Valid state transitions.
- Idempotent event processing.
- Referential integrity.
- Immutable posted records.
- Authorized adjustments.

Use database transactions for multi-record financial operations.

A partially completed financial posting must never leave the ledger in an inconsistent state.

---

21. BACKEND API DESIGN

Create API endpoints following existing AUTONOMUS conventions.

Suggested endpoint groups:

Dashboard

- GET /api/financial/dashboard
- GET /api/financial/overview
- GET /api/financial/health

Business finances

- GET /api/financial/businesses/{business_id}
- GET /api/financial/businesses/{business_id}/summary
- GET /api/financial/businesses/{business_id}/profitability
- GET /api/financial/businesses/{business_id}/cashflow

Revenue

- GET /api/financial/revenue
- POST /api/financial/revenue
- GET /api/financial/revenue/{revenue_id}

Expenses

- GET /api/financial/expenses
- POST /api/financial/expenses
- GET /api/financial/expenses/{expense_id}

Ledger

- GET /api/financial/ledger/accounts
- GET /api/financial/ledger/journals
- GET /api/financial/ledger/journals/{journal_id}

Budgets

- GET /api/financial/budgets
- POST /api/financial/budgets
- GET /api/financial/budgets/{budget_id}
- POST /api/financial/budgets/{budget_id}/allocations

Forecasting

- GET /api/financial/forecasts
- POST /api/financial/forecasts
- GET /api/financial/scenarios

Reconciliation

- GET /api/financial/reconciliation
- POST /api/financial/reconciliation/import
- POST /api/financial/reconciliation/{session_id}/review

Payments

- GET /api/financial/payments/providers
- POST /api/financial/payments/providers
- POST /api/financial/payments/webhooks/{provider}

Approvals

- GET /api/financial/approvals
- POST /api/financial/approvals/{approval_id}/decision

Reports

- GET /api/financial/reports/profit-loss
- GET /api/financial/reports/cashflow
- GET /api/financial/reports/balance-sheet
- GET /api/financial/reports/budget-utilization
- GET /api/financial/reports/reconciliation

These are suggested routes. Match the existing API structure and authentication model.

All write operations must enforce permissions, validation, audit logging, and idempotency where appropriate.

Never expose secrets in API responses.

---

22. FINANCIAL COMMAND CENTER UI

Implement the financial interface within the existing AUTONOMUS frontend.

Do not build the complete P-11 Command Center prematurely.

P-07 should deliver functional financial views that can later be integrated into P-11.

22.1 Portfolio overview

Display:

- Total verified collected revenue.
- Total verified expenses.
- Gross profit.
- Net profit, where sufficiently supported.
- Cash balance.
- Available cash.
- Protected reserves.
- Outstanding liabilities.
- Committed spending.
- Portfolio financial health.
- Active financial warnings.

Clearly label the reporting currency and selected period.

22.2 Revenue dashboard

Display:

- Revenue by business.
- Revenue by source.
- Revenue by period.
- Revenue by product.
- Collected versus projected revenue.
- Refunds and chargebacks.
- Recurring revenue.

Never combine actual and projected figures into one unlabeled chart.

22.3 Expense dashboard

Display:

- Expenses by category.
- Expenses by business.
- Recurring costs.
- Fixed versus variable costs.
- Budget utilization.
- Unusual expense changes.

22.4 Profitability dashboard

Display:

- Gross profit.
- Net profit.
- Profit margin.
- Break-even status.
- Contribution margin.
- Unit economics.
- Business profitability ranking.

Clearly identify businesses with insufficient financial data.

22.5 Cash-flow dashboard

Display:

- Historical cash flow.
- Forecast cash flow.
- Available cash.
- Protected reserves.
- Outstanding obligations.
- Runway estimate.

Use separate visual treatments for actual and forecast values.

22.6 Financial alerts and approvals

Display:

- Budget overruns.
- Unusual expenses.
- Payment discrepancies.
- Failed reconciliations.
- Upcoming renewals.
- Cash shortages.
- Pending financial approvals.

Every alert should lead to relevant evidence and a documented action.

---

23. SECURITY AND PRIVACY REQUIREMENTS

Financial information is highly sensitive.

Implement:

- Role-based access control.
- Business-level financial permissions.
- Least-privilege access.
- Secure credential storage.
- Environment variable protection.
- Encryption for sensitive information where appropriate.
- Secure local database permissions.
- Input validation.
- Webhook verification.
- API authentication.
- Rate limiting.
- Audit logs.
- Backup and recovery.
- Secure import handling.
- Data export controls.

23.1 Secret management

Never store the following in ordinary database fields or source code:

- Bank passwords.
- Payment-provider secret keys.
- Wallet private keys.
- Seed phrases.
- Recovery codes.
- Browser authentication cookies.

Use a suitable secure credential store, such as Windows Credential Manager or an appropriately protected secret-management mechanism.

Never send these credentials to the LLM.

Agents must receive only the minimum non-secret information needed for their task.

23.2 Transaction execution separation

The Financial Intelligence Engine is primarily an accounting, analysis, and governance subsystem.

If transaction execution is needed in the future, it must use a separate controlled executor.

That executor must have:

- Explicit permissions.
- Independent authorization.
- Transaction-level limits.
- Destination restrictions.
- Owner approval when required.
- Transaction preview.
- Execution confirmation.
- Post-execution verification.
- Complete audit history.

P-07 must not implement unrestricted autonomous transfers.

---

24. REPORTING AND EXPORT

Generate reliable financial reports.

Support:

- Profit and loss statement.
- Balance sheet.
- Cash-flow statement.
- Revenue report.
- Expense report.
- Budget utilization.
- Financial health report.
- Reconciliation report.
- Business comparison report.
- Forecast-versus-actual report.

Support export formats such as:

- CSV.
- JSON.
- PDF.

Exports must preserve:

- Currency.
- Reporting period.
- Accounting basis.
- Calculation methodology.
- Data freshness.
- Verification status.
- Report generation timestamp.

Do not label management estimates as audited financial statements.

---

25. INTEGRATION CONTRACTS WITH OTHER PHASES

P-02: Master Intelligence

Provide financial query tools and structured financial summaries.

The intelligence engine may request calculations and reports but must not modify the ledger directly.

P-03: Opportunity Discovery

Receive initial cost assumptions, revenue assumptions, expected margins, and break-even estimates.

Once an opportunity becomes a real business, maintain separate forecast and actual financial records.

Use actual results to evaluate the quality of original opportunity assumptions.

P-04: Agent Factory

Provide permission-aware budget and task-cost interfaces.

Agents must not have direct unrestricted ledger access.

P-05: Digital Execution Engine

Track measurable costs created by execution tasks.

Check financial permissions before controlled spending actions.

P-06: Business Creation Engine

Create a financial profile when a business is established.

Receive business type, revenue model, currency, and initial budget.

P-08: Survival and Scaling Engine

Expose reliable financial indicators:

- Verified collected revenue.
- Actual expenses.
- Profitability.
- Cash flow.
- Available capital.
- Runway.
- Financial risk.
- Budget utilization.
- Reconciliation status.

P-08 must use P-07 financial truth rather than generating its own competing financial calculations.

Define a stable integration interface now, but do not implement P-08 in this phase.

---

26. TESTING AND VALIDATION

Financial correctness must be treated as a critical system requirement.

Write comprehensive automated tests.

26.1 Unit tests

Test:

- Currency precision.
- Decimal arithmetic.
- Debit-credit balancing.
- Revenue calculations.
- Expense calculations.
- Gross profit.
- Net profit.
- Contribution margin.
- Break-even calculations.
- Cash-flow calculations.
- Available cash.
- Budget utilization.
- Runway.
- MRR and ARR.
- Refund calculations.
- Exchange-rate conversion.

26.2 Integration tests

Test:

- Business-to-financial profile integration.
- Revenue recording.
- Expense recording.
- Ledger posting.
- Payment event processing.
- Webhook verification.
- Reconciliation.
- Budget enforcement.
- Financial report generation.
- AI financial query integration.

26.3 Security tests

Test:

- Unauthorized financial access.
- Cross-business data leakage.
- Unauthorized budget changes.
- Unauthorized spending.
- Secret exposure.
- Forged webhook events.
- Replay attacks.
- Duplicate events.
- Financial record tampering.
- Invalid currency and amount inputs.
- Unauthorized ledger modification.
- Prompt injection through imported financial descriptions.

26.4 Critical financial scenarios

Scenario 1: Projected versus collected revenue

A business forecasts ₹50,000 in revenue but has received only ₹10,000.

Expected result:

- Projected revenue: ₹50,000.
- Collected revenue: ₹10,000.
- The system must not report ₹50,000 as collected revenue.

Scenario 2: Refund

A customer pays ₹1,000 and later receives a ₹200 partial refund.

Expected result:

- Original payment remains traceable.
- Refund is recorded independently.
- Net collected amount reflects the refund.
- Ledger entries remain balanced.

Scenario 3: Duplicate webhook

The same successful payment event is received three times.

Expected result:

- Only one economic transaction is posted.
- Duplicate events are recorded or safely acknowledged.
- No duplicate revenue is created.

Scenario 4: Unverified payment

An agent reports that a customer paid ₹5,000, but no authoritative evidence exists.

Expected result:

- The record remains unverified.
- It does not count as verified collected revenue.

Scenario 5: Budget restriction

A business has ₹10,000 available, but its approved experiment budget is ₹2,000.

An agent attempts to spend ₹2,500.

Expected result:

- The action is rejected or held for approval.
- No unauthorized financial obligation is created.
- An audit event is generated.

Scenario 6: Protected reserves

A business has ₹20,000 cash, ₹5,000 protected reserves, and ₹3,000 committed expenses.

Expected result:

- Available cash reflects the restrictions.
- The protected reserve cannot be treated as freely spendable.

Scenario 7: Currency conversion

A business records revenue in USD and reports in INR.

Expected result:

- Original USD transaction remains intact.
- The exchange rate and timestamp are recorded.
- Converted INR amount is traceable.
- Missing rates result in pending conversion, not fabricated values.

Scenario 8: Reconciliation mismatch

A payment provider reports ₹1,000, while the internal ledger reports ₹900.

Expected result:

- The discrepancy is flagged.
- The system does not silently overwrite either value.
- Resolution requires evidence and an auditable adjustment.

Scenario 9: Consolidated reporting

Two businesses transfer funds between themselves.

Expected result:

- The internal transfers are visible in individual business records.
- They are not counted as new external revenue in consolidated portfolio reporting.

Scenario 10: Missing financial data

A business has projected revenue but no verified expenses or payment evidence.

Expected result:

- Financial health is marked INSUFFICIENT_DATA where appropriate.
- Net profit is not invented.
- Missing evidence is clearly identified.

Scenario 11: Concurrent payment events

Two workers process the same external payment simultaneously.

Expected result:

- Database constraints and idempotency prevent duplicate posting.
- The final ledger remains consistent.

Scenario 12: Failed transaction posting

A journal operation fails partway through.

Expected result:

- Database transaction rollback prevents a partially posted financial event.
- No unbalanced journal remains.

Scenario 13: Negative financial outcome

A business receives ₹5,000 and incurs ₹8,000 in expenses.

Expected result:

- The loss is reported accurately.
- The system does not hide or reclassify the loss to make the business look successful.

Scenario 14: Unauthorized transfer request

An agent attempts to transfer money from a connected account.

Expected result:

- The request is blocked.
- No credentials are exposed.
- The attempt is audited.

---

27. PERFORMANCE AND RESOURCE OPTIMIZATION

AUTONOMUS must operate efficiently on modest Windows hardware.

Requirements:

- Financial calculations must use ordinary deterministic Python code.
- Do not invoke an LLM for basic accounting.
- Avoid unnecessary background workers.
- Use bounded task concurrency.
- Use database indexes appropriately.
- Paginate transaction history.
- Cache expensive report calculations carefully.
- Use incremental synchronization.
- Prevent duplicate background jobs.
- Avoid excessive polling.
- Keep frontend financial dashboards responsive.
- Support SQLite initially.
- Keep database access compatible with a future PostgreSQL migration.

Financial accuracy must never be sacrificed for performance.

---

28. DOCUMENTATION REQUIREMENTS

Create or update documentation covering:

1. Financial Intelligence architecture.
2. Database schema.
3. Ledger and accounting methodology.
4. Revenue classification.
5. Expense classification.
6. Profitability calculation formulas.
7. Budget and reserve rules.
8. Payment provider integration interface.
9. Webhook security.
10. Reconciliation methodology.
11. Multi-currency behavior.
12. Forecasting methodology.
13. Financial health classification.
14. API documentation.
15. Permission and approval model.
16. Secret-management approach.
17. Backup and recovery.
18. Testing instructions.
19. Known limitations.
20. Future integration requirements for P-08.

Document every important calculation.

A developer must be able to understand exactly how AUTONOMUS arrived at a financial figure without asking an LLM to explain its own output.

---

29. IMPLEMENTATION SEQUENCE

Do not implement the entire phase in one uncontrolled operation.

Use the following sequence.

Stage 1: Repository and architecture audit

- Inspect P-01 through P-06.
- Map existing business, opportunity, task, and permission models.
- Identify dependencies.
- Identify architectural conflicts.
- Prepare an implementation plan.

Stage 2: Financial core

- Implement currency-safe money handling.
- Implement accounting periods.
- Implement chart of accounts.
- Implement journal entries and journal validation.
- Implement immutable financial records.
- Add migrations and tests.

Stage 3: Revenue and expense management

- Implement revenue lifecycle.
- Implement expense lifecycle.
- Implement refunds and disputes.
- Integrate with business records.
- Add evidence classification.

Stage 4: Budget and capital governance

- Implement budget hierarchy.
- Implement spending limits.
- Implement protected reserves.
- Implement approval workflow.
- Integrate with P-04 and P-05.

Stage 5: Payment integration foundation

- Implement provider interfaces.
- Implement secure webhook processing.
- Implement idempotency.
- Implement payment verification.
- Implement offline imports.

Do not claim a provider integration is complete unless it has been tested against that provider's actual official interface or verified test environment.

Stage 6: Reconciliation

- Implement provider and bank statement imports.
- Implement matching.
- Implement discrepancy detection.
- Implement reconciliation reports.

Stage 7: Profitability and forecasting

- Implement unit economics.
- Implement cash-flow forecasting.
- Implement break-even calculations.
- Implement scenario analysis.
- Implement forecast-versus-actual reporting.

Stage 8: Financial risk and intelligence

- Implement financial health classifications.
- Implement anomaly detection.
- Implement alerts.
- Integrate with P-02.

Stage 9: Financial frontend

- Implement portfolio overview.
- Implement business-level financial views.
- Implement revenue and expense views.
- Implement budgets.
- Implement cash flow.
- Implement reports and approvals.

Stage 10: Integration and independent audit

- Test all previous-phase integrations.
- Run all financial and security tests.
- Review accounting correctness.
- Review database consistency.
- Review performance.
- Fix critical issues.
- Produce a completion report.

---

30. ACCEPTANCE CRITERIA

P-07 is complete only when all applicable criteria below are satisfied.

Financial correctness

- [ ] Revenue classifications are separate and accurate.
- [ ] Collected revenue requires verified evidence.
- [ ] Expenses are traceable.
- [ ] Ledger entries balance.
- [ ] Financial amounts use safe precision.
- [ ] Posted records cannot be silently overwritten.
- [ ] Refunds and chargebacks are represented correctly.
- [ ] Consolidated reporting avoids double-counting internal transfers.
- [ ] Profit calculations are reproducible.
- [ ] Missing data is identified honestly.

Financial governance

- [ ] Budgets exist at required levels.
- [ ] Spending limits are enforced.
- [ ] Protected reserves are respected.
- [ ] Approval workflows operate correctly.
- [ ] Agents cannot bypass financial permissions.
- [ ] Unrestricted transfers are impossible through the financial intelligence subsystem.

Data integrity

- [ ] Duplicate payment events are prevented.
- [ ] Webhook authenticity is checked.
- [ ] Reconciliation works.
- [ ] Discrepancies are visible.
- [ ] Audit history is preserved.
- [ ] Financial database operations are transaction-safe.

Intelligence

- [ ] Business profitability is calculated.
- [ ] Forecasts are separated from actuals.
- [ ] Scenario analysis works.
- [ ] Cash-flow analysis works.
- [ ] Financial health classification works.
- [ ] AI explanations use structured financial evidence.

Integration

- [ ] P-02 can query financial intelligence.
- [ ] P-03 assumptions can be compared with actual results.
- [ ] P-04 agents receive budget-aware permissions.
- [ ] P-05 execution costs can be tracked.
- [ ] P-06 businesses receive financial profiles.
- [ ] P-08 has a documented integration interface.

Engineering quality

- [ ] Migrations are tested.
- [ ] Unit tests pass.
- [ ] Integration tests pass.
- [ ] Security tests pass.
- [ ] Existing functionality remains operational.
- [ ] Documentation is updated.
- [ ] No secrets are committed.
- [ ] No unimplemented functionality is falsely marked complete.

Any critical financial-integrity or authorization test failure blocks completion.

---

31. FINAL AUDIT AND DELIVERY REPORT

At the end of P-07, produce a detailed report containing:

1. Original repository condition.
2. Existing financial capabilities discovered.
3. Missing capabilities.
4. Architecture changes.
5. Files created.
6. Files modified.
7. Database migrations.
8. Financial calculation methodology.
9. Ledger implementation details.
10. Revenue and expense capabilities.
11. Budget and reserve implementation.
12. Payment integration status.
13. Reconciliation status.
14. Forecasting and profitability status.
15. Security controls implemented.
16. API endpoints created.
17. Frontend features created.
18. Tests executed.
19. Test results.
20. Known limitations.
21. Unresolved risks.
22. Manual configuration required.
23. P-08 integration readiness.

Use explicit implementation statuses:

- COMPLETED AND TESTED.
- IMPLEMENTED BUT NOT FULLY TESTED.
- PARTIALLY IMPLEMENTED.
- BLOCKED.
- NOT IMPLEMENTED.
- REQUIRES OWNER CONFIGURATION.

Do not mark a feature complete merely because its files or UI have been created.

---

32. STRICT DEVELOPMENT RULES

1. Inspect before implementing.
2. Preserve all working previous phases.
3. Never invent financial records.
4. Never invent provider integrations.
5. Never expose financial credentials to an LLM.
6. Never allow agents to override financial controls.
7. Never use floating-point arithmetic for monetary calculations.
8. Never silently delete or modify posted financial history.
9. Never report forecast revenue as actual collected revenue.
10. Never count internal transfers as new portfolio revenue.
11. Never treat protected reserves as available capital.
12. Never execute unrestricted financial transactions.
13. Never hide losses or reconciliation discrepancies.
14. Never claim tax or accounting certification.
15. Test every critical financial calculation.
16. Document all material architectural changes.
17. Do not begin another development phase automatically.

If a requirement conflicts with an existing working architecture, explain the conflict and propose the safest minimal change before proceeding.

If a financial rule is ambiguous, stop and document the decision required rather than silently choosing a potentially unsafe interpretation.

---

33. FINAL EXECUTION BOUNDARY

Your responsibility is to complete P-07: Financial Intelligence Engine only.

After successful implementation and independent testing:

- Integrate P-07 with P-01 through P-06.
- Verify the integration contracts intended for P-08.
- Produce the final audit report.
- List all outstanding limitations.
- Present the system's actual completion status.
- Summarize the financial governance protections now active.

STOP AFTER P-07.

Do not automatically begin P-08: Survival and Scaling Engine.

Wait for explicit approval from the human owner.

The final objective is not to make AUTONOMUS appear financially intelligent.

It is to make AUTONOMUS financially accountable, mathematically reliable, evidence-driven, and incapable of casually risking the owner's capital.

END OF P-07 MASTER IMPLEMENTATION PROMPT