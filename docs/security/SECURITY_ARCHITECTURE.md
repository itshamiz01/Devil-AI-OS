# Security Architecture (P-10)

AUTONOMUS P-10 adds exactly one authority per security concern and
reuses everything earlier phases already own:

```
P-01 owns: principals, roles, permission rules and checks (engine),
sessions, hash-bound approvals, the audit_events trail.
P-07 owns: all money — journal, balances, spending evaluation.
P-09 owns: memory records and their pipeline secret screening.
P-05 owns: execution (filesystem, commands, browser) behind its
own internal policy engine.
P-10 owns: the governance LAYER over all of it — the broker's risk
gates, capability tokens, versioned security policy, the secret
metadata registry and broker, deterministic guards (filesystem /
command / download / egress / content), emergency modes, the
audit hash chain, alerts, incidents, the threat register,
classifications, agent restrictions, and backup verification.
```

Layers of defence (each independently fail-closed):

1. **API guard** — every security route requires a P-01 permission
   (`read_system_data` to read, `modify_system_config` to
   configure). Login is not duplicated; P-10 adds session
   list/revoke/logout on top of P-01 sessions.
2. **Service-level checks** — P-10 services re-check permissions
   through the P-01 engine and, since P-10, `ApprovalService.decide`
   itself enforces the `approve_actions` permission and refuses
   non-owner self-approval at the service layer.
3. **Permission broker** — risk classification (Levels 0–3), mode
   gates (normal / safe_mode / emergency_stop), per-agent
   restriction overlays, business-scope enforcement, capability
   tokens and hash-bound approval binding for higher-risk actions.
4. **Financial guard** — view/approve/execute separation over
   P-07's limits; execution binds an owner-decided P-01 approval
   to the exact transfer parameters and consumes it.
5. **Deterministic guards** — filesystem, command, download,
   egress (SSRF) and content screening: pure functions and regex/
   range rules. No LLM participates in any security decision.
6. **Auditability** — every governance decision writes to the
   P-01 audit trail; P-10 seals the trail with a SHA-256 hash
   chain (tamper-EVIDENT — see AUDIT_AND_MONITORING.md for what
   that does and does not prove on a single host).
7. **Emergency control** — owner-only mode transitions and
   financial suspension, effective immediately, always leaving
   the owner able to recover the system.

Honest boundaries:

- P-05 code execution remains process controls, **not** a strong
  sandbox (no OS/container isolation). P-10 does not claim
  otherwise anywhere.
- MFA is a standards-based TOTP verifier; enrolment is an owner
  configuration step, recovery codes are NOT IMPLEMENTED.
- Windows DPAPI / Credential Manager are an interface with an
  environment-variable fallback on Linux: REQUIRES OWNER
  CONFIGURATION.
- Encryption at rest relies on platform storage protection:
  PARTIALLY IMPLEMENTED (see DATA_PROTECTION.md).

See the threat model, the register in the database
(`security_threat_register`, seeded from THREAT_MODEL.md), and
`docs/audits/P10_IMPLEMENTATION_REPORT.md` for per-item status.
