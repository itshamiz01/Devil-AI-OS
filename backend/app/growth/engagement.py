"""P-17 funnels (§13), SEO (§15), communications (§16) and
partnerships (§18).

Funnel honesty: AUTONOMUS operates no website, so funnel counts are
owner-declared/imported records, labelled DECLARED — except lead,
conversion and verified-revenue figures, which the system counts
itself and reports separately.

SEO honesty: AUTONOMUS has no crawler and no search-console
connection, so SEO records are owner-declared or honestly imported
with mandatory source labels. Nothing is presented as live
third-party data.

Communication discipline: the queue enforces consent, suppression,
the owner's global communication stop and frequency limits. It
never dispatches: no email/SMS/social transport is connected, so a
dispatch attempt lands in the explicit ``dispatch_blocked`` state
with its reason — never a pretend "sent". Every template passes a
deceptive-pattern check before it can exist.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.base import as_utc
from ..database.models.growth import (
    CommunicationMessage, CommunicationTemplate, CrmCustomer,
    FunnelEvent, GrowthLead, LeadSuppression, Partnership, SeoRecord,
)
from ..permissions.models import Principal
from . import constants as C
from . import scoring

DISPATCH_BLOCKED_NOTE = (
    "dispatch blocked: no email/SMS/social transport is configured "
    "(REQUIRES OWNER CONFIGURATION); the system never records a "
    "message as sent or delivered")


class EngagementMixin:
    # ---------------------------------------------------- funnel (§13)
    def record_funnel_event(self, principal: Principal,
                            business_id: str, data: dict) -> dict:
        from .service import funnel_event_dict
        self._require_owner(principal, "growth.funnel.record")
        self._business_or_404(business_id)
        stage = str(data.get("stage") or "")
        if stage not in C.FUNNEL_STAGES:
            raise ValidationError(
                f"funnel stage must be one of {C.FUNNEL_STAGES}")
        source = str(data.get("source") or "")
        if source not in ("declared", "imported"):
            raise ValidationError(
                "funnel counts must be labelled declared|imported — "
                "AUTONOMUS operates no website and measures nothing "
                "itself (§13)")
        if not data.get("period_start") or not data.get("period_end"):
            raise ValidationError(
                "a declared funnel count needs its period "
                "(period_start and period_end); unperioded counts "
                "cannot be compared or audited")
        if int(data.get("count") or 0) <= 0:
            raise ValidationError("funnel count must be positive")
        session = self._session_factory()
        try:
            row = FunnelEvent(
                business_id=business_id,
                campaign_id=data.get("campaign_id"), stage=stage,
                count=int(data["count"]),
                period_start=str(data["period_start"]),
                period_end=str(data["period_end"]), source=source,
                is_fixture=bool(data.get("is_fixture", False)),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = funnel_event_dict(row)
        finally:
            session.close()
        return result

    def funnel_summary(self, principal: Principal, business_id: str, *,
                       campaign_id: str | None = None) -> dict:
        self._require_reader(principal, "growth.funnel.summary")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            query = select(FunnelEvent).where(
                FunnelEvent.business_id == business_id)
            if campaign_id:
                query = query.where(
                    FunnelEvent.campaign_id == campaign_id)
            events = session.execute(query).scalars().all()
            lead_query = select(GrowthLead).where(
                GrowthLead.business_id == business_id)
            if campaign_id:
                lead_query = lead_query.where(
                    GrowthLead.campaign_id == campaign_id)
            leads = session.execute(lead_query).scalars().all()
        finally:
            session.close()
        declared: dict[str, int] = {}
        for event in events:
            declared[event.stage] = declared.get(event.stage, 0) + event.count
        system_counts = {
            "leads_recorded": len(leads),
            "qualified_leads": sum(1 for lead in leads if lead.stage in (
                "qualified", "sales_conversation", "proposal_sent",
                "negotiation", "converted")),
            "converted_customers": sum(
                1 for lead in leads if lead.stage == "converted"),
        }
        ordered = [(stage, declared.get(stage, 0))
                   for stage in C.FUNNEL_STAGES]
        rates = scoring.funnel_rates(ordered)
        return {"business_id": business_id,
                "campaign_id": campaign_id,
                "declared_counts": declared,
                "declared_label": "DECLARED/IMPORTED by the owner — "
                                  "not measured by AUTONOMUS (§13)",
                "system_counts": system_counts,
                "system_label": "counted by the system from its own "
                                "lead records",
                "conversion_rates": rates["steps"],
                "overall_rate": rates["overall_rate"],
                "bottleneck": rates["bottleneck"]}

    # ------------------------------------------------------- SEO (§15)
    def create_seo_record(self, principal: Principal, business_id: str,
                          data: dict) -> dict:
        from .service import seo_dict
        self._require_owner(principal, "growth.seo.create")
        self._business_or_404(business_id)
        kind = str(data.get("kind") or "")
        if kind not in C.SEO_KINDS:
            raise ValidationError(f"SEO record kind must be one of "
                                  f"{C.SEO_KINDS} (§15)")
        source = str(data.get("source") or "")
        if source not in C.SEO_SOURCES:
            raise ValidationError(
                "SEO data must be labelled honestly: "
                f"{list(C.SEO_SOURCES)}; AUTONOMUS has no crawler and "
                "no search-console connection (§15)")
        title = str(data.get("title") or "").strip()
        if not title:
            raise ValidationError("SEO record title is required")
        payload = dict(data.get("data") or {})
        if kind == "keyword_set":
            for field in ("keywords", "search_intent", "competition"):
                if field not in payload:
                    raise ValidationError(
                        f"keyword_set records must include {field} "
                        "(§15)")
        session = self._session_factory()
        try:
            row = SeoRecord(
                business_id=business_id, kind=kind, source=source,
                title=title, data=payload,
                period_start=data.get("period_start"),
                period_end=data.get("period_end"),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = seo_dict(row)
        finally:
            session.close()
        return result

    def seo_summary(self, principal: Principal, business_id: str) -> dict:
        from .service import seo_dict
        self._require_reader(principal, "growth.seo.summary")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            rows = session.execute(
                select(SeoRecord).where(
                    SeoRecord.business_id == business_id)
                .order_by(SeoRecord.created_at)).scalars().all()
            items = [seo_dict(r) for r in rows]
        finally:
            session.close()
        by_kind: dict[str, int] = {}
        for item in items:
            by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1
        audits = [i for i in items if i["kind"] == "technical_audit"]
        delta = None
        if len(audits) >= 2:
            before = (audits[-2]["data"] or {}).get("issue_count")
            after = (audits[-1]["data"] or {}).get("issue_count")
            if isinstance(before, int) and isinstance(after, int):
                delta = {"technical_issues_before": before,
                         "technical_issues_after": after,
                         "change": after - before}
        return {"business_id": business_id, "by_kind": by_kind,
                "records": items, "technical_audit_delta": delta,
                "label": "owner-declared/honestly imported records; "
                         "no live third-party SEO data exists"}

    # ---------------------------------------------- communications (§16)
    def create_template(self, principal: Principal, data: dict) -> dict:
        from .service import template_dict
        self._require_owner(principal, "growth.template.create")
        business_id = data.get("business_id")
        if not business_id:
            raise ValidationError(
                "a template belongs to exactly one business "
                "(business_id is required; brand and consent rules "
                "never mix across businesses)")
        self._business_or_404(business_id)
        kind = str(data.get("kind") or "")
        if kind not in C.COMMUNICATION_KINDS:
            raise ValidationError(
                f"template kind must be one of "
                f"{C.COMMUNICATION_KINDS}")
        body = str(data.get("body") or "")
        subject = str(data.get("subject") or "")
        text = f"{subject} {body}".lower()
        hits = [p for p in C.DECEPTIVE_PATTERNS if p in text]
        if hits:
            self._audit(principal, "growth.template_refused_deceptive",
                        "growth", str(data.get("name") or ""), "deny",
                        "communication template refused: deceptive "
                        "patterns present (§3 rule 12 / §16)",
                        {"patterns": hits})
            raise ValidationError(
                f"template refused: deceptive pattern(s) {hits}. "
                "Marketing never uses fake urgency, false scarcity, "
                "fake testimonials or misleading claims (§16)")
        session = self._session_factory()
        try:
            row = CommunicationTemplate(
                business_id=business_id,
                name=str(data.get("name") or "").strip(),
                kind=kind, subject=subject, body=body, status="draft",
                created_by=C.actor_of(principal))
            if not row.name:
                raise ValidationError("template name is required")
            session.add(row)
            session.commit()
            session.refresh(row)
            result = template_dict(row)
        finally:
            session.close()
        return result

    def queue_message(self, principal: Principal, data: dict) -> dict:
        """Queue a message for a lead or customer. Hard refusals:
        communications stopped (owner control), no valid consent,
        suppressed contact, frequency limit exceeded, or a template
        from another business."""
        from .service import message_dict
        self._require_owner(principal, "growth.communication.queue")
        settings = self.get_settings()
        if settings["communications_stopped"]:
            raise ValidationError(
                "outbound communications are stopped by the owner "
                "(§24); queueing is refused")
        session = self._session_factory()
        try:
            template = session.get(CommunicationTemplate,
                                   data.get("template_id") or "")
            if template is None:
                raise NotFoundError("communication template not found")
            lead = customer = None
            if data.get("lead_id"):
                lead = session.get(GrowthLead, data["lead_id"])
                if lead is None:
                    raise NotFoundError("lead not found")
            if data.get("customer_id"):
                customer = session.get(CrmCustomer, data["customer_id"])
                if customer is None:
                    raise NotFoundError("customer not found")
            if lead is None and customer is None:
                raise ValidationError(
                    "a message needs a lead_id or customer_id recipient")
            recipient = lead if lead is not None else customer
            recipient_kind = "lead" if lead is not None else "customer"
            business_id = recipient.business_id
            if template.business_id != business_id:
                raise ValidationError(
                    "template belongs to a different business than "
                    "the recipient; cross-business messaging is "
                    "refused (isolation, §11/§16)")
            suppression = session.execute(
                select(LeadSuppression).where(
                    LeadSuppression.business_id == business_id,
                    LeadSuppression.dedupe_key == recipient.dedupe_key)
            ).scalar_one_or_none()
            if suppression is not None:
                raise ValidationError(
                    "recipient is on the suppression list and must "
                    "never be contacted again (§16)")
            if recipient.consent_status not in ("granted", "not_required"):
                raise ValidationError(
                    f"recipient consent is "
                    f"{recipient.consent_status}; messages may only "
                    "be queued for contacts with granted (or "
                    "not-required transactional) consent — withdrawn "
                    "and unknown consent are never contacted")
            limit = int(settings["comm_frequency_limit_per_30d"])
            cutoff = datetime.now(timezone.utc).timestamp() - 30 * 86400
            recent = session.execute(
                select(CommunicationMessage).where(
                    CommunicationMessage.business_id == business_id,
                    CommunicationMessage.recipient_kind == recipient_kind,
                    CommunicationMessage.recipient_id == recipient.id,
                    CommunicationMessage.status.in_(
                        ("queued", "dispatch_blocked")))
            ).scalars().all()
            recent_count = sum(
                1 for m in recent
                if m.created_at
                and as_utc(m.created_at).timestamp() >= cutoff)
            if recent_count >= limit:
                raise ValidationError(
                    f"frequency limit reached: {recent_count} queued "
                    f"messages in the last 30 days (limit {limit}); "
                    "anti-spam discipline is enforced (§16)")
            row = CommunicationMessage(
                business_id=business_id, template_id=template.id,
                recipient_kind=recipient_kind,
                recipient_id=recipient.id,
                channel=str(data.get("channel") or "email"),
                status="queued",
                dispatch_note="queued only — " + DISPATCH_BLOCKED_NOTE,
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = message_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.communication_queued", "growth",
                    result["id"], "allow",
                    "message queued (not sent — no transport "
                    "connected)", {"business_id": business_id})
        return result

    def list_messages(self, principal: Principal, business_id: str, *,
                      status: str | None = None) -> dict:
        from .service import message_dict
        self._require_reader(principal, "growth.communication.list")
        session = self._session_factory()
        try:
            query = select(CommunicationMessage).where(
                CommunicationMessage.business_id == business_id)
            if status:
                query = query.where(CommunicationMessage.status == status)
            rows = session.execute(
                query.order_by(CommunicationMessage.created_at)
            ).scalars().all()
            return {"items": [message_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()

    def dispatch_message(self, principal: Principal,
                         message_id: str) -> dict:
        """Attempt dispatch. Always honestly blocked: no transport
        is connected, so the message moves to the explicit
        dispatch_blocked state with its reason. This exists so the
        blocked state is an audited outcome, never a pretend-send."""
        from .service import message_dict
        self._require_owner(principal, "growth.communication.dispatch")
        session = self._session_factory()
        try:
            row = session.get(CommunicationMessage, message_id)
            if row is None:
                raise NotFoundError(f"message {message_id} not found")
            if row.status != "queued":
                raise ValidationError(
                    f"message is {row.status}; only queued messages "
                    "can be dispatched")
            row.status = "dispatch_blocked"
            row.dispatch_note = DISPATCH_BLOCKED_NOTE
            session.commit()
            session.refresh(row)
            result = message_dict(row)
        finally:
            session.close()
        self._audit(principal, "growth.communication_dispatch_blocked",
                    "growth", message_id, "deny", DISPATCH_BLOCKED_NOTE, {})
        return {**result, "dispatched": False,
                "reason": DISPATCH_BLOCKED_NOTE}

    # ---------------------------------------------- partnerships (§18)
    def create_partnership(self, principal: Principal, business_id: str,
                           data: dict) -> dict:
        from .service import partnership_dict, slug_for
        self._require_owner(principal, "growth.partnership.create")
        self._business_or_404(business_id)
        kind = str(data.get("kind") or "referral")
        if kind not in C.PARTNERSHIP_KINDS:
            raise ValidationError(
                f"partnership kind must be one of "
                f"{C.PARTNERSHIP_KINDS}")
        name = str(data.get("partner_name") or "").strip()
        if not name:
            raise ValidationError("partner_name is required")
        evaluation = dict(data.get("evaluation") or {})
        if data.get("terms") is not None:
            evaluation["declared_terms"] = data["terms"]
        session = self._session_factory()
        try:
            base = slug_for(name)
            code = base
            clash = session.execute(
                select(Partnership).where(
                    Partnership.business_id == business_id,
                    Partnership.referral_code == code)
            ).scalar_one_or_none()
            if clash is not None:
                code = f"{base}-{uuid.uuid4().hex[:6]}"
            row = Partnership(
                business_id=business_id, partner_name=name,
                kind=kind, stage="discovered", evaluation=evaluation,
                contact_proposal=str(data.get("contact_proposal") or ""),
                referral_code=code,
                notes=str(data.get("notes") or ""),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = partnership_dict(row)
        finally:
            session.close()
        return result

    def transition_partnership(self, principal: Principal,
                               partnership_id: str, target: str, *,
                               approval_id: str | None = None) -> dict:
        from .service import partnership_dict
        self._require_owner(principal, "growth.partnership.transition")
        if target not in C.PARTNERSHIP_STAGES:
            raise ValidationError(
                f"partnership stage must be one of "
                f"{C.PARTNERSHIP_STAGES}")
        approval = None
        if target in ("agreement_approved", "active"):
            approval = self._owner_approval(
                principal, action="growth.partnership.activate",
                resource=partnership_id,
                parameters={"partnership_id": partnership_id,
                            "target": target},
                reason="owner approval of a partnership stage that "
                       "records an agreement decision (§18: internal "
                       "record only — the system never enters a "
                       "binding agreement)",
                approval_id=approval_id)
        session = self._session_factory()
        try:
            row = session.get(Partnership, partnership_id)
            if row is None:
                raise NotFoundError(
                    f"partnership {partnership_id} not found")
            row.stage = target
            if approval is not None:
                row.approval_id = approval
            session.commit()
            session.refresh(row)
            result = partnership_dict(row)
        finally:
            session.close()
        return result

    def list_partnerships(self, principal: Principal,
                          business_id: str) -> dict:
        from .service import partnership_dict
        self._require_reader(principal, "growth.partnership.list")
        session = self._session_factory()
        try:
            rows = session.execute(
                select(Partnership).where(
                    Partnership.business_id == business_id)
                .order_by(Partnership.created_at)).scalars().all()
            items = [partnership_dict(r) for r in rows]
        finally:
            session.close()
        metrics = self._revenue_metrics(business_id)
        by_channel = (metrics or {}).get("by_channel_minor") or {}
        for item in items:
            attributed = 0
            if item["referral_channel"]:
                attributed = int(
                    by_channel.get(item["referral_channel"]) or 0)
            item["attributed_revenue_minor"] = attributed
            item["attributed_revenue_label"] = (
                "ATTRIBUTED verified collected revenue (P-07, by "
                "partner channel tag) — not guaranteed partner "
                "earnings (§18)")
        return {"items": items, "count": len(items)}
