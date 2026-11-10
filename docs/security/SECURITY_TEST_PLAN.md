# Security Test Plan (P-10)

## Layers

1. **Unit** (`tests/test_p10_unit.py`, 21 tests) — pure policy:
   risk classification, patch validation, mode matrix, delegation
   rules; SSRF validator incl. fake-resolver rebinding and
   redirect chains; command/download/filesystem guards; content
   screening; TOTP against RFC 6238 vectors; handoff validation;
   capability expiry; secret-reference validation; audit-chain
   linkage.
2. **Acceptance scenarios** (`tests/test_p10_scenarios.py`, 18
   tests) — one named test per §28.10 scenario of the P-10
   prompt, each stating premise, attack and expected outcome.
3. **Security tests** (`tests/test_p10_security.py`, 16 tests) —
   the decide role-check and self-approval refusals, Article 0
   under service/API/memory/injection attack, structural
   no-second-authority checks, secret-value non-appearance,
   fail-closed broker behaviour, login throttling, session
   revocation, restriction overlay.
4. **Integration** (`tests/test_p10_integration.py`, 11 tests) —
   migration cycle 123→137 tables (exact sets, twice), startup
   wiring, the full HTTP surface, the financial guard against a
   real P-06 business and real P-07 limits, login-attempt
   recording, and the structural proof that no P-10 table has a
   money column.
5. **Live smoke** (`backend/scripts/p10_smoke.py`) — real
   uvicorn, 33 checks, honesty section first; transcript at
   `docs/reports/P10_SMOKE_EVIDENCE.txt`.
6. **Regression** — the entire pre-P-10 suite (509 tests) must
   stay green in the same run. Two pre-existing tests changed
   with "P-10 disclosure" comments (strictness preserved): the
   P-06 and P-08 "agent cannot approve own…" service tests, whose
   refusal point moved earlier to the P-01 decide role check.

## Negative-testing rules

- Every allow path has a paired deny path in the same file.
- Security fixtures never contain real secret values; synthetic
  patterns only.
- A test that cannot fail is not evidence: the tamper tests
  mutate real rows/approvals and re-verify detection.
