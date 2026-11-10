# P-03 Security Report (§21)

**Date:** 9 November 2026 · **Security tests:** 14/14 passed (`tests/test_p03_security.py`) · **Smoke security evidence:** injection quarantined live in the pipeline (`P03_SMOKE_EVIDENCE.txt`)

## Findings by control

### 1. Untrusted content & prompt injection (§21.2) — CONTROLLED
- All source content is data. Research executes only through the registered `opportunity.research` P-01 handler with deterministic extractors; there is **no path** from document text to task creation, permission changes, scoring changes, messages, or any external write.
- `scan_for_injection` runs on every document before extraction. Matches quarantine the entire document (zero claims stored), emit `PromptInjectionDetected`, write an audit record, and add an `injection_quarantined` history entry.
- Demonstrated three ways: seed forum fixture through the real task pipeline (integration test **and** live smoke), and a malicious page via `MockTransport` (security test). In all cases: quarantined count 1, claims from the document 0, event present.
- Honest bound: the scanner is pattern-based (P-02 posture). A novel phrasing could evade the scan — but the structural layer (no execution path from content) means an unscanned instruction still does nothing.

### 2. Network safety (§8.2, §21) — CONTROLLED
- SSRF guard: http/https only; loopback/private/link-local/reserved/localhost refused (unit + integration tests). The test-only private-host escape hatch is refused by config validation when `environment=production`.
- robots.txt Disallow refuses the fetch; auth-required sources are never fetched (no credentials exist to leak); HTTP 403/404 recorded as unavailable with no content used — **no bypass of bot protection, paywalls, CAPTCHAs or rate limits anywhere in the codebase**.
- Response size capped; TLS verification uses the platform CA bundle and is never disabled (see implementation report, defect 1 — the fix *moved* verification to the correct trust store).

### 3. Governance isolation (§21, Article 0) — CONTROLLED
- Scoring weights: readable by permitted readers; writable only by the **owner principal** with `modify_system_config`. Agent principal → HTTP 403 (test). The service layer refuses non-owner edits independently of the route.
- Owner-grade evidence (`owner_real_world` / `owner_payment`, the only path to validation Levels 4–5): agent and service principals → HTTP 403 (test); owner succeeds.
- API surface: reads require `read_business_data`, writes `modify_business_data` (P-01 deny-by-default engine). Service principal → 403 on opportunities API; no principal → 401 (tests).
- No P-03 code writes outside its own tables; no external writes of any kind exist in the module (§26: no launches, purchases, accounts, messages).

### 4. Mode enforcement — CONTROLLED
- Emergency mode: research submission refused (test + code path through P-01 task admission).
- Simulation mode: live sources refused inside research sessions; seed/owner sources only (test).

### 5. Secrets handling — CONTROLLED
- `research_proxy_url` (whose sandbox value embeds a credential token) is masked in configuration dumps (`proxy` added to `SECRET_FIELD_HINTS` during this build) and was passed to the smoke server via environment only. It appears in no file, log, transcript or report. Verified: the string does not occur in the repository (grep over the project, excluding `.venv`).

### 6. Auditability — CONTROLLED
- Opportunity lifecycle transitions, hard rejections, injection quarantines and validation decisions are persisted (history table, audit events, system events: `ResearchStarted/Completed`, `OpportunityDiscovered/StatusChanged/HardRejected/Scored/Validated`, `PromptInjectionDetected`).

## Residual risks (accepted, recorded)

| Risk | Posture |
|---|---|
| Pattern-based injection scan evasion | Mitigated structurally (no execution path); revisit if an LLM ever reads research content (P-02 provider work, future phase) |
| robots.txt is a light Disallow check | Acceptable for registered-source research; full RFC 9309 parser is future work |
| Fetched pages could contain misleading (non-instruction) claims | Handled by evidence ceilings + corroboration + contradiction, not by the security layer |
| Live fetching inherits host network policy | By design; outcomes recorded truthfully |
