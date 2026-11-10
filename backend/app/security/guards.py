"""Filesystem, command and download guards (§10, §11, §12.5).

These guards EVALUATE; they never execute. Execution remains in
P-05 under its own 10-check policy engine — P-10's guards are the
cross-cutting policy surface other layers (and the security API)
consult before an action is even proposed to P-05.

- FilesystemGuard wraps P-05's Windows-first path validator
  (``app/execution/paths.py`` — reused, not reimplemented) and adds
  §10.3 protected roots + §17 classification on top of workspace
  containment.
- CommandGuard is deterministic: executable allowlist, destructive
  pattern denylist, structured-argv validation (shell strings are
  refused outright — there is no shell here to inject into),
  working-directory containment via the same P-05 validator.
  §11.4 honesty: a passing guard decision does NOT make execution
  sandboxed. P-05's code execution remains process controls, not a
  strong sandbox, and this guard changes nothing about that.
- DownloadGuard (§12.5): size ceiling + executable-extension
  refusal + quarantine disposition (downloads are data, never
  executed).
"""
from __future__ import annotations

import re
from pathlib import Path

from ..execution.paths import normalize_windows_lexical
from ..permissions.models import Principal
from . import constants as C
from . import policy as P

# ------------------------------------------------------------ command guard
# Destructive / policy-breaking command patterns (§11.3). Matched
# against the joined argv for the named cases; a denylist is a
# backstop, never the only control (allowlist + argv rules are
# primary, per §11.3's own warning).
DENY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("recursive_delete_root", re.compile(r"(?i)\b(rm|del|erase|rd|rmdir)\b.*\s(/|\\|[a-z]:\\?)\s*$")),
    ("recursive_delete_flag", re.compile(r"(?i)\brm\b.*(-rf|-fr|-r\s+-f)")),
    ("format_drive", re.compile(r"(?i)\bformat\s+[a-z]:")),
    ("disk_image_write", re.compile(r"(?i)\b(dd|mkfs|diskpart)\b")),
    ("shutdown_or_reboot", re.compile(r"(?i)\b(shutdown|reboot|restart-computer)\b")),
    ("security_disable", re.compile(r"(?i)(set-mppreference.*-disablerealtimemonitoring|netsh\s+advfirewall\s+set.*state\s+off|sc\s+(stop|config)\s+(windefend|sense))")),
    ("firewall_modify", re.compile(r"(?i)\bnetsh\s+advfirewall\b")),
    ("user_account_modify", re.compile(r"(?i)\bnet\s+(user|localgroup)\b.*(/add|/delete)")),
    ("registry_modify", re.compile(r"(?i)\breg\s+(add|delete|import)\b")),
    ("encoded_powershell", re.compile(r"(?i)\b(powershell|pwsh)\b.*(-enc|encodedcommand)")),
    ("remote_script_pipe", re.compile(r"(?i)(curl|wget|invoke-webrequest|iwr)\b.*\|\s*(sh|bash|powershell|pwsh|python)")),
    ("credential_extraction", re.compile(r"(?i)\b(mimikatz|sekurlsa|lsass|procdump.*lsass|ntdsutil)\b")),
    ("policy_tamper", re.compile(r"(?i)(autonomus.*security\.settings|security\.settings.*(delete|remove|disable))")),
]

SHELL_METACHARACTERS = (";", "&", "|", "`", "$(", ">", "<", "\n")


class FilesystemGuard:
    """§10 evaluation over workspace-relative paths."""

    def __init__(self, get_settings, classification_lookup, audit=None):
        """``classification_lookup(resource_ref) -> int | None``
        resolves a registered §17 classification level. Denied
        evaluations are written to the P-01 audit trail (§19.1:
        filesystem access attempts are security events); routine
        allows are not — §19.5 forbids alert noise for harmless
        activity."""
        self._get_settings = get_settings
        self._classification_lookup = classification_lookup
        self._audit = audit

    def _denied(self, principal, operation, path, reason, checks,
                requires_approval=False) -> dict:
        if self._audit is not None:
            self._audit(principal, "security.filesystem_guard", "filesystem",
                        path, "deny", reason, {"operation": operation})
        return {"allowed": False, "operation": operation, "path": path,
                "reason": reason, "checks": checks,
                "requires_approval": requires_approval}

    def evaluate(self, principal: Principal, *, operation: str,
                 raw_path: str) -> dict:
        """operation: read | create | modify | move | copy | delete."""
        checks: list[dict] = []

        def record(name: str, passed: bool, reason: str) -> bool:
            checks.append({"check": name, "passed": passed, "reason": reason})
            return passed

        try:
            relative = normalize_windows_lexical(raw_path)
        except Exception as exc:
            record("path_validation", False, str(exc))
            return self._denied(principal, operation, raw_path, str(exc), checks)
        record("path_validation", True,
               "path is lexically valid and workspace-contained by construction")

        settings = self._get_settings()
        first_segment = relative.split("/", 1)[0].lower() if relative else ""
        protected = first_segment in {r.lower() for r in settings.get("protected_roots", [])}
        if protected:
            if P.is_owner(principal):
                record("protected_root", True,
                       f"'{first_segment}' is a protected root; owner access permitted")
            else:
                record("protected_root", False,
                       f"'{first_segment}' is a protected root (§10.3); "
                       f"non-owner access denied")
                return self._denied(principal, operation, relative,
                                    checks[-1]["reason"], checks)
        else:
            record("protected_root", True, "target is not in a protected root")

        level = self._classification_lookup(relative)
        requires_approval = False
        if level is not None and level >= 4 and operation in ("delete", "modify"):
            requires_approval = not P.is_owner(principal)
            record("classification", True,
                   f"resource classification level {level} "
                   f"({C.CLASSIFICATION_LEVELS[level]}); destructive operations "
                   f"{'require owner approval' if requires_approval else 'by owner'}")
        else:
            record("classification", True,
                   "no restrictive classification on this resource"
                   if level is None else f"classification level {level}")
        return {"allowed": True, "operation": operation, "path": relative,
                "reason": "filesystem operation permitted by guard policy",
                "checks": checks, "requires_approval": requires_approval,
                "classification": level}


class CommandGuard:
    """§11 evaluation of a structured command (argv list)."""

    def __init__(self, get_settings, audit=None):
        self._get_settings = get_settings
        self._audit = audit

    def evaluate(self, principal: Principal, *, argv, working_dir: str = "") -> dict:
        checks: list[dict] = []

        def record(name: str, passed: bool, reason: str) -> bool:
            checks.append({"check": name, "passed": passed, "reason": reason})
            return passed

        def deny(reason: str, blocked: bool = False) -> dict:
            if self._audit is not None:
                self._audit(principal, "security.command_guard", "command",
                            str(argv)[:300], "deny", reason,
                            {"blocked_pattern": blocked})
            return {"allowed": False, "blocked": blocked, "argv": argv,
                    "reason": reason, "checks": checks,
                    "requires_approval": False}

        if isinstance(argv, str) or not isinstance(argv, (list, tuple)) or not argv:
            record("structured_argv", False,
                   "commands must be structured argument arrays, never shell strings (§11.2)")
            return deny(checks[-1]["reason"])
        joined = " ".join(str(a) for a in argv)
        if any(meta in joined for meta in SHELL_METACHARACTERS):
            record("structured_argv", False,
                   "shell metacharacters in arguments (shell injection refused)")
            return deny(checks[-1]["reason"])
        record("structured_argv", True, "structured argv, no shell metacharacters")

        for name, pattern in DENY_PATTERNS:
            if pattern.search(joined):
                record("denylist", False, f"matched destructive pattern '{name}' (§11.3)")
                return deny(checks[-1]["reason"], blocked=True)
        record("denylist", True, "no destructive pattern matched")

        executable = Path(str(argv[0])).name.lower()
        if executable.endswith(".exe"):
            executable = executable[:-4]
        allowlist = {a.lower() for a in self._get_settings().get("command_allowlist", [])}
        if executable not in allowlist:
            record("allowlist", False,
                   f"executable '{executable}' is not on the command allowlist (§11.2)")
            return deny(checks[-1]["reason"])
        record("allowlist", True, f"executable '{executable}' is allowlisted")

        if working_dir:
            try:
                normalize_windows_lexical(working_dir)
                record("working_directory", True,
                       "working directory is workspace-relative and contained")
            except Exception as exc:
                record("working_directory", False, str(exc))
                return deny(checks[-1]["reason"])
        return {"allowed": True, "blocked": False, "argv": list(argv),
                "reason": ("command permitted by guard policy (evaluation only — "
                           "execution remains governed by P-05; process controls "
                           "are not a strong sandbox)"),
                "checks": checks, "requires_approval": False}


class DownloadGuard:
    """§12.5: downloaded content is untrusted data in quarantine,
    never an executable."""

    def __init__(self, get_settings):
        self._get_settings = get_settings

    def evaluate(self, *, filename: str, size_bytes: int,
                 content_type: str | None = None) -> dict:
        settings = self._get_settings()
        suffix = Path(filename or "").suffix.lower()
        if suffix in C.EXECUTABLE_EXTENSIONS:
            return {"allowed": False, "filename": filename,
                    "reason": f"executable file type '{suffix}' refused by default (§12.5)",
                    "disposition": "reject"}
        limit = int(settings.get("max_download_bytes", 0))
        if limit and size_bytes > limit:
            return {"allowed": False, "filename": filename,
                    "reason": f"download size {size_bytes} exceeds the {limit}-byte ceiling (§12.5)",
                    "disposition": "reject"}
        return {"allowed": True, "filename": filename,
                "reason": "download accepted into isolated quarantine storage; "
                          "content remains untrusted and is never executed",
                "disposition": "quarantine"}
