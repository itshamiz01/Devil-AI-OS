"""Opportunity Discovery Engine service (P-03 §5, §20, §25, §26).

Orchestrates: briefs -> discovery -> screening -> research (as P-01
tasks through the registered ``opportunity.research`` handler) ->
evidence -> market/competitor/commercial analysis -> scoring ->
validation -> reports.

Governance posture, inherited from P-01/P-02 and never weakened here:
- Research executes ONLY as P-01 tasks via registered handlers.
- Fetched content is untrusted data: injection-scanned, quarantined on a
  hit, security-audited. It can never change scores, permissions or policy.
- Scoring weights are owner-governed configuration (ADR-005); this
  service reads them, and only the Owner principal may change them.
- Owner-grade evidence kinds (real-world / payment) can only be recorded
  by the Owner principal. The engine never creates them itself.
- Modes: emergency blocks research execution; simulation restricts
  research to seed/owner sources (no live fetching), mirroring P-02.
"""
from __future__ import annotations

import hashlib

from ..core.exceptions import (
    InvalidStateTransitionError, NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.base import utcnow
from ..database.models.core import AuditEvent
from ..database.models.intelligence import DecisionRecord
from ..database.models.opportunities import (
    CommercialAnalysis, Competitor, EvidenceRecord, MarketAnalysis, Opportunity,
    OpportunityHistory, OpportunityScore, ResearchBrief, ResearchSession,
    ResearchSource, ValidationRecord,
)
from ..database.repositories.core import AuditRepository, ConfigRepository
from ..database.repositories.intelligence import DecisionRecordRepository, MissionRepository
from ..database.repositories.opportunities import (
    BriefRepository, CommercialAnalysisRepository, CompetitorRepository,
    EvidenceRepository, HistoryRepository, MarketAnalysisRepository,
    OpportunityRepository, ResearchSessionRepository, ScoreRepository,
    SourceRepository, ValidationRepository,
)
from ..events.events import Event, EventType
from ..permissions.models import Principal, PrincipalType
from . import analysis as analysis_mod
from . import commercial as commercial_mod
from . import compliance as compliance_mod
from . import scoring as scoring_mod
from . import validation as validation_mod
from .constants import (
    CATEGORIES, INSUFFICIENT_EVIDENCE, SYSTEM_CAPABILITIES,
)
from .evidence import apply_corroboration, evidence_gaps, evidence_quality, freshness_for
from .lifecycle import can_transition, slugify_opportunity
from .schemas import capability_assessment
from .seed_data import CANDIDATES, SEED_DOCUMENTS, SEED_SOURCES
from .sources import AdapterRegistry, TransportError

RESEARCH_HANDLER = "opportunity.research"


def _actor(principal: Principal) -> str:
    return f"{principal.type.value}:{principal.id}"


def _dup_slug(base_slug: str) -> str:
    """A DUPLICATE row cannot reuse the unique slug it collided with; it
    stores a suffixed variant and records the base slug in its history."""
    import uuid
    return f"{base_slug}#dup-{uuid.uuid4().hex[:8]}"


class OpportunityService:
    def __init__(self, session_factory, bus, permissions, tasks, settings,
                 transport=None, recorder=None):
        self._session_factory = session_factory
        self._bus = bus
        self._permissions = permissions
        self._tasks = tasks
        self._settings = settings
        self._recorder = recorder  # P-02 DecisionRecorder (optional)
        if transport is None:
            from .sources import HttpTransport
            transport = HttpTransport(
                timeout_seconds=settings.research_http_timeout_seconds,
                proxy_url=settings.research_proxy_url,
                max_bytes=settings.research_max_fetch_bytes,
                allow_private_hosts=settings.research_allow_private_hosts)
        self.transport = transport
        self.adapters = AdapterRegistry(SEED_DOCUMENTS, transport, settings.mode)

    # -------------------------------------------------------------- seeding
    def seed_sources(self) -> int:
        session = self._session_factory()
        try:
            repo = SourceRepository(session)
            created = 0
            for spec in SEED_SOURCES:
                if repo.get_by_key(spec["source_key"]) is None:
                    repo.add(ResearchSource(**spec, rate_limit={"min_interval_seconds": 1}))
                    created += 1
            return created
        finally:
            session.close()

    def seed_scoring_config(self) -> None:
        session = self._session_factory()
        try:
            import json
            repo = ConfigRepository(session)
            if repo.get(scoring_mod.SCORING_CONFIG_KEY) is None:
                repo.set(scoring_mod.SCORING_CONFIG_KEY,
                         json.dumps({"version": scoring_mod.SCORING_V1_VERSION,
                                     "weights": scoring_mod.SCORING_V1_WEIGHTS}),
                         "P-03 opportunity scoring weights (ADR-005); owner-editable governance")
        finally:
            session.close()

    def scoring_config(self) -> dict:
        import json
        session = self._session_factory()
        try:
            row = ConfigRepository(session).get(scoring_mod.SCORING_CONFIG_KEY)
            if row and row.value:
                data = json.loads(row.value)
                weights = {**scoring_mod.SCORING_V1_WEIGHTS, **data.get("weights", {})}
                return {"version": data.get("version", scoring_mod.SCORING_V1_VERSION),
                        "weights": weights}
        finally:
            session.close()
        return {"version": scoring_mod.SCORING_V1_VERSION,
                "weights": dict(scoring_mod.SCORING_V1_WEIGHTS)}

    def update_scoring_weights(self, principal: Principal, weights: dict,
                               correlation_id: str | None = None) -> dict:
        """Owner-only governance (Article 0 pattern, cf. P-02 model
        profiles): scoring must never be tunable by an agent to favour an
        opportunity."""
        if principal.type != PrincipalType.OWNER:
            self._audit(principal, "opportunities.scoring_config_update", "system_config",
                        scoring_mod.SCORING_CONFIG_KEY, "deny",
                        "scoring weights are governance configuration; only the Owner may change them",
                        correlation_id)
            raise PermissionDeniedError(
                "scoring weights may only be changed by the Owner principal (ADR-005)",
                details={"config_key": scoring_mod.SCORING_CONFIG_KEY})
        unknown = set(weights) - set(scoring_mod.SCORING_V1_WEIGHTS)
        if unknown:
            raise ValidationError(f"unknown scoring dimensions: {sorted(unknown)}")
        merged = {**self.scoring_config()["weights"], **weights}
        total = sum(merged.values())
        if abs(total - 1.0) > 0.001:
            raise ValidationError(
                f"scoring weights must sum to 1.0 (got {round(total, 4)}); no change stored")
        import json
        session = self._session_factory()
        try:
            current = self.scoring_config()
            version = current["version"]
            base, _, suffix = version.partition("-v")
            n = int(suffix) + 1 if suffix.isdigit() else 2
            new_version = f"scoring-v{n}"
            ConfigRepository(session).set(
                scoring_mod.SCORING_CONFIG_KEY,
                json.dumps({"version": new_version, "weights": merged}),
                "P-03 opportunity scoring weights (ADR-005); owner-editable governance")
        finally:
            session.close()
        self._audit(principal, "opportunities.scoring_config_update", "system_config",
                    scoring_mod.SCORING_CONFIG_KEY, "allow",
                    f"scoring weights updated by owner; new version {new_version}", correlation_id)
        return {"version": new_version, "weights": merged}

    # -------------------------------------------------------------- helpers
    def _audit(self, principal, action, target_type, target_id, decision, reason,
               correlation_id=None, details=None) -> None:
        session = self._session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value if principal else "system",
                actor_id=principal.id if principal else "opportunity-engine",
                action=action, target_type=target_type, target_id=target_id,
                decision=decision, reason=reason, correlation_id=correlation_id,
                details=details or {}, created_at=utcnow()))
        finally:
            session.close()

    def _history(self, session, opportunity_id, event_type, actor, reason,
                 from_status=None, to_status=None, details=None) -> None:
        HistoryRepository(session).add(OpportunityHistory(
            opportunity_id=opportunity_id, event_type=event_type,
            from_status=from_status, to_status=to_status, actor=actor,
            reason=reason, details=details or {}))

    async def _publish(self, event_type, payload, correlation_id=None, severity="info"):
        if self._bus is not None:
            await self._bus.publish(Event(
                event_type=event_type, source="opportunities.service",
                payload=payload, correlation_id=correlation_id, severity=severity))

    def _record_decision(self, decision_type, actor, reason, mission_id=None,
                         evidence=None, correlation_id=None) -> None:
        if mission_id:
            if self._recorder is not None:
                self._recorder.record(decision_type, actor=actor, reason=reason,
                                      mission_id=mission_id, evidence=evidence or {},
                                      correlation_id=correlation_id)
                return
            session = self._session_factory()
            try:
                DecisionRecordRepository(session).add(DecisionRecord(
                    mission_id=mission_id, decision_type=decision_type, actor=actor,
                    reason=reason, evidence=evidence or {}, correlation_id=correlation_id))
            finally:
                session.close()

    # --------------------------------------------------------------- briefs
    def create_brief(self, principal: Principal, data: dict,
                     correlation_id: str | None = None) -> ResearchBrief:
        session = self._session_factory()
        try:
            mission_id = data.get("mission_id")
            if mission_id and MissionRepository(session).get(mission_id) is None:
                raise NotFoundError(f"mission {mission_id} not found")
            categories = [c for c in (data.get("categories") or []) if c in CATEGORIES]
            brief = BriefRepository(session).add(ResearchBrief(
                title=data["title"], objective=data["objective"],
                budget_amount=data.get("budget_amount"),
                # P-14 Stage B (DEF-D1): keep the integer minor-unit
                # column in step with the deprecated Float column.
                budget_minor=(None if data.get("budget_amount") is None
                              else int(round(float(data["budget_amount"]) * 100))),
                currency=(data.get("currency") or "USD").upper(),
                geography=data.get("geography") or "global",
                categories=categories,
                constraints=data.get("constraints") or {},
                creator_type=principal.type.value, creator_id=principal.id,
                mission_id=mission_id, status="open", correlation_id=correlation_id))
            return brief
        finally:
            session.close()

    def list_briefs(self, status=None, limit=50, offset=0):
        session = self._session_factory()
        try:
            return BriefRepository(session).list(status, limit, offset)
        finally:
            session.close()

    def get_brief(self, brief_id: str) -> ResearchBrief:
        session = self._session_factory()
        try:
            brief = BriefRepository(session).get(brief_id)
            if brief is None:
                raise NotFoundError(f"research brief {brief_id} not found")
            return brief
        finally:
            session.close()

    # ------------------------------------------------------------ discovery
    async def discover(self, principal: Principal, brief_id: str,
                       correlation_id: str | None = None) -> dict:
        """Stage 4 discovery + initial screening (§5, §7, §17).

        Candidates come from the seed candidate library (hypotheses, L0).
        Screening applies, in order: duplicate detection, compliance
        (prohibited -> BLOCKED_BY_COMPLIANCE), budget class vs the owner's
        budget (-> INCOMPATIBLE). Nothing here consults a market."""
        brief = self.get_brief(brief_id)
        session = self._session_factory()
        created: list[Opportunity] = []
        try:
            repo = OpportunityRepository(session)
            for candidate in CANDIDATES:
                if brief.categories and candidate["category"] not in brief.categories:
                    continue
                if brief.geography not in ("global", "") \
                        and candidate["geography"] not in ("global", brief.geography):
                    continue
                slug = slugify_opportunity(candidate["name"], candidate["category"],
                                           candidate["geography"])
                fit = capability_assessment(candidate.get("required_capabilities", []),
                                            SYSTEM_CAPABILITIES)
                fit["physical_inventory"] = bool(candidate.get("physical_inventory"))
                fit["candidate_source_keys"] = candidate.get("source_keys", [])
                fit["startup_class_usd"] = candidate.get("startup_class_usd")
                fit["startup_class_basis"] = (
                    "internal rough estimate class used ONLY for budget screening; "
                    "not a researched price (§19)")
                existing = repo.get_by_slug(slug)
                compliance_preview = compliance_mod.screen(type("C", (), candidate)())
                opp = Opportunity(
                    name=candidate["name"],
                    slug=slug if existing is None else _dup_slug(slug),

                    description=candidate["description"], category=candidate["category"],
                    target_customer=candidate["target_customer"],
                    geography=candidate["geography"],
                    problem_statement=candidate["problem_statement"],
                    proposed_solution=candidate["proposed_solution"],
                    revenue_model=candidate["revenue_model"],
                    discovery_method=candidate["discovery_method"],
                    status="DISCOVERED", validation_level=0,
                    brief_id=brief.id, mission_id=brief.mission_id,
                    capability_fit=fit, compliance=compliance_preview)
                if existing is not None:
                    opp.status = "DUPLICATE"
                    opp.duplicate_of_id = existing.id
                    opp = repo.add(opp)
                    self._history(session, opp.id, "duplicate_detected", _actor(principal),
                                  "same normalised name+category+geography as an existing opportunity",
                                  to_status="DUPLICATE",
                                  details={"duplicate_of_id": existing.id})
                    created.append(opp)
                    continue
                opp = repo.add(opp)
                self._history(session, opp.id, "discovered", _actor(principal),
                              f"candidate generated by {candidate['discovery_method']} discovery "
                              "from the seed candidate library (hypothesis, validation level 0)",
                              to_status="DISCOVERED")
                # INITIAL_SCREENING
                self._transition_in_session(session, opp, "INITIAL_SCREENING", _actor(principal),
                                            "automatic initial screening on discovery")
                if compliance_preview["verdict"] == "prohibited":
                    self._transition_in_session(
                        session, opp, "BLOCKED_BY_COMPLIANCE", _actor(principal),
                        "compliance screening matched prohibited rule(s): "
                        f"{[r['rule'] for r in compliance_preview['matched_rules']]}")
                elif brief.budget_amount is not None \
                        and candidate.get("startup_class_usd") is not None \
                        and float(candidate["startup_class_usd"]) > float(brief.budget_amount):
                    self._transition_in_session(
                        session, opp, "INCOMPATIBLE", _actor(principal),
                        f"estimated minimum launch class ${candidate['startup_class_usd']} "
                        f"exceeds the owner's budget ${brief.budget_amount}; the budget is "
                        "not raised (§13.6)")
                created.append(opp)
            brief_row = BriefRepository(session).get(brief.id)
            brief_row.status = "completed"
            BriefRepository(session).save(brief_row)
        finally:
            session.close()
        for opp in created:
            await self._publish(EventType.OPPORTUNITY_DISCOVERED,
                                {"opportunity_id": opp.id, "status": opp.status,
                                 "category": opp.category}, correlation_id)
        self._record_decision(
            "opportunity_discovery", actor="opportunity-engine",
            reason=f"discovery for brief '{brief.title}' produced {len(created)} candidate "
                   "record(s); all are hypotheses at validation level 0 until evidence exists",
            mission_id=brief.mission_id, correlation_id=correlation_id,
            evidence={"brief_id": brief.id, "created": len(created)})
        return {"brief": brief, "opportunities": created}

    def create_opportunity(self, principal: Principal, data: dict,
                           correlation_id: str | None = None) -> Opportunity:
        session = self._session_factory()
        try:
            repo = OpportunityRepository(session)
            slug = slugify_opportunity(data["name"], data["category"],
                                       data.get("geography") or "global")
            fit = capability_assessment(data.get("required_capabilities", []), SYSTEM_CAPABILITIES)
            fit["candidate_source_keys"] = data.get("source_keys", [])
            existing = repo.get_by_slug(slug)
            opp = Opportunity(
                name=data["name"], slug=slug if existing is None else _dup_slug(slug),
                description=data.get("description", ""),
                category=data["category"], target_customer=data.get("target_customer", ""),
                geography=data.get("geography") or "global",
                problem_statement=data.get("problem_statement", ""),
                proposed_solution=data.get("proposed_solution", ""),
                revenue_model=data.get("revenue_model", ""),
                discovery_method="manual", status="DISCOVERED", validation_level=0,
                brief_id=data.get("brief_id"), mission_id=data.get("mission_id"),
                capability_fit=fit)
            opp.compliance = compliance_mod.screen(opp)
            if existing is not None:
                opp.status = "DUPLICATE"
                opp.duplicate_of_id = existing.id
            opp = repo.add(opp)
            self._history(session, opp.id, "discovered", _actor(principal),
                          "manually recorded opportunity (hypothesis, validation level 0)",
                          to_status=opp.status)
            if opp.status == "DISCOVERED":
                self._transition_in_session(session, opp, "INITIAL_SCREENING", _actor(principal),
                                            "initial screening on manual creation")
                if opp.compliance.get("verdict") == "prohibited":
                    self._transition_in_session(
                        session, opp, "BLOCKED_BY_COMPLIANCE", _actor(principal),
                        "compliance screening matched prohibited rule(s): "
                        f"{[r['rule'] for r in opp.compliance['matched_rules']]}")
            return opp
        finally:
            session.close()

    def get_opportunity(self, opportunity_id: str) -> Opportunity:
        session = self._session_factory()
        try:
            opp = OpportunityRepository(session).get(opportunity_id)
            if opp is None:
                raise NotFoundError(f"opportunity {opportunity_id} not found")
            return opp
        finally:
            session.close()

    def list_opportunities(self, status=None, category=None, geography=None,
                           brief_id=None, limit=50, offset=0):
        session = self._session_factory()
        try:
            return OpportunityRepository(session).list(
                status, category, geography, brief_id, limit, offset)
        finally:
            session.close()

    # ------------------------------------------------------------- lifecycle
    def _transition_in_session(self, session, opp: Opportunity, target: str,
                               actor: str, reason: str) -> Opportunity:
        if not can_transition(opp.status, target):
            raise InvalidStateTransitionError(
                f"invalid opportunity transition {opp.status} -> {target}",
                details={"opportunity_id": opp.id, "from": opp.status, "to": target})
        previous = opp.status
        opp.status = target
        OpportunityRepository(session).save(opp)
        self._history(session, opp.id, "status_changed", actor, reason,
                      from_status=previous, to_status=target)
        return opp

    async def transition(self, principal: Principal, opportunity_id: str, target: str,
                         reason: str = "", correlation_id: str | None = None) -> Opportunity:
        opp = self.get_opportunity(opportunity_id)
        if target == "RECOMMENDED":
            session = self._session_factory()
            try:
                latest = ScoreRepository(session).latest_for(opportunity_id)
            finally:
                session.close()
            if opp.validation_level < 3:
                raise InvalidStateTransitionError(
                    "RECOMMENDED requires validation level >= 3 (commercially assessed); "
                    f"current level is {opp.validation_level}",
                    details={"opportunity_id": opportunity_id,
                             "validation_level": opp.validation_level})
            if latest is None or latest.hard_rejection:
                raise InvalidStateTransitionError(
                    "RECOMMENDED requires a current score with no hard rejection",
                    details={"opportunity_id": opportunity_id})
            if (opp.compliance or {}).get("verdict") == "prohibited":
                raise InvalidStateTransitionError(
                    "a prohibited opportunity can never be RECOMMENDED",
                    details={"opportunity_id": opportunity_id})
        session = self._session_factory()
        try:
            row = OpportunityRepository(session).get(opportunity_id)
            self._transition_in_session(session, row, target, _actor(principal),
                                        reason or f"manual transition requested by {_actor(principal)}")
            result = OpportunityRepository(session).get(opportunity_id)
        finally:
            session.close()
        await self._publish(EventType.OPPORTUNITY_STATUS_CHANGED,
                            {"opportunity_id": opportunity_id, "to": target},
                            correlation_id)
        return result

    # -------------------------------------------------------------- research
    async def start_research(self, principal: Principal, opportunity_id: str,
                             source_keys: list[str] | None = None,
                             objective: str = "",
                             correlation_id: str | None = None) -> ResearchSession:
        """Creates a research session and submits it as a P-01 task. The
        task executes only the registered ``opportunity.research`` handler."""
        if self._settings.mode == "emergency":
            self._audit(principal, "opportunities.research_blocked", "opportunity",
                        opportunity_id, "deny",
                        "operating mode is 'emergency': research execution is blocked",
                        correlation_id)
            raise InvalidStateTransitionError(
                "research execution is blocked in 'emergency' mode",
                details={"opportunity_id": opportunity_id, "mode": "emergency"})
        opp = self.get_opportunity(opportunity_id)
        if opp.status in ("BLOCKED_BY_COMPLIANCE", "DUPLICATE", "ARCHIVED", "REJECTED"):
            raise InvalidStateTransitionError(
                f"opportunity in status {opp.status} cannot be researched",
                details={"opportunity_id": opportunity_id, "status": opp.status})
        keys = source_keys or (opp.capability_fit or {}).get("candidate_source_keys") or []
        session = self._session_factory()
        try:
            sources = SourceRepository(session).list(enabled_only=True)
            by_key = {s.source_key: s for s in sources}
            unknown = [k for k in keys if k not in by_key]
            if unknown:
                raise ValidationError(
                    f"unknown or disabled research sources: {unknown}. "
                    "Only registered, enabled sources may be used (§8).")
            research = ResearchSessionRepository(session).add(ResearchSession(
                opportunity_id=opportunity_id,
                objective=objective or "Collect evidence from registered sources",
                stage="collect_evidence", status="pending",
                sources_examined=[{"source_key": k, "status": "pending"} for k in keys]))
            if opp.status in ("INITIAL_SCREENING", "DISCOVERED", "NEEDS_MORE_EVIDENCE", "OUTDATED"):
                row = OpportunityRepository(session).get(opportunity_id)
                if row.status == "DISCOVERED":
                    self._transition_in_session(session, row, "INITIAL_SCREENING",
                                                _actor(principal),
                                                "initial screening before research")
                self._transition_in_session(session, row, "RESEARCHING", _actor(principal),
                                            "research session started")
            research_id = research.id
        finally:
            session.close()
        task = await self._tasks.submit(
            principal, name=f"Research: {opp.name}", handler_name=RESEARCH_HANDLER,
            payload={"session_id": research_id}, category="research",
            description=f"Evidence collection for opportunity {opportunity_id}",
            timeout_seconds=120.0, idempotency_key=f"research:{research_id}",
            correlation_id=correlation_id)
        session = self._session_factory()
        try:
            row = ResearchSessionRepository(session).get(research_id)
            row.task_id = task.id
            ResearchSessionRepository(session).save(row)
            return row
        finally:
            session.close()

    def get_research_session(self, session_id: str) -> ResearchSession:
        session = self._session_factory()
        try:
            row = ResearchSessionRepository(session).get(session_id)
            if row is None:
                raise NotFoundError(f"research session {session_id} not found")
            return row
        finally:
            session.close()

    def list_research_sessions(self, opportunity_id: str, limit=50, offset=0):
        session = self._session_factory()
        try:
            return ResearchSessionRepository(session).list_for(opportunity_id, limit, offset)
        finally:
            session.close()

    async def run_research_stage(self, session_id: str) -> dict:
        """Executed BY the P-01 task worker (handler closure). Collects
        evidence for one session from its registered sources. Returns a
        summary dict stored as the task result."""
        session = self._session_factory()
        try:
            srepo = ResearchSessionRepository(session)
            research = srepo.get(session_id)
            if research is None:
                return {"ok": False, "error": f"research session {session_id} not found"}
            opp = OpportunityRepository(session).get(research.opportunity_id)
            research.status = "running"
            research.started_at = utcnow()
            srepo.save(research)
            source_keys = [e["source_key"] for e in (research.sources_examined or [])]
            examined: list[dict] = []
            new_evidence = 0
            quarantined = 0
            for key in source_keys:
                source = SourceRepository(session).get_by_key(key)
                if source is None or not source.enabled:
                    examined.append({"source_key": key, "status": "skipped",
                                     "reason": "source not registered or disabled"})
                    continue
                outcome = await self._collect_from_source(session, opp, source)
                examined.append({"source_key": key, **outcome})
                new_evidence += outcome.get("evidence_added", 0)
                quarantined += 1 if outcome.get("quarantined") else 0
            # Corroboration / contradiction pass over ALL stored evidence.
            ev_repo = EvidenceRepository(session)
            records, _ = ev_repo.list_for(opp.id, limit=1000)
            reliability = {}
            for s in SourceRepository(session).list():
                reliability[s.id] = s.reliability_classification
            changes = apply_corroboration(records, reliability)
            for change in changes:
                ev_repo.save(next(r for r in records if r.id == change["evidence_id"]))
            if changes:
                self._history(session, opp.id, "evidence_reclassified", "opportunity-engine",
                              "corroboration/contradiction pass updated evidence classifications",
                              details={"changes": changes})
            records, _ = ev_repo.list_for(opp.id, limit=1000)
            gaps = evidence_gaps(
                records,
                has_commercial=CommercialAnalysisRepository(session).latest_for(opp.id) is not None,
                competitor_count=len(CompetitorRepository(session).list_for(opp.id)))
            research.sources_examined = examined
            research.status = "completed"
            research.completed_at = utcnow()
            research.findings_summary = (
                f"{new_evidence} new evidence record(s) from {len(examined)} source(s); "
                f"{quarantined} document(s) quarantined; "
                f"{len(changes)} classification change(s). "
                f"Outstanding gaps: {'; '.join(gaps) if gaps else 'none recorded'}")
            srepo.save(research)
            opp_row = OpportunityRepository(session).get(opp.id)
            opp_row.last_researched_at = utcnow()
            OpportunityRepository(session).save(opp_row)
            if opp_row.status == "RESEARCHING":
                self._transition_in_session(session, opp_row, "EVIDENCE_REVIEW",
                                            "opportunity-engine",
                                            "research session completed; evidence ready for review")
            result = {"ok": True, "session_id": session_id, "opportunity_id": opp.id,
                      "evidence_added": new_evidence, "quarantined": quarantined,
                      "classification_changes": len(changes),
                      "sources_examined": examined}
        finally:
            session.close()
        await self._publish(EventType.RESEARCH_COMPLETED,
                            {"session_id": session_id, "opportunity_id": result["opportunity_id"],
                             "evidence_added": result["evidence_added"]})
        return result

    async def _collect_from_source(self, session, opp: Opportunity,
                                   source: ResearchSource) -> dict:
        """Fetch documents from one source and extract evidence. Content is
        untrusted: injection scan first; a hit quarantines the document
        (zero claims extracted) and writes a security audit record."""
        from ..intelligence.service import detect_injection

        try:
            adapter = self.adapters.for_source(source)
            documents = await adapter.fetch_documents(source, opp)
        except TransportError as exc:
            return {"status": "unavailable", "reason": str(exc), "evidence_added": 0}
        added = 0
        quarantined = False
        notes: list[str] = []
        ev_repo = EvidenceRepository(session)
        existing, _ = ev_repo.list_for(opp.id, limit=1000)
        existing_keys = {
            hashlib.sha256(f"{e.source_id}|{e.topic_key}|{e.claim}".encode()).hexdigest()
            for e in existing}
        for doc in documents:
            patterns = detect_injection(doc.text or "")
            if patterns:
                quarantined = True
                AuditRepository(session).add(AuditEvent(
                    actor_type="system", actor_id="opportunity-engine",
                    action="opportunities.injection_detected", target_type="research_source",
                    target_id=source.source_key, decision="deny",
                    reason=("prompt-injection patterns detected in content from source "
                            f"'{source.source_key}'; the document was quarantined as "
                            "untrusted data and NO claims were extracted from it (§27)"),
                    details={"patterns": patterns, "opportunity_id": opp.id,
                             "document_title": doc.title},
                    created_at=utcnow()))
                self._history(session, opp.id, "injection_quarantined", "opportunity-engine",
                              f"document '{doc.title}' from {source.source_key} quarantined: "
                              f"injection patterns {patterns}",
                              details={"source_key": source.source_key})
                await self._publish(EventType.PROMPT_INJECTION_DETECTED,
                                    {"opportunity_id": opp.id, "source_key": source.source_key,
                                     "patterns": patterns}, severity="error")
                notes.append(f"document '{doc.title}' quarantined (injection)")
                continue
            claims = list(doc.seed_claims)
            if doc.extraction_method in ("web_page", "rss"):
                from .sources import extract_price_mentions
                ceiling = "SUPPORTING" if source.reliability_classification in (
                    "primary_official", "government_regulatory") else "UNVERIFIED"
                for mention in extract_price_mentions(doc.text):
                    claims.append({
                        "claim": (f"{source.name} page states a price of "
                                  f"{mention['currency']} {mention['amount']}"
                                  f"{' per month' if mention['per_month'] else ''} "
                                  f"(verbatim: \"{mention['verbatim']}\")."),
                        "category": "pricing",
                        "topic_key": f"price-mention:{source.source_key}:{mention['currency']}:{mention['amount']}:{mention['per_month']}",
                        "classification": ceiling,
                        "supporting_content": mention["snippet"],
                    })
            for claim in claims:
                dedup = hashlib.sha256(
                    f"{source.id}|{claim.get('topic_key', '')}|{claim['claim']}".encode()).hexdigest()
                if dedup in existing_keys:
                    continue
                existing_keys.add(dedup)
                ev_repo.add(EvidenceRecord(
                    opportunity_id=opp.id, source_id=source.id,
                    claim=claim["claim"],
                    supporting_content=claim.get("supporting_content", doc.text[:500]),
                    category=claim.get("category", "demand"),
                    classification=claim.get("classification", "UNVERIFIED"),
                    evidence_kind="source_claim",
                    topic_key=claim.get("topic_key", ""),
                    independence_group=source.independence_group,
                    source_url=doc.url, retrieval_timestamp=utcnow(),
                    publication_date=doc.publication_date,
                    extraction_method=doc.extraction_method,
                    freshness_status=freshness_for(doc.publication_date),
                    recorded_by="opportunity-engine"))
                added += 1
        return {"status": "fetched", "documents": len(documents),
                "evidence_added": added, "quarantined": quarantined, "notes": notes}

    # -------------------------------------------------------------- evidence
    def add_evidence(self, principal: Principal, opportunity_id: str, data: dict,
                     correlation_id: str | None = None) -> EvidenceRecord:
        """Manual evidence recording. Owner-grade kinds are owner-only;
        an agent can never manufacture Level 4/5 evidence (§18)."""
        kind = data.get("evidence_kind", "source_claim")
        if kind in ("owner_real_world", "owner_payment") and principal.type != PrincipalType.OWNER:
            self._audit(principal, "opportunities.owner_evidence_denied", "opportunity",
                        opportunity_id, "deny",
                        f"evidence kind '{kind}' may only be recorded by the Owner principal",
                        correlation_id)
            raise PermissionDeniedError(
                f"evidence kind '{kind}' may only be recorded by the Owner principal (§18)",
                details={"evidence_kind": kind})
        classification = data.get("classification", "UNVERIFIED")
        if kind == "source_claim" and classification == "VERIFIED" \
                and principal.type != PrincipalType.OWNER:
            raise PermissionDeniedError(
                "a non-owner cannot record a VERIFIED source claim",
                details={"classification": classification})
        opp = self.get_opportunity(opportunity_id)
        session = self._session_factory()
        try:
            source = None
            if data.get("source_id"):
                source = SourceRepository(session).get(data["source_id"])
                if source is None:
                    raise NotFoundError(f"research source {data['source_id']} not found")
            record = EvidenceRepository(session).add(EvidenceRecord(
                opportunity_id=opp.id, source_id=source.id if source else None,
                claim=data["claim"], supporting_content=data.get("supporting_content", ""),
                category=data.get("category", "demand"), classification=classification,
                evidence_kind=kind, topic_key=data.get("topic_key", ""),
                independence_group=(source.independence_group if source
                                    else data.get("independence_group", "owner" if kind != "source_claim" else "")),
                source_url=data.get("source_url") or (source.url if source else None),
                retrieval_timestamp=utcnow(), publication_date=data.get("publication_date"),
                extraction_method="manual", freshness_status=freshness_for(data.get("publication_date")),
                recorded_by=_actor(principal)))
            self._history(session, opp.id, "evidence_added", _actor(principal),
                          f"evidence recorded manually (kind={kind}, classification={classification})",
                          details={"evidence_id": record.id, "category": record.category})
            return record
        finally:
            session.close()

    def list_evidence(self, opportunity_id: str, limit=200, offset=0):
        session = self._session_factory()
        try:
            return EvidenceRepository(session).list_for(opportunity_id, limit, offset)
        finally:
            session.close()

    # ------------------------------------------------------------ competitors
    def add_competitor(self, principal: Principal, opportunity_id: str,
                       data: dict) -> Competitor:
        opp = self.get_opportunity(opportunity_id)
        session = self._session_factory()
        try:
            if data.get("pricing_evidence_id"):
                evidence = EvidenceRepository(session).get(data["pricing_evidence_id"])
                if evidence is None or evidence.opportunity_id != opp.id:
                    raise ValidationError(
                        "pricing_evidence_id must reference an evidence record of this opportunity; "
                        "competitor prices are never recorded without evidence (§11.2)")
            competitor = CompetitorRepository(session).add(Competitor(
                opportunity_id=opp.id, name=data["name"], website=data.get("website"),
                product=data.get("product", ""), competitor_type=data.get("competitor_type", "direct"),
                pricing_claim=data.get("pricing_claim"),
                pricing_evidence_id=data.get("pricing_evidence_id"),
                features=data.get("features", []), strengths=data.get("strengths", []),
                weaknesses=data.get("weaknesses", []), positioning=data.get("positioning", "")))
            self._history(session, opp.id, "competitor_recorded", _actor(principal),
                          f"competitor '{competitor.name}' recorded",
                          details={"competitor_id": competitor.id})
            return competitor
        finally:
            session.close()

    def list_competitors(self, opportunity_id: str):
        session = self._session_factory()
        try:
            return CompetitorRepository(session).list_for(opportunity_id)
        finally:
            session.close()

    # -------------------------------------------------------------- analyses
    def _context(self, session, opportunity_id: str) -> dict:
        opp = OpportunityRepository(session).get(opportunity_id)
        if opp is None:
            raise NotFoundError(f"opportunity {opportunity_id} not found")
        records, _ = EvidenceRepository(session).list_for(opportunity_id, limit=1000)
        competitors = CompetitorRepository(session).list_for(opportunity_id)
        market = MarketAnalysisRepository(session).latest_for(opportunity_id)
        commercial = CommercialAnalysisRepository(session).latest_for(opportunity_id)
        return {"opportunity": opp, "records": records, "competitors": competitors,
                "market": market, "commercial": commercial,
                "capability_fit": opp.capability_fit or {},
                "compliance": opp.compliance or {}}

    def run_market_analysis(self, principal: Principal, opportunity_id: str,
                            correlation_id: str | None = None) -> MarketAnalysis:
        session = self._session_factory()
        try:
            ctx = self._context(session, opportunity_id)
            built = analysis_mod.build_market_analysis(
                ctx["opportunity"], ctx["records"], ctx["competitors"])
            row = MarketAnalysisRepository(session).add(MarketAnalysis(
                opportunity_id=opportunity_id,
                customer_segment=built["customer_segment"],
                geographic_market=built["geographic_market"],
                problem_analysis=built["problem_analysis"],
                demand_indicators=built["demand_indicators"],
                market_size=built["market_size"], saturation=built["saturation"],
                gaps=evidence_gaps(ctx["records"], has_commercial=bool(ctx["commercial"]),
                                   competitor_count=len(ctx["competitors"])),
                inputs_snapshot={"evidence_records": len(ctx["records"]),
                                 "competitors": len(ctx["competitors"])}))
            self._history(session, row.opportunity_id, "market_analysis", _actor(principal),
                          f"market analysis recorded; demand stage={built['demand_indicators']['stage']}, "
                          f"saturation={built['saturation']['level']}",
                          details={"analysis_id": row.id})
            return row
        finally:
            session.close()

    def run_competitor_analysis(self, principal: Principal, opportunity_id: str) -> dict:
        session = self._session_factory()
        try:
            ctx = self._context(session, opportunity_id)
            built = analysis_mod.build_competitor_analysis(ctx["opportunity"], ctx["competitors"])
            self._history(session, opportunity_id, "competitor_analysis", _actor(principal),
                          f"competitor analysis over {len(ctx['competitors'])} recorded competitor(s)",
                          details={"gaps": len(built["identified_gaps"])})
            return built
        finally:
            session.close()

    async def run_commercial_analysis(self, principal: Principal, opportunity_id: str,
                                      data: dict, correlation_id: str | None = None) -> CommercialAnalysis:
        session = self._session_factory()
        try:
            ctx = self._context(session, opportunity_id)
            opp = ctx["opportunity"]
            brief = BriefRepository(session).get(opp.brief_id) if opp.brief_id else None
            budget_amount = data.get("budget_amount")
            if budget_amount is None and brief is not None:
                budget_amount = brief.budget_amount
            computed = commercial_mod.compute_commercial(
                startup_costs=data.get("startup_costs", []),
                recurring_costs_monthly=data.get("recurring_costs_monthly", []),
                variable_costs_per_sale=data.get("variable_costs_per_sale", []),
                price=data.get("price"),
                platform_fee_pct=data.get("platform_fee_pct", 0.0),
                payment_fee_pct=data.get("payment_fee_pct", 0.0),
                scenario_sales=data.get("scenario_sales"),
                budget_amount=budget_amount)
            distribution = analysis_mod.build_distribution_analysis(
                opp, ctx["records"], data.get("proposed_channels"))
            row = CommercialAnalysisRepository(session).add(CommercialAnalysis(
                opportunity_id=opportunity_id,
                revenue_model=opp.revenue_model, currency=(data.get("currency")
                                                           or (brief.currency if brief else "USD")),
                startup_costs=computed["startup_costs"],
                recurring_costs_monthly=computed["recurring_costs_monthly"],
                variable_costs_per_sale=computed["variable_costs_per_sale"],
                price_assumption=computed["price_assumption"],
                scenarios=computed["scenarios"], break_even=computed["break_even"],
                budget=computed["budget"], distribution=distribution,
                inputs_snapshot={"totals": computed["totals"],
                                 "scenario_notes": computed["scenario_notes"],
                                 "budget_source": ("request" if data.get("budget_amount") is not None
                                                   else "research_brief" if brief else "none")}))
            self._history(session, opportunity_id, "commercial_analysis", _actor(principal),
                          "commercial analysis recorded (deterministic calculations over stated inputs)",
                          details={"analysis_id": row.id,
                                   "budget_compatible": computed["budget"]["compatible"]})
            if opp.status == "EVIDENCE_REVIEW":
                row_opp = OpportunityRepository(session).get(opportunity_id)
                self._transition_in_session(session, row_opp, "COMMERCIAL_ANALYSIS",
                                            _actor(principal), "commercial analysis performed")
            return row
        finally:
            session.close()

    # --------------------------------------------------------------- scoring
    async def score(self, principal: Principal, opportunity_id: str,
                    correlation_id: str | None = None) -> OpportunityScore:
        config = self.scoring_config()
        session = self._session_factory()
        try:
            ctx = self._context(session, opportunity_id)
            opp = ctx["opportunity"]
            dimensions, reasons = scoring_mod.derive_dimensions(ctx)
            rejection = scoring_mod.hard_rejection(ctx)
            eq, breakdown = evidence_quality(ctx["records"])
            weighted = scoring_mod.weighted_total(dimensions, config["weights"])
            recommendation = scoring_mod.recommendation_for(
                weighted, eq, rejection, opp.validation_level,
                bool((opp.compliance or {}).get("requires_professional_review")))
            row = ScoreRepository(session).add(OpportunityScore(
                opportunity_id=opportunity_id, scoring_version=config["version"],
                dimensions=dimensions, dimension_reasons=reasons,
                weights=config["weights"], weighted_score=weighted,
                evidence_quality=eq,
                risk_classification=scoring_mod.risk_classification(ctx, eq, rejection),
                hard_rejection=rejection, recommendation=recommendation,
                inputs_snapshot={"evidence_records": len(ctx["records"]),
                                 "evidence_breakdown": breakdown,
                                 "competitors": len(ctx["competitors"]),
                                 "has_market_analysis": ctx["market"] is not None,
                                 "has_commercial_analysis": ctx["commercial"] is not None}))
            self._history(session, opportunity_id, "scored", _actor(principal),
                          f"scored {weighted}/5 with {config['version']}; evidence quality "
                          f"{eq}/5 reported separately; recommendation: {recommendation}",
                          details={"score_id": row.id, "hard_rejection": rejection})
            if rejection:
                target = {"prohibited_category": "BLOCKED_BY_COMPLIANCE",
                          "impossible_budget": "INCOMPATIBLE"}.get(rejection["rule"], "REJECTED")
                if opp.status not in (target, "ARCHIVED") and can_transition(opp.status, target):
                    self._transition_in_session(session, opp, target, "opportunity-engine",
                                                f"hard rejection rule: {rejection['rule']}")
                self._audit(principal, "opportunities.hard_rejection", "opportunity",
                            opportunity_id, "deny",
                            f"hard rejection ({rejection['rule']}): {rejection['reason']}",
                            correlation_id, details={"score_id": row.id})
                await self._publish(EventType.OPPORTUNITY_HARD_REJECTED,
                                    {"opportunity_id": opportunity_id,
                                     "rule": rejection["rule"]}, correlation_id, severity="error")
            elif opp.status == "COMMERCIAL_ANALYSIS":
                self._transition_in_session(session, opp, "VALIDATION_PENDING",
                                            "opportunity-engine",
                                            "scoring complete without hard rejection")
            result = ScoreRepository(session).get(row.id)
            mission_id = opp.mission_id
        finally:
            session.close()
        self._record_decision(
            "opportunity_scored", actor="opportunity-engine",
            reason=f"opportunity scored {result.weighted_score}/5 ({result.scoring_version}); "
                   f"evidence quality {result.evidence_quality}/5; "
                   f"recommendation {result.recommendation}"
                   + (f"; HARD REJECTED: {result.hard_rejection['rule']}" if result.hard_rejection else ""),
            mission_id=mission_id, correlation_id=correlation_id,
            evidence={"opportunity_id": opportunity_id, "score_id": result.id})
        await self._publish(EventType.OPPORTUNITY_SCORED,
                            {"opportunity_id": opportunity_id,
                             "weighted_score": result.weighted_score,
                             "evidence_quality": result.evidence_quality},
                            correlation_id)
        return result

    def latest_score(self, opportunity_id: str) -> OpportunityScore | None:
        session = self._session_factory()
        try:
            return ScoreRepository(session).latest_for(opportunity_id)
        finally:
            session.close()

    def rankings(self, by: str = "overall", limit: int = 50) -> list[dict]:
        session = self._session_factory()
        try:
            latest = ScoreRepository(session).latest_scores()
            rows = []
            for opp_id, score in latest.items():
                opp = OpportunityRepository(session).get(opp_id)
                if opp is None:
                    continue
                commercial = CommercialAnalysisRepository(session).latest_for(opp_id)
                rows.append({
                    "opportunity_id": opp_id, "name": opp.name, "status": opp.status,
                    "validation_level": opp.validation_level,
                    "weighted_score": score.weighted_score,
                    "evidence_quality": score.evidence_quality,
                    "recommendation": score.recommendation,
                    "scoring_version": score.scoring_version,
                    "hard_rejection": score.hard_rejection,
                    "verified_demand": (score.dimensions or {}).get("verified_demand"),
                    "profit_potential": (score.dimensions or {}).get("profit_potential"),
                    "operational_simplicity": (score.dimensions or {}).get("operational_simplicity"),
                    "minimum_viable_cost": (commercial.budget or {}).get("minimum_viable_cost")
                    if commercial else None,
                })
            keys = {
                "overall": lambda r: -(r["weighted_score"] or 0),
                "strongest_demand": lambda r: -(r["verified_demand"] or 0),
                "highest_margin": lambda r: -(r["profit_potential"] or 0),
                "simplest": lambda r: -(r["operational_simplicity"] or 0),
                "lowest_cost": lambda r: (r["minimum_viable_cost"] is None,
                                          r["minimum_viable_cost"] or 0),
            }
            rows.sort(key=keys.get(by, keys["overall"]))
            return rows[:limit]
        finally:
            session.close()

    # ------------------------------------------------------------ validation
    async def validate(self, principal: Principal, opportunity_id: str,
                       claimed_level: int | None = None,
                       correlation_id: str | None = None) -> ValidationRecord:
        session = self._session_factory()
        try:
            ctx = self._context(session, opportunity_id)
            opp = ctx["opportunity"]
            sessions, _ = ResearchSessionRepository(session).list_for(opportunity_id, limit=200)
            vctx = {
                "records": ctx["records"],
                "sessions_completed": any(s.status == "completed" for s in sessions),
                "has_market": ctx["market"] is not None,
                "competitor_count": len(ctx["competitors"]),
                "commercial": ctx["commercial"],
            }
            level, met, missing = validation_mod.assess_level(
                vctx, reviewer_is_owner=principal.type == PrincipalType.OWNER)
            if claimed_level is not None and claimed_level > level:
                raise ValidationError(
                    f"validation level {claimed_level} is not supported by the stored "
                    f"evidence; the highest justified level is {level}. "
                    f"Missing: {'; '.join(missing)}",
                    details={"opportunity_id": opportunity_id, "justified_level": level,
                             "missing": missing})
            record = ValidationRepository(session).add(ValidationRecord(
                opportunity_id=opportunity_id, level=level, criteria_met=met,
                criteria_missing=missing,
                evidence_ids=[r.id for r in ctx["records"]],
                reviewer=_actor(principal),
                decision=f"level {level} ({validation_mod.LEVEL_NAMES[level]})",
                notes="Level computed deterministically from stored evidence (§18)."))
            if level != opp.validation_level:
                opp.validation_level = level
                OpportunityRepository(session).save(opp)
            self._history(session, opportunity_id, "validated", _actor(principal),
                          f"validation assessed at level {level} "
                          f"({validation_mod.LEVEL_NAMES[level]})",
                          details={"validation_id": record.id, "missing": missing})
            if level >= 2 and opp.status == "VALIDATION_PENDING":
                self._transition_in_session(session, opp, "VALIDATED", "opportunity-engine",
                                            f"validation level {level} meets the VALIDATED bar (>= 2)")
            result = ValidationRepository(session).get(record.id)
            mission_id = opp.mission_id
        finally:
            session.close()
        self._record_decision(
            "opportunity_validated", actor="opportunity-engine",
            reason=f"validation level assessed as {result.level} "
                   f"({validation_mod.LEVEL_NAMES[result.level]}) from stored evidence",
            mission_id=mission_id, correlation_id=correlation_id,
            evidence={"opportunity_id": opportunity_id, "missing": result.criteria_missing})
        await self._publish(EventType.OPPORTUNITY_VALIDATED,
                            {"opportunity_id": opportunity_id, "level": result.level},
                            correlation_id)
        return result

    def latest_validation(self, opportunity_id: str) -> ValidationRecord | None:
        session = self._session_factory()
        try:
            return ValidationRepository(session).latest_for(opportunity_id)
        finally:
            session.close()

    # ------------------------------------------------------------- reporting
    def report(self, opportunity_id: str) -> dict:
        """§23 structured report. Facts (evidence), estimates (analyses
        over stated inputs) and recommendations are kept in separate
        fields; gaps use the mandated insufficiency language."""
        session = self._session_factory()
        try:
            ctx = self._context(session, opportunity_id)
            opp = ctx["opportunity"]
            records = ctx["records"]
            score = ScoreRepository(session).latest_for(opportunity_id)
            validation = ValidationRepository(session).latest_for(opportunity_id)
            sessions, _ = ResearchSessionRepository(session).list_for(opportunity_id, limit=200)
            eq, breakdown = evidence_quality(records)
            gaps = evidence_gaps(records, has_commercial=bool(ctx["commercial"]),
                                 competitor_count=len(ctx["competitors"]))
            facts = [{
                "claim": r.claim, "category": r.category, "classification": r.classification,
                "evidence_kind": r.evidence_kind, "source_url": r.source_url,
                "retrieved_at": r.retrieval_timestamp.isoformat() if r.retrieval_timestamp else None,
                "freshness": r.freshness_status,
            } for r in records]
            market = ctx["market"]
            commercial = ctx["commercial"]
            return {
                "opportunity": {
                    "id": opp.id, "name": opp.name, "category": opp.category,
                    "target_customer": opp.target_customer, "geography": opp.geography,
                    "problem": opp.problem_statement, "proposed_solution": opp.proposed_solution,
                    "revenue_model": opp.revenue_model, "status": opp.status,
                    "discovery_method": opp.discovery_method,
                },
                "executive_summary": {
                    "overall_score": score.weighted_score if score else None,
                    "evidence_quality": eq,
                    "validation_level": opp.validation_level,
                    "recommendation": score.recommendation if score else "NOT SCORED",
                    "hard_rejection": score.hard_rejection if score else None,
                },
                "facts_from_evidence": facts,
                "evidence_breakdown": breakdown,
                "market_research": ({
                    "customer_segment": market.customer_segment,
                    "demand_indicators": market.demand_indicators,
                    "market_size": market.market_size,
                    "saturation": market.saturation,
                } if market else {"note": f"{INSUFFICIENT_EVIDENCE}: no market analysis has been run."}),
                "competitor_analysis": analysis_mod.build_competitor_analysis(opp, ctx["competitors"]),
                "commercial_feasibility": ({
                    "price_assumption": commercial.price_assumption,
                    "scenarios": commercial.scenarios,
                    "break_even": commercial.break_even,
                    "budget": commercial.budget,
                    "distribution": commercial.distribution,
                    "estimate_notice": ("All figures are deterministic calculations over "
                                        "caller-stated inputs classified per line "
                                        "(verified/quoted/historical/estimate/unknown). "
                                        "Estimated revenue is not verified revenue (§13.3)."),
                } if commercial else {"note": f"{INSUFFICIENT_EVIDENCE}: no commercial analysis has been run."}),
                "compliance": opp.compliance or {},
                "validation_assessment": ({
                    "level": validation.level, "decision": validation.decision,
                    "criteria_met": validation.criteria_met,
                    "criteria_missing": validation.criteria_missing,
                } if validation else {"level": opp.validation_level,
                                      "note": "no validation assessment has been run"}),
                "evidence_gaps": gaps,
                "research_sessions": [{
                    "id": s.id, "status": s.status, "task_id": s.task_id,
                    "findings_summary": s.findings_summary,
                } for s in sessions],
                "recommended_next_step": self._next_step(opp, score, gaps),
            }
        finally:
            session.close()

    @staticmethod
    def _next_step(opp: Opportunity, score, gaps: list[str]) -> str:
        if opp.status == "BLOCKED_BY_COMPLIANCE":
            return "Reject permanently: the model matches a prohibited category (§15)."
        if opp.status == "INCOMPATIBLE":
            return "Reject or re-scope: the model does not fit the owner's stated budget."
        if score and score.recommendation == "STRONG CANDIDATE":
            return "Submit for owner review; consider a small, pre-declared, owner-approved demand experiment (future phase)."
        if gaps:
            return "Gather more evidence: " + gaps[0]
        return "Continue the research pipeline (market/commercial analysis, scoring, validation)."

    # ------------------------------------------------------------- monitoring
    def engine_status(self) -> dict:
        session = self._session_factory()
        try:
            counts = OpportunityRepository(session).count_by_status()
            sources = SourceRepository(session).list()
            config = self.scoring_config()
            return {
                "opportunities_by_status": counts,
                "total_opportunities": sum(counts.values()),
                "sources_registered": len(sources),
                "sources_enabled": sum(1 for s in sources if s.enabled),
                "scoring_version": config["version"],
                "mode": self._settings.mode,
                "live_fetching": ("disabled in simulation mode"
                                  if self._settings.mode == "simulation"
                                  else "enabled for registered public sources only"),
            }
        finally:
            session.close()

    def research_queue(self) -> list[dict]:
        session = self._session_factory()
        try:
            pending = ResearchSessionRepository(session).pending()
            out = []
            for s in pending:
                task_status = None
                if s.task_id:
                    task = self._tasks.get(s.task_id) if self._tasks else None
                    task_status = task.status if task else None
                out.append({"session_id": s.id, "opportunity_id": s.opportunity_id,
                            "stage": s.stage, "status": s.status, "task_id": s.task_id,
                            "task_status": task_status,
                            "note": s.findings_summary or None})
            return out
        finally:
            session.close()

    def schedule_recheck(self, principal: Principal, opportunity_id: str,
                         note: str = "") -> ResearchSession:
        """§24 foundation: registers a pending recheck session (duplicate-
        prevented). It does NOT auto-execute — recurring operations are
        P-12 scope; the owner triggers research explicitly."""
        self.get_opportunity(opportunity_id)
        session = self._session_factory()
        try:
            repo = ResearchSessionRepository(session)
            for existing in repo.pending():
                if existing.opportunity_id == opportunity_id and existing.stage == "recheck":
                    return existing
            row = repo.add(ResearchSession(
                opportunity_id=opportunity_id,
                objective=note or "Scheduled recheck of stored evidence freshness",
                stage="recheck", status="pending",
                sources_examined=[],
                findings_summary="recheck registered; execution requires an explicit research run (P-12 will own scheduling)"))
            self._history(session, opportunity_id, "recheck_scheduled", _actor(principal),
                          "freshness recheck registered (foundation for §24 monitoring)",
                          details={"session_id": row.id})
            return row
        finally:
            session.close()

    # ---------------------------------------------------------------- sources
    def list_sources(self):
        session = self._session_factory()
        try:
            return SourceRepository(session).list()
        finally:
            session.close()

    def create_source(self, principal: Principal, data: dict) -> ResearchSource:
        session = self._session_factory()
        try:
            repo = SourceRepository(session)
            if repo.get_by_key(data["source_key"]) is not None:
                raise ValidationError(f"source_key '{data['source_key']}' is already registered")
            source = repo.add(ResearchSource(
                source_key=data["source_key"], name=data["name"], url=data.get("url"),
                source_type=data.get("source_type", "public_website"),
                access_method=data.get("access_method", "web_page"),
                auth_required=bool(data.get("auth_required", False)),
                rate_limit=data.get("rate_limit", {}),
                reliability_classification=data.get("reliability_classification", "unverified_claim"),
                usage_restrictions=data.get("usage_restrictions", ""),
                independence_group=data.get("independence_group", data["source_key"]),
                origin="owner", enabled=True))
            self._audit(principal, "opportunities.source_registered", "research_source",
                        source.source_key, "allow", "research source registered by an authorised principal")
            return source
        finally:
            session.close()

    async def fetch_source(self, source_id: str) -> dict:
        """Fetch ONE registered source through its adapter and report what
        happened (no evidence is created here — extraction happens inside
        governed research sessions). Demonstrates adapter behaviour and the
        injection scan on demand."""
        from ..intelligence.service import detect_injection

        session = self._session_factory()
        try:
            source = SourceRepository(session).get(source_id)
            if source is None:
                source = SourceRepository(session).get_by_key(source_id)
            if source is None:
                raise NotFoundError(f"research source {source_id} not found")
            source_snapshot = source
        finally:
            session.close()
        probe = Opportunity(name="__probe__", slug="__probe__", category="digital_products")
        try:
            adapter = self.adapters.for_source(source_snapshot)
            documents = await adapter.fetch_documents(source_snapshot, probe)
        except TransportError as exc:
            return {"source_key": source_snapshot.source_key, "status": "unavailable",
                    "reason": str(exc), "documents": []}
        out_docs = []
        for doc in documents:
            patterns = detect_injection(doc.text or "")
            out_docs.append({
                "title": doc.title, "url": doc.url, "status_code": doc.status_code,
                "extraction_method": doc.extraction_method,
                "text_preview": (doc.text or "")[:300],
                "injection_patterns_detected": patterns,
                "seed_claims": len(doc.seed_claims),
            })
            if patterns:
                self._audit(None, "opportunities.injection_detected", "research_source",
                            source_snapshot.source_key, "deny",
                            "injection patterns detected during a manual source fetch; "
                            "content treated as untrusted data only (§27)",
                            details={"patterns": patterns})
        return {"source_key": source_snapshot.source_key, "status": "fetched",
                "documents": out_docs}

    def history(self, opportunity_id: str, limit=200, offset=0):
        session = self._session_factory()
        try:
            return HistoryRepository(session).list_for(opportunity_id, limit, offset)
        finally:
            session.close()
