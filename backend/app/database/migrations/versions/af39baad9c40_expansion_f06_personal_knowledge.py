"""expansion feature 6: personal knowledge & file intelligence

Revision ID: af39baad9c40
Revises: c41f7a9d03e6

Expansion Feature 6 (Personal Knowledge & File Intelligence)
adds three new tables and alters nothing else:

- ``knowledge_collections``: one owner project collection; its
  slug is the P-09 ``project_ref`` its documents' chunks carry.
  ``excluded_patterns`` holds the owner's fnmatch exclusion list
  applied at intake.
- ``knowledge_documents``: one uploaded or folder-indexed file —
  provenance (filename, format, size, SHA-256 of the bytes), the
  extraction record (extractor name, per-format detail, outcome
  status) and chunk tallies. The bytes live on disk under the
  data dir, content-addressed by SHA-256; the row is metadata.
- ``knowledge_chunks``: one chunk of extracted text — citation
  locator (page / sheet+rows / slide / line range), char span,
  text hash, the P-09 ``memory_id`` the chunk resolved to
  through P-09's own governed ingestion, and that ingestion's
  outcome. A catalogue and citation map only: embeddings exist
  solely in P-09's vector store. Chunk text is NULL for chunks
  P-09's secret screen rejected, so credential-shaped material
  is never persisted here either.

No money column is added anywhere (the knowledge library is the
owner's data; this feature has no financial surface) and no
secret value is stored.

Features 4 and 5 of the expansion pack are DEFERRED by owner
decision (they need his Windows machine); F06 proceeds ahead of
them in the built sequence.

Create Date: 2026-11-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'af39baad9c40'
down_revision: Union[str, None] = 'c41f7a9d03e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('knowledge_collections',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('excluded_patterns', sa.JSON(), nullable=False),
    sa.Column('created_by', sa.String(length=200), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_collections_slug'), 'knowledge_collections', ['slug'], unique=True)
    op.create_table('knowledge_documents',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('collection_id', sa.String(length=36), nullable=False),
    sa.Column('filename', sa.String(length=400), nullable=False),
    sa.Column('source_kind', sa.String(length=16), nullable=False),
    sa.Column('source_path', sa.String(length=600), nullable=True),
    sa.Column('format', sa.String(length=24), nullable=False),
    sa.Column('content_type', sa.String(length=160), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('storage_path', sa.String(length=500), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('extractor_name', sa.String(length=120), nullable=True),
    sa.Column('extraction_detail', sa.JSON(), nullable=False),
    sa.Column('chunk_count', sa.Integer(), nullable=False),
    sa.Column('indexed_chunk_count', sa.Integer(), nullable=False),
    sa.Column('duplicate_of_id', sa.String(length=36), nullable=True),
    sa.Column('error_detail', sa.Text(), nullable=True),
    sa.Column('created_by', sa.String(length=200), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_documents_collection_id'), 'knowledge_documents', ['collection_id'], unique=False)
    op.create_index(op.f('ix_knowledge_documents_format'), 'knowledge_documents', ['format'], unique=False)
    op.create_index(op.f('ix_knowledge_documents_sha256'), 'knowledge_documents', ['sha256'], unique=False)
    op.create_index(op.f('ix_knowledge_documents_status'), 'knowledge_documents', ['status'], unique=False)
    op.create_index(op.f('ix_knowledge_documents_duplicate_of_id'), 'knowledge_documents', ['duplicate_of_id'], unique=False)
    op.create_table('knowledge_chunks',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('document_id', sa.String(length=36), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('locator', sa.String(length=200), nullable=False),
    sa.Column('char_start', sa.Integer(), nullable=False),
    sa.Column('char_end', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('text_hash', sa.String(length=64), nullable=False),
    sa.Column('memory_id', sa.String(length=36), nullable=True),
    sa.Column('index_status', sa.String(length=32), nullable=False),
    sa.Column('index_detail', sa.Text(), nullable=True),
    sa.Column('created_by', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_chunks_document_id'), 'knowledge_chunks', ['document_id'], unique=False)
    op.create_index(op.f('ix_knowledge_chunks_text_hash'), 'knowledge_chunks', ['text_hash'], unique=False)
    op.create_index(op.f('ix_knowledge_chunks_memory_id'), 'knowledge_chunks', ['memory_id'], unique=False)
    op.create_index(op.f('ix_knowledge_chunks_index_status'), 'knowledge_chunks', ['index_status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_knowledge_chunks_index_status'), table_name='knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_chunks_memory_id'), table_name='knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_chunks_text_hash'), table_name='knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_chunks_document_id'), table_name='knowledge_chunks')
    op.drop_table('knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_documents_duplicate_of_id'), table_name='knowledge_documents')
    op.drop_index(op.f('ix_knowledge_documents_status'), table_name='knowledge_documents')
    op.drop_index(op.f('ix_knowledge_documents_sha256'), table_name='knowledge_documents')
    op.drop_index(op.f('ix_knowledge_documents_format'), table_name='knowledge_documents')
    op.drop_index(op.f('ix_knowledge_documents_collection_id'), table_name='knowledge_documents')
    op.drop_table('knowledge_documents')
    op.drop_index(op.f('ix_knowledge_collections_slug'), table_name='knowledge_collections')
    op.drop_table('knowledge_collections')
