"""Deterministic commercial feasibility calculations (P-03 §13).

Pure functions over explicit inputs. Every figure the caller supplies is
classified (verified / quoted / historical / estimate / unknown); a line
whose amount is unknown contributes nothing to totals and is reported as
an unknown, never silently treated as a verified zero-cost. The engine
never invents a selling price or sales volumes: scenarios are computed
only from caller-stated assumptions, which are stored with the analysis.

Formulas (§13.3/§13.5), monthly basis:
  revenue            = sales x price
  variable costs     = sales x (unit variable cost + price x (platform% + payment%))
  gross profit       = revenue - direct delivery costs (unit variable x sales)
  contribution       = revenue - all variable costs (incl. fees)
  operating profit   = contribution - recurring monthly costs
  net cash flow      = operating profit (P-03 simplification: no receivables
                       timing; stated in the analysis assumptions)
  contribution/sale  = price - unit variable - price x fee%
  break-even sales   = ceil(recurring / contribution per sale), if positive
"""
from __future__ import annotations

import math

from .constants import COST_CLASSIFICATIONS

CONTINGENCY_RATE = 0.20  # stated assumption: 20% of startup cost (§13.6)


def normalise_lines(lines: list[dict]) -> list[dict]:
    out = []
    for line in lines or []:
        classification = str(line.get("classification", "unknown")).lower()
        if classification not in COST_CLASSIFICATIONS:
            classification = "unknown"
        amount = line.get("amount")
        if classification == "unknown":
            amount = None
        elif amount is not None:
            amount = float(amount)
        out.append({
            "name": str(line.get("name", "unnamed cost")),
            "amount": amount,
            "classification": classification,
            "source_note": str(line.get("source_note", "")),
        })
    return out


def total_known(lines: list[dict]) -> tuple[float, bool]:
    """(sum of known amounts, whether any line is unknown)."""
    total = 0.0
    unknown = False
    for line in lines:
        if line["amount"] is None:
            unknown = True
        else:
            total += line["amount"]
    return total, unknown


def compute_commercial(*, startup_costs: list[dict], recurring_costs_monthly: list[dict],
                       variable_costs_per_sale: list[dict], price: dict | None,
                       platform_fee_pct: float = 0.0, payment_fee_pct: float = 0.0,
                       scenario_sales: dict | None = None,
                       budget_amount: float | None = None) -> dict:
    """Returns the full commercial-analysis payload (scenarios, break-even,
    budget compatibility). All monetary values are in the caller's currency;
    no currency conversion is performed or implied."""
    startup = normalise_lines(startup_costs)
    recurring = normalise_lines(recurring_costs_monthly)
    variable = normalise_lines(variable_costs_per_sale)
    startup_total, startup_unknown = total_known(startup)
    recurring_total, recurring_unknown = total_known(recurring)
    unit_variable, variable_unknown = total_known(variable)

    price_amount = None
    price_block = {"amount": None, "classification": "unknown", "basis": ""}
    if price:
        classification = str(price.get("classification", "unknown")).lower()
        if classification not in COST_CLASSIFICATIONS:
            classification = "unknown"
        amount = price.get("amount")
        price_amount = float(amount) if amount is not None and classification != "unknown" else None
        price_block = {"amount": price_amount, "classification": classification,
                       "basis": str(price.get("basis", ""))}

    fee_rate = (float(platform_fee_pct) + float(payment_fee_pct)) / 100.0

    scenarios: dict = {}
    scenario_notes: list[str] = []
    if price_amount is None:
        scenario_notes.append(
            "Scenarios cannot be computed: no selling price with a known amount was "
            "provided. The engine does not invent prices (§13.1, §19).")
    elif not scenario_sales:
        scenario_notes.append(
            "Scenarios cannot be computed: monthly sales-volume assumptions were not "
            "provided. The engine does not invent demand (§3, §19).")
    else:
        for name in ("conservative", "base", "optimistic"):
            spec = scenario_sales.get(name)
            if not spec:
                continue
            sales = float(spec.get("sales_per_month", 0))
            assumptions = list(spec.get("assumptions", []))
            revenue = sales * price_amount
            direct_delivery = sales * unit_variable
            fees = revenue * fee_rate
            gross_profit = revenue - direct_delivery
            contribution = revenue - direct_delivery - fees
            operating_profit = contribution - recurring_total
            scenarios[name] = {
                "assumptions": assumptions,
                "sales_per_month": sales,
                "revenue": round(revenue, 2),
                "direct_delivery_costs": round(direct_delivery, 2),
                "fees": round(fees, 2),
                "gross_profit": round(gross_profit, 2),
                "contribution_margin": round(contribution, 2),
                "contribution_margin_pct": round(100.0 * contribution / revenue, 2) if revenue else None,
                "operating_profit": round(operating_profit, 2),
                "net_cash_flow": round(operating_profit, 2),
            }

    break_even: dict = {"feasible": None,
                        "note": "Break-even requires a known price and recurring costs."}
    if price_amount is not None:
        contribution_per_sale = price_amount - unit_variable - price_amount * fee_rate
        break_even = {
            "contribution_per_sale": round(contribution_per_sale, 2),
            "fixed_costs_monthly": round(recurring_total, 2),
            "variable_unknown": variable_unknown,
            "recurring_unknown": recurring_unknown,
        }
        if contribution_per_sale <= 0:
            break_even.update({
                "feasible": False, "break_even_sales_per_month": None,
                "break_even_revenue": None,
                "note": ("Contribution per sale is not positive at the stated price and "
                         "costs: the model cannot break even at any volume."),
            })
        else:
            be_sales = math.ceil(recurring_total / contribution_per_sale) if recurring_total > 0 else 0
            break_even.update({
                "feasible": True, "break_even_sales_per_month": be_sales,
                "break_even_revenue": round(be_sales * price_amount, 2),
                "note": "Break-even = ceil(recurring monthly costs / contribution per sale).",
            })

    minimum_viable = startup_total
    first_month_total = startup_total + recurring_total
    contingency = round(CONTINGENCY_RATE * startup_total, 2)
    if budget_amount is None:
        budget_block = {
            "budget_amount": None, "minimum_viable_cost": round(minimum_viable, 2),
            "first_month_total": round(first_month_total, 2),
            "recurring_monthly": round(recurring_total, 2),
            "contingency_required": contingency,
            "maximum_affordable_experiment_cost": None,
            "compatible": None,
            "note": ("No owner budget was specified for this analysis: budget "
                     "compatibility cannot be established (it is not assumed)."),
        }
    else:
        compatible = first_month_total <= budget_amount
        budget_block = {
            "budget_amount": budget_amount,
            "minimum_viable_cost": round(minimum_viable, 2),
            "first_month_total": round(first_month_total, 2),
            "recurring_monthly": round(recurring_total, 2),
            "contingency_required": contingency,
            "maximum_affordable_experiment_cost": round(budget_amount - contingency, 2),
            "compatible": compatible,
            "note": ("Compatible means startup + first month recurring fits the owner's "
                     "stated budget. The budget figure is the owner's; the engine never "
                     "raises it (§13.6)."),
        }

    return {
        "price_assumption": price_block,
        "startup_costs": startup, "recurring_costs_monthly": recurring,
        "variable_costs_per_sale": variable,
        "totals": {
            "startup_total_known": round(startup_total, 2), "startup_has_unknown": startup_unknown,
            "recurring_total_known": round(recurring_total, 2), "recurring_has_unknown": recurring_unknown,
            "unit_variable_known": round(unit_variable, 2), "variable_has_unknown": variable_unknown,
            "platform_fee_pct": float(platform_fee_pct), "payment_fee_pct": float(payment_fee_pct),
        },
        "scenarios": scenarios, "scenario_notes": scenario_notes,
        "break_even": break_even, "budget": budget_block,
    }
