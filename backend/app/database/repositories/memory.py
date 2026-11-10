"""Repository layer for P-09 memory tables. All SQL for the memory
package lives here or in the memory services built on these
repositories; API routes never build queries directly.

Append-only by convention: versions, contradictions, ingestion jobs,
retrieval logs, learning records, handoffs, deletion receipts and
exports expose no delete. Record deletion itself happens only through
the governed service path, which removes the record AND its embedding
together and writes a verified receipt.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.memory import (
    AgentHandoff, LearningRecord, MemoryConsolidation, MemoryContradiction,
    MemoryDeletionReceipt, MemoryEmbedding, MemoryEntity, MemoryExport,
    MemoryIngestionJob, MemoryRecord, MemoryRelationship,
    MemoryRetrievalLog, MemoryReviewTask, MemoryVersion,
    OwnerMemoryPreference,
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

    def list(self, *, limit: int = 50, offset: int = 0,
             filters: dict | None = None) -> tuple[list, int]:
        stmt = select(self.model)
        count_stmt = select(func.count()).select_from(self.model)
        conditions = []
        for key, value in (filters or {}).items():
            if value is None:
                continue
            column = getattr(self.model, key, None)
            if column is not None:
                conditions.append(column == value)
        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        total = self.session.scalar(count_stmt) or 0
        rows = self.session.scalars(
            stmt.order_by(self.model.created_at.desc())
            .limit(limit).offset(offset)).all()
        return list(rows), total


class MemoryRecordRepository(_Repo):
    model = MemoryRecord

    def by_content_hash(self, content_hash: str) -> MemoryRecord | None:
        return self.session.scalars(
            select(MemoryRecord).where(
                MemoryRecord.content_hash == content_hash)).first()

    def same_subject_predicate(self, subject: str, predicate: str,
                               *, exclude_id: str | None = None) -> list:
        if not subject or not predicate:
            return []
        stmt = select(MemoryRecord).where(
            MemoryRecord.subject == subject,
            MemoryRecord.predicate == predicate,
            MemoryRecord.status.notin_(["DELETED"]))
        if exclude_id:
            stmt = stmt.where(MemoryRecord.id != exclude_id)
        return list(self.session.scalars(stmt).all())

    def all_active(self, *, limit: int = 2000) -> list:
        return list(self.session.scalars(
            select(MemoryRecord).where(
                MemoryRecord.status.notin_(["DELETED", "ARCHIVED"]))
            .limit(limit)).all())

    def count_grouped(self, column) -> dict:
        rows = self.session.execute(
            select(column, func.count()).group_by(column)).all()
        return {str(k): int(v) for k, v in rows}


class MemoryVersionRepository(_Repo):
    model = MemoryVersion

    def for_memory(self, memory_id: str) -> list:
        return list(self.session.scalars(
            select(MemoryVersion).where(MemoryVersion.memory_id == memory_id)
            .order_by(MemoryVersion.version)).all())


class MemoryEntityRepository(_Repo):
    model = MemoryEntity

    def find(self, entity_type: str, entity_ref: str) -> MemoryEntity | None:
        return self.session.scalars(
            select(MemoryEntity).where(
                MemoryEntity.entity_type == entity_type,
                MemoryEntity.entity_ref == entity_ref)).first()


class MemoryRelationshipRepository(_Repo):
    model = MemoryRelationship

    def edges_from(self, entity_id: str) -> list:
        return list(self.session.scalars(
            select(MemoryRelationship).where(
                MemoryRelationship.from_entity_id == entity_id)).all())

    def edges_to(self, entity_id: str) -> list:
        return list(self.session.scalars(
            select(MemoryRelationship).where(
                MemoryRelationship.to_entity_id == entity_id)).all())


class MemoryEmbeddingRepository(_Repo):
    model = MemoryEmbedding

    def for_memory(self, memory_id: str) -> MemoryEmbedding | None:
        return self.session.scalars(
            select(MemoryEmbedding).where(
                MemoryEmbedding.memory_id == memory_id)).first()

    def all_rows(self) -> list:
        return list(self.session.scalars(select(MemoryEmbedding)).all())


class MemoryIngestionJobRepository(_Repo):
    model = MemoryIngestionJob


class MemoryContradictionRepository(_Repo):
    model = MemoryContradiction

    def open_between(self, a_id: str, b_id: str) -> MemoryContradiction | None:
        return self.session.scalars(
            select(MemoryContradiction).where(
                MemoryContradiction.status == "OPEN",
                ((MemoryContradiction.memory_a_id == a_id)
                 & (MemoryContradiction.memory_b_id == b_id))
                | ((MemoryContradiction.memory_a_id == b_id)
                   & (MemoryContradiction.memory_b_id == a_id)))).first()

    def for_memory(self, memory_id: str) -> list:
        return list(self.session.scalars(
            select(MemoryContradiction).where(
                (MemoryContradiction.memory_a_id == memory_id)
                | (MemoryContradiction.memory_b_id == memory_id))).all())


class MemoryRetrievalLogRepository(_Repo):
    model = MemoryRetrievalLog


class LearningRecordRepository(_Repo):
    model = LearningRecord

    def for_source(self, source_type: str, source_ref: str) -> list:
        return list(self.session.scalars(
            select(LearningRecord).where(
                LearningRecord.source_type == source_type,
                LearningRecord.source_ref == source_ref)).all())


class AgentHandoffRepository(_Repo):
    model = AgentHandoff

    def for_agent(self, agent_id: str, *, direction: str = "any") -> list:
        conditions = []
        if direction in ("any", "from"):
            conditions.append(AgentHandoff.from_agent_id == agent_id)
        rows = list(self.session.scalars(
            select(AgentHandoff).where(*conditions)
            .order_by(AgentHandoff.created_at.desc())).all())
        if direction == "any":
            rows += list(self.session.scalars(
                select(AgentHandoff).where(
                    AgentHandoff.to_agent_id == agent_id)
                .order_by(AgentHandoff.created_at.desc())).all())
        return rows


class MemoryConsolidationRepository(_Repo):
    model = MemoryConsolidation


class OwnerMemoryPreferenceRepository(_Repo):
    model = OwnerMemoryPreference

    def by_key(self, key: str) -> OwnerMemoryPreference | None:
        return self.session.scalars(
            select(OwnerMemoryPreference).where(
                OwnerMemoryPreference.key == key)).first()


class MemoryReviewTaskRepository(_Repo):
    model = MemoryReviewTask

    def open_for(self, memory_id: str, reason: str) -> MemoryReviewTask | None:
        return self.session.scalars(
            select(MemoryReviewTask).where(
                MemoryReviewTask.memory_id == memory_id,
                MemoryReviewTask.reason == reason,
                MemoryReviewTask.status == "OPEN")).first()


class MemoryDeletionReceiptRepository(_Repo):
    model = MemoryDeletionReceipt


class MemoryExportRepository(_Repo):
    model = MemoryExport
