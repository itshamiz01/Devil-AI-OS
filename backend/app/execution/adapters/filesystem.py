"""Filesystem execution adapter (§9).

Every operation runs inside a managed workspace; every path passes the
platform-first validator (Windows lexical rules + resolved containment)
in the adapter itself — policy already checked scope, the adapter
re-validates (defense in depth, §9.2). Writes are atomic (temporary file
+ ``os.replace``); overwrites snapshot the previous version under the
engine's temporary area and record before/after hashes; deletion is a
move to quarantine (reversible); permanent deletion only ever applies to
files already in quarantine and is Risk 2 at the policy layer.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import time
import uuid
from pathlib import Path

from ..errors import ExecutionValidationError, PathValidationError
from ..paths import resolve_within_workspace
from ..workspaces import WorkspaceManager
from .base import AdapterContext, AdapterResult

_READ_CAP = 1_000_000  # per-file scan cap for search


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".{target.name}.tmp-{uuid.uuid4().hex[:12]}"
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)


class FilesystemAdapter:
    adapter_type = "filesystem"

    def __init__(self, workspaces: WorkspaceManager):
        self._workspaces = workspaces

    def health(self) -> dict:
        try:
            self._workspaces.root.mkdir(parents=True, exist_ok=True)
            probe = self._workspaces.root / ".health_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return {"status": "available", "health_status": "healthy",
                    "details": {"root": str(self._workspaces.root),
                                "path_validation": "windows-lexical + resolved containment"}}
        except Exception as exc:
            return {"status": "degraded", "health_status": "degraded",
                    "details": {"error": f"{type(exc).__name__}: {exc}"}}

    # ------------------------------------------------------------------ util
    def _resolve(self, workspace_name: str, raw_path: str):
        workspace = self._workspaces.get_workspace(workspace_name)
        validated = resolve_within_workspace(Path(workspace.root_path), raw_path or "")
        return workspace, validated

    @staticmethod
    def _evidence(operation: str, workspace: str, relative: str, *,
                  after_hash: str | None = None, before_hash: str | None = None,
                  extra: dict | None = None) -> dict:
        details = {"operation": operation, "workspace": workspace, "path": relative}
        if before_hash is not None:
            details["before_hash"] = before_hash
        if extra:
            details.update(extra)
        return {"type": "file", "reference": f"{workspace}:{relative}",
                "content_hash": after_hash, "details": details}

    # ---------------------------------------------------------------- actions
    async def execute(self, action: str, parameters: dict,
                      context: AdapterContext) -> AdapterResult:
        handler = getattr(self, f"_do_{action}", None)
        if handler is None:
            return AdapterResult(False, error_category="ACTION_UNKNOWN",
                                 summary=f"filesystem adapter has no action '{action}'")
        try:
            return handler(parameters, context)
        except PathValidationError as exc:
            # §25.3 #3/#4: traversal and symlink escapes are security
            # events, categorized distinctly so the engine records them.
            return AdapterResult(False, error_category="PATH_TRAVERSAL",
                                 summary=f"path rejected: {exc.message}")
        except ExecutionValidationError as exc:
            return AdapterResult(False, error_category="VALIDATION",
                                 summary=exc.message)
        except Exception as exc:
            category = getattr(exc, "code", None) or type(exc).__name__
            return AdapterResult(False, error_category=str(category),
                                 summary=f"{type(exc).__name__}: {exc}")

    def _do_list(self, params, context):
        workspace, validated = self._resolve(params.get("workspace", ""), params.get("path", ""))
        target = validated.absolute
        if not target.exists():
            return AdapterResult(False, error_category="NOT_FOUND",
                                 summary=f"'{validated.relative}' does not exist")
        if not target.is_dir():
            return AdapterResult(False, error_category="NOT_A_DIRECTORY",
                                 summary=f"'{validated.relative}' is not a directory")
        entries = []
        for child in sorted(target.iterdir(), key=lambda p: p.name):
            stat = child.stat()
            entries.append({
                "name": child.name, "type": "directory" if child.is_dir() else "file",
                "size": stat.st_size if child.is_file() else None,
                "modified": stat.st_mtime})
        return AdapterResult(True, output={"entries": entries, "count": len(entries)},
                             summary=f"listed {len(entries)} entries in {workspace.name}:{validated.relative or '.'}")

    def _do_read(self, params, context):
        workspace, validated = self._resolve(params.get("workspace", ""), params.get("path", ""))
        target = validated.absolute
        if not target.is_file():
            return AdapterResult(False, error_category="NOT_FOUND",
                                 summary=f"'{validated.relative}' is not a file")
        cap = int(context.settings.get("max_output_bytes", 1_000_000))
        data = target.read_bytes()
        truncated = len(data) > cap
        shown = data[:cap]
        digest = sha256_bytes(data)
        return AdapterResult(
            True,
            output={"content": shown.decode("utf-8", errors="replace"),
                    "size": len(data), "sha256": digest, "truncated": truncated},
            summary=f"read {len(data)} bytes from {workspace.name}:{validated.relative}",
            evidence=[self._evidence("read", workspace.name, validated.relative, after_hash=digest)])

    def _do_metadata(self, params, context):
        workspace, validated = self._resolve(params.get("workspace", ""), params.get("path", ""))
        target = validated.absolute
        if not target.exists():
            return AdapterResult(False, error_category="NOT_FOUND",
                                 summary=f"'{validated.relative}' does not exist")
        stat = target.stat()
        output = {"is_dir": target.is_dir(), "size": stat.st_size,
                  "modified": stat.st_mtime,
                  "sha256": sha256_file(target) if target.is_file() else None}
        return AdapterResult(True, output=output,
                             summary=f"metadata for {workspace.name}:{validated.relative}")

    def _do_hash(self, params, context):
        workspace, validated = self._resolve(params.get("workspace", ""), params.get("path", ""))
        target = validated.absolute
        if not target.is_file():
            return AdapterResult(False, error_category="NOT_FOUND",
                                 summary=f"'{validated.relative}' is not a file")
        digest = sha256_file(target)
        return AdapterResult(True, output={"sha256": digest, "size": target.stat().st_size},
                             summary=f"sha256 of {workspace.name}:{validated.relative}")

    def _do_search(self, params, context):
        workspace, validated = self._resolve(params.get("workspace", ""), params.get("path", ""))
        query = str(params.get("query") or "")
        if not query:
            return AdapterResult(False, error_category="VALIDATION", summary="search requires a query")
        max_results = min(int(params.get("max_results", 50)), 500)
        base = validated.absolute
        if not base.exists():
            return AdapterResult(False, error_category="NOT_FOUND",
                                 summary=f"'{validated.relative}' does not exist")
        files = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()]
        matches = []
        for path in files:
            if len(matches) >= max_results:
                break
            try:
                if path.stat().st_size > _READ_CAP:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if query in line:
                    rel = path.relative_to(validated.root).as_posix()
                    matches.append({"path": rel, "line": number, "text": line.strip()[:300]})
                    if len(matches) >= max_results:
                        break
        return AdapterResult(True, output={"matches": matches, "count": len(matches)},
                             summary=f"{len(matches)} matches for '{query}' in {workspace.name}:{validated.relative or '.'}")

    def _do_mkdir(self, params, context):
        workspace, validated = self._resolve(params.get("workspace", ""), params.get("path", ""))
        validated.absolute.mkdir(parents=True, exist_ok=True)
        return AdapterResult(True, output={"path": validated.relative},
                             summary=f"directory {workspace.name}:{validated.relative} ready",
                             evidence=[self._evidence("mkdir", workspace.name, validated.relative)])

    def _write_file(self, params, context, *, must_not_exist: bool, operation: str):
        workspace, validated = self._resolve(params.get("workspace", ""), params.get("path", ""))
        target = validated.absolute
        content = str(params.get("content") or "")
        data = content.encode("utf-8")
        if len(data) > int(context.settings.get("max_input_bytes", 5_000_000)):
            return AdapterResult(False, error_category="INPUT_TOO_LARGE",
                                 summary="content exceeds the configured input ceiling")
        existed = target.exists()
        if must_not_exist and existed:
            return AdapterResult(False, error_category="FILE_EXISTS",
                                 summary=f"'{validated.relative}' already exists; create refuses to overwrite")
        before_hash = sha256_file(target) if existed and target.is_file() else None
        snapshot_ref = None
        if existed and target.is_file():
            snapshot_dir = self._workspaces.temporary_root() / "snapshots" / context.request_id
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            snapshot = snapshot_dir / (target.name + ".before")
            shutil.copyfile(target, snapshot)
            snapshot_ref = str(snapshot)
        atomic_write(target, data)
        after_hash = sha256_bytes(data)
        evidence = self._evidence(operation, workspace.name, validated.relative,
                                  after_hash=after_hash, before_hash=before_hash,
                                  extra={"snapshot": snapshot_ref} if snapshot_ref else None)
        return AdapterResult(
            True, output={"path": validated.relative, "size": len(data), "sha256": after_hash,
                          "before_sha256": before_hash, "snapshot": snapshot_ref},
            summary=f"{operation} {len(data)} bytes at {workspace.name}:{validated.relative}",
            evidence=[evidence])

    def _do_create(self, params, context):
        return self._write_file(params, context, must_not_exist=True, operation="create")

    def _do_write(self, params, context):
        return self._write_file(params, context, must_not_exist=False, operation="write")

    def _do_append(self, params, context):
        workspace, validated = self._resolve(params.get("workspace", ""), params.get("path", ""))
        target = validated.absolute
        existing = target.read_bytes() if target.is_file() else b""
        before_hash = sha256_bytes(existing) if target.is_file() else None
        addition = str(params.get("content") or "").encode("utf-8")
        data = existing + addition
        if len(data) > int(context.settings.get("max_input_bytes", 5_000_000)):
            return AdapterResult(False, error_category="INPUT_TOO_LARGE",
                                 summary="resulting file exceeds the configured input ceiling")
        atomic_write(target, data)
        after_hash = sha256_bytes(data)
        return AdapterResult(
            True, output={"path": validated.relative, "size": len(data), "sha256": after_hash,
                          "before_sha256": before_hash, "appended_bytes": len(addition)},
            summary=f"appended {len(addition)} bytes at {workspace.name}:{validated.relative}",
            evidence=[self._evidence("append", workspace.name, validated.relative,
                                     after_hash=after_hash, before_hash=before_hash)])

    def _copy_move(self, params, context, *, move: bool):
        src_ws, src = self._resolve(params.get("source_workspace", ""), params.get("source_path", ""))
        dst_ws, dst = self._resolve(params.get("dest_workspace", ""), params.get("dest_path", ""))
        source = src.absolute
        target = dst.absolute
        if not source.is_file():
            return AdapterResult(False, error_category="NOT_FOUND",
                                 summary=f"source '{src.relative}' is not a file")
        if target.exists():
            return AdapterResult(False, error_category="FILE_EXISTS",
                                 summary=f"destination '{dst.relative}' already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = sha256_file(source)
        if move:
            os.replace(source, target)
        else:
            shutil.copyfile(source, target)
        operation = "move" if move else "copy"
        return AdapterResult(
            True, output={"source": f"{src_ws.name}:{src.relative}",
                          "destination": f"{dst_ws.name}:{dst.relative}", "sha256": digest},
            summary=f"{operation} {src_ws.name}:{src.relative} -> {dst_ws.name}:{dst.relative}",
            evidence=[self._evidence(operation, dst_ws.name, dst.relative, after_hash=digest,
                                     extra={"source": f"{src_ws.name}:{src.relative}"})])

    def _do_copy(self, params, context):
        return self._copy_move(params, context, move=False)

    def _do_move(self, params, context):
        return self._copy_move(params, context, move=True)

    def _do_delete(self, params, context):
        workspace, validated = self._resolve(params.get("workspace", ""), params.get("path", ""))
        target = validated.absolute
        if not target.exists():
            return AdapterResult(False, error_category="NOT_FOUND",
                                 summary=f"'{validated.relative}' does not exist")
        if target.is_dir() and any(target.iterdir()):
            return AdapterResult(False, error_category="DIRECTORY_NOT_EMPTY",
                                 summary="only files and empty directories can be quarantined")
        quarantine = self._workspaces.quarantine_workspace()
        stamp = time.strftime("%Y%m%d%H%M%S")
        quarantined_name = f"{context.agent_id}__{stamp}__{target.name}"
        destination = Path(quarantine.root_path) / quarantined_name
        digest = sha256_file(target) if target.is_file() else None
        os.replace(target, destination)
        return AdapterResult(
            True, output={"quarantined_as": quarantined_name, "sha256": digest,
                          "original": f"{workspace.name}:{validated.relative}"},
            summary=f"moved {workspace.name}:{validated.relative} to quarantine as {quarantined_name} (reversible)",
            evidence=[self._evidence("delete_to_quarantine", workspace.name, validated.relative,
                                     after_hash=digest,
                                     extra={"quarantined_as": quarantined_name})])

    def _do_delete_permanent(self, params, context):
        workspace_name = str(params.get("workspace") or "")
        if workspace_name != "quarantine":
            return AdapterResult(
                False, error_category="POLICY",
                summary="permanent deletion applies only to files already in the quarantine workspace")
        workspace, validated = self._resolve(workspace_name, params.get("path", ""))
        target = validated.absolute
        if not target.is_file():
            return AdapterResult(False, error_category="NOT_FOUND",
                                 summary="only quarantined files can be permanently deleted")
        digest = sha256_file(target)
        target.unlink()
        return AdapterResult(
            True, output={"deleted": validated.relative, "sha256": digest},
            summary=f"permanently deleted quarantined file {validated.relative}",
            evidence=[self._evidence("delete_permanent", workspace.name, validated.relative,
                                     before_hash=digest)])
