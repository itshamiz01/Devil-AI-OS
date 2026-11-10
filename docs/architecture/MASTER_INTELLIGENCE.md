# AUTONOMUS — Master Intelligence Engine (P-02) — Architecture (as built)

The Master Intelligence layer turns a mission (plain-language intent from a
principal) into a governed, verifiable plan of P-01 tasks. It contains **no
execution capability of its own**: every unit of work still runs as a P-01
task through `TaskManager.submit`, under the P-01 permission engine, the
P-01 approval framework and the P-01 event bus. Intelligence proposes;
the deterministic policy layer disposes.

Package: `backend/app/intelligence/`. Design source:
`docs/reports/P02_PREPARATION.md` (owner-approved design, followed as built).

## 1. Deterministic-first planning

Two planners produce the **same** artefact — a `PlanProposal` (typed data,
never code) — and both pass through **one identical validation gate**:

1. **Baseline planner** (`planner.BaselinePlanner`) — a rule engine with
   three mission templates:
   - `system_health_check` (mission mentions "health"): `core.health_snapshot`
     (expect `ok=true`) → `core.echo_check` "task system self-test"
     (expect `echo.message` echoed back).
   - `wait_and_report` (mission mentions "wait"): `core.wait` with the
     duration parsed from the text (clamped to 10 s; expect `waited_ms`)
     → `core.echo_check` "wait complete".
   - `echo_message` (text starts with `echo `/`echo:`): one `core.echo_check`
     step expecting its own message back.
   No template match → no baseline plan (honest failure, never a guess).
2. **LLM planner adapter** (`providers.ModelProvider`) — a provider
   interface with two implementations:
   - `OllamaProvider`: probes `GET /api/tags`, plans via `POST /api/chat`
     with `format=json`. Uses `trust_env=False` — a local inference server
     is never reached through a system proxy. When no server/models
     respond it reports **unavailable**, plainly.
   - `CloudProviderStub`: exists so the router has a real branch to refuse.
     Returns "cloud AI not enabled" unless `AUTONOMUS_CLOUD_AI_ENABLED` is
     set — and even then reports that no cloud provider is configured in
     P-02. **No cloud vendor is wired.**
   - `FakeProvider` (tests only): scripted output/availability/delay.

**Identical validation** (`planner.PlanValidator`) for both planners:
plan schema → every step's tool exists in the P-01 `HandlerRegistry` →
payload validates against that handler's pydantic model → permission
pre-check via `PermissionEngine.check` for the planning principal.
A plan naming an unregistered tool (e.g. `os.system`) is rejected, the
rejection is recorded, and — for LLM output — the plan row is persisted
with status `rejected`. Malformed/timeout LLM output is *not* persisted as
a plan: it is recorded (`llm_plan_unusable`) and planning falls back to the
baseline planner, or fails honestly if no template matches.

## 2. Model router

`router.ModelRouter.select(task_class)`:
enabled `model_profiles` whose `model_id` is non-empty and whose
`task_classes` cover the class (or `*`), ordered by `limits.size_rank`
(smallest sufficient first) → profiles marked `requires_headroom` are
skipped while the P-01 monitor reports threshold violations → the
provider is probed; first available provider wins. Otherwise the baseline
planner is selected. **Every selection is recorded with its reasons.**
Seeded profiles (`fast-local`, `standard-local`, `coding-local`,
`reasoning-local`) ship with `model_id=""` and `enabled=False`: the owner's
hardware was unknown at build time (later evidence: CPU-only inference),
so **no default model was invented**.

## 3. Tool registry view

`tools.ToolRegistryView` wraps the P-01 `HandlerRegistry` with governance
metadata: `core.noop` L0, `core.health_snapshot` L0, `core.echo_check` L1,
`core.wait` L1 — all read-only/internal, all requiring `execute_tools`.
Level ≥2 tools (none exist yet) would additionally require the P-01
approvals flow per step.

## 4. Approvals and hash binding

Plan approval goes through the P-01 approvals service: action
`plan.execute`, resource `plan:{id}`, parameters `{"plan_id", "steps":
canonical_steps}`. The SHA-256 of the canonical steps is stored on the
plan (`plan_hash`) together with the `approval_id`. At execution time the
hash is recomputed from the stored steps; any post-approval modification
(payload, tool, order, expectation) fails the comparison → execution is
refused and a `plan_tampered` decision is recorded (also audited).

**Approval mapping (documented design decision):** all four `core.*`
handlers are L0/L1 read-only-internal, so one plan-level approval by the
Owner through `POST /plans/{id}/approve` (which itself requires the
`approve_actions` permission — Owner role only in the default policies)
covers the whole plan. If a future plan contains an L2+ step, per-step
P-01 approvals will be required in addition; no such tool exists in P-02.

## 5. Mode enforcement (`Settings.mode`, unchanged from P-01)

| Mode | Plan | Approve | Execute |
|---|---|---|---|
| simulation | ✅ | ✅ | ❌ blocked, `execution_blocked_mode` recorded |
| supervised | ✅ | ✅ (required) | ✅ approved plans only |
| controlled | ✅ | ✅ (required) | ✅ approved plans, no per-step prompts within scope |
| emergency | ✅ | ✅ | ❌ blocked, `execution_blocked_mode` recorded |

Unapproved execution in supervised/controlled is refused with an
`execution_blocked_unapproved` record. **The system never changes its own
mode** — mode is configuration, set by the owner outside the agent's reach.

## 6. Execution coordinator + result verifier

`service.IntelligenceService.execute_plan` re-checks mode, approval and
hash, then **re-validates every step's permission at execution time** (not
only at plan time) before submitting each step via `TaskManager.submit`
with idempotency key `plan:{plan_id}:step:{step_id}`. Steps run in order;
each resulting task is polled to a terminal state and passed to the
`verifier.ResultVerifier`, which compares the task result with the step's
declared `ExpectationSpec`:

- **verified** — task completed, `ok` matches, every expected field equals.
- **failed** — task did not complete, `ok` is not true, or a value differs.
- **unverified** — the outcome *cannot be confirmed* (no machine-checkable
  expectation, or an expected field is absent from the result). Unverified
  is a first-class, honest outcome — never silently upgraded to verified.

Any failed/unverified step halts the plan: later steps are never
submitted, the plan is marked `failed`, and the reason is recorded.

## 7. Decision recorder, context, events

Every CIO decision is a `decision_records` row: type, actor (`rule-engine`,
`llm:<provider>:<model>`, `verifier`, `owner:<id>`, `system`), reason,
evidence, correlation ID. Security-relevant types (`injection_detected`,
`plan_rejected`, `plan_tampered`, mode/unapproved blocks, permission
denials at execution, profile edits and denied edits) are **also written
to the P-01 audit log**. Mission text is scanned at intake for injection
patterns ("ignore your rules", "create a tool", "raise your permissions",
"edit model profiles", "bypass approval", …); a match is recorded as
`injection_detected` — detection never grants anything: the text is still
only eligible for the same safe templates as any mission.

`context.ContextManager` assembles per-mission working context strictly
from that mission's own row, its plans and its decision records — no
cross-mission data is reachable through it.

New EventBus types: `MissionReceived`, `PlanCreated`, `PlanApproved`,
`PlanExecutionStarted`, `StepVerified`, `StepVerificationFailed`,
`DecisionRecorded`, `PlanCompleted`, `PlanFailed` (critical/persisted:
PlanApproved, PlanFailed, StepVerificationFailed, DecisionRecorded).

`GET /plans/{id}/explanation` is assembled entirely from stored records:
mission, planner used, `llm_used` flag with an explicit honesty statement
("No LLM was used…" for rule-engine plans), per-step task + verification
outcomes, and the full decision trail.

## 8. Data model (one additive migration `c7a21f9e04b3`)

`missions` (text, creator, status, mode at intake, matched template) ·
`plans` (mission FK, version, planner, model profile, status, plan_hash,
approval_id, rationale) · `plan_steps` (plan FK, order, tool, payload,
expectation, task class, status, task_id, verification outcome) ·
`decision_records` (mission/plan/step refs, type, actor, reason, evidence,
correlation) · `model_profiles` (name, task classes, provider, model_id,
enabled, limits) — **editable only by the Owner principal (Article 0)**;
any other principal gets 403 and the attempt is recorded and audited.
