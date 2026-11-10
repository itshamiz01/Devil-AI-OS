"""Platform-first path validation (§9.2).

AUTONOMUS is Windows-first: the validator enforces the WINDOWS lexical
rules on every path, on every OS, BEFORE any POSIX resolution happens —
so behaviour in this Linux sandbox is the behaviour the owner's Windows
machine will get. Two independent layers, neither relying on string
prefix comparison alone:

1. **Windows lexical validation** of the raw submitted path: drive-letter
   injection (``C:\\...``, ``C:rel``), UNC paths (``\\\\host\\share``,
   ``\\\\?\\`` device paths), alternate data streams (``file.txt:stream``),
   ``..`` traversal (after lexical normalisation), reserved device names
   (CON/PRN/AUX/NUL/COM1…), trailing dot/space segment tricks (Windows
   silently strips them — a classic normalisation bypass), NUL bytes and
   control characters.
2. **Resolution containment**: the path is joined to the workspace root,
   fully resolved (symlinks/junctions followed for every existing
   component), and the result must be contained in the resolved root.
   A symlink inside the workspace pointing outside therefore fails,
   whether the target exists yet or not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .errors import PathValidationError

_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_RESERVED_NAMES = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


@dataclass(frozen=True)
class ValidatedPath:
    root: Path          # resolved workspace root
    absolute: Path      # resolved absolute target (contained in root)
    relative: str       # POSIX-style path relative to the root ("" = root)


def normalize_windows_lexical(raw: str) -> str:
    """Validate the raw path against Windows rules and return the
    lexically-normalised relative path (POSIX separators, no ``.``/``..``
    segments). Raises PathValidationError on any violation."""
    if raw is None:
        raise PathValidationError("path is required")
    if not isinstance(raw, str):
        raise PathValidationError("path must be a string")
    if "\x00" in raw:
        raise PathValidationError("path contains a NUL byte")
    if any(ord(ch) < 0x20 for ch in raw):
        raise PathValidationError("path contains control characters")
    if raw != raw.strip():
        # Never silently normalise surrounding whitespace away: on
        # Windows a trailing space is stripped by the OS itself, which
        # is exactly the normalisation bypass the segment check exists
        # to catch.
        raise PathValidationError(
            "path has leading or trailing whitespace (Windows normalisation bypass)")
    candidate = raw
    if candidate.startswith("\\\\") or candidate.startswith("//"):
        raise PathValidationError("UNC / network paths are not permitted")
    if candidate.startswith("\\\\?\\") or candidate.startswith("\\??\\"):
        raise PathValidationError("device-namespace paths are not permitted")
    if _DRIVE_RE.match(candidate):
        raise PathValidationError(
            "drive-letter paths are not permitted; paths are workspace-relative")
    if candidate.startswith(("/", "\\")):
        raise PathValidationError(
            "absolute paths are not permitted; paths are workspace-relative")

    segments: list[str] = []
    for segment in re.split(r"[/\\]+", candidate):
        if segment in ("", "."):
            continue
        if ":" in segment:
            raise PathValidationError(
                f"path segment '{segment}' contains ':' (drive or alternate-data-stream syntax)")
        if segment == "..":
            if not segments:
                raise PathValidationError("path escapes the workspace root ('..' above root)")
            segments.pop()
            continue
        base = segment.split(".", 1)[0].upper()
        if base in _RESERVED_NAMES:
            raise PathValidationError(f"path segment '{segment}' is a reserved Windows device name")
        if segment != segment.rstrip(" ."):
            raise PathValidationError(
                f"path segment '{segment}' ends with a dot or space (Windows normalisation bypass)")
        segments.append(segment)
    return "/".join(segments)


def resolve_within_workspace(root: Path, raw: str) -> ValidatedPath:
    """Lexically validate ``raw``, then resolve it inside ``root`` with
    symlink/junction following and prove containment in the resolved root."""
    relative = normalize_windows_lexical(raw)
    root_resolved = Path(root).resolve()
    target = (root_resolved / relative).resolve() if relative else root_resolved
    if target != root_resolved and root_resolved not in target.parents:
        raise PathValidationError(
            f"path '{raw}' resolves outside the workspace root (symlink/junction escape refused)")
    return ValidatedPath(root=root_resolved, absolute=target, relative=relative)


def is_within(root: Path, target: Path) -> bool:
    root_resolved = Path(root).resolve()
    resolved = Path(target).resolve()
    return resolved == root_resolved or root_resolved in resolved.parents
