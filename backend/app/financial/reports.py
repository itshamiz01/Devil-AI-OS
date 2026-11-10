"""Financial reports & exports (§24). Reports are management
information — never labelled audited financial statements. Every
export carries currency, period, accounting basis, methodology,
data freshness and verification metadata. CSV + JSON are supported;
PDF is NOT IMPLEMENTED (stdlib-only constraint, P-05 precedent)."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json

from ..core.exceptions import ValidationError
from ..database.repositories.financial import (
    AccountRepository, JournalRepository,
    ReconciliationItemRepository, ReconciliationSessionRepository,
)
from .analytics import AnalyticsService
from .budgets import BudgetService
from .ledger import LedgerService
from .revenue import RevenueService

NOTICE = ("Management information only — not audited financial "
          "statements. Figures are classified per the §3.1 truth "
          "hierarchy; projected and collected amounts are never merged.")


def _meta(report: str, currency: str, basis: str, methodology: str,
          period: dict | None = None) -> dict:
    return {
        "report": report, "currency": currency, "accounting_basis": basis,
        "methodology": methodology, "period": period,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "verification_status": "computed from stored records at "
                               "generation time",
        "notice": NOTICE,
    }


class ReportService:
    def __init__(self, session_factory, ledger: LedgerService,
                 revenue: RevenueService, budgets: BudgetService,
                 analytics: AnalyticsService):
        self._session_factory = session_factory
        self._ledger = ledger
        self._revenue = revenue
        self._budgets = budgets
        self._analytics = analytics

    # ------------------------------------------------------------ P&L
    def profit_loss(self, business_id: str, currency: str, *,
                    start: str | None = None, end: str | None = None) -> dict:
        session = self._session_factory()
        try:
            accounts = {a.id: a for a in
                        AccountRepository(session).for_business(business_id)}
            entries = JournalRepository(session).for_business(business_id,
                                                              limit=100000)
            lines = JournalRepository(session).all_lines_for_business(business_id)
        finally:
            session.close()
        entry_dates = {e.id: e.entry_date for e in entries}
        entry_transfer = {e.id: e.is_internal_transfer for e in entries}
        income: dict[str, int] = {}
        expenses: dict[str, int] = {}
        for line in lines:
            if line.currency != currency:
                continue
            date = entry_dates.get(line.entry_id, "")
            if start and date < start:
                continue
            if end and date > end:
                continue
            if entry_transfer.get(line.entry_id):
                continue  # internal transfers are never revenue (§18)
            account = accounts.get(line.account_id)
            if account is None:
                continue
            if account.account_type == "income":
                income[account.name] = income.get(account.name, 0) \
                    + line.credit_minor - line.debit_minor
            elif account.account_type == "expense":
                expenses[account.name] = expenses.get(account.name, 0) \
                    + line.debit_minor - line.credit_minor
        total_income = sum(income.values())
        total_expenses = sum(expenses.values())
        return {
            **_meta("profit_loss", currency, "accrual (journal-based)",
                    "income = Σ(credit−debit) on income accounts; "
                    "expenses = Σ(debit−credit) on expense accounts; "
                    "internal-transfer entries excluded",
                    {"start": start, "end": end}),
            "business_id": business_id,
            "income_lines_minor": income,
            "expense_lines_minor": expenses,
            "total_income_minor": total_income,
            "total_expenses_minor": total_expenses,
            "net_profit_minor": total_income - total_expenses,
        }

    # ----------------------------------------------------- balance sheet
    def balance_sheet(self, business_id: str, currency: str, *,
                      as_of: str | None = None) -> dict:
        session = self._session_factory()
        try:
            accounts = {a.id: a for a in
                        AccountRepository(session).for_business(business_id)}
            entries = JournalRepository(session).for_business(business_id,
                                                              limit=100000)
            lines = JournalRepository(session).all_lines_for_business(business_id)
        finally:
            session.close()
        entry_dates = {e.id: e.entry_date for e in entries}
        totals: dict[str, dict[str, int]] = {}
        for line in lines:
            if line.currency != currency:
                continue
            if as_of and entry_dates.get(line.entry_id, "") > as_of:
                continue
            bucket = totals.setdefault(line.account_id,
                                       {"debit": 0, "credit": 0})
            bucket["debit"] += line.debit_minor
            bucket["credit"] += line.credit_minor
        sections: dict[str, list[dict]] = {
            "assets": [], "liabilities": [], "equity": []}
        retained = 0
        for account_id, account in accounts.items():
            bucket = totals.get(account_id, {"debit": 0, "credit": 0})
            if account.account_type in ("asset", "expense"):
                balance = bucket["debit"] - bucket["credit"]
            else:
                balance = bucket["credit"] - bucket["debit"]
            if account.account_type == "income":
                retained += balance
            elif account.account_type == "expense":
                retained -= balance
            elif account.account_type in ("asset", "liability", "equity"):
                section = {"asset": "assets", "liability": "liabilities",
                           "equity": "equity"}[account.account_type]
                sections[section].append(
                    {"code": account.code, "name": account.name,
                     "balance_minor": balance})
        total_assets = sum(r["balance_minor"] for r in sections["assets"])
        total_liabilities = sum(r["balance_minor"]
                                for r in sections["liabilities"])
        total_equity = sum(r["balance_minor"] for r in sections["equity"]) \
            + retained
        return {
            **_meta("balance_sheet", currency, "accrual (journal-based)",
                    "balances from journal lines; retained earnings = "
                    "cumulative income − cumulative expenses",
                    {"as_of": as_of}),
            "business_id": business_id,
            "assets_minor": sections["assets"],
            "liabilities_minor": sections["liabilities"],
            "equity_lines_minor": sections["equity"],
            "retained_earnings_minor": retained,
            "total_assets_minor": total_assets,
            "total_liabilities_minor": total_liabilities,
            "total_equity_minor": total_equity,
            "balanced": total_assets == total_liabilities + total_equity,
        }

    # ------------------------------------------------------- cash flow
    def cashflow_statement(self, business_id: str, currency: str, *,
                           start: str, end: str) -> dict:
        flow = self._analytics.cashflow(business_id, currency,
                                        start=start, end=end)
        return {**_meta("cashflow", currency, "cash (journal-based)",
                        "cash deltas on cash/bank/processor accounts; "
                        "actuals and forecast block kept separate (§12.1)",
                        {"start": start, "end": end}), **flow}

    # ---------------------------------------------- budget utilisation
    def budget_utilization_report(self, business_id: str) -> dict:
        budgets, _ = self._budgets.list_budgets(business_id=business_id,
                                                limit=200)
        rows = [self._budgets.budget_utilisation(b["id"]) for b in budgets]
        return {
            **_meta("budget_utilization", "mixed",
                    "commitment accounting",
                    "spent = paid expenses linked to the budget; "
                    "committed = authorised unrecorded requests + "
                    "committed expenses"),
            "business_id": business_id, "budgets": rows,
        }

    # ----------------------------------------------- reconciliation
    def reconciliation_report(self, business_id: str) -> dict:
        session = self._session_factory()
        try:
            sessions, _ = ReconciliationSessionRepository(session).list(
                limit=200, business_id=business_id)
            item_repo = ReconciliationItemRepository(session)
            unresolved = []
            for sess in sessions:
                for item in item_repo.for_session(sess.id):
                    if item.status != "resolved":
                        unresolved.append({
                            "session_id": sess.id, "item_id": item.id,
                            "classification": item.classification,
                            "external_ref": item.external_ref,
                            "external_amount_minor": item.external_amount_minor,
                            "external_currency": item.external_currency,
                            "discrepancy": item.discrepancy})
            result_sessions = [
                {"id": s.id, "source_type": s.source_type,
                 "status": s.status, "summary": s.summary}
                for s in sessions]
        finally:
            session.close()
        return {
            **_meta("reconciliation", "mixed", "n/a",
                    "sessions and unresolved items; discrepancies are "
                    "reported, never silently corrected (§13)"),
            "business_id": business_id, "sessions": result_sessions,
            "unresolved_items": unresolved,
            "unresolved_count": len(unresolved),
        }

    # ------------------------------------------------------------ export
    def export(self, report: dict, fmt: str) -> tuple[str, str]:
        """Returns (content, media_type). CSV flattens the report's
        primary tabular block when one exists."""
        if fmt == "json":
            return json.dumps(report, indent=2, default=str), "application/json"
        if fmt == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["# AUTONOMUS financial report export"])
            writer.writerow(["# report", report.get("report")])
            writer.writerow(["# currency", report.get("currency")])
            writer.writerow(["# generated_at", report.get("generated_at")])
            writer.writerow(["# notice", report.get("notice")])
            rows = _tabular_rows(report)
            if rows:
                writer.writerow(rows[0])
                writer.writerows(rows[1:])
            else:
                for key, value in report.items():
                    if isinstance(value, (str, int, float)) or value is None:
                        writer.writerow([key, value])
            return buffer.getvalue(), "text/csv"
        if fmt == "pdf":
            raise ValidationError(
                "PDF export is NOT IMPLEMENTED in P-07 (stdlib-only "
                "constraint); use CSV or JSON (§24)")
        raise ValidationError(f"unknown export format {fmt!r}")


def _tabular_rows(report: dict) -> list[list]:
    if report.get("report") == "profit_loss":
        rows = [["line", "type", "amount_minor"]]
        for name, amount in report["income_lines_minor"].items():
            rows.append([name, "income", amount])
        for name, amount in report["expense_lines_minor"].items():
            rows.append([name, "expense", amount])
        rows.append(["net_profit", "total", report["net_profit_minor"]])
        return rows
    if report.get("report") == "budget_utilization":
        rows = [["budget", "approved_minor", "spent_minor",
                 "committed_minor", "remaining_minor", "currency"]]
        for budget in report["budgets"]:
            rows.append([budget["name"], budget["approved_minor"],
                         budget["spent_minor"], budget["committed_minor"],
                         budget["remaining_minor"], budget["currency"]])
        return rows
    return []
