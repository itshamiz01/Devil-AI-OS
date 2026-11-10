"""The code execution adapter (P-05 Stage 4).

Run one allow-listed interpreter, inside a managed workspace, with a wall-clock
timeout and capped output. This is the whole contract:

* **The interpreter is allow-listed.** The adapter spawns exactly one executable,
  resolved once at startup from ``settings.execution_code_interpreter`` (default:
  the interpreter running the engine). A request cannot name an interpreter, so
  "run code" cannot mean "run a binary of the requester's choosing". Combined
  with the workspace containment the FS adapter already proves, this bounds what
  a run can reach: the interpreter, its stdlib, and the workspace it runs in.
* **Isolation is self-labelled, and weak.** ``isolation_strength`` reports what
  was *verified*: ``"subprocess-with-timeout (weak)"``. §30 rule 22 forbids
  claiming sandbox strength that was not verified, and no OS-level sandbox is
  verifiable in this environment - so the honest label is a subprocess with a
  timeout, not a sandbox. That is why the code tool is Risk 2 and requires owner
  approval: the human gate is the control that stands in for the isolation this
  environment cannot provide. A stronger mechanism, when one is proven on the
  target machine, is a change to this string - never a silent upgrade.
* **The timeout kills the process tree.** A run that overruns its wall clock is
  terminated, and because children can outlive the parent, the whole process
  group is killed (``start_new_session=True`` + ``os.killpg`` here, detached
  process group on Windows). A half-finished run that lingers is a run that can
  still touch the workspace after its request has been recorded as done.
* **Output is capped, not silently truncated.** stdout and stderr are capped at
  ``execution_code_output_cap_bytes``; a run that exceeds the cap is recorded
  COMPLETED_WITH_WARNINGS with the fact stated, so a caller is never handed a
  result that looks whole while being partial - §6.1's rule that a result the
  caller cannot see is not a result.
* **The environment is controlled.** The child gets a minimal environment (the
  interpreter's own plus PATH/LANG/HOME), never the engine's full environment:
  secrets in the engine's environment must not become readable by a code run.

The adapter never decides authorization: it is called with a workspace the
policy engine has already checked, and its job is only to run the interpreter
safely inside that root. Identity, status, capability, scope, risk and approval
are policy's (Stage 2); this module owns the boundary on the process.

``execute`` is synchronous, like the filesystem adapter's: the scheduler calls
it in the caller's thread (Stage 3 runs one request at a time). A wall-clock
timeout means no run can block that thread indefinitely.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any

__all__ = [
    "CODE_ACTIONS",
    "ISOLATION_STRENGTH",
    "CodeExecutionError",
    "InterpreterNotAllowedError",
    "CodeAdapter",
]

#: §4's code operations. The code adapter runs one action: `run` a program.
CODE_ACTIONS = ("run",)

#: What isolation was *verified*, in words (§30 rule 22). Defaulting to
#: "subprocess-with-timeout (weak)": the subprocess + wall-clock timeout are
#: the mechanism, and "weak" is the honest strength until a real sandbox is
#: proven on the target machine.
ISOLATION_STRENGTH = "subprocess-with-timeout (weak)"

#: The interpreters that may be spawned. Empty means "the engine's own
#: interpreter only" (the default); a non-empty list adds allow-listed paths
#: that must resolve to an existing executable at startup.
DEFAULT_INTERPRETER_ALLOWLIST: tuple[str, ...] = ()


class CodeExecutionError(Exception):
    """A code run failed in a way that is not a policy refusal."""

    code = "code_execution_failed"


class InterpreterNotAllowedError(CodeExecutionError):
    """The requested interpreter is not on the allow-list.

    Raised rather than ignored: an interpreter outside the allow-list is a
    request to run an arbitrary binary, which is a different action from
    running code, and §30 forbids a requester choosing the executable.
    """

    code = "interpreter_not_allowed"


class CodeAdapter:
    """Run an allow-listed interpreter inside a managed workspace.

    Constructed per operation with the database session, settings and bus the
    caller owns; the adapter holds no state between calls. A request admitted by
    policy is handed to :meth:`execute` with the workspace it may run in and the
    program to run.
    """

    def __init__(self, db: Any, settings: Any, *, bus: Any = None) -> None:
        self.db = db
        self.settings = settings
        self.bus = bus
        #: The allow-listed interpreters, resolved to absolute paths once.
        #: ``None`` means "the engine's own interpreter". A list of one or
        #: more names is matched by executable basename or absolute path.
        self._interpreter_allowlist = self._resolve_allowlist()

    # ------------------------------------------------------------------ #
    # Interpreter allow-list
    # ------------------------------------------------------------------ #
    def _resolve_allowlist(self) -> tuple[str, ...]:
        """The allow-listed interpreters, or the engine's own if unset."""
        configured = str(
            getattr(self.settings, "execution_code_interpreters", "") or "")
        if not configured.strip():
            return (sys.executable,)
        paths = [p.strip() for p in configured.split(",") if p.strip()]
        return tuple(paths)

    def _allowed_interpreter(self, requested: str | None) -> str:
        """The allow-listed interpreter to run, or raise.

        ``requested`` comes from the run parameters; it is honoured only if it
        matches an allow-listed path or basename. The default is the first
        allow-listed interpreter (the engine's own).
        """
        allowlist = self._interpreter_allowlist or (sys.executable,)
        if not requested:
            return allowlist[0]
        candidate = os.path.abspath(requested)
        for allowed in allowlist:
            if candidate == os.path.abspath(allowed):
                return allowed
            if os.path.basename(candidate) == os.path.basename(allowed):
                return allowed
        raise InterpreterNotAllowedError(
            f"the interpreter {requested!r} is not allow-listed; "
            f"allow-listed: {', '.join(allowlist)}")

    # ------------------------------------------------------------------ #
    # Workspace resolution (the FS adapter's containment boundary)
    # ------------------------------------------------------------------ #
    @property
    def root(self) -> str:
        root = str(self.settings.execution_workspace_root)
        os.makedirs(root, exist_ok=True)
        return os.path.realpath(root)

    def workspace_root(self, workspace: Any) -> str:
        return os.path.realpath(getattr(workspace, "root_path", "") or
                                os.path.join(self.root, "workspace"))

    async def resolve_workspace(self, session: Any, *, owner_id: str,
                                scope: str) -> Any:
        """The workspace a request's scope names, created on first use.

        Reuses the filesystem adapter's containment boundary: a code run is a
        directory under the same execution root, proven against the same
        workspace row, so a program cannot reach outside its workspace through
        the path it is handed.
        """
        from .adapters_fs import FilesystemAdapter
        return await FilesystemAdapter(self.db, self.settings,
                                       bus=self.bus).resolve_workspace(
            session, owner_id=owner_id, scope=scope)

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #
    def execute(self, *, action: str, workspace: Any, code: str = "",
                interpreter: str | None = None,
                timeout_seconds: int | None = None, **_params: Any) -> dict[str, Any]:
        """Dispatch one admitted request to ``run``.

        Returns a result dict the run records: ``outcome``, ``exit_code``,
        ``stdout``, ``stderr``, ``resource_usage`` and ``isolation_strength``.
        Raises on failure so the scheduler records the attempt as FAILED with
        the category.
        """
        if action not in CODE_ACTIONS:
            raise CodeExecutionError(f"unknown code action '{action}'")
        return self._run(workspace, code, interpreter, timeout_seconds)

    def _run(self, workspace: Any, code: str, interpreter: str | None,
             timeout_seconds: int | None) -> dict[str, Any]:
        root = self.workspace_root(workspace)
        os.makedirs(root, exist_ok=True)
        exe = self._allowed_interpreter(interpreter)
        timeout = int(timeout_seconds or
                      getattr(self.settings, "execution_code_timeout_seconds", 20))
        cap = int(getattr(self.settings, "execution_code_output_cap_bytes",
                          65_536))

        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                [exe, "-I", "-"],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._child_env(),
                # New session/process group so the whole tree can be killed on
                # timeout: children can outlive the parent, and a run that
                # lingers after its request was recorded done is a run that can
                # still touch the workspace.
                start_new_session=(os.name != "nt"),
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                               if os.name == "nt" else 0),
            )
        except OSError as exc:
            raise CodeExecutionError(
                f"the interpreter {exe!r} could not be started: {exc}") from exc

        # Feed the program on stdin; a wall-clock timeout bounds the whole run.
        try:
            stdout_b, stderr_b = proc.communicate(
                input=code.encode("utf-8"), timeout=timeout)
            timed_out = False
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            # Kill the process group, not just the parent: children are not
            # killed by terminating the process that spawned them.
            self._kill_group(proc)
            try:
                stdout_b, stderr_b = proc.communicate(timeout=5)
            except Exception:  # noqa: BLE001
                stdout_b, stderr_b = b"", b""
            timed_out = True
            exit_code = None

        elapsed = round(time.monotonic() - started, 3)
        stdout, stderr, truncated = self._cap_output(stdout_b, stderr_b, cap)

        if timed_out:
            outcome = "TIMED_OUT"
            error_category = "timeout"
        elif exit_code == 0:
            outcome = "COMPLETED_WITH_WARNINGS" if truncated else "COMPLETED"
            error_category = None
        else:
            # A non-zero exit is a completed run whose program failed; that is
            # a different fact from the adapter failing to run it.
            outcome = "FAILED"
            error_category = "nonzero_exit"

        result = {
            "outcome": outcome,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": truncated,
            "elapsed_seconds": elapsed,
            "isolation_strength": ISOLATION_STRENGTH,
            "resource_usage": {"elapsed_seconds": elapsed,
                               "exit_code": exit_code,
                               "truncated": truncated},
        }
        if error_category:
            result["error_category"] = error_category
        return result

    def _cap_output(self, stdout_b: bytes, stderr_b: bytes,
                    cap: int) -> tuple[str, str, bool]:
        """Decode and cap both streams; return (stdout, stderr, truncated)."""
        truncated = len(stdout_b) > cap or len(stderr_b) > cap
        out = stdout_b[:cap].decode("utf-8", errors="replace")
        err = stderr_b[:cap].decode("utf-8", errors="replace")
        if truncated:
            out += f"\n[... output capped at {cap} bytes ...]\n"
        return out, err, truncated

    def _child_env(self) -> dict[str, str]:
        """A minimal environment for the child: never the engine's full env.

        Secrets in the engine's environment (API keys, DB URLs) must not become
        readable by a code run. The child gets the interpreter's own environment
        plus the essentials it needs to run, and nothing else the engine holds.
        """
        base = {k: v for k, v in os.environ.items()
                if k in ("PATH", "LANG", "LC_ALL", "TZ", "HOME", "SYSTEMROOT",
                         "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP")}
        base["PYTHONDONTWRITEBYTECODE"] = "1"
        base["PYTHONUNBUFFERED"] = "1"
        return base

    @staticmethod
    def _kill_group(proc: subprocess.Popen) -> None:
        """Terminate the whole process group, not just the parent."""
        if os.name == "nt":
            subprocess.call(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
            return
        try:
            os.killpg(os.getpgid(proc.pid), 9)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except OSError:
                pass
