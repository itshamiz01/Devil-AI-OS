"""Expansion Feature 2 security tests: broker-gated invocation
(permission + risk gates incl. hash-bound Level-3 approvals),
credential non-storage and P-10-brokered resolution, revoked
credentials, adapter failure modes from the mock harness (auth
failure, timeout, rate limit), and owner-only lifecycle control.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from app.core.exceptions import PermissionDeniedError
from app.integrations.service import IntegrationError
from app.permissions.models import Principal, PrincipalType
from tests.conftest import AGENT, OWNER, SERVICE
from tests.f02_support import (
    app_f02, attach_mock, audit_events, register_secret,
)

SECRET_VALUE = "sk-test-VALUE-that-must-never-be-stored-12345"


# ------------------------------------------------------- broker gating
async def test_principal_without_capability_permission_is_denied(app_f02):
    # local_echo.echo requires read_system_data at the broker; an
    # external principal holds no permissions at all — the broker
    # denies and the denial is recorded, with a broker decision id
    # attached. (Positive control: the agent role DOES hold
    # read_system_data and its Level-0 invocation is authorized —
    # the gate is permission-based, not a blanket refusal.)
    svc = app_f02.integrations
    allowed = await svc.invoke(AGENT, "local_echo", "echo",
                               {"message": "agent may read"})
    assert allowed["outcome"] == "success"

    from tests.conftest import EXTERNAL
    with pytest.raises(PermissionDeniedError):
        await svc.invoke(EXTERNAL, "local_echo", "echo", {"message": "hi"})
    invocations, _ = svc.list_invocations(connector_key="local_echo",
                                          outcome="denied")
    assert len(invocations) == 1
    assert invocations[0]["broker_decision_id"] is not None
    decisions, _ = app_f02.security.broker.list_decisions(
        principal_id=EXTERNAL.id, allowed=False)
    assert decisions and decisions[0]["permission"] == "read_system_data"


async def test_level3_capability_requires_hash_bound_owner_approval(app_f02):
    # A capability whose risk action P-10 classifies CRITICAL
    # (financial.transfer) cannot run on grants alone: it needs an
    # owner-decided approval bound to this exact call.
    from app.integrations.interfaces.base import (
        Capability, ConnectorDescriptor,
    )
    from app.integrations.testing import MockConnectorAdapter

    descriptor = ConnectorDescriptor(
        key="critical_mock", name="Critical mock", provider="Tests",
        kind="custom",
        capabilities=(Capability(
            name="move", permission="request_financial_operations",
            risk_action="financial.transfer",
            input_schema={"type": "object",
                          "properties": {"value": {"type": "string"}},
                          "additionalProperties": True}),))
    adapter = MockConnectorAdapter(key="critical_mock")
    adapter.descriptor = descriptor
    svc = app_f02.integrations
    svc.attach_adapter(OWNER, adapter)
    svc.set_enabled(OWNER, "critical_mock", True)

    payload = {"value": "x"}
    with pytest.raises(PermissionDeniedError):
        await svc.invoke(OWNER, "critical_mock", "move", payload)

    payload_hash = hashlib.sha256(json.dumps(
        payload, sort_keys=True, default=str).encode()).hexdigest()
    params = {"connector": "critical_mock", "capability": "move",
              "payload_sha256": payload_hash}

    # An approval bound to DIFFERENT parameters does not authorize.
    wrong = app_f02.approvals.create(
        OWNER, action="financial.transfer", resource="integration:critical_mock",
        risk_classification="critical", reason="wrong params",
        requested_permissions=["request_financial_operations"],
        parameters={**params, "payload_sha256": "0" * 64})
    app_f02.approvals.decide(wrong.id, OWNER, True)
    with pytest.raises(PermissionDeniedError):
        await svc.invoke(OWNER, "critical_mock", "move", payload,
                         approval_id=wrong.id)

    # The exactly-bound, owner-decided approval does.
    approval = app_f02.approvals.create(
        OWNER, action="financial.transfer", resource="integration:critical_mock",
        risk_classification="critical", reason="exact call",
        requested_permissions=["request_financial_operations"],
        parameters=params)
    app_f02.approvals.decide(approval.id, OWNER, True)
    result = await svc.invoke(OWNER, "critical_mock", "move", payload,
                              approval_id=approval.id)
    assert result["outcome"] == "success"


# --------------------------------------------------------- credentials
async def test_credential_resolved_only_through_p10_and_never_stored(
        app_f02, monkeypatch):
    monkeypatch.setenv("AUTONOMUS_MOCK_KEY", SECRET_VALUE)
    register_secret(app_f02, "mock_api_key", "AUTONOMUS_MOCK_KEY")
    adapter = attach_mock(app_f02, requires_credential=True)
    svc = app_f02.integrations

    result = await svc.invoke(OWNER, "mock_connector", "ping",
                              {"value": "hello"})
    assert result["outcome"] == "success"
    # The adapter saw a credential inside the brokered callback…
    assert adapter.calls[0]["credential_present"] is True
    # …P-10 recorded the brokered access (name + outcome only)…
    events, _ = app_f02.security.secrets.list_access_events(
        secret_name="mock_api_key")
    assert events and events[0]["outcome"] == "granted"
    # …and the secret VALUE exists nowhere in the framework's
    # tables or the audit trail.
    session = app_f02.session_factory()
    try:
        from sqlalchemy import text
        for table in ("integration_connectors", "integration_invocations",
                      "audit_events", "security_secret_metadata"):
            rows = session.execute(text(f"SELECT * FROM {table}")).fetchall()
            assert SECRET_VALUE not in str(rows), table
    finally:
        session.close()


async def test_revoked_credential_fails_as_requires_owner_configuration(
        app_f02, monkeypatch):
    monkeypatch.setenv("AUTONOMUS_MOCK_KEY", SECRET_VALUE)
    register_secret(app_f02, "mock_api_key", "AUTONOMUS_MOCK_KEY")
    attach_mock(app_f02, requires_credential=True)
    svc = app_f02.integrations
    assert (await svc.invoke(OWNER, "mock_connector", "ping", {}))["outcome"] \
        == "success"

    app_f02.security.secrets.revoke(OWNER, "mock_api_key")
    with pytest.raises(IntegrationError) as excinfo:
        await svc.invoke(OWNER, "mock_connector", "ping", {})
    assert excinfo.value.details["outcome"] == "requires_owner_configuration"
    assert svc.get_connector("mock_connector")["state"] == \
        "requires_owner_configuration"


async def test_missing_credential_value_fails_honestly(app_f02):
    # Secret registered in P-10 but the environment value is absent:
    # resolution fails closed — never a fabricated success.
    register_secret(app_f02, "mock_api_key", "AUTONOMUS_DEFINITELY_UNSET_KEY")
    attach_mock(app_f02, requires_credential=True)
    svc = app_f02.integrations
    with pytest.raises(IntegrationError) as excinfo:
        await svc.invoke(OWNER, "mock_connector", "ping", {})
    assert excinfo.value.details["outcome"] == "requires_owner_configuration"


# ------------------------------------------------------ adapter failures
async def test_adapter_auth_failure_and_error_are_recorded(app_f02):
    attach_mock(app_f02, behaviour="auth_error", key="auth_mock")
    svc = app_f02.integrations
    with pytest.raises(IntegrationError):
        await svc.invoke(OWNER, "auth_mock", "ping", {})
    connector = svc.get_connector("auth_mock")
    assert connector["state"] == "error"
    assert connector["error_count"] == 1
    invocations, _ = svc.list_invocations(connector_key="auth_mock",
                                          outcome="error")
    assert len(invocations) == 1
    assert "401" in invocations[0]["error_detail"]


async def test_adapter_timeout_is_recorded_as_error(app_f02):
    attach_mock(app_f02, behaviour="timeout", key="slow_mock")
    svc = app_f02.integrations
    with pytest.raises(IntegrationError) as excinfo:
        await svc.invoke(OWNER, "slow_mock", "ping", {}, timeout_seconds=0.2)
    assert "timed out" in str(excinfo.value.message)
    invocations, _ = svc.list_invocations(connector_key="slow_mock",
                                          outcome="error")
    assert len(invocations) == 1


async def test_rate_limit_is_enforced_from_recorded_history(app_f02):
    attach_mock(app_f02, rate_limit_per_minute=2, key="limited_mock")
    svc = app_f02.integrations
    for _ in range(2):
        result = await svc.invoke(OWNER, "limited_mock", "ping", {})
        assert result["outcome"] == "success"
    with pytest.raises(IntegrationError) as excinfo:
        await svc.invoke(OWNER, "limited_mock", "ping", {})
    assert excinfo.value.details["outcome"] == "rate_limited"
    _, limited = svc.list_invocations(connector_key="limited_mock",
                                      outcome="rate_limited")
    assert limited == 1


async def test_unhealthy_adapter_reports_error_state(app_f02):
    attach_mock(app_f02, behaviour="unhealthy", key="sick_mock")
    svc = app_f02.integrations
    health = await svc.health_check(OWNER, "sick_mock")
    assert health["state"] == "error"
    assert health["error_count"] == 1


# --------------------------------------------------------- owner control
async def test_lifecycle_acts_are_owner_only(app_f02):
    svc = app_f02.integrations
    agent = Principal(PrincipalType.AGENT, "agent-9")
    with pytest.raises(PermissionDeniedError):
        svc.register_connector(agent, {"key": "x", "name": "X",
                                       "provider": "P"})
    with pytest.raises(PermissionDeniedError):
        svc.configure_connector(agent, "local_echo", {"settings": {}})
    with pytest.raises(PermissionDeniedError):
        svc.set_enabled(SERVICE, "local_echo", False)
    # The connector is untouched by all three attempts.
    assert svc.get_connector("local_echo")["lifecycle_status"] == "enabled"


async def test_webhook_verification_uses_brokered_secret(app_f02, monkeypatch):
    # The framework's webhook verification runs through P-10's
    # brokered secret use; a connector without the hook refuses
    # honestly. (No public webhook route is added by the framework.)
    monkeypatch.setenv("AUTONOMUS_MOCK_KEY", SECRET_VALUE)
    register_secret(app_f02, "mock_api_key", "AUTONOMUS_MOCK_KEY")
    attach_mock(app_f02, requires_credential=True)
    svc = app_f02.integrations
    with pytest.raises(Exception) as excinfo:
        svc.verify_webhook(OWNER, "mock_connector", b"{}", {})
    assert "does not verify webhook signatures" in str(excinfo.value)
    assert audit_events(app_f02, "security.secret_access")
