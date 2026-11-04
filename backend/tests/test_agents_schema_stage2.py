"""P-04 Stage 2: the agent data architecture.

Covers the migration over a populated database (the failure mode that has
bitten this project before), the database-level constraints, and the typed
schemas that stop invalid templates at the boundary.
"""
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError

from app.agents.schemas import (
    AgentRecordView,
    ResourceBudget,
    TemplateConfiguration,
)

BACKEND = Path(__file__).resolve().parents[1]
PRE_P04_HEAD = "72ee9705e18f"


def _alembic(db_path: Path) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _seed_legacy_agent(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO principals (id, kind, name, active, created_at, updated_at) "
        "VALUES ('p1', 'owner', 'owner', 1, '2026-01-01', '2026-01-01')"
    )
    con.execute(
        "INSERT INTO agents (id, principal_id, name, role, status, metadata_json,"
        " created_at, updated_at) VALUES ('a1', 'p1', 'legacy', 'research',"
        " 'registered', '{}', '2026-01-01', '2026-01-01')"
    )
    con.commit()
    con.close()


def _seed_task(con) -> None:
    """Insert a minimal task row straight through SQL.

    Raw SQL bypasses the Python-side column defaults, so every NOT NULL
    column needs an explicit value; deriving them from PRAGMA keeps the
    seed honest if the tasks table grows again.
    """
    cols = con.execute("PRAGMA table_info(tasks)").fetchall()
    names, values = [], []
    given = {"id": "'t9'", "name": "'t'", "handler": "'system.noop'",
             "payload": "'{}'", "created_at": "'2026-01-01'",
             "updated_at": "'2026-01-01'"}
    for _cid, name, ctype, notnull, _dflt, _pk in cols:
        if name in given:
            names.append(name); values.append(given[name])
        elif notnull:
            kind = ctype.upper()
            if kind in ("INTEGER", "FLOAT", "NUMERIC"):
                values.append("0")
            elif kind in ("BOOLEAN",):
                values.append("0")
            elif kind.startswith("DATETIME"):
                values.append("'2026-01-01'")
            elif name.endswith("_json") or name in ("payload", "result"):
                values.append("'{}'")
            else:
                values.append("''")
            names.append(name)
    con.execute(f"INSERT INTO tasks ({', '.join(names)}) VALUES ({', '.join(values)})")


def test_migration_upgrades_a_populated_database_and_rewrites_legacy_status(tmp_path):
    db = tmp_path / "populated.db"
    command.upgrade(_alembic(db), PRE_P04_HEAD)
    _seed_legacy_agent(db)
    command.upgrade(_alembic(db), "head")
    con = sqlite3.connect(db)
    status, version = con.execute(
        "SELECT status, configuration_version FROM agents WHERE id='a1'"
    ).fetchone()
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert status == "ACTIVE"          # legacy value rewritten, not rejected
    assert version == 1
    assert {"agent_templates", "agent_template_versions", "agent_capabilities",
            "agent_permissions", "agent_assignments", "agent_health",
            "agent_metrics", "agent_configuration_history",
            "agent_creation_requests"} <= tables


def test_downgrade_restores_the_pre_p04_agents_shape(tmp_path):
    db = tmp_path / "down.db"
    command.upgrade(_alembic(db), "head")
    command.downgrade(_alembic(db), PRE_P04_HEAD)
    con = sqlite3.connect(db)
    cols = {r[1] for r in con.execute("PRAGMA table_info(agents)")}
    con.close()
    assert "template_id" not in cols
    assert "retired_at" not in cols
    assert {"id", "name", "role", "status", "metadata_json"} <= cols


@pytest.mark.parametrize("statement,table", [
    ("INSERT INTO agents (id, name, role, status, metadata_json, created_at,"
     " updated_at) VALUES ('a9', 'x', 'y', 'BANANA', '{}', '2026-01-01', '2026-01-01')",
     "agents"),
    ("INSERT INTO agent_metrics (id, agent_id, metric_name, metric_value,"
     " measurement_type, recorded_at, created_at, updated_at) VALUES ('m9', 'a9',"
     " 'x', 1.0, 'fabricated', '2026-01-01', '2026-01-01', '2026-01-01')",
     "agent_metrics"),
    ("INSERT INTO agent_capabilities (id, capability_key, name, category,"
     " risk_level, approval_level, access_class, description, enabled, created_at,"
     " updated_at) VALUES ('c9', 'k9', 'n', 'cat', 'LOW', 7, 'read', '', 1,"
     " '2026-01-01', '2026-01-01')",
     "agent_capabilities"),
    ("INSERT INTO agent_assignments (id, agent_id, task_id, status, priority,"
     " required_capabilities, expected_output_schema, delegation_depth,"
     " assigned_at, created_at, updated_at) VALUES ('as9', 'a9', 't9', 'assigned',"
     " 5, '[]', '{}', -1, '2026-01-01', '2026-01-01', '2026-01-01')",
     "agent_assignments"),
])
def test_database_constraints_reject_invalid_rows(tmp_path, statement, table):
    """An estimate stored as a measurement, or a state outside the lifecycle,
    must fail at the column, not merely at the service layer."""
    db = tmp_path / "checks.db"
    command.upgrade(_alembic(db), "head")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO agents (id, name, role, status, metadata_json,"
                " created_at, updated_at) VALUES ('a9', 'x', 'y', 'ACTIVE', '{}',"
                " '2026-01-01', '2026-01-01')")
    _seed_task(con)
    con.commit()
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(statement)
    con.close()


def test_a_template_cannot_allow_and_restrict_the_same_capability():
    with pytest.raises(ValidationError):
        TemplateConfiguration(
            role_definition="research",
            mission="research the market",
            allowed_capabilities=["web.research"],
            restricted_capabilities=["web.research"],
        )


def test_resource_budgets_are_bounded():
    with pytest.raises(ValidationError):
        ResourceBudget(max_concurrent_tasks=0)
    with pytest.raises(ValidationError):
        ResourceBudget(max_task_seconds=10 ** 7)


def test_the_registry_view_carries_the_lifecycle_fields():
    view = AgentRecordView(
        id="a1", name="researcher", role="research", status="ACTIVE",
        template_id=None, template_version=None, configuration_version=1,
        parent_agent_id=None, business_id=None, retired_at=None,
        created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
    )
    assert view.status == "ACTIVE"
    assert view.configuration_version == 1
