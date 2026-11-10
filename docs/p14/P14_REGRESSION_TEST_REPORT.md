# P-14 REGRESSION TEST REPORT — Stage A (Audit Only)

**Rule (§16):** nothing unexecuted is marked passed. Where a run was
poisoned by the environment, that is stated, the affected tests were
re-run clean, and both results are shown.

## 1. Headline results

| Suite | Collected | Passed | Failed | Errors | Xfailed | Verdict |
|---|---|---|---|---|---|---|
| Backend full suite, run 1 (one run, tmpfs basetemp + pruner) | 775 | 717 | 4 | 53 | 1 | **Environment-poisoned** — see §2 |
| Backend re-run of exactly the 57 affected tests (clean /tmp) | 57 | **57** | 0 | 0 | 0 | PASS |
| **Backend effective result** | **775** | **774** | **0** | **0** | **1** | **PASS** |
| Frontend suite (vitest, one run) | 40 | **40** | 0 | 0 | 0 | PASS |
| Frontend production build (`tsc --noEmit && vite build`) | — | clean | — | — | — | PASS (362 kB JS / 104 kB gzip) |

775 backend tests = **713 pre-existing** (P-01–P-13 baseline) +
**62 new P-14 audit tests**. All 713 pre-existing tests pass. Of the
62 new tests: 61 pass and 1 is xfailed by design (it evidences a
real defect, P14-DEF-F1).

## 2. The run-1 incident — disclosed in full

Run 1 (515 s) ended `4 failed, 717 passed, 1 xfailed, 53 errors`.
Every one of the 57 failures/errors carries the same root cause,
visible in the tracebacks: `sqlite3.OperationalError: database or
disk is full` during fixture setup (`Base.metadata.create_all`).
The audit's basetemp directory grew to 383 MB on this VM's 512 MB
tmpfs and the disk filled mid-run despite the pruner — the exact
failure mode recorded in this project's operational lessons since
ClipOS Phase 2. These were **not code failures**: the identical 57
tests, re-run immediately afterwards on a clean /tmp, passed 57/57
(including both migration-cycle tests and the P-05 symlink-escape
test). The full run-1 log is preserved as evidence in
`docs/p14/P14_FULL_RUN_LOG.txt`. The audit reports the effective
result as 774 passed + 1 xfailed **with this disclosure attached**;
it does not present run 1 as green.

## 3. New P-14 audit tests (62) — per file

| File | Tests | Result | Coverage |
|---|---|---|---|
| `tests/test_p14_audit.py` (coordinator) | 10 | 10 passed | §3 assembly (all 17 module services wired), full route surface (464 OpenAPI paths, per-module prefixes), 171-table metadata, health endpoints, honest dashboard zero-state, critical-event persistence, correlation-ID propagation, safe restart without duplicate seeds, backup create+verify, API latency measurement |
| `tests/test_p14_security.py` | 23 | 23 passed | §9 independent re-probes: authentication (5), approval replay/drift/self-approval (2), prompt injection + memory poisoning + secret-shape matrix (4), cross-business leakage (2), execution boundaries incl. symlink escapes (4), financial safety (2), credentials/audit-chain tamper-deletion/egress/log redaction (4). **Zero defects found at P0–P2**; two P3 observations (DEF-S1, DEF-S2) |
| `tests/test_p14_financial.py` | 13 | 12 passed, **1 xfailed** | §10 simulations (profitable, loss-making, new, liability-carrying, zero-revenue, multi-currency, interrupted transaction) + 8 invariants. The xfail **is** defect P14-DEF-F1 (portfolio gross collected = 0) |
| `tests/test_p14_orchestration.py` | 10 | 10 passed | §8 failure scenarios: provider unavailable → baseline fallback; unavailable + no template → honest `planning_failed`, no fabricated plan; garbage model output rejected + fallback; impermissible tool refused with **no** fallback; handler failure → workflow FAILED + dead-letter, never verified; unauthorized tool/handler rejected at validation; interrupted workflow → RECOVERY_PENDING, resume executes exactly once; duplicate submission idempotent; verification gate (completion ≠ success); exactly one learning record for verified outcome, zero for failed |
| `tests/test_p14_e2e.py` | 6 | 6 passed | §11 scenarios 1–6 (verdicts in §4) |

**Probe-writing errors (transparency):** four coordinator probes
initially failed on the *probe's* wrong assumptions — readiness
envelope key (`status`, not `ready`), diagnostics key
(`database_healthy`), this FastAPI version's opaque included routers
(surface check moved to the OpenAPI schema), and guessed route
prefixes (`/intelligence` does not exist; P-02 uses `/missions`,
`/plans`, `/models`). Each was corrected against the code and the
system behaved correctly in every case. None is a system defect;
all four are recorded here so the audit trail shows them.

## 4. §11 end-to-end scenario verdicts

| Scenario | Verdict | Notes |
|---|---|---|
| 1 Opportunity → business creation | **PARTIALLY EXECUTED** | Real-evidence path asserted honestly BLOCKED (Level < 3, zero businesses created); fixture path executed the full 12-step chain through real interfaces (P-06→P-03 eligibility, hash-bound approval, P-07 profile, P-08 snapshot, P-10 broker checks, P-13 registration, P-04 assignments, P-12 workflow, P-05 execution, P-11 dashboard via service **and** HTTP). Gaps E1 (no P-02←P-03 interface) and E4 (no auto-registration) recorded |
| 2 Autonomous task execution | **PARTIALLY EXECUTED** | Real chain for mission→plan→approve→execute→verify and for P-12 workflow by a real P-04 agent; learning record exactly 1 for verified, 0 for failed-verification control. Gap E2: P-02 planning does not retrieve P-09 memory (retrieval step is choreography) |
| 3 Business financial distress | **FULLY EXECUTED** | −₹5,000 net → P-08 loss_making gate, scaling BLOCKED → P-13 reflects → RECOVER decision refused before approval, executed after owner hash-bound approval, replay idempotent |
| 4 Multi-business collaboration | **FULLY EXECUTED** | Shared-service allocation labelled INTERNAL_ALLOCATION, P-07 consolidated byte-identical; cross-business workflow refused until both businesses authorized; participation created zero cross-access (denial audited) |
| 5 Infrastructure failure | **FULLY EXECUTED** | Provider killed at the adapter seam mid-chain: status reports both providers down, router records baseline fallback, unplannable mission honestly `planning_failed`, prior state preserved, dashboard shows `ai_provider: unavailable` |
| 6 Security incident | **FULLY EXECUTED** | Four agent attempts (portfolio cross-read, broker cross-read, protected-file read, policy change) all blocked + audited; critical alert raised; incident on the dashboard security surface via service and HTTP; critical notification non-dismissible (HTTP 422) |

Detail: `docs/p14/P14_E2E_EVIDENCE_NOTES.md`.

## 5. §10 financial simulations — summary

Profitable (+₹7,000), loss-making (−₹3,000, `is_loss`),
new business (honest `INSUFFICIENT_DATA`, `net_profit=None`),
liabilities (₹6,000 payables → available −₹1,000, balanced sheet),
zero-revenue portfolio (no invented cash,
`combined_available_cash=None`), multi-currency (**supported** —
12 seeded currencies; per-currency totals never summed; conversion
only via P-07 with an owner-recorded rate), interrupted posting (0
partial entries; idempotent retry posts exactly once). Invariants:
7 of 8 HOLDS outright; the traceability invariant holds for P-07
while its P-13 presentation is defect F1. Full detail:
P14_FINANCIAL_INTEGRITY_REPORT.md.

## 6. NOT EXECUTED — stated plainly

| Item | Why |
|---|---|
| Windows test execution (all suites) | No Windows machine exists in this environment (DEF-A1) |
| Real LLM behaviour (any test) | No real provider exists in the system (DEF-A2) |
| Live Stripe / real money movement | Interface-only by design; fixtures-only rule (§21.11) |
| Rendered-viewport / headless-browser checks | No headless browser in staging (carried from P-11) |
| Threaded concurrent-webhook race | Sequential duplicate idempotency re-verified instead; the threaded race remains covered by P-07's own Scenario 11 |
| Portfolio-level FX conversion | No such mechanism exists (conversion is P-07-only, and was tested there) |
| Load/volume testing | Not performed in Stage A (DEF-A7) |
| Dependency vulnerability scan | No scanner exists in the environment (DEF-C4) — never claimed |

## 7. Baseline comparison (§16 requirement 5)

Previous baseline (P-13 gate): backend 713/713, frontend 40/40.
This audit: backend **774 passed + 1 xfailed of 775** (baseline
fully preserved; the +62 are the audit's own probes), frontend
**40/40**, build clean. No pre-existing test was modified by P-14.
