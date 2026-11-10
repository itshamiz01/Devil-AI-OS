"""Repository layer for P-07 financial tables. All SQL for the
financial package lives here or in the financial services built on
these repositories; API routes never build queries directly."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.financial import (
    Budget, CashBalance, Dispute, ExchangeRate, ExpenseRecord,
    FinancialAccount, FinancialAlert, FinancialForecast, FinancialPeriod,
    FinancialProfile, FinancialReserve, FinancialScenario, Invoice,
    JournalEntry, JournalLine, Order, PaymentEvent, PaymentProvider,
    ProviderPayout, ReconciliationItem, ReconciliationSession, Refund,
    RevenueRecord, SpendingRequest, Subscription, TaskCostRecord,
    TaxRecord,
)


class _Repo:
    model = None

    def __init__(self, session: Session):
        self.session = session

    def add(self, row):
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def save(self, row):
        self.session.commit()
        self.session.refresh(row)
        return row

    def get(self, row_id: str):
        return self.session.get(self.model, row_id)

    def list(self, *, limit: int = 50, offset: int = 0, business_id: str | None = None,
             filters: dict | None = None) -> tuple[list, int]:
        stmt = select(self.model)
        count_stmt = select(func.count()).select_from(self.model)
        conditions = []
        if business_id is not None and hasattr(self.model, "business_id"):
            conditions.append(self.model.business_id == business_id)
        for key, value in (filters or {}).items():
            if value is not None and hasattr(self.model, key):
                conditions.append(getattr(self.model, key) == value)
        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        total = self.session.scalar(count_stmt) or 0
        rows = self.session.scalars(
            stmt.order_by(self.model.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(rows), total


class ProfileRepository(_Repo):
    model = FinancialProfile

    def for_business(self, business_id: str) -> FinancialProfile | None:
        return self.session.scalar(
            select(FinancialProfile).where(FinancialProfile.business_id == business_id))


class AccountRepository(_Repo):
    model = FinancialAccount

    def for_business(self, business_id: str) -> list[FinancialAccount]:
        return list(self.session.scalars(
            select(FinancialAccount)
            .where(FinancialAccount.business_id == business_id)
            .order_by(FinancialAccount.code)).all())

    def by_code(self, business_id: str, code: str,
                currency: str | None = None) -> FinancialAccount | None:
        query = select(FinancialAccount).where(
            FinancialAccount.business_id == business_id,
            FinancialAccount.code == code)
        if currency is not None:
            query = query.where(FinancialAccount.currency == currency)
        return self.session.scalar(query)


class PeriodRepository(_Repo):
    model = FinancialPeriod

    def for_label(self, business_id: str, label: str) -> FinancialPeriod | None:
        return self.session.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.business_id == business_id,
                FinancialPeriod.label == label))


class JournalRepository(_Repo):
    model = JournalEntry

    def lines(self, entry_id: str) -> list[JournalLine]:
        return list(self.session.scalars(
            select(JournalLine).where(JournalLine.entry_id == entry_id)).all())

    def by_idempotency_key(self, key: str) -> JournalEntry | None:
        return self.session.scalar(
            select(JournalEntry).where(JournalEntry.idempotency_key == key))

    def reversal_of(self, entry_id: str) -> JournalEntry | None:
        return self.session.scalar(
            select(JournalEntry).where(JournalEntry.reversal_of_id == entry_id))

    def for_business(self, business_id: str, limit: int = 200) -> list[JournalEntry]:
        return list(self.session.scalars(
            select(JournalEntry).where(JournalEntry.business_id == business_id)
            .order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc())
            .limit(limit)).all())

    def all_lines_for_business(self, business_id: str) -> list[JournalLine]:
        return list(self.session.scalars(
            select(JournalLine).join(
                JournalEntry, JournalLine.entry_id == JournalEntry.id)
            .where(JournalEntry.business_id == business_id)).all())


class RevenueRepository(_Repo):
    model = RevenueRecord

    def for_business(self, business_id: str, limit: int = 500) -> list[RevenueRecord]:
        return list(self.session.scalars(
            select(RevenueRecord).where(RevenueRecord.business_id == business_id)
            .order_by(RevenueRecord.transaction_date.desc()).limit(limit)).all())


class InvoiceRepository(_Repo):
    model = Invoice


class OrderRepository(_Repo):
    model = Order


class SubscriptionRepository(_Repo):
    model = Subscription

    def active_for(self, business_id: str) -> list[Subscription]:
        return list(self.session.scalars(
            select(Subscription).where(
                Subscription.business_id == business_id,
                Subscription.status == "active")).all())


class RefundRepository(_Repo):
    model = Refund

    def for_revenue(self, revenue_record_id: str) -> list[Refund]:
        return list(self.session.scalars(
            select(Refund).where(Refund.revenue_record_id == revenue_record_id)).all())

    def for_business(self, business_id: str) -> list[Refund]:
        return list(self.session.scalars(
            select(Refund).where(Refund.business_id == business_id)).all())


class DisputeRepository(_Repo):
    model = Dispute

    def for_business(self, business_id: str) -> list[Dispute]:
        return list(self.session.scalars(
            select(Dispute).where(Dispute.business_id == business_id)).all())


class ExpenseRepository(_Repo):
    model = ExpenseRecord

    def for_business(self, business_id: str, limit: int = 1000) -> list[ExpenseRecord]:
        return list(self.session.scalars(
            select(ExpenseRecord).where(ExpenseRecord.business_id == business_id)
            .order_by(ExpenseRecord.expense_date.desc()).limit(limit)).all())


class BudgetRepository(_Repo):
    model = Budget


class SpendingRequestRepository(_Repo):
    model = SpendingRequest


class ReserveRepository(_Repo):
    model = FinancialReserve

    def for_business(self, business_id: str | None) -> list[FinancialReserve]:
        stmt = select(FinancialReserve).where(FinancialReserve.status == "active")
        if business_id is None:
            stmt = stmt.where(FinancialReserve.business_id.is_(None))
        else:
            stmt = stmt.where(FinancialReserve.business_id == business_id)
        return list(self.session.scalars(stmt).all())


class CashBalanceRepository(_Repo):
    model = CashBalance

    def latest_for(self, business_id: str) -> list[CashBalance]:
        """Latest row per account_ref for the business."""
        rows = list(self.session.scalars(
            select(CashBalance).where(CashBalance.business_id == business_id)
            .order_by(CashBalance.created_at.desc())).all())
        latest: dict[str, CashBalance] = {}
        for row in rows:
            latest.setdefault(row.account_ref, row)
        return list(latest.values())


class ProviderRepository(_Repo):
    model = PaymentProvider

    def by_name(self, name: str) -> PaymentProvider | None:
        return self.session.scalar(
            select(PaymentProvider).where(PaymentProvider.name == name))


class PaymentEventRepository(_Repo):
    model = PaymentEvent

    def by_external(self, provider_id: str, external_event_id: str) -> PaymentEvent | None:
        return self.session.scalar(
            select(PaymentEvent).where(
                PaymentEvent.provider_id == provider_id,
                PaymentEvent.external_event_id == external_event_id))


class PayoutRepository(_Repo):
    model = ProviderPayout


class ReconciliationSessionRepository(_Repo):
    model = ReconciliationSession


class ReconciliationItemRepository(_Repo):
    model = ReconciliationItem

    def for_session(self, session_id: str) -> list[ReconciliationItem]:
        return list(self.session.scalars(
            select(ReconciliationItem)
            .where(ReconciliationItem.session_id == session_id)
            .order_by(ReconciliationItem.created_at.asc())).all())


class ExchangeRateRepository(_Repo):
    model = ExchangeRate

    def latest(self, from_currency: str, to_currency: str) -> ExchangeRate | None:
        return self.session.scalar(
            select(ExchangeRate).where(
                ExchangeRate.from_currency == from_currency,
                ExchangeRate.to_currency == to_currency)
            .order_by(ExchangeRate.created_at.desc()))


class ForecastRepository(_Repo):
    model = FinancialForecast


class ScenarioRepository(_Repo):
    model = FinancialScenario


class AlertRepository(_Repo):
    model = FinancialAlert

    def open_by_dedupe(self, dedupe_key: str) -> FinancialAlert | None:
        return self.session.scalar(
            select(FinancialAlert).where(
                FinancialAlert.dedupe_key == dedupe_key,
                FinancialAlert.status == "open"))


class TaxRepository(_Repo):
    model = TaxRecord


class TaskCostRepository(_Repo):
    model = TaskCostRecord
