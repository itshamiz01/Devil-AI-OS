"""Speech provider interface + the one real local adapter
(Expansion Feature 3).

The seam mirrors P-02's ``ModelProvider`` exactly: providers
subclass ``IntegrationAdapter``, report availability through an
honest ``probe()``, and raise :class:`ProviderUnavailable` rather
than fabricating output. Results carry their provenance —
provider name, model label, and whether the provider is a test
fixture — so every transcript and synthesized response stored by
the pipeline is labelled at the record level.

- :class:`LocalWhisperProvider` — the local-first candidate for
  speech-to-text (faster-whisper), per the pack's local-first
  rule. Its probe reports the truth in staging: the library is
  not installed and no model is configured, so it is unavailable
  and every call refuses honestly. The transcription path itself
  is real code against the library API; it has NOT been exercised
  against a real model (DEF-A2 — real-model acceptance is
  deferred to the owner's machine, whose CPU-only hardware
  bounds model choice per the P-04 feasibility verdict). It
  provides transcription only; it claims no synthesis.
- No speech-synthesis provider is implemented. Nothing in this
  module pretends otherwise: with no TTS provider attached, the
  pipeline's speech state is ``requires_owner_configuration``.
"""
from __future__ import annotations

import abc
import asyncio
import os
from dataclasses import dataclass

from ..integrations.interfaces.base import IntegrationAdapter, IntegrationHealth


class SpeechProviderError(Exception):
    """The provider failed to produce usable output."""


class ProviderUnavailable(SpeechProviderError):
    """The provider is not available / not configured / not enabled."""


@dataclass
class TranscriptionResult:
    text: str
    provider_name: str
    model_label: str
    is_fixture: bool = False
    confidence: float | None = None      # only when a provider reports it
    language: str | None = None
    duration_seconds: float | None = None


@dataclass
class SynthesisResult:
    audio: bytes
    content_type: str
    provider_name: str
    model_label: str
    is_fixture: bool = False


class SpeechProvider(IntegrationAdapter):
    """The speech-provider contract. ``is_fixture`` marks a test
    double at the type level: the pipeline copies it onto every
    record the provider produces, so fixture output can never be
    mistaken for real speech processing."""

    name = "unnamed"
    is_fixture = False
    supports_stt = False
    supports_tts = False

    @abc.abstractmethod
    async def probe(self) -> tuple[bool, str]:
        """(available, human-readable detail). Must be honest."""

    @abc.abstractmethod
    async def transcribe(self, audio: bytes, content_type: str,
                         language: str | None) -> TranscriptionResult:
        raise NotImplementedError

    @abc.abstractmethod
    async def synthesize(self, text: str, *, voice: str | None,
                         language: str | None, rate: float,
                         volume: float) -> SynthesisResult:
        raise NotImplementedError

    async def health(self) -> IntegrationHealth:
        available, detail = await self.probe()
        return IntegrationHealth(name=self.name, available=available, detail=detail)

    async def close(self) -> None:
        return None


class LocalWhisperProvider(SpeechProvider):
    """Local speech-to-text via faster-whisper (owner-configured).

    The model is named by ``AUTONOMUS_WHISPER_MODEL`` (a model size
    or a local model directory). Nothing is downloaded by this
    code and no network is touched: a model the owner has not
    placed on the machine simply is not there, and the probe says
    so.
    """

    name = "local_whisper"
    supports_stt = True
    supports_tts = False

    def __init__(self, model: str | None = None):
        self.model = model if model is not None else os.environ.get(
            "AUTONOMUS_WHISPER_MODEL", "")
        self._detail = "not probed yet"

    def _probe_sync(self) -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401
        except Exception:
            self._detail = (
                "faster-whisper is not installed in this environment; "
                "local speech recognition requires the owner to install "
                "it and configure a model (AUTONOMUS_WHISPER_MODEL). "
                "No speech model has been exercised (DEF-A2).")
            return False, self._detail
        if not self.model:
            self._detail = (
                "faster-whisper is installed but no model is "
                "configured (AUTONOMUS_WHISPER_MODEL is empty); "
                "speech recognition is not available.")
            return False, self._detail
        self._detail = f"faster-whisper available with model '{self.model}'"
        return True, self._detail

    async def probe(self) -> tuple[bool, str]:
        return await asyncio.to_thread(self._probe_sync)

    async def transcribe(self, audio: bytes, content_type: str,
                         language: str | None) -> TranscriptionResult:
        available, detail = await self.probe()
        if not available:
            raise ProviderUnavailable(detail)

        def _run() -> TranscriptionResult:
            import io

            from faster_whisper import WhisperModel
            model = WhisperModel(self.model, device="cpu",
                                 compute_type="int8")
            segments, info = model.transcribe(
                io.BytesIO(audio), language=language or None)
            text = "".join(segment.text for segment in segments).strip()
            return TranscriptionResult(
                text=text, provider_name=self.name,
                model_label=f"faster-whisper:{self.model}",
                is_fixture=False, confidence=None,
                language=getattr(info, "language", None) or language,
                duration_seconds=getattr(info, "duration", None))

        try:
            return await asyncio.to_thread(_run)
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise SpeechProviderError(
                f"local whisper transcription failed: "
                f"{type(exc).__name__}: {exc}") from exc

    async def synthesize(self, text: str, *, voice: str | None,
                         language: str | None, rate: float,
                         volume: float) -> SynthesisResult:
        raise ProviderUnavailable(
            "the local whisper provider transcribes only; no "
            "speech-synthesis provider is implemented or configured")
