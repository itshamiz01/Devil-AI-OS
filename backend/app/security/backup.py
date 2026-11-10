"""Backup creation and verification (§20.4).

For the SQLite-backed staging deployment this performs a REAL
backup: a consistent copy via the SQLite backup API, a SHA-256
manifest, and verification that re-opens the copy read-only and
checks integrity, table inventory and readability of the security
state. Restoration itself is an owner procedure (documented in
``docs/security/EMERGENCY_RESPONSE.md``) and is drill-tested in the
integration suite — the service deliberately does not overwrite a
live database.

For any non-SQLite database (e.g. a future PostgreSQL deployment)
no dump tooling is wired: the record is created with status
``requires_owner_configuration`` rather than pretending a backup
exists.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from ..core.exceptions import NotFoundError, PermissionDeniedError
from ..database.models.base import utcnow
from ..database.models.security import SecurityBackupRecord
from ..database.repositories.security import BackupRecordRepository
from ..permissions.models import Principal
from . import policy as P


def backup_to_dict(row: SecurityBackupRecord) -> dict:
    return {
        "id": row.id, "kind": row.kind, "location": row.location,
        "sha256": row.sha256, "size_bytes": row.size_bytes,
        "table_count": row.table_count, "status": row.status,
        "detail": row.detail, "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BackupService:
    def __init__(self, session_factory, database_url: str, data_dir: Path, audit):
        self._session_factory = session_factory
        self._database_url = database_url
        self._data_dir = Path(data_dir)
        self._audit = audit

    def _sqlite_path(self) -> Path | None:
        parsed = urlparse(self._database_url)
        if parsed.scheme != "sqlite" or not parsed.path or parsed.path == "/:memory:":
            return None
        return Path(parsed.path)

    def create_backup(self, principal: Principal) -> dict:
        if not P.is_owner(principal):
            raise PermissionDeniedError("backup creation is owner-only (§20.4)")
        source = self._sqlite_path()
        session = self._session_factory()
        try:
            repo = BackupRecordRepository(session)
            if source is None or not source.exists():
                row = repo.add(SecurityBackupRecord(
                    kind="database", location=self._database_url,
                    status="requires_owner_configuration",
                    detail=("no file-based SQLite database to copy; dump "
                            "tooling for this database is REQUIRES OWNER "
                            "CONFIGURATION"),
                    created_by=P.actor(principal)))
                return backup_to_dict(row)
            backup_dir = self._data_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = utcnow().strftime("%Y%m%dT%H%M%S%f")
            target = backup_dir / f"autonomus-{stamp}.db"
            src = sqlite3.connect(str(source))
            try:
                dst = sqlite3.connect(str(target))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            tables = self._table_inventory(target)
            row = repo.add(SecurityBackupRecord(
                kind="database", location=str(target),
                sha256=_sha256_file(target), size_bytes=target.stat().st_size,
                table_count=len(tables), status="created",
                detail="consistent SQLite backup copy; not yet verified",
                created_by=P.actor(principal)))
            result = backup_to_dict(row)
        finally:
            session.close()
        self._audit(principal, "security.backup_created", "backup", result["id"],
                    "allow", "database backup created", {})
        return result

    def verify_backup(self, principal: Principal, backup_id: str) -> dict:
        if not P.is_owner(principal):
            raise PermissionDeniedError("backup verification is owner-only (§20.4)")
        session = self._session_factory()
        try:
            repo = BackupRecordRepository(session)
            row = repo.get(backup_id)
            if row is None:
                raise NotFoundError(f"backup {backup_id} not found")
            path = Path(row.location)
            problems: list[str] = []
            if row.status == "requires_owner_configuration":
                problems.append("backup was never created (owner configuration required)")
            elif not path.exists():
                problems.append("backup file is missing")
            else:
                if _sha256_file(path) != row.sha256:
                    problems.append("backup file hash does not match its manifest")
                try:
                    tables = self._table_inventory(path)
                    if row.table_count is not None and len(tables) != row.table_count:
                        problems.append(
                            f"table inventory changed: manifest {row.table_count}, "
                            f"actual {len(tables)}")
                    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                    try:
                        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
                        if integrity != "ok":
                            problems.append(f"integrity_check: {integrity}")
                        # The security state must be readable in the copy:
                        # policies/identities/audit survive restoration.
                        for table in ("system_config", "audit_events", "agents",
                                      "security_policy_versions"):
                            if table not in tables:
                                problems.append(f"required table '{table}' missing")
                    finally:
                        con.close()
                except Exception as exc:
                    problems.append(f"backup could not be opened: {type(exc).__name__}")
            row.status = "verified" if not problems else "verify_failed"
            row.detail = ("backup verified: integrity ok, manifest hash matches, "
                          "security state readable" if not problems
                          else "; ".join(problems))
            row.verified_at = utcnow()
            result = backup_to_dict(repo.save(row))
        finally:
            session.close()
        self._audit(principal, "security.backup_verified", "backup", backup_id,
                    "allow" if result["status"] == "verified" else "deny",
                    result["detail"] or "", {})
        return result

    def list_backups(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            rows, total = BackupRecordRepository(session).list(
                limit=limit, offset=offset)
            return [backup_to_dict(r) for r in rows], total
        finally:
            session.close()

    @staticmethod
    def _table_inventory(path: Path) -> set[str]:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            con.close()
