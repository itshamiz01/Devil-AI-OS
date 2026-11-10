"""§18 Survival and growth forecasting + §21 decision outcomes.

Forecasts are frozen at creation and never rewritten (§18.4): the
service exposes no update path for a forecast row. Inputs are P-07
readings (indicators, runway, P-07 forecasts); the expected values a
P-08 forecast records are *declared scenario expectations* built
from those readings and labelled forecasts everywhere — never
facts, never P-07 figures in disguise. Forecast-vs-actual uses
P-07's own ``forecast_vs_actual`` where a P-07 forecast exists
(P-07 computes the error), and snapshot-to-snapshot reading
comparisons otherwise.

Decision outcomes (§21) judge a decision by the evidence available
when it was made: ``decision_quality`` is assessed independently of
whether the outcome happened to be good.
"""
from __future__ import annotations

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.survival import DecisionOutcome, SurvivalForecast
from ..database.repositories.survival import (
    DecisionOutcomeRepository, SurvivalForecastRepository,
)
from . import constants as C

SCENARIOS = ("conservative", "base", "optimistic")
# Scenario adjustments are declared assumptions (dimensionless
# ratios applied to a *declared expectation*, clearly labelled),
# never presented as P-07 figures.
SCENARIO_ASSUMPTIONS = {
    "conservative": [
        "demand falls", "conversion decreases", "costs rise",
        "churn increases", "acquisition becomes more expensive",
    ],
    "base": ["performance follows the most defensible available "
             "assumptions (current P-07 readings continue)"],
    "optimistic": [
        "demand improves", "retention increases",
        "acquisition becomes more efficient",
        "operations scale successfully",
    ],
}


def forecast_dict(row: SurvivalForecast) -> dict:
    return {
        "id": row.id, "business_id": row.business_id, "kind": row.kind,
        "scenario": row.scenario, "period_label": row.period_label,
        "assumptions": row.assumptions, "inputs": row.inputs,
        "expected": row.expected, "confidence": row.confidence,
        "p07_forecast_id": row.p07_forecast_id,
        "classification": "forecast",
        "note": "a forecast is a labelled expectation built from "
                "P-07 readings; it is never a fact and is never "
                "rewritten after creation (§18.4)",
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
    }


def outcome_dict(row: DecisionOutcome) -> dict:
    return {
        "id": row.id, "business_id": row.business_id,
        "decision_id": row.decision_id,
        "experiment_id": row.experiment_id, "problem": row.problem,
        "evidence_at_decision": row.evidence_at_decision,
        "expected_outcome": row.expected_outcome,
        "actual_outcome": row.actual_outcome, "actuals": row.actuals,
        "cost_minor": row.cost_minor,
        "decision_quality": row.decision_quality,
        "failure_kind": row.failure_kind, "lesson": row.lesson,
        "future_implications": row.future_implications,
        "forecast_error": row.forecast_error,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
        "p09_note": "structured learning record for P-09 "
                    "consumption: references and outcomes, not "
                    "copies of other phases' data (§21)",
    }


class ForecastingService:
    def __init__(self, session_factory, financial, monitoring, audit):
        self._session_factory = session_factory
        self._financial = financial
        self._monitoring = monitoring
        self._audit = audit

    def create_forecast(self, principal, business_id: str,
                        data: dict) -> dict:
        kind = data.get("kind") or "survival"
        if kind not in ("survival", "growth"):
            raise ValidationError("forecast kind must be survival or "
                                  "growth")
        scenario = data.get("scenario") or "base"
        if scenario not in SCENARIOS:
            raise ValidationError(f"unknown scenario {scenario!r}")
        reading = self._monitoring.collect(business_id)
        if reading["profile_missing"]:
            raise ValidationError(
                "cannot forecast without a P-07 financial profile: "
                "there are no authoritative readings to build on "
                "(INSUFFICIENT_DATA)")
        indicators = reading["indicators"]
        summary = reading["summary"]
        expected = data.get("expected") or {}
        if not expected:
            raise ValidationError(
                "expected values (the declared scenario expectation) "
                "are required: P-08 does not invent forecast numbers")
        session = self._session_factory()
        try:
            row = SurvivalForecastRepository(session).add(
                SurvivalForecast(
                    business_id=business_id, kind=kind,
                    scenario=scenario,
                    period_label=data.get("period_label") or "next_period",
                    assumptions=data.get("assumptions")
                    or SCENARIO_ASSUMPTIONS[scenario],
                    inputs={
                        "indicators": indicators,
                        "runway": summary.get("runway"),
                        "source": "p07 readings at forecast creation; "
                                  "frozen with the forecast",
                    },
                    expected=expected,
                    confidence=data.get("confidence") or "low",
                    p07_forecast_id=data.get("p07_forecast_id"),
                    created_by=_actor(principal)))
            result = forecast_dict(row)
        finally:
            session.close()
        self._audit(principal, "survival.forecast_created", "business",
                    business_id, "allow",
                    f"{kind}/{scenario} forecast frozen")
        return result

    def list_forecasts(self, *, business_id: str | None = None,
                       limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = SurvivalForecastRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [forecast_dict(r) for r in rows], total
        finally:
            session.close()

    def forecast_vs_actual(self, principal, forecast_id: str) -> dict:
        """Compare a frozen forecast with current readings. Where the
        forecast references a P-07 forecast, the error figures come
        from P-07's own forecast_vs_actual; otherwise the comparison
        is between the frozen declared expectation and the current
        P-07 reading — both reproduced verbatim. The original
        forecast row is never modified (§18.4)."""
        session = self._session_factory()
        try:
            row = SurvivalForecastRepository(session).get(forecast_id)
            if row is None:
                raise NotFoundError(f"forecast {forecast_id} not found")
            forecast = forecast_dict(row)
        finally:
            session.close()
        result: dict = {"forecast": forecast}
        if forecast["p07_forecast_id"]:
            result["p07_comparison"] = self._financial.forecasting \
                .forecast_vs_actual(forecast["p07_forecast_id"])
            result["error_source"] = "p07.forecasting.forecast_vs_actual"
        reading = self._monitoring.collect(forecast["business_id"])
        result["current_reading"] = reading.get("indicators")
        expected_revenue = forecast["expected"].get(
            "collected_revenue_minor")
        actual_revenue = (reading.get("indicators") or {}).get(
            "verified_collected_revenue_minor")
        if expected_revenue is not None and actual_revenue is not None:
            result["comparison"] = {
                "expected_collected_revenue_minor": expected_revenue,
                "actual_collected_revenue_minor": actual_revenue,
                "variance_minor": actual_revenue - expected_revenue,
                "note": "variance between the frozen declared "
                        "expectation and the current P-07 reading; "
                        "the original forecast is unchanged (§18.4)",
            }
        return result

    # ------------------------------------------------------ §21 outcomes
    def record_outcome(self, principal, business_id: str,
                       data: dict) -> dict:
        quality = data.get("decision_quality") or "unrated"
        if quality not in ("sound", "reasonable", "poor", "unrated"):
            raise ValidationError(
                "decision_quality must judge the decision against "
                "the evidence available when it was made: sound / "
                "reasonable / poor / unrated (§21)")
        failure_kind = data.get("failure_kind")
        if failure_kind is not None and \
                failure_kind not in C.FAILURE_KINDS:
            raise ValidationError(
                f"unknown failure kind {failure_kind!r}; supported: "
                f"{C.FAILURE_KINDS}")
        reading = self._monitoring.collect(business_id)
        session = self._session_factory()
        try:
            row = DecisionOutcomeRepository(session).add(
                DecisionOutcome(
                    business_id=business_id,
                    decision_id=data.get("decision_id"),
                    experiment_id=data.get("experiment_id"),
                    problem=data.get("problem") or "",
                    evidence_at_decision=data.get(
                        "evidence_at_decision") or [],
                    expected_outcome=data.get("expected_outcome") or "",
                    actual_outcome=data.get("actual_outcome") or "",
                    actuals=data.get("actuals") or {
                        "indicators": reading.get("indicators"),
                        "source": "p07 readings at outcome time"},
                    cost_minor=data.get("cost_minor"),
                    decision_quality=quality,
                    failure_kind=failure_kind,
                    lesson=data.get("lesson") or "",
                    future_implications=data.get(
                        "future_implications") or "",
                    forecast_error=data.get("forecast_error") or {},
                    created_by=_actor(principal)))
            result = outcome_dict(row)
        finally:
            session.close()
        self._audit(principal, "survival.outcome_recorded", "business",
                    business_id, "allow",
                    f"quality={quality} failure_kind={failure_kind}")
        return result

    def list_outcomes(self, *, business_id: str | None = None,
                      limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = DecisionOutcomeRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [outcome_dict(r) for r in rows], total
        finally:
            session.close()


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}" if principal else "system"
