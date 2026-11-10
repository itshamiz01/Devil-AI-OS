"""Memory and Continuous Learning API (P-09, §20).

Route map under /api/v1/memory (adapted from §20 to house style):
- engine: status, settings (owner-governed writes), analytics,
  maintenance scan, review queue
- records: create/list/get/patch, supersede, verify (owner),
  delete (owner, receipt-verified), sources, history
- ingestion: ingest candidate, jobs
- retrieval: search, context package
- contradictions: list, resolve (owner)
- graph: entities, relationships, traversal
- consolidation
- learning: analyze, list/get, observe, review (owner),
  from-experiment / from-decision (P-08 references), financial
  reference check (P-07 by reference only)
- agents: memory profile (via the completed P-04 interface),
  handoffs create/list
- owner: preferences get/set, audit trail, export

Permissions mirror P-07/P-08: read = read_business_data,
write = modify_business_data, approve/owner actions =
approve_actions at the route layer AND owner-principal checks in
the service (verify/delete/export/settings remain owner-only even
for other approve-holders). There is deliberately NO route that
lets memory write owner instructions, permissions or limits.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...permissions.models import Permission
from ..dependencies import correlation_id, get_application, require_permission
from ..schemas import memory as S
from ..schemas.common import ok, page

router = APIRouter(prefix="/memory", tags=["memory"])

READ = require_permission(Permission.READ_BUSINESS_DATA)
WRITE = require_permission(Permission.MODIFY_BUSINESS_DATA)
APPROVE = require_permission(Permission.APPROVE_ACTIONS)


def _svc(request: Request):
    return get_application(request).memory


# ------------------------------------------------------------------ engine
@router.get("/status")
async def status(request: Request, principal=Depends(READ)):
    return ok(_svc(request).status(), correlation_id(request))


@router.get("/settings")
async def get_settings(request: Request, principal=Depends(READ)):
    return ok(_svc(request).get_settings(), correlation_id(request))


@router.patch("/settings")
async def update_settings(request: Request, body: S.SettingsUpdateIn,
                          principal=Depends(APPROVE)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return ok(_svc(request).update_settings(principal, patch),
              correlation_id(request))


@router.get("/analytics/overview")
async def analytics(request: Request, principal=Depends(READ)):
    return ok(_svc(request).analytics(), correlation_id(request))


@router.post("/maintenance/scan")
async def maintenance_scan(request: Request, principal=Depends(WRITE)):
    return ok(_svc(request).knowledge.maintenance_scan(principal),
              correlation_id(request))


@router.get("/review/required")
async def review_required(request: Request, principal=Depends(READ),
                          status: str | None = "OPEN"):
    return ok(_svc(request).knowledge.review_tasks(status=status),
              correlation_id(request))


# ----------------------------------------------------------------- records
@router.post("")
async def create_record(request: Request, body: S.MemoryCreateIn,
                        principal=Depends(WRITE)):
    svc = _svc(request)
    record = svc.store.create(principal, body.model_dump())
    svc.knowledge.detect_contradictions(record["id"])
    return ok(record, correlation_id(request))


@router.get("")
async def list_records(request: Request, principal=Depends(READ),
                       limit: int = Query(50, ge=1, le=200),
                       offset: int = Query(0, ge=0),
                       layer: str | None = None, category: str | None = None,
                       status: str | None = None, business_id: str | None = None,
                       agent_id: str | None = None):
    filters = {k: v for k, v in {
        "layer": layer, "category": category, "status": status,
        "business_id": business_id, "agent_id": agent_id}.items() if v}
    rows, total = _svc(request).store.list(
        principal, limit=limit, offset=offset, filters=filters or None)
    return page(rows, total, limit, offset, correlation_id(request))


# --------------------------------------------------------------- ingestion
@router.post("/ingest")
async def ingest(request: Request, body: S.IngestIn, principal=Depends(WRITE)):
    svc = _svc(request)
    result = svc.ingestion.ingest(principal, body.model_dump())
    if result.get("memory_id"):
        svc.knowledge.detect_contradictions(result["memory_id"])
    return ok(result, correlation_id(request))


@router.get("/ingestion/jobs")
async def ingestion_jobs(request: Request, principal=Depends(READ),
                         limit: int = Query(50, ge=1, le=200),
                         offset: int = Query(0, ge=0),
                         status: str | None = None):
    rows, total = _svc(request).ingestion.jobs(
        limit=limit, offset=offset, status=status)
    return page(rows, total, limit, offset, correlation_id(request))


# --------------------------------------------------------------- retrieval
@router.post("/search")
async def search(request: Request, body: S.SearchIn, principal=Depends(READ)):
    return ok(_svc(request).retrieval.search(
        principal, query=body.query, categories=body.categories,
        business_id=body.business_id, project_ref=body.project_ref,
        agent_id=body.agent_id, since=body.since, until=body.until,
        include_history=body.include_history, limit=body.limit),
        correlation_id(request))


@router.post("/retrieve")
async def retrieve_context(request: Request, body: S.ContextIn,
                           principal=Depends(READ)):
    return ok(_svc(request).retrieval.build_context(
        principal, task=body.task, business_id=body.business_id,
        project_ref=body.project_ref, agent_id=body.agent_id,
        categories=body.categories), correlation_id(request))


# ----------------------------------------------------------- contradictions
@router.get("/contradictions/list")
async def contradictions(request: Request, principal=Depends(READ),
                         status: str | None = "OPEN"):
    return ok(_svc(request).knowledge.contradictions(status=status),
              correlation_id(request))


@router.post("/contradictions/{contradiction_id}/resolve")
async def resolve_contradiction(request: Request, contradiction_id: str,
                                body: S.ResolveContradictionIn,
                                principal=Depends(APPROVE)):
    return ok(_svc(request).knowledge.resolve_contradiction(
        principal, contradiction_id, resolution=body.resolution,
        supersede_id=body.supersede_id), correlation_id(request))


# -------------------------------------------------------------------- graph
@router.post("/entities")
async def upsert_entity(request: Request, body: S.EntityIn,
                        principal=Depends(WRITE)):
    return ok(_svc(request).knowledge.upsert_entity(principal, body.model_dump()),
              correlation_id(request))


@router.post("/relationships")
async def relate(request: Request, body: S.RelateIn, principal=Depends(WRITE)):
    return ok(_svc(request).knowledge.relate(principal, body.model_dump()),
              correlation_id(request))


@router.get("/entities/{entity_id}/traverse")
async def traverse(request: Request, entity_id: str, principal=Depends(READ),
                   depth: int = Query(2, ge=1, le=4)):
    return ok(_svc(request).knowledge.traverse(entity_id, depth=depth),
              correlation_id(request))


# -------------------------------------------------------------- consolidation
@router.post("/consolidate")
async def consolidate(request: Request, body: S.ConsolidateIn,
                      principal=Depends(WRITE)):
    return ok(_svc(request).knowledge.consolidate(
        principal, title=body.title, memory_ids=body.memory_ids,
        business_id=body.business_id), correlation_id(request))


# ----------------------------------------------------------------- learning
@router.post("/learning/analyze")
async def learning_analyze(request: Request, body: S.LearningIn,
                           principal=Depends(WRITE)):
    data = body.model_dump()
    if data.get("confidence") is None:
        data.pop("confidence", None)
    return ok(_svc(request).learning.analyze(principal, data),
              correlation_id(request))


@router.get("/learning")
async def learning_list(request: Request, principal=Depends(READ),
                        limit: int = Query(50, ge=1, le=200),
                        offset: int = Query(0, ge=0),
                        business_id: str | None = None):
    rows, total = _svc(request).learning.list(
        principal, limit=limit, offset=offset, business_id=business_id)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/learning/{learning_id}")
async def learning_get(request: Request, learning_id: str,
                       principal=Depends(READ)):
    return ok(_svc(request).learning.get(principal, learning_id),
              correlation_id(request))


@router.post("/learning/{learning_id}/observe")
async def learning_observe(request: Request, learning_id: str,
                           principal=Depends(WRITE)):
    return ok(_svc(request).learning.add_observation(principal, learning_id),
              correlation_id(request))


@router.post("/learning/{learning_id}/review")
async def learning_review(request: Request, learning_id: str,
                          principal=Depends(APPROVE)):
    return ok(_svc(request).learning.review(principal, learning_id),
              correlation_id(request))


@router.post("/learning/from-experiment/{experiment_id}")
async def learning_from_experiment(request: Request, experiment_id: str,
                                   body: S.LearningFromIn,
                                   principal=Depends(WRITE)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return ok(_svc(request).learning.from_experiment(
        principal, experiment_id, data), correlation_id(request))


@router.post("/learning/from-decision/{decision_id}")
async def learning_from_decision(request: Request, decision_id: str,
                                 body: S.LearningFromIn,
                                 principal=Depends(WRITE)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return ok(_svc(request).learning.from_decision(
        principal, decision_id, data), correlation_id(request))


@router.get("/learning/financial-reference/{ref}")
async def financial_reference(request: Request, ref: str,
                              principal=Depends(READ)):
    return ok(_svc(request).learning.financial_reference(principal, ref),
              correlation_id(request))


# ------------------------------------------------------------------- agents
@router.get("/agents/{agent_id}")
async def agent_memory(request: Request, agent_id: str,
                       principal=Depends(READ), scope: str = "approved_contextual_memory"):
    application = get_application(request)
    return ok(application.agents.memory.read(
        requester=principal, agent_id=agent_id, scope=scope),
        correlation_id(request))


@router.post("/agents/{agent_id}/handoff")
async def create_handoff(request: Request, agent_id: str, body: S.HandoffIn,
                         principal=Depends(WRITE)):
    data = body.model_dump()
    data["from_agent_id"] = agent_id
    return ok(_svc(request).knowledge.create_handoff(principal, data),
              correlation_id(request))


@router.get("/agents/{agent_id}/handoffs")
async def list_handoffs(request: Request, agent_id: str,
                        principal=Depends(READ)):
    return ok(_svc(request).knowledge.handoffs_for(principal, agent_id),
              correlation_id(request))


# -------------------------------------------------------------------- owner
@router.get("/owner/preferences")
async def owner_preferences(request: Request, principal=Depends(READ)):
    return ok(_svc(request).preferences(), correlation_id(request))


@router.patch("/owner/preferences/{key}")
async def set_preference(request: Request, key: str, body: S.PreferenceIn,
                         principal=Depends(WRITE)):
    return ok(_svc(request).set_preference(
        principal, key, body.value, kind=body.kind), correlation_id(request))


@router.get("/owner/audit")
async def owner_audit(request: Request, principal=Depends(READ),
                      limit: int = Query(50, ge=1, le=200)):
    return ok(_svc(request).owner_audit(limit=limit), correlation_id(request))


@router.post("/owner/export")
async def owner_export(request: Request, principal=Depends(APPROVE),
                       business_id: str | None = None):
    return ok(_svc(request).export(principal, business_id=business_id),
              correlation_id(request))


# ------------------------------------------- single-record routes (LAST:
# /{memory_id} must never shadow fixed paths like /learning or /owner)
@router.get("/{memory_id}")
async def get_record(request: Request, memory_id: str, principal=Depends(READ)):
    return ok(_svc(request).store.get(principal, memory_id),
              correlation_id(request))


@router.patch("/{memory_id}")
async def update_record(request: Request, memory_id: str,
                        body: S.MemoryUpdateIn, principal=Depends(WRITE)):
    patch = {k: v for k, v in body.model_dump().items()
             if v is not None and k != "reason"}
    return ok(_svc(request).store.update(
        principal, memory_id, patch, reason=body.reason),
        correlation_id(request))


@router.post("/{memory_id}/supersede")
async def supersede_record(request: Request, memory_id: str,
                           body: S.SupersedeIn, principal=Depends(WRITE)):
    return ok(_svc(request).store.supersede(
        principal, memory_id, body.record.model_dump(), reason=body.reason),
        correlation_id(request))


@router.post("/{memory_id}/verify")
async def verify_record(request: Request, memory_id: str, body: S.VerifyIn,
                        principal=Depends(APPROVE)):
    return ok(_svc(request).store.verify(
        principal, memory_id, evidence_refs=body.evidence_refs),
        correlation_id(request))


@router.delete("/{memory_id}")
async def delete_record(request: Request, memory_id: str,
                        principal=Depends(APPROVE)):
    return ok(_svc(request).store.delete(principal, memory_id),
              correlation_id(request))


@router.get("/{memory_id}/sources")
async def record_sources(request: Request, memory_id: str,
                         principal=Depends(READ)):
    return ok(_svc(request).store.sources(memory_id), correlation_id(request))


@router.get("/{memory_id}/history")
async def record_history(request: Request, memory_id: str,
                         principal=Depends(READ)):
    _svc(request).store.get(principal, memory_id)  # access check
    return ok(_svc(request).store.history(memory_id), correlation_id(request))


