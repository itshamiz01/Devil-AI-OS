"""§19 Growth and survival intelligence — deterministic analyst.

There is NO LLM in staging. Exactly as P-07 resolved its §17, this
module delivers a deterministic structured query interface over
P-02: each intent is answered from P-07 readings (via monitoring),
P-08 health snapshots, decisions and portfolio records, and every
figure carries a provenance classification — verified_fact /
calculated_metric / forecast / assumption / missing (§19.2). The
analyst invents nothing: when data is insufficient the answer says
so. The natural-language layer is NOT IMPLEMENTED (implementation
report §20).
"""
from __future__ import annotations

from ..core.exceptions import ValidationError
from . import constants as C


def _figure(label, value, classification, source):
    return {"label": label, "value": value,
            "classification": classification, "source": source}


class SurvivalAnalyst:
    def __init__(self, monitoring, health, portfolio, business):
        self._monitoring = monitoring
        self._health = health
        self._portfolio = portfolio
        self._business = business

    def answer(self, query: dict) -> dict:
        intent = query.get("intent")
        if intent not in C.ANALYST_INTENTS:
            raise ValidationError(
                f"unknown analyst intent {intent!r}; supported: "
                f"{C.ANALYST_INTENTS}")
        handler = getattr(self, f"_{intent}")
        return {"intent": intent, **handler(query)}

    # ------------------------------------------------------------ helpers
    def _snapshots(self) -> list[tuple[dict, dict | None]]:
        businesses, _ = self._business.list_businesses(limit=500)
        return [(b, self._health.latest_snapshot(b["id"]))
                for b in businesses]

    def _one_business(self, query) -> tuple[dict, dict]:
        business_id = query.get("business_id")
        if not business_id:
            raise ValidationError("this intent requires business_id")
        business = self._business.get_business(business_id)
        reading = self._monitoring.collect(business_id)
        return business, reading

    # -------------------------------------------------------------- intents
    def _most_stable_business(self, query) -> dict:
        ranked = [(b, s) for b, s in self._snapshots() if s]
        ranked.sort(key=lambda pair: pair[1]["score_bps"] or -1,
                    reverse=True)
        if not ranked:
            return {"answer": "no health snapshots exist yet",
                    "figures": [_figure("health_snapshots", 0,
                                        "missing", "p08.health")]}
        best_b, best_s = ranked[0]
        return {
            "answer": f"{best_b['name']} has the strongest recorded "
                      f"health ({best_s['classification']})",
            "figures": [
                _figure("classification", best_s["classification"],
                        "calculated_metric", "p08.health_snapshot"),
                _figure("score_bps", best_s["score_bps"],
                        "calculated_metric", "p08.health_snapshot"),
                _figure("verified_collected_revenue_minor",
                        (best_s["indicators"] or {}).get(
                            "verified_collected_revenue_minor"),
                        "verified_fact", "p07.p08_indicators"),
            ],
            "business_id": best_b["id"],
        }

    def _business_needing_attention(self, query) -> dict:
        needing = [(b, s) for b, s in self._snapshots()
                   if s and s["classification"] in
                   ("AT_RISK", "CRITICAL", "WATCH")]
        needing.sort(key=lambda pair: C.SEVERITY.get(
            pair[1]["classification"], 0), reverse=True)
        return {
            "answer": ("businesses needing attention: "
                       + ", ".join(b["name"] for b, _ in needing)
                       if needing else
                       "no business is currently classified WATCH or "
                       "worse"),
            "businesses": [{"business_id": b["id"], "name": b["name"],
                            "classification": s["classification"],
                            "explanation": s["explanation"]}
                           for b, s in needing],
            "figures": [_figure("count", len(needing),
                                "calculated_metric", "p08.health")],
        }

    def _resource_recommendation(self, query) -> dict:
        business, _reading = self._one_business(query)
        snapshot = self._health.latest_snapshot(business["id"])
        if snapshot is None or snapshot["classification"] in (
                "INSUFFICIENT_DATA", "AT_RISK", "CRITICAL"):
            return {
                "answer": "additional resources are not recommended: "
                          "health is "
                          f"{(snapshot or {}).get('classification', 'unevaluated')} "
                          "— growth must be earned (§3.2)",
                "figures": [_figure("classification",
                                    (snapshot or {}).get(
                                        "classification"),
                                    "calculated_metric",
                                    "p08.health_snapshot")],
            }
        return {
            "answer": "resources may be considered through a "
                      "resource proposal (§17): workload is measured "
                      "first and creation runs through P-04",
            "figures": [_figure("classification",
                                snapshot["classification"],
                                "calculated_metric",
                                "p08.health_snapshot")],
        }

    def _cost_reduction_candidates(self, query) -> dict:
        business, reading = self._one_business(query)
        summary = reading.get("summary") or {}
        totals = summary.get("expenses") or {}
        return {
            "answer": "expense categories by size (P-07 readings); "
                      "any reduction is a proposal with risks and "
                      "reversibility, never an automatic cancellation "
                      "(§12.3)",
            "figures": [
                _figure("expenses_by_category_minor",
                        totals.get("by_category_minor"),
                        "verified_fact", "p07.expenses.totals"),
                _figure("fixed_minor", totals.get("fixed_minor"),
                        "verified_fact", "p07.expenses.totals"),
                _figure("recurring_candidates",
                        "see P-07 recurring-expense detection",
                        "calculated_metric", "p07.expenses"),
            ],
        }

    def _scaling_readiness(self, query) -> dict:
        business, _reading = self._one_business(query)
        snapshot = self._health.latest_snapshot(business["id"])
        return {
            "answer": "scaling readiness is decided by the §10 "
                      "assessment; the latest health classification "
                      f"is {(snapshot or {}).get('classification', 'unevaluated')}",
            "figures": [
                _figure("classification",
                        (snapshot or {}).get("classification"),
                        "calculated_metric", "p08.health_snapshot"),
                _figure("hard_gates",
                        (snapshot or {}).get("hard_gates"),
                        "calculated_metric", "p08.health_snapshot"),
            ],
        }

    def _experiment_advice(self, query) -> dict:
        business, reading = self._one_business(query)
        indicators = reading.get("indicators") or {}
        return {
            "answer": "experiments run only pre-declared, with an "
                      "approved budget and a hard stop-loss (§9); "
                      "the maximum defensible budget is bounded by "
                      "P-07 available capital and the business's own "
                      "budget governance",
            "figures": [
                _figure("available_capital_minor",
                        indicators.get("available_capital_minor"),
                        "verified_fact", "p07.p08_indicators"),
            ],
        }

    def _best_channel(self, query) -> dict:
        business, reading = self._one_business(query)
        metrics = (reading.get("summary") or {}).get("revenue") or {}
        by_channel = metrics.get("by_channel_minor") or {}
        if not by_channel:
            return {"answer": "no verified collected revenue by "
                              "channel exists (INSUFFICIENT_DATA)",
                    "figures": [_figure("by_channel_minor", None,
                                        "missing", "p07.revenue.metrics")]}
        best = max(by_channel.items(), key=lambda kv: kv[1])
        return {
            "answer": f"{best[0]} carries the most verified "
                      "collected revenue for this business",
            "figures": [_figure("by_channel_minor", by_channel,
                                "verified_fact", "p07.revenue.metrics")],
        }

    def _model_sustainability(self, query) -> dict:
        business, reading = self._one_business(query)
        indicators = reading.get("indicators") or {}
        profit = indicators.get("profitability") or {}
        if profit.get("status") != "computed":
            return {"answer": "sustainability cannot be established "
                              "from verified figures yet "
                              "(INSUFFICIENT_DATA)",
                    "figures": [_figure("profitability_status",
                                        profit.get("status"), "missing",
                                        "p07.p08_indicators")]}
        return {
            "answer": "the model is "
                      + ("loss-making on verified figures"
                         if profit.get("is_loss") else
                         "not loss-making on verified figures")
                      + f"; runway status {indicators.get('runway_status')}",
            "figures": [
                _figure("net_profit_minor", profit.get("net_profit_minor"),
                        "verified_fact", "p07.p08_indicators"),
                _figure("runway_months",
                        indicators.get("runway_months"),
                        "calculated_metric", "p07.p08_indicators"),
            ],
        }

    def _market_expansion_advice(self, query) -> dict:
        return {
            "answer": "market expansion is a Level 3 decision "
                      "requiring P-03 market research and a scaling "
                      "assessment; P-08 does not duplicate the "
                      "opportunity discovery engine (§11.2)",
            "figures": [_figure("research_route", "p03.opportunities",
                                "assumption", "p08.analyst")],
        }

    def _max_safe_experiment_budget(self, query) -> dict:
        business, reading = self._one_business(query)
        indicators = reading.get("indicators") or {}
        return {
            "answer": "the safe ceiling for an experiment budget is "
                      "bounded by P-07 available capital and the "
                      "owner-approved budget for the business; the "
                      "experiment itself must also declare a maximum "
                      "acceptable loss (§9.4)",
            "figures": [
                _figure("available_capital_minor",
                        indicators.get("available_capital_minor"),
                        "verified_fact", "p07.p08_indicators"),
                _figure("budget_utilisation_max_ratio",
                        indicators.get("budget_utilisation_max_ratio"),
                        "calculated_metric", "p07.p08_indicators"),
            ],
        }

    def _pause_candidates(self, query) -> dict:
        candidates = [(b, s) for b, s in self._snapshots()
                      if s and s["classification"] in
                      ("AT_RISK", "CRITICAL")]
        return {
            "answer": "pause candidates are businesses classified "
                      "AT_RISK or CRITICAL; pausing preserves "
                      "records and obligations (§14.1)",
            "businesses": [{"business_id": b["id"], "name": b["name"],
                            "classification": s["classification"]}
                           for b, s in candidates],
            "figures": [_figure("count", len(candidates),
                                "calculated_metric", "p08.health")],
        }

    def _biggest_portfolio_risk(self, query) -> dict:
        concentration = self._portfolio.concentration()
        return {
            "answer": "the largest recorded portfolio risks are "
                      "concentration findings from P-07 channel "
                      "shares and P-06 channel records",
            "figures": [_figure("concentration_risks",
                                concentration["risks"],
                                "calculated_metric",
                                "p08.portfolio.concentration")],
        }

    def _resource_consumers(self, query) -> dict:
        rows = []
        for business, reading in (
                (b, self._monitoring.collect(b["id"]))
                for b, _s in self._snapshots()):
            indicators = reading.get("indicators") or {}
            rows.append({
                "business_id": business["id"], "name": business["name"],
                "actual_expenses_minor":
                    indicators.get("actual_expenses_minor"),
                "budget_utilisation_max_ratio":
                    indicators.get("budget_utilisation_max_ratio"),
            })
        rows.sort(key=lambda r: r["actual_expenses_minor"] or 0,
                  reverse=True)
        return {
            "answer": "businesses ranked by P-07 actual expenses; "
                      "consumption without results is visible where "
                      "expenses are high and verified collected "
                      "revenue is absent",
            "figures": [_figure("businesses", rows, "verified_fact",
                                "p07.p08_indicators")],
        }
