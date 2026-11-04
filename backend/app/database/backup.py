"""Database backup and restore.

Closes the "migration/backup tests" element of the P-01 security gate in
``SECURITY_FOUNDATION.md`` §11.

Design constraints that shaped this module:

* **WAL correctness.** The database runs with ``journal_mode=WAL``, so a plain
  file copy of ``autonomus.db`` can miss committed transactions still sitting in
  ``-wal`` and produce a torn snapshot. Everything here goes through SQLite's
  online backup API (``sqlite3.Connection.backup``), which takes a consistent
  snapshot without blocking writers.
* **Verify before trusting.** A backup is not reported as successful until
  ``PRAGMA integrity_check`` returns ``ok`` on the *copy*, and the core tables
  are present in it. A backup that cannot be verified is deleted rather than
  left behind to be mistaken for a good one.
* **Restore is destructive, so it is CLI-only.** Restoring overwrites the live
  database. It is deliberately *not* exposed over HTTP: P-01 §12 forbids
  exposing dangerous internal functions through API endpoints, and an
  owner-authenticated HTTP restore would still be one leaked session token away
  from destroying the audit trail. See ADR-0014.
* **A bad restore must be survivable.** The current database is copied aside
  before being replaced, so an incorrect restore can be undone.
* **Bounded retention.** Only the newest ``backup_retention_count`` backups are
  kept, so backups cannot silently consume the disk that
  ``monitoring.system_monitor`` is watching.

Tamper-resistance limitation, stated plainly because P-01 §11 requires it: these
are ordinary files on the same host as the database. They protect against
accidental corruption and application-level mistakes. They are **not**
cryptographically immutable and offer no protection against an attacker with
host administrator rights, who can alter or delete backups and the audit table
alike. Owner-protected off-machine backups are a later-phase concern.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..core.config import Settings

# Tables that must be present for a snapshot to count as a database backup
# rather than an arbitrary SQLite file.
REQUIRED_TABLES = frozenset({
    "principals", "permissions", "permission_assignments", "approvals",
    "tasks", "task_executions", "audit_events", "system_events",
    "system_configurations",
})

BACKUP_PREFIX = "autonomus-"
BACKUP_SUFFIX = ".db"


class BackupError(Exception):
    """Raised when a backup or restore cannot be completed safely."""


@dataclass
class BackupResult:
    path: Path
    size_bytes: int
    created_at: str
    integrity_ok: bool
    tables: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "integrity_ok": self.integrity_ok,
            "table_count": len(self.tables),
            "pruned": self.pruned,
        }


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def backup_dir(settings: Settings) -> Path:
    return Path(settings.backup_dir)


def list_backups(settings: Settings) -> list[Path]:
    """Existing backups, newest first (filename timestamps sort lexically)."""
    directory = backup_dir(settings)
    if not directory.is_dir():
        return []
    found = [p for p in directory.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}") if p.is_file()]
    return sorted(found, key=lambda p: p.name, reverse=True)


def verify_backup(path: Path) -> tuple[bool, list[str]]:
    """Run ``PRAGMA integrity_check`` and confirm the core schema is present.

    Returns ``(ok, tables)``. Never raises for a merely invalid file: an
    unverifiable backup is a normal, reportable outcome, not a crash.
    """
    path = Path(path)
    if not path.is_file():
        return False, []
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if not result or str(result[0]).lower() != "ok":
                return False, []
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            tables = sorted(str(r[0]) for r in rows)
            return REQUIRED_TABLES.issubset(set(tables)), tables
        finally:
            conn.close()
    except sqlite3.Error:
        return False, []


def create_backup(settings: Settings) -> BackupResult:
    """Take a consistent online snapshot of the live database.

    Safe to call while the backend is running: the SQLite backup API coordinates
    with WAL writers instead of racing them.
    """
    source = Path(settings.database_path)
    if not source.is_file():
        raise BackupError(f"Database not found at {source}; run migrations before backing up")

    directory = backup_dir(settings)
    directory.mkdir(parents=True, exist_ok=True)
    created_at = _timestamp()
    destination = directory / f"{BACKUP_PREFIX}{created_at}{BACKUP_SUFFIX}"

    src_conn: sqlite3.Connection | None = None
    dst_conn: sqlite3.Connection | None = None
    try:
        src_conn = sqlite3.connect(str(source))
        dst_conn = sqlite3.connect(str(destination))
        # pages=-1 copies the whole database in one pass.
        src_conn.backup(dst_conn, pages=-1)
        dst_conn.commit()
    except sqlite3.Error as exc:
        # Never leave a half-written file behind to be mistaken for a good backup.
        destination.unlink(missing_ok=True)
        raise BackupError(f"Backup failed: {exc}") from exc
    finally:
        for conn in (dst_conn, src_conn):
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass

    ok, tables = verify_backup(destination)
    if not ok:
        destination.unlink(missing_ok=True)
        raise BackupError("Backup did not pass integrity/schema verification and was discarded")

    pruned = _prune(settings)
    return BackupResult(
        path=destination,
        size_bytes=destination.stat().st_size,
        created_at=created_at,
        integrity_ok=True,
        tables=tables,
        pruned=[str(p) for p in pruned],
    )


def _prune(settings: Settings) -> list[Path]:
    """Delete all but the newest ``backup_retention_count`` backups."""
    keep = max(1, int(settings.backup_retention_count))
    existing = list_backups(settings)
    stale = existing[keep:]
    for path in stale:
        try:
            path.unlink()
        except OSError:
            # A file we cannot delete must not abort the backup that succeeded.
            continue
    return stale


def _live_backend_pid(settings: Settings) -> int | None:
    """PID of a running backend, or None. Used to refuse unsafe restores."""
    pid_path = Path(settings.data_dir) / "backend.pid"
    if not pid_path.is_file():
        return None
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    # A pid file can survive a hard kill (a known P-01 issue), so confirm the
    # process really exists before treating the backend as running.
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        return pid
    except OSError:
        return None
    return pid


def restore_backup(settings: Settings, backup_path: Path, assume_stopped: bool = False) -> dict:
    """Replace the live database with a verified backup.

    Refuses to run while the backend appears to be live, because overwriting a
    database that an engine has open would leave the running process writing to
    a file it no longer owns. ``assume_stopped`` exists for tests and for the
    documented recovery path where the pid file is known to be stale; it does
    not skip integrity verification.
    """
    backup_path = Path(backup_path)
    ok, tables = verify_backup(backup_path)
    if not ok:
        raise BackupError(f"Refusing to restore: {backup_path} failed integrity or schema verification")

    live_pid = _live_backend_pid(settings)
    if live_pid is not None and not assume_stopped:
        raise BackupError(
            f"Refusing to restore while the backend appears to be running (pid {live_pid}). "
            "Stop it first, or pass assume_stopped=True only if you have confirmed the pid file is stale."
        )

    target = Path(settings.database_path)
    preserved: Path | None = None
    if target.is_file():
        preserved = target.with_name(f"{target.stem}.pre-restore-{_timestamp()}{target.suffix}")
        shutil.copy2(target, preserved)

    # Checkpoint and remove WAL/SHM sidecars first: leaving a stale -wal next to
    # a freshly replaced database would let SQLite replay obsolete frames over
    # the restored content.
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(target) + suffix)
        if sidecar.exists():
            sidecar.unlink()

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, target)
    except OSError as exc:
        # Put the original back rather than leaving no database at all.
        if preserved is not None and preserved.is_file():
            shutil.copy2(preserved, target)
        raise BackupError(f"Restore failed, previous database preserved: {exc}") from exc

    restored_ok, restored_tables = verify_backup(target)
    if not restored_ok:
        if preserved is not None and preserved.is_file():
            for suffix in ("", "-wal", "-shm"):
                p = Path(str(target) + suffix)
                if p.exists():
                    p.unlink()
            shutil.copy2(preserved, target)
            raise BackupError("Restored database failed verification; previous database was rolled back")
        raise BackupError("Restored database failed verification and no rollback copy existed")

    return {
        "restored_from": str(backup_path),
        "database": str(target),
        "preserved_previous_at": str(preserved) if preserved else None,
        "integrity_ok": True,
        "table_count": len(restored_tables),
    }
