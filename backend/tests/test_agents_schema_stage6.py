"""P-04 Stage 6 schema: the assignment ledger's vocabulary, and the work a decision is about.

Stage 2 created ``agent_assignments`` with a free-text ``status``, and nothing
wrote to it until now. Two things had to be true before Stage 6 could treat the
table as a ledger rather than a scratch space: the status vocabulary has to be
closed in the database and not only in the code that happens to be running, and a
creation decision that says "give this work to an agent that already exists" has
to be able to record which work it meant.

Every assertion runs against a database that already holds rows, including one
holding a status the new CHECK would reject, because that is the case that breaks
``upgrade head`` in production: on SQLite the violation surfaces during the batch
rebuild's INSERT-SELECT, partway through non-transactional DDL, which is how a
database ends up half-migrated.
"""
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[1]
#: Pinned, not derived from "head", so a later revision cannot move what this proves.
STAGE5_HEAD = "e8b2ced758fc"
STAGE6_HEAD = "d577d056a63b"

STATUSES = ("assigned", "in_progress", "completed", "failed", "cancelled")


def _alembic(db_path: Path) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _columns(con, table):
    return list(con.execute(f"PRAGMA table_info({table})"))


def _fill(ctype: str, name: str) -> str:
    kind = ctype.upper()
    if kind in ("INTEGER", "FLOAT", "NUMERIC", "BOOLEAN"):
        return "0"
    if kind.startswith("DATETIME"):
        return "'2026-01-01'"
    if name.endswith("_json") or name in ("payload", "result"):
        return "'{}'"
    return "''"


def _seed(con, table, given):
    names, values = [], []
    for _cid, name, ctype, notnull, _dflt, _pk in _columns(con, table):
        if name in given:
            names.append(name); values.append(repr(given[name])); continue
        if notnull:
            names.append(name); values.append(_fill(ctype, name))
    con.execute(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join(values)})")


def _insert_omitting(con, table, given, omit):
    names, values = [], []
    for _cid, name, ctype, notnull, dflt, _pk in _columns(con, table):
        if name in omit:
            continue
        if name in given:
            names.append(name); values.append(repr(given[name])); continue
        if notnull and dflt is None:
            names.append(name); values.append(_fill(ctype, name))
    con.execute(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join(values)})")


def _table_sql(con, table):
    row = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                      (table,)).fetchone()
    return row[0] if row else ""


def _task(con, task_id: str) -> None:
    """Another task.

    ``agent_assignments.task_id`` is UNIQUE — one assignment per task, because two
    rows for one task would be two claims about who is doing it — so a test that
    inserts a second assignment needs a second task. Without one, the UNIQUE
    constraint fires first and a CHECK assertion passes for the wrong reason.
    """
    _seed(con, "tasks", {"id": task_id, "name": f"task-{task_id}", "status": "QUEUED",
                         "creator_id": "p1", "handler": "opportunities.screen"})


def _referents(con) -> None:
    """A principal, an agent and a task: the two foreign keys an assignment needs."""
    _seed(con, "principals", {"id": "p1", "kind": "owner", "name": "owner", "active": 1})
    _seed(con, "agents", {"id": "a1", "principal_id": "p1", "name": "agent-1",
                          "role": "researcher", "status": "ACTIVE"})
    _seed(con, "tasks", {"id": "k1", "name": "screen", "status": "QUEUED",
                         "creator_id": "p1", "handler": "opportunities.screen"})


@pytest.fixture()
def populated(tmp_path) -> Path:
    """A Stage-5 database holding an assignment whose status is already valid."""
    db = tmp_path / "stage5.db"
    command.upgrade(_alembic(db), STAGE5_HEAD)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    _referents(con)
    _seed(con, "agent_assignments", {"id": "as1", "agent_id": "a1", "task_id": "k1",
                                     "status": "assigned", "delegation_depth": 0})
    con.commit(); con.close()
    return db


@pytest.fixture()
def legacy(tmp_path) -> Path:
    """A Stage-5 database holding a status the new CHECK would reject."""
    db = tmp_path / "legacy.db"
    command.upgrade(_alembic(db), STAGE5_HEAD)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    _referents(con)
    _seed(con, "agent_assignments", {"id": "as1", "agent_id": "a1", "task_id": "k1",
                                     "status": "banana", "delegation_depth": 0})
    con.commit()
    assert con.execute("SELECT status FROM agent_assignments").fetchone()[0] == "banana"
    con.close()
    return db


def test_the_stage_6_revision_is_the_head_of_a_nine_deep_chain():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app/database/migrations"))
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(cfg)
    revisions = [s.revision for s in script.walk_revisions()]
    assert script.get_current_head() == STAGE6_HEAD
    assert len(revisions) == 9, revisions
    assert revisions[1] == STAGE5_HEAD, "Stage 6 must sit directly on Stage 5"


def test_upgrade_preserves_rows_and_every_reference(populated):
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    con.execute("PRAGMA foreign_keys=ON")
    assert con.execute("SELECT COUNT(*) FROM agent_assignments").fetchone()[0] == 1
    assert con.execute("SELECT agent_id, task_id FROM agent_assignments").fetchone() == ("a1", "k1")
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()


def test_an_unrecognized_status_is_normalized_and_explains_itself(legacy):
    """To `cancelled`, not to `assigned`.

    `assigned` would tell a scheduler that work is waiting to be handed out, which
    is a claim the revision has no evidence for. `cancelled` is terminal, so nothing
    acts on the row — and because that loses information, `failure_reason` says what
    happened rather than leaving a row that looks deliberate.
    """
    command.upgrade(_alembic(legacy), "head")
    con = sqlite3.connect(legacy)
    con.execute("PRAGMA foreign_keys=ON")
    status, reason = con.execute(
        "SELECT status, failure_reason FROM agent_assignments").fetchone()
    assert status == "cancelled", status
    assert reason and "normalized" in reason, reason
    assert STAGE6_HEAD[:8] in reason or "revision" in reason
    assert con.execute("SELECT COUNT(*) FROM agent_assignments").fetchone()[0] == 1
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()


def test_a_status_already_in_the_vocabulary_is_left_alone(populated):
    """Normalization corrects; it does not overwrite, and it does not annotate a
    row that was never wrong."""
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    status, reason = con.execute(
        "SELECT status, failure_reason FROM agent_assignments").fetchone()
    assert status == "assigned"
    assert not reason, "a valid row must not be told it was normalized"
    con.close()


@pytest.mark.parametrize("bad", ["banana", "ASSIGNED", "", "completed "])
def test_the_status_check_refuses_a_bad_value(populated, bad):
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    # A fresh task, so the failure is the CHECK and not the UNIQUE on task_id.
    _task(con, "k2")
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        _seed(con, "agent_assignments", {"id": "bad", "agent_id": "a1", "task_id": "k2",
                                         "status": bad})
    assert "ck_agent_assignments_status" in str(excinfo.value), str(excinfo.value)
    con.close()


def test_the_server_default_fills_an_insert_that_omits_status(populated):
    """The case the ORM hides: it supplies a Python-side default, so a migration
    that added nothing would still pass every ORM-level test while a restore or a
    script wrote an empty string into a governed column."""
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    _task(con, "k3")
    _insert_omitting(con, "agent_assignments",
                     {"id": "d1", "agent_id": "a1", "task_id": "k3"},
                     omit={"status", "priority", "delegation_depth"})
    row = con.execute("SELECT status, priority, delegation_depth "
                      "FROM agent_assignments WHERE id='d1'").fetchone()
    assert row == ("assigned", 5, 0), row
    con.close()


def test_the_creation_request_gains_a_task_reference(populated):
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    names = {c[1] for c in _columns(con, "agent_creation_requests")}
    assert "task_id" in names, sorted(names)
    # Existing rows keep working: the column is nullable, so a Stage-4 request that
    # named a role rather than a task still reads.
    assert con.execute("SELECT task_id FROM agent_creation_requests").fetchall() == []
    con.close()


def test_the_task_reference_is_enforced_and_rejects_an_unknown_task(populated):
    """A decision that points at work must point at work that exists."""
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    con.execute("PRAGMA foreign_keys=ON")
    # approval_status is CHECK-constrained since Stage 4, so it cannot be left to
    # the PRAGMA filler's empty string.
    base = {"requested_role": "researcher", "justification": "needed",
            "approval_status": "not_required"}
    with pytest.raises(sqlite3.IntegrityError):
        _seed(con, "agent_creation_requests", dict(base, id="cr1", task_id="no-such-task"))
    _seed(con, "agent_creation_requests", dict(base, id="cr2", task_id="k1"))
    assert con.execute("SELECT task_id FROM agent_creation_requests WHERE id='cr2'"
                       ).fetchone()[0] == "k1"
    con.close()


def test_downgrade_removes_exactly_what_upgrade_added(populated):
    command.upgrade(_alembic(populated), "head")
    command.downgrade(_alembic(populated), STAGE5_HEAD)
    con = sqlite3.connect(populated)
    con.execute("PRAGMA foreign_keys=ON")

    assert "ck_agent_assignments_status" not in _table_sql(con, "agent_assignments")
    assert "task_id" not in {c[1] for c in _columns(con, "agent_creation_requests")}
    # Rows survive both directions, and so do the references they hold.
    assert con.execute("SELECT COUNT(*) FROM agent_assignments").fetchone()[0] == 1
    assert con.execute("SELECT agent_id, task_id FROM agent_assignments").fetchone() == ("a1", "k1")
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()


def test_the_downgraded_schema_accepts_the_free_text_it_used_to(populated):
    command.upgrade(_alembic(populated), "head")
    command.downgrade(_alembic(populated), STAGE5_HEAD)
    con = sqlite3.connect(populated)
    _task(con, "k4")
    _seed(con, "agent_assignments", {"id": "free", "agent_id": "a1", "task_id": "k4",
                                     "status": "whatever"})
    assert con.execute("SELECT status FROM agent_assignments WHERE id='free'"
                       ).fetchone()[0] == "whatever"
    con.close()


def test_reupgrade_after_a_downgrade_is_clean(populated):
    command.upgrade(_alembic(populated), "head")
    command.downgrade(_alembic(populated), STAGE5_HEAD)
    command.upgrade(_alembic(populated), "head")
    con = sqlite3.connect(populated)
    con.execute("PRAGMA foreign_keys=ON")
    assert con.execute("SELECT COUNT(*) FROM agent_assignments").fetchone()[0] == 1
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == STAGE6_HEAD
    con.close()
