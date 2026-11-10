"""Financial values and the P-07 interface (§9/§27).

Every figure is a *financial value*: amount or range + currency + source
+ classification (estimate vs verified) + confidence + date + assumptions.
Pricing is data. There is no payment, purchase, wallet or transaction
code in P-06, and **collected revenue / profit can never be recorded**:
the builder below rejects those keys outright, whatever the claimed
classification (security test 11). All arithmetic is deterministic code
in this module — never model-generated (no model exists here anyway).
"""
from __future__ import annotations

import datetime as dt

from ..core.exceptions import ValidationError

CLASSIFICATIONS = {"estimate", "verified"}

# Keys that describe money actually received or earned. P-07 owns the
# truth about these; P-06 must not be able to state them at all.
FORBIDDEN_FINANCIAL_KEYS = {
    "collected_revenue", "revenue_collected", "verified_revenue",
    "revenue", "profit", "net_profit", "gross_profit", "income",
    "sales_total", "amount_collected", "earnings",
}


def _today() -> str:
    return dt.date.today().isoformat()


def financial_value(*, amount: float | None = None,
                    range_low: float | None = None,
                    range_high: float | None = None,
                    currency: str = "USD", source: str = "",
                    classification: str = "estimate",
                    confidence: float = 0.5, date: str | None = None,
                    assumptions: list[str] | None = None) -> dict:
    if classification not in CLASSIFICATIONS:
        raise ValidationError(
            f"financial classification must be one of {sorted(CLASSIFICATIONS)}")
    if amount is None and (range_low is None or range_high is None):
        raise ValidationError("a financial value needs an amount or a range")
    if not source:
        raise ValidationError("a financial value needs a source (§9)")
    return {
        "amount": amount, "range": (
            {"low": range_low, "high": range_high}
            if range_low is not None else None),
        "currency": currency, "source": source,
        "classification": classification,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "date": date or _today(), "assumptions": list(assumptions or []),
    }


def validate_financial_value(value: dict, *, field: str = "value") -> dict:
    """Re-validate a stored/candidate financial value (used for pricing
    supplied at product-spec time and for the P-07 payload)."""
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be a financial-value object")
    key = str(value.get("key", field)).lower()
    if key in FORBIDDEN_FINANCIAL_KEYS:
        raise ValidationError(
            f"{field}: P-06 cannot record {key!r} — collected revenue and "
            "profit are financial truth owned by P-07 (§9/§27)")
    classification = value.get("classification", "estimate")
    if classification not in CLASSIFICATIONS:
        raise ValidationError(f"{field}: unknown classification {classification!r}")
    if value.get("amount") is None and not value.get("range"):
        raise ValidationError(f"{field}: financial value needs amount or range")
    if not value.get("source"):
        raise ValidationError(f"{field}: financial value needs a source")
    return value


def sum_amounts(values: list[dict]) -> float:
    """Deterministic total over financial values (amount, else range
    midpoint). Rounding is explicit and stable."""
    total = 0.0
    for v in values:
        if v.get("amount") is not None:
            total += float(v["amount"])
        elif v.get("range"):
            total += (float(v["range"]["low"]) + float(v["range"]["high"])) / 2.0
    return round(total, 2)


def build_p07_payload(*, business, blueprint_row, product) -> dict:
    """The §9 interface P-07 will consume: estimates in, nothing claimed.

    Raises ValidationError if any stored figure violates the boundary
    (e.g. a hand-edited pricing object claiming verified revenue).
    """
    fin = (blueprint_row.blueprint or {}).get("financial_inputs", {})
    startup = [validate_financial_value(v, field=f"startup_costs[{i}]")
               for i, v in enumerate(fin.get("startup_costs", []))]
    recurring = [validate_financial_value(v, field=f"recurring_costs[{i}]")
                 for i, v in enumerate(fin.get("recurring_costs", []))]
    pricing = None
    if product is not None and product.pricing:
        pricing = validate_financial_value(product.pricing, field="pricing")
    return {
        "business_id": business.id,
        "business_name": business.name,
        "is_fixture": bool(business.is_fixture),
        "currency": fin.get("currency", "USD"),
        "startup_costs": startup,
        "recurring_costs": recurring,
        "startup_total_estimate": sum_amounts(startup),
        "recurring_monthly_estimate": sum_amounts(recurring),
        "pricing": pricing,
        "revenue_recognition": "none — no revenue is recorded by P-06; "
                               "P-07 owns collected-revenue truth",
        "generated_at": _today(),
    }
