# Open Decisions and Owner Approval Register

**Date:** 2026-11-03  
**Rule:** Recommendations are not approvals. No item below authorizes implementation, installation, spending or a security change by itself.

## Already authorized for P-00

- Use the Constitution and Prompt Pack supplied in the conversation as repository source documents.
- Continue P-00 with the Windows hardware audit explicitly pending.
- Work in `/home/user/Devil-AI-OS`; preserve the existing README and license.
- Stop after P-00 and request approval before P-01.

## Decisions requiring resolution

| ID | Decision / conflict | Recommendation | Impact if unresolved | Approval status |
|---|---|---|---|---|
| D-01 | Minimum Windows release, architecture and actual target directory | Windows 11 x64 initially; use the existing repo checkout here and let the owner choose the PC checkout path, optionally `C:\AUTONOMUS` | Current Playwright requires Windows 11+; Windows build/hardware readiness cannot be certified | **Pending** |
| D-02 | Constitution conceptual phases 0–11 versus Prompt Pack P-00–P-16 | Treat P-IDs as the canonical execution sequence; map concepts explicitly in the roadmap without renumbering the Constitution | Phase reports and acceptance gates could refer to different work | **Pending** |
| D-03 | Full financial/security phases occur after capabilities that need their protection | Add minimum deterministic policy, audit, approval, budget-reservation and ledger foundations to P-01/P-02; keep live financial execution disabled until P-07 gates pass | Premature external execution would violate the Constitution | **Partially approved for P-01 backend permission/approval foundations; full financial gates pending** |
| D-04 | “Net profit,” collected cash and accrual accounting are not interchangeable; Blueprint and Constitution formulas differ | Preserve constitutional labels; separately define a cash operating result and an accrual profit view; exclude deposits/internal transfers from revenue; define ROI denominator and zero-capital behavior | Misstated profit, double counting or unsafe reinvestment | **Pending** |
| D-05 | Candidate toolchain versions and Node 20 replacement | Node 24 LTS, TypeScript 6.0.3, Python 3.13; resolve exact compatible packages and test on Windows before locking | Latest TypeScript conflicts with current lint peer range; unsupported Node is unsuitable | **Backend dependencies installed conditionally; Windows/frontend lock pending** |
| D-06 | Local model/runtime installation and resource budget | First obtain Windows audit; then approve one small model and a bounded benchmark, not a model collection | No verified local inference capacity or model default | **Pending** |
| D-07 | Strong execution isolation on Windows | Evaluate Windows Sandbox/VM or an appropriately restricted execution environment; a subprocess alone is not a sandbox | Untrusted code/browser automation cannot safely receive broad host access | **Pending design selection** |
| D-08 | Vector database selection | Keep a replaceable retrieval interface; defer Chroma installation until P-09 requirements/benchmarks | Avoidable memory/dependency burden in the core OS | **Pending later gate** |
| D-09 | Business jurisdiction, account eligibility, tax and platform rules | Owner supplies intended operating jurisdiction and authorized accounts before live experiments; obtain appropriate professional review | Legal/platform eligibility cannot be inferred from technical capability | **Pending before live operation** |
| D-10 | Independent completion audit and P-01 authorization | Obtain a separate reviewer/approval after reviewing P-00 evidence and Windows results | Same-assistant checks cannot satisfy independent human certification | **Pending** |

## Non-blocking naming clarification

The product name is **AUTONOMUS**; the existing GitHub repository slug is **Devil-AI-OS**. They may coexist. No repository rename is required. The original README's literal survival/death language is archived, while the Constitution's controlled business-lifecycle model governs future behavior.

## Versioning

Any approved change to locked architecture, authority, financial permissions, platform or provider requirements must receive an ADR and an updated Constitution version. This register does not amend the Constitution.
