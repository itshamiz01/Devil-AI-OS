"""Expansion Feature 3 integration tests: migration cycle, the
honest not-configured pipeline (no speech provider available),
the full pipeline over the LABELLED test double (upload →
transcribe → interpret → execute, with fixture provenance on
every record), the confirmation flow for consequential commands,
the stop phrase, manual-entry fallback, retention deletion, and
the HTTP surface.
"""
from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.voice import constants as C
from app.voice.service import VoiceError
from tests.conftest import OWNER
from tests.f03_support import (
    WAV_BYTES, app_f03, attach_fixture, client_f03, make_session,
    owner_http_headers,
)


# ------------------------------------------------------------ migration
def test_f03_migration_cycle(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    db = tmp_path / "f03_cycle.db"
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
    # Expansion Feature 3 migration (c41f7a9d03e6 revises 3f7a1c9e52b4).
    # Expansion F06 disclosure: head/count advanced again by the
    # additive Expansion Feature 6 migration (af39baad9c40 revises
    # c41f7a9d03e6; three knowledge tables); same update, same
    # strictness.
    assert head() == "af39baad9c40"
    assert count() == 235  # 228 at F02 head + 4 F03 + 3 F06 tables
    command.downgrade(config, "3f7a1c9e52b4")
    assert count() == 228
    command.upgrade(config, "head")
    assert count() == 235


# ------------------------------------------------------- honest states
async def test_status_reports_honest_unavailability(app_f03):
    status = await app_f03.voice.status()
    # Expansion F06 disclosure: API version advanced to 1.4.0 under
    # the F02 versioning rule (minor per expansion feature built).
    assert status["api_version"] == "1.4.0"
    # No real speech model exists in staging: both capabilities
    # must say so, in the framework's one vocabulary.
    assert status["stt"]["state"] == C.STATE_REQUIRES_OWNER_CONFIGURATION
    assert status["tts"]["state"] == C.STATE_REQUIRES_OWNER_CONFIGURATION
    assert "DEF-A2" in status["stt"]["detail"]
    providers = {p["name"]: p for p in status["providers"]}
    assert providers["local_whisper"]["available"] is False
    assert providers["local_whisper"]["is_fixture"] is False
    # The fixture double is NOT attached by default.
    assert "fixture_speech_double" not in providers
    assert status["not_implemented"]


async def test_transcription_without_a_provider_is_honest(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    audio = svc.store_audio(
        OWNER, session["id"], filename="note.wav",
        content_type="audio/wav", data=WAV_BYTES)
    with pytest.raises(VoiceError) as excinfo:
        await svc.transcribe(OWNER, audio["id"])
    assert excinfo.value.details["state"] == \
        C.STATE_REQUIRES_OWNER_CONFIGURATION
    # The attempt itself is recorded, honestly labelled.
    rows, _total = svc.list_transcripts(OWNER, session["id"])
    assert len(rows) == 1
    assert rows[0]["status"] == C.TRANSCRIPT_NOT_CONFIGURED
    assert rows[0]["text"] == ""
    assert "faster-whisper" in rows[0]["error_detail"]


# ------------------------------------------------------------- pipeline
async def test_full_pipeline_over_the_labelled_double(app_f03):
    svc = app_f03.voice
    double = attach_fixture(app_f03, transcript_text="echo hello from voice")
    session = make_session(app_f03)
    audio = svc.store_audio(
        OWNER, session["id"], filename="cmd.wav",
        content_type="audio/wav", data=WAV_BYTES)
    assert audio["size_bytes"] == len(WAV_BYTES)
    assert audio["sha256"]

    transcript = await svc.transcribe(OWNER, audio["id"])
    assert transcript["status"] == C.TRANSCRIPT_COMPLETED
    assert transcript["text"] == "echo hello from voice"
    # Fixture provenance is on the record, permanently.
    assert transcript["is_fixture"] is True
    assert transcript["provider_name"] == "fixture_speech_double"
    assert "FIXTURE" in transcript["model_label"]
    assert transcript["confidence"] is None
    assert len(double.transcribe_calls) == 1

    command = await svc.interpret(OWNER, transcript["id"])
    assert command["status"] == C.CMD_COMPLETED
    assert command["category"] == C.CAT_SYSTEM_OPERATION
    assert command["risk_level"] == C.RISK_LOW
    assert command["requires_confirmation"] is False
    assert command["mission_id"] and command["plan_id"]
    assert command["broker_decision_id"]  # P-10 intake decision recorded
    assert "step(s)" in command["result_summary"]
    # The spoken response was synthesized by the double and is
    # labelled fixture in the command detail.
    assert command["speech_state"] == C.STATE_CONFIGURED
    assert command["response_audio_id"]
    assert command["detail"]["speech"]["is_fixture"] is True
    assert len(double.synthesize_calls) == 1
    # The response audio is a real stored record, downloadable.
    row, data, content_type = svc.read_audio(
        OWNER, command["response_audio_id"])
    assert row["kind"] == C.AUDIO_RESPONSE
    assert data[:4] == b"RIFF"
    # And the mission lives in the shared P-02 store (voice/text
    # share context through it).
    mission = app_f03.intelligence.get_mission(command["mission_id"])
    assert mission.text == "echo hello from voice"


async def test_interpretation_of_unplannable_text_needs_clarification(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    transcript = svc.create_manual_transcript(
        OWNER, session["id"], "flibberty gibbet nonsense")
    command = await svc.interpret(OWNER, transcript["id"])
    assert command["status"] == C.CMD_NEEDS_CLARIFICATION
    assert command["category"] == C.CAT_UNRESOLVED
    assert command["plan_id"] is None
    # Nothing executed: the mission exists as the record, unplanned.
    mission = app_f03.intelligence.get_mission(command["mission_id"])
    assert mission.status == "planning_failed"


async def test_manual_entry_is_labelled_as_fallback_not_transcription(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    transcript = svc.create_manual_transcript(
        OWNER, session["id"], "check the system health")
    assert transcript["source"] == C.SOURCE_MANUAL_ENTRY
    assert transcript["provider_name"] is None
    assert "not speech recognition" in transcript["model_label"]
    assert transcript["is_fixture"] is False
    command = await svc.interpret(OWNER, transcript["id"])
    assert command["status"] == C.CMD_COMPLETED
    # The health template's steps are a snapshot plus an echo
    # self-test, so the plan is a system operation, not a pure
    # information request (the classifier reads the plan's shape).
    assert command["category"] == C.CAT_SYSTEM_OPERATION


# ---------------------------------------------------------- confirmation
async def test_consequential_command_waits_for_on_screen_confirmation(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    # The destructive screen makes this consequential even though
    # the underlying plan (an echo) is innocuous: interpretation
    # must stop and show what was understood.
    transcript = svc.create_manual_transcript(
        OWNER, session["id"], "echo delete the old backups")
    command = await svc.interpret(OWNER, transcript["id"])
    assert command["category"] == C.CAT_HIGH_RISK
    assert command["requires_confirmation"] is True
    assert command["status"] == C.CMD_AWAITING_CONFIRMATION
    assert command["plan_hash"]
    # Nothing has executed: the plan is still a draft.
    plan = app_f03.intelligence.get_plan(command["plan_id"])
    assert plan.status == "draft"

    confirmed = await svc.confirm(OWNER, command["id"])
    assert confirmed["status"] == C.CMD_COMPLETED
    assert confirmed["confirmed_by"] == "owner:owner"
    assert confirmed["confirmed_at"]
    plan = app_f03.intelligence.get_plan(command["plan_id"])
    assert plan.status == "completed"


async def test_rejected_command_never_executes(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    transcript = svc.create_manual_transcript(
        OWNER, session["id"], "echo delete the old backups")
    command = await svc.interpret(OWNER, transcript["id"])
    rejected = svc.reject(OWNER, command["id"])
    assert rejected["status"] == C.CMD_REJECTED
    plan = app_f03.intelligence.get_plan(command["plan_id"])
    assert plan.status == "draft"  # never approved, never executed


async def test_spoken_approval_does_not_confirm_anything(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    transcript = svc.create_manual_transcript(
        OWNER, session["id"], "echo delete the old backups")
    command = await svc.interpret(OWNER, transcript["id"])
    assert command["status"] == C.CMD_AWAITING_CONFIRMATION
    # A transcript that says "yes, approve it" is just another
    # command — unplannable, and it changes nothing.
    yes = svc.create_manual_transcript(OWNER, session["id"], "yes approve it")
    yes_command = await svc.interpret(OWNER, yes["id"])
    assert yes_command["status"] == C.CMD_NEEDS_CLARIFICATION
    still = svc.get_command(OWNER, command["id"])
    assert still["status"] == C.CMD_AWAITING_CONFIRMATION
    plan = app_f03.intelligence.get_plan(command["plan_id"])
    assert plan.status == "draft"


async def test_stop_phrase_cancels_pending_commands(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    transcript = svc.create_manual_transcript(
        OWNER, session["id"], "echo delete the old backups")
    command = await svc.interpret(OWNER, transcript["id"])
    assert command["status"] == C.CMD_AWAITING_CONFIRMATION
    stop = svc.create_manual_transcript(OWNER, session["id"], "stop")
    stop_command = await svc.interpret(OWNER, stop["id"])
    assert stop_command["detail"]["stop_applied"] is True
    assert stop_command["detail"]["cancelled_command_ids"] == [command["id"]]
    assert svc.get_command(OWNER, command["id"])["status"] == C.CMD_CANCELLED


async def test_financial_request_never_moves_money(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    transcript = svc.create_manual_transcript(
        OWNER, session["id"], "transfer the payment to the wallet")
    command = await svc.interpret(OWNER, transcript["id"])
    assert command["category"] == C.CAT_FINANCIAL
    assert command["requires_confirmation"] is True
    # No financial tool exists in the registry, so the request
    # cannot even be planned — it ends at clarification, and no
    # P-07 record of any kind was created by the voice path.
    assert command["status"] == C.CMD_NEEDS_CLARIFICATION
    assert command["plan_id"] is None


# -------------------------------------------------------------- privacy
async def test_retention_deletion_removes_files_and_clears_text(app_f03, tmp_path):
    svc = app_f03.voice
    session = make_session(app_f03)
    audio = svc.store_audio(
        OWNER, session["id"], filename="private.wav",
        content_type="audio/wav", data=WAV_BYTES)
    from pathlib import Path
    stored = Path(app_f03.settings.data_dir) / "voice-audio"
    assert any(stored.iterdir())
    transcript = svc.create_manual_transcript(
        OWNER, session["id"], "echo a private thought")
    await svc.interpret(OWNER, transcript["id"])

    svc.delete_audio(OWNER, audio["id"])
    with pytest.raises(Exception):
        svc.read_audio(OWNER, audio["id"])

    svc.delete_session(OWNER, session["id"])
    # Files are gone from disk.
    assert not any(stored.iterdir())
    # The session is gone from the owner's surfaces.
    rows, total = svc.list_sessions(OWNER)
    assert total == 0


def test_audio_intake_validation(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    with pytest.raises(ValidationError):
        svc.store_audio(OWNER, session["id"], filename="empty.wav",
                        content_type="audio/wav", data=b"")
    with pytest.raises(ValidationError):
        svc.store_audio(OWNER, session["id"], filename="notes.txt",
                        content_type="text/plain", data=b"hello")
    with pytest.raises(ValidationError):
        svc.store_audio(OWNER, session["id"], filename="big.wav",
                        content_type="audio/wav",
                        data=b"\x00" * (C.MAX_AUDIO_BYTES + 1))


async def test_closed_session_refuses_new_work(app_f03):
    svc = app_f03.voice
    session = make_session(app_f03)
    svc.close_session(OWNER, session["id"])
    with pytest.raises(Exception):
        svc.create_manual_transcript(OWNER, session["id"], "echo hi")


# ------------------------------------------------------------------ HTTP
def test_http_surface_end_to_end(client_f03):
    headers = owner_http_headers(client_f03)
    resp = client_f03.get("/api/v1/voice/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["stt"]["state"] == \
        C.STATE_REQUIRES_OWNER_CONFIGURATION

    resp = client_f03.post("/api/v1/voice/sessions", headers=headers,
                           json={"title": "HTTP session", "language": "en"})
    assert resp.status_code == 201, resp.text
    session_id = resp.json()["data"]["id"]

    resp = client_f03.post(
        f"/api/v1/voice/sessions/{session_id}/audio?filename=cmd.wav",
        headers={**headers, "Content-Type": "audio/wav"},
        content=WAV_BYTES)
    assert resp.status_code == 201, resp.text
    audio_id = resp.json()["data"]["id"]

    # Transcription over HTTP with no provider: an honest 422
    # carrying the framework state, not a fabricated transcript.
    resp = client_f03.post(f"/api/v1/voice/audio/{audio_id}/transcribe",
                           headers=headers)
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["details"]["state"] == \
        C.STATE_REQUIRES_OWNER_CONFIGURATION

    resp = client_f03.post(
        f"/api/v1/voice/sessions/{session_id}/transcripts/manual",
        headers=headers, json={"text": "echo over http"})
    assert resp.status_code == 201, resp.text
    transcript_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["source"] == C.SOURCE_MANUAL_ENTRY

    resp = client_f03.post(
        f"/api/v1/voice/transcripts/{transcript_id}/interpret",
        headers=headers)
    assert resp.status_code == 200, resp.text
    command = resp.json()["data"]
    assert command["status"] == C.CMD_COMPLETED

    resp = client_f03.get(
        f"/api/v1/voice/sessions/{session_id}/commands", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 1
