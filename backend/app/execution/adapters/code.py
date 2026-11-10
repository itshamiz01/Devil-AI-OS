"""Controlled code execution adapter (§10) — Python only.

ISOLATION TRUTH (§10.2): the controls here are **process controls, not a
strong sandbox**: a dedicated temporary directory as cwd, an argv-only
exec of the application interpreter (never a shell), a scrubbed
environment (allowlisted variables only — no application secrets exist
in it), a timeout enforced by process-TREE termination, stdout/stderr
captured to files and read back under caps, and (POSIX, where supported)
CPU/file-size resource limits applied by a bootstrap before exec.
Language-level screening (§10.4) is a supplementary safeguard, never the
boundary (§10.3). Arbitrary untrusted code is NOT made safe by any of
this and is never grantable — the capability is owner-granted per agent,
and screened code can be escalated to hash-bound owner approval.

Supported languages: Python (the application interpreter) only.
JavaScript/Node and PowerShell are NOT enabled in this build: Node exists
on the staging host but a second runtime doubles the control surface;
PowerShell is Windows-only policy territory. Both are deferred and are
not represented as available anywhere.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import signal
import sys
import time
import uuid
from pathlib import Path

from ..paths import normalize_windows_lexical
from ..workspaces import WorkspaceManager
from .base import AdapterContext, AdapterResult
from .filesystem import sha256_bytes, sha256_file

# --------------------------------------------------------------------------
# §10.4 dangerous-construct screen. HARD = Risk-3 treatment (rejected by
# policy): credential/environment access, process spawning, dynamic code
# execution, network access, native-code bridges, destructive filesystem
# calls. SOFT = escalated to Risk 2 (hash-bound owner approval).
# --------------------------------------------------------------------------
HARD_PATTERNS: list[tuple[str, str]] = [
    ("environment_or_secret_access", r"os\.environ|environ\s*\[|\bgetenv\b"),
    ("subprocess_or_shell", r"subprocess|os\.system|\bpopen\b|\bpty\b"),
    ("dynamic_code_execution", r"\beval\s*\(|\bexec\s*\(|__import__|\bimportlib\b|\bcompile\s*\("),
    ("network_access", r"\bsocket\b|urllib|\brequests\b|\bhttpx\b|http\.client|ftplib|smtplib"),
    ("native_code_bridge", r"\bctypes\b|\bcffi\b|\bwinreg\b"),
    ("destructive_filesystem", r"shutil\.rmtree|os\.remove|os\.unlink|os\.rmdir"),
    ("privilege_or_system_change", r"os\.setuid|os\.setgid|os\.chmod|os\.chown\b"),
]
SOFT_PATTERNS: list[tuple[str, str]] = [
    ("filesystem_access", r"\bopen\s*\(|\bpathlib\b"),
    ("os_module", r"^\s*import\s+os\b|^\s*from\s+os\b|^\s*import\s+sys\b"),
]


def screen_code(code: str) -> dict:
    """Return {'hard': [names], 'soft': [names]} — construct NAMES only,
    suitable for audit records (the code itself is not copied)."""
    hard = [name for name, pattern in HARD_PATTERNS if re.search(pattern, code, re.MULTILINE)]
    soft = [name for name, pattern in SOFT_PATTERNS if re.search(pattern, code, re.MULTILINE)]
    return {"hard": hard, "soft": soft}


_ENV_ALLOWLIST = ("PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL")

_BOOTSTRAP = (
    "import os, sys\n"
    "try:\n"
    "    import resource\n"
    "    cpu = int(sys.argv[1]); fsize = int(sys.argv[2])\n"
    "    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))\n"
    "    resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))\n"
    "except Exception:\n"
    "    pass\n"
    "os.execv(sys.executable, [sys.executable, '-I', sys.argv[3]])\n"
)


def scrubbed_environment(run_dir: Path) -> dict:
    env = {key: os.environ[key] for key in _ENV_ALLOWLIST if key in os.environ}
    env.update({
        "AUTONOMUS_EXECUTION": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(run_dir), "TMP": str(run_dir), "TEMP": str(run_dir),
        "HOME": str(run_dir),
    })
    return env


class CodeExecutionAdapter:
    adapter_type = "code"
    isolation_level = "process_controls_only"

    def __init__(self, workspaces: WorkspaceManager):
        self._workspaces = workspaces
        self.active_processes: dict[str, asyncio.subprocess.Process] = {}

    def health(self) -> dict:
        return {"status": "available", "health_status": "degraded",
                "details": {
                    "interpreter": sys.executable,
                    "languages": ["python"],
                    "isolation": self.isolation_level,
                    "isolation_note": ("Process controls only (temp workspace, scrubbed env, "
                                       "timeout + process-tree kill, caps; POSIX rlimits where "
                                       "supported). NOT a strong sandbox (§10.2)."),
                    "deferred_languages": ["javascript/node", "powershell"],
                }}

    # ------------------------------------------------------------------- run
    async def execute(self, action: str, parameters: dict,
                      context: AdapterContext) -> AdapterResult:
        if action != "run":
            return AdapterResult(False, error_category="ACTION_UNKNOWN",
                                 summary=f"code adapter has no action '{action}'")
        code = str(parameters.get("code") or "")
        if not code.strip():
            return AdapterResult(False, error_category="VALIDATION", summary="code is required")
        if len(code.encode("utf-8")) > int(context.settings.get("max_input_bytes", 5_000_000)):
            return AdapterResult(False, error_category="INPUT_TOO_LARGE",
                                 summary="code exceeds the configured input ceiling")
        timeout = float(parameters.get("_timeout_seconds") or 30.0)
        settings = context.settings
        run_root = self._workspaces.temporary_root() / "code_runs"
        run_dir = run_root / f"{context.request_id}-{uuid.uuid4().hex[:8]}"
        input_dir = run_dir / "input"
        output_dir = run_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        created_inputs: list[str] = []
        try:
            for name, content in dict(parameters.get("inputs") or {}).items():
                relative = normalize_windows_lexical(str(name))
                target = input_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(content), encoding="utf-8")
                created_inputs.append(relative)
        except Exception as exc:
            shutil.rmtree(run_dir, ignore_errors=True)
            return AdapterResult(False, error_category="VALIDATION",
                                 summary=f"invalid input file name: {exc}")
        script = run_dir / "script.py"
        script.write_text(code, encoding="utf-8")

        before = self._snapshot(run_dir)
        started = time.monotonic()
        exit_code, timed_out = await self._run_process(
            script, run_dir, timeout, context.request_id)
        duration_ms = (time.monotonic() - started) * 1000.0

        output_cap = int(settings.get("max_output_bytes", 1_000_000))
        stdout = self._read_capped(run_dir / "stdout.log", output_cap)
        stderr = self._read_capped(run_dir / "stderr.log", output_cap)
        after = self._snapshot(run_dir)
        created = sorted(set(after) - set(before) - {"script.py", "stdout.log", "stderr.log"})
        modified = sorted(name for name in set(after) & set(before)
                          if after[name] != before[name] and name != "script.py")
        # §10.6/Scenario B: the temporary environment is cleaned up after
        # every run. What survives is the evidence: code hash, exit code,
        # captured output, and created/modified file names with hashes in
        # the run snapshot above — never the workspace itself.
        shutil.rmtree(run_dir, ignore_errors=True)
        cleaned = not run_dir.exists()
        evidence = [{
            "type": "code_execution",
            "reference": f"code_run:{run_dir.name}",
            "content_hash": sha256_bytes(code.encode("utf-8")),
            "details": {"isolation": self.isolation_level, "exit_code": exit_code,
                        "timed_out": timed_out, "duration_ms": round(duration_ms, 2),
                        "files_created": created, "files_modified": modified,
                        "inputs": created_inputs},
        }]
        output = {
            "exit_code": exit_code, "timed_out": timed_out,
            "stdout": stdout, "stderr": stderr,
            "duration_ms": round(duration_ms, 2),
            "files_created": created, "files_modified": modified,
            "file_hashes": {name: after[name] for name in created + modified
                            if name in after},
            "isolation": self.isolation_level,
            "workspace_cleaned": cleaned,
            "verification_status": "verified" if exit_code == 0 and not timed_out else "failed",
        }
        if timed_out:
            return AdapterResult(False, output=output, exit_code=None,
                                 error_category="EXECUTION_TIMEOUT", evidence=evidence,
                                 summary=f"code execution exceeded the {timeout:.0f}s timeout; "
                                         "the process tree was terminated",
                                 resource_usage={"duration_ms": round(duration_ms, 2)})
        success = exit_code == 0
        return AdapterResult(
            success, output=output, exit_code=exit_code, evidence=evidence,
            error_category=None if success else "NONZERO_EXIT",
            summary=(f"python exited 0 in {duration_ms:.0f} ms"
                     if success else f"python exited {exit_code}"),
            resource_usage={"duration_ms": round(duration_ms, 2),
                            "stdout_bytes": len(stdout.encode('utf-8')),
                            "stderr_bytes": len(stderr.encode('utf-8'))})

    async def _run_process(self, script: Path, run_dir: Path, timeout: float,
                           request_id: str) -> tuple[int | None, bool]:
        stdout_file = open(run_dir / "stdout.log", "wb")
        stderr_file = open(run_dir / "stderr.log", "wb")
        try:
            if os.name == "posix":
                argv = [sys.executable, "-I", "-c", _BOOTSTRAP,
                        str(int(timeout) + 5), str(10 * 1024 * 1024), str(script)]
            else:  # Windows: rlimits unavailable; timeout + tree kill still apply.
                argv = [sys.executable, "-I", str(script)]
            proc = await asyncio.create_subprocess_exec(
                *argv, cwd=str(run_dir), env=scrubbed_environment(run_dir),
                stdout=stdout_file, stderr=stderr_file,
                start_new_session=(os.name == "posix"))
            self.active_processes[request_id] = proc
            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout)
                return proc.returncode, False
            except asyncio.TimeoutError:
                await self._terminate_tree(proc)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
                return None, True
            finally:
                self.active_processes.pop(request_id, None)
        finally:
            stdout_file.close()
            stderr_file.close()

    async def terminate(self, request_id: str) -> bool:
        proc = self.active_processes.get(request_id)
        if proc is None or proc.returncode is not None:
            return False
        await self._terminate_tree(proc)
        return True

    @staticmethod
    async def _terminate_tree(proc: asyncio.subprocess.Process) -> None:
        if os.name == "posix":
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                return
            except (ProcessLookupError, PermissionError):
                pass
        elif os.name == "nt":  # pragma: no cover - Windows-only path
            try:
                killer = await asyncio.create_subprocess_exec(
                    "taskkill", "/PID", str(proc.pid), "/T", "/F",
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await killer.wait()
                return
            except Exception:
                pass
        try:
            proc.kill()
        except ProcessLookupError:
            pass

    # ------------------------------------------------------------------ util
    @staticmethod
    def _snapshot(run_dir: Path) -> dict[str, str]:
        snapshot = {}
        for path in run_dir.rglob("*"):
            if path.is_file():
                rel = path.relative_to(run_dir).as_posix()
                try:
                    snapshot[rel] = sha256_file(path)
                except Exception:
                    snapshot[rel] = "unreadable"
        return snapshot

    @staticmethod
    def _read_capped(path: Path, cap: int) -> str:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return ""
        return data[:cap].decode("utf-8", errors="replace")
