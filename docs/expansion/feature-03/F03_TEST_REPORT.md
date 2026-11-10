# Expansion Feature 3 — Voice Assistant: Test Report

All figures measured on final code, 2026-11-10.

## Feature acceptance tests (pack §5 Gate 3 + §7.3)

| Area | Where | Result |
| --- | --- | --- |
| Deterministic classifier: question / information request / system operation / financial / high-risk / unresolved; word-boundary screens; interrogatives | `tests/test_f03_unit.py` | pass |
| Stop phrases: exact normalised set (stop / cancel / never mind / emergency stop…), trailing punctuation tolerated, embedded "stop" does NOT cancel; configured stop word honoured | `tests/test_f03_unit.py` | pass |
| Provider honesty: `local_whisper` probe in staging → unavailable with the DEF-A2 reason; no TTS provider exists | `tests/test_f03_unit.py` | pass |
| Fixture labelling: the test double's every output carries `is_fixture=True` and the FIXTURE model label; no invented confidence | `tests/test_f03_unit.py` | pass |
| Schema guards: no money columns and no secret-value columns in any voice table; Article 0 structural guards (no `.decide(`, no financial/GovernanceService import in `app/voice`); metadata count 231; APP_VERSION 1.3.0 | `tests/test_f03_unit.py` | pass |
| Migration cycle 228 ⇄ 232 physical tables (head `c41f7a9d03e6`), downgrade removes exactly the 4 voice tables | `tests/test_f03_integration.py` | pass |
| Honest not-configured behaviour: with no provider, transcription records the attempt as `not_configured` with empty text; synthesis capability reports `requires_owner_configuration`; status counts only reality | `tests/test_f03_integration.py` | pass |
| Full pipeline over the labelled double: upload → transcribe (fixture provenance, no confidence) → interpret → execute through mission/plan → synthesize (stored response audio, fixture-labelled in the command detail) | `tests/test_f03_integration.py` | pass |
| Manual-entry fallback labelled "not speech recognition", enters the same pipeline | `tests/test_f03_integration.py` | pass |
| Confirmation discipline: consequential command waits `awaiting_confirmation` with plan + plan hash + broker decision; confirm executes; reject confirms nothing; double-confirm refused; plan-drift confirmation refused | `tests/test_f03_integration.py`, `tests/test_f03_security.py` | pass |
| A spoken "yes approve it" confirms nothing (lands in clarification; the pending command is untouched) | `tests/test_f03_integration.py` | pass |
| Stop phrase cancels only the session's own awaiting commands | `tests/test_f03_integration.py` | pass |
| Financial request classifies `financial_operation` and stops at clarification — no plan, no execution, no money | `tests/test_f03_integration.py` | pass |
| Retention/deletion: transcript deletion clears text; audio deletion removes the stored file; session deletion removes every file | `tests/test_f03_integration.py` | pass |
| Intake validation: text/plain upload 415; oversize 413; closed session refuses audio/manual entry; unplannable text → `needs_clarification`, nothing executes | `tests/test_f03_integration.py` | pass |
| HTTP end-to-end over the real API (create → manual → interpret → completed; status honest) | `tests/test_f03_integration.py` | pass |
| Non-owner / agent / service / external principals refused at the service layer; HTTP 403 for a non-owner bearer; per-owner isolation incl. audio content download | `tests/test_f03_security.py` | pass |
| No HTTP route can attach the fixture provider (404); attach is owner-only, audited (`voice.provider_attached`), and refused for non-owner principals | `tests/test_f03_security.py` | pass |
| Audit trail carries the `voice.*` actions with the actor as the owner | `tests/test_f03_security.py` | pass |
| Simulation mode blocks voice-originated execution via the pipeline's own mode gate (`mission_failed`, honestly recorded) | `tests/test_f03_security.py` | pass |

**F03 backend tests: 40 passed / 0 failed** (unit 14,
integration 15, security 11). **F03 frontend tests: 4 passed**
in `frontend/src/views/Voice.test.tsx` (honest capability
states + DEF-A2 line + not-implemented list rendered; transcript
provenance shown as the fallback it is; the interpreted plan is
shown before execution with Confirm/Reject; confirming posts to
the confirm endpoint — the only confirmation path; manual entry
posts typed text as a transcript).

## Full regression on final code

- **Backend: 1057 passed / 0 failed** (1017 pre-F03 baseline +
  40 new). Method: 16 chunks over the C-locale-sorted file list
  (per-file processes from chunk 9 onward after tmpfs basetemp
  accumulation produced `database or disk is full` fixture
  errors — environment failures, diagnosed and re-run green).
  The expected stale exact pins (migration head, table counts,
  metadata count, API version) were advanced with F03
  disclosure comments, strictness preserved. Full detail:
  `REGRESSION_EVIDENCE.txt` in this folder.
- **Frontend: 62 passed / 0 failed** (58 baseline + 4 new) and a
  clean strict build (`tsc --noEmit && vite build`).

## Live smoke (real uvicorn, built Command Center)

`backend/scripts/f03_smoke.py` →
`docs/reports/F03_SMOKE_EVIDENCE.txt`: **28 passed / 0
failed.** Auto-migration to `c41f7a9d03e6` (232 physical
tables); owner login attempt 1 behind the `/health/ready`
gate; status with STT and TTS both honestly
`requires_owner_configuration`; audio upload + hash;
transcription refused honestly (HTTP 422 carrying the state,
attempt recorded with empty text); manual-entry fallback
executes a low-risk command through the plan pipeline with a
broker decision id; a consequential command waits, a spoken
"approve" confirms nothing, on-screen confirmation executes
exactly what was shown; the stop phrase cancels a pending
command; a financial request stops at clarification; the
audit trail carries the voice events; OpenAPI 1.3.0 with
`x-required-permission=approve_actions` on the confirm route;
Command Center served at `/app`; session deletion removes the
stored audio files. A separate uvicorn process cannot attach
the fixture provider — by design there is no HTTP route for
it; the pipeline over a provider is covered in-process by the
integration suite.
