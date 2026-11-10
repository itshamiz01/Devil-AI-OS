"""P-07 API schemas. All monetary amounts are decimal STRINGS
(``"10000.00"``): a JSON number would arrive as a float, and floats
are forbidden in financial computation (§5.1) — pydantic rejects
non-string amounts with 422 before any arithmetic happens."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ProfileCreateIn(BaseModel):
    business_model: str | None = None


class OpeningBalanceIn(BaseModel):
    amount: str
    currency: str = "INR"
    entry_date: str
    account_ref: str = "cash:primary"
    source: str = "owner_recorded_opening_balance"
    verification_status: str = "reported"


class AccountCreateIn(BaseModel):
    code: str
    name: str
    account_type: str
    subtype: str = ""
    currency: str = "INR"


class JournalLineIn(BaseModel):
    account_id: str
    debit: str | None = None
    credit: str | None = None
    currency: str = "INR"
    memo: str | None = None


class JournalPostIn(BaseModel):
    business_id: str
    entry_date: str
    description: str = ""
    reference: str | None = None
    source_type: str = "manual"
    lines: list[JournalLineIn]
    idempotency_key: str | None = None


class JournalReverseIn(BaseModel):
    reason: str


class RevenueCreateIn(BaseModel):
    business_id: str
    category: str
    amount: str
    currency: str = "INR"
    transaction_date: str
    source: str = "manual"
    initial_status: str = "EXPECTED"
    external_ref: str | None = None
    customer_ref: str | None = None
    channel: str | None = None
    product_ref: str | None = None
    description: str = ""
    evidence: dict = Field(default_factory=dict)
    creation_method: str = "manual"


class RevenueTransitionIn(BaseModel):
    target_status: str


class RevenueVerifyIn(BaseModel):
    source: str
    evidence: dict = Field(default_factory=dict)
    approval_id: str | None = None


class InvoiceCreateIn(BaseModel):
    business_id: str
    number: str
    amount: str
    currency: str = "INR"
    issued_date: str
    due_date: str | None = None
    customer_ref: str | None = None
    revenue_record_id: str | None = None


class OrderCreateIn(BaseModel):
    business_id: str
    amount: str
    currency: str = "INR"
    order_date: str
    external_ref: str | None = None
    customer_ref: str | None = None
    channel: str | None = None


class SubscriptionCreateIn(BaseModel):
    business_id: str
    plan_ref: str
    amount: str
    currency: str = "INR"
    interval: str = "monthly"
    status: str = "active"
    started_date: str
    current_period_end: str | None = None
    customer_ref: str | None = None


class SubscriptionStatusIn(BaseModel):
    status: str


class RefundCreateIn(BaseModel):
    amount: str
    currency: str = "INR"
    refund_date: str
    reason: str | None = None
    source: str = "manual"
    external_ref: str | None = None


class DisputeCreateIn(BaseModel):
    amount: str
    currency: str = "INR"
    opened_date: str
    kind: str = "dispute"
    reason: str | None = None
    external_ref: str | None = None


class ExpenseCreateIn(BaseModel):
    business_id: str
    category: str
    amount: str
    currency: str = "INR"
    expense_date: str
    kind: str = "operating_expense"
    vendor: str | None = None
    description: str = ""
    recurrence_type: str = "one_time"
    cost_behavior: str = "variable"
    directness: str = "indirect"
    payment_status: str = "paid"
    payment_source: str | None = None
    evidence: dict = Field(default_factory=dict)
    verification_status: str = "unverified"
    project_ref: str | None = None
    experiment_ref: str | None = None
    budget_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    execution_request_id: str | None = None


class BudgetCreateIn(BaseModel):
    scope_type: str
    name: str
    amount: str
    currency: str = "INR"
    period_start: str
    period_end: str
    scope_ref: str | None = None
    business_id: str | None = None
    parent_budget_id: str | None = None
    approval_requirement: str = "level_2"
    review_date: str | None = None


class ReserveCreateIn(BaseModel):
    reserve_type: str
    amount: str
    currency: str = "INR"
    business_id: str | None = None
    target: str | None = None


class ReserveBalanceIn(BaseModel):
    amount: str
    currency: str = "INR"
    reason: str


class SpendRequestIn(BaseModel):
    business_id: str
    amount: str
    currency: str = "INR"
    category: str
    purpose: str = ""
    kind: str = "expense"
    budget_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    project_ref: str | None = None
    experiment_ref: str | None = None


class SpendApproveIn(BaseModel):
    approval_id: str


class SpendRejectIn(BaseModel):
    reason: str


class SpendRecordIn(BaseModel):
    expense_id: str


class TransferIn(BaseModel):
    to_business_id: str
    amount: str
    currency: str = "INR"
    entry_date: str
    reference: str


class RateIn(BaseModel):
    from_currency: str
    to_currency: str
    rate: str
    source: str


class ConvertIn(BaseModel):
    amount: str
    currency: str
    to_currency: str


class ForecastCreateIn(BaseModel):
    business_id: str
    forecast_type: str
    method: str = "historical_average"
    currency: str = "INR"


class ScenarioCreateIn(BaseModel):
    business_id: str
    scenario_type: str
    currency: str = "INR"
    revenue_factor: str | None = None
    expense_factor: str | None = None
    display_label: str | None = None
    assumptions: dict = Field(default_factory=dict)
    risks: list = Field(default_factory=list)
    confidence: str = "low"


class ReconciliationImportIn(BaseModel):
    business_id: str
    csv_text: str
    source_type: str = "bank_statement"
    source_ref: str | None = None


class ReconciliationResolveIn(BaseModel):
    action: str
    reason: str | None = None
    evidence: dict = Field(default_factory=dict)


class TaxRecordIn(BaseModel):
    jurisdiction: str
    category: str
    period_label: str
    currency: str = "INR"
    estimated_liability: str | None = None
    collected: str | None = None
    payable: str | None = None
    paid: str | None = None
    due_date: str | None = None
    rate: dict = Field(default_factory=dict)
    notes: str = ""


class TaskCostIn(BaseModel):
    business_id: str
    category: str
    currency: str = "INR"
    estimated: str = "0"
    approved_limit: str = "0"
    actual: str | None = None
    cost_kind: str = "direct_monetary"
    project_ref: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    execution_request_id: str | None = None
    approval_requirement: str = "level_2"
    notes: str = ""


class AnalystQueryIn(BaseModel):
    intent: str
    business_id: str | None = None
    currency: str = "INR"


class ApprovalDecisionIn(BaseModel):
    approve: bool
    notes: str | None = None
