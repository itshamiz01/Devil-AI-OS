# P-05 Implementation Plan — Universal Digital Execution Engine

Companion to `P05_PRE_IMPLEMENTATION_AUDIT.md` (Stage 1). Follows the
prompt's §29 stage order 1→11; stages are listed with the module that
implements each. Conventions are inherited from P-01–P-04: package per
phase, models + repositories per phase, service layer enforcing policy,
thin routes, typed errors on the `AutonomusError` hierarchy, `{success,
data, error, correlation_id, meta}` envelope, additive Alembic migration.

## 1. Module structure (`backend/app/execution/`)

| Module | Responsibility (§5.1 component) |
|---|---|
| `constants.py` | Risk levels, §6.1 outcomes, tool seed definitions, execution-settings defaults, error categories, capability-support map |
| `errors.py` | Typed errors: `ExecutionRejectedError`, `ExecutionPolicyError`, `AdapterUnavailableError`, `PathValidationError`, `WorkspaceError`, `WorkflowInvalidError`, `StandingAuthorizationError`, etc. |
| `schemas.py` | Pydantic payload models for every tool action + request/workflow inputs (validation before policy) |
| `paths.py` | Platform-first path validator (§9.2): Windows lexical rules + POSIX resolve + symlink/junction re-check |
| `workspaces.py` | Execution Environment Manager (§5.1 H): managed workspace provisioning, per-agent isolation, quarantine |
| `policy.py` | Execution Policy Engine + Capability Validator (§5.1 B/C): the §8.1 ten checks, risk mapping, standing-authorization matching |
| `registry.py` | Tool Registry (§5.1 E): seed, lifecycle transitions, health, restricted discovery view |
| `credentials.py` | Credential broker interface (§13.3): `EnvCredentialBroker` resolving `env:NAME` refs at execution time; values never returned to callers |
| `adapters/base.py` | Adapter interface: `execute(action, params, context) -> AdapterResult` + `health()` |
| `adapters/filesystem.py` | §9 adapter (list/read/metadata/hash/search/create/write/append/copy/move/mkdir/delete→quarantine/delete_permanent) |
| `adapters/documents.py` | §14 text/Markdown/CSV create/read/transform/summarize over the filesystem adapter's validated paths |
| `adapters/code.py` | §10 controlled Python subprocess adapter (argv-only, jailed temp dir, scrubbed env, timeout + tree kill, caps, pattern screen hooks) |
| `adapters/api.py` | §13 generic HTTP adapter over an injectable SSRF-guarded transport (real `HttpTransport` / `MockTransport`) |
| `adapters/browser.py` | §11 session/policy layer; fetch backend for read actions; interactive backend reporting unavailable in this environment |
| `adapters/desktop.py` | §12 interface, permanently disabled in this environment (no code path performs a desktop action) |
| `workflows.py` | §15/§16: definition validation (data only), run state machine, checkpoints, compensation registry, recovery scan |
| `service.py` | ExecutionRequestService + Adapter Manager + Scheduler + Evidence Collector + Result Validator + Audit + Recovery + emergency stop + health report + metrics (§5.1 A/F/G/J/K/L/M) |

Data: `app/database/models/execution.py`, `app/database/repositories/execution.py`.
API: `app/api/routes/execution.py`, `app/api/schemas/execution.py`.
Wiring: `app/core/application.py` (build + seed + recovery scan),
`app/main.py` (router), `app/events/events.py` (event types),
`app/core/config.py` (additive settings), `app/agents/constants.py`
(supported flags/descriptions for the six P-05 capabilities).

## 2. Execution lifecycle (one request)

```
submit(principal, agent_id, tool, action, parameters, task_id?,
       idempotency_key?, expected_outcome?, priority)
  → row created: status=ACCEPTED, requested_action recorded
  → VALIDATING: payload schema → tool exists/AVAILABLE → adapter present
  → POLICY (§8.1, in order): identity → agent state → task link →
    capabilities (live P-04 grants) → scope (workspace/domain/host) →
    tool status → risk → approval → resources → restrictions
       risk 3            → REJECTED (no approval path)
       risk 2, no approval & no standing authorization
                         → AWAITING_APPROVAL + hash-bound P-01 approval
                           created (action "execution.execute", params
                           hash over tool/action/parameters/agent)
       approval expired/drifted → REJECTED (fail closed)
  → QUEUED → scheduler slot (ceilings; full → structured 429 result)
  → RUNNING: run row created; adapter executes; evidence collected
  → RESULT VALIDATION against expected_outcome spec (exists / hash /
    status / contains / json_fields / exit_code)
       verified   → COMPLETED (or COMPLETED_WITH_WARNINGS)
       unverified → FAILED with verification_status=failed
  → terminal states per §6.1; every transition audited + evented
```

Modes: `emergency` mode or the execution safe-mode flag rejects at policy
with a recorded reason; `simulation` mode executes only no-side-effect
actions (reads, dry-run validations) — writes/external calls return a
structured simulation refusal recorded on the request.

Retry: only for actions whose tool declares `retry_eligible` AND the
operation is idempotent; a retry creates a new run row under the same
request; non-idempotent actions are never auto-retried (§13.5/§30.13).

Cancellation: owner/manage principals may cancel a non-terminal request;
a cancelled workflow launches no further steps (security test 13).

## 3. Approvals and standing authorizations (§17)

- Risk-2 execution creates a P-01 `Approval` with
  `action="execution.execute"`, `resource=<request id>`,
  `parameters={agent_id, tool, action, parameters, scope}` and an expiry
  (default 30 min, from execution settings). The owner decides through the
  existing approvals API. On `execute`, the engine loads the approval,
  requires status `approved`, and calls `verify_binding` against the
  request's current parameters — any drift rejects. Expired approvals are
  flipped to `expired` by the P-01 service on read and can never authorize
  (security test 17).
- Standing authorizations are P-05 rows created/revoked by the owner only.
  Mandatory: tool+action, scope pattern, subject (one agent or one role),
  `max_uses`, `expires_at`. Matching is exact on action and prefix on
  scope; use-count increments atomically with the run. They never apply to
  Risk 3, never to `delete_permanent`, never to code runs whose pattern
  screen escalated them.

## 4. Identity rule (from audit §5)

The API has owner/service/system principals; agents hold no credentials.
A submission naming `agent_id` requires the caller to hold
`manage_agents` (the same gate P-04 uses for acting on agents) — except
the owner, who holds all permissions. The engine then verifies the agent
row exists, is in an assignable lifecycle state, and holds the live
capability grants. Client-supplied identity is never trusted beyond this
check (§21). Reads: any authenticated principal may read execution
records (they contain no secrets; parameters are stored redacted of
credential material — credential *references* only, enforced at schema
validation: parameter keys matching secret hints with non-reference values
are rejected).

## 5. Scheduler and ceilings (§§18/26)

Execution settings (system_config `execution.settings`, owner-only):
`max_concurrent_runs` (4), `max_concurrent_subprocesses` (2),
`max_browser_sessions` (2), `max_api_concurrency` (4),
`max_workflow_concurrency` (2), `default_timeout_seconds` (60),
`max_timeout_seconds` (600), `max_input_bytes` (5 MB),
`max_output_bytes` (1 MB), `approval_expiry_minutes` (30),
`emergency_stop` (false), `code_execution_enabled` (true — still gated by
capability + screen), `browser_allowlist` ([]), `api_allowlist` ([]).
Concurrency is enforced with in-process semaphores per resource class;
exhaustion returns `RESOURCE_LIMIT_EXCEEDED` (429) as a structured result
on the request (Scenario I), never an exception crash. Host pressure from
the P-01 monitor is reported in `/execution/resources`; blocking follows
the owner's existing threshold switch semantics.

## 6. Workflows (§§15–16)

Definition JSON: `{name, version, description, steps: [{id, tool, action,
parameters (may reference {{inputs.x}} / {{steps.<id>.output}}),
depends_on: [], required_capabilities: [], risk_level, compensation:
{tool, action, parameters} | null, idempotent: bool}]}`. Validation
rejects unknown tools/actions, capability mismatches, dependency cycles,
and any step classified Risk 3. Runs persist after every step
(checkpoint: completed step ids + outputs + evidence refs). On failure:
compensations for completed steps run in reverse where defined and are
labelled `compensation` (never "rollback" for external effects). Restart
recovery (startup scan + explicit endpoint): runs left RUNNING with a
non-idempotent in-flight step → `RECOVERY_REQUIRED` and the owning request
→ `REQUIRES_RECONCILIATION`; idempotent in-flight steps may be resumed
explicitly by the owner. A cancelled/failed workflow never restarts a
completed step (security tests 13/14; Scenario H).

## 7. Database changes

One additive migration (down_revision `a694abea811f`) creating the ten
tables listed in audit §7; `execution_approvals` and
`execution_audit_events` deliberately **not** created (audit §7 rationale:
P-01 `approvals` with hash binding + `audit_events` already carry both;
§19 permits referencing). Downgrade drops exactly the ten new tables.
SQLite upgrade/downgrade/re-upgrade verified in tests, following the
P-02–P-04 migration-test pattern.

## 8. API surface (§21 adapted to `/api/v1`)

`POST/GET /execution/requests`, `GET /execution/requests/{id}`,
`POST /execution/requests/{id}/cancel|retry|execute` (execute = run an
approved/queued request), `GET /execution/tools`,
`GET /execution/tools/{id}`, `POST /execution/tools/{id}/validate|disable`
(owner/manage), `POST /execution/files/{list,read,write,copy,move,delete}`
(thin wrappers that build a request for the caller's chosen agent),
`POST /execution/code/run`, `GET /execution/code/{run_id}`,
`POST /execution/browser/sessions`, `GET /execution/browser/sessions`,
`POST /execution/browser/{navigate,inspect,interact,screenshot}`,
`POST /execution/browser/sessions/{id}/close`,
`GET /execution/desktop/windows`, `POST /execution/desktop/{screenshot,
action,emergency-stop}` (all truthfully reporting the disabled adapter),
`POST /execution/api/request`,
`GET/POST /execution/workflows`, `POST /execution/workflows/{id}/validate`,
`POST /execution/workflows/{id}/run`, `GET /execution/workflows/runs/{run_id}`,
`POST /execution/workflows/runs/{run_id}/{pause,resume,cancel}`,
`GET /execution/status`, `GET /execution/resources`,
`GET /execution/health-report`, `GET /execution/runs/{run_id}/evidence`,
`GET /execution/audit`,
`GET/POST /execution/standing-authorizations`,
`POST /execution/standing-authorizations/{id}/revoke`,
`GET/PATCH /execution/settings`, `POST /execution/emergency-stop`,
`POST /execution/emergency-resume`.

## 9. Testing strategy

- `test_p05_unit.py` — request validation, risk classification matrix,
  policy check order, path validator (Windows + POSIX cases),
  idempotency, workflow definition validation, result verification specs,
  standing-authorization matching (incl. the impossibility of unlimited),
  scheduler ceiling logic, credential-broker redaction.
- `test_p05_integration.py` — migrations up/down/up; end-to-end requests
  per adapter (filesystem in tmp workspaces, code runs, API via
  MockTransport, browser sessions via fetch backend + mock transport,
  documents/CSV), approval flow (hold → owner approve → execute; drift →
  reject), workflow run with checkpoints + compensation, restart recovery
  scan, emergency stop, health report truthfulness, P-04 grant door
  (grant through factory flow → execution allowed; revoke → denied).
- `test_p05_security.py` — all 18 §25.3 tests, one named test each.
- `test_p05_resources.py` — ceiling exhaustion (Scenario I), timeouts,
  output caps, queue behaviour.
- Acceptance scenarios A–J mapped in `docs/testing/P05_TEST_REPORT.md`.
- Full suite must pass in ONE run together with the 230 pre-existing
  tests. One disclosed pre-existing change: P-04's
  `test_creation_decision_rejects_unsupported_capability` switches its
  example capability from `browser_interaction` (now genuinely backed) to
  `memory_write` (still P-09, still unsupported) — same assertion, same
  strictness.

## 10. Rollback strategy

The migration downgrade drops only P-05 tables; the capability-support
flip is data, reverted by the same seed function with the P-04 values;
no pre-existing table, column or behaviour is modified. Removing the
`execution` package + router registration returns the system to the exact
P-04 state (230 tests).

## 11. Stage mapping (§29)

1 Audit → this document + pre-implementation audit. 2 Core → constants,
schemas, policy, registry, service skeleton. 3 Filesystem → paths,
workspaces, filesystem adapter. 4 Code → code adapter + screen. 5 Browser
→ browser adapter (fetch backend; interactive unavailable). 6 Desktop →
disabled interface. 7 API/documents → api + documents adapters + broker.
8 Workflows → workflows module. 9 Integration → capability flip, approval
binding, application wiring. 10 Monitoring → status/resources/health
report/metrics endpoints. 11 Testing/audit → test files, smoke run,
reports, tracker, zip.
