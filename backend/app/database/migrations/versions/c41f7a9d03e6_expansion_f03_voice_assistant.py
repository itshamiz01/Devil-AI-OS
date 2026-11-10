"""expansion feature 3: voice assistant

Revision ID: c41f7a9d03e6
Revises: 3f7a1c9e52b4

Expansion Feature 3 (Voice Assistant) adds four new tables and
alters nothing else:

- ``voice_sessions``: one owner voice conversation — state, the
  language/provider/voice configuration (settings data for a
  future real provider; wake-word and continuous-mode fields are
  configuration, not implemented detection), the last mission it
  produced.
- ``voice_audio``: audio metadata for uploaded input and
  synthesized responses. Bytes live on disk under the data dir,
  content-addressed by SHA-256; the row is metadata only.
  ``duration_seconds`` is recorded only when a provider reports
  it — never computed, never invented.
- ``voice_transcripts``: one transcription or manual-entry
  fallback with full record-level provenance (source, provider,
  model label, ``is_fixture``). Deletion clears the text.
- ``voice_commands``: one interpreted command — classification,
  the mission/plan it produced, the plan hash a confirmation
  binds to, the P-10 broker decision id taken at intake, the
  confirmation record and the outcome.

No money column is added anywhere (voice is an input channel;
financial action executes only as P-07-owned records through the
existing plan machinery) and no secret value is stored.

Create Date: 2026-11-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c41f7a9d03e6'
down_revision: Union[str, None] = '3f7a1c9e52b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('voice_sessions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('owner_id', sa.String(length=100), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('state', sa.String(length=24), nullable=False),
    sa.Column('language', sa.String(length=16), nullable=False),
    sa.Column('stt_provider', sa.String(length=100), nullable=True),
    sa.Column('tts_provider', sa.String(length=100), nullable=True),
    sa.Column('voice_name', sa.String(length=100), nullable=True),
    sa.Column('rate', sa.Float(), nullable=False),
    sa.Column('volume', sa.Float(), nullable=False),
    sa.Column('continuous_mode', sa.Boolean(), nullable=False),
    sa.Column('wake_word', sa.String(length=100), nullable=True),
    sa.Column('last_mission_id', sa.String(length=64), nullable=True),
    sa.Column('created_by', sa.String(length=200), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_voice_sessions_owner_id'), 'voice_sessions', ['owner_id'], unique=False)
    op.create_index(op.f('ix_voice_sessions_state'), 'voice_sessions', ['state'], unique=False)
    op.create_table('voice_audio',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('session_id', sa.String(length=36), nullable=False),
    sa.Column('command_id', sa.String(length=36), nullable=True),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('filename', sa.String(length=300), nullable=False),
    sa.Column('content_type', sa.String(length=120), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('storage_path', sa.String(length=500), nullable=False),
    sa.Column('duration_seconds', sa.Float(), nullable=True),
    sa.Column('created_by', sa.String(length=200), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_voice_audio_session_id'), 'voice_audio', ['session_id'], unique=False)
    op.create_index(op.f('ix_voice_audio_command_id'), 'voice_audio', ['command_id'], unique=False)
    op.create_index(op.f('ix_voice_audio_sha256'), 'voice_audio', ['sha256'], unique=False)
    op.create_table('voice_transcripts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('session_id', sa.String(length=36), nullable=False),
    sa.Column('audio_id', sa.String(length=36), nullable=True),
    sa.Column('source', sa.String(length=24), nullable=False),
    sa.Column('provider_name', sa.String(length=100), nullable=True),
    sa.Column('model_label', sa.String(length=300), nullable=True),
    sa.Column('is_fixture', sa.Boolean(), nullable=False),
    sa.Column('language', sa.String(length=16), nullable=True),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('error_detail', sa.Text(), nullable=True),
    sa.Column('created_by', sa.String(length=200), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_voice_transcripts_session_id'), 'voice_transcripts', ['session_id'], unique=False)
    op.create_index(op.f('ix_voice_transcripts_audio_id'), 'voice_transcripts', ['audio_id'], unique=False)
    op.create_index(op.f('ix_voice_transcripts_status'), 'voice_transcripts', ['status'], unique=False)
    op.create_table('voice_commands',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('session_id', sa.String(length=36), nullable=False),
    sa.Column('transcript_id', sa.String(length=36), nullable=False),
    sa.Column('mission_id', sa.String(length=64), nullable=True),
    sa.Column('plan_id', sa.String(length=64), nullable=True),
    sa.Column('interpreted_text', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('risk_level', sa.String(length=20), nullable=False),
    sa.Column('requires_confirmation', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('plan_hash', sa.String(length=64), nullable=True),
    sa.Column('broker_decision_id', sa.String(length=64), nullable=True),
    sa.Column('detail', sa.JSON(), nullable=False),
    sa.Column('confirmed_by', sa.String(length=200), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('result_summary', sa.Text(), nullable=True),
    sa.Column('response_audio_id', sa.String(length=36), nullable=True),
    sa.Column('speech_state', sa.String(length=40), nullable=True),
    sa.Column('error_detail', sa.Text(), nullable=True),
    sa.Column('created_by', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_voice_commands_session_id'), 'voice_commands', ['session_id'], unique=False)
    op.create_index(op.f('ix_voice_commands_transcript_id'), 'voice_commands', ['transcript_id'], unique=False)
    op.create_index(op.f('ix_voice_commands_category'), 'voice_commands', ['category'], unique=False)
    op.create_index(op.f('ix_voice_commands_status'), 'voice_commands', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_voice_commands_status'), table_name='voice_commands')
    op.drop_index(op.f('ix_voice_commands_category'), table_name='voice_commands')
    op.drop_index(op.f('ix_voice_commands_transcript_id'), table_name='voice_commands')
    op.drop_index(op.f('ix_voice_commands_session_id'), table_name='voice_commands')
    op.drop_table('voice_commands')
    op.drop_index(op.f('ix_voice_transcripts_status'), table_name='voice_transcripts')
    op.drop_index(op.f('ix_voice_transcripts_audio_id'), table_name='voice_transcripts')
    op.drop_index(op.f('ix_voice_transcripts_session_id'), table_name='voice_transcripts')
    op.drop_table('voice_transcripts')
    op.drop_index(op.f('ix_voice_audio_sha256'), table_name='voice_audio')
    op.drop_index(op.f('ix_voice_audio_command_id'), table_name='voice_audio')
    op.drop_index(op.f('ix_voice_audio_session_id'), table_name='voice_audio')
    op.drop_table('voice_audio')
    op.drop_index(op.f('ix_voice_sessions_state'), table_name='voice_sessions')
    op.drop_index(op.f('ix_voice_sessions_owner_id'), table_name='voice_sessions')
    op.drop_table('voice_sessions')
