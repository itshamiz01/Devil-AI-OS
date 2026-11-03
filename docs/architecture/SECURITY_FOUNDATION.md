# AUTONOMUS Security Foundation and Threat Model

**Phase:** P-00 · **Status:** Mandatory design baseline; controls not implemented  
**Authority:** Human owner and deterministic governance, never the language model  
**Rule:** No external capability is enabled merely because its adapter exists.

## 1. Protected assets

- Owner identity, administrative authority and financial credentials.
- Wallet/payment access, capital, reserves and transaction integrity.
- Customer personal data, contracts, orders and outstanding obligations.
- Business plans, research, products, source code and private memory.
- Browser sessions, integration tokens and local files.
- Policy configuration, approval records, audit history and backups.
- Host integrity, compute resources and availability of emergency controls.

## 2. Trust boundaries and assumptions

Untrusted inputs include model output, websites, search results, emails, documents, downloads, marketplace responses, third-party APIs and retrieved memory. A valid JSON object is not a trusted instruction. A signed-in browser is not permission to perform every available account action.

The initial host is owner-controlled, but malicious code running with the owner's full privileges can still access owner data. Application-level permissions are insufficient without OS-level isolation for hostile workloads. Tauri's core/plugin code is privileged; its WebView/core boundary must be explicitly constrained. [7](https://v2.tauri.app/security/)

No design in this document claims protection against a fully compromised OS administrator or physical device attacker. Hardware-backed credentials, separate execution hosts and external audit storage may be needed for stronger guarantees.

## 3. Threat model

| Threat | Example | Required control | Verification phase |
|---|---|---|---|
| Prompt injection | Web page asks agent to reveal tokens or change policy | Treat content as data; scoped tools; deterministic authorization; secret isolation | P-02/P-03/P-05/P-10 |
| Privilege escalation | Research agent requests financial tool or edits its role | Deny by default; owner-only policy changes; scope/ancestor checks | P-01/P-04/P-10 |
| Credential theft | Model asks for API key or reads browser cookies | Secrets broker; separate profiles; no secret values in prompts/logs | P-01/P-05/P-07 |
| Unauthorized spending | Forged invoice or repeated transfer request | Bound approval; atomic budget reservation; recipient/amount limits; payment executor | P-01 foundations/P-07 |
| Duplicate side effect | Retry sends a second email or payment | Idempotency, durable intent, external-state reconciliation | P-05/P-07/P-12 |
| Malicious code/download | Generated script reads unrelated files or installs malware | Isolated execution, scoped filesystem/network, dependency approval and scanning | P-05/P-10 |
| Data exfiltration | Private business data sent to an unapproved endpoint/cloud | Egress policy, data classification, provider allowlist and owner consent | P-02/P-05/P-10 |
| Cross-business leakage | Director reads another business's customers/memory | Scoped services, explicit sharing grants and negative tests | P-06/P-13 |
| Runaway multiplication | Agents recursively create workers | Factory quotas, depth/cycle checks, budgets and backpressure | P-04/P-08 |
| Audit evasion | Agent disables logging or rewrites history | Independent audit service, append-only records and owner-protected backups | P-01/P-10 |
| Supply-chain compromise | Malicious package/model/update | Pin/review dependencies, verify provenance, SBOM and signed updates | P-01 onward/P-15 |
| Fake revenue | Model labels a forecast as collected cash | Provider verification, reconciliation and segregated simulation data | P-07/P-08 |
| Local API abuse | Malicious local/web process calls privileged endpoints | Owner authentication, loopback binding, origin checks and narrow IPC | P-01/P-10 |
| Stale worker | Old process resumes after cancellation | Fencing tokens, revocation checks and pre-side-effect cancellation checks | P-01/P-12 |

## 4. Identity, authorization and approvals

- Separate owner, application service, agent, worker/node and integration identities.
- Authenticate local API callers; local origin alone is not identity.
- Use least-privilege, resource-specific grants with business scope and expiry.
- Evaluate mode, action risk, tool, resource, amount, recipient, policy version and emergency state.
- Deny by default; explicit deny and suspension override allow rules.
- Agents cannot edit their own grants, policy, audit configuration or owner identity.
- Approval requests show the exact action, amount/currency, recipient, business, evidence, risks and expiry.
- Approval binds to a canonical payload hash and is consumed atomically; changed details require new approval.
- Critical actions require the owner even if an agent has a broad operational role.
- Policy administration is outside the model/tool surface available to business agents.

The L0–L4 model is defined in [AGENT_GOVERNANCE.md](AGENT_GOVERNANCE.md). It is not a substitute for resource-level checks.

## 5. Secrets management

- No credentials in source code, Git, prompts, model memory, ordinary configuration, embeddings or error traces.
- Prefer Windows Credential Manager or appropriately scoped DPAPI-protected storage; verify the selected backend and account context.
- A service running under a different account may not decrypt a user's DPAPI secrets. Resolve the service identity design before implementation.
- Use separate credentials/scopes for research, publishing, payments and cloud inference.
- Prefer read-only integration credentials where supported.
- Broker secrets to a narrow executor, not to the reasoning agent.
- Never expose wallet private keys to a language model. P-00 does not select or connect a wallet.
- Redact logs and errors, but treat redaction as defense in depth—not permission to collect secrets.
- Support rotation, revocation and integration disablement without changing business logic.

`.env.example` and the JSON example are inert templates. They contain no credentials and are not read by an application in P-00.

## 6. Execution and host isolation

Required properties for untrusted code and automation:

- A restricted workspace with canonical path checks, symlink/junction/reparse-point protection and no arbitrary host-path access.
- Explicit command/tool registration; avoid shell interpolation and arbitrary command strings.
- Network egress restrictions by task/integration, including redirect and DNS-rebinding/SSRF considerations.
- CPU, memory, process, disk, queue and wall-clock limits.
- Download type/size limits, provenance recording and malware scanning where available.
- No automatic dependency installation or privileged system changes from model output.
- Cancellation and process-tree termination, including ambiguous-side-effect handling.

A Python subprocess, virtual environment or prompt instruction is **not** a sandbox. Windows isolation options such as Windows Sandbox, a VM or a suitably restricted AppContainer/Job Object design must be evaluated against edition, licensing, automation and resource requirements. D-07 remains open. Until a suitable boundary is verified, untrusted code execution stays disabled or confined to explicitly authorized low-risk workflows.

Desktop control is a fallback, not a universal permission. Prefer official APIs and structured automation. Do not grant unrestricted mouse/keyboard control over the owner's authenticated desktop.

## 7. Browser and integration security

- Separate anonymous research profiles from authenticated business sessions.
- Persist sessions only with explicit authorization and protected storage.
- Scope cookies/tokens by integration and business; never pass a whole browser profile to an arbitrary agent.
- Apply domain/action allowlists for authenticated operations.
- Treat page text, hidden elements and downloaded files as untrusted.
- Require approval for publication, messages, account changes and purchases according to policy.
- Respect platform terms, consent, anti-spam rules and rate limits.
- Record source coverage and evidence; do not fabricate market research.
- Use official APIs before browser automation and desktop interaction.

## 8. Financial safeguards

Minimum foundations must precede any corresponding external capability, even though comprehensive financial implementation is P-07.

- Live financial execution is disabled by default and remains unavailable in P-00.
- Separate reasoning, authorization, budget reservation, transaction execution and reconciliation.
- Enforce protected reserves, per-business/experiment budgets, maximum loss, exposure and liquidity limits in deterministic code.
- No borrowing, leverage or unapproved transfers.
- Verify balances and payments from authorized provider records; model text is not evidence of collection.
- Use idempotency keys where supported; otherwise query/reconcile before retry.
- Treat refunds, fees, chargebacks and liabilities as explicit records.
- Never reinvest forecast revenue or money reserved for obligations.
- Keep simulation and live ledgers separate; simulated payments cannot satisfy the real-revenue acceptance test.
- Suspend payments independently of the rest of the OS when necessary.

Accounting terminology and the exact profit/ROI definitions require D-04 approval before live financial reporting.

## 9. Audit, monitoring and privacy

Record actor, business, action, resource, policy version, decision, approval reference, correlation ID, timestamp, payload hash and outcome. Store concise rationale and evidence references, not hidden reasoning or secrets.

Use append-only audit records and a tamper-evident sequence where practical. A local hash chain is not immutable against a compromised host; protected external backups or another trust anchor are needed for stronger assurance.

Monitor denied actions, repeated failures, unusual spending, resource spikes, policy changes and cross-business access attempts. Define retention and access rules for logs and customer data. Cloud transfer requires explicit data-classification and provider policy approval.

## 10. Emergency controls

Design five distinct controls:

1. **Global emergency stop:** persist emergency mode, stop new external actions, revoke execution leases and cancel eligible work.
2. **Payment suspension:** block new financial commitments while retaining read-only reconciliation and monitoring.
3. **Business pause:** stop that business's workflows without deleting records or obligations.
4. **Agent pause/termination:** revoke grants and cancel/reassign eligible tasks.
5. **Permission/integration revocation:** invalidate future use immediately; investigate already-executed actions.

Cancellation cannot recall a completed external payment, email or publication. Mark uncertain outcomes and reconcile them. Emergency state must survive restart and must not be cleared automatically. Essential audit, recovery and owner-control paths remain available.

## 11. Cross-phase minimum security gates

| Phase | Minimum controls before acceptance |
|---|---|
| P-01 | Owner authentication; safe local binding/IPC; policy/approval schema; durable audit; secret-store design; emergency-state foundation; migration/backup tests |
| P-02 | Untrusted model-output validation; provider/privacy/budget policy; no self-authorization; bounded planning/tool proposals |
| P-03 | Source provenance; injection-resistant research; source coverage; no fabricated evidence |
| P-04 | Scoped identity; factory quotas/depth/cycle checks; no descendant privilege escalation |
| P-05 | Verified execution isolation; file/network/command restrictions; browser-session separation; cancellation |
| P-06 | Business/customer isolation; authorized channels; obligation tracking |
| P-07 | Verified ledger; atomic budgets; bound approvals; idempotent/reconciled payment execution |
| P-08/P-09 | Preserve essential controls; validated memory; no cross-business leakage |
| P-10 | Comprehensive adversarial testing, hardening and independent security review |
| P-12 | Restart-safe emergency state and no duplicate external effects |
| P-13/P-16 | Explicit cross-business/node identity and authorization |
| P-14/P-15 | Integration audit, dependency/license review, recovery and target-hardware reliability |

These are cross-cutting acceptance requirements, not permission to postpone protection until P-10. D-03 records the requested owner approval for this interpretation.

## 12. Required future security tests

Unauthorized API/IPC calls; altered/expired/replayed approvals; privilege escalation; prompt injection and secret extraction; path traversal and junction escape; SSRF/egress violations; malicious downloads; resource exhaustion; recursive agent creation; duplicate payments/messages; audit tampering; emergency stop during execution; restart in emergency mode; backup restore; cross-business and cross-node access denial.

**P-00 provides a threat model and design requirements only. It does not certify the application secure.**
