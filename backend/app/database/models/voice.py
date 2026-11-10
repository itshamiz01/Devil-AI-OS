"""SQLAlchemy models for the Voice Assistant (Expansion Feature 3).

Four additive tables; nothing else is altered:

- ``voice_sessions`` — one owner voice conversation: its state,
  its language/provider/voice configuration (data for a future
  real provider — wake-word and continuous-mode settings are
  configuration, not implemented detection), and the last mission
  it produced. Voice and text share context through the shared
  P-02 mission store; the session's transcript chain is the
  conversation record.
- ``voice_audio`` — audio metadata for uploaded input and for
  synthesized responses. The bytes live on disk under the
  application data dir, content-addressed by SHA-256; the row
  holds metadata only. ``duration_seconds`` is recorded only when
  a provider reports it — never computed, never invented (no
  audio DSP exists in staging).
- ``voice_transcripts`` — one transcription (or manual-entry
  fallback) with FULL provenance: source, provider name, model
  label, and ``is_fixture`` — a transcript produced by the test
  double is labelled fixture at the record level forever.
  Deletion clears ``text`` and stamps ``deleted_at``: the row
  remains as a tombstone so the audit trail stays coherent, but
  the owner's words are gone.
- ``voice_commands`` — one interpreted command: the interpreted
  text, its deterministic classification (category, risk),
  the mission/plan it produced, the plan hash the owner is asked
  to confirm against, the P-10 broker decision taken at intake,
  the confirmation record, and the outcome (result summary,
  synthesized response, honest speech state).

**No money columns** (voice is an input channel; anything
financial executes only as a P-07-owned record through the
existing plan machinery — this feature holds no financial
figure) and **no secret values** of any kind.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class VoiceSession(TimestampMixin, Base):
    """One owner voice conversation (F03)."""

    __tablename__ = "voice_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    state: Mapped[str] = mapped_column(String(24), default="active", index=True, nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    stt_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tts_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    voice_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rate: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    volume: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    continuous_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    wake_word: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_mission_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VoiceAudio(TimestampMixin, Base):
    """Audio metadata (F03). Bytes live on disk; this row is the
    record. ``command_id`` is set for synthesized responses."""

    __tablename__ = "voice_audio"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    command_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="input", nullable=False)
    filename: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VoiceTranscript(TimestampMixin, Base):
    """One transcription or manual-entry fallback (F03), with
    record-level provenance. Deletion clears the text."""

    __tablename__ = "voice_transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    audio_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(24), default="audio", nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="completed", index=True, nullable=False)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VoiceCommand(TimestampMixin, Base):
    """One interpreted voice command (F03): classification,
    governance references, confirmation, outcome."""

    __tablename__ = "voice_commands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transcript_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    mission_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    interpreted_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="unresolved", index=True, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="interpreted", index=True, nullable=False)
    plan_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    broker_decision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confirmed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_audio_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    speech_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
