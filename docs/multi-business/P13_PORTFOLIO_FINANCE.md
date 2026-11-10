# P-13 Portfolio Finance (§11)

**P-07 remains the only financial authority.** Portfolio finance
is an analytical layer over P-07's records: no second ledger, no
duplicated financial records, no transfer function.

## Rules and where they are enforced

| Rule | Enforcement |
|---|---|
| Figures come from P-07 at request time | `finance.py` calls `FinancialService.business_summary` / `revenue.metrics` per business; nothing financial is written to P-13 tables |
| Collected ≠ projected, always | separate fields (`net_collected_minor`, `collected_minor`, `projected_minor`, `recognized_minor`) in every view, comparison and report |
| Cash is never combined | per-business `available_cash` is listed per row; the portfolio response carries `combined_available_cash: null` plus `combined_cash_note` explaining why |
| Flow totals are honest sums | totals sum only the per-business P-07 flow figures displayed, same currency only, and say so in `totals.basis`; internal transfers are already excluded by P-07 |
| Internal allocations are not payments | rows are permanently `kind=INTERNAL_ALLOCATION`, carry `is_external_payment: false` and a presentation string; they are listed separately and excluded from every total |
| P-13 never transfers money | there is no transfer method on the service (Scenario 10 asserts none exists); real movement is P-07's governed internal-transfer path under owner control |
| No fabricated figures | a business without a P-07 profile appears with `financial_profile: null` and a note, and is excluded from totals rather than estimated |

## Internal cost allocations (§9/§11)

An allocation computation takes an owner-declared internal total
(management-accounting input — the cost of running the shared
service for a period) and splits it by method: `equal`,
`usage_based` (recorded usage units), `fixed` (share_bps summing
to 10000), `priority_weighted` (membership strategic priorities).
It writes one `internal_cost_allocations` row per charged business
(batch-linked, decided as a unit: RECORDED → APPROVED/REJECTED).
**Proof**: Scenario 12 asserts P-07's `consolidated("INR")` output
is byte-equal before and after an approved allocation, and the
live smoke re-checks portfolio totals across an allocation over
HTTP.

## P-08's role

P-08 remains the authority for allocation *proposals* (capital
between businesses) and survival readings. P-13's concentration
and risk layers consume P-07 figures; they do not re-implement
P-08's proposal machinery, and a P-13 recommendation to move
capital is only ever a recommendation — execution, if the owner
chooses it, goes through P-08/P-07's governed paths.
