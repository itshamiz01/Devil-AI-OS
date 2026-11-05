# Execution Policy and the Execution Core (P-05 Stage 2)

Stage 2 builds the part of the Universal Digital Execution Engine that decides,
records and queues — and deliberately not the part that acts. There is no adapter
in this stage: nothing reads a file, runs code, or touches a network. What exists
is the machinery every adapter will have to go through, built and tested before
any adapter can exist, so that when Stage 3's filesystem adapter arrives it
inherits a boundary rather than inventing one.

| Component | Module | What it does |
|---|---|---|
| Vocabularies | `app/execution/schemas.py` | The 14 outcomes (§6.1), the 7 tool states (§7), risk classes (§8), adapter families, request/tool models |
| Policy engine | `app/execution/policy.py` | §8.1's ten deterministic checks, risk classification, standing authorizations, approval binding |
| Tool registry | `app/execution/registry.py` | Tool registration, validation to AVAILABLE, disable, discovery |
| Request manager | `app/execution/requests.py` | Submission (§4 steps 3–9), approval opening, retry, cancellation, reads |
| Assembly | `app/execution/subsystem.py` | `build_execution` / `initialize`; wires P-04 capabilities, P-01 approvals, monitor, emergency |
| Persistence | `execution_*` / `workflow_*` / `browser_sessions` tables | Revision `229ca08ee712`; nine tables, 18 named CHECKs |

## The vocabulary is the brief's, and it is closed in the database

`EXECUTION_OUTCOMES` is §6.1's list verbatim, in the brief's order:
`ACCEPTED, VALIDATING, AWAITING_APPROVAL, QUEUED, RUNNING, COMPLETED,
COMPLETED_WITH_WARNINGS, FAILED, REJECTED, CANCELLED, TIMED_OUT, INTERRUPTED,
REQUIRES_HUMAN_ACTION, REQUIRES_RECONCILIATION`. Transitions between them are a
closed graph in `OUTCOME_TRANSITIONS`; terminal outcomes have no successors, and
`REQUIRES_RECONCILIATION` is terminal on purpose — §16.4 requires a person to
open a new request with reconciled facts rather than the engine resuming an
interrupted external action on its own authority.

The same vocabulary is a named CHECK constraint (`ck_execution_requests_status`)
on the table, rendered from the same tuple the code imports, so the statuses the
code can produce and the statuses the database accepts cannot drift apart. The
schema tests insert every one of the fourteen outcomes and assert a fifteenth is
refused.

**`COMPLETED` is not the default.** §6.1's rule — the engine must not return
COMPLETED merely because a tool returned without raising — is why two success
states exist and why `execution_runs.verification_status` is a separate column
written by a result validator, not by the adapter that did the work. What was
*requested* (the request row), what was *approved* (the approval binding), what
was *executed* (`execution_runs.executed_action`) and what was *verified* (the
run's verification status) are four different records, because §6 forbids
assuming they are identical.

## The ten checks (§8.1), in order, stopping at the first failure

`ExecutionPolicy.evaluate` runs `POLICY_CHECKS` in the brief's order:
`agent_identity`, `agent_status`, `assigned_task`, `required_capabilities`,
`requested_scope`, `tool_status`, `risk_category`, `approval_status`,
`resource_limits`, `policy_restrictions`. A refusal names the check and carries
every earlier check's pass, so a caller can tell a fixable no (grant a
capability) from a permanent one (the action is prohibited). Priority is read
only by the resource check — §8's rule that a high-priority task must never
override risk classification is structural: the risk check never sees priority.

Properties worth singling out:

- **Risk is computed, never declared.** The request model has no risk field.
  Classification comes from the tool's registered risk and the action name; a
  prohibited action name (the code-level `PROHIBITED_ACTIONS` list from §8's
  Risk-3 examples) classifies as Risk 3 whatever the tool declares, so a tool
  cannot launder a prohibited action by registering itself as safe. Risk 3 has
  **no approval path**: the check refuses before any approval is consulted.
- **Identity is the principal's.** The request model has no agent field. The
  agent is resolved from the authenticated principal (`agents.principal_id`),
  so holding `execution.submit` is not enough to submit as somebody else —
  and the owner, who holds every permission code, cannot submit at all,
  because no agent is bound to the owner principal. Authority to permit is
  not identity to act.
- **Capability checks use P-04's authority.** The merged requirement — the
  tool's declared capabilities plus the request's — is put to
  `CapabilityService.check()` (assignment rule 7's other caller). A missing
  authority fails closed: the work is refused as unverifiable rather than
  admitted on trust. Note the honest consequence at this stage: the catalog's
  execution entries (`filesystem.read`, `code.execute`, `execution.tool`, …)
  are still `enabled=False`, so a tool declaring one is refused with "the
  capability is disabled" until the adapter that exercises it lands (L-82).
- **Two gates refuse by construction, and say so.** `api` and `browser`
  adapters fail `policy_restrictions` because `external_execution_enabled` is
  locked false — the P-01 settings validator refuses to start with it on.
  That is a phase boundary, not a bug: the check exists so the refusal is
  recorded against the request instead of discovered inside an adapter.
- **Resource pressure queues only essential work.** Under
  `SystemMonitor.resource_pressure()`, priority 9–10 proceeds and the rest is
  refused with the pressure named, rather than the system competing for a
  loaded machine. In Stage 2 that refusal is terminal (L-81); the scheduler
  stage owns turning it into a wait.

## Approvals: one queue, bound by hash

A Risk 2 request (or one whose tool declares `required_approval_level >= 2`)
that policy cannot otherwise clear opens an approval in the central
`approvals` table — action `execution.execute`, resource the request's id,
risk translated through `APPROVAL_RISK_BY_CLASS` (the approval service's
`low/medium/high/critical` is not `RiskLevel`'s vocabulary, and the two are
kept apart on purpose). The approval's payload hash commits to tool, action,
parameters and scope (`binding_parameters`), so on retry
`ApprovalService.verify_binding` proves the request being admitted is the
request that was approved — the substituted-request test changes the
parameters after approval and is refused.

Two tables from §19 are deliberately **not** created: `execution_approvals`
(the central table carries these) and `execution_audit_events` (`audit_events`
and `system_events` already record execution decisions). One approval queue
for the owner is the property the design protects.

Approval states are three-way, and the distinction matters: *approved and
bound* admits; *pending and unexpired* returns the request to
`AWAITING_APPROVAL` unchanged (an impatient retry must not destroy a request
the owner is about to decide); *rejected, expired, or bound to different
parameters* refuses — §25.3's "an expired approval cannot authorize a new
action" is enforced at exactly this point.

**The approval opens outside the request's transaction.** Submission commits
the request row first, then creates the approval, then records the reference
in a short second transaction. Creating it inside the submission's session
deadlocks on SQLite: the request's uncommitted write holds the writer lock
the approval's own session needs. The intermediate state is visible only
between two commits inside one call, and retry opens the approval there
instead if submission somehow left none.

## Standing authorizations (§17)

Owner-configured, narrowly scoped standing authorizations live in
`system_configurations` under `execution.standing_authorizations` as
`{"authorizations": [{id, agent_id, tool_id, action_name, scope, max_uses,
expires_at, revoked}, …]}` — each entry carries the scope, limit, expiry and
revocation fields §17 requires. Matching is deterministic: agent, tool and
action must match (or be wildcarded), the granted scope must cover the
requested one by prefix, and the entry must be unexpired and unrevoked;
anything malformed fails closed (no match) without raising. Usage is counted
from the requests table itself — rows admitted under that authorization —
never from a figure the requester supplies. What the count includes is stated
in L-83.

## The tool registry: registration declares, validation admits

A registered tool lands at `REGISTERED`. Only validation moves it, through
`VALIDATING`, to `AVAILABLE` — reachable from no other state, per §7's rule
that a tool must not become available until its configuration and health
checks pass. Validation runs five deterministic checks: the adapter can run
in this environment at all, the tool declares actions, its risk class is one
the system may route (a Risk 3 tool can never be available), a sensitive tool
actually requires the approval its risk demands, and a code tool has declared
what isolation was *verified* (§30 rule 22 — an undeclared strength is an
unverified one). A failed validation disables the tool with the failures
recorded: checked-and-wanting is a different fact from never-checked, and the
registry says which it is holding. Real adapter health probing arrives with
the adapters (Stages 3–4) and reports through the same `health_status`.

The browser and desktop tools are registered at startup — `DISABLED`, health
`unsupported`, reason recorded ("no browser binary and no display…", "no
Windows UI Automation…"). The registry answers "is there a browser tool?" with
"yes, and here is why it cannot run" instead of "no", which would invite
somebody to register one. Their §21 routes are likewise **not registered**:
an endpoint that cannot work must not exist.

Discovery (`ToolView`) is narrower than the row on purpose: descriptions,
actions, contracts, capabilities and risk — never `configuration_reference`,
which is where a secret's address would live (§7).

## What Stage 2 does not do

`GET /api/v1/execution/status` reports it rather than implying otherwise:
`adapters.filesystem/code/api/document/data` are `false`, `scheduler` is
`false`, `workflows` is `false`, and `execution_draining` is `false` — QUEUED
is a waiting state in a queue nothing drains until Stages 3–4 land adapters.
Request expiry timestamps are recorded and reported; nothing sweeps them
(recovery is Stage 8's). Browser, desktop and frontend stages (5, 6, 10) are
deferred with reasons, per the plan: no browser binary, display, Windows UI
Automation or frontend exists in this environment.

## API summary

Eleven operations under `/api/v1/execution` (full table in
[API_REFERENCE.md](API_REFERENCE.md)): requests submit/list/get/retry/cancel,
tools list/get/register/validate/disable, and the status report. Seven new
permission codes (`execution.read`, `execution.submit`, `execution.files.write`,
`execution.code.run`, `execution.api.call`, `execution.workflows.write`,
`execution.admin`), add-only, owner-derived, and none in `SYSTEM_PERMISSIONS`
— the application can never submit, approve or administer its own execution.
There is deliberately no permission code for Risk 3 operations: a code would
imply the capability exists and merely needs granting.
