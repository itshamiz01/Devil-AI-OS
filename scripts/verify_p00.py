"""Structural and preservation checks for P-00 documents (not application tests).

Uses only the Python standard library. Does not install dependencies, access the
network, start services, inspect credentials or modify the remote repository.
With --write-report, writes a JSON evidence file under docs/audits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "docs/AUTONOMUS_MASTER_CONSTITUTION.md",
    "docs/AUTONOMUS_DEVELOPMENT_PROMPT_PACK.md",
    "docs/prompts/P-00_EXECUTION_CONTRACT.md",
    "docs/reports/ENVIRONMENT_AUDIT.md",
    "docs/reports/AI_HARDWARE_FEASIBILITY.md",
    "docs/reports/TECHNOLOGY_VALIDATION.md",
    "docs/reports/DEVELOPMENT_ROADMAP.md",
    "docs/reports/P00_COMPLETION_REPORT.md",
    "docs/architecture/SYSTEM_ARCHITECTURE.md",
    "docs/architecture/DATABASE_ARCHITECTURE.md",
    "docs/architecture/AGENT_GOVERNANCE.md",
    "docs/architecture/SECURITY_FOUNDATION.md",
    "docs/ARCHITECTURE_DECISIONS.md",
    "docs/PHASE_TRACKER.md",
    "docs/OPEN_DECISIONS.md",
    "docs/KNOWN_LIMITATIONS.md",
    "docs/audits/P00_CRITICAL_REVIEW.md",
    "docs/reports/ENVIRONMENT_EVIDENCE.json",
    "docs/reports/TECHNOLOGY_EVIDENCE.json",
    "docs/audits/P00_BASELINE.json",
    "docs/archive/INITIAL_README.md",
    "README.md", ".gitignore", ".env.example",
    "config/autonomus.example.json",
    "scripts/audit_windows.ps1",
]
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    checks: list[dict[str, object]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    for rel in REQUIRED:
        path = ROOT / rel
        check("required_file:" + rel, path.is_file() and path.stat().st_size > 100,
              "Present and non-empty" if path.is_file() else "Missing")

    baseline = json.loads((ROOT / "docs/audits/P00_BASELINE.json").read_text())
    license_hash = hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest()
    archive_hash = hashlib.sha256((ROOT / "docs/archive/INITIAL_README.md").read_bytes()).hexdigest()
    check("license_preserved", license_hash == baseline["license_sha256"], license_hash)
    check("original_readme_preserved", archive_hash == baseline["original_readme_sha256"], archive_hash)
    check("license_no_tracked_diff", git("diff", "--exit-code", "HEAD", "--", "LICENSE").returncode == 0,
          "LICENSE matches the initial commit")

    markdown_files = [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]
    broken: list[str] = []
    for path in markdown_files:
        text = path.read_text(encoding="utf-8")
        for target in LINK.findall(text):
            target = target.strip().strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            resolved = (path.parent / unquote(target.split("#", 1)[0])).resolve()
            if not resolved.exists():
                broken.append(f"{path.relative_to(ROOT)} -> {target}")
    check("local_markdown_links", not broken, "; ".join(broken) or "All checked local links resolve")

    adrs = sorted((ROOT / "docs/decisions").glob("ADR-*.md"))
    required_adr_fields = ["Decision ID", "Status", "Context", "Problem", "Options considered",
                           "Selected decision", "Reasons", "Consequences"]
    incomplete_adrs = [p.name for p in adrs if any(f not in p.read_text() for f in required_adr_fields)]
    check("adr_count_and_fields", len(adrs) >= 8 and not incomplete_adrs,
          f"{len(adrs)} ADRs; incomplete: {incomplete_adrs}")

    config = json.loads((ROOT / "config/autonomus.example.json").read_text())
    check("configuration_fail_closed",
          config["operating_mode"] == "simulation"
          and not config["external_execution_enabled"]
          and not config["financial_execution_enabled"]
          and not config["cloud_ai_enabled"],
          "Example is inert, simulation-only, with external/financial/cloud execution disabled")
    env_values: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env_values[key.strip()] = value.strip()
    secret_like = [k for k, v in env_values.items()
                   if any(s in k.upper() for s in ("TOKEN", "PASSWORD", "SECRET", "API_KEY")) and v]
    check("env_example_no_secret_values", not secret_like, f"Non-empty secret-like fields: {secret_like}")
    check("env_example_disabled_capabilities",
          env_values.get("AUTONOMUS_OPERATING_MODE") == "simulation"
          and all(env_values.get(k) == "false" for k in (
              "AUTONOMUS_EXTERNAL_EXECUTION_ENABLED",
              "AUTONOMUS_FINANCIAL_EXECUTION_ENABLED",
              "AUTONOMUS_CLOUD_AI_ENABLED")),
          "Environment example does not enable external, financial or cloud execution")

    ignored = [".env", ".env.local", "secrets/client.json", "data/local.db",
               "models/model.gguf", "browser-profiles/Default/Cookies",
               "backups/private.sqlite", "logs/app.log", ".venv/file",
               "node_modules/file", "desktop/src-tauri/target/file",
               "credentials/wallet.key", "playwright/.auth/user.json"]
    ignore_failures = [p for p in ignored if git("check-ignore", "--no-index", "-q", p).returncode != 0]
    check("git_sensitive_exclusions", not ignore_failures, f"Unignored paths: {ignore_failures}")
    public_examples = [".env.example", "config/autonomus.example.json"]
    example_failures = [p for p in public_examples if git("check-ignore", "--no-index", "-q", p).returncode == 0]
    check("safe_examples_not_ignored", not example_failures, f"Ignored examples: {example_failures}")

    implemented_markers = [str(p.relative_to(ROOT)) for folder in ("backend", "frontend", "desktop")
                           for p in (ROOT / folder).rglob("*") if p.is_file()] if any((ROOT / f).exists() for f in ("backend", "frontend", "desktop")) else []
    check("no_premature_application_modules", not implemented_markers,
          f"Application files found: {implemented_markers}" if implemented_markers else "No backend/frontend/desktop implementation created")

    script = (ROOT / "scripts/audit_windows.ps1").read_text()
    forbidden = ["Invoke-Expression", "Set-ItemProperty", "Remove-Item", "Install-Module",
                 "Install-Package", "winget install", "ollama pull", "Start-Process"]
    found = [term for term in forbidden if term in script]
    check("windows_helper_read_only_patterns", not found and "http://127.0.0.1:11434/api/tags" in script,
          f"Forbidden operations: {found}; static check only, not a Windows execution test")

    evidence = json.loads((ROOT / "docs/reports/ENVIRONMENT_EVIDENCE.json").read_text())
    check("environment_scope_explicit", evidence["scope"] == "Arena Linux sandbox only; not the owner Windows PC",
          evidence["scope"])
    roadmap = (ROOT / "docs/reports/DEVELOPMENT_ROADMAP.md").read_text()
    check("all_prompt_ids_in_roadmap", all(f"P-{i:02d}" in roadmap for i in range(17)), "P-00 through P-16 present")

    passed = sum(bool(c["passed"]) for c in checks)
    result = {
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "P-00 structural, configuration and preservation checks only; not runtime/security certification",
        "passed": passed, "total": len(checks), "failed": len(checks) - passed,
        "checks": checks,
        "document_sha256": {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
                            for rel in REQUIRED if (ROOT / rel).is_file()},
    }
    print(json.dumps({k: result[k] for k in ("checked_utc", "scope", "passed", "total", "failed")}, indent=2))
    for item in checks:
        if not item["passed"]:
            print("FAIL", item["name"], item["detail"])
    if args.write_report:
        destination = ROOT / "docs/audits/P00_STRUCTURAL_CHECKS.json"
        destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("Evidence written to", destination.relative_to(ROOT))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
