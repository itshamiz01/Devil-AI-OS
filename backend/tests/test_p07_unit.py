"""P-07 unit tests (§26.1): money, ledger, formulas, MRR/ARR,
break-even, runway, refunds, FX, recurring detection, forecasts."""
from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.financial.money import (
    CurrencyRegistry, Money, convert, format_money, parse_amount,
)
from tests.conftest import OWNER
from tests.p07_support import (
    app_fin, business_with_profile, money, paid_expense, verified_revenue,
)

REG = CurrencyRegistry()


# ------------------------------------------------------------------- money
def test_currency_precision_by_exponent():
    assert parse_amount("1000", "JPY", REG).minor == 1000
    assert parse_amount("1.234", "KWD", REG).minor == 1234
    assert parse_amount("1,00,000.50", "INR", REG).minor == 10000050
    with pytest.raises(ValidationError):
        parse_amount("1000.5", "JPY", REG)  # JPY has 0 decimal places
    with pytest.raises(ValidationError):
        parse_amount("10.999", "INR", REG)  # INR has 2 decimal places


def test_float_amounts_are_rejected():
    with pytest.raises(ValidationError):
        parse_amount(10.5, "INR", REG)
    with pytest.raises(ValidationError):
        Money(10.5, "INR")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        parse_amount(100, "INR", REG)  # bare ints are unit-ambiguous


def test_decimal_arithmetic_is_exact():
    a = parse_amount("0.10", "INR", REG)
    b = parse_amount("0.20", "INR", REG)
    assert (a + b).minor == 30  # never 0.30000000000000004
    assert (b - a).minor == 10
    with pytest.raises(ValidationError):
        _ = a + parse_amount("1.00", "USD", REG)  # no implicit FX (§14)


def test_indian_digit_grouping_format():
    assert format_money(Money(123456789, "INR"), REG) == "₹12,34,567.89 INR"
    assert format_money(Money(100000, "INR"), REG) == "₹1,000.00 INR"
    assert format_money(Money(-50000, "INR"), REG) == "-₹500.00 INR"


def test_no_float_calls_in_financial_package():
    """§5.1 structural proof: the string 'float(' appears nowhere in
    the financial package source."""
    from pathlib import Path
    package = Path(__file__).resolve().parents[1] / "app" / "financial"
    offenders = [str(p) for p in package.glob("*.py")
                 if "float(" in p.read_text()]
    assert offenders == []


# ------------------------------------------------------------------ ledger
async def test_journal_balancing_enforced(app_fin):
    business_id, _profile = await business_with_profile(app_fin)
    fin = app_fin.financial
    accounts = fin.ledger.list_accounts(business_id)
    by_code = {a["code"]: a for a in accounts}
    assert len(accounts) == 29  # the §5.2 template chart
    with pytest.raises(ValidationError):
        fin.ledger.post_entry(
            OWNER, business_id,
            lines=[
                {"account_id": by_code["1000"]["id"], "debit_minor": 100,
                 "credit_minor": 0, "currency": "INR"},
                {"account_id": by_code["3000"]["id"], "debit_minor": 0,
                 "credit_minor": 99, "currency": "INR"},
            ], entry_date="2026-11-05")
    entry = fin.ledger.post_simple(
        OWNER, business_id, debit_code="1000", credit_code="3000",
        amount_minor=10000, currency="INR", entry_date="2026-11-05",
        idempotency_key="unit:balanced")
    assert entry["total_debit_minor"] == entry["total_credit_minor"] == 10000
    again = fin.ledger.post_simple(
        OWNER, business_id, debit_code="1000", credit_code="3000",
        amount_minor=10000, currency="INR", entry_date="2026-11-05",
        idempotency_key="unit:balanced")
    assert again["id"] == entry["id"] and again["duplicate"] is True
    assert fin.ledger.verify_integrity(business_id)["ok"] is True


async def test_reversal_is_the_only_correction(app_fin):
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    entry = fin.ledger.post_simple(
        OWNER, business_id, debit_code="1000", credit_code="3000",
        amount_minor=5000, currency="INR", entry_date="2026-11-05")
    with pytest.raises(ValidationError):
        fin.ledger.reverse_entry(OWNER, entry["id"], reason="")
    reversal = fin.ledger.reverse_entry(OWNER, entry["id"],
                                        reason="posted to the wrong period")
    assert reversal["kind"] == "reversal"
    assert fin.ledger.account_balance(business_id, "1000") == 0
    with pytest.raises(Exception):
        fin.ledger.reverse_entry(OWNER, entry["id"], reason="twice")


# ---------------------------------------------------------------- formulas
async def test_available_cash_formula_no_double_count(app_fin):
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    fin.record_opening_balance(OWNER, business_id, {
        "amount": money(app_fin, "20000.00"), "entry_date": "2026-11-01",
        "account_ref": "bank:primary", "source": "bank_statement",
        "verification_status": "verified"})
    fin.budgets.create_reserve(OWNER, {
        "reserve_type": "emergency",
        "amount": money(app_fin, "5000.00"), "business_id": business_id})
    available = fin.budgets.available_cash(business_id, "INR")
    assert available["cash_balance_minor"] == 2000000
    assert available["protected_reserves_minor"] == 500000
    assert available["available_cash_minor"] == 1500000
    # An accounts-payable obligation reduces availability exactly once.
    fin.ledger.post_simple(
        OWNER, business_id, debit_code="5060", credit_code="2000",
        amount_minor=200000, currency="INR", entry_date="2026-11-06",
        description="vendor bill unpaid")
    available = fin.budgets.available_cash(business_id, "INR")
    assert available["obligations_minor"] == 200000
    assert available["available_cash_minor"] == 1300000


async def test_budget_utilisation_accounting(app_fin):
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    fin.record_opening_balance(OWNER, business_id, {
        "amount": money(app_fin, "10000.00"), "entry_date": "2026-11-01"})
    budget = fin.budgets.create_budget(OWNER, {
        "scope_type": "business", "business_id": business_id,
        "name": "Ops", "amount": money(app_fin, "2000.00"),
        "period_start": "2026-11-01", "period_end": "2026-11-30",
        "approval_requirement": "level_1"})
    await paid_expense(app_fin, business_id, "500.00", budget_id=budget["id"])
    decision = fin.budgets.request_spend(OWNER, business_id, {
        "amount": money(app_fin, "300.00"), "category": "software_subscription",
        "kind": "expense", "budget_id": budget["id"], "purpose": "tooling"})
    assert decision["status"] == "authorised_level1"
    utilisation = fin.budgets.budget_utilisation(budget["id"])
    assert utilisation["spent_minor"] == 50000
    assert utilisation["committed_minor"] == 30000
    assert utilisation["remaining_minor"] == 120000
    assert utilisation["utilisation_ratio"] == "0.4000"


# ------------------------------------------------------------ subscriptions
async def test_mrr_arr_methodology_no_double_counting(app_fin):
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    fin.revenue.create_subscription(OWNER, business_id, {
        "plan_ref": "pro-monthly", "amount": money(app_fin, "999.00"),
        "interval": "monthly", "started_date": "2026-11-01"})
    fin.revenue.create_subscription(OWNER, business_id, {
        "plan_ref": "pro-annual", "amount": money(app_fin, "12000.00"),
        "interval": "annual", "started_date": "2026-11-01"})
    cancelled = fin.revenue.create_subscription(OWNER, business_id, {
        "plan_ref": "gone", "amount": money(app_fin, "500.00"),
        "interval": "monthly", "started_date": "2026-10-01"})
    fin.revenue.set_subscription_status(OWNER, cancelled["id"], "cancelled")
    metrics = fin.revenue.metrics(business_id, "INR")
    # 999.00 monthly + 12000.00/12 = 1000.00 -> MRR ₹1,999.00
    assert metrics["mrr_minor"] == 199900
    assert metrics["arr_minor"] == 199900 * 12


# ------------------------------------------------------------------ refunds
async def test_refund_reduces_net_collected(app_fin):
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    record = await verified_revenue(app_fin, business_id, "1000.00")
    refund = fin.revenue.create_refund(OWNER, record["id"], {
        "amount": money(app_fin, "200.00"), "refund_date": "2026-11-07",
        "reason": "customer request"})
    assert refund["journal_entry_id"] is not None
    metrics = fin.revenue.metrics(business_id, "INR")
    assert metrics["net_collected_minor"] == 80000
    assert fin.revenue.get_revenue(record["id"])["lifecycle_status"] == \
        "PARTIALLY_REFUNDED"
    assert fin.ledger.verify_integrity(business_id)["ok"] is True
    with pytest.raises(ValidationError):
        fin.revenue.create_refund(OWNER, record["id"], {
            "amount": money(app_fin, "900.00"), "refund_date": "2026-11-08"})


# ----------------------------------------------------------------------- FX
async def test_exchange_rate_conversion_and_pending(app_fin):
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    pending = fin.convert_amount(money(app_fin, "10.00", "USD"), "INR")
    assert pending["status"] == "pending"
    assert pending["converted_minor"] is None
    fin.add_exchange_rate(OWNER, {"from_currency": "USD",
                                  "to_currency": "INR", "rate": "83.25",
                                  "source": "manual_owner"})
    converted = fin.convert_amount(money(app_fin, "10.00", "USD"), "INR")
    assert converted["status"] == "converted"
    assert converted["converted_minor"] == 83250
    assert converted["rate"] == "83.25"
    assert converted["source"] == "manual_owner"


# --------------------------------------------------------------- break-even
async def test_break_even_and_profitability(app_fin):
    business_id, _ = await business_with_profile(app_fin)
    await verified_revenue(app_fin, business_id, "50000.00")
    await paid_expense(app_fin, business_id, "20000.00",
                       category="content_production", directness="direct",
                       cost_behavior="variable")
    await paid_expense(app_fin, business_id, "10000.00",
                       category="software_subscription", directness="indirect",
                       cost_behavior="fixed")
    fin = app_fin.financial
    profit = fin.analytics.profitability(business_id, "INR")
    assert profit["gross_profit_minor"] == 3000000
    assert profit["net_profit_minor"] == 2000000
    assert profit["break_even"]["status"] == "computed"
    # fixed ₹10,000 / CM ratio (50000-20000)/50000 = 0.6 -> ₹16,666.67
    assert profit["break_even"]["break_even_revenue_minor"] == 1666667


# -------------------------------------------------------------------- runway
async def test_runway_from_available_cash_and_burn(app_fin):
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    fin.record_opening_balance(OWNER, business_id, {
        "amount": money(app_fin, "9000.00"), "entry_date": "2026-08-01"})
    for month in ("2026-08-10", "2026-09-10", "2026-10-10"):
        await paid_expense(app_fin, business_id, "3000.00", date=month)
    runway = fin.analytics.runway(business_id, "INR")
    assert runway["status"] == "computed"
    assert runway["average_monthly_burn_minor"] == 300000
    assert runway["runway_months"] == "3.00"


async def test_runway_zero_burn_is_not_infinite(app_fin):
    business_id, _ = await business_with_profile(app_fin)
    fin = app_fin.financial
    runway = fin.analytics.runway(business_id, "INR")
    assert runway["status"] == "insufficient_data"
    assert "runway_months" not in runway


# ------------------------------------------------------- recurring detection
async def test_recurring_expense_detection(app_fin):
    business_id, _ = await business_with_profile(app_fin)
    for date in ("2026-08-05", "2026-09-05", "2026-10-05"):
        await paid_expense(app_fin, business_id, "1200.00",
                           category="hosting", vendor="CloudHost",
                           date=date, recurrence_type="monthly")
    await paid_expense(app_fin, business_id, "1500.00",
                       category="hosting", vendor="CloudHost",
                       date="2026-11-05", recurrence_type="monthly")
    groups = app_fin.financial.expenses.detect_recurring(business_id)
    assert len(groups) == 1
    group = groups[0]
    assert group["occurrences"] == 4
    assert group["cadence_detected"] == "monthly"
    assert group["amount_changed"] is True  # 1200 -> 1500 flagged (§8.3)
    # gaps are 31/30/31 days -> average 30.67 -> step of 31 days
    assert group["next_expected_date"] == "2026-12-06"


# ----------------------------------------------------------------- forecasts
async def test_forecast_methods_and_freezing(app_fin):
    business_id, _ = await business_with_profile(app_fin)
    for date, amount in (("2026-08-15", "10000.00"),
                         ("2026-09-15", "20000.00"),
                         ("2026-10-15", "30000.00")):
        await verified_revenue(app_fin, business_id, amount, date=date)
    fin = app_fin.financial
    average = fin.forecasting.create_forecast(OWNER, business_id, {
        "forecast_type": "revenue", "method": "historical_average",
        "currency": "INR"})
    assert average["values"]["amount_minor"] == 2000000
    assert average["period_label"] == "2026-11"
    trend = fin.forecasting.create_forecast(OWNER, business_id, {
        "forecast_type": "revenue", "method": "trend", "currency": "INR"})
    assert trend["values"]["amount_minor"] == 4000000
    # §11.4: recording the actual never rewrites the frozen forecast.
    await verified_revenue(app_fin, business_id, "25000.00",
                           date="2026-11-15")
    comparison = fin.forecasting.forecast_vs_actual(average["id"])
    assert comparison["actual_minor"] == 2500000
    assert comparison["variance_minor"] == 500000
    assert comparison["values"]["amount_minor"] == 2000000
