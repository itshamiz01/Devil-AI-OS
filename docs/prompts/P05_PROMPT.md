AUTONOMUS P-05: UNIVERSAL DIGITAL EXECUTION ENGINE

Master Development Prompt | Version 1.0

Project: AUTONOMUS | Autonomous AI Business Operating System
Phase: P-05
Module: Universal Digital Execution Engine
Platform: Windows-first
Backend: Python + FastAPI
Frontend: React + TypeScript
AI Infrastructure: Hybrid, local-first, provider-independent
Primary Objective: Enable approved AI agents to perform real digital work through a secure, controlled, auditable execution infrastructure.

---

1. YOUR ROLE

Act as a principal software architect, senior Python engineer, browser automation specialist, Windows automation engineer, API integration engineer, sandbox security specialist, and autonomous systems developer.

Your responsibility is to implement P-05: Universal Digital Execution Engine inside the existing AUTONOMUS repository.

You are not building another chatbot, another agent framework, or a collection of unrelated automation scripts.

You are building the execution infrastructure that allows AUTONOMUS to translate approved tasks into real digital actions.

The system must support authorized interaction with:

1. Local files and directories.
2. Desktop applications.
3. Web browsers.
4. Websites and online platforms.
5. REST APIs and other approved integrations.
6. Sandboxed code environments.
7. Digital document workflows.
8. Data processing workflows.
9. Scheduled and multi-step digital operations.
10. Other approved execution adapters added in the future.

The engine must be modular, extensible, observable, resource-aware, and secure.

An AI agent must never receive unrestricted access to the computer merely because it has been assigned a task.

---

2. AUTONOMUS PROJECT CONTEXT

AUTONOMUS is a Windows-first Autonomous AI Business Operating System.

Its mission is to discover legitimate business opportunities, validate demand, create digital products and services, operate business workflows, acquire customers, deliver value, analyze financial results, and improve business operations.

The development roadmap is:

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
- P-10: Security and Governance Engine
- P-11: Premium Command Center
- P-12: Autonomous Operations Engine
- P-13: Multi-business Coordination
- P-14: Integration and System Audit
- P-15: Performance, Reliability and Production Readiness
- P-16: Autonomous AI Economy Expansion

P-05 depends on the existing architecture established in P-01, P-02, P-03, and P-04.

Locked decisions

AI infrastructure

- Local AI by default.
- Hybrid local/cloud architecture.
- Optional cloud models through provider adapters.
- No mandatory paid APIs.
- Shared model infrastructure.
- Provider-independent model routing.

Autonomy

- Controlled autonomy.
- Agents can execute approved actions within their assigned permissions.
- Sensitive actions require approval.
- Agents cannot grant themselves additional permissions.
- Agents cannot modify core security policies.
- The human owner retains ultimate authority.

Platform

- Windows-first desktop implementation.
- Future cloud and multi-machine expansion.
- Modular architecture.
- Local-first development.

Hardware considerations

The previously audited development machine has approximately:

- Intel Core i7-4712HQ.
- 16 GB RAM.
- NVIDIA Quadro K1100M 2 GB.
- Older NVIDIA compute architecture.

Design the engine to run efficiently on CPU-based systems.

Avoid unnecessary heavyweight services, multiple browser instances, excessive worker processes, and resource-intensive automation frameworks.

---

3. FIRST RULE: AUDIT THE EXISTING REPOSITORY

Do not immediately create a new execution framework.

Inspect the complete existing repository.

Review:

- P-01 core operating system.
- P-02 Master Intelligence Engine.
- P-03 Opportunity Discovery Engine.
- P-04 Dynamic Agent Factory.
- Agent registry and templates.
- Agent capability definitions.
- Permission and approval services.
- Task queue and workflow engine.
- Shared model router.
- Database architecture.
- Configuration management.
- Logging and audit records.
- Existing filesystem tools.
- Existing code execution facilities.
- Existing HTTP clients.
- Existing browser integrations.
- Existing Windows integrations.
- Frontend architecture.
- Existing tests.
- Dependencies and versions.
- Current security controls.

Identify whether any execution-related tools already exist.

Do not duplicate working functionality.

Create:

"docs/audits/P05_PRE_IMPLEMENTATION_AUDIT.md"

Include:

1. Existing execution capabilities.
2. Existing components that can be reused.
3. Missing execution capabilities.
4. Existing security controls.
5. Security vulnerabilities and limitations.
6. Existing agent-to-tool interfaces.
7. Database requirements.
8. Required integrations.
9. Resource constraints.
10. Compatibility risks.
11. Proposed implementation architecture.

Then create:

"docs/audits/P05_IMPLEMENTATION_PLAN.md"

Include the implementation sequence, architecture, module boundaries, APIs, permission checks, execution lifecycle, testing strategy, migration strategy, and rollback strategy.

Do not replace a working component simply because another library is more familiar.

---

4. CORE MISSION

Build a centralized execution engine that receives approved tasks from AUTONOMUS agents and performs them through registered execution tools.

The engine must support this lifecycle:

1. Agent receives a task.
2. Agent determines the actions needed.
3. Agent submits an execution request.
4. Execution engine validates the request.
5. Capability and permission services verify authorization.
6. Risk classification determines the approval requirement.
7. Resource manager checks availability.
8. Required human approval is obtained.
9. Execution plan is validated.
10. An appropriate execution adapter is selected.
11. The action runs in the permitted environment.
12. Execution results are collected.
13. Evidence is recorded.
14. The result is validated.
15. Task status is updated.
16. The agent receives a structured result.
17. Audit history is preserved.

Every step must be traceable.

The agent must not be able to bypass the execution engine by directly accessing tools or invoking unrestricted operating-system commands.

---

5. UNIVERSAL EXECUTION ARCHITECTURE

Implement a provider-independent execution architecture.

The execution engine should not be tightly coupled to a particular browser, desktop automation library, API provider, or code execution framework.

Use a central execution service with specialized adapters.

5.1 Required architectural components

Create or extend the following logical components:

A. Execution Request Manager

Receives execution requests from authorized agents.

B. Execution Policy Engine

Determines whether an action is allowed, restricted, approval-required, or prohibited.

C. Capability Validator

Checks whether the requesting agent possesses the required capability.

D. Execution Planner

Validates the requested action sequence and dependencies.

E. Tool Registry

Stores available execution tools and their requirements.

F. Adapter Manager

Routes requests to the appropriate execution adapter.

G. Execution Scheduler

Controls execution concurrency, priority, and resource availability.

H. Execution Environment Manager

Manages isolated workspaces and execution environments.

I. Approval Manager Integration

Obtains and verifies human approval for sensitive actions.

J. Evidence Collector

Captures execution outputs and verifiable evidence.

K. Result Validator

Checks whether the requested outcome was actually achieved.

L. Execution Audit Service

Records all relevant actions, decisions, errors, and approvals.

M. Recovery Manager

Handles interrupted workflows, failures, safe retries, and compensation actions.

These components should remain logically separated even if they are initially implemented in a single Python application.

---

6. UNIVERSAL EXECUTION REQUEST FORMAT

Every execution request must follow a validated schema.

Create a standard execution request model containing:

- Execution request ID.
- Requesting agent ID.
- Task ID.
- Business/project ID, where applicable.
- Tool ID.
- Adapter type.
- Action name.
- Action parameters.
- Input references.
- Required capabilities.
- Requested scope.
- Risk classification.
- Priority.
- Timeout.
- Retry policy.
- Expected output schema.
- Approval reference.
- Idempotency key.
- Creation timestamp.
- Expiration timestamp.

The execution request must distinguish:

- Requested action.
- Approved action.
- Actual executed action.
- Verified outcome.

Never assume these are identical.

6.1 Execution outcomes

Use standardized outcomes:

- ACCEPTED
- VALIDATING
- AWAITING_APPROVAL
- QUEUED
- RUNNING
- COMPLETED
- COMPLETED_WITH_WARNINGS
- FAILED
- REJECTED
- CANCELLED
- TIMED_OUT
- INTERRUPTED
- REQUIRES_HUMAN_ACTION
- REQUIRES_RECONCILIATION

The engine must not return COMPLETED merely because a tool returned without throwing an exception.

Completion requires validation against the expected outcome.

---

7. EXECUTION TOOL REGISTRY

Build a central registry for all execution tools.

Each registered tool must contain:

- Tool ID.
- Tool name.
- Description.
- Category.
- Version.
- Adapter type.
- Input schema.
- Output schema.
- Required capabilities.
- Risk classification.
- Required approval level.
- Supported operating systems.
- Resource requirements.
- Timeout defaults.
- Retry eligibility.
- Idempotency support.
- Availability status.
- Health status.
- Configuration reference.

Tool lifecycle

Support:

- REGISTERED
- VALIDATING
- AVAILABLE
- DEGRADED
- DISABLED
- DEPRECATED
- REMOVED

A tool must not become AVAILABLE until its configuration and health checks pass.

Tool discovery

Agents may discover available tools through a restricted registry query.

They should receive only:

- Tool descriptions.
- Supported actions.
- Input requirements.
- Output contracts.
- Required capabilities.
- Risk classifications.

Do not expose internal credentials, sensitive configuration, or secret values through tool discovery.

Tool registration

Support an adapter interface so future modules can register additional execution capabilities without modifying the core engine.

New external or high-risk tools must undergo authorization and validation before being activated.

---

8. EXECUTION POLICY AND RISK CLASSIFICATION

This is a mandatory security boundary.

Every execution action must be evaluated before execution.

Implement four risk categories.

Risk 0: Safe internal operations

Examples:

- Reading an approved project file.
- Listing an approved workspace directory.
- Creating an internal report.
- Processing local non-sensitive data.
- Running a predefined internal analysis.
- Reading approved database records.

These may execute autonomously when the agent has the required permissions.

Risk 1: Controlled operations

Examples:

- Modifying an existing project file.
- Creating a folder.
- Generating documents.
- Running approved code in a sandbox.
- Interacting with an approved website in read-only mode.
- Calling an authorized read-only API.

These may execute autonomously within predefined scopes and limits.

Risk 2: Sensitive or external operations

Examples:

- Publishing a public post.
- Sending an email or message.
- Uploading a document to an external platform.
- Changing account settings.
- Creating an external resource.
- Submitting a form.
- Modifying a remote record.
- Running code that changes a controlled external environment.

Require owner approval unless a specific, narrowly scoped standing authorization has been configured.

Risk 3: Prohibited or specially governed operations

Examples:

- Accessing private keys or raw passwords.
- Disabling security restrictions.
- Unrestricted filesystem access.
- Unrestricted remote code execution.
- Unauthorized access to external accounts.
- Bypassing access controls.
- Fraudulent or unlawful activity.
- Unauthorized financial transactions.
- Deleting or modifying audit records.
- Circumventing platform security mechanisms.

These must be rejected by the normal execution system.

A high-priority task must never override risk classification.

8.1 Policy enforcement

Implement deterministic policy checks.

Do not rely on the LLM to decide whether its own action is authorized.

The execution engine must independently verify:

1. Agent identity.
2. Agent status.
3. Assigned task.
4. Required capabilities.
5. Requested scope.
6. Tool status.
7. Risk category.
8. Approval status.
9. Resource limits.
10. Policy restrictions.

If any required condition fails, execution must not proceed.

---

9. FILESYSTEM EXECUTION ADAPTER

Implement a controlled filesystem adapter for Windows.

The adapter should support:

- List directory contents.
- Read approved files.
- Create files.
- Write files.
- Append content.
- Copy files.
- Move files.
- Rename files.
- Create directories.
- Search within approved workspaces.
- Retrieve file metadata.
- Generate file hashes.
- Delete files under explicit policy.

9.1 Workspace isolation

Create managed workspaces.

Example conceptual structure:

AUTONOMUS/
  workspaces/
    shared/
    projects/
    businesses/
    agent_workspaces/
    temporary/
    quarantine/

Adapt this to the actual repository.

Each agent should receive access only to its authorized workspace.

Do not allow arbitrary access to:

- Windows system directories.
- Browser profile folders.
- Credential stores.
- Other users' directories.
- Unapproved project directories.
- Application configuration files.
- Secret storage locations.

9.2 Path security

Implement robust path validation.

Protect against:

- Directory traversal.
- Absolute path injection.
- Symlink or junction escapes.
- Windows drive-letter manipulation.
- UNC network path abuse.
- Alternate data stream abuse.
- Path normalization bypass.
- Unauthorized access through symbolic links.
- File extension spoofing where relevant.

Resolve and validate paths against approved workspace roots.

Do not rely only on string prefix comparisons.

9.3 File integrity

For important file operations:

- Record original hash where practical.
- Record resulting hash.
- Record source and destination.
- Record operation type.
- Record agent ID.
- Record approval reference.
- Record timestamp.

For overwrite operations, create a backup or recoverable snapshot where feasible.

For deletion, use a controlled quarantine or reversible deletion mechanism when practical.

Permanent deletion must require a stronger approval policy.

9.4 File operations must be atomic where possible

Avoid partially written files.

Use temporary files and atomic replacement where supported.

If an operation fails, preserve the previous valid version whenever possible.

---

10. SANDBOXED CODE EXECUTION ADAPTER

Build a controlled code execution subsystem.

This is not unrestricted access to the host operating system.

The system should eventually support approved languages such as:

- Python.
- JavaScript or Node.js.
- PowerShell under strict restrictions, if explicitly authorized.
- Other languages through additional adapters.

Implement only the languages that can be safely supported by the current environment.

10.1 Execution isolation

Every code execution request must run in an isolated workspace.

The execution environment should have:

- Dedicated temporary directory.
- Controlled input files.
- Controlled output directory.
- Execution timeout.
- CPU/resource limits where supported.
- Process limits where supported.
- Restricted environment variables.
- Controlled network access.
- Limited filesystem visibility.
- Process termination handling.
- Output capture.
- Error capture.

10.2 Windows isolation strategy

Inspect the actual Windows environment and select the safest practical isolation mechanism.

Evaluate:

- Windows Job Objects.
- Restricted process tokens.
- Windows Sandbox where available.
- Container-based isolation where available and appropriate.
- Dedicated low-privilege execution accounts.
- Other compatible isolation mechanisms.

Do not claim strong sandbox isolation if the implementation only launches a normal subprocess with a timeout.

If the machine cannot support a secure isolation mechanism, label the capability accordingly and keep it disabled for untrusted code.

10.3 Execution controls

Implement:

- Execution timeout.
- Maximum output size.
- Maximum input size.
- Allowed executable list.
- Working-directory restrictions.
- Process-tree termination.
- Controlled environment variables.
- Restricted imports or execution policies where applicable.
- Network restrictions.
- File access restrictions.

Treat language-level restrictions as supplementary safeguards, not as the primary security boundary.

10.4 Dangerous command restrictions

Block or require explicit owner authorization for commands that:

- Modify system security settings.
- Change user privileges.
- Access credentials.
- Install unapproved software.
- Disable antivirus or security controls.
- Modify boot configuration.
- Change firewall rules.
- Delete protected files.
- Access unrestricted network resources.
- Launch unauthorized background processes.

Do not let an agent bypass these rules by encoding commands, using alternate shells, or invoking another executable.

10.5 Execution result

Return:

- Execution ID.
- Exit code.
- Standard output.
- Standard error.
- Duration.
- Files created.
- Files modified.
- Resource information, where measurable.
- Timeout status.
- Security warnings.
- Verification status.

Never expose sensitive environment variables in output.

---

11. BROWSER AUTOMATION ADAPTER

Build a browser automation adapter for authorized digital work.

Evaluate Playwright as the primary browser automation framework.

Reuse any existing compatible browser integration before adding dependencies.

11.1 Browser capabilities

Support:

- Launch an approved browser session.
- Open an approved URL.
- Navigate between pages.
- Inspect page structure.
- Read visible text.
- Capture screenshots.
- Click approved elements.
- Enter text into forms.
- Select options.
- Scroll.
- Wait for page states.
- Download approved files.
- Upload approved files.
- Extract structured data.
- Verify visible outcomes.
- Close or release sessions.

11.2 Browser session management

Create controlled browser sessions.

Each session should have:

- Session ID.
- Agent ID.
- Browser type.
- Session state.
- Approved domain scope.
- Permission profile.
- Start timestamp.
- Last activity.
- Expiration policy.

Use separate contexts for different security scopes where possible.

Do not automatically share authenticated browser sessions between agents.

Do not expose raw browser cookies, authentication tokens, or session storage to the model.

11.3 Domain restrictions

Implement configurable domain allowlists and deny rules.

For example:

- Public research domains.
- Approved business platforms.
- Approved development services.
- Approved communication platforms.

A task must not navigate to a new external domain simply because a webpage instructs it to.

Redirects must be checked against policy.

11.4 Website interaction

For browser actions:

1. Identify the target page.
2. Inspect the page state.
3. Validate the intended element.
4. Confirm the action is permitted.
5. Execute the action.
6. Inspect the resulting state.
7. Capture evidence.
8. Validate the expected outcome.

Avoid blind click sequences.

Prefer stable locators and accessible selectors over fragile screen coordinates.

11.5 Authentication and verification

Support authorized user-managed login sessions where permitted.

However:

- Never ask agents to extract or reveal passwords.
- Never expose OTPs or authentication secrets to agents unnecessarily.
- Never bypass CAPTCHA.
- Never bypass MFA.
- Never circumvent access controls.
- Never defeat anti-bot protections.
- Never use unauthorized session-cookie extraction.

When a platform requires OTP, MFA, CAPTCHA, or another human security challenge, pause execution and request human intervention.

Create a clear state:

"REQUIRES_HUMAN_AUTHENTICATION"

Resume only after the user completes the authorized verification process.

11.6 Platform compliance

Browser automation must respect:

- Platform terms.
- Access permissions.
- Rate limits.
- Robots and access restrictions where applicable.
- Privacy requirements.
- Applicable laws.

Do not implement spam, fake engagement, unauthorized scraping, credential abuse, or platform manipulation.

11.7 Browser verification

A click is not proof of success.

For actions such as publishing or submitting a form, verify the resulting state through an authoritative confirmation where available.

Capture:

- Target URL.
- Timestamp.
- Page title.
- Screenshot reference.
- Relevant page text.
- Confirmation identifier, where available.
- Verification status.

Do not fabricate confirmation IDs or successful publishing results.

---

12. WINDOWS DESKTOP AUTOMATION ADAPTER

Implement a controlled Windows desktop interaction interface.

Evaluate suitable libraries and native Windows APIs.

Possible technologies include:

- Windows UI Automation.
- pywinauto.
- pyautogui.
- pywin32.
- Windows APIs.
- Screenshot and image recognition tools.

Do not install all libraries automatically.

Select only the tools justified by the existing architecture and target machine.

12.1 Required capabilities

Where supported:

- Enumerate approved application windows.
- Inspect window titles.
- Identify active windows.
- Switch between approved windows.
- Capture screenshots.
- Click coordinates or recognized controls.
- Type text.
- Send keyboard shortcuts.
- Scroll.
- Inspect UI Automation elements.
- Detect dialogs.
- Monitor application state.
- Close an application safely.
- Verify resulting UI state.

12.2 Desktop safety

The adapter must not blindly interact with whichever window happens to be active.

Before an action:

1. Identify the target application.
2. Verify its window.
3. Check whether the requested interaction is permitted.
4. Confirm the expected UI state.
5. Perform the action.
6. Verify the resulting state.

Use semantic UI Automation selectors whenever possible.

Use coordinates only when semantic interaction is unavailable and the target state is verified.

12.3 Sensitive desktop actions

Require owner approval for sensitive actions such as:

- Sending messages.
- Submitting forms.
- Confirming purchases.
- Changing account settings.
- Installing applications.
- Deleting important data.
- Modifying security settings.
- Performing irreversible operations.

Do not automatically approve UAC prompts or elevate privileges.

Do not bypass Windows security dialogs.

12.4 Emergency interruption

Provide an emergency mechanism that can:

- Stop new desktop automation actions.
- Interrupt eligible running workflows.
- Release automation locks.
- Restore control to the user.

The owner must retain the ability to use the computer.

---

13. API AND EXTERNAL SERVICE ADAPTER

Build a generic API execution framework.

Do not create hardcoded integrations for every future platform.

Implement a reusable adapter supporting approved HTTP services.

13.1 Supported operations

Where authorized:

- GET.
- POST.
- PUT.
- PATCH.
- DELETE.

13.2 API request controls

Every request must define:

- Approved host.
- Endpoint.
- HTTP method.
- Request schema.
- Authentication reference.
- Timeout.
- Retry policy.
- Rate limit.
- Maximum response size.
- Expected response schema.

13.3 Authentication

Use a secure credential broker or secret-management interface.

Agents must never receive raw API keys or secret values.

The API adapter should obtain the credential internally, execute the authorized request, and return only the necessary response.

Do not log authorization headers or sensitive request bodies.

13.4 Network protection

Protect against:

- Server-side request forgery.
- Localhost access abuse.
- Private network access abuse.
- DNS rebinding where practical.
- Redirect-based domain bypass.
- Unrestricted outbound requests.
- Excessive request volume.
- Oversized responses.

Block access to internal and protected network targets unless explicitly authorized by a narrowly scoped administrative policy.

Revalidate destination addresses after redirects and DNS resolution where applicable.

13.5 API reliability

Implement:

- Timeouts.
- Rate limiting.
- Retry with exponential backoff for safe operations.
- Circuit breakers where appropriate.
- Structured response parsing.
- Error classification.
- Idempotency support for non-read operations where the external service supports it.

Never blindly retry a non-idempotent POST or other external action.

---

14. DIGITAL DOCUMENT AND DATA PROCESSING ADAPTERS

Provide reusable execution capabilities for ordinary business workflows.

Possible supported operations include:

Documents

- Create text documents.
- Create Markdown files.
- Generate reports.
- Read PDFs.
- Extract document text.
- Convert supported document formats.
- Create spreadsheets.
- Update spreadsheet data.
- Generate presentations where supported.

Data

- Read CSV files.
- Validate datasets.
- Transform structured data.
- Generate summaries.
- Run calculations.
- Produce reports.
- Export approved results.

Media

- Organize media files.
- Inspect metadata.
- Convert supported formats.
- Generate file manifests.
- Validate output files.

Use libraries compatible with the existing project and Windows environment.

Do not add unnecessary dependencies.

Respect copyright, privacy, licensing, and access restrictions.

For large documents or datasets, use bounded processing and streaming where appropriate.

---

15. MULTI-STEP EXECUTION WORKFLOW ENGINE

A major requirement is the ability to execute sequences of digital actions rather than only individual commands.

Build a reusable workflow execution mechanism.

Example:

Workflow: Generate and save a research report

1. Receive a research task.
2. Read approved project inputs.
3. Perform authorized research.
4. Validate collected data.
5. Generate a report.
6. Save the report to the approved workspace.
7. Verify the saved file.
8. Generate an execution summary.
9. Return the file reference to the requesting agent.

Another example:

Workflow: Update an approved website page

1. Identify the target website.
2. Verify the authenticated session.
3. Retrieve the existing page.
4. Prepare the proposed changes.
5. Validate the proposed content.
6. Obtain required approval.
7. Submit the update.
8. Verify the resulting page.
9. Capture evidence.
10. Report the outcome.

These examples describe workflow capabilities, not permission to modify every website or publish content automatically.

15.1 Workflow definitions

Each workflow should contain:

- Workflow ID.
- Name.
- Version.
- Description.
- Input schema.
- Output schema.
- Step definitions.
- Dependencies.
- Required capabilities.
- Risk classifications.
- Approval requirements.
- Timeout.
- Retry policy.
- Compensation strategy.
- Validation rules.

15.2 Workflow execution

Support:

- Sequential steps.
- Conditional branches.
- Parallel independent steps.
- Dependency management.
- Checkpoints.
- Timeouts.
- Cancellation.
- Failure recovery.
- Human intervention.
- Result aggregation.

Do not implement unrestricted arbitrary workflow code.

Use validated workflow definitions and approved execution adapters.

15.3 Workflow state

Use persistent states such as:

- DRAFT
- VALIDATING
- APPROVED
- QUEUED
- RUNNING
- PAUSED
- AWAITING_APPROVAL
- AWAITING_HUMAN
- COMPLETED
- FAILED
- CANCELLED
- RECOVERY_REQUIRED

A workflow must be recoverable after an application restart where its actions and state permit safe recovery.

---

16. EXECUTION TRANSACTIONS, CHECKPOINTS AND RECOVERY

Digital operations may fail halfway through a sequence.

The engine must not assume that every action can be rolled back.

Implement a recovery model.

16.1 Checkpoints

For multi-step workflows, record:

- Completed steps.
- Current step.
- Input references.
- Output references.
- Execution IDs.
- Approval references.
- Evidence references.
- Timestamp.
- Recovery status.

16.2 Idempotency

Support idempotency keys for operations where repeating an action could create duplicates.

Examples:

- Creating a file.
- Creating a remote record.
- Submitting an API request.
- Uploading a document.
- Publishing content.

Use deterministic idempotency records where possible.

16.3 Compensation actions

Where safe, define a compensating action.

Examples:

- Restore a previous file version.
- Remove a temporary workspace.
- Revert an approved local configuration change.
- Cancel a pending operation.

Do not claim a compensation action is a true rollback when the external system has already performed an irreversible operation.

For external actions that cannot be safely reversed, require reconciliation and human intervention.

16.4 Recovery after restart

When AUTONOMUS restarts:

1. Identify incomplete executions.
2. Retrieve their last persisted state.
3. Determine whether the previous operation may have succeeded.
4. Check for duplicate-action risk.
5. Resume only when safe.
6. Otherwise enter REQUIRES_RECONCILIATION.
7. Notify the owner where required.

Never blindly repeat an interrupted external action.

---

17. HUMAN APPROVAL AND INTERVENTION SYSTEM

Integrate with the existing approval infrastructure from earlier phases.

Do not build a second independent approval system.

Approval request details

An approval request must show:

- Requesting agent.
- Business or project.
- Intended action.
- Target application or service.
- Exact scope.
- Expected result.
- Risk classification.
- Data involved.
- Possible consequences.
- Whether the action is reversible.
- Expiration time.
- Evidence available before execution.

The owner must be able to:

- Approve.
- Reject.
- Request changes.
- Pause.
- Cancel.
- Require additional verification.

Standing authorization

Allow the owner to configure narrowly scoped standing authorization for repetitive, low-risk operations.

For example:

- Read-only access to an approved research domain.
- Writing files inside a specific project workspace.
- Running a predefined report workflow.
- Updating a designated internal file.

Standing authorization must specify:

- Action type.
- Scope.
- Agent or role.
- Limits.
- Expiration.
- Revocation conditions.

Do not create unlimited standing authorization.

---

18. RESOURCE MANAGEMENT AND EXECUTION SCHEDULING

P-05 must work within the existing hardware constraints.

Implement a central execution scheduler.

Track where measurable:

- CPU utilization.
- RAM usage.
- Active browser sessions.
- Active subprocesses.
- Running workflows.
- API request concurrency.
- File-processing workload.
- Model inference concurrency.
- Queue length.
- Execution duration.

Scheduling rules

- Respect P-01 task priorities.
- Respect P-04 agent limits.
- Prevent duplicate execution.
- Limit concurrent browser sessions.
- Limit code execution processes.
- Avoid unnecessary model inference.
- Release completed execution resources.
- Queue low-priority tasks during resource pressure.
- Prevent resource-intensive tasks from blocking critical system functions.

Use configurable resource ceilings.

When resources are exhausted, return a structured resource-limit result instead of crashing the application.

---

19. DATABASE DESIGN

Inspect existing database models before creating new tables.

Reuse compatible existing records.

The following are required logical entities.

execution_requests

- id
- task_id
- agent_id
- tool_id
- adapter_type
- action_name
- input_reference
- request_payload
- requested_scope
- risk_level
- approval_reference
- idempotency_key
- status
- created_at
- started_at
- completed_at

execution_tools

- id
- name
- description
- adapter_type
- version
- capability_requirements
- risk_level
- status
- health_status
- created_at
- updated_at

execution_runs

- id
- execution_request_id
- worker_id
- status
- started_at
- completed_at
- exit_code
- result_summary
- error_category
- resource_usage

execution_evidence

- id
- execution_run_id
- evidence_type
- evidence_reference
- content_hash
- verification_status
- created_at

execution_workspaces

- id
- workspace_name
- owner_type
- owner_id
- root_path
- permission_scope
- status
- created_at

browser_sessions

- id
- agent_id
- browser_type
- allowed_domains
- permission_scope
- status
- created_at
- last_activity
- expires_at

workflow_definitions

- id
- name
- version
- description
- definition_json
- status
- created_at
- updated_at

workflow_runs

- id
- workflow_id
- workflow_version
- requesting_agent_id
- task_id
- status
- current_step
- checkpoint_data
- started_at
- completed_at

workflow_step_runs

- id
- workflow_run_id
- step_id
- execution_run_id
- status
- input_reference
- output_reference
- error_details
- started_at
- completed_at

execution_approvals

Only create this table if the existing approval service cannot support the required relationship.

Prefer referencing existing approval records.

execution_audit_events

- id
- execution_request_id
- execution_run_id
- actor_type
- actor_id
- event_type
- event_data
- timestamp

Use:

- Foreign keys.
- Appropriate indexes.
- Unique constraints.
- Check constraints.
- Transactions.
- Schema validation.
- Migrations.
- Historical retention policies.

Never store raw passwords, API keys, private keys, or browser authentication tokens in these tables.

---

20. BACKEND MODULE STRUCTURE

Follow the existing project architecture.

If a compatible modular structure does not exist, consider:

backend/
  execution/
    core/
    requests/
    policies/
    registry/
    adapters/
      filesystem/
      code/
      browser/
      desktop/
      api/
      documents/
      data/
    workflows/
    scheduler/
    resources/
    approvals/
    evidence/
    recovery/
    monitoring/
    schemas/
    services/
    repositories/
    tests/

Potential services:

- ExecutionRequestService
- ExecutionPolicyService
- ExecutionToolRegistry
- ExecutionAdapterManager
- ExecutionScheduler
- ExecutionResourceManager
- ExecutionEnvironmentManager
- FilesystemExecutionService
- CodeExecutionService
- BrowserExecutionService
- DesktopExecutionService
- APIExecutionService
- DocumentExecutionService
- WorkflowExecutionService
- WorkflowRecoveryService
- EvidenceCollectionService
- ExecutionResultValidator
- ExecutionAuditService

Use clean interfaces.

Keep adapter-specific implementation details out of the central execution request manager.

Do not build one enormous execution class.

---

21. API REQUIREMENTS

Implement endpoints consistent with the existing FastAPI architecture.

These are logical endpoint requirements. Adapt paths to existing conventions.

Execution requests

- "POST /api/execution/requests"
- "GET /api/execution/requests"
- "GET /api/execution/requests/{request_id}"
- "POST /api/execution/requests/{request_id}/cancel"
- "POST /api/execution/requests/{request_id}/retry"

Tool registry

- "GET /api/execution/tools"
- "GET /api/execution/tools/{tool_id}"
- "POST /api/execution/tools/register"
- "POST /api/execution/tools/{tool_id}/validate"
- "POST /api/execution/tools/{tool_id}/disable"

Filesystem

- "POST /api/execution/files/list"
- "POST /api/execution/files/read"
- "POST /api/execution/files/write"
- "POST /api/execution/files/copy"
- "POST /api/execution/files/move"
- "POST /api/execution/files/delete"

Code execution

- "POST /api/execution/code/run"
- "GET /api/execution/code/{execution_id}"
- "POST /api/execution/code/{execution_id}/cancel"

Browser

- "POST /api/execution/browser/sessions"
- "GET /api/execution/browser/sessions"
- "POST /api/execution/browser/navigate"
- "POST /api/execution/browser/inspect"
- "POST /api/execution/browser/interact"
- "POST /api/execution/browser/screenshot"
- "POST /api/execution/browser/sessions/{session_id}/close"

Desktop

- "GET /api/execution/desktop/windows"
- "POST /api/execution/desktop/screenshot"
- "POST /api/execution/desktop/action"
- "POST /api/execution/desktop/emergency-stop"

API adapter

- "POST /api/execution/api/request"

Workflows

- "GET /api/execution/workflows"
- "POST /api/execution/workflows"
- "POST /api/execution/workflows/{workflow_id}/validate"
- "POST /api/execution/workflows/{workflow_id}/run"
- "GET /api/execution/workflows/runs/{run_id}"
- "POST /api/execution/workflows/runs/{run_id}/pause"
- "POST /api/execution/workflows/runs/{run_id}/resume"
- "POST /api/execution/workflows/runs/{run_id}/cancel"

Monitoring and evidence

- "GET /api/execution/status"
- "GET /api/execution/resources"
- "GET /api/execution/runs/{run_id}/evidence"
- "GET /api/execution/audit"

Security requirements:

- Authenticate and authorize administrative endpoints.
- Enforce agent permissions server-side.
- Validate all request schemas.
- Apply pagination.
- Enforce idempotency.
- Limit request sizes.
- Protect against unauthorized local API access.
- Prevent unsafe CORS configuration.
- Do not expose secrets.
- Do not trust client-supplied agent identity without verifying it.

---

22. FRONTEND INTEGRATION

P-05 is primarily an execution infrastructure phase.

Do not build the entire P-11 Command Center.

Extend the existing frontend only where useful for operational control and testing.

Provide a functional execution monitoring interface.

Execution overview

Display:

- Total execution requests.
- Running executions.
- Queued executions.
- Completed executions.
- Failed executions.
- Pending approvals.
- Interrupted workflows.
- Active browser sessions.
- Active code executions.

Tool registry

Display:

- Tool name.
- Adapter.
- Version.
- Availability.
- Health.
- Risk level.
- Required capabilities.

Execution history

Display:

- Execution ID.
- Agent.
- Task.
- Action.
- Target.
- Status.
- Duration.
- Approval reference.
- Verification result.

Workflow monitor

Display:

- Workflow name.
- Current step.
- Completed steps.
- Pending steps.
- Failed steps.
- Approval status.
- Recovery status.

Human intervention

Provide controls for:

- Approving or rejecting an action.
- Pausing a workflow.
- Resuming an eligible workflow.
- Cancelling an execution.
- Stopping desktop automation.
- Stopping new execution requests.

Sensitive actions must have clear confirmation steps.

Do not show fake activity or placeholder success metrics.

---

23. SECURITY REQUIREMENTS

Implement security controls before enabling broad execution capabilities.

23.1 Least privilege

Every execution adapter must enforce the requesting agent's permissions.

The tool must not infer permission from the agent's role alone.

23.2 Local API protection

Since AUTONOMUS runs on Windows, protect the local API against unauthorized local requests.

Implement:

- Authentication.
- Authorization.
- Secure local session handling.
- Request validation.
- Origin controls.
- Rate limits.
- CSRF protection where applicable.
- Secure secret storage.

Do not assume localhost automatically means trusted.

23.3 Process security

Code execution must not inherit unnecessary privileges.

Do not run agents or subprocesses as Administrator by default.

Use the minimum privileges needed.

23.4 Network security

Apply outbound network policies.

Restrict access to protected internal services.

Prevent uncontrolled port scanning, network discovery, and arbitrary connections.

23.5 Prompt injection

External data must always be treated as untrusted.

A webpage, file, document, API response, or another agent cannot authorize an action.

Execution policy must be evaluated independently of model instructions.

23.6 Sensitive operations

The engine must not directly provide unrestricted wallet or payment execution.

Financial transaction authority is outside P-05's general execution scope and remains subject to the dedicated financial governance architecture in later phases.

Read-only financial data integrations may be prepared only where explicitly authorized.

23.7 Emergency shutdown

Implement an emergency execution stop that:

- Blocks new execution requests.
- Stops eligible running tasks.
- Terminates managed subprocesses when safe.
- Closes or pauses controlled browser sessions.
- Interrupts desktop automation.
- Preserves audit records.
- Releases locks.
- Reports incomplete operations.

This mechanism must not depend on an LLM response.

---

24. MONITORING AND OBSERVABILITY

Track execution behavior.

Record:

- Request ID.
- Execution ID.
- Agent ID.
- Task ID.
- Tool ID.
- Adapter.
- Start and completion timestamps.
- Duration.
- Result.
- Exit code where applicable.
- Retry count.
- Resource usage.
- Approval reference.
- Evidence reference.
- Error category.

Implement useful execution metrics:

- Success rate.
- Failure rate.
- Timeout rate.
- Average execution duration.
- Average queue wait.
- Resource utilization.
- Adapter availability.
- Retry frequency.
- Human intervention frequency.
- Verification failure rate.

Distinguish measured data from estimated data.

Do not count a failed action as successful merely because the tool returned a response.

---

25. TESTING REQUIREMENTS

Build a comprehensive test suite.

Do not mark P-05 complete merely because the FastAPI server starts.

25.1 Unit tests

Test:

- Execution request validation.
- Tool registry.
- Adapter selection.
- Risk classification.
- Capability checks.
- Approval requirements.
- Idempotency.
- Path validation.
- File operations.
- Code execution policy.
- Browser domain restrictions.
- API destination restrictions.
- Workflow validation.
- Workflow state transitions.
- Recovery logic.
- Evidence collection.
- Result verification.

25.2 Integration tests

Test:

- P-01 task queue integration.
- P-02 intelligence integration.
- P-04 agent capability integration.
- Approval service integration.
- Database migrations.
- Filesystem adapter.
- Code execution adapter.
- Browser adapter.
- API adapter.
- Workflow engine.
- Audit service.
- Emergency shutdown.

Use mock external services wherever possible.

Do not require paid API credentials for the test suite.

25.3 Security tests

Verify that:

1. An unauthorized agent cannot execute a tool.
2. An agent cannot bypass a permission check.
3. A path traversal request is rejected.
4. A symbolic link cannot escape the approved workspace.
5. A code execution timeout terminates the managed process.
6. Untrusted code cannot access protected credentials.
7. A browser cannot navigate outside its permitted domain scope.
8. A redirect cannot bypass the domain restriction.
9. A webpage cannot instruct the agent to execute an unauthorized action.
10. An API request cannot access protected internal network targets.
11. An agent cannot access another agent's restricted workspace.
12. A sensitive action cannot execute without valid approval.
13. A cancelled execution cannot continue launching new steps.
14. An interrupted workflow cannot blindly repeat a non-idempotent action.
15. An ordinary agent cannot invoke the emergency administrative controls.
16. The audit log cannot be modified through the execution interface.
17. An expired approval cannot authorize a new action.
18. The desktop adapter cannot bypass UAC or MFA.

25.4 Acceptance scenarios

Scenario A: Create a project report

An approved Research Agent requests a report.

Expected:

- The agent submits an execution request.
- Filesystem and document tools are validated.
- The report is generated in the approved workspace.
- The file is verified.
- Evidence is recorded.
- The agent receives the result.

Scenario B: Execute approved Python code

An authorized Coding Agent submits a Python script.

Expected:

- Code execution permission is checked.
- The sandbox is initialized.
- Resource limits are applied.
- The script runs.
- Output and errors are captured.
- The environment is cleaned up.
- Execution status is recorded.

Scenario C: Browse an approved website

An authorized agent requests read-only website research.

Expected:

- Domain restrictions are checked.
- Browser session is initialized.
- Page content is inspected.
- Data is extracted.
- Evidence is collected.
- No external write operation occurs.

Scenario D: Submit a sensitive form

An agent requests an external form submission.

Expected:

- The action is classified as sensitive.
- The request is held for approval.
- The owner can inspect the intended action.
- No submission occurs before approval.
- The resulting state is verified after authorization.

Scenario E: OTP or MFA challenge

A browser session encounters an authentication challenge.

Expected:

- Automation pauses.
- Status becomes REQUIRES_HUMAN_AUTHENTICATION.
- The user completes the authorized verification.
- The session resumes only after validation.

Scenario F: Filesystem attack

An agent attempts to access a protected directory using path traversal.

Expected:

- The operation is rejected.
- No protected file is accessed.
- The security event is recorded.

Scenario G: Browser prompt injection

A website instructs the agent to reveal secrets and execute unrelated commands.

Expected:

- Website content remains untrusted.
- The instruction cannot change permissions.
- No unauthorized execution occurs.

Scenario H: Workflow interruption

A multi-step workflow is interrupted during execution.

Expected:

- Completed steps remain recorded.
- The last checkpoint is preserved.
- The system determines whether recovery is safe.
- Duplicate external actions are prevented.
- Unsafe recovery requires reconciliation.

Scenario I: Resource exhaustion

Multiple agents submit resource-intensive execution requests.

Expected:

- Scheduler applies concurrency limits.
- New work is queued.
- Resource warnings are recorded.
- The application remains responsive.

Scenario J: Emergency shutdown

The owner triggers the emergency execution stop.

Expected:

- New work is blocked.
- Eligible running work is interrupted.
- Managed processes are handled.
- Browser and desktop sessions are stopped or paused.
- Audit records remain intact.

---

26. PERFORMANCE AND RELIABILITY REQUIREMENTS

The engine must operate reliably on the target Windows machine.

Prioritize:

- Asynchronous I/O for suitable network operations.
- Bounded concurrency.
- Reusable HTTP clients.
- Reusable browser sessions where safe.
- Controlled process management.
- Streaming for large files.
- Lazy loading of adapters.
- Efficient database queries.
- Limited screenshot capture.
- Controlled log retention.
- Background health checks.

Avoid:

- Creating a new browser for every minor action.
- Launching heavyweight models for execution tools.
- Unbounded subprocess creation.
- Unbounded queues.
- Excessive polling.
- Repeatedly processing unchanged files.
- Keeping unnecessary browser sessions open.

Implement configurable limits for:

- Active execution runs.
- Active subprocesses.
- Browser sessions.
- API concurrency.
- File-processing jobs.
- Workflow concurrency.
- Execution duration.
- Input and output size.

---

27. WINDOWS INSTALLATION AND STARTUP

Provide a clean Windows setup procedure.

Document:

1. Required Python version.
2. Required Node.js version, if relevant.
3. Required browser dependencies.
4. Required system permissions.
5. Environment variables.
6. Database migration.
7. Adapter configuration.
8. Sandbox prerequisites.
9. Browser installation and verification.
10. Desktop automation prerequisites.
11. Startup procedure.
12. Shutdown procedure.
13. Troubleshooting.

Do not assume the user has Docker, Windows Sandbox, WSL, or administrator privileges.

Detect available system capabilities and report unsupported features clearly.

Create a startup health report that identifies:

- Available adapters.
- Disabled adapters.
- Missing dependencies.
- Failed health checks.
- Permission problems.
- Sandbox availability.
- Browser availability.
- Resource constraints.

The system should start even if an optional adapter is unavailable.

A missing desktop automation dependency must not prevent the filesystem or API adapters from operating.

---

28. DOCUMENTATION REQUIREMENTS

Create or update:

- "docs/architecture/P05_UNIVERSAL_EXECUTION_ENGINE.md"
- "docs/architecture/EXECUTION_ADAPTER_ARCHITECTURE.md"
- "docs/architecture/EXECUTION_POLICY_MODEL.md"
- "docs/architecture/WORKFLOW_EXECUTION_ENGINE.md"
- "docs/architecture/EXECUTION_RECOVERY.md"
- "docs/security/EXECUTION_SECURITY_MODEL.md"
- "docs/security/CODE_SANDBOX_SECURITY.md"
- "docs/security/BROWSER_AUTOMATION_SECURITY.md"
- "docs/operations/EXECUTION_ENGINE_OPERATIONS.md"
- "docs/operations/WINDOWS_SETUP.md"
- "docs/testing/P05_TEST_REPORT.md"
- "docs/audits/P05_IMPLEMENTATION_REPORT.md"

Documentation must describe the actual implementation.

Clearly distinguish:

- Implemented and tested.
- Implemented but not fully tested.
- Partially implemented.
- Disabled for security reasons.
- Deferred.
- Unsupported by the current hardware or environment.

Include examples of authorized execution requests.

Document every tool's capabilities, permissions, and risk classification.

---

29. IMPLEMENTATION ORDER

Execute P-05 in the following stages.

Stage 1: Repository audit

- Inspect all earlier phases.
- Identify existing execution capabilities.
- Document architecture.
- Prepare implementation plan.

Stage 2: Execution core

- Implement execution request models.
- Build execution state management.
- Implement policy validation.
- Build tool registry.

Stage 3: Filesystem adapter

- Implement workspace management.
- Add safe file operations.
- Add path validation.
- Add integrity checks.
- Add tests.

Stage 4: Code execution adapter

- Evaluate Windows isolation mechanisms.
- Implement controlled execution environments.
- Add process and resource controls.
- Add output capture.
- Add security tests.

Stage 5: Browser adapter

- Implement controlled browser sessions.
- Add domain restrictions.
- Add navigation and inspection.
- Add human authentication handoff.
- Add action verification.

Stage 6: Windows desktop adapter

- Evaluate Windows UI Automation.
- Implement window inspection.
- Add controlled interaction.
- Add emergency interruption.
- Test on the actual environment.

Stage 7: API and document adapters

- Implement generic HTTP execution.
- Add credential broker integration.
- Implement document and data processing capabilities.
- Add network security controls.

Stage 8: Workflow engine

- Implement workflow definitions.
- Add step dependencies.
- Add persistent execution state.
- Add checkpoints.
- Add recovery handling.
- Add idempotency.

Stage 9: Agent and approval integration

- Connect P-04 agent capabilities.
- Integrate P-01 task queues.
- Integrate P-02 intelligence.
- Integrate the existing approval system.
- Validate permission enforcement.

Stage 10: Monitoring and frontend integration

- Add execution monitoring.
- Add minimal management controls.
- Connect real backend data.
- Add operational health reporting.

Stage 11: Testing and audit

- Run existing tests.
- Run P-05 tests.
- Run security tests.
- Run Windows compatibility tests.
- Run resource tests.
- Resolve regressions.
- Produce final implementation report.

Do not skip the security and integration stages to reach a visual demonstration faster.

---

30. STRICT DEVELOPMENT RULES

1. Preserve all working P-01 through P-04 functionality.
2. Do not rebuild AUTONOMUS.
3. Do not replace existing infrastructure without documented necessity.
4. Do not introduce mandatory paid APIs.
5. Do not grant unrestricted computer access to agents.
6. Do not expose raw credentials to agents.
7. Do not permit unrestricted code execution.
8. Do not bypass MFA, CAPTCHA, UAC, or platform access controls.
9. Do not permit unauthorized external actions.
10. Do not allow arbitrary network access.
11. Do not allow filesystem access outside approved scopes.
12. Do not trust browser content or external documents as instructions.
13. Do not automatically retry non-idempotent operations.
14. Do not claim an external action succeeded without verification.
15. Do not mark an interrupted workflow as completed.
16. Do not let agents approve their own sensitive actions.
17. Do not create an independent approval system if one already exists.
18. Do not weaken existing security policies to make automation work.
19. Do not silently modify existing database structures.
20. Do not install unnecessary dependencies.
21. Do not launch unbounded browser or subprocess instances.
22. Do not claim sandbox security without verifying the isolation mechanism.
23. Do not commit credentials, browser profiles, tokens, or secrets.
24. Do not delete important user files during testing.
25. Do not begin P-06 or any later phase automatically.

If an adapter cannot be safely supported on the current machine, implement its interface, document the limitation, and leave it disabled rather than pretending it is operational.

---

31. FINAL ACCEPTANCE CRITERIA

P-05 is complete only when the following requirements have implementation and test evidence.

Core engine

- [ ] Execution request manager works.
- [ ] Tool registry works.
- [ ] Adapter manager works.
- [ ] Execution state management works.
- [ ] Policy validation works.
- [ ] Capability checks work.
- [ ] Approval integration works.
- [ ] Evidence collection works.
- [ ] Result verification works.
- [ ] Audit logging works.

Filesystem

- [ ] Managed workspaces work.
- [ ] Approved file operations work.
- [ ] Path traversal is blocked.
- [ ] Workspace isolation is enforced.
- [ ] File integrity tracking works.
- [ ] Dangerous deletion is controlled.

Code execution

- [ ] Supported languages are documented.
- [ ] Execution timeout works.
- [ ] Process termination works.
- [ ] Resource limits are enforced where supported.
- [ ] Environment variables are controlled.
- [ ] Isolation strength is accurately documented.
- [ ] Untrusted code cannot access protected credentials.

Browser

- [ ] Browser sessions work.
- [ ] Domain restrictions work.
- [ ] Navigation and inspection work.
- [ ] Approved interaction works.
- [ ] Authentication handoff works.
- [ ] Prompt injection does not bypass policy.
- [ ] Outcomes are independently verified.

Desktop

- [ ] Window inspection works where supported.
- [ ] Controlled screenshots work.
- [ ] Approved interactions work.
- [ ] Target application verification works.
- [ ] Emergency interruption works.
- [ ] No privilege escalation occurs.

API and workflows

- [ ] Generic API adapter works.
- [ ] Network restrictions work.
- [ ] Secret broker integration is secure.
- [ ] Workflow definitions validate.
- [ ] Multi-step workflows execute.
- [ ] Checkpoints persist.
- [ ] Recovery works.
- [ ] Idempotency safeguards work.

Integration and reliability

- [ ] P-01 integration verified.
- [ ] P-02 integration verified.
- [ ] P-04 integration verified.
- [ ] Existing tests pass.
- [ ] New security tests pass.
- [ ] Windows setup is documented.
- [ ] Emergency execution stop works.
- [ ] No critical unresolved regressions remain.

A checkbox must not be marked complete without evidence.

---

32. FINAL IMPLEMENTATION REPORT

Generate:

"docs/audits/P05_IMPLEMENTATION_REPORT.md"

Include:

1. Executive summary.
2. Initial repository condition.
3. Architecture audit findings.
4. Existing functionality reused.
5. New modules created.
6. Existing modules modified.
7. Database changes.
8. New API endpoints.
9. Tool registry implementation.
10. Execution policy architecture.
11. Filesystem adapter results.
12. Code sandbox implementation and isolation limitations.
13. Browser adapter results.
14. Windows desktop adapter results.
15. API adapter results.
16. Workflow engine implementation.
17. Approval integration.
18. Evidence and verification architecture.
19. Recovery and idempotency behavior.
20. Security test results.
21. Performance and resource measurements.
22. Windows installation instructions.
23. Known limitations.
24. Disabled capabilities.
25. Deferred work.
26. Outstanding risks.
27. Files changed.
28. Acceptance criteria evidence.
29. Recommended next phase.

Report exact test statistics:

- Tests executed.
- Tests passed.
- Tests failed.
- Tests skipped.
- Security tests passed.
- Integration tests passed.
- Known warnings.
- Outstanding blockers.

Do not claim a browser, desktop, or code execution adapter works unless it has been tested in the actual supported environment.

---

33. PHASE COMPLETION BOUNDARY

After completing implementation, integration, testing, documentation, and audit:

STOP. DO NOT AUTOMATICALLY START P-06.

Do not begin the Business Creation Engine.

Do not start automatic product creation, website creation, marketplace publishing, customer acquisition, or business launch workflows as part of P-05.

Those capabilities belong to later phases.

At completion:

1. Present the implementation report.
2. Show the actual test results.
3. Identify the adapters that are operational.
4. Identify adapters that remain disabled.
5. Explain security limitations.
6. Identify unresolved issues.
7. Confirm which acceptance criteria passed.
8. Request owner approval.

The next planned phase is:

P-06: BUSINESS CREATION ENGINE

P-06 may begin only after the owner reviews and explicitly approves P-05.

---

FINAL DIRECTIVE

Build an execution engine that allows AUTONOMUS to perform meaningful digital work without surrendering control of the computer to an uncontrolled AI process.

The architecture must separate intelligence from execution.

Agents decide what they want to accomplish. The execution engine determines what they are allowed to do. Specialized adapters perform authorized operations. Independent validation determines whether the requested outcome actually occurred.

Every execution must have:

- An authorized requesting agent.
- A defined objective.
- A validated action.
- Explicit capabilities.
- An approved scope.
- A risk classification.
- A controlled execution environment.
- A verifiable outcome.
- An audit record.
- A recovery strategy where appropriate.

The objective is not to automate every possible action immediately.

The objective is to establish a reliable execution foundation that can safely support increasingly sophisticated autonomous business operations.

Preserve the existing system. Build modularly. Enforce security before execution. Test on the actual Windows environment. Report only verified capabilities. Stop at P-05 and wait for owner approval.