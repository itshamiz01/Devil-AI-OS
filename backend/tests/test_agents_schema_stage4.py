"""P-04 Stage 4 schema: the creation ledger's new column, keys and vocabularies.

Stage 4 adds an idempotency key and two column CHECKs to
``agent_creation_requests``, which ``approvals`` references by foreign key and
which already holds rows in any deployment that ran Stage 2. The interesting
questions are the same ones Stage 3 had to answer: do the rows survive the
SQLite batch rebuild, do the references survive it, and does the new constraint
actually refuse a bad value once the migration has run rather than only in the
ORM's opinion of itself.

Every assertion here is against a populated database, because an empty one
proves nothing about preservation.
"""
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[1]
#: The Stage 3 head. Pinned rather than derived from "head minus one" so that
#: adding Stage 5's revision cannot silently move what this file proves.
STAGE3_HEAD = "e4817dfb6c0c"
STAGE4_HEAD = "d0db25c9da23"


def _alembic(db_path: Path) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _seed(con: sqlite3.Connection, table: str, given: dict) -> None:
    """Insert a row satisfying every NOT NULL column, read from PRAGMA.

    Raw SQL bypasses the ORM's Python-side defaults, so anything not given here
    is filled from the declared type; deriving it keeps the seed correct if these
    tables grow again.
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
    """A Stage-3 database holding a creation request and its approval."""
    db = tmp_path / "stage3.db"
    command.upgrade(_alembic(db), STAGE3_HEAD)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    _seed(con, "principals", {"id": "p1", "kind": "owner", "name": "owner", "active": 1})
    _seed(con, "agent_templates", {"id": "t1", "name": "researcher", "category": "research",
                                   "description": "d", "current_version": 1,
                                   "status": "published"})
    _seed(con, "approvals", {"id": "ap1", "requester_id": "p1", "action": "agent.create",
                             "resource": "cr1", "risk": "high", "reason": "r",
                             "payload_hash": "x" * 64, "status": "pending",
                             "expires_at": "2030-01-01"})
    _seed(con, "agent_creation_requests", {
        "id": "cr1", "requested_template_id": "t1", "justification": "needed",
        "requested_capabilities": '["research.read"]', "resource_estimate": "{}",
        "decision": "CREATE_AGENT", "approval_status": "pending", "approval_id": "ap1"})
    con.commit()
    con.close()
    return db


_TABLES = ("principals", "agent_templates", "approvals", "agent_creation_requests")


def test_the_stage_4_revision_is_the_head_of_a_seven_deep_chain():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app/database/migrations"))
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(cfg)
    revisions = [s.revision for s in script.walk_revisions()]
    assert script.get_current_head() == STAGE4_HEAD
    assert len(revisions) == 7, revisions


def test_the_rebuild_preserves_rows_and_every_reference(populated):
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    con.execute("PRAGMA foreign_keys=ON")
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _TABLES}
    violations = con.execute("PRAGMA foreign_key_check").fetchall()
    approval_id = con.execute(
        "SELECT approval_id FROM agent_creation_requests WHERE id='cr1'").fetchone()[0]
    decision, status = con.execute(
        "SELECT decision, approval_status FROM agent_creation_requests "
        "WHERE id='cr1'").fetchone()
    con.close()
    assert counts == {t: 1 for t in _TABLES}, counts
    assert violations == []
    assert approval_id == "ap1"
    # The stored decision must survive verbatim: rewriting history here would
    # make the ledger unusable as evidence.
    assert (decision, status) == ("CREATE_AGENT", "pending")


def test_the_new_column_and_its_default_land(populated):
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    cols = {r[1]: r for r in con.execute("PRAGMA table_info(agent_creation_requests)")}
    ddl = con.execute("SELECT sql FROM sqlite_master WHERE name='agent_creation_requests'"
                      ).fetchone()[0]
    con.close()
    assert "idempotency_key" in cols
    assert cols["approval_status"][4] == "'not_required'"
    for name in ("ck_agent_creation_requests_decision",
                 "ck_agent_creation_requests_approval_status",
                 "uq_agent_creation_requests_idempotency_key"):
        assert name in ddl, name


def test_the_server_default_applies_to_a_row_that_omits_the_column(populated):
    """A caller that does not know about approval_status still gets a valid one."""
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    con.execute("INSERT INTO agent_creation_requests (id, requested_role, justification,"
                " requested_capabilities, resource_estimate, created_at, updated_at)"
                " VALUES ('cr9','r','j','[]','{}','2026-01-01','2026-01-01')")
    con.commit()
    assert con.execute("SELECT approval_status FROM agent_creation_requests"
                       " WHERE id='cr9'").fetchone()[0] == "not_required"
    assert con.execute("SELECT decision IS NULL FROM agent_creation_requests"
                       " WHERE id='cr9'").fetchone()[0] == 1
    con.close()


@pytest.mark.parametrize("statement", [
    "UPDATE agent_creation_requests SET decision='MAYBE' WHERE id='cr1'",
    "UPDATE agent_creation_requests SET approval_status='perhaps' WHERE id='cr1'",
])
def test_the_vocabularies_are_enforced_at_the_column(populated, statement):
    """The service checks these too; the column is the last line, and it is the
    one that holds when a future caller forgets the service."""
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(statement)
    con.close()


def test_a_duplicate_idempotency_key_is_refused_but_nulls_coexist(populated):
    """The key exists to make a retry safe, so NULL must stay allowed: a request
    that did not claim a key cannot collide with one that did not either."""
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    insert = ("INSERT INTO agent_creation_requests (id, idempotency_key, requested_role,"
              " justification, requested_capabilities, resource_estimate, approval_status,"
              " created_at, updated_at) VALUES ({id}, {key}, 'r', 'j', '[]', '{{}}',"
              " 'not_required', '2026-01-01', '2026-01-01')")
    con.execute(insert.format(id="'cr2'", key="'same-key'"))
    con.commit()
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(insert.format(id="'cr3'", key="'same-key'"))
    con.execute(insert.format(id="'cr4'", key="NULL"))
    con.execute(insert.format(id="'cr5'", key="NULL"))
    con.commit()
    # cr1 from the fixture never claimed a key, and neither did cr4 or cr5.
    assert con.execute("SELECT COUNT(*) FROM agent_creation_requests WHERE"
                       " idempotency_key IS NULL").fetchone()[0] == 3
    con.close()


def test_a_legacy_value_outside_the_vocabulary_does_not_block_the_upgrade(tmp_path):
    """Stage 2 created these columns without a vocabulary, so a real database can
    hold a value the new CHECK would reject. Adding the constraint anyway fails
    mid-rebuild on SQLite and leaves the database half-migrated; the revision
    normalizes first, and this proves it."""
    db = tmp_path / "legacy.db"
    command.upgrade(_alembic(db), STAGE3_HEAD)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    _seed(con, "principals", {"id": "p1", "kind": "owner", "name": "owner", "active": 1})
    # approval_status left out on purpose: the seeder fills a NOT NULL column it
    # was not given with an empty string, which is exactly the legacy shape.
    _seed(con, "agent_creation_requests", {
        "id": "legacy1", "requested_role": "research", "justification": "old row",
        "requested_capabilities": "[]", "resource_estimate": "{}",
        "decision": "MAKE_ONE_UP"})
    con.commit()
    before = con.execute("SELECT approval_status, decision FROM agent_creation_requests"
                         " WHERE id='legacy1'").fetchone()
    con.close()
    assert before[0] not in ("not_required", "pending", "granted", "rejected", "expired")

    command.upgrade(_alembic(db), "head")

    con = sqlite3.connect(db)
    after = con.execute("SELECT approval_status, decision FROM agent_creation_requests"
                        " WHERE id='legacy1'").fetchone()
    rows = con.execute("SELECT COUNT(*) FROM agent_creation_requests").fetchone()[0]
    con.close()
    assert rows == 1, "the row must survive, not be dropped to satisfy the constraint"
    assert after[0] == "not_required"
    assert after[1] is None, "an unrecognized decision is cleared, not guessed at"


def test_the_stage_4_revision_is_reversible_over_the_same_rows(populated):
    cfg = _alembic(populated)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, STAGE3_HEAD)
    con = sqlite3.connect(populated)
    con.execute("PRAGMA foreign_keys=ON")
    cols = [r[1] for r in con.execute("PRAGMA table_info(agent_creation_requests)")]
    ddl = con.execute("SELECT sql FROM sqlite_master WHERE name='agent_creation_requests'"
                      ).fetchone()[0]
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _TABLES}
    violations = con.execute("PRAGMA foreign_key_check").fetchall()
    con.close()
    assert "idempotency_key" not in cols
    for name in ("ck_agent_creation_requests_decision",
                 "uq_agent_creation_requests_idempotency_key"):
        assert name not in ddl, name
    assert counts == {t: 1 for t in _TABLES}, counts
    assert violations == []
    # And it can be applied again, which is what a rollback-then-retry needs.
    command.upgrade(cfg, "head")


def test_the_decision_vocabulary_in_code_and_in_the_column_agree():
    """The enum, the tuple the CHECK is built from and the rendered DDL are three
    places one vocabulary can drift. They are compared rather than assumed."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    from app.agents.schemas import CREATION_DECISIONS, CREATION_APPROVAL_STATUSES
    from app.agents.schemas import CreationDecision
    from app.database.models import Base

    assert CREATION_DECISIONS == tuple(d.value for d in CreationDecision)
    assert len(CREATION_DECISIONS) == 6
    assert len(CREATION_APPROVAL_STATUSES) == 5
    ddl = str(CreateTable(Base.metadata.tables["agent_creation_requests"])
              .compile(dialect=postgresql.dialect()))
    for value in CREATION_DECISIONS + CREATION_APPROVAL_STATUSES:
        assert f"'{value}'" in ddl, value
