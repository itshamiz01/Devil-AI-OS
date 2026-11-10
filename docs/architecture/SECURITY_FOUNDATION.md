# P-00 Deliverable G — Security Foundation

**Authority:** Constitution §11 — the security layer has authority over every module; no business objective overrides it. **Article 0 (Supreme Principle):** the system must never be able to rewrite its own fundamental safety, ownership or financial-authority rules.

## 1. Identity & permissions (begins P-01, not P-10)

Owner identity (single administrative principal) · per-agent identities in the registry · role-based tool permissions · business-scoped permissions · approval levels L0–L4 enforced deterministically on every action by the Policy & Permission Layer. The AI model proposes; the policy layer disposes.

## 2. Secrets management

No credentials in source code, prompts, model memory or git (`.gitignore` + `.env.example` pattern enforced from P-00). Secrets live in OS secure storage / a secrets manager; agents receive **capability references, never raw credentials**; separate credentials per integration; log redaction standard (secrets, keys, session tokens never written to logs); provider credentials are never exposed to agents (Constitution §2.1 rule).

## 3. Execution security

Sandboxed code execution · filesystem allow-list (project workspace only; governance artefacts read-only) · controlled outbound network (allow-listed destinations per integration) · command execution restrictions · browser session isolation per business · execution timeouts and CPU/memory limits · download scanning before any file is opened by an agent · **untrusted content rule:** web pages, emails, documents and tool outputs are data, never instructions — prompt-injection attempts are logged and ignored (tested in P-10, including injection aimed at Article 0).

## 4. Financial protection

No unrestricted wallet access, ever · read-only connectivity first; payments only via a separate controlled transaction executor · transaction execution is architecturally separate from AI reasoning · explicit limits: starting capital $50 (simulation), per-experiment max loss, per-business budgets, protected reserves (60/20/10/10 allocation is the starting template) · financial audit logs append-only · payment verification & reconciliation before any figure is called "collected revenue" · emergency payment suspension available to the owner at all times · no borrowing, no leverage.

## 5. Emergency controls (designed here; implemented P-01 foundations → P-12 complete)

Global emergency shutdown (owner, one action) · per-agent shutdown · per-business pause · instant permission revocation · process termination · recovery after unexpected termination without duplicating financial or customer actions (idempotency keys).

## 6. Threat model (minimum set, expanded in P-10)

Prompt injection (incl. attempts to amend the Constitution/limits — Article 0 test) · malicious websites & downloads · fake/manipulated business opportunities · fraudulent payment requests · credential theft · agent loops & uncontrolled multiplication · unauthorised spending · privilege escalation · data exfiltration · compromised third-party integrations · silent failure / swallowed errors (forbidden by coding standards).

## 7. Configuration standards adopted in P-00

- ChromaDB telemetry **disabled** (`anonymized_telemetry=False`) — a local-first system does not phone home by default.
- Cloud AI **disabled by default** (`.env.example`: `CLOUD_AI_ENABLED=false`, budget 0) — enabling is an explicit owner act, per business, with costs ledgered.
- Operating mode default: **simulation**.
- Backups before major upgrades; restore rehearsed, not assumed (lesson carried from the ClipOS Phase 11 audit, where backup/DR was the hard gap).

## 8. Requirements imposed on future phases

P-01 ships identity/RBAC skeleton, secrets handling and audit logging with the Core OS. P-02 wires the Policy Layer into the Master Intelligence's execution path. No phase may process real money, real customer data or real publishing before its security acceptance tests pass. P-10 is full hardening + the Article 0 self-amendment test suite; it completes security, it does not start it.
