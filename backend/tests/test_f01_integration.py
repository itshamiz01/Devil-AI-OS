"""Expansion Feature 1 integration tests: migration cycle, the
device lifecycle (enrol → trust → bind → untrust/revoke/rotate)
through the real P-01 login path, the recovery-code lifecycle
(generate → verify → single-use → regenerate-invalidates), and
the HTTP surface.
"""
from __future__ import annotations

import hashlib

from tests.conftest import OWNER
from tests.f01_support import (
    PASSWORD, app_ids, audit_events, client_ids, enrol_device,
    login_with_device, owner_http_headers,
)


# ------------------------------------------------------------ migration
def test_f01_migration_cycle(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    db = tmp_path / "f01_cycle.db"
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

    def session_columns() -> set:
        with engine.connect() as conn:
            return {r[1] for r in conn.execute(text(
                "PRAGMA table_info(app_sessions)"))}

    command.upgrade(config, "head")
    # Expansion F02 disclosure: head advanced again by the additive
    # Expansion Feature 2 migration (3f7a1c9e52b4 revises 85b7a9805207);
    # same update, same strictness.
    # Expansion F03 disclosure: head advanced again by the additive
    # Expansion Feature 3 migration (c41f7a9d03e6 revises 3f7a1c9e52b4);
    # same update, same strictness.
    # Expansion F06 disclosure: head/count advanced again by the
    # additive Expansion Feature 6 migration (af39baad9c40 revises
    # c41f7a9d03e6; three knowledge tables); same update, same
    # strictness.
    assert head() == "af39baad9c40"
    assert count() == 235  # 224 at P-18 head + 2 F01 + 2 F02 + 4 F03 + 3 F06 tables
    assert "device_id" in session_columns()
    command.downgrade(config, "218ddd92a0aa")
    assert count() == 224
    assert "device_id" not in session_columns()
    command.upgrade(config, "head")
    assert count() == 235
    assert "device_id" in session_columns()


# -------------------------------------------------------------- devices
async def test_enrolment_starts_untrusted_and_secret_is_shown_once(app_ids):
    svc = app_ids.security.devices
    created, secret = enrol_device(app_ids, "Kitchen tablet")
    assert created["trust_status"] == "untrusted"
    assert created["label"] == "Kitchen tablet"
    assert len(secret) >= 32
    # The stored row holds only the SHA-256 hash of the secret.
    session = app_ids.session_factory()
    try:
        from app.database.models.security import SecurityDevice
        row = session.get(SecurityDevice, created["id"])
        assert row.secret_hash == hashlib.sha256(secret.encode()).hexdigest()
        assert row.secret_hash != secret
    finally:
        session.close()
    # No later surface returns the secret or its hash.
    for view in (svc.get_device(OWNER, created["id"]),
                 *svc.list_devices(OWNER)):
        assert "device_secret" not in view
        assert "secret_hash" not in view
    events = audit_events(app_ids, "security.device_enrolled")
    assert len(events) == 1
    assert secret not in str(events[0].details)


async def test_trusted_device_binds_session_at_login(app_ids):
    created, secret = enrol_device(app_ids, trust=True)
    token = login_with_device(app_ids, created["id"], secret)
    assert token is not None
    principal = app_ids.auth.resolve_bearer(token)
    assert principal is not None and principal.type.value == "owner"
    # The session row is bound, visible in the owner session list,
    # and the device's last-seen moved at login.
    sessions = app_ids.security.sessions.list_sessions(OWNER)
    bound = [s for s in sessions if s["device_id"] == created["id"]]
    assert len(bound) == 1
    device = app_ids.security.devices.get_device(OWNER, created["id"])
    assert device["last_seen_at"] is not None
    assert audit_events(app_ids, "security.device_login")


async def test_unbound_login_is_unchanged_legacy_behaviour(app_ids):
    token = app_ids.auth.login("owner", PASSWORD)
    assert token is not None
    sessions = app_ids.security.sessions.list_sessions(OWNER)
    assert sessions and all(s["device_id"] is None for s in sessions)


async def test_untrust_kills_bound_sessions(app_ids):
    created, secret = enrol_device(app_ids, trust=True)
    token = login_with_device(app_ids, created["id"], secret)
    assert app_ids.auth.resolve_bearer(token) is not None
    app_ids.security.devices.set_trust(OWNER, created["id"], False)
    assert app_ids.auth.resolve_bearer(token) is None
    sessions = app_ids.security.sessions.list_sessions(OWNER)
    bound = [s for s in sessions if s["device_id"] == created["id"]]
    assert bound and all(s["revoked"] for s in bound)
    # And a fresh login is refused while untrusted.
    assert login_with_device(app_ids, created["id"], secret) is None


async def test_relabel_updates_metadata_only(app_ids):
    created, _secret = enrol_device(app_ids)
    updated = app_ids.security.devices.relabel(
        OWNER, created["id"], {"label": "Renamed", "platform": "linux"})
    assert updated["label"] == "Renamed"
    assert updated["platform"] == "linux"
    assert updated["trust_status"] == "untrusted"
    assert audit_events(app_ids, "security.device_relabelled")


# -------------------------------------------------------- recovery codes
async def test_recovery_code_lifecycle(app_ids):
    svc = app_ids.security.recovery_codes
    status0 = svc.status(OWNER)
    assert status0["configured"] is False
    assert status0["unused"] == 0

    batch = svc.generate(OWNER)
    assert batch["count"] == 10 and len(batch["codes"]) == 10
    assert batch["shown_once"] is True
    status = svc.status(OWNER)
    assert status["configured"] is True
    assert status["unused"] == 10 and status["used"] == 0
    # Codes are never retrievable: the status surface has none.
    assert "codes" not in status

    code = batch["codes"][0]
    assert svc.verify(OWNER, code) == {"verified": True}
    # Single-use: the same code never verifies twice.
    assert svc.verify(OWNER, code) == {"verified": False}
    # Owner transcription (case/dashes/spacing) is normalised.
    messy = batch["codes"][1].lower().replace("-", " ")
    assert svc.verify(OWNER, messy) == {"verified": True}
    assert svc.verify(OWNER, "ZZZZ-ZZZZ-ZZZZ") == {"verified": False}
    status = svc.status(OWNER)
    assert status["used"] == 2 and status["unused"] == 8
    actions = {e.action for e in audit_events(app_ids, "security.recovery")}
    assert "security.recovery_codes_generated" in actions
    assert "security.recovery_code_used" in actions
    assert "security.recovery_code_refused" in actions


async def test_regeneration_invalidates_previous_unused_codes(app_ids):
    svc = app_ids.security.recovery_codes
    first = svc.generate(OWNER, count=4)
    assert svc.verify(OWNER, first["codes"][0]) == {"verified": True}
    second = svc.generate(OWNER, count=4)
    assert second["invalidated_previous"] == 3  # 4 minted - 1 used
    # An unused code from the old batch is dead; the used one stays used.
    assert svc.verify(OWNER, first["codes"][1]) == {"verified": False}
    # The new batch works.
    assert svc.verify(OWNER, second["codes"][0]) == {"verified": True}
    status = svc.status(OWNER)
    assert status["batches"] == 2
    assert status["invalidated"] == 3
    assert status["used"] == 2 and status["unused"] == 3


# ------------------------------------------------------------------ HTTP
def test_http_device_and_recovery_surface(client_ids):
    headers = owner_http_headers(client_ids)
    created = client_ids.post(
        "/api/v1/security/devices", headers=headers,
        json={"label": "HTTP device", "platform": "windows"})
    assert created.status_code == 201, created.text
    device = created.json()["data"]
    secret = device["device_secret"]
    assert device["trust_status"] == "untrusted"

    listed = client_ids.get("/api/v1/security/devices", headers=headers)
    assert listed.status_code == 200
    rows = listed.json()["data"]
    assert len(rows) == 1 and "device_secret" not in rows[0]
    assert "secret_hash" not in rows[0]

    trusted = client_ids.post(
        f"/api/v1/security/devices/{device['id']}/trust", headers=headers)
    assert trusted.status_code == 200
    assert trusted.json()["data"]["trust_status"] == "trusted"

    # Device-bound login over real HTTP; the session list shows it.
    login = client_ids.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": PASSWORD,
              "device_id": device["id"], "device_secret": secret})
    assert login.status_code == 200, login.text
    sessions = client_ids.get("/api/v1/security/auth/sessions", headers=headers)
    bound = [s for s in sessions.json()["data"]
             if s.get("device_id") == device["id"]]
    assert len(bound) == 1

    gen = client_ids.post(
        "/api/v1/security/auth/recovery-codes/generate",
        headers=headers, json={"count": 3})
    assert gen.status_code == 201, gen.text
    codes = gen.json()["data"]["codes"]
    assert len(codes) == 3
    status = client_ids.get(
        "/api/v1/security/auth/recovery-codes", headers=headers)
    assert status.json()["data"]["unused"] == 3
    verify = client_ids.post(
        "/api/v1/security/auth/recovery-codes/verify",
        headers=headers, json={"code": codes[0]})
    assert verify.json()["data"] == {"verified": True}
    again = client_ids.post(
        "/api/v1/security/auth/recovery-codes/verify",
        headers=headers, json={"code": codes[0]})
    assert again.json()["data"] == {"verified": False}

    revoked = client_ids.post(
        f"/api/v1/security/devices/{device['id']}/revoke", headers=headers)
    assert revoked.status_code == 200
    assert revoked.json()["data"]["trust_status"] == "revoked"
    assert revoked.json()["data"]["revoked_by"] == "owner:owner"
    # The HTTP session bound to the device is dead too.
    dead = client_ids.get(
        "/api/v1/auth/me",
        headers={"Authorization":
                 f"Bearer {login.json()['data']['access_token']}"})
    assert dead.status_code == 401


def test_http_trust_state_machine_errors_are_409(client_ids):
    headers = owner_http_headers(client_ids)
    created = client_ids.post(
        "/api/v1/security/devices", headers=headers, json={"label": "D"})
    device_id = created.json()["data"]["id"]
    # Trusting twice is a state error, not a silent no-op.
    assert client_ids.post(
        f"/api/v1/security/devices/{device_id}/trust",
        headers=headers).status_code == 200
    assert client_ids.post(
        f"/api/v1/security/devices/{device_id}/trust",
        headers=headers).status_code == 409
    # Revoked is terminal: trust after revoke is refused.
    assert client_ids.post(
        f"/api/v1/security/devices/{device_id}/revoke",
        headers=headers).status_code == 200
    assert client_ids.post(
        f"/api/v1/security/devices/{device_id}/trust",
        headers=headers).status_code == 409
