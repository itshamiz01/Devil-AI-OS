from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

from alembic import command
from alembic.config import Config
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..core.config import Settings
from .models import Base

BACKEND_DIR = Path(__file__).resolve().parents[2]


def run_migrations_sync(settings: Settings) -> None:
    # Only SQLite needs the directory, and creating it unconditionally would
    # crash startup on a read-only serverless filesystem where the external
    # database makes the directory pointless.
    if settings.database_is_sqlite:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.migration_database_url)
    command.upgrade(cfg, "head")


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        is_sqlite = settings.database_is_sqlite
        self.engine = create_async_engine(
            settings.async_database_url,
            echo=False,
            future=True,
            # A pooled connection to a serverless Postgres may have been closed
            # by the pooler between uses; ping before handing it out. SQLite
            # connections are local files and need no such check.
            pool_pre_ping=not is_sqlite,
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        if is_sqlite:
            # PRAGMA is SQLite syntax; sending it to Postgres would raise on
            # every connect, so the listener only exists for SQLite.
            event.listen(self.engine.sync_engine, "connect", self._set_sqlite_pragma)

    @staticmethod
    def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    async def initialize(self, *, run_migrations: bool | None = None) -> None:
        # None means "whatever the deployment asked for"; an explicit argument
        # overrides it, which is how a caller applies the chain deliberately.
        if run_migrations is None:
            run_migrations = self.settings.run_migrations_on_startup
        if run_migrations:
            await asyncio.to_thread(run_migrations_sync, self.settings)
        # The reachability check always runs: skipping migrations is not a
        # reason to start up against a database nobody has confirmed is there.
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def health(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
