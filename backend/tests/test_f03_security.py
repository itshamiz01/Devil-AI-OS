"""Expansion Feature 3 security tests: the owner-only channel
(non-owner, agent, service and external principals refused at the
service layer and over HTTP), confirmation binding (plan drift
refuses; double confirmation refuses), the impossibility of
attaching the test double over HTTP, audit-trail evidence for the
voice acts, per-owner record isolation, and the plan pipeline's
own mode gate applying unchanged to voice-originated execution.
"""
from __future__ import annotations

import pytest

from app.core.exceptions import (
    ApprovalError, InvalidStateTransitionError, NotFoundError,
    PermissionDeniedError,
)
from app.permissions.models import Principal, PrincipalType
from tests.conftest import AGENT, EXTERNAL, OWNER, SERVICE
from tests.f03_support import (
    app_f03, audit_events, client_f03, make_session, owner_http_headers,
    service_http_headers,
)

OTHER_OWNER = Principal(PrincipalType.OWNER, "owner-2")


# ------------------------------------------------------- owner-only
async def test_non_owner_principals_are_refused_by_the_service(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    transcript = svc.create_manual_transcript(
        OWNER, session["id"], "echo delete the old backups")
    command = await svc.interpret(OWNER, transcript["id"])
    for principal in (AGENT, SERVICE, EXTERNAL):
        with pytest.raises(PermissionDeniedError):
            svc.create_session(principal, {"title": "nope"})
        with pytest.raises(PermissionDeniedError):
            svc.list_sessions(principal)
        with pytest.raises(PermissionDeniedError):
            svc.get_session(principal, session["id"])
        with pytest.raises(PermissionDeniedError):
            await svc.interpret(principal, transcript["id"])
        with pytest.raises(PermissionDeniedError):
            await svc.confirm(principal, command["id"])
        with pytest.raises(PermissionDeniedError):
            svc.reject(principal, command["id"])
        with pytest.raises(PermissionDeniedError):
            svc.delete_session(principal, session["id"])
    # The command is untouched by all of that.
    assert svc.get_command(OWNER, command["id"])["status"] == \
        "awaiting_confirmation"


def test_voice_records_are_isolated_per_owner(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    rows, total = svc.list_sessions(OTHER_OWNER)
    assert total == 0
    with pytest.raises(NotFoundError):
        svc.get_session(OTHER_OWNER, session["id"])


def test_http_non_owner_is_refused(client_f03):
    # The service principal holds read_system_data, so it passes
    # the route gate — the service layer still refuses it (the
    # two-depth pattern), because voice data is the owner's.
    resp = client_f03.get("/api/v1/voice/sessions",
                          headers=service_http_headers())
    assert resp.status_code == 403, resp.text
    resp = client_f03.post("/api/v1/voice/sessions",
                           headers=service_http_headers(),
                           json={"title": "nope"})
    assert resp.status_code == 403, resp.text
    # Confirmation is gated on approve_actions at the route: the
    # service principal never reaches the service at all.
    resp = client_f03.post("/api/v1/voice/commands/whatever/confirm",
                           headers=service_http_headers())
    assert resp.status_code == 403, resp.text
    # Unauthenticated is refused outright.
    resp = client_f03.get("/api/v1/voice/sessions")
    assert resp.status_code in (401, 403), resp.text


# ------------------------------------------------- confirmation binding
async def test_confirmation_refuses_a_plan_that_changed(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    transcript = svc.create_manual_transcript(
        OWNER, session["id"], "echo delete the old backups")
    command = await svc.interpret(OWNER, transcript["id"])
    assert command["status"] == "awaiting_confirmation"

    # Tamper with the plan after it was shown: the confirmation
    # hash no longer binds, so confirmation must refuse.
    from app.database.repositories.intelligence import PlanRepository
    session_db = app_f03.session_factory()
    try:
        repo = PlanRepository(session_db)
        plan = repo.get(command["plan_id"])
        plan.steps[0].payload = {"message": "tampered", "data": {}}
        repo.save(plan)
    finally:
        session_db.close()

    with pytest.raises(ApprovalError):
        await svc.confirm(OWNER, command["id"])
    assert svc.get_command(OWNER, command["id"])["status"] == \
        "awaiting_confirmation"
    actions = [e.action for e in audit_events(app_f03, "voice.")]
    assert "voice.command_confirmation_refused" in actions


async def test_double_confirmation_is_refused(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    transcript = svc.create_manual_transcript(
        OWNER, session["id"], "echo delete the old backups")
    command = await svc.interpret(OWNER, transcript["id"])
    await svc.confirm(OWNER, command["id"])
    with pytest.raises(InvalidStateTransitionError):
        await svc.confirm(OWNER, command["id"])
    with pytest.raises(InvalidStateTransitionError):
        svc.reject(OWNER, command["id"])


# -------------------------------------------------------- fixture safety
def test_no_http_route_can_attach_a_provider(client_f03):
    headers = owner_http_headers(client_f03)
    spec_paths = [p for p in client_f03.get(
        "/openapi.json").json()["paths"] if p.startswith("/api/v1/voice")]
    assert not any("attach" in p for p in spec_paths)
    resp = client_f03.post("/api/v1/voice/providers/attach",
                           headers=headers, json={"name": "fixture"})
    assert resp.status_code in (404, 405), resp.text


def test_fixture_attach_is_owner_only_and_audited(app_f03):
    from app.voice.testing import FixtureSpeechProvider
    with pytest.raises(PermissionDeniedError):
        app_f03.voice.attach_provider(AGENT, FixtureSpeechProvider())
    app_f03.voice.attach_provider(OWNER, FixtureSpeechProvider())
    actions = [e.action for e in audit_events(app_f03, "voice.")]
    assert "voice.provider_attached" in actions
    event = next(e for e in audit_events(app_f03, "voice.provider_attached"))
    assert event.details["is_fixture"] is True


# --------------------------------------------------------------- audit
async def test_voice_acts_land_in_the_shared_audit_trail(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    transcript = svc.create_manual_transcript(
        OWNER, session["id"], "echo audit me")
    await svc.interpret(OWNER, transcript["id"])
    actions = [e.action for e in audit_events(app_f03, "voice.")]
    for expected in ("voice.session_created",
                     "voice.transcript_manual_entry",
                     "voice.command_executed"):
        assert expected in actions


# ------------------------------------------------------------ mode gate
async def test_simulation_mode_blocks_voice_execution(tmp_path):
    # The plan pipeline's own mode gate applies to voice exactly
    # as to text: in simulation mode interpretation succeeds but
    # execution is refused by execute_plan, and the command
    # records the failure honestly.
    from app.core.application import Application
    from tests.conftest import make_settings

    application = Application(make_settings(tmp_path, mode="simulation"))
    await application.startup()
    try:
        svc = application.voice
        session = svc.create_session(OWNER, {"title": "sim"})
        transcript = svc.create_manual_transcript(
            OWNER, session["id"], "echo in simulation")
        command = await svc.interpret(OWNER, transcript["id"])
        assert command["status"] == "failed"
        assert "simulation" in command["error_detail"]
    finally:
        await application.shutdown()
