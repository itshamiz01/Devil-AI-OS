# P-03 — Research Security (§21) — summary

Full detail: `docs/reports/P03_SECURITY_REPORT.md`.

## Core rule

**All fetched/seeded content is untrusted data.** Instructions inside research content are never authority — they cannot create tasks, change permissions, alter scoring, contact anyone, or modify the system. Enforcement is structural, in layers:

1. **Nothing executes content.** Research runs only as P-01 tasks via the registered `opportunity.research` handler; the handler processes declared source ids with deterministic extractors. There is no code path from document text to any action.
2. **Injection scanning before use.** Every document (seed fixture or fetched page) passes `scan_for_injection` (directive patterns: "ignore previous instructions", "system prompt", "you must … send/run/delete", credential/token exfiltration phrasing, etc.). A match **quarantines the whole document**: none of its claims enter the evidence store, a `PromptInjectionDetected` system event is emitted, an audit record is written, and the opportunity history gains an `injection_quarantined` entry. Demonstrated in the smoke run (forum fixture document) and in security tests (fixture path and MockTransport web-page path).
3. **SSRF guard** on every fetch (scheme allowlist; loopback/private/link-local/reserved refused), robots.txt respect, no auth-required sources, no paywall/CAPTCHA bypass, response-size cap.
4. **Governance isolation.** Scoring weights are owner-only configuration (agent/service principals get 403 at the API and a service-layer refusal); owner-grade validation evidence is owner-only; API access is permission-gated (`read_business_data` / `modify_business_data` / `modify_system_config`) on top of P-01's deny-by-default engine; no-principal requests get 401.
5. **Modes.** Emergency mode blocks research submission; simulation mode disables live fetching entirely (seed/owner sources only).
6. **Secrets.** The research proxy URL is treated as a secret-shaped setting (masked in config dumps — `proxy` added to `SECRET_FIELD_HINTS` during this build) and is passed to processes via environment only; it never appears in code, docs or transcripts.
7. **Data minimisation.** Extraction keeps verbatim price mentions and claim records with provenance; raw page bodies are not persisted beyond the research session's processing.

## Residual risks (honest)

- The injection scanner is pattern-based (same posture as P-02): it catches known directive shapes; novel phrasing may pass the scan — but layer 1 means even an unscanned instruction has no execution path. Defence in depth, honestly bounded.
- robots.txt handling is a light Disallow check, not a full RFC 9309 group parser.
- Live fetching inherits the host environment's network policy (sandbox proxy here; owner's network on his machine).
