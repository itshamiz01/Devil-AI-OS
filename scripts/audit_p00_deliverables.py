#!/usr/bin/env python3
"""P-00 deliverable and acceptance-criteria auditor.

Mechanically checks the P-00 deliverables required by section 14 of the P-00
prompt (A-J), the workspace structure, and the Git hygiene exclusions required
by section 13. Emits machine-readable evidence so that no acceptance-criteria
box is ticked without a check behind it.

Unlike the historical ``scripts/verify_p00.py``, this auditor does NOT treat the
existence of ``backend/`` as a violation: P-01 was conditionally authorized,
implemented and merged, so implementation is expected. It audits P-00 artifacts
only and reports implementation state as context.

Read-only: it writes nothing except the report path you pass to --out.

Usage:
    python3 scripts/audit_p00_deliverables.py --pretty
    python3 scripts/audit_p00_deliverables.py --out docs/audits/P00_DELIVERABLE_AUDIT.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Deliverable ID -> (path relative to repo root, required content markers).
# Markers are lowercased substrings; each one maps to a bullet in P-00 section 14.
DELIVERABLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "A_environment_audit": ("docs/reports/ENVIRONMENT_AUDIT.md", (
        "operating system", "hardware", "tool", "dependenc", "missing",
        "compatibilit", "recommended setup",
    )),
    "B_ai_hardware_feasibility": ("docs/reports/AI_HARDWARE_FEASIBILITY.md", (
        "model", "quantization", "memory", "inference", "concurrenc",
        "limitation", "cloud",
    )),
    "C_technology_validation": ("docs/reports/TECHNOLOGY_VALIDATION.md", (
        "compatibilit", "licens", "alternative", "recommendation", "unresolved",
    )),
    "D_system_architecture": ("docs/architecture/SYSTEM_ARCHITECTURE.md", (
        "responsibilit", "communication", "data flow", "security boundar",
        "integration",
    )),
    "E_database_architecture": ("docs/architecture/DATABASE_ARCHITECTURE.md", (
        "entit", "relationship", "lifecycle", "persistence", "postgresql",
    )),
    "F_agent_governance": ("docs/architecture/AGENT_GOVERNANCE.md", (
        "hierarch", "permission", "lifecycle", "resource", "failure",
        "creation", "terminat",
    )),
    "G_security_foundation": ("docs/architecture/SECURITY_FOUNDATION.md", (
        "permission", "secret", "execution", "financial", "emergency", "threat",
    )),
    "H_development_roadmap": ("docs/reports/DEVELOPMENT_ROADMAP.md", (
        "p-00", "p-16", "dependenc", "milestone", "risk", "completion",
    )),
    "I_readme": ("README.md", (
        "autonomus", "mission", "status", "stack", "structure", "roadmap",
        "security",
    )),
}

# Section 3: the two governance documents that must be located and read.
GOVERNANCE_DOCS: tuple[str, ...] = (
    "docs/AUTONOMUS_MASTER_CONSTITUTION.md",
    "docs/AUTONOMUS_DEVELOPMENT_PROMPT_PACK.md",
)

# Section 7: proposed workspace structure.
PROPOSED_DIRS: tuple[str, ...] = (
    "docs", "backend", "frontend", "desktop", "shared", "tests", "scripts",
    "data", "logs", "backups", "config",
)
PROPOSED_FILES: tuple[str, ...] = (".gitignore", ".env.example", "README.md")

# Section 13: .gitignore must exclude these categories.
GITIGNORE_RULES: dict[str, tuple[str, ...]] = {
    "environment_files_with_secrets": (".env",),
    "credentials": ("credentials/", "secrets/", "*.pem", "*.key"),
    "browser_sessions": ("browser-profiles/", "browser_sessions/", "playwright/.auth/"),
    "virtual_environments": (".venv/", "venv/"),
    "build_outputs": ("dist/", "build/", "node_modules/"),
    "temporary_files": ("*.tmp", "*.bak", "*.log"),
    "local_databases": ("*.db", "*.sqlite", "data/"),
    "model_weights": ("*.gguf", "*.safetensors", "*.ckpt", "models/"),
}

ADR_REQUIRED_FIELDS: tuple[str, ...] = (
    "context", "problem", "option", "decision", "reason", "consequence", "status",
)


def _load(repo: Path, rel: str) -> str | None:
    path = repo / rel
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def audit_deliverables(repo: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, (rel, markers) in DELIVERABLES.items():
        text = _load(repo, rel)
        if text is None:
            out[key] = {"path": rel, "exists": False, "missing_markers": list(markers), "coverage": 0.0}
            continue
        lowered = text.lower()
        found = [m for m in markers if m in lowered]
        missing = [m for m in markers if m not in lowered]
        out[key] = {
            "path": rel,
            "exists": True,
            "lines": text.count("\n") + 1,
            "words": len(text.split()),
            "markers_found": found,
            "missing_markers": missing,
            "coverage": round(len(found) / len(markers), 3),
        }
    return out


def audit_governance_docs(repo: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for rel in GOVERNANCE_DOCS:
        text = _load(repo, rel)
        out[rel] = {
            "exists": text is not None,
            "words": len(text.split()) if text else 0,
        }
    pack = _load(repo, GOVERNANCE_DOCS[1]) or ""
    out["prompt_pack_phase_ids"] = sorted(set(re.findall(r"\bP-\d{2}\b", pack)))
    constitution = _load(repo, GOVERNANCE_DOCS[0]) or ""
    out["constitution_section_count"] = len(re.findall(r"(?m)^## \d+\.", constitution))
    return out


def audit_structure(repo: Path) -> dict[str, Any]:
    dirs = {d: (repo / d).is_dir() for d in PROPOSED_DIRS}
    files = {f: (repo / f).is_file() for f in PROPOSED_FILES}
    absent_dirs = [d for d, present in dirs.items() if not present]
    return {
        "proposed_dirs_present": dirs,
        "proposed_files_present": files,
        "absent_dirs": absent_dirs,
        "note": (
            "Absent directories are NOT automatically a defect: P-00 section 7 forbids "
            "creating placeholder modules or empty directories merely to make the tree "
            "look complete. Each absence must be justified by the phase that owns it."
        ),
    }


def audit_gitignore(repo: Path) -> dict[str, Any]:
    text = _load(repo, ".gitignore")
    if text is None:
        return {"exists": False, "categories": {}}
    categories: dict[str, Any] = {}
    for category, needles in GITIGNORE_RULES.items():
        hits = [n for n in needles if n in text]
        categories[category] = {"satisfied": bool(hits), "matched": hits, "expected_any_of": list(needles)}
    return {"exists": True, "categories": categories,
            "all_satisfied": all(c["satisfied"] for c in categories.values())}


def audit_adrs(repo: Path) -> dict[str, Any]:
    decisions = repo / "docs" / "decisions"
    if not decisions.is_dir():
        return {"exists": False, "count": 0, "files": {}}
    files: dict[str, Any] = {}
    for path in sorted(decisions.glob("ADR-*.md")):
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        missing = [f for f in ADR_REQUIRED_FIELDS if f not in text]
        files[path.name] = {"missing_required_fields": missing, "complete": not missing}
    return {
        "exists": True,
        "count": len(files),
        "files": files,
        "all_complete": all(f["complete"] for f in files.values()),
    }


def audit_implementation_context(repo: Path) -> dict[str, Any]:
    """Context only. P-00 must not execute P-01; this records what already exists."""
    backend = repo / "backend"
    py = sorted(str(p.relative_to(repo)) for p in backend.rglob("*.py")) if backend.is_dir() else []
    tests = [p for p in py if "/tests/" in p]
    return {
        "backend_python_files": len(py),
        "backend_test_files": len(tests),
        "frontend_present": (repo / "frontend").is_dir(),
        "desktop_present": (repo / "desktop").is_dir(),
        "note": "Recorded as context. P-01 backend was conditionally authorized (ADR-0009) and merged.",
    }


def build_report(repo: Path) -> dict[str, Any]:
    deliverables = audit_deliverables(repo)
    governance = audit_governance_docs(repo)
    structure = audit_structure(repo)
    gitignore = audit_gitignore(repo)
    adrs = audit_adrs(repo)

    incomplete = [k for k, v in deliverables.items() if not v["exists"] or v["coverage"] < 1.0]
    expected_phases = [f"P-{i:02d}" for i in range(17)]
    missing_phases = [p for p in expected_phases if p not in governance.get("prompt_pack_phase_ids", [])]

    return {
        "audited_utc": datetime.now(timezone.utc).isoformat(),
        "auditor": "scripts/audit_p00_deliverables.py",
        "repository_path": str(repo),
        "read_only": True,
        "deliverables": deliverables,
        "deliverables_all_present": all(v["exists"] for v in deliverables.values()),
        "deliverables_full_coverage": not incomplete,
        "deliverables_with_gaps": incomplete,
        "governance_documents": governance,
        "prompt_pack_missing_phase_ids": missing_phases,
        "workspace_structure": structure,
        "gitignore": gitignore,
        "architecture_decision_records": adrs,
        "implementation_context": audit_implementation_context(repo),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    report = build_report(args.repo)
    text = json.dumps(report, indent=2 if args.pretty else None, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote P-00 deliverable audit -> {args.out}")
    else:
        print(text)

    ok = report["deliverables_all_present"] and report["gitignore"]["all_satisfied"] and report["architecture_decision_records"]["all_complete"]
    print(f"deliverables present : {report['deliverables_all_present']}", file=sys.stderr)
    print(f"full marker coverage : {report['deliverables_full_coverage']} (gaps: {report['deliverables_with_gaps']})", file=sys.stderr)
    print(f"prompt pack phases   : {len(report['governance_documents'].get('prompt_pack_phase_ids', []))}/17", file=sys.stderr)
    print(f"gitignore categories : {report['gitignore']['all_satisfied']}", file=sys.stderr)
    print(f"ADRs complete        : {report['architecture_decision_records']['all_complete']} ({report['architecture_decision_records']['count']} files)", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
