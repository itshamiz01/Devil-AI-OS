"""Tests for database backup, verification and restore.

Covers the "migration/backup tests" element of the P-01 security gate in
``SECURITY_FOUNDATION.md`` §11. The emphasis is on the safety properties, not
just the happy path: an unverified backup must never be presented as good, and a
restore must never leave the system without a database.
"""

import asyncio
import os
import sqlite3
from pathlib import Path

import pytest

from app.database.backup import (
    REQUIRED_TABLES,
    BackupError,
    create_backup,
    list_backups,
    restore_backup,
    verify_backup,
)
from app.database.connection import Database
from app.database.repositories import PrincipalRepo, TaskRepo
from conftest import _bootstrap


def _dead_pid() -> int:
    """A pid that is not currently running, for stale-pid-file tests."""
    for candidate in range(4_000_000, 4_010_000):
        try:
            os.kill(candidate, 0)
        except ProcessLookupError:
            return candidate
        except PermissionError:
            continue
    pytest.skip("could not find an unused pid")


def test_backup_creates_a_verified_snapshot(settings, owner_credentials):
    asyncio.run(_bootstrap(settings, *owner_credentials))

    result = create_backup(settings)

    assert result.path.is_file()
    assert result.integrity_ok is True
    assert result.size_bytes > 0
    # The snapshot must carry the real schema, not merely be a valid SQLite file.
    assert REQUIRED_TABLES.issubset(set(result.tables))

    ok, tables = verify_backup(result.path)
    assert ok is True
    assert REQUIRED_TABLES.issubset(set(tables))
    assert result.path in list_backups(settings)


def test_backup_refuses_when_no_database_exists(settings):
    """A backup of nothing must fail loudly rather than produce an empty file."""
    assert not Path(settings.database_path).exists()
    with pytest.raises(BackupError, match="Database not found"):
        create_backup(settings)
    assert list_backups(settings) == []


def test_verify_rejects_a_corrupt_file(settings, tmp_path):
    bogus = tmp_path / "not-a-database.db"
    bogus.write_bytes(b"this is not a sqlite database at all" * 40)
    ok, tables = verify_backup(bogus)
    assert ok is False
    assert tables == []


def test_verify_rejects_a_valid_sqlite_file_with_the_wrong_schema(tmp_path):
    """Integrity alone is not sufficient: an empty database is not a backup."""
    other = tmp_path / "empty.db"
    conn = sqlite3.connect(str(other))
    try:
        conn.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()

    ok, tables = verify_backup(other)
    assert ok is False
    assert "unrelated" in tables


def test_verify_handles_a_missing_file(tmp_path):
    assert verify_backup(tmp_path / "absent.db") == (False, [])


def test_restore_recovers_the_backed_up_state(settings, owner_credentials):
    """The point of a backup: later damage is undone by restoring."""
    asyncio.run(_bootstrap(settings, *owner_credentials))
    backup = create_backup(settings)

    async def add_task() -> str:
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                owner = await PrincipalRepo(session).by_name(owner_credentials[0])
                task = await TaskRepo(session).create(
                    name="created-after-backup", handler="system.noop", status="COMPLETED",
                    creator_id=owner.id, payload={},
                )
                await session.commit()
                return task.id
        finally:
            await db.dispose()

    late_task_id = asyncio.run(add_task())

    async def task_exists(task_id: str) -> bool:
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                return await TaskRepo(session).get(task_id) is not None
        finally:
            await db.dispose()

    assert asyncio.run(task_exists(late_task_id)) is True

    outcome = restore_backup(settings, backup.path)
    assert outcome["integrity_ok"] is True

    # The post-backup task is gone; the owner identity from before it survives.
    assert asyncio.run(task_exists(late_task_id)) is False

    async def owner_present() -> bool:
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                return await PrincipalRepo(session).by_name(owner_credentials[0]) is not None
        finally:
            await db.dispose()

    assert asyncio.run(owner_present()) is True


def test_restore_preserves_the_previous_database(settings, owner_credentials):
    """A restore must be reversible: the displaced database is kept."""
    asyncio.run(_bootstrap(settings, *owner_credentials))
    backup = create_backup(settings)

    outcome = restore_backup(settings, backup.path)

    preserved = outcome["preserved_previous_at"]
    assert preserved is not None
    assert Path(preserved).is_file()
    ok, _ = verify_backup(Path(preserved))
    assert ok is True, "the preserved pre-restore copy must itself be a valid database"


def test_restore_refuses_an_unverified_backup(settings, owner_credentials, tmp_path):
    asyncio.run(_bootstrap(settings, *owner_credentials))
    bogus = tmp_path / "bogus.db"
    bogus.write_bytes(b"garbage" * 100)

    with pytest.raises(BackupError, match="failed integrity or schema verification"):
        restore_backup(settings, bogus)

    # The live database must be untouched by the refused restore.
    ok, tables = verify_backup(Path(settings.database_path))
    assert ok is True
    assert REQUIRED_TABLES.issubset(set(tables))


def test_restore_refuses_while_the_backend_is_running(settings, owner_credentials):
    """Overwriting a database an engine has open would corrupt the running app."""
    asyncio.run(_bootstrap(settings, *owner_credentials))
    backup = create_backup(settings)

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    pid_file = settings.data_dir / "backend.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    try:
        with pytest.raises(BackupError, match="appears to be running"):
            restore_backup(settings, backup.path)
    finally:
        pid_file.unlink(missing_ok=True)


def test_restore_tolerates_a_stale_pid_file(settings, owner_credentials):
    """A pid file can survive a hard kill, so a dead pid must not block recovery."""
    asyncio.run(_bootstrap(settings, *owner_credentials))
    backup = create_backup(settings)

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    pid_file = settings.data_dir / "backend.pid"
    pid_file.write_text(str(_dead_pid()), encoding="utf-8")
    try:
        outcome = restore_backup(settings, backup.path)
        assert outcome["integrity_ok"] is True
    finally:
        pid_file.unlink(missing_ok=True)


def test_restore_requires_explicit_override_for_a_live_pid(settings, owner_credentials):
    asyncio.run(_bootstrap(settings, *owner_credentials))
    backup = create_backup(settings)

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    pid_file = settings.data_dir / "backend.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    try:
        outcome = restore_backup(settings, backup.path, assume_stopped=True)
        assert outcome["integrity_ok"] is True
    finally:
        pid_file.unlink(missing_ok=True)


def test_retention_prunes_oldest_backups(settings, owner_credentials):
    asyncio.run(_bootstrap(settings, *owner_credentials))
    limited = settings.model_copy(update={"backup_retention_count": 2})

    created = [create_backup(limited).path for _ in range(4)]

    remaining = list_backups(limited)
    assert len(remaining) == 2
    # Names sort newest-first, so the two newest are the survivors.
    assert remaining == sorted(created, key=lambda p: p.name, reverse=True)[:2]
    for stale in created[:2]:
        assert not stale.exists()


def test_list_backups_is_empty_before_any_backup(settings):
    assert list_backups(settings) == []
