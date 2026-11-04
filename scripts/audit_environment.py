#!/usr/bin/env python3
"""Read-only development-environment auditor for AUTONOMUS P-00.

Captures the machine facts that P-00 Deliverables A, B and C depend on, and
writes them as machine-readable evidence. Designed to be re-runnable on any
workspace, including the owner's Windows PC (where the PowerShell helper
``scripts/audit_windows.ps1`` covers the Windows-specific items instead).

Safety contract, mirroring ``audit_windows.ps1``:
  * installs nothing and downloads nothing
  * reads no credentials, wallet material or secret store
  * mutates no environment variable and no repository file
  * its only write is the report path you ask for

Network probing is limited to a fixed host list and records HTTP status codes
only - never response bodies - because the outbound allowlist materially decides
whether P-03 discovery and P-05 browser automation can be verified at all.
Disable it with --no-network.

Usage:
    python3 scripts/audit_environment.py --out docs/reports/EVIDENCE.json
    python3 scripts/audit_environment.py --no-network --pretty
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Hosts that decide whether later phases can be verified from this machine.
PROBE_HOSTS: tuple[str, ...] = (
    "https://pypi.org/simple/",
    "https://registry.npmjs.org/",
    "https://api.github.com/",
    "https://ollama.com/",
    "https://huggingface.co/",
    "https://www.google.com/",
)

# Packages the proposed stack depends on; presence is recorded, never installed.
STACK_DISTRIBUTIONS: tuple[str, ...] = (
    "fastapi", "uvicorn", "pydantic", "pydantic-settings", "sqlalchemy",
    "alembic", "aiosqlite", "psutil", "argon2-cffi", "httpx", "pytest",
    "playwright", "chromadb", "keyring", "ollama",
)

TOOLS: tuple[str, ...] = (
    "python3", "node", "npm", "npx", "yarn", "pnpm", "git", "pwsh",
    "powershell", "cargo", "rustc", "ollama", "docker", "playwright",
    "nvidia-smi", "lscpu",
)


def _run(argv: list[str], timeout: int = 10) -> str | None:
    """Return stripped stdout, or None if the tool is absent or failed."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _first_line(text: str | None) -> str | None:
    return text.splitlines()[0].strip() if text else None


def _read_int(path: Path, pattern: str) -> int | None:
    """MULTILINE is required: without it '^' matches only the first line, so
    every /proc/meminfo key after MemTotal would silently read as absent."""
    try:
        match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    except OSError:
        return None
    return int(match.group(1)) if match else None


def collect_os() -> dict[str, Any]:
    libc = ""
    try:
        libc = platform.platform()
    except Exception:  # platform can raise on odd kernels; record and continue
        libc = "unavailable"
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform_string": libc,
        "is_windows_target": platform.system() == "Windows",
    }


def collect_cpu() -> dict[str, Any]:
    info: dict[str, Any] = {
        "visible_logical": os.cpu_count(),
        "affinity_count": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "physical_model": None,
        "flags_aes_avx2": None,
    }
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        try:
            text = cpuinfo.read_text(encoding="utf-8")
        except OSError:
            text = ""
        model = re.search(r"^model name\s*:\s*(.+)$", text, re.MULTILINE)
        if model:
            info["physical_model"] = model.group(1).strip()
        flags = re.search(r"^flags\s*:\s*(.+)$", text, re.MULTILINE)
        if flags:
            present = set(flags.group(1).split())
            info["flags_aes_avx2"] = {f: (f in present) for f in ("aes", "avx", "avx2", "fma")}
    lscpu = _run(["lscpu"])
    if lscpu and not info["physical_model"]:
        model = re.search(r"Model name:\s*(.+)", lscpu)
        if model:
            info["physical_model"] = model.group(1).strip()
    return info


def collect_memory() -> dict[str, Any]:
    meminfo = Path("/proc/meminfo")
    out: dict[str, Any] = {}
    for key in ("MemTotal", "MemAvailable", "SwapTotal"):
        out[f"{key}_KiB"] = _read_int(meminfo, rf"^{key}:\s+(\d+) kB")
    if out.get("MemTotal_KiB"):
        out["MemTotal_GiB"] = round(out["MemTotal_KiB"] / 1048576, 2)
    if out.get("MemAvailable_KiB"):
        out["MemAvailable_GiB"] = round(out["MemAvailable_KiB"] / 1048576, 2)
    return out


def collect_storage(path: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:
        return {"path": str(path), "error": str(exc)}
    return {
        "path": str(path),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "total_GiB": round(usage.total / 1024**3, 2),
        "free_GiB": round(usage.free / 1024**3, 2),
        "physical_media_type": "Not established",
    }


def collect_gpu() -> dict[str, Any]:
    nvidia = sorted(str(p) for p in Path("/dev").glob("nvidia*"))
    dri = sorted(str(p) for p in Path("/dev/dri").glob("*")) if Path("/dev/dri").exists() else []
    return {
        "dev_nvidia": nvidia,
        "dev_dri": dri,
        "nvidia_smi": _first_line(_run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv"])),
        "conclusion": (
            "GPU interfaces exposed" if (nvidia or dri)
            else "No /dev/nvidia* or /dev/dri/* interfaces exposed; host GPU existence is not established."
        ),
    }


def collect_cgroup() -> dict[str, Any]:
    limits: dict[str, Any] = {}
    candidates = {
        "memory.max": "/sys/fs/cgroup/memory.max",
        "memory.high": "/sys/fs/cgroup/memory.high",
        "cpu.max": "/sys/fs/cgroup/cpu.max",
        "v1_memory_limit": "/sys/fs/cgroup/memory/memory.limit_in_bytes",
    }
    for name, path in candidates.items():
        p = Path(path)
        if p.exists():
            try:
                limits[name] = p.read_text(encoding="utf-8").strip()
            except OSError:
                limits[name] = None
    return limits


def collect_tools() -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for tool in TOOLS:
        if shutil.which(tool) is None:
            found[tool] = None
            continue
        args = {"lscpu": [], "python3": ["--version"], "node": ["--version"]}
        found[tool] = _first_line(_run([tool, *args.get(tool, ["--version"])]))
    return found


def collect_distributions() -> dict[str, str | None]:
    try:
        from importlib import metadata
    except ImportError:  # pragma: no cover - Python 3.8+ always has it
        return {"error": "importlib.metadata unavailable"}
    out: dict[str, str | None] = {}
    for name in STACK_DISTRIBUTIONS:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
        except Exception as exc:  # record, never swallow silently
            out[name] = f"error: {exc}"
    return out


def probe_network(timeout: int = 6) -> dict[str, Any]:
    """Record reachability of the hosts later phases depend on. Status only."""
    import urllib.error
    import urllib.request

    results: dict[str, Any] = {}
    for url in PROBE_HOSTS:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "autonomus-p00-audit"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - fixed allowlist, no secrets
                results[url] = {"reachable": True, "status": resp.status}
        except urllib.error.HTTPError as exc:
            results[url] = {"reachable": True, "status": exc.code}
        except Exception as exc:
            results[url] = {"reachable": False, "status": None, "error": type(exc).__name__}
    reachable = [u for u, r in results.items() if r.get("reachable")]
    blocked = [u for u, r in results.items() if not r.get("reachable")]
    return {"results": results, "reachable_count": len(reachable), "blocked": blocked}


def collect_workspace(repo: Path) -> dict[str, Any]:
    windows_candidates = {p: Path(p).exists() for p in ("C:\\AUTONOMUS", "/mnt/c/AUTONOMUS", "/c/AUTONOMUS")}
    top = sorted(
        p.name + ("/" if p.is_dir() else "")
        for p in repo.iterdir()
        if p.name != ".git"
    ) if repo.exists() else []
    tracked = _run(["git", "-C", str(repo), "ls-files"])
    return {
        "repository_path": str(repo),
        "windows_path_visibility": windows_candidates,
        "top_level_entries": top,
        "tracked_file_count": len(tracked.splitlines()) if tracked else None,
        "git_branch": _run(["git", "-C", str(repo), "branch", "--show-current"]),
        "git_head": _run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"]),
        "git_remote": _run(["git", "-C", str(repo), "remote", "get-url", "origin"]),
    }


def build_evidence(repo: Path, probe: bool) -> dict[str, Any]:
    return {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "auditor": "scripts/audit_environment.py",
        "scope": "Development workspace only; not the owner Windows production target",
        "os": collect_os(),
        "cpu": collect_cpu(),
        "memory": collect_memory(),
        "storage": collect_storage(repo),
        "gpu": collect_gpu(),
        "cgroup": collect_cgroup(),
        "tools": collect_tools(),
        "python_distributions": collect_distributions(),
        "network": probe_network() if probe else {"skipped": True},
        "workspace": collect_workspace(repo),
        "not_performed": [
            "Windows hardware audit",
            "Windows application build",
            "model download",
            "inference benchmark",
            "dependency installation",
            "financial integration",
            "external business action",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1],
                        help="repository root to describe (default: this script's parent)")
    parser.add_argument("--out", type=Path, default=None, help="write JSON evidence here (default: stdout)")
    parser.add_argument("--no-network", action="store_true", help="skip reachability probing entirely")
    parser.add_argument("--pretty", action="store_true", help="indent the JSON output")
    args = parser.parse_args()

    evidence = build_evidence(args.repo, probe=not args.no_network)
    text = json.dumps(evidence, indent=2 if args.pretty else None, sort_keys=False, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote environment evidence -> {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
