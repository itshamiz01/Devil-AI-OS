# P-05 — Universal Digital Execution Engine

**Status:** Built and verified in staging (Linux sandbox), awaiting owner gate.
**Module:** `backend/app/execution/` · **API:** `backend/app/api/routes/execution.py` · **Migration:** `6ffcc7e899fa` (additive, revises P-04 head `a694abea811f`)

## Purpose

P-01–P-04 gave AUTONOMUS a core OS, a deterministic intelligence layer,
opportunity discovery, and a governed agent factory — but no hands. P-05
is the hands: a single governed doorway through which agents perform
real digital work (files, documents, code, HTTP, browser sessions), with
the separation the phase directive demands:

- **Agents decide** what they want to accomplish (P-02/P-04).
- **The execution engine decides** what they are allowed to do
  (deterministic policy, §§8/8.1 — an LLM never classifies its own
  action as authorized).
- **Adapters perform** one validated action each.
- **Independent verification decides** whether the requested outcome
  actually occurred (§6.1: a tool returning without error is *not*
  completion).

## The request lifecycle

```
submit ──► secret hygiene (§19) ──► workspace provisioning
       ──► PolicyContext ──► ExecutionPolicy.evaluate (10 checks, §8.1)
             ├─ prohibited / failed check ─► REJECTED (checks recorded)
             ├─ Risk ≥ 2, no approval ─────► AWAITING_APPROVAL
             │     (P-01 hash-bound approval created; nothing executes)
             └─ allowed ───────────────────► QUEUED
execute ─► approval gate (status + verify_binding + expiry, P-01)
        ─► policy RE-RUN (grants/mode/emergency may have changed)
        ─► scheduler semaphore (per resource class; exhaustion = the
           request stays QUEUED with a recorded reason, never a crash)
        ─► adapter.execute (one action)
        ─► verification against expected_outcome
        ─► terminal outcome + evidence + audit + events
```

### Four separate facts (§6)

Every request row carries `requested_action`, `approved_action`,
`executed_action`, and `verified_outcome` as distinct JSON facts.
Outcomes are exactly §6.1's fourteen: ACCEPTED, VALIDATING,
AWAITING_APPROVAL, QUEUED, RUNNING, COMPLETED, COMPLETED_WITH_WARNINGS,
FAILED, REJECTED, CANCELLED, TIMED_OUT, INTERRUPTED,
REQUIRES_HUMAN_ACTION, REQUIRES_RECONCILIATION.

### Verification (§6.1)

`ExecutionService._verify` checks the adapter result against the
request's `expected_outcome`: `exit_code`, `output_contains`, `status`,
and `file` (`{workspace, path, sha256?, content_contains?}`). Explicit
checks that fail produce FAILED/`VERIFICATION_FAILED`. With no explicit
expectations, recorded evidence (or structured output) verifies the run;
a successful call with neither completes as COMPLETED_WITH_WARNINGS
with `verification_status = unverified`.

## Components

| Component | File | Responsibility |
|---|---|---|
| ExecutionService | `execution/service.py` | Lifecycle, approvals, scheduler, emergency stop, recovery, metrics, health report |
| ExecutionPolicy | `execution/policy.py` | The ten §8.1 checks, in order, all recorded |
| ToolRegistry | `execution/registry.py` | DB-backed tool catalogue; discovery vs admin views |
| WorkspaceManager | `execution/workspaces.py` | Managed workspace layout + authorization rules |
| Path validator | `execution/paths.py` | Windows-lexical rules first, then resolved containment |
| CredentialBroker | `execution/credentials.py` | `env:NAME` references resolved at execution time only |
| WorkflowEngine | `execution/workflows.py` | Data-defined workflows, checkpoints, compensation, recovery |
| Adapters | `execution/adapters/*.py` | filesystem, documents, code, api, browser, desktop |

## Reuse, not duplication (audit-verified)

- **Approvals:** P-01 `ApprovalService` (hash-bound `execution.execute`
  approvals). No `execution_approvals` table — §19's permission was not
  needed; the audit found the existing service carries the relationship.
- **Audit:** P-01 `audit_events`. No `execution_audit_events` table.
- **Capabilities:** P-04 `CapabilityService.has_capability` (live ledger
  grant AND permission-engine allow) is the only capability oracle.
- **Settings pattern:** owner-only JSON in `system_config`, mirroring
  P-04's factory settings (`execution.settings`).
- **HTTP discipline:** P-03's `assert_url_allowed` SSRF guard +
  redirect-re-validating transport.
- **Events:** P-01 bus; P-05 event types added to the enum, security
  types in the persisted-critical set.

## Modes (§23)

`simulation` — policy check 10 permits only true read actions; all
side-effecting execution is refused. `supervised`/`controlled` — full
policy applies. `emergency` mode, or the execution emergency-stop flag —
policy check 1 refuses everything; the stop endpoint additionally
terminates managed subprocesses and pauses browser sessions (§23.7).

## Per-adapter status in THIS environment

| Adapter | Status | Basis |
|---|---|---|
| filesystem | **Operational** | Built + fully tested here (Stage 3) |
| documents | **Operational** | stdlib text/Markdown/CSV; PDF deferred |
| code (Python) | **Operational, process controls only** | NOT a strong sandbox (§10.2) |
| api_http | **Operational** | SSRF-guarded transport; real fetch works where the network allows |
| browser | **Partial** | Session/policy layer + fetch-backed reads operational; interactive backend unavailable here |
| desktop | **Disabled** | Windows UI Automation cannot exist/test on Linux staging |

## Frontend

None (§22): staging has no frontend; P-11 owns the Command Center. All
monitoring data is exposed via endpoints (`/execution/status`,
`/execution/health-report`, requests/evidence/audit views).
