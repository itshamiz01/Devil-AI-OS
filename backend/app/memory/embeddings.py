"""Vector storage for P-09 (§8.2) — decided with evidence, labelled
honestly.

Stage-1 evidence (recorded in docs/audits/P09_PRE_IMPLEMENTATION_AUDIT.md):

- ``chromadb`` is NOT installed in the project environment
  (``ModuleNotFoundError``), and neither is ``numpy``. ChromaDB would
  be a new heavyweight dependency whose default telemetry was
  recorded at P-00 as ON. It is therefore NOT used, and nothing in
  this build claims it runs here.
- The deliverable is the replaceable :class:`VectorStore` interface
  plus :class:`SqliteVectorStore`, a working local adapter over the
  ``memory_embeddings`` table, fed by :class:`LocalHashEmbedder` — a
  deterministic, offline, dependency-free embedder (token + character
  trigram hashing, L2-normalised). It needs no paid API, no model
  download and no network, satisfying §8.2's local-first rules. It is
  a lexical-semantic approximation, NOT a neural embedding model;
  retrieval never treats its similarity as truth (§30 rule 4).

If the store is disabled or fails, :class:`UnavailableVectorStore`
(or the service's try/except) yields zero semantic candidates and
retrieval reports ``degraded.semantic = true`` — keyword and exact
retrieval continue (Scenario 11).
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


class LocalHashEmbedder:
    """Deterministic offline embedder: hashed bag of tokens and
    character trigrams into a fixed-dimension signed space."""

    name = "local-hash-v1"
    dim = 192

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = tokenize(text)
        features: list[str] = list(tokens)
        for token in tokens:
            padded = f"#{token}#"
            for i in range(len(padded) - 2):
                features.append(padded[i:i + 3])
        for feature in features:
            digest = hashlib.md5(feature.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [round(v / norm, 6) for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class VectorStore(Protocol):
    name: str

    def upsert(self, memory_id: str, text: str) -> None: ...
    def remove(self, memory_id: str) -> bool: ...
    def contains(self, memory_id: str) -> bool: ...
    def search(self, query_text: str, *, limit: int = 25) -> list[dict]: ...
    def health(self) -> dict: ...


class SqliteVectorStore:
    """Working local adapter over ``memory_embeddings``."""

    name = "sqlite-local"

    def __init__(self, session_factory, embedder: LocalHashEmbedder | None = None):
        self._session_factory = session_factory
        self.embedder = embedder or LocalHashEmbedder()

    def upsert(self, memory_id: str, text: str) -> None:
        from ..database.models.memory import MemoryEmbedding
        from ..database.repositories.memory import MemoryEmbeddingRepository
        vector = self.embedder.embed(text)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        session = self._session_factory()
        try:
            repo = MemoryEmbeddingRepository(session)
            row = repo.for_memory(memory_id)
            if row is None:
                repo.add(MemoryEmbedding(
                    memory_id=memory_id, model_name=self.embedder.name,
                    dim=self.embedder.dim, vector=vector, content_hash=digest))
            else:
                row.vector = vector
                row.content_hash = digest
                row.model_name = self.embedder.name
                repo.save(row)
        finally:
            session.close()

    def remove(self, memory_id: str) -> bool:
        from ..database.repositories.memory import MemoryEmbeddingRepository
        session = self._session_factory()
        try:
            repo = MemoryEmbeddingRepository(session)
            row = repo.for_memory(memory_id)
            if row is None:
                return False
            repo.delete_row(row)
            return True
        finally:
            session.close()

    def contains(self, memory_id: str) -> bool:
        from ..database.repositories.memory import MemoryEmbeddingRepository
        session = self._session_factory()
        try:
            return MemoryEmbeddingRepository(session).for_memory(memory_id) is not None
        finally:
            session.close()

    def search(self, query_text: str, *, limit: int = 25) -> list[dict]:
        from ..database.repositories.memory import MemoryEmbeddingRepository
        query_vec = self.embedder.embed(query_text)
        session = self._session_factory()
        try:
            rows = MemoryEmbeddingRepository(session).all_rows()
        finally:
            session.close()
        scored = [
            {"memory_id": row.memory_id,
             "similarity": max(0.0, cosine(query_vec, row.vector or []))}
            for row in rows
        ]
        scored.sort(key=lambda item: item["similarity"], reverse=True)
        return [s for s in scored if s["similarity"] > 0][:limit]

    def health(self) -> dict:
        from ..database.repositories.memory import MemoryEmbeddingRepository
        session = self._session_factory()
        try:
            count = len(MemoryEmbeddingRepository(session).all_rows())
        finally:
            session.close()
        return {"store": self.name, "status": "ok", "indexed": count,
                "embedder": self.embedder.name,
                "note": "local SQLite adapter; ChromaDB is not installed "
                        "in this environment and is not claimed"}


class UnavailableVectorStore:
    """Degraded-mode store (Scenario 11): every operation is a truthful
    no-op failure so retrieval can report degraded semantic search."""

    name = "unavailable"

    def upsert(self, memory_id: str, text: str) -> None:
        raise RuntimeError("vector store unavailable")

    def remove(self, memory_id: str) -> bool:
        raise RuntimeError("vector store unavailable")

    def contains(self, memory_id: str) -> bool:
        raise RuntimeError("vector store unavailable")

    def search(self, query_text: str, *, limit: int = 25) -> list[dict]:
        raise RuntimeError("vector store unavailable")

    def health(self) -> dict:
        return {"store": self.name, "status": "unavailable", "indexed": 0,
                "embedder": None, "note": "semantic retrieval degraded"}
