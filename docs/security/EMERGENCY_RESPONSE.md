# Emergency Response (P-10)

## Modes

| Mode | Non-owner effect | Set by |
|------|------------------|--------|
| `normal` | policy as configured | owner |
| `safe_mode` | read-only (Level 0); services read + heartbeat | owner |
| `emergency_stop` | all non-owner actions denied | owner |

The owner is never mode-blocked — the owner must always be able
to recover the system. Transitions go through the versioned
policy path (the generic settings endpoint refuses mode keys),
are recorded as policy versions AND append-only
`security_emergency_events`, and take effect immediately for
every broker and guard decision.

## Financial suspension

Independent of mode: `financial_suspension` blocks every
financial-guard action except `view`. Set/cleared by the owner
via `/security/emergency/financial-suspension`.

## Incidents

`security_incidents` is the register: open → contained →
recovered → closed, with severity and a summary. Creating an
incident never requires the system to be in a special mode;
closing one is owner-only.

## Runbook (owner)

1. Suspected agent compromise: set `safe_mode`; revoke the
   agent's capabilities; add a restriction (suspend); review the
   audit trail filtered by the agent.
2. Suspected money risk: suspend financial operations; verify
   open approvals; review `security_broker_decisions`.
3. Suspected secret exposure: revoke the secret metadata entry,
   rotate the value **in the owner's vault/environment** (never
   through AUTONOMUS), review `security_secret_access_events`.
4. Recovery: verify the audit chain, clear restrictions
   deliberately, return mode to `normal`, close the incident
   with a summary.

See INCIDENT_RESPONSE_PLAYBOOK.md for the detailed playbook.
