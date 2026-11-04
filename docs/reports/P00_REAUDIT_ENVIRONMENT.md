# P-00 Environment Audit — Current Workspace Re-Audit

**Audit date:** 2026-11-03 (re-audit)
**Supersedes for this workspace:** [ENVIRONMENT_AUDIT.md](ENVIRONMENT_AUDIT.md) and [ENVIRONMENT_EVIDENCE.json](ENVIRONMENT_EVIDENCE.json), captured 2026-11-03T05:16Z against a *different* sandbox
**Scope:** The Arena Linux workspace actually in use now. Still **not** the owner's Windows PC.
**Result:** Workspace re-measured. Toolchain and memory envelope have materially changed since the original P-00 audit. Windows target remains **NOT VERIFIED**.
**Evidence:** [P00_REAUDIT_ENVIRONMENT_EVIDENCE.json](P00_REAUDIT_ENVIRONMENT_EVIDENCE.json), produced by `scripts/audit_environment.py` (read-only; installs nothing, downloads nothing, reads no credentials)
**Verification baseline:** `43 passed, 1 warning` on the merged tree

## 1. Why this re-audit exists

The original P-00 evidence describes a sandbox that no longer matches this one.
Six of its recorded facts are now wrong, and two of them change phase decisions.
P-00 requires inspecting the actual development machine, so the numbers were
re-measured rather than inherited.

| Item | Recorded 05:16Z | Measured now | Effect |
|---|---|---|---|
| Python | 3.13.16 | **3.11.2** | **Regression** — below `backend/pyproject.toml` `requires-python = ">=3.13"` |
| Node.js | v20.20.2 (past support end 2026-04-30) | **v22.22.3** (LTS line) | **Improved** — largely resolves `L-04`; `D-05` proposed Node 24 |
| npm | 10.8.2 | 10.9.8 | Neutral |
| Git | 2.47.3 | 2.39.5 | Older, functional |
| MemTotal | 2,030,404 KiB (~1.94 GiB) | **4,034,452 KiB (~3.85 GiB)** | **Improved ~2x** — invalidates `L-03` as written |
| MemAvailable | ~1.46 GiB | **~3.60 GiB** | **Improved ~2.5x** |
| Swap | 0 KiB | 0 KiB | Unchanged — no cushion |
| Free storage | 20.04 GiB | 19.27 GiB | Marginally less |
| CPU model | "Not established" | **Intel(R) Xeon(R) @ 2.60 GHz** | Newly established |
| CPU SIMD flags | not captured | **aes, avx, avx2, fma all present** | Newly established — matters for CPU inference |
| GPU | none exposed | none exposed | Unchanged |
| Git remote | "no configured remote" | **`origin` configured; push and PR merge verified** | Changed — see §5 |

Unchanged absences: `ollama`, `cargo`, `rustc`, `pwsh`/`powershell`, `playwright`,
`docker`, `pnpm`, `nvidia-smi`.

## 2. Operating environment

| Item | Observed | Interpretation |
|---|---|---|
| OS | Linux, kernel `6.1.158+` | Not the Windows production target |
| Architecture | x86_64 | Same family as a Windows x64 target; does not validate a Windows build |
| Interpreter | CPython 3.11.2 | **Below the project's declared floor** |
| Logical CPUs | 2 visible, affinity 2 | Hard ceiling on bounded concurrency |
| CPU model | Intel(R) Xeon(R) Processor @ 2.60GHz | Virtualized; host topology not established |
| ISA features | aes, avx, avx2, fma present | SIMD-capable; relevant to `llama.cpp`-class CPU inference |
| Total memory | 4,034,452 KiB (~3.85 GiB) | Small envelope, doubled since the original audit |
| Available memory | ~3.60 GiB at capture | Point-in-time, not a guarantee |
| Swap | 0 KiB | Exhaustion is fatal, not slow |
| Storage | 20.34 GiB total / 19.27 GiB free at the repo | Filesystem view, not a physical disk spec |
| Storage medium | Not established | Do not assume SSD/NVMe |
| GPU | No `/dev/nvidia*` or `/dev/dri/*` | Does not prove the physical host has no GPU |
| cgroup limits | No limit files exposed | Do not infer unlimited resources |

## 3. Windows directory check (P-00 §7)

`C:\AUTONOMUS` is a Windows path and cannot be inspected from this Linux
workspace. `C:\AUTONOMUS`, `/mnt/c/AUTONOMUS` and `/c/AUTONOMUS` are all
absent here. As in the original audit, this does **not** establish whether the
directory exists on the owner's PC — it is *unknown*, not failed.

The active workspace is `/home/user/Devil-AI-OS`, the existing repository
checkout, consistent with `D-01`'s recommendation. No unrelated directory was
created or modified, and nothing was deleted.

## 4. Tool and dependency inventory

Present: `python3` 3.11.2, `node` v22.22.3, `npm` 10.9.8, `npx` 10.9.8,
`yarn` 1.22.22, `git` 2.39.5, `lscpu`.

Absent: `pnpm`, `pwsh`, `powershell`, `cargo`, `rustc`, `ollama`, `docker`,
`playwright`, `nvidia-smi`.

**The system interpreter has none of the application stack.** `fastapi`,
`uvicorn`, `pydantic`, `pydantic-settings`, `sqlalchemy`, `alembic`, `aiosqlite`,
`psutil`, `argon2-cffi`, `httpx`, `pytest`, `playwright`, `chromadb`, `keyring`
and `ollama` are all absent from system site-packages. The 43-test baseline was
produced inside a virtual environment created under `/tmp`, which **did not
survive between sessions and had to be rebuilt**.

Consequences:

1. There is **no persisted, reproducible development environment**. `requirements.txt`
   pins exact versions, which is good, but there is no hash-locked lockfile and no
   committed environment, so every session rebuilds from the network.
2. Environment setup is **network-dependent**. If the registry allowlist narrows,
   the test baseline cannot be reproduced at all.
3. This is a P-00 "development and testing environments" gap, recorded as a new
   limitation rather than papered over.

## 5. Network posture — newly measured, materially restrictive

Outbound access was probed (status codes only, no bodies, fixed host list):

| Host | Result | Consequence |
|---|---|---|
| `pypi.org` | reachable | Python dependencies installable |
| `registry.npmjs.org` | reachable | Frontend dependencies installable |
| `api.github.com` | reachable | Git/PR delivery works |
| `ollama.com` | **blocked** | Ollama cannot be installed from here |
| `huggingface.co` | **blocked** | GGUF models cannot be downloaded |
| `google.com` | **blocked** | No general web access |

This is the single most important new finding for roadmap sequencing, because it
decides what can be *verified* here versus only *implemented*:

- **P-02 Master Intelligence** — the provider-independent interface, router,
  availability detection and task profiles can be built and tested against a
  deterministic stub provider. **Real local inference cannot be demonstrated**,
  because no runtime is installed and none can be fetched.
- **P-03 Opportunity Discovery** — its acceptance criterion is "discover real
  opportunities, preserve source evidence". With general internet blocked, that
  criterion **cannot be satisfied from this workspace**. Scanner, connectors,
  scoring, dedup and provenance can be implemented and fixture-tested; discovered
  opportunities must not be claimed. Constitution §8 forbids claiming to have
  searched sources that were not inspected.
- **P-05 Digital Execution** — Playwright is absent and browser downloads are
  blocked, so browser automation cannot be verified here.
- **Desktop shell** — no `cargo`/`rustc`, so Tauri cannot be built or tested here.

## 6. Compatibility findings

1. **Python floor not met.** `requires-python = ">=3.13"` while the workspace has
   3.11.2. The pinned dependencies do install and all 43 tests pass on 3.11, so
   the code is *compatible* with 3.11 in practice, but the declared floor is
   unenforced (`requirements.txt` carries no marker) and unmet. Either lower the
   floor to what is verified or restore a 3.13 interpreter. **Owner decision.**
2. **Frontend tooling is now viable.** Node 22.22.3 with npm 10.9.8 and yarn is
   present, so the React/TypeScript remainder of P-01 can be built and tested in
   this workspace. `D-05` proposed Node 24 LTS; building on 22 needs an explicit
   decision so the recorded choice and the actual toolchain do not diverge.
3. **Desktop build blocked.** Tauri's Windows prerequisites include MSVC C++ Build
   Tools and WebView2; neither Rust nor Windows is available here.
4. **Browser automation blocked.** Current Playwright documentation lists Windows
   11+ as a supported Windows client target, and the package is not installed here.
5. **Local AI blocked by network, not only by hardware.** Even with ~3.6 GiB
   available and AVX2 present, no runtime or model can be obtained. See
   [P00_REAUDIT_AI_FEASIBILITY.md](P00_REAUDIT_AI_FEASIBILITY.md).
6. **Financial integrations intentionally absent.** No account, wallet, payment
   processor or trading service was contacted. `AUTONOMUS_FINANCIAL_EXECUTION_ENABLED`
   and `AUTONOMUS_EXTERNAL_EXECUTION_ENABLED` are rejected at startup if enabled.

## 7. Recommended setup actions — approval required before any installation

1. Decide the Python floor: restore 3.13 in the workspace, or amend
   `requires-python` to `>=3.11` with evidence and an ADR.
2. Decide the Node target: build the P-01 frontend on the available Node 22, or
   hold for Node 24 per `D-05`.
3. Add a reproducible environment artifact (hash-locked lockfile or a documented
   one-command bootstrap) so the 43-test baseline survives session boundaries.
4. Run `scripts/audit_windows.ps1` on the intended PC and review the report for
   private information before sharing it.
5. Confirm the minimum supported Windows release (`D-01`); Windows 11 x64 remains
   the recommendation, not an owner-locked minimum.
6. Defer Ollama and model selection until a host with model-download access and
   measured capacity is available (`D-06`).
7. Keep models, runtime databases, browser profiles and credentials outside Git
   (already enforced by `.gitignore`, verified by
   `scripts/audit_p00_deliverables.py`).

## 8. Readiness decision

**Workspace readiness for documentation, backend work and frontend work: READY.**

**Windows environment readiness: NOT READY / PENDING** — unchanged from the
original audit and not closable from this machine.

**Local AI feasibility here: NOT VERIFIABLE** — no runtime, no model, and the
download hosts are blocked.

This workspace is adequate for P-00 documentation, backend implementation and
testing, and (newly) for frontend implementation and testing. It is not evidence
of readiness for a Windows application, local model workload, real opportunity
discovery, production operation or financial execution. **No P-01 or later
implementation work was performed during this re-audit.**
