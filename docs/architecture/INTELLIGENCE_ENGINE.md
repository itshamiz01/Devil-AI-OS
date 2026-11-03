# Intelligence Engine Architecture (P-02)

Status labels used throughout: **Implemented** (code exists and is tested), **Partially implemented**, **Planned** (designed, not built), **Not supported**, **Requires future phase**.

## 1. What this layer is

The Master Intelligence Engine sits between the owner and the P-01 Core OS. It interprets requests, reasons about them, produces plans and recommends decisions. It does not execute. Every execution path ends at `TaskManager.submit`, and every authorization ends with the owner.

This is not a chatbot and not an unrestricted agent. The governing rule for the phase is that intelligence is flexible while authority stays bounded — see [ADR-0015](../decisions/ADR-0015-INTELLIGENCE-ENGINE-BOUNDARIES.md).

## 2. Module map

All modules live in `backend/app/intelligence/`. Each owns one concern; none reaches into persistence, permissions, execution, tools, finance or UI except through an explicit interface.

| Module | Responsibility | Spec | Status |
|---|---|---|---|
| `schemas.py` | Enums, Pydantic contracts (`extra="forbid"`), mission state machine | §7 | Implemented |
| `providers.py` | `ModelProvider` protocol, `OllamaProvider`, `NoRuntimeProvider`, error types | §6.1 | Implemented (Ollama **not verified** against a live server) |
| `registry.py` | `ModelRegistry` of known models and declared capabilities | §6.2 | Implemented |
| `router.py` | Selection, admission, concurrency, timeouts, fallback, usage accounting | §6.3–6.5 | Implemented |
| `missions.py` | Deterministic request interpretation | §7 | Implemented |
| `reasoning.py` | Evidence, hypotheses, uncertainty, reasoning pipeline | §8 | Implemented |
| `capabilities.py` | What the system can actually do | §11.2 | Implemented |
| `planning.py` | Decomposition, dependency graph, validation, replanning | §9 | Implemented |
| `decisions.py` | Transparent scoring, risk classification, decision records | §10 | Implemented |
| `autonomy.py` | Who may act, at what level | §15 | Implemented (levels 0–2; 3–4 refused) |
| `prompts.py` | Static invariants, untrusted-content fencing | §12.4 | Implemented |
| `context.py` | Assembly, prioritisation, budget, injection scanning | §12 | Implemented |
| `orchestrator.py` | Dispatch through P-01, progress from real task states, failure assessment | §11 | Implemented |
| `output.py` | Schema validation of model output, authority-field refusal, bounded repair | §13 | Implemented |
| `repository.py` | Persistence to the ten P-02 tables | §17 | Implemented |
| `engine.py` | The facade the API talks to | §5 | Implemented |
| `factory.py` | Composition root; wires the engine to P-01 services | §4 | Implemented |

## 3. Request lifecycle

```
owner request
  -> security pre-check        (override attempt? credential request?  -> refuse, no mission)
  -> MissionInterpreter        (deterministic: category, classification, risk, constraints)
  -> clarification?            -> return questions, never invent a budget or success criterion
  -> mission created           -> persisted (missions, mission_history)
  -> optional model enrichment (non-authoritative fields only)
  -> Planner                   -> PlanValidator (reject, do not repair)
  -> DecisionEngine            -> RECOMMENDATION (never AUTHORIZED)
  -> owner approval            -> AutonomyController gate
  -> TaskDispatcher            -> TaskManager.submit  (P-01 permission + approval gate)
  -> ProgressMonitor           -> percentages from persisted task rows only
```

The security pre-check runs **before** interpretation, planning and any model call. A request to override policy or exfiltrate credentials is refused without creating a mission, without generating a plan and without spending inference.

## 4. Composition

`factory.build_intelligence(settings, db, tasks)` is the only construction path used by the application. It returns an `IntelligenceServices` bundle. `factory.initialize(services)` performs the async startup work: persisting configured model registrations and recovering missions stored before the last shutdown.

Construction performs no I/O and starts no model. Health probing is lazy, so an absent runtime cannot delay startup (§18). `core/application.py` builds intelligence after the task manager, because the orchestrator dispatches through it.

Recovery restores **visibility only**. Nothing is re-planned, re-dispatched or re-authorized, and a rebuilt subsystem starts at the configured autonomy level rather than at whatever the previous process had escalated to.

## 5. Degraded operation

With `model_provider="none"` — the default, and the truth on the P-02 host — the router is built with `NoRuntimeProvider`. The engine remains fully functional for every deterministic operation and reports model-dependent work as `ResponseStatus.UNAVAILABLE` with an explicit limitation. It never fabricates reasoning and never falls back to a paid provider ([ADR-0016](../decisions/ADR-0016-NO-PAID-INFERENCE-FALLBACK.md), [ADR-0017](../decisions/ADR-0017-DETERMINISTIC-FIRST-INTELLIGENCE.md)).

Configuration notes explaining an empty registry are surfaced through `GET /api/v1/intelligence/status` rather than written to logs, so an operator can see *why* no model is registered.

## 6. What this layer is not

| Capability | Status |
|---|---|
| Opportunity discovery / market research | **Requires future phase** (P-03). A plan for research is not research. |
| Autonomous agents | **Requires future phase** (P-04) |
| Tool execution, shell, browser | **Not supported**; no such call exists in the package |
| Financial operations | **Not supported**; blocked by phase flag and by the interpreter |
| Multi-agent debate | **Not supported** in P-02 (§8.5 excludes it deliberately) |
| Vector retrieval / RAG | **Requires future phase** (ADR-0008, P-09) |
| Autonomy levels 3–4 | **Not supported**; refused by `Literal` at config load and by `AutonomyController` at runtime |

## 7. Related documents

[MODEL_ROUTING.md](MODEL_ROUTING.md) · [MISSION_INTERPRETATION.md](MISSION_INTERPRETATION.md) · [REASONING_AND_EVIDENCE.md](REASONING_AND_EVIDENCE.md) · [PLANNING_AND_DEPENDENCIES.md](PLANNING_AND_DEPENDENCIES.md) · [DECISION_ENGINE.md](DECISION_ENGINE.md) · [ORCHESTRATION_AND_DISPATCH.md](ORCHESTRATION_AND_DISPATCH.md) · [CONTEXT_AND_PROMPT_SECURITY.md](CONTEXT_AND_PROMPT_SECURITY.md) · [AUTONOMY_LEVELS.md](AUTONOMY_LEVELS.md) · [API_REFERENCE.md](API_REFERENCE.md) · [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md)
