#!/usr/bin/env python3
"""Read-only technology-stack re-validation for AUTONOMUS P-00 Deliverable C.

Queries official package registries for the current release, interpreter/engine
floor and license of each proposed stack component, and records the result as
machine-readable evidence. Nothing is installed, resolved, built or downloaded
beyond registry metadata; no credentials are read or sent.

Registries contacted:
  * https://pypi.org/pypi/<package>/json
  * https://registry.npmjs.org/<package>/latest

If a registry is unreachable (for example from a network-restricted workspace),
the component is recorded as "unreachable" rather than guessed. Fabricating a
version would violate the P-00 rule against unsupported technical claims.

Usage:
    python3 scripts/audit_technology.py --pretty
    python3 scripts/audit_technology.py --out docs/reports/P00_REAUDIT_TECHNOLOGY_EVIDENCE.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PYPI_URL = "https://pypi.org/pypi/{}/json"
NPM_URL = "https://registry.npmjs.org/{}/latest"

# Backend / AI / automation components, with the reason each is proposed.
PYPI_PACKAGES: dict[str, str] = {
    "fastapi": "Backend API framework (Constitution §12)",
    "uvicorn": "ASGI server for the local backend",
    "pydantic": "Validation and typed schemas",
    "pydantic-settings": "Configuration-driven behavior (§12.1)",
    "sqlalchemy": "ORM; SQLite now, PostgreSQL-ready schema",
    "alembic": "Versioned database migrations (§12.1)",
    "aiosqlite": "Async SQLite driver for the local system of record",
    "greenlet": "SQLAlchemy async support",
    "psutil": "Resource monitoring and admission control",
    "argon2-cffi": "Owner password hashing (Argon2id)",
    "httpx": "API test client and future provider adapters",
    "pytest": "Automated testing (§12.1)",
    "playwright": "Browser automation (P-05)",
    "chromadb": "Vector memory candidate (P-09, deferred by ADR-0008)",
    "keyring": "OS secure secret storage candidate (P-10)",
    "ollama": "Local inference client candidate (P-02)",
}

# Frontend / desktop components.
NPM_PACKAGES: dict[str, str] = {
    "react": "Dashboard UI (Constitution §12, P-11)",
    "react-dom": "React renderer",
    "typescript": "Typed frontend (Constitution §12)",
    "vite": "Frontend build tooling candidate",
    "vitest": "Frontend test runner candidate",
    "typescript-eslint": "Lint toolchain; peer range constrains the TS choice (L-05)",
    "@tauri-apps/cli": "Windows desktop shell build tooling (P-01 desktop)",
    "@tauri-apps/api": "Desktop shell bridge",
}


def _get_json(url: str, timeout: int = 15) -> tuple[dict[str, Any] | None, str | None]:
    """Return (payload, error). An unreachable registry is reported, never guessed."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "autonomus-p00-technology-audit", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - public registry metadata only
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def audit_pypi() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, rationale in PYPI_PACKAGES.items():
        data, error = _get_json(PYPI_URL.format(name))
        if data is None:
            out[name] = {"rationale": rationale, "reachable": False, "error": error}
            continue
        info = data.get("info", {})
        out[name] = {
            "rationale": rationale,
            "reachable": True,
            "version": info.get("version"),
            "requires_python": info.get("requires_python"),
            "license_expression": info.get("license_expression") or info.get("license"),
            "yanked": bool(info.get("yanked")),
        }
    return out


def audit_npm() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, rationale in NPM_PACKAGES.items():
        data, error = _get_json(NPM_URL.format(name))
        if data is None:
            out[name] = {"rationale": rationale, "reachable": False, "error": error}
            continue
        out[name] = {
            "rationale": rationale,
            "reachable": True,
            "version": data.get("version"),
            "license": data.get("license"),
            "engines": data.get("engines"),
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    pypi = audit_pypi()
    npm = audit_npm()
    report = {
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "auditor": "scripts/audit_technology.py",
        "scope": "Official registry metadata only; not installed, not built, not target-hardware verified",
        "read_only": True,
        "pypi": pypi,
        "npm": npm,
        "unreachable": {
            "pypi": [k for k, v in pypi.items() if not v.get("reachable")],
            "npm": [k for k, v in npm.items() if not v.get("reachable")],
        },
        "not_performed": [
            "dependency installation", "lockfile resolution", "build",
            "target-hardware verification", "inference benchmark",
        ],
    }
    text = json.dumps(report, indent=2 if args.pretty else None, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote technology evidence -> {args.out}")
    else:
        print(text)

    unreachable = report["unreachable"]
    print(f"pypi components resolved : {len(pypi) - len(unreachable['pypi'])}/{len(pypi)}", file=sys.stderr)
    print(f"npm components resolved  : {len(npm) - len(unreachable['npm'])}/{len(npm)}", file=sys.stderr)
    if unreachable["pypi"] or unreachable["npm"]:
        print(f"unreachable              : {unreachable}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
