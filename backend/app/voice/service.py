"""VoiceService — the Voice Assistant pipeline (Expansion Feature 3).

Composed on the Application after F02, consuming only existing
authorities:

- **Identity & audit: P-01.** Principals come from the shared
  auth path; every voice act is written to the P-01
  ``audit_events`` trail via the shared repository — no parallel
  log. The voice channel is the owner's channel: every
  data-bearing method refuses a non-owner principal in the
  service layer (routes additionally gate on the Permission
  enum — the two-depth pattern of §4.2).
- **Authorization: P-10.** Every interpretation is authorized
  through the PermissionBroker (``submit_tasks`` / ``draft.create``,
  parameters bound to the transcript and the hash of its text)
  before any mission exists, and execution itself is governed by
  the plan pipeline's own machinery — per-step permission checks
  and the hash-bound ``ApprovalService`` binding inside
  ``approve_plan`` / ``execute_plan``, untouched.
- **Execution: P-02.** A transcript becomes a command only as a
  mission → plan → (approval) → execution through
  ``IntelligenceService``. Voice adds no execution path of its
  own, and a voice-originated action carries the authenticated
  principal's permissions and nothing more.
- **Memory: P-09.** Transcripts are never fed to memory. A
  completed command's verified outcome summary is fed
  best-effort through P-09's existing ingestion (the P-18
  posture), labelled ``voice-command:<id>``.
- **Money: none.** Voice tables hold no money column; a request
  that touches finance classifies ``financial_operation``,
  requires on-screen confirmation, and still executes only as a
  plan — in staging no financial tool exists, so such requests
  end at ``needs_clarification``, never at a money movement.

Honesty contract (DEF-A2): with no available speech provider,
transcription and synthesis refuse with the framework's honest
states and the provider's own probe detail. Nothing here
fabricates a transcript, an understanding, or a voice. The one
test double lives in ``app/voice/testing.py``, is labelled
fixture on every record it touches, and is attachable only
in-process through the owner-only audited hook below — never at
startup, never over HTTP.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from pathlib import Path

from ..core.exceptions import (
    ApprovalError, AutonomusError, InvalidStateTransitionError,
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..core.version import APP_VERSION
from ..database.models.base import utcnow
from ..database.models.core import AuditEvent
from ..database.models.voice import (
    VoiceAudio, VoiceCommand, VoiceSession, VoiceTranscript,
)
from ..database.repositories.core import AuditRepository
from ..database.repositories.voice import (
    VoiceAudioRepository, VoiceCommandRepository, VoiceSessionRepository,
    VoiceTranscriptRepository,
)
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from .classifier import classify, is_stop_phrase
from .providers import (
    LocalWhisperProvider, ProviderUnavailable, SpeechProvider,
    SpeechProviderError,
)

_log = logging.getLogger(__name__)


class VoiceError(AutonomusError):
    status_code = 422


def _actor(principal: Principal | None) -> str:
    return f"{principal.type.value}:{principal.id}" if principal else "system"


def session_to_dict(row: VoiceSession) -> dict:
    return {
        "id": row.id, "owner_id": row.owner_id, "title": row.title,
        "state": row.state, "language": row.language,
        "stt_provider": row.stt_provider, "tts_provider": row.tts_provider,
        "voice_name": row.voice_name, "rate": row.rate, "volume": row.volume,
        "continuous_mode": row.continuous_mode, "wake_word": row.wake_word,
        "last_mission_id": row.last_mission_id,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
    }


def audio_to_dict(row: VoiceAudio) -> dict:
    return {
        "id": row.id, "session_id": row.session_id,
        "command_id": row.command_id, "kind": row.kind,
        "filename": row.filename, "content_type": row.content_type,
        "size_bytes": row.size_bytes, "sha256": row.sha256,
        "duration_seconds": row.duration_seconds,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def transcript_to_dict(row: VoiceTranscript) -> dict:
    return {
        "id": row.id, "session_id": row.session_id, "audio_id": row.audio_id,
        "source": row.source, "provider_name": row.provider_name,
        "model_label": row.model_label, "is_fixture": row.is_fixture,
        "language": row.language, "text": row.text,
        "confidence": row.confidence, "status": row.status,
        "error_detail": row.error_detail, "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def command_to_dict(row: VoiceCommand) -> dict:
    return {
        "id": row.id, "session_id": row.session_id,
        "transcript_id": row.transcript_id, "mission_id": row.mission_id,
        "plan_id": row.plan_id, "interpreted_text": row.interpreted_text,
        "category": row.category, "risk_level": row.risk_level,
        "requires_confirmation": row.requires_confirmation,
        "status": row.status, "plan_hash": row.plan_hash,
        "broker_decision_id": row.broker_decision_id,
        "detail": row.detail or {},
        "confirmed_by": row.confirmed_by,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "result_summary": row.result_summary,
        "response_audio_id": row.response_audio_id,
        "speech_state": row.speech_state, "error_detail": row.error_detail,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class VoiceService:
    def __init__(self, application):
        self._app = application
        self._session_factory = application.session_factory
        self._settings = application.settings
        # The provider seam: exactly one real provider candidate is
        # attached by default — the local whisper adapter, whose
        # probe honestly reports it unavailable until the owner
        # installs the library and a model. No fixture is ever
        # attached here (see app/voice/testing.py).
        whisper = LocalWhisperProvider(
            getattr(self._settings, "whisper_model", None))
        self.providers: dict[str, SpeechProvider] = {whisper.name: whisper}

    # ------------------------------------------------------------ hooks
    def attach_provider(self, principal: Principal,
                        provider: SpeechProvider) -> dict:
        """Developer/test hook (the F02 attach_adapter precedent):
        attach a speech provider in-process. Owner-only and
        audited. There is deliberately NO HTTP route for this —
        a test double can never be attached over the API."""
        self._require_owner(principal)
        self.providers[provider.name] = provider
        self._audit(principal, "voice.provider_attached", "voice_provider",
                    provider.name, "allow",
                    "speech provider attached in-process",
                    {"provider": provider.name,
                     "is_fixture": provider.is_fixture,
                     "supports_stt": provider.supports_stt,
                     "supports_tts": provider.supports_tts})
        return {"name": provider.name, "is_fixture": provider.is_fixture,
                "supports_stt": provider.supports_stt,
                "supports_tts": provider.supports_tts}

    # ------------------------------------------------------------ guards
    def _require_owner(self, principal: Principal | None) -> None:
        if principal is None or principal.type != PrincipalType.OWNER:
            raise PermissionDeniedError(
                "the voice channel is owner-only: voice sessions, "
                "audio, transcripts and commands are the owner's "
                "data and act with the owner's authority, so no "
                "other principal may use them",
                details={"principal": _actor(principal)})

    def _get_session_row(self, principal: Principal,
                         session_id: str) -> VoiceSession:
        session = self._session_factory()
        try:
            row = VoiceSessionRepository(session).get(session_id)
            if (row is None or row.deleted_at is not None
                    or row.owner_id != principal.id):
                raise NotFoundError(f"voice session {session_id} not found")
            session.expunge(row)
            return row
        finally:
            session.close()

    def _require_active(self, row: VoiceSession) -> None:
        if row.state != C.SESSION_ACTIVE:
            raise InvalidStateTransitionError(
                f"voice session is '{row.state}'; new voice work "
                "requires an active session",
                details={"session_id": row.id, "state": row.state})

    def _get_audio_row(self, principal: Principal, audio_id: str) -> VoiceAudio:
        session = self._session_factory()
        try:
            row = VoiceAudioRepository(session).get(audio_id)
            if row is None or row.deleted_at is not None:
                raise NotFoundError(f"voice audio {audio_id} not found")
            owner = VoiceSessionRepository(session).get(row.session_id)
            if owner is None or owner.owner_id != principal.id:
                raise NotFoundError(f"voice audio {audio_id} not found")
            session.expunge(row)
            return row
        finally:
            session.close()

    def _get_transcript_row(self, principal: Principal,
                            transcript_id: str) -> VoiceTranscript:
        session = self._session_factory()
        try:
            row = VoiceTranscriptRepository(session).get(transcript_id)
            if row is None or row.deleted_at is not None:
                raise NotFoundError(f"voice transcript {transcript_id} not found")
            owner = VoiceSessionRepository(session).get(row.session_id)
            if owner is None or owner.owner_id != principal.id:
                raise NotFoundError(f"voice transcript {transcript_id} not found")
            session.expunge(row)
            return row
        finally:
            session.close()

    def _get_command_row(self, principal: Principal,
                         command_id: str) -> VoiceCommand:
        session = self._session_factory()
        try:
            row = VoiceCommandRepository(session).get(command_id)
            if row is None:
                raise NotFoundError(f"voice command {command_id} not found")
            owner = VoiceSessionRepository(session).get(row.session_id)
            if owner is None or owner.owner_id != principal.id:
                raise NotFoundError(f"voice command {command_id} not found")
            session.expunge(row)
            return row
        finally:
            session.close()

    _REPOS = {}  # populated below the class (model -> repository)

    def _save(self, row):
        """Persist a detached row the F02 way: re-fetch the stored
        row in a fresh session, copy every column across, commit,
        expunge, return."""
        repo_cls = self._REPOS[type(row)]
        session = self._session_factory()
        try:
            repo = repo_cls(session)
            stored = repo.get(row.id)
            if stored is None:
                raise NotFoundError(
                    f"{type(row).__tablename__} row {row.id} not found")
            for column in type(row).__table__.columns:
                if column.key not in ("id", "created_at"):
                    setattr(stored, column.key, getattr(row, column.key))
            saved = repo.save(stored)
            session.expunge(saved)
            return saved
        finally:
            session.close()

    # ------------------------------------------------------------- audit
    def _audit(self, principal, action: str, target_type: str, target_id,
               decision: str, reason: str | None = None,
               details: dict | None = None) -> None:
        session = self._session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value if principal else "system",
                actor_id=principal.id if principal else "voice-assistant",
                action=action, target_type=target_type, target_id=target_id,
                decision=decision, reason=reason, details=details or {},
                created_at=utcnow()))
        finally:
            session.close()

    # ------------------------------------------------------------ status
    async def providers_status(self) -> list[dict]:
        rows = []
        for provider in self.providers.values():
            available, detail = await provider.probe()
            rows.append({
                "name": provider.name, "is_fixture": provider.is_fixture,
                "supports_stt": provider.supports_stt,
                "supports_tts": provider.supports_tts,
                "available": available, "detail": detail})
        return rows

    async def _capability_state(self, capability: str,
                                  session: VoiceSession | None = None):
        """(state, detail, provider|None) for 'stt' or 'tts' in the
        F02 vocabulary. A provider is only returned when it probes
        available — callers must never invoke an unavailable one
        and call the result speech."""
        named = None
        if session is not None:
            named = (session.stt_provider if capability == "stt"
                     else session.tts_provider)
        if named:
            provider = self.providers.get(named)
            if provider is None:
                return (C.STATE_NOT_CONFIGURED,
                        f"provider '{named}' named by the session is "
                        "not attached", None)
            supports = (provider.supports_stt if capability == "stt"
                        else provider.supports_tts)
            if not supports:
                return (C.STATE_NOT_CONFIGURED,
                        f"provider '{named}' does not provide "
                        f"{capability}", None)
            available, detail = await provider.probe()
            if not available:
                return C.STATE_REQUIRES_OWNER_CONFIGURATION, detail, None
            return C.STATE_CONFIGURED, detail, provider
        candidates = [p for p in self.providers.values()
                      if (p.supports_stt if capability == "stt"
                          else p.supports_tts)]
        if not candidates:
            return (C.STATE_REQUIRES_OWNER_CONFIGURATION,
                    f"no {capability} provider is implemented or "
                    "configured; only an owner configuration act "
                    "can advance this", None)
        first_detail = None
        for provider in candidates:
            available, detail = await provider.probe()
            if first_detail is None:
                first_detail = detail
            if available:
                return C.STATE_CONFIGURED, detail, provider
        return (C.STATE_REQUIRES_OWNER_CONFIGURATION,
                first_detail or "no provider available", None)

    async def status(self) -> dict:
        providers = await self.providers_status()
        stt_state, stt_detail, _ = await self._capability_state("stt")
        tts_state, tts_detail, _ = await self._capability_state("tts")
        session = self._session_factory()
        try:
            from sqlalchemy import func, select
            counts = {}
            for label, model in (("sessions", VoiceSession),
                                 ("audio", VoiceAudio),
                                 ("transcripts", VoiceTranscript),
                                 ("commands", VoiceCommand)):
                counts[label] = session.scalar(
                    select(func.count()).select_from(model)) or 0
            awaiting = session.scalar(
                select(func.count()).select_from(VoiceCommand).where(
                    VoiceCommand.status == C.CMD_AWAITING_CONFIRMATION)) or 0
        finally:
            session.close()
        return {
            "api_version": APP_VERSION,
            "providers": providers,
            "stt": {"state": stt_state, "detail": stt_detail},
            "tts": {"state": tts_state, "detail": tts_detail},
            "state_vocabulary": list(C.STATES),
            "counts": counts,
            "awaiting_confirmation": awaiting,
            "not_implemented": list(C.NOT_IMPLEMENTED),
            "def_a2": ("no real speech or language model has been "
                       "exercised in this system; real-model "
                       "acceptance is deferred to the owner's "
                       "machine"),
        }

    # ----------------------------------------------------------- sessions
    def create_session(self, principal: Principal, data: dict) -> dict:
        self._require_owner(principal)
        rate = float(data.get("rate", 1.0))
        volume = float(data.get("volume", 1.0))
        if not 0.25 <= rate <= 4.0:
            raise ValidationError("rate must be between 0.25 and 4.0")
        if not 0.0 <= volume <= 1.0:
            raise ValidationError("volume must be between 0.0 and 1.0")
        session = self._session_factory()
        try:
            row = VoiceSessionRepository(session).add(VoiceSession(
                owner_id=principal.id,
                title=(data.get("title") or "").strip(),
                language=(data.get("language") or "en").strip() or "en",
                stt_provider=data.get("stt_provider"),
                tts_provider=data.get("tts_provider"),
                voice_name=data.get("voice_name"),
                rate=rate, volume=volume,
                continuous_mode=bool(data.get("continuous_mode", False)),
                wake_word=data.get("wake_word"),
                created_by=_actor(principal)))
        finally:
            session.close()
        self._audit(principal, "voice.session_created", "voice_session",
                    row.id, "allow", "voice session created",
                    {"language": row.language})
        return session_to_dict(row)

    def list_sessions(self, principal: Principal, *, limit: int = 100,
                      offset: int = 0):
        self._require_owner(principal)
        session = self._session_factory()
        try:
            rows, total = VoiceSessionRepository(session).list_for_owner(
                principal.id, limit=limit, offset=offset)
            return [session_to_dict(r) for r in rows], total
        finally:
            session.close()

    def get_session(self, principal: Principal, session_id: str) -> dict:
        self._require_owner(principal)
        return session_to_dict(self._get_session_row(principal, session_id))

    def update_session(self, principal: Principal, session_id: str,
                       patch: dict) -> dict:
        self._require_owner(principal)
        row = self._get_session_row(principal, session_id)
        allowed = {"title", "language", "stt_provider", "tts_provider",
                   "voice_name", "rate", "volume", "continuous_mode",
                   "wake_word"}
        for key, value in patch.items():
            if key not in allowed or value is None and key in (
                    "title", "language", "rate", "volume",
                    "continuous_mode"):
                continue
            if key == "rate" and not 0.25 <= float(value) <= 4.0:
                raise ValidationError("rate must be between 0.25 and 4.0")
            if key == "volume" and not 0.0 <= float(value) <= 1.0:
                raise ValidationError("volume must be between 0.0 and 1.0")
            setattr(row, key, value)
        row = self._save(row)
        self._audit(principal, "voice.session_updated", "voice_session",
                    row.id, "allow", "voice session settings updated",
                    {"fields": sorted(k for k in patch if k in allowed)})
        return session_to_dict(row)

    def close_session(self, principal: Principal, session_id: str) -> dict:
        self._require_owner(principal)
        row = self._get_session_row(principal, session_id)
        if row.state != C.SESSION_CLOSED:
            row.state = C.SESSION_CLOSED
            row.closed_at = utcnow()
            row = self._save(row)
            self._audit(principal, "voice.session_closed", "voice_session",
                        row.id, "allow", "voice session closed", {})
        return session_to_dict(row)

    def delete_session(self, principal: Principal, session_id: str) -> dict:
        """Retention deletion (privacy): stored audio files are
        removed, transcript and interpreted texts are cleared, and
        the rows remain only as tombstones so the audit trail
        stays coherent. The owner's words do not survive it."""
        self._require_owner(principal)
        row = self._get_session_row(principal, session_id)
        session = self._session_factory()
        try:
            audio_repo = VoiceAudioRepository(session)
            for audio in audio_repo.list_all_for_session(session_id):
                self._remove_file(audio.storage_path)
                if audio.deleted_at is None:
                    audio.deleted_at = utcnow()
                    audio_repo.save(audio)
            transcript_repo = VoiceTranscriptRepository(session)
            for transcript in transcript_repo.list_all_for_session(session_id):
                if transcript.deleted_at is None:
                    transcript.text = ""
                    transcript.deleted_at = utcnow()
                    transcript_repo.save(transcript)
            command_repo = VoiceCommandRepository(session)
            commands, _ = command_repo.list_for_session(
                session_id, limit=10000)
            for command in commands:
                if command.interpreted_text or command.result_summary:
                    command.interpreted_text = ""
                    command.result_summary = None
                    command_repo.save(command)
            row.deleted_at = utcnow()
            row.state = C.SESSION_CLOSED
        finally:
            session.close()
        row = self._save(row)
        self._audit(principal, "voice.session_deleted", "voice_session",
                    session_id, "allow",
                    "voice session deleted by owner (files removed, "
                    "texts cleared)", {})
        return {"id": session_id, "deleted": True}

    # -------------------------------------------------------------- audio
    def _storage_root(self) -> Path:
        root = Path(self._settings.data_dir) / "voice-audio"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _remove_file(self, storage_path: str) -> None:
        try:
            path = Path(self._settings.data_dir) / storage_path
            if path.is_file():
                path.unlink()
        except Exception as exc:  # deletion is best-effort on disk
            _log.warning("voice audio file removal failed: %s", exc)

    def _write_audio_file(self, data: bytes, extension: str) -> tuple[str, str]:
        digest = hashlib.sha256(data).hexdigest()
        name = f"{digest[:16]}-{uuid.uuid4().hex[:12]}{extension}"
        root = self._storage_root()
        (root / name).write_bytes(data)
        return digest, str(Path("voice-audio") / name)

    @staticmethod
    def _extension_for(filename: str, content_type: str) -> str | None:
        ext = Path(filename or "").suffix.lower()
        if ext in C.AUDIO_EXTENSIONS:
            return ext
        return {  # content-type fallback for browser recordings
            "audio/wav": ".wav", "audio/x-wav": ".wav",
            "audio/mpeg": ".mp3", "audio/ogg": ".ogg",
            "audio/webm": ".webm", "audio/mp4": ".m4a",
            "audio/flac": ".flac", "audio/aac": ".aac",
        }.get((content_type or "").split(";")[0].strip().lower())

    def store_audio(self, principal: Principal, session_id: str, *,
                    filename: str, content_type: str, data: bytes) -> dict:
        self._require_owner(principal)
        session_row = self._get_session_row(principal, session_id)
        self._require_active(session_row)
        if not data:
            raise ValidationError("audio upload is empty")
        if len(data) > C.MAX_AUDIO_BYTES:
            raise ValidationError(
                f"audio upload exceeds the {C.MAX_AUDIO_BYTES} byte "
                "intake cap", details={"size_bytes": len(data)})
        extension = self._extension_for(filename, content_type)
        if extension is None and not (content_type or "").startswith("audio/"):
            raise ValidationError(
                "unsupported audio type: the intake accepts audio "
                "content only (wav/mp3/ogg/opus/webm/m4a/flac/aac)",
                details={"content_type": content_type, "filename": filename})
        digest, storage_path = self._write_audio_file(
            data, extension or ".bin")
        session = self._session_factory()
        try:
            row = VoiceAudioRepository(session).add(VoiceAudio(
                session_id=session_id, kind=C.AUDIO_INPUT,
                filename=filename or "", content_type=content_type or "",
                size_bytes=len(data), sha256=digest,
                storage_path=storage_path, created_by=_actor(principal)))
        finally:
            session.close()
        self._audit(principal, "voice.audio_stored", "voice_audio", row.id,
                    "allow", "audio uploaded to a voice session",
                    {"session_id": session_id, "size_bytes": len(data),
                     "sha256_prefix": digest[:12],
                     "content_type": content_type})
        return audio_to_dict(row)

    def list_audio(self, principal: Principal, session_id: str, *,
                   limit: int = 100, offset: int = 0):
        self._require_owner(principal)
        self._get_session_row(principal, session_id)
        session = self._session_factory()
        try:
            rows, total = VoiceAudioRepository(session).list_for_session(
                session_id, limit=limit, offset=offset)
            return [audio_to_dict(r) for r in rows], total
        finally:
            session.close()

    def read_audio(self, principal: Principal, audio_id: str):
        """(row dict, bytes, content_type) for the content route."""
        self._require_owner(principal)
        row = self._get_audio_row(principal, audio_id)
        path = Path(self._settings.data_dir) / row.storage_path
        if not path.is_file():
            raise NotFoundError(
                "the audio record exists but its file is missing "
                "from storage", details={"audio_id": audio_id})
        return audio_to_dict(row), path.read_bytes(), row.content_type

    def delete_audio(self, principal: Principal, audio_id: str) -> dict:
        self._require_owner(principal)
        row = self._get_audio_row(principal, audio_id)
        self._remove_file(row.storage_path)
        row.deleted_at = utcnow()
        self._save(row)
        self._audit(principal, "voice.audio_deleted", "voice_audio",
                    audio_id, "allow",
                    "audio deleted by owner (file removed)", {})
        return {"id": audio_id, "deleted": True}

    # -------------------------------------------------------- transcripts
    async def transcribe(self, principal: Principal, audio_id: str,
                         correlation_id: str | None = None) -> dict:
        """Transcribe one uploaded audio record through the speech
        provider seam. Every attempt is recorded — including the
        honest not-configured refusal, which is a transcript row
        with status ``not_configured`` and the provider's own
        reason, never an invented text."""
        self._require_owner(principal)
        audio = self._get_audio_row(principal, audio_id)
        if audio.kind != C.AUDIO_INPUT:
            raise ValidationError("only input audio can be transcribed")
        session_row = self._get_session_row(principal, audio.session_id)
        self._require_active(session_row)
        state, detail, provider = await self._capability_state(
            "stt", session_row)

        def record(status: str, *, text: str = "",
                   provider_name: str | None = None,
                   model_label: str | None = None, is_fixture: bool = False,
                   confidence=None, language=None,
                   error: str | None = None) -> VoiceTranscript:
            session = self._session_factory()
            try:
                return VoiceTranscriptRepository(session).add(VoiceTranscript(
                    session_id=audio.session_id, audio_id=audio.id,
                    source=C.SOURCE_AUDIO, provider_name=provider_name,
                    model_label=model_label, is_fixture=is_fixture,
                    language=language, text=text, confidence=confidence,
                    status=status, error_detail=error,
                    created_by=_actor(principal)))
            finally:
                session.close()

        if provider is None:
            row = record(C.TRANSCRIPT_NOT_CONFIGURED, error=detail)
            self._audit(principal, "voice.transcription_unavailable",
                        "voice_transcript", row.id, "deny",
                        "no speech-to-text provider is available; "
                        "transcription refused honestly",
                        {"state": state, "detail": detail,
                         "audio_id": audio.id})
            raise VoiceError(
                f"speech-to-text is {state}: {detail}",
                details={"state": state, "transcript_id": row.id})

        path = Path(self._settings.data_dir) / audio.storage_path
        if not path.is_file():
            raise NotFoundError(
                "the audio record exists but its file is missing "
                "from storage", details={"audio_id": audio.id})
        try:
            result = await provider.transcribe(
                path.read_bytes(), audio.content_type,
                session_row.language)
        except ProviderUnavailable as exc:
            row = record(C.TRANSCRIPT_NOT_CONFIGURED,
                         provider_name=provider.name, error=str(exc))
            self._audit(principal, "voice.transcription_unavailable",
                        "voice_transcript", row.id, "deny",
                        "speech provider reported itself unavailable",
                        {"provider": provider.name, "detail": str(exc)})
            raise VoiceError(
                f"speech-to-text is "
                f"{C.STATE_REQUIRES_OWNER_CONFIGURATION}: {exc}",
                details={"state": C.STATE_REQUIRES_OWNER_CONFIGURATION,
                         "transcript_id": row.id}) from exc
        except SpeechProviderError as exc:
            row = record(C.TRANSCRIPT_FAILED,
                         provider_name=provider.name,
                         is_fixture=provider.is_fixture, error=str(exc))
            self._audit(principal, "voice.transcription_failed",
                        "voice_transcript", row.id, "deny",
                        "speech provider failed to transcribe",
                        {"provider": provider.name, "detail": str(exc)})
            raise VoiceError(
                f"transcription failed: {exc}",
                details={"state": C.STATE_ERROR,
                         "transcript_id": row.id}) from exc

        if audio.duration_seconds is None and result.duration_seconds:
            audio.duration_seconds = result.duration_seconds
            self._save(audio)
        row = record(C.TRANSCRIPT_COMPLETED, text=result.text,
                     provider_name=result.provider_name,
                     model_label=result.model_label,
                     is_fixture=result.is_fixture,
                     confidence=result.confidence,
                     language=result.language or session_row.language)
        self._audit(principal, "voice.transcribed", "voice_transcript",
                    row.id, "allow",
                    "audio transcribed through the speech provider seam",
                    {"provider": result.provider_name,
                     "model_label": result.model_label,
                     "is_fixture": result.is_fixture,
                     "audio_id": audio.id})
        return transcript_to_dict(row)

    def create_manual_transcript(self, principal: Principal,
                                 session_id: str, text: str) -> dict:
        """The manual fallback (pack Phase 5): owner-typed text when
        audio services fail. Real owner input — and labelled as
        exactly that, never as speech recognition."""
        self._require_owner(principal)
        session_row = self._get_session_row(principal, session_id)
        self._require_active(session_row)
        text = (text or "").strip()
        if not text:
            raise ValidationError("manual transcript text must not be empty")
        session = self._session_factory()
        try:
            row = VoiceTranscriptRepository(session).add(VoiceTranscript(
                session_id=session_id, source=C.SOURCE_MANUAL_ENTRY,
                provider_name=None, model_label=C.MANUAL_ENTRY_MODEL_LABEL,
                is_fixture=False, language=session_row.language, text=text,
                status=C.TRANSCRIPT_COMPLETED, created_by=_actor(principal)))
        finally:
            session.close()
        self._audit(principal, "voice.transcript_manual_entry",
                    "voice_transcript", row.id, "allow",
                    "manual-entry transcript recorded (fallback input, "
                    "not speech recognition)", {"session_id": session_id})
        return transcript_to_dict(row)

    def list_transcripts(self, principal: Principal, session_id: str, *,
                         limit: int = 100, offset: int = 0):
        self._require_owner(principal)
        self._get_session_row(principal, session_id)
        session = self._session_factory()
        try:
            rows, total = VoiceTranscriptRepository(session).list_for_session(
                session_id, limit=limit, offset=offset)
            return [transcript_to_dict(r) for r in rows], total
        finally:
            session.close()

    def delete_transcript(self, principal: Principal,
                          transcript_id: str) -> dict:
        self._require_owner(principal)
        row = self._get_transcript_row(principal, transcript_id)
        row.text = ""
        row.deleted_at = utcnow()
        self._save(row)
        self._audit(principal, "voice.transcript_deleted", "voice_transcript",
                    transcript_id, "allow",
                    "transcript deleted by owner (text cleared)", {})
        return {"id": transcript_id, "deleted": True}

    # ---------------------------------------------------------- commands
    @staticmethod
    def _plan_hash(plan) -> str:
        canonical = [
            {"tool_name": step.tool_name, "payload": step.payload}
            for step in sorted(plan.steps, key=lambda s: s.order_index)]
        return hashlib.sha256(json.dumps(
            canonical, sort_keys=True, default=str).encode()).hexdigest()

    def _new_command(self, principal, session_id: str, transcript_id: str,
                     text: str, **fields) -> VoiceCommand:
        session = self._session_factory()
        try:
            return VoiceCommandRepository(session).add(VoiceCommand(
                session_id=session_id, transcript_id=transcript_id,
                interpreted_text=text, created_by=_actor(principal),
                **fields))
        finally:
            session.close()

    async def interpret(self, principal: Principal, transcript_id: str,
                        correlation_id: str | None = None) -> dict:
        """Turn one completed transcript into a governed command:
        stop handling → broker intake → mission → plan →
        classification → execute (low risk) or stop at
        awaiting_confirmation (consequential) or
        needs_clarification (unplannable)."""
        self._require_owner(principal)
        transcript = self._get_transcript_row(principal, transcript_id)
        session_row = self._get_session_row(principal, transcript.session_id)
        self._require_active(session_row)
        if transcript.status != C.TRANSCRIPT_COMPLETED or not transcript.text:
            raise ValidationError(
                "only a completed transcript with text can be "
                "interpreted", details={"transcript_id": transcript_id,
                                        "status": transcript.status})
        text = transcript.text
        intelligence = self._app.intelligence

        # --- the voice-native stop: cancels this session's own
        # pending commands, grants and executes nothing.
        if is_stop_phrase(text):
            session = self._session_factory()
            try:
                repo = VoiceCommandRepository(session)
                cancelled = []
                for pending in repo.pending_for_session(session_row.id):
                    pending.status = C.CMD_CANCELLED
                    pending.error_detail = (
                        "cancelled by a voice stop command in the "
                        "same session")
                    repo.save(pending)
                    cancelled.append(pending.id)
            finally:
                session.close()
            row = self._new_command(
                principal, session_row.id, transcript.id, text,
                category=C.CAT_SYSTEM_OPERATION, risk_level=C.RISK_LOW,
                status=C.CMD_CANCELLED,
                detail={"stop_applied": True,
                        "cancelled_command_ids": cancelled})
            self._audit(principal, "voice.stop_applied", "voice_command",
                        row.id, "allow",
                        "voice stop phrase cancelled the session's "
                        "pending commands",
                        {"cancelled_command_ids": cancelled})
            return command_to_dict(row)

        # --- classification screen (pre-plan), command record, then
        # the P-10 broker intake decision BEFORE any mission exists.
        category, risk, requires_confirmation = classify(text, [], None)
        row = self._new_command(
            principal, session_row.id, transcript.id, text,
            category=category, risk_level=risk,
            requires_confirmation=requires_confirmation,
            status=C.CMD_INTERPRETED)
        decision = self._app.security.broker.authorize(
            principal, permission="submit_tasks", action="draft.create",
            resource=f"voice-session:{session_row.id}",
            parameters={"transcript_id": transcript.id,
                        "text_sha256": hashlib.sha256(
                            text.encode()).hexdigest(),
                        "category": category},
            correlation_id=correlation_id)
        row.broker_decision_id = decision.get("decision_id")
        if not decision["allowed"]:
            row.status = C.CMD_DENIED
            row.error_detail = decision["reason"]
            row = self._save(row)
            self._audit(principal, "voice.command_denied", "voice_command",
                        row.id, "deny",
                        "the P-10 broker denied this voice-originated "
                        "request at intake",
                        {"reason": decision["reason"],
                         "broker_decision_id": row.broker_decision_id})
            raise PermissionDeniedError(
                f"voice command denied by the P-10 broker: "
                f"{decision['reason']}",
                details={"command_id": row.id,
                         "broker_decision_id": row.broker_decision_id})

        # --- the existing text machinery: mission, then plan.
        mission = await intelligence.create_mission(
            principal, text, correlation_id=correlation_id)
        row.mission_id = mission.id
        session_row.last_mission_id = mission.id
        self._save(session_row)
        from ..intelligence.planner import PlanRejectedError
        try:
            plan = await intelligence.create_plan(
                principal, mission.id, correlation_id=correlation_id)
        except PlanRejectedError as exc:
            row.status = C.CMD_FAILED
            row.error_detail = f"the planner's proposal was rejected: {exc}"
            row = self._save(row)
            self._audit(principal, "voice.command_failed", "voice_command",
                        row.id, "deny",
                        "plan proposal rejected by the P-02 validator",
                        {"mission_id": mission.id})
            return command_to_dict(row)
        except ValidationError:
            row.status = C.CMD_NEEDS_CLARIFICATION
            row.detail = {"planner": "none",
                          "reason": ("no baseline template matched and "
                                     "no usable LLM plan was available; "
                                     "the command was not executed")}
            row = self._save(row)
            self._audit(principal, "voice.command_needs_clarification",
                        "voice_command", row.id, "allow",
                        "no planner could produce a plan; nothing "
                        "was executed", {"mission_id": mission.id})
            return command_to_dict(row)

        steps = [{"name": s.name, "tool_name": s.tool_name,
                  "payload": s.payload,
                  "permission": intelligence.tools.permission(s.tool_name)}
                 for s in sorted(plan.steps, key=lambda s: s.order_index)]
        category, risk, requires_confirmation = classify(
            text, steps, intelligence.tools)
        row.category = category
        row.risk_level = risk
        row.requires_confirmation = requires_confirmation
        row.plan_id = plan.id
        row.plan_hash = self._plan_hash(plan)
        row.detail = {"steps": steps, "planner": plan.planner,
                      "template": mission.matched_template}
        if requires_confirmation:
            row.status = C.CMD_AWAITING_CONFIRMATION
            row = self._save(row)
            self._audit(principal, "voice.command_confirmation_required",
                        "voice_command", row.id, "allow",
                        "consequential voice command held for "
                        "on-screen owner confirmation",
                        {"category": category, "plan_id": plan.id,
                         "plan_hash": row.plan_hash})
            return command_to_dict(row)

        row = self._save(row)
        return await self._execute(principal, row, correlation_id)

    async def _execute(self, principal: Principal, row: VoiceCommand,
                       correlation_id: str | None) -> dict:
        """Execution is the plan pipeline's own: approve_plan
        (hash-bound ApprovalService record) then execute_plan
        (mode gates + per-step permission re-validation)."""
        intelligence = self._app.intelligence
        row.status = C.CMD_EXECUTING
        row = self._save(row)
        try:
            await intelligence.approve_plan(
                principal, row.plan_id, correlation_id=correlation_id)
            plan = await intelligence.execute_plan(
                principal, row.plan_id, correlation_id=correlation_id)
        except AutonomusError as exc:
            row.status = C.CMD_FAILED
            row.error_detail = f"{type(exc).__name__}: {exc}"
            row = self._save(row)
            self._audit(principal, "voice.command_failed", "voice_command",
                        row.id, "deny",
                        "the plan pipeline refused or failed this "
                        "command", {"plan_id": row.plan_id,
                                    "detail": row.error_detail})
            return command_to_dict(row)
        step_lines = [
            f"{s.name} ({s.tool_name}): {s.status}, "
            f"verification {s.verification_status}"
            for s in sorted(plan.steps, key=lambda s: s.order_index)]
        if plan.status == "completed":
            row.status = C.CMD_COMPLETED
            row.result_summary = (
                f"Executed {len(step_lines)} step(s) from the "
                f"interpreted command. " + "; ".join(step_lines))
            row = self._save(row)
            self._audit(principal, "voice.command_executed", "voice_command",
                        row.id, "allow",
                        "voice command executed through the plan "
                        "pipeline", {"plan_id": plan.id,
                                     "mission_id": row.mission_id})
            self._feed_memory(principal, row)
            await self._try_synthesize(principal, row)
        else:
            row.status = C.CMD_FAILED
            row.error_detail = (
                f"plan halted in status '{plan.status}': "
                + "; ".join(step_lines))
            row = self._save(row)
            self._audit(principal, "voice.command_failed", "voice_command",
                        row.id, "deny",
                        "plan execution halted before completion",
                        {"plan_id": plan.id, "plan_status": plan.status})
        return command_to_dict(self._get_command_row(principal, row.id))

    async def confirm(self, principal: Principal, command_id: str,
                      correlation_id: str | None = None) -> dict:
        """The on-screen confirmation (route-gated on
        approve_actions, owner-checked here). The plan must be
        byte-identical to what was shown — any drift refuses and
        requires re-interpretation. This is the ONLY confirmation
        path: no transcript, however phrased, can confirm."""
        self._require_owner(principal)
        row = self._get_command_row(principal, command_id)
        if row.status != C.CMD_AWAITING_CONFIRMATION:
            raise InvalidStateTransitionError(
                f"only a command awaiting confirmation can be "
                f"confirmed (current status: {row.status})",
                details={"command_id": command_id, "status": row.status})
        plan = self._app.intelligence.get_plan(row.plan_id)
        if self._plan_hash(plan) != row.plan_hash:
            self._audit(principal, "voice.command_confirmation_refused",
                        "voice_command", row.id, "deny",
                        "the interpreted plan changed after it was "
                        "shown for confirmation; confirmation refused",
                        {"plan_id": row.plan_id})
            raise ApprovalError(
                "the interpreted command changed after it was shown "
                "for confirmation; re-interpret before executing",
                details={"command_id": command_id, "plan_id": row.plan_id})
        row.confirmed_by = _actor(principal)
        row.confirmed_at = utcnow()
        row = self._save(row)
        self._audit(principal, "voice.command_confirmed", "voice_command",
                    row.id, "allow",
                    "owner confirmed the interpreted command on "
                    "screen", {"plan_id": row.plan_id,
                               "plan_hash": row.plan_hash})
        return await self._execute(principal, row, correlation_id)

    def reject(self, principal: Principal, command_id: str) -> dict:
        self._require_owner(principal)
        row = self._get_command_row(principal, command_id)
        if row.status != C.CMD_AWAITING_CONFIRMATION:
            raise InvalidStateTransitionError(
                f"only a command awaiting confirmation can be "
                f"rejected (current status: {row.status})",
                details={"command_id": command_id, "status": row.status})
        row.status = C.CMD_REJECTED
        row = self._save(row)
        self._audit(principal, "voice.command_rejected", "voice_command",
                    row.id, "allow",
                    "owner rejected the interpreted command; it was "
                    "not executed", {"plan_id": row.plan_id})
        return command_to_dict(row)

    def list_commands(self, principal: Principal, session_id: str, *,
                      status: str | None = None, limit: int = 100,
                      offset: int = 0):
        self._require_owner(principal)
        self._get_session_row(principal, session_id)
        session = self._session_factory()
        try:
            rows, total = VoiceCommandRepository(session).list_for_session(
                session_id, status=status, limit=limit, offset=offset)
            return [command_to_dict(r) for r in rows], total
        finally:
            session.close()

    def get_command(self, principal: Principal, command_id: str) -> dict:
        self._require_owner(principal)
        return command_to_dict(self._get_command_row(principal, command_id))

    # ----------------------------------------------------- spoken response
    async def _synthesize_for(self, principal: Principal,
                              row: VoiceCommand) -> dict:
        """Attempt synthesis of the result summary. Returns the
        command dict; the outcome is recorded on the command either
        way (response_audio_id + configured, or the honest speech
        state). Never fabricates audio."""
        session_row = self._get_session_row(principal, row.session_id)
        state, detail, provider = await self._capability_state(
            "tts", session_row)
        if provider is None:
            row.speech_state = state
            row = self._save(row)
            return {"command": command_to_dict(row), "state": state,
                    "detail": detail}
        result = await provider.synthesize(
            row.result_summary or "", voice=session_row.voice_name,
            language=session_row.language, rate=session_row.rate,
            volume=session_row.volume)
        extension = self._extension_for("response", result.content_type) \
            or ".bin"
        digest, storage_path = self._write_audio_file(result.audio, extension)
        session = self._session_factory()
        try:
            audio = VoiceAudioRepository(session).add(VoiceAudio(
                session_id=row.session_id, command_id=row.id,
                kind=C.AUDIO_RESPONSE,
                filename=f"response-{row.id}{extension}",
                content_type=result.content_type,
                size_bytes=len(result.audio), sha256=digest,
                storage_path=storage_path, created_by=_actor(principal)))
        finally:
            session.close()
        row.response_audio_id = audio.id
        row.speech_state = C.STATE_CONFIGURED
        detail = dict(row.detail or {})
        detail["speech"] = {"provider": result.provider_name,
                            "model_label": result.model_label,
                            "is_fixture": result.is_fixture}
        row.detail = detail
        row = self._save(row)
        self._audit(principal, "voice.response_synthesized", "voice_audio",
                    audio.id, "allow",
                    "spoken response synthesized through the speech "
                    "provider seam",
                    {"provider": result.provider_name,
                     "model_label": result.model_label,
                     "is_fixture": result.is_fixture,
                     "command_id": row.id})
        return {"command": command_to_dict(row),
                "state": C.STATE_CONFIGURED, "detail": "synthesized"}

    async def _try_synthesize(self, principal: Principal,
                              row: VoiceCommand) -> None:
        """Best-effort spoken response at completion: a synthesis
        failure or absence never changes the command's outcome —
        the text summary stands, with the speech state recorded."""
        try:
            await self._synthesize_for(principal, row)
        except (ProviderUnavailable, SpeechProviderError) as exc:
            row.speech_state = C.STATE_REQUIRES_OWNER_CONFIGURATION
            row = self._save(row)
            _log.info("voice synthesis unavailable for command %s: %s",
                      row.id, exc)
        except Exception as exc:  # synthesis must not break execution
            _log.warning("voice synthesis failed for command %s: %s",
                         row.id, exc)

    async def synthesize(self, principal: Principal,
                         command_id: str) -> dict:
        """Explicit (re-)synthesis of a completed command's spoken
        response. Unlike the best-effort completion path, an
        unavailable provider is an honest error here."""
        self._require_owner(principal)
        row = self._get_command_row(principal, command_id)
        if row.status != C.CMD_COMPLETED or not row.result_summary:
            raise InvalidStateTransitionError(
                "only a completed command with a result summary "
                "can be spoken", details={"command_id": command_id,
                                           "status": row.status})
        outcome = await self._synthesize_for(principal, row)
        if outcome["state"] != C.STATE_CONFIGURED:
            raise VoiceError(
                f"speech synthesis is {outcome['state']}: "
                f"{outcome['detail']}",
                details={"state": outcome["state"], "command_id": command_id})
        return outcome["command"]

    # ------------------------------------------------------------- memory
    def _feed_memory(self, principal: Principal, row: VoiceCommand) -> None:
        """Best-effort P-09 feed of the verified outcome only
        (the P-18 posture). Transcripts themselves are never fed:
        the owner's raw words stay in the voice records."""
        memory = getattr(self._app, "memory", None)
        if memory is None:
            return
        try:
            memory.ingestion.ingest(principal, {
                "title": f"Voice command outcome ({row.category})",
                "content": (f"Interpreted request: {row.interpreted_text}\n"
                            f"Outcome: {row.result_summary}"),
                "source_type": "agent_output",
                "source_ref": f"voice-command:{row.id}",
                "business_id": None,
                "verification_status": "verified"})
        except Exception as exc:  # feeding must not break the pipeline
            _log.warning("voice outcome feed to P-09 failed: %s", exc)


VoiceService._REPOS = {
    VoiceSession: VoiceSessionRepository,
    VoiceAudio: VoiceAudioRepository,
    VoiceTranscript: VoiceTranscriptRepository,
    VoiceCommand: VoiceCommandRepository,
}
