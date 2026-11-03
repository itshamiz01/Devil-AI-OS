# AUTONOMUS AI OS

- **Repository:** `itshamiz01/Devil-AI-OS`
- **Current phase:** P-01 — conditional backend-only implementation, partially complete
- **Application status:** Core backend working in the Linux sandbox; Windows/desktop/frontend not certified
- **P-02 status:** Not started and not authorized

## Mission

AUTONOMUS is a Windows-first autonomous AI Business Operating System concept. Its long-term purpose is to discover legitimate opportunities, execute complete digital business workflows, deliver customer value, verify revenue, calculate actual profitability and scale only what evidence and approved resources justify.

The governing principles are hybrid local-first AI, controlled autonomy, human ownership, capital preservation, deterministic security/financial authority and evidence-based operation. The original repository README is preserved in [docs/archive/INITIAL_README.md](docs/archive/INITIAL_README.md).

## Current implementation

P-01 was conditionally authorized after P-00 ended partially complete. The implemented scope is a backend core only:

- Python/FastAPI versioned API with owner authentication and protected endpoints.
- Validated configuration, structured rotating logs, lifecycle and health checks.
- SQLite + SQLAlchemy + Alembic core schema and repositories.
- Bounded persistent task queue with safe internal handlers, retry, cancellation, pause/resume and restart recovery.
- Internal event bus, persisted system events and audit records.
- Deny-by-default permission engine and approval framework.
- Lightweight resource monitoring and nonessential task admission control.
- 43 passing backend tests and a loopback live smoke test.

Explicitly not implemented: frontend dashboard, Tauri desktop shell, AI models/Ollama, autonomous agent creation, browser/desktop automation, business execution, wallets/payments, remote access, Windows certification.

Start with:

- [P-01 Implementation Report](docs/reports/P01_IMPLEMENTATION_REPORT.md)
- [P-01 Test Report](docs/reports/P01_TEST_REPORT.md)
- [P-01 Security Report](docs/reports/P01_SECURITY_REPORT.md)
- [P-01 Implementation Assessment](docs/reports/P01_IMPLEMENTATION_ASSESSMENT.md)
- [Phase Tracker](docs/PHASE_TRACKER.md)
- [Open Decisions](docs/OPEN_DECISIONS.md)

## Governing documents

- [Master Development Constitution](docs/AUTONOMUS_MASTER_CONSTITUTION.md)
- [Development Prompt Pack](docs/AUTONOMUS_DEVELOPMENT_PROMPT_PACK.md)
- [Architecture Decision Records](docs/ARCHITECTURE_DECISIONS.md)
- [P-00 Completion Report](docs/reports/P00_COMPLETION_REPORT.md) — historical pre-P-01 gate

## Running the conditional backend

Dependencies are listed in `backend/requirements.txt`. From the repository root:

```text
cd backend
python -m app.cli init-owner
python -m app.cli serve
```

The backend binds to `127.0.0.1:8000` by default. Logs are written to `logs/autonomus.log`; the SQLite database is `data/autonomus.db`. Use Ctrl+C in the backend console for graceful shutdown.

Windows helper scripts are provided but not Windows-certified:

```powershell
.\scripts\validate_environment.ps1
.\scripts\start_dev.ps1
.\scripts\health_check.ps1
```

`.\scripts\stop_backend.ps1 -Force` is emergency-only and not graceful.

## Publishing to GitHub

Work produced in the assistant workspace is delivered as an `AUTONOMUS_*.zip` package. It is **not** pushed to GitHub automatically, and the assistant workspace holds no GitHub credentials. Publishing always runs on the owner's PC.

**Easiest:** put `Publish-to-GitHub.cmd`, `publish_to_github.ps1` and the package ZIP in your Downloads folder and double-click `Publish-to-GitHub.cmd`. Choose `1` to preview, `2` to publish, `3` to publish after running tests.

**Or one command:**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\publish_to_github.ps1"
```

The script finds the newest package, clones or reuses `%USERPROFILE%\Devil-AI-OS`, backs up files it will overwrite, blocks secrets and runtime data, commits and pushes to `main`. Use `-DryRun` to preview, `-RunTests` to run backend tests first, `-NoPush` to keep the commit local. Sign-in is handled by Git Credential Manager or your browser; never paste tokens into chat.

Details: [Publishing guide](docs/architecture/PUBLISHING.md) · [Validation report](docs/reports/PUBLISH_SCRIPT_VALIDATION.md)

## API and frontend contract

OpenAPI snapshot: [shared/openapi-p01.json](shared/openapi-p01.json). API reference: [docs/architecture/API_REFERENCE.md](docs/architecture/API_REFERENCE.md). The full Command Center is deferred to P-11; no finished dashboard is claimed.

## Project structure

```text
Devil-AI-OS/
├── backend/
│   ├── app/
│   ├── tests/
│   ├── alembic.ini
│   ├── pyproject.toml
│   └── requirements.txt
├── shared/
│   └── openapi-p01.json
├── docs/
├── scripts/
├── config/
├── data/      # runtime, ignored
├── logs/      # runtime, ignored
└── backups/   # runtime, ignored
```

## Security principles

No unrestricted wallet access; no credentials in prompts or Git; no self-granted agent permissions; no unverified revenue claims; no unauthorized account/platform actions; no blind agent multiplication; deterministic authorization; recoverable operations; owner-controlled emergency shutdown. P-01 rejects remote binding and external/financial/cloud execution flags.

## License

The existing [MIT License](LICENSE) is preserved unchanged. Dependency and model licenses require separate review before distribution or commercial use.
