"""Shared API contract (P-01 §15): envelope, errors, pagination."""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class Envelope(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    error: ErrorBody | None = None
    correlation_id: str | None = None
    meta: PageMeta | None = None


def ok(data, correlation_id: str | None = None, meta: PageMeta | None = None) -> dict:
    return {"success": True, "data": data, "error": None,
            "correlation_id": correlation_id, "meta": meta.model_dump() if meta else None}


def page(rows: list, total: int, limit: int, offset: int, correlation_id: str | None = None) -> dict:
    return ok(rows, correlation_id=correlation_id,
              meta=PageMeta(total=total, limit=limit, offset=offset))
