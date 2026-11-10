"""Expansion Feature 6 integration tests: the migration cycle,
the intake pipeline per format with real extraction evidence,
P-09 indexing with provenance, cited retrieval with project
scoping, deterministic comparison, folder indexing inside the
import root, and total deletion (bytes + index, proven), plus
the HTTP surface.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.version import APP_VERSION
from tests.conftest import OWNER
from tests.f06_support import (
    CSV_BYTES, TXT_BYTES, app_f06, audit_events, client_f06,
    make_collection, make_docx_bytes, make_pdf_bytes, make_png_bytes,
    make_pptx_bytes, make_xlsx_bytes, owner_http_headers, upload,
)


# ------------------------------------------------------------ migration
def test_f06_migration_cycle(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    db = tmp_path / "f06_cycle.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")

    def count() -> int:
        with engine.connect() as conn:
            return conn.execute(text(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            )).scalar_one()

    def head() -> str:
        with engine.connect() as conn:
            return conn.execute(text(
                "SELECT version_num FROM alembic_version")).scalar_one()

    command.upgrade(config, "head")
    assert head() == "af39baad9c40"
    assert count() == 235  # 232 at F03 head + 3 F06 tables
    command.downgrade(config, "c41f7a9d03e6")
    assert count() == 232
    command.upgrade(config, "head")
    assert count() == 235


def test_f06_version_pin():
    assert APP_VERSION == "1.4.0"


# ------------------------------------------------------------ collections
async def test_collection_crud_and_slug_uniqueness(app_f06):
    svc = app_f06.knowledge
    created = make_collection(app_f06, "Aurora Project")
    assert created["slug"] == "aurora-project"
    with pytest.raises(Exception) as excinfo:
        make_collection(app_f06, "Aurora Project")
    assert "already exists" in str(excinfo.value)
    updated = svc.update_collection(
        OWNER, created["id"],
        {"description": "the aurora files",
         "excluded_patterns": ["*.tmp"]})
    assert updated["excluded_patterns"] == ["*.tmp"]
    rows, total = svc.list_collections(OWNER)
    assert total == 1 and rows[0]["document_count"] == 0


# -------------------------------------------------------------- ingestion
async def test_text_upload_indexes_into_p09_with_provenance(app_f06):
    col = make_collection(app_f06)
    doc = upload(app_f06, col["id"], "notes.txt", TXT_BYTES)
    assert doc["status"] == "indexed"
    assert doc["extractor_name"] == "stdlib-utf8"
    assert doc["chunk_count"] == 1 and doc["indexed_chunk_count"] == 1

    detail = app_f06.knowledge.get_document(OWNER, doc["id"])
    chunk = detail["chunks"][0]
    assert chunk["index_status"] == "stored"
    assert chunk["locator"] == "lines 1–3"
    # The chunk IS a P-09 record with document provenance.
    record = app_f06.memory.store.get(OWNER, chunk["memory_id"])
    assert record["source_type"] == "document"
    assert record["source_ref"] == f"knowledge_document:{doc['id']}"
    assert record["project_ref"] == "aurora-project"
    assert record["truth_class"] == "user_provided"
    assert record["access_scope"] == "OWNER_ONLY"
    assert app_f06.memory.vectors.contains(chunk["memory_id"])


@pytest.mark.parametrize("filename,builder,pages_key,locator_hint", [
    ("report.pdf", lambda: make_pdf_bytes(
        ["Alpha page one content.", "Beta page two content."]),
     "pages", "page 2"),
    ("plan.docx", make_docx_bytes, "paragraphs", "table 1"),
    ("book.xlsx", make_xlsx_bytes, "sheets", "sheet 'Budget'"),
    ("deck.pptx", make_pptx_bytes, "slides", "slide 1"),
])
async def test_office_and_pdf_uploads_extract_for_real(
        app_f06, filename, builder, pages_key, locator_hint):
    col = make_collection(app_f06)
    doc = upload(app_f06, col["id"], filename, builder())
    assert doc["status"] == "indexed", doc
    assert pages_key in doc["extraction_detail"]
    detail = app_f06.knowledge.get_document(OWNER, doc["id"])
    locators = [c["locator"] for c in detail["chunks"]]
    assert any(locator_hint in loc for loc in locators), locators


async def test_csv_upload_indexes_rows(app_f06):
    col = make_collection(app_f06)
    doc = upload(app_f06, col["id"], "data.csv", CSV_BYTES)
    assert doc["status"] == "indexed"
    assert doc["extraction_detail"]["columns"] == ["item", "amount"]


async def test_image_upload_is_metadata_only(app_f06):
    col = make_collection(app_f06)
    doc = upload(app_f06, col["id"], "shot.png", make_png_bytes())
    assert doc["status"] == "metadata_only"
    assert doc["extraction_detail"]["ocr"] == "not_implemented"
    assert doc["chunk_count"] == 0


async def test_unknown_extension_is_unsupported_not_invented(app_f06):
    col = make_collection(app_f06)
    doc = upload(app_f06, col["id"], "mystery.xyz", b"some bytes")
    assert doc["status"] == "unsupported_format"
    assert doc["chunk_count"] == 0


async def test_malformed_pdf_is_extraction_failed(app_f06):
    col = make_collection(app_f06)
    doc = upload(app_f06, col["id"], "broken.pdf",
                 b"%PDF- definitely not a pdf")
    assert doc["status"] == "extraction_failed"
    assert doc["chunk_count"] == 0


async def test_empty_document_is_empty(app_f06):
    col = make_collection(app_f06)
    doc = upload(app_f06, col["id"], "blank.txt", b"   \n")
    assert doc["status"] == "empty"


async def test_duplicate_upload_links_and_dedupes(app_f06):
    col = make_collection(app_f06)
    first = upload(app_f06, col["id"], "notes.txt", TXT_BYTES)
    second = upload(app_f06, col["id"], "notes.txt", TXT_BYTES)
    assert second["status"] == "duplicate"
    assert second["duplicate_of_id"] == first["id"]
    detail = app_f06.knowledge.get_document(OWNER, second["id"])
    # P-09 dedups on content hash (title + content): the identical
    # chunk of the identically-named document resolved to the
    # SAME P-09 record — nothing was stored twice.
    first_detail = app_f06.knowledge.get_document(OWNER, first["id"])
    assert detail["chunks"][0]["memory_id"] == \
        first_detail["chunks"][0]["memory_id"]
    assert detail["chunks"][0]["index_status"] == "duplicate"
    groups = app_f06.knowledge.duplicates(OWNER)
    assert groups["group_count"] == 1


async def test_byte_duplicate_under_another_name_is_catalogued(app_f06):
    col = make_collection(app_f06)
    first = upload(app_f06, col["id"], "notes.txt", TXT_BYTES)
    renamed = upload(app_f06, col["id"], "notes-copy.txt", TXT_BYTES)
    # Byte identity is filename-independent: the catalogue links
    # it as a duplicate document even though P-09 stores its
    # chunk under the new title (its own provenance).
    assert renamed["status"] == "duplicate"
    assert renamed["duplicate_of_id"] == first["id"]


async def test_excluded_pattern_skips_storage_and_index(app_f06):
    col = make_collection(app_f06, "Guarded",
                          excluded_patterns=["secret*"])
    doc = upload(app_f06, col["id"], "secret-plan.txt", TXT_BYTES)
    assert doc["status"] == "excluded"
    assert doc["chunk_count"] == 0
    # Bytes were not stored.
    _meta, total = app_f06.knowledge.list_documents(OWNER, col["id"])
    assert total == 1
    with pytest.raises(Exception):
        app_f06.knowledge.read_document_bytes(OWNER, doc["id"])


async def test_oversize_upload_is_refused(app_f06):
    from app.knowledge import constants as C
    col = make_collection(app_f06)
    with pytest.raises(Exception) as excinfo:
        upload(app_f06, col["id"], "big.txt",
               b"x" * (C.MAX_FILE_BYTES + 1))
    assert "cap" in str(excinfo.value)


# --------------------------------------------------------- folder intake
async def test_folder_indexing_inside_import_root(app_f06, tmp_path):
    col = make_collection(app_f06)
    root = Path(app_f06.settings.data_dir) / "knowledge-import" / "proj"
    root.mkdir(parents=True)
    (root / "a.txt").write_bytes(TXT_BYTES)
    sub = root / "sub"
    sub.mkdir()
    (sub / "b.csv").write_bytes(CSV_BYTES)
    result = app_f06.knowledge.index_folder(OWNER, col["id"], folder="proj")
    assert result["files_found"] == 2
    statuses = {r["filename"]: r["status"] for r in result["results"]}
    assert statuses["proj/a.txt"] == "indexed"
    assert statuses["proj/sub/b.csv"] == "indexed"


# --------------------------------------------------------------- retrieval
async def test_search_returns_cited_chunks(app_f06):
    col = make_collection(app_f06)
    doc = upload(app_f06, col["id"], "notes.txt", TXT_BYTES)
    found = app_f06.knowledge.search(OWNER, query="budget review")
    assert found["count"] >= 1
    hit = found["results"][0]
    cite = hit["citations"][0]
    assert cite["document_id"] == doc["id"]
    assert cite["filename"] == "notes.txt"
    assert cite["locator"] == "lines 1–3"
    assert "budget review" in hit["excerpt"]
    assert found["embedder"] == "local-hash-v1"
    assert "lexical" in found["embedder_caveat"]


async def test_search_is_project_scoped(app_f06):
    aurora = make_collection(app_f06, "Aurora Project")
    other = make_collection(app_f06, "Other Project")
    upload(app_f06, aurora["id"], "notes.txt", TXT_BYTES)
    upload(app_f06, other["id"], "other.txt",
           b"Completely different content about gardening tools "
           b"and soil preparation schedules.\n")
    scoped = app_f06.knowledge.search(
        OWNER, query="budget review", collection_id=aurora["id"])
    assert scoped["count"] >= 1
    for hit in scoped["results"]:
        for cite in hit["citations"]:
            assert cite["collection_id"] == aurora["id"]
    scoped_other = app_f06.knowledge.search(
        OWNER, query="budget review", collection_id=other["id"])
    assert scoped_other["count"] == 0


async def test_search_ignores_non_document_memory(app_f06):
    col = make_collection(app_f06)
    upload(app_f06, col["id"], "notes.txt", TXT_BYTES)
    app_f06.memory.ingestion.ingest(OWNER, {
        "title": "budget review memo",
        "content": "A budget review happened in the operations "
                   "meeting yesterday afternoon.",
        "source_type": "user_input", "source_ref": "chat:1"})
    found = app_f06.knowledge.search(OWNER, query="budget review")
    assert found["count"] >= 1
    for hit in found["results"]:
        assert hit["citations"], "knowledge search cites documents only"


# ------------------------------------------------------ compare & detail
async def test_compare_is_a_deterministic_diff(app_f06):
    col = make_collection(app_f06)
    v1 = upload(app_f06, col["id"], "plan.txt",
                b"Line one of the plan.\nLine two stays.\n")
    v2 = upload(app_f06, col["id"], "plan-v2.txt",
                b"Line one of the plan, revised.\nLine two stays.\n")
    result = app_f06.knowledge.compare(OWNER, v1["id"], v2["id"])
    assert "difflib" in result["method"]
    assert result["identical_bytes"] is False
    assert result["lines_added"] == 1 and result["lines_removed"] == 1
    same = app_f06.knowledge.compare(OWNER, v1["id"], v1["id"])
    assert same["identical_bytes"] is True
    assert same["similarity_ratio"] == 1.0


async def test_document_detail_carries_labelled_intelligence(app_f06):
    col = make_collection(app_f06)
    doc = upload(app_f06, col["id"], "notes.txt", TXT_BYTES)
    detail = app_f06.knowledge.get_document(OWNER, doc["id"])
    intel = detail["intelligence"]
    assert "statistics" in intel["keyphrase_method"]
    assert "not an AI summary" in intel["excerpt"]["label"]
    assert intel["keyphrases"], "frequency statistics are present"


# --------------------------------------------------------------- deletion
async def test_delete_removes_bytes_chunks_and_index(app_f06):
    col = make_collection(app_f06)
    doc = upload(app_f06, col["id"], "notes.txt", TXT_BYTES)
    detail = app_f06.knowledge.get_document(OWNER, doc["id"])
    memory_id = detail["chunks"][0]["memory_id"]
    # Content-addressed storage: the path derives from the SHA-256.
    stored = (Path(app_f06.settings.data_dir) / "knowledge-files"
              / doc["sha256"][:2] / doc["sha256"])
    assert stored.is_file()
    result = app_f06.knowledge.delete_document(OWNER, doc["id"])
    assert result["bytes_removed"] is True
    assert result["chunks_removed"] == 1
    assert result["memories_deleted"][0]["index_sync_verified"] is True
    assert not stored.is_file()
    # The P-09 record is governed-deleted and the embedding is gone.
    assert not app_f06.memory.vectors.contains(memory_id)
    with pytest.raises(Exception):
        app_f06.memory.store.get(OWNER, memory_id)
    found = app_f06.knowledge.search(OWNER, query="budget review")
    assert found["count"] == 0


async def test_delete_keeps_memory_shared_with_live_duplicate(app_f06):
    col = make_collection(app_f06)
    first = upload(app_f06, col["id"], "notes.txt", TXT_BYTES)
    second = upload(app_f06, col["id"], "notes.txt", TXT_BYTES)
    memory_id = app_f06.knowledge.get_document(
        OWNER, first["id"])["chunks"][0]["memory_id"]
    result = app_f06.knowledge.delete_document(OWNER, first["id"])
    assert result["shared_memories_kept"] == 1
    assert app_f06.memory.vectors.contains(memory_id)
    # Deleting the last referencing document removes the index entry.
    result2 = app_f06.knowledge.delete_document(OWNER, second["id"])
    assert result2["memories_deleted"][0]["index_sync_verified"] is True
    assert not app_f06.memory.vectors.contains(memory_id)


async def test_delete_collection_cascades(app_f06):
    col = make_collection(app_f06)
    upload(app_f06, col["id"], "notes.txt", TXT_BYTES)
    result = app_f06.knowledge.delete_collection(OWNER, col["id"])
    assert result["documents_deleted"] == 1
    rows, total = app_f06.knowledge.list_collections(OWNER)
    assert total == 0


# ------------------------------------------------------------------- HTTP
def test_http_surface_round_trip(client_f06):
    headers = owner_http_headers(client_f06)
    created = client_f06.post("/api/v1/knowledge/collections",
                              json={"name": "HTTP Project"},
                              headers=headers)
    assert created.status_code == 201, created.text
    col_id = created.json()["data"]["id"]
    up = client_f06.post(
        f"/api/v1/knowledge/collections/{col_id}/documents"
        "?filename=notes.txt",
        content=TXT_BYTES,
        headers={**headers, "Content-Type": "text/plain"})
    assert up.status_code == 201, up.text
    assert up.json()["data"]["status"] == "indexed"
    status = client_f06.get("/api/v1/knowledge/status", headers=headers)
    assert status.json()["data"]["api_version"] == "1.4.0"
    found = client_f06.get("/api/v1/knowledge/search",
                           params={"q": "budget review"},
                           headers=headers)
    assert found.json()["data"]["count"] >= 1
    cite = found.json()["data"]["results"][0]["citations"][0]
    assert cite["locator"] == "lines 1–3"


def test_http_requires_authentication(client_f06):
    resp = client_f06.get("/api/v1/knowledge/status")
    assert resp.status_code in (401, 403)
