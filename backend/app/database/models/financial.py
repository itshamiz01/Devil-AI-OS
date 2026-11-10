"""SQLAlchemy models for the P-07 Financial Intelligence Engine tables.

One additive migration creates these tables; no P-01..P-06 table is
altered. Approvals reuse the P-01 ``approvals`` table and the financial
audit trail reuses the append-only P-01 ``audit_events`` table (P-07
pre-implementation audit §3) — there is deliberately no
``financial_approvals`` or ``financial_audit_logs`` table here.

Money discipline (§5.1): every amount is an **integer count of minor
units** (``*_minor`` BigInteger) with an explicit currency column.
There is no float column anywhere in this module. Posted journal
entries are immutable through every service/API path; corrections are
reversal or adjustment entries (``journal_entries.reversal_of_id``).
"""
from __future__ import annotations

from sqlalchemy import (
    JSON, BigInteger, Boolean, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class FinancialProfile(TimestampMixin, Base):
    """One financial profile per P-06 business (§18). Estimates ingested
    from the P-06 bridge stay labelled estimates forever."""

    __tablename__ = "financial_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), unique=True, nullable=False, index=True)
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    reporting_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    reporting_period: Mapped[str] = mapped_column(
        String(20), nullable=False, default="monthly")
    business_model: Mapped[str] = mapped_column(
        String(40), nullable=False, default="digital_products")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(
        String(40), nullable=False, default="p06_bridge")
    p06_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    estimates: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class FinancialAccount(TimestampMixin, Base):
    """Chart of accounts, per business (§5.2)."""

    __tablename__ = "financial_accounts"
    # One chart instance per (business, currency): a business books
    # in its base currency and may hold additional currency charts
    # for foreign-currency transactions (§14) — codes repeat across
    # currencies, never within one.
    __table_args__ = (UniqueConstraint(
        "business_id", "code", "currency",
        name="uq_financial_account_code_currency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True)  # asset|liability|equity|income|expense
    subtype: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class FinancialPeriod(TimestampMixin, Base):
    __tablename__ = "financial_periods"
    __table_args__ = (UniqueConstraint("business_id", "label",
                                       name="uq_financial_period_label"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    period_type: Mapped[str] = mapped_column(String(20), nullable=False, default="month")
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[str] = mapped_column(String(10), nullable=False)
    end_date: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")


class JournalEntry(TimestampMixin, Base):
    """A posted double-entry journal entry. Immutable once created;
    corrections happen only through new entries (reversal/adjustment).
    ``is_reversed`` is computed from the existence of a reversal entry,
    never by mutating this row."""

    __tablename__ = "journal_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    period_id: Mapped[str | None] = mapped_column(
        ForeignKey("financial_periods.id"), nullable=True)
    entry_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="manual", index=True)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="standard")  # standard|reversal|adjustment|opening
    reversal_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("journal_entries.id"), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(300), unique=True, nullable=True)
    is_internal_transfer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False)
    # P-14 Stage B (DEF-D3): canonical foreign keys on the
    # width-matching subset (businesses.id is String(36),
    # approvals.id is String(64)); previously plain strings.
    counterpart_business_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("businesses.id"), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("approvals.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_by: Mapped[str] = mapped_column(String(120), nullable=False)


class JournalLine(TimestampMixin, Base):
    __tablename__ = "journal_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    entry_id: Mapped[str] = mapped_column(
        ForeignKey("journal_entries.id"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("financial_accounts.id"), nullable=False, index=True)
    debit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    credit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)


class RevenueRecord(TimestampMixin, Base):
    """One revenue record with §3.2 evidence metadata. ``classification``
    is the §3.1 truth bucket the record currently counts toward;
    ``verification_status`` gates whether it may count as collected."""

    __tablename__ = "revenue_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    classification: Mapped[str] = mapped_column(
        String(20), nullable=False, default="projected", index=True)
    lifecycle_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="EXPECTED", index=True)
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unverified", index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    transaction_date: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    invoice_id: Mapped[str | None] = mapped_column(
        ForeignKey("invoices.id"), nullable=True)
    order_id: Mapped[str | None] = mapped_column(
        ForeignKey("orders.id"), nullable=True)
    subscription_id: Mapped[str | None] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=True)
    customer_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(120), nullable=True)
    product_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    creation_method: Mapped[str] = mapped_column(
        String(60), nullable=False, default="manual")
    is_internal_transfer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False)
    journal_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("journal_entries.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(60), nullable=False)
    revenue_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    customer_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="issued", index=True)
    issued_date: Mapped[str] = mapped_column(String(10), nullable=False)
    due_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    customer_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="created", index=True)
    channel: Mapped[str | None] = mapped_column(String(120), nullable=True)
    order_date: Mapped[str] = mapped_column(String(10), nullable=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class Subscription(TimestampMixin, Base):
    """A recurring contract. Contracts are NOT cash collections (§6.3):
    MRR is computed from active contracts, collected revenue only from
    verified revenue records."""

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    customer_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    plan_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    interval: Mapped[str] = mapped_column(
        String(20), nullable=False, default="monthly")  # monthly|annual
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", index=True)
    started_date: Mapped[str] = mapped_column(String(10), nullable=False)
    current_period_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class Refund(TimestampMixin, Base):
    """A refund is an independent record linked to the original payment
    (§26.4 Scenario 2); the original revenue record is never edited."""

    __tablename__ = "refunds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    revenue_record_id: Mapped[str] = mapped_column(
        ForeignKey("revenue_records.id"), nullable=False, index=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="manual")
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    refund_date: Mapped[str] = mapped_column(String(10), nullable=False)
    journal_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("journal_entries.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class Dispute(TimestampMixin, Base):
    __tablename__ = "disputes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    revenue_record_id: Mapped[str] = mapped_column(
        ForeignKey("revenue_records.id"), nullable=False, index=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="dispute")  # dispute|chargeback
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="opened", index=True)
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    opened_date: Mapped[str] = mapped_column(String(10), nullable=False)
    journal_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("journal_entries.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class ExpenseRecord(TimestampMixin, Base):
    """§8.2 expense record. ``kind`` distinguishes true expenses from
    asset purchases, deposits, loans and transfers — not every payment
    is an expense."""

    __tablename__ = "expense_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default="operating_expense", index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    expense_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    vendor: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recurrence_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="one_time")
    cost_behavior: Mapped[str] = mapped_column(
        String(20), nullable=False, default="variable")  # fixed|variable
    directness: Mapped[str] = mapped_column(
        String(20), nullable=False, default="indirect")  # direct|indirect
    payment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="paid", index=True)
    payment_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unverified")
    project_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    experiment_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    budget_id: Mapped[str | None] = mapped_column(
        ForeignKey("budgets.id"), nullable=True, index=True)
    approval_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_required")
    # P-14 Stage B (DEF-D3): canonical FK (approvals.id is String(64)).
    approval_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("approvals.id"), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    execution_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recurring_group_key: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    is_internal_transfer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False)
    journal_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("journal_entries.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class Budget(TimestampMixin, Base):
    """§9.1 budget. Spent/committed are computed from linked expense
    records and spending requests — never stored as editable totals."""

    __tablename__ = "budgets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    scope_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True)  # portfolio|business|project|experiment|agent_task|campaign|integration
    scope_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    parent_budget_id: Mapped[str | None] = mapped_column(
        ForeignKey("budgets.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(200), nullable=False)
    period_start: Mapped[str] = mapped_column(String(10), nullable=False)
    period_end: Mapped[str] = mapped_column(String(10), nullable=False)
    approved_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    approval_requirement: Mapped[str] = mapped_column(
        String(20), nullable=False, default="level_2")
    review_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", index=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class SpendingRequest(TimestampMixin, Base):
    """A §9.5 authorisation decision. P-07 authorises the *recording of
    an obligation*; it never executes a payment or transfer (§23.2).
    Level-3 kinds are structurally blocked."""

    __tablename__ = "spending_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    budget_id: Mapped[str | None] = mapped_column(
        ForeignKey("budgets.id"), nullable=True, index=True)
    requester_type: Mapped[str] = mapped_column(String(32), nullable=False)
    requester_id: Mapped[str] = mapped_column(String(200), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default="expense", index=True)
    required_level: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="held_for_owner", index=True)
    # P-14 Stage B (DEF-D3): canonical FK (approvals.id is String(64)).
    approval_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("approvals.id"), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expense_record_id: Mapped[str | None] = mapped_column(
        ForeignKey("expense_records.id"), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    experiment_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)


class FinancialReserve(TimestampMixin, Base):
    """§9.3 protected reserve. A designation over cash: its balance is
    subtracted in the available-cash formula and is never spendable.
    Balance changes are owner-only and audited."""

    __tablename__ = "financial_reserves"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    reserve_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    target_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CashBalance(TimestampMixin, Base):
    """An authoritative cash figure from a named source (§3.1 #11).
    The latest row per (business, account_ref) is current."""

    __tablename__ = "cash_balances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    account_ref: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="reported")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class PaymentProvider(TimestampMixin, Base):
    """A provider registration. Secrets are NEVER stored: only the
    NAME of the environment variable that holds the webhook secret
    (§23.1)."""

    __tablename__ = "payment_providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    adapter_key: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="interface_only", index=True)
    webhook_secret_env: Mapped[str | None] = mapped_column(String(120), nullable=True)
    capabilities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class PaymentEvent(TimestampMixin, Base):
    """One inbound provider event. Unique (provider, external id) is
    the duplicate/concurrent-delivery guard (Scenarios 3 & 11)."""

    __tablename__ = "payment_events"
    __table_args__ = (UniqueConstraint("provider_id", "external_event_id",
                                       name="uq_payment_event_external"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_id: Mapped[str] = mapped_column(
        ForeignKey("payment_providers.id"), nullable=False, index=True)
    external_event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="received", index=True)
    journal_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("journal_entries.id"), nullable=True)
    revenue_record_id: Mapped[str | None] = mapped_column(
        ForeignKey("revenue_records.id"), nullable=True)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ProviderPayout(TimestampMixin, Base):
    __tablename__ = "provider_payouts"
    __table_args__ = (UniqueConstraint("provider_id", "external_ref",
                                       name="uq_provider_payout_external"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_id: Mapped[str] = mapped_column(
        ForeignKey("payment_providers.id"), nullable=False, index=True)
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    external_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="expected", index=True)
    period_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    period_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    received_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class ReconciliationSession(TimestampMixin, Base):
    __tablename__ = "reconciliation_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    period_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    period_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", index=True)
    summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class ReconciliationItem(TimestampMixin, Base):
    __tablename__ = "reconciliation_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("reconciliation_sessions.id"), nullable=False, index=True)
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    external_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    external_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    external_date: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    matched_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    matched_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    match_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    classification: Mapped[str] = mapped_column(
        String(30), nullable=False, default="UNMATCHED", index=True)
    discrepancy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    resolution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", index=True)


class ExchangeRate(TimestampMixin, Base):
    """A conversion rate with provenance (§14). ``rate`` is a decimal
    string (units of to-currency per 1 unit of from-currency); never a
    float, never invented."""

    __tablename__ = "exchange_rates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    from_currency: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    to_currency: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    rate: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class FinancialForecast(TimestampMixin, Base):
    """A frozen forecast (§11.4): no update path exists, so history can
    never be rewritten to look accurate."""

    __tablename__ = "financial_forecasts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    forecast_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(60), nullable=False)
    period_label: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[str] = mapped_column(String(10), nullable=False)
    period_end: Mapped[str] = mapped_column(String(10), nullable=False)
    values: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    assumptions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class FinancialScenario(TimestampMixin, Base):
    __tablename__ = "financial_scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    scenario_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True)  # conservative|base|optimistic
    display_label: Mapped[str] = mapped_column(String(60), nullable=False)
    assumptions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    results: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    risks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class FinancialAlert(TimestampMixin, Base):
    """A deterministic risk signal (§16). An alert is a signal for
    investigation, never an accusation."""

    __tablename__ = "financial_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    impact: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    detection_method: Mapped[str] = mapped_column(String(120), nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    human_review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", index=True)
    dedupe_key: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="system")


class TaxRecord(TimestampMixin, Base):
    """Tax *tracking* only (§15): no rate is hardcoded, no compliance
    is claimed; every record carries the professional-review flag."""

    __tablename__ = "tax_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    jurisdiction: Mapped[str] = mapped_column(String(80), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    period_label: Mapped[str] = mapped_column(String(20), nullable=False)
    estimated_liability_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0)
    collected_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    payable_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    paid_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    due_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rate: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    professional_review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class TaskCostRecord(TimestampMixin, Base):
    """§19 agent/task cost declaration. Local inference has a direct
    monetary cost of zero unless the owner configures an electricity
    estimate — a cost is never invented for free local software."""

    __tablename__ = "task_cost_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True)
    project_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    execution_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    estimated_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    approved_limit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    actual_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    cost_kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default="direct_monetary")
    approval_requirement: Mapped[str] = mapped_column(
        String(20), nullable=False, default="level_2")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="estimated", index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
