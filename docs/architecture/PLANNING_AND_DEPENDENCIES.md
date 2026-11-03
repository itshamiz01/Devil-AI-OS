# Planning, Dependency Graphs and Replanning (P-02 §9)

## 1. Plan structure

A `Plan` carries `plan_id`, `mission_id`, `version`, `objective`, `strategy`, `steps`, `status`, `estimated_resource_requirements`, `risk`, `approval_required`, `completion_criteria`, `alternative_strategies`, `validation_errors`, `revision_reason` and `supersedes_plan_id`.

A `PlanStep` carries `step_id`, `title`, `depends_on`, `capability_id`, `expected_output`, `completion_criteria`, `status`, `task_id`, `parallel_group`, `estimated_duration_seconds` and `risk`. Its `task_handler` is a `Literal` restricted to the only three handlers P-01 registers, so a step cannot name a handler that does not exist.

`PlanStatus` (8): `draft`, `validated`, `rejected`, `active`, `superseded`, `completed`, `failed`, `cancelled`.
`StepStatus` (10): `pending`, `ready`, `dispatched`, `running`, `awaiting_approval`, `blocked`, `completed`, `failed`, `cancelled`, `skipped`.

`AWAITING_APPROVAL` exists as its own member rather than being folded into `BLOCKED`. Collapsing the two made "waiting for the owner" indistinguishable from "stuck because something failed", and `ProgressMonitor` then counted cancelled steps as awaiting approval. The distinction is semantic and is preserved.

## 2. Decomposition

`TaskDecomposer` selects a strategy from `STRATEGIES` based on the mission's category and objective. Each strategy is a list of `StepTemplate`s. Verified step counts for representative requests:

| Request | Strategy | Steps |
|---|---|---|
| `"Create a roadmap for launching a digital product."` | roadmap | 5 |
| `"Research an online business opportunity that can be started with $50."` | research | 4 |
| `"Check the system status and report health."` | system status | 3 |

`alternative_strategies` records the strategies that were *not* chosen, so the owner can see that a plan is one option among several rather than the only conceivable one (§9.1).

`MAX_PLAN_STEPS = 24` by default and is configurable through `plan_max_steps` (1–64). A plan exceeding it is **rejected**, not truncated: silently dropping steps from a plan the owner will approve would misrepresent what was approved.

## 3. Dependency graph

**Template keys and emitted step ids are different namespaces.** A template's `depends_on` refers to template keys; the decomposer must translate each into the id of the step it actually emitted. Getting this wrong reports every dependency as unknown and rejects every plan — which is how the defect first appeared.

`DependencyResolver` provides:

| Method | Behaviour |
|---|---|
| `validate_references(steps)` | Rejects a `depends_on` naming a step that does not exist |
| `find_cycles(steps)` | Iterative DFS; reports the cycle rather than recursing until the stack dies |
| `topological_order(steps)` | A valid execution order, or raises on a cycle |
| `assign_parallel_groups(steps)` | Groups steps that can run concurrently |
| `ready_steps(steps)` | Steps whose dependencies have completed — excluding any whose dependency failed or was cancelled |
| `blocked_by_failure(steps)` | Transitively everything downstream of a failed or cancelled step |

`MAX_DEPENDENCIES_PER_STEP` bounds fan-in so a step cannot depend on the whole plan.

The five hazards §9.3 names are each prevented and each tested: circular dependencies, invalid references, duplicate execution, blocked execution, and premature parent completion.

Parallel groups are real: the roadmap plan produces a `parallel-2` group.

## 4. Validation (§9.5)

`PlanValidator.validate(plan, mission)` returns a `ValidationResult` with `valid`, `errors` and `warnings`. Plans are **rejected, never repaired**. Checks include:

- duplicate step ids
- a step naming no capability, or an unregistered one, or one that is registered but unavailable
- a capability that requires a permission nobody holds
- circular dependencies and invalid references
- a step whose risk exceeds the plan's declared risk
- a plan whose risk understates its riskiest step
- a high- or critical-risk step that is not marked `approval_required`
- a mission that requires clarification
- a mission at `CRITICAL` risk with no owner-stated success criteria
- a plan exceeding `ValidationPolicy.max_steps`
- a plan referencing a mission other than the one being validated

Plan risk is `max(mission.risk, riskiest capability risk)`. A `HIGH` or `CRITICAL` step forces `approval_required=True`; the planner cannot opt out.

A mission at `CRITICAL` risk with no success criteria is refused with the reason *"a mission at risk CRITICAL needs owner-stated success criteria before it can be planned; success criteria are never invented"*. Verified: an override request produces `CRITICAL` and a rejected plan.

**The validator never creates a task that no registered capability supports.** An unsupported step is dropped during decomposition; if dropping leaves nothing, the plan is rejected for having no steps. Withdrawing a single capability is therefore not an error — the remaining plan is still valid — but withdrawing every capability a strategy needs is.

## 5. Replanning (§9.6)

`Replanner.revise(previous, mission, reason=..., completed_step_ids=None)` returns `(superseded, revised)`.

- A non-empty `reason` is **required**; a revision that does not record why is refused.
- The previous plan is marked `SUPERSEDED`. It is never deleted, so the full plan history survives.
- `version` increments and `supersedes_plan_id` points back.
- Completed steps are carried over rather than re-executed. When the caller does not supply `completed_step_ids`, the set is **derived from the previous plan itself**. Requiring the caller to pass it meant that forgetting the argument silently re-executed finished work, which §9.3 forbids; the safe behaviour is now the default.
- Steps are matched across versions by **title**, not by id, because a revision renumbers steps. Matching by id would have lost every completed step.
- A silent objective change is refused: the revised plan must still address the mission it was given.
- A revision that fails validation raises `PlanValidationError` and the previous plan stays active.

## 6. Verification status

| Claim | Evidence |
|---|---|
| All of the above | `tests/test_planning.py` — 50 tests |
| Plans validate for all five §20 requests | Executed; initially every plan was rejected until the namespace defect was fixed |
| Cycle detection, reference validation, parallel groups, ready/blocked sets | Tested directly on `DependencyResolver` |
| Replanning preserves versions and completed work | Tested, including the derived-default path |
| Success criteria are never invented | Tested via the `CRITICAL`-risk rejection |
