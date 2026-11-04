"""P-04 Stage 3 schema: the template vocabularies and the rebuild they need.

Stage 3 alters ``agent_templates``, which three other tables reference by
foreign key. On SQLite that alter runs through Alembic's batch mode, which
rebuilds the table, so the interesting question is not whether the constraint
lands but whether the rows and the references survive. These tests answer it
against a populated database rather than an empty one.
"""
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[1]
STAGE2_HEAD = "3013ebdd2699"


def _alembic(db_path: Path) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _seed(con: sqlite3.Connection, table: str, given: dict) -> None:
    """Insert a row satisfying every NOT NULL column, read from PRAGMA.

    Raw SQL bypasses the ORM's Python-side defaults, so anything not given here
    has to be filled from the declared type; deriving it keeps the seed correct
    if these tables grow again.
    """
    names, values = [], []
    for _cid, name, ctype, notnull, _dflt, _pk in con.execute(f"PRAGMA table_info({table})"):
        if name in given:
            names.append(name); values.append(repr(given[name])); continue
        if notnull:
            kind = ctype.upper()
            if kind in ("INTEGER", "FLOAT", "NUMERIC", "BOOLEAN"):
                values.append("0")
            elif kind.startswith("DATETIME"):
                values.append("'2026-01-01'")
            elif name.endswith("_json") or name in ("payload", "configuration_json"):
                values.append("'{}'")
            else:
                values.append("''")
            names.append(name)
    con.execute(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join(values)})")


@pytest.fixture()
def populated(tmp_path) -> Path:
    """A Stage-2 database holding a template and everything that points at it."""
    db = tmp_path / "stage2.db"
    command.upgrade(_alembic(db), STAGE2_HEAD)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    _seed(con, "principals", {"id": "p1", "kind": "owner", "name": "owner", "active": 1})
    _seed(con, "agent_templates", {"id": "t1", "name": "researcher", "category": "research",
                                   "description": "d", "current_version": 1,
                                   "status": "published"})
    _seed(con, "agent_template_versions", {
        "id": "v1", "template_id": "t1", "version": 1,
        "configuration_json": '{"role_definition": "r", "mission": "m"}',
        "validation_status": "valid", "created_by": "p1"})
    _seed(con, "agents", {"id": "a1", "principal_id": "p1", "name": "built-from-t1",
                          "role": "research", "status": "ACTIVE", "metadata_json": "{}",
                          "template_id": "t1", "template_version": 1,
                          "configuration_version": 1})
    _seed(con, "agent_creation_requests", {"id": "cr1", "requested_template_id": "t1",
                                           "justification": "needed"})
    con.commit()
    con.close()
    return db


_TABLES = ("agent_templates", "agent_template_versions", "agents",
           "agent_creation_requests")


def test_the_rebuild_preserves_rows_and_every_reference(populated):
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    con.execute("PRAGMA foreign_keys=ON")
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _TABLES}
    assert counts == {t: 1 for t in _TABLES}, counts
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert con.execute("SELECT template_id FROM agents WHERE id='a1'").fetchone()[0] == "t1"
    assert con.execute(
        "SELECT template_id FROM agent_template_versions WHERE id='v1'").fetchone()[0] == "t1"
    assert con.execute(
        "SELECT requested_template_id FROM agent_creation_requests WHERE id='cr1'"
    ).fetchone()[0] == "t1"
    con.close()


def test_the_new_column_and_both_defaults_land(populated):
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    version_cols = {r[1]: r for r in con.execute("PRAGMA table_info(agent_template_versions)")}
    template_cols = {r[1]: r for r in con.execute("PRAGMA table_info(agent_templates)")}
    con.close()
    assert "validation_details_json" in version_cols
    assert version_cols["validation_status"][4] == "'unvalidated'"
    assert template_cols["status"][4] == "'draft'"


@pytest.mark.parametrize("statement", [
    "UPDATE agent_templates SET status='banana' WHERE id='t1'",
    "INSERT INTO agent_templates (id, name, category, description, current_version,"
    " status, created_at, updated_at) VALUES ('t2', 'x', 'c', '', 0, 'retired',"
    " '2026-01-01', '2026-01-01')",
    "UPDATE agent_template_versions SET validation_status='maybe' WHERE id='v1'",
    "INSERT INTO agent_template_versions (id, template_id, version, configuration_json,"
    " validation_status, created_at, updated_at) VALUES ('v2', 't1', 2, '{}',"
    " 'approved', '2026-01-01', '2026-01-01')",
])
def test_the_vocabularies_are_enforced_at_the_column(populated, statement):
    """Service code checks these too; the column is the last line, and it is the
    one that holds when a future caller forgets the service."""
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(statement)
    con.close()


def test_a_null_verdict_details_is_allowed_and_a_valid_one_round_trips(populated):
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    assert con.execute(
        "SELECT validation_details_json FROM agent_template_versions WHERE id='v1'"
    ).fetchone()[0] is None
    con.execute("UPDATE agent_template_versions SET validation_details_json="
                "'{\"issues\": []}' WHERE id='v1'")
    con.commit()
    assert con.execute(
        "SELECT validation_details_json FROM agent_template_versions WHERE id='v1'"
    ).fetchone()[0] == '{"issues": []}'
    con.close()


def test_the_stage_3_revision_is_reversible_over_the_same_rows(populated):
    cfg = _alembic(populated)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, STAGE2_HEAD)
    con = sqlite3.connect(populated)
    con.execute("PRAGMA foreign_keys=ON")
    cols = [r[1] for r in con.execute("PRAGMA table_info(agent_template_versions)")]
    ddl = con.execute(
        "SELECT sql FROM sqlite_master WHERE name='agent_templates'").fetchone()[0]
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _TABLES}
    violations = con.execute("PRAGMA foreign_key_check").fetchall()
    con.close()
    assert "validation_details_json" not in cols
    assert "ck_agent_templates_status" not in ddl
    assert counts == {t: 1 for t in _TABLES}, counts
    assert violations == []
    # And it can be applied again, which is what a rollback-then-retry needs.
    command.upgrade(cfg, "head")
