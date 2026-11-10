"""§6 Continuous business monitoring.

Financial monitoring reads ONLY through the P-07 FinancialService
(the §25 ``p08_indicators`` contract plus P-07's own summary/metrics
reads). P-08 sums no monetary amounts: the only derivations here are
*counts* of commercial facts (distinct/repeat customers, collected
records) taken from P-07's existing ``list_revenue`` read API — audit
gap G-1 — and dimensionless comparisons between two P-07 readings.

Commercial and operational monitoring (§6.2/§6.3) is evidence-based:
observations are recorded with provenance and a reliability ceiling.
Vanity metrics (traffic, followers, impressions, downloads) are
flagged at write time and can never validate a business (§6.2).
Strategic observations (§6.4) carry provenance; an unverified rumour
is recorded as unverified, never as a confirmed risk.
"""
from __future__ import annotations

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.base import utcnow
from ..database.models.survival import (
    BusinessMonitoringEvent, BusinessObservation,
)
from ..database.repositories.survival import (
    MonitoringEventRepository, ObservationRepository,
)
from . import constants as C

VANITY_RELIABILITY_CAP = "tentative"


def observation_dict(row: BusinessObservation) -> dict:
    return {
        "id": row.id, "business_id": row.business_id, "kind": row.kind,
        "metrics": row.metrics, "source": row.source,
        "reliability": row.reliability, "is_vanity": row.is_vanity,
        "evidence_refs": row.evidence_refs, "observed_on": row.observed_on,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
    }


def monitoring_event_dict(row: BusinessMonitoringEvent) -> dict:
    return {
        "id": row.id, "business_id": row.business_id, "kind": row.kind,
        "severity": row.severity, "source": row.source,
        "payload": row.payload, "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
    }


class MonitoringService:
    def __init__(self, session_factory, financial, business, audit):
        self._session_factory = session_factory
        self._financial = financial
        self._business = business
        self._audit = audit

    # ---------------------------------------------------- P-07 readings
    def collect(self, business_id: str) -> dict:
        """One monitoring reading for a business. Every monetary figure
        is a verbatim P-07 value; ``counts`` are commercial counts
        derived from P-07's read API (no amounts are summed)."""
        self._business.get_business(business_id)
        profile = self._financial.get_profile(business_id)
        if profile is None:
            return {
                "business_id": business_id, "profile_missing": True,
                "currency": None, "indicators": None, "summary": None,
                "counts": None, "collected_customers": None,
                "note": "no P-07 financial profile exists for this "
                        "business; financial monitoring has nothing "
                        "authoritative to read",
            }
        currency = profile["base_currency"]
        indicators = self._financial.p08_indicators(business_id)
        summary = self._financial.business_summary(business_id)
        counts = self._commercial_counts(business_id, currency)
        return {
            "business_id": business_id, "profile_missing": False,
            "currency": currency, "indicators": indicators,
            "summary": summary, "counts": counts,
            "collected_customers": counts["distinct_customers"],
            "note": "all monetary figures are P-07 values, reproduced "
                    "verbatim; P-08 computes no financial figure (§6.1)",
        }

    def _commercial_counts(self, business_id: str, currency: str) -> dict:
        """Counts (never amounts) from P-07's list_revenue read API:
        verified collected records, distinct customers, repeat
        customers, active subscriptions (P-07 monthly value is NOT
        summed here — MRR comes from P-07 metrics in the summary)."""
        records, _total = self._financial.revenue.list_revenue(
            business_id, limit=1000)
        verified = [r for r in records
                    if r["currency"] == currency
                    and r["classification"] in ("collected", "recognized")
                    and r["verification_status"] == "verified"
                    and not r["is_internal_transfer"]
                    and r["lifecycle_status"] not in
                    ("CANCELLED", "FAILED", "REVERSED")]
        per_customer: dict[str, int] = {}
        channels: dict[str, int] = {}
        for record in verified:
            ref = record.get("customer_ref")
            if ref:
                per_customer[ref] = per_customer.get(ref, 0) + 1
            channel = record.get("channel") or "unspecified"
            channels[channel] = channels.get(channel, 0) + 1
        return {
            "verified_collected_records": len(verified),
            "distinct_customers": len(per_customer),
            "repeat_customers": sum(
                1 for n in per_customer.values() if n >= 2),
            "records_by_channel": channels,
            "source": "p07.revenue.list_revenue (counts only; audit G-1)",
        }

    # ----------------------------------------------------- observations
    def record_observation(self, principal, business_id: str,
                           data: dict) -> dict:
        self._business.get_business(business_id)
        kind = str(data.get("kind") or "").strip()
        if not kind:
            raise ValidationError("observation kind is required")
        metrics = data.get("metrics") or {}
        if not isinstance(metrics, dict) or not metrics:
            raise ValidationError("observation metrics are required")
        source = str(data.get("source") or "").strip()
        if not source:
            raise ValidationError(
                "observation source (provenance) is required (§6.4)")
        reliability = data.get("reliability") or "tentative"
        if reliability not in ("verified", "corroborated", "supporting",
                               "tentative", "unverified"):
            raise ValidationError(f"unknown reliability {reliability!r}")
        metric_keys = {str(k).lower() for k in metrics}
        is_vanity = kind in C.VANITY_KINDS or (
            bool(metric_keys) and metric_keys <= C.VANITY_METRIC_KEYS)
        if is_vanity and reliability in ("verified", "corroborated"):
            reliability = VANITY_RELIABILITY_CAP  # vanity caps (§6.2)
        session = self._session_factory()
        try:
            row = ObservationRepository(session).add(BusinessObservation(
                business_id=business_id, kind=kind, metrics=metrics,
                source=source, reliability=reliability,
                is_vanity=is_vanity,
                evidence_refs=data.get("evidence_refs") or [],
                observed_on=data.get("observed_on")
                or utcnow().date().isoformat(),
                created_by=_actor(principal)))
            result = observation_dict(row)
        finally:
            session.close()
        self._audit(principal, "survival.observation_recorded",
                    "business", business_id, "allow",
                    f"observation {kind} vanity={is_vanity}")
        return result

    def list_observations(self, business_id: str, *, kind: str | None = None,
                          limit: int = 100) -> list[dict]:
        session = self._session_factory()
        try:
            rows = ObservationRepository(session).for_business(
                business_id, limit=limit)
            return [observation_dict(r) for r in rows
                    if kind is None or r.kind == kind]
        finally:
            session.close()

    def latest_observations(self, business_id: str) -> dict[str, dict]:
        """Latest observation per kind (for health/scaling evidence)."""
        latest: dict[str, dict] = {}
        for row in self.list_observations(business_id, limit=200):
            latest.setdefault(row["kind"], row)
        return latest

    # ------------------------------------------------- monitoring events
    def record_event(self, principal, business_id: str, kind: str,
                     severity: str, source: str, payload: dict) -> dict:
        session = self._session_factory()
        try:
            row = MonitoringEventRepository(session).add(
                BusinessMonitoringEvent(
                    business_id=business_id, kind=kind, severity=severity,
                    source=source, payload=payload,
                    created_by=_actor(principal)))
            return monitoring_event_dict(row)
        finally:
            session.close()

    def list_events(self, business_id: str, *, limit: int = 100,
                    offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = MonitoringEventRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [monitoring_event_dict(r) for r in rows], total
        finally:
            session.close()

    def run_checks(self, principal, business_id: str,
                   previous_indicators: dict | None) -> list[dict]:
        """Bounded, event-driven monitoring checks (§6.5): compares the
        current P-07 reading with the previous snapshot's reading and
        records findings. Deltas are comparisons of two P-07 readings,
        not new financial calculations."""
        reading = self.collect(business_id)
        events: list[dict] = []
        if reading["profile_missing"]:
            events.append(self.record_event(
                principal, business_id, "financial_profile_missing",
                "warning", "p08.monitoring",
                {"note": reading["note"]}))
            return events
        ind = reading["indicators"]
        if ind["profitability"]["is_loss"]:
            events.append(self.record_event(
                principal, business_id, "loss_making", "warning",
                "p07.p08_indicators",
                {"profitability": ind["profitability"]}))
        if previous_indicators:
            before = previous_indicators.get(
                "verified_collected_revenue_minor") or 0
            now = ind["verified_collected_revenue_minor"] or 0
            if before > 0 and now < before:
                events.append(self.record_event(
                    principal, business_id, "collected_revenue_declined",
                    "warning", "p08.monitoring",
                    {"previous_reading_minor": before,
                     "current_reading_minor": now,
                     "note": "comparison of two P-07 readings"}))
        recon = ind["reconciliation_status"]
        if recon["unresolved_items"] > 0:
            events.append(self.record_event(
                principal, business_id, "reconciliation_unresolved",
                "critical", "p07.p08_indicators",
                {"unresolved_items": recon["unresolved_items"]}))
        if ind["runway_status"] == "computed" and ind["runway_months"]:
            from decimal import Decimal
            if Decimal(ind["runway_months"]) < Decimal("3"):
                events.append(self.record_event(
                    principal, business_id, "runway_short", "warning",
                    "p07.p08_indicators",
                    {"runway_months": ind["runway_months"]}))
        return events


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}" if principal else "system"
