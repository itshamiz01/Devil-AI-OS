# Expansion Feature 2 — Universal Integration Framework: Test Report

All figures measured on final code, 2026-11-10.

## Feature acceptance tests (pack §5 Gate 3 + §7.2)

| Area | Where | Result |
| --- | --- | --- |
| Descriptor/capability contract validation (bad permission, UNCLASSIFIED risk action, duplicate capability, bad schema) | `tests/test_f02_unit.py` | pass |
| Payload schema validator (types, required, enum, additionalProperties) | `tests/test_f02_unit.py` | pass |
| Schema guards: no money columns, no secret-value columns (whitelisted NAME reference only); framework source holds no financial/approval machinery | `tests/test_f02_unit.py` | pass |
| Catalogue + OpenAPI: `x-required-permission` present, public operations == 3, literal permission bindings all name enum values, version single source | `tests/test_f02_unit.py` | pass |
| Migration cycle 226 ⇄ 228 physical tables (head `3f7a1c9e52b4`) | `tests/test_f02_integration.py` | pass |
| Seeded registry honest states (1 configured, 17 requires_owner_configuration, exactly 1 adapter) | `tests/test_f02_integration.py` | pass |
| Lifecycle: register → configure (unknown secret NAME refused) → enable refused without adapter → attach adapter → enable/disable; counts | `tests/test_f02_integration.py` | pass |
| Reference connector end-to-end invoke with broker decision id; health; disable honesty | `tests/test_f02_integration.py` | pass |
| Honest failures: unconfigured Stripe (no fabricated success), undeclared capability, schema-violating payload | `tests/test_f02_integration.py` | pass |
| Idempotent replay returns the recorded result, adapter not re-executed | `tests/test_f02_integration.py` | pass |
| HTTP surface + catalogue over the real API; 401 unauthenticated; 403 non-owner configure | `tests/test_f02_integration.py` | pass |
| Broker denial for an EXTERNAL principal recorded with decision id (AGENT positive control passes) | `tests/test_f02_security.py` | pass |
| Level-3 hash-bound approval: none → denied; mis-bound → denied; exactly-bound owner approval → success | `tests/test_f02_security.py` | pass |
| Credential resolved only via P-10; value absent from framework tables, audit details and secrets metadata; revoked credential → honest refusal; missing env value fails honestly | `tests/test_f02_security.py` | pass |
| Adapter auth_error/timeout recorded as `error`; rate limit enforced; unhealthy adapter reported; webhook verification refuses honestly without a hook | `tests/test_f02_security.py` | pass |
| Lifecycle/configuration owner-only at the service layer | `tests/test_f02_security.py` | pass |

**F02 backend tests: 34 passed / 0 failed** (unit 12, integration
11, security 11). **F02 frontend tests: 3 passed** in
`frontend/src/views/Integrations.test.tsx` (registry states
rendered honestly incl. "None — not a working connector";
configure carries a secret NAME only; invoke posts through the
framework and shows the result).

## Full regression on final code

- **Backend: 1017 passed / 0 failed** (983 pre-F02 baseline + 34
  new). Method: 14 chunks over the C-locale-sorted file list,
  per-chunk tmpfs basetemp deleted after each chunk (`/tmp` is a
  512 MB tmpfs). First pass: 1002 passed / 15 failed — all 15
  were exact migration-head/table-count pins in earlier suites
  advanced by F02's additive migration; advanced with F02
  disclosure comments (strictness preserved) and the 12 affected
  files re-run green (74 + 100 passed). Full detail:
  `REGRESSION_EVIDENCE.txt` in this folder.
- **Frontend: 58 passed / 0 failed** (55 baseline + 3 new) and a
  clean strict build (`tsc --noEmit && vite build`).

## Live smoke (real uvicorn, built Command Center)

`backend/scripts/f02_smoke.py` → `docs/reports/F02_SMOKE_EVIDENCE.txt`:
**27 passed / 0 failed.** Auto-migration to `3f7a1c9e52b4`
(228 tables); readiness-gated owner login succeeded on attempt 1
(the P-17 boot-window observation did not recur); registry seeded
(18 connectors, 1 adapter); echo invocation through the broker
with decision id; idempotent replay; honest 502 for unconfigured
Stripe; 422 for a schema-violating payload; disable/enable cycle;
adapter-less custom connector cannot be enabled (422); catalogue
names the invoke permission and counts exactly 3 public
operations; OpenAPI version 1.2.0 with `x-required-permission`;
invocation ledger and audit trail carry the framework's events;
Command Center served at `/app`.
