# Agent Security Controls (P-04, §16)

Controls are enforced in backend policy code (`backend/app/agents/`,
P-01 permission/approval/audit substrate). Each control names its
evidence test in `backend/tests/test_p04_security.py` (12 tests) unless
noted.

## Controls

1. **No self-granted permissions.** Capability requests from an agent
   principal can only ask; Level-2 grants materialize solely through
   an owner-decided, hash-bound approval. An agent attempting to
   decide its own approval gets `PermissionDeniedError`.
   → `test_01_agent_cannot_grant_itself_permissions`
2. **Governance is owner-only (Article 0).** Factory settings and
   limits cannot be modified by agent or service principals, at the
   service layer or via HTTP. Attempts are refused and audited.
   → `test_02_*`, `test_02b_*`
3. **Cross-agent data isolation.** The §15 memory interface serves an
   agent only its *own* configuration history / task references; other
   agents' scopes raise `PermissionDeniedError`; P-09 scopes report
   unavailable rather than leaking. → `test_03_*`
4. **No raw secrets.** Level-3 `reveal_secrets` is prohibited —
   requesting or directly granting it raises
   `CapabilityProhibitedError` and writes a denied ledger row. No API
   payload contains credential material. → `test_04_*`, `test_04b_*`
5. **Prompt-injection resistance.** Instructions embedded in
   requirements, justifications or template system instructions cannot
   alter deterministic decisions: a Level-2 capability still forces
   owner approval, and a template smuggling `reveal_secrets` into its
   allowed set validates as `invalid` and can never publish.
   → `test_05_*`, `test_09_*`
6. **Append-only audit.** No DELETE surface exists for agents/events;
   `AuditRepository` exposes no delete/update. Denied attempts are
   themselves audited. → `test_06_*`
7. **Least-privilege administration.** The service principal (no
   `manage_agents`) receives 403 on template creation, factory
   creation, emergency stop and governed agent creation.
   → `test_07_*`
8. **Owner-only approvals.** Creation approvals refuse service
   principals (403), anonymous callers (401) and non-owner service
   calls; the owner's decision materializes the agent with the
   approved capabilities. → `test_08_*`
9. **External content cannot override policy.** Webpage-style override
   text in a requirement changes neither settings nor the decision
   path. → `test_09_*`
10. **Retirement is final for work.** Retired agents reject
    assignments and capability requests; history stays readable.
    → `test_10_*`
11. **Emergency stop is deterministic** (§16.5): owner-only backend
    logic — suspend, cancel eligible tasks, revoke grants, safe mode —
    with no LLM in the path. → integration
    `test_scenario_h_emergency_stop_via_api` + smoke Scenario H.
12. **Hash-bound approvals (drift-proof).** Creation and grant
    approvals bind SHA-256 over the exact action + parameters (P-01
    mechanism); any drift between request and decision fails closed.
13. **Prohibited set is structural.** Level-3 capabilities exist in
    the catalogue only as `enabled=False` records so attempts are
    visible and auditable; `CapabilityService.grant` refuses them as a
    backstop even if a caller bypasses the request flow.

## Residual risks (honest)

- Audit is append-only *by API and repository surface*, not
  cryptographically tamper-proof (carried from P-01).
- The permission-engine mirror is eventually consistent within a
  single request flow (grant → mirror is one service call chain; a
  crash between ledger write and mirror write would leave the ledger
  ahead — the ledger is the factory's source of truth and the mirror
  can be rebuilt from it; no repair tool exists yet).
- Cancellation of running tasks is cooperative (P-01 limitation);
  emergency stop cancels *eligible* (queued) tasks immediately and
  flags running ones.
