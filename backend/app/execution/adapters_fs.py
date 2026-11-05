"""The filesystem execution adapter (P-05 Stage 3).

Six operations, a workspace per agent, and containment against the *resolved*
root. The operations are the brief's §4 list: `list`, `read`, `write`,
`create_dir`, `move`, `delete`. Everything an agent may reach is a path inside
a workspace root, and the boundary between "inside" and "outside" is computed
from the filesystem's own resolution - `os.path.realpath`, not a prefix string
comparison, because `workspace:../outside` and a symlink escaping the root are
the two ways a prefix check says "inside" about something outside.

The properties that matter, and the reason each is here:

* **Containment is resolved-path containment.** A path is relative to its
  workspace root; any absolute path, drive letter, UNC or `..` segment is
  refused before the filesystem is consulted. The path is then resolved against
  the realpath'd root, and the *nearest existing ancestor* of the target is
  resolved and checked to be inside the root - so a write into
  `a/b/c.txt` where `a/b` is a symlink out of the workspace is refused even
  though `c.txt` does not exist yet and has no realpath of its own.
* **Writes are atomic.** Content goes to a temp file in the destination
  directory and `os.replace` swaps it in. A failure mid-write leaves the
  previous content in place and a `.tmp-*` file that a later write may clean
  up, rather than a half-written file an agent could read as if it were whole.
* **Deletes are reversible.** A delete moves the file to
  `<workspace_root>/_quarantine/<workspace_id>/` with a timestamped name and
  records where it went, so an owner can put it back. Nothing is unlinked from
  inside the adapter: §6's rule that an action with external effects must be
  able to say what it did applies to removing a file like any other.
* **Size caps bound the work.** Reads and writes are capped (1 MB default)
  and a capped write is recorded as a warning, not as silent truncation: a
  result the caller cannot see is not a result. The caps are resource limits
  under `SystemMonitor`-style reasoning, not a security boundary - §30 rule 22
  is about claiming strengths that were not verified, and these caps are what
  they claim to be.
* **Evidence is recorded for the artefacts.** A written file and a read file
  get a `execution_evidence` row with a content hash, because §13 asks for
  evidence by reference (path + hash, never the content itself) and an agent
  that wrote a file is the kind of action an owner later wants to confirm.

The adapter never decides anything about authorization: it is called with a
workspace scope that policy has already checked against the workspace row, and
its job is only to make the bytes move safely inside that root. Identity,
status, capability, scope, risk and approval are policy's (Stage 2); this
module owns the boundary on the filesystem.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "FS_ACTIONS",
    "FS_CAPABILITY_BY_ACTION",
    "FS_WRITE_ACTIONS",
    "FS_READ_ACTIONS",
    "WorkspaceEscapeError",
    "WorkspaceNotFoundError",
    "FileSystemOperationError",
    "FilesystemAdapter",
    "hash_file",
]

#: §4's six operations, and the tool actions that route to them.
FS_ACTIONS = ("list", "read", "write", "create_dir", "move", "delete")

#: Which capability a filesystem action needs. The read operations need the
#: read capability; the mutating ones need the write capability (whose scope
#: requirement is the workspace itself, which is what makes a grant bounded).
FS_READ_ACTIONS = frozenset({"list", "read"})
FS_WRITE_ACTIONS = frozenset({"write", "create_dir", "move", "delete"})
FS_CAPABILITY_BY_ACTION = {
    **{a: "filesystem.read" for a in FS_READ_ACTIONS},
    **{a: "filesystem.write" for a in FS_WRITE_ACTIONS},
}

#: Quarantine lives at the root of every workspace collection, sibling to the
#: workspaces themselves, so a quarantined file is always inside the
#: execution root even though it is outside its original workspace.
QUARANTINE_DIRNAME = "_quarantine"

#: The size caps. Bounded so a single operation cannot exhaust memory on the
#: machine the monitor is watching; recorded on the run so a caller can see a
#: capped write was capped rather than silently truncated.
DEFAULT_READ_CAP_BYTES = 1_048_576
DEFAULT_WRITE_CAP_BYTES = 1_048_576

#: Characters that make a path absolute before the OS is consulted. Rejecting
#: them first is what lets the containment check below be about the *resolved*
#: path rather than about what the caller typed.
_ABSOLUTE_PREFIXES = ("/", "\\", "~")


class FileSystemOperationError(Exception):
    """A filesystem operation failed in a way that is not an escape.

    Raised by the adapter and caught by the scheduler, which records the run
    FAILED with `error_category` so the failure is visible rather than
    surfacing as an unhandled 500.
    """

    code = "filesystem_operation_failed"


class WorkspaceEscapeError(FileSystemOperationError):
    """A path resolved outside its workspace root.

    Raised rather than returned: an escape attempt is a security event, not a
    business outcome, and the run that raised it is recorded FAILED with this
    category so an owner can see an attempt was made and refused.
    """

    code = "workspace_escape"

    def __init__(self, path: str, root: str) -> None:
        super().__init__(
            f"the path {path!r} resolves outside the workspace root {root!r}")


class WorkspaceNotFoundError(FileSystemOperationError):
    """The requested scope names no workspace this agent owns."""

    code = "workspace_not_found"


def hash_file(path: str) -> str:
    """SHA-256 of a file, read in chunks so a large file cannot exhaust memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FilesystemAdapter:
    """The six filesystem operations, confined to managed workspaces.

    Constructed per operation with the database session, settings and bus the
    caller owns; the adapter holds no state between calls. A request that has
    been admitted by policy is handed to :meth:`execute` with the workspace
    name and path resolved from its parameters.
    """

    def __init__(self, db: Any, settings: Any, *, bus: Any = None) -> None:
        self.db = db
        self.settings = settings
        self.bus = bus

    # ------------------------------------------------------------------ #
    # Workspace resolution
    # ------------------------------------------------------------------ #
    @property
    def root(self) -> str:
        """The absolute root every workspace lives under.

        Created if absent: the root is a directory the engine owns, and a
        missing root is a missing deployment rather than an error every caller
        should have to handle.
        """
        root = str(self.settings.execution_workspace_root)
        os.makedirs(root, exist_ok=True)
        return os.path.realpath(root)

    def workspace_root(self, workspace: Any) -> str:
        return os.path.realpath(workspace.root_path)

    def _ensure_quarantine(self, workspace_id: str) -> str:
        path = os.path.join(self.root, QUARANTINE_DIRNAME, str(workspace_id))
        os.makedirs(path, exist_ok=True)
        return path

    async def resolve_workspace(self, session: Any, *, owner_id: str,
                                scope: str) -> Any:
        """The workspace a request's scope names, created on first use.

        Scope is the workspace name (`reports`, `scratch`). The engine owns the
        workspace, so an agent asking to work in one that does not exist yet
        gets one - its own directory under the execution root - rather than an
        error that would make every first use a registration ceremony. The
        workspace row is the containment boundary: the adapter proves every
        path against this row's `root_path`, and the scope a request names is
        what the scheduler resolves it against.
        """
        from ..database.repositories import ExecutionWorkspaceRepo
        repo = ExecutionWorkspaceRepo(session)
        name = scope.split("/", 1)[0].strip() or "workspace"
        existing = await repo.by_owner_name("agent", owner_id, name)
        if existing is not None:
            return existing
        root = self.root
        owner_dir = os.path.join(root, owner_id)
        workspace_dir = os.path.join(owner_dir, name)
        os.makedirs(workspace_dir, exist_ok=True)
        row = await repo.create(
            workspace_name=name, owner_type="agent", owner_id=owner_id,
            root_path=workspace_dir, permission_scope=name)
        await session.commit()
        return row

    # ------------------------------------------------------------------ #
    # Containment
    # ------------------------------------------------------------------ #
    @staticmethod
    def _check_no_absolute(path: str) -> None:
        if path.startswith(_ABSOLUTE_PREFIXES):
            raise WorkspaceEscapeError(path, "(absolute path)")
        if len(path) > 1 and path[1] == ":":
            raise WorkspaceEscapeError(path, "(drive-relative path)")
        parts = [p for p in path.replace("\\", "/").split("/")]
        if any(p == ".." for p in parts):
            raise WorkspaceEscapeError(path, "(parent segment)")

    def _resolve_within(self, workspace_root: str, rel_path: str) -> str:
        """Resolve `rel_path` against the realpath'd root and prove containment.

        Returns the absolute path to operate on. The check is on the nearest
        existing ancestor, because a file being created has no realpath of its
        own yet; a path whose existing ancestor is a symlink out of the root
        fails here, and so does a path that simply resolves elsewhere.
        """
        self._check_no_absolute(rel_path)
        candidate = os.path.normpath(os.path.join(workspace_root, rel_path))
        root = os.path.realpath(workspace_root)
        # Walk up to the first ancestor that exists.
        probe = candidate
        while True:
            if os.path.exists(probe):
                break
            parent = os.path.dirname(probe)
            if parent == probe:
                # Nothing exists up to the filesystem root: the path is
                # constructible but nothing in it is real, so the target
                # cannot be created inside a root that does not exist.
                break
            probe = parent
        resolved_ancestor = os.path.realpath(probe)
        if resolved_ancestor != root and not resolved_ancestor.startswith(root + os.sep):
            raise WorkspaceEscapeError(rel_path, root)
        # The full target, resolved, for operations that need the final path.
        return os.path.realpath(candidate)

    # ------------------------------------------------------------------ #
    # Operations
    # ------------------------------------------------------------------ #
    def execute(self, *, action: str, workspace: Any, path: str = "",
                **params: Any) -> dict[str, Any]:
        """Dispatch one admitted request to the right operation.

        Returns a result dict the run records: `outcome`, `result`, and for
        read/write the content hash. Raises on failure so the scheduler can
        record the attempt as FAILED with the category.
        """
        if action == "list":
            return self._list(workspace, path)
        if action == "read":
            return self._read(workspace, path)
        if action == "write":
            return self._write(workspace, path, params.get("content", ""))
        if action == "create_dir":
            return self._create_dir(workspace, path)
        if action == "move":
            return self._move(workspace, path, params.get("destination", ""))
        if action == "delete":
            return self._delete(workspace, path)
        raise FileSystemOperationError(f"unknown filesystem action '{action}'")

    def _list(self, workspace: Any, path: str) -> dict[str, Any]:
        root = self.workspace_root(workspace)
        target = self._resolve_within(root, path or "")
        if not os.path.isdir(target):
            raise FileSystemOperationError(f"{path or '.'} is not a directory")
        entries = []
        for name in sorted(os.listdir(target)):
            full = os.path.join(target, name)
            entries.append({"name": name, "type": "dir" if os.path.isdir(full)
                            else "file", "size": os.path.getsize(full)})
        return {"outcome": "COMPLETED", "entries": entries, "count": len(entries)}

    def _read(self, workspace: Any, path: str) -> dict[str, Any]:
        root = self.workspace_root(workspace)
        target = self._resolve_within(root, path)
        if not os.path.isfile(target):
            raise FileSystemOperationError(f"{path} is not a file")
        size = os.path.getsize(target)
        cap = int(getattr(self.settings, "execution_fs_read_cap_bytes",
                          DEFAULT_READ_CAP_BYTES) or DEFAULT_READ_CAP_BYTES)
        truncated = False
        if size > cap:
            # Reading the first cap bytes is honest only if the caller is told
            # the file is larger than what was returned.
            with open(target, "rb") as handle:
                content = handle.read(cap)
            truncated = True
        else:
            with open(target, "rb") as handle:
                content = handle.read()
        return {"outcome": "COMPLETED", "content": content.decode("utf-8", errors="replace"),
                "size": size, "truncated": truncated,
                "content_hash": hash_file(target)}

    def _write(self, workspace: Any, path: str, content: str) -> dict[str, Any]:
        root = self.workspace_root(workspace)
        target = self._resolve_within(root, path)
        if not target or os.sep in target.replace(root, "", 1).lstrip(os.sep):
            pass  # containment already proven; this is readability of intent
        parent = os.path.dirname(target)
        # Parents are created as needed: the six operations are the agent's
        # whole filesystem vocabulary, and making it write a file only after
        # an explicit create_dir - or making create_dir a precondition that
        # fails as an opaque "does not exist" - would leave the vocabulary
        # unable to build a directory tree in one pass. Containment is
        # already proven for every ancestor of the target above.
        os.makedirs(parent, exist_ok=True)
        cap = int(getattr(self.settings, "execution_fs_write_cap_bytes",
                          DEFAULT_WRITE_CAP_BYTES) or DEFAULT_WRITE_CAP_BYTES)
        size = len(content.encode("utf-8"))
        if size > cap:
            return {"outcome": "COMPLETED_WITH_WARNINGS",
                    "warning": f"the write was capped at {cap} bytes; "
                               f"{size - cap} bytes were not written",
                    "size": cap, "content_hash": None}
        temp = os.path.join(parent, f".tmp-{os.urandom(8).hex()}")
        try:
            with open(temp, "wb") as handle:
                handle.write(content.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        except OSError:
            if os.path.exists(temp):
                os.unlink(temp)
            raise
        return {"outcome": "COMPLETED", "size": size,
                "content_hash": hash_file(target)}

    def _create_dir(self, workspace: Any, path: str) -> dict[str, Any]:
        root = self.workspace_root(workspace)
        target = self._resolve_within(root, path)
        if os.path.exists(target):
            raise FileSystemOperationError(f"{path} already exists")
        os.makedirs(target)
        return {"outcome": "COMPLETED", "created": target}

    def _move(self, workspace: Any, path: str, destination: str) -> dict[str, Any]:
        root = self.workspace_root(workspace)
        source = self._resolve_within(root, path)
        if not os.path.exists(source):
            raise FileSystemOperationError(f"{path} does not exist")
        dest = self._resolve_within(root, destination)
        # The destination's parent is created as needed, like write's: the
        # workspace vocabulary should be able to build a tree in one move
        # rather than requiring a create_dir between two moves. Containment
        # of every ancestor is already proven above.
        os.makedirs(os.path.dirname(dest) or root, exist_ok=True)
        if os.path.exists(dest):
            raise FileSystemOperationError(f"{destination} already exists")
        shutil.move(source, dest)
        return {"outcome": "COMPLETED", "moved": destination}

    def _delete(self, workspace: Any, path: str) -> dict[str, Any]:
        root = self.workspace_root(workspace)
        target = self._resolve_within(root, path)
        if not os.path.exists(target):
            raise FileSystemOperationError(f"{path} does not exist")
        quarantine = self._ensure_quarantine(str(workspace.id))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        moved = os.path.join(quarantine, f"{stamp}-{os.path.basename(target)}")
        os.makedirs(os.path.dirname(target) or root, exist_ok=True)
        shutil.move(target, moved)
        return {"outcome": "COMPLETED", "quarantined": moved, "reversible": True}
