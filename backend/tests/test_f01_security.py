"""Expansion Feature 1 security tests: the refusal paths.

Non-owner principals are refused at the service layer and over
HTTP; device logins are refused for unknown / untrusted / revoked
devices and bad secrets (each audited, each counted by the login
guard); revocation is terminal and kills live sessions; rotation
kills the old credential and its sessions; recovery-code
plaintext exists nowhere in the database or the audit trail.
"""
from __future__ import annotations

import pytest

from app.core.exceptions import (
    InvalidStateTransitionError, PermissionDeniedError,
)
from tests.conftest import AGENT, EXTERNAL, OWNER, SERVICE
from tests.f01_support import (
    PASSWORD, app_ids, audit_events, client_ids, enrol_device,
    login_with_device, owner_http_headers, service_http_headers,
)


# ------------------------------------------------------- owner-only ops
@pytest.mark.parametrize("principal", [AGENT, SERVICE, EXTERNAL],
                         ids=["agent", "service", "external"])
async def test_non_owner_refused_every_device_operation(app_ids, principal):
    devices = app_ids.security.devices
    created, _secret = enrol_device(app_ids)
    with pytest.raises(PermissionDeniedError):
        devices.enrol(principal, {"label": "rogue"})
    with pytest.raises(PermissionDeniedError):
        devices.list_devices(principal)
    with pytest.raises(PermissionDeniedError):
        devices.get_device(principal, created["id"])
    with pytest.raises(PermissionDeniedError):
        devices.set_trust(principal, created["id"], True)
    with pytest.raises(PermissionDeniedError):
        devices.revoke(principal, created["id"])
    with pytest.raises(PermissionDeniedError):
        devices.rotate_secret(principal, created["id"])
    codes = app_ids.security.recovery_codes
    with pytest.raises(PermissionDeniedError):
        codes.generate(principal)
    with pytest.raises(PermissionDeniedError):
        codes.status(principal)
    with pytest.raises(PermissionDeniedError):
        codes.verify(principal, "AAAA-BBBB-CCCC")


async def test_non_owner_http_refusals(client_ids):
    # The service principal holds read_system_data (route guard
    # passes) but the service layer is owner-only: 403 either way.
    listed = client_ids.get("/api/v1/security/devices",
                            headers=service_http_headers())
    assert listed.status_code == 403
    created = client_ids.post("/api/v1/security/devices",
                              headers=service_http_headers(),
                              json={"label": "rogue"})
    assert created.status_code == 403
    gen = client_ids.post("/api/v1/security/auth/recovery-codes/generate",
                          headers=service_http_headers(), json={"count": 2})
    assert gen.status_code == 403
    unauthenticated = client_ids.get("/api/v1/security/devices")
    assert unauthenticated.status_code == 401


# --------------------------------------------------- device login refusals
async def test_login_refused_for_unknown_device(app_ids):
    assert login_with_device(app_ids, "no-such-device", "whatever") is None
    events = audit_events(app_ids, "security.device_credential_refused")
    assert len(events) == 1
    assert events[0].details["reason"] == "unknown_device"


async def test_login_refused_for_untrusted_device(app_ids):
    created, secret = enrol_device(app_ids)  # stays untrusted
    assert login_with_device(app_ids, created["id"], secret) is None
    events = audit_events(app_ids, "security.device_credential_refused")
    assert events[0].details["reason"] == "device_not_trusted"


async def test_login_refused_for_bad_secret_and_audited(app_ids):
    created, secret = enrol_device(app_ids, trust=True)
    assert login_with_device(app_ids, created["id"], "wrong-secret") is None
    events = audit_events(app_ids, "security.device_credential_refused")
    assert events[0].details["reason"] == "bad_secret"
    # The secret (real or attempted) never reaches the audit trail.
    assert secret not in str(events[0].details)
    assert "wrong-secret" not in str(events[0].details)
    # The refusal counts as a failed login for throttling/alerts.
    session = app_ids.session_factory()
    try:
        from sqlalchemy import func, select
        from app.database.models.security import SecurityLoginAttempt
        failures = session.scalar(
            select(func.count()).select_from(SecurityLoginAttempt).where(
                SecurityLoginAttempt.success == False))  # noqa: E712
    finally:
        session.close()
    assert failures >= 1


async def test_login_refused_with_partial_device_fields(app_ids):
    created, secret = enrol_device(app_ids, trust=True)
    # device_id without its secret (and vice versa) fails closed.
    assert app_ids.auth.login("owner", PASSWORD,
                              device_id=created["id"]) is None
    assert app_ids.auth.login("owner", PASSWORD,
                              device_secret=secret) is None


async def test_device_credential_does_not_replace_password(app_ids):
    created, secret = enrol_device(app_ids, trust=True)
    # A valid device credential with a WRONG password still fails:
    # the device is a binding, never a password substitute.
    assert app_ids.auth.login("owner", "not-the-password",
                              device_id=created["id"],
                              device_secret=secret) is None


# ------------------------------------------- revocation / rotation kills
async def test_revocation_is_terminal_and_kills_sessions(app_ids):
    created, secret = enrol_device(app_ids, trust=True)
    token = login_with_device(app_ids, created["id"], secret)
    assert app_ids.auth.resolve_bearer(token) is not None
    app_ids.security.devices.revoke(OWNER, created["id"])
    # The live token dies with the device.
    assert app_ids.auth.resolve_bearer(token) is None
    # Fresh logins are refused, audited as device_revoked.
    assert login_with_device(app_ids, created["id"], secret) is None
    reasons = {e.details.get("reason") for e in
               audit_events(app_ids, "security.device_credential_refused")}
    assert "device_revoked" in reasons
    # Terminal: no way back, no rotation, no second revoke.
    with pytest.raises(InvalidStateTransitionError):
        app_ids.security.devices.set_trust(OWNER, created["id"], True)
    with pytest.raises(InvalidStateTransitionError):
        app_ids.security.devices.rotate_secret(OWNER, created["id"])
    with pytest.raises(InvalidStateTransitionError):
        app_ids.security.devices.revoke(OWNER, created["id"])


async def test_rotation_kills_old_secret_and_its_sessions(app_ids):
    created, secret = enrol_device(app_ids, trust=True)
    token = login_with_device(app_ids, created["id"], secret)
    rotated = app_ids.security.devices.rotate_secret(OWNER, created["id"])
    new_secret = rotated["device_secret"]
    assert new_secret != secret
    assert app_ids.auth.resolve_bearer(token) is None
    assert login_with_device(app_ids, created["id"], secret) is None
    assert login_with_device(app_ids, created["id"], new_secret) is not None
    assert audit_events(app_ids, "security.device_secret_rotated")


# ------------------------------------------------- recovery-code hygiene
async def test_recovery_code_plaintext_exists_nowhere_in_storage(app_ids):
    svc = app_ids.security.recovery_codes
    batch = svc.generate(OWNER, count=3)
    session = app_ids.session_factory()
    try:
        from sqlalchemy import select
        from app.database.models.security import SecurityRecoveryCode
        rows = list(session.scalars(select(SecurityRecoveryCode)))
    finally:
        session.close()
    assert len(rows) == 3
    for code in batch["codes"]:
        normalized = code.replace("-", "")
        for row in rows:
            assert code not in row.code_hash
            assert normalized not in row.code_hash
            assert row.code_hash.startswith("scrypt$")
    # Nor in any audit detail.
    for event in audit_events(app_ids, "security.recovery"):
        for code in batch["codes"]:
            assert code not in str(event.details)


async def test_recovery_verify_for_other_identity_is_refused(app_ids):
    svc = app_ids.security.recovery_codes
    batch = svc.generate(OWNER, count=1)
    with pytest.raises(PermissionDeniedError):
        svc.verify(AGENT, batch["codes"][0])
    # The refused attempt did not consume the code.
    assert svc.verify(OWNER, batch["codes"][0]) == {"verified": True}
