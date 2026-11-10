# Incident Response Playbook (P-10)

Severity guide: `critical` = money moved or secrets exposed or
governance altered; `high` = attempted critical, blocked;
`medium` = policy violation contained; `low` = noise/threshold
events.

## 1. Agent misbehaviour / suspected compromise

1. `POST /security/emergency/mode` → `safe_mode` (stops writes).
2. Revoke the agent's capabilities
   (`POST /security/capabilities/{id}/revoke`).
3. Suspend the agent (`POST /security/agents/{id}/restriction`
   → `suspended`).
4. Open an incident; pull the audit trail filtered by the agent
   (`GET /security/audit?actor_id=…` includes P-01
   `permission.check` rows).
5. If money may be involved: financial suspension ON; review
   `security_broker_decisions` and P-07's journal.
6. Recover deliberately: clear restriction → mode `normal` →
   close the incident with a summary.

## 2. Suspected secret exposure

1. Revoke the registry entry (`POST /security/secrets/{name}/revoke`).
2. Rotate the value **in the vault/environment** (never via chat,
   tickets, or AUTONOMUS itself).
3. Review `security_secret_access_events` for the window.
4. Outbound-screen any content sent in the window; open an
   incident at `critical` if the value left the host.

## 3. Audit integrity failure

1. Do NOT re-seal over a broken chain — preserve the database.
2. `GET /security/audit/verify` reports the first broken link;
   compare against the most recent backup's chain state.
3. Restore from the last verified backup (stop the app, replace
   the database file with the backup copy, restart, verify).
4. Treat unexplained breaks as `critical` incidents.

## 4. Brute force / credential stuffing

1. Confirm the login guard is throttling (status + attempts).
2. Shorten the window / lower `login_max_failures` via a policy
   update if the attack persists.
3. Revoke all sessions for the targeted account
   (`/security/auth/sessions`), rotate the owner's password
   through P-01's normal flow, enrol MFA (owner step).

## 5. Restore drill (rehearsed, not improvised)

Stop app → copy current DB aside → copy backup file into place →
start app → `GET /security/status` + `/security/audit/verify` →
log the drill in an incident record marked as a drill. The P-10
test suite rehearses exactly this cycle against a scratch
database (Scenario 13).
