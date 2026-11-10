"""Context manager (P-02): assembles the working context for ONE mission
from that mission's own rows only — mission text, its latest plan and
steps, and its decision records. Queries are strictly scoped by
mission_id, so context can never leak across missions."""
from __future__ import annotations

from ..core.exceptions import NotFoundError
from ..database.repositories.intelligence import (
    DecisionRecordRepository, MissionRepository, PlanRepository,
)
from ..permissions.models import Principal, PrincipalType


class ContextManager:
    def __init__(self, session_factory):
        self._session_factory = session_factory
        # P-14 Stage B (DEF-E2): P-09 MemoryService handle, attached
        # post-construction by the Application assembly (P-09 is built
        # after P-02). ``None`` → mission contexts omit memory with an
        # honest note instead of fabricating recall.
        self._memory = None

    def attach_memory(self, memory) -> None:
        self._memory = memory

    # Recall principal: SYSTEM reads only what the P-09 classification
    # policy allows it (policy.can_read applies to every record —
    # P-09's rules are NOT widened by context building).
    _RECALL_PRINCIPAL = Principal(PrincipalType.SYSTEM,
                                  "intelligence-context")

    def build_context(self, mission_id: str) -> dict:
        session = self._session_factory()
        try:
            mission = MissionRepository(session).get(mission_id)
            if mission is None:
                raise NotFoundError(f"mission {mission_id} not found")
            plan_repo = PlanRepository(session)
            plan = plan_repo.latest_for_mission(mission_id)
            decisions, _ = DecisionRecordRepository(session).list(
                mission_id=mission_id, limit=500)
            context = {
                "mission": {
                    "id": mission.id, "text": mission.text, "status": mission.status,
                    "mode": mission.mode, "matched_template": mission.matched_template,
                },
                "plan": None if plan is None else {
                    "id": plan.id, "version": plan.version, "planner": plan.planner,
                    "model_profile": plan.model_profile, "status": plan.status,
                    "steps": [
                        {"id": s.id, "order": s.order_index, "tool_name": s.tool_name,
                         "status": s.status, "task_id": s.task_id,
                         "verification_status": s.verification_status}
                        for s in plan_repo.steps_for(plan.id)
                    ],
                },
                "decisions": [
                    {"id": d.id, "type": d.decision_type, "actor": d.actor,
                     "reason": d.reason}
                    for d in decisions
                ],
            }
            context["memory"] = self._recall(mission)
            return context
        finally:
            session.close()

    def _recall(self, mission) -> dict:
        """P-09 retrieval scoped to this mission's text (DEF-E2).

        Recall is a live query against the governed retrieval
        service; classification rules stay enforced inside retrieval.
        Recall failure degrades to an honest empty result — context
        building never breaks because memory is unavailable.
        """
        if self._memory is None:
            return {"available": False, "records": [],
                    "note": ("P-09 memory service is not wired into "
                             "mission context building")}
        query = (mission.text or "").strip()
        if not query:
            return {"available": True, "records": [],
                    "note": "mission carries no text to recall by"}
        try:
            result = self._memory.retrieval.search(
                self._RECALL_PRINCIPAL, query=query, limit=5)
            records = [
                {"id": r["id"], "title": r["title"],
                 "layer": r["layer"], "category": r["category"],
                 "truth_class": r["truth_class"],
                 # P-09 rows carry full content, no summary field:
                 # the context summary is a bounded content excerpt.
                 "summary": (r.get("content") or "")[:200]}
                for r in result.get("results", [])]
            return {"available": True, "records": records,
                    "note": ("records retrieved through P-09 governed "
                             "retrieval; classification policy applied "
                             "to every record")}
        except Exception as exc:  # recall must never break a mission
            return {"available": False, "records": [],
                    "note": f"memory recall failed: {type(exc).__name__}"}
