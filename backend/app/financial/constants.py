"""P-07 vocabularies, default chart of accounts and owner-governed
settings (§5.2, §9, §14). Settings live in ``system_config`` under
``SETTINGS_KEY`` and are writable only by the Owner principal — the
system can never modify its own financial limits (Article 0, §3.3).
"""
from __future__ import annotations

SOURCE = "financial.engine"
SETTINGS_KEY = "financial.settings"
CURRENCIES_KEY = "financial.currencies"

# ---------------------------------------------------------------- §3.1 truth
# The twelve §3.1 categories. Revenue-side buckets stored on records:
REVENUE_CLASSIFICATIONS = {
    "projected", "booked", "invoiced", "collected", "recognized",
}
VERIFICATION_STATUSES = {"unverified", "verified"}

# Sources that may make a payment "collected" (§6.4/§7.3). Anything
# else — browser redirect, frontend message, agent report, LLM
# response, unverified webhook, order creation — can NEVER verify.
VERIFIED_SOURCES = {
    "verified_payment_event",      # signature-verified provider webhook
    "authorized_provider_report",  # provider report via an adapter
    "reconciled_bank_statement",   # bank statement matched in reconciliation
    "verified_marketplace_settlement",
    "owner_attested_with_evidence",  # owner manual entry + evidence + approval
}

# §6.2 lifecycle. FORWARD_PATH is the happy path; side states can be
# entered from the states listed in REVENUE_TRANSITIONS.
REVENUE_LIFECYCLE = [
    "EXPECTED", "ORDER_CREATED", "PAYMENT_PENDING", "PAYMENT_AUTHORIZED",
    "PAYMENT_SETTLED", "VERIFIED", "RECOGNIZED",
]
REVENUE_SIDE_STATES = {
    "CANCELLED", "FAILED", "PARTIALLY_REFUNDED", "REFUNDED", "DISPUTED",
    "CHARGEBACK", "REVERSED",
}
REVENUE_TRANSITIONS: dict[str, set[str]] = {
    "EXPECTED": {"ORDER_CREATED", "PAYMENT_PENDING", "PAYMENT_SETTLED",
                 "CANCELLED", "FAILED"},
    "ORDER_CREATED": {"PAYMENT_PENDING", "PAYMENT_AUTHORIZED", "CANCELLED",
                      "FAILED"},
    "PAYMENT_PENDING": {"PAYMENT_AUTHORIZED", "PAYMENT_SETTLED", "FAILED",
                        "CANCELLED"},
    "PAYMENT_AUTHORIZED": {"PAYMENT_SETTLED", "FAILED", "CANCELLED"},
    "PAYMENT_SETTLED": {"VERIFIED", "DISPUTED", "CHARGEBACK",
                        "PARTIALLY_REFUNDED", "REFUNDED", "REVERSED"},
    "VERIFIED": {"RECOGNIZED", "DISPUTED", "CHARGEBACK",
                 "PARTIALLY_REFUNDED", "REFUNDED", "REVERSED"},
    "RECOGNIZED": {"DISPUTED", "CHARGEBACK", "PARTIALLY_REFUNDED",
                   "REFUNDED", "REVERSED"},
    "PARTIALLY_REFUNDED": {"REFUNDED", "DISPUTED", "CHARGEBACK"},
    "DISPUTED": {"VERIFIED", "RECOGNIZED", "CHARGEBACK", "REVERSED"},
    "CHARGEBACK": {"REVERSED"},
    "REFUNDED": set(),
    "REVERSED": set(),
    "CANCELLED": set(),
    "FAILED": set(),
}

# Lifecycle status -> §3.1 classification bucket.
CLASSIFICATION_BY_STATUS = {
    "EXPECTED": "projected",
    "ORDER_CREATED": "booked",
    "PAYMENT_PENDING": "booked",
    "PAYMENT_AUTHORIZED": "booked",
    "PAYMENT_SETTLED": "collected",
    "VERIFIED": "collected",
    "RECOGNIZED": "recognized",
}

REVENUE_CATEGORIES = {
    "product_sale", "digital_download", "software_subscription",
    "saas_plan", "service_payment", "freelance_project", "consulting",
    "affiliate_commission", "advertising", "marketplace_royalty",
    "licensing", "membership", "other",
}

# ---------------------------------------------------------------- §8 expenses
EXPENSE_CATEGORIES = {
    "hosting", "domain", "software_subscription", "ai_inference",
    "api_cost", "advertising", "marketing", "payment_processing",
    "contractor", "content_production", "marketplace_fee",
    "transaction_fee", "maintenance", "operational", "tax", "other",
}
EXPENSE_KINDS = {
    "operating_expense", "direct_cost", "capital_expense",
    "asset_purchase", "deposit", "loan", "transfer", "internal_transfer",
    "refund_loss", "tax_payment",
}
# Kinds that count as expenses in profitability (P&L expense lines).
P_AND_L_EXPENSE_KINDS = {"operating_expense", "direct_cost",
                         "capital_expense", "refund_loss", "tax_payment"}

# ---------------------------------------------------------------- §5.2 chart
# (code, name, account_type, subtype)
DEFAULT_CHART = [
    ("1000", "Cash", "asset", "cash"),
    ("1010", "Bank Account", "asset", "bank"),
    ("1020", "Payment Processor Balance", "asset", "processor"),
    ("1100", "Accounts Receivable", "asset", "receivable"),
    ("1200", "Other Current Assets", "asset", "other_current"),
    ("2000", "Accounts Payable", "liability", "payable"),
    ("2010", "Refund Liability", "liability", "refund_liability"),
    ("2020", "Customer Credits", "liability", "customer_credits"),
    ("2100", "Taxes Payable", "liability", "taxes_payable"),
    ("2200", "Subscription Obligations", "liability", "subscription_obligations"),
    ("2300", "Other Outstanding Liabilities", "liability", "other_liabilities"),
    ("3000", "Owner Contributions", "equity", "owner_contributions"),
    ("3100", "Retained Earnings", "equity", "retained_earnings"),
    ("3200", "Owner Withdrawals", "equity", "owner_withdrawals"),
    ("4000", "Product Sales", "income", "product_sales"),
    ("4010", "Service Revenue", "income", "service_revenue"),
    ("4020", "Subscription Revenue", "income", "subscription_revenue"),
    ("4030", "Affiliate Income", "income", "affiliate_income"),
    ("4040", "Advertising Income", "income", "advertising_income"),
    ("4090", "Other Operating Income", "income", "other_income"),
    ("5000", "Software Expenses", "expense", "software"),
    ("5010", "Hosting Expenses", "expense", "hosting"),
    ("5020", "Marketing Expenses", "expense", "marketing"),
    ("5030", "Advertising Expenses", "expense", "advertising"),
    ("5040", "Payment Processing Fees", "expense", "payment_processing"),
    ("5050", "Contractor Costs", "expense", "contractor"),
    ("5060", "Operational Expenses", "expense", "operational"),
    ("5070", "Refund Losses", "expense", "refund_losses"),
    ("5090", "Other Business Expenses", "expense", "other_expenses"),
]

REVENUE_CATEGORY_ACCOUNT = {
    "product_sale": "4000", "digital_download": "4000",
    "software_subscription": "4020", "saas_plan": "4020",
    "membership": "4020", "service_payment": "4010",
    "freelance_project": "4010", "consulting": "4010",
    "affiliate_commission": "4030", "advertising": "4040",
    "marketplace_royalty": "4090", "licensing": "4090", "other": "4090",
}
EXPENSE_CATEGORY_ACCOUNT = {
    "software_subscription": "5000", "hosting": "5010", "domain": "5010",
    "marketing": "5020", "advertising": "5030",
    "payment_processing": "5040", "transaction_fee": "5040",
    "marketplace_fee": "5040", "contractor": "5050",
    "content_production": "5060", "maintenance": "5060",
    "operational": "5060", "ai_inference": "5060", "api_cost": "5060",
    "tax": "5060", "other": "5090",
}
ACCOUNT_CASH = "1000"
ACCOUNT_BANK = "1010"
ACCOUNT_PROCESSOR = "1020"
ACCOUNT_RECEIVABLE = "1100"
ACCOUNT_PAYABLE = "2000"
ACCOUNT_REFUND_LIABILITY = "2010"
ACCOUNT_OWNER_CONTRIBUTIONS = "3000"

# ---------------------------------------------------------------- §9 budgets
BUDGET_SCOPES = {"portfolio", "business", "project", "experiment",
                 "agent_task", "campaign", "integration"}
RESERVE_TYPES = {"emergency", "operational", "tax", "refund",
                 "business_continuity", "owner_designated"}
# §9.5: kinds that are Level 3 — structurally blocked in P-07 (§23.2).
LEVEL3_KINDS = {"transfer", "wallet_transfer", "investment",
                "reserve_change", "policy_change", "high_value_transfer"}
LEVEL2_KINDS = {"new_category", "new_recurring_commitment",
                "budget_increase", "refund", "payout"}

# ---------------------------------------------------------------- §14 fx
# ISO 4217 minor-unit exponents (seed defaults; owner-configurable).
DEFAULT_CURRENCIES = {
    "INR": 2, "USD": 2, "EUR": 2, "GBP": 2, "AED": 2, "SGD": 2,
    "AUD": 2, "CAD": 2, "JPY": 0, "KRW": 0, "KWD": 3, "BHD": 3,
}
FX_RATE_SOURCES = {"manual_owner", "ecb_reference", "provider_report"}

# ---------------------------------------------------------------- §12 health
HEALTH_STATUSES = {"HEALTHY", "STABLE", "WATCH", "AT_RISK", "CRITICAL",
                   "INSUFFICIENT_DATA"}

# ---------------------------------------------------------------- settings
DEFAULT_SETTINGS = {
    "default_currency": "INR",
    # Manual revenue entries stay unverified unless the owner attests
    # with evidence through a hash-bound approval (§6.4 policy).
    "manual_revenue_policy": "owner_attestation_required_for_verified",
    # §9.2 spending limits, per currency, as decimal strings. A
    # currency with no configured limit fails safe to Level 2.
    "spending_limits": {
        "INR": {"max_single_transaction": "100000.00",
                "max_daily": "200000.00", "max_weekly": "500000.00",
                "max_monthly": "1000000.00",
                "max_experiment_loss": "5000.00",
                "max_campaign_expenditure": "50000.00",
                "max_recurring_commitment_monthly": "20000.00"},
        "USD": {"max_single_transaction": "1000.00",
                "max_daily": "2000.00", "max_weekly": "5000.00",
                "max_monthly": "10000.00",
                "max_experiment_loss": "50.00",
                "max_campaign_expenditure": "500.00",
                "max_recurring_commitment_monthly": "200.00"},
    },
    "webhook_replay_window_seconds": 300,
    "health_thresholds": {
        "watch_runway_months": 6, "at_risk_runway_months": 3,
        "critical_runway_months": 1, "high_refund_rate": "0.10",
        "high_chargeback_rate": "0.02",
    },
    "risk_thresholds": {
        "expense_spike_ratio": "1.5", "unusual_amount_multiplier": "5",
        "revenue_concentration": "0.80",
    },
    # §19.1: owner-configurable electricity estimate for local
    # inference cost *estimates*. Null = not estimated (cost stays 0
    # monetary / resource-only). Never invented by the system.
    "electricity_cost_per_hour": None,
    "professional_review_notice": (
        "Financial reports are management information, not audited "
        "financial statements. Tax figures are tracking estimates; "
        "obtain qualified professional accounting/tax review."),
}
