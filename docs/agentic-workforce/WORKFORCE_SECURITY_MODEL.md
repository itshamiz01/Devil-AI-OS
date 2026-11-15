# Workforce Security Model — Devil AI OS (§21/§22/§29)

**Hierarchy is not authority.** The CEO and managers sit BELOW the
P-10 security system and beside P-07 financial authority, never above
either. Every safeguard below is enforced in services/engines, not in
prompts, and each is covered by a test in
`backend/tests/test_workforce_security.py` (plus the P-04/P-10 suites).

| Rule | Enforcement |
|---|---|
| No self-permission changes | Lifecycle control (pause/resume/disable) and seeding are owner-only in `WorkforceService`; factory config updates require `manage_agents`, which agent principals do not hold (tested). |
| Tool access is least-privilege | A profile's `tool_access` is a DECLARATION from the P-04 catalogue (supported entries only). It grants nothing: a seeded employee holds ZERO capability grants until the governed factory grant path runs (tested). |
| Prohibited capabilities | Catalogue level-3 (`reveal_secrets`, `disable_security_controls`, `bypass_approvals`, `modify_audit_records`, `unrestricted_financial_authority`) can never be granted — even by the owner (tested, P-04 suite). |
| CEO cannot bypass owner approval | Restricted work orders create a P-01 Approval and are never dispatched. `ApprovalService.decide` requires `approve_actions`; CEO and manager principals are refused (tested). |
| Managers cannot override P-10 | Managers hold no approval authority and no policy-write path; security settings/modes are owner-governed via P-10's versioned policy path. |
| Financial authority | Finance-department employees can read/analyze P-07 records (`financial_data_read`) and REQUEST operations (`financial_transaction_request` = a request through the approval framework). No employee can transfer funds; P-07 remains the sole execution authority. |
| Action pipeline (§21) | Work order → service validation (hierarchy, status, plan membership) → manager review of the deliverable → (restricted: owner approval BEFORE dispatch) → task release → task-engine execution record → audit row at every step. |
| Emergency control | P-12 `emergency_stop(scope="global")` sets the P-10 emergency mode; workforce dispatch reads the live mode and refuses new work orders until the owner resumes (tested). Owner can also pause/disable any single employee immediately. |
| Memory isolation | Per-profile `memory_scope`: identity + role + own department; business context assigned-only; sharing only via approved handoffs; credentials NEVER in agent memory (`memory_scope.credentials = "never"`, asserted in tests). |
| Audit | Seed, status changes, objective intake, dispatch, escalation, review and handoffs all write append-only `audit_events`. |
| Business isolation | Work orders carry no cross-business data access; an employee's data scope is its assignment (P-13 isolation rules unchanged). |
