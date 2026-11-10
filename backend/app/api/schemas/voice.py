"""Voice Assistant API schemas (Expansion Feature 3).

Inputs only — outputs are the service layer's plain dicts. No
schema carries audio bytes except the multipart upload itself,
and none returns a secret of any kind (the voice feature holds
none).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class VoiceSessionCreateIn(BaseModel):
    """Session configuration is DATA for a future real provider:
    language, provider selection, voice, rate, volume, continuous
    mode, wake word. Storing a wake word does not implement
    wake-word detection (see the status surface's not-implemented
    list)."""

    title: str = ""
    language: str = "en"
    stt_provider: str | None = None
    tts_provider: str | None = None
    voice_name: str | None = None
    rate: float = 1.0
    volume: float = 1.0
    continuous_mode: bool = False
    wake_word: str | None = None


class VoiceSessionUpdateIn(BaseModel):
    title: str | None = None
    language: str | None = None
    stt_provider: str | None = None
    tts_provider: str | None = None
    voice_name: str | None = None
    rate: float | None = None
    volume: float | None = None
    continuous_mode: bool | None = None
    wake_word: str | None = None


class ManualTranscriptIn(BaseModel):
    """The manual fallback: owner-typed text, recorded with
    manual-entry provenance — never presented as transcription."""

    text: str = Field(min_length=1)
