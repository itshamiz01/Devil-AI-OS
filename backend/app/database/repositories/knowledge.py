"""Repository layer for Personal Knowledge & File Intelligence
(Expansion Feature 6). All SQL for the feature's three tables
lives here; routes never build queries directly.

Tombstoned rows (``deleted_at`` set) are excluded from the
list/get paths the service uses for owner surfaces; the deletion
cascade uses the ``*_all`` views.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.knowledge import (
    KnowledgeChunk, KnowledgeCollection, KnowledgeDocument,
)


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

    def delete_row(self, row) -> None:
        self.session.delete(row)
        self.session.commit()


class KnowledgeCollectionRepository(_Repo):
    model = KnowledgeCollection

    def by_slug(self, slug: str):
        return self.session.scalars(
            select(KnowledgeCollection).where(
                KnowledgeCollection.slug == slug,
                KnowledgeCollection.deleted_at.is_(None))).first()

    def list_live(self, *, limit: int = 100, offset: int = 0) -> tuple[list, int]:
        stmt = (select(KnowledgeCollection)
                .where(KnowledgeCollection.deleted_at.is_(None))
                .order_by(KnowledgeCollection.created_at))
        count = (select(func.count()).select_from(KnowledgeCollection)
                 .where(KnowledgeCollection.deleted_at.is_(None)))
        total = self.session.scalar(count) or 0
        return list(self.session.scalars(stmt.limit(limit).offset(offset))), total


class KnowledgeDocumentRepository(_Repo):
    model = KnowledgeDocument

    def list_for_collection(self, collection_id: str, *, limit: int = 100,
                            offset: int = 0) -> tuple[list, int]:
        stmt = (select(KnowledgeDocument)
                .where(KnowledgeDocument.collection_id == collection_id,
                       KnowledgeDocument.deleted_at.is_(None))
                .order_by(KnowledgeDocument.created_at.desc()))
        count = (select(func.count()).select_from(KnowledgeDocument)
                 .where(KnowledgeDocument.collection_id == collection_id,
                        KnowledgeDocument.deleted_at.is_(None)))
        total = self.session.scalar(count) or 0
        return list(self.session.scalars(stmt.limit(limit).offset(offset))), total

    def by_sha256(self, sha256: str):
        """Live documents whose bytes are identical to ``sha256``
        (exact duplicate detection over document bytes)."""
        return list(self.session.scalars(
            select(KnowledgeDocument).where(
                KnowledgeDocument.sha256 == sha256,
                KnowledgeDocument.deleted_at.is_(None))
            .order_by(KnowledgeDocument.created_at)))

    def list_live(self, *, limit: int = 1000) -> list:
        return list(self.session.scalars(
            select(KnowledgeDocument).where(
                KnowledgeDocument.deleted_at.is_(None)).limit(limit)))


class KnowledgeChunkRepository(_Repo):
    model = KnowledgeChunk

    def list_for_document(self, document_id: str) -> list:
        return list(self.session.scalars(
            select(KnowledgeChunk).where(
                KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.chunk_index)))

    def by_memory_ids(self, memory_ids: list[str]) -> list:
        if not memory_ids:
            return []
        return list(self.session.scalars(
            select(KnowledgeChunk).where(
                KnowledgeChunk.memory_id.in_(memory_ids))))

    def by_memory_id(self, memory_id: str) -> list:
        return list(self.session.scalars(
            select(KnowledgeChunk).where(
                KnowledgeChunk.memory_id == memory_id)))

    def delete_for_document(self, document_id: str) -> int:
        rows = self.list_for_document(document_id)
        for row in rows:
            self.session.delete(row)
        self.session.commit()
        return len(rows)
