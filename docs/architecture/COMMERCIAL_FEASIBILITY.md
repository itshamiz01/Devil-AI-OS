# Commercial Feasibility (P-03)

Covers `backend/app/opportunities/commercial.py` — §13.

## 1. What this module computes

Given a cost structure, a price per unit, an expected monthly volume and the owner's budget, it produces: three volume scenarios, a break-even and payback figure, and a verdict on whether the whole thing fits the stated capital. Everything is exact decimal arithmetic. Nothing is sampled, forecast with a model, or rounded to look tidy.

## 2. Inputs

`CostStructure` has a single field, `items`, holding `CostItem` records. Four `CostItem` fields are required:

| Field | Values |
|---|---|
| `name` | Free text |
| `amount` | `Decimal` |
| `provenance` | One of 5 `Provenance` values |
| `kind` | `Literal['startup', 'recurring', 'variable_per_unit']` |

Optional: `billing_period` (`Literal['once', 'monthly', 'annual', 'per_unit']`), `currency`, `vendor`, `evidence_id`, `assumption`.

`provenance` being **required on every cost** is the load-bearing rule. A cost with no stated origin cannot be distinguished from a guess, and the three `kind` values are aggregated separately precisely so that a guess in one bucket does not contaminate the others:

* `startup_total()` — one-time costs
* `recurring_monthly_total()` — normalised to a month, so an `annual` item is divided by twelve
* `variable_per_unit_total()` — per unit sold

`CommercialInputs` is a dataclass (not a Pydantic model): `costs`, `price_per_unit`, `price_provenance`, `base_units_monthly`, `units_provenance`, `budget`, `period_months`.

Both `price_provenance` and `units_provenance` are required alongside the numbers they qualify. **A price and a volume may not be supplied without saying where they came from.**

## 3. The projection chain

`project(costs, *, price_per_unit, units_sold, period_months=1, include_startup_in_period=True)` → `FinancialProjection`. Four fields are required: `units_sold`, `price_per_unit`, `variable_cost_per_unit`, `recurring_fixed_cost`.

```
revenue                 = price_per_unit * units_sold
variable_cost           = variable_cost_per_unit * units_sold
gross_profit            = revenue - variable_cost
gross_margin            = gross_profit / revenue
contribution_per_unit   = price_per_unit - variable_cost_per_unit
contribution_margin     = contribution_per_unit / price_per_unit
operating_profit        = gross_profit - recurring_fixed_cost
net_cash_flow           = operating_profit - one_time_cost_in_period
```

`one_time_cost_in_period` is the startup total when `include_startup_in_period` is true and the period is the first one, else zero. Keeping it as its own field rather than folding it into fixed costs is what makes `operating_profit` and `net_cash_flow` mean different things: the first is the run rate, the second is the cash actually left at the end of the period.

`unpriced_cost_items` names costs that were supplied without an amount. It is **derived in a validator**, not accepted from the caller — a caller-supplied list duplicating derivable information is a lie waiting to happen, so the field is computed with `object.__setattr__` and any input is ignored.

## 4. The three scenarios

`SCENARIO_VOLUME_FACTORS`: `conservative` 0.5, `base` 1.0, `optimistic` 1.75.

Each scenario re-runs the full projection at `(base_units_monthly * factor).quantize(Decimal("0.01"))`. Only volume scales — **startup and recurring costs do not**, which is the whole reason the conservative case is informative: it shows whether the fixed cost base survives a halving of demand.

`ScenarioProjection` wraps a projection with `name`, `volume_factor`, `rationale` and `projection`. The numbers live on `.projection`; the wrapper exists so each scenario can carry its own justification. The optimistic rationale states in terms that it is *"shown to bound the upside, not to be planned against"*.

## 5. Break-even and payback

`break_even(costs, *, price_per_unit)` constructs a `BreakEvenResult` from three inputs — `contribution_per_unit`, `recurring_fixed_monthly`, `startup_cost` — and a `mode="after"` validator derives the rest as **whole, ceiling-rounded integers**:

```
contribution_per_unit <= 0  ->  achievable = False, and a reason saying no volume
                                can recover fixed costs at this price. Nothing else
                                is computed; infinity is not reported as a number.

monthly_break_even_units    = ceil(recurring_fixed_monthly / contribution_per_unit)
units_to_recover_startup    = ceil((startup_cost + recurring_fixed_monthly)
                                    / contribution_per_unit)
months_to_recover_startup   = ceil(units_to_recover_startup / monthly_break_even_units)
```

Two details are easy to get wrong and are therefore pinned by tests:

1. **Monthly break-even covers the recurring fixed cost only.** Including startup there would overstate the monthly threshold by the whole one-time cost.
2. **Startup payback includes the recurring cost of the month it lands in.** Recovering the startup cost in a month where you also have to cover that month's fixed costs means the denominator has to clear both. With a 100 startup, 20 recurring and 18 contribution: monthly break-even is `ceil(20/18) = 2` units, payback is `ceil(120/18) = 7` units, over `ceil(7/2) = 4` months.

`achievable` defaults to `False` and is set `True` only by the validator. A break-even that defaulted to achievable would report success for any input it failed to process.

`MINIMUM_CONTRIBUTION_MARGIN = Decimal("0.20")` is the floor below which a price is flagged as too thin to be viable. **This constant is a design choice with no external authority** and is listed for owner ratification.

## 6. Budget compatibility

`budget_compatibility(costs, budget, *, base_units_monthly)` → `BudgetCompatibility`:

| Field | Meaning |
|---|---|
| `available_capital` | Copied read-only from the owner's `BudgetConstraint` |
| `required_startup` | The one-time total |
| `required_first_period_cash` | startup + recurring + variable at base volume |
| `compatible` | Whether the capital covers the first period |
| `shortfall` | How much is missing, `>= 0` |
| `utilisation_pct` | Share of capital consumed |
| `verdict` | `compatible`, `tight`, `incompatible`, `cannot_determine` |
| `budget_was_modified` | **A literal `False`** |
| `unpriced_cost_items` | Costs supplied without an amount |

The critical invariant, stated in the model's own docstring: **this model reports a shortfall, it never repairs one.** `available_capital` is copied in so the comparison stays auditable after the fact, and no code path may raise it.

The consequence is tested end to end: with capital 10 against an 800 startup cost the verdict is `incompatible`, `shortfall == 790.00`, `budget_was_modified is False`, and the owner's `BudgetConstraint` object is unchanged afterwards. The opportunity is classified `INCOMPATIBLE_WITH_CONSTRAINTS` — the constraint wins, not the opportunity.

`cannot_determine` is the default verdict, so an assessment that could not run says so rather than defaulting to `compatible`.

## 7. `CommercialAssessment`

The aggregate: `affordable`, `viable`, `verdict`, `reasons`, `assumptions`, `break_even`, `budget_compatibility`, `budget_was_modified`, `costs`, `scenarios`, `unpriced_cost_items`.

`affordable` and `viable` are separate booleans. An opportunity can be affordable and still not viable (a positive budget fit with a negative contribution margin), and the reasons list names which condition failed.

`assumptions` is the one place in the P-03 schema set where a JSON column holds Pydantic models. That combination does not serialise on its own — committing one raises `TypeError`, surfaced as a `StatementError`. Every read and write path therefore goes through a shared `_assumptions()` / `_to_assumptions()` pair rather than relying on each call site to remember.

## 8. Decimal storage

Every monetary and decimal value in this module is stored in SQLite as `String(32)` text. SQLite has no decimal type, and a float round trip would silently change a price or a margin by an amount no test comparing to a rounded literal would catch. Recorded in [ADR-0022](../decisions/ADR-0022-MONETARY-VALUES-AS-DECIMAL-TEXT.md).
