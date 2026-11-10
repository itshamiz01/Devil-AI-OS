# AUTONOMUS P-02 TEST REPORT

**Test status: Passed — 111/111** (P-01 regression 76/76 + P-02 new 35/35), run on Linux in the staging venv, one full-suite run: `111 passed in 18.32s`. No assertion was weakened; three implementation defects found by the tests were fixed in code (see P02_IMPLEMENTATION_REPORT §2).

## New tests (35) — backend/tests/test_p02_*.py

**Unit (17) — test_p02_unit.py**
Plan schema rejects empty tool name · parse_proposal rejects non-dict / bad shape / empty steps, accepts valid shape · baseline decomposition of the health-check template (exact tools + expectations) · wait-and-report template parses "2 seconds" → `{"milliseconds": 2000}` with `waited_ms` expectation · echo template + no-match returns None · validator rejects unregistered tool (`os.system`), invalid payload (missing `message`), and permission-denied principal (EXTERNAL) — and accepts the baseline health plan for the owner · verifier matrix: verified / value-mismatch failed / ok=false failed / task-failed failed / absent-field **unverified** / kind=none **unverified** / dotted-path verified · router matrix: no profiles → baseline · fake profile available → LLM selected · **cloud stub never selected** · unavailable provider → baseline · resource pressure (monitor violations) → headroom profile deferred to baseline · decision recorder + context isolation (mission 2's context contains none of mission 1's records) · Ollama probe against a dead port → honestly unavailable · seeded profiles: 4, all `model_id=""`, all disabled.

**Integration (10) — test_p02_integration.py**
Acceptance scenario (supervised, HTTP): mission "Check system health and report whether the task system is working" → plan (rule-engine) → approve → execute → plan completed, both steps completed as real P-01 tasks, both **verified** → GET plan shows decision records incl. router_selection → GET explanation: `llm_used=false`, "No LLM was used…" honesty statement, verified steps · same scenario with FakeProvider returning a valid plan → planner `llm:fake:fake-1`, `llm_used=true` · FakeProvider plan naming `os.system` → HTTP 422, plan persisted `rejected`, `plan_rejected` decision recorded, **zero tasks created** · garbage LLM output (`{"nonsense": true}`) → `llm_plan_unusable` recorded + baseline fallback plan · provider timeout (fake delay 1.0s vs 0.2s budget) → same fallback · unplannable mission → 422, mission `planning_failed`, `plan_failed` recorded · models/status + profiles endpoints (ollama unavailable, cloud not enabled, seeded profiles empty) · migration test: fresh DB via auto-migrate → 5 new tables present, alembic_version = `c7a21f9e04b3`.

**Security / Article 0 (8) — test_p02_security.py**
Detailed in P02_SECURITY_REPORT: injection mission creates nothing and is recorded + audited · non-owner profile edit → 403 + audited deny (HTTP) and service-level denial recorded with the profile provably unchanged · plan tampered after approval → 409, `plan_tampered` recorded, zero tasks · simulation mode → approve allowed, execute 409 with `execution_blocked_mode` record · emergency mode → execute 409 with record · unapproved plan → 409 with `execution_blocked_unapproved` record · failing step (test-registered exploding handler via FakeProvider plan) → plan failed, later step never submitted (no task_id), `plan_failed` recorded.

## Regression

Full suite command: `.venv/bin/python -m pytest tests/ -q` → **111 passed**. The P-01 suite (76) is untouched and green; P-02's application wiring (router registration, service construction at startup, profile seeding) is exercised by every P-01 API test's lifespan as well.

## Live smoke (not a test — real server evidence)

uvicorn + curl acceptance run in supervised mode on a fresh auto-migrated DB: all 7 calls succeeded; executed plan completed with both steps verified; explanation and models/status honest. Transcript: `docs/reports/P02_SMOKE_EVIDENCE.txt`.

## Not covered (honest gaps)

No real Ollama server exists in this environment, so the adapter's success path (a real model returning a real plan) is **untested against a live model** — only its unavailable path is probe-tested, and the planning pipeline's LLM branch is verified with FakeProvider. Windows execution of everything above is unverified (carried item). Load/concurrency behaviour of synchronous plan execution is untested by design (P-05 scope).
