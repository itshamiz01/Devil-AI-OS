# Dependency Security (P-10)

## Inventory

Runtime dependencies are pinned by the backend virtual
environment (`backend/pyproject.toml`). The P-10 phase added
**no new third-party dependencies** — the broker, guards, hash
chain (hashlib) and TOTP verifier (hmac/hashlib/base64) are
standard library only, deliberately: every new dependency is new
attack surface, and security code should need as little of it as
possible.

Principal existing dependencies and their security roles:
FastAPI/Starlette + uvicorn (HTTP), SQLAlchemy + Alembic
(storage/migrations), httpx (client), pydantic (validation).

## Scanning — NOT RUN in staging

No vulnerability scanner (pip-audit / OSV) is installed in the
staging environment, and **no scan results are claimed**. The
owner-side procedure is:

```powershell
pip-audit -r requirements.txt   # or: pip-audit (venv-aware)
```

run at deployment and monthly; findings triaged as incidents
when they touch the HTTP, crypto or deserialization surface.

## Policy

- New dependencies require owner approval and a note in the
  implementation report of the phase that adds them.
- Dependency updates are ordinary code changes: full test suite
  green before merge, no auto-update bots with write access.
- The lock posture is "known versions, reviewed changes", not
  "latest at any cost".
