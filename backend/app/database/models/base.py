from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def as_utc(value: dt.datetime | None) -> dt.datetime | None:
    """Normalise a database-read datetime to aware UTC (P-14 DEF-D2).

    The platform's DateTime columns are timezone-naive on SQLite, so
    values read back from the database are naive even though they
    were written as UTC. Comparing such a value against ``utcnow()``
    raises ``TypeError``. Every comparison site used to carry its own
    inline re-attachment shim; this helper is the single standard:
    None stays None, naive values are re-attached as UTC (the
    platform's storage convention), aware values pass through.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value


def new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(default=utcnow, onupdate=utcnow, nullable=False)
