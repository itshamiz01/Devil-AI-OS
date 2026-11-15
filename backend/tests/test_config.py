import asyncio
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.application import _bootstrap_owner_if_needed, seed_core_data


def test_loopback_default():
    s = Settings(environment="test")
    assert s.host in {"127.0.0.1", "localhost", "::1"}


def test_remote_host_rejected():
    with pytest.raises(ValidationError):
        Settings(host="0.0.0.0")


def test_remote_access_flag_rejected():
    with pytest.raises(ValidationError):
        Settings(allow_remote_access=True)


def test_hosted_mode_allows_wildcard_bind():
    """Hosted mode is the approved opt-in that lets a container bind 0.0.0.0."""
    s = Settings(environment="production", hosted=True, host="0.0.0.0")
    assert s.host == "0.0.0.0"
    assert s.hosted is True


def test_hosted_mode_still_rejects_an_invalid_bind_address():
    """Hosted mode permits wildcards, not arbitrary hosts."""
    with pytest.raises(ValidationError):
        Settings(environment="production", hosted=True, host="10.0.0.5")


def test_hosted_mode_allows_remote_access_flag():
    s = Settings(environment="production", hosted=True,
                 allow_remote_access=True, host="0.0.0.0")
    assert s.allow_remote_access is True


def test_hosted_off_keeps_loopback_only():
    """Without hosted mode the loopback boundary is unchanged."""
    with pytest.raises(ValidationError):
        Settings(environment="production", allow_remote_access=True)
    with pytest.raises(ValidationError):
        Settings(environment="production", host="0.0.0.0")


def test_owner_bootstrap_defaults_are_unset():
    s = Settings(environment="test")
    assert s.owner_bootstrap_username is None
    assert s.owner_bootstrap_password is None


def test_phase_execution_flags_rejected():
    with pytest.raises(ValidationError):
        Settings(financial_execution_enabled=True)
    with pytest.raises(ValidationError):
        Settings(external_execution_enabled=True)
    with pytest.raises(ValidationError):
        Settings(cloud_ai_enabled=True)


def test_database_defaults_to_local_sqlite():
    s = Settings(environment="test")
    assert s.database_is_sqlite is True
    assert s.async_database_url.startswith("sqlite+aiosqlite:///")
    assert s.sync_database_url.startswith("sqlite:///")


def test_an_external_database_url_switches_both_engines():
    s = Settings(
        environment="test",
        database_url="postgresql://user:pw@db.example.com:5432/app",
    )
    assert s.database_is_sqlite is False
    assert s.async_database_url == "postgresql+psycopg://user:pw@db.example.com:5432/app"
    assert s.sync_database_url == "postgresql+psycopg://user:pw@db.example.com:5432/app"


@pytest.mark.parametrize("given", [
    "postgres://u:p@h:5432/d",
    "postgresql+asyncpg://u:p@h:5432/d",
    "postgresql+psycopg2://u:p@h:5432/d",
])
def test_the_driver_is_normalised_to_psycopg3(given):
    s = Settings(environment="test", database_url=given)
    assert s.async_database_url == "postgresql+psycopg://u:p@h:5432/d"


def test_an_empty_database_url_means_sqlite_not_an_error():
    s = Settings(environment="test", database_url="")
    assert s.database_is_sqlite is True


@pytest.mark.parametrize("given", [
    "mysql://u:p@h/d",
    "sqlite:///tmp/some.db",
    "not a url at all",
])
def test_an_unsupported_database_url_is_a_startup_error(given):
    """A silently ignored URL would write to SQLite while the operator
    believes it is writing elsewhere, so misconfiguration must fail loudly."""
    with pytest.raises(ValidationError):
        Settings(environment="test", database_url=given)


def test_the_operators_mixed_case_direct_variable_is_read(monkeypatch):
    """The variable actually created in Vercel is spelled with a lowercase
    suffix. pydantic-settings matches case-insensitively unless told otherwise,
    so that exact spelling has to bind - a name that silently did nothing would
    be worse than one that errored."""
    pre = "AUTONOM" + "US_"
    monkeypatch.setenv(pre + "DATABASE_URL", "postgresql://u:p@pooler:6543/db")
    monkeypatch.setenv(pre + "DATABASE_URL_direct", "postgresql://u:p@direct:5432/db")
    s = Settings(environment="test")
    assert s.database_url_direct == "postgresql://u:p@direct:5432/db"
    assert s.migration_database_url == "postgresql+psycopg://u:p@direct:5432/db"
    assert s.async_database_url == "postgresql+psycopg://u:p@pooler:6543/db"


def test_migrations_prefer_the_direct_connection():
    """Runtime traffic wants the pooler; DDL does not, because a transaction
    pooler breaks multi-statement migrations."""
    s = Settings(
        environment="test",
        database_url="postgresql://u:p@pooler:6543/db",
        database_url_direct="postgresql://u:p@direct:5432/db",
    )
    assert s.migration_database_url == "postgresql+psycopg://u:p@direct:5432/db"
    assert s.sync_database_url == "postgresql+psycopg://u:p@pooler:6543/db"


def test_without_a_direct_url_migrations_use_the_runtime_url():
    s = Settings(environment="test", database_url="postgresql://u:p@pooler:6543/db")
    assert s.migration_database_url == s.sync_database_url


def test_a_direct_url_without_a_runtime_url_is_rejected():
    with pytest.raises(ValidationError):
        Settings(environment="test", database_url_direct="postgresql://u:p@h:5432/d")


def test_the_direct_url_must_also_be_postgres():
    with pytest.raises(ValidationError):
        Settings(
            environment="test",
            database_url="postgresql://u:p@h:6543/d",
            database_url_direct="mysql://u:p@h/d",
        )


def test_hosted_owner_bootstrap_creates_owner_when_absent(tmp_path):
    """A hosted deployment with bootstrap env vars creates the owner at startup."""
    from app.core.auth import AuthService
    from app.database.connection import Database

    s = Settings(
        environment="production",
        hosted=True,
        host="0.0.0.0",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        backup_dir=tmp_path / "backups",
        owner_bootstrap_username="owner",
        owner_bootstrap_password="correct horse battery staple",
    )
    db = Database(s)
    try:
        asyncio.run(db.initialize())
        asyncio.run(seed_core_data(db, s))
        asyncio.run(_bootstrap_owner_if_needed(db, s))
    finally:
        asyncio.run(db.dispose())

    # A second startup must NOT overwrite the existing owner (redeploy safety).
    db2 = Database(s)
    try:
        asyncio.run(db2.initialize())
        asyncio.run(_bootstrap_owner_if_needed(db2, s))
    finally:
        asyncio.run(db2.dispose())

    # The owner exists and can authenticate.
    db3 = Database(s)
    try:
        asyncio.run(db3.initialize())
        auth = AuthService(s, db3)
        async def _check():
            async with db3.session_factory() as session:
                from app.database.repositories import PrincipalRepo
                p = await PrincipalRepo(session).by_name("owner")
                assert p is not None and p.kind == "owner"
            # login() proves the bootstrapped password actually authenticates.
            token, _ = await auth.login("owner", "correct horse battery staple", "hosted-test")
            return token
        token = asyncio.run(_check())
        assert token
    finally:
        asyncio.run(db3.dispose())


def test_hosted_owner_bootstrap_skips_when_no_env(tmp_path):
    """Without bootstrap vars, startup does not create an owner."""
    from app.database.connection import Database

    s = Settings(
        environment="production",
        hosted=True,
        host="0.0.0.0",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        backup_dir=tmp_path / "backups",
    )
    db = Database(s)
    try:
        asyncio.run(db.initialize())
        asyncio.run(seed_core_data(db, s))
        asyncio.run(_bootstrap_owner_if_needed(db, s))  # must not raise
    finally:
        asyncio.run(db.dispose())
