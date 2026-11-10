"""Expense intelligence (§8). Paid P&L expenses post to the ledger
(Dr expense account / Cr cash). Non-expense kinds (asset purchases,
deposits, loans, transfers) are recorded and classified but never
silently treated as P&L expenses."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.financial import ExpenseRecord
from ..database.repositories.financial import ExpenseRepository
from . import constants as C
from .ledger import LedgerService
from .money import Money, require_positive


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}"


def expense_dict(row: ExpenseRecord) -> dict:
    return {
        "id": row.id, "business_id": row.business_id,
        "category": row.category, "kind": row.kind,
        "amount_minor": row.amount_minor, "currency": row.currency,
        "expense_date": row.expense_date, "vendor": row.vendor,
        "description": row.description,
        "recurrence_type": row.recurrence_type,
        "cost_behavior": row.cost_behavior, "directness": row.directness,
        "payment_status": row.payment_status,
        "payment_source": row.payment_source, "evidence": row.evidence,
        "verification_status": row.verification_status,
        "project_ref": row.project_ref, "experiment_ref": row.experiment_ref,
        "budget_id": row.budget_id, "approval_status": row.approval_status,
        "approval_id": row.approval_id, "agent_id": row.agent_id,
        "task_id": row.task_id, "execution_request_id": row.execution_request_id,
        "recurring_group_key": row.recurring_group_key,
        "is_internal_transfer": row.is_internal_transfer,
        "journal_entry_id": row.journal_entry_id,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def group_key(vendor: str | None, category: str) -> str:
    return f"{(vendor or 'unknown').strip().lower()}|{category}"


class ExpenseService:
    def __init__(self, session_factory, ledger: LedgerService, audit):
        self._session_factory = session_factory
        self._ledger = ledger
        self._audit = audit

    def create_expense(self, principal, business_id: str, data: dict, *,
                       post_journal: bool = True) -> dict:
        if data["category"] not in C.EXPENSE_CATEGORIES:
            raise ValidationError(f"unknown expense category {data['category']!r}")
        kind = data.get("kind", "operating_expense")
        if kind not in C.EXPENSE_KINDS:
            raise ValidationError(f"unknown expense kind {kind!r}")
        amount: Money = require_positive(data["amount"])
        self._ledger.assert_known_currency(amount.currency)
        session = self._session_factory()
        try:
            row = ExpenseRecord(
                business_id=business_id, category=data["category"], kind=kind,
                amount_minor=amount.minor, currency=amount.currency,
                expense_date=data["expense_date"], vendor=data.get("vendor"),
                description=data.get("description", ""),
                recurrence_type=data.get("recurrence_type", "one_time"),
                cost_behavior=data.get("cost_behavior", "variable"),
                directness=data.get("directness", "indirect"),
                payment_status=data.get("payment_status", "paid"),
                payment_source=data.get("payment_source"),
                evidence=data.get("evidence") or {},
                verification_status=data.get("verification_status", "unverified"),
                project_ref=data.get("project_ref"),
                experiment_ref=data.get("experiment_ref"),
                budget_id=data.get("budget_id"),
                approval_status=data.get("approval_status", "not_required"),
                approval_id=data.get("approval_id"),
                agent_id=data.get("agent_id"), task_id=data.get("task_id"),
                execution_request_id=data.get("execution_request_id"),
                recurring_group_key=group_key(data.get("vendor"), data["category"]),
                is_internal_transfer=(kind == "internal_transfer"),
                created_by=_actor(principal))
            ExpenseRepository(session).add(row)
            session.expunge(row)
            expense = expense_dict(row)
        finally:
            session.close()
        if post_journal and expense["payment_status"] == "paid" \
                and kind in C.P_AND_L_EXPENSE_KINDS:
            entry = self._ledger.post_simple(
                principal, business_id,
                debit_code=C.EXPENSE_CATEGORY_ACCOUNT[data["category"]],
                credit_code=C.ACCOUNT_CASH, amount_minor=amount.minor,
                currency=amount.currency, entry_date=data["expense_date"],
                description=f"Expense {expense['id']} ({data['category']})",
                source_type="expense", source_id=expense["id"],
                idempotency_key=f"expense:{expense['id']}")
            session = self._session_factory()
            try:
                repo = ExpenseRepository(session)
                stored = repo.get(expense["id"])
                stored.journal_entry_id = entry["id"]
                repo.save(stored)
                expense["journal_entry_id"] = entry["id"]
            finally:
                session.close()
        return expense

    def get_expense(self, expense_id: str) -> dict:
        session = self._session_factory()
        try:
            row = ExpenseRepository(session).get(expense_id)
            if row is None:
                raise NotFoundError(f"expense {expense_id} not found")
            session.expunge(row)
            return expense_dict(row)
        finally:
            session.close()

    def list_expenses(self, business_id: str, limit: int = 50,
                      offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            rows, total = ExpenseRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [expense_dict(r) for r in rows], total
        finally:
            session.close()

    def totals(self, business_id: str, currency: str, *,
               start: str | None = None, end: str | None = None) -> dict:
        session = self._session_factory()
        try:
            rows = ExpenseRepository(session).for_business(business_id)
        finally:
            session.close()
        selected = [r for r in rows if r.currency == currency
                    and not r.is_internal_transfer
                    and (start is None or r.expense_date >= start)
                    and (end is None or r.expense_date <= end)]
        paid = [r for r in selected if r.payment_status == "paid"]
        pl_paid = [r for r in paid if r.kind in C.P_AND_L_EXPENSE_KINDS]
        direct = sum(r.amount_minor for r in pl_paid if r.directness == "direct")
        by_category: dict[str, int] = defaultdict(int)
        for row in pl_paid:
            by_category[row.category] += row.amount_minor
        return {
            "business_id": business_id, "currency": currency,
            "total_paid_minor": sum(r.amount_minor for r in paid),
            "pl_expense_paid_minor": sum(r.amount_minor for r in pl_paid),
            "direct_costs_minor": direct,
            "indirect_costs_minor": sum(r.amount_minor for r in pl_paid) - direct,
            "committed_minor": sum(r.amount_minor for r in selected
                                   if r.payment_status == "committed"),
            "non_expense_paid_minor": sum(
                r.amount_minor for r in paid
                if r.kind not in C.P_AND_L_EXPENSE_KINDS),
            "by_category_minor": dict(by_category),
            "fixed_minor": sum(r.amount_minor for r in pl_paid
                               if r.cost_behavior == "fixed"),
            "variable_minor": sum(r.amount_minor for r in pl_paid
                                  if r.cost_behavior == "variable"),
        }

    # ------------------------------------------------- §8.3 recurring
    def detect_recurring(self, business_id: str) -> list[dict]:
        """Group paid expenses by (vendor, category): a group with >=2
        charges at a stable cadence is a detected recurring expense.
        Detection is a *suggestion* — the owner confirms or corrects."""
        session = self._session_factory()
        try:
            rows = ExpenseRepository(session).for_business(business_id)
        finally:
            session.close()
        groups: dict[str, list[ExpenseRecord]] = defaultdict(list)
        for row in rows:
            if row.payment_status == "paid" and row.recurring_group_key:
                groups[row.recurring_group_key].append(row)
        results = []
        for key, items in sorted(groups.items()):
            if len(items) < 2:
                continue
            items.sort(key=lambda r: r.expense_date)
            amounts = [i.amount_minor for i in items]
            dates = [dt.date.fromisoformat(i.expense_date) for i in items]
            gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
            avg_gap = sum(gaps) / len(gaps) if gaps else 0
            cadence = ("monthly" if 25 <= avg_gap <= 35 else
                       "annual" if 330 <= avg_gap <= 400 else
                       "weekly" if 6 <= avg_gap <= 8 else "irregular")
            latest = items[-1]
            amount_changed = len(set(amounts)) > 1
            next_expected = None
            if cadence in ("monthly", "annual", "weekly") and gaps:
                step = dt.timedelta(days=int(round(avg_gap)))
                next_expected = (dates[-1] + step).isoformat()
            results.append({
                "group_key": key, "vendor": latest.vendor,
                "category": latest.category, "currency": latest.currency,
                "occurrences": len(items),
                "amounts_minor": amounts,
                "cadence_detected": cadence,
                "average_gap_days": round(avg_gap, 1),
                "latest_amount_minor": latest.amount_minor,
                "amount_changed": amount_changed,
                "next_expected_date": next_expected,
                "confirmation_status": "unconfirmed — owner confirmation "
                                       "required (§8.3)",
            })
        return results
