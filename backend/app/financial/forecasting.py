"""Forecasting & scenarios (§11). Deterministic methods only — no
LLM ever calculates a financial figure. Forecasts are frozen at
creation (§11.4): variance is computed against the stored forecast,
which is never rewritten. An optimistic scenario is a projection and
is never labelled expected income."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from ..core.exceptions import ValidationError
from ..database.models.financial import FinancialForecast, FinancialScenario
from ..database.repositories.financial import (
    ExpenseRepository, ForecastRepository, RevenueRepository,
    ScenarioRepository,
)
from .analytics import monthly_series
from .budgets import BudgetService


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}"


def _next_month(label: str) -> tuple[str, str, str]:
    year, month = int(label[:4]), int(label[5:7])
    month += 1
    if month == 13:
        year, month = year + 1, 1
    start = dt.date(year, month, 1)
    end = (start + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
    return f"{year:04d}-{month:02d}", start.isoformat(), end.isoformat()


def _average(values: list[int]) -> int:
    if not values:
        return 0
    return int((Decimal(sum(values)) / Decimal(len(values))).quantize(Decimal(1)))


def _trend_next(values: list[int]) -> int:
    """Least-squares linear trend over the monthly series, Decimal
    arithmetic throughout; projects one step ahead."""
    n = len(values)
    if n == 0:
        return 0
    if n == 1:
        return values[0]
    xs = [Decimal(i) for i in range(n)]
    ys = [Decimal(v) for v in values]
    mean_x = sum(xs) / Decimal(n)
    mean_y = sum(ys) / Decimal(n)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator = sum((x - mean_x) ** 2 for x in xs)
    slope = numerator / denominator if denominator != 0 else Decimal(0)
    intercept = mean_y - slope * mean_x
    projected = intercept + slope * Decimal(n)
    return max(0, int(projected.quantize(Decimal(1))))


class ForecastingService:
    def __init__(self, session_factory, budgets: BudgetService, audit):
        self._session_factory = session_factory
        self._budgets = budgets
        self._audit = audit

    def _series(self, business_id: str, currency: str,
                forecast_type: str) -> dict[str, int]:
        session = self._session_factory()
        try:
            if forecast_type in ("revenue", "cashflow"):
                records = RevenueRepository(session).for_business(business_id)
                pairs = [(r.transaction_date, r.amount_minor) for r in records
                         if r.currency == currency
                         and r.verification_status == "verified"
                         and r.classification in ("collected", "recognized")
                         and not r.is_internal_transfer]
                gross = monthly_series(pairs)
                refunds = [(r.transaction_date, 0) for r in records]
                del refunds
                return gross
            expenses = ExpenseRepository(session).for_business(business_id)
            pairs = [(e.expense_date, e.amount_minor) for e in expenses
                     if e.currency == currency and e.payment_status == "paid"
                     and e.kind in ("operating_expense", "direct_cost",
                                    "capital_expense", "refund_loss",
                                    "tax_payment")]
            return monthly_series(pairs)
        finally:
            session.close()

    def create_forecast(self, principal, business_id: str, data: dict) -> dict:
        forecast_type = data["forecast_type"]
        method = data.get("method", "historical_average")
        currency = data["currency"]
        if forecast_type not in ("revenue", "expense", "cashflow"):
            raise ValidationError(f"unknown forecast type {forecast_type!r}")
        if method not in ("historical_average", "moving_average", "trend"):
            raise ValidationError(f"unknown forecast method {method!r}")
        revenue_series = self._series(business_id, currency, "revenue")
        expense_series = self._series(business_id, currency, "expense")
        series = (revenue_series if forecast_type == "revenue"
                  else expense_series)
        months = sorted(series)
        values = [series[m] for m in months]
        if forecast_type == "cashflow":
            all_months = sorted(set(revenue_series) | set(expense_series))
            values = [revenue_series.get(m, 0) - expense_series.get(m, 0)
                      for m in all_months]
            months = all_months
        window = values[-3:] if method == "moving_average" else values
        if method == "trend":
            projected = _trend_next(values)
        else:
            projected = _average(window)
        if months:
            label, start, end = _next_month(months[-1])
        else:
            today = dt.date.today()
            label, start, end = _next_month(
                f"{today.year:04d}-{today.month:02d}")
        confidence = ("high" if len(values) >= 6 else
                      "medium" if len(values) >= 3 else "low")
        assumptions = [
            f"method={method} over {len(values)} month(s) of actuals",
            "forecasts are projections from historical actuals, not "
            "expected income (§11.3)",
        ]
        if not values:
            assumptions.append("no historical actuals exist; the projected "
                               "value is 0 and confidence is low — this is "
                               "an absence of data, not a prediction")
            confidence = "low"
        session = self._session_factory()
        try:
            row = FinancialForecast(
                business_id=business_id, forecast_type=forecast_type,
                method=method, period_label=label, period_start=start,
                period_end=end,
                values={"amount_minor": projected, "currency": currency,
                        "history_months": months,
                        "history_values_minor": values},
                assumptions=assumptions, confidence=confidence,
                created_by=_actor(principal))
            ForecastRepository(session).add(row)
            session.expunge(row)
            return forecast_dict(row)
        finally:
            session.close()

    def forecast_vs_actual(self, forecast_id: str) -> dict:
        session = self._session_factory()
        try:
            row = ForecastRepository(session).get(forecast_id)
            if row is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError(f"forecast {forecast_id} not found")
            session.expunge(row)
            forecast = forecast_dict(row)
        finally:
            session.close()
        currency = forecast["values"]["currency"]
        series = self._series(forecast["business_id"], currency,
                              forecast["forecast_type"])
        if forecast["forecast_type"] == "cashflow":
            revenue_series = self._series(forecast["business_id"], currency,
                                          "revenue")
            actual = revenue_series.get(forecast["period_label"], 0) \
                - series.get(forecast["period_label"], 0)
        else:
            actual = series.get(forecast["period_label"])
        projected = forecast["values"]["amount_minor"]
        if actual is None:
            return {**forecast, "actual_minor": None,
                    "status": "period_not_recorded_yet",
                    "note": "no actuals recorded for the forecast period; "
                            "the frozen forecast is unchanged (§11.4)"}
        variance = actual - projected
        error_ratio = (str((Decimal(abs(variance)) / Decimal(projected)
                            ).quantize(Decimal("0.0001")))
                       if projected else None)
        return {**forecast, "actual_minor": actual,
                "variance_minor": variance,
                "forecast_error_ratio": error_ratio,
                "status": "compared",
                "note": "variance is computed against the frozen forecast; "
                        "the forecast itself is never rewritten (§11.4)"}

    # ------------------------------------------------------------- scenarios
    def create_scenario(self, principal, business_id: str, data: dict) -> dict:
        scenario_type = data["scenario_type"]
        if scenario_type not in ("conservative", "base", "optimistic"):
            raise ValidationError(f"unknown scenario type {scenario_type!r}")
        label = data.get("display_label") or f"{scenario_type} scenario"
        if scenario_type == "optimistic" and "expected" in label.lower():
            raise ValidationError(
                "an optimistic scenario may never be labelled expected "
                "income (§11.3)")
        if scenario_type == "optimistic":
            label = f"{label} (projection — not expected income)"
        currency = data["currency"]
        revenue_series = self._series(business_id, currency, "revenue")
        expense_series = self._series(business_id, currency, "expense")
        base_revenue = _average(list(revenue_series.values()))
        base_expenses = _average(list(expense_series.values()))
        defaults = {
            "conservative": ("0.80", "1.10"),
            "base": ("1.00", "1.00"),
            "optimistic": ("1.25", "0.95"),
        }
        revenue_factor = Decimal(str(data.get(
            "revenue_factor", defaults[scenario_type][0])))
        expense_factor = Decimal(str(data.get(
            "expense_factor", defaults[scenario_type][1])))
        expected_revenue = int((Decimal(base_revenue) * revenue_factor
                                ).quantize(Decimal(1)))
        expected_expenses = int((Decimal(base_expenses) * expense_factor
                                 ).quantize(Decimal(1)))
        available = self._budgets.available_cash(business_id, currency)
        cash_requirement = max(0, expected_expenses
                               - available["available_cash_minor"])
        results = {
            "currency": currency,
            "base_monthly_revenue_minor": base_revenue,
            "base_monthly_expenses_minor": base_expenses,
            "expected_revenue_minor": expected_revenue,
            "expected_expenses_minor": expected_expenses,
            "expected_profit_minor": expected_revenue - expected_expenses,
            "cash_requirement_minor": cash_requirement,
            "break_even_note": "see the profitability break-even figure; "
                               "scenario break-even uses the same fixed-cost "
                               "data and is not recomputed differently here",
        }
        session = self._session_factory()
        try:
            row = FinancialScenario(
                business_id=business_id, scenario_type=scenario_type,
                display_label=label,
                assumptions={
                    "revenue_factor": str(revenue_factor),
                    "expense_factor": str(expense_factor),
                    "basis": "average monthly verified actuals",
                    **(data.get("assumptions") or {})},
                results=results, risks=data.get("risks") or [],
                confidence=data.get("confidence", "low"),
                created_by=_actor(principal))
            ScenarioRepository(session).add(row)
            session.expunge(row)
            return scenario_dict(row)
        finally:
            session.close()

    def list_scenarios(self, business_id: str) -> list[dict]:
        session = self._session_factory()
        try:
            rows, _ = ScenarioRepository(session).list(
                limit=100, business_id=business_id)
            return [scenario_dict(r) for r in rows]
        finally:
            session.close()

    def list_forecasts(self, business_id: str) -> list[dict]:
        session = self._session_factory()
        try:
            rows, _ = ForecastRepository(session).list(
                limit=100, business_id=business_id)
            return [forecast_dict(r) for r in rows]
        finally:
            session.close()


def forecast_dict(row: FinancialForecast) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "forecast_type": row.forecast_type, "method": row.method,
            "period_label": row.period_label, "period_start": row.period_start,
            "period_end": row.period_end, "values": row.values,
            "assumptions": row.assumptions, "confidence": row.confidence,
            "created_by": row.created_by,
            "frozen": True,
            "created_at": row.created_at.isoformat() if row.created_at else None}


def scenario_dict(row: FinancialScenario) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "scenario_type": row.scenario_type,
            "display_label": row.display_label,
            "assumptions": row.assumptions, "results": row.results,
            "risks": row.risks, "confidence": row.confidence,
            "created_by": row.created_by}
