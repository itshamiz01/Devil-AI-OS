# P-05 Implementation Report — Universal Digital Execution Engine

Generated per §32 of the P-05 prompt. Every claim below is backed by the
test run, the smoke transcript, or the code itself. **Read the
limitations (§12, §23–§26 of this report) before the successes: two of
six adapters are not fully operational in this environment, by design
and by evidence.**

## 1. Executive summary

P-05 is built and verified in staging on top of the accepted P-01–P-04
substrate. Agents now perform governed real work — workspace files,
documents/data, controlled Python, allowlisted HTTP, and read-only
browser sessions — through one policy doorway with hash-bound approvals,
independent outcome verification, evidence, and audit. **300/300 tests
pass in a single run** (230 regression + 70 new). The Windows desktop
adapter is interface-only and DISABLED here; browser interaction has no
live engine here; code isolation is process controls only. Gate
recommendation: **accept in staging on the same terms as P-01–P-04**,
with Windows verification carried.

## 2. Initial repository condition

Baseline re-run before any P-05 code: **230/230 passed** (62.32 s),
migration head `a694abea811f`, 35 tables. Stage-1 audit:
`docs/audits/P05_PRE_IMPLEMENTATION_AUDIT.md`; plan:
`docs/audits/P05_IMPLEMENTATION_PLAN.md`.

## 3. Architecture audit findings

- P-01 approvals/audit/permissions carry every P-05 need §19 lists —
  `execution_approvals` and `execution_audit_events` tables were **not**
  built (the prompt permits them only on proof of need; none existed).
- P-04's capability catalogue already named the six P-05 capabilities as
  unsupported; the correct move was flipping `supported` through the
  catalogue (source + seeded rows) with grants unchanged.
- Playwright's Python package installs in this sandbox but its Chromium
  binary **cannot be downloaded** (cdn.playwright.dev delivers 0 bytes;
  280 s attempt, cache stayed 4 KB) → no live browser engine can run
  here; the package was uninstalled again to match `requirements.txt`.
- The pre-existing P-05 preparation pack's handler-centric design was
  superseded by the owner's issued prompt architecture; its governance
  principles (capability-only door, allowlists, evidence, verification)
  were adopted.

## 4. Existing functionality reused

P-01: ApprovalService (hash-bound), PermissionEngine, audit_events,
system_config, event bus + persisted-critical set, task engine (link
checks), mode system. P-02: none needed at runtime (workflows follow its
plans-as-data pattern). P-03: `assert_url_allowed` SSRF guard,
`html_to_text`, transport discipline, `research_proxy_url` setting.
P-04: CapabilityService (the capability oracle), factory settings
pattern, lifecycle states, emergency-stop pattern. Zero duplicated
subsystems.

## 5. New modules created

`app/execution/` — `constants.py`, `errors.py`, `schemas.py`, `paths.py`,
`credentials.py`, `registry.py`, `workspaces.py`, `policy.py`,
`service.py`, `workflows.py`, `adapters/{base,filesystem,documents,code,
api,browser,desktop}.py`. Plus `app/database/models/execution.py`,
`app/database/repositories/execution.py`,
`app/api/routes/execution.py`, `app/api/schemas/execution.py`,
`backend/scripts/p05_smoke.py`, 4 test files + `tests/p05_support.py`,
and this phase's docs.

## 6. Existing modules modified

`app/main.py` (router), `app/core/application.py` (service assembly +
recovery scan), `app/events/events.py` (15 P-05 event types; 7 added to
the persisted-critical set), `app/agents/constants.py` (six capability
entries flipped to supported with P-05 descriptions),
`app/database/models/__init__.py` (model registration). Disclosed test
edits: see §20.

## 7. Database changes

One additive migration `6ffcc7e899fa` (revises `a694abea811f`): 10 new
tables — `execution_tools`, `execution_workspaces`,
`execution_requests`, `execution_runs`, `execution_evidence`,
`execution_browser_sessions`, `execution_workflow_definitions`,
`execution_workflow_runs`, `execution_workflow_steps` (as
`execution_workflow_step_runs`), `execution_standing_authorizations`
(45 tables total). Verified cycle on scratch SQLite: upgrade 35→45,
downgrade removes exactly the 10 (35 remain), re-upgrade → 45. No table
stores secrets: parameters are reference-only by submission validation;
`StandingAuthorization.max_uses`/`expires_at` are NOT NULL by design.

## 8. New API endpoints

Under `/api/v1/execution`: tools (list/validate/disable), workspaces
(list/ensure-agent), requests (submit/list/get/execute/cancel/
request-approval/evidence/audit), convenience wrappers
(`/files/{action}`, `/documents/{action}`, `/code/run`, `/api/{method}`,
`/browser/{action}`, `/desktop/{action}`, `/browser/sessions`),
workflows (create/list/start runs; runs list/get/pause/resume/cancel),
standing-authorizations (create/list/revoke), settings (get/patch),
status, health-report, emergency-stop, emergency-resume. 30 routes.

## 9. Tool registry implementation

DB-backed, seeded from `constants.TOOL_SEEDS` (6 tools, 31 actions with
per-action risk/capabilities/idempotency). Startup applies each
adapter's real health; health can never resurrect an owner-disabled
tool. Discovery view (agents) hides configuration references; admin view
(owner) includes health details. Desktop is seeded `disabled`.

## 10. Execution policy architecture

Deterministic, runs at submit AND execute; ten §8.1 checks in order, all
recorded into the audit entry. Risk 0–3 exactly per §8 with the §10.4
code screen as the escalation input; Risk 3 has no approval path in
code. Approvals are P-01 hash-bound with drift detection; standing
authorizations are owner-only, scope/agent/role-narrow, use-bounded,
expiry-mandatory, and never cover `delete_permanent`. Priority is never
an input. See `docs/architecture/EXECUTION_POLICY_MODEL.md`.

## 11. Filesystem adapter results

**Operational.** All 13 actions implemented and tested end-to-end:
atomic writes with before/after SHA-256 and overwrite snapshots,
quarantine-based reversible deletion, governed permanent deletion
(Risk 2). Platform-first path validation (Windows lexical rules +
resolved containment incl. symlink/junction escape) — 14 parametrized
validator cases + adapter-level traversal/symlink tests pass; smoke §F
demonstrates rejection with audit entries over real HTTP.

## 12. Code sandbox implementation and isolation limitations

**Operational as a controlled subprocess adapter; isolation =
`process_controls_only`, NOT a strong sandbox (§10.2).** Controls:
per-run temp workspace (deleted after the run — smoke verified 0
leftovers on disk), argv-only exec of the app interpreter in isolated
mode, allowlist-scrubbed environment (test proves a planted server
secret never reaches the child), timeout with process-tree termination
(tested: 60 s sleep killed at 2 s), stdout/stderr file capture under
caps, POSIX RLIMIT_CPU/RLIMIT_FSIZE via pre-exec bootstrap where
supported. The §10.4 screen rejects credential/subprocess/network/
dynamic-exec constructs as Risk 3 and escalates filesystem use to
Risk 2. Python only; Node/PowerShell deferred. Full statement:
`docs/security/CODE_SANDBOX_SECURITY.md`.

## 13. Browser adapter results

**Partial.** Session/policy layer fully implemented and tested:
per-session domain allowlists enforced at policy AND transport
(redirect hops re-validated), read-only navigate/inspect/extract over
the SSRF-guarded fetch backend with evidence, HTML snapshot capture
(honestly labelled, not a rendered screenshot), auth/CAPTCHA/MFA
detection → REQUIRES_HUMAN_ACTION (never bypassed), prompt-injection
flagging. **Interactive actions are unavailable in this environment**
(no downloadable browser engine — §3) and return ADAPTER_UNAVAILABLE;
Scenario D's post-approval outcome in tests is exactly that truthful
failure.

## 14. Windows desktop adapter results

**Disabled.** Interface + registry presence only; every action refused;
health reports the reason. The module contains no elevation, credential
capture, or automation machinery at all (structurally asserted by
§25.3 test 18). Enablement plan for the owner's machine is in
`docs/operations/WINDOWS_SETUP.md`; nothing about desktop automation is
claimed to work anywhere yet.

## 15. API adapter results

**Operational.** Generic HTTP over the redirect-re-validating,
SSRF-guarded transport; owner host allowlist (default empty); retries
only for idempotent methods; credential references resolved by the
broker at execution time (test proves the value appears only in the
outbound header — never in parameters, results, runs, or logs). One
real-network attempt appears in the smoke (post-approval POST): the
gate opened and the sandbox's TLS interception failed the fetch —
recorded as-is.

## 16. Workflow engine implementation

Definitions are validated data (≤50 steps, unique ids, failure
strategies, compensation shapes), versioned, and executed step-by-step
through the same request pipeline — same policy, approvals, audit.
Per-step checkpoints, idempotency keys, approval/human blocking with
resume, compensation in reverse order (labelled compensation, never
"rollback"), and restart recovery that requeues only idempotent
interruptions and sends the rest to RECOVERY_REQUIRED. Tested: happy
path, compensation, approval-block/resume, cancellation (§25.3 #13),
interruption rules (#14).

## 17. Approval integration

P-01 ApprovalService only. Engine-created approvals bind
`execution.execute` + `execution:<agent>:<tool>:<action>` + the exact
parameters hash, expiring per `approval_expiry_minutes` (30). Execute
re-verifies status + binding + expiry; tampered parameters void the
approval (tested); denied approvals finalize REJECTED; expired
approvals cannot authorize and can be replaced via
`POST /execution/requests/{id}/request-approval`.

## 18. Evidence and verification architecture

Adapters emit typed evidence (`file`, `code_execution`, `api_response`,
`browser_page`, `browser_snapshot`) with content hashes, stored per run
in `execution_evidence`. Verification compares results against the
request's `expected_outcome` (`exit_code`, `output_contains`, `status`,
`file` incl. SHA-256/content) — COMPLETED requires it; explicit-check
failure is FAILED/`VERIFICATION_FAILED`; no evidence and no output is
COMPLETED_WITH_WARNINGS/`unverified`, never a silent COMPLETED.

## 19. Recovery and idempotency behavior

Startup scan marks RUNNING runs/requests INTERRUPTED (outcome never
assumed), requeues workflow runs whose interrupted step is idempotent
or already terminal, and sends non-idempotent interruptions to
RECOVERY_REQUIRED with a checkpoint record. Idempotency keys dedupe
submissions at request and workflow-step level. Retries exist only for
registry-idempotent actions with bounded attempts.

## 20. Security test results

§25.3 items 1–18 are named tests in `tests/test_p05_security.py`, plus
#12b (approval drift): **19/19 passed**. Disclosed pre-existing test
changes (strictness preserved, P-03/P-04 precedent): (1)
`test_p04_unit.py` unsupported-capability example switched
`browser_interaction` → `memory_write`; (2) migration-head pins in the
P-02/P-03/P-04 integration suites updated to `6ffcc7e899fa` with
in-code disclosure comments. Six defects were found by the new suites
and fixed during the build (listed in the test report), including a
fail-closed allowlist bug in both HTTP transports and a workflow
resume path that skipped the approval gate.

## 21. Performance and resource measurements

Full suite: 300 tests in 102.84 s on this shared VM (1.5 CPU / 6 GB).
Smoke metrics after 8 requests: 5 runs, average duration 28.87 ms
(local adapters; network excluded). Scheduler ceilings are
semaphore-enforced per resource class (Scenario I test: with
`max_concurrent_subprocesses = 1`, a second code run stays QUEUED with
a recorded reason and completes after the first). No unbounded queues:
submission is synchronous, concurrency is capped, payload/output sizes
are capped in settings.

## 22. Windows installation instructions

`docs/operations/WINDOWS_SETUP.md` — prerequisites, the §27 health
report checks, the [verify on Windows] code-run termination check, the
Playwright backend enablement path, the §12 desktop evaluation plan,
and the owner configuration checklist. Nothing in it is claimed to have
been executed on Windows.

## 23. Known limitations

1. Code isolation is process controls only (see §12).
2. Desktop adapter disabled everywhere until built/tested on Windows.
3. Browser interaction unavailable in staging (no engine); fetch-backed
   reads only.
4. SSRF guard does not resolve DNS (inherited P-03 discipline); public
   hostnames are constrained by the owner allowlist instead.
5. No real LLM exercised (unchanged from P-02–P-04); the engine itself
   is deterministic and needs none.
6. Windows behaviour of every adapter is unverified (carried from
   P-00); POSIX rlimits and process-group kill are Linux-verified only,
   with the Windows code paths present but untested.
7. Audit is append-only by interface, not cryptographically
   tamper-proof (carried from P-01).

## 24. Disabled capabilities

Desktop tool (all actions). Browser `interact`. Capabilities still
unsupported in the catalogue: `code_generation` (P-06), `memory_write`
(P-09), `external_communication` (no adapter), all Level-3 capabilities
(permanently prohibited).

## 25. Deferred work

PDF/presentation document support (no existing dependency); Node and
PowerShell code runtimes; Playwright interactive backend (owner's
machine); desktop adapter implementation (§12 evaluation first);
DNS-resolution SSRF hardening; cryptographic audit chaining (P-10
territory).

## 26. Outstanding risks

- The owner's Windows machine remains unverified for ALL phases
  (P-00 environment evidence still outstanding) — the single largest
  carried risk in the programme.
- Granting `sandboxed_code_execution` on a real machine deserves the
  owner's explicit attention: process controls deter accidents and
  honest agents, not a determined malicious process; the capability
  should stay narrowly granted.
- Live external fetching from staging is network-limited (TLS
  interception, blocked CDNs); adapter behaviour against real APIs is
  proven by transport-level tests + P-03's live-fetch heritage, not by
  broad live use.

## 27. Files changed

New: `backend/app/execution/**` (17 files), `backend/app/database/
models/execution.py`, `backend/app/database/repositories/execution.py`,
migration `6ffcc7e899fa`, `backend/app/api/routes/execution.py`,
`backend/app/api/schemas/execution.py`, `backend/scripts/p05_smoke.py`,
`backend/tests/{p05_support,test_p05_unit,test_p05_integration,
test_p05_security,test_p05_resources}.py`, 12 P-05 docs, smoke
transcript. Modified: `app/main.py`, `app/core/application.py`,
`app/events/events.py`, `app/agents/constants.py`,
`app/database/models/__init__.py`, three migration-head test pins, one
P-04 unit-test example. No dependencies added (Playwright was tried and
removed again — `requirements.txt` untouched).

## 28. Acceptance criteria evidence (§31)

**Core engine** — ✅ all ten: request manager, registry, adapters, state
management, policy, capabilities, approvals, evidence, verification,
audit (unit/integration suites + smoke).
**Filesystem** — ✅ all six (validator tests, isolation tests, integrity
hashes in Scenario A evidence, Risk-2 permanent deletion flow tested).
**Code execution** — ✅ all seven, with isolation honestly documented
(process controls only).
**Browser** — ✅ sessions, domain restrictions, navigation/inspection,
authentication handoff, injection containment, independent verification.
❌ *"Approved interaction works"* — **not claimed**: no live engine
exists in this environment; interaction returns ADAPTER_UNAVAILABLE
(§30/§32 honesty rule). Becomes claimable only after the Windows
enablement in WINDOWS_SETUP.md.
**Desktop** — ❌ all six items **not claimed** in this environment
(adapter disabled by design; "no privilege escalation" holds trivially
and structurally — there is no elevation code path). Evidence is the
disabled state + §25.3 test 18.
**API and workflows** — ✅ all eight.
**Integration and reliability** — ✅ P-01/P-02/P-04 integration verified
(shared substrate, full regression green), existing tests pass (230),
new security tests pass (19), Windows setup documented, emergency stop
works (Scenario J + smoke), no critical unresolved regressions.

## 29. Recommended next phase

**P-06 Business Creation Engine** — only after the owner accepts this
gate. Recommended owner-side actions in the meantime (unchanged,
carried): provide the P-00 Windows evidence, decide the GitHub repo
creation/visibility, and — when ready — run the Windows health-report
checks in WINDOWS_SETUP.md.

## Exact test statistics (§32)

- Tests executed: **300** — Tests passed: **300** — Failed: **0** —
  Skipped: **0**
- Security tests passed: **19/19** (§25.3 ×18 + approval drift)
- Integration tests passed: **17/17** (P-05 file; broader integration
  evidence includes the 230-test regression across P-01–P-04 suites)
- New P-05 tests: **70** (29 unit, 17 integration, 19 security, 5 resource)
- Known warnings: 1 pre-existing Starlette TestClient deprecation notice
- Outstanding blockers: none for the staging gate; Windows verification
  remains carried (all phases)
