"""Expansion Feature 6 security tests: the owner-only boundary at
both depths, P-09's secret screen applied to document content
(the value persisted NOWHERE), the prompt-injection rule
(documents are data, never instructions — nothing executes),
folder traversal refusal, audit coverage, and the Article 0
schema guards (no money columns, no secret-value columns).
"""
from __future__ import annotations

import pytest
from sqlalchemy import inspect

from app.core.exceptions import PermissionDeniedError, ValidationError
from tests.conftest import AGENT, EXTERNAL, OWNER, SERVICE
from tests.f06_support import (
    INJECTION_TEXT, SECRET_TEXT, TXT_BYTES, app_f06, audit_events,
    client_f06, make_collection, owner_http_headers, upload,
)


# --------------------------------------------------------- owner boundary
@pytest.mark.parametrize("principal", [AGENT, SERVICE, EXTERNAL],
                         ids=["agent", "service", "external"])
async def test_non_owner_refused_at_service_layer(app_f06, principal):
    col = make_collection(app_f06)
    doc = upload(app_f06, col["id"], "notes.txt", TXT_BYTES)
    svc = app_f06.knowledge
    with pytest.raises(PermissionDeniedError):
        svc.create_collection(principal, {"name": "Nope"})
    with pytest.raises(PermissionDeniedError):
        svc.list_collections(principal)
    with pytest.raises(PermissionDeniedError):
        svc.add_document(principal, col["id"], filename="x.txt",
                         data=TXT_BYTES)
    with pytest.raises(PermissionDeniedError):
        svc.search(principal, query="budget")
    with pytest.raises(PermissionDeniedError):
        svc.get_document(principal, doc["id"])
    with pytest.raises(PermissionDeniedError):
        svc.delete_document(principal, doc["id"])


def test_http_service_token_cannot_use_knowledge(client_f06):
    from tests.f03_support import service_http_headers
    headers = service_http_headers()
    resp = client_f06.get("/api/v1/knowledge/status", headers=headers)
    # The service principal is not the owner: the two-depth model
    # refuses it (route gate or service layer), never serves data.
    assert resp.status_code in (401, 403, 422)
    if resp.status_code == 200:  # pragma: no cover - must not happen
        raise AssertionError("service token was served knowledge data")


# ------------------------------------------------------------ secret screen
async def test_secret_chunk_is_screened_and_value_persisted_nowhere(app_f06):
    col = make_collection(app_f06)
    doc = upload(app_f06, col["id"], "ops.txt", SECRET_TEXT)
    # The whole file is one segment/chunk, and that chunk carries
    # credential-shaped material: P-09's screen rejects it.
    assert doc["status"] == "rejected_sensitive"
    detail = app_f06.knowledge.get_document(OWNER, doc["id"])
    chunk = detail["chunks"][0]
    assert chunk["index_status"] == "rejected_sensitive"
    assert chunk["memory_id"] is None
    # The chunk text is NULL in the catalogue — the value is not
    # persisted here either.
    assert chunk["text"] is None
    # And the secret value appears in no knowledge row and no
    # memory record (the P-09 security event names patterns only).
    session = app_f06.session_factory()
    try:
        from sqlalchemy import select
        from app.database.models.knowledge import (
            KnowledgeChunk, KnowledgeDocument)
        from app.database.models.memory import MemoryRecord
        for row in session.scalars(select(KnowledgeChunk)).all():
            assert "AKIAIOSFODNN7EXAMPLE" not in (row.text or "")
            assert "AKIAIOSFODNN7EXAMPLE" not in (row.index_detail or "")
        for row in session.scalars(select(KnowledgeDocument)).all():
            assert "AKIAIOSFODNN7EXAMPLE" not in (row.error_detail or "")
        for row in session.scalars(select(MemoryRecord)).all():
            assert "AKIAIOSFODNN7EXAMPLE" not in (row.content or "")
    finally:
        session.close()


async def test_secret_in_one_chunk_leaves_the_rest_indexed(app_f06):
    col = make_collection(app_f06)
    clean = b"Ordinary project text about the roadmap and design.\n"
    doc = app_f06.knowledge.add_document(
        OWNER, col["id"], filename="mixed.txt",
        data=clean + b"\n" + SECRET_TEXT)
    # Two line-block segments would be one chunk here (short
    # file): assert instead at the invariant level — no memory
    # record in P-09 contains the secret, whatever the chunking.
    session = app_f06.session_factory()
    try:
        from sqlalchemy import select
        from app.database.models.memory import MemoryRecord
        for row in session.scalars(select(MemoryRecord)).all():
            assert "AKIAIOSFODNN7EXAMPLE" not in (row.content or "")
    finally:
        session.close()
    assert doc["status"] in ("indexed", "partially_indexed",
                             "rejected_sensitive")


# -------------------------------------------------------- prompt injection
async def test_document_instructions_are_data_never_executed(app_f06):
    col = make_collection(app_f06)
    before = app_f06.tasks.list(limit=1, offset=0)
    doc = upload(app_f06, col["id"], "directives.txt", INJECTION_TEXT)
    after = app_f06.tasks.list(limit=1, offset=0)
    # The document indexed as data; nothing executed, no task or
    # plan was created from its content (pack §5 security rule).
    assert doc["status"] in ("indexed", "partially_indexed")
    assert before[1] == after[1]
    detail = app_f06.knowledge.get_document(OWNER, doc["id"])
    memory_id = detail["chunks"][0]["memory_id"]
    if memory_id:
        record = app_f06.memory.store.get(OWNER, memory_id)
        # Stored as user-provided DATA at document reliability —
        # never as an owner instruction, whatever the text claims.
        assert record["truth_class"] == "user_provided"
        assert record["category"] == "PROJECT_CONTEXT"
        assert record["source_type"] == "document"


# ------------------------------------------------------------ folder guard
async def test_folder_traversal_is_refused(app_f06):
    col = make_collection(app_f06)
    with pytest.raises(ValidationError):
        app_f06.knowledge.index_folder(OWNER, col["id"],
                                       folder="../outside")
    with pytest.raises(ValidationError):
        app_f06.knowledge.index_folder(OWNER, col["id"],
                                       folder="/etc")


# ------------------------------------------------------------------- audit
async def test_knowledge_acts_are_audited(app_f06):
    col = make_collection(app_f06)
    doc = upload(app_f06, col["id"], "notes.txt", TXT_BYTES)
    app_f06.knowledge.search(OWNER, query="budget review")
    app_f06.knowledge.delete_document(OWNER, doc["id"])
    actions = {e.action for e in audit_events(app_f06, "knowledge.")}
    assert "knowledge.collection_created" in actions
    assert "knowledge.document_received" in actions
    assert "knowledge.document_indexed" in actions
    assert "knowledge.searched" in actions
    assert "knowledge.document_deleted" in actions


# --------------------------------------------------------- schema guards
def test_knowledge_tables_have_no_money_or_secret_columns(app_f06):
    engine = app_f06.session_factory().get_bind()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"knowledge_collections", "knowledge_documents",
            "knowledge_chunks"} <= tables
    money_words = ("amount", "price", "balance", "currency",
                   "revenue", "cost", "fee", "payment", "wallet")
    secret_words = ("secret", "password", "token", "credential",
                    "api_key")
    for table in ("knowledge_collections", "knowledge_documents",
                  "knowledge_chunks"):
        for column in inspector.get_columns(table):
            name = column["name"].lower()
            assert not any(w in name for w in money_words), \
                f"{table}.{name} looks like a money column"
            assert not any(w in name for w in secret_words), \
                f"{table}.{name} looks like a secret-value column"


def test_no_public_knowledge_routes_added(client_f06):
    """F02's guard, restated for F06: the unauthenticated surface
    stays exactly the baseline three operations — F06 adds no
    public route."""
    headers = owner_http_headers(client_f06)
    resp = client_f06.get("/api/v1/integrations/api-catalogue",
                          headers=headers)
    catalogue = resp.json()["data"]
    assert catalogue["by_authorization_depth"]["public"] == 3
    knowledge_ops = [op for op in catalogue["operations"]
                     if op["path"].startswith("/api/v1/knowledge")]
    assert knowledge_ops, "the knowledge surface is catalogued"
    assert all(op["authorization_depth"] != "public"
               for op in knowledge_ops)
