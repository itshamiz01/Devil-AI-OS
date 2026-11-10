"""AI Financial Analyst — deterministic structured interface (§17).

There is NO LLM in staging (carried P-02 limitation), so this module
implements the honest core of §17: a structured query interface over
the same deterministic calculations the reports use. Every figure in
an answer is classified per §17.2 — verified fact / calculated
metric / forecast / assumption / missing — and cites its underlying
records. The natural-language conversational layer is NOT
IMPLEMENTED and is reported as such; nothing here generates prose
that could invent a figure, and there is no path from this module to
any ledger write (§25: P-02 may query, never modify)."""
from __future__ import annotations

import datetime as dt

from ..core.exceptions import ValidationError
from .analytics import AnalyticsService
from .budgets import BudgetService
from .expenses import ExpenseService
from .revenue import RevenueService

INTENTS = {
    "collected_revenue", "profitability", "committed_capital",
    "break_even", "runway", "cash_shortage_risk", "budget_overruns",
    "losing_businesses", "highest_collected_revenue",
    "subscriptions_review", "expense_overview",
}


def _figure(label: str, value, currency: str, classification: str,
            source: str) -> dict:
    return {"label": label, "value_minor": value, "currency": currency,
            "classification": classification, "source": source}


class FinancialAnalyst:
    def __init__(self, revenue: RevenueService, expenses: ExpenseService,
                 budgets: BudgetService, analytics: AnalyticsService):
        self._revenue = revenue
        self._expenses = expenses
        self._budgets = budgets
        self._analytics = analytics

    def answer(self, query: dict, *, businesses: list[str]) -> dict:
        intent = query.get("intent")
        if intent not in INTENTS:
            raise ValidationError(
                f"unknown analyst intent {intent!r}; supported: "
                f"{sorted(INTENTS)}")
        currency = query.get("currency", "INR")
        business_id = query.get("business_id")
        figures: list[dict] = []
        missing: list[str] = []
        recommendations: list[str] = []
        answer: dict = {"intent": intent}

        if intent in ("collected_revenue", "profitability", "break_even",
                      "runway", "committed_capital", "expense_overview",
                      "subscriptions_review"):
            if not business_id:
                raise ValidationError(f"intent {intent} requires business_id")
        if intent == "collected_revenue":
            metrics = self._revenue.metrics(business_id, currency)
            figures.append(_figure(
                "verified net collected revenue",
                metrics["net_collected_minor"], currency, "verified_fact",
                "revenue_records (verified) − refunds − chargebacks"))
            figures.append(_figure(
                "projected revenue (NOT collected)",
                metrics["projected_minor"], currency, "forecast",
                "revenue_records classification=projected"))
            answer["metrics"] = metrics
        elif intent == "profitability":
            profit = self._analytics.profitability(business_id, currency)
            figures.append(_figure(
                "net profit (verified basis)", profit["net_profit_minor"],
                currency,
                "calculated_metric" if profit["net_profit_minor"] is not None
                else "missing",
                "analytics.profitability"))
            missing.extend(profit["missing_data"])
            answer["profitability"] = profit
            if profit.get("is_loss"):
                recommendations.append(
                    "The business is loss-making on verified figures; "
                    "review direct costs before any new commitments.")
        elif intent == "break_even":
            profit = self._analytics.profitability(business_id, currency)
            answer["break_even"] = profit["break_even"]
            if profit["break_even"]["status"] == "computed":
                figures.append(_figure(
                    "break-even revenue",
                    profit["break_even"]["break_even_revenue_minor"],
                    currency, "calculated_metric", "analytics.profitability"))
            else:
                missing.append(profit["break_even"]["reason"])
        elif intent == "runway":
            runway = self._analytics.runway(business_id, currency)
            answer["runway"] = runway
            if runway.get("runway_months") is not None:
                figures.append({
                    "label": "runway (months)",
                    "value": runway["runway_months"], "currency": currency,
                    "classification": "calculated_metric",
                    "source": "analytics.runway"})
                if runway.get("preliminary"):
                    missing.append("runway is preliminary: fewer than 3 "
                                   "months of expense history")
            else:
                missing.append(runway.get("reason", "runway unavailable"))
        elif intent == "committed_capital":
            available = self._budgets.available_cash(business_id, currency)
            figures.append(_figure(
                "committed capital", available["committed_minor"], currency,
                "calculated_metric", "budgets.available_cash"))
            figures.append(_figure(
                "protected reserves (not spendable)",
                available["protected_reserves_minor"], currency,
                "verified_fact", "financial_reserves"))
            answer["available_cash"] = available
        elif intent == "expense_overview":
            totals = self._expenses.totals(business_id, currency)
            recurring = self._expenses.detect_recurring(business_id)
            figures.append(_figure(
                "paid P&L expenses", totals["pl_expense_paid_minor"],
                currency, "verified_fact", "expense_records (paid)"))
            answer["totals"] = totals
            answer["recurring_detected"] = recurring
            for group in recurring:
                if group["amount_changed"]:
                    recommendations.append(
                        f"Recurring charge from {group['vendor']} changed "
                        "amount — owner confirmation recommended (§8.3).")
        elif intent == "subscriptions_review":
            recurring = self._expenses.detect_recurring(business_id)
            answer["recurring_expenses"] = recurring
            recommendations.append(
                "Detected recurring charges are suggestions until the "
                "owner confirms them (§8.3).")
        elif intent == "losing_businesses":
            losers = []
            for bid in businesses:
                profit = self._analytics.profitability(bid, currency)
                if profit.get("is_loss"):
                    losers.append({"business_id": bid,
                                   "net_profit_minor": profit["net_profit_minor"]})
                    figures.append(_figure(
                        f"net profit {bid}", profit["net_profit_minor"],
                        currency, "calculated_metric",
                        "analytics.profitability"))
            answer["losing_businesses"] = losers
            if not losers:
                answer["note"] = "no business is loss-making on verified figures"
        elif intent == "highest_collected_revenue":
            ranked = []
            for bid in businesses:
                metrics = self._revenue.metrics(bid, currency)
                ranked.append({"business_id": bid,
                               "net_collected_minor": metrics["net_collected_minor"]})
            ranked.sort(key=lambda r: -r["net_collected_minor"])
            answer["ranking"] = ranked
            if ranked:
                figures.append(_figure(
                    "highest verified net collected revenue",
                    ranked[0]["net_collected_minor"], currency,
                    "verified_fact", "revenue_records (verified)"))
        elif intent == "cash_shortage_risk":
            at_risk = []
            for bid in businesses:
                health = self._analytics.health(bid, currency)
                if health["status"] in ("AT_RISK", "CRITICAL", "WATCH"):
                    at_risk.append({"business_id": bid,
                                    "status": health["status"],
                                    "reasons": health["reasons"]})
            answer["businesses_at_risk"] = at_risk
            if at_risk:
                recommendations.append(
                    "Review AT_RISK/CRITICAL businesses before authorising "
                    "new spending.")
        elif intent == "budget_overruns":
            overruns = []
            budgets, _ = self._budgets.list_budgets(limit=500)
            for budget in budgets:
                utilisation = self._budgets.budget_utilisation(budget["id"])
                if utilisation["over_budget"]:
                    overruns.append(utilisation)
                    figures.append(_figure(
                        f"overrun {budget['name']}",
                        -utilisation["remaining_minor"], budget["currency"],
                        "calculated_metric", "budgets.budget_utilisation"))
            answer["overrun_budgets"] = overruns

        return {
            **answer,
            "figures": figures,
            "missing_information": missing,
            "recommendations": recommendations,
            "provenance": {
                "engine": "deterministic calculations only; no LLM is "
                          "involved (§17.1 boundaries enforced by design)",
                "calculated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "natural_language_layer": "NOT IMPLEMENTED — no LLM "
                                          "exists in staging",
            },
        }
