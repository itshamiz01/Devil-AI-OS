#!/usr/bin/env python
"""Apply the Devil-AI-OS schema to a Supabase (or any Postgres) database.

This is the reproducible, repeatable way to put the schema on a hosted
Postgres. It runs the application's own Alembic migration chain against the
``AUTONOMUS_DATABASE_URL`` (or a ``--url`` argument), using the exact same
migrations the app runs on startup. It is idempotent: if the schema is already
at head, it connects, confirms the version, and exits cleanly.

Use the **direct** (non-pooled) connection string, not the transaction-pooler
one. A transaction pooler breaks multi-statement DDL, so migrations must go
through a direct connection. Supabase exposes both; pick the port-5432 direct
connection for this script (and for ``AUTONOMUS_DATABASE_URL_direct``).

Usage:
    # From the repository root, with the backend virtualenv active:
    AUTONOMUS_DATABASE_URL="postgresql://postgres:PASSWORD@db.REF.supabase.co:5432/postgres" \
        python scripts/supabase_migrate.py

    # Or pass it explicitly:
    python scripts/supabase_migrate.py --url "postgresql://postgres:PASSWORD@db.REF.supabase.co:5432/postgres"

The script prints the alembic_version and the Devil-AI-OS table count after
applying, so a successful run is verifiable without opening a database client.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# The script lives at <repo>/scripts/; the backend (with alembic.ini and the
# app package) is one level up in <repo>/backend.
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402


def _normalise_url(url: str) -> str:
    """Normalise a Postgres URL to the psycopg3 driver the app uses.

    Mirrors the app's own normalisation so the script and the runtime agree on
    the driver. Supabase connection strings use ``postgresql://``; the app
    normalises that to ``postgresql+psycopg://``.
    """
    url = url.strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql+psycopg://" + url[len("postgresql+psycopg2://"):]
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + url[len("postgresql+asyncpg://"):]
    raise SystemExit(
        f"Refusing to migrate: {url!r} is not a Postgres URL. "
        "Use the Supabase direct connection string (postgresql://...)."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=None,
        help="Postgres connection string. Defaults to AUTONOMUS_DATABASE_URL.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Connect and report the current schema state without applying migrations.",
    )
    args = parser.parse_args()

    import os
    url = args.url or os.environ.get("AUTONOMUS_DATABASE_URL", "")
    if not url:
        raise SystemExit(
            "No database URL. Set AUTONOMUS_DATABASE_URL or pass --url with "
            "the Supabase direct connection string."
        )
    pg_url = _normalise_url(url)

    # Verify connectivity before touching the schema, so a bad URL fails fast
    # with a clear message rather than halfway through a migration.
    engine = create_engine(pg_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"Connected to {pg_url.split('@')[-1]}")
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Could not connect to the database: {exc}")

    if args.check_only:
        with engine.connect() as conn:
            try:
                version = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
            except Exception:  # noqa: BLE001
                version = "(no alembic_version table - schema not applied)"
            count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name IN "
                    "('permissions','principals','agents','tasks','workforce_employees',"
                    "'workforce_departments','workforce_work_orders','execution_tools',"
                    "'opportunities','missions','alembic_version')"
                )
            ).scalar_one()
        print(f"alembic_version: {version}")
        print(f"Devil-AI-OS key tables present: {count}/11")
        if version == "a117e3f0b9c2":
            print("Schema is at head. No migration needed.")
            return 0
        raise SystemExit("Schema is not at head. Run without --check-only to migrate.")

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", pg_url)
    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        version = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    print(f"Migration complete. alembic_version: {version}")
    print("Schema applied to the database via the application's Alembic chain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
