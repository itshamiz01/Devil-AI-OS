# Expansion Feature 1 — Test Report (Gate 3 evidence)

All figures are from runs on the FINAL code (10 Nov 2026).

## Feature acceptance tests (new, F01)

**Backend: 30 new tests, all passing**
(`tests/test_f01_unit.py` 7, `tests/test_f01_integration.py` 10,
`tests/test_f01_security.py` 13; support: `tests/f01_support.py`).

Coverage against the feature's acceptance list:

- **Device enrolment** — starts untrusted; secret returned once;
  stored row holds only the SHA-256 hash (asserted against the
  live value); list/detail surfaces never contain the secret or
  its hash; enrolment audited without the secret.
- **Trust** — explicit owner act; double-trust and trust-after-
  revoke are state errors (409 over HTTP).
- **Session binding** — trusted-device login binds the session
  (row + owner session list show `device_id`, last-seen moves,
  `security.device_login` audited); unbound login behaviour is
  byte-identical legacy behaviour; a device credential never
  substitutes for the password (valid device + wrong password
  fails).
- **Refusal paths** — unknown device, untrusted device, bad
  secret, revoked device, and partial device fields all refuse
  the login, are audited with reason categories
  (`security.device_credential_refused`), and are recorded by
  the P-10 login guard as failed attempts.
- **Revocation** — kills the live bound token; terminal (trust,
  rotate and re-revoke all refused); sessions swept in the store.
- **Rotation** — old secret refused, new secret works, bound
  sessions killed.
- **Untrust** — kills bound sessions and refuses new bindings.
- **Recovery codes** — generate (counts only afterwards), verify
  success, **single-use** (second verify fails), transcription
  normalisation, wrong code fails, **regeneration invalidates**
  the previous unused codes (exact counts asserted), audit
  actions for generate/use/refuse.
- **Secrets hygiene** — plaintext codes exist in no stored
  column (scrypt hashes asserted) and in no audit detail; the
  device secret likewise.
- **Non-owner refusals** — agent/service/external principals
  refused for every device and recovery operation, at the service
  layer and over HTTP (403), unauthenticated 401; a non-owner
  verify attempt does not consume the code.
- **Schema guards** — metadata registers exactly two new tables;
  no money-shaped column exists in either; `app_sessions.device_id`
  is nullable (legacy rows valid).
- **Migration cycle** — upgrade to head `85b7a9805207` = 226
  physical tables with `device_id` present; downgrade to
  `218ddd92a0aa` = 224 without it; re-upgrade = 226.

**Frontend: 3 new tests, all passing**
(`src/views/IdentityDevices.test.tsx`): device list renders the
backend's trust state and the Trust action posts to P-10 and
re-reads; enrolment displays the minted secret once and dismiss
removes it (no re-display path); recovery panel shows counts,
generates a batch shown once (behind a confirmation), and a
verify round-trip reports consumption honestly.

## Full regression (final code)

- **Backend: 983 passed / 0 failed** (953 P-18 baseline + 30 new).
  Method: 13 chunks over a C-locale-sorted file list, per-chunk
  tmpfs basetemp + pruning (the P-16→P-18 method). First pass:
  970 passed / 13 failed — all 13 were exact-pin assertions the
  additive migration necessarily advances (head/count pins in the
  p02–p05, p11–p16 files). Each was advanced with an Expansion
  F01 disclosure comment, strictness preserved; the ten affected
  files were re-run in two chunks: 84 + 73 passed. Transcript:
  `REGRESSION_EVIDENCE.txt` in this folder.
- **Frontend: 55 passed / 55** (52 baseline + 3 new), 16 files,
  plus a clean strict TypeScript build (`tsc --noEmit` + vite
  build).
- **Live smoke: 29 passed / 0 failed** over real uvicorn
  (`backend/scripts/f01_smoke.py`, transcript
  `docs/reports/F01_SMOKE_EVIDENCE.txt`): fresh auto-migrated DB
  at the F01 head with 226 tables; the full device lifecycle and
  recovery-code lifecycle over HTTP; rotation and revocation
  killing live sessions over HTTP; the audit trail carrying every
  event; the built Command Center served at /app. Owner login
  succeeded on attempt 1 behind the `/health/ready` gate.

## Environment notes

- `/tmp` was checked before every run and pruned between chunks;
  no disk-full event occurred during the final runs, so no result
  needed the environment-failure diagnosis.
- One test-authoring defect was found and fixed during the build
  (the recovery-code alphabet has 31 symbols, not 32 — the unit
  test now pins the true count; entropy ≈ 59 bits per code).
