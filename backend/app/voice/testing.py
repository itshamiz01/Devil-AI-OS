"""Deterministic speech test double (Expansion Feature 3).

TEST FIXTURE ONLY. ``FixtureSpeechProvider`` is NOT a speech
model: it does not listen, recognise or speak. Transcription
returns a preset text supplied by the test; synthesis returns a
generated *silent* WAV. Every result it produces is stamped
``is_fixture=True`` and labelled ``FIXTURE:test-double (not a real
speech model)``, and the pipeline copies that provenance onto the
stored record — fixture output can never be presented as real
transcription or real speech.

It is never attached at startup, never seeded, and has no HTTP
route. Tests attach it in-process through the owner-only audited
service hook ``VoiceService.attach_provider`` (the F02 mock
harness precedent). Production code paths never import it.
"""
from __future__ import annotations

import io
import wave

from .providers import (
    ProviderUnavailable, SpeechProvider, SynthesisResult, TranscriptionResult,
)

FIXTURE_MODEL_LABEL = "FIXTURE:test-double (not a real speech model)"


def _silent_wav(seconds: float = 0.25, sample_rate: int = 8000) -> bytes:
    """A tiny valid WAV of pure silence — synthesized *data* for
    exercising the response pipeline, labelled fixture everywhere
    it lands. It is not a voice and claims not to be."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * int(seconds * sample_rate))
    return buffer.getvalue()


class FixtureSpeechProvider(SpeechProvider):
    """Deterministic double with a preset transcript.``available``
    can be flipped to exercise the honest-unavailable path."""

    name = "fixture_speech_double"
    is_fixture = True
    supports_stt = True
    supports_tts = True

    def __init__(self, transcript_text: str = "echo fixture",
                 available: bool = True):
        self.transcript_text = transcript_text
        self._available = available
        self.transcribe_calls: list[dict] = []
        self.synthesize_calls: list[dict] = []

    async def probe(self) -> tuple[bool, str]:
        if self._available:
            return True, ("fixture speech double attached for testing "
                          "(not a real speech model)")
        return False, "fixture speech double marked unavailable by the test"

    async def transcribe(self, audio: bytes, content_type: str,
                         language: str | None) -> TranscriptionResult:
        self.transcribe_calls.append(
            {"bytes": len(audio), "content_type": content_type,
             "language": language})
        if not self._available:
            raise ProviderUnavailable(
                "fixture speech double marked unavailable by the test")
        return TranscriptionResult(
            text=self.transcript_text, provider_name=self.name,
            model_label=FIXTURE_MODEL_LABEL, is_fixture=True,
            # A double must not invent a confidence figure.
            confidence=None, language=language, duration_seconds=None)

    async def synthesize(self, text: str, *, voice: str | None,
                         language: str | None, rate: float,
                         volume: float) -> SynthesisResult:
        self.synthesize_calls.append(
            {"text": text, "voice": voice, "language": language,
             "rate": rate, "volume": volume})
        if not self._available:
            raise ProviderUnavailable(
                "fixture speech double marked unavailable by the test")
        return SynthesisResult(
            audio=_silent_wav(), content_type="audio/wav",
            provider_name=self.name, model_label=FIXTURE_MODEL_LABEL,
            is_fixture=True)
