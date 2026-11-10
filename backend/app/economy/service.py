"""P-16 EconomyService: the AI Economy Expansion Engine.

An economic intelligence and recommendation layer over P-01–P-15.
It owns only economy state (see models/economy.py). Every authority
stays where it already lives:

* business identity + lifecycle — P-06 (referenced, never copied;
  lifecycle labels are P-13's derivation over P-06's machine);
* money — P-07 (every figure is read live from ``FinancialService``;
  P-16 stores no ledger data, executes no spend, and its proposals
  provably leave P-07's consolidated output byte-equal);
* portfolio grouping/relationships — P-13 (read as the relationship
  map source; P-16 adds classifications, not a second registry);
* opportunity research substrate — P-03 (P-16's pipeline references
  P-03 opportunities; per-opportunity research stays in P-03);
* experiments — P-08 (P-16 proposals hand off; P-08 binds the real
  P-07 budget and enforces the stop-loss);
* approvals — P-01 hash-bound approvals (P-16 stores only ids);
* memory — P-09 (verified outcomes fed best-effort; memory is data,
  never authority — Article 0);
* governance — P-10 (P-16 adds no authority; writes are owner-gated
  in-service on the P-13 pattern, and its pause/freeze flags compose
  with P-10 modes rather than replacing them).

The owner's strategic priority — profitability before new
businesses, then diversification, then capital efficiency — is a
mechanical gate (see ``profitability_gate`` in scoring.py and
``_gate`` here), not a comment: while the gate is closed, new-
business and market-entry work cannot be approved or advanced, the
growth allocation scenario is refused, and recommendations lead
with improving what already exists. Only the owner can override,
explicitly, per item, with a recorded reason.
"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import select

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..core.logging import get_logger
from ..database.models.base import as_utc, utcnow
from ..database.models.core import AuditEvent
from ..database.models.economy import (
    EconomyClassification, EconomicDecision,
)
from ..database.repositories.core import AuditRepository, ConfigRepository
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from . import scoring
from .capital import CapitalMixin
from .markets import MarketsMixin
from .opportunities import OpportunitiesMixin
from .risk import RiskMixin
from .ventures import VenturesMixin

SYSTEM_PRINCIPAL = Principal(PrincipalType.SYSTEM, "p16-economy")

_log = get_logger("economy.service")


def _iso(value: dt.datetime | None) -> str | None:
    value = as_utc(value)
    return value.isoformat() if value else None


def _actor(principal) -> str:
    return C.actor_of(principal)


# ------------------------------------------------------------ dicts
def classification_dict(row: EconomyClassification) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "industry": row.industry, "revenue_model": row.revenue_model,
            "market": row.market, "geographic_exposure": row.geographic_exposure,
            "capital_requirements_band": row.capital_requirements_band,
            "strategic_importance": row.strategic_importance,
            "notes": row.notes, "updated_by": row.updated_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def decision_dict(row: EconomicDecision) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "opportunity_id": row.opportunity_id,
            "objective": row.objective,
            "supporting_evidence": row.supporting_evidence or [],
            "financial_assumptions": row.financial_assumptions or {},
            "expected_benefits": row.expected_benefits,
            "potential_losses": row.potential_losses,
            "alternatives": row.alternatives or [],
            "confidence": row.confidence,
            "required_permissions": row.required_permissions or [],
            "recommended_action": row.recommended_action,
            "outcome": row.outcome,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


class EconomyService(MarketsMixin, OpportunitiesMixin, CapitalMixin,
                     VenturesMixin, RiskMixin):
    """Composed of mixins, one per prompt area, sharing the helpers
    here (the P-13 PortfolioService shape). Constructed over the
    assembled Application (the P-15 precedent)."""

    def __init__(self, application):
        self._app = application
        self._session_factory = application.session_factory
        self._business = application.business        # P-06
        self._financial = application.financial      # P-07
        self._survival = application.survival        # P-08
        self._memory = application.memory            # P-09
        self._portfolio = application.portfolio      # P-13
        self._discovery = application.opportunities  # P-03
        self._approvals = application.approvals      # P-01
        self._bus = application.bus

    # ------------------------------------------------------- settings
    def seed_settings(self) -> None:
        session = self._session_factory()
        try:
            repo = ConfigRepository(session)
            if repo.get(C.SETTINGS_KEY) is None:
                repo.set(C.SETTINGS_KEY, json.dumps(C.DEFAULT_SETTINGS),
                         "P-16 economy expansion settings; owner-editable "
                         "governance (autonomy level, pause/freeze flags, "
                         "evidence gate, scoring weights, shares)")
        finally:
            session.close()

    def get_settings(self) -> dict:
        session = self._session_factory()
        try:
            row = ConfigRepository(session).get(C.SETTINGS_KEY)
            stored = json.loads(row.value) if row and row.value else {}
        finally:
            session.close()
        merged = dict(C.DEFAULT_SETTINGS)
        merged.update(stored)
        for nested in ("factor_weights", "country_weights",
                       "reinvestment_shares"):
            merged[nested] = {**C.DEFAULT_SETTINGS[nested],
                              **(stored.get(nested) or {})}
        return merged

    def update_settings(self, principal: Principal, patch: dict) -> dict:
        self._require_owner(principal, "economy.settings.update")
        current = self.get_settings()
        for key in ("expansion_paused", "capital_commitments_frozen"):
            if key in patch:
                current[key] = bool(patch[key])
        if "autonomy_level" in patch:
            level = int(patch["autonomy_level"])
            if level not in C.AUTONOMY_LEVELS:
                raise ValidationError("autonomy_level must be 1..4 (§18)")
            current["autonomy_level"] = level
        for key, lo, hi in (("evidence_gate_min_confidence", 0, 100),
                            ("evidence_gate_min_items", 0, 20),
                            ("concentration_threshold_bps", 1, 10000)):
            if key in patch:
                value = int(patch[key])
                if not lo <= value <= hi:
                    raise ValidationError(f"{key} must be within {lo}..{hi}")
                current[key] = value
        for key, valid in (("factor_weights", C.FACTOR_KEYS),
                           ("country_weights", C.COUNTRY_CRITERIA)):
            if key in patch:
                for factor, weight in dict(patch[key]).items():
                    if factor not in valid:
                        raise ValidationError(f"unknown {key} entry: {factor}")
                    if float(weight) < 0:
                        raise ValidationError("weights must be >= 0")
                    current[key][factor] = weight
        if "reinvestment_shares" in patch:
            shares = {k: float(v) for k, v in
                      dict(patch["reinvestment_shares"]).items()}
            if any(v < 0 for v in shares.values()):
                raise ValidationError("reinvestment shares must be >= 0")
            if abs(sum(shares.values()) - 100.0) > 0.001:
                raise ValidationError(
                    "reinvestment shares must sum to 100")
            current["reinvestment_shares"] = shares
        session = self._session_factory()
        try:
            ConfigRepository(session).set(
                C.SETTINGS_KEY, json.dumps(current),
                "P-16 economy expansion settings; owner-editable")
        finally:
            session.close()
        self._audit(principal, "economy.settings_updated", "economy",
                    None, "allow", "owner updated P-16 economy settings",
                    {"keys": sorted(patch.keys())})
        return current

    # ------------------------------------------------------------ audit
    def _audit(self, principal, action, target_type, target_id, decision,
               reason=None, details=None) -> None:
        session = self._session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value if principal else "system",
                actor_id=principal.id if principal else "economy-engine",
                action=action, target_type=target_type,
                target_id=target_id, decision=decision, reason=reason,
                correlation_id=None, details=details or {},
                created_at=utcnow()))
        finally:
            session.close()

    # ------------------------------------------------------ authorities
    @staticmethod
    def _require_owner(principal: Principal, action: str) -> None:
        if principal.type != PrincipalType.OWNER:
            raise PermissionDeniedError(
                f"{action} is restricted to the owner: economy-level "
                "decisions change cross-business strategy and remain "
                "owner authority (§18/§24)")

    def _require_reader(self, principal: Principal, action: str) -> None:
        """Economy aggregates are owner/system-only (the P-13 §20
        posture): an agent never sees the whole ecosystem by
        default."""
        if principal.type not in (PrincipalType.OWNER,
                                  PrincipalType.SYSTEM):
            self._audit(principal, "economy.isolation_violation",
                        "economy", None, "deny",
                        f"{action}: economy aggregates are not visible "
                        "to this principal",
                        {"principal": _actor(principal)})
            raise PermissionDeniedError(
                "economy-level information is restricted to the owner; "
                "agents receive only explicitly scoped grants")

    # ---------------------------------------------------------- helpers
    def _business_or_404(self, business_id: str) -> dict:
        try:
            return self._business.get_business(business_id)
        except Exception:
            raise NotFoundError(f"business {business_id} not found")

    def _all_businesses(self) -> list[dict]:
        rows, _total = self._business.list_businesses(limit=500)
        return rows

    def _indicators(self, business_id: str) -> dict | None:
        """P-07's stable read contract; None when the business has
        no financial profile (never fabricated)."""
        try:
            return self._financial.p08_indicators(business_id)
        except Exception:
            return None

    def _profitability_rows(self) -> list[dict]:
        rows = []
        for business in self._all_businesses():
            indicators = self._indicators(business["id"])
            if indicators is None:
                rows.append({"business_id": business["id"],
                             "name": business["name"],
                             "is_fixture": business.get("is_fixture", False),
                             "has_profile": False,
                             "verified_collected_revenue_minor": 0,
                             "net_profit_minor": None})
                continue
            profit = indicators.get("profitability") or {}
            rows.append({
                "business_id": business["id"], "name": business["name"],
                "is_fixture": business.get("is_fixture", False),
                "has_profile": True,
                "verified_collected_revenue_minor":
                    indicators.get("verified_collected_revenue_minor") or 0,
                "net_profit_minor": profit.get("net_profit_minor"),
                "profitability_status": profit.get("status"),
                "available_capital_minor":
                    indicators.get("available_capital_minor"),
                "runway_months": indicators.get("runway_months"),
                "financial_risk": indicators.get("financial_risk")})
        return rows

    def _gate(self) -> dict:
        """The owner's profitability gate over live P-07 figures."""
        return scoring.profitability_gate(self._profitability_rows())

    def _owner_approval(self, principal: Principal, *, action: str,
                        resource: str | None, parameters: dict,
                        reason: str, approval_id: str | None = None,
                        ) -> str:
        """The P-08 approval pattern: a supplied approval must be a
        hash-bound, owner-decided P-01 approval for exactly these
        parameters; an owner caller without one gets a created +
        decided approval (the owner's call *is* the decision, bound
        and audited); anyone else is refused."""
        if approval_id:
            ok = False
            try:
                approval = self._approvals.get(approval_id)
                ok = (approval.status == "approved"
                      and bool(approval.approver_id)
                      and approval.approver_id.startswith("owner:")
                      and self._approvals.verify_binding(
                          approval, action, resource, parameters))
            except Exception:
                ok = False
            if not ok:
                self._audit(principal, f"{action}.approve", "economy",
                            resource, "deny",
                            "approval binding invalid or not "
                            "owner-decided", {"approval_id": approval_id})
                raise PermissionDeniedError(
                    "approval must be a hash-bound P-01 approval "
                    "decided by the owner for exactly these parameters")
            return approval_id
        if principal.type == PrincipalType.OWNER:
            approval = self._approvals.create(
                principal, action=action, resource=resource,
                risk_classification="high", reason=reason,
                requested_permissions=["approve_actions"],
                parameters=parameters)
            self._approvals.decide(approval.id, principal, True)
            return approval.id
        raise PermissionDeniedError(
            "this economy decision requires owner approval; an agent "
            "cannot approve its own proposals (§18)")

    def _feed_memory(self, principal, *, title: str, content: str,
                     source_ref: str, business_id: str | None = None,
                     outcome_status: str = "verified") -> None:
        """Best-effort P-09 feed of *verified outcomes only*
        (experiment evaluations, recorded decision outcomes). A feed
        failure never changes the economy result (the P-14 I6
        posture)."""
        if self._memory is None:
            return
        try:
            self._memory.ingestion.ingest(principal, {
                "title": title, "content": content,
                "source_type": "agent_output", "source_ref": source_ref,
                "business_id": business_id,
                "verification_status": outcome_status})
        except Exception as exc:  # feeding must not break the engine
            _log.warning("P-16 outcome feed to P-09 failed: %s", exc)

    # ---------------------------------------------------------- status
    def engine_status(self, principal: Principal) -> dict:
        self._require_reader(principal, "economy.status")
        settings = self.get_settings()
        return {
            "engine": C.ENGINE_NAME,
            "autonomy_level": settings["autonomy_level"],
            "expansion_paused": settings["expansion_paused"],
            "capital_commitments_frozen":
                settings["capital_commitments_frozen"],
            "profitability_gate": self._gate(),
            "financial_authority": "P-07",
            "business_authority": "P-06",
            "experiment_authority": "P-08",
            "execution_capability": "none — intelligence, "
                                    "recommendations and governed "
                                    "handoffs only",
            "generated_at": utcnow().isoformat(),
        }

    # ------------------------------------------------- §15A/§21 overview
    def overview(self, principal: Principal) -> dict:
        """§15 Panel A + §21 KPIs, all read live from P-07. Flow
        figures (revenue, profit) sum across businesses in the same
        currency only where P-07's own per-business figures share
        the profile currency — mixed-currency rows are listed, never
        summed. Cash is per business, never combined (P-13 rule)."""
        self._require_reader(principal, "economy.overview")
        rows = self._profitability_rows()
        profiled = [r for r in rows if r["has_profile"]]
        total_collected = sum(r["verified_collected_revenue_minor"]
                              for r in profiled)
        profits = [r["net_profit_minor"] for r in profiled
                   if r["net_profit_minor"] is not None]
        total_profit = sum(profits) if len(profits) == len(profiled) \
            and profiled else None
        expenses_total = None
        revenue_detail = []
        recurring_arr = 0
        for business in self._all_businesses():
            indicators = self._indicators(business["id"])
            if indicators is None:
                continue
            summary = self._financial.business_summary(business["id"])
            revenue_detail.append({
                "business_id": business["id"], "name": business["name"],
                "is_fixture": business.get("is_fixture", False),
                "currency": summary["revenue"].get("currency"),
                "net_collected_minor":
                    summary["revenue"].get("net_collected_minor") or 0,
                "projected_minor":
                    summary["revenue"].get("projected_minor") or 0,
                "mrr_minor": summary["revenue"].get("mrr_minor") or 0})
            recurring_arr += int(summary["revenue"].get("arr_minor") or 0)
            exp = (summary.get("expenses") or {}).get(
                "pl_expense_paid_minor")
            if exp is not None:
                expenses_total = (expenses_total or 0) + int(exp)
        gate = scoring.profitability_gate(rows)
        concentration = self._revenue_concentration(rows)
        return {
            "generated_at": utcnow().isoformat(),
            "financial_authority": "P-07",
            "businesses": {
                "total": len(rows), "with_financial_profile": len(profiled),
                "fixtures_labelled": all(
                    "is_fixture" in r for r in rows)},
            "global_economic_overview": {
                "total_verified_collected_revenue_minor": total_collected,
                "total_net_profit_minor": total_profit,
                "total_actual_expenses_minor": expenses_total,
                "per_business": revenue_detail,
                "collected_vs_projected": "separate fields, never blended",
                "combined_available_cash": None,
                "combined_cash_note": "cash balances of separate "
                                      "businesses are never summed "
                                      "(P-13 §11 rule); see each "
                                      "business's available capital in "
                                      "the portfolio view"},
            "kpis": {
                "total_realized_revenue_minor": total_collected,
                "net_operating_profit_minor": total_profit,
                "recurring_revenue_arr_minor": recurring_arr,
                "recurring_share_of_collected": (
                    round(recurring_arr / (recurring_arr + total_collected), 4)
                    if (recurring_arr + total_collected) > 0 else None),
                "revenue_concentration": concentration,
                "business_survival": {
                    "operating": sum(1 for b in self._all_businesses()
                                     if b["status"] == "OPERATIONAL"),
                    "total": len(rows)},
                "note": "KPIs are computed from P-07/P-06 data only; "
                        "counts of businesses or opportunities are "
                        "reported as inventory, never as success "
                        "metrics (§21)"},
            "profitability_gate": gate,
        }

    def _revenue_concentration(self, rows: list[dict]) -> dict:
        amounts = {r["business_id"]: r["verified_collected_revenue_minor"]
                   for r in rows if r["has_profile"]}
        index = scoring.hhi(amounts)
        top, share = scoring.largest_share(amounts)
        settings = self.get_settings()
        threshold = settings["concentration_threshold_bps"] / 10000
        return {"hhi": index, "top_business_id": top,
                "top_share": share,
                "threshold_share": threshold,
                "overconcentrated": (share is not None
                                     and share > threshold),
                "basis": "verified collected revenue per business "
                         "(P-07), same-currency profiles only in "
                         "practice; businesses without profiles are "
                         "excluded, never estimated"}

    # ------------------------------------------- §5.1 classifications
    def set_classification(self, principal: Principal,
                           business_id: str, data: dict) -> dict:
        self._require_owner(principal, "economy.classification.set")
        self._business_or_404(business_id)
        if data.get("revenue_model") and \
                data["revenue_model"] not in C.REVENUE_MODELS:
            raise ValidationError(
                f"unknown revenue_model: {data['revenue_model']}")
        if data.get("capital_requirements_band") and \
                data["capital_requirements_band"] not in (
                        "minimal", "low", "moderate", "high", "unknown"):
            raise ValidationError("unknown capital_requirements_band")
        importance = int(data.get("strategic_importance", 50))
        if not 0 <= importance <= 100:
            raise ValidationError("strategic_importance must be 0..100")
        session = self._session_factory()
        try:
            row = session.execute(
                select(EconomyClassification).where(
                    EconomyClassification.business_id == business_id)
            ).scalars().first()
            if row is None:
                row = EconomyClassification(
                    business_id=business_id, updated_by=_actor(principal))
                session.add(row)
            for key in ("industry", "revenue_model", "market",
                        "geographic_exposure",
                        "capital_requirements_band", "notes"):
                if key in data:
                    setattr(row, key, data[key])
            row.strategic_importance = importance
            row.updated_by = _actor(principal)
            session.commit()
            session.refresh(row)
            result = classification_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.classification_set", "business",
                    business_id, "allow",
                    "owner set the §5.1 business classification")
        return result

    def list_classifications(self, principal: Principal) -> dict:
        """§5.1/§15 Panel B: declared classification + live derived
        facts (profitability, maturity label, concentration share).
        The §5.2 lifecycle label is derived from P-06 state through
        P-13's own derivation function; P-16 stores no lifecycle and
        marks nothing operational or profitable itself."""
        self._require_reader(principal, "economy.classifications")
        from ..portfolio.constants import portfolio_stage
        session = self._session_factory()
        try:
            declared = {r.business_id: classification_dict(r) for r in
                        session.execute(
                            select(EconomyClassification)).scalars()}
        finally:
            session.close()
        rows = self._profitability_rows()
        total_collected = sum(r["verified_collected_revenue_minor"]
                              for r in rows if r["has_profile"]) or 0
        label_map = {
            "IDEA": "idea", "VALIDATING": "validation",
            "APPROVED": "validation", "BUILDING": "launch",
            "LAUNCHING": "launch", "OPERATIONAL": "established_operation",
            "OPTIMIZING": "maturity", "SCALING": "expansion",
            "AT_RISK": "restructuring", "RESTRUCTURING": "restructuring",
            "PAUSED": "established_operation", "BLOCKED": "restructuring",
            "CLOSING": "exit_or_closure", "ARCHIVED": "exit_or_closure"}
        items = []
        for business in self._all_businesses():
            prow = next((r for r in rows
                         if r["business_id"] == business["id"]), {})
            stage = portfolio_stage(business["status"], None)
            share = (prow.get("verified_collected_revenue_minor", 0)
                     / total_collected) if total_collected else None
            items.append({
                "business_id": business["id"], "name": business["name"],
                "is_fixture": business.get("is_fixture", False),
                "p06_status": business["status"],
                "lifecycle_label": label_map.get(stage, "idea"),
                "lifecycle_basis": "derived from P-06 status via "
                                   "P-13's portfolio_stage(); P-16 "
                                   "stores no lifecycle",
                "classification": declared.get(business["id"]),
                "profitability": {
                    "has_profile": prow.get("has_profile", False),
                    "verified_collected_revenue_minor":
                        prow.get("verified_collected_revenue_minor", 0),
                    "net_profit_minor": prow.get("net_profit_minor"),
                    "status": prow.get("profitability_status")},
                "revenue_share": (round(share, 4)
                                  if share is not None else None),
                "available_capital_minor":
                    prow.get("available_capital_minor"),
                "risk": prow.get("financial_risk")})
        settings = self.get_settings()
        threshold = settings["concentration_threshold_bps"] / 10000
        over = [i for i in items if i["revenue_share"] is not None
                and i["revenue_share"] > threshold]
        return {"items": items, "total": len(items),
                "overconcentration_flags": [
                    {"business_id": i["business_id"],
                     "revenue_share": i["revenue_share"],
                     "threshold_share": threshold,
                     "warning": "one business supplies more than the "
                                "owner's concentration threshold of "
                                "verified collected revenue (§5.1)"}
                    for i in over]}

    # ------------------------------------------------ §5 relationship map
    def relationship_map(self, principal: Principal) -> dict:
        """§5 economic relationship map, sourced from P-13's
        registry and relationships (read with the system principal —
        P-13's reader rule admits owner/system). P-16 adds the
        cross-selling reading: businesses sharing a declared market
        or revenue model are *candidate* synergies, labelled as
        candidates — a shared attribute grants nothing and proves
        no synergy (§5 consent/rights rule)."""
        self._require_reader(principal, "economy.relationship_map")
        portfolios = self._portfolio.list_portfolios(SYSTEM_PRINCIPAL)
        members: dict[str, list[str]] = {}
        for portfolio in portfolios.get("items", []):
            listed = self._portfolio.list_members(
                SYSTEM_PRINCIPAL, portfolio["id"])
            members[portfolio["id"]] = [
                m["business_id"] for m in listed.get("items", [])]
        relationships = self._portfolio.list_relationships(
            SYSTEM_PRINCIPAL)
        rel_items = relationships.get("items", []) \
            if isinstance(relationships, dict) else relationships
        session = self._session_factory()
        try:
            declared = {r.business_id: r for r in session.execute(
                select(EconomyClassification)).scalars()}
        finally:
            session.close()
        by_market: dict[str, list[str]] = {}
        by_model: dict[str, list[str]] = {}
        for bid, row in declared.items():
            if row.market:
                by_market.setdefault(row.market, []).append(bid)
            if row.revenue_model:
                by_model.setdefault(row.revenue_model, []).append(bid)
        candidates = []
        for basis, groups in (("shared_market", by_market),
                              ("shared_revenue_model", by_model)):
            for key, bids in groups.items():
                if len(bids) > 1:
                    candidates.append({
                        "basis": basis, "key": key, "business_ids": bids,
                        "label": "candidate synergy only — shared "
                                 "audiences, customer data and "
                                 "resources require consent, "
                                 "contractual rights and privacy "
                                 "protection before any use (§5)"})
        return {"portfolios": portfolios.get("items", []),
                "members": members, "relationships": rel_items,
                "cross_selling_candidates": candidates,
                "source": "P-13 registry and relationships (live)"}

    # ------------------------------------------------ §16 decisions
    def create_decision(self, principal: Principal, data: dict) -> dict:
        self._require_owner(principal, "economy.decision.create")
        if not (data.get("objective") or "").strip():
            raise ValidationError("a decision record requires an "
                                  "objective (§16)")
        if data.get("business_id"):
            self._business_or_404(data["business_id"])
        confidence = int(data.get("confidence", 0))
        if not 0 <= confidence <= 100:
            raise ValidationError("confidence must be 0..100")
        session = self._session_factory()
        try:
            row = EconomicDecision(
                business_id=data.get("business_id"),
                opportunity_id=data.get("opportunity_id"),
                objective=data["objective"],
                supporting_evidence=data.get("supporting_evidence") or [],
                financial_assumptions=data.get("financial_assumptions") or {},
                expected_benefits=data.get("expected_benefits") or "",
                potential_losses=data.get("potential_losses") or "",
                alternatives=data.get("alternatives") or [],
                confidence=confidence,
                required_permissions=data.get("required_permissions") or [],
                recommended_action=data.get("recommended_action") or "",
                created_by=_actor(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = decision_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.decision_created", "economy",
                    result["id"], "allow",
                    "economic decision record created (§16)")
        return result

    def list_decisions(self, principal: Principal, *,
                       business_id: str | None = None,
                       limit: int = 100) -> dict:
        self._require_reader(principal, "economy.decisions")
        session = self._session_factory()
        try:
            stmt = select(EconomicDecision)
            if business_id:
                stmt = stmt.where(
                    EconomicDecision.business_id == business_id)
            rows = session.execute(
                stmt.order_by(EconomicDecision.created_at.desc())
                .limit(limit)).scalars().all()
            return {"items": [decision_dict(r) for r in rows],
                    "total": len(rows)}
        finally:
            session.close()

    def record_decision_outcome(self, principal: Principal,
                                decision_id: str, data: dict) -> dict:
        """§16 field 13 + §17: the actual outcome, recorded when
        known, and fed to P-09 as a verified outcome. A recorded
        success is stored as history — never as proof the same
        strategy will succeed again."""
        self._require_owner(principal, "economy.decision.outcome")
        result_value = data.get("result")
        if result_value not in ("success", "failure", "mixed",
                                "abandoned"):
            raise ValidationError(
                "outcome result must be success|failure|mixed|abandoned")
        session = self._session_factory()
        try:
            row = session.get(EconomicDecision, decision_id)
            if row is None:
                raise NotFoundError(f"decision {decision_id} not found")
            row.outcome = {"result": result_value,
                           "notes": data.get("notes") or "",
                           "recorded_at": utcnow().isoformat(),
                           "recorded_by": _actor(principal)}
            session.commit()
            session.refresh(row)
            result = decision_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.decision_outcome", "economy",
                    decision_id, "allow",
                    f"decision outcome recorded: {result_value}")
        self._feed_memory(
            principal,
            title=f"Economic decision outcome: {result_value}",
            content=(f"Decision {decision_id} "
                     f"({result['objective'][:200]}) concluded "
                     f"{result_value}. {data.get('notes') or ''}"),
            source_ref=f"p16:decision:{decision_id}",
            business_id=result.get("business_id"))
        return result
