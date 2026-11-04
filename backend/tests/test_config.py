import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_loopback_default():
    s = Settings(environment="test")
    assert s.host in {"127.0.0.1", "localhost", "::1"}


def test_remote_host_rejected():
    with pytest.raises(ValidationError):
        Settings(host="0.0.0.0")


def test_remote_access_flag_rejected():
    with pytest.raises(ValidationError):
        Settings(allow_remote_access=True)


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
