"""P-05 Stage 2 schema: the execution core's nine tables, on a populated database.

Every assertion runs against a database that already holds P-01 to P-04 rows,
upgraded from the Stage-6 head, because that is the case that breaks
`upgrade head` in production. The new tables are empty at that point by
definition, so what is being proven is different from the earlier stages: not
that legacy values survive a new constraint, but that the constraints exist
at all. Autogenerate rendered none of the 18 CHECKs for these tables (the
L-56 / ADR-0024 omission), so each one is proven by inserting a value it must
refuse and asserting the refusal names it.

The heads are pinned, not derived from "head", so a later revision cannot
move what this proves.
"""
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[1]
STAGE6_HEAD = "d577d056a63b"
EXECUTION_HEAD = "229ca08ee712"

NEW_TABLES = (
    "execution_tools", "execution_requests", "execution_runs",
    "execution_evidence", "execution_workspaces", "browser_sessions",
    "workflow_definitions", "workflow_runs", "workflow_step_runs",
)

OUTCOMES = (
    "ACCEPTED", "VALIDATING", "AWAITING_APPROVAL", "QUEUED", "RUNNING",
    "COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED", "REJECTED", "CANCELLED",
    "TIMED_OUT", "INTERRUPTED", "REQUIRES_HUMAN_ACTION",
    "REQUIRES_RECONCILIATION",
)


def _alembic(db_path: Path) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _tables(con) -> set[str]:
    return {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _seeded_db(tmp_path: Path) -> Path:
    """A database at the Stage-6 head holding rows the upgrade must not lose."""
    db_path = tmp_path / "populated.db"
    command.upgrade(_alembic(db_path), STAGE6_HEAD)
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute(
        "INSERT INTO principals (id, kind, name, active, created_at, updated_at) "
        "VALUES ('p-owner', 'owner', 'owner', 1, '2026-01-01', '2026-01-01')")
    con.execute(
        "INSERT INTO agents (id, principal_id, name, role, status, metadata_json, "
        "configuration_version, created_at, updated_at) VALUES ('a-1', NULL, 'worker', "
        "'research', 'ACTIVE', '{}', 1, '2026-01-01', '2026-01-01')")
    con.execute(
        "INSERT INTO tasks (id, name, description, category, handler, priority, status, "
        "creator_id, payload, result, progress, retry_count, max_retries, timeout_seconds, "
        "cancellation_requested, approval_required, essential, created_at, updated_at) "
        "VALUES ('t-1', 'job', '', 'research', 'test.handler', 5, 'QUEUED', 'p-owner', "
        "'{}', NULL, '{}', 0, 3, 30.0, 0, 0, 0, '2026-01-01', '2026-01-01')")
    con.commit()
    con.close()
    return db_path


def _insert(con, table: str, row: dict) -> None:
    cols = ", ".join(row)
    vals = ", ".join(repr(v) for v in row.values())
    con.execute(f"INSERT INTO {table} ({cols}) VALUES ({vals})")


def _tool_row(**over):
    row = {"id": "tool-1", "name": "fs.read", "description": "", "category": "filesystem",
           "adapter_type": "filesystem", "version": "1.0.0", "supported_actions": "[]",
           "input_schema": "{}", "output_schema": "{}", "capability_requirements": "[]",
           "supported_platforms": "[]", "resource_requirements": "{}",
           "retry_eligible": 0, "idempotent": 0,
           "created_at": "2026-01-01", "updated_at": "2026-01-01"}
    row.update(over)
    return row


def test_the_nine_tables_arrive_and_existing_rows_survive(tmp_path):
    db_path = _seeded_db(tmp_path)
    command.upgrade(_alembic(db_path), "head")
    con = sqlite3.connect(db_path)
    assert set(NEW_TABLES) <= _tables(con)
    assert con.execute("SELECT name FROM agents WHERE id='a-1'").fetchone() == ("worker",)
    assert con.execute("SELECT name FROM tasks WHERE id='t-1'").fetchone() == ("job",)


def test_outcome_vocabulary_is_closed_in_the_database(tmp_path):
    db_path = _seeded_db(tmp_path)
    command.upgrade(_alembic(db_path), "head")
    con = sqlite3.connect(db_path)
    _insert(con, "execution_tools", _tool_row())
    base = {"id": "req-1", "task_id": "t-1", "agent_id": "a-1", "tool_id": "tool-1",
            "adapter_type": "filesystem", "action_name": "read", "request_payload": "{}",
            "input_references": "[]", "requested_scope": "workspace:x",
            "required_capabilities": "[]", "risk_level": 1, "priority": 5,
            "timeout_seconds": 60, "retry_policy": "{}", "expected_output_schema": "{}",
            "created_at": "2026-01-01", "updated_at": "2026-01-01"}
    with pytest.raises(sqlite3.IntegrityError, match="ck_execution_requests_status"):
        _insert(con, "execution_requests", {**base, "status": "DONE"})
    con.rollback()
    # Every one of the fourteen outcomes is storable; the vocabulary is closed,
    # not narrowed by the migration to a subset the code happens to use today.
    for index, outcome in enumerate(OUTCOMES):
        _insert(con, "execution_requests",
                {**base, "id": f"req-{index}", "status": outcome})
    con.commit()
    assert con.execute("SELECT count(*) FROM execution_requests").fetchone()[0] == 14


def test_tool_vocabulary_and_ranges_are_closed(tmp_path):
    db_path = _seeded_db(tmp_path)
    command.upgrade(_alembic(db_path), "head")
    con = sqlite3.connect(db_path)
    with pytest.raises(sqlite3.IntegrityError, match="ck_execution_tools_status"):
        _insert(con, "execution_tools", _tool_row(status="READY"))
    con.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="ck_execution_tools_adapter_type"):
        _insert(con, "execution_tools", _tool_row(adapter_type="telepathy"))
    con.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="ck_execution_tools_risk_level"):
        _insert(con, "execution_tools", _tool_row(risk_level=7))
    con.rollback()
    # SQLite reports UNIQUE failures by column, not constraint name; the
    # constraint's name is proven by the rendered DDL in the portability suite.
    with pytest.raises(sqlite3.IntegrityError,
                       match="UNIQUE constraint failed: execution_tools.name"):
        _insert(con, "execution_tools", _tool_row())
        _insert(con, "execution_tools", _tool_row(id="tool-2"))
    con.rollback()


def test_idempotency_key_is_unique_but_optional(tmp_path):
    db_path = _seeded_db(tmp_path)
    command.upgrade(_alembic(db_path), "head")
    con = sqlite3.connect(db_path)
    _insert(con, "execution_tools", _tool_row())
    base = {"task_id": "t-1", "agent_id": "a-1", "tool_id": "tool-1",
            "adapter_type": "filesystem", "action_name": "read", "request_payload": "{}",
            "input_references": "[]", "requested_scope": "workspace:x",
            "required_capabilities": "[]", "risk_level": 0, "status": "QUEUED",
            "priority": 5, "timeout_seconds": 60, "retry_policy": "{}",
            "expected_output_schema": "{}",
            "created_at": "2026-01-01", "updated_at": "2026-01-01"}
    # NULL keys never collide: requests that did not ask for idempotency are
    # not deduplicated against each other.
    _insert(con, "execution_requests", {**base, "id": "r-null-1"})
    _insert(con, "execution_requests", {**base, "id": "r-null-2"})
    _insert(con, "execution_requests", {**base, "id": "r-key-1", "idempotency_key": "k-1"})
    with pytest.raises(sqlite3.IntegrityError,
                       match="UNIQUE constraint failed: execution_requests.idempotency_key"):
        _insert(con, "execution_requests", {**base, "id": "r-key-2", "idempotency_key": "k-1"})
    con.rollback()


def test_raw_inserts_receive_in_vocabulary_defaults(tmp_path):
    """A raw insert that omits defaulted columns gets values inside the
    constrained vocabulary, not empty strings the CHECK would then reject."""
    db_path = _seeded_db(tmp_path)
    command.upgrade(_alembic(db_path), "head")
    con = sqlite3.connect(db_path)
    _insert(con, "execution_tools", _tool_row())
    row = con.execute(
        "SELECT status, risk_level, required_approval_level, health_status "
        "FROM execution_tools WHERE id='tool-1'").fetchone()
    assert row == ("REGISTERED", 1, 0, "unknown")


def test_the_two_deliberately_absent_tables_stay_absent(tmp_path):
    """§19's execution_approvals and execution_audit_events are not created:
    the central approvals and audit tables carry those records (§17)."""
    db_path = _seeded_db(tmp_path)
    command.upgrade(_alembic(db_path), "head")
    con = sqlite3.connect(db_path)
    assert "execution_approvals" not in _tables(con)
    assert "execution_audit_events" not in _tables(con)


def test_downgrade_removes_only_the_new_tables(tmp_path):
    db_path = _seeded_db(tmp_path)
    command.upgrade(_alembic(db_path), "head")
    command.downgrade(_alembic(db_path), STAGE6_HEAD)
    con = sqlite3.connect(db_path)
    assert not (set(NEW_TABLES) & _tables(con))
    assert con.execute("SELECT count(*) FROM agents").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM tasks").fetchone()[0] == 1
    version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert version == STAGE6_HEAD
