# Agent assignment and orchestration (P-04 Stage 6)

Stage 6 answers one question — *may this piece of work be given to this agent?* —
and one follow-up: *did the result satisfy what the work asked for?*

It is implemented in `backend/app/agents/assignments.py` behind
`AssignmentService`, recorded in the `agent_assignments` table Stage 2 created, and
exposed at `/api/v1/agents/{agent_id}/assign` and `/api/v1/assignments`.

It does **not** run anything. Execution stays with `TaskManager`, and an assignment
module that also dispatched work would be a second scheduler with its own idea of
what is allowed to run. The ledger says who was given work; the task manager says
what happened to it.

Related documents: [AGENT_GOVERNANCE.md](AGENT_GOVERNANCE.md) §3 for the task
lifecycle this plugs into, [AGENT_CAPABILITIES.md](AGENT_CAPABILITIES.md) for the
authority rule 7 consults, and [AGENT_FACTORY.md](AGENT_FACTORY.md) for the
creation decision that can now name work.

## 1. The nine rules

Rules run in order and stop at the first refusal. A refusal names the rule that
refused, so a caller learns which condition failed rather than only that something
did. The names are the literal strings in `ASSIGNMENT_RULES`, in this order:

| # | Rule | Refuses when | Source |
|---|---|---|---|
| 1 | `task_exists_and_is_assignable` | The task does not exist, or its state is `VALIDATING`, `RUNNING`, `WAITING_FOR_APPROVAL` or terminal | governance §3 step 1–2 (scope, dependencies) |
| 2 | `task_is_not_already_assigned` | A live assignment or the task's own pointer already holds it | `agent_assignments.task_id` UNIQUE; governance "reassign only after revoking the previous lease" |
| 3 | `emergency_stop_clear` | The global stop is active | `TaskManager` admission precedent; factory check 1 |
| 4 | `agent_can_accept_work` | The agent does not exist, or is not `ACTIVE`/`IDLE` | lifecycle states; Stage 5's ungrantable-state rule |
| 5 | `delegation_within_limit` | Depth exceeds `AUTONOMOUS_AGENT_MAX_DELEGATION_DEPTH`, or the parent chain cycles | governance §11 "reject quota/depth/cycle violations"; factory check 4 |
| 6 | `business_scope_matches` | The task declares a business the agent is not inside | governance §11 "enforce business isolation" |
| 7 | `agent_holds_required_capabilities` | `CapabilityService.check()` denies any required key | plan §2 "assignment validation"; governance §3 step 4 "scoped capabilities" |
| 8 | `no_permission_escalation` | A required key is outside the template's `allowed_capabilities` | governance §11 "prevent permission escalation" |
| 9 | `concurrency_within_budget` | In-flight assignments already fill the template's `max_concurrent_tasks` | governance §11 quota; `ResourceBudget` from Stage 3 |

**The enumeration is reconstructed, not quoted.** The P-04 brief's own list of nine
is not in this repository, and `P04_IMPLEMENTATION_PLAN.md` §2 refers to "the nine
assignment rules" without naming them. Rather than invent nine and present them as
the brief's, each rule above names the document, column or existing check it comes
from, and the count is what those sources support. If the owner's list differs, the
difference is a documentation fix and a rule change, not a hidden assumption.

Three rules deserve their reasoning stated:

* **Rule 6 says when it could not check anything.** Tasks carry no `business_id`
  column; only a task's JSON payload can declare one. When it does, an agent outside
  that business is refused — including an agent belonging to *no* business, which
  cannot show it is inside one. When the payload declares nothing, the rule passes
  and its detail says isolation could not be checked against a business, rather than
  implying a boundary was verified.
* **Rules 7 and 8 ask different questions.** Rule 7 asks whether the agent *holds*
  the authority; rule 8 asks whether its template ever *authorized* it. Both are
  needed: a capability granted outside the template's allowed set passes rule 7 and
  is caught by rule 8, which is the escalation case.
* **Rule 9 counts only in-flight work.** `completed`, `failed` and `cancelled` rows
  do not consume budget, because an agent's history must not limit its future.

## 2. Refusals write nothing

A refusal produces no ledger row and no event. The vocabulary has no `refused`
member, and adding one would let the table be read as a list of work that includes
work nobody was ever given. A refusal is an audit row (`assignment.refused`,
outcome `denied`) carrying the rule and the reason, and the HTTP response is a
`409` whose `details.evaluation` holds every rule that ran.

This mirrors Stage 5's capability refusals, with one difference: the whole
evaluation is returned, because an assignment refusal is a decision about work
rather than a prohibition, and the rules that *did* pass are part of the answer.

## 3. One row per task, so reassignment supersedes

Stage 2 put a `UNIQUE` on `agent_assignments.task_id`. Stage 6's semantics want a
history; that constraint allows one row per task.

A row in a terminal status is history rather than a hold, so it does not block
reassignment — work has to be movable, and governance requires reassignment
precisely *after* the previous hold is released. Reassignment therefore **supersedes
the row in place**: the new agent, contract, priority and depth replace the old, and
`failure_reason` keeps `superseded: previously held by agent <id>, which reached
'<status>'`. That is the only place the previous holder survives.

Dropping the `UNIQUE` would give a per-attempt ledger, which is what governance's
fencing/attempt identifier eventually needs. It was not done here: the constraint is
unnamed in the existing schema, and `batch_op.drop_constraint(None, type_='unique')`
fails with `AttributeError: 'NoneType' object has no attribute 'get_context'` —
verified, not assumed. Removing it needs a hand-rolled table rebuild, so it is
recorded as a limitation for P-05 rather than done quietly.

## 4. The output contract

`POST /assignments/{id}/complete` judges the result against the assignment's
`expected_output_schema`. A reported success that does not satisfy the contract is
recorded as **`failed`**, with the violations listed. Without that, "done" means
whatever the agent said.

The validator implements a deliberate subset of JSON Schema — `type`, `required`,
`properties`, `items`, `additionalProperties` — because adding a schema dependency
for one call site is a heavier commitment than the check needs, and the subset
covers what a template's `expected_output_schema` can express. Two edges are
handled explicitly rather than left to chance:

* A contract naming a type this validator does not implement is **refused**, not
  passed. An unchecked result recorded as verified is worse than a refusal.
* An empty schema declares no contract and accepts anything. The completion reason
  then says the result was recorded *unjudged*, so a pass is never silent about
  having checked nothing.

`True` is not an integer: Python treats `bool` as `int`, and a contract asking for a
number should not accept a flag.

## 5. Statuses and transitions

`assigned` → `in_progress` → `completed` | `failed` | `cancelled`, with `assigned`
also able to reach `completed`, `failed` and `cancelled` directly. The three
terminal states have no successors.

`assigned` may reach `completed` without passing through `in_progress` because work
can finish before anyone recorded it starting. Refusing that would push callers to
report a start they never observed, and a fabricated `started_at` is worse than a
null one that reads honestly as "we did not see it begin".

## 6. `ASSIGN_EXISTING` is emitted now

`CreationRequestInput` gained an optional `task_id`. When a creation request names
work and an agent already fills the role, the factory answers `ASSIGN_EXISTING`
instead of `REUSE_EXISTING`: the first is an answer about work, the second about
identity. Without a named task the Stage-4 answer is unchanged.

The executor then runs the nine rules through `AssignmentService`. The factory
deciding that an agent *should* take work is not evidence that it *may*, and a
refusal is recorded on the creation request rather than retried. `ASSIGN_EXISTING`
publishes no creation event — the assignment publishes `AgentAssignmentChanged`,
which says what actually happened instead of implying an agent was created.

Because a created agent holds zero capabilities (L-73), an `ASSIGN_EXISTING` that
names required capabilities is refused at rule 7 until those grants exist. That is
the rules working, not a defect in the decision, and it is recorded as a limitation.

## 7. Authorization

`agents.write` (new in Stage 6, owner only) covers assign, start, complete and
cancel. `agents.read` covers the ledger and its status. Assignment is a write and
deliberately is not covered by `agents.read`, which has only ever looked at the
registry: widening a read permission would have made every existing reader able to
commit work. Neither code is in `SYSTEM_PERMISSIONS`, so the application can never
assign work to an agent on its own authority.

## 8. Verification

Numbers below were read back from the running code and a rendered migration, not
recalled:

* **83 paths / 91 operations** in `create_app(Settings()).openapi()` (75/83 after
  Stage 5); the eight assignment operations are all present.
* **58 event types** (57 after Stage 5); `AgentAssignmentChanged` is the addition.
* **35 permissions** (34 after Stage 5); `agents.write` is the addition.
* **9 rules, 5 statuses**, read back from `ASSIGNMENT_RULES` and
  `ASSIGNMENT_STATUSES`.
* Migration chain **nine revisions deep**, head `d577d056a63b` on `e8b2ced758fc`.
* Stage-6 delta rendered offline against Postgres: **1** `UPDATE alembic_version`,
  **2** `ADD CONSTRAINT`, **1** `CHECK (`, **1** `SET DEFAULT`, **1** `ADD COLUMN`,
  **1** `CREATE INDEX`, **2** normalization `UPDATE`s, **0** `CREATE TABLE`, **0**
  SQLite-isms; `ck_agent_assignments_status`,
  `fk_agent_creation_requests_task_id` and `ix_agent_creation_requests_task_id`
  each appear exactly once. Whole chain: 44 `CREATE TABLE`, 13 `CHECK (`, 1
  `INSERT` + 8 `UPDATE` on `alembic_version`, 0 SQLite-isms.
* **33 tests** in `tests/test_agents_assignments.py` and **14** in
  `tests/test_agents_schema_stage6.py`, covering every rule's refusal by name, the
  contract's accept/refuse/unjudged cases, forward-only transitions, supersede on
  reassignment, and `ASSIGN_EXISTING` both emitted and refused.
