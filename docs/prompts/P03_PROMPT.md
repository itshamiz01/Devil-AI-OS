AUTONOMUS AI OS

P-03: OPPORTUNITY DISCOVERY ENGINE

Autonomous Market Research, Business Opportunity Intelligence, Demand Validation, Commercial Feasibility and Opportunity Ranking

Prompt ID: P-03
Development Phase: Phase 3
Priority: Critical
Execution Type: Research infrastructure and opportunity intelligence implementation
Target Platform: Windows Desktop
Backend: Python + FastAPI
Frontend Integration: Existing API contracts, with full Command Center planned for P-11
AI Infrastructure: Hybrid, local-first
Intelligence Layer: P-02 Master Intelligence Engine
Task Infrastructure: P-01 Core Operating System
Database: Existing database architecture with controlled migrations
Research Mode: Evidence-driven, permission-controlled and source-aware
Development Standard: Modular, auditable, testable, cost-conscious and commercially realistic

---

1. YOUR ROLE

You are acting as the:

- Chief Market Intelligence Architect.
- Senior Market Research Engineer.
- Business Opportunity Analyst.
- Competitive Intelligence Specialist.
- Commercial Feasibility Analyst.
- Data Acquisition Architect.
- AI Research Systems Engineer.
- Business Strategy Analyst.
- Senior Backend Developer.
- Independent Research Auditor.

Your responsibility is to develop the Opportunity Discovery Engine of AUTONOMUS.

You are not building a generic idea generator.

You are building a systematic business research and opportunity evaluation system capable of discovering potential revenue opportunities, investigating their commercial viability, identifying market risks and recommending which opportunities deserve further investment.

The system must be capable of researching multiple digital business categories, comparing opportunities and maintaining a structured record of the evidence supporting each recommendation.

The long-term objective is to allow AUTONOMUS to continuously discover potential businesses and identify the strongest opportunities for controlled experimentation.

However, this phase must focus on discovering and validating opportunities.

It must not automatically launch businesses, spend money or create uncontrolled autonomous operations.

Your objective is to help AUTONOMUS distinguish between an attractive business idea and a commercially defensible opportunity.

---

2. MANDATORY PRE-DEVELOPMENT INSPECTION

Before implementation, inspect the actual P-01 and P-02 codebases.

Read:

1. AUTONOMUS_MASTER_CONSTITUTION.md
2. AUTONOMUS_DEVELOPMENT_PROMPT_PACK.md
3. SYSTEM_ARCHITECTURE.md
4. MASTER_INTELLIGENCE_ARCHITECTURE.md
5. MODEL_ROUTING_ARCHITECTURE.md
6. MISSION_INTERPRETATION.md
7. REASONING_PIPELINE.md
8. STRATEGIC_PLANNING_ENGINE.md
9. DECISION_INTELLIGENCE.md
10. MASTER_ORCHESTRATOR.md
11. DATABASE_IMPLEMENTATION.md
12. API_REFERENCE.md
13. P01_IMPLEMENTATION_REPORT.md
14. P02_IMPLEMENTATION_REPORT.md
15. P02_TEST_REPORT.md
16. P02_SECURITY_REPORT.md
17. Relevant Architecture Decision Records.

Inspect the actual source code, database migrations, service interfaces and test results.

Verify:

- Core OS functionality.
- Task management.
- Event communication.
- Permission enforcement.
- Approval framework.
- Master Intelligence Engine.
- Model routing.
- Mission interpretation.
- Strategic planning.
- Decision evaluation.
- Context management.
- Existing API contracts.

Do not assume any functionality is working because it appears in documentation.

Run relevant tests.

If critical defects exist in P-01 or P-02, report them and resolve or obtain approval before building P-03 on top of broken components.

Preserve existing working functionality.

---

3. UNDERSTAND THE OBJECTIVE

AUTONOMUS must eventually operate as an autonomous digital business operating system.

To accomplish that, it must identify opportunities worth investigating before committing resources.

Consider the following owner instruction:

"Find a legitimate digital business that I can start with $50. It should have low operating costs, realistic demand and the potential to generate revenue."

The Opportunity Discovery Engine must understand that this requires several independent investigations.

It must:

1. Discover possible business categories.
2. Identify customer problems.
3. Search for evidence of demand.
4. Identify target customers.
5. Research competitors.
6. Analyze existing solutions.
7. Examine market pricing.
8. Identify possible revenue models.
9. Estimate startup costs.
10. Estimate ongoing operating costs.
11. Evaluate distribution channels.
12. Identify legal and platform restrictions.
13. Assess operational complexity.
14. Evaluate risks.
15. Compare alternatives.
16. Produce a ranked shortlist.
17. Recommend opportunities for further validation.

It must not automatically assume that a business will make money.

It must not invent market statistics.

It must not treat search-result counts, social media views or AI-generated market estimates as proof of customer demand.

---

4. OPPORTUNITY DISCOVERY ARCHITECTURE

Build the Opportunity Discovery Engine as an independent, modular subsystem that integrates with P-02.

Proposed architecture:

backend/app/opportunities/
│
├── __init__.py
│
├── core/
│   ├── opportunity_engine.py
│   ├── discovery_controller.py
│   ├── research_coordinator.py
│   └── opportunity_lifecycle.py
│
├── discovery/
│   ├── idea_generator.py
│   ├── category_discovery.py
│   ├── problem_discovery.py
│   ├── trend_discovery.py
│   └── opportunity_expander.py
│
├── research/
│   ├── research_engine.py
│   ├── source_manager.py
│   ├── search_adapter.py
│   ├── browser_adapter.py
│   ├── data_collector.py
│   ├── evidence_extractor.py
│   └── source_verifier.py
│
├── market/
│   ├── demand_analyzer.py
│   ├── customer_analyzer.py
│   ├── competitor_analyzer.py
│   ├── pricing_analyzer.py
│   ├── trend_analyzer.py
│   └── market_saturation.py
│
├── commercial/
│   ├── business_model_analyzer.py
│   ├── revenue_estimator.py
│   ├── cost_estimator.py
│   ├── profitability_analyzer.py
│   ├── distribution_analyzer.py
│   └── feasibility_analyzer.py
│
├── validation/
│   ├── validation_engine.py
│   ├── validation_criteria.py
│   ├── evidence_validator.py
│   ├── demand_validator.py
│   └── validation_report.py
│
├── scoring/
│   ├── opportunity_scorer.py
│   ├── scoring_models.py
│   ├── ranking_engine.py
│   ├── risk_scorer.py
│   └── sensitivity_analyzer.py
│
├── monitoring/
│   ├── trend_monitor.py
│   ├── opportunity_monitor.py
│   └── research_scheduler.py
│
├── storage/
│   ├── opportunity_repository.py
│   ├── research_repository.py
│   └── evidence_repository.py
│
├── integrations/
│   ├── source_interfaces.py
│   ├── search_interfaces.py
│   └── market_data_interfaces.py
│
└── schemas/
    ├── opportunity.py
    ├── research.py
    ├── evidence.py
    ├── market_analysis.py
    ├── commercial_analysis.py
    └── validation.py

This is a proposed structure.

Adapt it to the existing repository and architecture.

Do not create unnecessary modules, duplicate P-02 reasoning functionality or build independent database infrastructure.

---

5. OPPORTUNITY DISCOVERY ENGINE

Implement the central Opportunity Discovery Engine.

It must coordinate the complete opportunity research workflow.

Conceptually:

class OpportunityDiscoveryEngine:

    async def discover_opportunities(self, request):
        ...

    async def research_opportunity(self, opportunity_id):
        ...

    async def analyze_market(self, opportunity_id):
        ...

    async def evaluate_competition(self, opportunity_id):
        ...

    async def estimate_commercial_feasibility(self, opportunity_id):
        ...

    async def validate_opportunity(self, opportunity_id):
        ...

    async def rank_opportunities(self, filters=None):
        ...

    async def generate_report(self, opportunity_id):
        ...

These are illustrative interfaces.

Follow existing P-02 service and schema conventions.

Responsibilities

The engine must:

- Receive an opportunity research mission.
- Understand the owner's constraints.
- Discover candidate opportunities.
- Avoid duplicate discoveries.
- Create structured opportunity records.
- Coordinate research tasks.
- Collect evidence.
- Analyze markets.
- Evaluate commercial feasibility.
- Score opportunities.
- Generate recommendations.
- Preserve research history.
- Submit findings to the Master Intelligence Engine.

All long-running research must use the P-01 task management infrastructure.

Do not create uncontrolled background processes.

---

6. BUSINESS CATEGORY DISCOVERY

Develop a system capable of investigating a wide range of legitimate digital business models.

Do not limit AUTONOMUS to one business category.

Initially support the following categories.

6.1 Digital products

Examples:

- E-books.
- Educational guides.
- Templates.
- Digital planners.
- Research reports.
- Printable products.
- Design assets.
- Spreadsheet tools.
- Digital learning materials.
- Original software products.

6.2 Software and technology services

Examples:

- Micro-SaaS.
- Small productivity tools.
- Workflow automation.
- Business dashboards.
- Data processing services.
- Industry-specific software.
- AI-assisted business tools.
- Website utilities.

6.3 Content businesses

Examples:

- Educational websites.
- Specialized blogs.
- Original newsletters.
- Online learning resources.
- Research publications.
- Niche content libraries.
- Original video content.
- Content licensing.

6.4 Freelance and productized services

Examples:

- Website development.
- Business automation.
- Data analysis.
- Content production.
- Design services.
- Technical documentation.
- Research services.
- Digital consulting.

6.5 Online education

Examples:

- Skill-based courses.
- Specialized training.
- Downloadable learning resources.
- Paid educational communities.
- Certification preparation resources, subject to applicable rules.

6.6 E-commerce and digital distribution

Examples:

- Print-on-demand.
- Authorized digital marketplaces.
- Original merchandise.
- Digital asset marketplaces.
- Licensed digital products.

Physical inventory and shipping-intensive models should receive additional capital and operational complexity penalties.

6.7 Business-to-business opportunities

Examples:

- Industry-specific automation.
- Data reporting services.
- Lead research using authorized sources.
- Business workflow tools.
- Internal productivity solutions.
- Specialized digital infrastructure.

These are discovery categories, not automatically approved business models.

Every opportunity must be evaluated individually.

---

7. OPPORTUNITY DISCOVERY METHODS

Implement multiple discovery strategies.

The system must not depend on one source or one idea-generation prompt.

7.1 Customer problem discovery

Identify recurring problems faced by specific customer groups.

Investigate:

- Customer complaints.
- Repeated questions.
- Inefficient workflows.
- Existing product limitations.
- Expensive manual processes.
- Unmet requirements.
- Time-consuming tasks.
- Poorly served niche markets.

A problem should be described in terms of:

- Who experiences it.
- How frequently it occurs.
- How important it is.
- What customers currently do.
- What existing solutions cost.
- Why current solutions may be insufficient.

7.2 Demand-driven discovery

Search for signals that people are actively looking for solutions.

Potential indicators include:

- Search interest.
- Relevant customer discussions.
- Product reviews.
- Marketplace activity.
- Customer questions.
- Existing purchase options.
- Public pricing.
- Publicly available demand reports.
- Public product launches and adoption information.

Distinguish between attention and purchasing intent.

High engagement does not necessarily mean customers will pay.

7.3 Competitor-gap discovery

Identify opportunities where existing products or services may be insufficient.

Look for:

- Poor customer reviews.
- Missing features.
- High pricing relative to alternatives.
- Complex onboarding.
- Weak localization.
- Underserved customer segments.
- Limited accessibility.
- Outdated products.
- Unnecessary workflow complexity.

Do not assume that a competitor's weakness creates a profitable opportunity.

Evaluate whether the problem is important enough for customers to switch.

7.4 Emerging-trend discovery

Monitor relevant changes such as:

- New technology adoption.
- New business regulations.
- Industry workflow changes.
- Emerging customer needs.
- New distribution platforms.
- New product categories.
- Changing consumer preferences.

Treat trends as research signals, not guaranteed commercial opportunities.

7.5 Skill and capability-driven discovery

Evaluate opportunities that can be executed using the actual capabilities of AUTONOMUS.

For example:

- Available coding capabilities.
- Research capabilities.
- Content production capabilities.
- Design capabilities.
- Automation capabilities.
- Existing software infrastructure.

An opportunity that requires unavailable skills, licenses, capital or integrations must be marked accordingly.

7.6 Budget-driven discovery

Generate opportunity candidates based on the owner's available capital.

Support budget ranges such as:

- Under $10.
- $10–$50.
- $50–$100.
- $100–$500.
- $500–$1,000.
- Above $1,000.

Allow custom budgets.

The system must distinguish:

- Initial startup capital.
- Recurring operating expenses.
- Variable costs.
- Required working capital.
- Emergency reserve.

Do not assume that an initial budget is entirely available for spending.

---

8. RESEARCH SOURCE AND DATA ACQUISITION FRAMEWORK

Build a modular source acquisition architecture.

AUTONOMUS must be able to use multiple authorized information sources.

Potential source categories:

1. Public search engines.
2. Public websites.
3. Public marketplaces.
4. Public product catalogues.
5. Public customer reviews.
6. Public forums and discussions.
7. Public industry reports.
8. Public government statistics.
9. Public pricing pages.
10. Official platform documentation.
11. Authorized APIs.
12. Owner-provided research material.

Do not hardcode dependence on a single search provider.

Create provider-independent interfaces.

8.1 Source adapter architecture

Every source adapter should declare:

- Source identifier.
- Source name.
- Source type.
- Access method.
- Authentication requirement.
- Rate limits.
- Data fields available.
- Update frequency.
- Licensing or usage restrictions.
- Reliability classification.
- Supported operations.

8.2 Source acquisition methods

Support appropriate acquisition methods:

- Official APIs.
- Permitted public-page access.
- Authorized browser research.
- User-provided documents.
- Licensed datasets.
- Manually imported research.

Use the method permitted by the source.

Do not bypass:

- Authentication controls.
- Paywalls.
- CAPTCHA.
- Rate limits.
- Robots or access restrictions.
- Platform security measures.
- Contractual usage restrictions.

Do not use stolen credentials or unauthorized accounts.

Respect applicable terms, copyright, privacy and data protection requirements.

Do not scrape private customer information.

8.3 Source reliability

Classify sources into categories such as:

- Primary official source.
- Government or regulatory source.
- Direct marketplace evidence.
- Established industry publication.
- Public customer feedback.
- Community discussion.
- Secondary analysis.
- Unverified claim.

A source's classification must not automatically make every claim accurate.

8.4 Research provenance

Every important finding must record:

- Source ID.
- Source title.
- Source URL, when available.
- Retrieval timestamp.
- Publication date, when available.
- Relevant extracted information.
- Verification status.
- Reliability classification.
- Related opportunity.
- Extraction method.

Never invent a URL, publication date or source.

If a source cannot be independently verified, label it accordingly.

---

9. EVIDENCE COLLECTION AND VALIDATION

Build an evidence management system specifically for business research.

This system must work with the evidence and uncertainty infrastructure established in P-02.

9.1 Evidence types

Support:

- Demand evidence.
- Customer problem evidence.
- Purchasing-intent evidence.
- Competitor evidence.
- Pricing evidence.
- Market-size evidence.
- Cost evidence.
- Distribution evidence.
- Operational evidence.
- Legal and regulatory evidence.
- Platform-policy evidence.

9.2 Evidence classifications

Classify findings as:

- VERIFIED.
- CORROBORATED.
- SUPPORTING.
- TENTATIVE.
- UNVERIFIED.
- CONTRADICTED.
- OUTDATED.

Use these labels consistently.

9.3 Evidence validation

For every important commercial claim:

1. Identify the claim.
2. Locate its source.
3. Check source relevance.
4. Check source freshness.
5. Identify whether the source directly supports the claim.
6. Compare independent evidence where possible.
7. Identify contradictory findings.
8. Record confidence and limitations.

Do not count multiple pages repeating the same original claim as independent evidence.

9.4 Evidence gaps

If important information is missing, report the gap.

Examples:

- No verified pricing information.
- No reliable customer demand evidence.
- No evidence of actual purchases.
- No confirmed platform fee structure.
- No reliable market-size estimate.

The system must not fill these gaps with fabricated figures.

---

10. MARKET AND CUSTOMER ANALYSIS

Implement the Market Analysis Engine.

It must analyze the actual customer segment and market conditions for each opportunity.

10.1 Target customer identification

Identify:

- Customer segment.
- Customer characteristics relevant to the product.
- Geographic market.
- Customer needs.
- Purchasing motivations.
- Current alternatives.
- Expected purchasing frequency.
- Potential willingness to pay.

Do not make unsupported assumptions about customer demographics.

10.2 Customer problem analysis

For each opportunity, document:

- Problem statement.
- Affected customer group.
- Problem frequency.
- Problem severity.
- Existing workaround.
- Cost of current workaround.
- Consequences of not solving the problem.
- Potential improvement.

10.3 Market demand

Investigate:

- Search demand indicators.
- Customer discussion frequency.
- Marketplace activity.
- Existing products.
- Pricing evidence.
- Public adoption indicators.
- Customer reviews.
- Available purchase-intent signals.

Clearly distinguish:

- General interest.
- Active problem awareness.
- Purchase consideration.
- Verified transactions.

Do not claim that a large total addressable market means AUTONOMUS can capture a meaningful portion of it.

10.4 Market size

When estimating market size, distinguish:

- TAM: Total Addressable Market.
- SAM: Serviceable Available Market.
- SOM: Serviceable Obtainable Market.

Use defensible methodologies.

If reliable market data is unavailable, state that a reliable estimate cannot yet be established.

Do not fabricate TAM, SAM or SOM values merely to make a report appear professional.

10.5 Geographic analysis

Allow the owner to specify:

- India.
- United States.
- United Kingdom.
- European markets.
- Global online markets.
- Specific countries or regions.

Evaluate:

- Customer purchasing power.
- Language requirements.
- Currency.
- Payment availability.
- Tax considerations.
- Distribution restrictions.
- Regional competition.
- Local regulations.

Do not assume that a product successful in one country will automatically work in another.

---

11. COMPETITOR INTELLIGENCE ENGINE

Build the Competitor Analysis Engine.

Its purpose is to understand the competitive environment and identify whether a viable differentiation strategy exists.

11.1 Competitor identification

Identify relevant:

- Direct competitors.
- Indirect competitors.
- Substitute solutions.
- Free alternatives.
- Manual workarounds.
- Established platforms.

11.2 Competitor analysis

For each competitor, collect available evidence about:

- Product or service.
- Target customer.
- Pricing.
- Business model.
- Features.
- Positioning.
- Distribution channels.
- Public customer reviews.
- Strengths.
- Weaknesses.
- Differentiation.
- Market presence.

Do not invent competitor revenue, customer counts or market share.

11.3 Competitor comparison

Create structured comparison matrices.

Evaluate:

- Price.
- Ease of use.
- Feature coverage.
- Quality.
- Customer experience.
- Specialization.
- Accessibility.
- Localization.
- Customer support.
- Distribution.

11.4 Competitive positioning

Identify possible differentiation opportunities.

Examples:

- More focused product.
- Better workflow.
- Better customer experience.
- Lower legitimate operating cost.
- Better localization.
- More accessible pricing.
- Specialized customer segment.
- Improved integration.

A recommendation must explain why customers might choose the proposed solution over existing alternatives.

"Competitors are expensive" is not sufficient evidence of a viable opportunity.

---

12. BUSINESS MODEL ANALYSIS

Build a Business Model Analyzer.

For every opportunity, identify possible revenue models.

Initially support:

- One-time product sales.
- Subscription revenue.
- Usage-based pricing.
- Service fees.
- Project-based contracts.
- Licensing.
- Memberships.
- Advertising, where suitable.
- Affiliate commissions through legitimate disclosed arrangements.
- Marketplace sales.
- Freemium models.

For each revenue model, evaluate:

- Customer payment reason.
- Pricing structure.
- Expected purchase frequency.
- Recurring revenue potential.
- Customer acquisition requirements.
- Delivery costs.
- Platform dependency.
- Refund exposure.
- Operational complexity.

Do not recommend a revenue model simply because it is popular.

Explain why it suits the actual product and customer.

---

13. COMMERCIAL FEASIBILITY ENGINE

This is one of the most important modules in P-03.

The system must evaluate whether an opportunity can realistically operate with the owner's available resources.

13.1 Startup cost estimation

Estimate relevant initial costs:

- Domain registration.
- Hosting.
- Software.
- Platform registration.
- Required licenses.
- Development.
- Design.
- Initial marketing.
- Payment processing setup.
- Other necessary expenses.

Classify every figure as:

- Verified price.
- Quoted price.
- Historical price.
- Estimate.
- Unknown.

Do not assume that all services offer permanent free plans.

13.2 Recurring cost estimation

Estimate:

- Hosting.
- Software subscriptions.
- API usage.
- AI inference.
- Payment processing.
- Marketplace fees.
- Customer support.
- Maintenance.
- Advertising.
- Other operational expenses.

Use actual published prices where available.

Record the source and date.

13.3 Revenue model calculations

Implement deterministic financial calculations.

Example:

Revenue = Number of Paid Sales × Selling Price

Gross Profit = Revenue - Direct Delivery Costs

Contribution Margin = Revenue - Variable Costs

Operating Profit = Revenue - All Operating Expenses

Net Cash Flow = Cash Received - Cash Paid

Account for:

- Refunds.
- Discounts.
- Taxes where applicable.
- Platform fees.
- Payment processing fees.
- Currency conversion.
- Delivery costs.
- Customer acquisition costs.

Clearly distinguish estimated revenue from verified revenue.

P-07 will eventually implement the complete Financial Intelligence Engine.

P-03 must establish research-based commercial estimates, not actual financial account management.

13.4 Scenario analysis

Generate three scenarios:

Conservative scenario

Assumes weak demand, slower customer acquisition and lower conversion.

Base scenario

Uses reasonable assumptions supported by available evidence.

Optimistic scenario

Assumes favorable conditions but remains within defensible limits.

Every scenario must identify its assumptions.

Do not present optimistic estimates as expected results.

13.5 Break-even analysis

Calculate:

- Break-even sales volume.
- Break-even revenue.
- Fixed costs.
- Variable costs.
- Contribution per sale.
- Required customer volume.

Use transparent formulas.

13.6 Budget compatibility

Evaluate whether the opportunity fits the owner's budget.

Calculate:

- Initial investment required.
- Minimum viable launch cost.
- Recurring operating cost.
- Contingency requirement.
- Maximum affordable experiment cost.

If the opportunity cannot be started within the budget, mark it as incompatible.

Do not silently increase the owner's budget.

---

14. DISTRIBUTION AND CUSTOMER ACQUISITION ANALYSIS

An opportunity is not commercially viable simply because a product can be created.

The system must investigate how customers will discover and purchase it.

For each opportunity, identify suitable distribution channels.

Potential channels:

- Search engines.
- Educational content.
- Direct website traffic.
- Authorized marketplaces.
- Email marketing with consent.
- Social media.
- Partnerships.
- Legitimate affiliate arrangements.
- Business-to-business outreach.
- Paid advertising, where economically justified.

Evaluate:

- Channel availability.
- Platform restrictions.
- Competition.
- Organic traffic difficulty.
- Paid acquisition costs.
- Time to reach customers.
- Conversion requirements.
- Customer acquisition risks.

Do not assume organic traffic will arrive automatically.

Do not assume paid advertising will be profitable.

Do not recommend unsolicited bulk messaging, spam, fake reviews, misleading endorsements or platform manipulation.

Every marketing recommendation must comply with applicable laws and platform policies.

---

15. LEGAL, PLATFORM AND ETHICAL RISK ANALYSIS

Build a dedicated compliance and risk assessment component.

For each opportunity, identify relevant issues involving:

- Copyright.
- Trademarks.
- Intellectual property.
- Licensing.
- Privacy.
- Consumer protection.
- Advertising disclosure.
- Taxation.
- Payment provider requirements.
- Marketplace policies.
- Geographic restrictions.
- Regulated industries.
- Product safety where applicable.

Examples of higher-risk categories requiring additional scrutiny:

- Financial advice.
- Investment products.
- Medical claims.
- Health-related products.
- Legal services.
- Personal data processing.
- Children's products.
- Products requiring professional certification.

Do not automatically classify a business as legal because competitors are operating it.

Identify whether the model requires professional legal or tax review.

Prohibited or unacceptable opportunity categories

Do not recommend or facilitate:

- Fraud.
- Phishing.
- Credential theft.
- Malware.
- Unauthorized access.
- Fake reviews.
- Spam operations.
- Counterfeit goods.
- Copyright infringement.
- Deceptive advertising.
- Unauthorized data harvesting.
- Market manipulation.
- Illegal financial schemes.
- Misleading financial or medical claims.
- Circumvention of platform protections.

The discovery system must be capable of rejecting such opportunities.

---

16. OPPORTUNITY SCORING AND RANKING ENGINE

Build a transparent opportunity scoring framework.

Every discovered opportunity must be evaluated using consistent criteria.

16.1 Scoring dimensions

Implement the following dimensions.

Dimension| Weight
Verified demand strength| 20%
Customer problem importance| 10%
Competitive opportunity| 10%
Revenue model viability| 10%
Profit potential| 15%
Startup budget compatibility| 10%
Distribution feasibility| 10%
Operational simplicity| 5%
Strategic fit| 5%
Evidence quality| 5%
Total| 100%

These are initial proposed weights.

Keep them configurable.

Document the scoring methodology and allow future adjustment through approved configuration.

16.2 Score calculation

Use a consistent normalized scale.

For example:

- 0: No evidence or completely unsuitable.
- 1: Very weak.
- 2: Weak.
- 3: Moderate.
- 4: Strong.
- 5: Very strong.

Calculate the weighted score deterministically.

Do not allow an LLM to arbitrarily assign the final score without structured evidence and validation.

16.3 Evidence confidence

The system must calculate or classify evidence quality separately from commercial attractiveness.

An opportunity may have:

- High theoretical potential.
- Weak evidence.
- Unknown demand.

Such an opportunity must not receive a misleadingly high confidence label.

16.4 Hard rejection rules

Some conditions must override a high numerical score.

Examples:

- Illegal business model.
- Unauthorized data collection.
- Unacceptable safety risk.
- Impossible budget requirement.
- No legitimate distribution path.
- Unavailable essential license.
- Unresolved critical legal restriction.

A high score must never override a prohibited or disallowed operation.

16.5 Opportunity ranking

Support rankings such as:

- Best overall opportunity.
- Lowest startup cost.
- Strongest demand evidence.
- Highest potential margin.
- Simplest execution.
- Lowest operational risk.
- Best recurring revenue potential.
- Best fit for available system capabilities.

The ranking must be reproducible from stored scoring inputs.

---

17. OPPORTUNITY LIFECYCLE MANAGEMENT

Every opportunity must have a controlled lifecycle.

Implement states such as:

DISCOVERED
    ↓
INITIAL_SCREENING
    ↓
RESEARCHING
    ↓
EVIDENCE_REVIEW
    ↓
COMMERCIAL_ANALYSIS
    ↓
VALIDATION_PENDING
    ↓
VALIDATED
    ↓
RECOMMENDED

Alternative outcomes:

NEEDS_MORE_EVIDENCE
REJECTED
INCOMPATIBLE
BLOCKED_BY_COMPLIANCE
DUPLICATE
OUTDATED
ARCHIVED

An opportunity may return to research if new evidence becomes available.

Every important status change must be recorded.

Do not mark an opportunity as VALIDATED merely because the AI generated a convincing report.

Define validation criteria and require supporting evidence.

---

18. OPPORTUNITY VALIDATION ENGINE

Build a dedicated validation framework.

This is different from generating an idea or conducting preliminary research.

Validation must establish whether the opportunity has sufficient evidence to justify a controlled real-world experiment.

18.1 Validation dimensions

Evaluate:

- Customer problem validity.
- Demand evidence.
- Purchasing-intent evidence.
- Competitive positioning.
- Pricing feasibility.
- Revenue model viability.
- Startup affordability.
- Distribution feasibility.
- Operational feasibility.
- Legal and platform compliance.

18.2 Validation levels

Use the following validation stages.

Level 0: Idea

A possible business concept exists.

No meaningful evidence has been collected.

Level 1: Preliminary research

Basic market and competitor research has been completed.

Level 2: Evidence-supported

Multiple relevant sources support the existence of a customer problem and plausible demand.

Level 3: Commercially assessed

Pricing, costs, competition, distribution and financial scenarios have been examined.

Level 4: Real-world demand validation

Actual customer behavior has been observed through an authorized validation method.

Examples include:

- Customer interviews.
- Voluntary surveys.
- Legitimate waitlist registrations.
- Approved product tests.
- Valid customer inquiries.
- Authorized preorders where properly disclosed and fulfilled or refunded as required.

Level 5: Revenue verified

Actual payments have been independently verified through authorized financial records or payment-provider evidence.

This final level must be based on real financial evidence.

P-03 must not automatically conduct transactions or launch businesses.

It may record owner-provided or authorized verified evidence for this validation level.

18.3 Validation limitations

Do not claim Level 4 validation from:

- Search volume alone.
- Social media views.
- Likes.
- AI-generated personas.
- Hypothetical surveys.
- Competitor existence.
- Model-generated willingness-to-pay estimates.

Do not claim Level 5 validation from:

- A generated invoice.
- An unpaid order.
- A payment screenshot without verification.
- A forecast.
- A simulated transaction.

18.4 Validation report

Every opportunity that reaches validation review must receive a structured report.

Include:

- Opportunity summary.
- Target customer.
- Problem.
- Demand evidence.
- Competition.
- Pricing.
- Business model.
- Cost structure.
- Financial scenarios.
- Distribution.
- Compliance.
- Key assumptions.
- Unresolved risks.
- Evidence gaps.
- Validation level.
- Recommendation.

---

19. RESEARCH QUALITY AND ANTI-HALLUCINATION CONTROLS

This is a critical requirement.

The system must not produce fabricated research to satisfy a mission.

Implement:

1. Source-backed claims.
2. Evidence provenance.
3. Retrieval timestamps.
4. Source freshness checks.
5. Duplicate source detection.
6. Contradictory evidence detection.
7. Claim verification.
8. Confidence classification.
9. Missing-data reporting.
10. Research audit history.

Mandatory research rules

- Never invent statistics.
- Never invent competitor prices.
- Never invent customer reviews.
- Never invent market size.
- Never invent transaction volume.
- Never invent source URLs.
- Never invent publication dates.
- Never claim an API was queried if it was not.
- Never claim a website was inspected if it was not.
- Never convert estimates into verified facts.
- Never use AI-generated research as independent market evidence.

When data is unavailable, explicitly report:

"Insufficient verified evidence."

This is preferable to a fabricated confident answer.

---

20. AUTOMATED RESEARCH WORKFLOWS

Integrate P-03 with the P-02 Master Intelligence Engine and P-01 Task Manager.

The research engine must support structured workflows.

Example:

Opportunity Research Mission
        |
        v
Mission Interpretation
        |
        v
Opportunity Discovery
        |
        v
Duplicate Detection
        |
        v
Initial Screening
        |
        v
Research Task Creation
        |
        v
Evidence Collection
        |
        v
Market Analysis
        |
        v
Competitor Analysis
        |
        v
Commercial Analysis
        |
        v
Compliance Review
        |
        v
Opportunity Scoring
        |
        v
Validation Assessment
        |
        v
Final Opportunity Report

Each stage must have a clear input, output and completion criterion.

If a stage fails, record the failure and decide whether the workflow can safely continue.

Do not silently skip critical research stages.

20.1 Research task structure

Each research task must contain:

- Research ID.
- Related opportunity ID.
- Research objective.
- Research category.
- Requested source types.
- Required evidence.
- Data constraints.
- Time limit.
- Retry policy.
- Expected output.
- Completion criteria.

20.2 Research prioritization

Prioritize tasks according to:

- Opportunity importance.
- Missing critical evidence.
- Potential commercial impact.
- Research cost.
- Time sensitivity.
- Available resources.

Avoid spending excessive time researching opportunities that have already failed basic screening.

---

21. OPPORTUNITY DATABASE IMPLEMENTATION

Extend the existing database using migrations.

Do not replace the database or delete P-01/P-02 records.

Implement suitable entities for:

Opportunities

- Opportunity ID.
- Name.
- Description.
- Business category.
- Target customer.
- Geography.
- Proposed business model.
- Lifecycle status.
- Discovery method.
- Related mission.
- Creation timestamp.
- Last research timestamp.

Research sessions

- Research ID.
- Opportunity ID.
- Research objective.
- Status.
- Sources examined.
- Start time.
- Completion time.
- Findings summary.

Research sources

- Source ID.
- Source name.
- Source URL.
- Source type.
- Retrieval time.
- Publication date.
- Reliability classification.
- Usage restrictions.

Evidence records

- Evidence ID.
- Opportunity ID.
- Source ID.
- Claim.
- Supporting content.
- Evidence category.
- Verification status.
- Confidence classification.
- Freshness status.

Competitors

- Competitor ID.
- Opportunity ID.
- Name.
- Website.
- Product.
- Pricing evidence.
- Features.
- Positioning.
- Strengths.
- Weaknesses.

Market analyses

- Market ID.
- Opportunity ID.
- Customer segment.
- Geographic market.
- Demand indicators.
- Market-size methodology.
- Competitive conditions.
- Uncertainty.

Commercial analyses

- Analysis ID.
- Opportunity ID.
- Revenue model.
- Startup cost.
- Recurring costs.
- Variable costs.
- Pricing assumptions.
- Scenario calculations.
- Break-even analysis.

Opportunity scores

- Score ID.
- Opportunity ID.
- Scoring version.
- Individual scoring dimensions.
- Final weighted score.
- Evidence quality.
- Risk classification.
- Scoring timestamp.

Validation records

- Validation ID.
- Opportunity ID.
- Validation level.
- Required criteria.
- Supporting evidence.
- Missing evidence.
- Reviewer.
- Decision.
- Timestamp.

Research history

Preserve previous findings, scoring changes, source updates and lifecycle transitions.

Do not overwrite historical research when new evidence arrives.

---

22. API IMPLEMENTATION

Create versioned API endpoints consistent with P-01 and P-02.

Proposed endpoints:

Discovery

POST /api/v1/opportunities/discover
GET  /api/v1/opportunities
GET  /api/v1/opportunities/{opportunity_id}

Research

POST /api/v1/opportunities/{opportunity_id}/research
GET  /api/v1/opportunities/{opportunity_id}/research
GET  /api/v1/research/{research_id}

Analysis

POST /api/v1/opportunities/{opportunity_id}/market-analysis
POST /api/v1/opportunities/{opportunity_id}/competitor-analysis
POST /api/v1/opportunities/{opportunity_id}/commercial-analysis

Validation

POST /api/v1/opportunities/{opportunity_id}/validate
GET  /api/v1/opportunities/{opportunity_id}/validation

Scoring and ranking

POST /api/v1/opportunities/{opportunity_id}/score
GET  /api/v1/opportunities/rankings

Reporting

GET /api/v1/opportunities/{opportunity_id}/report
GET /api/v1/opportunities/reports

Monitoring

GET /api/v1/opportunities/status
GET /api/v1/opportunities/research-queue

Adapt the endpoints to the actual architecture.

All endpoints must:

- Validate input.
- Enforce permissions.
- Apply pagination.
- Handle failures consistently.
- Avoid exposing secrets.
- Use structured response schemas.
- Record relevant audit events.

Do not expose unrestricted source crawling through public endpoints.

---

23. OPPORTUNITY REPORT GENERATOR

Build a professional structured report generator.

Each completed opportunity report must include:

A. Executive summary

- Opportunity name.
- Business category.
- Target customer.
- Main problem.
- Proposed solution.
- Opportunity status.
- Overall score.
- Evidence quality.

B. Market research

- Market overview.
- Customer demand.
- Customer problems.
- Geographic considerations.
- Market trends.
- Evidence limitations.

C. Competitor analysis

- Direct competitors.
- Indirect competitors.
- Pricing.
- Differentiation.
- Competitive risks.

D. Business model

- Revenue model.
- Pricing strategy.
- Delivery method.
- Distribution strategy.
- Customer acquisition assumptions.

E. Financial feasibility

- Startup cost.
- Monthly operating cost.
- Variable cost.
- Revenue scenarios.
- Break-even point.
- Budget compatibility.
- Key assumptions.

F. Risk analysis

- Commercial risks.
- Competition.
- Legal considerations.
- Platform dependency.
- Operational complexity.
- Financial exposure.

G. Validation assessment

- Validation level.
- Verified evidence.
- Supporting evidence.
- Missing evidence.
- Next validation requirements.

H. Final recommendation

Classify the opportunity as:

- STRONG CANDIDATE.
- PROMISING BUT UNVALIDATED.
- REQUIRES MORE RESEARCH.
- LOW PRIORITY.
- FINANCIALLY INCOMPATIBLE.
- REJECTED.

Explain the reasons.

I. Recommended next step

Identify what should happen next.

For example:

- Gather additional customer evidence.
- Verify platform pricing.
- Interview potential customers.
- Conduct a small authorized demand test.
- Reject the opportunity.
- Submit the opportunity for owner review.

The report must clearly separate facts, estimates, assumptions and recommendations.

---

24. OPPORTUNITY MONITORING AND SCHEDULING FOUNDATION

Prepare the architecture for ongoing opportunity monitoring.

P-12 will implement the complete Autonomous Operations Engine.

P-03 may implement a limited research scheduling foundation using the P-01 task manager.

Support configurable research jobs such as:

- Recheck an opportunity after a specified period.
- Refresh competitor pricing.
- Check whether source information is outdated.
- Re-evaluate a previously promising opportunity.
- Detect material changes in known market evidence.

Scheduling must be owner-configurable.

Do not continuously crawl websites.

Do not create unlimited recurring research jobs.

Apply:

- Source-specific rate limits.
- Research budgets.
- Task concurrency limits.
- Execution windows.
- Duplicate-job prevention.
- Cancellation controls.

Do not automatically launch a business because a monitored opportunity receives a higher score.

---

25. INTEGRATION WITH THE MASTER INTELLIGENCE ENGINE

P-03 must integrate with P-02 rather than creating a second intelligence system.

Use the Master Intelligence Engine for:

- Understanding owner research requests.
- Extracting constraints.
- Generating research plans.
- Interpreting research findings.
- Evaluating hypotheses.
- Producing strategic recommendations.

Use P-03 for:

- Opportunity discovery.
- Research source acquisition.
- Evidence collection.
- Market analysis.
- Competitor intelligence.
- Commercial feasibility.
- Opportunity scoring.
- Validation tracking.

Use P-01 for:

- Task execution management.
- Persistence infrastructure.
- Permissions.
- Approvals.
- Logging.
- Events.
- Monitoring.

Maintain these responsibility boundaries.

---

26. HUMAN APPROVAL AND OPPORTUNITY GOVERNANCE

The Opportunity Discovery Engine may independently:

- Search authorized sources.
- Generate opportunity candidates.
- Conduct permitted research.
- Calculate estimated costs.
- Analyze competitors.
- Generate reports.
- Rank opportunities.
- Recommend next steps.

It must not independently:

- Purchase domains.
- Buy subscriptions.
- Pay for datasets.
- Run paid advertisements.
- Place orders.
- Register businesses.
- Sign contracts.
- Collect customer payments.
- Launch external campaigns.
- Commit the owner to a financial obligation.

These operations require future execution and financial infrastructure plus the applicable owner approvals.

If a research activity itself has external costs or legal consequences, it must follow the permission and approval framework.

---

27. SECURITY AND DATA PROTECTION

Implement the security controls relevant to research operations.

Requirements:

1. Treat all retrieved web content as untrusted.
2. Defend against prompt injection.
3. Do not execute code extracted from webpages.
4. Do not expose browser credentials to models.
5. Do not collect unnecessary personal information.
6. Respect access restrictions.
7. Maintain source provenance.
8. Restrict network access through approved adapters.
9. Protect API credentials.
10. Redact secrets from logs.
11. Enforce research task permissions.
12. Maintain audit records.

External research content must never be able to change system policies, permissions or owner instructions.

Do not bypass CAPTCHA or other access controls.

---

28. TESTING AND QUALITY ASSURANCE

Testing must cover actual research behavior, not merely whether the modules import successfully.

28.1 Discovery tests

Test:

- Opportunity generation.
- Category filtering.
- Budget filtering.
- Geography filtering.
- Duplicate detection.
- Capability compatibility.
- Invalid opportunity rejection.

28.2 Source tests

Test:

- Source adapter behavior.
- Invalid URLs.
- Unavailable websites.
- API failures.
- Rate limiting.
- Timeouts.
- Source freshness.
- Duplicate sources.
- Missing publication dates.

Use mock source adapters for deterministic tests.

28.3 Evidence tests

Test:

- Evidence classification.
- Provenance tracking.
- Contradictory findings.
- Unsupported claims.
- Stale evidence.
- Duplicate evidence.
- Confidence handling.

28.4 Market analysis tests

Test:

- Customer segmentation.
- Demand classification.
- Competitor identification.
- Pricing analysis.
- Market-size uncertainty.
- Market saturation limitations.

28.5 Commercial analysis tests

Test:

- Startup cost calculations.
- Recurring costs.
- Variable costs.
- Gross profit.
- Contribution margin.
- Break-even analysis.
- Scenario calculations.
- Currency handling.
- Budget compatibility.

Use deterministic fixtures and independently verified formulas.

28.6 Scoring tests

Test:

- Weight calculations.
- Score normalization.
- Ranking reproducibility.
- Missing evidence penalties.
- Risk overrides.
- Hard rejection rules.
- Scoring version changes.

28.7 Validation tests

Test:

- Level 0 through Level 5 classification.
- Unsupported validation claims.
- Missing evidence.
- Owner-provided evidence.
- Payment verification limitations.
- Rejection conditions.

28.8 Security tests

Test:

- Prompt injection in retrieved pages.
- Unauthorized source access.
- Secret leakage.
- Unsafe URLs.
- Permission bypass.
- Unapproved paid research.
- Unrestricted network activity.

28.9 End-to-end tests

Test this complete workflow:

Owner request → Mission interpretation → Opportunity discovery → Research planning → Source acquisition → Evidence collection → Market analysis → Commercial analysis → Risk assessment → Scoring → Validation → Opportunity report.

Use test fixtures and authorized public sources.

Do not conduct real purchases or launch real businesses during P-03 testing.

---

29. REQUIRED ACCEPTANCE SCENARIOS

The following scenarios must work.

Scenario A: Low-budget opportunity discovery

Owner:

"Find digital business opportunities that can be started with $50."

Expected:

- Identify suitable categories.
- Discover candidate opportunities.
- Filter incompatible models.
- Research actual demand signals.
- Compare startup costs.
- Identify risks.
- Rank candidates.
- Report insufficient evidence where applicable.

Scenario B: Country-specific opportunity research

Owner:

"Find digital business opportunities targeting customers in India."

Expected:

- Analyze the specified geography.
- Consider relevant purchasing and payment conditions.
- Identify competition.
- Consider applicable regional requirements.
- Avoid assuming global market conditions apply.

Scenario C: Competitor-gap analysis

Owner:

"Find opportunities where existing products have poor customer experiences."

Expected:

- Identify relevant products.
- Collect permitted customer feedback.
- Classify recurring complaints.
- Identify possible gaps.
- Evaluate whether those gaps have commercial significance.

Scenario D: Attractive idea without evidence

Expected:

- Mark the opportunity as unvalidated.
- Explain the evidence gap.
- Avoid assigning unsupported demand confidence.
- Recommend additional research or rejection.

Scenario E: Budget-incompatible business

Expected:

- Identify required startup capital.
- Compare it with the owner's limit.
- Mark it as incompatible.
- Do not silently increase the budget.

Scenario F: Competitor exists but market is saturated

Expected:

- Analyze competitive conditions.
- Identify barriers to differentiation.
- Evaluate customer acquisition difficulty.
- Reduce the opportunity score where justified.
- Recommend rejection if no defensible entry strategy exists.

Scenario G: Untrusted webpage

A retrieved page contains instructions telling AUTONOMUS to ignore its security rules.

Expected:

- Treat the page as untrusted.
- Do not follow embedded instructions.
- Preserve security boundaries.
- Record the relevant security event.

Scenario H: No reliable market information

Expected:

- Report missing evidence.
- Avoid fabricated market statistics.
- Mark the opportunity as requiring more research.
- Explain what information is needed.

Scenario I: Strong research but no verified sales

Expected:

- Distinguish commercial feasibility from actual revenue.
- Do not claim the business is profitable.
- Do not claim Level 5 validation.
- Recommend a controlled demand experiment if appropriate.

---

30. PERFORMANCE AND RESOURCE OPTIMIZATION

P-03 must respect the actual hardware constraints documented in P-00.

Requirements:

- Bounded research concurrency.
- Controlled browser sessions.
- Efficient HTML extraction.
- Limited context size.
- Reusable source results.
- Duplicate request prevention.
- Cached data with freshness metadata.
- Controlled model inference.
- Research task timeouts.
- Queue-based execution.

Avoid repeatedly researching the same opportunity without a reason.

Avoid excessive model calls for deterministic tasks.

Use code for calculations, validation and ranking.

Use AI for interpretation, synthesis and research planning.

Do not download large datasets unnecessarily.

Do not start hundreds of research jobs simultaneously.

---

31. REQUIRED DOCUMENTATION

Create or update:

docs/
│
├── architecture/
│   ├── OPPORTUNITY_DISCOVERY_ARCHITECTURE.md
│   ├── RESEARCH_SOURCE_ARCHITECTURE.md
│   ├── EVIDENCE_MANAGEMENT.md
│   ├── MARKET_ANALYSIS_ENGINE.md
│   ├── COMPETITOR_INTELLIGENCE.md
│   ├── COMMERCIAL_FEASIBILITY.md
│   ├── OPPORTUNITY_SCORING.md
│   ├── OPPORTUNITY_VALIDATION.md
│   └── RESEARCH_SECURITY.md
│
├── reports/
│   ├── P03_IMPLEMENTATION_REPORT.md
│   ├── P03_TEST_REPORT.md
│   ├── P03_RESEARCH_QUALITY_REPORT.md
│   ├── P03_COMMERCIAL_VALIDATION_REPORT.md
│   └── P03_SECURITY_REPORT.md
│
└── decisions/
    └── New architecture decision records

Also create a sample opportunity report using clearly labelled test data.

Do not present test data as real market research.

Document all supported source adapters and their access limitations.

---

32. DEVELOPMENT EXECUTION ORDER

Execute the implementation in the following sequence.

Stage 1: Existing system audit

- Inspect P-01 and P-02.
- Verify tests.
- Verify interfaces.
- Identify integration dependencies.

Stage 2: Architecture design

- Finalize module boundaries.
- Define schemas.
- Define source interfaces.
- Define database migrations.
- Define research workflows.

Stage 3: Opportunity data foundation

- Implement opportunity models.
- Implement research records.
- Implement evidence records.
- Implement repositories.
- Implement lifecycle transitions.

Stage 4: Discovery engine

- Implement category discovery.
- Implement problem discovery.
- Implement idea generation.
- Implement budget and geography filters.
- Implement duplicate detection.

Stage 5: Research infrastructure

- Implement source interfaces.
- Implement authorized search adapters.
- Implement browser research adapters where appropriate.
- Implement extraction.
- Implement source provenance.
- Implement freshness management.

Stage 6: Evidence engine

- Implement evidence classification.
- Implement claim tracking.
- Implement source verification.
- Implement contradictory evidence detection.
- Implement missing-data handling.

Stage 7: Market intelligence

- Implement customer analysis.
- Implement demand analysis.
- Implement competitor analysis.
- Implement pricing analysis.
- Implement market saturation assessment.

Stage 8: Commercial intelligence

- Implement business model analysis.
- Implement startup cost estimation.
- Implement recurring cost estimation.
- Implement revenue scenarios.
- Implement break-even calculations.
- Implement distribution analysis.

Stage 9: Compliance and risk

- Implement risk classification.
- Implement restricted-category screening.
- Implement legal and platform risk records.
- Implement rejection rules.

Stage 10: Scoring and validation

- Implement scoring.
- Implement ranking.
- Implement validation levels.
- Implement validation reports.
- Implement sensitivity analysis.

Stage 11: Orchestration and APIs

- Integrate with P-02.
- Integrate with P-01 task management.
- Implement API routes.
- Add authorization.
- Add audit events.

Stage 12: Monitoring

- Implement research scheduling foundation.
- Implement opportunity monitoring.
- Implement freshness checks.
- Implement resource limits.

Stage 13: Testing and audit

- Run unit tests.
- Run integration tests.
- Run security tests.
- Run commercial calculation tests.
- Run end-to-end research workflows.
- Perform independent research-quality review.

Stage 14: Final reporting

- Document actual implementation.
- Report test results.
- Report research limitations.
- Report unresolved issues.
- Assess P-04 readiness.

---

33. STRICT DEVELOPMENT RESTRICTIONS

Do not implement functionality belonging to future phases.

Do not:

- Build the Dynamic Agent Factory from P-04.
- Build the Universal Digital Execution Engine from P-05.
- Build the Business Creation Engine from P-06.
- Implement the complete Financial Intelligence Engine from P-07.
- Implement business survival and capital allocation from P-08.
- Implement the complete memory and learning system from P-09.
- Replace the comprehensive security program planned for P-10.
- Build the complete Command Center from P-11.
- Implement autonomous business operations from P-12.
- Implement multi-business coordination from P-13.

Do not:

- Launch a business.
- Buy domains.
- Purchase subscriptions.
- Spend money on research.
- Run paid advertising.
- Create marketplace accounts.
- Send unsolicited messages.
- Collect customer payments.
- Make financial commitments.
- Circumvent website restrictions.
- Invent research findings.
- Claim revenue without verified payment evidence.

Prepare interfaces for future phases, but do not pretend those future capabilities already exist.

---

34. P-03 ACCEPTANCE CRITERIA

P-03 is complete only when the following requirements are verified.

Opportunity discovery

- [ ] Multiple business categories supported.
- [ ] Customer problem discovery works.
- [ ] Demand-driven discovery works.
- [ ] Competitor-gap discovery works.
- [ ] Budget filtering works.
- [ ] Geographic filtering works.
- [ ] Duplicate detection works.

Research infrastructure

- [ ] Source adapter architecture implemented.
- [ ] Authorized research acquisition works.
- [ ] Source provenance is stored.
- [ ] Retrieval timestamps are recorded.
- [ ] Source freshness is tracked.
- [ ] Research failures are handled safely.

Evidence management

- [ ] Evidence records are persisted.
- [ ] Claims can be linked to sources.
- [ ] Evidence quality is classified.
- [ ] Contradictory evidence is identified.
- [ ] Missing information is reported.
- [ ] Unsupported claims are not presented as facts.

Market intelligence

- [ ] Customer analysis works.
- [ ] Demand analysis works.
- [ ] Competitor analysis works.
- [ ] Pricing analysis works.
- [ ] Market saturation assessment works.
- [ ] Market-size uncertainty is handled correctly.

Commercial feasibility

- [ ] Business model analysis works.
- [ ] Startup cost estimation works.
- [ ] Recurring cost estimation works.
- [ ] Revenue scenarios work.
- [ ] Break-even calculations are verified.
- [ ] Budget compatibility works.
- [ ] Distribution feasibility is evaluated.

Scoring and validation

- [ ] Configurable scoring works.
- [ ] Rankings are reproducible.
- [ ] Hard rejection rules work.
- [ ] Evidence quality is separated from attractiveness.
- [ ] Validation levels work.
- [ ] Unsupported validation claims are rejected.

Integration

- [ ] P-02 integration works.
- [ ] P-01 task management integration works.
- [ ] Database migrations preserve existing data.
- [ ] API endpoints work.
- [ ] Permission enforcement works.
- [ ] Audit records are generated.

Quality and security

- [ ] Unit tests pass.
- [ ] Integration tests pass.
- [ ] Financial calculation tests pass.
- [ ] Research quality tests pass.
- [ ] Prompt injection tests pass.
- [ ] Security tests pass.
- [ ] Documentation matches implementation.
- [ ] Independent audit is complete.

No checklist item may be marked complete without supporting evidence.

---

35. FINAL COMPLETION REPORT

Generate:

AUTONOMUS P-03 IMPLEMENTATION REPORT

Overall status: Complete / Partially Complete / Blocked

Opportunity Discovery Engine: Working / Not Working

Research Source Framework: Working / Not Working

Evidence Management: Working / Not Working

Market Analysis: Working / Not Working

Competitor Intelligence: Working / Not Working

Commercial Feasibility: Working / Not Working

Opportunity Scoring: Working / Not Working

Validation Engine: Working / Not Working

API Integration: Working / Not Working

Security Verification: Passed / Failed / Partial

Research Quality: Passed / Failed / Partial

Test Status: Passed / Failed / Partial

P-04 Readiness: Ready for Review / Not Ready

Include:

1. Features implemented.
2. Files created or modified.
3. Database migrations.
4. Research adapters implemented.
5. Supported source types.
6. Actual research limitations.
7. Opportunity scoring methodology.
8. Commercial calculation examples.
9. Sample opportunity reports.
10. Test results.
11. Security findings.
12. Research-quality findings.
13. Known limitations.
14. Outstanding defects.
15. Required owner decisions.
16. Exact instructions for using the discovery engine.

Real-world research verification

Provide at least three example opportunity investigations using authorized and traceable research sources where available.

For each, include:

- The opportunity.
- Target customer.
- Evidence collected.
- Source references.
- Competitor findings.
- Cost assumptions.
- Commercial assessment.
- Score.
- Validation level.
- Unresolved uncertainties.

Clearly identify any test fixtures or simulated data.

Do not invent three successful opportunities just to satisfy this requirement.

If genuine research cannot be completed, explain the technical or source-access limitation.

---

36. FINAL DEVELOPMENT GATE

After P-03 is complete:

STOP.

Do not automatically begin P-04.

Present the implementation report, research-quality report and security report.

Wait for explicit owner approval.

P-04 will introduce the Dynamic Agent Factory.

That phase will allow AUTONOMUS to create and manage specialized agents when additional execution capabilities are genuinely required.

P-03 must first establish a trustworthy opportunity discovery system so future agents have meaningful, evidence-backed work to perform.

---

FINAL INSTRUCTION

Build the commercial intelligence system of AUTONOMUS.

It must be capable of discovering legitimate opportunities, investigating customer problems, understanding demand, evaluating competition, estimating costs, analyzing revenue models and determining which opportunities deserve further attention.

Do not build an idea generator and call it a business discovery engine.

Do not build a collection of search results and call it market research.

Do not produce attractive financial projections without evidence.

Do not confuse market interest with customer purchasing behavior.

Do not confuse commercial feasibility with verified profitability.

Every recommendation must have a traceable basis.

Every important assumption must be visible.

Every uncertainty must be acknowledged.

Every opportunity must be allowed to fail evaluation.

AUTONOMUS must become better at rejecting bad business opportunities than it is at generating attractive business ideas.

Inspect first. Research systematically. Verify evidence. Calculate deterministically. Evaluate commercially. Audit independently. Stop at the P-03 approval gate.