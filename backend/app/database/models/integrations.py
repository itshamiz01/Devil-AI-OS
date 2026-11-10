"""SQLAlchemy models for the Universal Integration Framework
(Expansion Feature 2).

Two additive tables; nothing else is altered:

- ``integration_connectors`` — the connector registry (pack §3):
  identity, provider, declared capabilities (the descriptor
  snapshot), lifecycle, reported state, health/sync/error history.
  ``adapter_key`` names the in-code adapter that implements the
  connector; NULL means **no implementation exists** and the
  connector can never be invoked — it is a registry record of a
  surface that awaits a real connector, reported honestly as
  ``requires_owner_configuration``.
- ``integration_invocations`` — the append-only invocation ledger:
  every attempt (success, error, denied, refused, rate-limited,
  duplicate) with its broker decision reference. Adapter *results*
  are stored on success so an idempotent replay can return them;
  a credential value can never be part of a result by contract.

**No secret values, ever.** The only credential-shaped column is
``credential_secret_name`` — the NAME of a P-10 secrets-registry
entry (a metadata reference like the P-10 registry itself holds).
Values live in the owner's environment/vault and are resolved by
P-10 at the moment of use. **No money columns**: the framework is
plumbing; it moves no money and keeps no financial figure.
"""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid
import datetime as dt


class IntegrationConnector(TimestampMixin, Base):
    """One registered connector (F02 registry)."""

    __tablename__ = "integration_connectors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(30), default="1.0.0", nullable=False)
    kind: Mapped[str] = mapped_column(String(30), default="custom", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="owner", nullable=False, index=True)
    descriptor: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    adapter_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    requires_credential: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    credential_secret_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(
        String(24), default="registered", index=True, nullable=False)
    health_state: Mapped[str] = mapped_column(
        String(40), default="not_configured", index=True, nullable=False)
    health_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_health_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_invoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    registered_by: Mapped[str | None] = mapped_column(String(232), nullable=True)


class IntegrationInvocation(TimestampMixin, Base):
    """One recorded invocation attempt (F02). Append-only."""

    __tablename__ = "integration_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    connector_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(100), nullable=False)
    principal_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    principal_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    broker_decision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
