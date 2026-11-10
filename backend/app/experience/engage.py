"""P-18 engagement: customer communications (§8), feedback
(§10) and proactive-success candidates (§12).

Communications follow the P-17 pattern exactly: they are
queued, checked against consent, the P-17 suppression list and
frequency limits, and dispatch is honestly BLOCKED — no channel
is connected, so nothing is ever sent. Refund promises are not
a communication kind at all: a message can never commit the
business financially.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.base import utcnow
from ..database.models.experience import (
    CxCommunication, CxFeedback, CxFulfillment, CxOnboarding,
)
from ..database.models.growth import LeadSuppression
from ..permissions.models import Principal
from . import constants as C
from .scoring import parse_time


class EngageMixin:
    # ---------------------------------------------------- communications (§8)
    def queue_communication(self, principal: Principal,
                            business_id: str, data: dict) -> dict:
        from .service import communication_dict
        self._require_owner(principal, "experience.communication.queue")
        self._business_or_404(business_id)
        settings = self.get_settings()
        if settings.get("communications_stopped"):
            raise ValidationError(
                "communications are stopped for experience (owner "
                "kill switch in experience settings)")
        kind = str(data.get("kind") or "")
        if kind not in C.COMMUNICATION_KINDS:
            raise ValidationError(
                f"kind must be one of {sorted(C.COMMUNICATION_KINDS)}; "
                "note there is deliberately no refund-promise kind — "
                "messages never commit the business financially")
        requires_approval, essential = C.COMMUNICATION_KINDS[kind]
        channel = str(data.get("channel") or "email")
        if channel not in C.COMMUNICATION_CHANNELS:
            raise ValidationError(
                f"channel must be one of {C.COMMUNICATION_CHANNELS}")
        customer_id = str(data.get("customer_id") or "")
        approval_id = None
        if requires_approval:
            approval_id = self._owner_approval(
                principal,
                action="experience.communication.sensitive",
                resource=f"{customer_id}:{kind}",
                parameters={"business_id": business_id,
                            "customer_id": customer_id, "kind": kind},
                reason="sensitive customer communication requires "
                       "owner approval (§8)",
                approval_id=data.get("approval_id"))
        session = self._session_factory()
        try:
            customer = self._customer_or_404(
                session, customer_id, business_id)
            suppressed = {r.dedupe_key for r in session.execute(
                select(LeadSuppression).where(
                    LeadSuppression.business_id == business_id)
            ).scalars().all()}
            identities = {customer.dedupe_key}
            email = (customer.contact or {}).get("email")
            if email:
                identities.add(str(email).strip().lower())
            if identities & suppressed:
                raise ValidationError(
                    "this customer is on the P-17 suppression list "
                    "for this business; the communication is refused")
            if customer.consent_status == "withdrawn":
                raise ValidationError(
                    "the customer's consent is withdrawn; no "
                    "communication of any kind is queued")
            if customer.consent_status not in ("granted", "not_required"):
                raise ValidationError(
                    f"customer consent status is "
                    f"{customer.consent_status!r}; communications "
                    "require recorded consent (granted) or a "
                    "not_required basis on the P-17 customer record")
            prefs = customer.preferences or {}
            if prefs.get("communication_opt_in") is False \
                    and not essential:
                raise ValidationError(
                    "the customer has opted out of non-essential "
                    "communications on their P-17 record")
            related_ref = data.get("related_ref")
            dedupe_key = f"{customer.id}|{kind}|{related_ref or ''}"
            duplicate = session.execute(
                select(CxCommunication).where(
                    CxCommunication.dedupe_key == dedupe_key,
                    CxCommunication.status.in_(
                        ("queued", "dispatch_blocked")))
            ).scalar_one_or_none()
            if duplicate is not None:
                raise ValidationError(
                    "an equivalent communication is already queued "
                    "for this customer; duplicates are refused")
            window_start = utcnow() - timedelta(days=30)
            recent = session.execute(
                select(CxCommunication).where(
                    CxCommunication.customer_id == customer.id,
                    CxCommunication.created_at >= window_start)
            ).scalars().all()
            limit = int(settings.get("comm_frequency_limit_per_30d", 30))
            if len(recent) >= limit:
                raise ValidationError(
                    f"frequency limit reached ({limit} communications "
                    "in 30 days for this customer)")
            row = CxCommunication(
                business_id=business_id, customer_id=customer.id,
                kind=kind, channel=channel,
                body=str(data.get("body") or ""),
                related_ref=related_ref, dedupe_key=dedupe_key,
                status="queued",
                requires_approval=requires_approval,
                approval_id=approval_id,
                is_fixture=bool(data.get("is_fixture", False)),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = communication_dict(row)
        finally:
            session.close()
        self._audit(principal, "experience.communication_queued",
                    "experience", result["id"], "allow",
                    f"{kind} communication queued (never sent: no "
                    "channel connected)", {"business_id": business_id})
        return result

    def attempt_dispatch(self, principal: Principal,
                         communication_id: str) -> dict:
        """Dispatch is attempted honestly and blocked honestly:
        no support or messaging channel is connected."""
        from .service import communication_dict
        self._require_owner(principal, "experience.communication.dispatch")
        session = self._session_factory()
        try:
            row = session.get(CxCommunication, communication_id)
            if row is None:
                raise NotFoundError("communication not found")
            row.status = "dispatch_blocked"
            row.dispatch_note = C.DISPATCH_BLOCKED_NOTE
            session.commit()
            session.refresh(row)
            result = communication_dict(row)
        finally:
            session.close()
        self._audit(principal, "experience.communication_dispatch_blocked",
                    "experience", communication_id, "allow",
                    "dispatch attempted and blocked: no channel "
                    "connected", {})
        return result

    def list_communications(self, principal: Principal,
                            business_id: str,
                            *, customer_id: str | None = None) -> dict:
        from .service import communication_dict
        self._require_reader(principal, "experience.communication.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            query = select(CxCommunication).where(
                CxCommunication.business_id == business_id)
            if customer_id:
                query = query.where(
                    CxCommunication.customer_id == customer_id)
            rows = session.execute(
                query.order_by(CxCommunication.created_at)).scalars().all()
            return {"items": [communication_dict(r) for r in rows],
                    "count": len(rows),
                    "note": "queued communications are never sent: "
                            "no channel is connected"}
        finally:
            session.close()

    # ---------------------------------------------------- proactive success (§12)
    def proactive_candidates(self, principal: Principal,
                             business_id: str) -> dict:
        """Deterministic candidates for owner review: stalled
        onboarding check-ins and post-delivery feedback requests.
        Candidates are recommendations — nothing is queued or
        sent from here."""
        self._require_reader(principal, "experience.proactive")
        self._business_or_404(business_id)
        settings = self.get_settings()
        now = utcnow()
        candidates: list[dict] = []
        session = self._session_factory()
        try:
            onboardings = session.execute(
                select(CxOnboarding).where(
                    CxOnboarding.business_id == business_id,
                    CxOnboarding.status.notin_(
                        ("completed", "failed")))
            ).scalars().all()
            for ob in onboardings:
                last = parse_time(ob.updated_at) or ob.created_at
                if last and (now - last) > timedelta(
                        hours=int(settings.get(
                            "onboarding_stall_hours", 72))):
                    candidates.append({
                        "candidate_type": "onboarding_check_in",
                        "customer_id": ob.customer_id,
                        "reason": "onboarding has not progressed "
                                  "within the stall threshold",
                        "suggested_kind": "onboarding_instructions",
                        "suggested_success_task_kind":
                            "onboarding_assistance",
                        "subject_ref": ob.id})
            interval = timedelta(days=int(settings.get(
                "feedback_request_interval_days", 14)))
            delivered = session.execute(
                select(CxFulfillment).where(
                    CxFulfillment.business_id == business_id,
                    CxFulfillment.status.in_(
                        ("delivered", "completed")))
            ).scalars().all()
            feedback_rows = session.execute(
                select(CxFeedback).where(
                    CxFeedback.business_id == business_id)
            ).scalars().all()
            last_feedback: dict[str, object] = {}
            for fb in feedback_rows:
                if fb.customer_id and (
                        fb.customer_id not in last_feedback
                        or fb.created_at > last_feedback[fb.customer_id]):
                    last_feedback[fb.customer_id] = fb.created_at
            seen_customers = set()
            for f in delivered:
                if not f.customer_id or f.customer_id in seen_customers:
                    continue
                seen_customers.add(f.customer_id)
                delivered_at = parse_time(f.delivered_at) or f.created_at
                last_fb = last_feedback.get(f.customer_id)
                if delivered_at and (now - delivered_at) > interval \
                        and (last_fb is None
                             or (now - last_fb) > interval):
                    candidates.append({
                        "candidate_type": "feedback_request",
                        "customer_id": f.customer_id,
                        "reason": "delivery recorded more than the "
                                  "feedback interval ago with no "
                                  "recent feedback recorded",
                        "suggested_kind": "feedback_request",
                        "suggested_success_task_kind": "service_review",
                        "subject_ref": f.id})
        finally:
            session.close()
        return {"business_id": business_id, "items": candidates,
                "count": len(candidates),
                "note": "candidates are computed from recorded data "
                        "for owner review; queuing still passes the "
                        "consent, suppression and frequency checks"}

    # ---------------------------------------------------- feedback (§10)
    def record_feedback(self, principal: Principal, business_id: str,
                        data: dict) -> dict:
        from .service import feedback_dict
        self._require_owner(principal, "experience.feedback.record")
        self._business_or_404(business_id)
        kind = str(data.get("kind") or "")
        if kind not in C.FEEDBACK_KINDS:
            raise ValidationError(
                f"kind must be one of {C.FEEDBACK_KINDS}")
        score = data.get("score")
        if score is not None:
            if kind not in C.FEEDBACK_SCORE_RANGES:
                raise ValidationError(
                    f"{kind} feedback carries no score; scores exist "
                    "only for csat, nps and effort")
            lo, hi = C.FEEDBACK_SCORE_RANGES[kind]
            if not lo <= int(score) <= hi:
                raise ValidationError(
                    f"{kind} scores run {lo}..{hi}")
        source = str(data.get("source") or "recorded")
        if source not in C.FEEDBACK_SOURCES:
            raise ValidationError(
                "source must be recorded or owner_declared — "
                "feedback is never invented")
        session = self._session_factory()
        try:
            customer = self._customer_or_404(
                session, str(data.get("customer_id") or ""), business_id)
            row = CxFeedback(
                business_id=business_id, customer_id=customer.id,
                kind=kind,
                score=int(score) if score is not None else None,
                comment=str(data.get("comment") or ""),
                source=source, related_ref=data.get("related_ref"),
                is_fixture=bool(data.get("is_fixture", False)),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = feedback_dict(row)
        finally:
            session.close()
        return result

    def list_feedback(self, principal: Principal, business_id: str,
                      *, customer_id: str | None = None,
                      kind: str | None = None) -> dict:
        from .service import feedback_dict
        self._require_reader(principal, "experience.feedback.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            query = select(CxFeedback).where(
                CxFeedback.business_id == business_id)
            if customer_id:
                query = query.where(CxFeedback.customer_id == customer_id)
            if kind:
                query = query.where(CxFeedback.kind == kind)
            rows = session.execute(
                query.order_by(CxFeedback.created_at)).scalars().all()
            return {"items": [feedback_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()
