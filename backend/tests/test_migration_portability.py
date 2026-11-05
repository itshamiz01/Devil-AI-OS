"""The chain must render for Postgres as well as run on SQLite.

SQLite always takes Alembic's batch path, so a keyword that batch mode accepts
and Postgres rejects is invisible to every other test in this suite. Rendering
the chain offline against a ``postgresql+psycopg://`` URL exercises the
non-batch branch without needing a server.
"""
import contextlib
import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[1]


def _render(url: str) -> str:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        command.upgrade(cfg, "head", sql=True)
    return buf.getvalue()


@pytest.fixture(scope="module")
def postgres_sql() -> str:
    return _render("postgresql+psycopg://postgres:postgres@localhost:5433/devil")


def test_the_whole_chain_renders_without_dialect_errors(postgres_sql):
    """A TypeError here means a shim call Postgres cannot execute."""
    assert "CREATE TABLE alembic_version" in postgres_sql
    assert postgres_sql.count("CREATE TABLE ") == 44   # 43 tables + version


def test_no_sqlite_only_statements_reach_postgres(postgres_sql):
    assert "PRAGMA" not in postgres_sql
    assert "AUTOINCREMENT" not in postgres_sql


def test_every_p_04_table_is_created(postgres_sql):
    for table in ("agent_templates", "agent_template_versions", "agent_capabilities",
                  "agent_permissions", "agent_assignments", "agent_health",
                  "agent_metrics", "agent_configuration_history",
                  "agent_creation_requests"):
        assert f"CREATE TABLE {table} " in postgres_sql, table


def test_the_agents_extension_renders_as_plain_ddl(postgres_sql):
    for column in ("template_id", "template_version", "configuration_version",
                   "parent_agent_id", "business_id", "retired_at"):
        assert f"ALTER TABLE agents ADD COLUMN {column} " in postgres_sql, column
    assert "ALTER TABLE agents ADD CONSTRAINT fk_agents_template_id" in postgres_sql
    assert "ALTER TABLE agents ADD CONSTRAINT fk_agents_parent_agent_id" in postgres_sql


def test_the_lifecycle_check_and_default_are_applied(postgres_sql):
    assert "ADD CONSTRAINT ck_agents_status_lifecycle CHECK" in postgres_sql
    assert "ALTER TABLE agents ALTER COLUMN status SET DEFAULT" in postgres_sql
    assert "UPDATE agents SET status='ACTIVE'" in postgres_sql


def test_batch_mode_is_not_used_on_postgres(postgres_sql):
    """Batch would rebuild a table per operation; the render must be direct.

    ``agents`` is created exactly once, by the P-01 revision, and is never
    dropped and rebuilt by the P-04 extension.
    """
    assert postgres_sql.count("CREATE TABLE agents ") == 1
    assert "DROP TABLE agents" not in postgres_sql


def test_the_chain_is_eight_revisions_deep(postgres_sql):
    """One INSERT for the base revision, one UPDATE per revision after it.

    This count is deliberately brittle: it is the one assertion that notices a
    revision was added without its DDL being reviewed. Deriving it from the
    revision count would defeat the purpose, so it is bumped by hand, by whoever
    added the revision.

    Last reviewed for `e8b2ced758fc` (P-04 Stage 5), whose DDL is hand-written
    because autogenerate renders neither a CHECK addition nor a `server_default`
    change on an existing column (L-56): it detected only the two added columns.
    """
    assert postgres_sql.count("INSERT INTO alembic_version") == 1
    assert postgres_sql.count("UPDATE alembic_version") == 7


def test_the_shim_implements_every_batch_method_the_chain_uses():
    """A revision calling a method the shim lacks fails at migration time.

    Found the hard way: Stage 4 called ``create_unique_constraint``, which the
    batch proxy did not implement, so ``upgrade head`` raised ``AttributeError``
    partway through the revision - on SQLite *after* the preceding ADD COLUMN
    had already been applied, because SQLite DDL is non-transactional. Scanning
    the revisions for ``batch_op.<method>(`` catches that before it can run.
    """
    import re

    from app.database.migrations.portable import _PortableTable

    versions = BACKEND / "app/database/migrations/versions"
    used: set[str] = set()
    for revision in sorted(versions.glob("*.py")):
        used.update(re.findall(r"batch_op\.([a-zA-Z_]+)\(", revision.read_text()))
    assert used, "no batch_op calls found - is the scan pattern still correct?"
    missing = sorted(m for m in used if not hasattr(_PortableTable, m))
    assert not missing, f"portable shim is missing: {missing}"


def test_the_stage_3_template_changes_render_for_postgres(postgres_sql):
    assert ("ALTER TABLE agent_template_versions ADD COLUMN "
            "validation_details_json") in postgres_sql
    assert "ADD CONSTRAINT ck_agent_templates_status CHECK" in postgres_sql
    assert ("ADD CONSTRAINT ck_agent_template_versions_validation_status "
            "CHECK") in postgres_sql
    # The server defaults the models declare, which Stage 2's revision omitted.
    assert "ALTER TABLE agents ALTER COLUMN status SET DEFAULT" in postgres_sql
    assert "ALTER COLUMN validation_status SET DEFAULT" in postgres_sql


def test_the_stage_4_creation_request_changes_render_for_postgres(postgres_sql):
    assert ("ALTER TABLE agent_creation_requests ADD COLUMN "
            "idempotency_key") in postgres_sql
    assert "ADD CONSTRAINT uq_agent_creation_requests_idempotency_key UNIQUE" in postgres_sql
    assert "ADD CONSTRAINT ck_agent_creation_requests_decision CHECK" in postgres_sql
    assert ("ADD CONSTRAINT ck_agent_creation_requests_approval_status "
            "CHECK") in postgres_sql
    assert "ALTER COLUMN approval_status SET DEFAULT" in postgres_sql
