"""P-17 customer intelligence: brand profiles (§6), personas
(§4.1), ideal customer profiles (§4.2), acquisition channel
evaluations (§4.3) and marketing strategies (§5).

Research discipline: every research record carries its evidence
with an honesty kind (verified | public_research | assumption |
hypothesis). Scores are computed deterministically from declared
factor inputs and stored with the inputs, so any number can be
re-derived. Nothing here is scraped, purchased or fabricated —
records exist only because the owner (or an owner-governed path)
entered them.
"""
from __future__ import annotations

from sqlalchemy import select

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.growth import (
    BrandProfile, ChannelEvaluation, CustomerPersona,
    IdealCustomerProfile, MarketingStrategy,
)
from ..permissions.models import Principal
from . import constants as C
from . import scoring


class IntelligenceMixin:
    # ------------------------------------------------------ brand (§6)
    def set_brand_profile(self, principal: Principal, business_id: str,
                          data: dict) -> dict:
        from .service import brand_profile_dict
        self._require_owner(principal, "growth.brand_profile.set")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            row = session.execute(
                select(BrandProfile).where(
                    BrandProfile.business_id == business_id)).scalar_one_or_none()
            if row is None:
                row = BrandProfile(business_id=business_id,
                                   updated_by=C.actor_of(principal))
                session.add(row)
            for key in ("brand_name", "identity", "tone_of_voice",
                        "typography", "messaging_guidelines",
                        "product_information"):
                if key in data:
                    setattr(row, key, str(data[key]))
            for key in ("colors", "logo_refs", "prohibited_claims", "assets"):
                if key in data:
                    setattr(row, key, list(data[key]))
            row.updated_by = C.actor_of(principal)
            session.commit()
            session.refresh(row)
            result = brand_profile_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.brand_profile_set", "business",
                    business_id, "allow", "brand profile set for business",
                    {})
        return result

    def get_brand_profile(self, principal: Principal,
                          business_id: str) -> dict | None:
        from .service import brand_profile_dict
        self._require_reader(principal, "growth.brand_profile.get")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            row = session.execute(
                select(BrandProfile).where(
                    BrandProfile.business_id == business_id)).scalar_one_or_none()
            return brand_profile_dict(row) if row else None
        finally:
            session.close()

    # --------------------------------------------------- personas (§4.1)
    def create_persona(self, principal: Principal, business_id: str,
                       data: dict) -> dict:
        from .service import persona_dict
        self._require_owner(principal, "growth.persona.create")
        self._business_or_404(business_id)
        evidence = list(data.get("evidence") or [])
        for item in evidence:
            kind = item.get("kind")
            if kind not in C.EVIDENCE_KINDS:
                raise ValidationError(
                    f"persona evidence kind must be one of "
                    f"{C.EVIDENCE_KINDS}; got {kind!r}. Research must "
                    "distinguish verified information, public research, "
                    "assumptions and hypotheses (§4.1)")
        if data.get("budget_sensitivity", "unknown") not in (
                "low", "medium", "high", "unknown"):
            raise ValidationError("budget_sensitivity must be "
                                  "low|medium|high|unknown")
        session = self._session_factory()
        try:
            row = CustomerPersona(
                business_id=business_id,
                segment=str(data.get("segment") or "").strip(),
                needs=list(data.get("needs") or []),
                problems=list(data.get("problems") or []),
                motivations=list(data.get("motivations") or []),
                budget_sensitivity=data.get("budget_sensitivity", "unknown"),
                product_category=str(data.get("product_category") or ""),
                objections=list(data.get("objections") or []),
                discovery_channels=list(data.get("discovery_channels") or []),
                buying_journey=str(data.get("buying_journey") or ""),
                demographics=dict(data.get("demographics") or {}),
                evidence=evidence,
                is_fixture=bool(data.get("is_fixture", False)),
                created_by=C.actor_of(principal))
            if not row.segment:
                raise ValidationError("persona segment is required")
            session.add(row)
            session.commit()
            session.refresh(row)
            result = persona_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.persona_created", "growth",
                    result["id"], "allow", "customer persona created",
                    {"business_id": business_id})
        return result

    def list_personas(self, principal: Principal, business_id: str) -> dict:
        from .service import persona_dict
        self._require_reader(principal, "growth.persona.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            rows = session.execute(
                select(CustomerPersona).where(
                    CustomerPersona.business_id == business_id)
                .order_by(CustomerPersona.created_at)).scalars().all()
            return {"items": [persona_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()

    def delete_persona(self, principal: Principal, persona_id: str) -> dict:
        self._require_owner(principal, "growth.persona.delete")
        session = self._session_factory()
        try:
            row = session.get(CustomerPersona, persona_id)
            if row is None:
                raise NotFoundError(f"persona {persona_id} not found")
            session.delete(row)
            session.commit()
        finally:
            session.close()
        return {"deleted": persona_id}

    # -------------------------------------------------------- ICP (§4.2)
    def create_icp(self, principal: Principal, business_id: str,
                   data: dict) -> dict:
        from .service import icp_dict
        self._require_owner(principal, "growth.icp.create")
        self._business_or_404(business_id)
        kind = str(data.get("kind") or "")
        if kind not in ("b2b", "b2c"):
            raise ValidationError("ICP kind must be b2b or b2c (§4.2)")
        factors = dict(data.get("factor_scores") or {})
        unknown = [k for k in factors if k not in C.ICP_FACTOR_KEYS]
        if unknown:
            raise ValidationError(
                f"unknown ICP factor(s): {unknown}; valid factors are "
                f"{list(C.ICP_FACTOR_KEYS)}")
        scored = scoring.icp_priority(
            factors, self.get_settings()["icp_weights"])
        session = self._session_factory()
        try:
            row = IdealCustomerProfile(
                business_id=business_id, kind=kind,
                segment=str(data.get("segment") or "").strip(),
                criteria=dict(data.get("criteria") or {}),
                factor_scores=factors,
                priority_score=scored["score"],
                rationale=str(data.get("rationale") or ""),
                is_fixture=bool(data.get("is_fixture", False)),
                created_by=C.actor_of(principal))
            if not row.segment:
                raise ValidationError("ICP segment is required")
            session.add(row)
            session.commit()
            session.refresh(row)
            result = {**icp_dict(row), "scoring": scored}
        finally:
            session.close()
        self._audit(principal, "growth.icp_created", "growth",
                    result["id"], "allow", "ideal customer profile created",
                    {"business_id": business_id, "kind": kind})
        return result

    def list_icps(self, principal: Principal, business_id: str) -> dict:
        from .service import icp_dict
        self._require_reader(principal, "growth.icp.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            rows = session.execute(
                select(IdealCustomerProfile).where(
                    IdealCustomerProfile.business_id == business_id)
                .order_by(IdealCustomerProfile.priority_score.desc())
            ).scalars().all()
            items = [icp_dict(r) for r in rows]
            return {"items": items, "count": len(items),
                    "recommendation": (
                        f"prioritise '{items[0]['segment']}' first"
                        if items else
                        "no ICPs recorded yet; segment priority cannot "
                        "be recommended from evidence")}
        finally:
            session.close()

    # --------------------------------------------------- channels (§4.3)
    def create_channel_evaluation(self, principal: Principal,
                                  business_id: str, data: dict) -> dict:
        from .service import channel_dict
        self._require_owner(principal, "growth.channel.create")
        self._business_or_404(business_id)
        channel_key = str(data.get("channel_key") or "")
        if channel_key not in C.CHANNELS:
            raise ValidationError(
                f"unknown channel_key {channel_key!r}; valid channels "
                f"are {sorted(C.CHANNELS)}")
        factors = dict(data.get("factor_scores") or {})
        unknown = [k for k in factors if k not in C.CHANNEL_FACTOR_KEYS]
        if unknown:
            raise ValidationError(
                f"unknown channel factor(s): {unknown}; valid factors "
                f"are {list(C.CHANNEL_FACTOR_KEYS)}")
        scored = scoring.channel_value(
            factors, self.get_settings()["channel_weights"])
        category = C.CHANNELS[channel_key][0]
        session = self._session_factory()
        try:
            row = ChannelEvaluation(
                business_id=business_id, channel_key=channel_key,
                category=category,
                evaluation=dict(data.get("evaluation") or {}),
                factor_scores=factors,
                expected_value_score=scored["score"],
                status=str(data.get("status") or "candidate"),
                notes=str(data.get("notes") or ""),
                created_by=C.actor_of(principal))
            if row.status not in ("candidate", "recommended", "active",
                                  "rejected"):
                raise ValidationError("channel status must be candidate|"
                                      "recommended|active|rejected")
            session.add(row)
            session.commit()
            session.refresh(row)
            result = {**channel_dict(row), "scoring": scored}
        finally:
            session.close()
        self._audit(principal, "growth.channel_evaluated", "growth",
                    result["id"], "allow",
                    "acquisition channel evaluated",
                    {"business_id": business_id, "channel": channel_key})
        return result

    def channel_ranking(self, principal: Principal,
                        business_id: str) -> dict:
        from .service import channel_dict
        self._require_reader(principal, "growth.channel.ranking")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            rows = session.execute(
                select(ChannelEvaluation).where(
                    ChannelEvaluation.business_id == business_id)
                .order_by(ChannelEvaluation.expected_value_score.desc())
            ).scalars().all()
            items = [channel_dict(r) for r in rows]
        finally:
            session.close()
        evaluated = {i["channel_key"] for i in items}
        return {"items": items, "count": len(items),
                "not_evaluated": [k for k in C.CHANNELS
                                  if k not in evaluated],
                "note": "ranked by expected commercial value from "
                        "declared estimates (§4.3); paid channels are "
                        "never recommended merely for traffic — check "
                        "recorded CAC in the budget view before "
                        "committing spend"}

    # ------------------------------------------------- strategies (§5)
    def create_strategy(self, principal: Principal, business_id: str,
                        data: dict) -> dict:
        from .service import strategy_dict
        self._require_owner(principal, "growth.strategy.create")
        self._business_or_404(business_id)
        approach = str(data.get("approach") or "content")
        if approach not in C.STRATEGY_APPROACHES:
            raise ValidationError(
                f"approach must be one of {C.STRATEGY_APPROACHES}")
        kind = str(data.get("kind") or "improve")
        if kind not in C.STRATEGY_KINDS:
            raise ValidationError(
                f"strategy kind must be one of {C.STRATEGY_KINDS} "
                "(the owner's ordering categories)")
        sections = dict(data.get("sections") or {})
        unknown = [k for k in sections if k not in C.STRATEGY_SECTION_KEYS]
        if unknown:
            raise ValidationError(
                f"unknown strategy section(s): {unknown}; the fifteen "
                f"§5 sections are {list(C.STRATEGY_SECTION_KEYS)}")
        session = self._session_factory()
        try:
            row = MarketingStrategy(
                business_id=business_id,
                title=str(data.get("title") or "").strip(),
                approach=approach, kind=kind, sections=sections,
                status="draft", created_by=C.actor_of(principal))
            if not row.title:
                raise ValidationError("strategy title is required")
            session.add(row)
            session.commit()
            session.refresh(row)
            result = strategy_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.strategy_created", "growth",
                    result["id"], "allow", "marketing strategy drafted",
                    {"business_id": business_id, "kind": kind})
        return result

    def list_strategies(self, principal: Principal, *,
                        business_id: str | None = None,
                        status: str | None = None) -> dict:
        from .service import strategy_dict
        self._require_reader(principal, "growth.strategy.list")
        session = self._session_factory()
        try:
            query = select(MarketingStrategy)
            if business_id:
                query = query.where(
                    MarketingStrategy.business_id == business_id)
            if status:
                query = query.where(MarketingStrategy.status == status)
            rows = session.execute(
                query.order_by(MarketingStrategy.created_at)).scalars().all()
            items = []
            gate = self._gate()
            for row in rows:
                item = strategy_dict(row)
                item["blocked_by_profitability_gate"] = bool(
                    row.kind == "expansion" and row.status in
                    ("draft", "proposed") and gate["state"] == "closed"
                    and not row.gate_override)
                items.append(item)
            return {"items": items, "count": len(items),
                    "profitability_gate": gate}
        finally:
            session.close()

    def decide_strategy(self, principal: Principal, strategy_id: str,
                        decision: str, *,
                        approval_id: str | None = None,
                        gate_override_reason: str | None = None) -> dict:
        from .service import strategy_dict
        self._require_owner(principal, "growth.strategy.decide")
        if decision not in ("approve", "reject"):
            raise ValidationError("decision must be approve or reject")
        session = self._session_factory()
        try:
            row = session.get(MarketingStrategy, strategy_id)
            if row is None:
                raise NotFoundError(f"strategy {strategy_id} not found")
            if row.status not in ("draft", "proposed"):
                raise ValidationError(
                    f"strategy is {row.status}; only draft/proposed "
                    "strategies can be decided")
            snapshot = strategy_dict(row)
        finally:
            session.close()
        override = None
        if decision == "approve":
            if snapshot["kind"] == "expansion":
                override = self._check_gate(
                    principal, what="an expansion strategy",
                    gate_override_reason=gate_override_reason)
            approval = self._owner_approval(
                principal, action="growth.strategy.approve",
                resource=strategy_id,
                parameters={"strategy_id": strategy_id,
                            "business_id": snapshot["business_id"],
                            "kind": snapshot["kind"]},
                reason="owner approval of P-17 marketing strategy (§5)",
                approval_id=approval_id)
        session = self._session_factory()
        try:
            row = session.get(MarketingStrategy, strategy_id)
            if decision == "approve":
                row.status = "approved"
                row.approval_id = approval
                if override is not None:
                    row.gate_override = override
            else:
                row.status = "rejected"
            session.commit()
            session.refresh(row)
            result = strategy_dict(row)
        finally:
            session.close()
        self._audit(principal, f"growth.strategy_{decision}d", "growth",
                    strategy_id, "allow",
                    f"marketing strategy {decision}d",
                    {"gate_override": bool(override)})
        return result
