# AUTONOMUS Agent Governance Blueprint

**Phase:** P-00 · **Status:** Governance design only; no agents created  
**Principle:** An agent is a scoped logical identity and workload, not an independent security authority or a dedicated LLM process.

## 1. Hierarchy and proposed responsibilities

| Level | Role | Responsibility | Boundary |
|---|---|---|---|
| 0 | Master Orchestrator / Intelligence | Mission interpretation, portfolio planning and coordination | Proposes; cannot self-authorize privilege or spending |
| 1 | Executive agents | Strategy, finance, risk, operations, intelligence and technology | Business/portfolio scope; advisory unless explicitly authorized |
| 2 | Business directors | One accountable director per business | Cannot access another business without a grant |
| 3 | Department agents | Research, product, marketing, sales, operations and support | Department/business-scoped tasks and tools |
| 4 | Execution agents | Bounded tool work and artifact production | Narrow task grants, budgets and cancellation |

Proposed specialist responsibilities include Research Agent, Opportunity Analyst, Market Validation Agent, Business Strategist, Product Creation Agent, Coding Agent, Marketing Agent, Customer Operations Agent, Financial Analyst, Security Guardian and Independent Review Agent. These are future roles, not a requirement to instantiate them all.

The Security Guardian may be an advisory agent, but the actual security authority is deterministic governance code. An Independent Review Agent can challenge results; it cannot replace owner approval or an independent external audit.

## 2. Agent identity and configuration

Each agent record must include:

- Unique ID, name, role and schema/template version.
- Parent ID and hierarchy depth; no cycles or self-parenting.
- Business scope and mission/task assignment.
- Objective and measurable completion criteria.
- Approved model profile and fallback policy.
- Explicit tool/resource permissions and denied actions.
- CPU/memory/task/time/token/cost budgets.
- Memory namespace and evidence access scope.
- Lifecycle state, configuration version and audit references.
- Execution history and quality/performance records.

Creating an agent does not create a wallet, browser session, OS administrator identity or model server. Those resources require separate grants.

## 3. Task assignment and lifecycle

```text
QUEUED → LEASED → RUNNING → VERIFYING → COMPLETED
                    ↓            ↓
              WAITING_APPROVAL  FAILED / UNCERTAIN
                    ↓
              APPROVED / DENIED / EXPIRED

Operational overlays: PAUSED, CANCEL_REQUESTED, CANCELED
```

1. A mission/plan produces a typed task proposal.
2. The task service checks scope, dependencies, budget and duplicates.
3. The scheduler leases eligible work to an authorized agent/worker.
4. The worker receives only the task context and scoped capabilities it needs.
5. Progress is reported as structured events and artifact references.
6. Completion requires deterministic verification appropriate to the task.
7. The parent receives the verified result, not merely a model's “done” message.

A lease includes a fencing/attempt identifier. A stale worker cannot commit results after losing its lease. Task state and external-action intent must be durable before side effects.

## 4. Tool request and authorization flow

```text
Agent proposes action
  → validate schema and registered tool
  → authenticate agent and business scope
  → classify action risk and resource sensitivity
  → check policy version, grant, quota, budget and mode
  → allow / deny / require owner approval
  → bind approval to exact action payload
  → reserve budget atomically where needed
  → execute through gateway
  → record result and reconcile uncertain external state
```

Permission levels from the Constitution:

- **L0 Observe:** permitted read-only research/inspection within scope.
- **L1 Prepare:** drafts, code, products and proposals in restricted workspaces.
- **L2 Execute:** explicitly approved external operations within limits.
- **L3 Financial:** restricted spending/commitments through the financial boundary.
- **L4 Critical:** owner approval for irreversible/high-risk actions and authority changes.

Levels are not a simple integer privilege ladder. A role may have L1 for files, L0 for customer data and no financial permission. Risk, resource, business scope, amount, recipient and operating mode are separate checks. Deny rules and emergency suspension take precedence.

An approval is bound to actor, action, canonical payload hash, amount/currency, recipient, business, policy version, expiry and permitted use count. Editing the payload invalidates it. Approvals cannot be copied to descendants.

## 5. Information sharing and untrusted content

- Share artifacts and evidence through scoped services, not unrestricted filesystem or memory access.
- Label source, capture time, verification status and claim type.
- Treat websites, customer messages, downloaded documents and retrieved memories as untrusted input.
- External content cannot alter system instructions, grant permissions or create financial authority.
- Cross-business sharing requires an explicit grant and audit record.
- Do not place credentials, private keys or unnecessary personal data into model context.
- Record concise decision rationale and evidence, not hidden chain-of-thought.

## 6. Duplicate-work and loop prevention

- Use task fingerprints and idempotency keys for equivalent work.
- Check existing artifacts/evidence before repeating research or production.
- Bound retries, recursion depth, tool calls, tokens, wall-clock time and cost per task.
- Detect repeated no-progress states and identical tool requests.
- Use bounded queues and backpressure rather than creating more agents automatically.
- A child cannot retry a denied action through another parent or tool alias.
- External side effects require reconciliation before retry; a timeout is not proof of failure.

## 7. Agent Factory creation gate

A creation request must demonstrate:

1. A real, authorized workload and measurable need.
2. Why existing capacity cannot handle it within required time/cost.
3. Expected value and a bounded evaluation period.
4. Available compute, queue capacity and business budget.
5. A non-duplicate role and clear parent/business scope.
6. Permissions no broader than the parent and task require.
7. Compliance with global/per-business quotas and maximum depth.
8. An approved model profile and resource limits.
9. Owner approval when the role/action class requires it.

The factory records the decision even when it rejects creation. Quotas and recursion limits are mandatory; their numeric defaults require phase-specific approval and hardware evidence. The hierarchy has five levels, but that does not mean every branch should be populated.

**Initial engineering recommendation:** one shared generation model, one inference slot and a small number of logical workers until benchmarked. This is not a claim that more agents improve throughput.

## 8. Resource governance

Track per-agent and per-business:

- Queue wait, active time and model invocations.
- Input/output tokens and estimated/verified provider cost.
- Tool calls, failures, retries and wall-clock duration.
- Artifact quality and verification failures.
- Memory/CPU observations where the execution environment exposes them.
- Budget consumed and remaining.

Local inference cost must include an explicitly labelled estimate of compute/energy/opportunity cost if used; it is not a verified cash expense merely because a token counter exists. Shared costs need a consistent allocation policy and must not be double counted in consolidated profit.

## 9. Performance evaluation

Separate business outcomes from agent contribution.

| Agent type | Appropriate measures | Inappropriate sole measure |
|---|---|---|
| Research | Evidence quality, coverage, freshness, usefulness, cost | Direct revenue attributed to every report |
| Coding | Tests, defects, maintainability, security, delivery time | Lines of code |
| Marketing | Authorized reach, conversion quality, acquisition cost, compliance | Raw message volume |
| Support | Resolution, satisfaction, response time, obligation handling | Number of closed tickets alone |
| Finance analysis | Reconciliation accuracy, forecast calibration, limit compliance | Predicted profit presented as actual |
| Director | Business outcomes, risk, resource use and obligation handling | Agent count |

Attribution must acknowledge uncertainty. A research agent can be valuable without directly collecting payment; a profitable business does not prove every agent was effective.

## 10. Failure, pause and termination

- Retry only operations classified as safe to retry.
- Pause on budget exhaustion, repeated verification failure, abnormal resource use or policy violations.
- Reassign work only after revoking the previous lease and checking external state.
- Roll back agent configuration to an approved version when appropriate.
- Termination revokes grants, cancels eligible work, releases unspent reservations and preserves records.
- Customer obligations, refunds, financial history, artifacts and audit logs survive termination.
- Essential governance, audit, recovery and financial-control services cannot be retired by the survival engine for being “non-revenue-generating.”

## 11. Future acceptance tests

Create/pause/reassign/terminate agents; reject quota/depth/cycle violations; prevent permission escalation; enforce business isolation; consume approvals once; reject altered payloads; stop loops; recover stale leases; preserve obligations on termination; prove shared inference rather than one model process per agent.

These tests are requirements for later phases. **No agent behavior is implemented or verified in P-00.**
