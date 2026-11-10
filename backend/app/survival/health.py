"""§7 Business health and sustainability engine.

Seven dimensions, each carrying evidence, freshness, confidence and
missing information (§7.4). The weighted score is a *secondary*
summary (§7.3): hard gates are evaluated first and cap the
classification regardless of the score. The financial dimension is a
pass-through of P-07's own health classification and indicators —
P-08 never re-derives a financial figure (lock 1). Dimension scores
for non-financial dimensions are band mappings over recorded
evidence (observations with provenance, P-06 records, commercial
counts), documented in docs/architecture/P08_HEALTH_METHODOLOGY.md.
"""
from __future__ import annotations

from decimal import Decimal

from ..database.models.survival import (
    BusinessHealthDimension, BusinessHealthSnapshot,
)
from ..database.repositories.survival import (
    HealthDimensionRepository, HealthSnapshotRepository,
    ObservationRepository,
)
from . import constants as C

STATUS_SCORE_BPS = {
    "EXCELLENT": 9000, "HEALTHY": 8000, "STABLE": 6000, "WATCH": 4500,
    "AT_RISK": 3000, "CRITICAL": 1000,
}


def _dim(dimension, status, evidence=None, missing=None,
         confidence="low", notes=""):
    return {
        "dimension": dimension, "status": status,
        "score_bps": STATUS_SCORE_BPS.get(status),
        "evidence": evidence or [], "missing": missing or [],
        "freshness": "current" if status != "INSUFFICIENT_DATA"
                     else "no_data",
        "confidence": confidence, "notes": notes,
    }


def _ratio(numerator: int, denominator: int) -> Decimal | None:
    """Dimensionless ratio of two P-07-returned figures (never a new
    monetary amount)."""
    if not denominator:
        return None
    return Decimal(numerator) / Decimal(denominator)


class HealthService:
    def __init__(self, session_factory, monitoring, business,
                 settings_getter, audit):
        self._session_factory = session_factory
        self._monitoring = monitoring
        self._business = business
        self._settings = settings_getter
        self._audit = audit

    # ------------------------------------------------------------ compute
    def compute(self, business_id: str, reading: dict,
                pause_active: bool) -> dict:
        business = self._business.get_business(business_id)
        observations = self._monitoring.latest_observations(business_id)
        settings = self._settings()
        dimensions: list[dict] = []
        gates: list[dict] = []

        profile_missing = reading["profile_missing"]
        indicators = reading.get("indicators") or {}
        summary = reading.get("summary") or {}
        metrics = (summary.get("revenue") or {})
        collected = indicators.get("verified_collected_revenue_minor") or 0

        # ------------------------------------------- financial (P-07)
        if profile_missing:
            dimensions.append(_dim(
                "financial", "INSUFFICIENT_DATA",
                missing=["P-07 financial profile",
                         "verified collected revenue", "expenses",
                         "cash balances"],
                notes="no P-07 profile: P-08 has no authoritative "
                      "financial source for this business"))
        else:
            p07_health = summary.get("health") or {}
            p07_status = p07_health.get("status", "INSUFFICIENT_DATA")
            fin_status = ("INSUFFICIENT_DATA"
                          if p07_status == "INSUFFICIENT_DATA"
                          else p07_status)
            evidence = [{
                "source": "p07.analytics.health",
                "status": p07_status,
                "reasons": p07_health.get("reasons", []),
            }, {
                "source": "p07.p08_indicators",
                "verified_collected_revenue_minor": collected,
                "available_cash_minor":
                    indicators.get("available_capital_minor"),
                "runway_months": indicators.get("runway_months"),
            }]
            dimensions.append(_dim(
                "financial", fin_status, evidence=evidence,
                missing=p07_health.get("missing_data", []),
                confidence="high" if fin_status != "INSUFFICIENT_DATA"
                else "low",
                notes="classification is P-07's own (§6.1); P-08 does "
                      "not re-derive financial figures"))
            available = summary.get("available_cash") or {}
            if (available.get("available_cash_minor") or 0) < 0:
                gates.append({
                    "gate": "cash_below_obligations",
                    "cap": "CRITICAL", "blocks_scaling": True,
                    "detail": "P-07 available cash is negative after "
                              "reserves, commitments and obligations"})
            elif (available.get("obligations_minor") or 0) > \
                    (available.get("cash_balance_minor") or 0) >= 0 and \
                    (available.get("obligations_minor") or 0) > 0:
                gates.append({
                    "gate": "obligations_exceed_cash", "cap": "AT_RISK",
                    "blocks_scaling": True,
                    "detail": "P-07 known obligations exceed the cash "
                              "balance (profit does not clear this)"})
            if indicators.get("profitability", {}).get("is_loss"):
                gates.append({
                    "gate": "loss_making", "blocks_scaling": True,
                    "detail": "P-07 profitability reports a loss on "
                              "verified figures; scaling is prohibited "
                              "and cost investigation is required (§3.1)"})
            if collected == 0 and ((metrics.get("projected_minor") or 0) > 0
                                   or (metrics.get("booked_minor") or 0) > 0):
                gates.append({
                    "gate": "unverified_revenue_only",
                    "blocks_scaling": True,
                    "detail": "projected/booked revenue exists but "
                              "verified collected revenue is zero; "
                              "unverified revenue cannot improve the "
                              "financial assessment (§7.3)"})
            recon = indicators.get("reconciliation_status") or {}
            if (recon.get("unresolved_items") or 0) > 0:
                gates.append({
                    "gate": "unresolved_reconciliation",
                    "blocks_scaling": True, "blocks_material_allocation": True,
                    "confidence_reduction": True,
                    "detail": f"{recon['unresolved_items']} unresolved "
                              "reconciliation item(s) in P-07; growth "
                              "confidence is reduced until resolved (§26.4 S13)"})

        # ------------------------------------------- market (P-06/P-03 evidence)
        level = business.get("validation_level_at_creation")
        market_obs = observations.get("market")
        market_evidence = [{
            "source": "p06.business.validation_level_at_creation",
            "level": level,
        }]
        if market_obs:
            market_evidence.append({
                "source": "p08.observation.market",
                "reliability": market_obs["reliability"],
                "metrics": market_obs["metrics"]})
        if level is not None and level >= 3 and market_obs and \
                market_obs["reliability"] in ("verified", "corroborated",
                                              "supporting"):
            dimensions.append(_dim(
                "market", "STABLE", evidence=market_evidence,
                confidence="moderate",
                notes="creation-time validation was computed by P-03; "
                      "market observations carry provenance"))
        elif level is not None and level >= 3:
            dimensions.append(_dim(
                "market", "WATCH", evidence=market_evidence,
                missing=["corroborated current market observation"],
                confidence="low",
                notes="validation exists but no current corroborated "
                      "market evidence is recorded"))
        else:
            dimensions.append(_dim(
                "market", "INSUFFICIENT_DATA", evidence=market_evidence,
                missing=["validated demand evidence"],
                notes="no sufficient market evidence"))

        # ------------------------------------------- commercial (counts + P-07 metrics)
        counts = reading.get("counts") or {}
        if profile_missing or counts.get("verified_collected_records", 0) == 0:
            dimensions.append(_dim(
                "commercial", "INSUFFICIENT_DATA",
                evidence=[{"source": "p07.revenue.list_revenue.counts",
                           "counts": counts}],
                missing=["verified paying customers"],
                notes="traffic, followers and impressions are not "
                      "commercial proof (§6.2)"))
        else:
            repeat = counts.get("repeat_customers", 0)
            distinct = counts.get("distinct_customers", 0)
            refund_rate = _ratio(metrics.get("refunds_minor") or 0,
                                 metrics.get("collected_gross_minor") or 0)
            status = "STABLE" if repeat > 0 else "WATCH"
            notes = ("repeat customers exist" if repeat > 0 else
                     "collected revenue exists but no repeat customer "
                     "has been observed")
            if refund_rate is not None and refund_rate > Decimal("0.10"):
                status = "WATCH"
                notes += "; refund rate exceeds 10% of collected gross"
            dimensions.append(_dim(
                "commercial", status,
                evidence=[{"source": "p07.revenue.list_revenue.counts",
                           "counts": counts},
                          {"source": "p07.revenue.metrics",
                           "refund_rate": str(refund_rate)
                           if refund_rate is not None else None}],
                confidence="moderate" if distinct >= 3 else "low",
                notes=notes))

        # ------------------------------------------- operational (observations)
        ops = observations.get("operations")
        if ops and not ops["is_vanity"]:
            rate = ops["metrics"].get("delivery_completion_rate")
            failures = ops["metrics"].get("failed_runs")
            if rate is not None:
                rate_d = Decimal(str(rate))
                status = ("HEALTHY" if rate_d >= Decimal("0.95") else
                          "STABLE" if rate_d >= Decimal("0.85") else
                          "WATCH" if rate_d >= Decimal("0.70") else
                          "AT_RISK")
                dimensions.append(_dim(
                    "operational", status,
                    evidence=[{"source": "p08.observation.operations",
                               "reliability": ops["reliability"],
                               "metrics": ops["metrics"]}],
                    confidence="moderate" if ops["reliability"] in
                    ("verified", "corroborated") else "low",
                    notes=f"delivery completion {rate_d}; failed runs "
                          f"{failures}"))
            else:
                dimensions.append(_dim(
                    "operational", "INSUFFICIENT_DATA",
                    evidence=[{"source": "p08.observation.operations",
                               "metrics": ops["metrics"]}],
                    missing=["delivery completion rate"],
                    notes="operational observation lacks a delivery rate"))
        else:
            dimensions.append(_dim(
                "operational", "INSUFFICIENT_DATA",
                missing=["delivery/operations evidence"],
                notes="no operational evidence recorded"))

        # ------------------------------------------- product (observations)
        product = observations.get("product")
        if product and not product["is_vanity"]:
            satisfaction = product["metrics"].get("satisfaction")
            status = "INSUFFICIENT_DATA"
            if satisfaction is not None:
                sat = Decimal(str(satisfaction))
                status = ("HEALTHY" if sat >= Decimal("0.8") else
                          "STABLE" if sat >= Decimal("0.6") else
                          "WATCH" if sat >= Decimal("0.4") else "AT_RISK")
            dimensions.append(_dim(
                "product", status,
                evidence=[{"source": "p08.observation.product",
                           "reliability": product["reliability"],
                           "metrics": product["metrics"]}],
                missing=[] if satisfaction is not None
                else ["customer satisfaction measure"],
                confidence="low",
                notes="product health rests on recorded observations, "
                      "not on generated artefacts"))
        else:
            dimensions.append(_dim(
                "product", "INSUFFICIENT_DATA",
                missing=["product quality / satisfaction evidence"],
                notes="a generated product is not product-health "
                      "evidence (§5.2)"))

        # ------------------------------------------- strategic (channels + concentration)
        channels, _total = self._business.list_channels(business_id)
        by_channel = metrics.get("by_channel_minor") or {}
        total_collected_gross = metrics.get("collected_gross_minor") or 0
        top_share = None
        top_channel = None
        if total_collected_gross > 0 and by_channel:
            top_channel, top_amount = max(
                by_channel.items(), key=lambda kv: kv[1])
            top_share = _ratio(top_amount, total_collected_gross)
        strat_evidence = [{
            "source": "p06.business_channels",
            "channels": [c.get("platform") for c in channels],
        }, {
            "source": "p07.revenue.metrics.by_channel",
            "top_channel": top_channel,
            "top_channel_share": str(top_share) if top_share else None,
        }]
        threshold = Decimal(settings.get("concentration_threshold", "0.6"))
        if top_share is not None and top_share > threshold:
            dimensions.append(_dim(
                "strategic", "WATCH", evidence=strat_evidence,
                confidence="moderate",
                notes=f"channel concentration: {top_channel} carries "
                      f"{top_share} of verified collected revenue"))
            gates.append({
                "gate": "channel_concentration",
                "detail": f"{top_channel} concentration share {top_share} "
                          f"exceeds {threshold}"})
        elif channels:
            dimensions.append(_dim(
                "strategic", "STABLE", evidence=strat_evidence,
                confidence="low",
                notes="channels recorded; concentration within "
                      "threshold where measurable"))
        else:
            dimensions.append(_dim(
                "strategic", "INSUFFICIENT_DATA", evidence=strat_evidence,
                missing=["distribution channel records"],
                notes="no channel evidence"))

        # ------------------------------------------- governance (pause + compliance)
        compliance = observations.get("compliance")
        violation = bool(compliance and compliance["metrics"].get(
            "violation") and compliance["reliability"] in
            ("verified", "corroborated"))
        if pause_active:
            dimensions.append(_dim(
                "governance", "CRITICAL",
                evidence=[{"source": "p08.pause_control",
                           "state": "emergency_pause_active"}],
                confidence="high",
                notes="an emergency pause is active for this business "
                      "(§25.2)"))
            gates.append({
                "gate": "security_incident", "cap": "CRITICAL",
                "blocks_scaling": True,
                "detail": "emergency pause active; new controlled "
                          "execution is blocked (§25.2)"})
        elif violation:
            dimensions.append(_dim(
                "governance", "AT_RISK",
                evidence=[{"source": "p08.observation.compliance",
                           "reliability": compliance["reliability"],
                           "metrics": compliance["metrics"]}],
                confidence="moderate",
                notes="a corroborated compliance violation is "
                      "recorded; scaling is blocked until resolved"))
            gates.append({
                "gate": "compliance_violation", "cap": "WATCH",
                "blocks_scaling": True,
                "detail": "confirmed compliance violation blocks "
                          "scaling (§7.3)"})
        elif compliance:
            dimensions.append(_dim(
                "governance", "STABLE",
                evidence=[{"source": "p08.observation.compliance",
                           "reliability": compliance["reliability"],
                           "metrics": compliance["metrics"]}],
                confidence="low",
                notes="compliance observation recorded, no violation"))
        else:
            dimensions.append(_dim(
                "governance", "INSUFFICIENT_DATA",
                missing=["compliance review evidence"],
                notes="no compliance evidence recorded; the system "
                      "does not certify compliance (§7.1G)"))

        # ------------------------------------------- score + classification
        weights = settings["health_weights"]
        weighted = Decimal(0)
        weight_total = Decimal(0)
        for dim in dimensions:
            if dim["score_bps"] is not None:
                w = Decimal(weights.get(dim["dimension"], 0))
                weighted += Decimal(dim["score_bps"]) * w
                weight_total += w
        score_bps = (int(weighted / weight_total)
                     if weight_total > 0 else None)
        bands = settings["health_bands"]
        if score_bps is None:
            classification = "INSUFFICIENT_DATA"
        else:
            ratio = Decimal(score_bps) / Decimal(10000)
            classification = (
                "EXCELLENT" if ratio >= Decimal(bands["excellent"]) else
                "HEALTHY" if ratio >= Decimal(bands["healthy"]) else
                "STABLE" if ratio >= Decimal(bands["stable"]) else
                "WATCH" if ratio >= Decimal(bands["watch"]) else
                "AT_RISK" if ratio >= Decimal(bands["at_risk"]) else
                "CRITICAL")
        fin_status = dimensions[0]["status"]
        if fin_status == "INSUFFICIENT_DATA":
            classification = "INSUFFICIENT_DATA"
        for gate in gates:
            cap = gate.get("cap")
            if cap and classification in C.SEVERITY and \
                    C.SEVERITY[classification] < C.SEVERITY[cap]:
                classification = cap
        data_dims = sum(1 for d in dimensions
                        if d["status"] != "INSUFFICIENT_DATA")
        confidence = ("high" if data_dims >= 6 else
                      "moderate" if data_dims >= 4 else "low")
        if any(g.get("confidence_reduction") for g in gates):
            confidence = {"high": "moderate", "moderate": "low",
                          "low": "low"}[confidence]
        explanation = self._explain(classification, dimensions, gates,
                                    business)
        return {
            "business": business, "dimensions": dimensions,
            "hard_gates": gates, "classification": classification,
            "score_bps": score_bps, "confidence": confidence,
            "explanation": explanation,
        }

    @staticmethod
    def _explain(classification, dimensions, gates, business) -> str:
        parts = [f"classification {classification}"]
        scored = [f"{d['dimension']}={d['status']}" for d in dimensions]
        parts.append("dimensions: " + ", ".join(scored))
        missing = [d["dimension"] for d in dimensions
                   if d["status"] == "INSUFFICIENT_DATA"]
        if missing:
            parts.append("insufficient data in: " + ", ".join(missing))
        for gate in gates:
            parts.append(f"gate[{gate['gate']}]: {gate['detail']}")
        if business.get("is_fixture"):
            parts.append("business is a labelled staging fixture")
        return "; ".join(parts)

    # ------------------------------------------------------------ persist
    def evaluate(self, principal, business_id: str, reading: dict,
                 pause_active: bool) -> dict:
        computed = self.compute(business_id, reading, pause_active)
        indicators = reading.get("indicators") or {}
        session = self._session_factory()
        try:
            snapshot = HealthSnapshotRepository(session).add(
                BusinessHealthSnapshot(
                    business_id=business_id,
                    classification=computed["classification"],
                    score_bps=computed["score_bps"],
                    currency=reading.get("currency") or "INR",
                    overlay_state="EARLY_OPERATIONS",  # facade refines
                    hard_gates=computed["hard_gates"],
                    explanation=computed["explanation"],
                    confidence=computed["confidence"],
                    indicators=indicators,
                    created_by=_actor(principal)))
            dim_repo = HealthDimensionRepository(session)
            for dim in computed["dimensions"]:
                dim_repo.add(BusinessHealthDimension(
                    snapshot_id=snapshot.id, business_id=business_id,
                    dimension=dim["dimension"], status=dim["status"],
                    score_bps=dim["score_bps"], evidence=dim["evidence"],
                    missing=dim["missing"], freshness=dim["freshness"],
                    confidence=dim["confidence"], notes=dim["notes"]))
            snapshot_id = snapshot.id
        finally:
            session.close()
        result = self.get_snapshot(snapshot_id)
        result["suggested_overlay"] = computed["classification"]
        return result

    def get_snapshot(self, snapshot_id: str) -> dict:
        session = self._session_factory()
        try:
            row = HealthSnapshotRepository(session).get(snapshot_id)
            if row is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError(f"health snapshot {snapshot_id} not found")
            dims = HealthDimensionRepository(session).for_snapshot(snapshot_id)
            return snapshot_dict(row, dims)
        finally:
            session.close()

    def latest_snapshot(self, business_id: str) -> dict | None:
        session = self._session_factory()
        try:
            row = HealthSnapshotRepository(session).latest_for(business_id)
            if row is None:
                return None
            dims = HealthDimensionRepository(session).for_snapshot(row.id)
            return snapshot_dict(row, dims)
        finally:
            session.close()

    def history(self, business_id: str, *, limit: int = 50,
                offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = HealthSnapshotRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            result = []
            dim_repo = HealthDimensionRepository(session)
            for row in rows:
                result.append(snapshot_dict(
                    row, dim_repo.for_snapshot(row.id)))
            return result, total
        finally:
            session.close()

    def snapshot_count(self, business_id: str) -> int:
        session = self._session_factory()
        try:
            return HealthSnapshotRepository(session).count_for(business_id)
        finally:
            session.close()

    def snapshots_with_revenue(self, business_id: str) -> int:
        """Snapshots whose stored P-07 reading showed verified
        collected revenue > 0 (evidence of sustained demand, §5.2)."""
        session = self._session_factory()
        try:
            rows, _ = HealthSnapshotRepository(session).list(
                limit=200, business_id=business_id)
            return sum(
                1 for r in rows
                if ((r.indicators or {}).get(
                    "verified_collected_revenue_minor") or 0) > 0)
        finally:
            session.close()


def snapshot_dict(row: BusinessHealthSnapshot, dims: list) -> dict:
    return {
        "id": row.id, "business_id": row.business_id,
        "classification": row.classification, "score_bps": row.score_bps,
        "currency": row.currency, "overlay_state": row.overlay_state,
        "hard_gates": row.hard_gates, "explanation": row.explanation,
        "confidence": row.confidence, "indicators": row.indicators,
        "indicators_source": row.indicators_source,
        "dimensions": [{
            "dimension": d.dimension, "status": d.status,
            "score_bps": d.score_bps, "evidence": d.evidence,
            "missing": d.missing, "freshness": d.freshness,
            "confidence": d.confidence, "notes": d.notes,
        } for d in dims],
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
    }


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}" if principal else "system"
