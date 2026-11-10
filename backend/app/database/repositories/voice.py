"""Repository layer for the Voice Assistant (Expansion Feature 3).
All SQL for the feature's four tables lives here; routes never
build queries directly.

Deletion is a service-level act (files removed, transcript text
cleared); repositories expose the row operations only. Tombstoned
rows (``deleted_at`` set) are excluded from the list/get paths the
service uses for owner surfaces.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.voice import VoiceAudio, VoiceCommand, VoiceSession, VoiceTranscript


class _Repo:
    model = None

    def __init__(self, session: Session):
        self.session = session

    def add(self, row):
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def save(self, row):
        self.session.commit()
        self.session.refresh(row)
        return row

    def get(self, row_id: str):
        return self.session.get(self.model, row_id)


class VoiceSessionRepository(_Repo):
    model = VoiceSession

    def list_for_owner(self, owner_id: str, *, limit: int = 100,
                       offset: int = 0) -> tuple[list, int]:
        stmt = (select(VoiceSession)
                .where(VoiceSession.owner_id == owner_id,
                       VoiceSession.deleted_at.is_(None))
                .order_by(VoiceSession.created_at.desc()))
        count = (select(func.count()).select_from(VoiceSession)
                 .where(VoiceSession.owner_id == owner_id,
                        VoiceSession.deleted_at.is_(None)))
        total = self.session.scalar(count) or 0
        return list(self.session.scalars(stmt.limit(limit).offset(offset))), total


class VoiceAudioRepository(_Repo):
    model = VoiceAudio

    def list_for_session(self, session_id: str, *, limit: int = 100,
                         offset: int = 0) -> tuple[list, int]:
        stmt = (select(VoiceAudio)
                .where(VoiceAudio.session_id == session_id,
                       VoiceAudio.deleted_at.is_(None))
                .order_by(VoiceAudio.created_at.desc()))
        count = (select(func.count()).select_from(VoiceAudio)
                 .where(VoiceAudio.session_id == session_id,
                        VoiceAudio.deleted_at.is_(None)))
        total = self.session.scalar(count) or 0
        return list(self.session.scalars(stmt.limit(limit).offset(offset))), total

    def list_all_for_session(self, session_id: str) -> list:
        """Including tombstones — the deletion cascade's view."""
        return list(self.session.scalars(
            select(VoiceAudio).where(VoiceAudio.session_id == session_id)))


class VoiceTranscriptRepository(_Repo):
    model = VoiceTranscript

    def list_for_session(self, session_id: str, *, limit: int = 100,
                         offset: int = 0) -> tuple[list, int]:
        stmt = (select(VoiceTranscript)
                .where(VoiceTranscript.session_id == session_id,
                       VoiceTranscript.deleted_at.is_(None))
                .order_by(VoiceTranscript.created_at))
        count = (select(func.count()).select_from(VoiceTranscript)
                 .where(VoiceTranscript.session_id == session_id,
                        VoiceTranscript.deleted_at.is_(None)))
        total = self.session.scalar(count) or 0
        return list(self.session.scalars(stmt.limit(limit).offset(offset))), total

    def list_all_for_session(self, session_id: str) -> list:
        return list(self.session.scalars(
            select(VoiceTranscript).where(
                VoiceTranscript.session_id == session_id)))


class VoiceCommandRepository(_Repo):
    model = VoiceCommand

    def list_for_session(self, session_id: str, *, status: str | None = None,
                         limit: int = 100, offset: int = 0) -> tuple[list, int]:
        stmt = select(VoiceCommand).where(
            VoiceCommand.session_id == session_id)
        count = select(func.count()).select_from(VoiceCommand).where(
            VoiceCommand.session_id == session_id)
        if status is not None:
            stmt = stmt.where(VoiceCommand.status == status)
            count = count.where(VoiceCommand.status == status)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(VoiceCommand.created_at.desc())
            .limit(limit).offset(offset)))
        return rows, total

    def pending_for_session(self, session_id: str) -> list:
        return list(self.session.scalars(
            select(VoiceCommand).where(
                VoiceCommand.session_id == session_id,
                VoiceCommand.status == "awaiting_confirmation")))
