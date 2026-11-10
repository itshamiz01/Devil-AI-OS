"""SQLAlchemy models for Personal Knowledge & File Intelligence
(Expansion Feature 6).

Three additive tables; nothing else is altered:

- ``knowledge_collections`` — one owner project collection. The
  collection's ``slug`` is the P-09 ``project_ref`` its documents'
  chunks carry, so project scoping in retrieval is P-09's own
  filter, not a parallel one. ``excluded_patterns`` holds the
  owner's fnmatch exclusion list, applied at intake.
- ``knowledge_documents`` — one uploaded or folder-indexed file:
  full provenance (filename, format, size, SHA-256 of the bytes),
  the extraction record (extractor name, per-format detail such as
  page/sheet/slide counts, outcome status) and the chunk tallies.
  The bytes live on disk under the application data dir,
  content-addressed by SHA-256; the row holds metadata only.
- ``knowledge_chunks`` — one chunk of extracted text and its
  citation locator (page / sheet+rows / slide / line range), char
  span, text hash, the P-09 ``memory_id`` the chunk resolved to
  through P-09's own ingestion, and that ingestion's outcome.
  This table is a catalogue and citation map — the index itself
  (embeddings) exists only in P-09's vector store. Chunk ``text``
  is stored for detail/diff surfaces; it is NULL for chunks P-09's
  secret screen rejected, so credential-shaped material is never
  persisted here either.

**No money columns** (knowledge is the owner's data; this feature
has no financial surface) and **no secret values** of any kind.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class KnowledgeCollection(TimestampMixin, Base):
    """One owner project collection (F06)."""

    __tablename__ = "knowledge_collections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    excluded_patterns: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)


class KnowledgeDocument(TimestampMixin, Base):
    """One file in the owner's library (F06): provenance and the
    extraction record. Bytes live on disk, content-addressed."""

    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    collection_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(400), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), default="upload", nullable=False)
    source_path: Mapped[str | None] = mapped_column(String(600), nullable=True)
    format: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="received", index=True, nullable=False)
    extractor_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    extraction_detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    indexed_chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_of_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)


class KnowledgeChunk(TimestampMixin, Base):
    """One chunk of a document (F06): citation locator and the
    P-09 ingestion outcome. The embedding lives only in P-09."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    locator: Mapped[str] = mapped_column(String(200), nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    memory_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    index_status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    index_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
