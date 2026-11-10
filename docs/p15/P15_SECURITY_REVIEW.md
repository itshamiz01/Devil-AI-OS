# P-15 SECURITY REVIEW (§15)

## Posture

P-15 operates entirely under P-10. It introduces no new auth, no
new permission system, no credential storage and no execution
privilege. The review below is against §15's checklist.

| §15 requirement | Implementation |
|---|---|
| Role-based access to operational controls | Reads: existing `read_system_data`. Writes: `modify_system_config` at the route **and** an in-service owner gate (portfolio pattern) for incident create/acknowledge/resolve, benchmark runs, backup creation and settings |
| Permission checks before recovery operations | P-15 performs no recovery operations itself; the controls it surfaces delegate to P-10 (backups, suspension) which enforce their own checks — verified live (service principal → 403 on incident create and backup trigger) |
| Audit logs for configuration changes | Settings updates, incident transitions, benchmark runs and backup creation write P-01 audit events via the shared AuditRepository |
| Secure storage of monitoring credentials | None exist: monitoring is in-process (psutil + the app's own services); no new credentials are introduced or stored |
| Protection against log injection | Incident titles/details are length-bounded at the API schema (pydantic) and rendered as data, never formatted into log templates by P-15 |
| Input validation | All request bodies are `extra="forbid"` pydantic models with bounded fields; severity is pattern-restricted to P0–P3 |
| Rate limiting for monitoring APIs | Read endpoints ride the existing FastAPI stack; sampling is interval-bound by settings (min 5s). No dedicated limiter was added — the surface is owner-local and read-mostly; recorded as a noted gap for any future networked deployment |
| Protection against unauthorised process termination | P-15 exposes no process controls at all (deliberate: §14I stop-workers/shutdown stay with the P-01 lifecycle and the operator) |
| Secure backup access | Backup creation delegates to the P-10 service (its own principal checks + audit); P-15 stores no backup copies |
| Separation of monitoring and execution privileges | The sampler/evaluator run as in-process loops with write access only to P-15's four tables; the service's governed methods require an explicit principal |

## Article 0

Nothing in P-15 touches governance, safety or financial-authority
rules: the Constitution/ADRs are untouched, P-10's policy and
broker are read-only inputs, P-07 is read-only (test-proven), and
no P-15 code path can grant an agent new permissions — the
§15 rule "an AI agent must never gain additional permissions
because it repairs a component" holds trivially, because P-15
repairs nothing automatically: it detects, records and reports.

## Findings

- No P0–P2 findings in the P-15 surface. One P3 note: monitoring
  API rate limiting relies on the deployment being owner-local
  (the platform's standing posture); revisit if the Command
  Center is ever exposed beyond the owner's machine.
- One latent pre-existing defect was surfaced by P-15's agent
  panel and repaired minimally (see the changelog): the P-11
  dashboard `agents_summary` counted a non-existent column and
  would have raised on first real use.
