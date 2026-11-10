# Code Execution Security (P-05, §10) — read this before granting the capability

## The one fact that matters

**The code adapter's isolation is PROCESS CONTROLS ONLY. It is not a
strong sandbox** (§10.2). This label appears in the tool registry
description, the adapter health report, the startup health report, every
run's evidence, and this document. Arbitrary untrusted code must never
be treated as safe because it passed through this adapter. The
`sandboxed_code_execution` capability is therefore owner-granted per
agent (Level 2), and the §10.4 screen can escalate or reject code before
it runs.

## Controls that ARE in place

| Control | Mechanism |
|---|---|
| Dedicated environment | Fresh temp directory per run as cwd (`temporary/code_runs/<request>-<uuid>`), deleted after the run |
| No shell | argv-only exec of the application Python interpreter (`-I` isolated mode) |
| Scrubbed environment | Built from an allowlist (PATH, SYSTEMROOT, WINDIR, LANG/LC_ALL) + engine variables (TMPDIR/HOME pointed at the run dir). Server secrets are never inherited — proven by test (a planted server env secret does not appear in the child's environment) |
| Timeout | `asyncio.wait_for` at the adapter level; on expiry the **process tree** is killed (POSIX process group SIGKILL; Windows `taskkill /T /F` path exists for the owner's machine) — tested with a 60 s sleep killed at 2 s |
| Output bounds | stdout/stderr captured to files, read back under `max_output_bytes` |
| Input bounds | Code + input files bounded by `max_input_bytes`; input filenames pass the path validator |
| Resource limits (POSIX) | A pre-exec bootstrap applies `RLIMIT_CPU` (timeout+5 s) and `RLIMIT_FSIZE` (10 MB) where the platform supports it. Windows: these rlimits do not exist; timeout + tree-kill still apply |
| Emergency stop | The owner stop terminates every managed process via the adapter's process registry |

## The §10.4 screen (supplementary, never the boundary — §10.3)

Pattern screen over submitted code (`adapters/code.py::screen_code`):

- **Hard → Risk 3, rejected, `SandboxViolation` event:** `os.environ` /
  `getenv`, `subprocess` / `os.system` / `popen` / `pty`, `eval` / `exec`
  / `__import__` / `importlib` / `compile`, `socket` / `urllib` /
  `requests` / `httpx` / `http.client` / `ftplib` / `smtplib`, `ctypes` /
  `cffi` / `winreg`, `shutil.rmtree` / `os.remove` / `os.unlink` /
  `os.rmdir`, `os.setuid/setgid/chmod/chown`.
- **Soft → escalated to Risk 2** (hash-bound owner approval): `open(` /
  `pathlib`, `import os` / `import sys`.

The screen is a tripwire with false negatives by design (it is regex
over source text); the actual boundary is the capability grant + the
approval + the process controls. Do not invert that relationship.

## Languages

Python only. JavaScript/Node and PowerShell are **deferred** and are
not represented as available anywhere in the system.
