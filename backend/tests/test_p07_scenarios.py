"""P-07 critical financial scenarios (§26.4), one named test each.
All amounts are the prompt's own ₹ figures, in INR records."""
from __future__ import annotations

import json
import threading

from sqlalchemy import select

from app.database.models.core import AuditEvent
from app.financial.payments import fake_webhook_headers
from tests.conftest import OWNER
from tests.p07_support import (
    AGENT, app_fin, business_with_profile, money, paid_expense,
    verified_revenue,
)


def _audit_actions(application, action: str) -> list:
    session = application.financial._session_factory()
    try:
        return list(session.scalars(
            select(AuditEvent).where(AuditEvent.action == action)).all())
    finally:
        session.close()


def _fake_body(business_id: str, event_id: str, amount_minor: int,
               ref: str = "pay-1") -> bytes:
    return json.dumps({
        "event_id": event_id, "type": "payment.settled",
        "payment_ref": ref, "business_id": business_id,
        "amount_minor": amount_minor, "currency": "INR",
        "occurred_date": "2026-11-05",
    }).encode()


# ------------------------------------------------------------ Scenario 1
async def test_scenario_01_projected_vs_collected(app_fin):
    """₹50,000 forecast, ₹10,000 received: the two figures are never
    merged."""
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    fin.revenue.create_revenue(OWNER, business_id, {
        "category": "product_sale",
        "amount": money(app_fin, "50000.00"),
        "transaction_date": "2026-11-05", "source": "manual",
        "initial_status": "EXPECTED", "creation_method": "forecast"})
    await verified_revenue(app_fin, business_id, "10000.00")
    metrics = fin.revenue.metrics(business_id, "INR")
    assert metrics["projected_minor"] == 5000000
    assert metrics["net_collected_minor"] == 1000000
    assert metrics["projected_minor"] != metrics["net_collected_minor"]


# ------------------------------------------------------------ Scenario 2
async def test_scenario_02_refund(app_fin):
    """₹1,000 paid, ₹200 refunded: original traceable, refund separate,
    net reflects the refund, ledger balanced."""
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    record = await verified_revenue(app_fin, business_id, "1000.00")
    original_entry = record["journal_entry_id"]
    refund = fin.revenue.create_refund(OWNER, record["id"], {
        "amount": money(app_fin, "200.00"), "refund_date": "2026-11-07"})
    after = fin.revenue.get_revenue(record["id"])
    assert after["amount_minor"] == 100000  # original untouched
    assert after["journal_entry_id"] == original_entry
    assert refund["id"] != record["id"]
    assert fin.revenue.metrics(business_id, "INR")["net_collected_minor"] \
        == 80000
    assert fin.ledger.verify_integrity(business_id)["ok"] is True


# ------------------------------------------------------------ Scenario 3
async def test_scenario_03_duplicate_webhook(app_fin):
    """The same signed payment event delivered three times posts
    exactly one economic transaction."""
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    body = _fake_body(business_id, "evt-dup-1", 1000000)
    headers = fake_webhook_headers("fake-provider-test-secret", body)
    results = [fin.payments.process_webhook("fake-provider", body, headers)
               for _ in range(3)]
    assert results[0]["status"] == "processed"
    assert results[1]["status"] == "duplicate"
    assert results[2]["status"] == "duplicate"
    metrics = fin.revenue.metrics(business_id, "INR")
    assert metrics["net_collected_minor"] == 1000000
    assert metrics["collected_count"] == 1


# ------------------------------------------------------------ Scenario 4
async def test_scenario_04_unverified_payment(app_fin):
    """An agent reports a ₹5,000 payment with no authoritative
    evidence: it stays unverified and never counts as collected."""
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    record = fin.revenue.create_revenue(AGENT, business_id, {
        "category": "product_sale", "amount": money(app_fin, "5000.00"),
        "transaction_date": "2026-11-05", "source": "manual",
        "initial_status": "PAYMENT_SETTLED",
        "creation_method": "agent_report",
        "description": "agent claims the customer paid"})
    assert record["verification_status"] == "unverified"
    assert record["classification"] == "booked"  # settled != collected
    metrics = fin.revenue.metrics(business_id, "INR")
    assert metrics["net_collected_minor"] == 0
    # And it cannot be walked into VERIFIED without evidence.
    import pytest
    from app.core.exceptions import InvalidStateTransitionError
    with pytest.raises(InvalidStateTransitionError):
        fin.revenue.transition(AGENT, record["id"], "VERIFIED")


# ------------------------------------------------------------ Scenario 5
async def test_scenario_05_budget_restriction(app_fin):
    """₹10,000 available but the experiment budget is ₹2,000: a
    ₹2,500 spend is held for the owner, nothing is obligated, and
    the decision is audited."""
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    fin.record_opening_balance(OWNER, business_id, {
        "amount": money(app_fin, "10000.00"), "entry_date": "2026-11-01"})
    budget = fin.budgets.create_budget(OWNER, {
        "scope_type": "experiment", "business_id": business_id,
        "scope_ref": "exp-1", "name": "Experiment budget",
        "amount": money(app_fin, "2000.00"),
        "period_start": "2026-11-01", "period_end": "2026-11-30",
        "approval_requirement": "level_1"})
    decision = fin.budgets.request_spend(AGENT, business_id, {
        "amount": money(app_fin, "2500.00"), "category": "advertising",
        "kind": "expense", "budget_id": budget["id"],
        "experiment_ref": "exp-1", "purpose": "test ad spend"})
    assert decision["status"] == "held_for_owner"
    assert decision["expense_record_id"] is None
    expenses, total = fin.expenses.list_expenses(business_id)
    assert total == 0  # no obligation was created
    assert _audit_actions(app_fin, "financial.spend_decided")


# ------------------------------------------------------------ Scenario 6
async def test_scenario_06_protected_reserves(app_fin):
    """₹20,000 cash − ₹5,000 reserve − ₹3,000 committed − ₹2,000
    obligations = ₹10,000 available (§9.4's own example)."""
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    fin.record_opening_balance(OWNER, business_id, {
        "amount": money(app_fin, "20000.00"), "entry_date": "2026-11-01",
        "account_ref": "bank:primary", "source": "bank_statement",
        "verification_status": "verified"})
    fin.budgets.create_reserve(OWNER, {
        "reserve_type": "emergency",
        "amount": money(app_fin, "5000.00"), "business_id": business_id})
    budget = fin.budgets.create_budget(OWNER, {
        "scope_type": "business", "business_id": business_id,
        "name": "Operations", "amount": money(app_fin, "50000.00"),
        "period_start": "2026-11-01", "period_end": "2026-11-30",
        "approval_requirement": "level_1"})
    decision = fin.budgets.request_spend(OWNER, business_id, {
        "amount": money(app_fin, "3000.00"), "category": "operational",
        "kind": "expense", "budget_id": budget["id"],
        "purpose": "committed hosting contract"})
    assert decision["status"] == "authorised_level1"
    fin.ledger.post_simple(
        OWNER, business_id, debit_code="5060", credit_code="2000",
        amount_minor=200000, currency="INR", entry_date="2026-11-06",
        description="unpaid vendor bill (obligation)")
    available = fin.budgets.available_cash(business_id, "INR")
    assert available["cash_balance_minor"] == 2000000
    assert available["protected_reserves_minor"] == 500000
    assert available["committed_minor"] == 300000
    assert available["obligations_minor"] == 200000
    assert available["available_cash_minor"] == 1000000


# ------------------------------------------------------------ Scenario 7
async def test_scenario_07_currency_conversion(app_fin):
    """USD revenue reported in INR: original intact, rate + timestamp
    recorded, converted figure traceable; missing rate -> pending."""
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    record = await verified_revenue(app_fin, business_id, "100.00",
                                    currency="USD", date="2026-11-05")
    pending = fin.convert_amount(money(app_fin, "100.00", "USD"), "INR")
    assert pending["status"] == "pending"
    assert pending["converted_minor"] is None
    rate = fin.add_exchange_rate(OWNER, {
        "from_currency": "USD", "to_currency": "INR", "rate": "83.25",
        "source": "manual_owner"})
    converted = fin.convert_amount(money(app_fin, "100.00", "USD"), "INR")
    assert converted["status"] == "converted"
    assert converted["converted_minor"] == 832500
    assert converted["rate"] == "83.25"
    assert converted["rate_id"] == rate["id"]
    assert converted["rate_recorded_at"] is not None
    original = fin.revenue.get_revenue(record["id"])
    assert original["amount_minor"] == 10000
    assert original["currency"] == "USD"


# ------------------------------------------------------------ Scenario 8
async def test_scenario_08_reconciliation_mismatch(app_fin):
    """Provider says ₹1,000, the ledger says ₹900: flagged, neither
    value overwritten; resolution is an audited adjustment."""
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    record = await verified_revenue(app_fin, business_id, "900.00",
                                    external_ref="pay-900")
    parsed = fin.payments.import_statement(
        OWNER, business_id,
        csv_text=("date,description,amount,currency,external_ref\n"
                  "2026-11-05,provider settlement,1000.00,INR,pay-900\n"),
        source_type="provider_statement", source_ref="fake-nov")
    session = fin.reconciliation.create_session_with_items(
        OWNER, business_id, source_type="provider_statement",
        source_ref="fake-nov", items=parsed["items"])
    result = fin.reconciliation.run_matching(OWNER, session["id"])
    assert result["status"] == "needs_review"
    detail = fin.reconciliation.get_session(session["id"])
    item = detail["items"][0]
    assert item["classification"] == "AMOUNT_MISMATCH"
    assert item["discrepancy"]["difference_minor"] == 10000
    # Neither side was overwritten.
    assert fin.revenue.get_revenue(record["id"])["amount_minor"] == 90000
    assert item["external_amount_minor"] == 100000
    resolved = fin.reconciliation.resolve_item(OWNER, item["id"], {
        "action": "create_adjustment",
        "reason": "provider settlement included a ₹100 bonus; "
                  "adjustment booked, originals untouched",
        "evidence": {"statement": "fake-nov"}})
    assert resolved["status"] == "resolved"
    assert resolved["resolution"]["journal_entry_id"]
    assert fin.revenue.get_revenue(record["id"])["amount_minor"] == 90000
    assert fin.ledger.verify_integrity(business_id)["ok"] is True


# ------------------------------------------------------------ Scenario 9
async def test_scenario_09_consolidated_reporting(app_fin):
    """An internal transfer is visible in both businesses' records
    and is NOT new portfolio revenue."""
    business_a, _ = await business_with_profile(app_fin, name="Ebook One")
    business_b, _ = await business_with_profile(
        app_fin, name="Ebook Two", template="content_publication",
        category="content")
    fin = app_fin.financial
    fin.record_opening_balance(OWNER, business_a, {
        "amount": money(app_fin, "10000.00"), "entry_date": "2026-11-01"})
    await verified_revenue(app_fin, business_a, "2000.00")
    transfer = fin.record_internal_transfer(OWNER, business_a, business_b, {
        "amount": money(app_fin, "5000.00"), "entry_date": "2026-11-06",
        "reference": "xfer-1"})
    assert transfer["counted_as_revenue"] is False
    # Visible in both businesses' journals.
    entries_a, _ = fin.ledger.list_entries(business_a)
    entries_b, _ = fin.ledger.list_entries(business_b)
    assert any(e["is_internal_transfer"] for e in entries_a)
    assert any(e["is_internal_transfer"] for e in entries_b)
    assert fin.ledger.account_balance(business_b, "1000") == 500000
    # Consolidated: only the real ₹2,000 counts as revenue.
    consolidated = fin.consolidated("INR")
    assert consolidated["totals"]["net_collected_minor"] == 200000
    assert consolidated["internal_transfers_excluded"] is True


# ----------------------------------------------------------- Scenario 10
async def test_scenario_10_missing_financial_data(app_fin):
    """Projected revenue only: health is INSUFFICIENT_DATA and no
    profit is invented."""
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    fin.revenue.create_revenue(OWNER, business_id, {
        "category": "product_sale", "amount": money(app_fin, "50000.00"),
        "transaction_date": "2026-11-05", "source": "manual",
        "initial_status": "EXPECTED", "creation_method": "forecast"})
    health = fin.analytics.health(business_id, "INR")
    assert health["status"] == "INSUFFICIENT_DATA"
    profit = fin.analytics.profitability(business_id, "INR")
    assert profit["status"] == "insufficient_data"
    assert profit["net_profit_minor"] is None
    assert profit["missing_data"]


# ----------------------------------------------------------- Scenario 11
async def test_scenario_11_concurrent_payment_events(app_fin):
    """Two workers deliver the same payment simultaneously: one
    posting, a consistent ledger."""
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    body = _fake_body(business_id, "evt-race-1", 700000, ref="pay-race")
    headers = fake_webhook_headers("fake-provider-test-secret", body)
    barrier = threading.Barrier(2)
    results: list[dict] = []
    errors: list[Exception] = []

    def deliver():
        try:
            barrier.wait(timeout=10)
            results.append(fin.payments.process_webhook(
                "fake-provider", body, headers))
        except Exception as exc:  # collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=deliver) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert errors == []
    statuses = sorted(r["status"] for r in results)
    assert statuses == ["duplicate", "processed"]
    assert fin.revenue.metrics(business_id, "INR")["net_collected_minor"] \
        == 700000
    assert fin.ledger.verify_integrity(business_id)["ok"] is True


# ----------------------------------------------------------- Scenario 12
async def test_scenario_12_failed_posting_rolls_back(app_fin):
    """A journal operation that fails partway leaves no partial or
    unbalanced entry behind."""
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    accounts = {a["code"]: a for a in fin.ledger.list_accounts(business_id)}
    before, total_before = fin.ledger.list_entries(business_id, limit=100)
    assert total_before == 0
    import pytest
    with pytest.raises(Exception):
        fin.ledger.post_entry(
            OWNER, business_id,
            lines=[
                {"account_id": accounts["1000"]["id"],
                 "debit_minor": 10000, "credit_minor": 0,
                 "currency": "INR"},
                {"account_id": accounts["3000"]["id"],
                 "debit_minor": 0, "credit_minor": 10000},
                # ^ missing currency -> fails mid-operation
            ], entry_date="2026-11-05",
            idempotency_key="scenario12:doomed")
    _after, total_after = fin.ledger.list_entries(business_id, limit=100)
    assert total_after == 0  # nothing partial persisted
    assert fin.ledger.verify_integrity(business_id)["ok"] is True
    assert fin.ledger.account_balance(business_id, "1000") == 0


# ----------------------------------------------------------- Scenario 13
async def test_scenario_13_negative_financial_outcome(app_fin):
    """₹5,000 in, ₹8,000 out: the loss is reported as a loss."""
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    await verified_revenue(app_fin, business_id, "5000.00")
    await paid_expense(app_fin, business_id, "8000.00")
    profit = fin.analytics.profitability(business_id, "INR")
    assert profit["net_profit_minor"] == -300000
    assert profit["is_loss"] is True
    health = fin.analytics.health(business_id, "INR")
    assert health["status"] != "HEALTHY"
    assert any("loss" in reason for reason in health["reasons"])


# ----------------------------------------------------------- Scenario 14
async def test_scenario_14_unauthorized_transfer_request(app_fin):
    """An agent attempts a transfer: blocked, audited, and no
    credential material appears anywhere in the outcome."""
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    decision = fin.budgets.request_spend(AGENT, business_id, {
        "amount": money(app_fin, "1000.00"), "category": "operational",
        "kind": "transfer", "purpose": "move money to an external wallet"})
    assert decision["status"] == "blocked_level3"
    assert decision["required_level"] == 3
    assert _audit_actions(app_fin, "financial.level3_blocked")
    rendered = json.dumps(decision).lower()
    assert "secret" not in rendered
    assert "credential" not in rendered
    assert "sk-" not in rendered
    _entries, total = fin.ledger.list_entries(business_id)
    assert total == 0  # nothing moved, nothing posted
