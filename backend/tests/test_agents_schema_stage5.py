"""P-04 Stage 5 schema: the capability and grant vocabularies, closed.

Stage 2 created ``agent_capabilities`` and ``agent_permissions`` with an
``approval_level`` CHECK and nothing else. Three columns were free text and four
had Python-side defaults only, so a raw insert - a restore, a script, a future
service that does not go through the ORM - could store a risk level nobody
recognises or an empty access class. Stage 5 governs those columns, so this file
proves the migration closes them.

Four questions, each answered against a database that already holds rows, because
an empty one proves nothing:

1. do the rows and their foreign keys survive the SQLite batch rebuild;
2. are the legacy values that the new CHECKs would reject **normalized first** -
   the failure mode Stage 4 established, where a constraint existing rows violate
   fails partway through non-transactional DDL and leaves a half-migrated
   database;
3. do the CHECKs actually refuse a bad value once the migration has run, rather
   than only in the ORM's opinion of itself;
4. does the downgrade remove exactly what the upgrade added, and no more.
"""
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[1]
#: Pinned rather than derived from "head" or "head minus one", so that adding
#: Stage 6's revision cannot silently move what this file proves.
STAGE4_HEAD = "d0db25c9da23"
STAGE5_HEAD = "e8b2ced758fc"

#: The vocabularies the migration closes, read here as the migration states them.
RISK_LEVELS = ("low", "medium", "high", "critical")
ACCESS_CLASSES = ("read", "write", "execute")
GRANT_STATUSES = ("pending", "active", "revoked", "expired")


def _alembic(db_path: Path) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _columns(con: sqlite3.Connection, table: str) -> list[tuple]:
    return list(con.execute(f"PRAGMA table_info({table})"))


def _fill(ctype: str, name: str) -> str:
    kind = ctype.upper()
    if kind in ("INTEGER", "FLOAT", "NUMERIC", "BOOLEAN"):
        return "0"
    if kind.startswith("DATETIME"):
        return "'2026-01-01'"
    if name.endswith("_json"):
        return "'{}'"
    return "''"


def _seed(con: sqlite3.Connection, table: str, given: dict) -> None:
    """Insert a row satisfying every NOT NULL column, read from PRAGMA."""
    names, values = [], []
    for _cid, name, ctype, notnull, _dflt, _pk in _columns(con, table):
        if name in given:
            names.append(name); values.append(repr(given[name])); continue
        if notnull:
            names.append(name); values.append(_fill(ctype, name))
    con.execute(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join(values)})")


def _insert_omitting(con: sqlite3.Connection, table: str, given: dict,
                     omit: set[str]) -> None:
    """Insert while leaving ``omit`` to their server defaults.

    A column with no server default still has to be supplied, or the insert fails
    for a reason that has nothing to do with the default under test.
    """
    names, values = [], []
    for _cid, name, ctype, notnull, dflt, _pk in _columns(con, table):
        if name in omit:
            continue
        if name in given:
            names.append(name); values.append(repr(given[name])); continue
        if notnull and dflt is None:
            names.append(name); values.append(_fill(ctype, name))
    con.execute(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join(values)})")


def _table_sql(con: sqlite3.Connection, table: str) -> str:
    row = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                      (table,)).fetchone()
    return row[0] if row else ""


def _base_rows(con: sqlite3.Connection, *, capability_values: dict,
               grant_status: str) -> None:
    """A principal, an agent, a capability and one grant pointing at both."""
    _seed(con, "principals", {"id": "p1", "kind": "owner", "name": "owner", "active": 1})
    _seed(con, "agents", {"id": "a1", "principal_id": "p1", "name": "agent-1",
                          "role": "researcher", "status": "ACTIVE"})
    capability = {"id": "c1", "capability_key": "research.read", "name": "Read research",
                  "category": "research", "approval_level": 0}
    capability.update(capability_values)
    _seed(con, "agent_capabilities", capability)
    _seed(con, "agent_permissions", {"id": "g1", "agent_id": "a1", "capability_id": "c1",
                                     "approval_level": 0, "status": grant_status,
                                     "scope": "evidence/*"})


@pytest.fixture()
def populated(tmp_path) -> Path:
    """A Stage-4 database holding values the new CHECKs already accept."""
    db = tmp_path / "stage4.db"
    command.upgrade(_alembic(db), STAGE4_HEAD)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    _base_rows(con, capability_values={"risk_level": "low", "access_class": "read",
                                       "description": "reads research", "enabled": 1},
               grant_status="active")
    con.commit(); con.close()
    return db


@pytest.fixture()
def legacy(tmp_path) -> Path:
    """A Stage-4 database holding values the new CHECKs would reject.

    This is the fixture that matters. Adding a CHECK over existing rows is what
    breaks ``upgrade head`` on a populated legacy database, and on SQLite the
    violation surfaces during the batch rebuild's INSERT-SELECT, partway through
    non-transactional DDL - which is how a database ends up half-migrated.
    """
    db = tmp_path / "legacy.db"
    command.upgrade(_alembic(db), STAGE4_HEAD)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    _base_rows(con, capability_values={"risk_level": "EXTREME", "access_class": "destroy",
                                       "description": "legacy row", "enabled": 1},
               grant_status="banana")
    con.commit()
    # Prove the fixture really holds values the new CHECKs would refuse.
    assert con.execute("SELECT risk_level FROM agent_capabilities").fetchone()[0] == "EXTREME"
    assert con.execute("SELECT status FROM agent_permissions").fetchone()[0] == "banana"
    con.close()
    return db


# --------------------------------------------------------------------------- #
# The chain
# --------------------------------------------------------------------------- #
def test_the_stage_5_revision_is_the_head_of_an_eight_deep_chain():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app/database/migrations"))
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(cfg)
    revisions = [s.revision for s in script.walk_revisions()]
    assert script.get_current_head() == STAGE5_HEAD
    assert len(revisions) == 8, revisions
    assert revisions[1] == STAGE4_HEAD, "Stage 5 must sit directly on Stage 4"


# --------------------------------------------------------------------------- #
# Preservation
# --------------------------------------------------------------------------- #
def test_upgrade_preserves_rows_and_every_reference(populated):
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    con.execute("PRAGMA foreign_keys=ON")
    assert con.execute("SELECT COUNT(*) FROM agent_capabilities").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM agent_permissions").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM agents").fetchone()[0] == 1
    # The grant still points at the agent and the capability it pointed at before:
    # a batch rebuild that dropped a reference would leave the row and lose the link.
    assert con.execute(
        "SELECT agent_id, capability_id, scope FROM agent_permissions").fetchone() == (
        "a1", "c1", "evidence/*")
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()


def test_legacy_values_are_normalized_rather_than_rejected(legacy):
    """The upgrade must succeed on a database that already violates the new CHECKs,
    and must map each unrecognized value to the safest member of its vocabulary
    rather than dropping the row."""
    command.upgrade(_alembic(legacy), "head")
    con = sqlite3.connect(legacy)
    con.execute("PRAGMA foreign_keys=ON")
    risk, access = con.execute(
        "SELECT risk_level, access_class FROM agent_capabilities").fetchone()
    assert risk == "medium", "an unrecognized risk must not become 'low'"
    assert access == "read", "an unrecognized access class must not become 'execute'"
    assert con.execute("SELECT status FROM agent_permissions").fetchone()[0] == "active"
    assert con.execute("SELECT COUNT(*) FROM agent_capabilities").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM agent_permissions").fetchone()[0] == 1
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()


def test_values_inside_the_vocabulary_are_left_alone(populated):
    """Normalization must correct, not overwrite: 'low' stays 'low'."""
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    assert con.execute(
        "SELECT risk_level, access_class FROM agent_capabilities").fetchone() == (
        "low", "read")
    con.close()


# --------------------------------------------------------------------------- #
# The constraints bite
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("column,value,constraint", [
    ("risk_level", "extreme", "ck_agent_capabilities_risk_level"),
    ("access_class", "destroy", "ck_agent_capabilities_access_class"),
    ("approval_level", 4, "ck_agent_capabilities_approval_level"),
])
def test_the_capability_checks_refuse_a_bad_value(populated, column, value, constraint):
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        _seed(con, "agent_capabilities",
              {"id": "bad", "capability_key": "bad.one", "name": "Bad", "category": "x",
               "risk_level": "low", "access_class": "read", "approval_level": 0,
               column: value})
    assert constraint in str(excinfo.value), str(excinfo.value)
    con.close()


def test_the_grant_status_check_refuses_a_bad_value(populated):
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        _seed(con, "agent_permissions",
              {"id": "bad", "agent_id": "a1", "capability_id": "c1",
               "approval_level": 0, "status": "banana"})
    assert "ck_agent_permissions_status" in str(excinfo.value), str(excinfo.value)
    con.close()


def test_a_duplicate_capability_key_is_refused(populated):
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    with pytest.raises(sqlite3.IntegrityError):
        _seed(con, "agent_capabilities",
              {"id": "dup", "capability_key": "research.read", "name": "Duplicate",
               "category": "research", "risk_level": "low", "access_class": "read",
               "approval_level": 0})
    con.close()


def test_the_server_defaults_fill_an_insert_that_omits_them(populated):
    """A raw insert that omits them gets a valid value, not an empty string.

    This is the case the ORM hides: it supplies Python-side defaults, so a
    migration that added nothing would still pass every ORM-level test while a
    restore or a script wrote empty strings into governed columns.
    """
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    _insert_omitting(con, "agent_capabilities",
                     {"id": "d1", "capability_key": "defaulted", "name": "Defaulted",
                      "category": "research", "risk_level": "low"},
                     omit={"approval_level", "access_class", "description", "enabled",
                           "requires_scope", "prohibited_reason"})
    row = con.execute(
        "SELECT approval_level, access_class, description, enabled, requires_scope, "
        "prohibited_reason FROM agent_capabilities WHERE id='d1'").fetchone()
    assert row == (0, "read", "", 1, 0, ""), row
    # Booleans must read back as booleans: a text default of '0' that came back as
    # a truthy string would invert the meaning of requires_scope.
    assert row[3] is not True or row[4] == 0
    assert bool(row[4]) is False, "requires_scope '0' must not be truthy"

    _insert_omitting(con, "agent_permissions",
                     {"id": "d2", "agent_id": "a1", "capability_id": "d1"},
                     omit={"scope", "approval_level", "status"})
    grant = con.execute(
        "SELECT scope, approval_level, status FROM agent_permissions WHERE id='d2'").fetchone()
    assert grant == ("", 0, "active"), grant
    con.close()


def test_the_two_new_columns_exist(populated):
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    names = {c[1] for c in _columns(con, "agent_capabilities")}
    assert {"requires_scope", "prohibited_reason"} <= names, sorted(names)
    con.close()


# --------------------------------------------------------------------------- #
# The downgrade
# --------------------------------------------------------------------------- #
def test_downgrade_removes_exactly_what_upgrade_added(populated):
    command.upgrade(_alembic(populated), "head")
    command.downgrade(_alembic(populated), STAGE4_HEAD)
    con = sqlite3.connect(populated)
    con.execute("PRAGMA foreign_keys=ON")

    names = {c[1] for c in _columns(con, "agent_capabilities")}
    assert "requires_scope" not in names and "prohibited_reason" not in names

    sql = _table_sql(con, "agent_capabilities")
    for gone in ("ck_agent_capabilities_risk_level", "ck_agent_capabilities_access_class"):
        assert gone not in sql, f"{gone} survived the downgrade"
    # The approval_level CHECK belongs to Stage 2, not to this revision, so the
    # downgrade must leave it: removing it would widen the schema back past the
    # revision being returned to.
    assert "ck_agent_capabilities_approval_level" in sql
    assert "ck_agent_permissions_status" not in _table_sql(con, "agent_permissions")

    assert con.execute("SELECT COUNT(*) FROM agent_capabilities").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM agent_permissions").fetchone()[0] == 1
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()


def test_the_downgraded_schema_accepts_the_values_it_used_to(populated):
    """Returning to Stage 4 must actually return to Stage 4's freedoms."""
    command.upgrade(_alembic(populated), "head")
    command.downgrade(_alembic(populated), STAGE4_HEAD)
    con = sqlite3.connect(populated)
    _seed(con, "agent_capabilities",
          {"id": "free", "capability_key": "free.text", "name": "Free", "category": "x",
           "risk_level": "EXTREME", "access_class": "destroy", "approval_level": 0})
    assert con.execute("SELECT risk_level FROM agent_capabilities WHERE id='free'"
                       ).fetchone()[0] == "EXTREME"
    con.close()


def test_reupgrade_after_a_downgrade_is_clean(populated):
    command.upgrade(_alembic(populated), "head")
    command.downgrade(_alembic(populated), STAGE4_HEAD)
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    con.execute("PRAGMA foreign_keys=ON")
    assert con.execute("SELECT COUNT(*) FROM agent_capabilities").fetchone()[0] == 1
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert version == STAGE5_HEAD
    con.close()
