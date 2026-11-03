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
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.sync_database_url)
    command.upgrade(cfg, "head")


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = create_async_engine(settings.async_database_url, echo=False, future=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        event.listen(self.engine.sync_engine, "connect", self._set_sqlite_pragma)

    @staticmethod
    def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    async def initialize(self) -> None:
        await asyncio.to_thread(run_migrations_sync, self.settings)
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
