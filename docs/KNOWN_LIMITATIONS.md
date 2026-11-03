# Known Limitations and Risk Register

**Phase:** P-00 · **Updated:** 2026-11-03 (re-audited against the current workspace; P-02 limitations appended below)

## Verified limitations

| ID | Limitation / risk | Severity | Current treatment | Required resolution |
|---|---|---|---|---|
| L-01 | Owner Windows PC is inaccessible; no Windows build/runtime evidence | Critical for P-01 | Linux audit clearly scoped; read-only Windows helper supplied | Run audit and target smoke tests |
| L-02 | No Ollama/model installed; no inference benchmark | High | No local-model performance claim; shared-inference design only. **Confirmed again during P-02 on 2026-11-03:** all six runtimes absent, `ollama.com` and `huggingface.co` unreachable, no GPU, `SwapTotal 0`. P-02 was therefore built deterministic-first (ADR-0017) and every model-dependent acceptance item is reported NOT VERIFIED | Hardware review, approved model and benchmark |
| L-03 | Approximately 3.85 GiB total / 3.60 GiB available sandbox RAM (re-measured 2026-11-03; previously recorded as ~1.94 GiB), 0 KiB swap, 2 logical CPUs, no exposed GPU | High for local AI | Defer heavyweight inference; no model downloads; 0.5-1B Q4 is the only class with genuine headroom | Use a suitable target or smaller approved experiments |
| L-04 | **Resolved in this workspace.** Node v22.22.3 with npm 10.9.8 is installed and satisfies the measured engine floors of vite 8.3.5, vitest 5.1.0 and typescript-eslint 8.72.1 | Closed here | Frontend toolchain is installable on the present Node without the proposed Node 24 upgrade | Owner confirmation that Node 22 (not 24) is the build target |
| L-05 | **Confirmed with exact evidence.** typescript-eslint 8.72.1 peers `typescript >=4.8.4 <6.1.0` while npm `latest` is 7.0.2, so installing both at latest yields an unmet peer dependency | Medium | TypeScript 6.0.x is the highest safe line; must be pinned, never tracked at `latest` | Build/lint/type-check the exact pinned set |
| L-06 | No application, database, agent, wallet or business workflow exists | Expected P-00 limitation | All such capabilities labelled planned | Implement and verify in later phases |
| L-07 | Governance documents are conversation-sourced transcriptions | Medium | Provenance disclosed; owner authorized reuse | Owner review; replace with signed/canonical originals if desired |
| L-08 | Conceptual phase numbers differ from prompt IDs | Medium | Proposed mapping; Constitution unchanged | D-02 approval |
| L-09 | Accounting terms/formulas need reconciliation | Critical before live finance | Cash/accrual distinction and safeguards documented | D-04 approval and P-07 tests |
| L-10 | Security/financial full phases occur later than some dependent capabilities | Critical | Early minimum-control gates proposed; live execution disabled | D-03 approval and phase acceptance tests |
| L-11 | Windows execution sandbox not selected/verified | Critical before untrusted execution | No unrestricted computer control created | D-07 design and adversarial tests |
| L-12 | No independent external audit or owner approval yet | Critical for full P-00 closure | Separate same-assistant review is explicitly not external certification | D-10 review and approval |
| L-13 | **No longer applies.** `origin` is configured and authorized in this workspace; the P-01 tree and the approval-gate fix were pushed and merged as PR #1 on 2026-11-03 | Closed | Delivery now runs through branch + pull request with explicit owner authorization per push | Keep pushes explicitly authorized; never treat a push as implicit |
| L-14 | Business jurisdiction, platform/account eligibility and tax rules unknown | Critical before live business operation | No live operation attempted | D-09 owner input and appropriate professional review |
| L-15 | Package versions are registry observations, not an installed compatibility matrix | Medium | Candidate baseline and evidence recorded | P-01 lockfiles and Windows integration tests |
| L-16 | Local audit tamper evidence cannot defeat a compromised host administrator | Residual security risk | Trust assumptions disclosed | Stronger external trust anchor if required |
| L-17 | Workspace interpreter is Python 3.11.2 while `backend/pyproject.toml` declares `requires-python = ">=3.13"`; the floor is unenforced (`requirements.txt` carries no marker) and unmet | Medium | All 43 tests pass on 3.11.2 and no stack dependency requires 3.13 (highest observed floor `>=3.11`) | Owner decision: lower the floor via ADR, or supply a 3.13 interpreter |
| L-18 | No persisted, reproducible development environment. System site-packages holds none of the stack; the test baseline runs in a `/tmp` venv that did not survive between sessions. No hash-locked lockfile exists | Medium for evidence integrity | `requirements.txt` pins exact versions; venv rebuilt and baseline re-verified this session | Add a hash-locked lockfile or a documented one-command bootstrap |
| L-19 | Outbound network is restricted to `pypi.org`, `registry.npmjs.org` and `api.github.com`. `ollama.com`, `huggingface.co` and general web are blocked | Critical for P-02/P-03/P-05 verification | Recorded, not worked around. No inference, discovery or browser claim is made | P-02 against an approved stub provider; P-03 discovery evidence and P-05 browser verification require an unrestricted host |
| L-20 | `AUTONOMUS_OPERATING_MODE` is still not a `Settings` field and P-01 implements no operating modes. It is now **explicitly labelled inert** in `.env.example`, and `scripts/audit_config_docs.py` tolerates it only while that label is present | Medium | No semantics invented: the four modes P-12 requires are named in no approved document, so wiring them would mean guessing | Owner decision `D-15`: wire it as a real validated mode in P-12, or remove the line |
| L-21 | No `.gitattributes`, and all seven `.ps1` files are LF-only despite the handoff claim that `.ps1` uses CRLF (only `Publish-to-GitHub.cmd` is CRLF). Hash-verified, so faithful to the bundle | Medium for Windows-first | Endings are unpinned, so a future Windows checkout is not deterministic | Add `.gitattributes` and settle endings before any Windows acceptance claim |
| L-22 | **Closed 2026-11-03.** All three `SECURITY_FOUNDATION.md` §11 P-01 gates are addressed: emergency-state foundation implemented and tested (`core/emergency.py`, ADR-0013); verified backup/restore implemented and tested (`database/backup.py`, ADR-0014); secret-store **design** delivered (`SECRET_STORE_DESIGN.md`, ADR-0012) | Closed | 24 new tests, 67 passing in total | Secret-store *implementation* remains a P-05/P-07 obligation against the seven acceptance criteria in the design |

## Product and economic limits

- $50 is illustrative experimental capital, not proof of sufficient runway or a revenue guarantee.
- Creating products, websites or agents does not establish demand, distribution or profitability.
- Customer acquisition, quality, support, fees, refunds and legal eligibility can dominate model costs.
- Market research must declare source coverage and uncertainty; it cannot inspect the entire economy.
- Simulated revenue cannot satisfy the real business acceptance test.
- High-risk financial activities remain separately gated; P-00 authorizes none.

## Preservation and delivery

The original README and MIT license were inspected before edits. The README is archived and the license is unchanged. No application code was replaced because none existed. No packages/models were installed, no financial accounts connected and no remote push performed.

The final completion report distinguishes structural checks from runtime verification and lists the exact remaining gate.

## P-02 limitations (added 2026-11-03)

| ID | Limitation / risk | Severity | Current treatment | Required resolution |
|---|---|---|---|---|
| L-23 | **Local model integration is NOT VERIFIED.** `OllamaProvider` is implemented against the documented HTTP API but has never been exercised against a live server | High | Provider-independent `ModelProvider` protocol, so an adapter can be added or replaced without touching the router; all tests use mocks that exist only in `backend/tests/` | Run the six-step verification in `docs/reports/P02_MODEL_AVAILABILITY_REPORT.md` §6 on a host with a runtime |
| L-24 | **No performance measurement of any kind exists** for inference — no latency, memory or token throughput figure | High for claims | No figure is reported in any P-02 document; §25 forbids inventing measurements and none were invented | Measure on real hardware before any performance claim is made |
| L-25 | Prompt-injection **detection** is pattern-based (four regex banks) and will miss novel phrasings | Medium | Acceptable only because the defence is **structural**: `fence_untrusted` neutralises embedded fence markers and `INVARIANTS`/`SYSTEM_PROMPT` are never interpolated with external values, so protection does not depend on detection succeeding. Detection exists to report, not to protect | Add semantic detection in a later phase; do not rely on the regex banks as the control |
| L-26 | Request interpretation is deterministic and **English-shaped** | Medium | Mis-categorisation errs toward `needs_clarification` and higher risk, never toward execution, so a mis-read request asks a question rather than acting | Multi-language interpretation in a later phase |
| L-27 | **No rate limiting on the intelligence endpoints.** P-01's login rate limit does not cover them | Low (loopback, owner-only) | All fourteen require owner-only permissions and the server binds loopback only | Add per-principal rate limiting if the API is ever exposed beyond loopback |
| L-28 | Mission persistence is **per-request, not transactional** with the in-memory state change | Medium | A crash between a state change and the next persist point loses that change. Making it transactional would require the engine's synchronous transitions to become async, changing the P-01-facing API | Owner decision R-5 |
| L-29 | **Cloud inference routing is implemented and unit-tested but inert** in the running application | Informational | `validate_phase_flags` rejects `cloud_ai_enabled=True`; the P-01 control was **not** weakened. Deleting the code was rejected because it would make the local-first rule untestable | Owner decision R-1 |
| L-30 | §16.3/§16.4 scenarios remain untested: path traversal, malformed-input fuzzing, database-unavailable, shutdown-during-execution | Medium | Carried forward from P-01; P-02 adds no new coverage for them | Dedicated adversarial test pass |
