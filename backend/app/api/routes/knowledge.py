"""Personal Knowledge & File Intelligence routes
(/api/v1/knowledge/...).

Expansion Feature 6. Authorization follows the Gate 2 review
§4.2 inheritance contract and the feature's own standard — BOTH
depths, deliberately: routes gate on the ``Permission`` enum
(reads: ``read_system_data``; every write, including deletion:
``write_system_data``), and the service layer additionally
refuses every non-owner principal, because the library is the
owner's private data.

Upload is a raw-body intake (the F03 precedent): the request
body IS the file, its Content-Type header the media type, and
``filename`` a query parameter — no multipart dependency is
added for one endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from ...core.application import Application
from ...permissions.models import Permission, Principal
from ..dependencies import (
    correlation_id, get_application, get_principal, require_permission,
)
from ..schemas.common import ok, page
from ..schemas.knowledge import (
    CollectionCreateIn, CollectionUpdateIn, IndexFolderIn,
)

router = APIRouter(tags=["knowledge"])

READ = require_permission(Permission.READ_SYSTEM_DATA)
WRITE = require_permission(Permission.WRITE_SYSTEM_DATA)


def _svc(application: Application):
    return application.knowledge


# -------------------------------------------------------------- status
@router.get("/knowledge/status")
async def knowledge_status(request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(READ)):
    return ok(_svc(application).status(principal),
              correlation_id(request))


@router.get("/knowledge/formats")
async def knowledge_formats(request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(READ)):
    return ok(_svc(application).formats(principal),
              correlation_id(request))


# ---------------------------------------------------------- collections
@router.post("/knowledge/collections", status_code=201)
async def create_collection(body: CollectionCreateIn, request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(WRITE)):
    return ok(_svc(application).create_collection(
        principal, body.model_dump()), correlation_id(request))


@router.get("/knowledge/collections")
async def list_collections(request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(READ),
                           limit: int = Query(default=100, ge=1, le=500),
                           offset: int = Query(default=0, ge=0)):
    rows, total = _svc(application).list_collections(
        principal, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/knowledge/collections/{collection_id}")
async def get_collection(collection_id: str, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(READ)):
    return ok(_svc(application).get_collection(principal, collection_id),
              correlation_id(request))


@router.patch("/knowledge/collections/{collection_id}")
async def update_collection(collection_id: str, body: CollectionUpdateIn,
                            request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(WRITE)):
    patch = body.model_dump(exclude_unset=True)
    return ok(_svc(application).update_collection(
        principal, collection_id, patch), correlation_id(request))


@router.delete("/knowledge/collections/{collection_id}")
async def delete_collection(collection_id: str, request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(WRITE)):
    return ok(_svc(application).delete_collection(principal, collection_id),
              correlation_id(request))


# ------------------------------------------------------------ documents
@router.post("/knowledge/collections/{collection_id}/documents",
             status_code=201)
async def upload_document(collection_id: str, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(WRITE),
                          filename: str = Query(default="document")):
    data = await request.body()
    result = _svc(application).add_document(
        principal, collection_id, filename=filename,
        content_type=request.headers.get("content-type", ""), data=data)
    return ok(result, correlation_id(request))


@router.post("/knowledge/collections/{collection_id}/index-folder")
async def index_folder(collection_id: str, body: IndexFolderIn,
                       request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(WRITE)):
    return ok(_svc(application).index_folder(
        principal, collection_id, folder=body.folder),
        correlation_id(request))


@router.get("/knowledge/collections/{collection_id}/documents")
async def list_documents(collection_id: str, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(READ),
                         limit: int = Query(default=100, ge=1, le=500),
                         offset: int = Query(default=0, ge=0)):
    rows, total = _svc(application).list_documents(
        principal, collection_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/knowledge/documents/{document_id}")
async def get_document(document_id: str, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(READ),
                       q: str = Query(default="")):
    return ok(_svc(application).get_document(principal, document_id,
                                             query=q),
              correlation_id(request))


@router.get("/knowledge/documents/{document_id}/content")
async def document_content(document_id: str, request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(READ)):
    row, data = _svc(application).read_document_bytes(principal, document_id)
    return Response(content=data,
                    media_type=row["content_type"]
                    or "application/octet-stream")


@router.get("/knowledge/documents/{document_id}/compare/{other_id}")
async def compare_documents(document_id: str, other_id: str,
                            request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(READ)):
    return ok(_svc(application).compare(principal, document_id, other_id),
              correlation_id(request))


@router.delete("/knowledge/documents/{document_id}")
async def delete_document(document_id: str, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(WRITE)):
    return ok(_svc(application).delete_document(principal, document_id),
              correlation_id(request))


# --------------------------------------------------------------- search
@router.get("/knowledge/search")
async def search(request: Request,
                 application: Application = Depends(get_application),
                 principal: Principal = Depends(READ),
                 q: str = Query(min_length=1),
                 collection_id: str | None = Query(default=None),
                 limit: int = Query(default=20, ge=1, le=100)):
    return ok(_svc(application).search(
        principal, query=q, collection_id=collection_id, limit=limit),
        correlation_id(request))


@router.get("/knowledge/duplicates")
async def duplicates(request: Request,
                     application: Application = Depends(get_application),
                     principal: Principal = Depends(READ),
                     collection_id: str | None = Query(default=None)):
    return ok(_svc(application).duplicates(
        principal, collection_id=collection_id), correlation_id(request))
