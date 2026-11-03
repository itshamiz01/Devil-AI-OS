from __future__ import annotations

import argparse
import asyncio
import getpass
import os

import uvicorn

from .core.auth import AuthService
from .core.config import get_settings
from .database.connection import Database


async def init_owner(username: str, password: str) -> str:
    settings = get_settings()
    db = Database(settings)
    try:
        await db.initialize()
        from .core.application import seed_core_data
        await seed_core_data(db, settings)
        return await AuthService(settings, db).bootstrap_owner(username, password)
    finally:
        await db.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="autonomus")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init-owner", help="Create or reset the local owner identity")
    init.add_argument("--username", default="owner")
    sub.add_parser("serve", help="Run the loopback backend")
    args = parser.parse_args()
    if args.command == "init-owner":
        password = getpass.getpass("Owner password (min 12 chars): ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise SystemExit("Passwords do not match")
        principal_id = asyncio.run(init_owner(args.username, password))
        print(f"Owner principal ready: {principal_id}")
    elif args.command == "serve":
        settings = get_settings()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        pid_path = settings.data_dir / "backend.pid"
        pid_path.write_text(str(os.getpid()), encoding="utf-8")
        try:
            uvicorn.run("app.main:app", host=settings.host, port=settings.port, log_config=None)
        finally:
            pid_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
