"""P-10 integration tests: migration cycle, application wiring,
the HTTP surface end-to-end (policy versioning, capability
lifecycle, emergency flow, secret metadata masking, audit chain,
backups, session surface), the financial guard against a real P-06
business, and login-attempt recording.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.security.financial_guard import canonical_parameters
from tests.conftest import OWNER
from tests.p06_support import make_fixture_business  # noqa: F401
from tests.p10_support import (  # noqa: F401
    AGENT, app_sec, client_sec, owner_http_headers, service_http_headers,
)

SECURITY_TABLES = {
    "security_capabilities", "security_broker_decisions",
    "security_policy_versions", "security_secret_metadata",
    "security_secret_access_events", "security_emergency_events",
    "security_alerts", "security_incidents", "security_backup_records",
    "security_threat_register", "security_audit_chain",
    "security_login_attempts", "security_agent_restrictions",
    "security_data_classifications",
}


def _alembic_config(url: str):
    from alembic.config import Config
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location",
                           str(backend / "app" / "database" / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _table_names(url: str) -> set[str]:
    from sqlalchemy import create_engine, inspect
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_p10_migration_cycle(tmp_path):
    """P-09 head (123 tables) -> P-10 head (137) -> downgrade (123)
    -> re-upgrade (137): one additive migration, exact and reversible."""
    from alembic import command
    url = f"sqlite:///{tmp_path}/p10_cycle.db"
    config = _alembic_config(url)
    command.upgrade(config, "7b13db7e9bfa")
    before = _table_names(url)
    assert len(before) == 123
    # P-11 disclosure: "head" has since advanced to the additive P-11
    # migration (193731df4c37 revises e37d00443d20), so this cycle now
    # targets the P-10 head explicitly — the exact table-count and
    # downgrade assertions below are unchanged in kind.
    command.upgrade(config, "e37d00443d20")
    after = _table_names(url)
    assert len(after) == 137
    assert after - before == SECURITY_TABLES
    command.downgrade(config, "7b13db7e9bfa")
    assert _table_names(url) == before
    command.upgrade(config, "e37d00443d20")
    assert _table_names(url) == after


async def test_security_tables_and_facade_on_startup(app_sec):
    from sqlalchemy import inspect
    tables = set(inspect(app_sec.engine).get_table_names())
    assert SECURITY_TABLES <= tables
    assert app_sec.security is not None
    settings = app_sec.security.get_settings()
    assert settings["mode"] == "normal"
    assert settings["financial_suspension"] is False
    threats, total = app_sec.security.list_threats()
    assert total == 14
    versions, vtotal = app_sec.security.list_policy_versions()
    assert vtotal == 1 and versions[0]["actor"] == "system:bootstrap"
    # The login guard is wired into P-01 auth at startup.
    assert app_sec.auth.login_guard is app_sec.security.login_guard
    # P-10 emitted no parallel approvals: the approvals table is P-01's.
    assert "security_approval_requests" not in tables


def test_http_status_and_policy_flow(client_sec):
    owner = owner_http_headers(client_sec)
    status = client_sec.get("/api/v1/security/status", headers=owner)
    assert status.status_code == 200
    data = status.json()["data"]
    assert data["mode"] == "normal"
    assert "audit_chain" in data and "recent_security_events" in data
    # Owner updates a policy value; the change is versioned.
    put = client_sec.put("/api/v1/security/policies", headers=owner,
                         json={"patch": {"alert_denial_threshold": 3},
                               "reason": "tune alerting"})
    assert put.status_code == 200
    assert put.json()["data"]["settings"]["alert_denial_threshold"] == 3
    versions = client_sec.get("/api/v1/security/policies/versions",
                              headers=owner)
    assert versions.json()["meta"]["total"] == 2
    # Validation endpoint reports without applying.
    bad = client_sec.post("/api/v1/security/policies/validate", headers=owner,
                          json={"patch": {"mode": "yolo"}})
    assert bad.json()["data"]["valid"] is False
    # Identities view: principal types + registered agents.
    identities = client_sec.get("/api/v1/security/identities", headers=owner)
    assert identities.status_code == 200
    assert "owner" in identities.json()["data"]["principal_types"]


def test_http_capability_lifecycle(client_sec):
    owner = owner_http_headers(client_sec)
    issued = client_sec.post("/api/v1/security/capabilities", headers=owner,
                             json={"holder_id": "agent-1",
                                   "permission": "execute_tools",
                                   "reason": "publish the digest"})
    assert issued.status_code == 201, issued.text
    cap = issued.json()["data"]
    # The broker honours the capability for a Level-2 action.
    check = client_sec.post(
        "/api/v1/security/permissions/check", headers=owner,
        json={"principal_id": "agent-1", "permission": "execute_tools",
              "action": "content.publish", "capability_id": cap["id"],
              "parameters": {}})
    assert check.json()["data"]["allowed"] is True, check.text
    # Revoke it and the same check fails.
    revoked = client_sec.post(
        f"/api/v1/security/capabilities/{cap['id']}/revoke", headers=owner)
    assert revoked.status_code == 200
    again = client_sec.post(
        "/api/v1/security/permissions/check", headers=owner,
        json={"principal_id": "agent-1", "permission": "execute_tools",
              "action": "content.publish", "capability_id": cap["id"],
              "parameters": {}})
    assert again.json()["data"]["allowed"] is False
    # The decision ledger recorded both outcomes.
    ledger = client_sec.get("/api/v1/security/broker/decisions",
                            headers=owner)
    assert ledger.json()["meta"]["total"] >= 2


def test_http_emergency_flow(client_sec):
    owner = owner_http_headers(client_sec)
    safe = client_sec.post("/api/v1/security/emergency/mode", headers=owner,
                           json={"mode": "safe_mode", "reason": "drill"})
    assert safe.status_code == 200
    assert safe.json()["data"]["mode"] == "safe_mode"
    # In safe mode the agent's write is denied at the broker, reads pass.
    write = client_sec.post(
        "/api/v1/security/permissions/check", headers=owner,
        json={"principal_id": "agent-1", "permission": "execute_tools",
              "action": "filesystem.write", "parameters": {}})
    assert write.json()["data"]["allowed"] is False
    read = client_sec.post(
        "/api/v1/security/permissions/check", headers=owner,
        json={"principal_id": "agent-1", "permission": "read_system_data",
              "action": "read", "parameters": {}})
    assert read.json()["data"]["allowed"] is True
    suspend = client_sec.post(
        "/api/v1/security/emergency/financial-suspension", headers=owner,
        json={"suspended": True, "reason": "drill"})
    assert suspend.json()["data"]["financial_suspension"] is True
    client_sec.post("/api/v1/security/emergency/financial-suspension",
                    headers=owner, json={"suspended": False})
    back = client_sec.post("/api/v1/security/emergency/mode", headers=owner,
                           json={"mode": "normal", "reason": "drill over"})
    assert back.json()["data"]["mode"] == "normal"
    events = client_sec.get("/api/v1/security/emergency/events",
                            headers=owner)
    assert events.json()["meta"]["total"] >= 3


def test_http_secret_metadata_flow(client_sec, monkeypatch):
    value = "sk-" + "W" * 24
    monkeypatch.setenv("P10_HTTP_KEY", value)
    owner = owner_http_headers(client_sec)
    created = client_sec.post(
        "/api/v1/security/secrets", headers=owner,
        json={"name": "http-key", "reference": "env:P10_HTTP_KEY",
              "purpose": "integration test", "classification": 4})
    assert created.status_code == 201, created.text
    body = created.json()["data"]
    assert body["reference_hint"] == "env:***"
    assert value not in created.text
    assert "env:P10_HTTP_KEY" not in created.text
    listing = client_sec.get("/api/v1/security/secrets", headers=owner)
    assert value not in listing.text
    assert "env:P10_HTTP_KEY" not in listing.text
    # Brokered access check: the agent is refused, the owner allowed —
    # and neither response carries a value (checks never resolve).
    agent_check = client_sec.post(
        "/api/v1/security/secrets/http-key/access-check", headers=owner,
        json={"principal_id": "agent-1", "purpose": "test"})
    assert agent_check.json()["data"]["allowed"] is False
    owner_check = client_sec.post(
        "/api/v1/security/secrets/http-key/access-check", headers=owner,
        json={"principal_type": "owner", "principal_id": "owner",
              "purpose": "test"})
    assert owner_check.json()["data"]["allowed"] is True
    assert value not in owner_check.text
    # Lifecycle: rotate then revoke; a revoked secret no longer checks out.
    assert client_sec.post("/api/v1/security/secrets/http-key/rotate",
                           headers=owner).status_code == 200
    assert client_sec.post("/api/v1/security/secrets/http-key/revoke",
                           headers=owner).status_code == 200
    after = client_sec.post(
        "/api/v1/security/secrets/http-key/access-check", headers=owner,
        json={"principal_type": "owner", "principal_id": "owner"})
    assert after.json()["data"]["allowed"] is False
    events = client_sec.get("/api/v1/security/secrets/access-events",
                            headers=owner)
    assert events.json()["meta"]["total"] >= 3
    backends = client_sec.get("/api/v1/security/secrets/backends",
                              headers=owner).json()["data"]["backends"]
    windows = next(b for b in backends if b["backend"] == "windows-vault")
    assert windows["available"] is False
    assert windows["status"] == "REQUIRES OWNER CONFIGURATION"


def test_http_audit_chain_flow(client_sec):
    owner = owner_http_headers(client_sec)
    client_sec.put("/api/v1/security/policies", headers=owner,
                   json={"patch": {"alert_denial_threshold": 4},
                         "reason": "chain flow"})
    sealed = client_sec.post("/api/v1/security/audit/seal", headers=owner)
    assert sealed.status_code == 200
    assert sealed.json()["data"]["sealed"] >= 1
    verify = client_sec.get("/api/v1/security/audit/verify", headers=owner)
    assert verify.json()["data"]["ok"] is True
    events = client_sec.get("/api/v1/security/audit", headers=owner,
                            params={"action_prefix": "security."})
    assert events.json()["meta"]["total"] >= 1
    # The audit trail is read-only over HTTP: no update/delete route
    # exists for it (Scenario 18's surface check).
    assert client_sec.delete("/api/v1/security/audit",
                             headers=owner).status_code in (404, 405)
    assert client_sec.put("/api/v1/security/audit",
                          headers=owner).status_code in (404, 405)
    assert client_sec.patch("/api/v1/security/audit",
                            headers=owner).status_code in (404, 405)


def test_http_backup_flow(client_sec):
    owner = owner_http_headers(client_sec)
    created = client_sec.post("/api/v1/security/backups", headers=owner)
    assert created.status_code == 201, created.text
    backup = created.json()["data"]
    assert backup["status"] == "created" and backup["sha256"]
    verified = client_sec.post(
        f"/api/v1/security/backups/{backup['id']}/verify", headers=owner)
    assert verified.json()["data"]["status"] == "verified"
    listing = client_sec.get("/api/v1/security/backups", headers=owner)
    assert listing.json()["meta"]["total"] == 1


async def test_financial_guard_with_real_business(app_sec):
    _opp_id, business = await make_fixture_business(app_sec)
    business_id = business["id"]
    params = canonical_parameters(business_id, 250_00, "USD", "printer-co")
    approval = app_sec.approvals.create(
        AGENT, action="financial.transfer", resource=business_id,
        risk_classification="high", reason="pay the printer",
        requested_permissions=["request_financial_operations"],
        parameters=params)
    app_sec.approvals.decide(approval.id, OWNER, True)
    guard = app_sec.security.financial_guard
    # Permission separation: an analyst-style agent may view but the
    # execute path needs the approval-bound owner authority.
    view = guard.authorize(AGENT, action="view", business_id=business_id)
    assert view["allowed"] is True
    executed = guard.authorize(
        OWNER, action="execute_transfer", business_id=business_id,
        amount_minor=250_00, currency="USD", recipient="printer-co",
        approval_id=approval.id)
    assert executed["allowed"] is True, executed
    # Over the P-07 single-transaction ceiling (USD 1000.00): denied
    # at the limit gate before binding is even considered.
    big_params = canonical_parameters(business_id, 1500_00, "USD", "printer-co")
    big = app_sec.approvals.create(
        AGENT, action="financial.transfer", resource=business_id,
        risk_classification="high", reason="too big",
        requested_permissions=["request_financial_operations"],
        parameters=big_params)
    app_sec.approvals.decide(big.id, OWNER, True)
    over = guard.authorize(
        OWNER, action="execute_transfer", business_id=business_id,
        amount_minor=1500_00, currency="USD", recipient="printer-co",
        approval_id=big.id)
    assert over["allowed"] is False
    assert "limit" in over["reason"]
    # Financial suspension blocks even a fully approved transfer.
    app_sec.security.emergency.set_financial_suspension(OWNER, True, "test")
    suspended = guard.authorize(
        OWNER, action="execute_transfer", business_id=business_id,
        amount_minor=250_00, currency="USD", recipient="printer-co",
        approval_id=approval.id)
    assert suspended["allowed"] is False
    app_sec.security.emergency.set_financial_suspension(OWNER, False, "test over")


async def test_login_attempts_recorded(app_sec):
    assert app_sec.auth.login("owner", "bad-password") is None
    assert app_sec.auth.login("owner", "test-owner-password-123")
    from app.database.models.security import SecurityLoginAttempt
    from sqlalchemy import select
    session = app_sec.session_factory()
    try:
        rows = list(session.scalars(select(SecurityLoginAttempt)))
    finally:
        session.close()
    outcomes = {(r.username, r.success) for r in rows}
    assert ("owner", False) in outcomes
    assert ("owner", True) in outcomes
    # No password material is ever stored on the attempt rows.
    assert all(not hasattr(r, "password") for r in rows)


async def test_no_money_columns_in_security_tables(app_sec):
    """Structural lock: P-10 is not a financial authority — none of
    its tables carries a money/amount/balance column (§16)."""
    from sqlalchemy import inspect
    inspector = inspect(app_sec.engine)
    offenders = []
    for table in SECURITY_TABLES:
        for column in inspector.get_columns(table):
            name = column["name"].lower()
            if any(word in name for word in ("amount", "balance", "money",
                                             "price", "total_minor")):
                offenders.append(f"{table}.{column['name']}")
    assert offenders == [], offenders
