AUTONOMUS P-06: BUSINESS CREATION ENGINE

Master Development Prompt | Version 1.0

Project: AUTONOMUS | Autonomous AI Business Operating System
Phase: P-06
Module: Business Creation Engine
Platform: Windows-first
Backend: Python + FastAPI
Frontend: React + TypeScript
AI Infrastructure: Hybrid, local-first, provider-independent
Primary Objective: Transform validated business opportunities into structured, buildable, testable, launch-ready digital businesses.

---

1. YOUR ROLE

Act as a principal business systems architect, senior software engineer, digital product strategist, startup operations architect, product development engineer, business automation specialist, and AI orchestration specialist.

Your responsibility is to implement P-06: Business Creation Engine inside the existing AUTONOMUS repository.

You are not building a simple website generator, landing-page generator, or AI business idea generator.

You are building a coordinated business creation infrastructure that can transform an approved business opportunity into an operational digital business.

The engine must be capable of:

1. Converting validated opportunities into structured business projects.
2. Defining target customers and customer problems.
3. Designing products and services.
4. Developing commercially viable business models.
5. Creating business identities and positioning.
6. Building product requirements and development plans.
7. Creating digital business assets.
8. Generating websites and landing pages.
9. Preparing digital products and services.
10. Establishing distribution channels.
11. Preparing customer acquisition systems.
12. Establishing customer support workflows.
13. Preparing operational procedures.
14. Preparing launch documentation.
15. Testing business readiness.
16. Coordinating specialized agents.
17. Managing approvals and business lifecycle transitions.
18. Delivering a complete, traceable business launch package.

The system must create real business infrastructure, not merely generate attractive documents.

A business must never be marked operational simply because its website or product files have been generated.

---

2. AUTONOMUS PROJECT CONTEXT

AUTONOMUS is a Windows-first Autonomous AI Business Operating System.

Its mission is to discover legitimate revenue opportunities, validate demand, build digital products and services, operate business workflows, acquire customers, deliver value, analyze actual financial outcomes, and improve business performance.

The development roadmap:

- P-00: Master Development Initialization
- P-01: Core Operating System
- P-02: Master Intelligence Engine
- P-03: Opportunity Discovery Engine
- P-04: Dynamic Agent Factory
- P-05: Universal Digital Execution Engine
- P-06: Business Creation Engine
- P-07: Financial Intelligence Engine
- P-08: Survival and Scaling Engine
- P-09: Memory and Continuous Learning
- P-10: Security and Governance
- P-11: Premium Command Center
- P-12: Autonomous Operations
- P-13: Multi-business Coordination
- P-14: Integration and System Audit
- P-15: Performance, Reliability and Production Readiness
- P-16: Autonomous AI Economy Expansion

P-06 must integrate with the earlier phases.

Required dependencies

P-01: Core Operating System

- Task management.
- Workflow infrastructure.
- Project and business identifiers.
- Database and configuration.
- Logging and system events.

P-02: Master Intelligence Engine

- Planning.
- Decision support.
- Business strategy coordination.
- Reasoning and evaluation interfaces.

P-03: Opportunity Discovery Engine

- Validated opportunity records.
- Market research.
- Customer problem evidence.
- Competitor research.
- Revenue model evaluation.
- Opportunity risk assessment.

P-04: Dynamic Agent Factory

- Agent registry.
- Agent templates.
- Agent assignment.
- Capability validation.
- Agent lifecycle management.
- Resource limits.

P-05: Universal Digital Execution Engine

- Filesystem operations.
- Controlled code execution.
- Browser automation.
- API adapters.
- Document processing.
- Workflow execution.
- Evidence collection.
- Human approval.
- Execution recovery.

Do not recreate these systems inside P-06.

Reuse the existing implementations and interfaces.

---

3. LOCKED ARCHITECTURAL DECISIONS

These decisions must remain unchanged.

AI infrastructure

- Hybrid architecture.
- Local AI by default.
- Optional cloud AI through provider adapters.
- No mandatory paid API.
- Shared model infrastructure.
- Provider-independent model routing.

Autonomy

- Controlled autonomy.
- Agents may create internal business assets within approved scopes.
- Sensitive external actions require approval.
- Agents cannot grant themselves permissions.
- Agents cannot change financial or security policies.
- Human owner retains ultimate authority.

Platform

- Windows-first desktop system.
- Future cloud and multi-machine compatibility.
- Modular backend.
- Local-first development.

Resource constraints

Previously identified target hardware:

- Intel Core i7-4712HQ.
- Approximately 16 GB RAM.
- NVIDIA Quadro K1100M 2 GB.

Design the business creation engine to work efficiently on this hardware.

Use shared model infrastructure and bounded agent concurrency.

Do not launch separate heavyweight LLM instances for each business or agent.

---

4. FIRST RULE: AUDIT BEFORE IMPLEMENTATION

Do not immediately begin generating business creation modules.

Inspect the actual repository.

Audit:

- P-01 project and task architecture.
- P-02 intelligence interfaces.
- P-03 opportunity records and validation levels.
- P-04 agent factory.
- P-05 execution engine and available adapters.
- Database schemas and migrations.
- Existing project management modules.
- File and workspace management.
- Browser and API integrations.
- Approval mechanisms.
- Business-related data structures.
- Model routing.
- Logging and monitoring.
- Frontend structure.
- Existing tests.
- Dependencies and version compatibility.

Create:

"docs/audits/P06_PRE_IMPLEMENTATION_AUDIT.md"

Include:

1. Existing architecture.
2. Existing business-related functionality.
3. Reusable modules.
4. Missing functionality.
5. Integration requirements.
6. Database changes required.
7. Execution adapter availability.
8. Security and approval requirements.
9. Resource constraints.
10. Compatibility risks.

Then create:

"docs/audits/P06_IMPLEMENTATION_PLAN.md"

Include:

- Proposed architecture.
- Business lifecycle.
- Business templates.
- Business model framework.
- Product creation architecture.
- Asset generation architecture.
- Website and distribution integration.
- Operational readiness.
- Approval gates.
- Database design.
- API design.
- Testing strategy.
- Migration and rollback strategy.

Do not create duplicate task, agent, workflow, approval, or execution systems.

---

5. CORE MISSION OF THE BUSINESS CREATION ENGINE

Build a system that can transform a validated business opportunity into a complete business project.

The basic process:

1. Select a validated opportunity.
2. Verify that it meets the business creation requirements.
3. Create a business project.
4. Develop its business blueprint.
5. Define the target customer.
6. Design the offer.
7. Select the business model.
8. Define product or service requirements.
9. Plan product development.
10. Create required digital assets.
11. Build and test the product or service.
12. Establish distribution infrastructure.
13. Prepare customer acquisition.
14. Prepare customer support.
15. Prepare business operations.
16. Conduct launch-readiness checks.
17. Obtain required owner approvals.
18. Produce a launch-ready business package.

Every stage must have traceable inputs, decisions, outputs, dependencies, and validation criteria.

The engine must support multiple business models and must not assume that every opportunity should become a SaaS application or website.

---

6. BUSINESS CREATION ELIGIBILITY GATE

Not every opportunity should enter business creation.

Before creating a business project, evaluate the opportunity.

Required checks:

- Opportunity exists in P-03.
- Opportunity has a valid identifier.
- Validation level meets configurable minimum requirements.
- Customer problem is sufficiently understood.
- Evidence is available.
- Target customer is identifiable.
- Revenue model is defined.
- Distribution route is plausible.
- Startup requirements are estimated.
- Major legal and platform risks are identified.
- Business creation is within available resources.
- Required owner approval has been obtained.

Eligibility decisions

Support:

- ELIGIBLE_FOR_CREATION.
- ELIGIBLE_WITH_CONDITIONS.
- REQUIRES_MORE_RESEARCH.
- REQUIRES_OWNER_APPROVAL.
- REJECTED.
- DEFERRED.

A high opportunity score must not automatically authorize business creation.

Hard rejection rules from P-03 must remain authoritative.

Opportunity traceability

Every business must retain a reference to its originating opportunity.

Store:

- Opportunity ID.
- Opportunity version.
- Validation level.
- Evidence references.
- Opportunity score.
- Risk classification.
- Approval reference.
- Creation decision.

If the opportunity changes materially during business creation, the engine must identify the affected assumptions and request reevaluation.

---

7. BUSINESS TYPE AND TEMPLATE SYSTEM

Build a reusable business template framework.

The system must support different types of digital businesses.

Initial business categories:

A. Software businesses

- SaaS products.
- Micro-SaaS.
- Web applications.
- Mobile applications.
- Browser-based tools.
- Developer tools.
- AI-assisted software products.

B. Digital product businesses

- E-books.
- Digital guides.
- Templates.
- Digital planners.
- Educational resources.
- Downloadable assets.
- Research products.
- Design resources.

C. Content businesses

- Blogs.
- Niche publishing.
- Newsletters.
- Video content businesses.
- Educational content platforms.
- Digital media libraries.

D. Digital service businesses

- Productized services.
- Consulting support platforms.
- Research services.
- Content production services.
- Software development services.
- Automation services.

E. Education businesses

- Online courses.
- Learning platforms.
- Digital training.
- Specialized knowledge products.
- Subscription learning services.

F. Digital distribution businesses

- Authorized digital marketplaces.
- E-commerce businesses.
- Digital storefronts.
- Subscription products.
- Licensed digital asset distribution.

G. B2B businesses

- Business software.
- Business intelligence products.
- Workflow solutions.
- Industry-specific digital services.
- Enterprise support tools.

Support additional categories through extensible templates.

Business templates

Each template must define:

- Template ID.
- Template name.
- Category.
- Description.
- Required business information.
- Required agents.
- Required capabilities.
- Product development stages.
- Asset requirements.
- Distribution requirements.
- Customer acquisition requirements.
- Operational requirements.
- Approval gates.
- Resource estimates.
- Launch-readiness criteria.

Templates must be versioned.

Changing a template must not silently modify existing businesses.

---

8. BUSINESS BLUEPRINT ENGINE

Every business must have a structured business blueprint before substantial production begins.

The blueprint is the central specification for the business.

8.1 Business identity

Generate and manage:

- Business name proposals.
- Brand positioning.
- Short description.
- Mission.
- Value proposition.
- Brand personality.
- Target market.
- Business category.
- Product/service identity.
- Brand language and communication guidelines.

Names must be checked for:

- Similar existing brands.
- Domain availability, where checked.
- Obvious trademark conflicts, where research is available.
- Platform restrictions.
- Misleading claims.
- Potential confusion with established businesses.

Do not claim that a name is legally available based only on a web search.

Trademark verification and legal registration require appropriate checks and, where necessary, professional advice.

8.2 Customer definition

Create structured customer profiles.

Include:

- Customer segment.
- Customer type.
- Demographics only where relevant and lawful.
- Customer problem.
- Existing alternatives.
- Purchasing motivation.
- Buying objections.
- Willingness-to-pay evidence.
- Preferred channels.
- Customer expectations.
- Customer journey.

Separate verified research from assumptions.

8.3 Value proposition

Define:

- Primary problem solved.
- Customer outcome.
- Differentiating value.
- Key features.
- Benefits.
- Limitations.
- Competitive alternatives.
- Reasons to choose the product.

Avoid generic AI-generated claims such as "best in the world" without evidence.

8.4 Business positioning

Generate:

- Market positioning.
- Competitive positioning.
- Target segment.
- Differentiation strategy.
- Brand promise.
- Product category.
- Initial market entry strategy.

8.5 Business assumptions

Maintain an explicit assumption register.

Each assumption should contain:

- Assumption ID.
- Description.
- Importance.
- Evidence reference.
- Confidence.
- Validation method.
- Validation status.
- Owner.
- Last reviewed timestamp.

The system must distinguish:

- VERIFIED.
- SUPPORTED.
- TENTATIVE.
- UNVERIFIED.
- CONTRADICTED.

Never present assumptions as established facts.

---

9. BUSINESS MODEL DESIGN ENGINE

The engine must identify how a business will deliver value and generate revenue.

Support:

- One-time purchases.
- Subscription.
- Freemium.
- Usage-based pricing.
- Licensing.
- Productized services.
- Consulting.
- Digital downloads.
- Advertising-supported models.
- Marketplace commissions.
- B2B contracts.
- Hybrid revenue models.

Business model components

For every business, define:

1. Target customer.
2. Customer problem.
3. Product or service.
4. Value proposition.
5. Revenue source.
6. Pricing structure.
7. Distribution channel.
8. Customer acquisition approach.
9. Delivery method.
10. Customer support approach.
11. Recurring operating costs.
12. Variable costs.
13. Major risks.
14. Dependencies.
15. Competitive alternatives.

Pricing research

Pricing recommendations must use available market evidence.

Include:

- Competitor pricing.
- Alternative product pricing.
- Customer willingness-to-pay evidence.
- Proposed pricing.
- Pricing assumptions.
- Confidence level.
- Testing strategy.

Do not invent competitor prices.

Do not assume that a lower price automatically creates a competitive advantage.

Financial integration boundary

P-06 may produce preliminary cost estimates and business assumptions.

However, it must not implement the full Financial Intelligence Engine.

That belongs to P-07.

Prepare structured financial inputs for P-07:

- Startup cost estimates.
- Recurring cost estimates.
- Variable cost assumptions.
- Proposed prices.
- Revenue model.
- Expected sales volume assumptions.
- Estimated gross margin assumptions.
- Financial risks.
- Funding requirements.

Clearly label all projections as estimates.

Never classify projected revenue as collected revenue.

Never authorize payments or spending through P-06.

---

10. PRODUCT AND SERVICE DESIGN ENGINE

A business needs a concrete offer.

Implement a product/service specification system.

10.1 Product definition

Each product must define:

- Product ID.
- Business ID.
- Product name.
- Product type.
- Description.
- Target customer.
- Problem solved.
- Core value.
- Delivery format.
- Pricing model.
- Feature list.
- Quality requirements.
- Dependencies.
- Product version.
- Status.

10.2 Product requirement document

Generate a structured PRD containing:

- Product vision.
- Problem statement.
- Target users.
- User needs.
- User journeys.
- Functional requirements.
- Nonfunctional requirements.
- Core features.
- Secondary features.
- Out-of-scope features.
- Technical requirements.
- Security requirements.
- Accessibility requirements.
- Acceptance criteria.
- Testing requirements.
- Release criteria.

10.3 MVP design

For every suitable product, define a minimum viable product.

The MVP must focus on validating the core customer value.

Classify features:

- MUST HAVE.
- SHOULD HAVE.
- COULD HAVE.
- NOT IN MVP.

Avoid unnecessary feature expansion.

Do not build a large application before validating its core value.

10.4 Product validation

Before launch, test:

- Core functionality.
- Usability.
- Reliability.
- Compatibility.
- Performance.
- Security.
- Accessibility.
- Data integrity.
- Error handling.
- User onboarding.
- Product documentation.

The engine must record test results.

---

11. PRODUCT CREATION AND DEVELOPMENT COORDINATION

P-06 must coordinate product creation using P-04 agents and P-05 execution tools.

It should not replace the code execution engine or build an independent agent framework.

Required agent responsibilities

Create or reuse suitable agents for:

- Product Strategy.
- Product Research.
- Requirements Analysis.
- UX Research.
- Technical Architecture.
- Software Development.
- Content Production.
- Design Planning.
- Quality Assurance.
- Documentation.
- Security Review.
- Release Readiness.

The factory must reuse existing agents where possible.

Only create specialized agents when workload and requirements justify them.

Development workflow

For software products:

1. Approve the product requirements.
2. Generate technical architecture.
3. Define project structure.
4. Create development tasks.
5. Assign approved coding agents.
6. Execute code changes through P-05.
7. Run tests.
8. Review implementation.
9. Resolve defects.
10. Perform security checks.
11. Build release artifacts.
12. Verify deployment readiness.

For content and digital products:

1. Approve the product concept.
2. Define the content structure.
3. Generate production tasks.
4. Assign relevant agents.
5. Produce content.
6. Review factual accuracy.
7. Review originality and rights.
8. Check formatting.
9. Run quality assurance.
10. Generate deliverables.
11. Verify the final files.

For service businesses:

1. Define the service package.
2. Define deliverables.
3. Establish delivery procedures.
4. Define quality standards.
5. Prepare customer onboarding.
6. Prepare service documentation.
7. Test the delivery workflow.

Existing project preservation

When building software products:

- Use an isolated project workspace.
- Maintain source control.
- Create a project baseline.
- Record changes.
- Run tests before release.
- Preserve existing working files.
- Never overwrite unrelated user projects.

---

12. BUSINESS BRAND AND ASSET CREATION ENGINE

Create a reusable system for producing business assets.

Assets may include:

- Business names.
- Brand descriptions.
- Logos or logo briefs.
- Brand guidelines.
- Color palettes.
- Typography specifications.
- Website copy.
- Product descriptions.
- Product screenshots.
- Digital product covers.
- E-book covers.
- Social media graphics.
- Marketing images.
- Documentation.
- Sales materials.
- Email templates.
- Customer onboarding documents.

Asset management

Every asset must have:

- Asset ID.
- Business ID.
- Asset type.
- Name.
- Version.
- File reference.
- Creation method.
- Creator agent.
- Approval status.
- Usage rights information.
- Creation timestamp.
- Last updated timestamp.

Store assets inside managed business workspaces.

Do not mix assets from different businesses.

Copyright and originality

The engine must:

- Avoid copying competitors' branding.
- Avoid unauthorized use of trademarks.
- Respect image and font licenses.
- Record third-party asset sources.
- Avoid copying copyrighted content.
- Maintain source references where relevant.
- Flag uncertain licensing.
- Require review for assets with unclear rights.

Do not claim generated content is automatically copyright-safe or guaranteed to be original.

---

13. WEBSITE AND DIGITAL PRESENCE CREATION

Many digital businesses require a website or online presence.

Build a reusable website creation workflow.

13.1 Website requirements

Support generation of:

- Business landing pages.
- Product websites.
- SaaS marketing websites.
- Digital storefront interfaces.
- Blog websites.
- Documentation websites.
- Portfolio websites.
- Service websites.

Do not force every business to have a website.

The business model should determine whether a website is necessary.

13.2 Website planning

Before implementation, define:

- Website purpose.
- Target audience.
- Required pages.
- Navigation.
- Content structure.
- Primary conversion action.
- Contact method.
- Product presentation.
- Legal and policy pages required for the business model.
- Accessibility requirements.
- SEO requirements.

13.3 Common page types

Where relevant:

- Home.
- About.
- Product.
- Pricing.
- Features.
- Contact.
- Blog.
- Documentation.
- FAQ.
- Privacy Policy.
- Terms and Conditions.
- Refund Policy.
- Cookie information.

Legal page content must be reviewed for the applicable jurisdiction and business model.

Do not generate false company addresses, registrations, licenses, certifications, or testimonials.

13.4 Website implementation

Use existing P-05 filesystem, code execution, browser, and deployment adapters.

Support configurable technology templates.

Do not hardcode a single frontend framework into the entire business creation engine.

Use project-specific technology decisions.

Website creation must include:

- Responsive design.
- Accessible structure.
- SEO metadata.
- Fast loading.
- Secure forms.
- Clear navigation.
- Error handling.
- Basic analytics integration where authorized.
- Functional testing.

13.5 Website verification

Before a website can be marked launch-ready, verify:

- Pages load.
- Links work.
- Forms behave correctly.
- Responsive layouts work.
- Content is present.
- Images load.
- No obvious placeholder text remains.
- Metadata is configured.
- Security checks pass.
- Required legal pages exist where applicable.
- Conversion actions are functional.

A locally generated website is not a publicly deployed website.

Track these states separately.

---

14. DISTRIBUTION CHANNEL PREPARATION

A product without distribution has no reliable route to customers.

The engine must identify and prepare suitable distribution channels.

Potential channels:

- Official product websites.
- Search engines.
- Authorized marketplaces.
- Digital product platforms.
- App marketplaces.
- Newsletter platforms.
- Content platforms.
- B2B outreach channels.
- Affiliate partnerships.
- Authorized e-commerce platforms.
- Professional communities.

Channel evaluation

For each channel, evaluate:

- Target customer relevance.
- Audience access.
- Fees.
- Platform restrictions.
- Eligibility.
- Competition.
- Distribution requirements.
- Content or product requirements.
- Operational complexity.
- Risks.
- Expected acquisition cost, where evidence exists.

Do not assume that every platform supports automated publishing.

Do not bypass platform rules.

Channel preparation states

Support:

- DISCOVERED.
- EVALUATING.
- SELECTED.
- ACCOUNT_SETUP_REQUIRED.
- ASSETS_PREPARED.
- READY_FOR_APPROVAL.
- APPROVED.
- CONNECTED.
- ACTIVE.
- PAUSED.
- REJECTED.

External account setup

The engine may prepare instructions and required information.

It must not:

- Create accounts using false identity information.
- Bypass account verification.
- Circumvent OTP or MFA.
- Store credentials in agent prompts.
- Misrepresent business registrations.
- Publish without required authorization.

Where human verification is necessary, pause and request owner action.

---

15. CUSTOMER ACQUISITION PREPARATION

Prepare customer acquisition systems based on the actual business model.

Potential acquisition methods:

- Organic search.
- Content marketing.
- Educational content.
- Email marketing with appropriate consent.
- Partnerships.
- Affiliate programs.
- Paid advertising, when explicitly authorized.
- Community participation.
- B2B outreach.
- Referral programs.
- Marketplace discovery.

Acquisition strategy

For each business, define:

- Primary customer acquisition channel.
- Secondary channels.
- Audience profile.
- Content requirements.
- Conversion path.
- Lead qualification.
- Customer onboarding.
- Measurement strategy.
- Estimated costs.
- Risks.
- Validation experiments.

Campaign planning

Create campaign assets:

- Campaign objective.
- Target audience.
- Key message.
- Offer.
- Content plan.
- Distribution plan.
- Conversion action.
- Measurement criteria.
- Budget estimate.
- Approval requirements.

Compliance

Do not implement:

- Spam campaigns.
- Fake reviews.
- Fake testimonials.
- Fake engagement.
- Misleading advertisements.
- Unauthorized scraping for outreach.
- Unsolicited bulk messaging.
- Deceptive lead generation.

External messages and paid campaigns require appropriate authorization.

---

16. CUSTOMER SUPPORT AND DELIVERY OPERATIONS

Every business must define how customers receive value after purchasing.

Create an operational delivery framework.

Required components

- Customer onboarding.
- Order or request intake.
- Product/service delivery.
- Customer communication.
- Support procedures.
- Complaint handling.
- Refund request handling.
- Quality assurance.
- Service recovery.
- Customer feedback collection.

Customer support preparation

Generate:

- FAQ.
- Support knowledge base.
- Common issue guides.
- Response templates.
- Escalation rules.
- Support hours.
- Refund and cancellation workflow.
- Data privacy procedures.

Do not make unsupported promises about response times, warranties, refunds, or service levels.

Human escalation

Escalate when:

- A customer reports a serious problem.
- Sensitive personal information is involved.
- A legal complaint is received.
- A refund or financial decision exceeds policy limits.
- The system cannot resolve the issue confidently.
- A customer requests a human.

P-06 prepares these workflows.

It does not implement the complete autonomous customer operations engine.

That will be expanded in P-12.

---

17. BUSINESS OPERATING PLAYBOOK

Every created business should receive an operating playbook.

The playbook must define how the business works.

Include:

1. Business overview.
2. Product or service description.
3. Target customer.
4. Value proposition.
5. Business model.
6. Pricing assumptions.
7. Product delivery procedure.
8. Distribution channels.
9. Customer acquisition process.
10. Customer support process.
11. Quality standards.
12. Technology stack.
13. Required external services.
14. Dependencies.
15. Operational risks.
16. Escalation procedures.
17. Compliance considerations.
18. Maintenance responsibilities.
19. Performance indicators.
20. Business owner responsibilities.

The playbook must be versioned and stored with the business project.

---

18. BUSINESS PROJECT AND WORKSPACE MANAGEMENT

Each business must have an isolated project identity and workspace.

Conceptual structure:

AUTONOMUS/
  businesses/
    business_001/
      blueprint/
      research/
      brand/
      product/
      website/
      content/
      marketing/
      operations/
      customer_support/
      documentation/
      releases/
      evidence/
      reports/

Adapt the structure to existing project and workspace conventions.

Workspace requirements

- Isolated business data.
- Scoped agent access.
- Versioned assets.
- Structured documents.
- Source control where applicable.
- Execution history.
- Approval references.
- Evidence storage.
- Backup and recovery support.

One business must not automatically access another business's workspace.

The owner must be able to export a business project.

---

19. BUSINESS LIFECYCLE MANAGEMENT

Implement a formal lifecycle state machine.

Required states:

- PROPOSED.
- ELIGIBILITY_REVIEW.
- APPROVAL_PENDING.
- BLUEPRINTING.
- BLUEPRINT_READY.
- PRODUCT_PLANNING.
- IN_DEVELOPMENT.
- INTERNAL_TESTING.
- DISTRIBUTION_PREPARATION.
- LAUNCH_REVIEW.
- READY_FOR_LAUNCH.
- LAUNCH_APPROVAL_PENDING.
- LAUNCHING.
- OPERATIONAL.
- PAUSED.
- BLOCKED.
- FAILED.
- ARCHIVED.

The lifecycle must distinguish between business creation and actual business operation.

Important distinctions

- BLUEPRINT_READY does not mean a product exists.
- PRODUCT_COMPLETE does not mean the product is tested.
- TESTED does not mean deployed.
- DEPLOYED does not mean publicly available.
- PUBLICLY_AVAILABLE does not mean customers exist.
- CUSTOMERS_EXIST does not mean revenue has been collected.
- REVENUE_RECORDED does not mean profit exists.

Financial truth will be governed by P-07.

State transitions

Define valid state transitions and required conditions.

Examples:

- PROPOSED → ELIGIBILITY_REVIEW.
- ELIGIBILITY_REVIEW → APPROVAL_PENDING.
- APPROVAL_PENDING → BLUEPRINTING.
- BLUEPRINTING → BLUEPRINT_READY.
- BLUEPRINT_READY → PRODUCT_PLANNING.
- PRODUCT_PLANNING → IN_DEVELOPMENT.
- IN_DEVELOPMENT → INTERNAL_TESTING.
- INTERNAL_TESTING → DISTRIBUTION_PREPARATION.
- DISTRIBUTION_PREPARATION → LAUNCH_REVIEW.
- LAUNCH_REVIEW → READY_FOR_LAUNCH.
- READY_FOR_LAUNCH → LAUNCH_APPROVAL_PENDING.
- LAUNCH_APPROVAL_PENDING → LAUNCHING.
- LAUNCHING → OPERATIONAL.

Additional failure, pause, recovery, and archive transitions must be defined.

Do not allow arbitrary state changes through an LLM-generated request.

State transitions must be validated by deterministic backend logic.

---

20. LAUNCH READINESS ENGINE

Build a launch-readiness evaluation system.

A business cannot enter READY_FOR_LAUNCH simply because all development tasks are marked complete.

Evaluate the following dimensions.

A. Market readiness

- Opportunity validation is sufficient.
- Target customer is defined.
- Customer problem is understood.
- Competitive research exists.
- Pricing assumptions are documented.

B. Product readiness

- Product exists.
- Core features work.
- Quality tests pass.
- Product limitations are documented.
- User experience is acceptable.
- Required documentation exists.

C. Brand readiness

- Business identity exists.
- Branding assets are prepared.
- Product descriptions are accurate.
- No obvious unresolved rights issue exists.

D. Distribution readiness

- Primary channel is selected.
- Platform requirements are reviewed.
- Required assets are ready.
- Account setup is complete where required.
- Publishing permissions are available.

E. Customer readiness

- Onboarding is prepared.
- Support procedures exist.
- Customer communication is prepared.
- Refund and complaint handling is documented where relevant.

F. Operational readiness

- Monitoring is configured where available.
- Backups exist where required.
- Recovery procedures exist.
- Dependencies are identified.
- Responsible agents and owners are assigned.

G. Legal and compliance readiness

- Applicable requirements have been identified.
- Required policies are prepared.
- Licensing questions are resolved or flagged.
- Platform terms are reviewed.
- Required registrations or approvals are identified.

Do not claim legal compliance has been independently certified.

H. Financial preparation

- Preliminary costs are documented.
- Pricing assumptions are documented.
- Financial risks are recorded.
- P-07 integration requirements are prepared.

Do not invent verified profitability.

Readiness result

Return:

- READY.
- READY_WITH_WARNINGS.
- NOT_READY.
- BLOCKED.
- OWNER_REVIEW_REQUIRED.

Provide a score only when the scoring methodology is defined.

Hard blockers must override the numerical score.

Every readiness decision must include evidence and outstanding requirements.

---

21. BUSINESS CREATION ORCHESTRATION

P-06 must coordinate existing agents through P-04.

It must not create a new unrestricted multi-agent framework.

Suggested agent workflow

Stage 1: Business strategy

- Strategy Agent.
- Market Research Agent.
- Customer Research Agent.

Stage 2: Product planning

- Product Strategy Agent.
- Requirements Agent.
- Technical Architecture Agent.

Stage 3: Production

- Coding Agent, where required.
- Content Production Agent.
- Design Agent.
- Documentation Agent.

Stage 4: Quality assurance

- QA Agent.
- Security Review Agent.
- Product Review Agent.

Stage 5: Go-to-market

- Distribution Research Agent.
- Marketing Strategy Agent.
- Customer Acquisition Planning Agent.

Stage 6: Operational preparation

- Operations Agent.
- Customer Support Preparation Agent.
- Compliance Review Agent.

The actual agents should be selected according to business type.

Do not assign unnecessary agents to every business.

Orchestration requirements

- Task dependencies.
- Agent availability.
- Resource limits.
- Quality gates.
- Human approval.
- Retry limits.
- Escalation.
- Result aggregation.
- Evidence tracking.

A single agent must not approve its own critical deliverables.

For important business decisions, use an independent reviewer or owner approval.

---

22. BUSINESS INTELLIGENCE AND EVIDENCE MANAGEMENT

Every business decision must be traceable.

Maintain a business evidence repository.

Evidence types:

- Market research.
- Customer research.
- Competitor analysis.
- Pricing evidence.
- Product testing.
- Security testing.
- Website verification.
- Platform eligibility.
- Legal and licensing research.
- Distribution research.
- Customer feedback.
- Approval records.

Every evidence item should include:

- Evidence ID.
- Business ID.
- Source.
- Evidence type.
- Source reference.
- Date collected.
- Date verified.
- Reliability classification.
- Associated assumption.
- Associated decision.
- Expiration or freshness status.
- Content hash where appropriate.

Preserve source provenance.

Do not present LLM-generated reasoning as independent market evidence.

Flag outdated research.

---

23. BUSINESS CREATION DATABASE DESIGN

Inspect the existing database before creating tables.

Reuse existing project, task, agent, approval, and workspace records.

The following entities are logical requirements.

businesses

- id
- name
- slug
- description
- category
- business_model
- lifecycle_status
- originating_opportunity_id
- opportunity_version
- owner_id
- template_id
- created_at
- updated_at
- archived_at

business_templates

- id
- name
- category
- description
- version
- configuration_json
- status
- created_at

business_blueprints

- id
- business_id
- version
- blueprint_json
- approval_status
- created_at
- updated_at

business_assumptions

- id
- business_id
- description
- importance
- evidence_reference
- confidence
- validation_status
- created_at
- updated_at

business_products

- id
- business_id
- name
- product_type
- description
- version
- status
- specification_json
- created_at
- updated_at

product_requirements

- id
- product_id
- requirement_type
- description
- priority
- acceptance_criteria
- status

business_assets

- id
- business_id
- asset_type
- name
- version
- file_reference
- approval_status
- usage_rights_status
- created_at

business_channels

- id
- business_id
- channel_name
- channel_type
- evaluation_status
- connection_status
- requirements_json
- created_at

business_campaigns

- id
- business_id
- campaign_name
- objective
- audience
- channel
- budget_estimate
- approval_status
- status
- created_at

business_playbooks

- id
- business_id
- version
- playbook_json
- status
- created_at

business_readiness_reviews

- id
- business_id
- review_version
- readiness_status
- review_data
- blockers
- warnings
- evidence_references
- reviewed_at

business_lifecycle_events

- id
- business_id
- previous_status
- new_status
- reason
- actor_type
- actor_id
- approval_reference
- created_at

business_evidence

- id
- business_id
- evidence_type
- source_reference
- reliability
- verification_status
- content_hash
- collected_at
- verified_at

business_approvals

Only create this if the existing approval architecture cannot support business-related approval references.

Prefer reusing the central approval service.

Use proper foreign keys, indexes, constraints, migration support, and transaction boundaries.

Preserve historical records.

Do not duplicate information unnecessarily across multiple tables.

---

24. BACKEND MODULE STRUCTURE

Follow the existing repository conventions.

If needed, use a modular structure similar to:

backend/
  business_creation/
    core/
    eligibility/
    registry/
    templates/
    blueprint/
    strategy/
    business_models/
    products/
    requirements/
    asset_management/
    website_creation/
    distribution/
    acquisition/
    customer_support/
    operations/
    orchestration/
    lifecycle/
    readiness/
    evidence/
    approvals/
    financial_interface/
    schemas/
    services/
    repositories/
    tests/

Potential services:

- BusinessEligibilityService
- BusinessRegistryService
- BusinessTemplateService
- BusinessBlueprintService
- CustomerDefinitionService
- ValuePropositionService
- BusinessModelService
- ProductSpecificationService
- ProductPlanningService
- BusinessAssetService
- WebsitePlanningService
- DistributionStrategyService
- CustomerAcquisitionPlanner
- CustomerSupportPreparationService
- BusinessOperationsService
- BusinessOrchestrationService
- BusinessLifecycleService
- LaunchReadinessService
- BusinessEvidenceService
- BusinessApprovalService
- FinancialIntegrationAdapter

Keep the module modular.

Do not put all business creation functionality into one large service.

---

25. API REQUIREMENTS

Implement endpoints consistent with existing FastAPI conventions.

Adapt the paths where equivalent endpoints already exist.

Business registry

- "GET /api/businesses"
- "GET /api/businesses/{business_id}"
- "POST /api/businesses"
- "PATCH /api/businesses/{business_id}"
- "POST /api/businesses/{business_id}/pause"
- "POST /api/businesses/{business_id}/archive"

Eligibility

- "POST /api/businesses/eligibility/evaluate"
- "GET /api/businesses/{business_id}/eligibility"

Templates

- "GET /api/business-templates"
- "GET /api/business-templates/{template_id}"
- "POST /api/business-templates"
- "POST /api/business-templates/{template_id}/clone"
- "POST /api/business-templates/{template_id}/validate"

Blueprint

- "POST /api/businesses/{business_id}/blueprint/generate"
- "GET /api/businesses/{business_id}/blueprint"
- "PATCH /api/businesses/{business_id}/blueprint"
- "POST /api/businesses/{business_id}/blueprint/validate"
- "POST /api/businesses/{business_id}/blueprint/approve"

Products

- "GET /api/businesses/{business_id}/products"
- "POST /api/businesses/{business_id}/products"
- "GET /api/business-products/{product_id}"
- "PATCH /api/business-products/{product_id}"
- "POST /api/business-products/{product_id}/requirements"
- "POST /api/business-products/{product_id}/development-plan"
- "POST /api/business-products/{product_id}/quality-review"

Assets

- "GET /api/businesses/{business_id}/assets"
- "POST /api/businesses/{business_id}/assets"
- "GET /api/business-assets/{asset_id}"
- "POST /api/business-assets/{asset_id}/approve"

Distribution

- "GET /api/businesses/{business_id}/channels"
- "POST /api/businesses/{business_id}/channels/evaluate"
- "POST /api/businesses/{business_id}/channels"
- "POST /api/businesses/{business_id}/channels/{channel_id}/prepare"

Operations

- "GET /api/businesses/{business_id}/playbook"
- "POST /api/businesses/{business_id}/playbook/generate"
- "PATCH /api/businesses/{business_id}/playbook"

Readiness

- "POST /api/businesses/{business_id}/readiness/evaluate"
- "GET /api/businesses/{business_id}/readiness"
- "GET /api/businesses/{business_id}/blockers"

Lifecycle

- "GET /api/businesses/{business_id}/lifecycle"
- "POST /api/businesses/{business_id}/lifecycle/transition"

Evidence

- "GET /api/businesses/{business_id}/evidence"
- "POST /api/businesses/{business_id}/evidence"

Orchestration

- "POST /api/businesses/{business_id}/creation/run"
- "GET /api/businesses/{business_id}/creation/status"
- "POST /api/businesses/{business_id}/creation/pause"
- "POST /api/businesses/{business_id}/creation/resume"
- "POST /api/businesses/{business_id}/creation/cancel"

Administration

- "GET /api/business-creation/status"
- "GET /api/business-creation/resources"

All endpoints must:

- Validate input.
- Enforce authorization.
- Apply business-level data isolation.
- Use pagination.
- Record important state changes.
- Avoid exposing secrets.
- Support idempotency for creation operations.
- Use structured error responses.

---

26. FRONTEND INTEGRATION

P-06 is primarily a business creation backend phase.

Do not build the full P-11 Command Center.

Extend existing frontend screens where necessary to provide practical visibility and control.

Business overview

Show:

- Total businesses.
- Businesses being created.
- Businesses in development.
- Businesses under testing.
- Businesses awaiting approval.
- Businesses ready for launch.
- Operational businesses.
- Paused businesses.
- Blocked businesses.

Business workspace

Provide sections for:

- Overview.
- Blueprint.
- Market research.
- Products.
- Assets.
- Website.
- Distribution.
- Customer acquisition.
- Operations.
- Evidence.
- Approvals.
- Lifecycle history.

Business creation progress

Display:

- Current creation stage.
- Completed stages.
- Pending tasks.
- Assigned agents.
- Failed tasks.
- Approval requirements.
- Resource warnings.
- Launch blockers.

Launch readiness screen

Display:

- Readiness result.
- Completed checks.
- Missing requirements.
- Warnings.
- Evidence references.
- Required owner decisions.

Every displayed value must come from real backend data.

Do not use decorative fake progress percentages.

---

27. INTEGRATION WITH P-07 FINANCIAL INTELLIGENCE

P-06 must prepare a clean financial integration interface.

Do not implement the full P-07 financial engine.

Prepare business financial inputs including:

- Initial cost estimates.
- Fixed cost assumptions.
- Variable cost assumptions.
- Proposed product prices.
- Revenue model.
- Estimated customer volume.
- Distribution fees.
- Platform fees.
- Infrastructure costs.
- Expected refund exposure.
- Funding requirements.

Every financial value must have:

- Amount or range.
- Currency.
- Source.
- Estimate or verified classification.
- Confidence.
- Date.
- Assumptions.

Use deterministic calculations where applicable.

Do not use LLM-generated arithmetic as the source of financial truth.

Do not authorize payments.

Do not connect wallets or execute transactions.

P-07 will own financial accounting, reconciliation, profit calculation, cash management, and financial governance.

---

28. SECURITY AND GOVERNANCE

The Business Creation Engine will create assets and interact with external platforms.

Security must be enforced from the beginning.

28.1 Business isolation

A business must not access another business's data without explicit authorization.

Validate business IDs server-side.

Do not rely on frontend filtering.

28.2 Agent permissions

Agents may:

- Generate internal business blueprints.
- Prepare product specifications.
- Create approved local assets.
- Build approved project files.
- Perform authorized research.
- Prepare distribution materials.

Agents may not automatically:

- Register legal entities.
- Sign contracts.
- Spend money.
- Purchase domains.
- Buy advertising.
- Publish publicly.
- Create financial accounts.
- Agree to legal terms.
- Submit tax information.
- Make legal or financial representations on behalf of the owner.

These actions require explicit authorization and, where applicable, human verification.

28.3 Business data privacy

Protect:

- Customer information.
- Business credentials.
- Proprietary research.
- Internal product specifications.
- Financial assumptions.
- External account information.

Do not put secrets in generated business documents.

28.4 Intellectual property

Record relevant sources and licensing information.

Flag assets with uncertain rights.

Do not claim ownership or exclusivity without a verified legal basis.

28.5 External content security

Treat all external documents, websites, and API responses as untrusted.

Prompt injection cannot authorize business creation actions, external publication, or permission changes.

28.6 Approval integrity

Approval must be:

- Explicit.
- Authenticated.
- Scoped.
- Time-bounded where appropriate.
- Traceable.
- Revocable before execution where possible.

An agent cannot approve its own critical business launch actions.

---

29. TESTING REQUIREMENTS

Build comprehensive automated tests.

Do not mark P-06 complete merely because the application starts or produces a business blueprint.

29.1 Unit tests

Test:

- Business eligibility.
- Opportunity linking.
- Business creation.
- Template selection.
- Blueprint generation schemas.
- Assumption tracking.
- Customer profile validation.
- Business model validation.
- Product requirements.
- Asset metadata.
- Distribution evaluation.
- Lifecycle transitions.
- Readiness evaluation.
- Approval enforcement.
- Business workspace isolation.
- Financial interface validation.

29.2 Integration tests

Test:

- P-01 project and task integration.
- P-02 strategy integration.
- P-03 opportunity integration.
- P-04 agent orchestration.
- P-05 execution adapters.
- Database migrations.
- Workspace creation.
- Asset generation.
- Product development workflow.
- Approval workflow.
- Evidence collection.
- P-07 financial input interface.

Use mocked model providers and external services where appropriate.

Do not require paid APIs.

29.3 Security tests

Verify:

1. A rejected opportunity cannot enter business creation.
2. An unauthorized agent cannot create a business.
3. One business cannot access another business's workspace.
4. An agent cannot approve its own launch.
5. An agent cannot authorize spending.
6. An agent cannot publish externally without approval.
7. Secrets do not appear in business assets.
8. External content cannot override system policies.
9. An unapproved asset cannot enter a public launch workflow.
10. A business cannot enter OPERATIONAL without required launch checks.
11. A business cannot claim verified revenue through P-06.
12. A user cannot access a business without authorization.
13. Invalid lifecycle transitions are rejected.
14. An expired approval cannot authorize a new action.
15. Unverified legal or trademark claims are not represented as verified.

29.4 Acceptance scenarios

Scenario A: Create a digital product business

Input: A validated opportunity for a digital educational product.

Expected:

- Eligibility is evaluated.
- Business project is created.
- Target customers are defined.
- Business model is prepared.
- Product specification is generated.
- Production tasks are assigned.
- Product assets are created.
- Quality checks are recorded.
- Distribution channels are evaluated.
- Launch-readiness report is generated.

Scenario B: Create a SaaS business

Input: A validated opportunity for a niche software tool.

Expected:

- SaaS template is selected.
- Product requirements are generated.
- MVP scope is defined.
- Technical architecture is prepared.
- Coding agents receive authorized tasks.
- P-05 executes approved development tasks.
- Product tests are recorded.
- Website and onboarding requirements are prepared.
- Readiness checks are performed.

Scenario C: Create a content business

Input: A validated opportunity for a niche content publication.

Expected:

- Content business template is selected.
- Audience and positioning are defined.
- Editorial plan is generated.
- Brand assets are prepared.
- Publishing infrastructure requirements are defined.
- Distribution channels are evaluated.
- Support and operating procedures are prepared.

Scenario D: Insufficient opportunity evidence

Input: An opportunity with weak or contradictory demand evidence.

Expected:

- Business creation is blocked or returned for additional research.
- No unnecessary business infrastructure is created.
- Reasons are recorded.

Scenario E: External publishing request

Input: A business agent requests public publishing.

Expected:

- Publishing action is classified.
- Permission is validated.
- Approval is requested.
- No external publication occurs before authorization.
- Outcome is verified after execution.

Scenario F: Invalid business readiness

Input: A product with missing quality tests and incomplete customer support.

Expected:

- Readiness result is NOT_READY.
- Missing requirements are listed.
- Business cannot transition to READY_FOR_LAUNCH.

Scenario G: Business workspace isolation

Input: An agent belonging to Business A requests Business B files.

Expected:

- Access is rejected.
- Security event is recorded.

Scenario H: Financial integration

Input: A business blueprint contains cost and pricing assumptions.

Expected:

- Financial inputs are structured.
- Estimate classifications are preserved.
- Data is made available to the P-07 interface.
- No actual revenue or profit is invented.

Scenario I: Business creation interruption

Input: The application stops during product development.

Expected:

- Business lifecycle state persists.
- Completed tasks remain recorded.
- Safe tasks can resume.
- Duplicate assets and external actions are prevented.
- Unsafe recovery requires review.

Scenario J: Launch approval

Input: A business passes all automated readiness checks.

Expected:

- Business enters READY_FOR_LAUNCH.
- Owner approval is requested.
- No public launch occurs until approval is granted.
- The final launch action is verified.

---

30. PERFORMANCE AND RESOURCE MANAGEMENT

The engine must operate efficiently on the target Windows machine.

Implement:

- Shared model inference.
- Bounded agent concurrency.
- Reusable execution adapters.
- Background task processing.
- Efficient asset storage.
- Incremental file generation.
- Database indexing.
- Lazy loading.
- Caching of reusable research where appropriate.
- Controlled image processing.
- Limited parallel development tasks.

Avoid:

- Creating all possible agents for every business.
- Generating unnecessary assets.
- Building features outside the MVP scope.
- Repeating identical research.
- Running multiple heavyweight models simultaneously.
- Unbounded website builds.
- Excessive screenshot capture.
- Keeping unnecessary browser sessions alive.

When resource pressure occurs:

1. Pause nonessential tasks.
2. Queue lower-priority work.
3. Preserve active business state.
4. Notify the owner.
5. Resume only when resource conditions permit.

---

31. DOCUMENTATION REQUIREMENTS

Create or update:

- "docs/architecture/P06_BUSINESS_CREATION_ENGINE.md"
- "docs/architecture/BUSINESS_BLUEPRINT_ARCHITECTURE.md"
- "docs/architecture/BUSINESS_MODEL_FRAMEWORK.md"
- "docs/architecture/PRODUCT_CREATION_WORKFLOW.md"
- "docs/architecture/BUSINESS_ASSET_MANAGEMENT.md"
- "docs/architecture/BUSINESS_LIFECYCLE.md"
- "docs/architecture/LAUNCH_READINESS_ENGINE.md"
- "docs/security/BUSINESS_DATA_ISOLATION.md"
- "docs/operations/BUSINESS_CREATION_OPERATIONS.md"
- "docs/operations/BUSINESS_WORKSPACE_GUIDE.md"
- "docs/testing/P06_TEST_REPORT.md"
- "docs/audits/P06_IMPLEMENTATION_REPORT.md"

Document actual functionality.

Clearly identify:

- Implemented.
- Partially implemented.
- Planned.
- Disabled.
- Requires external integration.
- Requires owner approval.

Include practical Windows setup instructions.

---

32. IMPLEMENTATION ORDER

Execute P-06 in controlled stages.

Stage 1: Repository audit

- Inspect P-01 through P-05.
- Identify reusable infrastructure.
- Document gaps.
- Prepare implementation plan.

Stage 2: Business registry

- Implement business identity.
- Connect originating opportunities.
- Create workspace integration.
- Implement business lifecycle.

Stage 3: Eligibility and templates

- Build eligibility checks.
- Implement business templates.
- Add template versioning.
- Add approval gates.

Stage 4: Business blueprint

- Implement customer definition.
- Implement value proposition.
- Add business model design.
- Add assumption register.
- Add evidence references.

Stage 5: Product and service design

- Implement product registry.
- Add PRD generation.
- Add MVP scope.
- Add development plans.
- Integrate agent assignments.

Stage 6: Asset creation

- Implement asset registry.
- Add brand and content asset management.
- Add usage rights metadata.
- Integrate approved execution tools.

Stage 7: Website and distribution preparation

- Implement website planning.
- Add website creation workflows where supported.
- Add channel evaluation.
- Add publishing preparation.
- Add approval integration.

Stage 8: Customer and operations preparation

- Add customer acquisition plans.
- Generate customer support materials.
- Generate business operating playbooks.
- Add delivery procedures.

Stage 9: Launch readiness

- Implement readiness checks.
- Add blockers and warnings.
- Add evidence-based evaluation.
- Add owner approval.

Stage 10: Financial integration interface

- Prepare structured business cost and revenue assumptions.
- Connect only to approved P-07 interfaces.
- Do not build the financial engine.

Stage 11: Frontend integration

- Extend existing business screens.
- Add progress and lifecycle visibility.
- Connect actual backend data.
- Add safe approval controls.

Stage 12: Testing and independent audit

- Run existing tests.
- Run P-06 tests.
- Run security tests.
- Run integration tests.
- Run resource tests.
- Resolve regressions.
- Generate the final report.

Do not skip stages.

---

33. STRICT DEVELOPMENT RULES

1. Preserve all working P-01 through P-05 functionality.
2. Do not rebuild AUTONOMUS.
3. Do not replace existing architecture without technical justification.
4. Do not introduce mandatory paid APIs.
5. Do not assume every opportunity should become a SaaS business.
6. Do not create a business without opportunity eligibility checks.
7. Do not treat generated assumptions as market evidence.
8. Do not claim profitability without verified financial data.
9. Do not build unnecessary product features.
10. Do not generate fake customer testimonials.
11. Do not fabricate company registrations or legal certifications.
12. Do not claim trademark availability without appropriate verification.
13. Do not copy competitors' protected branding or content.
14. Do not publish externally without authorization.
15. Do not make purchases or spend money.
16. Do not store raw credentials in agent instructions.
17. Do not bypass platform verification.
18. Do not allow cross-business data access without permission.
19. Do not allow an agent to approve its own critical actions.
20. Do not create duplicate agent, workflow, task, or approval infrastructure.
21. Do not implement P-07 financial accounting inside P-06.
22. Do not claim a product is operational before required tests.
23. Do not claim a business is operational merely because its website exists.
24. Do not silently modify existing database schemas.
25. Do not install unnecessary dependencies.
26. Do not delete user data or existing projects.
27. Do not start P-07 or later phases automatically.

If a dependency from an earlier phase is missing, document the blocker and implement only the safe portion.

---

34. FINAL ACCEPTANCE CRITERIA

P-06 is complete only when the following requirements have implementation and test evidence.

Business foundation

- [ ] Repository audit completed.
- [ ] P-03 opportunity integration verified.
- [ ] Business registry operational.
- [ ] Eligibility gate operational.
- [ ] Business templates operational.
- [ ] Business lifecycle operational.
- [ ] Business workspace isolation enforced.

Blueprint and strategy

- [ ] Business blueprint generation operational.
- [ ] Customer definition implemented.
- [ ] Value proposition implemented.
- [ ] Business model framework implemented.
- [ ] Assumption register operational.
- [ ] Evidence traceability implemented.

Product creation

- [ ] Product registry operational.
- [ ] PRD generation operational.
- [ ] MVP scope generation operational.
- [ ] Product development workflow integrated.
- [ ] Product quality checks recorded.
- [ ] Service business workflows supported where applicable.

Business assets

- [ ] Asset registry operational.
- [ ] Brand asset management operational.
- [ ] Usage rights metadata supported.
- [ ] Business workspace integration verified.
- [ ] Asset approval controls enforced.

Website and distribution

- [ ] Website planning operational.
- [ ] Website creation supported where adapters are available.
- [ ] Website verification implemented.
- [ ] Distribution channel evaluation operational.
- [ ] External publishing approval enforced.

Operations and launch

- [ ] Customer acquisition planning operational.
- [ ] Customer support preparation operational.
- [ ] Business operating playbook generated.
- [ ] Launch readiness engine operational.
- [ ] Hard launch blockers enforced.
- [ ] Owner launch approval enforced.
- [ ] Lifecycle transitions validated.

Integration and governance

- [ ] P-01 integration verified.
- [ ] P-02 integration verified.
- [ ] P-03 integration verified.
- [ ] P-04 integration verified.
- [ ] P-05 integration verified.
- [ ] P-07 financial interface prepared.
- [ ] Security tests pass.
- [ ] Existing tests pass.
- [ ] Windows documentation complete.
- [ ] No critical unresolved regression remains.

A checkbox must not be marked complete without evidence.

---

35. FINAL IMPLEMENTATION REPORT

Generate:

"docs/audits/P06_IMPLEMENTATION_REPORT.md"

Include:

1. Executive summary.
2. Initial repository condition.
3. Existing functionality reused.
4. New components implemented.
5. Existing modules modified.
6. Business categories supported.
7. Eligibility architecture.
8. Business blueprint implementation.
9. Business model framework.
10. Product creation capabilities.
11. Asset management.
12. Website creation capabilities.
13. Distribution preparation.
14. Customer acquisition preparation.
15. Customer support preparation.
16. Operating playbook.
17. Business lifecycle.
18. Launch readiness.
19. Agent orchestration.
20. Approval and security controls.
21. Database changes.
22. API endpoints.
23. P-07 integration interface.
24. Test results.
25. Windows setup.
26. Known limitations.
27. Deferred functionality.
28. Outstanding risks.
29. Files changed.
30. Acceptance criteria evidence.
31. Recommended next development phase.

Report exact test statistics:

- Tests executed.
- Tests passed.
- Tests failed.
- Tests skipped.
- Integration tests passed.
- Security tests passed.
- Known warnings.
- Outstanding blockers.

Clearly distinguish a locally created business package from a deployed business, and a deployed business from an operational revenue-generating business.

Never fabricate a successful launch.

---

36. PHASE COMPLETION BOUNDARY

After P-06 has been implemented, tested, documented, and independently audited:

STOP. DO NOT AUTOMATICALLY START P-07.

Do not build the full Financial Intelligence Engine.

Do not implement financial accounting, cash reconciliation, profit calculations, wallet management, payment authorization, or autonomous financial decision-making within this phase.

Do not launch real businesses automatically.

Instead:

1. Present the implementation report.
2. Show the actual test results.
3. Identify supported business categories.
4. Identify which business assets can actually be generated.
5. Identify which products can actually be built and tested.
6. Identify which distribution integrations are operational.
7. Show launch-readiness evidence.
8. Identify unresolved security and operational issues.
9. Confirm acceptance criteria.
10. Wait for explicit owner approval.

The next planned phase is:

P-07: FINANCIAL INTELLIGENCE ENGINE

P-07 begins only after the owner reviews and approves P-06.

---

FINAL DIRECTIVE

Build the Business Creation Engine as a disciplined system for turning validated commercial opportunities into real, testable, launch-ready business infrastructure.

Do not confuse a business idea with a business.

Do not confuse a generated product with a tested product.

Do not confuse a deployed website with customer demand.

Do not confuse projected revenue with collected revenue.

Do not create businesses merely to increase the number of projects in AUTONOMUS.

Every business must have:

- A traceable opportunity.
- A defined customer.
- A real problem.
- A clear value proposition.
- A documented business model.
- A concrete product or service.
- A viable delivery mechanism.
- A distribution strategy.
- A customer support process.
- An operating playbook.
- Evidence-backed launch readiness.
- Explicit approval for sensitive external actions.

The goal is to make AUTONOMUS capable of creating businesses systematically, while preserving capital, minimizing unnecessary development, and avoiding unsupported commercial assumptions.

Build carefully. Reuse existing infrastructure. Create only what the business actually needs. Validate every deliverable. Preserve all earlier phases. Stop at P-06 and wait for owner approval.