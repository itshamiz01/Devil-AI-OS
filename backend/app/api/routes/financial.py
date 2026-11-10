"""Financial Intelligence Engine routes (P-07, §21 — adapted to the
repo's /api/v1 prefix as P-06 adapted its routes).

Authorisation mirrors the P-01 catalogue: reads require
``read_business_data``, writes ``modify_business_data``, spend
*requests* are decided by the engine itself for any authenticated
principal (agents request; the engine decides; nothing executes —
§23.2), and governance writes (budgets, reserves, settings, rates,
tax) are additionally owner-only inside the services. Webhooks are
unauthenticated by design: their authenticity is the HMAC signature,
never a bearer token (§7.2).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

from ...core.exceptions import PermissionDeniedError
from ...permissions.models import Permission, Principal, PrincipalType
from ..dependencies import correlation_id, get_application, get_principal, require_permission
from ..schemas.common import ok, page
from ..schemas.financial import (
    AccountCreateIn, AnalystQueryIn, ApprovalDecisionIn, BudgetCreateIn,
    ConvertIn, DisputeCreateIn, ExpenseCreateIn, ForecastCreateIn,
    InvoiceCreateIn, JournalPostIn, JournalReverseIn, OpeningBalanceIn,
    OrderCreateIn, ProfileCreateIn, RateIn, ReconciliationImportIn,
    ReconciliationResolveIn, RefundCreateIn, ReserveBalanceIn,
    ReserveCreateIn, RevenueCreateIn, RevenueTransitionIn, RevenueVerifyIn,
    ScenarioCreateIn, SpendApproveIn, SpendRecordIn, SpendRejectIn,
    SpendRequestIn, SubscriptionCreateIn, SubscriptionStatusIn,
    TaskCostIn, TaxRecordIn, TransferIn,
)

router = APIRouter(tags=["financial"])

READ = require_permission(Permission.READ_BUSINESS_DATA)
WRITE = require_permission(Permission.MODIFY_BUSINESS_DATA)
APPROVE = require_permission(Permission.APPROVE_ACTIONS)


def _svc(request: Request):
    return get_application(request).financial


def _money(svc, amount: str, currency: str):
    from ...financial.money import parse_amount
    return parse_amount(amount, currency, svc.registry)


def _guard(svc, principal: Principal, business_id: str) -> None:
    svc.assert_business_access(principal, business_id)


def _export(request: Request, report: dict, fmt: str | None):
    if fmt in (None, "envelope"):
        return ok(report, correlation_id=correlation_id(request))
    content, media = _svc(request).reports.export(report, fmt)
    return PlainTextResponse(content, media_type=media)


# ------------------------------------------------------------------ status
@router.get("/financial/status")
async def financial_status(request: Request, _=Depends(READ)):
    return ok(_svc(request).engine_status())


@router.get("/financial/settings")
async def get_settings(request: Request, _=Depends(READ)):
    return ok(_svc(request).get_settings())


@router.put("/financial/settings")
async def update_settings(request: Request, payload: dict,
                          principal: Principal = Depends(WRITE)):
    return ok(_svc(request).update_settings(principal, payload))


@router.get("/financial/currencies")
async def get_currencies(request: Request, _=Depends(READ)):
    return ok(_svc(request).get_currencies())


@router.get("/financial/dashboard")
async def dashboard(request: Request, _=Depends(READ)):
    svc = _svc(request)
    businesses = []
    for business_id in svc.list_business_ids():
        profile = svc.get_profile(business_id)
        if profile is None:
            continue
        currency = profile["base_currency"]
        health = svc.analytics.health(business_id, currency)
        available = svc.budgets.available_cash(business_id, currency)
        metrics = svc.revenue.metrics(business_id, currency)
        businesses.append({
            "business_id": business_id, "currency": currency,
            "is_fixture": profile["is_fixture"],
            "health": health["status"],
            "verified_net_collected_minor": metrics["net_collected_minor"],
            "projected_minor": metrics["projected_minor"],
            "available_cash_minor": available["available_cash_minor"],
            "protected_reserves_minor": available["protected_reserves_minor"],
        })
    alerts, alert_total = svc.analytics.list_alerts(None, limit=1)
    return ok({"businesses": businesses, "open_alerts": alert_total,
               "note": "projected and collected figures are separate "
                       "columns by design (§3.1)"})


@router.get("/financial/overview")
async def overview(request: Request, _=Depends(READ),
                   currency: str = Query("INR")):
    return ok(_svc(request).consolidated(currency))


@router.get("/financial/health")
async def portfolio_health(request: Request, _=Depends(READ)):
    svc = _svc(request)
    result = {}
    for business_id in svc.list_business_ids():
        profile = svc.get_profile(business_id)
        if profile is not None:
            result[business_id] = svc.analytics.health(
                business_id, profile["base_currency"])
    return ok(result)


# ---------------------------------------------------------------- profiles
@router.post("/financial/businesses/{business_id}/profile", status_code=201)
async def ensure_profile(request: Request, business_id: str,
                         payload: ProfileCreateIn,
                         principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    return ok(await svc.ensure_profile(
        principal, business_id, business_model=payload.business_model))


@router.get("/financial/businesses/{business_id}")
async def business_finances(request: Request, business_id: str,
                            principal: Principal = Depends(READ)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    return ok(svc.business_summary(business_id))


@router.get("/financial/businesses/{business_id}/summary")
async def business_summary(request: Request, business_id: str,
                           principal: Principal = Depends(READ)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    return ok(svc.business_summary(business_id))


@router.get("/financial/businesses/{business_id}/profitability")
async def business_profitability(request: Request, business_id: str,
                                 principal: Principal = Depends(READ),
                                 model: str | None = Query(None)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    profile = svc.get_profile(business_id)
    if profile is None:
        from ...core.exceptions import NotFoundError
        raise NotFoundError("no financial profile for this business")
    return ok(svc.analytics.profitability(
        business_id, profile["base_currency"],
        model or profile["business_model"]))


@router.get("/financial/businesses/{business_id}/cashflow")
async def business_cashflow(request: Request, business_id: str,
                            principal: Principal = Depends(READ),
                            start: str = Query(...), end: str = Query(...)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    profile = svc.get_profile(business_id)
    if profile is None:
        from ...core.exceptions import NotFoundError
        raise NotFoundError("no financial profile for this business")
    return ok(svc.analytics.cashflow(
        business_id, profile["base_currency"], start=start, end=end))


@router.get("/financial/businesses/{business_id}/indicators")
async def business_indicators(request: Request, business_id: str,
                              principal: Principal = Depends(READ)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    return ok(svc.p08_indicators(business_id))


@router.get("/financial/businesses/{business_id}/assumption-comparison")
async def assumption_comparison(request: Request, business_id: str,
                                principal: Principal = Depends(READ)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    return ok(svc.assumption_comparison(business_id))


@router.post("/financial/businesses/{business_id}/opening-balance",
             status_code=201)
async def opening_balance(request: Request, business_id: str,
                          payload: OpeningBalanceIn,
                          principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    return ok(svc.record_opening_balance(principal, business_id, {
        "amount": _money(svc, payload.amount, payload.currency),
        "account_ref": payload.account_ref, "source": payload.source,
        "verification_status": payload.verification_status,
        "entry_date": payload.entry_date}))


@router.post("/financial/businesses/{business_id}/transfers", status_code=201)
async def internal_transfer(request: Request, business_id: str,
                            payload: TransferIn,
                            principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    svc._require_owner(principal, "record internal transfer")
    return ok(svc.record_internal_transfer(principal, business_id,
                                           payload.to_business_id, {
        "amount": _money(svc, payload.amount, payload.currency),
        "entry_date": payload.entry_date, "reference": payload.reference}))


@router.post("/financial/businesses/{business_id}/risk-scan")
async def risk_scan(request: Request, business_id: str,
                    principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    profile = svc.get_profile(business_id)
    currency = profile["base_currency"] if profile else "INR"
    return ok(svc.analytics.run_risk_scan(principal, business_id, currency))


# ------------------------------------------------------------------ ledger
@router.get("/financial/ledger/accounts")
async def list_accounts(request: Request, _=Depends(READ),
                        business_id: str = Query(...)):
    return ok(_svc(request).ledger.list_accounts(business_id))


@router.post("/financial/ledger/accounts", status_code=201)
async def add_account(request: Request, payload: AccountCreateIn,
                      principal: Principal = Depends(WRITE),
                      business_id: str = Query(...)):
    svc = _svc(request)
    return ok(svc.ledger.add_account(principal, business_id, {
        "code": payload.code, "name": payload.name,
        "account_type": payload.account_type, "subtype": payload.subtype,
        "currency": payload.currency}))


@router.post("/financial/ledger/journals", status_code=201)
async def post_journal(request: Request, payload: JournalPostIn,
                       principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    lines = []
    for line in payload.lines:
        lines.append({
            "account_id": line.account_id,
            "debit_minor": _money(svc, line.debit, line.currency).minor
            if line.debit is not None else 0,
            "credit_minor": _money(svc, line.credit, line.currency).minor
            if line.credit is not None else 0,
            "currency": line.currency, "memo": line.memo})
    return ok(svc.ledger.post_entry(
        principal, payload.business_id, lines=lines,
        entry_date=payload.entry_date, description=payload.description,
        reference=payload.reference, source_type=payload.source_type,
        idempotency_key=payload.idempotency_key))


@router.get("/financial/ledger/journals")
async def list_journals(request: Request, _=Depends(READ),
                        business_id: str = Query(...),
                        limit: int = Query(50), offset: int = Query(0)):
    rows, total = _svc(request).ledger.list_entries(business_id, limit, offset)
    return page(rows, total, limit, offset)


@router.get("/financial/ledger/journals/{entry_id}")
async def get_journal(request: Request, entry_id: str, _=Depends(READ)):
    return ok(_svc(request).ledger.get_entry(entry_id))


@router.post("/financial/ledger/journals/{entry_id}/reverse")
async def reverse_journal(request: Request, entry_id: str,
                          payload: JournalReverseIn,
                          principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    svc._require_owner(principal, "reverse a journal entry")
    return ok(svc.ledger.reverse_entry(principal, entry_id,
                                       reason=payload.reason))


@router.get("/financial/ledger/integrity")
async def ledger_integrity(request: Request, _=Depends(READ),
                           business_id: str = Query(...)):
    return ok(_svc(request).ledger.verify_integrity(business_id))


@router.get("/financial/ledger/balances")
async def account_balances(request: Request, _=Depends(READ),
                           business_id: str = Query(...)):
    return ok(_svc(request).ledger.account_balances(business_id))


# ----------------------------------------------------------------- revenue
@router.get("/financial/revenue/metrics")
async def revenue_metrics(request: Request,
                          principal: Principal = Depends(READ),
                          business_id: str = Query(...),
                          currency: str = Query("INR")):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    return ok(svc.revenue.metrics(business_id, currency))


@router.post("/financial/revenue", status_code=201)
async def create_revenue(request: Request, payload: RevenueCreateIn,
                         principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    return ok(svc.revenue.create_revenue(principal, payload.business_id, {
        "category": payload.category,
        "amount": _money(svc, payload.amount, payload.currency),
        "transaction_date": payload.transaction_date, "source": payload.source,
        "initial_status": payload.initial_status,
        "external_ref": payload.external_ref,
        "customer_ref": payload.customer_ref, "channel": payload.channel,
        "product_ref": payload.product_ref, "description": payload.description,
        "evidence": payload.evidence, "creation_method": payload.creation_method}))


@router.get("/financial/revenue")
async def list_revenue(request: Request,
                       principal: Principal = Depends(READ),
                       business_id: str = Query(...),
                       limit: int = Query(50), offset: int = Query(0)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    rows, total = svc.revenue.list_revenue(business_id, limit, offset)
    return page(rows, total, limit, offset)


@router.get("/financial/revenue/{revenue_id}")
async def get_revenue(request: Request, revenue_id: str, _=Depends(READ)):
    return ok(_svc(request).revenue.get_revenue(revenue_id))


@router.post("/financial/revenue/{revenue_id}/transition")
async def transition_revenue(request: Request, revenue_id: str,
                             payload: RevenueTransitionIn,
                             principal: Principal = Depends(WRITE)):
    return ok(_svc(request).revenue.transition(
        principal, revenue_id, payload.target_status))


@router.post("/financial/revenue/{revenue_id}/verify")
async def verify_revenue(request: Request, revenue_id: str,
                         payload: RevenueVerifyIn,
                         principal: Principal = Depends(APPROVE)):
    svc = _svc(request)
    svc._require_owner(principal, "verify revenue")
    if payload.source == "owner_attested_with_evidence":
        if not payload.approval_id:
            raise PermissionDeniedError(
                "owner attestation requires a hash-bound approval_id "
                "(financial.revenue_verify)")
        approval = get_application(request).approvals.get(payload.approval_id)
        record = svc.revenue.get_revenue(revenue_id)
        if not get_application(request).approvals.verify_binding(
                approval, "financial.revenue_verify", record["business_id"],
                {"revenue_id": revenue_id, "source": payload.source}):
            raise PermissionDeniedError(
                "approval does not bind this verification (drift)")
    return ok(svc.revenue.verify_revenue(
        principal, revenue_id, source=payload.source,
        evidence=payload.evidence))


@router.post("/financial/revenue/{revenue_id}/refunds", status_code=201)
async def create_refund(request: Request, revenue_id: str,
                        payload: RefundCreateIn,
                        principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    return ok(svc.revenue.create_refund(principal, revenue_id, {
        "amount": _money(svc, payload.amount, payload.currency),
        "refund_date": payload.refund_date, "reason": payload.reason,
        "source": payload.source, "external_ref": payload.external_ref}))


@router.post("/financial/revenue/{revenue_id}/disputes", status_code=201)
async def create_dispute(request: Request, revenue_id: str,
                         payload: DisputeCreateIn,
                         principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    return ok(svc.revenue.create_dispute(principal, revenue_id, {
        "amount": _money(svc, payload.amount, payload.currency),
        "opened_date": payload.opened_date, "kind": payload.kind,
        "reason": payload.reason, "external_ref": payload.external_ref}))


@router.post("/financial/invoices", status_code=201)
async def create_invoice(request: Request, payload: InvoiceCreateIn,
                         principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    return ok(svc.revenue.create_invoice(principal, payload.business_id, {
        "number": payload.number,
        "amount": _money(svc, payload.amount, payload.currency),
        "issued_date": payload.issued_date, "due_date": payload.due_date,
        "customer_ref": payload.customer_ref,
        "revenue_record_id": payload.revenue_record_id}))


@router.post("/financial/orders", status_code=201)
async def create_order(request: Request, payload: OrderCreateIn,
                       principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    return ok(svc.revenue.create_order(principal, payload.business_id, {
        "amount": _money(svc, payload.amount, payload.currency),
        "order_date": payload.order_date,
        "external_ref": payload.external_ref,
        "customer_ref": payload.customer_ref, "channel": payload.channel}))


@router.post("/financial/subscriptions", status_code=201)
async def create_subscription(request: Request, payload: SubscriptionCreateIn,
                              principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    return ok(svc.revenue.create_subscription(principal, payload.business_id, {
        "plan_ref": payload.plan_ref,
        "amount": _money(svc, payload.amount, payload.currency),
        "interval": payload.interval, "status": payload.status,
        "started_date": payload.started_date,
        "current_period_end": payload.current_period_end,
        "customer_ref": payload.customer_ref}))


@router.post("/financial/subscriptions/{subscription_id}/status")
async def subscription_status(request: Request, subscription_id: str,
                              payload: SubscriptionStatusIn,
                              principal: Principal = Depends(WRITE)):
    return ok(_svc(request).revenue.set_subscription_status(
        principal, subscription_id, payload.status))


# ---------------------------------------------------------------- expenses
@router.post("/financial/expenses", status_code=201)
async def create_expense(request: Request, payload: ExpenseCreateIn,
                         principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    return ok(svc.expenses.create_expense(principal, payload.business_id, {
        "category": payload.category,
        "amount": _money(svc, payload.amount, payload.currency),
        "expense_date": payload.expense_date, "kind": payload.kind,
        "vendor": payload.vendor, "description": payload.description,
        "recurrence_type": payload.recurrence_type,
        "cost_behavior": payload.cost_behavior,
        "directness": payload.directness,
        "payment_status": payload.payment_status,
        "payment_source": payload.payment_source, "evidence": payload.evidence,
        "verification_status": payload.verification_status,
        "project_ref": payload.project_ref,
        "experiment_ref": payload.experiment_ref,
        "budget_id": payload.budget_id, "agent_id": payload.agent_id,
        "task_id": payload.task_id,
        "execution_request_id": payload.execution_request_id}))


@router.get("/financial/expenses")
async def list_expenses(request: Request,
                        principal: Principal = Depends(READ),
                        business_id: str = Query(...),
                        limit: int = Query(50), offset: int = Query(0)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    rows, total = svc.expenses.list_expenses(business_id, limit, offset)
    return page(rows, total, limit, offset)


@router.get("/financial/expenses/recurring")
async def recurring_expenses(request: Request,
                             principal: Principal = Depends(READ),
                             business_id: str = Query(...)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    return ok(svc.expenses.detect_recurring(business_id))


@router.get("/financial/expenses/{expense_id}")
async def get_expense(request: Request, expense_id: str, _=Depends(READ)):
    return ok(_svc(request).expenses.get_expense(expense_id))


# ----------------------------------------------------------------- budgets
@router.post("/financial/budgets", status_code=201)
async def create_budget(request: Request, payload: BudgetCreateIn,
                        principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    return ok(svc.budgets.create_budget(principal, {
        "scope_type": payload.scope_type, "scope_ref": payload.scope_ref,
        "business_id": payload.business_id,
        "parent_budget_id": payload.parent_budget_id, "name": payload.name,
        "amount": _money(svc, payload.amount, payload.currency),
        "period_start": payload.period_start, "period_end": payload.period_end,
        "approval_requirement": payload.approval_requirement,
        "review_date": payload.review_date}))


@router.get("/financial/budgets")
async def list_budgets(request: Request, _=Depends(READ),
                       business_id: str | None = Query(None),
                       limit: int = Query(50), offset: int = Query(0)):
    rows, total = _svc(request).budgets.list_budgets(business_id, limit, offset)
    return page(rows, total, limit, offset)


@router.get("/financial/budgets/{budget_id}")
async def get_budget(request: Request, budget_id: str, _=Depends(READ)):
    return ok(_svc(request).budgets.budget_utilisation(budget_id))


@router.get("/financial/budgets/{budget_id}/utilisation")
async def budget_utilisation(request: Request, budget_id: str,
                             _=Depends(READ)):
    return ok(_svc(request).budgets.budget_utilisation(budget_id))


@router.post("/financial/spending-requests", status_code=201)
async def request_spend(request: Request, payload: SpendRequestIn,
                        principal: Principal = Depends(get_principal)):
    """Any authenticated principal may REQUEST; the engine decides.
    An authorised decision records a commitment only — no payment or
    transfer is ever executed by P-07 (§23.2)."""
    svc = _svc(request)
    return ok(svc.budgets.request_spend(principal, payload.business_id, {
        "amount": _money(svc, payload.amount, payload.currency),
        "category": payload.category, "purpose": payload.purpose,
        "kind": payload.kind, "budget_id": payload.budget_id,
        "agent_id": payload.agent_id, "task_id": payload.task_id,
        "project_ref": payload.project_ref,
        "experiment_ref": payload.experiment_ref}))


@router.get("/financial/spending-requests")
async def list_spend_requests(request: Request,
                              principal: Principal = Depends(READ),
                              business_id: str = Query(...),
                              limit: int = Query(50),
                              offset: int = Query(0)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    rows, total = svc.budgets.list_requests(business_id, limit, offset)
    return page(rows, total, limit, offset)


@router.post("/financial/spending-requests/{request_id}/approve")
async def approve_spend(request: Request, request_id: str,
                        payload: SpendApproveIn,
                        principal: Principal = Depends(APPROVE)):
    return ok(_svc(request).budgets.approve_spend(
        principal, request_id, payload.approval_id))


@router.post("/financial/spending-requests/{request_id}/reject")
async def reject_spend(request: Request, request_id: str,
                       payload: SpendRejectIn,
                       principal: Principal = Depends(APPROVE)):
    return ok(_svc(request).budgets.reject_spend(
        principal, request_id, reason=payload.reason))


@router.post("/financial/spending-requests/{request_id}/record")
async def record_spend(request: Request, request_id: str,
                       payload: SpendRecordIn,
                       principal: Principal = Depends(WRITE)):
    return ok(_svc(request).budgets.mark_recorded(
        principal, request_id, payload.expense_id))


# ---------------------------------------------------------------- reserves
@router.post("/financial/reserves", status_code=201)
async def create_reserve(request: Request, payload: ReserveCreateIn,
                         principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    return ok(svc.budgets.create_reserve(principal, {
        "reserve_type": payload.reserve_type,
        "amount": _money(svc, payload.amount, payload.currency),
        "business_id": payload.business_id,
        "target": _money(svc, payload.target, payload.currency)
        if payload.target else None}))


@router.get("/financial/reserves")
async def list_reserves(request: Request, _=Depends(READ),
                        business_id: str | None = Query(None)):
    return ok(_svc(request).budgets.list_reserves(business_id))


@router.post("/financial/reserves/{reserve_id}/balance")
async def set_reserve_balance(request: Request, reserve_id: str,
                              payload: ReserveBalanceIn,
                              principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    return ok(svc.budgets.set_reserve_balance(
        principal, reserve_id,
        _money(svc, payload.amount, payload.currency),
        reason=payload.reason))


@router.get("/financial/businesses/{business_id}/available-cash")
async def available_cash(request: Request, business_id: str,
                         principal: Principal = Depends(READ),
                         currency: str = Query("INR")):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    return ok(svc.budgets.available_cash(business_id, currency))


# ---------------------------------------------------------------- payments
@router.get("/financial/payments/providers")
async def list_providers(request: Request, _=Depends(READ)):
    return ok(_svc(request).payments.list_providers())


@router.get("/financial/payments/providers/{name}/health")
async def provider_health(request: Request, name: str, _=Depends(READ)):
    return ok(_svc(request).payments.provider_health(name))


@router.post("/financial/payments/webhooks/{provider}")
async def webhook(request: Request, provider: str):
    """Unauthenticated by design — authenticity is the provider's
    HMAC signature over the raw body (§7.2)."""
    svc = _svc(request)
    raw = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    return ok(svc.payments.process_webhook(provider, raw, headers))


# ----------------------------------------------------------- reconciliation
@router.post("/financial/reconciliation/import", status_code=201)
async def reconciliation_import(request: Request,
                                payload: ReconciliationImportIn,
                                principal: Principal = Depends(WRITE)):
    svc = _svc(request)
    parsed = svc.payments.import_statement(
        principal, payload.business_id, csv_text=payload.csv_text,
        source_type=payload.source_type, source_ref=payload.source_ref)
    return ok(svc.reconciliation.create_session_with_items(
        principal, payload.business_id, source_type=payload.source_type,
        source_ref=payload.source_ref, items=parsed["items"]))


@router.post("/financial/reconciliation/{session_id}/run")
async def reconciliation_run(request: Request, session_id: str,
                             principal: Principal = Depends(WRITE)):
    return ok(_svc(request).reconciliation.run_matching(principal, session_id))


@router.get("/financial/reconciliation")
async def reconciliation_list(request: Request,
                              principal: Principal = Depends(READ),
                              business_id: str = Query(...),
                              limit: int = Query(50),
                              offset: int = Query(0)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    rows, total = svc.reconciliation.list_sessions(business_id, limit, offset)
    return page(rows, total, limit, offset)


@router.get("/financial/reconciliation/{session_id}")
async def reconciliation_get(request: Request, session_id: str,
                             _=Depends(READ)):
    return ok(_svc(request).reconciliation.get_session(session_id))


@router.post("/financial/reconciliation/items/{item_id}/resolve")
async def reconciliation_resolve(request: Request, item_id: str,
                                 payload: ReconciliationResolveIn,
                                 principal: Principal = Depends(WRITE)):
    return ok(_svc(request).reconciliation.resolve_item(principal, item_id, {
        "action": payload.action, "reason": payload.reason,
        "evidence": payload.evidence}))


# ---------------------------------------------------------------------- FX
@router.post("/financial/fx/rates", status_code=201)
async def add_rate(request: Request, payload: RateIn,
                   principal: Principal = Depends(WRITE)):
    return ok(_svc(request).add_exchange_rate(principal, {
        "from_currency": payload.from_currency,
        "to_currency": payload.to_currency, "rate": payload.rate,
        "source": payload.source}))


@router.post("/financial/fx/convert")
async def convert_currency(request: Request, payload: ConvertIn,
                           principal: Principal = Depends(READ)):
    svc = _svc(request)
    return ok(svc.convert_amount(
        _money(svc, payload.amount, payload.currency), payload.to_currency))


# --------------------------------------------------------------- forecasting
@router.post("/financial/forecasts", status_code=201)
async def create_forecast(request: Request, payload: ForecastCreateIn,
                          principal: Principal = Depends(WRITE)):
    return ok(_svc(request).forecasting.create_forecast(
        principal, payload.business_id, {
            "forecast_type": payload.forecast_type, "method": payload.method,
            "currency": payload.currency}))


@router.get("/financial/forecasts")
async def list_forecasts(request: Request,
                         principal: Principal = Depends(READ),
                         business_id: str = Query(...)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    return ok(svc.forecasting.list_forecasts(business_id))


@router.get("/financial/forecasts/{forecast_id}/vs-actual")
async def forecast_vs_actual(request: Request, forecast_id: str,
                             _=Depends(READ)):
    return ok(_svc(request).forecasting.forecast_vs_actual(forecast_id))


@router.post("/financial/scenarios", status_code=201)
async def create_scenario(request: Request, payload: ScenarioCreateIn,
                          principal: Principal = Depends(WRITE)):
    data = {"scenario_type": payload.scenario_type,
            "currency": payload.currency,
            "display_label": payload.display_label,
            "assumptions": payload.assumptions, "risks": payload.risks,
            "confidence": payload.confidence}
    if payload.revenue_factor is not None:
        data["revenue_factor"] = payload.revenue_factor
    if payload.expense_factor is not None:
        data["expense_factor"] = payload.expense_factor
    return ok(_svc(request).forecasting.create_scenario(
        principal, payload.business_id, data))


@router.get("/financial/scenarios")
async def list_scenarios(request: Request,
                         principal: Principal = Depends(READ),
                         business_id: str = Query(...)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    return ok(svc.forecasting.list_scenarios(business_id))


# ------------------------------------------------------------------- alerts
@router.get("/financial/alerts")
async def list_alerts(request: Request, _=Depends(READ),
                      business_id: str | None = Query(None),
                      limit: int = Query(50), offset: int = Query(0)):
    rows, total = _svc(request).analytics.list_alerts(business_id, limit, offset)
    return page(rows, total, limit, offset)


# ---------------------------------------------------------------------- tax
@router.post("/financial/businesses/{business_id}/tax-records", status_code=201)
async def create_tax_record(request: Request, business_id: str,
                            payload: TaxRecordIn,
                            principal: Principal = Depends(WRITE)):
    return ok(_svc(request).create_tax_record(principal, business_id, {
        "jurisdiction": payload.jurisdiction, "category": payload.category,
        "period_label": payload.period_label, "currency": payload.currency,
        "estimated_liability": payload.estimated_liability,
        "collected": payload.collected, "payable": payload.payable,
        "paid": payload.paid, "due_date": payload.due_date,
        "rate": payload.rate, "notes": payload.notes}))


@router.get("/financial/businesses/{business_id}/tax-records")
async def list_tax_records(request: Request, business_id: str,
                           principal: Principal = Depends(READ)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    return ok(svc.list_tax_records(business_id))


# --------------------------------------------------------------- task costs
@router.post("/financial/task-costs", status_code=201)
async def record_task_cost(request: Request, payload: TaskCostIn,
                           principal: Principal = Depends(WRITE)):
    return ok(_svc(request).record_task_cost(principal, {
        "business_id": payload.business_id, "category": payload.category,
        "currency": payload.currency, "estimated": payload.estimated,
        "approved_limit": payload.approved_limit, "actual": payload.actual,
        "cost_kind": payload.cost_kind, "project_ref": payload.project_ref,
        "agent_id": payload.agent_id, "task_id": payload.task_id,
        "execution_request_id": payload.execution_request_id,
        "approval_requirement": payload.approval_requirement,
        "notes": payload.notes}))


@router.get("/financial/task-costs")
async def list_task_costs(request: Request,
                          principal: Principal = Depends(READ),
                          business_id: str = Query(...)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    return ok(svc.list_task_costs(business_id))


# ------------------------------------------------------------------ analyst
@router.post("/financial/analyst/query")
async def analyst_query(request: Request, payload: AnalystQueryIn,
                        principal: Principal = Depends(READ)):
    svc = _svc(request)
    if payload.business_id:
        _guard(svc, principal, payload.business_id)
    return ok(svc.analyst.answer(
        {"intent": payload.intent, "business_id": payload.business_id,
         "currency": payload.currency},
        businesses=svc.list_business_ids()))


# ---------------------------------------------------------------- approvals
@router.get("/financial/approvals")
async def list_financial_approvals(request: Request, _=Depends(APPROVE),
                                   status: str | None = Query(None),
                                   limit: int = Query(50),
                                   offset: int = Query(0)):
    application = get_application(request)
    rows = application.approvals.list(status=status, limit=limit, offset=offset)
    financial = [a for a in rows if a.action.startswith("financial.")]
    return ok([{
        "id": a.id, "action": a.action, "resource": a.resource,
        "status": a.status, "parameters": a.parameters,
        "requester": f"{a.requesting_principal_type}:{a.requesting_principal_id}",
        "approver_id": a.approver_id,
        "system": "P-01 ApprovalService (hash-bound) — P-07 keeps no "
                  "parallel approval system",
    } for a in financial])


@router.post("/financial/approvals/{approval_id}/decision")
async def decide_financial_approval(request: Request, approval_id: str,
                                    payload: ApprovalDecisionIn,
                                    principal: Principal = Depends(APPROVE)):
    application = get_application(request)
    approval = application.approvals.decide(
        approval_id, principal, payload.approve, payload.notes)
    return ok({"id": approval.id, "status": approval.status,
               "action": approval.action})


# ------------------------------------------------------------------ reports
@router.get("/financial/reports/profit-loss")
async def report_profit_loss(request: Request,
                             principal: Principal = Depends(READ),
                             business_id: str = Query(...),
                             currency: str = Query("INR"),
                             start: str | None = Query(None),
                             end: str | None = Query(None),
                             format: str | None = Query(None)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    report = svc.reports.profit_loss(business_id, currency,
                                     start=start, end=end)
    return _export(request, report, format)


@router.get("/financial/reports/balance-sheet")
async def report_balance_sheet(request: Request,
                               principal: Principal = Depends(READ),
                               business_id: str = Query(...),
                               currency: str = Query("INR"),
                               as_of: str | None = Query(None),
                               format: str | None = Query(None)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    report = svc.reports.balance_sheet(business_id, currency, as_of=as_of)
    return _export(request, report, format)


@router.get("/financial/reports/cashflow")
async def report_cashflow(request: Request,
                          principal: Principal = Depends(READ),
                          business_id: str = Query(...),
                          currency: str = Query("INR"),
                          start: str = Query(...), end: str = Query(...),
                          format: str | None = Query(None)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    report = svc.reports.cashflow_statement(business_id, currency,
                                            start=start, end=end)
    return _export(request, report, format)


@router.get("/financial/reports/budget-utilization")
async def report_budget_utilization(request: Request,
                                    principal: Principal = Depends(READ),
                                    business_id: str = Query(...),
                                    format: str | None = Query(None)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    report = svc.reports.budget_utilization_report(business_id)
    return _export(request, report, format)


@router.get("/financial/reports/reconciliation")
async def report_reconciliation(request: Request,
                                principal: Principal = Depends(READ),
                                business_id: str = Query(...),
                                format: str | None = Query(None)):
    svc = _svc(request)
    _guard(svc, principal, business_id)
    report = svc.reports.reconciliation_report(business_id)
    return _export(request, report, format)


@router.get("/financial/reports/business-comparison")
async def report_business_comparison(request: Request, _=Depends(READ),
                                     currency: str = Query("INR"),
                                     format: str | None = Query(None)):
    svc = _svc(request)
    report = {"report": "business_comparison", "currency": currency,
              **svc.consolidated(currency)}
    return _export(request, report, format)
