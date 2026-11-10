AUTONOMUS P-09: MEMORY AND CONTINUOUS LEARNING ENGINE

Master Implementation Prompt | Phase 9

---

1. ROLE AND MISSION

Act as a Principal AI Memory Architect, Cognitive Systems Engineer, Knowledge Graph Architect, Machine Learning Engineer, Database Architect, Retrieval-Augmented Generation Specialist, AI Agent Infrastructure Engineer, and Autonomous Systems Researcher.

Your mission is to inspect, design, implement, test, and integrate the Memory and Continuous Learning Engine (P-09) into the existing AUTONOMUS AI Business Operating System.

You are not building a basic chatbot conversation history, a folder containing text files, or a vector database that indiscriminately stores everything.

You are building a persistent intelligence and learning infrastructure that enables AUTONOMUS to:

1. Remember important information across sessions.
2. Understand the history of every business and project.
3. Remember previous decisions and why they were made.
4. Recall successful and failed experiments.
5. Learn from actual business outcomes.
6. Retain useful knowledge from completed tasks.
7. Understand relationships between businesses, agents, projects, decisions, and resources.
8. Avoid repeating previously identified mistakes.
9. Maintain continuity when an agent is restarted or replaced.
10. Retrieve relevant knowledge when a task requires it.
11. Distinguish verified facts from assumptions and predictions.
12. Detect outdated or contradictory information.
13. Update knowledge when new evidence becomes available.
14. Preserve important historical records without silently rewriting them.
15. Share authorized knowledge between specialized agents.
16. Prevent unauthorized agents from accessing private or restricted information.
17. Improve decision quality through evidence-backed outcome analysis.
18. Maintain useful intelligence even when the local LLM is unavailable.
19. Support local-first memory with optional external storage or model integrations.
20. Provide the foundation for future autonomous operations and multi-business intelligence.

The objective is to make AUTONOMUS a system that builds institutional knowledge over time.

Core principle: AUTONOMUS must remember what matters, retrieve what is relevant, distinguish truth from uncertainty, learn from outcomes, and preserve the history that explains how its intelligence evolved.

---

2. LOCKED ARCHITECTURE AND DEVELOPMENT CONTEXT

AUTONOMUS is a Windows-first autonomous AI Business Operating System.

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
- Vector memory: ChromaDB or a replaceable alternative.
- Browser automation: Playwright.
- Source control: Git and GitHub.
- Agent architecture: Shared, resource-aware infrastructure.
- Autonomy model: Controlled autonomy.
- Human owner: Ultimate decision authority.

The system must work on modest Windows hardware.

Memory retrieval, indexing, storage, and maintenance must not require a continuously running cloud service or expensive external API.

2.1 Previous-phase dependencies

Before implementation, inspect the actual implementations of:

- P-01: Core Operating System.
- P-02: Master Intelligence Engine.
- P-03: Opportunity Discovery Engine.
- P-04: Dynamic Agent Factory.
- P-05: Universal Digital Execution Engine.
- P-06: Business Creation Engine.
- P-07: Financial Intelligence Engine.
- P-08: Survival and Scaling Engine.

Inspect:

- Existing database schemas.
- Conversation/session history.
- Agent definitions and lifecycle.
- Task records.
- Business records.
- Opportunity research.
- Evidence storage.
- Financial ledger references.
- Business decision history.
- Experiment outcomes.
- Forecast history.
- Execution logs.
- Existing vector database.
- Existing memory or retrieval services.
- API contracts.
- Tests.
- Documentation.

Do not assume a previous feature exists because a development prompt requested it.

2.2 Preservation requirements

- Do not rebuild AUTONOMUS.
- Do not replace working memory or database infrastructure without evidence that it is inadequate.
- Do not create duplicate agent registries.
- Do not duplicate business, financial, or decision records.
- Do not make vector storage the authoritative source of financial or operational truth.
- Do not allow memory updates to silently modify historical records.
- Preserve existing interfaces wherever possible.
- Use migrations for database changes.
- Document significant architectural decisions.

If a previous phase has incomplete memory integration, identify the gap and implement the smallest safe integration.

---

3. THE AUTONOMUS MEMORY CONSTITUTION

The memory system must follow strict principles.

3.1 Memory is not a source of automatic truth

A stored statement is not necessarily true.

Every important memory must retain information about:

- Origin.
- Source.
- Creation time.
- Last verification time.
- Confidence.
- Evidence.
- Scope.
- Validity.
- Access permissions.

The system must distinguish:

- Verified facts.
- Corroborated information.
- User-provided information.
- Agent-generated conclusions.
- Assumptions.
- Hypotheses.
- Predictions.
- Historical observations.
- Contradicted information.
- Outdated information.

3.2 Preserve history

When a business decision changes, preserve the original decision and record the new decision separately.

When a user changes a project requirement, retain the history of the change.

When an experiment fails, preserve its original hypothesis and outcome.

Do not silently rewrite the past to make the current system appear consistent.

3.3 Store selectively

Do not save every LLM message, tool output, temporary variable, or routine system event as permanent memory.

Memory must be selected based on:

- Future usefulness.
- Relevance.
- Reliability.
- Importance.
- Uniqueness.
- Stability.
- Business impact.
- Retrieval value.

3.4 Retrieve contextually

The system must retrieve memory based on the current task.

A coding agent should not receive unrelated customer support memories.

A business strategy agent should receive relevant market research, financial evidence, decisions, and experiment outcomes.

An agent should only retrieve information it is authorized to access.

3.5 Learn from outcomes, not activity

Completing a task does not automatically mean the system learned something useful.

Learning must be based on meaningful differences between:

- Expected outcome.
- Actual outcome.
- Supporting evidence.
- Decision quality.
- Execution quality.
- Context.

---

4. MEMORY SYSTEM ARCHITECTURE

Build P-09 as a modular memory infrastructure.

Suggested logical structure:

memory/

- core/
  - memory_manager.py
  - memory_router.py
  - memory_lifecycle.py
  - memory_policy.py
  - memory_validator.py
- stores/
  - structured_store.py
  - episodic_store.py
  - semantic_store.py
  - procedural_store.py
  - vector_store.py
  - graph_store.py
- ingestion/
  - memory_ingestion.py
  - conversation_extractor.py
  - task_extractor.py
  - decision_extractor.py
  - document_ingestion.py
  - evidence_ingestion.py
- retrieval/
  - memory_retriever.py
  - hybrid_search.py
  - reranker.py
  - context_builder.py
  - relevance_scoring.py
- learning/
  - outcome_analyzer.py
  - pattern_detector.py
  - contradiction_detector.py
  - confidence_manager.py
  - knowledge_updater.py
- agents/
  - agent_memory.py
  - shared_memory.py
  - private_memory.py
  - agent_handoff.py
- knowledge/
  - entity_manager.py
  - relationship_manager.py
  - knowledge_graph.py
  - provenance_manager.py
- maintenance/
  - memory_consolidator.py
  - duplicate_detector.py
  - expiration_manager.py
  - archive_manager.py
  - integrity_checker.py
- privacy/
  - access_control.py
  - retention_policy.py
  - deletion_manager.py
  - sensitive_data_filter.py
- analytics/
  - memory_analytics.py
  - retrieval_analytics.py
  - learning_metrics.py
- api/
- models/
- services/
- tests/

This is a logical architecture, not permission to duplicate existing modules.

Reuse existing infrastructure and follow project conventions.

---

5. MULTI-LAYER MEMORY MODEL

Implement a layered memory architecture.

Different information requires different storage and retrieval behavior.

5.1 Working memory

Purpose:

Hold the information currently needed to perform an active task.

Examples:

- Current user request.
- Current task instructions.
- Active project context.
- Current execution state.
- Temporary agent findings.
- Relevant retrieved memories.
- Current plan and pending steps.

Requirements:

- Short-lived.
- Session-aware.
- Task-scoped.
- Resource-efficient.
- Explicitly cleared or expired when appropriate.
- Never treated as permanent knowledge automatically.

Working memory must support task continuation after interruption.

5.2 Episodic memory

Purpose:

Store meaningful events and experiences.

Examples:

- A business was launched.
- An experiment failed.
- A user approved a particular decision.
- An agent completed a complex project.
- A customer acquisition campaign produced a measurable result.
- A deployment caused an operational failure.
- A recovery plan successfully restored performance.

Each episode should contain:

- Event ID.
- Event type.
- Timestamp.
- Related business.
- Related project.
- Related agent.
- Trigger.
- Context.
- Actions performed.
- Results.
- Evidence.
- Participants.
- Outcome.
- Lessons.
- Confidence.

Episodic memory must preserve chronological history.

5.3 Semantic memory

Purpose:

Store relatively stable knowledge and facts.

Examples:

- A business's operating model.
- A project's architecture.
- A product's features.
- A documented API contract.
- A known technical constraint.
- A validated market observation.
- A recurring business rule.

Each semantic memory should contain:

- Memory ID.
- Subject.
- Predicate or relationship.
- Information.
- Scope.
- Source.
- Evidence.
- Confidence.
- Created date.
- Last verified date.
- Validity status.
- Access permissions.

Support versioning when information changes.

5.4 Procedural memory

Purpose:

Remember how to perform tasks reliably.

Examples:

- How to deploy a particular project.
- How to execute a verified development workflow.
- How to publish an approved content format.
- How to troubleshoot a known technical issue.
- How to execute a business recovery procedure.
- How to conduct a validated experiment.

Store:

- Procedure ID.
- Name.
- Purpose.
- Preconditions.
- Required permissions.
- Ordered steps.
- Required tools.
- Expected outputs.
- Failure conditions.
- Recovery procedure.
- Validation evidence.
- Version.
- Last successful execution.
- Success rate, when supported by sufficient data.

Procedural memory must not turn an unsafe or unauthorized historical action into an approved reusable procedure.

5.5 Preference and owner instruction memory

Purpose:

Preserve stable, explicitly authorized owner preferences and operating instructions.

Examples:

- Preferred project development workflow.
- Approved technology choices.
- Communication preferences.
- Budget constraints.
- Preferred review requirements.
- Explicitly authorized autonomy boundaries.

Requirements:

- Preserve exact meaning.
- Record source and timestamp.
- Support updates.
- Distinguish explicit owner instructions from inferred preferences.
- Never allow an agent-generated inference to override an explicit owner instruction.

Sensitive information must receive additional protection.

5.6 Organizational memory

Purpose:

Create reusable institutional knowledge across authorized businesses and agents.

Examples:

- Validated development procedures.
- Shared technical architecture knowledge.
- Proven operating processes.
- Common failure patterns.
- Reusable business templates.
- Documented lessons from previous projects.

Organizational memory must have explicit ownership and sharing rules.

---

6. MEMORY CLASSIFICATION AND METADATA

Every memory must be classified before permanent storage.

6.1 Memory categories

Support:

- OWNER_INSTRUCTION.
- USER_PREFERENCE.
- PROJECT_CONTEXT.
- BUSINESS_CONTEXT.
- TECHNICAL_KNOWLEDGE.
- BUSINESS_KNOWLEDGE.
- CUSTOMER_INSIGHT.
- MARKET_EVIDENCE.
- FINANCIAL_INSIGHT.
- DECISION_HISTORY.
- EXPERIMENT_OUTCOME.
- TASK_HISTORY.
- AGENT_EXPERIENCE.
- PROCEDURE.
- SYSTEM_CONFIGURATION.
- LESSON_LEARNED.
- SECURITY_EVENT.
- COMPLIANCE_RECORD.

6.2 Required metadata

Every permanent memory must include, where applicable:

- Unique ID.
- Memory category.
- Title.
- Content.
- Source type.
- Source reference.
- Owner or originating actor.
- Business ID.
- Project ID.
- Agent ID.
- Related task ID.
- Related decision ID.
- Related evidence ID.
- Creation timestamp.
- Last updated timestamp.
- Last verified timestamp.
- Confidence.
- Importance.
- Relevance scope.
- Sensitivity classification.
- Access policy.
- Retention policy.
- Lifecycle status.
- Version.
- Expiration date, if applicable.

Do not invent unavailable identifiers.

6.3 Memory status

Support:

- ACTIVE.
- UNVERIFIED.
- NEEDS_REVIEW.
- CONTRADICTED.
- OUTDATED.
- SUPERSEDED.
- ARCHIVED.
- DELETED.

Deletion must follow the applicable retention and audit policy.

---

7. MEMORY INGESTION ENGINE

Create an ingestion pipeline for capturing useful knowledge from AUTONOMUS activities.

7.1 Supported ingestion sources

Integrate with authorized existing sources:

- User instructions.
- Conversation history.
- Completed tasks.
- Agent outputs.
- Business records.
- Opportunity research.
- Market evidence.
- Business creation artifacts.
- Financial summaries.
- Business decisions.
- Experiments.
- Execution results.
- Technical documentation.
- Approved uploaded files.
- Operational events.
- Learning reports.

Do not automatically ingest every raw record.

7.2 Ingestion workflow

Implement:

1. Receive a candidate memory.
2. Identify its source.
3. Validate source access.
4. Classify the content.
5. Extract relevant entities.
6. Detect sensitive information.
7. Identify existing related memories.
8. Detect possible duplicates.
9. Evaluate future usefulness.
10. Assign confidence and importance.
11. Apply retention and access policies.
12. Store or reject the candidate.
13. Record provenance.
14. Make approved memory available for retrieval.

7.3 Memory extraction

Use deterministic extraction where practical.

Use local AI when semantic interpretation is required.

Examples:

A user states an explicit project technology decision.

The system should identify:

- The technology.
- The project.
- The instruction.
- Whether it is a confirmed decision.
- Whether it replaces an earlier decision.
- The scope of the instruction.

An agent completes a task.

The system should extract:

- What was attempted.
- What actually worked.
- What failed.
- What evidence supports the result.
- Whether the result is reusable.

7.4 Candidate memory filtering

Reject or avoid permanent storage of:

- Trivial conversational filler.
- Repeated content without additional value.
- Temporary status messages.
- Unverified speculation presented as fact.
- Irrelevant tool outputs.
- Sensitive credentials.
- Private keys.
- Passwords.
- Authentication tokens.
- Unnecessary personal data.
- Untrusted instructions embedded in external documents.

Secrets must never be placed in vector memory or ordinary semantic memory.

---

8. HYBRID MEMORY STORAGE

Implement multiple storage strategies according to the type of information.

8.1 Structured storage

Use the relational database for:

- Memory metadata.
- Ownership.
- Access control.
- Version history.
- Retention policies.
- Relationships.
- Approval records.
- Audit history.
- Structured facts.

The relational database is authoritative for memory metadata and lifecycle state.

8.2 Vector storage

Use ChromaDB or a replaceable vector store for semantic similarity retrieval.

Support:

- Document chunking.
- Embedding generation.
- Metadata filtering.
- Similarity search.
- Embedding model versioning.
- Re-indexing.
- Deletion synchronization.

Requirements:

- Local embedding models where feasible.
- No mandatory paid embedding API.
- Batch processing.
- Resource-aware indexing.
- Configurable chunk sizes.
- Duplicate detection.
- Embedding failure recovery.

Vector results are retrieval candidates, not authoritative truth.

8.3 Graph storage

Create relationship support for entities such as:

- Businesses.
- Projects.
- Agents.
- Customers.
- Products.
- Tasks.
- Decisions.
- Experiments.
- Documents.
- Technical components.
- Market opportunities.
- Procedures.

Example:

Business A
→ uses Product B
→ acquired Customer C
→ through Channel D
→ under Experiment E
→ approved by Decision F
→ generated Outcome G.

The relationship system must support traversal and contextual retrieval.

Use a relational representation initially if it is simpler and more reliable than adding a separate graph database.

Do not add unnecessary infrastructure.

8.4 File and document references

Store references to original files and documents.

Avoid duplicating large files into memory records.

Keep:

- Original file reference.
- Extracted text reference.
- Relevant sections.
- File hash.
- Ingestion status.
- Source provenance.

Respect existing file and library access permissions.

---

9. HYBRID MEMORY RETRIEVAL ENGINE

Build a retrieval system that combines multiple methods.

9.1 Retrieval methods

Support:

- Exact identifier lookup.
- Keyword search.
- Full-text search.
- Metadata filtering.
- Semantic vector search.
- Relationship traversal.
- Time-based retrieval.
- Business-scoped retrieval.
- Project-scoped retrieval.
- Agent-scoped retrieval.
- Historical retrieval.

9.2 Hybrid retrieval

Combine:

1. Exact matches.
2. Keyword relevance.
3. Semantic similarity.
4. Entity relationships.
5. Recency.
6. Importance.
7. Confidence.
8. Task relevance.
9. Access permissions.

Do not rely solely on vector similarity.

A highly similar but outdated memory may be less useful than a verified current record.

9.3 Retrieval relevance scoring

Implement configurable scoring.

Suggested initial factors:

- Task relevance: 25%.
- Semantic similarity: 20%.
- Evidence confidence: 15%.
- Source reliability: 10%.
- Importance: 10%.
- Recency: 10%.
- Relationship relevance: 10%.

These weights must be configurable and tested.

Apply hard filters before ranking:

- Access permissions.
- Business isolation.
- Data sensitivity.
- Validity status.
- Explicit scope.
- Retention rules.

A high relevance score must never override an access restriction.

9.4 Temporal retrieval

Support questions such as:

- What did we decide last month?
- What was the original project architecture?
- Which business experiments failed?
- What changed between two project versions?
- What was the last verified customer acquisition result?
- Which strategy was previously attempted?
- What happened before the current business entered recovery?

Temporal queries must preserve historical context.

9.5 Retrieval confidence

Every retrieval response should identify:

- Relevant memories.
- Source references.
- Confidence.
- Freshness.
- Contradictions.
- Missing information.

If no reliable memory exists, return an explicit no-reliable-memory result.

Do not fabricate a remembered fact.

---

10. CONTEXT ASSEMBLY ENGINE

Create a context builder that supplies the correct memories to the correct task or agent.

10.1 Context assembly workflow

1. Identify the active user request.
2. Identify the current task.
3. Identify relevant business and project IDs.
4. Determine the active agent.
5. Identify required context categories.
6. Check access permissions.
7. Retrieve relevant memories.
8. Remove duplicates.
9. Resolve superseded information.
10. Identify contradictions.
11. Rank relevant memories.
12. Apply context size limits.
13. Assemble a structured context package.
14. Attach provenance references.
15. Provide the context to the authorized agent.

10.2 Context package

A context package may contain:

- Current task.
- Owner instructions.
- Project summary.
- Business summary.
- Relevant historical decisions.
- Technical constraints.
- Relevant procedures.
- Recent task outcomes.
- Known risks.
- Contradictory information.
- Open questions.
- Source references.

10.3 Context limits

Respect the model's available context window.

Prioritize:

1. Current explicit instructions.
2. Security and permission constraints.
3. Relevant current project state.
4. Verified facts.
5. Important historical decisions.
6. Relevant outcomes and lessons.
7. Supporting context.

Do not fill the entire context window with old conversation history.

10.4 Context explanations

The system should be able to explain why a memory was retrieved.

This is important for debugging incorrect agent behavior.

---

11. CONTINUOUS LEARNING ENGINE

Build a system that extracts useful knowledge from actual task and business outcomes.

Learning must be evidence-based.

11.1 Learning sources

Integrate with:

- P-05 execution results.
- P-06 business creation outcomes.
- P-07 financial results.
- P-08 business decisions.
- P-08 experiment outcomes.
- Agent task results.
- Project development outcomes.
- Approved user corrections.
- Operational incidents.

11.2 Learning workflow

Implement:

1. Identify a completed task, decision, or experiment.
2. Retrieve its original objective.
3. Retrieve the original assumptions.
4. Retrieve expected results.
5. Retrieve actual results.
6. Compare expected and actual outcomes.
7. Identify possible causes.
8. Assess evidence quality.
9. Identify reusable lessons.
10. Detect whether the lesson conflicts with existing knowledge.
11. Assign confidence.
12. Create a learning record.
13. Store the learning record.
14. Make it available for future retrieval.
15. Track whether it improves later decisions.

11.3 Learning record structure

Each learning record should contain:

- Learning ID.
- Source event.
- Business or project.
- Original hypothesis.
- Expected outcome.
- Actual outcome.
- Relevant metrics.
- Supporting evidence.
- Identified causes.
- Alternative explanations.
- Lesson.
- Confidence.
- Applicability scope.
- Limitations.
- Creation date.
- Review status.

11.4 Learning confidence

Use explicit confidence categories:

- VERY_LOW.
- LOW.
- MODERATE.
- HIGH.
- VERIFIED.

Do not mark a lesson VERIFIED merely because an LLM generated it.

Require supporting evidence and, where appropriate, repeated observations.

11.5 Learning from failed tasks

Failures must be treated as valuable information.

Examples:

- A deployment method repeatedly fails on a particular Windows configuration.
- A business acquisition channel produces traffic but not paying customers.
- A particular workflow consumes excessive local inference resources.
- A specific pricing assumption produces poor conversion.
- An agent repeatedly fails a particular task because of missing permissions.

Record the context and the actual cause when supported by evidence.

Do not generalize one failure into a universal rule.

---

12. CONTRADICTION AND KNOWLEDGE EVOLUTION ENGINE

Implement a mechanism to identify conflicting memories.

12.1 Contradiction examples

- Project uses SQLite versus project now uses PostgreSQL.
- A business is active versus business has been closed.
- An API endpoint exists versus endpoint has been removed.
- A strategy was approved versus strategy was rejected.
- A procedure was successful versus newer evidence shows it fails.
- A customer requirement changed.

12.2 Contradiction detection

Evaluate:

- Entity identity.
- Subject.
- Relationship.
- Scope.
- Timestamp.
- Source reliability.
- Version.
- Verification status.

Not every apparent contradiction is a true contradiction.

Two statements may refer to different time periods, environments, or projects.

12.3 Resolution workflow

When a conflict is detected:

1. Preserve both records.
2. Identify the conflicting fields.
3. Compare timestamps.
4. Compare source reliability.
5. Check whether a new owner instruction exists.
6. Check supporting evidence.
7. Determine whether the new information supersedes the old information.
8. Update current validity status.
9. Preserve historical records.
10. Request owner clarification when necessary.

An explicit owner correction takes precedence over an inferred agent conclusion, subject to applicable safety and governance constraints.

12.4 Versioned knowledge

Support:

- Original record.
- New version.
- Change reason.
- Source.
- Verification.
- Effective date.
- Superseded version.
- Historical validity.

Do not overwrite important knowledge without a version record.

---

13. MEMORY CONSOLIDATION AND MAINTENANCE

Build a memory maintenance process.

A long-running system will accumulate duplicate, outdated, and low-value information.

The engine must keep memory useful without destroying valuable history.

13.1 Consolidation

Combine related information when doing so improves retrieval.

Examples:

- Multiple updates about one project can produce a current project summary.
- Repeated technical findings can become a verified procedure.
- Multiple experiment outcomes can form a business learning summary.
- Several related decisions can produce a strategic history summary.

Consolidation must retain links to the original source records.

13.2 Duplicate detection

Detect:

- Exact duplicates.
- Near duplicates.
- Repeated conversation extracts.
- Repeated document chunks.
- Equivalent facts with different wording.

Do not merge records that differ materially in time, scope, ownership, or validity.

13.3 Memory aging

Use configurable aging policies.

For example:

- Temporary working memory: expires after its task or session lifecycle.
- Operational snapshots: retained according to operational needs.
- Current project summaries: updated as project state changes.
- Important decisions: preserved historically.
- Verified business outcomes: retained as historical evidence.
- Procedures: periodically revalidated.
- Time-sensitive market observations: flagged as potentially outdated.

Age alone must not delete important knowledge.

13.4 Revalidation

Identify memories that need review.

Examples:

- Outdated technical documentation.
- Expired pricing assumptions.
- Old market research.
- Procedures not used for a long time.
- Previously verified facts contradicted by new evidence.

13.5 Archiving

Move low-frequency but historically important information into an archive or lower-cost storage layer when appropriate.

Archived records must remain retrievable when authorized.

---

14. AGENT MEMORY AND SHARED KNOWLEDGE

Integrate with P-04 Dynamic Agent Factory.

Each agent must have access to relevant knowledge without exposing unrestricted organizational memory.

14.1 Agent memory types

Support:

- Private agent memory.
- Task memory.
- Project memory.
- Business memory.
- Authorized shared memory.
- Organizational knowledge.

14.2 Agent continuity

When an agent is stopped, restarted, or replaced, its relevant context must remain available.

Support:

- Agent identity.
- Role.
- Current assignment.
- Active task state.
- Completed task history.
- Relevant procedures.
- Previous findings.
- Pending handoffs.
- Known limitations.

Do not depend on an agent process remaining continuously alive.

14.3 Agent handoff

When work moves between agents, create a structured handoff package containing:

- Task objective.
- Work completed.
- Current status.
- Decisions made.
- Evidence collected.
- Files modified.
- Outstanding tasks.
- Known problems.
- Required permissions.
- Recommended next actions.

The receiving agent must retrieve the handoff and verify relevant current state before continuing.

14.4 Shared knowledge permissions

Define access scopes:

- OWNER_ONLY.
- PRIVATE_AGENT.
- TASK_ONLY.
- PROJECT_SHARED.
- BUSINESS_SHARED.
- ORGANIZATION_SHARED.

An agent must not automatically share private memory across businesses.

14.5 Memory poisoning prevention

Treat all external and agent-generated content as untrusted until validated.

Prevent:

- Prompt injection through documents.
- Malicious memory insertion.
- Unauthorized instruction persistence.
- Fabricated procedures.
- False system policy updates.
- Cross-business memory leakage.

No agent can write a permanent owner instruction or change governance rules.

---

15. PROJECT AND TECHNICAL KNOWLEDGE MEMORY

AUTONOMUS must retain technical continuity across development projects.

15.1 Project memory

Store:

- Project purpose.
- Requirements.
- Technology stack.
- Architecture.
- Repository references.
- Branch information.
- Important files.
- API contracts.
- Database schema references.
- Implementation status.
- Known bugs.
- Testing results.
- Deployment configuration references.
- Previous decisions.
- Outstanding tasks.

15.2 Development continuity

When a coding agent begins a project task, it should retrieve:

- Current architecture.
- Relevant previous implementation.
- Existing conventions.
- Important constraints.
- Related bugs.
- Recent changes.
- Previous test results.
- Current task status.

Do not assume old code descriptions remain current.

For code-related knowledge, retrieve or inspect the actual repository state when current correctness depends on it.

Memory is context, not a substitute for source-code inspection.

15.3 Architecture decision records

Preserve Architecture Decision Records containing:

- Decision title.
- Context.
- Options considered.
- Selected option.
- Reason.
- Consequences.
- Owner approval.
- Date.
- Superseding decision, if any.

This prevents future agents from unknowingly reversing important architectural choices.

---

16. BUSINESS AND FINANCIAL LEARNING

Integrate P-09 with P-03, P-06, P-07, and P-08.

16.1 Business memory

Preserve:

- Business model.
- Target customer.
- Value proposition.
- Market assumptions.
- Validated demand.
- Pricing decisions.
- Distribution strategy.
- Customer acquisition results.
- Product performance.
- Operational constraints.
- Lifecycle history.

16.2 Financial learning

Use P-07 as the authoritative financial source.

Preserve useful financial lessons such as:

- Forecast accuracy.
- Actual versus expected costs.
- Contribution margin outcomes.
- Customer acquisition economics.
- Refund and chargeback patterns.
- Cash-flow issues.
- Capital allocation results.
- Experiment profitability.

Do not copy financial records into an independent competing ledger.

Memory should reference the original financial records and may store carefully labelled derived insights.

16.3 Business decision learning

Use P-08 decision history.

For each important decision, track:

- Original recommendation.
- Evidence available at the time.
- Approval.
- Action taken.
- Expected result.
- Actual result.
- Unexpected effects.
- Decision quality.
- Reusable lesson.

Do not judge a decision solely by its outcome.

A reasonable decision can produce a bad result because of external events, and a poor decision can occasionally produce a lucky result.

---

17. OWNER MEMORY AND PERSONALIZATION

Create a controlled owner context system.

Its purpose is to preserve explicit operating preferences and relevant instructions that help AUTONOMUS interact consistently with its owner.

17.1 Supported information

Examples:

- Preferred communication style.
- Explicit project preferences.
- Approved technologies.
- Development conventions.
- Business objectives.
- Confirmed budget constraints.
- Autonomy settings.
- Preferred approval workflows.
- Long-term project priorities.

17.2 Explicit versus inferred information

Distinguish:

- EXPLICIT_OWNER_INSTRUCTION.
- CONFIRMED_OWNER_PREFERENCE.
- INFERRED_PREFERENCE.
- TEMPORARY_CONTEXT.

Never present an inferred preference as something the owner explicitly stated.

17.3 Owner controls

The owner must be able to:

- View stored memory.
- Search memory.
- Inspect memory provenance.
- Correct memory.
- Mark information outdated.
- Request deletion.
- Set retention preferences.
- Control sharing.
- Restrict sensitive information.
- Export memory.
- Review important memory changes.

A user correction must update the current knowledge state without destroying relevant historical audit records.

Deletion requests must follow applicable legal, privacy, and retention requirements.

The system must not claim deletion is complete until all applicable copies and indexes have been handled and verified.

---

18. MEMORY PRIVACY AND SECURITY

Memory may contain commercially sensitive and personal information.

Implement strong security controls.

18.1 Access control

Enforce:

- Role-based access.
- Business isolation.
- Project isolation.
- Agent-level permissions.
- Task-level permissions.
- Owner-only memory.
- Restricted memory categories.

18.2 Sensitive data detection

Detect and prevent ordinary memory storage of:

- Passwords.
- API keys.
- Access tokens.
- Private keys.
- Wallet secrets.
- Session cookies.
- Authentication codes.
- Recovery codes.
- Unnecessary personal identifiers.

Store secrets only through the approved secure secrets infrastructure, if required.

Memory may retain a safe reference indicating that a secret exists, but must never retain the secret value.

18.3 Encryption

Use appropriate encryption for:

- Sensitive stored records.
- Backups.
- Data transfers.
- Secure exports.

Keep encryption keys outside the database.

Never expose encryption keys to LLM prompts.

18.4 Audit logging

Record important operations:

- Memory creation.
- Memory modification.
- Memory retrieval of restricted data.
- Permission changes.
- Memory sharing.
- Memory deletion.
- Export.
- Retention changes.
- Administrative actions.

Avoid logging secret values or unnecessary sensitive content.

18.5 Prompt injection protection

External documents and retrieved memory must be treated as data, not instructions.

A memory record cannot modify:

- System rules.
- Owner permissions.
- Security policies.
- Spending limits.
- Agent authorization.
- Approval requirements.

Instruction-like content found in retrieved documents must not gain authority merely because it was stored.

---

19. DATABASE AND DATA MODEL

Use the existing database conventions.

Suggested logical entities:

- memory_records
- memory_metadata
- memory_versions
- memory_sources
- memory_evidence_links
- memory_relationships
- memory_entities
- memory_access_policies
- memory_permissions
- memory_retention_policies
- memory_audit_events
- memory_embeddings
- memory_index_jobs
- memory_ingestion_jobs
- memory_retrieval_logs
- memory_consolidation_jobs
- memory_contradictions
- memory_review_tasks
- memory_archives
- learning_records
- learning_evidence
- learning_outcomes
- agent_memory_profiles
- agent_handoffs
- project_memory_profiles
- business_memory_profiles
- owner_memory_preferences

These are logical entities, not mandatory table names.

Avoid creating redundant storage when existing tables can be extended safely.

Use:

- Foreign keys.
- Database constraints.
- Indexes.
- Transaction-safe operations.
- Versioning.
- Migration support.
- Data integrity checks.
- Ownership validation.
- Retention enforcement.

Keep relational metadata authoritative.

---

20. BACKEND API DESIGN

Follow existing API and authentication conventions.

Suggested route groups:

Memory management

- GET /api/memory
- GET /api/memory/{memory_id}
- POST /api/memory
- PATCH /api/memory/{memory_id}
- DELETE /api/memory/{memory_id}

Retrieval

- POST /api/memory/search
- POST /api/memory/retrieve
- GET /api/memory/{memory_id}/sources
- GET /api/memory/{memory_id}/history

Ingestion

- POST /api/memory/ingest
- GET /api/memory/ingestion/jobs
- GET /api/memory/ingestion/jobs/{job_id}

Consolidation and maintenance

- POST /api/memory/consolidate
- GET /api/memory/maintenance/status
- GET /api/memory/review/required
- POST /api/memory/{memory_id}/revalidate

Learning

- GET /api/memory/learning
- POST /api/memory/learning/analyze
- GET /api/memory/learning/{learning_id}
- GET /api/memory/learning/outcomes

Agent memory

- GET /api/memory/agents/{agent_id}
- POST /api/memory/agents/{agent_id}/handoff
- GET /api/memory/agents/{agent_id}/handoffs

Owner controls

- GET /api/memory/owner
- GET /api/memory/owner/preferences
- PATCH /api/memory/owner/preferences
- GET /api/memory/owner/audit
- POST /api/memory/owner/export

Analytics

- GET /api/memory/analytics/overview
- GET /api/memory/analytics/retrieval
- GET /api/memory/analytics/quality
- GET /api/memory/analytics/storage

Adapt routes to existing conventions.

All write operations must enforce authorization, validation, audit logging, and safe transaction handling.

Deletion must also synchronize applicable vector indexes and derived copies.

---

21. MEMORY COMMAND CENTER INTERFACE

Integrate P-09 into the existing frontend.

Do not build the complete P-11 Command Center prematurely.

Create functional memory management views.

21.1 Memory overview

Display:

- Total active memories.
- Memory by category.
- Working memory usage.
- Episodic memory count.
- Semantic memory count.
- Procedural memory count.
- Learning record count.
- Pending review count.
- Outdated memory count.
- Contradiction count.
- Storage usage.
- Recent memory activity.

21.2 Memory explorer

Allow authorized users to:

- Search memories.
- Filter by category.
- Filter by project.
- Filter by business.
- Filter by source.
- Filter by date.
- Inspect provenance.
- View confidence.
- View relationships.
- View version history.

21.3 Memory detail view

Display:

- Content.
- Classification.
- Source.
- Confidence.
- Validity.
- Creation date.
- Verification date.
- Related memories.
- Access policy.
- Version history.
- Retrieval usage, where available.

21.4 Learning center

Display:

- Recent lessons.
- Successful procedures.
- Failed experiments.
- Repeated operational issues.
- Learning confidence.
- Supporting evidence.
- Applicable projects or businesses.

21.5 Memory health

Display:

- Duplicate memories.
- Contradictory memories.
- Outdated records.
- Failed indexing jobs.
- Pending consolidation.
- Broken source references.
- Retention issues.
- Access anomalies.

21.6 Owner controls

Provide controls for:

- Correcting information.
- Marking records outdated.
- Restricting sharing.
- Requesting deletion.
- Reviewing important changes.
- Exporting authorized records.

All controls must perform real backend operations.

Do not create decorative controls that appear functional but have no implementation.

---

22. MEMORY AND LEARNING ANALYTICS

Measure whether memory actually improves AUTONOMUS.

22.1 Memory quality metrics

Track:

- Memory duplication rate.
- Memory verification rate.
- Outdated memory rate.
- Contradiction rate.
- Missing provenance rate.
- Sensitive data detection rate.
- Retrieval relevance.
- Retrieval latency.
- Indexing failure rate.

22.2 Learning effectiveness metrics

Track:

- Repeated failure frequency.
- Successful procedure reuse.
- Decision improvement.
- Forecast accuracy changes.
- Task completion improvements.
- Reduction in repeated research.
- Reduction in unnecessary LLM calls.
- Agent handoff success.
- Retrieval-assisted task success.

Do not claim that memory improves intelligence merely because storage volume increases.

22.3 Retrieval evaluation

Create an evaluation dataset containing representative queries and expected relevant memories.

Test:

- Exact retrieval.
- Semantic retrieval.
- Historical retrieval.
- Business-scoped retrieval.
- Project-scoped retrieval.
- Permission-filtered retrieval.
- Contradiction-aware retrieval.
- Current-versus-outdated retrieval.

Measure precision and recall where ground truth is available.

---

23. FAILURE RECOVERY AND MEMORY INTEGRITY

Memory is critical infrastructure.

It must survive application restarts and recover from storage failures.

Implement:

- Database backup.
- Vector index backup or deterministic re-indexing.
- Recovery from incomplete ingestion.
- Retryable indexing jobs.
- Failed job tracking.
- Duplicate prevention.
- Integrity validation.
- Orphan reference detection.
- Version consistency checks.
- Safe shutdown.
- Database migration rollback strategy where supported.

The relational records must not become permanently inconsistent with vector indexes.

If vector storage is unavailable, structured memory lookup must continue working.

If embeddings are unavailable, keyword and exact retrieval must continue working.

If the LLM is unavailable, deterministic memory management and access controls must continue working.

---

24. PERFORMANCE AND RESOURCE OPTIMIZATION

AUTONOMUS must run on modest Windows hardware.

Implement:

- Local embeddings where practical.
- Batch embedding generation.
- Bounded indexing concurrency.
- Background ingestion queues.
- Incremental updates.
- Efficient metadata filtering.
- Lazy loading.
- Context-size limits.
- Caching of suitable retrieval results.
- Configurable indexing schedules.
- Database indexes.
- Efficient document chunking.
- Memory storage limits.
- Cleanup of temporary working memory.

Do not:

- Load a heavyweight model for every memory operation.
- Generate embeddings repeatedly for unchanged content.
- Re-index the entire database after every update.
- Run expensive consolidation continuously.
- Send entire memory collections into LLM context.
- Block critical business execution while memory indexing runs.

Memory must remain functional under resource constraints.

---

25. TESTING AND VALIDATION

Create comprehensive tests.

25.1 Unit tests

Test:

- Memory classification.
- Metadata validation.
- Confidence assignment.
- Importance scoring.
- Memory lifecycle.
- Duplicate detection.
- Relevance ranking.
- Access filtering.
- Context assembly.
- Versioning.
- Contradiction detection.
- Consolidation.
- Retention.
- Learning record creation.
- Agent handoff.

25.2 Integration tests

Test:

- Database storage.
- Vector indexing.
- Hybrid retrieval.
- Entity relationships.
- Document ingestion.
- P-02 intelligence integration.
- P-04 agent integration.
- P-05 execution history integration.
- P-06 project and business integration.
- P-07 financial reference integration.
- P-08 decision and experiment integration.
- API authorization.
- Frontend memory explorer.
- Deletion synchronization.
- Backup and recovery.

25.3 Security tests

Test:

- Unauthorized memory retrieval.
- Cross-business memory leakage.
- Cross-project access.
- Agent access to owner-only memory.
- Malicious document instructions.
- Credential ingestion.
- Secret exposure through search results.
- Unauthorized memory modification.
- Unauthorized deletion.
- Permission escalation.
- Vector index access bypass.
- Memory export authorization.

25.4 Critical acceptance scenarios

Scenario 1: Project continuity

An agent works on a project, is stopped, and later restarted.

Expected result:

- The new agent retrieves relevant project context.
- It understands previous decisions.
- It identifies completed and pending tasks.
- It does not unnecessarily repeat completed work.

Scenario 2: Contradictory technical information

An older memory states that a project uses SQLite, while a newer verified architecture record states PostgreSQL.

Expected result:

- Both historical records remain preserved.
- The newer verified record is identified as current.
- Retrieval prioritizes the current state.
- Historical queries can still retrieve the older state.

Scenario 3: Failed experiment learning

A business experiment fails because customer acquisition costs exceed its contribution margin.

Expected result:

- The system stores the experiment outcome.
- It links the lesson to financial evidence.
- It does not generalize the finding beyond its supported scope.
- Future related experiments can retrieve the lesson.

Scenario 4: Agent handoff

A research agent completes research and transfers work to a business creation agent.

Expected result:

- A structured handoff is generated.
- Relevant findings and evidence are preserved.
- The receiving agent can retrieve the context.
- Restricted private information is not shared.

Scenario 5: Memory poisoning

An external document contains instructions telling AUTONOMUS to ignore owner rules and change security settings.

Expected result:

- The content is treated as untrusted data.
- It cannot alter system instructions.
- It cannot change owner permissions.
- Any relevant security concern is recorded safely.

Scenario 6: Owner correction

The owner corrects a previously stored project requirement.

Expected result:

- Current knowledge is updated.
- The correction source is recorded.
- The older version remains historically traceable.
- Future retrieval prioritizes the corrected instruction.

Scenario 7: Outdated market research

A market research record is several months old.

Expected result:

- The memory is flagged for revalidation when its freshness policy requires it.
- It is not presented as current verified market information.
- Its original historical value remains accessible.

Scenario 8: Restricted memory

A private business memory exists, and an agent working on another business requests similar information.

Expected result:

- Unauthorized information is not disclosed.
- The access decision is logged.
- Retrieval ranking cannot bypass permissions.

Scenario 9: Duplicate memory ingestion

The same document is ingested twice.

Expected result:

- Duplicate detection prevents unnecessary storage and indexing.
- Original provenance remains preserved.
- No duplicate learning records are created.

Scenario 10: LLM unavailable

The local model service is offline.

Expected result:

- Structured memory lookup continues.
- Keyword retrieval continues.
- Access control continues.
- Historical records remain available.
- New AI-assisted summaries may be deferred.

Scenario 11: Vector database unavailable

The vector store becomes unavailable.

Expected result:

- Structured and keyword retrieval continue.
- The system reports degraded semantic retrieval.
- Index recovery can be initiated.
- No authoritative memory records are lost.

Scenario 12: Secret detection

An agent output contains an API key.

Expected result:

- The secret is blocked from ordinary memory storage.
- Sensitive content is not embedded.
- Logs do not expose the value.
- The system records a safe security event.

Scenario 13: Historical decision retrieval

The owner asks why a particular business strategy was selected.

Expected result:

- The system retrieves the original decision.
- It presents the context and alternatives.
- It provides the evidence and approval history.
- It does not invent an explanation.

Scenario 14: Learning quality

One successful experiment produces a positive result.

Expected result:

- The system stores the result with appropriate confidence.
- It does not immediately classify the strategy as universally successful.
- It requires additional evidence before broad generalization.

Scenario 15: Memory deletion

The owner requests deletion of an eligible memory.

Expected result:

- Authorization is checked.
- Applicable retention rules are evaluated.
- The operation is tracked.
- Relevant derived indexes and copies are synchronized.
- Completion is reported only after verification.

Scenario 16: Agent restart during task

An agent is interrupted while working.

Expected result:

- Task progress and handoff state remain available.
- The restarted agent can reconstruct the relevant context.
- Incomplete operations are not falsely marked complete.

Scenario 17: Memory retrieval relevance

A business strategy agent asks about a particular business.

Expected result:

- Relevant business memories are prioritized.
- Unrelated project and owner-private memories are excluded.
- The context package remains within configured limits.

---

26. DOCUMENTATION REQUIREMENTS

Create or update documentation covering:

1. P-09 architecture.
2. Memory classification.
3. Memory lifecycle.
4. Working memory.
5. Episodic memory.
6. Semantic memory.
7. Procedural memory.
8. Owner preference memory.
9. Organizational memory.
10. Ingestion pipeline.
11. Structured storage.
12. Vector storage.
13. Relationship storage.
14. Hybrid retrieval.
15. Context assembly.
16. Learning methodology.
17. Confidence methodology.
18. Contradiction resolution.
19. Consolidation.
20. Retention.
21. Agent memory.
22. Agent handoff.
23. Business and financial learning.
24. Privacy and security.
25. Database schema.
26. API documentation.
27. Indexing and backup.
28. Recovery procedures.
29. Testing instructions.
30. P-10 integration requirements.

Document the limitations of memory retrieval.

Do not claim that semantic similarity guarantees correctness.

---

27. IMPLEMENTATION SEQUENCE

Implement P-09 in controlled stages.

Stage 1: Repository and dependency audit

- Inspect P-01 through P-08.
- Map existing storage.
- Map existing agent memory.
- Map business and decision history.
- Map vector database usage.
- Identify duplication.
- Produce an architecture and migration plan.

Stage 2: Memory foundation

- Implement memory metadata.
- Implement memory categories.
- Implement structured storage.
- Implement lifecycle.
- Implement versioning.
- Implement source provenance.

Stage 3: Memory ingestion

- Implement candidate extraction.
- Implement classification.
- Implement usefulness filtering.
- Implement sensitive data filtering.
- Implement duplicate detection.
- Implement ingestion jobs.

Stage 4: Hybrid storage

- Integrate structured storage.
- Integrate vector storage.
- Implement relationship storage.
- Implement indexing and recovery.
- Implement document references.

Stage 5: Retrieval

- Implement exact search.
- Implement keyword search.
- Implement semantic search.
- Implement metadata filters.
- Implement relationship traversal.
- Implement hybrid ranking.

Stage 6: Context assembly

- Implement task context.
- Implement project context.
- Implement business context.
- Implement agent context.
- Implement access-aware context assembly.
- Implement token and size limits.

Stage 7: Continuous learning

- Implement outcome extraction.
- Implement learning records.
- Integrate P-05 task results.
- Integrate P-07 financial evidence.
- Integrate P-08 decision and experiment outcomes.
- Implement confidence and applicability.

Stage 8: Knowledge evolution

- Implement contradiction detection.
- Implement versioning workflows.
- Implement revalidation.
- Implement consolidation.
- Implement retention and archiving.

Stage 9: Agent memory

- Implement private and shared memory.
- Implement agent continuity.
- Implement handoff packages.
- Implement memory access boundaries.

Stage 10: Owner memory and controls

- Implement owner preference storage.
- Implement correction.
- Implement review.
- Implement deletion workflows.
- Implement export.
- Implement audit history.

Stage 11: Frontend integration

- Implement memory overview.
- Implement memory explorer.
- Implement memory details.
- Implement learning center.
- Implement memory health.
- Implement owner controls.

Stage 12: Independent testing and audit

- Run unit tests.
- Run integration tests.
- Run security tests.
- Run retrieval evaluation.
- Test degraded operation.
- Test backup and recovery.
- Verify previous-phase functionality.
- Fix critical issues.
- Produce final report.

Do not skip stages to make the UI look complete.

---

28. ACCEPTANCE CRITERIA

P-09 is complete only when the following are satisfied.

Memory foundation

- [ ] Multiple memory categories are supported.
- [ ] Memory metadata is structured.
- [ ] Source provenance is preserved.
- [ ] Memory versions are traceable.
- [ ] Historical records are preserved.
- [ ] Retention policies work.

Ingestion

- [ ] Authorized sources can be ingested.
- [ ] Memory classification works.
- [ ] Low-value information can be filtered.
- [ ] Duplicate detection works.
- [ ] Sensitive data is blocked.
- [ ] Ingestion failures can recover.

Storage and retrieval

- [ ] Structured storage works.
- [ ] Vector indexing works.
- [ ] Hybrid retrieval works.
- [ ] Relationship retrieval works.
- [ ] Temporal retrieval works.
- [ ] Permissions are enforced before results are exposed.
- [ ] Retrieval confidence and provenance are visible.

Continuous learning

- [ ] Task outcomes can create learning records.
- [ ] Business outcomes can create learning records.
- [ ] Financial insights reference P-07.
- [ ] Business decisions reference P-08.
- [ ] Lessons include supporting evidence.
- [ ] Uncertain findings are not presented as verified.

Knowledge evolution

- [ ] Contradictions can be detected.
- [ ] Superseded records remain traceable.
- [ ] Current knowledge is distinguishable from historical knowledge.
- [ ] Consolidation preserves source links.
- [ ] Outdated memories can be reviewed.

Agent integration

- [ ] Agent memory is persistent.
- [ ] Agent handoff works.
- [ ] Shared memory is permission-controlled.
- [ ] Cross-business access is restricted.
- [ ] Agent restart does not erase relevant task context.

Owner controls

- [ ] Owner can inspect memory.
- [ ] Owner can correct memory.
- [ ] Owner can review provenance.
- [ ] Owner can request deletion.
- [ ] Owner can control sharing.
- [ ] Owner can export authorized information.

Engineering quality

- [ ] Database migrations pass.
- [ ] API authorization tests pass.
- [ ] Retrieval tests pass.
- [ ] Security tests pass.
- [ ] Backup and recovery are validated.
- [ ] Degraded operation is tested.
- [ ] Existing P-01 through P-08 functionality remains operational.
- [ ] Documentation is complete.
- [ ] No unimplemented feature is falsely marked complete.

Critical failures in access control, sensitive data protection, provenance, memory integrity, or cross-business isolation block completion.

---

29. FINAL AUDIT AND DELIVERY REPORT

At the end of P-09, generate a comprehensive report containing:

1. Initial repository condition.
2. P-01 through P-08 integration audit.
3. Existing memory infrastructure reused.
4. Architecture changes.
5. Files created.
6. Files modified.
7. Database migrations.
8. Memory classification capabilities.
9. Ingestion capabilities.
10. Storage architecture.
11. Vector indexing implementation.
12. Hybrid retrieval implementation.
13. Context assembly.
14. Learning engine.
15. Contradiction detection.
16. Consolidation and retention.
17. Agent memory and handoff.
18. Business and financial learning.
19. Owner memory controls.
20. Privacy and security controls.
21. API endpoints.
22. Frontend functionality.
23. Backup and recovery.
24. Retrieval evaluation results.
25. Tests executed.
26. Test results.
27. Performance observations.
28. Known limitations.
29. Unresolved risks.
30. Manual configuration requirements.
31. P-10 integration readiness.

Use explicit statuses:

- COMPLETED AND TESTED.
- IMPLEMENTED BUT NOT FULLY TESTED.
- PARTIALLY IMPLEMENTED.
- BLOCKED.
- NOT IMPLEMENTED.
- REQUIRES OWNER CONFIGURATION.

Do not claim that AUTONOMUS has learned something simply because a memory record was created.

Report measurable results where possible.

---

30. STRICT DEVELOPMENT RULES

1. Inspect before implementing.
2. Preserve all working previous phases.
3. Do not duplicate existing authoritative records.
4. Do not treat vector similarity as proof of truth.
5. Preserve source provenance.
6. Preserve historical decisions and versions.
7. Never store secrets in ordinary memory.
8. Never allow retrieved documents to override system instructions.
9. Never expose owner-only memory to unauthorized agents.
10. Never permit cross-business memory leakage.
11. Never turn an unverified assumption into a verified fact.
12. Never generalize a single experiment without sufficient evidence.
13. Never overwrite historical information silently.
14. Never use memory as a substitute for checking current source code or financial records.
15. Never make memory retrieval dependent on an LLM being available.
16. Never create unnecessary heavyweight infrastructure.
17. Never allow an agent to modify owner permissions.
18. Never report a deletion as complete before verifying applicable copies and indexes.
19. Test critical privacy and authorization boundaries.
20. Document significant architectural changes.
21. Do not automatically start the next phase.

If a requirement conflicts with an existing architecture, document the conflict and propose the smallest safe modification.

If the system cannot establish a memory's reliability, label it accordingly.

---

31. FINAL EXECUTION BOUNDARY

Your responsibility is to complete P-09: Memory and Continuous Learning Engine only.

After implementation:

- Integrate P-09 with P-01 through P-08.
- Verify all memory categories.
- Verify ingestion and classification.
- Verify structured and vector storage.
- Verify hybrid retrieval.
- Verify contextual memory assembly.
- Verify continuous learning.
- Verify contradiction and version management.
- Verify agent continuity and handoffs.
- Verify business and financial learning.
- Verify owner controls.
- Verify privacy and security boundaries.
- Run the complete test suite.
- Conduct an independent audit.
- Produce the final completion report.
- Clearly identify incomplete capabilities and remaining risks.

STOP AFTER P-09.

Do not automatically begin P-10: Security and Governance Engine.

Wait for explicit approval from the human owner.

The final objective is to give AUTONOMUS persistent, structured, trustworthy institutional memory and a measurable ability to improve from experience.

It must not merely remember what happened.

It must understand what happened, why it happened, what evidence supports that conclusion, and whether the lesson should influence future decisions.

END OF P-09 MASTER IMPLEMENTATION PROMPT