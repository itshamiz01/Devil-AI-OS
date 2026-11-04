"""Dialect-portable ALTER TABLE for the Alembic chain.

SQLite cannot add a NOT NULL column with a server default, nor drop or alter
many constraints, in place; those ALTERs must run through Alembic's batch
(table-rebuild) mode. Postgres supports them natively.

Running this chain's 144 index operations through batch mode on Postgres would
rebuild the affected table once *per index*, which is both slow and lossy, so
on any non-SQLite dialect the same calls go straight to DDL instead. One
migration body therefore serves both backends.
"""
from __future__ import annotations

from contextlib import contextmanager

from alembic import op


class _PortableTable:
    """Mirrors the small slice of the batch API the chain actually uses."""

    def __init__(self, table: str, schema: str | None = None) -> None:
        self._table = table
        self._schema = schema
        self._batch = None

    def add_column(self, column, **kw):
        if self._batch is not None:
            self._batch.add_column(column, **kw)
        else:
            op.add_column(self._table, column, schema=self._schema, **kw)

    def drop_column(self, name, **kw):
        if self._batch is not None:
            self._batch.drop_column(name, **kw)
        else:
            op.drop_column(name, table_name=self._table, schema=self._schema, **kw)

    def create_index(self, name, columns=None, **kw):
        if self._batch is not None:
            self._batch.create_index(name, columns, **kw)
        else:
            op.create_index(name, self._table, columns, schema=self._schema, **kw)

    def f(self, name, **kw):
        # Alembic's batch API exposes ``f`` for explicitly quoted identifiers.
        # Outside batch mode a plain string is already quoted correctly by the
        # dialect, so the name passes through unchanged.
        if self._batch is not None:
            return self._batch.f(name, **kw)
        return name

    def drop_index(self, name, **kw):
        if self._batch is not None:
            self._batch.drop_index(name, **kw)
        else:
            op.drop_index(name, table_name=self._table, schema=self._schema, **kw)


@contextmanager
def portable_alter_table(table: str, schema: str | None = None):
    dialect = op.get_context().dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table(table, schema=schema) as batch_op:
            proxy = _PortableTable(table, schema)
            proxy._batch = batch_op
            yield proxy
    else:
        yield _PortableTable(table, schema)
