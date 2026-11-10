"""Expansion Feature 3 unit tests: the deterministic classifier
(a screen, not an NLU), the speech-provider seam's honest probe
behaviour, the fixture double's labelling, the schema guards (no
money columns, no secret-value columns, Article 0 structural
guards), the metadata table count, and the single-source API
version.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.voice import constants as C
from app.voice.classifier import classify, is_stop_phrase
from app.voice.providers import LocalWhisperProvider, ProviderUnavailable

BACKEND = Path(__file__).resolve().parents[1]


class _Tools:
    """Minimal ToolRegistryView stand-in for classifier tests."""

    def __init__(self, approval_tools=()):
        self._approval = set(approval_tools)

    def requires_approval(self, tool_name: str) -> bool:
        return tool_name in self._approval


def _step(tool: str, permission: str = "execute_tools") -> dict:
    return {"tool_name": tool, "permission": permission}


# --------------------------------------------------------- stop phrase
def test_stop_phrases_match_exactly_and_normalised():
    assert is_stop_phrase("stop")
    assert is_stop_phrase("  Stop! ")
    assert is_stop_phrase("emergency stop")
    assert is_stop_phrase("cancel that")
    # Near-misses must NOT trigger a stop.
    assert not is_stop_phrase("stop the echo test")
    assert not is_stop_phrase("please stop by the office")
    assert not is_stop_phrase("echo stop")


# --------------------------------------------------------- classifier
def test_classifier_financial_screen_is_consequential():
    category, risk, confirm = classify(
        "please transfer the payment", [], _Tools())
    assert category == C.CAT_FINANCIAL
    assert risk == C.RISK_CONSEQUENTIAL
    assert confirm is True


def test_classifier_high_risk_screen_is_consequential():
    category, risk, confirm = classify(
        "delete the old reports", [], _Tools())
    assert category == C.CAT_HIGH_RISK
    assert risk == C.RISK_CONSEQUENTIAL
    assert confirm is True


def test_classifier_word_boundaries_avoid_false_positives():
    # "display" contains no screened word as a word; "echo" text
    # with an innocuous plan stays a low-risk system operation.
    category, risk, confirm = classify(
        "echo display the summary", [_step("core.echo_check")], _Tools())
    assert category == C.CAT_SYSTEM_OPERATION
    assert risk == C.RISK_LOW
    assert confirm is False


def test_classifier_information_from_read_only_plan():
    category, risk, confirm = classify(
        "check the system", [_step("core.health_snapshot")], _Tools())
    assert category == C.CAT_INFORMATION
    assert confirm is False


def test_classifier_question_and_unresolved_without_a_plan():
    category, _, _ = classify("what is the system status?", [], _Tools())
    assert category == C.CAT_QUESTION
    category, _, _ = classify("flibberty gibbet", [], _Tools())
    assert category == C.CAT_UNRESOLVED


def test_classifier_approval_tool_makes_any_plan_consequential():
    category, risk, confirm = classify(
        "run the thing", [_step("core.echo_check")],
        _Tools(approval_tools={"core.echo_check"}))
    assert confirm is True
    assert risk == C.RISK_CONSEQUENTIAL


def test_classifier_approval_required_permission_is_consequential():
    category, risk, confirm = classify(
        "run the thing",
        [_step("core.echo_check", permission="access_sensitive_data")],
        _Tools())
    assert confirm is True


# ------------------------------------------------------------ providers
async def test_local_whisper_probe_is_honest_in_staging():
    provider = LocalWhisperProvider("")
    available, detail = await provider.probe()
    # In staging the library and/or model are absent: the provider
    # must say so, never claim availability.
    assert available is False
    assert "DEF-A2" in detail or "no model is configured" in detail
    assert provider.supports_stt is True
    assert provider.supports_tts is False
    assert provider.is_fixture is False


async def test_local_whisper_refuses_to_transcribe_or_speak():
    provider = LocalWhisperProvider("")
    with pytest.raises(ProviderUnavailable):
        await provider.transcribe(b"bytes", "audio/wav", "en")
    with pytest.raises(ProviderUnavailable):
        await provider.synthesize("hello", voice=None, language="en",
                                  rate=1.0, volume=1.0)


async def test_fixture_double_is_labelled_and_deterministic():
    from app.voice.testing import FIXTURE_MODEL_LABEL, FixtureSpeechProvider
    provider = FixtureSpeechProvider(transcript_text="echo hello")
    assert provider.is_fixture is True
    available, _detail = await provider.probe()
    assert available is True
    result = await provider.transcribe(b"\x00\x01", "audio/wav", "en")
    assert result.text == "echo hello"
    assert result.is_fixture is True
    assert result.model_label == FIXTURE_MODEL_LABEL
    # A double must not invent a confidence figure.
    assert result.confidence is None
    spoken = await provider.synthesize("summary", voice=None,
                                       language="en", rate=1.0, volume=1.0)
    assert spoken.is_fixture is True
    assert spoken.audio[:4] == b"RIFF"  # a real (silent) WAV container
    unavailable = FixtureSpeechProvider(available=False)
    with pytest.raises(ProviderUnavailable):
        await unavailable.transcribe(b"x", "audio/wav", "en")


# --------------------------------------------------------- schema guards
def test_metadata_registers_exactly_four_new_tables():
    from app.database.models.base import Base
    import app.database.models  # noqa: F401

    # Expansion Feature 3: 227 pre-F03 metadata tables + 4 voice tables.
    # Expansion F06 disclosure: F06 added three knowledge tables;
    # the exact total is now 234.
    assert len(Base.metadata.tables) == 234
    assert {"voice_sessions", "voice_audio", "voice_transcripts",
            "voice_commands"} <= set(Base.metadata.tables)


def test_voice_tables_have_no_money_or_secret_value_columns():
    from app.database.models.voice import (
        VoiceAudio, VoiceCommand, VoiceSession, VoiceTranscript,
    )
    money_tokens = ("amount", "minor", "currency", "price", "balance",
                    "revenue", "profit", "collected", "journal", "ledger",
                    "charge", "fee")
    value_tokens = ("secret_value", "api_key", "password", "token_value",
                    "credential_value", "private_key")
    for model in (VoiceSession, VoiceAudio, VoiceTranscript, VoiceCommand):
        for column in model.__table__.columns:
            for token in money_tokens:
                assert token not in column.name, (model.__tablename__,
                                                  column.name)
            for token in value_tokens:
                assert token not in column.name, (model.__tablename__,
                                                  column.name)


def test_voice_never_decides_approvals_or_writes_finance():
    # Article 0 structural guard, mirroring F02's: the voice
    # package consumes the plan pipeline's approval path; it does
    # not decide approvals itself and contains no financial write
    # surface.
    sources = "\n".join(
        p.read_text() for p in (BACKEND / "app" / "voice").rglob("*.py"))
    assert ".decide(" not in sources
    assert "FinancialService" not in sources
    assert "JournalEntry" not in sources


def test_fixture_double_is_never_attached_by_default():
    # Structural guard: the application wiring and the service
    # constructor must not reference the test double at all.
    service_source = (BACKEND / "app" / "voice" / "service.py").read_text()
    application_source = (
        BACKEND / "app" / "core" / "application.py").read_text()
    assert "FixtureSpeechProvider" not in service_source
    assert "voice.testing" not in service_source
    assert "FixtureSpeechProvider" not in application_source


def test_api_version_single_source():
    from app.core.version import APP_VERSION
    # Expansion Feature 3 minor bump under the F02 versioning rule.
    # Expansion F06 disclosure: advanced to 1.4.0 by the same rule.
    assert APP_VERSION == "1.4.0"
