# P-10 Test Report — Security and Governance Engine

## Full suite (one run, final code)

```
575 passed, 1 warning in 366.21s
```

- 509 pre-existing tests (P-01…P-09 regression) — all green.
- 66 new P-10 tests — all green.
- /tmp hygiene (512 MB tmpfs): 5% used (22 MB) before the run,
  5% used (22 MB) after; run used a tmpfs basetemp with a pruner
  deleting finished tests' directories (the P-08/P-09 method).
- The single warning is the pre-existing Starlette/httpx
  deprecation notice, unrelated to P-10.

## New P-10 tests by file

| File | Tests | Covers |
|------|-------|--------|
| `tests/test_p10_unit.py` | 21 | risk classification, patch validation, mode matrix, delegation; SSRF (fake resolvers, rebinding, redirect chains, IP ranges); command/download/filesystem guards; content screening; TOTP RFC 6238 vectors; handoff validation; capability expiry; secret references; hash-chain linkage |
| `tests/test_p10_scenarios.py` | 18 | one named test per §28.10 acceptance scenario (see the implementation report §B for the mapping) |
| `tests/test_p10_security.py` | 16 | decide role check + self-approval refusals + expiry; Article 0 via service, API, P-09 memory poisoning and prompt injection; structural no-second-authority checks; secret values never surface; fail-closed broker under a broken settings store; revoked/bare capability refusals; policy versioning/rollback; login guard normal use + throttle lockout; session logout/revocation; restriction overlay |
| `tests/test_p10_integration.py` | 11 | migration cycle 123→137 (exact sets, twice); startup wiring (facade, guard hook, no duplicate approval table); HTTP status/policies, capability lifecycle, emergency flow, secret metadata masking, audit chain seal/verify + read-only methods, backup create/verify; financial guard against a real P-06 business and real P-07 limits; login-attempt recording; structural no-money-columns proof |

## Live smoke (real uvicorn)

`backend/scripts/p10_smoke.py` — **33 passed, 0 failed**;
transcript: `docs/reports/P10_SMOKE_EVIDENCE.txt`. Opens with the
honesty section (normal mode on empty staging, Windows vault
REQUIRES OWNER CONFIGURATION, MFA unconfigured, 14 seeded
threats), then covers versioned policy, broker + capability
lifecycle, financial authorization (fake/exact/replay), guards,
SSRF, content screening, secret metadata, emergency modes, audit
chain (59 events sealed and verified), alerting, verified backup,
and logout (revoked token → 401).

## Pre-existing tests changed (7, all disclosed in-file)

- `test_p06_security.py::test_security_04_agent_cannot_approve_own_launch` and
  `test_p08_security.py::test_agent_cannot_approve_own_decision` —
  the agent's `decide` call now raises `PermissionDeniedError` at
  the P-01 service layer (the P-10 fix); the P-06/P-08 refusal
  assertions are unchanged in kind and still exercised via the
  owner path.
- Five migration tests (P-02, P-03, P-04, P-05 head pins; P-09
  cycle) — head advanced to `e37d00443d20` / cycle re-pinned to
  its own revision, following the identical P-05…P-09 disclosure
  precedent; exactness preserved.

No other pre-existing test was modified.
