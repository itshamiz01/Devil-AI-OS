# P-08 — Survival and Scaling: Security (§28.18)

## Governance model

- **Autonomy levels are enforced in the service layer**, not the
  API layer alone: decision types carry fixed levels (§20.2);
  Level 3 execution requires status APPROVED via a hash-bound,
  binding-verified, owner-decided P-01 approval; Level 4 (CLOSE)
  cannot be originated by an agent at all and its execution
  additionally verifies the approval's approver is `owner:*`.
- **Settings are owner-governed** (`survival.settings` in
  `system_config`): weights, bands, criteria, caps and hardware
  limits. `update_settings` refuses non-owner principals at the
  service layer (Article 0) in addition to the API permission.
- **Protected reserves have no P-08 write path at all** — no
  survival service exposes a reserve mutation (structural test);
  reserve-sourced allocations are recorded BLOCKED.
- **Per-business isolation** mirrors P-07's
  `assert_business_access`: owner/system unrestricted; an agent
  reaches only the business its Agent row is registered to;
  everyone else is denied. The HTTP layer additionally requires
  the P-01 business permissions per route class.
- **Emergency pause** (§25.2): engaging a pause needs only modify
  permission (incident response must not wait), emits a critical
  owner-visible system event (`SurvivalBusinessPaused`, in the
  persisted critical set), blocks decision execution, experiment
  start and experiment spend for that business, preserves all
  records, and can be lifted only by the owner.
- **Prompt injection**: imported evidence/observation text is data.
  It is stored verbatim in evidence fields and never parsed for
  instructions; gates read only typed fields (reliability, metric
  values). A tentative compliance claim cannot trigger the
  compliance gate; an instruction to "approve everything" inside
  market data changes no gate and grants nothing (named test).
- **Idempotency**: decision execution keys are unique; repeat
  execution (any key) replays the first execution's outcome.
  Closure execution is idempotent per review. Experiment spend
  authorisation re-checks stop-loss and remaining budget on every
  call.
- **Audit**: every mutation writes to the P-01 audit trail with
  actor, action, decision (allow/deny) and reason; denials in the
  approval-verification, closure and pause paths are audited
  explicitly.

## §26.3 security test mapping (all real, named tests)

| §26.3 item | Test |
|---|---|
| Unauthorised closure | `test_unauthorised_closure_agent_denied`, `test_closure_with_forged_approval_denied` (+ S9 agent attempt) |
| Unauthorised scaling | `test_unauthorised_scaling_plan_approval_denied`, S5 agent plan-approval attempt |
| Budget bypass | `test_budget_bypass_beyond_remaining_denied`, `test_experiment_spend_before_start_denied` (+ S4) |
| Protected-reserve modification | `test_protected_reserve_has_no_p08_write_path` (+ S12 blocked allocation) |
| Agent self-approval | `test_agent_cannot_approve_own_decision` |
| Cross-business access | `test_cross_business_access_denied_for_unassigned` |
| Prompt injection via imported market data | `test_prompt_injection_in_market_data_changes_nothing` |
| Unauthorised lifecycle transitions | `test_unauthorised_lifecycle_transitions_denied` |
| Execution without approval | `test_level3_decision_execution_without_approval_denied` |
| Repeated decision execution | `test_repeated_execution_with_new_key_denied` (+ unit idempotency test) |
| Emergency pause behaviour | `test_pause_blocks_scaling_assessment_too` (+ S15) |

## Carried residual (from P-07, unchanged)

P-01's `ApprovalService.decide` has no role check at the service
level (gated at the API layer). P-08 therefore never trusts a
decided approval on its own: verification additionally requires
the approver to be the owner wherever the level demands it, which
is why the self-approval test passes at the P-08 layer even though
the agent could decide its own P-01 request. Full hardening of
`decide` remains a P-10 item.
