# Execution Security Model (P-05)

## Trust boundaries

1. **Agents are untrusted callers.** Naming an `agent_id` confers no
   authority; identity is verified server-side against the P-04 registry
   and the caller's principal on every submit and every execute.
2. **Capabilities are live grants, never roles.** The only capability
   oracle is P-04's `CapabilityService.has_capability` (ledger + engine
   mirror, deny wins). Grants flow only through the factory's governed
   flow.
3. **Page/API content is untrusted data.** Browser extraction returns
   text/links; instruction-like content is flagged
   (`injection_markers`) for the audit trail and never acted on (§11.8).
4. **Parameters are hostile input.** Secret-looking keys carrying raw
   values are rejected before policy (§19); paths pass a Windows-first
   lexical validator plus resolved containment — in the policy layer
   AND again inside the adapters.

## Controls by layer

| Layer | Controls |
|---|---|
| Submission | secret hygiene, idempotency keys, agent existence, timeout clamping |
| Policy | 10 deterministic checks, recorded; Risk 3 has no approval path; priority never affects risk |
| Approvals | P-01 hash-bound (action+resource+exact parameters), expiry enforced on read, drift detected at execution |
| Standing auth | owner-only, scoped, use-bounded, expiry mandatory by schema, never for `delete_permanent` |
| Adapters | path re-validation, SSRF guard + per-hop redirect re-validation, credential broker (values never logged/stored/returned), process-tree timeouts, output/input caps |
| Scheduler | per-resource-class semaphores; exhaustion is a structured QUEUED result, never a crash |
| Emergency | owner-only stop: settings flag + subprocess termination + browser-session pause + audit; resume owner-only |
| Audit | P-01 `audit_events` for every submit/execute/cancel/settings/stop decision; security categories (PATH_TRAVERSAL, SECRET_VALUE_REJECTED, code-screen hits) also publish persisted-critical `SandboxViolation` events |

## Known limitations (stated, not hidden)

- **SSRF guard depth:** the inherited P-03 `assert_url_allowed` checks
  scheme, blocked hostnames, and IP-literal targets. It does not resolve
  DNS names, so a *public hostname that resolves to a private address*
  is constrained by the owner allowlist layer (default: empty — nothing
  external is reachable until the owner allowlists hosts) rather than by
  resolution checks. DNS-resolution enforcement is a documented
  hardening candidate for a later phase.
- **Code isolation** is process controls only — see
  CODE_SANDBOX_SECURITY.md.
- **Audit** is append-only through the application interfaces, not
  cryptographically tamper-proof (carried from P-01).
- **Browser** interactive automation is unavailable in this environment
  (see BROWSER_AUTOMATION_SECURITY.md).

## Security test evidence

All eighteen §25.3 verifications are named tests in
`backend/tests/test_p05_security.py` (plus approval-drift), mapped in
`docs/testing/P05_TEST_REPORT.md`. Result at the P-05 gate: **19/19
passed** as part of the 300/300 full-suite run.
