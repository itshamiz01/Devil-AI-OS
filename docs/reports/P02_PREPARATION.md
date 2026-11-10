# AUTONOMUS P-02 — Preparation Pack (Master Intelligence Engine)

**Status:** PREPARED, build not started. Prepared 9 Nov 2026 after the owner accepted the P-01 staging gate (Windows verification carried as a pending item, non-blocking for staging work).
**Method:** grounded in an inspection of the actual P-01 code (not only its docs) on 9 Nov 2026. Every integration point below names the real file/signature it was read from.

---

## 1. Implementation assessment — what P-02 builds on (verified in code)

| P-01 asset (real) | Location | How P-02 uses it |
|---|---|---|
| `TaskManager.submit(principal, *, name, handler_name, …, idempotency_key)` | `backend/app/tasks/manager.py` | The Execution Coordinator submits every plan step as a P-01 task. P-02 never executes anything directly. |
| `HandlerRegistry.register(name, func, payload_model)` with built-ins `core.noop / core.echo_check / core.health_snapshot / core.wait` | `backend/app/tasks/handlers.py` | Becomes the seed of the **Tool Registry**: P-02 wraps registered handlers as callable tools with permission metadata. No new execution path is created. |
| `PermissionEngine.check(principal, permission, …)` — deny-by-default, audited | `backend/app/permissions/engine.py` | Every tool call and every plan approval passes through it, exactly as P-01 tasks already do. **Permission integration (the owner's Part-3 correction) is therefore an extension, not a new system.** |
| Approvals workflow (parameter-hash bound) | `backend/app/permissions/approvals.py` | Plans containing L2+ steps are approved through this existing flow; a changed plan invalidates the approval automatically by hash. |
| `EventBus.subscribe(event_type, handler)` / `publish(event)` with correlation IDs + persisted critical events | `backend/app/events/bus.py` | P-02 adds intelligence event types (MissionReceived, PlanCreated, PlanApproved, StepVerified, DecisionRecorded) on the same bus. |
| `Settings` already carries `mode ∈ {simulation, supervised, controlled, emergency}` | `backend/app/core/config.py` | Mode enforcement point for autonomy: in `simulation`, plans may be created but external-effect steps cannot execute; mode is config/owner-controlled, never model-controlled. |
| Integration interface base | `backend/app/integrations/interfaces/base.py` | The Model Provider interface extends this existing pattern. |
| Monitoring thresholds + admission guard | `backend/app/monitoring/` | The Model Router reads the same resource state before choosing local model size / concurrency. |

**Gaps P-02 must fill (nothing here exists yet):** missions/plans data model · model provider interface + Ollama adapter · model router · planning engine · decision recorder · result verifier · context manager · intelligence API routes. No P-01 module needs modification except: new Alembic migration, new event types, router registration in lifecycle startup, new config section (additive only).

## 2. Design decisions proposed for P-02 (owner can amend before build)

1. **Deterministic-first planning, LLM-assisted — not LLM-dependent.** The acceptance criterion ("receive a mission → structured plan → complete an authorised bounded task → explain the result") must pass **even with no model available**, because the owner's hardware/model shortlist is still unknown. So P-02 ships: (a) a rule-based **baseline planner** that decomposes known mission templates into registered-tool steps; (b) an **LLM planner adapter** behind the provider interface that proposes plans in the same schema when a model is configured; (c) identical validation for both — schema check, tool-existence check, permission check, budget check — before any plan can execute. This mirrors the proven ClipOS Phase 10 pattern (deterministic planner, no live model required, proposals never self-apply).
2. **A plan is data, never code.** Plans are typed step lists referencing registered tool names + validated payloads — the same anti-smuggling rule P-01 enforced for tasks (an `os.system` "tool" is rejected at validation).
3. **Model Router policy:** task class → profile (fast/standard/reasoning/coding) → provider availability probe (Ollama `/api/tags`-equivalent) → resource check (P-01 monitoring) → pick smallest sufficient local model → optional cloud only if `CLOUD_AI_ENABLED` and the business budget allows, with the call costed. Router decisions are recorded with reasons (auditable "why this model").
4. **Decision records are first-class:** every CIO decision (plan created, step approved/denied, model chosen, result verified/failed) writes a `decision_records` row with mission/plan correlation, inputs summary, rule/model used, and outcome — this is what "explain its result" reads from.
5. **Result verification is a separate component from execution** (per prompt pack): a step is only "done" when the Verifier confirms the handler's result against the step's declared expectation; unverified results are reported as unverified.

## 3. Data model additions (one Alembic migration, additive)

`missions` (owner text, status, mode, creator) · `plans` (mission FK, version, status draft/approved/executing/completed/failed, plan hash for approval binding) · `plan_steps` (plan FK, order, tool name, payload JSON validated against the tool's schema, expected result, status, task FK once submitted) · `decision_records` (mission/plan/step refs, decision type, actor — rule engine or model profile —, reason, evidence refs, correlation ID) · `model_profiles` (name, task classes, provider, model id, limits) — configuration-grade table, editable only by owner/governance (Article 0: agents cannot edit it).

## 4. API additions (all under /api/v1, same envelope/auth)

`POST /missions` · `GET /missions`, `GET /missions/{id}` · `POST /missions/{id}/plan` (creates a draft plan) · `POST /plans/{id}/approve` (routes through P-01 approvals when L2+ steps present) · `POST /plans/{id}/execute` · `GET /plans/{id}` incl. step states + decision records · `GET /models/profiles`, `GET /models/status` (provider availability, honestly reported) · `GET /decisions?mission_id=…`

## 5. Test plan (gate will require)

Unit: plan schema validation, template decomposition, router selection under (no model / local only / cloud enabled+disabled / resource pressure), decision-record writing, verifier pass/fail/unverified paths. Integration: the acceptance scenario end-to-end with the deterministic planner AND with a fake provider (mission → plan → approve → execute bounded task via P-01 handlers → verified result → explanation assembled from decision records); a plan containing an unregistered tool is rejected; a plan whose parameters change after approval cannot execute; simulation mode blocks external-effect steps; permission-denied step halts the plan and is recorded. Security: prompt-injection text inside a mission cannot create tools, raise permissions, or alter model profiles (Article 0 test, carried into every later phase); model output is parsed as untrusted data and schema-rejected when malformed. Regression: full P-01 suite (76 tests) must stay green.

## 6. Acceptance scenario (the P-02 gate demo)

Mission (owner, supervised mode): *"Check system health and report whether the task system is working."* → CIO produces a structured plan (steps: `core.health_snapshot`, `core.echo_check` self-test) → plan approved → steps execute as P-01 tasks → Verifier confirms both results → CIO explains the outcome **from decision records**, including which planner (rule/model) and which model profile were used, or honestly states no model was used. Plus the negative demos: injection mission fails safely; unapproved L2 plan does not execute.

## 7. Open items (do not block preparation; two affect build choices)

- **Local model shortlist** — still pending the owner's hardware evidence (P-00 carried item). P-02 is designed to be correct without it (§2.1), but the Ollama adapter's default profile names stay empty until hardware is known.
- **Cloud provider choice** — none selected; cloud path ships disabled by default, per ADR-001.
- **Start authorisation** — preparation is complete; the build starts when the owner issues the P-02 prompt or says "P-02 start karo", following the same staging pattern as P-01.
