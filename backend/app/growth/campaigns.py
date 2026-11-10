"""P-17 campaigns (§7), content production (§6) and growth
experiments (§14).

Campaign discipline: a campaign's budget ceiling is an approved
ceiling, never spend; actual spend and attributed revenue are read
live from P-07 (§21/§22). Approval is a governed owner decision;
expansion-purpose approval additionally respects the P-16
profitability gate. Auto-pause exists only inside explicitly
approved campaign rules at autonomy level 4 (§24) — otherwise the
engine alerts and asks.

Content discipline: the §6 workflow (brief → generation → fact
check → brand review → copyright/licensing → quality → approval)
is explicit state. The brand check is mechanical: content
containing one of its own business's prohibited claims cannot be
marked brand-passed. Release records an owner-attested external
reference — no platform is connected and the system publishes
nothing itself.

Experiment discipline: pre-declared in full (Constitution rule),
executed only by handoff to P-08, concluded only on the declared
minimum evaluation (§14).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.growth import (
    ContentItem, GrowthExperiment, GrowthLead, MarketingCampaign,
)
from ..permissions.models import Principal
from . import constants as C
from . import scoring


class CampaignsMixin:
    # --------------------------------------------------- campaigns (§7)
    def create_campaign(self, principal: Principal, business_id: str,
                        data: dict) -> dict:
        from .service import campaign_dict, slug_for
        self._require_owner(principal, "growth.campaign.create")
        self._business_or_404(business_id)
        purpose = str(data.get("purpose") or "acquisition")
        if purpose not in C.CAMPAIGN_PURPOSES:
            raise ValidationError(
                f"campaign purpose must be one of {C.CAMPAIGN_PURPOSES}")
        channel_key = str(data.get("channel_key") or "")
        if channel_key and channel_key not in C.CHANNELS:
            raise ValidationError(f"unknown channel_key {channel_key!r}")
        ceiling = data.get("budget_ceiling_minor")
        if ceiling is not None and int(ceiling) < 0:
            raise ValidationError("budget ceiling cannot be negative")
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValidationError("campaign name is required")
        session = self._session_factory()
        try:
            base_code = slug_for(name)
            code = base_code
            clash = session.execute(
                select(MarketingCampaign).where(
                    MarketingCampaign.business_id == business_id,
                    MarketingCampaign.code == code)).scalar_one_or_none()
            if clash is not None:
                code = f"{base_code}-{uuid.uuid4().hex[:6]}"
            row = MarketingCampaign(
                business_id=business_id, name=name, code=code,
                objective=str(data.get("objective") or ""),
                purpose=purpose,
                strategy_id=data.get("strategy_id"),
                channel_evaluation_id=data.get("channel_evaluation_id"),
                channel_key=channel_key,
                target_audience=dict(data.get("target_audience") or {}),
                start_date=data.get("start_date"),
                end_date=data.get("end_date"),
                budget_ceiling_minor=(int(ceiling)
                                      if ceiling is not None else None),
                currency=str(data.get("currency") or "INR"),
                expected_results=dict(data.get("expected_results") or {}),
                creative_asset_refs=list(
                    data.get("creative_asset_refs") or []),
                landing_page=str(data.get("landing_page") or ""),
                conversion_event=str(data.get("conversion_event") or ""),
                status="idea",
                auto_pause_rules=data.get("auto_pause_rules"),
                is_fixture=bool(data.get("is_fixture", False)),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = campaign_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.campaign_created", "growth",
                    result["id"], "allow", "campaign created",
                    {"business_id": business_id, "purpose": purpose})
        return result

    def list_campaigns(self, principal: Principal, *,
                       business_id: str | None = None,
                       status: str | None = None) -> dict:
        from .service import campaign_dict
        self._require_reader(principal, "growth.campaign.list")
        session = self._session_factory()
        try:
            query = select(MarketingCampaign)
            if business_id:
                query = query.where(
                    MarketingCampaign.business_id == business_id)
            if status:
                query = query.where(MarketingCampaign.status == status)
            rows = session.execute(
                query.order_by(MarketingCampaign.created_at)).scalars().all()
            items = [campaign_dict(r) for r in rows]
            return {"items": items, "count": len(items)}
        finally:
            session.close()

    def get_campaign(self, principal: Principal, campaign_id: str) -> dict:
        from .service import campaign_dict
        self._require_reader(principal, "growth.campaign.get")
        session = self._session_factory()
        try:
            row = session.get(MarketingCampaign, campaign_id)
            if row is None:
                raise NotFoundError(f"campaign {campaign_id} not found")
            return campaign_dict(row)
        finally:
            session.close()

    def transition_campaign(self, principal: Principal, campaign_id: str,
                            target: str) -> dict:
        from .service import campaign_dict
        self._require_owner(principal, "growth.campaign.transition")
        if target == "approved":
            raise ValidationError(
                "campaign approval is a governed decision; use the "
                "approve path, not a lifecycle transition")
        session = self._session_factory()
        try:
            row = session.get(MarketingCampaign, campaign_id)
            if row is None:
                raise NotFoundError(f"campaign {campaign_id} not found")
            allowed = C.CAMPAIGN_TRANSITIONS.get(row.status, ())
            if target not in allowed:
                raise ValidationError(
                    f"campaign cannot move from {row.status} to {target}; "
                    f"allowed: {list(allowed)}")
            if target in ("active", "scheduled") and self.get_settings()[
                    "all_campaigns_paused"]:
                raise ValidationError(
                    "all campaigns are paused by the owner's emergency "
                    "control (§24); activation is refused until it is "
                    "lifted")
            row.status = target
            if target == "active":
                row.paused_reason = None
            session.commit()
            session.refresh(row)
            result = campaign_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.campaign_transition", "growth",
                    campaign_id, "allow", f"campaign -> {target}", {})
        return result

    def approve_campaign(self, principal: Principal, campaign_id: str, *,
                         approval_id: str | None = None,
                         gate_override_reason: str | None = None) -> dict:
        from .service import campaign_dict
        self._require_owner(principal, "growth.campaign.approve")
        session = self._session_factory()
        try:
            row = session.get(MarketingCampaign, campaign_id)
            if row is None:
                raise NotFoundError(f"campaign {campaign_id} not found")
            if row.status not in ("idea", "research", "strategy", "draft",
                                  "approval_pending"):
                raise ValidationError(
                    f"campaign is {row.status}; only pre-approval states "
                    "can be approved")
            snapshot = campaign_dict(row)
        finally:
            session.close()
        override = None
        if snapshot["purpose"] == "expansion":
            override = self._check_gate(
                principal, what="an expansion-purpose campaign",
                gate_override_reason=gate_override_reason)
        approval = self._owner_approval(
            principal, action="growth.campaign.approve",
            resource=campaign_id,
            parameters={"campaign_id": campaign_id,
                        "business_id": snapshot["business_id"],
                        "budget_ceiling_minor":
                            snapshot["budget_ceiling_minor"],
                        "purpose": snapshot["purpose"]},
            reason="owner approval of P-17 marketing campaign (§7)",
            approval_id=approval_id)
        session = self._session_factory()
        try:
            row = session.get(MarketingCampaign, campaign_id)
            row.status = "approved"
            row.approval_id = approval
            if override is not None:
                row.gate_override = override
            session.commit()
            session.refresh(row)
            result = campaign_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.campaign_approved", "growth",
                    campaign_id, "allow", "campaign approved",
                    {"gate_override": bool(override)})
        return result

    def prepare_spend_request(self, principal: Principal,
                              campaign_id: str, data: dict) -> dict:
        """Prepare a P-07 spending request for this campaign (§21).
        The request lives entirely inside P-07's approval workflow;
        P-17 stores only its id. Refused while marketing spend is
        frozen (owner control) or the campaign is unapproved."""
        from ..financial.money import Money
        self._require_owner(principal, "growth.campaign.spend_request")
        if self.get_settings()["marketing_spend_frozen"]:
            raise ValidationError(
                "marketing expenditure is frozen by the owner (§24); "
                "spending requests are refused until it is lifted")
        session = self._session_factory()
        try:
            row = session.get(MarketingCampaign, campaign_id)
            if row is None:
                raise NotFoundError(f"campaign {campaign_id} not found")
            business_id = row.business_id
            status = row.status
            ceiling = row.budget_ceiling_minor
            currency = row.currency
            existing_ids = list(row.spend_request_ids or [])
        finally:
            session.close()
        if status not in ("approved", "scheduled", "active", "paused"):
            raise ValidationError(
                f"campaign is {status}; spending can only be prepared "
                "for an approved campaign")
        amount_minor = int(data.get("amount_minor") or 0)
        if amount_minor <= 0:
            raise ValidationError("spend amount must be positive")
        if ceiling is not None:
            spent = self._campaign_spend(business_id, campaign_id)
            if spent["actual_spend_minor"] + amount_minor > ceiling:
                raise ValidationError(
                    "requested amount would exceed the campaign's "
                    "approved budget ceiling; budgets are never "
                    "increased beyond approved limits (§3 rule 16)")
        request = self._financial.budgets.request_spend(
            principal, business_id,
            {"amount": Money(amount_minor, currency),
             "category": str(data.get("category") or "marketing"),
             "purpose": f"P-17 campaign {campaign_id}: "
                        f"{data.get('purpose') or 'marketing spend'}",
             "budget_id": data.get("budget_id"),
             "project_ref": f"{C.CAMPAIGN_PROJECT_REF_PREFIX}{campaign_id}",
             "kind": "expense"})
        session = self._session_factory()
        try:
            row = session.get(MarketingCampaign, campaign_id)
            row.spend_request_ids = existing_ids + [request["id"]]
            session.commit()
        finally:
            session.close()
        self._audit(principal, "growth.campaign_spend_requested", "growth",
                    campaign_id, "allow",
                    "P-07 spending request prepared for campaign",
                    {"spending_request_id": request["id"],
                     "amount_minor": amount_minor})
        return {"campaign_id": campaign_id, "spending_request": request,
                "note": "the request is a P-07 record now; its approval "
                        "and any resulting expense follow P-07's "
                        "workflow — P-17 executes no spend"}

    def campaign_metrics(self, principal: Principal,
                         campaign_id: str) -> dict:
        from .service import campaign_dict
        self._require_reader(principal, "growth.campaign.metrics")
        session = self._session_factory()
        try:
            row = session.get(MarketingCampaign, campaign_id)
            if row is None:
                raise NotFoundError(f"campaign {campaign_id} not found")
            snapshot = campaign_dict(row)
            leads = session.execute(
                select(GrowthLead).where(
                    GrowthLead.campaign_id == campaign_id)).scalars().all()
        finally:
            session.close()
        business_id = snapshot["business_id"]
        spend = self._campaign_spend(business_id, campaign_id)
        metrics = self._revenue_metrics(business_id)
        attributed = 0
        if metrics is not None:
            attributed = int((metrics.get("by_channel_minor") or {}).get(
                snapshot["attribution_channel"]) or 0)
        lead_count = len(leads)
        qualified = sum(1 for lead in leads if lead.stage in (
            "qualified", "sales_conversation", "proposal_sent",
            "negotiation", "converted"))
        converted = sum(1 for lead in leads if lead.stage == "converted")
        cac = scoring.cac(
            spend["actual_spend_minor"] if spend["actual_spend_minor"]
            else None, converted)
        alerts = self._campaign_alerts(snapshot, spend, converted,
                                       cac, lead_count)
        return {
            "campaign": snapshot, "spend": spend,
            "attributed_revenue_minor": attributed,
            "attributed_revenue_label": "ATTRIBUTED verified collected "
            "revenue (P-07, by channel tag) — attribution is not "
            "causation and is not accounting revenue (§22)",
            "contribution_minor": attributed - spend["actual_spend_minor"],
            "leads": lead_count, "qualified_leads": qualified,
            "converted_customers": converted,
            "lead_conversion_rate": (round(converted / lead_count, 4)
                                     if lead_count else None),
            "cac": cac, "alerts": alerts}

    def _campaign_alerts(self, snapshot: dict, spend: dict,
                         converted: int, cac: dict,
                         lead_count: int) -> list[dict]:
        alerts: list[dict] = []
        ceiling = snapshot["budget_ceiling_minor"]
        actual = spend["actual_spend_minor"]
        if actual > 0 and converted == 0:
            alerts.append({
                "kind": "spending_without_conversions",
                "detail": "the campaign has recorded P-07 spend but "
                          "no converted customers"})
        if ceiling is not None and ceiling > 0 and actual >= ceiling:
            alerts.append({
                "kind": "budget_exhausted",
                "detail": "recorded spend has reached the approved "
                          "budget ceiling"})
        max_cac = (snapshot["expected_results"] or {}).get("max_cac_minor")
        if max_cac and cac.get("cac_minor") is not None and \
                cac["cac_minor"] > int(max_cac):
            alerts.append({
                "kind": "high_acquisition_cost",
                "detail": f"CAC {cac['cac_minor']} exceeds the "
                          f"campaign's declared maximum {int(max_cac)} "
                          "(minor units)"})
        if lead_count >= 10 and converted == 0:
            alerts.append({
                "kind": "no_lead_conversion",
                "detail": "10+ leads and zero conversions; review "
                          "targeting and the offer before more spend"})
        return alerts

    def evaluate_auto_pause(self, principal: Principal) -> dict:
        """§7/§24: auto-pause applies ONLY within explicitly
        approved campaign rules at autonomy level 4. Below level 4
        this evaluates alerts and changes nothing."""
        from .service import campaign_dict
        self._require_owner(principal, "growth.campaign.auto_pause")
        settings = self.get_settings()
        if settings["autonomy_level"] < 4:
            return {"status": "not_applied",
                    "reason": "auto-pause requires autonomy level 4 "
                              "(controlled autonomous growth) and "
                              "explicitly approved campaign rules; at "
                              f"level {settings['autonomy_level']} the "
                              "engine alerts and asks instead",
                    "actions": []}
        session = self._session_factory()
        try:
            rows = session.execute(
                select(MarketingCampaign).where(
                    MarketingCampaign.status == "active")).scalars().all()
            candidates = [campaign_dict(r) for r in rows
                          if (r.auto_pause_rules or {}).get("enabled")]
        finally:
            session.close()
        actions = []
        for snapshot in candidates:
            rules = snapshot["auto_pause_rules"] or {}
            spend = self._campaign_spend(snapshot["business_id"],
                                         snapshot["id"])
            session = self._session_factory()
            try:
                converted = session.execute(
                    select(GrowthLead).where(
                        GrowthLead.campaign_id == snapshot["id"],
                        GrowthLead.stage == "converted")).scalars().all()
                converted_count = len(converted)
            finally:
                session.close()
            reason = None
            if rules.get("max_spend_minor") is not None and \
                    spend["actual_spend_minor"] >= int(rules["max_spend_minor"]):
                reason = ("auto-pause rule: recorded spend reached "
                          "the approved max_spend_minor")
            elif rules.get("max_cac_minor") is not None:
                cac = scoring.cac(
                    spend["actual_spend_minor"] or None, converted_count)
                minimum = int(rules.get("min_conversions") or 1)
                if cac.get("cac_minor") is not None and \
                        converted_count >= minimum and \
                        cac["cac_minor"] > int(rules["max_cac_minor"]):
                    reason = ("auto-pause rule: CAC exceeded the "
                              "approved max_cac_minor")
            if reason:
                session = self._session_factory()
                try:
                    row = session.get(MarketingCampaign, snapshot["id"])
                    row.status = "paused"
                    row.paused_reason = reason
                    session.commit()
                finally:
                    session.close()
                actions.append({"campaign_id": snapshot["id"],
                                "action": "paused", "reason": reason})
                self._audit(principal, "growth.campaign_auto_paused",
                            "growth", snapshot["id"], "allow", reason, {})
        return {"status": "evaluated", "actions": actions}

    # ----------------------------------------------------- content (§6)
    def create_content(self, principal: Principal, business_id: str,
                       data: dict) -> dict:
        from .service import content_dict
        self._require_owner(principal, "growth.content.create")
        self._business_or_404(business_id)
        kind = str(data.get("kind") or "other")
        if kind not in C.CONTENT_KINDS:
            raise ValidationError(f"content kind must be one of "
                                  f"{C.CONTENT_KINDS}")
        session = self._session_factory()
        try:
            row = ContentItem(
                business_id=business_id,
                campaign_id=data.get("campaign_id"), kind=kind,
                title=str(data.get("title") or "").strip(),
                brief=dict(data.get("brief") or {}),
                body=str(data.get("body") or ""),
                status="draft",
                review={section: {"status": "pending", "notes": ""}
                        for section in C.REVIEW_SECTIONS},
                created_by=C.actor_of(principal))
            if not row.title:
                raise ValidationError("content title is required")
            session.add(row)
            session.commit()
            session.refresh(row)
            result = content_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.content_created", "growth",
                    result["id"], "allow", "content item drafted",
                    {"business_id": business_id, "kind": kind})
        return result

    def list_content(self, principal: Principal, business_id: str, *,
                     status: str | None = None) -> dict:
        from .service import content_dict
        self._require_reader(principal, "growth.content.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            query = select(ContentItem).where(
                ContentItem.business_id == business_id)
            if status:
                query = query.where(ContentItem.status == status)
            rows = session.execute(
                query.order_by(ContentItem.created_at)).scalars().all()
            return {"items": [content_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()

    def review_content(self, principal: Principal, content_id: str,
                       section: str, status: str,
                       notes: str = "") -> dict:
        from .service import content_dict
        self._require_owner(principal, "growth.content.review")
        if section not in C.REVIEW_SECTIONS:
            raise ValidationError(
                f"review section must be one of {C.REVIEW_SECTIONS}")
        if status not in ("pass", "fail"):
            raise ValidationError("review status must be pass or fail")
        session = self._session_factory()
        try:
            row = session.get(ContentItem, content_id)
            if row is None:
                raise NotFoundError(f"content {content_id} not found")
            if section == "brand_consistency" and status == "pass":
                violations = self._brand_violations(
                    row.business_id, row.body)
                if violations:
                    review = dict(row.review or {})
                    review[section] = {
                        "status": "fail",
                        "notes": "mechanical check: body contains "
                                 f"prohibited claim(s) {violations} "
                                 "from this business's own brand profile"}
                    row.review = review
                    row.status = "in_review"
                    session.commit()
                    session.refresh(row)
                    result = content_dict(row)
                    self._audit(principal, "growth.content_brand_blocked",
                                "growth", content_id, "deny",
                                "brand pass refused: prohibited claim "
                                "present", {"violations": violations})
                    return {**result,
                            "brand_check": "failed_mechanically",
                            "violations": violations}
            review = dict(row.review or {})
            review[section] = {"status": status, "notes": notes}
            row.review = review
            if row.status == "draft":
                row.status = "in_review"
            session.commit()
            session.refresh(row)
            result = content_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.content_reviewed", "growth",
                    content_id, "allow", f"{section}: {status}", {})
        return result

    def _brand_violations(self, business_id: str, body: str) -> list[str]:
        session = self._session_factory()
        try:
            from ..database.models.growth import BrandProfile
            row = session.execute(
                select(BrandProfile).where(
                    BrandProfile.business_id == business_id)
            ).scalar_one_or_none()
            claims = (row.prohibited_claims or []) if row else []
        finally:
            session.close()
        lowered = body.lower()
        return [c for c in claims if c and c.lower() in lowered]

    def approve_content(self, principal: Principal,
                        content_id: str) -> dict:
        from .service import content_dict
        self._require_owner(principal, "growth.content.approve")
        session = self._session_factory()
        try:
            row = session.get(ContentItem, content_id)
            if row is None:
                raise NotFoundError(f"content {content_id} not found")
            review = row.review or {}
            incomplete = [s for s in C.REVIEW_SECTIONS
                          if (review.get(s) or {}).get("status") != "pass"]
            if incomplete:
                raise ValidationError(
                    f"content cannot be approved; review sections not "
                    f"passed: {incomplete} (§6 workflow)")
            row.status = "approved"
            session.commit()
            session.refresh(row)
            result = content_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.content_approved", "growth",
                    content_id, "allow", "content approved after full "
                    "§6 review", {})
        return result

    def schedule_content(self, principal: Principal, content_id: str,
                         scheduled_at: str) -> dict:
        from .service import content_dict
        self._require_owner(principal, "growth.content.schedule")
        session = self._session_factory()
        try:
            row = session.get(ContentItem, content_id)
            if row is None:
                raise NotFoundError(f"content {content_id} not found")
            if row.status != "approved":
                raise ValidationError("only approved content can be "
                                      "scheduled")
            row.scheduled_at = scheduled_at
            row.status = "scheduled"
            session.commit()
            session.refresh(row)
            result = content_dict(row)
        finally:
            session.close()
        return result

    def release_content(self, principal: Principal, content_id: str,
                        external_ref: str) -> dict:
        """Record an owner-attested external publication. The system
        publishes nothing itself — no platform is connected — so a
        release exists only as the owner's attestation with the
        external reference they supply."""
        from .service import content_dict
        self._require_owner(principal, "growth.content.release")
        if not external_ref or not external_ref.strip():
            raise ValidationError(
                "an external reference is required: the system cannot "
                "publish, so a release is recorded only against the "
                "owner's attested reference")
        session = self._session_factory()
        try:
            row = session.get(ContentItem, content_id)
            if row is None:
                raise NotFoundError(f"content {content_id} not found")
            if row.status not in ("approved", "scheduled"):
                raise ValidationError("only approved/scheduled content "
                                      "can be released")
            row.status = "released"
            row.release_ref = external_ref.strip()
            session.commit()
            session.refresh(row)
            result = content_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.content_released", "growth",
                    content_id, "allow",
                    "release recorded against owner-attested external "
                    "reference; the system published nothing",
                    {"release_ref": external_ref})
        return {**result,
                "release_label": "owner-attested external publication; "
                                 "AUTONOMUS posted nothing"}

    # ------------------------------------------------ experiments (§14)
    def create_experiment(self, principal: Principal, business_id: str,
                          data: dict) -> dict:
        from .service import experiment_dict
        self._require_owner(principal, "growth.experiment.create")
        self._business_or_404(business_id)
        hypothesis = str(data.get("hypothesis") or "").strip()
        primary_metric = str(data.get("primary_metric") or "").strip()
        minimum = dict(data.get("minimum_evaluation") or {})
        if not hypothesis or not primary_metric or not minimum.get(
                "min_observations_per_variant"):
            raise ValidationError(
                "an experiment must be pre-declared in full before it "
                "runs: hypothesis, primary metric and minimum "
                "evaluation are all required (Constitution "
                "pre-declaration rule; §14)")
        if int(data.get("duration_days") or 0) <= 0:
            raise ValidationError("duration_days must be positive")
        if int(data.get("budget_ceiling_minor") or 0) < 0:
            raise ValidationError("budget ceiling cannot be negative")
        session = self._session_factory()
        try:
            row = GrowthExperiment(
                business_id=business_id,
                campaign_id=data.get("campaign_id"),
                title=str(data.get("title") or "").strip(),
                hypothesis=hypothesis,
                control_description=str(
                    data.get("control_description") or ""),
                test_description=str(data.get("test_description") or ""),
                primary_metric=primary_metric,
                minimum_evaluation=minimum,
                duration_days=int(data["duration_days"]),
                budget_ceiling_minor=int(
                    data.get("budget_ceiling_minor") or 0),
                max_acceptable_loss_minor=data.get(
                    "max_acceptable_loss_minor"),
                status="draft", created_by=C.actor_of(principal))
            if not row.title:
                raise ValidationError("experiment title is required")
            session.add(row)
            session.commit()
            session.refresh(row)
            result = experiment_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.experiment_created", "growth",
                    result["id"], "allow",
                    "growth experiment pre-declared",
                    {"business_id": business_id})
        return result

    def list_experiments(self, principal: Principal, *,
                         business_id: str | None = None) -> dict:
        from .service import experiment_dict
        self._require_reader(principal, "growth.experiment.list")
        session = self._session_factory()
        try:
            query = select(GrowthExperiment)
            if business_id:
                query = query.where(
                    GrowthExperiment.business_id == business_id)
            rows = session.execute(
                query.order_by(GrowthExperiment.created_at)).scalars().all()
            return {"items": [experiment_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()

    def approve_experiment(self, principal: Principal,
                           experiment_id: str, *,
                           approval_id: str | None = None) -> dict:
        from .service import experiment_dict
        self._require_owner(principal, "growth.experiment.approve")
        session = self._session_factory()
        try:
            row = session.get(GrowthExperiment, experiment_id)
            if row is None:
                raise NotFoundError(
                    f"experiment {experiment_id} not found")
            if row.status != "draft":
                raise ValidationError(
                    f"experiment is {row.status}; only drafts can be "
                    "approved")
            snapshot = experiment_dict(row)
        finally:
            session.close()
        approval = self._owner_approval(
            principal, action="growth.experiment.approve",
            resource=experiment_id,
            parameters={"experiment_id": experiment_id,
                        "business_id": snapshot["business_id"],
                        "budget_ceiling_minor":
                            snapshot["budget_ceiling_minor"]},
            reason="owner approval of P-17 growth experiment (§14)",
            approval_id=approval_id)
        session = self._session_factory()
        try:
            row = session.get(GrowthExperiment, experiment_id)
            row.status = "approved"
            row.approval_id = approval
            session.commit()
            session.refresh(row)
            result = experiment_dict(row)
        finally:
            session.close()
        return result

    def handoff_experiment(self, principal: Principal,
                           experiment_id: str) -> dict:
        """Create the real experiment in P-08 (the P-16 handoff
        pattern): P-08 binds a P-07 budget and enforces the
        mechanical stop-loss. Requires autonomy level ≥ 3."""
        from .service import experiment_dict
        self._require_owner(principal, "growth.experiment.handoff")
        if self.get_settings()["autonomy_level"] < 3:
            raise ValidationError(
                "experiment handoff requires autonomy level 3 "
                "(controlled execution); at lower levels experiments "
                "remain approved designs (§24)")
        session = self._session_factory()
        try:
            row = session.get(GrowthExperiment, experiment_id)
            if row is None:
                raise NotFoundError(
                    f"experiment {experiment_id} not found")
            if row.status != "approved":
                raise ValidationError(
                    "only an approved experiment can be handed to P-08")
            snapshot = experiment_dict(row)
        finally:
            session.close()
        if snapshot["budget_ceiling_minor"] <= 0:
            raise ValidationError(
                "P-08 requires a positive approved budget (it binds a "
                "real P-07 budget as the stop-loss surface); set a "
                "budget ceiling first")
        campaign_objective = ""
        if snapshot["campaign_id"]:
            campaign = self.get_campaign(principal, snapshot["campaign_id"])
            campaign_objective = campaign["objective"]
        declaration = {
            "name": snapshot["title"],
            "hypothesis": snapshot["hypothesis"],
            "problem": campaign_objective or
                       "conversion experiment (P-17 design)",
            "target_customer": "campaign audience (P-17)",
            "expected_outcome": f"improvement in "
                                f"{snapshot['primary_metric']}",
            "success_metric": snapshot["primary_metric"],
            "failure_metric": f"no improvement in "
                              f"{snapshot['primary_metric']}",
            "minimum_evidence": (
                f"{snapshot['minimum_evaluation'].get('min_observations_per_variant')} "
                "observations per variant"),
            "evaluation_schedule": "end of duration",
            "max_duration_days": snapshot["duration_days"],
            "approved_budget_minor": snapshot["budget_ceiling_minor"],
            "max_acceptable_loss_minor":
                snapshot["max_acceptable_loss_minor"]
                if snapshot["max_acceptable_loss_minor"] is not None
                else snapshot["budget_ceiling_minor"],
            "currency": "INR",
        }
        experiment = self._survival.experiments.create_experiment(
            principal, snapshot["business_id"], declaration)
        self._survival.experiments.approve_experiment(
            principal, experiment["id"], {})
        session = self._session_factory()
        try:
            row = session.get(GrowthExperiment, experiment_id)
            row.status = "handed_off"
            row.p08_experiment_id = experiment["id"]
            session.commit()
            session.refresh(row)
            result = experiment_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.experiment_handed_off", "growth",
                    experiment_id, "allow",
                    "handed to P-08; the P-07 budget it created is the "
                    "stop-loss enforcement surface",
                    {"p08_experiment_id": experiment["id"]})
        return result

    def record_observations(self, principal: Principal,
                            experiment_id: str,
                            observations: dict) -> dict:
        from .service import experiment_dict
        self._require_owner(principal, "growth.experiment.observe")
        session = self._session_factory()
        try:
            row = session.get(GrowthExperiment, experiment_id)
            if row is None:
                raise NotFoundError(
                    f"experiment {experiment_id} not found")
            for variant in ("control", "test"):
                entry = dict((observations or {}).get(variant) or {})
                if int(entry.get("successes", 0)) > int(entry.get("n", 0)):
                    raise ValidationError(
                        f"{variant} successes cannot exceed observations")
            row.observations = observations
            session.commit()
            session.refresh(row)
            result = experiment_dict(row)
        finally:
            session.close()
        return result

    def conclude_experiment(self, principal: Principal,
                            experiment_id: str) -> dict:
        """Conclude from the declared observations with §14
        discipline: below the declared minimum the verdict is
        INSUFFICIENT_DATA, whatever the rates say."""
        from .service import experiment_dict
        self._require_owner(principal, "growth.experiment.conclude")
        session = self._session_factory()
        try:
            row = session.get(GrowthExperiment, experiment_id)
            if row is None:
                raise NotFoundError(
                    f"experiment {experiment_id} not found")
            snapshot = experiment_dict(row)
        finally:
            session.close()
        minimum = int((snapshot["minimum_evaluation"] or {}).get(
            "min_observations_per_variant") or 1)
        result = scoring.ab_result(
            (snapshot["observations"] or {}).get("control") or {},
            (snapshot["observations"] or {}).get("test") or {},
            minimum)
        result = {**result, "basis": "DECLARED observations recorded "
                                      "by the owner (§14)",
                  "primary_metric": snapshot["primary_metric"]}
        session = self._session_factory()
        try:
            row = session.get(GrowthExperiment, experiment_id)
            row.result = result
            row.status = "concluded"
            session.commit()
            session.refresh(row)
            final = experiment_dict(row)
        finally:
            session.close()
        if result["verdict"] != "insufficient_data":
            self._feed_memory(
                principal, title=f"Growth experiment concluded: "
                                 f"{snapshot['title']}",
                content=f"verdict {result['verdict']} on declared "
                        f"observations for metric "
                        f"{snapshot['primary_metric']}",
                source_ref=f"p17-experiment:{experiment_id}",
                business_id=snapshot["business_id"],
                outcome_status="declared")
        self._audit(principal, "growth.experiment_concluded", "growth",
                    experiment_id, "allow",
                    f"experiment concluded: {result['verdict']}", {})
        return final
