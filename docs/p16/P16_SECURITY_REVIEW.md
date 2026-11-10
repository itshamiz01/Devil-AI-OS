# P-16 — Security Review (§19)

**Scope:** `app/economy/`, `app/api/routes/economy.py`,
`app/database/models/economy.py`, migration `ccd744b29e54`.

## Authority boundaries

| Rule | Enforcement |
|---|---|
| Economy aggregates are owner/system-only | `_require_reader` on every aggregate read; agent/external principals refused and audited (security tests) |
| All writes are owner-only | `_require_owner` on every create/decide/advance/compute |
| P-07 is the sole financial authority | P-16 has **no** money-movement surface at all — a test asserts `EconomyService` has no transfer/spend/pay/invest/create-business methods; P-07 books byte-equal after P-16 write batches (test + live smoke) |
| P-06 owns business creation | Commercialization hands off to P-03 only; a scenario test proves the business count is unchanged after a full handoff |
| Approvals are hash-bound | P-01 create/decide/verify pattern; foreign-parameter approval refused (security test) |
| Article 0 | No governance, safety or financial-authority rule is modified; settings live in SystemConfig under P-01's config service; Constitution/ADRs untouched |

## Data rules

- **No money columns outside P-07.** P-16's amount fields are
  labelled proposal data (P-13 INTERNAL_ALLOCATION precedent) and
  every API surface that returns them says PROPOSED.
- **Fixtures labelled.** `is_fixture` propagates from P-06 through
  classifications, diversification and the Command Center.
- **Projections never blended.** Collected and projected revenue
  are separate fields in every response.
- **Scores are not probabilities.** Stated in the scoring doc, the
  API rationale strings and the UI.
- **Stress results labelled SIMULATION** in the payload itself.

## Input integrity

- Route models are `extra="forbid"` pydantic models (house
  pattern); unknown keys 422.
- Unknown **scoring** keys (factors, country criteria) are refused
  at the service layer with the valid vocabulary in the error —
  added after the live smoke caught silent dropping; regression
  test `test_unknown_scoring_keys_refused`.
- Evidence requirements are structural: market reports require
  `evidence_sources`, competitors require `source_refs`,
  experiments require the full pre-declaration; all refuse with
  422 rather than defaulting.

## Residual risks / honest limits

- P-16 inherits the platform's standing limits: audit is
  tamper-evident, not tamper-proof (P-10); encryption at rest is
  PARTIAL; DPAPI remains REQUIRES OWNER CONFIGURATION (DEF-A1
  family).
- No real LLM participates in any P-16 judgement (DEF-A2): all
  detectors and recommendations are deterministic rules over
  recorded figures, and say so.
- The profitability gate trusts P-07's verified figures; if P-07
  data were wrong, the gate would be wrong with it. That is the
  intended single-source-of-truth posture, recorded here so the
  dependency is explicit.
