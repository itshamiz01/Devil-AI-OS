# Known Limitations and Risk Register

**Phase:** P-00 · **Updated:** 2026-11-03 (re-audited against the current workspace)

## Verified limitations

| ID | Limitation / risk | Severity | Current treatment | Required resolution |
|---|---|---|---|---|
| L-01 | Owner Windows PC is inaccessible; no Windows build/runtime evidence | Critical for P-01 | Linux audit clearly scoped; read-only Windows helper supplied | Run audit and target smoke tests |
| L-02 | No Ollama/model installed; no inference benchmark | High | No local-model performance claim; shared-inference design only | Hardware review, approved model and benchmark |
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
