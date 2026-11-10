# Execution Policy Model (P-05, §§8/8.1/17)

The policy engine (`execution/policy.py`) is deterministic backend code.
An LLM never classifies its own action as authorized. Policy runs
**twice**: at submit, and again at execute (grants, mode, and the
emergency stop may have changed while a request waited).

## The ten checks (§8.1), in order

| # | Check | What it proves |
|---|---|---|
| 1 | policy_restrictions (global) | Emergency stop / emergency mode halts everything |
| 2 | agent_identity | The caller may act for this agent (owner, a `manage_agents` principal, or the agent itself); the agent is verified server-side from the registry |
| 3 | agent_status | Agent is in an assignable lifecycle state (P-04) |
| 4 | assigned_task | A linked task exists and is not another agent's |
| 5 | capabilities | Every required capability is a **live P-04 grant** (`CapabilityService.has_capability`: ledger grant AND permission-engine allow) — never role inference |
| 6 | requested_scope | Workspace authorization / API host allowlist / browser session domains |
| 7 | tool_status | Registry status is `available` or `degraded` (desktop fails here: `disabled`) |
| 8 | risk_category | Action risk 0–3 (§8) with §10.4 code-screen escalation; Risk 3 = prohibited, no approval path exists |
| 9 | approval_status | Risk ≥ 2 requires a verified hash-bound approval or a matching standing authorization |
| 10 | resource_limits + mode | Payload ceiling; simulation mode permits only true read actions |

Every check's outcome is recorded on the `PolicyDecision` and persisted
in the submit audit entry — any refusal is explainable after the fact.
**Priority never overrides risk** (§8): priority is not an input to any
check (tested at priority 10).

## Risk model (§8)

- **Risk 0** — read-only, internal (file reads, hash, list, CSV summary).
- **Risk 1** — reversible workspace writes, code runs passing the screen,
  allowlisted GET, browser read navigation.
- **Risk 2** — mutating HTTP, browser interaction, permanent deletion,
  code escalated by the screen. Requires a hash-bound owner approval
  (P-01 `ApprovalService`, action `execution.execute`, parameters =
  agent+tool+action+exact parameters) or a narrow standing authorization.
- **Risk 3** — prohibited constructs (credential access, subprocess,
  dynamic code execution, network from code, native bridges, destructive
  filesystem calls in code). **Rejected outright; no approval path
  exists in the code.**

## Approval binding & drift

Approvals bind SHA-256 over `action + resource + parameters`, where the
resource is `execution:<agent>:<tool>:<action>` and parameters are the
exact request payload. If stored parameters are tampered with after
approval, `verify_binding` fails and execution stays blocked
(§25.3 #12b, tested). Expired approvals are expired on read by the P-01
service and cannot authorize (tested). Denied approvals finalize the
request as REJECTED/`APPROVAL_DENIED`.

## Standing authorizations (§17)

Owner-configured only. A row names tool + action + scope pattern +
(optional) agent or role + limits, and — by schema construction —
**must** have `max_uses` and `expires_at` (both NOT NULL): an unlimited
standing authorization cannot be expressed. Matching is exact on
tool+action, prefix on scope, and never applies to `delete_permanent`.
Uses are consumed only when a run actually executes; exhaustion flips
the row to `exhausted`. Revocation is owner-only and immediate.

## Scope rules

- **Workspaces:** an agent's own workspace (full), `shared` (full),
  `projects`/`businesses` (write requires the request's `business_ref`),
  `quarantine` (read/list; write only as the destination of a governed
  `delete`, plus the single `delete_permanent` exception whose control
  is the Risk-2 approval), `temporary` (internal only, never
  agent-addressable).
- **API:** host must match the owner-governed `api_allowlist` (exact or
  `*.domain`); the transport re-checks every redirect hop.
- **Browser:** navigation host must be inside the session's domain
  allowlist, and inside the owner-governed global `browser_allowlist`
  when one is configured; session creation validates requested domains
  against the global list.

## Capability support map (audit §6)

P-05 flips six P-04 catalogue capabilities to `supported` — grants still
flow **only** through the P-04 factory flow (owner approval for Level 2):
`file_read`, `file_write`, `api_read`, `api_write`,
`sandboxed_code_execution`, `browser_interaction`. Still unsupported:
`code_generation` (P-06), `memory_write` (P-09),
`external_communication` (no adapter exists), financial execution (P-07;
`financial_transaction_request` remains request-only).
