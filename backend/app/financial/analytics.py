"""Profitability, cash flow, health and risk (§10, §12, §16).

Every metric names its formula and its data requirements. Missing
data yields an explicit ``insufficient_data`` entry — never an
invented value (§10.1). Losses are reported as losses (Scenario 13).
Hard risk conditions override favourable numbers (§12.3)."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from ..database.models.financial import FinancialAlert
from ..database.repositories.financial import (
    AlertRepository, ExpenseRepository, RevenueRepository,
)
from .budgets import BudgetService
from .expenses import ExpenseService
from .ledger import LedgerService
from .revenue import RevenueService

CASH_SUBTYPES = {"cash", "bank", "processor"}


def _ratio(numerator: int, denominator: int) -> str | None:
    if denominator == 0:
        return None
    return str((Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("0.0001")))


def monthly_series(records_dates_amounts: list[tuple[str, int]]) -> dict[str, int]:
    series: dict[str, int] = defaultdict(int)
    for date_str, amount in records_dates_amounts:
        series[date_str[:7]] += amount
    return dict(sorted(series.items()))


class AnalyticsService:
    def __init__(self, session_factory, ledger: LedgerService,
                 revenue: RevenueService, expenses: ExpenseService,
                 budgets: BudgetService, audit, settings_getter):
        self._session_factory = session_factory
        self._ledger = ledger
        self._revenue = revenue
        self._expenses = expenses
        self._budgets = budgets
        self._audit = audit
        self._settings = settings_getter

    # ------------------------------------------------------- profitability
    def profitability(self, business_id: str, currency: str,
                      model: str = "digital_products") -> dict:
        rev = self._revenue.metrics(business_id, currency)
        exp = self._expenses.totals(business_id, currency)
        has_revenue = rev["collected_count"] > 0
        has_expenses = exp["pl_expense_paid_minor"] > 0 or \
            exp["total_paid_minor"] > 0
        missing = []
        if not has_revenue:
            missing.append("no verified collected revenue records")
        if not has_expenses:
            missing.append("no paid expense records")
        net_revenue = rev["net_collected_minor"]
        direct_costs = exp["direct_costs_minor"]
        gross_profit = net_revenue - direct_costs
        operating_expenses = exp["pl_expense_paid_minor"] - direct_costs
        operating_profit = gross_profit - operating_expenses
        result = {
            "business_id": business_id, "currency": currency,
            "model_profile": model,
            "status": "computed" if has_revenue or has_expenses
                      else "insufficient_data",
            "missing_data": missing,
            "gross_revenue_minor": rev["collected_gross_minor"],
            "refunds_minor": rev["refunds_minor"],
            "chargebacks_minor": rev["chargebacks_minor"],
            "net_revenue_minor": net_revenue,
            "direct_costs_minor": direct_costs,
            "gross_profit_minor": gross_profit if has_revenue or has_expenses else None,
            "gross_margin_ratio": _ratio(gross_profit, net_revenue)
            if has_revenue and net_revenue else None,
            "operating_expenses_minor": operating_expenses,
            "operating_profit_minor": operating_profit if has_revenue or has_expenses else None,
            "net_profit_minor": operating_profit if has_revenue or has_expenses else None,
            "net_profit_basis": (
                "net profit = verified net collected revenue − all paid "
                "P&L expenses (cash basis, staging policy); it is null "
                "when neither verified revenue nor expenses exist"),
            "is_loss": bool((has_revenue or has_expenses) and operating_profit < 0),
            "methodology": (
                "gross profit = net revenue − direct costs; operating "
                "profit = gross profit − indirect operating expenses"),
        }
        result["unit_economics"] = self._unit_economics(
            business_id, currency, model, rev, exp)
        result["break_even"] = self._break_even(exp, result)
        return result

    def _break_even(self, exp: dict, profit: dict) -> dict:
        fixed = exp["fixed_minor"]
        net_revenue = profit["net_revenue_minor"] or 0
        variable = exp["variable_minor"]
        if net_revenue <= 0:
            return {"status": "insufficient_data",
                    "reason": "break-even needs positive net revenue to "
                              "derive a contribution margin ratio"}
        cm_ratio = Decimal(net_revenue - variable) / Decimal(net_revenue)
        if cm_ratio <= 0:
            return {"status": "insufficient_data",
                    "reason": "contribution margin is not positive; "
                              "break-even revenue is undefined"}
        break_even = (Decimal(fixed) / cm_ratio).quantize(Decimal(1))
        return {"status": "computed",
                "break_even_revenue_minor": int(break_even),
                "contribution_margin_ratio": str(cm_ratio.quantize(Decimal("0.0001"))),
                "methodology": "break-even revenue = fixed costs / "
                               "contribution margin ratio, where CM ratio "
                               "= (net revenue − variable costs) / net revenue"}

    def _unit_economics(self, business_id: str, currency: str, model: str,
                        rev: dict, exp: dict) -> dict:
        """Model-specific profiles (§10.2): SaaS metrics are never
        applied to a services business and vice versa."""
        if model == "saas":
            session = self._session_factory()
            try:
                from ..database.repositories.financial import SubscriptionRepository
                subs = SubscriptionRepository(session).list(
                    limit=1000, business_id=business_id)[0]
            finally:
                session.close()
            active = [s for s in subs if s.status == "active"]
            cancelled = [s for s in subs if s.status == "cancelled"]
            churn = _ratio(len(cancelled), len(active) + len(cancelled))
            return {
                "profile": "saas",
                "mrr_minor": rev["mrr_minor"], "arr_minor": rev["arr_minor"],
                "active_subscriptions": len(active),
                "churn_ratio": churn if churn is not None else None,
                "churn_status": "computed" if churn is not None
                                else "insufficient_data",
                "gross_margin_ratio": _ratio(
                    (rev["net_collected_minor"] or 0) - exp["direct_costs_minor"],
                    rev["net_collected_minor"]) if rev["net_collected_minor"]
                else None,
            }
        if model == "services":
            return {
                "profile": "services",
                "project_revenue_minor": sum(
                    v for k, v in rev["by_category_minor"].items()
                    if k in ("service_payment", "freelance_project", "consulting")),
                "delivery_costs_minor": exp["direct_costs_minor"],
                "contractor_costs_minor": exp["by_category_minor"].get("contractor", 0),
                "effective_hourly_margin": {
                    "status": "insufficient_data",
                    "reason": "hours are not tracked by AUTONOMUS; an "
                              "hourly margin is never invented (§10.1)"},
            }
        # digital_products (default) and content/affiliate variants
        collected = rev["collected_count"]
        refunds_count_note = rev["refunds_minor"]
        return {
            "profile": model,
            "sales_volume": collected,
            "average_selling_price_minor": rev["average_order_value_minor"],
            "marketplace_commission_minor": exp["by_category_minor"].get(
                "marketplace_fee", 0),
            "payment_processing_fees_minor": exp["by_category_minor"].get(
                "payment_processing", 0),
            "production_cost_minor": exp["by_category_minor"].get(
                "content_production", 0),
            "refund_rate_ratio": _ratio(rev["refunds_minor"],
                                        rev["collected_gross_minor"])
            if rev["collected_gross_minor"] else None,
            "refunds_total_minor": refunds_count_note,
            "contribution_margin_minor": (
                rev["net_collected_minor"] - exp["direct_costs_minor"]),
        }

    # ------------------------------------------------------------ cash flow
    def cashflow(self, business_id: str, currency: str, *,
                 start: str, end: str) -> dict:
        """Actual cash flow from journal lines on cash/bank/processor
        accounts. Forecast figures live in a separate block and are
        never merged into actuals (§12.1)."""
        session = self._session_factory()
        try:
            from ..database.repositories.financial import (
                AccountRepository, JournalRepository,
            )
            accounts = {a.id: a for a in
                        AccountRepository(session).for_business(business_id)}
            entries = JournalRepository(session).for_business(business_id,
                                                              limit=100000)
            lines = JournalRepository(session).all_lines_for_business(business_id)
        finally:
            session.close()
        lines_by_entry: dict[str, list] = defaultdict(list)
        for line in lines:
            lines_by_entry[line.entry_id].append(line)
        opening = 0
        inflow = 0
        outflow = 0
        for entry in entries:
            cash_delta = sum(
                line.debit_minor - line.credit_minor
                for line in lines_by_entry.get(entry.id, [])
                if accounts.get(line.account_id) is not None
                and accounts[line.account_id].subtype in CASH_SUBTYPES
                and line.currency == currency)
            if entry.entry_date < start:
                opening += cash_delta
            elif entry.entry_date <= end:
                if cash_delta > 0:
                    inflow += cash_delta
                else:
                    outflow += -cash_delta
        available = self._budgets.available_cash(business_id, currency)
        return {
            "business_id": business_id, "currency": currency,
            "period": {"start": start, "end": end}, "basis": "actual",
            "opening_cash_minor": opening, "cash_inflows_minor": inflow,
            "cash_outflows_minor": outflow,
            "net_cash_flow_minor": inflow - outflow,
            "closing_cash_minor": opening + inflow - outflow,
            "available_cash": available,
            "forecast_block": {
                "basis": "forecast — kept separate from actuals",
                "committed_future_payments_minor": available["committed_minor"],
                "expected_inflows_note": "uncollected invoices are NOT "
                                         "counted as expected cash (§12.2)",
                "outstanding_receivables_minor":
                    self._revenue.metrics(business_id, currency)
                    ["outstanding_receivables_minor"],
            },
        }

    # --------------------------------------------------------------- runway
    def runway(self, business_id: str, currency: str) -> dict:
        session = self._session_factory()
        try:
            expenses = ExpenseRepository(session).for_business(business_id)
        finally:
            session.close()
        paid_pl = [e for e in expenses if e.currency == currency
                   and e.payment_status == "paid"
                   and e.kind in ("operating_expense", "direct_cost",
                                  "capital_expense", "refund_loss",
                                  "tax_payment")]
        series = monthly_series([(e.expense_date, e.amount_minor)
                                 for e in paid_pl])
        available = self._budgets.available_cash(business_id, currency)
        available_minor = available["available_cash_minor"]
        if not series:
            return {"business_id": business_id, "currency": currency,
                    "status": "insufficient_data",
                    "reason": "no paid expense history; burn cannot be "
                              "estimated and runway is not invented",
                    "available_cash_minor": available_minor}
        months = len(series)
        total_burn = sum(series.values())
        avg_burn = Decimal(total_burn) / Decimal(months)
        if avg_burn <= 0:
            return {"business_id": business_id, "currency": currency,
                    "status": "not_applicable",
                    "reason": "average operating burn is zero; a runway "
                              "figure would be misleading (no negative "
                              "or infinite runway is reported, §12.2)",
                    "available_cash_minor": available_minor}
        months_value = (Decimal(available_minor) / avg_burn).quantize(
            Decimal("0.01"))
        return {
            "business_id": business_id, "currency": currency,
            "status": "preliminary" if months < 3 else "computed",
            "preliminary": months < 3,
            "history_months": months,
            "average_monthly_burn_minor": int(avg_burn),
            "available_cash_minor": available_minor,
            "runway_months": str(months_value),
            "methodology": "runway = available cash (§9.4 formula, "
                           "reserves and commitments already excluded) / "
                           "average monthly paid P&L burn over the "
                           "recorded history; uncollected invoices are "
                           "never treated as cash",
        }

    # --------------------------------------------------------------- health
    def health(self, business_id: str, currency: str) -> dict:
        rev = self._revenue.metrics(business_id, currency)
        exp = self._expenses.totals(business_id, currency)
        available = self._budgets.available_cash(business_id, currency)
        runway = self.runway(business_id, currency)
        thresholds = self._settings().get("health_thresholds", {})
        reasons: list[str] = []
        has_any_data = (rev["collected_count"] > 0
                         or exp["total_paid_minor"] > 0
                         or available["cash_balance_minor"] > 0)
        if not has_any_data:
            return {"business_id": business_id, "currency": currency,
                    "status": "INSUFFICIENT_DATA",
                    "reasons": ["no verified revenue, no expenses and no "
                                "cash balance records exist"],
                    "missing_data": ["verified collected revenue",
                                     "expense records", "cash balances"],
                    "components": {"revenue": rev, "available_cash": available}}
        status = "STABLE"
        if rev["net_collected_minor"] > exp["pl_expense_paid_minor"] > 0 \
                or (rev["net_collected_minor"] > 0
                    and exp["pl_expense_paid_minor"] == 0):
            status = "HEALTHY"
            reasons.append("verified net collected revenue exceeds paid expenses")
        if available["available_cash_minor"] < 0:
            status = "CRITICAL"
            reasons.append("available cash is negative after reserves, "
                           "commitments and obligations (hard override)")
        elif available["obligations_minor"] > available["cash_balance_minor"] \
                and available["cash_balance_minor"] >= 0:
            status = "AT_RISK"
            reasons.append("known obligations exceed the cash balance "
                           "(hard override — projected revenue does not "
                           "make this business healthy, §12.3)")
        runway_months = runway.get("runway_months")
        if runway_months is not None:
            value = Decimal(runway_months)
            critical = Decimal(str(thresholds.get("critical_runway_months", 1)))
            at_risk = Decimal(str(thresholds.get("at_risk_runway_months", 3)))
            watch = Decimal(str(thresholds.get("watch_runway_months", 6)))
            if value < critical:
                status = "CRITICAL"
                reasons.append(f"runway {value} months < {critical} (critical)")
            elif value < at_risk and status not in ("CRITICAL",):
                status = "AT_RISK"
                reasons.append(f"runway {value} months < {at_risk}")
            elif value < watch and status in ("HEALTHY", "STABLE"):
                status = "WATCH"
                reasons.append(f"runway {value} months < {watch}")
        gross = rev["collected_gross_minor"]
        if gross > 0:
            refund_rate = Decimal(rev["refunds_minor"]) / Decimal(gross)
            if refund_rate > Decimal(str(thresholds.get("high_refund_rate", "0.10"))):
                if status in ("HEALTHY", "STABLE"):
                    status = "WATCH"
                reasons.append(f"refund rate {refund_rate} exceeds the "
                               "configured threshold")
            chargeback_rate = Decimal(rev["chargebacks_minor"]) / Decimal(gross)
            if chargeback_rate > Decimal(str(thresholds.get("high_chargeback_rate", "0.02"))):
                status = "AT_RISK" if status != "CRITICAL" else status
                reasons.append(f"chargeback rate {chargeback_rate} exceeds "
                               "the configured threshold")
        if exp["pl_expense_paid_minor"] > rev["net_collected_minor"] \
                and rev["collected_count"] > 0:
            if status == "HEALTHY":
                status = "STABLE"
            reasons.append("the business is loss-making on verified figures "
                           "(reported as a loss, never reclassified)")
        return {"business_id": business_id, "currency": currency,
                "status": status, "reasons": reasons,
                "components": {"revenue": rev, "expenses": exp,
                               "available_cash": available, "runway": runway}}

    # ----------------------------------------------------------------- risk
    def run_risk_scan(self, principal, business_id: str, currency: str) -> dict:
        """Deterministic threshold scan (§16). Alerts are signals for
        investigation — never accusations of fraud."""
        settings = self._settings()
        thresholds = settings.get("risk_thresholds", {})
        created: list[dict] = []

        def emit(alert_type, severity, title, impact, evidence, method,
                 action, dedupe_suffix):
            session = self._session_factory()
            try:
                repo = AlertRepository(session)
                key = f"{business_id}:{alert_type}:{dedupe_suffix}"
                if repo.open_by_dedupe(key) is not None:
                    return
                row = FinancialAlert(
                    business_id=business_id, alert_type=alert_type,
                    severity=severity, title=title, impact=impact,
                    evidence=evidence, detection_method=method,
                    recommended_action=action, human_review_required=True,
                    status="open", dedupe_key=key,
                    created_by="system:risk_engine")
                repo.add(row)
                session.expunge(row)
                created.append(alert_dict(row))
            finally:
                session.close()

        session = self._session_factory()
        try:
            expenses = ExpenseRepository(session).for_business(business_id)
            revenues = RevenueRepository(session).for_business(business_id)
        finally:
            session.close()
        paid = [e for e in expenses if e.currency == currency
                and e.payment_status == "paid"]
        # sudden expense increase (needs >= 2 months)
        series = monthly_series([(e.expense_date, e.amount_minor)
                                 for e in paid])
        months = sorted(series)
        if len(months) >= 2:
            prev, latest = series[months[-2]], series[months[-1]]
            ratio = Decimal(str(thresholds.get("expense_spike_ratio", "1.5")))
            if prev > 0 and Decimal(latest) > Decimal(prev) * ratio:
                emit("expense_spike", "high",
                     f"Expenses spiked in {months[-1]}",
                     {"amount_minor": latest - prev, "currency": currency},
                     {"previous_month": months[-2], "previous_minor": prev,
                      "latest_month": months[-1], "latest_minor": latest},
                     "deterministic threshold: latest month > previous "
                     f"month × {ratio}",
                     "Review the largest expense categories for the month.",
                     months[-1])
        # duplicate charges
        seen: dict[tuple, object] = {}
        for expense in sorted(paid, key=lambda e: e.expense_date):
            key = (expense.vendor, expense.amount_minor, expense.currency)
            prior = seen.get(key)
            if prior is not None:
                gap = abs((dt.date.fromisoformat(expense.expense_date)
                           - dt.date.fromisoformat(prior.expense_date)).days)
                if gap <= 7:
                    emit("duplicate_charge", "medium",
                         "Possible duplicate charge detected",
                         {"amount_minor": expense.amount_minor,
                          "currency": currency},
                         {"expense_ids": [prior.id, expense.id],
                          "vendor": expense.vendor, "gap_days": gap},
                         "same vendor + amount within 7 days",
                         "Verify with the vendor whether both charges are "
                         "legitimate; this is a signal, not an accusation.",
                         f"{expense.vendor}:{expense.amount_minor}:{expense.expense_date}")
            seen[key] = expense
        # unusual transaction size
        amounts = sorted(e.amount_minor for e in paid)
        if len(amounts) >= 4:
            median = amounts[len(amounts) // 2]
            multiplier = Decimal(str(thresholds.get(
                "unusual_amount_multiplier", "5")))
            for expense in paid:
                if median > 0 and Decimal(expense.amount_minor) > \
                        Decimal(median) * multiplier:
                    emit("unusual_transaction", "medium",
                         "Unusually large expense",
                         {"amount_minor": expense.amount_minor,
                          "currency": currency},
                         {"expense_id": expense.id, "median_minor": median},
                         f"amount > median × {multiplier}",
                         "Confirm the expense was intended and correctly "
                         "categorised.", expense.id)
        # budget overruns
        budgets, _ = self._budgets.list_budgets(business_id=business_id,
                                                limit=200)
        for budget in budgets:
            utilisation = self._budgets.budget_utilisation(budget["id"])
            if utilisation["over_budget"]:
                emit("budget_overrun", "high",
                     f"Budget {budget['name']} is over its approved amount",
                     {"amount_minor": -utilisation["remaining_minor"],
                      "currency": budget["currency"]},
                     {"budget_id": budget["id"],
                      "utilisation": utilisation["utilisation_ratio"]},
                     "deterministic: spent + committed > approved",
                     "Owner review: raise the budget through approval or "
                     "stop further commitments.", budget["id"])
        # refund / chargeback rates
        rev = self._revenue.metrics(business_id, currency)
        gross = rev["collected_gross_minor"]
        health_thresholds = settings.get("health_thresholds", {})
        if gross > 0:
            refund_rate = Decimal(rev["refunds_minor"]) / Decimal(gross)
            if refund_rate > Decimal(str(health_thresholds.get(
                    "high_refund_rate", "0.10"))):
                emit("high_refund_rate", "high", "Refund rate is high",
                     {"amount_minor": rev["refunds_minor"], "currency": currency},
                     {"refund_rate": str(refund_rate)},
                     "deterministic threshold on verified collected revenue",
                     "Investigate product quality / listing accuracy.",
                     "current")
            chargeback_rate = Decimal(rev["chargebacks_minor"]) / Decimal(gross)
            if chargeback_rate > Decimal(str(health_thresholds.get(
                    "high_chargeback_rate", "0.02"))):
                emit("high_chargeback_rate", "critical",
                     "Chargeback rate is high",
                     {"amount_minor": rev["chargebacks_minor"],
                      "currency": currency},
                     {"chargeback_rate": str(chargeback_rate)},
                     "deterministic threshold on verified collected revenue",
                     "Review payment descriptors and dispute evidence.",
                     "current")
        # revenue concentration
        by_channel = rev["by_channel_minor"]
        if gross > 0 and by_channel:
            top_channel, top_amount = max(by_channel.items(),
                                          key=lambda kv: kv[1])
            share = Decimal(top_amount) / Decimal(gross)
            if share > Decimal(str(thresholds.get(
                    "revenue_concentration", "0.80"))):
                emit("revenue_concentration", "medium",
                     f"Revenue concentrated in channel {top_channel}",
                     {"amount_minor": top_amount, "currency": currency},
                     {"channel": top_channel, "share": str(share)},
                     "deterministic threshold on collected revenue by channel",
                     "Consider diversifying distribution channels.", "current")
        return {"business_id": business_id, "alerts_created": created,
                "alerts_created_count": len(created)}

    def list_alerts(self, business_id: str | None, limit: int = 50,
                    offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            rows, total = AlertRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [alert_dict(r) for r in rows], total
        finally:
            session.close()


def alert_dict(row: FinancialAlert) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "alert_type": row.alert_type, "severity": row.severity,
            "title": row.title, "impact": row.impact,
            "evidence": row.evidence, "detection_method": row.detection_method,
            "recommended_action": row.recommended_action,
            "human_review_required": row.human_review_required,
            "status": row.status, "created_by": row.created_by,
            "classification": "signal requiring investigation — not an "
                              "accusation of fraud (§16)"}
