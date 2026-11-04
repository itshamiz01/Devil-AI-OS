# P-01 Event System

The internal event bus is asynchronous and bounded. Events have ID, type, timestamp, source, correlation ID, optional task ID, severity and payload. System events are persisted to SQLite. Subscriber exceptions are isolated and logged. The bus rejects unknown event types and applies backpressure when full.

Implemented event types (21) include application lifecycle, task lifecycle, approval, permission denial, system warning/error, database unavailable, resource threshold, and the two emergency-stop types `EmergencyActivated` / `EmergencyDeactivated` added beyond the P-01 §8 initial list of 19 so that a security-critical state change is observable through the same bus (ADR-0013). Critical audit records are written separately by permission/task/approval services and do not depend only on in-memory event delivery.

## Later phases

The count of 21 above is the P-01 state. `EVENT_TYPES` has grown additively since, one phase at a time, with each new type added in the same commit as the code that publishes it — the bus rejects an unknown type, so a publisher and its event type cannot drift apart. Verified by reading the set back: **52 types, no duplicates**, grouped in the source by phase.

| Phase | Added | Running total |
|---|---|---|
| P-01 §8 initial list | 19 | 19 |
| P-01 emergency stop (ADR-0013) | 2 — `EmergencyActivated`, `EmergencyDeactivated` | 21 |
| P-02 intelligence engine (ADR-0015) | 10 — mission, plan, dispatch, decision, model and injection types | 31 |
| P-03 opportunity discovery | 10 — opportunity, research, source, evidence, compliance and governance types | 41 |
| P-04 Stage 3 agent templates | 6 — `AgentTemplateCreated`, `AgentTemplateRevised`, `AgentTemplateValidated`, `AgentTemplatePublished`, `AgentTemplateDeprecated`, `AgentTemplateRestored` | 47 |
| P-04 Stage 4 agent creation | 5 — `AgentCreationRequested`, `AgentCreated`, `AgentCreationQueued`, `AgentCreationApprovalRequested`, `AgentCreationRejected` | 52 |

The Stage 3 types carry source `agent_templates` and the Stage 4 types carry source `agent_factory`. An **invalid** validation verdict is published as well as a valid one, with its issue count: "this template was refused, and why" is the record an owner needs after the fact, and a bus carrying only successes would be a log of what went right. See [AGENT_TEMPLATES.md](AGENT_TEMPLATES.md).

The creation types follow the same rule, with one asymmetry that is deliberate. Every creation request publishes `AgentCreationRequested` carrying the decision, and a rejection or a queued request publishes its own type as well, because what the system decided **not** to do is what an owner audits afterwards. `REUSE_EXISTING` publishes only `AgentCreationRequested`: reusing an agent creates nothing, so emitting `AgentCreated` for it would inflate every downstream count of agents that were made. See [AGENT_FACTORY.md](AGENT_FACTORY.md).

This is not a distributed broker. Recursive flooding is bounded by queue capacity and subscriber limits, but P-01 does not implement a distributed outbox.
