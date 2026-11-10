"""P-14 Stage A §10 Financial Reconciliation — additive audit tests.

Fixtures only. No production code is modified by this suite.
Simulations (a)-(g) + 8 invariants, verified end-to-end against
P-07 (sole financial authority) and P-13 (analytical layer only).
"""
from __future__ import annotations

import json

import pytest

from app.core.exceptions import PermissionDeniedError, ValidationError
from app.financial.payments import fake_webhook_headers
from tests.conftest import OWNER
from tests.p06_support import DECLARATION, make_fixture_business
from tests.p07_support import (
    AGENT, EXTERNAL, app_fin, business_with_profile, money, paid_expense,
    verified_revenue,
)
from tests.p13_support import (
    app_portfolio, business_with_collected, make_business, make_portfolio,
    make_service_with_access,
)

pytestmark = pytest.mark.asyncio


async def _usd_business(application, name="USD Biz"):
    """Business whose P-07 profile is USD (manual path: the p07
    helper forces INR, so set the governed default before blueprint)."""
    svc = application.business
    _opp, biz = await make_fixture_business(application, name=name)
    bid = biz["id"]
    svc.update_settings(OWNER, {"default_currency": "USD"})
    await svc.create_declaration(OWNER, bid, DECLARATION)
    await svc.generate_blueprint(OWNER, bid)
    profile = await application.financial.ensure_profile(OWNER, bid)
    assert profile["base_currency"] == "USD", profile
    return bid


# (a) profitable
async def test_p14_a_profitable_business(app_fin):
    bid, _ = await business_with_profile(app_fin, name="P14 Profitable")
    await verified_revenue(app_fin, bid, "10000.00")
    await paid_expense(app_fin, bid, "3000.00")
    fin = app_fin.financial
    profit = fin.analytics.profitability(bid, "INR")
    assert profit["status"] == "computed"
    assert profit["net_revenue_minor"] == 1000000
    assert profit["net_profit_minor"] == 700000
    assert profit["is_loss"] is False
    assert fin.ledger.verify_integrity(bid)["ok"] is True
    cons = fin.consolidated("INR")
    row = next(b for b in cons["businesses"] if b["business_id"] == bid)
    assert row["net_profit_minor"] == 700000


# (b) loss-making
async def test_p14_b_loss_making_business(app_fin):
    bid, _ = await business_with_profile(app_fin, name="P14 Loss")
    await verified_revenue(app_fin, bid, "5000.00")
    await paid_expense(app_fin, bid, "8000.00")
    profit = app_fin.financial.analytics.profitability(bid, "INR")
    assert profit["net_profit_minor"] == -300000
    assert profit["is_loss"] is True
    health = app_fin.financial.analytics.health(bid, "INR")
    assert health["status"] != "HEALTHY"
    assert any("loss" in r for r in health["reasons"])


# (c) newly launched, zero transactions -> honest insufficient
async def test_p14_c_new_business_zero_transactions_honest(app_fin):
    bid, _ = await business_with_profile(app_fin, name="P14 New")
    fin = app_fin.financial
    metrics = fin.revenue.metrics(bid, "INR")
    assert metrics["net_collected_minor"] == 0
    assert metrics["collected_count"] == 0
    assert metrics["projected_minor"] == 0
    profit = fin.analytics.profitability(bid, "INR")
    assert profit["status"] == "insufficient_data"
    assert profit["net_profit_minor"] is None
    assert profit["missing_data"]
    health = fin.analytics.health(bid, "INR")
    assert health["status"] == "INSUFFICIENT_DATA"
    avail = fin.budgets.available_cash(bid, "INR")
    assert avail["cash_balance_minor"] == 0
    assert avail["available_cash_minor"] == 0
    entries, total = fin.ledger.list_entries(bid)
    assert total == 0


# (d) outstanding liabilities
async def test_p14_d_outstanding_liabilities(app_fin):
    bid, _ = await business_with_profile(app_fin, name="P14 Liabilities")
    fin = app_fin.financial
    fin.record_opening_balance(OWNER, bid, {
        "amount": money(app_fin, "5000.00"), "entry_date": "2026-11-01"})
    # Unpaid vendor bill: Dr operational expense / Cr accounts payable
    fin.ledger.post_simple(
        OWNER, bid, debit_code="5060", credit_code="2000",
        amount_minor=600000, currency="INR", entry_date="2026-11-06",
        description="unpaid vendor bill (obligation)")
    avail = fin.budgets.available_cash(bid, "INR")
    assert avail["cash_balance_minor"] == 500000
    assert avail["obligations_minor"] == 600000
    assert avail["available_cash_minor"] == -100000
    health = fin.analytics.health(bid, "INR")
    assert health["status"] in ("AT_RISK", "CRITICAL")
    # Balance sheet must balance and show the liability
    bs = fin.reports.balance_sheet(bid, "INR")
    assert bs["balanced"] is True
    assert bs["total_liabilities_minor"] >= 600000
    assert fin.ledger.verify_integrity(bid)["ok"] is True


# (e) zero-revenue business in a portfolio invents no cash
async def test_p14_e_zero_revenue_portfolio_no_invented_cash(app_portfolio):
    a = await make_business(app_portfolio, name="P14 Zero A")
    b = await make_business(app_portfolio, name="P14 Zero B")
    # profiles with zero transactions
    from tests.p07_support import business_with_profile as _bwp  # noqa
    # make_business already created businesses without profiles;
    # portfolio finance must exclude / zero them honestly
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    finance = app_portfolio.portfolio.portfolio_finance(OWNER, portfolio["id"])
    assert finance["totals"]["net_collected_minor"] == 0
    assert finance["totals"]["projected_minor"] == 0
    assert finance["combined_available_cash"] is None
    assert "never summed" in finance["combined_cash_note"]


# (f) multi-currency: separation + P-07-only conversion
async def test_p14_f_multi_currency_separation(app_fin):
    usd_bid = await _usd_business(app_fin, name="P14 USD Biz")
    inr_bid, _ = await business_with_profile(app_fin, name="P14 INR Biz")
    await verified_revenue(app_fin, usd_bid, "100.00", currency="USD")
    await verified_revenue(app_fin, inr_bid, "10000.00", currency="INR")
    fin = app_fin.financial
    # Per-business, per-currency metrics never mix
    assert fin.revenue.metrics(usd_bid, "USD")["net_collected_minor"] == 10000
    assert fin.revenue.metrics(usd_bid, "INR")["net_collected_minor"] == 0
    assert fin.revenue.metrics(usd_bid, "USD")["other_currencies"] == []
    assert fin.revenue.metrics(inr_bid, "INR")["net_collected_minor"] == 1000000
    # Consolidated is per-currency only
    cons_inr = fin.consolidated("INR")
    cons_usd = fin.consolidated("USD")
    assert [b["business_id"] for b in cons_inr["businesses"]] == [inr_bid]
    assert cons_inr["totals"]["net_collected_minor"] == 1000000
    assert [b["business_id"] for b in cons_usd["businesses"]] == [usd_bid]
    assert cons_usd["totals"]["net_collected_minor"] == 10000
    # Conversion only via documented rate; missing rate -> pending
    pending = fin.convert_amount(money(app_fin, "100.00", "USD"), "INR")
    assert pending["status"] == "pending" and pending["converted_minor"] is None
    fin.add_exchange_rate(OWNER, {"from_currency": "USD", "to_currency": "INR",
                                  "rate": "83.25", "source": "manual_owner"})
    conv = fin.convert_amount(money(app_fin, "100.00", "USD"), "INR")
    assert conv["status"] == "converted" and conv["converted_minor"] == 832500
    # Unknown currency is refused, never guessed
    with pytest.raises(ValidationError):
        money(app_fin, "10.00", "XXX")


async def test_p14_f2_portfolio_gross_collected_traceable(app_portfolio):
    """P-14 Stage B: DEF-F1 repaired — portfolio per-business + totals
    collected_minor now equal P-07 collected_gross_minor (was xfail in
    Stage A: finance.py read a non-existent metrics key)."""
    a = await business_with_collected(app_portfolio, name="P14 Gross A", amount="4000")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a])
    finance = app_portfolio.portfolio.portfolio_finance(OWNER, portfolio["id"])
    row = next(r for r in finance["businesses"] if r["business_id"] == a)
    assert row["collected_minor"] == 400000
    assert finance["totals"]["collected_minor"] == 400000


# (g) interrupted transaction: no partial, safe retry, no double-count
async def test_p14_g_interrupted_posting_no_partial_safe_retry(app_fin):
    bid, _ = await business_with_profile(app_fin, name="P14 Interrupt")
    fin = app_fin.financial
    accounts = {a["code"]: a for a in fin.ledger.list_accounts(bid)}
    with pytest.raises(Exception):
        fin.ledger.post_entry(
            OWNER, bid,
            lines=[
                {"account_id": accounts["1000"]["id"], "debit_minor": 10000,
                 "credit_minor": 0, "currency": "INR"},
                {"account_id": accounts["3000"]["id"], "debit_minor": 0,
                 "credit_minor": 10000},  # missing currency -> fails mid-op
            ], entry_date="2026-11-05", idempotency_key="p14:doomed")
    _e, total = fin.ledger.list_entries(bid, limit=100)
    assert total == 0
    assert fin.ledger.verify_integrity(bid)["ok"] is True
    # Safe retry with same key and correct lines posts exactly once
    ok_lines = [
        {"account_id": accounts["1000"]["id"], "debit_minor": 10000,
         "credit_minor": 0, "currency": "INR"},
        {"account_id": accounts["3000"]["id"], "debit_minor": 0,
         "credit_minor": 10000, "currency": "INR"},
    ]
    first = fin.ledger.post_entry(OWNER, bid, lines=ok_lines,
                                  entry_date="2026-11-05",
                                  idempotency_key="p14:doomed")
    second = fin.ledger.post_entry(OWNER, bid, lines=ok_lines,
                                   entry_date="2026-11-05",
                                   idempotency_key="p14:doomed")
    assert first["id"] == second["id"]
    assert second.get("duplicate") is True
    _e, total2 = fin.ledger.list_entries(bid, limit=100)
    assert total2 == 1
    assert fin.ledger.account_balance(bid, "1000") == 10000


# Invariant: idempotency — duplicate revenue external_ref + duplicate webhook
async def test_p14_invariant_no_double_count_duplicates(app_fin):
    bid, _ = await business_with_profile(app_fin, name="P14 Dup")
    fin = app_fin.financial
    await verified_revenue(app_fin, bid, "1000.00", external_ref="p14-pay-1")
    with pytest.raises(ValidationError):
        await verified_revenue(app_fin, bid, "1000.00", external_ref="p14-pay-1")
    assert fin.revenue.metrics(bid, "INR")["net_collected_minor"] == 100000
    # Webhook delivered twice
    body = json.dumps({
        "event_id": "p14-evt-1", "type": "payment.settled",
        "payment_ref": "p14-pay-2", "business_id": bid,
        "amount_minor": 50000, "currency": "INR",
        "occurred_date": "2026-11-05"}).encode()
    headers = fake_webhook_headers("fake-provider-test-secret", body)
    r1 = fin.payments.process_webhook("fake-provider", body, headers)
    r2 = fin.payments.process_webhook("fake-provider", body, headers)
    assert r1["status"] == "processed" and r2["status"] == "duplicate"
    # 1000 revenue + 500 webhook = 1500 total, counted once each
    assert fin.revenue.metrics(bid, "INR")["net_collected_minor"] == 150000
    assert fin.ledger.verify_integrity(bid)["ok"] is True


# Invariant: internal allocation leaves P-07 consolidated byte-equal
async def test_p14_invariant_internal_allocation_byte_equal(app_portfolio):
    a = await business_with_collected(app_portfolio, name="P14 Alloc A", amount="4000")
    b = await business_with_collected(app_portfolio, name="P14 Alloc B", amount="4000")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    svc = app_portfolio.portfolio
    service = make_service_with_access(app_portfolio, business_ids=[a, b])
    svc.record_usage(OWNER, service["id"], {"business_id": a, "units": 10})
    before = app_portfolio.financial.consolidated("INR")
    before_json = json.dumps(before, sort_keys=True)
    alloc = svc.create_allocation(OWNER, {
        "service_id": service["id"], "portfolio_id": portfolio["id"],
        "method": "equal", "total_cost_minor": 2000, "business_ids": [a, b]})
    svc.decide_allocation(OWNER, alloc["id"], True)
    after = app_portfolio.financial.consolidated("INR")
    assert json.dumps(after, sort_keys=True) == before_json
    assert after == before
    finance = svc.portfolio_finance(OWNER, portfolio["id"])
    assert finance["totals"]["net_collected_minor"] == 800000
    assert all(r["kind"] == "INTERNAL_ALLOCATION" and r["is_external_payment"] is False
               for r in finance["internal_allocations"])


# Invariant: projected != collected never summed
async def test_p14_invariant_projected_never_summed(app_fin):
    bid, _ = await business_with_profile(app_fin, name="P14 Projected")
    fin = app_fin.financial
    fin.revenue.create_revenue(OWNER, bid, {
        "category": "product_sale", "amount": money(app_fin, "50000.00"),
        "transaction_date": "2026-11-05", "source": "manual",
        "initial_status": "EXPECTED", "creation_method": "forecast"})
    await verified_revenue(app_fin, bid, "10000.00")
    m = fin.revenue.metrics(bid, "INR")
    assert m["projected_minor"] == 5000000
    assert m["net_collected_minor"] == 1000000
    assert m["projected_minor"] + m["net_collected_minor"] != m["net_collected_minor"]
    # Analyst keeps them as separately classified figures
    ans = fin.analyst.answer({"intent": "collected_revenue", "business_id": bid,
                              "currency": "INR"}, businesses=[bid])
    labels = {f["label"]: f for f in ans["figures"]}
    assert labels["verified net collected revenue"]["value_minor"] == 1000000
    assert labels["verified net collected revenue"]["classification"] == "verified_fact"
    assert labels["projected revenue (NOT collected)"]["value_minor"] == 5000000
    assert labels["projected revenue (NOT collected)"]["classification"] == "forecast"
    # Health/profit must not use projected as collected
    profit = fin.analytics.profitability(bid, "INR")
    assert profit["net_revenue_minor"] == 1000000


# Invariant: unauthorized principal cannot record verified revenue / spend / reverse
async def test_p14_invariant_unauthorized_principal(app_fin):
    bid, _ = await business_with_profile(app_fin, name="P14 Authz")
    fin = app_fin.financial
    # Business-access gate
    with pytest.raises(PermissionDeniedError):
        fin.assert_business_access(EXTERNAL, bid)
    with pytest.raises(PermissionDeniedError):
        fin.assert_business_access(AGENT, bid)  # agent-1 not registered to bid
    # Agent-reported settled payment stays unverified / booked, never collected
    rec = fin.revenue.create_revenue(AGENT, bid, {
        "category": "product_sale", "amount": money(app_fin, "5000.00"),
        "transaction_date": "2026-11-05", "source": "manual",
        "initial_status": "PAYMENT_SETTLED", "creation_method": "agent_report"})
    assert rec["verification_status"] == "unverified"
    assert rec["classification"] == "booked"
    assert fin.revenue.metrics(bid, "INR")["net_collected_minor"] == 0
    # External cannot request spend at all
    with pytest.raises(PermissionDeniedError):
        fin.budgets.request_spend(EXTERNAL, bid, {
            "amount": money(app_fin, "100.00"), "category": "operational",
            "kind": "expense", "purpose": "x"})
    # Transfer kind is blocked even for agent (Level 3)
    decision = fin.budgets.request_spend(AGENT, bid, {
        "amount": money(app_fin, "1000.00"), "category": "operational",
        "kind": "transfer", "purpose": "move money"})
    assert decision["status"] == "blocked_level3"
    # Governance settings + reversal are owner-only
    with pytest.raises(PermissionDeniedError):
        fin.update_settings(AGENT, {"x": 1})
    verified = await verified_revenue(app_fin, bid, "1000.00")
    with pytest.raises(PermissionDeniedError):
        fin.ledger.reverse_entry(AGENT, verified["journal_entry_id"],
                                 reason="agent attempt")


# Invariant: reversal-only correction + traceability to journal
async def test_p14_invariant_reversal_only_and_traceability(app_fin):
    bid, _ = await business_with_profile(app_fin, name="P14 Trace")
    fin = app_fin.financial
    rec = await verified_revenue(app_fin, bid, "10000.00")
    await paid_expense(app_fin, bid, "3000.00")
    entry_id = rec["journal_entry_id"]
    original_before = fin.ledger.get_entry(entry_id)
    # Reversal: original unchanged, new reversal entry created
    reversal = fin.ledger.reverse_entry(OWNER, entry_id, reason="P14 audit correction")
    assert reversal["id"] != entry_id
    assert reversal["kind"] == "reversal"
    assert reversal["reversal_of_id"] == entry_id
    original_after = fin.ledger.get_entry(entry_id)
    assert original_after["total_debit_minor"] == original_before["total_debit_minor"]
    assert original_after["lines"] == original_before["lines"]
    assert original_after["is_reversed"] is True
    # Second reversal of same entry is refused (no double-correct)
    from app.core.exceptions import InvalidStateTransitionError
    with pytest.raises(InvalidStateTransitionError):
        fin.ledger.reverse_entry(OWNER, entry_id, reason="again")
    # Traceability: every entry balanced, sum(debits)==sum(credits),
    # P&L from journal == revenue/expense totals (reversal nets income to 0
    # for the reversed sale, expense remains)
    entries, total = fin.ledger.list_entries(bid, limit=100)
    assert total >= 3  # revenue, expense, reversal
    for e in entries:
        assert e["total_debit_minor"] == e["total_credit_minor"]
        assert e["total_debit_minor"] > 0
    assert fin.ledger.verify_integrity(bid)["ok"] is True
    pl = fin.reports.profit_loss(bid, "INR")
    # Income journal: +10000 revenue -10000 reversal = 0; expenses 3000
    assert pl["total_income_minor"] == 0, pl
    assert pl["total_expenses_minor"] == 300000, pl
    assert pl["net_profit_minor"] == -300000
    balances = {r["code"]: r["balance_minor"] for r in fin.ledger.account_balances(bid)}
    # Cash: -3000 expense (Dr expense / Cr cash) -> cash balance -300000
    assert balances["1000"] == -300000
