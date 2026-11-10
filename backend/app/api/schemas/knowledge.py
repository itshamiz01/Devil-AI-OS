"""Personal Knowledge & File Intelligence API schemas
(Expansion Feature 6).

Inputs only — outputs are the service layer's plain dicts. No
schema carries file bytes except the raw-body upload itself,
and none returns a secret of any kind (the knowledge feature
holds none; document content the P-09 secret screen rejected is
never persisted, so it can never be returned either).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CollectionCreateIn(BaseModel):
    """A project collection. The slug is the P-09 ``project_ref``
    its documents' chunks will carry; when omitted it is derived
    from the name."""

    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=120)
    description: str = ""
    excluded_patterns: list[str] = Field(default_factory=list)


class CollectionUpdateIn(BaseModel):
    """The slug is immutable: it is the project identity P-09
    records already carry."""

    name: str | None = None
    description: str | None = None
    excluded_patterns: list[str] | None = None


class IndexFolderIn(BaseModel):
    """A folder name relative to the knowledge-import directory.
    Absolute paths and traversal are refused by the service."""

    folder: str = Field(min_length=1, max_length=400)
