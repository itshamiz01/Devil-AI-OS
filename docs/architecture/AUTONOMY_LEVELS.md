# Autonomy Levels and Safety Boundaries (P-02 §15, §16)

## 1. Levels

`AutonomyLevel` declares five members so the boundary is explicit and refused by code rather than merely absent.

| Level | Value | May submit tasks | May retry autonomously | May replan autonomously | P-02 status |
|---|---|---|---|---|---|
| 0 | `0_advisory` | **No** | No | No | **Implemented**; the default |
| 1 | `1_assisted_execution` | Yes | No | No | **Implemented** |
| 2 | `2_controlled_autonomy` | Yes | Yes | Yes | **Implemented** |
| 3 | `3_delegated_business_operations` | — | — | — | **Not supported**; refused |
| 4 | `4_multi_business_coordination` | — | — | — | **Not supported**; refused |

`EXECUTION_PERMITTED_LEVELS = {LEVEL_1, LEVEL_2}` and `UNIMPLEMENTED_LEVELS = {LEVEL_3, LEVEL_4}`.

Level 0 is advisory and **cannot submit execution tasks** (§15). This is the single most consequential guarantee in the phase, and it holds even after the owner approves a plan.

## 2. Two independent refusals for levels 3 and 4

- `Settings.autonomy_level` is a `Literal` of the three permitted values, so levels 3 and 4 are **rejected at configuration load**. Verified: `3_delegated_business_operations` and `4_multi_business_coordination` both fail startup.
- `AutonomyController` refuses them at construction *and* at `request_change`, raising `AutonomyEscalationError` **even when `authorized_by_owner=True`**. Owner authorization is necessary but not sufficient: the capability does not exist, so it cannot be granted.
- The API request schema rejects them with `422`, so they cannot be requested over HTTP either.

Three layers, because a single check that is later relaxed would silently enable an unimplemented capability.

## 3. Changing level requires the owner

`request_change(target, principal_id=..., authorized_by_owner=..., reason=...)` raises `AutonomyEscalationError` when:

- the target is in `UNIMPLEMENTED_LEVELS` — unconditionally
- `authorized_by_owner` is false — *"a model may not upgrade its own autonomy"*
- `principal_id` is empty — an authorization must name who gave it
- `reason` is blank — a level change must record why

Every outcome, including refusals, is appended to `history`. A silently refused escalation would be as misleading as a silently granted one, so refusals are recorded rather than dropped.

`AutonomyState` records `level`, `set_by_principal_id`, `set_at` and `reason`. `describe()` returns the current state, the permissions the level grants, and an explicit note that the permission engine remains authoritative.

At the HTTP boundary, `POST /api/v1/intelligence/autonomy` requires the owner-only `intelligence.autonomy` permission and sets `authorized_by_owner=True` **only because that permission check passed** — never from a value in the request body. A caller cannot assert their own authorization.

## 4. The permission engine stays authoritative

Regardless of level, `PermissionEngine` decides what any principal may do. Autonomy is an *additional* restriction the intelligence layer imposes on itself; it never relaxes a P-01 permission check. Raising the level to 2 does not grant `tasks.write` to a principal that lacks it, and does not make an approval requirement disappear.

## 5. The eleven safeguards (§16)

| # | Never | How it is enforced |
|---|---|---|
| 1 | Bypass the permission engine | Dispatch goes only through `TaskManager.submit`; no alternative path exists |
| 2 | Execute financial operations | Interpreter classifies them `CRITICAL`; phase flag rejects `financial_execution_enabled` |
| 3 | Launch a real business | No capability exists; `CapabilityRegistry` refuses handlers outside `REAL_HANDLERS` |
| 4 | Give a model unrestricted tool access | Models return text; only `StructuredOutputParser` consumes it, and it refuses authority fields |
| 5 | Treat model output as verified fact | `Evidence` validator makes `MODEL_GENERATED` + `VERIFIED` unconstructable |
| 6 | Self-escalate autonomy | `request_change` requires `authorized_by_owner` and a named principal |
| 7 | Invent a budget, authorization or success criterion | `success_criteria` is always empty unless owner-stated; `CRITICAL` missions without one cannot be planned |
| 8 | Silently switch to a paid provider | Cloud candidates excluded at selection; tested on the exact list of models tried |
| 9 | Mark a failed mission completed | `completion_state` returns `FAILED` if any step failed; a missing task row is `BLOCKED` |
| 10 | Exceed the context budget by dropping a financial cap | `assemble(strict=True)` raises `ContextOverflowError` |
| 11 | Present a weighted score as a probability | Every `reasoning_summary` says it is not; weights documented as an ordering heuristic |

## 6. Five distinct things (§16)

The system distinguishes, and never conflates:

1. **recommendation** — what the engine produced
2. **decision proposal** — a recommendation put forward for a decision
3. **authorized decision** — one with an owner's name on it
4. **executable task** — submitted to P-01
5. **completed action** — a task that actually finished

`DecisionStatus` has a member for each of the first four, and `COMPLETED` for the fifth. `to_proposal` accepts only a `RECOMMENDATION`; only `record_authorization` produces `AUTHORIZED`; only dispatch produces an executable task; only a persisted `COMPLETED` task row produces a completed action.

## 7. Permissions

Four codes were added, all owner-only, all derived into `OWNER_PERMISSIONS` and deliberately absent from `SYSTEM_PERMISSIONS`:

| Code | Guards |
|---|---|
| `intelligence.use` | `chat`, `analyze` |
| `intelligence.read` | `missions` list/detail, `progress`, `models`, `status` |
| `intelligence.manage` | `plan`, `approve`, `pause`, `cancel`, `replan` |
| `intelligence.autonomy` | `autonomy` |

Because they are absent from `SYSTEM_PERMISSIONS`, the application can never reason about, re-plan or re-authorize itself on its own authority. `SYSTEM_PERMISSIONS` remains exactly `['system.read', 'tasks.read', 'events.read']` — verified unchanged. Total permission codes: **24** (was 20).

An agent principal receives `403` on every intelligence endpoint; this is tested per operation.

## 8. Verification status

| Claim | Evidence |
|---|---|
| Level 0 cannot submit tasks, even after approval | `test_advisory_level_approves_but_dispatches_nothing` — asserts `dispatched == []` **and** that the P-01 task list is empty |
| Levels 3/4 refused at config load, at construction, at `request_change`, and over HTTP | Four separate tests |
| Model self-escalation refused | `AutonomyEscalationError`; tested |
| Owner authorization works and is audited + published | Tested, including the `AutonomyLevelChanged` event |
| `authorized_by_owner` never taken from the request body | Verified in the route; `extra="forbid"` rejects an unexpected field |
| Agent principal refused on every operation | Parametrised over six operations |
| Recovery does not restore an escalated level | `test_recovery_does_not_resume_execution` |
