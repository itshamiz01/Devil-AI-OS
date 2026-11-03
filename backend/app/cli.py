from __future__ import annotations

import argparse
import asyncio
import getpass
import os
from pathlib import Path

import uvicorn

from .core.auth import AuthService
from .core.config import get_settings
from .database.backup import BackupError, create_backup, list_backups, restore_backup, verify_backup
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
    sub.add_parser("backup", help="Create a verified database backup")
    sub.add_parser("list-backups", help="List existing backups, newest first")
    restore = sub.add_parser("restore", help="Restore the database from a verified backup")
    restore.add_argument("--from", dest="source", required=True, help="Backup file to restore")
    restore.add_argument("--yes", action="store_true", help="Skip the interactive confirmation")
    restore.add_argument(
        "--assume-stopped", action="store_true",
        help="Proceed even though a backend pid file exists; use only when you have confirmed it is stale",
    )
    args = parser.parse_args()
    if args.command == "init-owner":
        password = getpass.getpass("Owner password (min 12 chars): ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise SystemExit("Passwords do not match")
        principal_id = asyncio.run(init_owner(args.username, password))
        print(f"Owner principal ready: {principal_id}")
    elif args.command == "backup":
        try:
            result = create_backup(get_settings())
        except BackupError as exc:
            raise SystemExit(f"Backup failed: {exc}")
        print(f"Backup created: {result.path} ({result.size_bytes} bytes, integrity ok, {len(result.tables)} tables)")
        if result.pruned:
            print(f"Pruned {len(result.pruned)} older backup(s) past the retention limit")
    elif args.command == "list-backups":
        backups = list_backups(get_settings())
        if not backups:
            print("No backups found")
        for b in backups:
            ok, tables = verify_backup(b)
            print(f"{'VERIFIED ' if ok else 'INVALID  '} {b.name} ({b.stat().st_size} bytes, {len(tables)} tables)")
    elif args.command == "restore":
        settings = get_settings()
        source = Path(args.source)
        ok, _ = verify_backup(source)
        if not ok:
            raise SystemExit(f"Refusing to restore: {source} failed integrity or schema verification")
        if not args.yes:
            answer = input(f"This OVERWRITES {settings.database_path} with {source.name}. Type RESTORE to continue: ")
            if answer.strip() != "RESTORE":
                raise SystemExit("Restore cancelled")
        try:
            outcome = restore_backup(settings, source, assume_stopped=args.assume_stopped)
        except BackupError as exc:
            raise SystemExit(f"Restore failed: {exc}")
        print(f"Restored {outcome['database']} from {outcome['restored_from']}")
        if outcome["preserved_previous_at"]:
            print(f"Previous database preserved at {outcome['preserved_previous_at']}")
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
