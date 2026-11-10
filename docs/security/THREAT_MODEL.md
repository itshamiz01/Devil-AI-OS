# Threat Model (P-10)

Scope: the AUTONOMUS staging system — a single-host, local-first
application with one owner, delegated agents, business units,
financial records (P-07), memory (P-09) and execution (P-05).

## Adversaries and failure sources

1. **A compromised or misbehaving agent** — exceeds its mandate,
   tries to widen its permissions, approve its own work, move
   money, read secrets, or persist hostile instructions in memory
   for later phases.
2. **Hostile external content** — web pages, emails, documents and
   tool outputs carrying prompt-injection: instructions dressed as
   data, including content an agent stored in P-09 memory and a
   later agent retrieves.
3. **A buggy component** — a subsystem that mis-authorizes, leaks
   a secret into a log, or corrupts the audit trail.
4. **An external network attacker** — SSRF against internal
   services and cloud metadata, open redirects, malicious
   downloads, credential-bearing URLs.
5. **Local misuse** — destructive commands, protected-path access,
   execution of untrusted binaries.

## Trust boundaries

- Only the **owner** is root authority. Agents, external accounts,
  services and AI models never hold owner-only permissions
  (approve actions, modify configuration, access sensitive data)
  and can never receive them by delegation or by handoff payload.
- All untrusted content enters as **data** with a trust level;
  lower trust never overrides higher (owner > developer > user >
  system tool output > business data > memory > external content).
- The database is trusted storage on the owner's host; the audit
  hash chain makes post-hoc edits *detectable*, not impossible
  (see AUDIT_AND_MONITORING.md).

## Seeded threat register

The register is seeded into `security_threat_register` (14
threats, T-01…T-14), each row naming its control and the test that
verifies it:

| ID | Threat | Primary control | Verifying test |
|----|--------|-----------------|----------------|
| T-01 | Agent privilege escalation | broker risk gates + delegation rules | test_scenario_01 |
| T-02 | Approval replay / tampering / expiry | P-01 hash binding + P-10 single-use consumption | test_scenario_02, 03; security tests |
| T-03 | Prompt injection via content or memory | trust hierarchy, screening, memory-is-data | test_scenario_05; security tests |
| T-04 | SSRF to internal/metadata endpoints | egress validator, per-hop revalidation | test_scenario_09; unit tests |
| T-05 | Secret leakage into logs/memory/content | metadata+broker, pattern-only events, outbound screen | test_scenario_06 |
| T-06 | Financial transfer without approval | financial guard view/approve/execute separation | test_scenario_07 |
| T-07 | Forged payment webhook | P-07 signature verification (unchanged) | test_scenario_10 |
| T-08 | Audit tampering / log deletion | hash chain, append-only trail, read-only API | test_scenario_18 |
| T-09 | Destructive command execution | command guard denylist/allowlist via P-05 | test_scenario_05(unit), guards tests |
| T-10 | Malicious download | download guard (extensions/size/quarantine) | unit tests |
| T-11 | Credential stuffing / brute force | login guard throttling, session controls | test_scenario_11; security tests |
| T-12 | Browser session crossing businesses | session/business binding check | test_scenario_12 |
| T-13 | Governance self-amendment (Article 0) | owner-only policy path; agents blocked at service + API | test_scenario_16; security tests |
| T-14 | Backup corruption / failed restore | checksum + integrity verify, restore drill | test_scenario_13 |

## Out of scope (stated plainly)

- A host-level attacker with write access to the database file
  AND the ability to recompute the hash chain undetected over
  time (mitigated only by off-host copies — owner's choice).
- Nation-state endpoint compromise, side channels, and physical
  access.
- Multi-tenant isolation: AUTONOMUS is a single-owner system.
