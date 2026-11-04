"""Whether the migration chain is applied at startup.

A hosted deployment can turn that off, because applying the whole chain on
every serverless cold start is slow and two cold starts at once can race on the
same revision. What must not change is that the database is still reached:
skipping migrations is not a reason to start up against a connection nobody
has verified.
"""
import asyncio
import sqlite3
from pathlib import Path

from app.core.config import Settings
from app.database.connection import Database


def _settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(
        environment="test",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        backup_dir=tmp_path / "backups",
        **overrides,
    )


def _table_count(tmp_path: Path) -> int:
    db_file = tmp_path / "data" / "autonomus.db"
    assert db_file.exists(), "the database file was never created"
    con = sqlite3.connect(db_file)
    try:
        return con.execute(
            "SELECT count(*) FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
    finally:
        con.close()


def test_migrations_run_by_default_and_create_the_schema(tmp_path):
    s = _settings(tmp_path)
    assert s.run_migrations_on_startup is True
    db = Database(s)
    asyncio.run(db.initialize())
    asyncio.run(db.dispose())
    assert _table_count(tmp_path) > 0


def test_skipping_startup_migrations_leaves_the_schema_unapplied(tmp_path):
    s = _settings(tmp_path, run_migrations_on_startup=False)
    # On SQLite the data directory is created by the migration step itself, so
    # a migration-less start needs it to exist already. That is one more reason
    # this flag is meant for hosted Postgres, where there is no directory.
    s.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(s)
    asyncio.run(db.initialize())
    asyncio.run(db.dispose())
    assert _table_count(tmp_path) == 0


def test_an_explicit_argument_overrides_the_setting(tmp_path):
    """So an operator can apply the chain deliberately on a host where startup
    application is switched off."""
    s = _settings(tmp_path, run_migrations_on_startup=False)
    db = Database(s)
    asyncio.run(db.initialize(run_migrations=True))
    asyncio.run(db.dispose())
    assert _table_count(tmp_path) > 0
