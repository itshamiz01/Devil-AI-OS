"""Expansion Feature 2 integration tests: migration cycle, the
seeded registry, the connector lifecycle (register → configure →
enable → invoke → disable), the reference connector end to end,
idempotent replay, honest not-configured failures, and the HTTP
surface including the API catalogue.
"""
from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.integrations.service import IntegrationError
from tests.conftest import OWNER
from tests.f02_support import (
    app_f02, audit_events, client_f02, owner_http_headers,
    service_http_headers,
)


# ------------------------------------------------------------ migration
def test_f02_migration_cycle(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    db = tmp_path / "f02_cycle.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")

    def count() -> int:
        with engine.connect() as conn:
            return conn.execute(text(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            )).scalar_one()

    def head() -> str:
        with engine.connect() as conn:
            return conn.execute(text(
                "SELECT version_num FROM alembic_version")).scalar_one()

    command.upgrade(config, "head")
    # Expansion F03 disclosure: head advanced again by the additive
    # Expansion Feature 3 migration (c41f7a9d03e6 revises 3f7a1c9e52b4);
    # same update, same strictness.
    # Expansion F06 disclosure: head/count advanced again by the
    # additive Expansion Feature 6 migration (af39baad9c40 revises
    # c41f7a9d03e6; three knowledge tables); same update, same
    # strictness.
    assert head() == "af39baad9c40"
    assert count() == 235  # 226 at F01 head + 2 F02 tables + 4 F03 + 3 F06 tables
    command.downgrade(config, "85b7a9805207")
    assert count() == 226
    command.upgrade(config, "head")
    assert count() == 235


# -------------------------------------------------------------- seeding
async def test_registry_is_seeded_with_honest_states(app_f02):
    svc = app_f02.integrations
    status = svc.framework_status()
    # Expansion F03 disclosure: the recorded versioning rule advances
    # the API minor per expansion feature — F03 takes it to 1.3.0.
    # Expansion F06 disclosure: F06 takes it to 1.4.0 by the same rule.
    assert status["api_version"] == "1.4.0"
    assert status["connector_count"] == 18
    assert status["with_adapter"] == 1

    echo = svc.get_connector("local_echo")
    assert echo["lifecycle_status"] == "enabled"
    assert echo["state"] == "configured"
    assert echo["has_adapter"] is True

    stripe = svc.get_connector("stripe")
    assert stripe["source"] == "p07"
    assert stripe["has_adapter"] is False
    assert stripe["state"] == "requires_owner_configuration"
    assert stripe["requires_credential"] is True
    # The declared capability contract mirrors P-07's own map.
    assert {c["name"] for c in stripe["capabilities"]} >= {
        "payment_events", "refunds", "balances"}

    rows, _ = svc.list_connectors(source="p17")
    assert len(rows) == 8
    assert all(r["state"] == "requires_owner_configuration" for r in rows)
    rows, _ = svc.list_connectors(source="p18")
    assert len(rows) == 8


# ------------------------------------------------------------ lifecycle
async def test_register_configure_enable_lifecycle(app_f02):
    svc = app_f02.integrations
    created = svc.register_connector(OWNER, {
        "key": "owner_custom", "name": "Owner Custom",
        "provider": "Example", "kind": "rest_api",
        "capabilities": [{"name": "ping", "permission": "execute_tools",
                          "risk_action": "network.fetch"}]})
    assert created["lifecycle_status"] == "registered"
    assert created["state"] == "requires_owner_configuration"

    with pytest.raises(ValidationError, match="already registered"):
        svc.register_connector(OWNER, {
            "key": "owner_custom", "name": "Dup", "provider": "Example"})

    # Configuring with an unregistered secret name is refused —
    # typos surface here, not at invocation time.
    with pytest.raises(ValidationError, match="not registered in the P-10"):
        svc.configure_connector(OWNER, "owner_custom",
                                {"credential_secret_name": "nope"})

    # A connector with no adapter can never be enabled: enabling
    # would claim a connector that does not exist.
    with pytest.raises(ValidationError, match="no implemented adapter"):
        svc.set_enabled(OWNER, "owner_custom", True)

    configured = svc.configure_connector(OWNER, "owner_custom",
                                         {"settings": {"region": "eu"}})
    assert configured["lifecycle_status"] == "configured"
    assert configured["settings"] == {"region": "eu"}
    events = audit_events(app_f02, "integration.connector_")
    assert {e.action for e in events} >= {
        "integration.connector_registered", "integration.connector_configured"}


async def test_reference_connector_end_to_end(app_f02):
    svc = app_f02.integrations
    health = await svc.health_check(OWNER, "local_echo")
    assert health["state"] == "configured"
    assert health["last_health_at"] is not None

    result = await svc.invoke(OWNER, "local_echo", "echo",
                              {"message": "hello framework"})
    assert result["outcome"] == "success"
    assert result["result"]["echo"] == "hello framework"
    assert result["broker_decision_id"] is not None

    invocations, total = svc.list_invocations(connector_key="local_echo")
    assert total == 1
    assert invocations[0]["outcome"] == "success"
    assert invocations[0]["broker_decision_id"] == result["broker_decision_id"]
    assert audit_events(app_f02, "integration.invoked")

    echo = svc.get_connector("local_echo")
    assert echo["last_invoked_at"] is not None


async def test_disable_blocks_invocation_honestly(app_f02):
    svc = app_f02.integrations
    svc.set_enabled(OWNER, "local_echo", False)
    with pytest.raises(IntegrationError):
        await svc.invoke(OWNER, "local_echo", "echo", {"message": "x"})
    invocations, _ = svc.list_invocations(connector_key="local_echo",
                                          outcome="not_configured")
    assert len(invocations) == 1
    svc.set_enabled(OWNER, "local_echo", True)
    result = await svc.invoke(OWNER, "local_echo", "echo", {"message": "back"})
    assert result["outcome"] == "success"


async def test_unconfigured_connector_fails_honestly_never_fakes(app_f02):
    svc = app_f02.integrations
    # Stripe is registered but has no adapter: invocation is an
    # honest requires_owner_configuration failure, recorded.
    with pytest.raises(IntegrationError) as excinfo:
        await svc.invoke(OWNER, "stripe", "balances", {})
    assert excinfo.value.details["outcome"] == "requires_owner_configuration"
    invocations, _ = svc.list_invocations(
        connector_key="stripe", outcome="requires_owner_configuration")
    assert len(invocations) == 1
    # And no success was fabricated anywhere.
    _, successes = svc.list_invocations(connector_key="stripe",
                                        outcome="success")
    assert successes == 0


async def test_undeclared_capability_and_bad_payload_are_refused(app_f02):
    svc = app_f02.integrations
    with pytest.raises(ValidationError, match="not declared"):
        await svc.invoke(OWNER, "local_echo", "teleport", {})
    with pytest.raises(ValidationError, match="input schema"):
        await svc.invoke(OWNER, "local_echo", "echo", {"message": 42})
    with pytest.raises(ValidationError, match="input schema"):
        await svc.invoke(OWNER, "local_echo", "echo", {"wrong": "field"})
    outcomes = {row["outcome"] for row in
                svc.list_invocations(connector_key="local_echo")[0]}
    assert outcomes == {"invalid_request"}


async def test_idempotent_replay_never_reexecutes(app_f02):
    svc = app_f02.integrations
    first = await svc.invoke(OWNER, "local_echo", "echo",
                             {"message": "once"}, idempotency_key="req-1")
    second = await svc.invoke(OWNER, "local_echo", "echo",
                              {"message": "once"}, idempotency_key="req-1")
    assert first["outcome"] == "success"
    assert second["outcome"] == "duplicate"
    assert second["result"] == first["result"]
    _, successes = svc.list_invocations(connector_key="local_echo",
                                        outcome="success")
    assert successes == 1
    _, duplicates = svc.list_invocations(connector_key="local_echo",
                                         outcome="duplicate")
    assert duplicates == 1


# ----------------------------------------------------------------- HTTP
def test_http_surface_and_catalogue(client_f02):
    headers = owner_http_headers(client_f02)
    resp = client_f02.get("/api/v1/integrations", headers=headers)
    assert resp.status_code == 200
    keys = {row["key"] for row in resp.json()["data"]}
    assert {"local_echo", "stripe"} <= keys

    resp = client_f02.post("/api/v1/integrations/local_echo/invoke",
                           headers=headers,
                           json={"capability": "echo",
                                 "payload": {"message": "over http"}})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["result"]["echo"] == "over http"

    resp = client_f02.get("/api/v1/integrations/framework/status",
                          headers=headers)
    # Expansion F03 disclosure: API version advanced to 1.3.0 (above).
    # Expansion F06 disclosure: API version advanced to 1.4.0 (above).
    assert resp.json()["data"]["api_version"] == "1.4.0"

    resp = client_f02.get("/api/v1/integrations/api-catalogue",
                          headers=headers)
    catalogue = resp.json()["data"]
    invoke = next(op for op in catalogue["operations"]
                  if op["path"] == "/api/v1/integrations/{key}/invoke")
    assert invoke["required_permission"] == "execute_tools"
    assert catalogue["by_authorization_depth"]["public"] == 3


def test_http_requires_authentication(client_f02):
    assert client_f02.get("/api/v1/integrations").status_code == 401
    assert client_f02.post(
        "/api/v1/integrations/local_echo/invoke",
        json={"capability": "echo", "payload": {"message": "x"}}).status_code == 401


def test_http_non_owner_cannot_configure(client_f02):
    # The service principal holds no modify_system_config: the
    # route gate refuses before the service is reached.
    resp = client_f02.post("/api/v1/integrations/local_echo/disable",
                           headers=service_http_headers())
    assert resp.status_code == 403
    resp = client_f02.post("/api/v1/integrations",
                           headers=service_http_headers(),
                           json={"key": "sneaky", "name": "S",
                                 "provider": "P"})
    assert resp.status_code == 403
