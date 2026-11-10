"""Intelligence mixin (§6/§7/§12): cross-business opportunity
detection, portfolio recommendations, the evidence gate,
concentration analysis and portfolio risk assessment.

Deterministic detectors only — no LLM invents synergies. Every
detector cites system evidence (P-06 channels, P-07/P-08 figures,
P-09 shared memory, P-13 service/relationship state). The evidence
gate is mechanical: an opportunity or recommendation whose evidence
does not cite a trusted system source is rejected by the engine's
own rules (§21 Scenario 6), and speculative items are labelled
SPECULATIVE and can never be accepted as verified fact.
"""
from __future__ import annotations

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.portfolio import (
    CrossBusinessOpportunity, PortfolioRecommendation,
    PortfolioRiskAssessment,
)
from ..database.repositories.portfolio import (
    OpportunityRepository, RecommendationRepository,
    RiskAssessmentRepository, ServiceAccessRepository,
    SharedServiceRepository,
)
from ..permissions.models import Principal, PrincipalType
from ..events.events import Event, EventType
from . import constants as C
from .constants import actor_of


def opportunity_dict(row: CrossBusinessOpportunity) -> dict:
    evaluation = row.evaluation or {}
    return {
        "id": row.id, "portfolio_id": row.portfolio_id,
        "category": row.category,
        "involved_business_ids": row.business_ids,
        "business_ids": row.business_ids,
        "title": row.title, "description": row.description,
        "evidence": row.evidence, "evidence_status": row.evidence_status,
        "expected_benefits": evaluation.get("expected_benefits", []),
        "estimated_costs": evaluation.get("estimated_costs", []),
        "risks": evaluation.get("risks", []),
        "resource_requirements": evaluation.get(
            "resource_requirements", {}),
        "confidence": row.confidence, "status": row.status,
        "detector": row.origin, "origin": row.origin,
        "created_by": row.created_by,
        "decided_by": row.decided_by,
        "decision_rationale": row.decision_note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def recommendation_dict(row: PortfolioRecommendation) -> dict:
    implications = row.financial_implications or {}
    return {
        "id": row.id, "portfolio_id": row.portfolio_id,
        "kind": row.kind, "title": row.title,
        "rationale": implications.get("rationale", ""),
        "affected_business_ids": row.affected_business_ids,
        "evidence": row.evidence,
        "evidence_status": row.evidence_status,
        "assumptions": row.assumptions, "confidence": row.confidence,
        "expected_impact": row.expected_benefit,
        "risks": row.risks,
        "approval_requirements": row.approval_requirements,
        "status": row.status, "origin": row.origin,
        "created_by": row.created_by,
        "decided_by": row.decided_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def validate_evidence(principal: Principal, evidence) -> str:
    """The §6 evidence gate. Returns VERIFIED or SPECULATIVE.

    Raises ValidationError when the evidence cites no trusted system
    source — an unsupported synergy claim is rejected outright, not
    stored and labelled (§21 Scenario 6). Owner attestations count
    only when the owner actually made them.
    """
    if not isinstance(evidence, list) or not evidence:
        raise ValidationError(
            "evidence is required: every portfolio claim must cite "
            "system evidence (a trusted source) or an explicit owner "
            "attestation")
    verified = False
    for item in evidence:
        if not isinstance(item, dict) or "source" not in item:
            raise ValidationError(
                "each evidence item must name its source")
        source = str(item["source"])
        if source not in C.TRUSTED_EVIDENCE_SOURCES:
            raise ValidationError(
                f"untrusted evidence source {source!r}: synergy and "
                "portfolio claims must cite system evidence "
                f"({sorted(C.TRUSTED_EVIDENCE_SOURCES)})")
        if source == "owner.attestation" and \
                principal.type != PrincipalType.OWNER:
            raise ValidationError(
                "only the owner can supply an owner attestation")
        if not item.get("speculative"):
            verified = True
    return "VERIFIED" if verified else "SPECULATIVE"


class IntelligenceMixin:
    # --------------------------------------------------- submissions
    def submit_opportunity(self, principal: Principal, portfolio_id: str,
                           data: dict) -> dict:
        """An opportunity proposed from outside the detectors (owner,
        agent, another engine). The evidence gate applies to all."""
        self._portfolio_or_404(portfolio_id)
        category = str(data.get("category") or "")
        if category not in C.OPPORTUNITY_CATEGORIES:
            raise ValidationError(f"unknown opportunity category: {category}")
        involved = list(data.get("involved_business_ids")
                        or data.get("business_ids") or [])
        if len(involved) < 2:
            raise ValidationError(
                "a cross-business opportunity involves at least two "
                "businesses")
        for business_id in involved:
            self._business_or_404(business_id)
        evidence_status = validate_evidence(principal, data.get("evidence"))
        confidence = str(data.get("confidence") or "low")
        if confidence not in C.CONFIDENCE_LEVELS:
            raise ValidationError(f"unknown confidence level: {confidence}")
        session = self._session_factory()
        try:
            row = OpportunityRepository(session).add(CrossBusinessOpportunity(
                portfolio_id=portfolio_id, category=category,
                business_ids=involved,
                title=str(data.get("title") or "")[:300],
                description=str(data.get("description") or ""),
                evidence=list(data.get("evidence") or []),
                evidence_status=evidence_status,
                evaluation={
                    "expected_benefits": list(
                        data.get("expected_benefits") or []),
                    "estimated_costs": list(
                        data.get("estimated_costs") or []),
                    "risks": list(data.get("risks") or []),
                    "resource_requirements": dict(
                        data.get("resource_requirements") or {}),
                },
                confidence=confidence, origin="external",
                created_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.opportunity_submitted",
                    "cross_business_opportunity", row.id, "allow",
                    "opportunity submitted through the evidence gate",
                    {"evidence_status": evidence_status})
        return opportunity_dict(row)

    def decide_opportunity(self, principal: Principal, opportunity_id: str,
                           decision: str, rationale: str = "") -> dict:
        self._require_owner(principal, "portfolio.opportunity_decide")
        if decision not in C.OPPORTUNITY_STATUSES - {"PROPOSED"}:
            raise ValidationError(f"unknown opportunity decision: {decision}")
        session = self._session_factory()
        try:
            repo = OpportunityRepository(session)
            row = repo.get(opportunity_id)
            if row is None:
                raise NotFoundError(
                    f"opportunity {opportunity_id} not found")
            if row.status != "PROPOSED":
                raise ValidationError(
                    f"opportunity is already {row.status}")
            if row.evidence_status == "SPECULATIVE" and decision in (
                    "VALIDATED", "ACCEPTED"):
                raise ValidationError(
                    "speculative opportunities cannot be validated or "
                    "accepted: speculative synergy is never presented "
                    "as verified (§6/§25 rule 12)")
            row.status = decision
            row.decided_by = actor_of(principal)
            row.decision_note = str(rationale or "")
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.opportunity_decided",
                    "cross_business_opportunity", opportunity_id, "allow",
                    f"opportunity {decision}", {"rationale": rationale})
        return opportunity_dict(row)

    def list_opportunities(self, principal: Principal, portfolio_id: str,
                           *, status: str | None = None) -> dict:
        self._require_portfolio_reader(principal, "portfolio.opportunities")
        session = self._session_factory()
        try:
            rows, _total = OpportunityRepository(session).list(
                limit=200, portfolio_id=portfolio_id, status=status)
            items = [opportunity_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": len(items)}

    def decide_recommendation(self, principal: Principal,
                              recommendation_id: str, decision: str,
                              rationale: str = "") -> dict:
        self._require_owner(principal, "portfolio.recommendation_decide")
        if decision not in ("ACCEPTED", "REJECTED", "DISMISSED"):
            raise ValidationError(
                f"unknown recommendation decision: {decision}")
        session = self._session_factory()
        try:
            repo = RecommendationRepository(session)
            row = repo.get(recommendation_id)
            if row is None:
                raise NotFoundError(
                    f"recommendation {recommendation_id} not found")
            if row.status != "PROPOSED":
                raise ValidationError(
                    f"recommendation is already {row.status}")
            if row.evidence_status == "SPECULATIVE" and \
                    decision == "ACCEPTED":
                raise ValidationError(
                    "a speculative recommendation cannot be accepted "
                    "as verified fact (§6)")
            row.status = decision
            row.decided_by = actor_of(principal)
            row.decision_note = str(rationale or "")
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.recommendation_decided",
                    "portfolio_recommendation", recommendation_id, "allow",
                    f"recommendation {decision}", {"rationale": rationale})
        return recommendation_dict(row)

    def list_recommendations(self, principal: Principal, portfolio_id: str,
                             *, status: str | None = None) -> dict:
        self._require_portfolio_reader(principal,
                                       "portfolio.recommendations")
        session = self._session_factory()
        try:
            rows, _total = RecommendationRepository(session).list(
                limit=200, portfolio_id=portfolio_id, status=status)
            items = [recommendation_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": len(items)}

    # ------------------------------------------------------ analysis
    def analyze_portfolio(self, principal: Principal,
                          portfolio_id: str) -> dict:
        """Run the deterministic detectors over a portfolio and
        persist only NEW findings (signature-deduped, so re-running
        analysis never spams duplicates). Owner/system only."""
        self._require_portfolio_reader(principal, "portfolio.analyze")
        portfolio = self._portfolio_or_404(portfolio_id)
        members = [m for m in self.list_members(principal, portfolio_id)
                   ["items"] if m["status"] != "REMOVED"]
        member_ids = [m["business_id"] for m in members]
        businesses = {bid: self._business_or_404(bid)
                      for bid in member_ids}
        summaries = {m["business_id"]: m["business"] for m in members}

        found_opportunities: list[dict] = []
        found_recommendations: list[dict] = []

        def opportunity(category, involved, title, description,
                        evidence, detector, benefits=None):
            found_opportunities.append({
                "category": category, "involved": sorted(set(involved)),
                "title": title, "description": description,
                "evidence": evidence, "detector": detector,
                "benefits": benefits or [],
                "signature": f"{detector}:{category}:"
                             f"{','.join(sorted(set(involved)))}"})

        def recommendation(kind, title, rationale, evidence, detector,
                           confidence="moderate", affected=None):
            found_recommendations.append({
                "kind": kind, "title": title, "rationale": rationale,
                "evidence": evidence, "detector": detector,
                "confidence": confidence, "affected": affected or [],
                "signature": f"{detector}:{kind}:{title}"})

        # -- detector 1: shared distribution channels (§7)
        channel_users: dict[str, list[str]] = {}
        for bid in member_ids:
            try:
                channels = self._business.get_business_channels(bid)
            except Exception:
                channels = []
            for channel in channels or []:
                ctype = channel.get("channel_type") or channel.get("type")
                if ctype:
                    channel_users.setdefault(ctype, []).append(bid)
        for ctype, users in sorted(channel_users.items()):
            if len(set(users)) >= 2:
                opportunity(
                    "SHARED_AUDIENCE", users,
                    f"Shared audience on {ctype}",
                    f"{len(set(users))} portfolio businesses publish "
                    f"on {ctype}; a coordinated cross-promotion is "
                    "possible without sharing customer records.",
                    [{"source": "p06.channels", "channel_type": ctype,
                      "business_ids": sorted(set(users))}],
                    "shared_channel",
                    ["coordinated cross-promotion on an existing "
                     "channel"])

        # -- detector 2: shared-service fit (§7/§9)
        session = self._session_factory()
        try:
            services, _total = SharedServiceRepository(session).list(
                limit=200)
            access_repo = ServiceAccessRepository(session)
            for service in services:
                if service.status != "AVAILABLE":
                    continue
                subscribed, missing = [], []
                for bid in member_ids:
                    access = access_repo.get_access(service.id, bid)
                    if access is not None and access.status in (
                            "APPROVED", "ACTIVE"):
                        subscribed.append(bid)
                    else:
                        missing.append(bid)
                if subscribed and missing:
                    opportunity(
                        "SHARED_SERVICE", subscribed + missing,
                        f"Adopt shared service: {service.name}",
                        f"{service.name} already serves "
                        f"{len(subscribed)} portfolio business(es); "
                        f"{len(missing)} more could use the same "
                        "infrastructure instead of duplicating it.",
                        [{"source": "p13.shared_service",
                          "service_id": service.id,
                          "service": service.name}],
                        "shared_service_fit",
                        ["one infrastructure cost instead of "
                         "per-business duplication"])
        finally:
            session.close()

        # -- detector 3: complementary operational businesses (§7)
        operational = [bid for bid in member_ids
                       if summaries[bid]["portfolio_stage"]
                       in ("OPERATIONAL", "OPTIMIZING", "SCALING")]
        pairs = [(a, b) for i, a in enumerate(operational)
                 for b in operational[i + 1:]]
        for a, b in pairs[:10]:
            if businesses[a]["category"] != businesses[b]["category"]:
                opportunity(
                    "COMPLEMENTARY_PRODUCT", [a, b],
                    f"Complementary offer: {businesses[a]['name']} + "
                    f"{businesses[b]['name']}",
                    "Two operational businesses in different "
                    "categories could bundle or cross-refer; no "
                    "revenue is claimed until P-07 records it.",
                    [{"source": "p06.business", "business_ids": [a, b],
                      "categories": [businesses[a]["category"],
                                     businesses[b]["category"]]}],
                    "complementary_categories",
                    ["possible bundle or referral path (unverified)"])

        # -- detector 4: duplicated product lines (§7)
        for i, a in enumerate(member_ids):
            for b in member_ids[i + 1:]:
                if businesses[a]["category"] == businesses[b]["category"] \
                        and summaries[a]["template"] is not None \
                        and summaries[a]["template"] == \
                        summaries[b]["template"]:
                    recommendation(
                        "RESTRUCTURING",
                        f"Possible duplicated product line: "
                        f"{businesses[a]['name']} / {businesses[b]['name']}",
                        "Both businesses share category and product "
                        "template; the owner may be funding the same "
                        "product twice.",
                        [{"source": "p06.business",
                          "business_ids": [a, b],
                          "category": businesses[a]["category"],
                          "template": summaries[a]["template"]}],
                        "duplication", affected=[a, b])

        # -- detector 5: concentration (§12) — from P-07 figures
        concentration = self.concentration_view(
            principal, portfolio_id)
        for row in concentration["businesses"]:
            if row["share_bps"] >= concentration["threshold_bps"] and \
                    row["collected_minor"] > 0:
                recommendation(
                    "RISK_REDUCTION",
                    f"Revenue concentration: {row['name']}",
                    f"{row['name']} provides {row['share_bps'] / 100:.1f}% "
                    "of verified collected portfolio revenue, above "
                    "the configured threshold. Diversification or a "
                    "contingency plan is advisable.",
                    [{"source": "p08.concentration",
                      "business_id": row["business_id"],
                      "share_bps": row["share_bps"]}],
                    "concentration", confidence="high",
                    affected=[row["business_id"]])

        # -- detector 6: organization-shared lessons (§7/§14)
        lessons = self._shared_lessons()
        if lessons and len(member_ids) >= 2:
            opportunity(
                "SHARED_KNOWLEDGE", member_ids,
                "Generalized lessons are organization-shared",
                f"{len(lessons)} P-09 memory record(s) are explicitly "
                "ORGANIZATION_SHARED and may inform every portfolio "
                "business. Business-specific memory stays isolated.",
                [{"source": "p09.memory", "shared_records": len(lessons)}],
                "shared_knowledge",
                ["reuse of verified generalized lessons"])

        # ------------------------------------------------ persistence
        session = self._session_factory()
        created_o = created_r = 0
        try:
            opp_repo = OpportunityRepository(session)
            existing, _t = opp_repo.list(limit=500,
                                         portfolio_id=portfolio_id)
            known_o = {(r.evaluation or {}).get("signature")
                       for r in existing}
            for item in found_opportunities:
                if item["signature"] in known_o:
                    continue
                opp_repo.add(CrossBusinessOpportunity(
                    portfolio_id=portfolio_id, category=item["category"],
                    business_ids=item["involved"],
                    title=item["title"], description=item["description"],
                    evidence=item["evidence"], evidence_status="VERIFIED",
                    evaluation={
                        "expected_benefits": item["benefits"],
                        "signature": item["signature"]},
                    confidence="moderate", origin=item["detector"],
                    created_by=actor_of(principal)))
                created_o += 1
            rec_repo = RecommendationRepository(session)
            existing_r, _t = rec_repo.list(limit=500,
                                           portfolio_id=portfolio_id)
            known_r = {(r.financial_implications or {}).get("signature")
                       for r in existing_r}
            for item in found_recommendations:
                if item["signature"] in known_r:
                    continue
                rec_repo.add(PortfolioRecommendation(
                    portfolio_id=portfolio_id, kind=item["kind"],
                    title=item["title"],
                    affected_business_ids=item["affected"],
                    evidence=item["evidence"],
                    evidence_status="VERIFIED",
                    confidence=item["confidence"],
                    approval_requirements="owner decision required "
                                           "before any action",
                    financial_implications={
                        "rationale": item["rationale"],
                        "signature": item["signature"],
                        "detector": item["detector"]},
                    origin=item["detector"],
                    created_by=actor_of(principal)))
                created_r += 1
        finally:
            session.close()
        self._audit(principal, "portfolio.analysis_run", "portfolio",
                    portfolio_id, "allow",
                    "deterministic portfolio analysis completed",
                    {"opportunities_created": created_o,
                     "recommendations_created": created_r,
                     "survival_mode": bool(portfolio.survival_mode)})
        return {
            "portfolio_id": portfolio_id,
            "businesses_analyzed": len(member_ids),
            "opportunities_created": created_o,
            "recommendations_created": created_r,
            "concentration": concentration,
        }

    def _shared_lessons(self) -> list[dict]:
        """ORGANIZATION_SHARED P-09 records only — the single memory
        category that may cross businesses (§14). Read through the
        P-09 store with the system principal (P-09's own read policy
        applies), then filtered to the organization scope in code:
        business-scoped records are structurally excluded."""
        if self._memory is None:
            return []
        system = Principal(type=PrincipalType.SYSTEM, id="system",
                           name="System")
        try:
            rows, _total = self._memory.store.list(system, limit=200)
        except Exception:
            return []
        return [{"id": r["id"], "title": r.get("title"),
                 "record_type": r.get("category")}
                for r in rows
                if r.get("access_scope") == "ORGANIZATION_SHARED"]

    # ------------------------------------------------- concentration
    def concentration_view(self, principal: Principal, portfolio_id: str,
                           currency: str = "INR") -> dict:
        """§12 concentration: verified collected shares per business,
        computed from P-07 figures only. Shares are of COLLECTED
        revenue — projected figures never enter."""
        self._require_portfolio_reader(principal, "portfolio.concentration")
        self._portfolio_or_404(portfolio_id)
        member_ids = self._member_business_ids(portfolio_id)
        settings = self.get_settings()
        rows = []
        total = 0
        channels_present: set[str] = set()
        for bid in member_ids:
            metrics = self._financial.revenue.metrics(bid, currency)
            collected = int(metrics.get("net_collected_minor") or 0)
            total += collected
            rows.append({
                "business_id": bid,
                "name": self._business_or_404(bid)["name"],
                "collected_minor": collected,
            })
            try:
                channels = self._business.get_business_channels(bid)
            except Exception:
                channels = []
            for channel in channels or []:
                ctype = channel.get("channel_type") or channel.get("type")
                if ctype:
                    channels_present.add(ctype)
        for row in rows:
            row["share_bps"] = (row["collected_minor"] * 10000 // total
                                if total > 0 else 0)
        rows.sort(key=lambda r: -r["collected_minor"])
        return {
            "portfolio_id": portfolio_id, "currency": currency,
            "total_collected_minor": total,
            "threshold_bps": settings["concentration_threshold_bps"],
            "businesses": rows,
            "channels_present": sorted(channels_present),
            "note": "shares are of verified collected revenue only "
                    "(P-07); per-channel revenue attribution is not "
                    "fabricated for multi-channel businesses",
        }

    # ------------------------------------------------------------ risk
    def assess_risk(self, principal: Principal, portfolio_id: str) -> dict:
        """§12 portfolio risk assessment: per-business levels from
        P-08 lifecycle readings + concentration + shared-service
        single points of failure. Persisted as an assessment row
        (per-business readings ride inside findings, tagged
        business_risk, so the stored record stays complete)."""
        self._require_portfolio_reader(principal, "portfolio.risk")
        portfolio = self._portfolio_or_404(portfolio_id)
        member_ids = self._member_business_ids(portfolio_id)
        concentration = self.concentration_view(principal, portfolio_id)
        share_by_id = {r["business_id"]: r["share_bps"]
                       for r in concentration["businesses"]}
        per_business = []
        findings: list[dict] = []
        worst = 0
        for bid in member_ids:
            summary = self._business_summary(bid)
            score = 0
            signals = []
            stage = summary["portfolio_stage"]
            if stage == "AT_RISK" or \
                    summary["p08_overlay_state"] == "AT_RISK":
                score += 3
                signals.append("P-08 overlay reads AT_RISK")
            if summary["p08_overlay_state"] in ("RECOVERY",
                                                "CLOSURE_REVIEW"):
                score += 2
                signals.append(
                    f"P-08 overlay reads {summary['p08_overlay_state']}")
            if summary["p06_state"] in ("BLOCKED", "FAILED"):
                score += 2
                signals.append(f"P-06 state is {summary['p06_state']}")
            if summary["paused"]:
                score += 1
                signals.append("business is paused (P-08)")
            share = share_by_id.get(bid, 0)
            if share >= concentration["threshold_bps"] and \
                    concentration["total_collected_minor"] > 0:
                score += 2
                signals.append(
                    f"revenue concentration {share / 100:.1f}% of "
                    "verified collected portfolio revenue")
                findings.append({
                    "kind": "concentration", "business_id": bid,
                    "detail": signals[-1]})
            level = ("low" if score == 0 else
                     "moderate" if score <= 2 else
                     "high" if score <= 4 else "critical")
            worst = max(worst, C.RISK_LEVELS.index(level))
            per_business.append({
                "business_id": bid, "name": summary["name"],
                "portfolio_stage": stage, "risk_level": level,
                "risk_score": score, "signals": signals,
                "collected_share_bps": share})
        # shared-service single points of failure
        session = self._session_factory()
        try:
            services, _t = SharedServiceRepository(session).list(limit=200)
            access_repo = ServiceAccessRepository(session)
            for service in services:
                users = [a for a in access_repo.for_service(service.id)
                         if a.status in ("APPROVED", "ACTIVE")]
                if len(users) >= 2 and service.status != "AVAILABLE":
                    findings.append({
                        "kind": "shared_service_spof",
                        "service_id": service.id,
                        "detail": f"{service.name} is {service.status} "
                                  f"and serves {len(users)} businesses"})
                    worst = max(worst, 2)
        finally:
            session.close()
        if portfolio.survival_mode:
            findings.append({
                "kind": "survival_mode",
                "detail": "portfolio survival mode is ACTIVE (owner-"
                          "activated); endangered businesses are "
                          "flagged and discretionary allocations are "
                          "blocked"})
        level = C.RISK_LEVELS[worst]
        stored_findings = findings + [
            {"kind": "business_risk", **row} for row in per_business]
        session = self._session_factory()
        try:
            row = RiskAssessmentRepository(session).add(
                PortfolioRiskAssessment(
                    portfolio_id=portfolio_id, overall_level=level,
                    findings=stored_findings,
                    assessed_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.risk_assessed", "portfolio",
                    portfolio_id, "allow",
                    f"portfolio risk assessed: {level}",
                    {"findings": len(findings)})
        # P-14 Stage B (DEF-I1): risk assessments are first-class bus
        # events, persisted via the critical set.
        if self._bus is not None:
            self._bus.publish_sync_safe(Event(
                event_type=EventType.PORTFOLIO_RISK_DETECTED,
                source="portfolio.intelligence",
                payload={"portfolio_id": portfolio_id,
                         "assessment_id": row.id, "risk_level": level,
                         "findings": len(findings),
                         "businesses_assessed": len(per_business)},
                severity=("warning" if level in ("high", "critical")
                          else "info"),
                actor=actor_of(principal)))
        return {
            "id": row.id, "portfolio_id": portfolio_id,
            "risk_level": level, "per_business": per_business,
            "findings": findings,
            "assessed_by": row.assessed_by,
            "created_at": row.created_at.isoformat()
            if row.created_at else None,
        }

    def latest_risk(self, principal: Principal, portfolio_id: str) -> dict:
        self._require_portfolio_reader(principal, "portfolio.risk")
        session = self._session_factory()
        try:
            rows, _t = RiskAssessmentRepository(session).list(
                limit=200, portfolio_id=portfolio_id)
            if not rows:
                return {"portfolio_id": portfolio_id, "risk_level": None,
                        "note": "no risk assessment has run yet"}
            row = rows[0]  # repository lists newest first
            findings = row.findings or []
            per_business = [f for f in findings
                            if f.get("kind") == "business_risk"]
            other = [f for f in findings
                     if f.get("kind") != "business_risk"]
            return {
                "id": row.id, "portfolio_id": portfolio_id,
                "risk_level": row.overall_level,
                "per_business": per_business,
                "findings": other,
                "assessed_by": row.assessed_by,
                "created_at": row.created_at.isoformat()
                if row.created_at else None,
            }
        finally:
            session.close()
