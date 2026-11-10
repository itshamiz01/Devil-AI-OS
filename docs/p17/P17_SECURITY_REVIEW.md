# P-17 — Security Review (§25)

## Authority boundaries

- **Owner-only writes and decisions** in-service (the P-13/P-16
  posture): agents are refused on every write path and on every
  read of customer/growth aggregates; a refused read is audited as
  `growth.isolation_violation`. Routes mirror the house pattern
  (read / modify / approve permissions) and never widen service
  rules.
- **Article 0 held.** No governance, safety or financial-authority
  rule was modified. A named test proves P-07's revenue metrics,
  expense totals and business summary are **byte-equal before and
  after a full round of P-17 writes**; a schema test proves no
  P-17 table carries a revenue/profit/journal/ledger/collected
  column. P-17's only financial act is preparing P-07 spending
  requests inside P-07's own approval workflow.
- **The P-16 profitability gate is consumed, never rebuilt or
  bypassed**; the only override is per-item, owner-only, with a
  mandatory recorded reason.

## Customer-data protections

- Per-business isolation on every row; no cross-business read,
  copy or messaging path exists (template↔recipient business match
  is enforced at queue time). Tested explicitly.
- Lead sources are a closed authorised vocabulary; purchased /
  scraped / brokered sources are refused and the attempt audited.
- Consent is recorded before contact; queueing requires granted
  (or not-required transactional) consent; withdrawn/unknown are
  never contacted. Suppression is permanent per business and
  blocks re-creation and queueing.
- Anti-spam frequency cap per recipient (owner-configurable,
  default 4 per 30 days), enforced at queue time.
- Deceptive marketing is refused mechanically: templates
  containing false-urgency / false-scarcity / guaranteed-results
  patterns are rejected and audited; content containing the owning
  business's own prohibited claims cannot pass its brand check.
  (The pattern list is a documented guardrail, not a censor — see
  `constants.DECEPTIVE_PATTERNS`.)

## Honest security limits

- No transport exists, so no message can leak: dispatch is
  structurally blocked, and no row can be marked sent/delivered.
- Customer data is plaintext SQLite in staging, as in every prior
  phase; encryption at rest remains PARTIAL (P-10 posture) and
  Windows DPAPI remains REQUIRES OWNER CONFIGURATION (DEF-A1).
- P-05 execution remains process controls, not a strong sandbox —
  unchanged, and P-17 adds no execution capability at all.
