AUTONOMUS P-10: SECURITY AND GOVERNANCE ENGINE

Master Development Prompt | Version 1.0

---

1. ROLE AND MISSION

Act as a principal security architect, application security engineer, Windows security specialist, AI safety engineer, DevSecOps engineer, and backend architect.

Your mission is to design, implement, test, and integrate the Security and Governance Engine (P-10) into the existing AUTONOMUS AI Operating System.

AUTONOMUS is a Windows-first, hybrid-AI autonomous business operating system. It coordinates multiple agents, executes digital tasks, creates and operates businesses, manages financial intelligence, learns from outcomes, and makes decisions under controlled autonomy.

This creates a substantial attack surface.

The Security and Governance Engine must protect:

- The owner and their identity.
- The AUTONOMUS core system.
- AI models and agent processes.
- Agent instructions, tools, and permissions.
- Business workspaces and their data.
- Local files and Windows resources.
- Browser sessions and authenticated accounts.
- API integrations and external services.
- Financial records, wallets, and payment operations.
- Memory, knowledge bases, and retrieved information.
- System configuration, secrets, and backups.
- Autonomous workflows and scheduled operations.

Your objective is not to add a few authentication screens. You must establish a system-wide security architecture that controls what every component can access, what it can execute, what it can change, and when human authorization is mandatory.

Fundamental security principle

AUTONOMUS must never have more authority than the owner explicitly grants it.

An AI agent cannot grant itself new permissions, remove security restrictions, bypass approval requirements, or rewrite the security constitution.

The owner remains the ultimate authority.

---

2. NON-NEGOTIABLE DEVELOPMENT RULES

Before writing code, follow these rules.

1. Do not rebuild AUTONOMUS from scratch.
2. Do not delete existing working functionality.
3. Do not replace existing architecture without a documented technical justification.
4. Do not create duplicate authentication, permission, logging, or security systems when an existing implementation can be extended.
5. Inspect the actual repository and existing code before proposing changes.
6. Reuse the existing P-01 through P-09 components wherever possible.
7. Maintain compatibility with the existing Windows-first environment.
8. Keep local-first operation as the default.
9. Do not introduce mandatory paid security services or paid APIs.
10. Never hardcode passwords, API keys, private keys, tokens, or encryption secrets.
11. Never expose credentials to an LLM as ordinary prompt content.
12. Do not trust an agent's claim that an action is safe. Enforce permissions independently of the model.
13. Never allow a security decision to depend exclusively on an LLM response.
14. Fail closed for sensitive operations when authorization or verification is unavailable.
15. Keep security policy outside the control of autonomous agents.
16. Every security-critical action must be auditable.
17. Build tests before declaring security features complete.
18. Document all changes and their impact on existing modules.

If a required component does not exist, create it using the current architecture's conventions.

If an existing component is incomplete, extend it instead of duplicating it.

---

3. PRE-IMPLEMENTATION SYSTEM AUDIT

Before implementation, conduct a comprehensive audit of P-01 through P-09.

Inspect the actual repository, not merely the documentation.

3.1 Inspect these modules

- P-01: Core Operating System
- P-02: Master Intelligence Engine
- P-03: Opportunity Discovery Engine
- P-04: Dynamic Agent Factory
- P-05: Universal Digital Execution Engine
- P-06: Business Creation Engine
- P-07: Financial Intelligence Engine
- P-08: Survival and Scaling Engine, if implemented
- P-09: Memory and Continuous Learning Engine

3.2 Inspect existing security-related components

Identify:

- Authentication and session management.
- User and agent identities.
- Agent permission handling.
- Tool execution permissions.
- File access restrictions.
- Command execution mechanisms.
- Browser automation.
- API authentication.
- Database access controls.
- Secret storage.
- Financial approval workflows.
- Audit logs.
- Memory access restrictions.
- Backup and recovery.
- Emergency shutdown mechanisms.
- Scheduled and background tasks.

3.3 Produce an audit report

For each component, classify it as:

- Implemented and verified.
- Implemented but insufficiently protected.
- Partially implemented.
- Missing.
- Duplicated.
- Vulnerable.
- Requires redesign.

Include:

- Existing implementation.
- Security weaknesses.
- Threats introduced by the weakness.
- Severity.
- Recommended remediation.
- Dependencies.
- Compatibility risks.

Do not assume that documentation accurately reflects the code.

3.4 Architecture preservation

Create a P-10 integration map showing how security will connect to existing modules.

Identify the authoritative source for:

- User identity.
- Agent identity.
- Permissions.
- Security policies.
- Financial approvals.
- Business ownership.
- Memory access.
- Audit events.

There must be one authoritative policy enforcement mechanism, even if several modules consume its decisions.

Do not begin implementation until the audit and implementation plan are documented.

---

4. SECURITY ARCHITECTURE AND THREAT MODEL

Design a centralized security architecture that can protect the entire operating system.

4.1 Establish security boundaries

Define separate trust boundaries for:

1. Owner interface.
2. Core operating system.
3. Master Intelligence Engine.
4. Individual agents.
5. Agent tools.
6. Business workspaces.
7. External websites.
8. External APIs.
9. Local AI models.
10. Cloud AI providers.
11. Financial services.
12. Local operating system resources.
13. Third-party files and documents.
14. Retrieved memory and knowledge.
15. Background automation processes.

Never treat all these environments as equally trusted.

4.2 Asset inventory

Maintain an inventory of protected assets.

Include:

- Owner credentials.
- Authentication tokens.
- API keys.
- Encryption keys.
- Browser cookies.
- Financial credentials.
- Business information.
- Customer data.
- Internal source code.
- Local files.
- Agent instructions.
- System policies.
- Financial records.
- Database files.
- Memory stores.
- Backups.
- Logs.

Assign sensitivity classifications.

Suggested classifications:

Level| Classification| Examples
1| Public| Public research and published content
2| Internal| General system configuration
3| Confidential| Business strategies and private documents
4| Restricted| Personal credentials and financial records
5| Critical| Encryption keys, recovery secrets, privileged credentials

Access to each classification must be controlled.

4.3 Threat model

Use a documented threat-modeling approach such as STRIDE where appropriate.

Consider:

- Unauthorized access.
- Identity impersonation.
- Privilege escalation.
- Malicious agent behavior.
- Prompt injection.
- Malicious downloaded files.
- Browser session theft.
- Credential leakage.
- Data exfiltration.
- Command injection.
- Path traversal.
- Server-side request forgery.
- Financial manipulation.
- Unauthorized payments.
- Agent-to-agent privilege escalation.
- Memory poisoning.
- Supply-chain compromise.
- Database corruption.
- Denial of service.
- Accidental destructive execution.
- Malicious external websites.
- Compromised AI providers.

For every significant threat, document:

- Threat description.
- Entry point.
- Affected assets.
- Likelihood.
- Impact.
- Risk level.
- Preventive controls.
- Detection controls.
- Recovery procedure.
- Verification test.

Maintain a living threat register.

---

5. IDENTITY AND ACCESS MANAGEMENT

Build a centralized identity and access management system.

It must distinguish between the owner, system components, agents, tools, and external integrations.

5.1 Identity types

Support identities for:

- Primary system owner.
- Additional authorized human users, if introduced.
- Master Intelligence Engine.
- Individual AI agents.
- Background workers.
- Scheduled tasks.
- Tool executors.
- API integrations.
- External services.

Each identity must have a unique identifier and defined authority.

5.2 Authentication

Implement secure owner authentication.

Requirements:

- Secure password hashing using a modern password-hashing algorithm.
- Session expiration.
- Secure session storage.
- Logout and session revocation.
- Login attempt protection.
- Configurable lockout or throttling.
- Secure password reset.
- Protection against session fixation.
- CSRF protection where applicable.
- Secure cookie configuration for web interfaces.
- Optional additional authentication for sensitive actions.

Never store plaintext passwords.

Do not rely on frontend authentication alone. Verify authentication on the backend.

5.3 Multi-factor authentication

Design optional MFA support.

Potential methods:

- TOTP authenticator.
- Recovery codes.
- Additional approval through the owner interface.

MFA should be configurable without making the local development environment unnecessarily difficult to use.

For critical operations, require stronger authentication or recent reauthentication where appropriate.

5.4 Session management

Implement:

- Session creation.
- Session expiry.
- Session revocation.
- Device/session visibility.
- Suspicious session detection.
- Secure logout.
- Refresh-token rotation if refresh tokens are used.

Protect browser sessions and external account credentials separately from AUTONOMUS owner sessions.

---

6. ROLE-BASED AND ATTRIBUTE-BASED ACCESS CONTROL

Implement a permission architecture combining RBAC and ABAC where appropriate.

6.1 Suggested roles

Create configurable roles such as:

- Owner.
- System Administrator.
- Security Administrator.
- Business Manager.
- Agent Supervisor.
- Research Agent.
- Execution Agent.
- Financial Analyst.
- Read-Only Auditor.

Do not automatically give every agent a role with broad permissions.

6.2 Permission dimensions

Evaluate access using:

- Identity.
- Role.
- Requested action.
- Resource type.
- Resource ownership.
- Business ID.
- Project ID.
- Task ID.
- Agent identity.
- Environment.
- Risk classification.
- Approval status.
- Permission expiry.
- Current security mode.

Example:

A research agent working on Business A must not automatically access confidential documents belonging to Business B.

A content agent must not receive financial transaction permissions merely because it operates inside a business workspace.

6.3 Permission matrix

Build an explicit permission matrix.

Example:

Action| Research Agent| Execution Agent| Financial Agent| Owner
Read assigned research| Yes| Limited| Limited| Yes
Modify assigned files| Limited| Yes| Limited| Yes
Execute approved commands| No| Limited| No| Yes
View financial reports| No| Limited| Yes| Yes
Initiate payments| No| No| Request only| Approve
Change security policies| No| No| No| Yes
Disable emergency protection| No| No| No| Yes

This is a starting example, not a hardcoded universal permission model.

6.4 Least privilege

Every agent and service must receive only the permissions required for its assigned task.

Permissions should be:

- Scoped.
- Time-limited where possible.
- Revocable.
- Auditable.
- Explicitly granted.
- Independently verified.

Do not grant permanent unrestricted access to agents.

6.5 Authorization enforcement

Create a centralized authorization service.

All sensitive actions must pass through backend authorization checks.

The frontend may display permissions, but it must never be the authority that grants them.

---

7. PERMISSION BROKER AND CAPABILITY SYSTEM

Build a Permission Broker between AI agents and executable tools.

Agents must not call sensitive tools directly without authorization.

7.1 Architecture

Use the following conceptual flow:

Owner policy → Permission Broker → Authorization decision → Tool executor → Result validation → Audit event

Every request must identify:

- Requesting agent.
- Task ID.
- Business ID, if applicable.
- Requested tool.
- Requested operation.
- Target resource.
- Required permissions.
- Risk level.
- Approval requirement.
- Expiration.
- Execution constraints.

7.2 Capability-based access

Where practical, issue narrowly scoped capabilities for individual tasks.

For example:

An agent may receive permission to:

- Read a specific project directory.
- Create files in a designated output folder.
- Access a specific approved website.
- Execute a particular command with defined arguments.
- Update a specific business record.

It must not receive general filesystem or unrestricted command access.

Capabilities must expire and be revocable.

7.3 Permission escalation

If an agent needs additional permissions:

1. It must explain the reason.
2. It must specify the exact permission.
3. It must identify the resource and intended action.
4. The broker must evaluate the request.
5. Human approval must be requested when policy requires it.
6. The granted permission must be scoped and logged.

An agent cannot grant itself permission by creating another agent.

---

8. HUMAN APPROVAL AND CONTROLLED AUTONOMY

Create a configurable approval engine.

The objective is to let AUTONOMUS work independently while ensuring sensitive actions remain under owner control.

8.1 Action risk classification

Classify actions into four levels.

Level 0: Read-only

Examples:

- Read approved project files.
- Analyze research.
- Generate reports.
- Inspect permitted business metrics.

Default: May execute automatically within scope.

Level 1: Reversible low-risk actions

Examples:

- Create a draft.
- Generate a local report.
- Create an isolated project file.
- Update a non-critical task status.

Default: May execute automatically within assigned permissions.

Level 2: Significant or externally visible actions

Examples:

- Publish public content.
- Send external messages.
- Modify a production website.
- Change external account settings.
- Install software.
- Execute commands that alter important system state.

Default: Require approval unless a narrowly scoped owner-approved policy explicitly permits the operation.

Level 3: Critical or irreversible actions

Examples:

- Transfer money.
- Change wallet permissions.
- Delete important data.
- Change security policies.
- Expose credentials.
- Modify recovery settings.
- Make high-value purchases.
- Disable security controls.

Default: Explicit owner approval and additional verification.

8.2 Approval request interface

Each approval request must display:

- Requesting agent.
- Business or project.
- Requested action.
- Exact target.
- Reason.
- Risk classification.
- Expected consequences.
- Data affected.
- Financial impact, if any.
- Whether the action is reversible.
- Available alternatives.
- Approval expiry.

Provide actions such as:

- Approve once.
- Reject.
- Request modification.
- Approve under a defined limited policy, where supported.

Approval must not silently authorize unrelated future operations.

8.3 Approval integrity

- Bind approvals to the exact action and its parameters.
- Prevent approval reuse for a different action.
- Expire stale approvals.
- Revalidate permissions immediately before execution.
- Log the approving identity.
- Log the execution result.
- Require new approval if the action materially changes.

An LLM-generated statement such as "the owner approved this" is not an approval record.

8.4 Owner-controlled policies

The owner may configure approved autonomy levels.

However:

- Agents cannot modify approval policies.
- Agents cannot disable approval requirements.
- Agents cannot approve their own requests.
- Agent supervisors cannot bypass owner-only restrictions.
- Security-critical policy changes require owner authentication.

---

9. SECURE SECRETS MANAGEMENT

Build a secure credential-management architecture.

This is one of the most important modules in P-10.

9.1 Protected secrets

Handle:

- AI provider API keys.
- External platform credentials.
- Database credentials.
- Browser authentication data.
- OAuth tokens.
- Webhook secrets.
- Payment service credentials.
- Encryption keys.
- Recovery credentials.

9.2 Windows-first secret storage

Prefer native Windows protection mechanisms where appropriate, such as:

- Windows Credential Manager.
- DPAPI-backed encryption.
- A dedicated secure local vault.

Select the mechanism based on the existing architecture and document the security trade-offs.

Do not invent a custom cryptographic algorithm.

Use established, maintained cryptographic libraries.

9.3 Secret handling rules

Secrets must never be:

- Printed in application logs.
- Added to ordinary agent prompts.
- Stored in vector memory.
- Included in generated reports.
- Committed to Git.
- Written to frontend source code.
- Returned in API responses.
- Included in exception tracebacks visible to ordinary users.
- Sent to untrusted external websites.

9.4 Secret access broker

Agents should request an authorized operation that uses a secret, not receive the secret itself.

For example:

A deployment agent may request an approved deployment operation through a credential-aware executor.

The agent does not need to see the deployment token.

9.5 Secret lifecycle

Implement:

- Secure creation.
- Encryption at rest.
- Controlled retrieval.
- Rotation.
- Revocation.
- Expiration tracking.
- Access auditing.
- Secure deletion where technically possible.

9.6 Development environment

Use environment variables only for non-persistent development configuration or controlled secret injection.

Ensure ".env" files are excluded from Git.

Provide a safe ".env.example" containing placeholder names only.

Implement secret scanning before commits or releases.

---

10. FILESYSTEM AND WINDOWS RESOURCE SECURITY

AUTONOMUS will operate on a Windows machine. Unrestricted filesystem access could damage the owner's system.

Build a strict filesystem security layer.

10.1 Workspace isolation

Use dedicated directories for:

- AUTONOMUS configuration.
- System data.
- Agent workspaces.
- Business workspaces.
- Temporary files.
- Downloaded files.
- Generated files.
- Logs.
- Backups.
- Local model data.

Suggested conceptual structure:

C:\AUTONOMUS\
    app\
    config\
    data\
    agents\
    businesses\
    projects\
    workspace\
    downloads\
    temporary\
    logs\
    backups\
    models\

Adapt this structure to the actual existing repository and configuration.

Do not blindly relocate existing data.

10.2 Path validation

Implement protection against:

- Path traversal.
- Absolute-path abuse.
- Symbolic-link escapes.
- Junction escapes.
- Alternate data stream abuse where relevant.
- Unauthorized access to protected directories.
- Unsafe file overwrites.
- Unauthorized recursive deletion.

Normalize and validate resolved paths before every operation.

Check the final resolved path, not just the user-provided string.

10.3 Protected directories

Create configurable protected locations.

Examples:

- Windows system directories.
- User profile credentials.
- Browser profile directories.
- AUTONOMUS security configuration.
- Database backups.
- Encryption-key storage.
- Critical source-code directories.

Do not allow an ordinary agent to modify these directories.

10.4 Safe file operations

Support:

- Read.
- Create.
- Modify.
- Move.
- Copy.
- Delete.

Every operation must be checked against the agent's granted capabilities.

For destructive operations:

- Check ownership.
- Check scope.
- Check risk.
- Check approval requirements.
- Create a backup or recovery point when appropriate.
- Record the result.

10.5 Windows system controls

Control access to:

- Process management.
- Startup applications.
- Registry.
- Power settings.
- Network configuration.
- System services.
- Installed applications.
- Firewall settings.
- User account settings.

High-impact system modifications must require explicit owner approval.

Never permit unrestricted registry, PowerShell, or system-administration access for ordinary agents.

---

11. COMMAND EXECUTION AND CODE SANDBOXING

P-05 provides digital execution capabilities. P-10 must secure them.

11.1 Central command execution gateway

All agent-initiated shell and subprocess operations must pass through a central execution gateway.

Do not let agents directly execute arbitrary operating-system commands.

11.2 Execution policy

Implement:

- Command allowlists.
- Executable path validation.
- Argument validation.
- Working-directory restrictions.
- Environment-variable restrictions.
- Execution timeouts.
- CPU and memory limits where practical.
- Output-size limits.
- Process-tree termination.
- Restricted network access.
- Execution logs.

Avoid shell-string construction.

Prefer structured argument arrays and safe subprocess APIs.

11.3 Risky commands

Require approval or block commands that could:

- Delete large directory trees.
- Format drives.
- Modify boot configuration.
- Disable security software.
- Change firewall rules.
- Modify privileged user accounts.
- Extract credentials.
- Install unverified executables.
- Run remote scripts.
- Modify protected system files.
- Change AUTONOMUS security policy.

Maintain an explicit denylist for known dangerous patterns, but do not rely on a denylist alone.

11.4 Code execution sandbox

Provide isolated environments for generated code.

Prefer:

- Dedicated temporary workspaces.
- Restricted user permissions.
- Virtual environments or containers where supported.
- Limited filesystem access.
- Network restrictions.
- Resource limits.
- Execution timeouts.
- Cleanup after completion.

If the host cannot provide a strong isolation boundary, restrict the types of code and actions allowed.

Do not claim that a normal Python virtual environment is a security sandbox.

11.5 Dependency installation

Agents must not install arbitrary packages automatically.

Require:

- Package identification.
- Source verification.
- Version pinning.
- Risk assessment.
- Approval according to policy.
- Post-installation testing.

---

12. BROWSER AUTOMATION SECURITY

AUTONOMUS may interact with websites and authenticated accounts.

Browser automation is a high-risk execution surface.

12.1 Browser isolation

Use separate browser contexts or profiles for different businesses and tasks where practical.

Do not expose the owner's everyday browser profile to all agents.

Protect:

- Cookies.
- Authentication tokens.
- Saved passwords.
- Browser storage.
- Download directories.
- Session state.

12.2 Website trust assessment

Before interacting with a website:

- Verify the intended domain.
- Detect suspicious domain variations.
- Check HTTPS where appropriate.
- Identify redirects.
- Inspect unexpected login pages.
- Detect unexpected downloads.
- Restrict sensitive operations to approved domains.

12.3 Browser action policies

Classify actions such as:

- Navigate.
- Read.
- Search.
- Download.
- Upload.
- Fill forms.
- Send messages.
- Publish.
- Purchase.
- Change account settings.
- Delete account data.

Apply appropriate approval requirements.

12.4 Browser prompt injection

Websites can contain instructions designed to manipulate AI agents.

Treat website content as untrusted data.

A website cannot:

- Override system instructions.
- Change owner policies.
- Grant agent permissions.
- Request hidden credentials.
- Disable security protections.
- Authorize financial transactions.
- Instruct an agent to reveal internal files.

12.5 Browser download protection

Before processing downloaded files:

- Validate file type.
- Check file size.
- Reject unexpected executable files by default.
- Use isolated storage.
- Scan files where supported.
- Avoid executing downloaded content.
- Treat embedded instructions as untrusted.

12.6 External account actions

For public publishing, messaging, purchases, account modifications, and similar operations, enforce approval rules based on action risk and the owner's explicit policies.

Never bypass OTP, CAPTCHA, authentication challenges, or platform security mechanisms.

---

13. NETWORK AND API SECURITY

Create a network security layer for all external communication.

13.1 Outbound network policy

Support configurable:

- Domain allowlists.
- Denylists.
- Per-agent network permissions.
- Per-business network permissions.
- Request rate limits.
- Data-transfer limits.
- Connection timeouts.

Default to restricted access for agents that do not need external connectivity.

13.2 SSRF protection

Prevent requests to unauthorized internal resources.

Protect against:

- Loopback access.
- Private network access.
- Cloud metadata endpoints.
- Internal service exposure.
- DNS rebinding.
- Redirect-based bypasses.
- IPv4 and IPv6 address variations.

Validate the resolved destination IP and every redirect, not merely the original hostname.

13.3 Local services

Bind local services to loopback interfaces unless external access is explicitly required.

Protect local administrative APIs.

Do not expose development dashboards, database services, or model endpoints publicly by default.

13.4 API security

For every internal and external API integration, implement appropriate:

- Authentication.
- Authorization.
- Input validation.
- Output validation.
- Rate limiting.
- Request-size limits.
- Timeout handling.
- Error handling.
- Audit logging.

13.5 Webhook security

For incoming webhooks:

- Verify signatures.
- Validate timestamps.
- Prevent replay attacks.
- Validate event types.
- Enforce idempotency.
- Reject malformed payloads.
- Log verification outcomes.

Never trust a webhook merely because it claims a payment succeeded.

---

14. AI SECURITY AND PROMPT INJECTION DEFENSE

This section protects the intelligence layer itself.

AUTONOMUS will process websites, documents, emails, code, research results, retrieved memories, and outputs from other agents.

Any of these can contain malicious instructions.

14.1 Trust hierarchy

Maintain a strict separation between:

1. Owner-approved security constitution.
2. System-level policies.
3. Authorized task instructions.
4. Agent-generated plans.
5. External information.
6. Untrusted tool output.

External information must never gain authority over higher-level instructions.

14.2 Prompt injection defense

Protect against:

- Direct prompt injection.
- Indirect prompt injection.
- Document-based injection.
- Website-based injection.
- Email-based injection.
- Code-comment injection.
- Tool-output injection.
- Memory poisoning.
- Agent-to-agent instruction manipulation.

14.3 Content isolation

Mark retrieved content as untrusted.

Separate:

- Instructions.
- Evidence.
- User-provided information.
- External content.
- Agent conclusions.

Do not concatenate untrusted documents into privileged system instructions.

14.4 Agent-to-agent communication

Require structured messages between agents.

Every handoff must include:

- Sender identity.
- Recipient identity.
- Task ID.
- Business scope.
- Message type.
- Content classification.
- Evidence references.
- Requested action.
- Permission requirements.

A receiving agent must independently verify permissions.

14.5 Tool output validation

Never assume tool output is safe because it came from an internal tool.

Validate:

- Structure.
- Data types.
- Size.
- Resource references.
- File paths.
- URLs.
- Command arguments.
- External instructions.

14.6 Model limitations

An AI model is not a security authority.

Do not use LLM reasoning as the sole mechanism for:

- Authentication.
- Permission verification.
- Financial authorization.
- Secret access.
- Security-policy modification.
- Risk-limit enforcement.

These controls must be deterministic and enforced by trusted application code.

---

15. DYNAMIC AGENT FACTORY SECURITY

P-04 allows AUTONOMUS to create specialized agents.

P-10 must ensure that new agents cannot become a privilege-escalation mechanism.

15.1 Agent registration

Every new agent must have:

- Unique agent ID.
- Defined purpose.
- Parent or creator identity.
- Assigned business scope.
- Assigned task scope.
- Tool permissions.
- Data-access permissions.
- Resource limits.
- Lifecycle status.
- Expiration or review policy.

15.2 Agent creation controls

Before activating a new agent:

1. Validate the requested purpose.
2. Check whether the agent is necessary.
3. Define its minimum permissions.
4. Check resource limits.
5. Check business ownership.
6. Check policy restrictions.
7. Record the creation event.

15.3 Permission inheritance

New agents must not automatically inherit all permissions of their creator.

Permissions must be explicitly assigned.

An agent may delegate only permissions that policy allows it to delegate.

It must never delegate owner-only privileges.

15.4 Agent lifecycle

Support:

- Created.
- Pending review.
- Active.
- Suspended.
- Restricted.
- Revoked.
- Archived.

A suspicious agent must be suspendable without shutting down the entire operating system.

15.5 Agent behavior monitoring

Monitor:

- Repeated permission denials.
- Unexpected tool usage.
- Attempts to access unrelated businesses.
- Unusual filesystem activity.
- Unusual network activity.
- Repeated approval requests.
- Attempts to modify security settings.
- Unexpected resource consumption.

Do not automatically label every unusual action malicious. Use risk-based investigation and audit evidence.

---

16. FINANCIAL SECURITY AND TRANSACTION GOVERNANCE

Integrate with P-07 Financial Intelligence and P-08 Survival and Scaling where implemented.

Do not create a second financial ledger.

The financial engine remains authoritative for financial records and accounting.

P-10 provides authorization, protection, and execution controls.

16.1 Financial security principles

- No unrestricted wallet access.
- No unrestricted transfer authority.
- Never expose private keys to language models or agents.
- Use read-only financial connections initially.
- Separate transaction execution from AI reasoning.
- Use a constrained transaction executor.
- Enforce deterministic spending limits.
- Require explicit approval for critical transactions.

16.2 Financial permission levels

Create separate permissions for:

- View balances.
- View transactions.
- Read financial reports.
- Prepare payment requests.
- Validate payment details.
- Request transfers.
- Approve transfers.
- Execute approved transactions.
- Modify financial policies.

An agent with permission to analyze financial records must not automatically be able to transfer funds.

16.3 Transaction approval

Every sensitive transaction must be evaluated using:

- Amount.
- Currency.
- Recipient.
- Destination.
- Business ID.
- Available balance.
- Budget.
- Daily limit.
- Per-transaction limit.
- Risk classification.
- Transaction purpose.
- Approval status.

Bind approval to the exact recipient, amount, currency, and transaction details.

If any critical parameter changes, require a new approval.

16.4 Financial safeguards

Implement:

- Per-business spending caps.
- Daily and monthly limits.
- Maximum experiment loss.
- Protected reserves.
- Emergency transaction suspension.
- Duplicate transaction detection.
- Idempotency controls.
- Reconciliation checks.
- Transaction audit records.

16.5 Payment verification

Only verified payment events may be treated as confirmed collections.

Protect against:

- Forged payment notifications.
- Replayed webhooks.
- Duplicate transactions.
- Incorrect currency.
- Incorrect recipient.
- Amount manipulation.
- Unverified payment claims.

16.6 Financial emergency mode

Allow the owner to immediately:

- Block new transaction requests.
- Suspend transaction execution.
- Revoke financial agent permissions.
- Disable connected transaction capabilities.
- Preserve financial records and audit logs.

Emergency suspension must not delete historical financial records.

---

17. DATA PROTECTION AND PRIVACY

Build a consistent data-protection policy.

17.1 Data classification

Apply the classification model established in the threat model.

Each data object should have appropriate metadata:

- Owner.
- Business ID.
- Project ID.
- Classification.
- Creation date.
- Retention policy.
- Access policy.
- Source.
- Encryption status, where applicable.

17.2 Data isolation

Prevent cross-business data leakage.

Business A agents must not automatically access Business B data.

Enforce business scope at the backend, database query, file access, and memory retrieval layers.

Do not rely on frontend filtering.

17.3 Encryption

Use established encryption libraries and platform protections.

Protect sensitive data:

- At rest.
- In transit.
- In backups.
- During external integrations.

Use TLS for network communications where appropriate.

Do not invent cryptographic algorithms or use obsolete encryption.

17.4 Data minimization

Only collect and store information needed for the task.

Avoid retaining unnecessary personal information, authentication data, and external account content.

17.5 Retention and deletion

Create configurable retention policies.

Support:

- Retention periods.
- Archiving.
- Owner-authorized deletion.
- Secure deletion where technically achievable.
- Deletion audit records.
- Backup expiration policies.

Explain where deletion cannot immediately remove data from backups or immutable records.

17.6 Memory security integration

Integrate with P-09.

Requirements:

- Security-sensitive memories require restricted access.
- Secrets must not enter ordinary memory.
- External content remains untrusted after storage.
- Memory retrieval must respect business and project scopes.
- Agents must not use memory to bypass permissions.
- Owner instructions and security policies must be distinguishable from inferred preferences and external information.

---

18. DATABASE AND APPLICATION SECURITY

Secure all databases and application endpoints.

18.1 Database security

Implement:

- Parameterized queries.
- Safe ORM usage.
- Input validation.
- Least-privilege database access.
- Restricted database file permissions.
- Secure backup procedures.
- Migration integrity.
- Data isolation.

Do not build SQL queries by concatenating untrusted user input.

18.2 API endpoint security

Every protected endpoint must enforce:

- Authentication.
- Authorization.
- Input validation.
- Business/project scope.
- Rate limits where necessary.
- Safe error responses.

Do not expose stack traces, secrets, internal paths, or database details to ordinary users.

18.3 Frontend security

Implement:

- Secure authentication flows.
- Safe rendering of external content.
- Protection against cross-site scripting.
- Appropriate Content Security Policy.
- CSRF protection where relevant.
- Safe file upload handling.
- Restricted administrative routes.

Never treat hidden frontend buttons as authorization controls.

18.4 Configuration security

Validate security-related configuration at startup.

If a critical configuration is missing or invalid, enter a restricted or safe mode rather than silently disabling protection.

---

19. AUDIT LOGGING AND SECURITY MONITORING

Create a central security event system.

19.1 Events to record

Record:

- Login attempts.
- Session creation and revocation.
- Authentication failures.
- Permission grants.
- Permission denials.
- Approval requests.
- Approval decisions.
- Security policy changes.
- Agent creation and suspension.
- Tool executions.
- Filesystem modifications.
- Command executions.
- Browser actions.
- Secret access requests.
- Financial authorization decisions.
- Transaction execution results.
- Network policy violations.
- Emergency shutdown events.
- Backup and recovery operations.

19.2 Audit event fields

Each event should contain:

- Event ID.
- Timestamp.
- Actor identity.
- Actor type.
- Action.
- Target resource.
- Business/project/task scope.
- Risk level.
- Authorization decision.
- Approval reference.
- Execution result.
- Correlation ID.
- Relevant evidence references.

Do not store raw secrets or unnecessary sensitive content in audit logs.

19.3 Tamper resistance

Protect audit records against unauthorized modification.

Where practical:

- Use append-only records.
- Restrict update/delete permissions.
- Maintain integrity hashes or hash chains.
- Protect backups.
- Record log export and deletion events.

A hash chain is useful for tamper detection but is not a substitute for protected storage.

19.4 Monitoring dashboard

Create security monitoring views for:

- Current system security status.
- Active sessions.
- Active agents.
- Agent permission summaries.
- Pending approvals.
- Recent security events.
- Blocked operations.
- Suspicious activity.
- Financial protection status.
- Backup status.
- Emergency mode status.

19.5 Alerting

Provide configurable alerts for critical events.

Examples:

- Repeated failed authentication.
- Unexpected access to protected directories.
- Suspicious agent behavior.
- Unauthorized policy modification attempts.
- Financial authorization violations.
- Possible secret leakage.
- Critical backup failures.

Do not generate excessive alerts for harmless routine activity.

---

20. EMERGENCY SHUTDOWN, SAFE MODE AND RECOVERY

Implement a reliable emergency-control system.

20.1 Owner-controlled emergency stop

Provide a clearly accessible emergency control.

It must be able to:

1. Stop new autonomous task dispatch.
2. Pause or cancel running agent tasks safely.
3. Block new external side effects.
4. Suspend sensitive tool execution.
5. Disable transaction execution.
6. Revoke temporary capabilities.
7. Preserve audit records.
8. Display current shutdown status.

Do not terminate the entire computer or corrupt active databases.

20.2 Safe mode

Implement a safe mode that allows only essential read-only functionality.

When activated:

- Agents cannot initiate external actions.
- Financial transactions remain disabled.
- Security policies cannot be changed by agents.
- Sensitive command execution is blocked.
- Owner access to reports and logs remains available.

20.3 Failure behavior

For critical security components:

- Permission service unavailable: deny sensitive actions.
- Secret vault unavailable: deny secret-dependent operations.
- Approval service unavailable: deny approval-required actions.
- Policy configuration invalid: enter restricted mode.
- Audit subsystem unavailable: block critical actions that require an audit record.
- Authentication state uncertain: do not assume the owner is authenticated.

20.4 Recovery

Create controlled recovery procedures for:

- Database corruption.
- Lost application configuration.
- Compromised credentials.
- Revoked API tokens.
- Compromised agent.
- Malicious file execution.
- Failed deployment.
- Backup restoration.
- Interrupted shutdown.

Test recovery, not just backup creation.

20.5 Recovery authority

Only the owner or a specifically authorized recovery mechanism may restore privileged access or disable emergency protection.

---

21. WINDOWS DESKTOP SECURITY

AUTONOMUS is Windows-first.

Design protections for the actual host environment.

21.1 Local application security

- Use restricted local service bindings.
- Protect local configuration.
- Restrict writable application directories.
- Avoid running the application as Administrator by default.
- Do not require elevated privileges for ordinary operations.
- Request elevation only for an explicitly approved operation that genuinely requires it.

21.2 Startup and background processes

- Disclose startup behavior.
- Require owner authorization for automatic startup registration.
- Identify AUTONOMUS background processes.
- Allow the owner to pause background execution.
- Prevent agents from silently installing persistent startup mechanisms.

21.3 Local ports and services

Maintain an inventory of local services and ports.

- Bind internal services to loopback by default.
- Restrict access to administrative endpoints.
- Do not expose local model servers or databases publicly without explicit configuration.
- Document firewall requirements.

21.4 Local AI model security

Treat local models as untrusted computational components, not security authorities.

- Restrict model access to approved interfaces.
- Validate model-generated tool calls.
- Apply the same permission broker to local and cloud models.
- Prevent direct access to secrets.
- Limit resource consumption.
- Record provider/model metadata where appropriate.

21.5 Cloud AI provider security

When cloud models are enabled:

- Disclose what data may leave the machine.
- Apply data classification rules.
- Exclude secrets and restricted data.
- Use provider-specific configuration.
- Allow the owner to disable cloud inference.
- Do not send data to a cloud provider merely because a local model fails.

---

22. SUPPLY-CHAIN AND DEPENDENCY SECURITY

Protect the application from compromised dependencies and build tools.

22.1 Dependency management

- Pin critical dependency versions.
- Review newly introduced packages.
- Prefer maintained packages.
- Avoid unnecessary dependencies.
- Identify abandoned or vulnerable dependencies.
- Use lockfiles.
- Document dependency upgrades.

22.2 Security scanning

Where practical, integrate free tools for:

- Python dependency vulnerability scanning.
- JavaScript dependency auditing.
- Static code analysis.
- Secret detection.
- Basic software composition analysis.

Select tools compatible with the actual project stack.

22.3 Software bill of materials

Generate an SBOM where practical.

Track:

- Package name.
- Version.
- Source.
- License.
- Known vulnerability status.

22.4 Git protection

Ensure the repository excludes:

- ".env" files.
- API keys.
- Private keys.
- Browser profiles.
- Database credentials.
- Wallet secrets.
- Authentication cookies.
- Local vault data.
- Sensitive logs.
- Private customer records.

Provide a pre-commit secret-scanning process.

If a secret is accidentally committed, removing it from the latest commit is not enough. Document credential revocation and repository-history remediation.

22.5 Release integrity

For future releases, plan:

- Versioned releases.
- Build verification.
- Integrity checks.
- Signed artifacts where practical.
- Reproducible or documented build processes.

---

23. SECURITY POLICY MANAGEMENT

Create a centralized security policy system.

23.1 Policy categories

Support policies for:

- Authentication.
- Sessions.
- Agent permissions.
- Tool permissions.
- Filesystem access.
- Command execution.
- Network access.
- Browser actions.
- Financial operations.
- Data classification.
- Retention.
- Human approvals.
- Agent creation.
- Resource limits.
- Emergency shutdown.

23.2 Policy enforcement

Policies must be enforced by trusted application code.

An agent may request a policy change, but it cannot implement or approve that change.

23.3 Policy versioning

Every policy change must record:

- Previous value.
- New value.
- Actor.
- Timestamp.
- Reason.
- Approval reference.
- Policy version.

23.4 Policy rollback

Allow the owner to restore a previous valid policy configuration.

Do not allow rollback to silently disable mandatory protections.

23.5 Policy testing

Before applying major policy changes:

- Validate configuration.
- Check for conflicts.
- Run policy tests.
- Identify affected modules.
- Require approval when appropriate.

---

24. SECURITY COMMAND CENTER

Integrate security visibility into the existing AUTONOMUS interface.

Do not redesign the entire application or prematurely implement the full P-11 Command Center.

Create the security section and its necessary views using existing frontend conventions.

24.1 Security overview

Display:

- Overall security state.
- Active security mode.
- Authentication status.
- Active sessions.
- Active agents.
- Pending approvals.
- Recent security events.
- Critical alerts.
- Financial execution status.
- Backup health.

24.2 Access management

Allow the owner to inspect:

- Users.
- Agents.
- Roles.
- Permissions.
- Business scopes.
- Tool access.
- Temporary capabilities.
- Revoked permissions.

24.3 Approval center

Display:

- Pending requests.
- Requesting agent.
- Requested action.
- Risk level.
- Target.
- Financial impact.
- Expiry.
- Approval history.

24.4 Security event explorer

Provide filters for:

- Date.
- Actor.
- Agent.
- Business.
- Project.
- Event category.
- Severity.
- Authorization result.

24.5 Emergency controls

Provide clearly visible controls for:

- Pause autonomous operations.
- Disable external actions.
- Suspend transaction execution.
- Revoke temporary capabilities.
- Enter safe mode.
- Resume operations after owner verification.

Make dangerous controls difficult to trigger accidentally.

Require confirmation and authentication for critical actions.

---

25. DATABASE DESIGN

Inspect the existing database before creating new models.

Reuse existing entities wherever possible.

Add only what is necessary.

Potential entities include:

Identity and access

- "security_users"
- "security_identities"
- "security_roles"
- "security_permissions"
- "security_role_permissions"
- "security_identity_roles"
- "security_sessions"
- "security_capabilities"

Authorization and approvals

- "security_policy_versions"
- "security_authorization_decisions"
- "security_approval_requests"
- "security_approval_decisions"
- "security_permission_grants"
- "security_permission_revocations"

Agent security

- "security_agent_profiles"
- "security_agent_scopes"
- "security_agent_events"
- "security_agent_restrictions"

Secrets and data protection

- "security_secret_metadata"
- "security_secret_access_events"
- "security_data_classifications"
- "security_retention_policies"

Store secret metadata separately from encrypted secret material.

Do not store plaintext credentials in these tables.

Monitoring and recovery

- "security_audit_events"
- "security_alerts"
- "security_incidents"
- "security_emergency_events"
- "security_backup_records"
- "security_recovery_events"
- "security_threat_register"

Define appropriate:

- Primary keys.
- Foreign keys.
- Unique constraints.
- Indexes.
- Timestamps.
- Status fields.
- Business and project scope.
- Retention behavior.

Use migrations.

Do not destroy existing data.

---

26. BACKEND ARCHITECTURE

Adapt the module structure to the existing repository.

Suggested organization:

security/
    __init__.py
    config.py

    identity/
        authentication.py
        sessions.py
        identities.py

    authorization/
        rbac.py
        abac.py
        policy_engine.py
        permission_broker.py
        capabilities.py

    approvals/
        approval_engine.py
        approval_rules.py

    secrets/
        vault.py
        windows_protection.py
        secret_access.py

    execution/
        filesystem_guard.py
        command_guard.py
        sandbox.py

    browser/
        browser_security.py
        domain_validation.py

    network/
        egress_policy.py
        ssrf_protection.py

    ai_security/
        prompt_injection.py
        content_trust.py
        agent_handoff.py

    financial/
        transaction_guard.py
        spending_controls.py

    data_protection/
        classification.py
        encryption.py
        retention.py

    monitoring/
        audit_logger.py
        security_monitor.py
        alerts.py

    recovery/
        emergency_stop.py
        safe_mode.py
        backup_validation.py

    policies/
        policy_manager.py
        policy_validator.py

    tests/

This is a suggested logical structure, not an instruction to duplicate existing modules.

26.1 API endpoints

Design secure endpoints using existing API conventions.

Potential endpoints:

POST   /api/security/auth/login
POST   /api/security/auth/logout
GET    /api/security/auth/session

GET    /api/security/status
GET    /api/security/policies
POST   /api/security/policies/validate
PUT    /api/security/policies/{policy_id}

GET    /api/security/identities
GET    /api/security/agents
GET    /api/security/agents/{agent_id}/permissions

POST   /api/security/permissions/check
POST   /api/security/permissions/request
POST   /api/security/permissions/revoke

GET    /api/security/approvals
POST   /api/security/approvals/{request_id}/approve
POST   /api/security/approvals/{request_id}/reject

GET    /api/security/audit
GET    /api/security/alerts
GET    /api/security/incidents

POST   /api/security/emergency/pause
POST   /api/security/emergency/safe-mode
POST   /api/security/emergency/resume

GET    /api/security/backups
POST   /api/security/backups/verify

All endpoints must enforce authentication, authorization, validation, and appropriate scope.

Do not implement an endpoint merely because it appears in this list if an equivalent secure endpoint already exists.

Never expose secret values through these APIs.

---

27. INTEGRATION WITH P-01 THROUGH P-09

P-10 must act as a security layer across the existing operating system.

P-01: Core Operating System

Integrate:

- Authentication.
- Configuration protection.
- Central authorization.
- Audit logging.
- Emergency control.

P-02: Master Intelligence Engine

Ensure:

- Intelligence can request actions but cannot bypass authorization.
- Decision-making respects owner policies.
- Model outputs are not treated as trusted security decisions.
- Restricted data is excluded from unauthorized contexts.

P-03: Opportunity Discovery Engine

Ensure:

- External research is treated as untrusted.
- Research agents cannot access unrelated business data.
- External sources cannot alter system policies.
- Research outputs preserve source provenance.

P-04: Dynamic Agent Factory

Ensure:

- Agent creation is authorized.
- Agent permissions are explicitly assigned.
- New agents cannot inherit unrestricted privileges.
- Agent spawning obeys resource and security limits.

P-05: Universal Digital Execution Engine

Ensure:

- Every tool call passes through authorization.
- Filesystem access is restricted.
- Commands are validated.
- Browser operations obey policy.
- Network access is controlled.
- High-risk actions require approval.

P-06: Business Creation Engine

Ensure:

- Business workspaces are isolated.
- Customer and business information is protected.
- Publishing and external actions obey approval policies.
- Business agents cannot access unrelated workspaces.

P-07: Financial Intelligence Engine

Ensure:

- Financial records remain authoritative in P-07.
- Transaction authorization is enforced independently.
- Financial secrets are protected.
- Payment verification is mandatory.
- Financial limits cannot be overridden by agents.

P-08: Survival and Scaling Engine

Ensure:

- Survival decisions cannot override security limits.
- Scaling cannot silently expand privileges.
- New resources and services pass security review.
- Emergency suspension takes priority over scaling.

P-09: Memory and Continuous Learning Engine

Ensure:

- Memory retrieval respects authorization.
- Secrets are excluded from ordinary memory.
- External information remains untrusted.
- Cross-business memory leakage is prevented.
- Security policies cannot be learned away or rewritten by agents.

---

28. TESTING AND SECURITY VALIDATION

Security is not complete because the code compiles.

Build a dedicated security test suite.

Use unit tests, integration tests, API tests, and controlled adversarial tests.

28.1 Authentication tests

Test:

- Valid login.
- Invalid login.
- Session expiry.
- Session revocation.
- Password reset.
- Session fixation protection.
- Brute-force throttling.
- Unauthorized endpoint access.

28.2 Authorization tests

Test:

- Role enforcement.
- Permission enforcement.
- Business isolation.
- Project isolation.
- Task-level permissions.
- Agent permission restrictions.
- Expired capability rejection.
- Revoked capability rejection.
- Privilege escalation attempts.

28.3 Filesystem tests

Test:

- Path traversal.
- Absolute path escape.
- Symbolic-link escape.
- Junction escape.
- Protected directory access.
- Unauthorized deletion.
- Unauthorized file modification.
- Unsafe overwrite.

28.4 Command execution tests

Test:

- Unapproved executable.
- Dangerous command.
- Shell injection.
- Malicious argument.
- Unauthorized working directory.
- Execution timeout.
- Resource limit enforcement.
- Process-tree termination.
- Restricted network access.

28.5 Network tests

Test:

- Unauthorized domain.
- Loopback request.
- Private IP request.
- Metadata endpoint request.
- DNS rebinding scenarios.
- Redirect-based SSRF.
- Invalid TLS configuration.
- Excessive request rates.

28.6 AI security tests

Create adversarial test inputs containing:

- Instructions to reveal secrets.
- Instructions to override system policies.
- Fake owner approvals.
- Requests to disable security.
- Malicious instructions embedded in websites.
- Malicious document content.
- Malicious memory entries.
- Agent-to-agent privilege escalation attempts.

Verify that the system treats these as untrusted content.

28.7 Financial tests

Test:

- Unauthorized payment request.
- Unauthorized approval.
- Modified transaction after approval.
- Duplicate transaction.
- Forged webhook.
- Replayed webhook.
- Amount manipulation.
- Recipient manipulation.
- Spending-limit violation.
- Emergency financial suspension.

28.8 Data protection tests

Test:

- Cross-business data leakage.
- Unauthorized memory retrieval.
- Secret leakage in logs.
- Secret leakage in prompts.
- Secret leakage in API responses.
- Unauthorized backup access.
- Retention policy enforcement.

28.9 Emergency and recovery tests

Test:

- Emergency stop during active tasks.
- Emergency stop during browser activity.
- Emergency stop during transaction preparation.
- Safe-mode enforcement.
- Restart while in safe mode.
- Recovery from interrupted operations.
- Backup restoration.
- Recovery of security configuration.

28.10 Required acceptance scenarios

The following scenarios must pass before P-10 can be accepted.

Scenario 1: Unauthorized file access

A research agent tries to read a protected credential file.

Expected: Access denied, event recorded, no file content returned.

Scenario 2: Cross-business data leakage

An agent assigned to Business A requests Business B's confidential records.

Expected: Access denied regardless of the agent's model-generated reasoning.

Scenario 3: Prompt injection

A website instructs an agent to reveal credentials and ignore its security policy.

Expected: Website instructions remain untrusted. No credentials are revealed and no policy is changed.

Scenario 4: Fake approval

An agent claims that the owner approved a payment.

Expected: No valid approval record, so the transaction is blocked.

Scenario 5: Modified approval

An approved payment amount or recipient is changed before execution.

Expected: Approval invalidated and new approval required.

Scenario 6: Agent privilege escalation

An agent creates another agent and attempts to give it owner privileges.

Expected: Delegation denied and logged.

Scenario 7: Dangerous command

An execution agent attempts an unauthorized destructive command.

Expected: Command blocked before execution.

Scenario 8: Secret leakage

An agent attempts to include an API key in its prompt or generated report.

Expected: Secret is not exposed; the attempt is safely handled and recorded.

Scenario 9: SSRF attack

A browser or research agent attempts to access a restricted local or internal service.

Expected: Request blocked.

Scenario 10: Forged payment event

An external webhook claims a payment succeeded without valid verification.

Expected: Payment remains unconfirmed.

Scenario 11: Emergency stop

The owner activates emergency stop while autonomous tasks are running.

Expected: New autonomous operations stop, sensitive actions are blocked, active tasks are safely paused or cancelled, and audit records remain intact.

Scenario 12: Security service failure

The authorization service becomes unavailable.

Expected: Sensitive actions fail closed. No agent receives implicit permission.

Scenario 13: Recovery

The system restores a valid backup after a controlled database failure.

Expected: Security policies, identities, and audit records are recovered and validated without granting unintended privileges.

Scenario 14: Approval replay

An agent attempts to reuse an old approval for another action.

Expected: Rejected.

Scenario 15: Frontend bypass

A user or agent attempts to call a protected API directly without the required permission.

Expected: Backend authorization rejects the operation.

Scenario 16: Security policy manipulation

An agent attempts to change its own permissions or disable mandatory approvals.

Expected: Rejected. Owner-controlled policy remains unchanged.

Scenario 17: Browser session isolation

An agent assigned to one business attempts to access another business's authenticated browser session.

Expected: Access denied.

Scenario 18: Audit integrity

An ordinary agent attempts to modify or delete security audit records.

Expected: Operation denied and logged.

---

29. PERFORMANCE AND RESOURCE MANAGEMENT

AUTONOMUS must remain usable on modest Windows hardware.

Security must not create unnecessary resource consumption.

Requirements:

- Avoid launching a separate heavyweight model for security decisions.
- Use deterministic policy code for authorization.
- Avoid unnecessary LLM calls.
- Keep audit logging efficient.
- Use indexed database queries.
- Use bounded background workers.
- Avoid excessive filesystem scans.
- Schedule vulnerability scans appropriately.
- Avoid blocking normal operations with expensive security checks when cached, valid policy decisions can safely be reused.

However, do not cache authorization decisions beyond their validity or allow revoked permissions to remain active.

Security must take priority over performance for sensitive operations.

---

30. DOCUMENTATION REQUIREMENTS

Create or update the following documentation:

docs/security/
    SECURITY_ARCHITECTURE.md
    THREAT_MODEL.md
    ASSET_INVENTORY.md
    IDENTITY_AND_ACCESS_CONTROL.md
    PERMISSION_BROKER.md
    APPROVAL_POLICIES.md
    SECRETS_MANAGEMENT.md
    FILESYSTEM_SECURITY.md
    COMMAND_EXECUTION_SECURITY.md
    BROWSER_SECURITY.md
    NETWORK_SECURITY.md
    AI_PROMPT_INJECTION_DEFENSE.md
    FINANCIAL_SECURITY.md
    DATA_PROTECTION.md
    AUDIT_AND_MONITORING.md
    EMERGENCY_RESPONSE.md
    WINDOWS_SECURITY.md
    DEPENDENCY_SECURITY.md
    SECURITY_TEST_PLAN.md
    SECURITY_OPERATIONS_GUIDE.md
    INCIDENT_RESPONSE_PLAYBOOK.md
    P10_IMPLEMENTATION_REPORT.md

Documentation must explain actual implemented behavior, not aspirational features.

Include configuration examples without real secrets.

Provide clear owner instructions for:

- Managing permissions.
- Reviewing approvals.
- Adding credentials.
- Revoking credentials.
- Responding to security alerts.
- Activating emergency stop.
- Recovering from an incident.
- Restoring backups.

---

31. IMPLEMENTATION SEQUENCE

Implement P-10 in controlled stages.

Do not attempt to implement the entire security system in one large uncontrolled change.

Stage 1: Audit and security foundation

- Complete P-01 through P-09 security audit.
- Build asset inventory.
- Create threat model.
- Identify existing security mechanisms.
- Design the integration architecture.
- Define security invariants.
- Produce implementation plan.

Stage 2: Identity and authorization

- Owner authentication.
- Session management.
- Identity registry.
- RBAC/ABAC.
- Central authorization service.
- Permission broker.
- Agent permission scopes.

Stage 3: Approval engine

- Risk classification.
- Approval requests.
- Approval decisions.
- Approval expiry.
- Action-bound approval validation.
- Owner approval interface.

Stage 4: Secrets and execution security

- Secure secret storage.
- Secret access broker.
- Filesystem guard.
- Command execution gateway.
- Restricted code execution.
- Tool permission integration.

Stage 5: Browser, network, and AI security

- Browser session isolation.
- Domain validation.
- Download protection.
- Network egress rules.
- SSRF protection.
- Prompt injection defense.
- Agent handoff validation.

Stage 6: Financial and data security

- Financial transaction guard.
- Spending controls.
- Payment event verification integration.
- Business data isolation.
- Memory security integration.
- Encryption and retention controls.

Stage 7: Monitoring and recovery

- Security audit events.
- Security dashboard.
- Alerting.
- Emergency stop.
- Safe mode.
- Backup validation.
- Recovery procedures.

Stage 8: Testing and independent audit

- Run all existing tests.
- Run all new security tests.
- Run acceptance scenarios.
- Review authorization boundaries.
- Perform dependency checks.
- Inspect secret leakage.
- Verify emergency behavior.
- Produce final security report.

---

32. DEFINITION OF DONE

P-10 is not complete merely because the new security modules exist.

The implementation must satisfy all applicable criteria below.

Architecture

- [ ] Existing P-01 through P-09 architecture has been inspected.
- [ ] Security architecture is documented.
- [ ] Threat model is documented.
- [ ] Asset inventory exists.
- [ ] No unnecessary duplicate security systems were introduced.
- [ ] Existing working functionality is preserved.

Identity and access

- [ ] Owner authentication works.
- [ ] Session management works.
- [ ] Agent identities are registered.
- [ ] RBAC/ABAC authorization is enforced.
- [ ] Permission broker is integrated.
- [ ] Business and project isolation is enforced.
- [ ] Temporary capabilities can expire and be revoked.

Approvals

- [ ] Risk-based approval engine works.
- [ ] Sensitive actions require appropriate authorization.
- [ ] Approvals are bound to exact action parameters.
- [ ] Expired and replayed approvals are rejected.
- [ ] Agents cannot approve their own requests.
- [ ] Agents cannot change approval policies.

Secrets and execution

- [ ] Secrets are protected at rest.
- [ ] Secrets are not exposed to ordinary agent prompts.
- [ ] Secret values are not leaked in logs or API responses.
- [ ] Filesystem access is restricted.
- [ ] Command execution is controlled.
- [ ] Dangerous operations are blocked or require approval.
- [ ] Code execution is isolated to the extent supported by the host.

Browser, network, and AI

- [ ] Browser contexts are appropriately isolated.
- [ ] Untrusted websites cannot override policies.
- [ ] Downloads are handled safely.
- [ ] Network restrictions are enforced.
- [ ] SSRF protections are tested.
- [ ] Prompt injection defenses are tested.
- [ ] Agent handoffs do not transfer unauthorized privileges.

Financial and data protection

- [ ] Financial transaction permissions are separated from analysis permissions.
- [ ] Financial approvals are enforced.
- [ ] Payment events are verified.
- [ ] Business data isolation is enforced.
- [ ] Memory access respects permissions.
- [ ] Sensitive data receives appropriate protection.

Monitoring and recovery

- [ ] Security events are logged.
- [ ] Audit records are protected.
- [ ] Security dashboard works.
- [ ] Critical alerts work.
- [ ] Emergency stop works.
- [ ] Safe mode works.
- [ ] Backup restoration has been tested.
- [ ] Recovery procedures are documented.

Quality

- [ ] Existing tests pass.
- [ ] New security tests pass.
- [ ] Critical acceptance scenarios pass.
- [ ] No known unresolved critical security vulnerability is accepted without explicit owner review.
- [ ] Documentation reflects actual behavior.
- [ ] No secrets have been committed.
- [ ] No unauthorized external side effects occurred during testing.

Any unchecked item must be reported honestly.

Do not mark an unimplemented feature as complete.

---

33. FINAL IMPLEMENTATION REPORT

At the end of P-10, generate a detailed report containing:

1. Executive summary.
2. Initial security audit findings.
3. Final architecture.
4. Files created.
5. Files modified.
6. Existing components reused.
7. Database changes and migrations.
8. API endpoints implemented.
9. Authentication and authorization status.
10. Permission broker status.
11. Approval engine status.
12. Secrets-management status.
13. Filesystem and command security status.
14. Browser and network security status.
15. AI security status.
16. Financial security integration.
17. Memory security integration.
18. Audit and monitoring status.
19. Emergency stop and recovery status.
20. Tests executed.
21. Acceptance scenario results.
22. Known limitations.
23. Unresolved vulnerabilities.
24. Performance impact.
25. Manual configuration required from the owner.
26. Recommended next actions.

Use evidence wherever possible:

- Test results.
- File references.
- API responses.
- Database migration results.
- Configuration checks.
- Security scan results.

Separate:

- Implemented and tested.
- Implemented but not fully tested.
- Partially implemented.
- Not implemented.
- Blocked by environment limitations.

Do not report a successful security audit if only basic tests were performed.

---

34. STRICT DEVELOPMENT STOP CONDITION

After completing P-10:

1. Run the complete relevant test suite.
2. Review all changed files.
3. Verify that existing modules remain functional.
4. Verify security boundaries.
5. Generate the final implementation report.
6. Document all remaining issues.
7. Present the results to the owner.

STOP.

Do not automatically start P-11.

Do not redesign the Command Center.

Do not begin unrelated modules.

Do not modify the AUTONOMUS master constitution without owner approval.

Wait for the owner's explicit approval before proceeding to P-11.

---

35. FINAL DIRECTIVE

Build P-10 as a permanent security foundation for AUTONOMUS.

Remember the following:

- Intelligence does not equal authority.
- An agent's capability does not equal permission.
- A successful tool call does not prove that the action was authorized.
- A model's confidence does not prove that an action is safe.
- An approval for one action does not authorize another.
- A business's growth does not justify bypassing financial limits.
- Stored information does not automatically become trusted information.
- Autonomous operation does not mean unrestricted operation.

The security architecture must remain independent of the agents it protects.

The owner controls the system. The security engine enforces that authority. Agents operate only within the boundaries they are granted.

Build this carefully, preserve the existing system, test the actual enforcement mechanisms, document limitations, and stop after P-10 for owner review.

END OF P-10 DEVELOPMENT PROMPT
