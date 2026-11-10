# P-05 Test Report

**Final full-suite run (one run, the phase acceptance criterion):**
`300 passed, 0 failed, 0 skipped` in 102.84 s —
230 pre-existing (P-01–P-04) + **70 new P-05 tests**:

| Suite | File | Tests | Covers |
|---|---|---|---|
| Unit | `tests/test_p05_unit.py` | 29 | Path validator (14 parametrized cases incl. symlink escape), code screen, standing-authorization matching, workflow definition validation, secret hygiene, settings governance, registry views, health-report truthfulness, capability flip, policy check recording, timeout clamping, idempotent submit, priority-vs-risk |
| Integration | `tests/test_p05_integration.py` | 17 | Migration cycle, Scenarios A (×2: service + full HTTP), B, C, D, E, J, standing-authorization lifecycle, credential broker, workflows (happy path, compensation, approval-block/resume), simulation mode gate, CSV pipeline, filesystem lifecycle |
| Security | `tests/test_p05_security.py` | 19 | §25.3 items 1–18 as named tests + #12b approval drift |
| Resource | `tests/test_p05_resources.py` | 5 | Scenario I concurrency ceiling, browser session ceiling, payload ceiling, idempotent-only retry, measured metrics |

Suites run with `TMPDIR=/tmp` (the VM's known tmpfs speed note). One
warning: Starlette's TestClient deprecation notice (pre-existing).

## §25.3 security mapping (all real tests)

| # | Verification | Test |
|---|---|---|
| 1 | Unauthorized agent cannot execute | `test_01_unauthorized_agent_cannot_execute` |
| 2 | Permission check cannot be bypassed | `test_02_agent_cannot_bypass_permission_checks` |
| 3 | Path traversal rejected | `test_03_path_traversal_rejected` |
| 4 | Symlink cannot escape workspace | `test_04_symlink_escape_rejected` |
| 5 | Code timeout terminates the process | `test_05_code_timeout_terminates_process` |
| 6 | Untrusted code cannot reach credentials | `test_06_untrusted_code_cannot_reach_credentials` (+ adapter-level env-scrub proof in integration) |
| 7 | Browser domain scope | `test_07_browser_domain_scope_enforced` |
| 8 | Redirect cannot bypass domains | `test_08_redirect_cannot_bypass_domain_restriction` |
| 9 | Webpage cannot instruct the agent | `test_09_webpage_injection_is_contained` |
| 10 | API SSRF to internal targets | `test_10_api_ssrf_to_internal_targets_blocked` |
| 11 | Cross-workspace access | `test_11_cross_workspace_access_rejected` |
| 12 | Sensitive action needs valid approval | `test_12_sensitive_action_requires_approval`, `test_12b_approval_drift_is_detected` |
| 13 | Cancelled work launches no new steps | `test_13_cancelled_work_cannot_launch_new_steps` |
| 14 | Interrupted workflow: no blind repeat | `test_14_interrupted_workflow_recovery_rules` |
| 15 | Agent cannot invoke emergency controls | `test_15_agent_cannot_invoke_emergency_controls` |
| 16 | Audit immutable via execution interface | `test_16_audit_immutable_through_execution_interface` |
| 17 | Expired approval cannot authorize | `test_17_expired_approval_cannot_authorize` |
| 18 | Desktop cannot bypass UAC/MFA | `test_18_desktop_adapter_cannot_bypass_uac_or_mfa` (disabled state + no elevation path in code, proven structurally) |

## §25.4 acceptance-scenario mapping

| Scenario | Evidence |
|---|---|
| A — project report | `test_scenario_a_research_agent_report_verified`, `test_scenario_a_over_http`; smoke §A |
| B — approved Python | `test_scenario_b_approved_python_execution`; smoke §B (stdout captured, cleanup verified on disk) |
| C — browse approved site | `test_scenario_c_browser_readonly_research` (fetch backend, mock transport) |
| D — sensitive form | `test_scenario_d_sensitive_action_held_until_approval`; smoke §D (held → 409 → 0 runs → owner inspects → post-approval gate opens; interact then fails truthfully as ADAPTER_UNAVAILABLE in tests) |
| E — OTP/MFA challenge | `test_scenario_e_auth_challenge_requires_human` (REQUIRES_HUMAN_ACTION + session `requires_human`) |
| F — filesystem attack | security #3/#4; smoke §F |
| G — prompt injection | security #9 |
| H — workflow interruption | security #14 |
| I — resource exhaustion | `test_scenario_i_subprocess_ceiling_queues_work` |
| J — emergency shutdown | `test_scenario_j_emergency_stop_and_resume`; smoke §J |

## Smoke (real uvicorn)

`backend/scripts/p05_smoke.py` boots the application under real uvicorn
(controlled mode, migrated DB) and drives Scenarios A, B, D, F, J over
HTTP. Transcript: `docs/reports/P05_SMOKE_EVIDENCE.txt`. Headlines:
A COMPLETED/verified with evidence hash; B COMPLETED with stdout
`smoke total 45`, isolation labelled, **0 leftover run dirs on disk**;
F FAILED/`PATH_TRAVERSAL` with audit entries; D held at
AWAITING_APPROVAL, execute → HTTP 409 with **0 runs**, owner inspects
the hash-bound approval, post-approval the gate opens (the sandbox's
live fetch then fails on TLS interception — recorded as-is); J stop →
submissions REJECTED, resume → submissions COMPLETED.

## Disclosed pre-existing test changes (strictness preserved)

1. `tests/test_p04_unit.py::test_creation_decision_rejects_unsupported_capability`
   — example capability changed `browser_interaction` → `memory_write`
   (P-05 genuinely backs browser_interaction; memory_write remains
   unsupported until P-09). Same assertion.
2. Migration-head pins in `test_p02_integration.py`,
   `test_p03_integration.py`, `test_p04_integration.py` — updated from
   `a694abea811f` to the new head `6ffcc7e899fa` (the P-04 migration
   cycle test keeps its intermediate pin; only its two "head" landings
   moved), each with an in-code disclosure comment. Same exact-head
   strictness, following the P-03/P-04 precedent.

## Defects found by the P-05 suites and fixed during the build

1. `host_matches` called per-pattern (string iterated as characters) in
   both HTTP transports — every allowlist check failed closed; fixed to
   pass the whole allowlist.
2. Workflow engine never routed AWAITING_APPROVAL step requests through
   the execution approval gate on resume; fixed.
3. Path validator stripped surrounding whitespace before segment checks,
   defeating the trailing-space rule; fixed (explicit rejection).
4. `..` segments were reported as "ends with a dot or space" (check
   ordering); fixed — traversal now reports as traversal.
5. P-03's `html_to_text` returns `(title, text)`; the browser adapter
   initially treated it as a string; fixed.
6. httpx clients trusted ambient proxy env (which crashes client
   construction on this sandbox's `no_proxy` value and would silently
   reroute governed traffic); the engine transport is now
   `trust_env=False` with an explicit proxy setting.
