# P-00 Technology Validation — Current Re-Audit

**Date:** 2026-11-03 (re-audit)
**Complements:** [TECHNOLOGY_VALIDATION.md](TECHNOLOGY_VALIDATION.md) and [TECHNOLOGY_EVIDENCE.json](TECHNOLOGY_EVIDENCE.json) (registry observations captured 05:14–05:18Z)
**Method:** Live registry metadata re-queried through `scripts/audit_technology.py` (read-only; nothing installed, resolved or built)
**Evidence:** [P00_REAUDIT_TECHNOLOGY_EVIDENCE.json](P00_REAUDIT_TECHNOLOGY_EVIDENCE.json) — 16/16 PyPI and 8/8 npm components resolved
**Scope:** Registry metadata plus the actual workspace toolchain. **Not** target-hardware verified, **not** Windows verified.

## 1. Headline changes since the original validation

Three recorded conclusions change on fresh evidence. Two improve, one is confirmed
and sharpened.

| ID | Recorded position | Re-audit result |
|---|---|---|
| `L-04` | Node 20 past its support end date; upgrade required before frontend work | **Resolved here.** Node **v22.22.3** is installed and satisfies every frontend engine floor measured below. Frontend work is no longer blocked on a Node upgrade in this workspace |
| `L-05` | TypeScript 7 conflicts with the `typescript-eslint` peer range; 6.0.3 proposed | **Confirmed and sharpened.** `typescript-eslint@8.72.1` peer-requires `typescript >=4.8.4 <6.1.0`; npm `latest` for TypeScript is **7.0.2**. Installing both at `latest` yields an unmet peer dependency. The `<6.1.0` ceiling makes **6.0.x the highest safe line**, so `D-05`'s 6.0.3 candidate is correct and must be pinned, not tracked at `latest` |
| `D-05` | Python 3.13 as the target interpreter | **Needs an owner decision.** The workspace has **3.11.2**, and **no dependency in the stack requires 3.13** — the highest floor observed is `>=3.11` |

## 2. Backend stack — measured interpreter floors

All sixteen PyPI components resolved. The decisive observation is in the final
column: `backend/pyproject.toml` declares `requires-python = ">=3.13"`, but
**nothing in the stack needs 3.13**.

| Package | Latest | `requires_python` | License |
|---|---|---|---|
| fastapi | 0.162.0 | `>=3.10` | MIT |
| uvicorn | 0.54.0 | `>=3.10` | BSD-3-Clause |
| pydantic | 2.14.2 | `>=3.10` | MIT |
| pydantic-settings | 2.16.2 | `>=3.11` | MIT |
| sqlalchemy | 2.1.6 | `>=3.11` | MIT |
| alembic | 1.20.1 | `>=3.10` | MIT |
| aiosqlite | 0.22.1 | `>=3.9` | not declared in metadata |
| greenlet | 3.5.6 | `>=3.10` | MIT AND PSF-2.0 |
| psutil | 7.2.2 | `>=3.6` | BSD-3-Clause |
| argon2-cffi | 25.1.0 | `>=3.8` | MIT |
| httpx | 0.28.1 | `>=3.8` | BSD-3-Clause |
| pytest | 9.2.0 | `>=3.10` | MIT |
| playwright | 1.64.1 | `>=3.10` | Apache-2.0 |
| chromadb | 1.5.9 | `>=3.9` | not declared in metadata (upstream Apache-2.0) |
| keyring | 25.7.0 | `>=3.9` | MIT |
| ollama | 0.6.3 | `>=3.8` | MIT |

**Empirical confirmation:** the pinned set in `backend/requirements.txt` installs
cleanly on Python 3.11.2 and the full suite passes there — `43 passed, 1 warning`.
So the code is *demonstrably* 3.11-compatible, and the declared floor is stricter
than any dependency requires.

Two pins trail `latest` by design: `pydantic` is pinned 2.14.1 (latest 2.14.2) and
`pytest` 9.0.3 (latest 9.2.0). Exact pinning is intentional and consistent with
§12.1's dependency-documentation requirement; it is not an error, but it does mean
upgrades are a deliberate act.

### Decision required — the Python floor

`requires-python = ">=3.13"` is currently **unenforced and unmet**:
`requirements.txt` carries no interpreter marker, so a 3.11 user gets no warning
and the suite quietly passes. Pick one:

- **(a) Lower the floor to `>=3.11`**, matching verified reality, with an ADR; or
- **(b) Keep `>=3.13`** and provide a 3.13 interpreter in the workspace, accepting
  that the current 43-test baseline was produced on an unsupported interpreter.

Recommendation: **(a)**, because it is the only option backed by execution evidence
today. This is an owner decision, not a silent amendment — Constitution §18
requires an ADR for a change touching platform support.

## 3. Frontend and desktop — measured engine floors

Node **v22.22.3**, npm **10.9.8** and yarn **1.22.22** are installed. Every
frontend engine floor is satisfied by 22.22.3:

| Package | Latest | `engines.node` | Node 22.22.3 | License |
|---|---|---|---|---|
| react | 19.3.1 | `>=0.10.0` | ✅ | MIT |
| react-dom | 19.3.1 | — | ✅ | MIT |
| vite | 8.3.5 | `^20.19.0 \|\| >=22.12.0` | ✅ | MIT |
| vitest | 5.1.0 | `^22.12.0 \|\| ^24.0.0 \|\| >=26.0.0` | ✅ | MIT |
| typescript-eslint | 8.72.1 | `^18.18.0 \|\| ^20.9.0 \|\| >=21.1.0` | ✅ | MIT |
| typescript | **7.0.2** | `>=16.20.0` | ✅ engine, ❌ **peer** | Apache-2.0 |
| @tauri-apps/cli | 2.12.4 | `>= 10` | ✅ | Apache-2.0 OR MIT |
| @tauri-apps/api | 2.12.4 | — | ✅ | Apache-2.0 OR MIT |

**A consistent, installable frontend set exists today** on the installed Node:
react 19.3.1 + vite 8.3.5 + vitest 5.1.0 + typescript-eslint 8.72.1 +
**typescript pinned to 6.0.x** (not `latest`). Cross-checks that make this set
coherent rather than merely individually installable:

- `vitest@5.1.0` peers `vite ^6.4.0 || ^7.0.0 || ^8.0.0` → vite 8.3.5 ✅
- `vitest@5.1.0` peers `@types/node ^22.0.0 || >=24.0.0` → `@types/node` 22.x ✅
- `vite@8.3.5` peers `@types/node ^20.19.0 || >=22.12.0` → same ✅
- `typescript-eslint@8.72.1` peers `eslint ^8.57.0 || ^9.0.0 || ^10.0.0` and
  `typescript >=4.8.4 <6.1.0` → eslint 9/10 + TS 6.0.x ✅

This resolves the practical blocker behind `L-04`/`L-05` **without** needing the
Node 24 upgrade that `D-05` proposed. Node 24 remains a fine future target, but it
is no longer a prerequisite for starting the P-01 frontend.

**Desktop shell: still not validatable here.** `@tauri-apps/cli` 2.12.4 is
installable, but a Tauri build needs a Rust toolchain (`cargo`/`rustc` absent),
MSVC C++ Build Tools and WebView2 on Windows. None is present. Tauri remains the
preferred candidate; nothing about it is verified.

## 4. AI, automation and memory components

| Component | Position after re-audit |
|---|---|
| Ollama server | **Cannot be installed** — `ollama.com` blocked. Not a version problem |
| `ollama` Python client 0.6.3 | Installable (MIT, `>=3.8`). Enables **stub-provider** development of the P-02 model router without a real model |
| GGUF models | **Cannot be downloaded** — `huggingface.co` blocked |
| Playwright 1.64.1 | Package installable from PyPI (Apache-2.0), but browser binaries come from a CDN outside the allowlist and the package is not installed. **P-05 browser automation is not verifiable here** |
| ChromaDB 1.5.9 | Installable, but metadata declares no license expression (upstream Apache-2.0). Deferral under ADR-0008 stands; confirm licensing before adoption |
| keyring 25.7.0 | Installable (MIT). The natural candidate for the OS secret store that `SECURITY_FOUNDATION.md` §11 assigns to P-01 but which does not exist yet |

## 5. Licensing

No new obligation appeared. The stack remains permissive: MIT, BSD-3-Clause,
Apache-2.0, and `Apache-2.0 OR MIT` for Tauri. Two items need attention before any
distribution or commercial use, and are **not** cleared by this audit:

1. `aiosqlite` and `chromadb` publish no `license_expression` in registry
   metadata; confirm upstream licenses before bundling.
2. Model weights carry their own licenses, entirely separate from code licenses.
   No model was downloaded, so no model license has been reviewed.

## 6. Reproducibility gap (new finding)

The workspace has **no persisted development environment**. System site-packages
contains none of the stack; the 43-test baseline was produced in a `/tmp` virtual
environment that **did not survive between sessions and had to be rebuilt**.
`requirements.txt` pins exact versions but there is no hash-locked lockfile and no
one-command bootstrap.

This is a genuine P-00 "development and testing environments" gap: the evidence
baseline is reproducible only while registry access and `/tmp` persist. Recorded
as a new limitation with a recommended remedy (hash-locked lockfile or a
documented bootstrap script), not worked around silently.

## 7. Final recommendation

| Layer | Recommendation | Confidence |
|---|---|---|
| Backend | Keep Python + FastAPI + SQLAlchemy 2.x + Alembic + Pytest exactly as pinned | High — 43 tests pass on the installed interpreter |
| Python floor | Lower `requires-python` to `>=3.11` via ADR, **or** supply 3.13. Owner decision | High — no dependency needs 3.13 |
| Frontend | Proceed on the installed Node 22.22.3 with react 19.3.1, vite 8.3.5, vitest 5.1.0, typescript-eslint 8.72.1, **typescript pinned 6.0.x**, eslint 9/10 | High on metadata; **not yet build-verified** — no frontend exists |
| Desktop | Keep Tauri 2.12.4 as candidate; do not attempt a build until Rust + MSVC + WebView2 are confirmed on Windows | Low — unverifiable here |
| Local AI | Keep Ollama/GGUF as the locked default, but plan P-02 against a **stub provider**; no model decision until the Windows hardware audit | Blocked here by network, not by version |
| Vector memory | Keep deferred (ADR-0008) | Unchanged |
| Secrets | Adopt `keyring` as the candidate OS secret store when the P-01 §11 gap is scheduled | Metadata only; not evaluated at runtime |
| Environment | Add a hash-locked lockfile or bootstrap script | New requirement |

## 8. Unresolved decisions carried forward

- **`D-05`** — interpreter and Node targets. Evidence now supports Python `>=3.11`
  and Node 22 for the frontend; the recorded Node 24 proposal is no longer a
  prerequisite. Needs an explicit owner update.
- **`D-01`** — minimum Windows release and the PC checkout path. Unchanged,
  still blocking Windows acceptance.
- **`D-06`** — model selection and resource budget. Unchanged; blocked here by
  network as well as hardware.
- **`D-07`** — Windows execution isolation. Unchanged.
- **New** — reproducible environment artifact (lockfile or bootstrap).
- **New** — whether P-02 may be built and tested against a stub model provider,
  with real inference explicitly marked unverified.

No recommendation in this document is an approval. Nothing was installed,
upgraded, replaced or downloaded beyond registry metadata.
