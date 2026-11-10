"""Repository layer for the Universal Integration Framework
(Expansion Feature 2). All SQL for the framework's two tables
lives here; routes never build queries directly.

Connectors transition lifecycle/health only through the framework
service, which audits every transition. Invocations are
append-only: no update or delete is exposed.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.integrations import IntegrationConnector, IntegrationInvocation


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


class ConnectorRepository(_Repo):
    model = IntegrationConnector

    def get_by_key(self, key: str):
        return self.session.scalars(
            select(IntegrationConnector).where(
                IntegrationConnector.key == key)).first()

    def list(self, *, lifecycle_status: str | None = None,
             health_state: str | None = None, source: str | None = None,
             limit: int = 100, offset: int = 0) -> tuple[list, int]:
        stmt = select(IntegrationConnector)
        count = select(func.count()).select_from(IntegrationConnector)
        for column, value in (
                (IntegrationConnector.lifecycle_status, lifecycle_status),
                (IntegrationConnector.health_state, health_state),
                (IntegrationConnector.source, source)):
            if value is not None:
                stmt = stmt.where(column == value)
                count = count.where(column == value)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(IntegrationConnector.key).limit(limit).offset(offset)))
        return rows, total


class InvocationRepository(_Repo):
    model = IntegrationInvocation

    def list(self, *, connector_key: str | None = None,
             outcome: str | None = None, limit: int = 50,
             offset: int = 0) -> tuple[list, int]:
        stmt = select(IntegrationInvocation)
        count = select(func.count()).select_from(IntegrationInvocation)
        if connector_key is not None:
            stmt = stmt.where(IntegrationInvocation.connector_key == connector_key)
            count = count.where(IntegrationInvocation.connector_key == connector_key)
        if outcome is not None:
            stmt = stmt.where(IntegrationInvocation.outcome == outcome)
            count = count.where(IntegrationInvocation.outcome == outcome)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(IntegrationInvocation.created_at.desc())
            .limit(limit).offset(offset)))
        return rows, total

    def find_idempotent(self, connector_key: str, capability: str,
                        idempotency_key: str):
        return self.session.scalars(
            select(IntegrationInvocation).where(
                IntegrationInvocation.connector_key == connector_key,
                IntegrationInvocation.capability == capability,
                IntegrationInvocation.idempotency_key == idempotency_key,
                IntegrationInvocation.outcome == "success")
            .order_by(IntegrationInvocation.created_at)).first()

    def count_since(self, connector_key: str, capability: str,
                    since: dt.datetime) -> int:
        return self.session.scalar(
            select(func.count()).select_from(IntegrationInvocation).where(
                IntegrationInvocation.connector_key == connector_key,
                IntegrationInvocation.capability == capability,
                IntegrationInvocation.created_at >= since,
                IntegrationInvocation.outcome.in_(("success", "error")))) or 0
