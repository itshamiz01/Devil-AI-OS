"""KnowledgeService — Personal Knowledge & File Intelligence
(Expansion Feature 6).

Composed on the Application after F03, consuming only existing
authorities:

- **Memory & retrieval: P-09.** Chunks are ingested through
  P-09's own governed ingestion (secret screen, usefulness
  filter, exact-duplicate detection, policy-gated store, vector
  index); search is P-09's hybrid retrieval with F06 citations
  attached; deletion goes through P-09's governed deletion,
  which removes the embedding and verifies its absence. F06
  keeps NO index of its own — its tables are a catalogue and a
  citation map (collections, document provenance, chunk
  locators).
- **Identity & audit: P-01.** Principals come from the shared
  auth path; every knowledge act is written to the P-01
  ``audit_events`` trail via the shared repository. The library
  is the owner's private data: every data-bearing method
  refuses a non-owner principal in the service layer (routes
  additionally gate on the Permission enum — the two-depth
  pattern of Gate 2 review §4.2).
- **Money: none.** Knowledge tables hold no money column and
  the feature has no financial surface; P-07 is untouched.

Honesty contract: extraction is real per format or an honest
status says why not (unsupported format, metadata-only image —
OCR is NOT IMPLEMENTED, encrypted/malformed bytes fail
extraction); "intelligence" outputs are deterministic and
labelled (frequency statistics, verbatim extractive excerpts,
``difflib`` diffs) — no generated prose exists here because no
LLM is configured (DEF-A2); retrieval quality is capped by
P-09's ``local-hash-v1`` lexical embedder and says so on every
search response. Documents are DATA, never instructions: no
path in this feature turns document content into a task, plan
or execution.
"""
from __future__ import annotations

import difflib
import fnmatch
import hashlib
import logging
import re
from pathlib import Path

from ..core.exceptions import (
    AutonomusError, NotFoundError, PermissionDeniedError, ValidationError,
)
from ..core.version import APP_VERSION
from ..database.models.base import utcnow
from ..database.models.core import AuditEvent
from ..database.models.knowledge import (
    KnowledgeChunk, KnowledgeCollection, KnowledgeDocument,
)
from ..database.repositories.core import AuditRepository
from ..database.repositories.knowledge import (
    KnowledgeChunkRepository, KnowledgeCollectionRepository,
    KnowledgeDocumentRepository,
)
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from . import extractors
from .chunking import chunk_segments, document_text, extractive_excerpt, keyphrases

_log = logging.getLogger(__name__)


class KnowledgeError(AutonomusError):
    status_code = 422


def _actor(principal: Principal | None) -> str:
    return f"{principal.type.value}:{principal.id}" if principal else "system"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug[:120] or "collection"


def collection_to_dict(row: KnowledgeCollection) -> dict:
    return {
        "id": row.id, "name": row.name, "slug": row.slug,
        "description": row.description,
        "excluded_patterns": row.excluded_patterns or [],
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def document_to_dict(row: KnowledgeDocument) -> dict:
    return {
        "id": row.id, "collection_id": row.collection_id,
        "filename": row.filename, "source_kind": row.source_kind,
        "source_path": row.source_path, "format": row.format,
        "content_type": row.content_type, "size_bytes": row.size_bytes,
        "sha256": row.sha256, "status": row.status,
        "extractor_name": row.extractor_name,
        "extraction_detail": row.extraction_detail or {},
        "chunk_count": row.chunk_count,
        "indexed_chunk_count": row.indexed_chunk_count,
        "duplicate_of_id": row.duplicate_of_id,
        "error_detail": row.error_detail, "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def chunk_to_dict(row: KnowledgeChunk) -> dict:
    return {
        "id": row.id, "document_id": row.document_id,
        "chunk_index": row.chunk_index, "locator": row.locator,
        "char_start": row.char_start, "char_end": row.char_end,
        "text": row.text, "text_hash": row.text_hash,
        "memory_id": row.memory_id, "index_status": row.index_status,
        "index_detail": row.index_detail,
    }


class KnowledgeService:
    def __init__(self, application):
        self._app = application
        self._session_factory = application.session_factory
        self._settings = application.settings
        self._memory = application.memory

    # ------------------------------------------------------------ guards
    def _require_owner(self, principal: Principal | None) -> None:
        if principal is None or principal.type != PrincipalType.OWNER:
            raise PermissionDeniedError(
                "the knowledge library is owner-only: the files are "
                "the owner's private data, so no other principal "
                "may read, add or delete them",
                details={"principal": _actor(principal)})

    def _audit(self, principal, action: str, target_type: str, target_id,
               decision: str, reason: str | None = None,
               details: dict | None = None) -> None:
        session = self._session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value if principal else "system",
                actor_id=principal.id if principal else "knowledge",
                action=action, target_type=target_type, target_id=target_id,
                decision=decision, reason=reason, details=details or {},
                created_at=utcnow()))
        finally:
            session.close()

    # ------------------------------------------------------------ status
    def status(self, principal: Principal | None = None) -> dict:
        if principal is not None:
            self._require_owner(principal)
        session = self._session_factory()
        try:
            from sqlalchemy import func, select
            collections = session.scalar(
                select(func.count()).select_from(KnowledgeCollection)
                .where(KnowledgeCollection.deleted_at.is_(None))) or 0
            documents = session.scalar(
                select(func.count()).select_from(KnowledgeDocument)
                .where(KnowledgeDocument.deleted_at.is_(None))) or 0
            chunks = session.scalar(
                select(func.count()).select_from(KnowledgeChunk)) or 0
            indexed = session.scalar(
                select(func.count()).select_from(KnowledgeChunk)
                .where(KnowledgeChunk.memory_id.is_not(None))) or 0
        finally:
            session.close()
        return {
            "engine": "Personal Knowledge & File Intelligence "
                      "(Expansion Feature 6)",
            "api_version": APP_VERSION,
            "counts": {"collections": collections, "documents": documents,
                       "chunks": chunks, "indexed_chunks": indexed},
            "formats": extractors.format_support(),
            "embedder": "local-hash-v1",
            "embedder_caveat": C.EMBEDDER_CAVEAT,
            "retrieval_owner": "P-09 (ingestion, vector store, "
                               "hybrid retrieval, governed deletion)",
            "not_implemented": [
                "OCR — no OCR engine exists in this environment; "
                "images are metadata-only",
                "neural/semantic embedding — retrieval quality is "
                "capped by the local-hash-v1 lexical embedder "
                "(DEF-A2, owner-machine work)",
                "folder access beyond the knowledge-import "
                "directory — the owner's real folders live on his "
                "Windows machine (DEF-A1)",
            ],
        }

    def formats(self, principal: Principal | None = None) -> dict:
        if principal is not None:
            self._require_owner(principal)
        support = extractors.format_support()
        return {"formats": {
            fmt: {"state": state,
                  "extractor": extractors.extractor_name(fmt)}
            for fmt, state in support.items()},
            "note": "states are probed at runtime from the "
                    "installed extractors, not asserted"}

    # -------------------------------------------------------- collections
    def create_collection(self, principal: Principal, data: dict) -> dict:
        self._require_owner(principal)
        name = (data.get("name") or "").strip()
        if not name:
            raise ValidationError("a collection requires a name")
        slug = _slugify(data.get("slug") or name)
        session = self._session_factory()
        try:
            repo = KnowledgeCollectionRepository(session)
            if repo.by_slug(slug) is not None:
                raise ValidationError(
                    f"a live collection with slug '{slug}' already exists")
            row = repo.add(KnowledgeCollection(
                name=name, slug=slug,
                description=(data.get("description") or "").strip(),
                excluded_patterns=list(data.get("excluded_patterns") or []),
                created_by=_actor(principal)))
            result = collection_to_dict(row)
        finally:
            session.close()
        self._audit(principal, "knowledge.collection_created",
                    "knowledge_collection", result["id"], "allow",
                    f"slug={slug}")
        return result

    def list_collections(self, principal: Principal, *, limit: int = 100,
                         offset: int = 0) -> tuple[list, int]:
        self._require_owner(principal)
        session = self._session_factory()
        try:
            repo = KnowledgeCollectionRepository(session)
            rows, total = repo.list_live(limit=limit, offset=offset)
            doc_repo = KnowledgeDocumentRepository(session)
            results = []
            for row in rows:
                entry = collection_to_dict(row)
                _docs, count = doc_repo.list_for_collection(
                    row.id, limit=1, offset=0)
                entry["document_count"] = count
                results.append(entry)
            return results, total
        finally:
            session.close()

    def _get_collection_row(self, principal: Principal,
                            collection_id: str) -> KnowledgeCollection:
        session = self._session_factory()
        try:
            row = KnowledgeCollectionRepository(session).get(collection_id)
            if row is None or row.deleted_at is not None:
                raise NotFoundError(
                    f"knowledge collection {collection_id} not found")
            session.expunge(row)
            return row
        finally:
            session.close()

    def get_collection(self, principal: Principal,
                       collection_id: str) -> dict:
        self._require_owner(principal)
        row = self._get_collection_row(principal, collection_id)
        session = self._session_factory()
        try:
            _docs, count = KnowledgeDocumentRepository(
                session).list_for_collection(row.id, limit=1, offset=0)
        finally:
            session.close()
        result = collection_to_dict(row)
        result["document_count"] = count
        return result

    def update_collection(self, principal: Principal, collection_id: str,
                          patch: dict) -> dict:
        self._require_owner(principal)
        session = self._session_factory()
        try:
            repo = KnowledgeCollectionRepository(session)
            row = repo.get(collection_id)
            if row is None or row.deleted_at is not None:
                raise NotFoundError(
                    f"knowledge collection {collection_id} not found")
            if "name" in patch and patch["name"]:
                row.name = str(patch["name"]).strip()
            if "description" in patch and patch["description"] is not None:
                row.description = str(patch["description"])
            if "excluded_patterns" in patch and \
                    patch["excluded_patterns"] is not None:
                row.excluded_patterns = list(patch["excluded_patterns"])
            repo.save(row)
            result = collection_to_dict(row)
        finally:
            session.close()
        self._audit(principal, "knowledge.collection_updated",
                    "knowledge_collection", collection_id, "allow",
                    f"keys={sorted(patch)}")
        return result

    def delete_collection(self, principal: Principal,
                          collection_id: str) -> dict:
        self._require_owner(principal)
        row = self._get_collection_row(principal, collection_id)
        session = self._session_factory()
        try:
            docs, _total = KnowledgeDocumentRepository(
                session).list_for_collection(collection_id, limit=10000)
            doc_ids = [d.id for d in docs]
        finally:
            session.close()
        deleted = [self.delete_document(principal, doc_id)
                   for doc_id in doc_ids]
        session = self._session_factory()
        try:
            repo = KnowledgeCollectionRepository(session)
            live = repo.get(collection_id)
            live.deleted_at = utcnow()
            repo.save(live)
        finally:
            session.close()
        self._audit(principal, "knowledge.collection_deleted",
                    "knowledge_collection", collection_id, "allow",
                    f"{len(deleted)} documents deleted with it")
        return {"id": collection_id, "slug": row.slug,
                "documents_deleted": len(deleted),
                "document_results": deleted}

    # ------------------------------------------------------------- storage
    def _storage_root(self) -> Path:
        return Path(self._settings.data_dir) / C.STORAGE_DIRNAME

    def _store_bytes(self, data: bytes, digest: str) -> str:
        """Content-addressed storage (the F03 pattern): the file's
        name IS its SHA-256, under a two-character shard."""
        name = f"{digest[:2]}/{digest}"
        path = self._storage_root() / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        return str(Path(C.STORAGE_DIRNAME) / name)

    def _import_root(self) -> Path:
        root = (Path(self._settings.data_dir) / C.IMPORT_DIRNAME).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    # ----------------------------------------------------------- documents
    def add_document(self, principal: Principal, collection_id: str, *,
                     filename: str, content_type: str = "",
                     data: bytes, source_kind: str = "upload",
                     source_path: str | None = None) -> dict:
        """The one intake path for uploads and folder indexing:
        store bytes, extract for real, chunk, ingest into P-09,
        and record every outcome — including the refusals."""
        self._require_owner(principal)
        collection = self._get_collection_row(principal, collection_id)
        filename = (filename or "").strip() or "unnamed"
        base_name = filename.replace("\\", "/").rsplit("/", 1)[-1]
        if len(data) > C.MAX_FILE_BYTES:
            raise ValidationError(
                f"file is {len(data)} bytes; the per-file cap is "
                f"{C.MAX_FILE_BYTES} bytes (bounded processing)")
        digest = hashlib.sha256(data).hexdigest()
        extension = Path(base_name).suffix.lower()
        fmt = C.FORMAT_BY_EXTENSION.get(extension, "unknown")

        session = self._session_factory()
        try:
            doc_repo = KnowledgeDocumentRepository(session)
            earlier = [d for d in doc_repo.by_sha256(digest)
                       if d.id is not None]
            duplicate_of = earlier[0].id if earlier else None
        finally:
            session.close()

        excluded = any(
            fnmatch.fnmatch(candidate.lower(), pattern.lower())
            for pattern in (collection.excluded_patterns or [])
            for candidate in (base_name, filename))
        storage_path = "" if excluded else self._store_bytes(data, digest)

        session = self._session_factory()
        try:
            row = KnowledgeDocumentRepository(session).add(
                KnowledgeDocument(
                    collection_id=collection.id, filename=filename,
                    source_kind=source_kind, source_path=source_path,
                    format=fmt, content_type=content_type or "",
                    size_bytes=len(data), sha256=digest,
                    storage_path=storage_path, status="received",
                    duplicate_of_id=duplicate_of, created_by=_actor(principal)))
            doc_id = row.id
        finally:
            session.close()
        self._audit(principal, "knowledge.document_received",
                    "knowledge_document", doc_id, "allow",
                    f"{filename} ({len(data)} bytes, sha256={digest[:12]}…)",
                    {"format": fmt, "source_kind": source_kind,
                     "duplicate_of": duplicate_of})

        if excluded:
            return self._finish_document(
                principal, doc_id, status="excluded",
                error="matched the collection's exclusion patterns; "
                      "bytes were not stored and nothing was indexed")
        if fmt == "unknown" or (fmt != "image"
                                and fmt not in C.SUPPORTED_FORMATS):
            return self._finish_document(
                principal, doc_id, status="unsupported_format",
                error=f"no extractor for format '{fmt}' "
                      f"(extension '{extension or 'none'}'); bytes are "
                      "stored and the document is catalogued, but no "
                      "text was extracted or invented")
        try:
            segments, detail = extractors.extract(fmt, data)
        except extractors.UnsupportedFormat:
            return self._finish_document(
                principal, doc_id, status="unsupported_format",
                extractor=extractors.extractor_name(fmt),
                error=f"no extractor for format '{fmt}'")
        except extractors.ExtractionError as exc:
            return self._finish_document(
                principal, doc_id, status="extraction_failed",
                extractor=extractors.extractor_name(fmt),
                error=str(exc))

        if fmt == "image":
            return self._finish_document(
                principal, doc_id, status="metadata_only",
                extractor="pillow-metadata", detail=detail,
                error="image metadata recorded; OCR is not "
                      "implemented in this environment, so no text "
                      "was extracted")
        text = document_text(segments)
        if not text.strip():
            return self._finish_document(
                principal, doc_id, status="empty",
                extractor=extractors.extractor_name(fmt), detail=detail,
                error="extraction succeeded but the document "
                      "contains no text")

        chunks = chunk_segments(segments)
        outcomes = self._ingest_chunks(
            principal, collection, doc_id, filename, chunks)
        stored = sum(1 for o in outcomes
                     if o["index_status"] in ("stored", "duplicate"))
        sensitive = sum(1 for o in outcomes
                        if o["index_status"] == "rejected_sensitive")
        if duplicate_of:
            status = "duplicate"
        elif stored == 0 and sensitive == len(outcomes) and outcomes:
            status = "rejected_sensitive"
        elif stored < len(outcomes):
            status = "partially_indexed"
        else:
            status = "indexed"
        result = self._finish_document(
            principal, doc_id, status=status,
            extractor=extractors.extractor_name(fmt), detail=detail,
            chunk_count=len(chunks), indexed=stored)
        self._audit(principal, "knowledge.document_indexed",
                    "knowledge_document", doc_id,
                    "allow" if status in ("indexed", "duplicate") else "partial",
                    f"status={status}; chunks={len(chunks)}; "
                    f"indexed={stored}",
                    {"outcomes": {o["index_status"]: sum(
                        1 for x in outcomes
                        if x["index_status"] == o["index_status"])
                        for o in outcomes}})
        return result

    def _ingest_chunks(self, principal, collection, doc_id: str,
                       filename: str, chunks) -> list[dict]:
        """Each chunk through P-09's governed ingestion — the
        secret screen, usefulness filter and duplicate detection
        apply to document content exactly as to any memory."""
        outcomes = []
        session = self._session_factory()
        try:
            chunk_repo = KnowledgeChunkRepository(session)
            for index, chunk in enumerate(chunks):
                result = self._memory.ingestion.ingest(principal, {
                    "title": f"{filename} — {chunk.locator}",
                    "content": chunk.text,
                    "source_type": "document",
                    "source_ref": f"knowledge_document:{doc_id}",
                    "category": "PROJECT_CONTEXT",
                    "truth_class": "user_provided",
                    "access_scope": "OWNER_ONLY",
                    "project_ref": collection.slug,
                    "layer": "semantic",
                })
                job_status = result["status"]
                mapping = {
                    "STORED": "stored",
                    "REJECTED_DUPLICATE": "duplicate",
                    "REJECTED_SENSITIVE": "rejected_sensitive",
                    "REJECTED_LOW_VALUE": "rejected_low_value",
                }
                index_status = mapping.get(job_status, "rejected_low_value")
                memory_id = result.get("memory_id") \
                    if index_status in ("stored", "duplicate") else None
                row = chunk_repo.add(KnowledgeChunk(
                    document_id=doc_id, chunk_index=index,
                    locator=chunk.locator, char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    # A chunk the secret screen rejected is never
                    # persisted here either — hash only.
                    text=None if index_status == "rejected_sensitive"
                    else chunk.text,
                    text_hash=hashlib.sha256(
                        chunk.text.encode("utf-8")).hexdigest(),
                    memory_id=memory_id, index_status=index_status,
                    index_detail=result.get("reason", ""),
                    created_by=_actor(principal)))
                outcomes.append({"chunk_id": row.id,
                                 "index_status": index_status,
                                 "memory_id": memory_id})
        finally:
            session.close()
        return outcomes

    def _finish_document(self, principal, doc_id: str, *, status: str,
                         extractor: str | None = None,
                         detail: dict | None = None,
                         error: str | None = None,
                         chunk_count: int = 0, indexed: int = 0) -> dict:
        session = self._session_factory()
        try:
            repo = KnowledgeDocumentRepository(session)
            row = repo.get(doc_id)
            row.status = status
            if extractor is not None:
                row.extractor_name = extractor
            if detail is not None:
                row.extraction_detail = detail
            if error is not None:
                row.error_detail = error
            row.chunk_count = chunk_count
            row.indexed_chunk_count = indexed
            repo.save(row)
            return document_to_dict(row)
        finally:
            session.close()

    def index_folder(self, principal: Principal, collection_id: str, *,
                     folder: str) -> dict:
        """Index a folder the owner placed under the import root.
        The resolved path must stay inside the root — traversal
        is refused, and nothing outside the root is reachable
        (the owner's real folders live on his machine, DEF-A1)."""
        self._require_owner(principal)
        collection = self._get_collection_row(principal, collection_id)
        root = self._import_root()
        target = (root / folder).resolve()
        if target != root and root not in target.parents:
            raise ValidationError(
                "folder must resolve inside the knowledge-import "
                f"directory ({root})")
        if not target.is_dir():
            raise NotFoundError(
                f"folder '{folder}' not found under the "
                "knowledge-import directory")
        files = sorted(p for p in target.rglob("*") if p.is_file())
        self._audit(principal, "knowledge.folder_index_requested",
                    "knowledge_collection", collection.id, "allow",
                    f"folder={folder}; files={len(files)}")
        results = []
        for path in files:
            relative = str(path.relative_to(root))
            data = path.read_bytes()
            if len(data) > C.MAX_FILE_BYTES:
                results.append({"filename": relative,
                                "status": "skipped_too_large",
                                "size_bytes": len(data)})
                continue
            results.append(self.add_document(
                principal, collection.id, filename=relative,
                data=data, source_kind="folder", source_path=relative))
        return {"collection_id": collection.id, "folder": folder,
                "files_found": len(files), "results": results}

    def list_documents(self, principal: Principal, collection_id: str, *,
                       limit: int = 100, offset: int = 0) -> tuple[list, int]:
        self._require_owner(principal)
        self._get_collection_row(principal, collection_id)
        session = self._session_factory()
        try:
            rows, total = KnowledgeDocumentRepository(
                session).list_for_collection(collection_id,
                                             limit=limit, offset=offset)
            return [document_to_dict(r) for r in rows], total
        finally:
            session.close()

    def _get_document_row(self, principal: Principal,
                          document_id: str) -> KnowledgeDocument:
        session = self._session_factory()
        try:
            row = KnowledgeDocumentRepository(session).get(document_id)
            if row is None or row.deleted_at is not None:
                raise NotFoundError(
                    f"knowledge document {document_id} not found")
            session.expunge(row)
            return row
        finally:
            session.close()

    def _document_text(self, document_id: str) -> str:
        session = self._session_factory()
        try:
            chunks = KnowledgeChunkRepository(
                session).list_for_document(document_id)
            return "\n".join(c.text for c in chunks if c.text)
        finally:
            session.close()

    def get_document(self, principal: Principal, document_id: str, *,
                     query: str = "") -> dict:
        self._require_owner(principal)
        row = self._get_document_row(principal, document_id)
        session = self._session_factory()
        try:
            chunks = KnowledgeChunkRepository(
                session).list_for_document(document_id)
            chunk_dicts = [chunk_to_dict(c) for c in chunks]
            text = "\n".join(c.text for c in chunks if c.text)
        finally:
            session.close()
        result = document_to_dict(row)
        result["chunks"] = chunk_dicts
        result["intelligence"] = {
            "keyphrases": keyphrases(text) if text else [],
            "keyphrase_method": "token-frequency statistics "
                                "(deterministic; not model-inferred "
                                "topics)",
            "excerpt": extractive_excerpt(text, query),
        }
        return result

    def read_document_bytes(self, principal: Principal,
                            document_id: str) -> tuple[dict, bytes]:
        self._require_owner(principal)
        row = self._get_document_row(principal, document_id)
        if not row.storage_path:
            raise NotFoundError(
                "this document's bytes were not stored "
                f"(status: {row.status})")
        path = Path(self._settings.data_dir) / row.storage_path
        if not path.is_file():
            raise NotFoundError("the stored file is missing from disk")
        return document_to_dict(row), path.read_bytes()

    # -------------------------------------------------------------- search
    def search(self, principal: Principal, *, query: str,
               collection_id: str | None = None,
               limit: int = 20) -> dict:
        """P-09 hybrid retrieval, enriched with F06 citations.
        Ranking is P-09's own — F06 filters to knowledge chunks
        and attaches (document, chunk, locator) citations; it
        re-ranks nothing."""
        self._require_owner(principal)
        project_ref = None
        if collection_id:
            project_ref = self._get_collection_row(
                principal, collection_id).slug
        found = self._memory.retrieval.search(
            principal, query=query, project_ref=project_ref,
            limit=max(limit * 3, limit))
        memory_ids = [r["id"] for r in found["results"]]
        session = self._session_factory()
        try:
            chunk_rows = KnowledgeChunkRepository(
                session).by_memory_ids(memory_ids)
            doc_ids = {c.document_id for c in chunk_rows}
            docs = {}
            doc_repo = KnowledgeDocumentRepository(session)
            for doc_id in doc_ids:
                doc = doc_repo.get(doc_id)
                if doc is not None and doc.deleted_at is None:
                    docs[doc_id] = doc
            citations: dict[str, list[dict]] = {}
            for chunk in chunk_rows:
                doc = docs.get(chunk.document_id)
                if doc is None:
                    continue
                if collection_id and doc.collection_id != collection_id:
                    continue
                citations.setdefault(chunk.memory_id, []).append({
                    "document_id": doc.id, "filename": doc.filename,
                    "collection_id": doc.collection_id,
                    "chunk_id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "locator": chunk.locator,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                })
        finally:
            session.close()
        results = []
        for entry in found["results"]:
            cites = citations.get(entry["id"])
            if not cites:
                continue
            # P-09's own §9.5 reliability bar for what counts as a
            # match (task relevance, or semantic similarity at
            # least 0.35): a stray trigram collision in the
            # lexical embedder is not a knowledge hit. Order is
            # P-09's, unchanged — this filters, never re-ranks.
            breakdown = entry["score_breakdown"]
            if breakdown["task_relevance"] == 0.0 \
                    and breakdown["semantic_similarity"] < 0.35:
                continue
            results.append({
                "memory_id": entry["id"], "score": entry["score"],
                "score_breakdown": entry["score_breakdown"],
                "title": entry["title"], "excerpt": entry["content"],
                "truth_class": entry["truth_class"],
                "freshness": entry["freshness"],
                "citations": cites,
            })
            if len(results) >= limit:
                break
        self._audit(principal, "knowledge.searched",
                    "knowledge_collection", collection_id, "allow",
                    f"query_len={len(query)}; results={len(results)}")
        return {
            "query": query, "results": results, "count": len(results),
            "method": "P-09 hybrid retrieval (exact + keyword + "
                      "local-hash vector) with F06 citations; "
                      "ranking is P-09's, unchanged; hits must "
                      "clear P-09's §9.5 reliability bar",
            "embedder": "local-hash-v1",
            "embedder_caveat": C.EMBEDDER_CAVEAT,
            "degraded": found["degraded"],
            "note": "every result cites the document and chunk "
                    "location it came from; content is the "
                    "document's own words, distinguished from any "
                    "interpretation by the citation",
        }

    # ------------------------------------------------- compare & duplicates
    def compare(self, principal: Principal, document_id: str,
                other_id: str) -> dict:
        self._require_owner(principal)
        left_row = self._get_document_row(principal, document_id)
        right_row = self._get_document_row(principal, other_id)
        left = self._document_text(document_id).splitlines()
        right = self._document_text(other_id).splitlines()
        diff = list(difflib.unified_diff(
            left, right, fromfile=left_row.filename,
            tofile=right_row.filename, lineterm=""))
        matcher = difflib.SequenceMatcher(None, left, right)
        added = sum(1 for line in diff if line.startswith("+")
                    and not line.startswith("+++"))
        removed = sum(1 for line in diff if line.startswith("-")
                      and not line.startswith("---"))
        self._audit(principal, "knowledge.documents_compared",
                    "knowledge_document", document_id, "allow",
                    f"against {other_id}: +{added}/-{removed} lines")
        return {
            "method": "deterministic text diff (difflib) over the "
                      "extracted texts — not a semantic comparison",
            "left": {"document_id": document_id,
                     "filename": left_row.filename,
                     "sha256": left_row.sha256},
            "right": {"document_id": other_id,
                      "filename": right_row.filename,
                      "sha256": right_row.sha256},
            "identical_bytes": left_row.sha256 == right_row.sha256,
            "similarity_ratio": round(matcher.ratio(), 4),
            "lines_added": added, "lines_removed": removed,
            "diff": diff[:2000],
            "diff_truncated": len(diff) > 2000,
        }

    def duplicates(self, principal: Principal, *,
                   collection_id: str | None = None) -> dict:
        self._require_owner(principal)
        session = self._session_factory()
        try:
            docs = KnowledgeDocumentRepository(session).list_live(
                limit=10000)
        finally:
            session.close()
        groups: dict[str, list[dict]] = {}
        for doc in docs:
            if collection_id and doc.collection_id != collection_id:
                continue
            groups.setdefault(doc.sha256, []).append(document_to_dict(doc))
        exact = [{"sha256": digest, "documents": rows}
                 for digest, rows in groups.items() if len(rows) > 1]
        return {"method": "exact byte identity (SHA-256) — "
                          "near-duplicate similarity is not claimed",
                "groups": exact, "group_count": len(exact)}

    # -------------------------------------------------------------- delete
    def delete_document(self, principal: Principal,
                        document_id: str) -> dict:
        """Total deletion, proven: stored bytes removed, chunk
        rows removed, and every exclusively-owned P-09 memory
        record deleted through P-09's governed deletion (which
        removes the embedding and verifies its absence). A
        memory record another live document also cites survives
        until that document is deleted."""
        self._require_owner(principal)
        row = self._get_document_row(principal, document_id)
        session = self._session_factory()
        try:
            chunk_repo = KnowledgeChunkRepository(session)
            chunks = chunk_repo.list_for_document(document_id)
            memory_ids = sorted({c.memory_id for c in chunks
                                 if c.memory_id})
            shared: dict[str, int] = {}
            exclusive: list[str] = []
            for memory_id in memory_ids:
                refs = chunk_repo.by_memory_id(memory_id)
                others = {c.document_id for c in refs} - {document_id}
                live_others = 0
                doc_repo = KnowledgeDocumentRepository(session)
                for other_id in others:
                    other = doc_repo.get(other_id)
                    if other is not None and other.deleted_at is None:
                        live_others += 1
                if live_others:
                    shared[memory_id] = live_others
                else:
                    exclusive.append(memory_id)
            chunk_repo.delete_for_document(document_id)
            # Bytes are shared by content address: remove only
            # when no other live document uses the same file.
            bytes_removed = False
            if row.storage_path:
                same = [d for d in KnowledgeDocumentRepository(session)
                        .by_sha256(row.sha256) if d.id != document_id]
                if not same:
                    path = Path(self._settings.data_dir) / row.storage_path
                    if path.is_file():
                        path.unlink()
                        bytes_removed = True
            doc_repo = KnowledgeDocumentRepository(session)
            live = doc_repo.get(document_id)
            live.deleted_at = utcnow()
            doc_repo.save(live)
        finally:
            session.close()
        receipts = []
        for memory_id in exclusive:
            receipt = self._memory.store.delete(principal, memory_id)
            receipts.append({"memory_id": memory_id,
                             "status": receipt["status"],
                             "index_sync_verified":
                                 receipt["index_sync_verified"]})
        self._audit(principal, "knowledge.document_deleted",
                    "knowledge_document", document_id, "allow",
                    f"memories_deleted={len(receipts)}; "
                    f"shared_kept={len(shared)}; "
                    f"bytes_removed={bytes_removed}",
                    {"receipts": receipts})
        return {"document_id": document_id, "filename": row.filename,
                "memories_deleted": receipts,
                "shared_memories_kept": len(shared),
                "bytes_removed": bytes_removed,
                "chunks_removed": len(chunks)}
