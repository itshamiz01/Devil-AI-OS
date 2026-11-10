"""MarketsMixin — §4.1 market research records, §8 customer
segments, §13 competitor profiles and §14 country assessments.

All four are governed *records*: content is entered through
owner-gated writes with source references, and the system fabricates
nothing. Market research for a specific opportunity continues to
live in P-03 (market analyses, evidence, per-opportunity
competitors); these records are the economy-level layer — markets,
segments and countries that span opportunities and businesses.
"""
from __future__ import annotations

from sqlalchemy import select

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.base import utcnow
from ..database.models.economy import (
    CompetitorProfile, CountryAssessment, CustomerSegment, MarketReport,
)
from ..permissions.models import Principal
from . import constants as C
from . import scoring


def _iso(value):
    from ..database.models.base import as_utc
    value = as_utc(value)
    return value.isoformat() if value else None


def market_dict(row: MarketReport) -> dict:
    return {"id": row.id, "title": row.title, "sector": row.sector,
            "classification": row.classification,
            "description": row.description,
            "target_customers": row.target_customers,
            "demand_indicators": row.demand_indicators or [],
            "competitor_notes": row.competitor_notes,
            "revenue_models": row.revenue_models or [],
            "startup_requirements": row.startup_requirements,
            "operating_costs": row.operating_costs,
            "acquisition_challenges": row.acquisition_challenges,
            "legal_regulatory": row.legal_regulatory,
            "risks": row.risks or [],
            "evidence_sources": row.evidence_sources or [],
            "confidence": row.confidence,
            "figures_label": row.figures_label,
            "figures_note": "figures in a market report are "
                            "estimates unless the evidence sources "
                            "verify them (§4.1); the system fabricates "
                            "no market size, demand or competitor "
                            "revenue",
            "p03_opportunity_id": row.p03_opportunity_id,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def competitor_dict(row: CompetitorProfile) -> dict:
    return {"id": row.id, "name": row.name, "market": row.market,
            "market_report_id": row.market_report_id,
            "products": row.products or [],
            "pricing_notes": row.pricing_notes,
            "business_model": row.business_model,
            "positioning": row.positioning,
            "strengths": row.strengths or [],
            "weaknesses": row.weaknesses or [],
            "source_refs": row.source_refs or [],
            "source_rule": "public or authorized sources only (§13)",
            "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def country_dict(row: CountryAssessment) -> dict:
    return {"id": row.id, "country": row.country, "region": row.region,
            "criteria_scores": row.criteria_scores or {},
            "weights": row.weights or {},
            "total_score": row.total_score,
            "entry_checklist": row.entry_checklist or {},
            "notes": row.notes, "status": row.status,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def segment_dict(row: CustomerSegment) -> dict:
    return {"id": row.id, "name": row.name, "kind": row.kind,
            "business_id": row.business_id,
            "description": row.description,
            "needs": row.needs or [], "attributes": row.attributes or {},
            "international_checklist": row.international_checklist or {},
            "data_rule": "segments are owner-declared from "
                         "legitimately obtained data; the system "
                         "fabricates no customer data (§8)",
            "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


class MarketsMixin:
    # ---------------------------------------------------- §4.1 markets
    def create_market_report(self, principal: Principal,
                             data: dict) -> dict:
        self._require_owner(principal, "economy.market.create")
        if data.get("sector") not in C.MARKET_SECTORS:
            raise ValidationError(
                f"sector must be one of {list(C.MARKET_SECTORS)}")
        if data.get("classification") not in C.MARKET_CLASSIFICATIONS:
            raise ValidationError(
                "classification must be one of "
                f"{list(C.MARKET_CLASSIFICATIONS)} (§4.1)")
        if not (data.get("title") or "").strip():
            raise ValidationError("a market report requires a title")
        if not data.get("evidence_sources"):
            raise ValidationError(
                "a market report requires at least one evidence "
                "source (§4.1: source-backed evidence; do not "
                "fabricate market size, demand or competitor "
                "revenue)")
        confidence = int(data.get("confidence", 0))
        if not 0 <= confidence <= 100:
            raise ValidationError("confidence must be 0..100")
        session = self._session_factory()
        try:
            row = MarketReport(
                title=data["title"], sector=data["sector"],
                classification=data["classification"],
                description=data.get("description") or "",
                target_customers=data.get("target_customers") or "",
                demand_indicators=data.get("demand_indicators") or [],
                competitor_notes=data.get("competitor_notes") or "",
                revenue_models=data.get("revenue_models") or [],
                startup_requirements=data.get("startup_requirements") or "",
                operating_costs=data.get("operating_costs") or "",
                acquisition_challenges=data.get("acquisition_challenges") or "",
                legal_regulatory=data.get("legal_regulatory") or "",
                risks=data.get("risks") or [],
                evidence_sources=data["evidence_sources"],
                confidence=confidence,
                figures_label=data.get("figures_label") or "estimates",
                p03_opportunity_id=data.get("p03_opportunity_id"),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = market_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.market_created", "economy",
                    result["id"], "allow",
                    "market report recorded (§4.1)")
        return result

    def list_market_reports(self, principal: Principal, *,
                            classification: str | None = None,
                            limit: int = 100) -> dict:
        self._require_reader(principal, "economy.markets")
        session = self._session_factory()
        try:
            stmt = select(MarketReport)
            if classification:
                stmt = stmt.where(
                    MarketReport.classification == classification)
            rows = session.execute(
                stmt.order_by(MarketReport.created_at.desc())
                .limit(limit)).scalars().all()
            return {"items": [market_dict(r) for r in rows],
                    "total": len(rows)}
        finally:
            session.close()

    def get_market_report(self, principal: Principal,
                          report_id: str) -> dict:
        self._require_reader(principal, "economy.markets")
        session = self._session_factory()
        try:
            row = session.get(MarketReport, report_id)
            if row is None:
                raise NotFoundError(f"market report {report_id} not found")
            return market_dict(row)
        finally:
            session.close()

    # ------------------------------------------------- §13 competitors
    def create_competitor(self, principal: Principal,
                          data: dict) -> dict:
        self._require_owner(principal, "economy.competitor.create")
        if not (data.get("name") or "").strip():
            raise ValidationError("a competitor profile requires a name")
        if not data.get("source_refs"):
            raise ValidationError(
                "a competitor profile requires source references — "
                "public or authorized sources only; profiles without "
                "sources cannot be created (§13)")
        session = self._session_factory()
        try:
            row = CompetitorProfile(
                name=data["name"], market=data.get("market") or "",
                market_report_id=data.get("market_report_id"),
                products=data.get("products") or [],
                pricing_notes=data.get("pricing_notes") or "",
                business_model=data.get("business_model") or "",
                positioning=data.get("positioning") or "",
                strengths=data.get("strengths") or [],
                weaknesses=data.get("weaknesses") or [],
                source_refs=data["source_refs"],
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = competitor_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.competitor_created", "economy",
                    result["id"], "allow",
                    "competitor profile recorded from declared "
                    "sources (§13)")
        return result

    def list_competitors(self, principal: Principal, *,
                         market: str | None = None,
                         limit: int = 100) -> dict:
        self._require_reader(principal, "economy.competitors")
        session = self._session_factory()
        try:
            stmt = select(CompetitorProfile)
            if market:
                stmt = stmt.where(CompetitorProfile.market == market)
            rows = session.execute(
                stmt.order_by(CompetitorProfile.created_at.desc())
                .limit(limit)).scalars().all()
            return {"items": [competitor_dict(r) for r in rows],
                    "total": len(rows)}
        finally:
            session.close()

    def competitor_comparison(self, principal: Principal, *,
                              market: str) -> dict:
        """§13 comparison report over the recorded profiles of one
        market, with the competitive-gap reading. Gaps are readings
        of the recorded weaknesses, labelled as analysis of declared
        sources — not intelligence the system gathered itself."""
        self._require_reader(principal, "economy.competitors")
        listed = self.list_competitors(principal, market=market)
        gaps = []
        for item in listed["items"]:
            for weakness in item["weaknesses"]:
                gaps.append({"competitor": item["name"],
                             "recorded_weakness": weakness,
                             "reading": "potential gap to compete on "
                                        "through pricing, function, "
                                        "experience, speed, "
                                        "specialisation or automation "
                                        "(§13) — verify before acting"})
        return {"market": market, "competitors": listed["items"],
                "competitor_count": listed["total"],
                "identified_gaps": gaps,
                "generated_at": utcnow().isoformat(),
                "basis": "declared public/authorized sources only"}

    # --------------------------------------------------- §14 countries
    def create_country_assessment(self, principal: Principal,
                                  data: dict) -> dict:
        self._require_owner(principal, "economy.country.create")
        if not (data.get("country") or "").strip():
            raise ValidationError("a country assessment requires a "
                                  "country")
        unknown_criteria = sorted(
            set(data.get("criteria_scores") or {}) - set(C.COUNTRY_CRITERIA))
        if unknown_criteria:
            raise ValidationError(
                f"unknown §14 criteria keys: {unknown_criteria}; "
                f"valid keys are {list(C.COUNTRY_CRITERIA)}")
        settings = self.get_settings()
        weights = data.get("weights") or settings["country_weights"]
        scored = scoring.country_score(data.get("criteria_scores") or {},
                                       weights)
        session = self._session_factory()
        try:
            row = CountryAssessment(
                country=data["country"],
                region=data.get("region") or "",
                criteria_scores=data.get("criteria_scores") or {},
                weights=scored["weights"],
                total_score=scored["total_score"],
                entry_checklist=data.get("entry_checklist") or {},
                notes=data.get("notes") or "",
                status=data.get("status") or "assessed",
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = country_dict(row)
            result["missing_criteria"] = scored["missing_criteria"]
        finally:
            session.close()
        self._audit(principal, "economy.country_created", "economy",
                    result["id"], "allow",
                    "country entry assessment recorded (§14)")
        return result

    def rank_countries(self, principal: Principal) -> dict:
        """§14 ranking by the stored transparent scores. A business
        model succeeding in one country is never assumed to succeed
        in another — the ranking orders research, not decisions."""
        self._require_reader(principal, "economy.countries")
        session = self._session_factory()
        try:
            rows = session.execute(
                select(CountryAssessment).order_by(
                    CountryAssessment.total_score.desc())).scalars().all()
            items = [country_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": len(items),
                "methodology": "weighted mean of criterion "
                               "attractiveness scores with the "
                               "weights stored on each assessment; "
                               "rankings order research priority, "
                               "never entry decisions (§14)"}

    # ---------------------------------------------------- §8 segments
    def create_segment(self, principal: Principal, data: dict) -> dict:
        self._require_owner(principal, "economy.segment.create")
        if data.get("kind") not in C.SEGMENT_KINDS:
            raise ValidationError(
                f"kind must be one of {list(C.SEGMENT_KINDS)} (§8)")
        if not (data.get("name") or "").strip():
            raise ValidationError("a segment requires a name")
        if data.get("business_id"):
            self._business_or_404(data["business_id"])
        if data.get("kind") == "geographic" and not data.get(
                "international_checklist"):
            raise ValidationError(
                "a geographic expansion segment requires the §8 "
                "international checklist (tax, regulations, payments, "
                "currency, consumer protection, privacy, "
                "localization, distribution) before it can be "
                "recorded")
        session = self._session_factory()
        try:
            row = CustomerSegment(
                name=data["name"], kind=data["kind"],
                business_id=data.get("business_id"),
                description=data.get("description") or "",
                needs=data.get("needs") or [],
                attributes=data.get("attributes") or {},
                international_checklist=data.get(
                    "international_checklist") or {},
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = segment_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.segment_created", "economy",
                    result["id"], "allow",
                    "customer segment recorded (§8)")
        return result

    def list_segments(self, principal: Principal, *,
                      business_id: str | None = None,
                      limit: int = 100) -> dict:
        self._require_reader(principal, "economy.segments")
        session = self._session_factory()
        try:
            stmt = select(CustomerSegment)
            if business_id:
                stmt = stmt.where(
                    CustomerSegment.business_id == business_id)
            rows = session.execute(
                stmt.order_by(CustomerSegment.created_at.desc())
                .limit(limit)).scalars().all()
            return {"items": [segment_dict(r) for r in rows],
                    "total": len(rows)}
        finally:
            session.close()
