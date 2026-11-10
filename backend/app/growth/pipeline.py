"""P-17 lead generation and scoring (§8/§9), the sales pipeline
(§10) and the CRM layer (§11: customer profiles, interaction
history, lifecycle segmentation, payment and service history from
P-07).

Lead discipline: sources come from a closed authorised set.
Purchased lists, scraped contacts and other prohibited sources are
refused outright — the system never buys, scrapes or imports them.
Every lead's consent status is recorded before any communication
may be queued; suppressed and withdrawn contacts are never
contacted again. Cross-business isolation: one business's leads and
customers are never visible to, or reusable for, another business.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.base import as_utc, utcnow
from ..database.models.growth import (
    CrmCustomer, GrowthInteraction, GrowthLead, LeadSuppression,
    SalesOpportunity,
)
from ..permissions.models import Principal
from . import constants as C
from . import scoring


class PipelineMixin:
    # -------------------------------------------------------- leads (§8)
    def create_lead(self, principal: Principal, business_id: str,
                    data: dict, *, campaign_id: str | None = None) -> dict:
        from .service import dedupe_key_for, lead_dict
        self._require_owner(principal, "growth.lead.create")
        self._business_or_404(business_id)
        source = str(data.get("source") or "")
        if source in C.FORBIDDEN_LEAD_SOURCES:
            self._audit(principal, "growth.lead_source_refused",
                        "growth", source, "deny",
                        "lead source is prohibited: the system never "
                        "purchases, scrapes or brokers contact data "
                        "(§3 rules 9/10)", {"business_id": business_id})
            raise ValidationError(
                f"lead source {source!r} is prohibited: the system "
                "never purchases, scrapes or brokers contact data (§3 "
                "rules 9/10). The attempt is audited.")
        if source not in C.LEAD_SOURCES:
            raise ValidationError(
                f"lead source must be one of {sorted(C.LEAD_SOURCES)}; "
                f"got {source!r}")
        consent = str(data.get("consent_status") or "")
        if consent not in C.CONSENT_STATUSES:
            raise ValidationError(
                f"consent_status is required at lead creation and "
                f"must be one of {C.CONSENT_STATUSES} — consent is "
                "recorded before any communication may be queued "
                "(§8/§16)")
        contact = dict(data.get("contact") or {})
        if not (contact.get("email") or contact.get("phone")
                or contact.get("name")):
            raise ValidationError("lead contact needs at least an "
                                  "email, phone or name")
        dedupe_key = dedupe_key_for(contact)
        session = self._session_factory()
        try:
            suppression = session.execute(
                select(LeadSuppression).where(
                    LeadSuppression.business_id == business_id,
                    LeadSuppression.dedupe_key == dedupe_key)
            ).scalar_one_or_none()
            if suppression is not None:
                self._audit(principal, "growth.lead_suppressed_refused",
                            "growth", dedupe_key, "deny",
                            "lead creation refused: contact is on the "
                            "suppression list (never contacted again)",
                            {"reason": suppression.reason})
                raise ValidationError(
                    "this contact is on the suppression list for this "
                    "business and must never be contacted again; the "
                    "lead was not created")
            existing = session.execute(
                select(GrowthLead).where(
                    GrowthLead.business_id == business_id,
                    GrowthLead.dedupe_key == dedupe_key)
            ).scalar_one_or_none()
            if existing is not None:
                result = lead_dict(existing)
                result["deduplicated"] = True
                return result
            row = GrowthLead(
                business_id=business_id,
                campaign_id=campaign_id or data.get("campaign_id"),
                dedupe_key=dedupe_key, source_kind=source,
                source_channel=str(data.get("source_channel") or ""),
                contact=contact, consent_status=consent,
                lawful_basis=str(data.get("lawful_basis") or ""),
                segment=str(data.get("segment") or ""),
                interest=str(data.get("interest") or ""),
                stage="new",
                is_fixture=bool(data.get("is_fixture", False)),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = {**lead_dict(row), "deduplicated": False}
        finally:
            session.close()
        self._audit(principal, "growth.lead_created", "growth",
                    result["id"], "allow", "lead recorded from an "
                    "authorised source", {"business_id": business_id,
                                           "source": source})
        return result

    def import_leads(self, principal: Principal, business_id: str,
                     leads: list[dict], *,
                     campaign_id: str | None = None) -> dict:
        """Batch import with per-row honesty: refused rows are
        reported with their reason, never silently dropped (§8:
        import permission and abuse prevention are explicit)."""
        self._require_owner(principal, "growth.lead.import")
        created, deduplicated, refused = [], [], []
        for idx, item in enumerate(leads or []):
            try:
                result = self.create_lead(
                    principal, business_id, item,
                    campaign_id=campaign_id)
                (deduplicated if result.get("deduplicated")
                 else created).append(result)
            except ValidationError as exc:
                refused.append({"index": idx, "reason": str(exc)})
        return {"created": created, "deduplicated": deduplicated,
                "refused": refused,
                "counts": {"created": len(created),
                           "deduplicated": len(deduplicated),
                           "refused": len(refused)}}

    def list_leads(self, principal: Principal, business_id: str, *,
                   stage: str | None = None) -> dict:
        from .service import lead_dict
        self._require_reader(principal, "growth.lead.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            query = select(GrowthLead).where(
                GrowthLead.business_id == business_id)
            if stage:
                query = query.where(GrowthLead.stage == stage)
            rows = session.execute(
                query.order_by(GrowthLead.created_at)).scalars().all()
            return {"items": [lead_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()

    def score_lead(self, principal: Principal, lead_id: str,
                   factor_scores: dict) -> dict:
        """§9: closed factor vocabulary only (product interest,
        requirements fit, budget compatibility, business fit,
        engagement, purchase intent, decision authority, timing).
        Sensitive personal attributes are not in the vocabulary at
        all, and a score is a prioritisation estimate — never a
        purchase probability."""
        from .service import lead_dict
        self._require_owner(principal, "growth.lead.score")
        unknown = [k for k in factor_scores
                   if k not in C.LEAD_SCORE_FACTORS]
        if unknown:
            raise ValidationError(
                f"unknown lead factor(s): {unknown}; valid factors "
                f"are {list(C.LEAD_SCORE_FACTORS)} (§9 closed "
                "vocabulary)")
        scored = scoring.lead_score(
            dict(factor_scores), self.get_settings()["lead_score_weights"])
        session = self._session_factory()
        try:
            row = session.get(GrowthLead, lead_id)
            if row is None:
                raise NotFoundError(f"lead {lead_id} not found")
            row.score_factors = dict(factor_scores)
            row.score = scored["score"]
            row.score_band = scored["band"]
            session.commit()
            session.refresh(row)
            result = {**lead_dict(row), "scoring": scored}
        finally:
            session.close()
        return result

    def transition_lead(self, principal: Principal, lead_id: str,
                        target: str) -> dict:
        from .service import lead_dict
        self._require_owner(principal, "growth.lead.transition")
        if target not in C.LEAD_STAGES:
            raise ValidationError(
                f"lead stage must be one of {C.LEAD_STAGES}")
        session = self._session_factory()
        try:
            row = session.get(GrowthLead, lead_id)
            if row is None:
                raise NotFoundError(f"lead {lead_id} not found")
            row.stage = target
            session.commit()
            session.refresh(row)
            result = lead_dict(row)
        finally:
            session.close()
        return result

    def set_consent(self, principal: Principal, lead_id: str,
                    consent_status: str,
                    lawful_basis: str | None = None) -> dict:
        from .service import lead_dict
        self._require_owner(principal, "growth.lead.consent")
        if consent_status not in C.CONSENT_STATUSES:
            raise ValidationError(
                f"consent_status must be one of {C.CONSENT_STATUSES}")
        session = self._session_factory()
        try:
            row = session.get(GrowthLead, lead_id)
            if row is None:
                raise NotFoundError(f"lead {lead_id} not found")
            row.consent_status = consent_status
            if lawful_basis is not None:
                row.lawful_basis = lawful_basis
            session.commit()
            session.refresh(row)
            result = lead_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.lead_consent_updated", "growth",
                    lead_id, "allow", f"consent -> {consent_status}", {})
        return result

    def suppress_lead(self, principal: Principal, lead_id: str,
                      reason: str) -> dict:
        """Suppress = never contacted again. Sets the lead's consent
        to withdrawn and writes the suppression row that blocks
        re-creation and queueing."""
        from .service import suppression_dict
        self._require_owner(principal, "growth.lead.suppress")
        if reason not in C.SUPPRESSION_REASONS:
            raise ValidationError(
                f"suppression reason must be one of "
                f"{C.SUPPRESSION_REASONS}")
        session = self._session_factory()
        try:
            lead = session.get(GrowthLead, lead_id)
            if lead is None:
                raise NotFoundError(f"lead {lead_id} not found")
            lead.consent_status = "withdrawn"
            existing = session.execute(
                select(LeadSuppression).where(
                    LeadSuppression.business_id == lead.business_id,
                    LeadSuppression.dedupe_key == lead.dedupe_key)
            ).scalar_one_or_none()
            if existing is None:
                row = LeadSuppression(
                    business_id=lead.business_id,
                    dedupe_key=lead.dedupe_key, reason=reason,
                    source="owner suppression in P-17",
                    created_by=C.actor_of(principal))
                session.add(row)
                session.commit()
                session.refresh(row)
                result = suppression_dict(row)
            else:
                session.commit()
                result = suppression_dict(existing)
        finally:
            session.close()
        self._audit(principal, "growth.lead_suppressed", "growth",
                    lead_id, "allow",
                    f"suppressed ({reason}); never contacted again", {})
        return result

    def list_suppressions(self, principal: Principal,
                          business_id: str) -> dict:
        from .service import suppression_dict
        self._require_reader(principal, "growth.suppression.list")
        session = self._session_factory()
        try:
            rows = session.execute(
                select(LeadSuppression).where(
                    LeadSuppression.business_id == business_id)
                .order_by(LeadSuppression.created_at)).scalars().all()
            return {"items": [suppression_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()

    # ------------------------------------------- sales pipeline (§10)
    def create_opportunity(self, principal: Principal, business_id: str,
                           data: dict) -> dict:
        from .service import sales_opportunity_dict
        self._require_owner(principal, "growth.opportunity.create")
        self._business_or_404(business_id)
        stage = str(data.get("stage") or "new")
        if stage not in C.SALES_STAGES:
            raise ValidationError(
                f"sales stage must be one of {C.SALES_STAGES}")
        value = data.get("estimated_value_minor")
        if value is not None and int(value) < 0:
            raise ValidationError("estimated value cannot be negative")
        probability = data.get("probability")
        probability = (int(probability) if probability is not None
                       else C.STAGE_DEFAULT_PROBABILITY[stage])
        if probability < 0 or probability > 100:
            raise ValidationError("probability must be within 0..100 "
                                  "(a declared percent estimate)")
        session = self._session_factory()
        try:
            row = SalesOpportunity(
                business_id=business_id, lead_id=data.get("lead_id"),
                customer_id=data.get("customer_id"),
                product=str(data.get("product") or ""),
                stage=stage, probability=probability,
                estimated_value_minor=(int(value)
                                       if value is not None else None),
                currency=str(data.get("currency") or "INR"),
                expected_close_date=data.get("expected_close_date"),
                next_action=str(data.get("next_action") or ""),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = sales_opportunity_dict(row)
        finally:
            session.close()
        return result

    def transition_opportunity(self, principal: Principal,
                               opportunity_id: str, target: str,
                               *, lost_reason: str | None = None,
                               probability: int | None = None) -> dict:
        from .service import sales_opportunity_dict
        self._require_owner(principal, "growth.opportunity.transition")
        if target not in C.SALES_STAGES:
            raise ValidationError(
                f"sales stage must be one of {C.SALES_STAGES}")
        if target == "closed_lost" and not (lost_reason or "").strip():
            raise ValidationError(
                "a closed-lost opportunity must carry a lost_reason "
                "(§10)")
        if probability is not None and not 0 <= probability <= 100:
            raise ValidationError("probability must be within 0..100")
        session = self._session_factory()
        try:
            row = session.get(SalesOpportunity, opportunity_id)
            if row is None:
                raise NotFoundError(
                    f"opportunity {opportunity_id} not found")
            row.stage = target
            if lost_reason is not None:
                row.lost_reason = lost_reason
            if probability is not None:
                row.probability = int(probability)
            session.commit()
            session.refresh(row)
            result = sales_opportunity_dict(row)
        finally:
            session.close()
        return result

    def pipeline_summary(self, principal: Principal,
                         business_id: str) -> dict:
        from .service import sales_opportunity_dict
        self._require_reader(principal, "growth.opportunity.summary")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            rows = session.execute(
                select(SalesOpportunity).where(
                    SalesOpportunity.business_id == business_id)
            ).scalars().all()
            items = [sales_opportunity_dict(r) for r in rows]
        finally:
            session.close()
        by_stage: dict[str, dict] = {}
        weighted = 0
        for item in items:
            bucket = by_stage.setdefault(
                item["stage"], {"count": 0,
                                "estimated_value_minor": 0,
                                "weighted_value_minor": 0})
            bucket["count"] += 1
            bucket["estimated_value_minor"] += (
                item["estimated_value_minor"] or 0)
            bucket["weighted_value_minor"] += (
                item["weighted_value_minor"] or 0)
            weighted += item["weighted_value_minor"] or 0
        return {"business_id": business_id, "by_stage": by_stage,
                "weighted_pipeline_minor": weighted,
                "label": "pipeline values are ESTIMATES (§10) — "
                         "probability-weighted forecasts, never "
                         "revenue; collected revenue exists only in "
                         "P-07"}

    # -------------------------------------------------------- CRM (§11)
    def convert_lead(self, principal: Principal, lead_id: str) -> dict:
        """Convert a converted lead into a CRM customer of the same
        business. Refuses withdrawn contacts and leads that have not
        reached the converted stage. No copy path exists between
        businesses — conversion stays inside the lead's business."""
        from .service import customer_dict
        self._require_owner(principal, "growth.customer.convert")
        session = self._session_factory()
        try:
            lead = session.get(GrowthLead, lead_id)
            if lead is None:
                raise NotFoundError(f"lead {lead_id} not found")
            if lead.stage != "converted":
                raise ValidationError(
                    f"lead is {lead.stage}; only converted leads become "
                    "customers")
            if lead.consent_status == "withdrawn":
                raise ValidationError(
                    "a withdrawn/suppressed contact cannot be "
                    "converted")
            existing = session.execute(
                select(CrmCustomer).where(
                    CrmCustomer.business_id == lead.business_id,
                    CrmCustomer.dedupe_key == lead.dedupe_key)
            ).scalar_one_or_none()
            if existing is not None:
                return {**customer_dict(existing), "already_existed": True}
            ref_base = (lead.contact.get("email")
                        or lead.dedupe_key).strip().lower()
            display_name = (lead.contact.get("name")
                            or lead.contact.get("email")
                            or lead.dedupe_key)
            row = CrmCustomer(
                business_id=lead.business_id,
                display_name=str(display_name),
                contact=dict(lead.contact),
                dedupe_key=lead.dedupe_key,
                p07_customer_ref=f"p17-cust-{ref_base}",
                segment=lead.segment,
                lifecycle_stage="onboarding",
                consent_status=lead.consent_status,
                acquisition_campaign_id=lead.campaign_id,
                acquisition_channel=lead.source_channel
                or lead.source_kind,
                source_lead_id=lead.id,
                created_by=C.actor_of(principal))
            session.add(row)
            session.flush()
            lead.converted_customer_id = row.id
            session.commit()
            session.refresh(row)
            result = {**customer_dict(row), "already_existed": False}
        finally:
            session.close()
        self._audit(principal, "growth.customer_converted", "growth",
                    result["id"], "allow",
                    "converted lead became a CRM customer",
                    {"lead_id": lead_id})
        return result

    def create_customer(self, principal: Principal, business_id: str,
                        data: dict) -> dict:
        from .service import customer_dict, dedupe_key_for
        self._require_owner(principal, "growth.customer.create")
        self._business_or_404(business_id)
        contact = dict(data.get("contact") or {})
        if not (contact.get("email") or contact.get("phone")
                or contact.get("name")):
            raise ValidationError("customer contact needs at least an "
                                  "email, phone or name")
        lifecycle = str(data.get("lifecycle_stage") or "onboarding")
        if lifecycle not in C.CUSTOMER_LIFECYCLES:
            raise ValidationError(
                f"lifecycle_stage must be one of "
                f"{C.CUSTOMER_LIFECYCLES}")
        consent = str(data.get("consent_status") or "unknown")
        if consent not in C.CONSENT_STATUSES:
            raise ValidationError(
                f"consent_status must be one of {C.CONSENT_STATUSES}")
        dedupe_key = data.get("dedupe_key") or dedupe_key_for(contact)
        session = self._session_factory()
        try:
            existing = session.execute(
                select(CrmCustomer).where(
                    CrmCustomer.business_id == business_id,
                    CrmCustomer.dedupe_key == dedupe_key)
            ).scalar_one_or_none()
            if existing is not None:
                return {**customer_dict(existing), "already_existed": True}
            display_name = (data.get("display_name")
                            or contact.get("name")
                            or contact.get("email") or dedupe_key)
            row = CrmCustomer(
                business_id=business_id,
                display_name=str(display_name), contact=contact,
                dedupe_key=dedupe_key,
                p07_customer_ref=data.get("p07_customer_ref")
                or f"p17-cust-{dedupe_key}",
                segment=str(data.get("segment") or ""),
                lifecycle_stage=lifecycle, consent_status=consent,
                preferences=dict(data.get("preferences") or {}),
                acquisition_campaign_id=data.get(
                    "acquisition_campaign_id"),
                acquisition_channel=str(
                    data.get("acquisition_channel") or ""),
                source_lead_id=data.get("lead_id"),
                is_fixture=bool(data.get("is_fixture", False)),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = {**customer_dict(row), "already_existed": False}
        finally:
            session.close()
        return result

    def list_customers(self, principal: Principal, business_id: str,
                       *, lifecycle_stage: str | None = None) -> dict:
        from .service import customer_dict
        self._require_reader(principal, "growth.customer.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            query = select(CrmCustomer).where(
                CrmCustomer.business_id == business_id)
            if lifecycle_stage:
                query = query.where(
                    CrmCustomer.lifecycle_stage == lifecycle_stage)
            rows = session.execute(
                query.order_by(CrmCustomer.created_at)).scalars().all()
            return {"items": [customer_dict(r) for r in rows],
                    "count": len(rows),
                    "isolation": "customers belong to one business "
                                 "only; nothing here is shared or "
                                 "reused across businesses (§11)"}
        finally:
            session.close()

    def customer_detail(self, principal: Principal,
                        customer_id: str) -> dict:
        from .service import (customer_dict, interaction_dict,
                              sales_opportunity_dict)
        self._require_reader(principal, "growth.customer.detail")
        session = self._session_factory()
        try:
            row = session.get(CrmCustomer, customer_id)
            if row is None:
                raise NotFoundError(f"customer {customer_id} not found")
            snapshot = customer_dict(row)
            interactions = session.execute(
                select(GrowthInteraction).where(
                    GrowthInteraction.subject_kind == "customer",
                    GrowthInteraction.subject_id == customer_id)
                .order_by(GrowthInteraction.created_at)).scalars().all()
            opps = session.execute(
                select(SalesOpportunity).where(
                    SalesOpportunity.customer_id == customer_id)
            ).scalars().all()
            interaction_items = [interaction_dict(i) for i in interactions]
            opp_items = [sales_opportunity_dict(o) for o in opps]
        finally:
            session.close()
        purchases = self.customer_purchases(
            principal, snapshot["business_id"],
            snapshot["p07_customer_ref"])
        ltv = scoring.ltv(
            actual_collected_minor=purchases["total_minor"],
            contribution_margin_ratio=None, expected_periods=None)
        return {"customer": snapshot,
                "interaction_history": interaction_items,
                "opportunities": opp_items,
                "purchases": purchases,
                "ltv": ltv,
                "labels": {"purchases": "VERIFIED collected revenue "
                                        "(P-07, by customer ref)",
                           "ltv": "actual collected is a fact over "
                                  "recorded P-07 history; a projected "
                                  "LTV exists only as an ESTIMATE with "
                                  "stated margin and period "
                                  "assumptions (§17)"}}

    def customer_purchases(self, principal: Principal, business_id: str,
                           p07_customer_ref: str | None) -> dict:
        """Payment history from P-07 revenue records by customer
        ref. Duplicated nowhere: this is a live read."""
        self._require_reader(principal, "growth.customer.purchases")
        if not p07_customer_ref:
            return {"business_id": business_id, "customer_ref": None,
                    "source": "P-07 revenue records (verified collected)",
                    "count": 0, "total_minor": 0, "records": [],
                    "note": "no P-07 customer reference is recorded "
                            "for this customer"}
        records, _total = self._financial.revenue.list_revenue(
            business_id, limit=1000)
        records = [r for r in records
                   if r.get("customer_ref") == p07_customer_ref
                   and r.get("verification_status") == "verified"
                   and r.get("classification") in ("collected",
                                                   "recognized")]
        total = sum(int(r["amount_minor"]) for r in records)
        return {"business_id": business_id,
                "customer_ref": p07_customer_ref,
                "source": "P-07 revenue records (verified collected)",
                "count": len(records), "total_minor": total,
                "records": records}

    def record_interaction(self, principal: Principal,
                           customer_id: str, data: dict) -> dict:
        from .service import interaction_dict
        self._require_owner(principal, "growth.interaction.create")
        kind = str(data.get("kind") or "note")
        if kind not in C.INTERACTION_KINDS:
            raise ValidationError(
                f"interaction kind must be one of "
                f"{C.INTERACTION_KINDS}")
        session = self._session_factory()
        try:
            customer = session.get(CrmCustomer, customer_id)
            if customer is None:
                raise NotFoundError(f"customer {customer_id} not found")
            row = GrowthInteraction(
                business_id=customer.business_id,
                subject_kind="customer", subject_id=customer_id,
                kind=kind, summary=str(data.get("summary") or ""),
                outcome=str(data.get("outcome") or ""),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = interaction_dict(row)
        finally:
            session.close()
        return result

    def recompute_customer_health(self, principal: Principal,
                                  customer_id: str) -> dict:
        """Health from recency (P-07 purchases + recorded
        interactions), open support issues and lifecycle — every
        deduction explained by scoring.customer_health, never an
        opaque number."""
        from .service import customer_dict
        self._require_owner(principal, "growth.customer.health")
        session = self._session_factory()
        try:
            row = session.get(CrmCustomer, customer_id)
            if row is None:
                raise NotFoundError(f"customer {customer_id} not found")
            snapshot = customer_dict(row)
            business_id = row.business_id
            p07_ref = row.p07_customer_ref
            interactions = session.execute(
                select(GrowthInteraction).where(
                    GrowthInteraction.subject_kind == "customer",
                    GrowthInteraction.subject_id == customer_id)
            ).scalars().all()
            open_support = sum(
                1 for i in interactions
                if i.kind == "support" and not i.outcome)
            last_interaction = max(
                (i.created_at for i in interactions if i.created_at),
                default=None)
        finally:
            session.close()
        purchases = self.customer_purchases(principal, business_id, p07_ref)
        last_purchase_date = None
        if purchases["records"]:
            last_purchase_date = max(
                r.get("transaction_date") or ""
                for r in purchases["records"]) or None
        now = utcnow()
        days_since_interaction = (
            (now - as_utc(last_interaction)).days
            if last_interaction is not None else None)
        days_since_purchase = None
        if last_purchase_date:
            try:
                purchased_on = date.fromisoformat(last_purchase_date)
                days_since_purchase = (
                    datetime.now(timezone.utc).date() - purchased_on).days
            except ValueError:
                days_since_purchase = None
        health = scoring.customer_health(
            days_since_interaction=days_since_interaction,
            days_since_purchase=days_since_purchase,
            open_support_issues=open_support,
            lifecycle_stage=snapshot["lifecycle_stage"])
        session = self._session_factory()
        try:
            row = session.get(CrmCustomer, customer_id)
            row.health_score = health["score"]
            row.health_factors = {"band": health["band"],
                                  "factors": health["factors"],
                                  "note": health["note"]}
            row.health_computed_at = now.isoformat()
            session.commit()
            session.refresh(row)
            result = customer_dict(row)
        finally:
            session.close()
        return {**result, "health": health}
