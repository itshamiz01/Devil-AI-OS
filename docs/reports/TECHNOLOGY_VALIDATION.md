# P-00 Technology Validation Report

**Observed:** 2026-11-03, approximately 05:14–05:18 UTC  
**Status:** Documentary validation complete; target-hardware and integration validation pending  
**Installation status:** No project dependencies installed; no lockfiles created

## 1. Method and evidence

Version observations came from official Python package metadata, npm registry metadata, crates.io metadata, Ollama's official release endpoint and Node's release index. Compatibility and licensing were checked against official documentation or package/license metadata where available. Raw selected observations are in [TECHNOLOGY_EVIDENCE.json](TECHNOLOGY_EVIDENCE.json).

“Latest published” does not mean “approved,” “installed,” “compatible with every other component,” or “tested on the owner's PC.” Versions below are candidates for a P-01 resolution/build gate, not a silently locked stack.

## 2. Backend and persistence

| Component | Observed stable release | Reason and compatibility | Hardware / limitations | License | Alternative | Recommendation |
|---|---|---|---|---|---|---|
| Python | 3.13.17 Windows release listed; sandbox has 3.13.16 | Mature backend ecosystem; retain 3.13 rather than chase the newest minor | Windows version/support and native wheels must be checked; newer Python is not automatically better supported | PSF and bundled-component notices | Newer supported Python after compatibility tests | **Candidate: Python 3.13.17 on Windows**, subject to audit |
| FastAPI | 0.162.0; requires Python ≥3.10 | Typed API boundaries and schema generation | Pre-1.0 versioning: pin and review changes; not a security boundary by itself | MIT | Django/other API frameworks | Retain; validate in P-01 |
| Uvicorn | 0.54.0; Python ≥3.10 | Local ASGI serving | Local production lifecycle/restart behavior still needs design; do not expose unauthenticated LAN access | BSD-3-Clause | Other ASGI servers | Retain as candidate |
| Pydantic | 2.14.2; Python ≥3.10 | Typed boundary validation | Model output validation does not prove truth or authorize actions | MIT | dataclasses plus explicit validators | Retain; pin with FastAPI |
| SQLAlchemy | 2.1.6; Python ≥3.11 | Explicit persistence boundary and PostgreSQL path | Do not allow agents to execute arbitrary SQL; test dialect differences | MIT | Lower-level DB API | Proposed adapter choice; not yet installed |
| Alembic | 1.20.1; Python ≥3.10 | Versioned migrations | Migration/rollback and backup tests required | MIT | Framework-native migrations | Retain as candidate |
| SQLite | Bundled/native library version to be recorded on target | Low-overhead local persistence | WAL is local-host, not a network-file-system/multi-machine database; write serialization remains | Public domain | PostgreSQL earlier if workload demands | Initial system of record, with measured limits |
| PostgreSQL | Supported major to be selected at migration gate | Future concurrency/multi-node path | Separate service, credentials, backup and migration burden | PostgreSQL License | Remain on SQLite until evidence requires migration | **Deferred**, not a P-01 dependency |
| ChromaDB | 1.5.9; metadata says Python ≥3.9 | Preferred vector-memory candidate | Windows/native dependency footprint and small-RAM behavior unverified; not needed for core OS | Apache-2.0, verified from upstream LICENSE | Replaceable vector adapter; another local store after comparison | **Defer selection/installation** until retrieval requirements and benchmark |
| keyring | 25.7.0; Python ≥3.9 | Candidate adapter to OS credential storage | Backend must be verified; Windows Credential Manager/DPAPI behavior depends on account/service design | MIT | Direct approved Windows credential APIs | Candidate only; never a prompt-visible secret store |

Python's official Windows listing includes 3.13.16 and 3.13.17 and explicitly notes that these releases cannot be used on Windows 7 or earlier. [6](https://www.python.org/downloads/windows/) SQLite WAL documentation explains its local-host requirement and concurrency tradeoffs. [5](https://www.sqlite.org/wal.html)

Package sources: [FastAPI](https://pypi.org/project/fastapi/), [Uvicorn](https://pypi.org/project/uvicorn/), [Pydantic](https://pypi.org/project/pydantic/), [SQLAlchemy](https://pypi.org/project/SQLAlchemy/), [Alembic](https://pypi.org/project/Alembic/), [ChromaDB](https://pypi.org/project/chromadb/), [keyring](https://pypi.org/project/keyring/), [SQLite copyright/release information](https://www.sqlite.org/copyright.html), [PostgreSQL licensing](https://www.postgresql.org/about/licence/).

## 3. Frontend and Windows desktop

| Component | Observed stable release | Compatibility finding | Limitations / hardware | License | Alternative | Recommendation |
|---|---|---|---|---|---|---|
| Node.js | 24.22.2 LTS and 26.13.0 LTS published | Node 20 support ended 2026-04-30; Node 24 support ends 2028-04-30 | Current sandbox Node 20.20.2 should not be the new project baseline | MIT and bundled dependency notices | Node 26 LTS after toolchain verification | **Candidate: Node 24.22.2 LTS** for conservative compatibility; owner approval before installation |
| React / React DOM | 19.3.1 | Suitable dashboard UI; align both packages | UI must never hold privileged credentials or directly execute arbitrary tools | MIT | Other web UI frameworks | Retain |
| TypeScript | Latest 7.0.2; compatible-line candidate 6.0.3 | Current typescript-eslint 8.72.1 advertises TypeScript ≥4.8.4 <6.1.0 | Latest TypeScript 7 is outside that peer range; do not assume compatibility | Apache-2.0 | Upgrade lint tooling only after verified support | **Candidate: TypeScript 6.0.3**, with full toolchain smoke test |
| Vite | 8.3.5; Node ^20.19 or ≥22.12 | Compatible with proposed Node 24 | Development server is not the production security model | MIT | Other build systems | Candidate; pin after resolution |
| @vitejs/plugin-react | 6.2.1; peer Vite ^8 | Registry lists additional peer dependencies | Resolve the complete peer graph; do not install only React/Vite and assume success | MIT | Another supported React plugin combination | Candidate integration gate |
| Vitest | 5.1.0; Node ^22.12, ^24 or ≥26 | Node 24 candidate fits; sandbox Node 20 does not | Browser/desktop E2E still needs separate tests | MIT | Another test runner | Candidate |
| Tauri Rust crate | 2.12.5 | Windows-native WebView shell candidate | Requires Rust and native build tooling; core/plugins are privileged | MIT OR Apache-2.0 | Electron; native .NET shell | Retain preference; Windows build gate required |
| Tauri CLI | 2.12.4 | CLI and core crate have separate version streams | Do not force identical patch numbers across differently versioned packages | MIT OR Apache-2.0 | Rust CLI installation | Candidate, verify with core crate |
| Rust | Stable MSVC toolchain; exact target installation pending | Required for Tauri | Rust/Cargo absent in sandbox; MSVC/SDK must be inspected on Windows | MIT OR Apache-2.0 and dependency notices | Not applicable while Tauri retained | Install only after approval |
| WebView2 | Evergreen runtime version pending Windows audit | Required for Tauri on Windows | Runtime presence and update policy must be checked | Microsoft runtime terms | Different desktop shell only via ADR | Verify; do not bundle a runtime blindly |

Tauri's official prerequisites require Microsoft C++ Build Tools and WebView2 on Windows; its security model treats the Rust core and WebView as separate trust domains. Core/plugin code is not automatically sandboxed. [1](https://v2.tauri.app/start/prerequisites/) [7](https://v2.tauri.app/security/)

Node version/support observations: [Node release index](https://nodejs.org/dist/index.json) and [official release schedule](https://github.com/nodejs/Release/blob/main/schedule.json). Frontend package/peer observations: [npm registry](https://registry.npmjs.org/), [typescript-eslint package](https://www.npmjs.com/package/typescript-eslint), [Tauri releases](https://github.com/tauri-apps/tauri/releases).

### Concrete compatibility gate

Before P-01 is accepted, resolve and build the exact React/TypeScript/Vite/plugin/lint/test combination on the supported Node version. The TypeScript peer-range conflict is already identified; a successful install alone is insufficient. Run type-checking, linting, unit tests, production build and a minimal Tauri IPC/startup/shutdown test on Windows.

## 4. AI, automation and testing

| Component | Observed version / status | Reason and compatibility | Limitations | License | Alternative | Recommendation |
|---|---|---|---|---|---|---|
| Ollama | 0.40.13 stable release | Shared local inference, native Windows application | Not installed; Windows 10 22H2+ and GPU-specific drivers per official docs; model memory separate from 4 GB install requirement | MIT, upstream LICENSE | llama.cpp-compatible server through adapter | Retain local default; benchmark before model lock |
| GGUF / llama.cpp interface | Runtime/model to be selected | Replaceable local inference path | Quantization support and model licenses vary | Runtime and model licenses differ | Other local provider adapters | Abstraction required; no model download in P-00 |
| Optional cloud AI | No provider selected | Optional capability/capacity | Explicit privacy, budget, provider allowlist and cost recording; no silent fallback | Provider terms | Remain local/pause | **No cloud dependency approved** |
| Playwright Python | 1.64.1; Python ≥3.10 | Browser automation and E2E tests | Official Windows client requirement is Windows 11+; browser binaries add storage | Apache-2.0 | Dedicated APIs first; other browser tooling via ADR | Retain; Windows 11 target recommendation |
| Windows automation | Library not selected | Fallback for authorized desktop tasks | Screen automation is brittle and high privilege; OS sandbox design required | Library-specific | Official APIs/UI Automation where available | Defer library choice to P-05 threat/design review |
| Pytest | 9.2.0; Python ≥3.10 | Backend tests | Sandbox has 9.0.3; no application tests exist yet | MIT | unittest | Candidate; pin in P-01 |

Ollama Windows requirements: [2](https://docs.ollama.com/windows). Playwright's official system requirements and general-purpose library use: [4](https://playwright.dev/python/docs/intro). Model weights are not covered by the inference runtime's license; each model requires a separate license/provenance check.

## 5. Licensing and distribution obligations

- Existing project license: MIT; unchanged.
- Permissive dependency licenses still require preservation of applicable copyright/license notices in distributions.
- Apache-2.0 components require applicable notice handling; review NOTICE files and attribution during packaging.
- Model licenses may restrict commercial use, redistribution or acceptable use. “Downloadable” is not “approved for business use.”
- WebView2, Windows SDK, build tools, cloud providers, payment services and marketplaces have separate terms.
- Generate a dependency/software bill of materials and license review before release. P-00 is not a legal clearance.

## 6. Final recommendation and unresolved items

Retain the owner's preferred stack. Use a **modular local application**, shared inference, SQLite-first persistence and a thin privileged desktop shell. Do not introduce PostgreSQL, a vector server, cloud AI, browser farms or distributed workers as mandatory P-01 dependencies.

Owner/review decisions still required:

1. Minimum Windows release and target architecture; Windows 11 x64 is recommended.
2. Candidate version baseline, especially Node LTS and TypeScript 6.0.3 rather than latest 7.
3. Actual Windows hardware and permission to install the small P-01 toolchain.
4. Model/runtime download approval after the hardware audit.
5. Vector store and Windows automation library after their specific phase benchmarks.
6. Independent review of the proposed version/compatibility baseline.

**No technology replacement or version lock is represented as approved by this report.** See [ADR-0007](../decisions/ADR-0007-CANDIDATE-TOOLCHAIN.md).
