"""Finance mixin (§11): portfolio financial intelligence as an
ANALYTICAL layer over P-07 — nothing else.

* Every figure comes from ``FinancialService`` at request time; no
  financial record is duplicated into P-13 storage.
* Collected and projected are always separate fields, never blended.
* Cash is reported per business. Separate businesses' cash balances
  are NEVER summed into a "portfolio cash" figure — the response
  carries ``combined_available_cash: null`` and says why.
* Internal cost allocations (P-13 management accounting) are listed
  separately, labelled INTERNAL_ALLOCATION, and never enter the
  P-07-derived totals (§21 Scenario 12).
* P-13 has no transfer function. Moving money between businesses
  is P-07's governed internal-transfer path under owner control.
"""
from __future__ import annotations

from ..core.exceptions import NotFoundError, ValidationError
from ..database.repositories.portfolio import AllocationRepository
from ..permissions.models import Principal
from .shared_services import allocation_dict


class FinanceMixin:
    def business_finance(self, principal: Principal, business_id: str) -> dict:
        """§5/§11 per-business finance, straight from P-07."""
        self._assert_business_read(principal, business_id)
        self._business_or_404(business_id)
        try:
            summary = self._financial.business_summary(business_id)
        except NotFoundError:
            return {"business_id": business_id, "financial_profile": None,
                    "note": "no P-07 financial profile exists for this "
                            "business yet; no figures are fabricated"}
        return {"business_id": business_id, "summary": summary,
                "source": "P-07 FinancialService (live, not copied)"}

    def portfolio_finance(self, principal: Principal, portfolio_id: str,
                          currency: str = "INR") -> dict:
        self._require_portfolio_reader(principal, "portfolio.finance")
        self._portfolio_or_404(portfolio_id)
        member_ids = self._member_business_ids(portfolio_id)
        rows = []
        totals = {"net_collected_minor": 0, "collected_minor": 0,
                  "projected_minor": 0}
        for bid in member_ids:
            business = self._business_or_404(bid)
            try:
                summary = self._financial.business_summary(bid)
            except NotFoundError:
                rows.append({
                    "business_id": bid, "name": business["name"],
                    "financial_profile": None,
                    "note": "no P-07 financial profile; excluded from "
                            "totals rather than estimated"})
                continue
            revenue = summary["revenue"]
            row = {
                "business_id": bid, "name": business["name"],
                "currency": revenue.get("currency", currency),
                "net_collected_minor": int(
                    revenue.get("net_collected_minor") or 0),
                # P-14 Stage B (DEF-F1): P-07's gross collected key is
                # ``collected_gross_minor``; the P-14 audit found this
                # read used a non-existent ``collected_minor`` key, so
                # portfolio gross collected revenue silently read 0.
                "collected_minor": int(
                    revenue.get("collected_gross_minor") or 0),
                "projected_minor": int(revenue.get("projected_minor") or 0),
                "recognized_minor": int(
                    revenue.get("recognized_minor") or 0),
                # Per-business cash: reported, never combined.
                "available_cash": summary["available_cash"],
                "profitability": summary["profitability"],
                "health_score": (summary.get("health") or {}).get("score"),
            }
            if row["currency"] == currency:
                for key in totals:
                    totals[key] += row[key]
            rows.append(row)
        session = self._session_factory()
        try:
            alloc_rows, _t = AllocationRepository(session).list(
                limit=500, portfolio_id=portfolio_id, status="APPROVED")
            allocations = [allocation_dict(r) for r in alloc_rows]
        finally:
            session.close()
        return {
            "portfolio_id": portfolio_id, "currency": currency,
            "businesses": rows,
            "totals": {**totals,
                       "basis": "sums of the per-business P-07 flow "
                                "figures above (same currency only); "
                                "internal transfers excluded by P-07",
                       "collected_vs_projected": "kept as separate "
                                                   "fields, never "
                                                   "blended"},
            "combined_available_cash": None,
            "combined_cash_note": "cash balances of separate "
                                  "businesses are never summed and "
                                  "presented as freely available "
                                  "portfolio cash (§11); see each "
                                  "business's available_cash",
            "internal_allocations": allocations,
            "internal_allocations_note": "internal management "
                                         "allocations are not external "
                                         "payments and are excluded "
                                         "from every total above",
            "financial_authority": "P-07",
        }

    def compare_businesses(self, principal: Principal,
                           business_ids: list[str],
                           currency: str = "INR") -> dict:
        """§18C business comparison from live P-06/P-07/P-08 data."""
        self._require_portfolio_reader(principal, "portfolio.compare")
        if not 2 <= len(business_ids) <= 6:
            raise ValidationError("compare between 2 and 6 businesses")
        rows = []
        for bid in business_ids:
            summary = self._business_summary(bid)
            finance = self.business_finance(principal, bid)
            row = {**summary}
            if finance.get("summary"):
                revenue = finance["summary"]["revenue"]
                row["net_collected_minor"] = int(
                    revenue.get("net_collected_minor") or 0)
                row["projected_minor"] = int(
                    revenue.get("projected_minor") or 0)
                row["available_cash"] = finance["summary"]["available_cash"]
                row["profitability"] = finance["summary"]["profitability"]
            else:
                row["net_collected_minor"] = None
                row["projected_minor"] = None
                row["available_cash"] = None
                row["profitability"] = None
                row["finance_note"] = "no P-07 financial profile"
            rows.append(row)
        return {"businesses": rows, "currency": currency,
                "note": "collected figures are verified P-07 amounts; "
                        "projected figures are shown separately and "
                        "never blended into collected"}
