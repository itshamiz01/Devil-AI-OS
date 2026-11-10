"""P-18 support: SLA policies (§7), tickets and case management
(§7), the knowledge base (§13) and the knowledge-grounded support
assistant (§6).

The assistant is deterministic and extractive: it retrieves
*approved* knowledge articles by keyword overlap and answers by
quoting them with pinned citations. It has no generative path,
so it cannot invent a policy, a price, a warranty or a date —
when the knowledge base cannot verify an answer it says so and
escalates, and the question is recorded as a ticket so it is
never silently lost.
"""
from __future__ import annotations

from sqlalchemy import select

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.base import utcnow
from ..database.models.experience import (
    CxKnowledgeArticle, CxSlaPolicy, CxSupportAnswer, CxTicket,
    CxTicketMessage,
)
from ..permissions.models import Principal
from . import constants as C
from .scoring import article_match, confidence_for, priority_for, sla_state

_HIGH_IMPACT_TERMS = {"refund", "refunds", "cancel", "cancellation",
                      "legal", "lawsuit", "chargeback", "warranty",
                      "guarantee", "compensation", "sue"}


def policy_for(session, business_id: str, category: str) -> dict | None:
    """The business's SLA policy for a category: exact category
    first, then the business-wide ``*`` policy. None when the
    business configured neither — no target is invented."""
    rows = session.execute(
        select(CxSlaPolicy).where(
            CxSlaPolicy.business_id == business_id)).scalars().all()
    by_category = {r.category: r for r in rows}
    row = by_category.get(category) or by_category.get("*")
    if row is None:
        return None
    return {"id": row.id, "category": row.category,
            "first_response_minutes": row.first_response_minutes,
            "resolution_minutes": row.resolution_minutes,
            "source": row.source}


class SupportMixin:
    # ---------------------------------------------------- SLA policies (§7)
    def upsert_sla_policy(self, principal: Principal, business_id: str,
                          data: dict) -> dict:
        from .service import sla_policy_dict
        self._require_owner(principal, "experience.sla.upsert")
        self._business_or_404(business_id)
        category = str(data.get("category") or "*")
        if category != "*" and category not in C.TICKET_CATEGORIES:
            raise ValidationError(
                f"category must be * or one of {C.TICKET_CATEGORIES}")
        for key in ("first_response_minutes", "resolution_minutes"):
            if data.get(key) is not None and int(data[key]) <= 0:
                raise ValidationError(f"{key} must be positive")
        if data.get("first_response_minutes") is None \
                and data.get("resolution_minutes") is None:
            raise ValidationError(
                "a policy needs at least one target (first response "
                "or resolution minutes)")
        session = self._session_factory()
        try:
            row = session.execute(
                select(CxSlaPolicy).where(
                    CxSlaPolicy.business_id == business_id,
                    CxSlaPolicy.category == category)
            ).scalar_one_or_none()
            if row is None:
                row = CxSlaPolicy(
                    business_id=business_id, category=category,
                    created_by=C.actor_of(principal))
                session.add(row)
            row.first_response_minutes = data.get("first_response_minutes")
            row.resolution_minutes = data.get("resolution_minutes")
            row.source = "owner_configured"
            session.commit()
            session.refresh(row)
            result = sla_policy_dict(row)
        finally:
            session.close()
        self._audit(principal, "experience.sla_policy_upsert",
                    "experience", result["id"], "allow",
                    f"SLA policy configured for category {category}",
                    {"business_id": business_id})
        return result

    def list_sla_policies(self, principal: Principal,
                          business_id: str) -> dict:
        from .service import sla_policy_dict
        self._require_reader(principal, "experience.sla.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            rows = session.execute(
                select(CxSlaPolicy).where(
                    CxSlaPolicy.business_id == business_id)
                .order_by(CxSlaPolicy.category)).scalars().all()
            items = [sla_policy_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "count": len(items),
                "status": "configured" if items else "not_configured",
                "note": "targets exist only where the owner "
                        "configured them; P-18 invents no SLA"}

    def sla_compliance(self, principal: Principal,
                       business_id: str) -> dict:
        self._require_reader(principal, "experience.sla.compliance")
        self._business_or_404(business_id)
        now = utcnow()
        session = self._session_factory()
        try:
            policies = session.execute(
                select(CxSlaPolicy).where(
                    CxSlaPolicy.business_id == business_id)
            ).scalars().all()
            tickets = session.execute(
                select(CxTicket).where(
                    CxTicket.business_id == business_id)
            ).scalars().all()
            states = []
            for t in tickets:
                policy = policy_for(session, business_id, t.category)
                states.append(sla_state(
                    policy, created_at=t.created_at,
                    first_response_at=t.first_response_at,
                    resolved_at=t.resolved_at, now=now)["status"])
        finally:
            session.close()
        if not policies:
            return {"business_id": business_id,
                    "status": "NOT_AVAILABLE",
                    "reason": "no SLA policy is configured for this "
                              "business; compliance is not computed "
                              "against invented targets",
                    "tickets_total": len(tickets)}
        breached = states.count("breached")
        within = states.count("within")
        measured = breached + within
        return {"business_id": business_id, "status": "computed",
                "tickets_total": len(tickets),
                "tickets_measured": measured,
                "breached": breached, "within": within,
                "compliance_percent": (
                    round(within / measured * 100, 1) if measured
                    else None),
                "note": "tickets without an applicable policy are "
                        "counted in tickets_total but never in the "
                        "compliance denominator"}

    # ---------------------------------------------------- tickets (§7)
    def create_ticket(self, principal: Principal, business_id: str,
                      data: dict) -> dict:
        from .service import ticket_dict
        self._require_owner(principal, "experience.ticket.create")
        self._business_or_404(business_id)
        category = str(data.get("category") or "general_inquiry")
        if category not in C.TICKET_CATEGORIES:
            raise ValidationError(
                f"category must be one of {C.TICKET_CATEGORIES}")
        factors = dict(data.get("priority_factors") or {})
        for key, value in factors.items():
            if key not in C.PRIORITY_FACTORS:
                raise ValidationError(f"unknown priority factor: {key}")
            if not 0 <= int(value) <= 3:
                raise ValidationError(
                    "priority factors are scored 0..3")
        priority = priority_for(factors, category)
        session = self._session_factory()
        try:
            customer_id = data.get("customer_id")
            if customer_id:
                self._customer_or_404(session, customer_id, business_id)
            row = CxTicket(
                business_id=business_id, customer_id=customer_id,
                category=category,
                subject=str(data.get("subject") or "Support case"),
                description=str(data.get("description") or ""),
                priority=priority["level"],
                priority_factors={"declared": factors, **priority},
                status="assigned" if data.get("assigned_to") else "new",
                assigned_to=data.get("assigned_to"),
                related_ref=data.get("related_ref"),
                is_fixture=bool(data.get("is_fixture", False)),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = ticket_dict(row)
        finally:
            session.close()
        self._audit(principal, "experience.ticket_created", "experience",
                    result["id"], "allow",
                    f"ticket created ({category}, priority "
                    f"{priority['level']})", {"business_id": business_id})
        return result

    def _ticket_or_404(self, session, ticket_id: str) -> CxTicket:
        row = session.get(CxTicket, ticket_id or "")
        if row is None:
            raise NotFoundError(f"ticket {ticket_id} not found")
        return row

    def get_ticket(self, principal: Principal, ticket_id: str) -> dict:
        from .service import ticket_dict
        self._require_reader(principal, "experience.ticket.get")
        session = self._session_factory()
        try:
            row = self._ticket_or_404(session, ticket_id)
            policy = policy_for(session, row.business_id, row.category)
            result = ticket_dict(row)
            result["sla"] = sla_state(
                policy, created_at=row.created_at,
                first_response_at=row.first_response_at,
                resolved_at=row.resolved_at, now=utcnow())
            messages = session.execute(
                select(CxTicketMessage).where(
                    CxTicketMessage.ticket_id == ticket_id)
                .order_by(CxTicketMessage.created_at)).scalars().all()
            from .service import ticket_message_dict
            result["messages"] = [ticket_message_dict(m) for m in messages]
        finally:
            session.close()
        return result

    def list_tickets(self, principal: Principal, business_id: str,
                     *, status: str | None = None,
                     category: str | None = None,
                     customer_id: str | None = None) -> dict:
        from .service import ticket_dict
        self._require_reader(principal, "experience.ticket.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            query = select(CxTicket).where(
                CxTicket.business_id == business_id)
            if status:
                query = query.where(CxTicket.status == status)
            if category:
                query = query.where(CxTicket.category == category)
            if customer_id:
                query = query.where(CxTicket.customer_id == customer_id)
            rows = session.execute(
                query.order_by(CxTicket.created_at)).scalars().all()
            items = []
            for r in rows:
                item = ticket_dict(r)
                policy = policy_for(session, business_id, r.category)
                item["sla"] = sla_state(
                    policy, created_at=r.created_at,
                    first_response_at=r.first_response_at,
                    resolved_at=r.resolved_at, now=utcnow())
                items.append(item)
            return {"items": items, "count": len(items)}
        finally:
            session.close()

    def transition_ticket(self, principal: Principal, ticket_id: str,
                          status: str) -> dict:
        from .service import ticket_dict
        self._require_owner(principal, "experience.ticket.transition")
        if status not in C.TICKET_STATUSES:
            raise ValidationError(
                f"status must be one of {C.TICKET_STATUSES}")
        session = self._session_factory()
        try:
            row = self._ticket_or_404(session, ticket_id)
            allowed = C.TICKET_TRANSITIONS.get(row.status, ())
            if status not in allowed:
                raise ValidationError(
                    f"ticket is {row.status}; it cannot move to "
                    f"{status} (allowed: {sorted(allowed)})")
            reopening = row.status in ("resolved", "closed") \
                and status == "in_progress"
            row.status = status
            if status == "resolved":
                row.resolved_at = utcnow().isoformat()
            if status == "closed":
                row.closed_at = utcnow().isoformat()
            if reopening:
                row.reopened_count += 1
                row.resolved_at = None
                row.closed_at = None
            session.commit()
            session.refresh(row)
            result = ticket_dict(row)
        finally:
            session.close()
        self._audit(principal, "experience.ticket_transition",
                    "experience", ticket_id, "allow",
                    f"ticket -> {status}"
                    + (" (reopened)" if reopening else ""), {})
        return result

    def assign_ticket(self, principal: Principal, ticket_id: str,
                      assigned_to: str) -> dict:
        from .service import ticket_dict
        self._require_owner(principal, "experience.ticket.assign")
        session = self._session_factory()
        try:
            row = self._ticket_or_404(session, ticket_id)
            row.assigned_to = str(assigned_to)
            if row.status in ("new", "classified"):
                row.status = "assigned"
            session.commit()
            session.refresh(row)
            result = ticket_dict(row)
        finally:
            session.close()
        return result

    def add_ticket_message(self, principal: Principal, ticket_id: str,
                           data: dict) -> dict:
        from .service import ticket_message_dict
        self._require_owner(principal, "experience.ticket.message")
        author_kind = str(data.get("author_kind") or "owner")
        if author_kind not in ("customer", "owner", "agent", "system"):
            raise ValidationError(
                "author_kind must be customer, owner, agent or system")
        session = self._session_factory()
        try:
            ticket = self._ticket_or_404(session, ticket_id)
            row = CxTicketMessage(
                business_id=ticket.business_id, ticket_id=ticket_id,
                author_kind=author_kind,
                body=str(data.get("body") or ""),
                internal=bool(data.get("internal", False)),
                created_by=C.actor_of(principal))
            session.add(row)
            if author_kind in ("owner", "agent") \
                    and not row.internal \
                    and ticket.first_response_at is None:
                ticket.first_response_at = utcnow().isoformat()
            session.commit()
            session.refresh(row)
            result = ticket_message_dict(row)
        finally:
            session.close()
        return result

    def escalate_ticket(self, principal: Principal, ticket_id: str,
                        data: dict | None = None) -> dict:
        """Escalation is a P-12 workflow (DRAFT, structured steps,
        idempotency key per ticket+level) on the P-13 precedent —
        P-18 builds no queue of its own."""
        from .service import ticket_dict
        self._require_owner(principal, "experience.ticket.escalate")
        data = data or {}
        session = self._session_factory()
        try:
            row = self._ticket_or_404(session, ticket_id)
            if row.status in ("resolved", "closed"):
                raise ValidationError(
                    "a resolved or closed ticket cannot escalate; "
                    "reopen it first")
            business_id = row.business_id
            subject = row.subject
            level = row.escalation_level + 1
        finally:
            session.close()
        workflow = self._operations.create_workflow(principal, {
            "business_id": business_id,
            "name": f"P-18 escalation L{level}: {subject}"[:300],
            "objective": "Human review and resolution of an "
                         "escalated support case",
            "origin": "p18_experience",
            "idempotency_key": f"p18-escalation:{ticket_id}:{level}",
            "definition": {"steps": [{
                "step_key": "escalation_review",
                "name": "Review escalated support case",
                "kind": "task_handler",
                "action_class": "business.read",
                "substrate": {
                    "handler": "core.echo_check",
                    "payload": {"message": "escalated support case "
                                           "awaiting human review",
                                "ticket_id": ticket_id,
                                "level": level,
                                "reason": str(data.get("reason") or "")}},
                "acceptance_criteria": {"task_status": "completed"},
            }]},
        })
        session = self._session_factory()
        try:
            row = self._ticket_or_404(session, ticket_id)
            row.status = "escalated"
            row.escalation_level = level
            row.escalation_workflow_id = workflow["id"]
            session.commit()
            session.refresh(row)
            result = {**ticket_dict(row),
                      "workflow_id": workflow["id"]}
        finally:
            session.close()
        self._audit(principal, "experience.ticket_escalated",
                    "experience", ticket_id, "allow",
                    f"ticket escalated to level {level}; P-12 "
                    f"workflow {workflow['id']} created",
                    {"business_id": business_id})
        return result

    # ---------------------------------------------------- knowledge base (§13)
    def create_article(self, principal: Principal, business_id: str,
                       data: dict) -> dict:
        from .service import article_dict
        self._require_owner(principal, "experience.kb.create")
        self._business_or_404(business_id)
        if not str(data.get("title") or "").strip():
            raise ValidationError("an article needs a title")
        if not str(data.get("content") or "").strip():
            raise ValidationError("an article needs content")
        session = self._session_factory()
        try:
            row = CxKnowledgeArticle(
                business_id=business_id,
                title=str(data["title"]), content=str(data["content"]),
                category=str(data.get("category") or "general"),
                source=str(data.get("source") or ""),
                approval_status="draft", review_status="current",
                is_fixture=bool(data.get("is_fixture", False)),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = article_dict(row)
        finally:
            session.close()
        return result

    def update_article(self, principal: Principal, article_id: str,
                       data: dict) -> dict:
        from .service import article_dict
        self._require_owner(principal, "experience.kb.update")
        session = self._session_factory()
        try:
            row = session.get(CxKnowledgeArticle, article_id)
            if row is None:
                raise NotFoundError("article not found")
            changed = False
            for key in ("title", "content", "category", "source"):
                if key in data and data[key] is not None:
                    setattr(row, key, str(data[key]))
                    changed = True
            if changed:
                row.version += 1
                row.review_status = "current"
                if row.approval_status == "approved":
                    # Policy-sensitive content is never silently
                    # republished: an edit returns it to draft.
                    row.approval_status = "draft"
                    row.approved_by = None
            session.commit()
            session.refresh(row)
            result = article_dict(row)
        finally:
            session.close()
        return result

    def approve_article(self, principal: Principal, article_id: str) -> dict:
        from .service import article_dict
        self._require_owner(principal, "experience.kb.approve")
        session = self._session_factory()
        try:
            row = session.get(CxKnowledgeArticle, article_id)
            if row is None:
                raise NotFoundError("article not found")
            if row.approval_status == "retired":
                raise ValidationError("a retired article cannot be "
                                      "approved; create a new one")
            row.approval_status = "approved"
            row.approved_by = C.actor_of(principal)
            session.commit()
            session.refresh(row)
            result = article_dict(row)
        finally:
            session.close()
        self._audit(principal, "experience.kb_approved", "experience",
                    article_id, "allow",
                    "knowledge article approved for grounded answers",
                    {})
        return result

    def retire_article(self, principal: Principal, article_id: str) -> dict:
        from .service import article_dict
        self._require_owner(principal, "experience.kb.retire")
        session = self._session_factory()
        try:
            row = session.get(CxKnowledgeArticle, article_id)
            if row is None:
                raise NotFoundError("article not found")
            row.approval_status = "retired"
            session.commit()
            session.refresh(row)
            result = article_dict(row)
        finally:
            session.close()
        return result

    def set_article_review(self, principal: Principal, article_id: str,
                           review_status: str) -> dict:
        from .service import article_dict
        self._require_owner(principal, "experience.kb.review")
        if review_status not in ("current", "stale"):
            raise ValidationError("review_status must be current or stale")
        session = self._session_factory()
        try:
            row = session.get(CxKnowledgeArticle, article_id)
            if row is None:
                raise NotFoundError("article not found")
            row.review_status = review_status
            session.commit()
            session.refresh(row)
            result = article_dict(row)
        finally:
            session.close()
        return result

    def list_articles(self, principal: Principal, business_id: str,
                      *, approval_status: str | None = None,
                      category: str | None = None) -> dict:
        from .service import article_dict
        self._require_reader(principal, "experience.kb.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            query = select(CxKnowledgeArticle).where(
                CxKnowledgeArticle.business_id == business_id)
            if approval_status:
                query = query.where(
                    CxKnowledgeArticle.approval_status == approval_status)
            if category:
                query = query.where(
                    CxKnowledgeArticle.category == category)
            rows = session.execute(
                query.order_by(CxKnowledgeArticle.created_at)
            ).scalars().all()
            return {"items": [article_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()

    def kb_health(self, principal: Principal, business_id: str) -> dict:
        self._require_reader(principal, "experience.kb.health")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            rows = session.execute(
                select(CxKnowledgeArticle).where(
                    CxKnowledgeArticle.business_id == business_id)
            ).scalars().all()
        finally:
            session.close()
        approved = [r for r in rows if r.approval_status == "approved"]
        return {
            "business_id": business_id, "total": len(rows),
            "approved": len(approved),
            "draft": sum(1 for r in rows
                         if r.approval_status == "draft"),
            "retired": sum(1 for r in rows
                           if r.approval_status == "retired"),
            "stale": [r.id for r in rows if r.review_status == "stale"],
            "grounding_available": bool(approved),
            "note": "only approved articles ground support answers; "
                    "a business with no approved article gets "
                    "insufficient_information answers and escalations",
        }

    # ---------------------------------------------------- support assistant (§6)
    def ask_support(self, principal: Principal, business_id: str,
                    data: dict) -> dict:
        """Answer a customer question from approved knowledge only.

        verified: the answer quotes the best-matching approved
        article (id + version pinned). partially_verified: quoted
        but flagged for human review. insufficient_information /
        human_review_required: no answer is invented — the honest
        cannot-verify text is returned, the case escalates, and a
        ticket records the question so it is never lost."""
        from .service import answer_dict, article_dict
        self._require_owner(principal, "experience.support.ask")
        self._business_or_404(business_id)
        question = str(data.get("question") or "").strip()
        if not question:
            raise ValidationError("a question is required")
        session = self._session_factory()
        try:
            customer_id = data.get("customer_id")
            if customer_id:
                self._customer_or_404(session, customer_id, business_id)
            articles = session.execute(
                select(CxKnowledgeArticle).where(
                    CxKnowledgeArticle.business_id == business_id,
                    CxKnowledgeArticle.approval_status == "approved",
                    CxKnowledgeArticle.review_status == "current")
            ).scalars().all()
            article_rows = {r.id: r for r in articles}
            ranked = article_match(
                question, [article_dict(r) for r in articles])
            best = ranked[0] if ranked else None
            confidence = confidence_for(best["score"] if best else None)
            from .scoring import tokens
            high_impact = bool(tokens(question) & _HIGH_IMPACT_TERMS)
            escalated = False
            refs: list[dict] = []
            if best and confidence in ("verified", "partially_verified"):
                article = article_rows[best["article_id"]]
                excerpt = (article.content or "")[:600]
                answer_text = (
                    f"According to the approved knowledge article "
                    f"\"{article.title}\" (version {article.version}): "
                    f"{excerpt}")
                refs = [{"article_id": article.id,
                         "version": article.version,
                         "title": article.title,
                         "match_score": best["score"]}]
                if confidence == "partially_verified":
                    escalated = True
                    answer_text += (
                        " [This answer is partially verified and has "
                        "been flagged for human review.]")
                if high_impact:
                    confidence = "human_review_required"
                    escalated = True
                    answer_text += (
                        " [This question touches a high-impact topic "
                        "and requires human review before any "
                        "commitment is made.]")
            else:
                confidence = "insufficient_information" \
                    if not high_impact else "human_review_required"
                escalated = True
                answer_text = (
                    "I cannot verify an answer to this question from "
                    "the business's approved knowledge base, so I "
                    "will not guess. The question has been recorded "
                    "and routed to a human for review.")
            row = CxSupportAnswer(
                business_id=business_id, customer_id=customer_id,
                ticket_id=data.get("ticket_id"),
                question=question, answer_text=answer_text,
                article_refs=refs, confidence_class=confidence,
                escalated=escalated,
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = answer_dict(row)
        finally:
            session.close()
        ticket_id = data.get("ticket_id")
        if escalated and not ticket_id:
            ticket = self.create_ticket(principal, business_id, {
                "customer_id": customer_id,
                "category": str(data.get("category")
                                or "general_inquiry"),
                "subject": f"Support question requiring review: "
                           f"{question[:120]}",
                "description": question,
                "priority_factors": {"customer_impact": 1},
                "is_fixture": bool(data.get("is_fixture", False)),
            })
            ticket_id = ticket["id"]
            session = self._session_factory()
            try:
                row = session.get(CxSupportAnswer, result["id"])
                row.ticket_id = ticket_id
                session.commit()
                result["ticket_id"] = ticket_id
            finally:
                session.close()
        result["ticket_id"] = ticket_id
        self._audit(principal, "experience.support_answer", "experience",
                    result["id"], "allow",
                    f"grounded answer: {confidence}"
                    + ("; escalated" if escalated else ""),
                    {"business_id": business_id})
        return result

    def list_answers(self, principal: Principal, business_id: str) -> dict:
        from .service import answer_dict
        self._require_reader(principal, "experience.support.answers")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            rows = session.execute(
                select(CxSupportAnswer).where(
                    CxSupportAnswer.business_id == business_id)
                .order_by(CxSupportAnswer.created_at)).scalars().all()
            return {"items": [answer_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()
