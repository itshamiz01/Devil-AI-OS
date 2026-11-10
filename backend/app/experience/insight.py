"""P-18 insight: experience metrics (§16), customer health
(§12), quality assurance (§9), complaint & resolution handling
with P-07-executed financial remedies (§11), success tasks
(§12), continuous-improvement insights (§19) and the
customer/business overviews (§17).

Money never moves here: a refund recommendation executes only
through P-07 `create_refund` against verified collected
revenue, and a goodwill credit only as a P-07 spending request
that follows P-07's own approval workflow. P-18 stores only the
ids P-07 returns — never an amount.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.experience import (
    CxFeedback, CxFulfillment, CxHealthSnapshot, CxIncident,
    CxOnboarding, CxQualityReview, CxResolution, CxSuccessTask,
    CxTicket, CxTicketMessage,
)
from ..financial.money import Money
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from .scoring import (
    csat as csat_score, effort as effort_score, health as health_score,
    nps as nps_score, parse_time, quality_score, rate,
)

_IMPROVEMENT_MAP = {
    "product": "Fix the recurring product cause and add a "
               "regression check before the next release.",
    "service": "Review the service step involved and sample more "
               "interactions for quality review.",
    "process": "Simplify the process step where these cases "
               "accumulate and add earlier detection.",
    "fulfillment_provider": "Escalate to the fulfilment provider "
                            "and track their remediation.",
    "technical": "Fix the technical cause and verify the recovery "
                 "path end to end.",
    "communication": "Close the communication gap: earlier "
                     "proactive updates at the affected stage.",
    "human_error": "Add a checklist or second pair of eyes at the "
                   "step where the error recurs.",
    "policy_ambiguity": "Clarify the policy wording involved and "
                        "publish it to the knowledge base.",
}

_OPEN_TICKET_STATUSES = ("new", "classified", "assigned",
                         "in_progress", "waiting_for_customer",
                         "escalated")


class InsightMixin:
    # ---------------------------------------------------- metrics (§16)
    def experience_metrics(self, principal: Principal,
                           business_id: str) -> dict:
        self._require_reader(principal, "experience.metrics")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            feedback = session.execute(
                select(CxFeedback).where(
                    CxFeedback.business_id == business_id)
            ).scalars().all()
            tickets = session.execute(
                select(CxTicket).where(
                    CxTicket.business_id == business_id)
            ).scalars().all()
            messages = session.execute(
                select(CxTicketMessage).where(
                    CxTicketMessage.business_id == business_id)
            ).scalars().all()
            onboardings = session.execute(
                select(CxOnboarding).where(
                    CxOnboarding.business_id == business_id)
            ).scalars().all()
        finally:
            session.close()
        by_kind: dict[str, list[int]] = {}
        for fb in feedback:
            if fb.score is not None:
                by_kind.setdefault(fb.kind, []).append(fb.score)
        resolved = [t for t in tickets
                    if t.status in ("resolved", "closed")]
        first_response_minutes = []
        resolution_minutes = []
        for t in tickets:
            created = parse_time(t.created_at)
            fr = parse_time(t.first_response_at)
            if fr and created:
                first_response_minutes.append(
                    (fr - created).total_seconds() / 60)
            res = parse_time(t.resolved_at)
            if res and created:
                resolution_minutes.append(
                    (res - created).total_seconds() / 60)
        responses_by_ticket: dict[str, int] = {}
        for m in messages:
            if not m.internal and m.author_kind in ("owner", "agent"):
                responses_by_ticket[m.ticket_id] = \
                    responses_by_ticket.get(m.ticket_id, 0) + 1
        fcr = [t for t in resolved
               if t.reopened_count == 0
               and responses_by_ticket.get(t.id, 0) <= 1]
        complaints = [t for t in tickets
                      if t.category == "service_quality_complaint"]
        revenue_rows, _total = self._financial.revenue.list_revenue(
            business_id, limit=500)
        per_customer_category: dict[tuple, int] = {}
        for t in tickets:
            if t.customer_id:
                key = (t.customer_id, t.category)
                per_customer_category[key] = \
                    per_customer_category.get(key, 0) + 1
        repeat_tickets = sum(
            n - 1 for n in per_customer_category.values() if n > 1)
        completed_ob = [o for o in onboardings
                        if o.status == "completed"]
        decided_ob = [o for o in onboardings
                      if o.status in ("completed", "failed")]

        def avg(values):
            return (round(sum(values) / len(values), 1)
                    if values else None)

        return {
            "business_id": business_id,
            "basis": "recorded P-18 data only; every figure carries "
                     "its sample size and is never presented as "
                     "more than it is",
            "csat": csat_score(by_kind.get("csat", [])),
            "nps": nps_score(by_kind.get("nps", [])),
            "customer_effort": effort_score(by_kind.get("effort", [])),
            "complaint_rate": (
                rate(len(complaints), len(revenue_rows),
                     "service-quality complaints per verified P-07 "
                     "revenue record (percent)")
                if revenue_rows else
                {"status": "NOT_AVAILABLE",
                 "reason": "no verified P-07 revenue records to "
                           "rate complaints against"}),
            "repeat_issue_rate": rate(
                repeat_tickets, len(tickets),
                "repeat same-category tickets per ticket"),
            "first_contact_resolution": rate(
                len(fcr), len(resolved),
                "resolved without reopen and with at most one "
                "recorded response"),
            "reopen_rate": rate(
                sum(1 for t in tickets if t.reopened_count > 0),
                len(resolved), "reopened per resolved ticket"),
            "avg_first_response_minutes": {
                "value": avg(first_response_minutes),
                "samples": len(first_response_minutes)},
            "avg_resolution_minutes": {
                "value": avg(resolution_minutes),
                "samples": len(resolution_minutes)},
            "sla": self.sla_compliance(principal, business_id),
            "onboarding_completion": rate(
                len(completed_ob), len(decided_ob),
                "completed per decided onboarding"),
            "tickets_total": len(tickets),
            "feedback_total": len(feedback),
        }

    # ---------------------------------------------------- health (§12)
    def compute_health(self, principal: Principal, business_id: str,
                       customer_id: str, data: dict | None = None) -> dict:
        from .service import health_dict
        self._require_owner(principal, "experience.health.compute")
        self._business_or_404(business_id)
        data = data or {}
        session = self._session_factory()
        try:
            self._customer_or_404(session, customer_id, business_id)
            tickets = session.execute(
                select(CxTicket).where(
                    CxTicket.business_id == business_id,
                    CxTicket.customer_id == customer_id)
            ).scalars().all()
            open_tickets = [t for t in tickets
                            if t.status in _OPEN_TICKET_STATUSES]
            fulfils = session.execute(
                select(CxFulfillment).where(
                    CxFulfillment.business_id == business_id,
                    CxFulfillment.customer_id == customer_id)
            ).scalars().all()
            obs = session.execute(
                select(CxOnboarding).where(
                    CxOnboarding.business_id == business_id,
                    CxOnboarding.customer_id == customer_id)
            ).scalars().all()
            low_scores = [fb.score for fb in session.execute(
                select(CxFeedback).where(
                    CxFeedback.business_id == business_id,
                    CxFeedback.customer_id == customer_id,
                    CxFeedback.kind == "csat")
            ).scalars().all()
                if fb.score is not None and fb.score <= 2]
            signals = {
                "open_critical_tickets": sum(
                    1 for t in open_tickets if t.priority == "critical"),
                "open_high_tickets": sum(
                    1 for t in open_tickets if t.priority == "high"),
                "open_tickets_other": sum(
                    1 for t in open_tickets
                    if t.priority in ("low", "medium")),
                "reopened_tickets": sum(
                    1 for t in tickets if t.reopened_count > 0),
                "fulfillment_problems": sum(
                    1 for f in fulfils
                    if f.status in ("failed", "returned")),
                "onboarding_incomplete": any(
                    o.status in ("not_started", "in_progress",
                                 "stalled") for o in obs),
                "low_feedback_count": len(low_scores),
            }
            evidence = {
                "open_ticket_ids": [t.id for t in open_tickets],
                "fulfillment_problem_ids": [
                    f.id for f in fulfils
                    if f.status in ("failed", "returned")],
                "onboarding_statuses": [o.status for o in obs],
                "low_csat_scores": low_scores,
                "signals_measured": signals,
            }
            for declared in data.get("declared_signals") or []:
                # Owner-declared context is recorded as evidence
                # only; it never moves the computed score.
                evidence.setdefault("owner_declared", []).append({
                    "factor": str(declared.get("factor") or ""),
                    "note": str(declared.get("evidence") or "")})
            settings = self.get_settings()
            result = health_score(
                signals,
                weights=settings.get("health_weights") or {})
            row = CxHealthSnapshot(
                business_id=business_id, customer_id=customer_id,
                classification=result["classification"],
                score=result["score"],
                factors=result["factors"],
                evidence=evidence,
                confidence=result["confidence"],
                recommended_action=result["recommended_action"],
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            snapshot = health_dict(row)
        finally:
            session.close()
        return snapshot

    def latest_health(self, principal: Principal, business_id: str,
                      customer_id: str) -> dict:
        from .service import health_dict
        self._require_reader(principal, "experience.health.latest")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            self._customer_or_404(session, customer_id, business_id)
            row = session.execute(
                select(CxHealthSnapshot).where(
                    CxHealthSnapshot.business_id == business_id,
                    CxHealthSnapshot.customer_id == customer_id)
                .order_by(CxHealthSnapshot.created_at.desc())
            ).scalars().first()
            if row is None:
                return {"customer_id": customer_id,
                        "classification": "insufficient_data",
                        "status": "INSUFFICIENT_DATA",
                        "reason": "no health snapshot has been "
                                  "computed for this customer yet"}
            return health_dict(row)
        finally:
            session.close()

    def health_overview(self, principal: Principal,
                        business_id: str) -> dict:
        from .service import health_dict
        self._require_reader(principal, "experience.health.overview")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            rows = session.execute(
                select(CxHealthSnapshot).where(
                    CxHealthSnapshot.business_id == business_id)
                .order_by(CxHealthSnapshot.created_at)
            ).scalars().all()
        finally:
            session.close()
        latest: dict[str, dict] = {}
        for r in rows:
            latest[r.customer_id] = health_dict(r)
        distribution: dict[str, int] = {}
        for snap in latest.values():
            distribution[snap["classification"]] = \
                distribution.get(snap["classification"], 0) + 1
        return {"business_id": business_id,
                "customers_with_snapshots": len(latest),
                "distribution": distribution,
                "latest": latest,
                "note": "classifications come from recorded signals "
                        "only; customers without snapshots are not "
                        "classified at all"}

    # ---------------------------------------------------- quality (§9)
    def create_quality_review(self, principal: Principal,
                              business_id: str, data: dict) -> dict:
        from .service import quality_review_dict
        self._require_owner(principal, "experience.quality.create")
        self._business_or_404(business_id)
        dimensions = dict(data.get("dimensions") or {})
        if not dimensions:
            raise ValidationError("a review scores at least one "
                                  "quality dimension")
        for key, value in dimensions.items():
            if key not in C.QUALITY_DIMENSIONS:
                raise ValidationError(
                    f"unknown quality dimension: {key}")
            if not 0 <= float(value) <= 5:
                raise ValidationError("dimension scores run 0..5")
        session = self._session_factory()
        try:
            ticket = session.get(CxTicket, str(data.get("ticket_id")
                                               or ""))
            if ticket is None or ticket.business_id != business_id:
                raise NotFoundError(
                    "quality reviews sample a recorded ticket of "
                    "this business; ticket not found")
            row = CxQualityReview(
                business_id=business_id, ticket_id=ticket.id,
                dimensions=dimensions,
                method=str(data.get("method")
                           or "manual_sample_review"),
                notes=str(data.get("notes") or ""),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = quality_review_dict(row)
        finally:
            session.close()
        return result

    def list_quality_reviews(self, principal: Principal,
                             business_id: str) -> dict:
        from .service import quality_review_dict
        self._require_reader(principal, "experience.quality.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            rows = session.execute(
                select(CxQualityReview).where(
                    CxQualityReview.business_id == business_id)
                .order_by(CxQualityReview.created_at)).scalars().all()
            return {"items": [quality_review_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()

    def quality_summary(self, principal: Principal,
                        business_id: str) -> dict:
        self._require_reader(principal, "experience.quality.summary")
        listing = self.list_quality_reviews(principal, business_id)
        items = listing["items"]
        if not items:
            return {"business_id": business_id,
                    "status": "INSUFFICIENT_DATA",
                    "reason": "no quality reviews recorded"}
        values = [i["aggregate"]["value"] for i in items
                  if i["aggregate"]["value"] is not None]
        per_dimension: dict[str, list[float]] = {}
        for i in items:
            for key, value in i["dimensions"].items():
                per_dimension.setdefault(key, []).append(float(value))
        return {"business_id": business_id, "status": "computed",
                "reviews": len(items),
                "average_score": (round(sum(values) / len(values), 2)
                                  if values else None),
                "dimension_averages": {
                    k: round(sum(v) / len(v), 2)
                    for k, v in per_dimension.items()},
                "basis": "recorded QA sample reviews of support "
                         "cases; sampling is the reviewer's, not "
                         "a census, and a review score is never "
                         "customer satisfaction"}

    # ---------------------------------------------------- resolutions (§11)
    def create_resolution(self, principal: Principal,
                          business_id: str, data: dict) -> dict:
        from .service import resolution_dict
        self._require_owner(principal, "experience.resolution.create")
        self._business_or_404(business_id)
        problem_class = str(data.get("problem_class") or "general")
        if problem_class not in C.PROBLEM_CLASSES:
            raise ValidationError(
                f"problem_class must be one of {C.PROBLEM_CLASSES}")
        group = data.get("root_cause_group")
        if group is not None and group not in C.ROOT_CAUSE_GROUPS:
            raise ValidationError(
                f"root_cause_group must be one of "
                f"{C.ROOT_CAUSE_GROUPS}")
        action = str(data.get("action_kind") or "")
        if action not in C.RESOLUTION_ACTIONS:
            raise ValidationError(
                f"action_kind must be one of {C.RESOLUTION_ACTIONS}")
        if not str(data.get("rationale") or "").strip():
            raise ValidationError(
                "a resolution recommendation carries a rationale "
                "the customer could be shown")
        basis = str(data.get("basis") or "na")
        if basis not in ("full", "partial", "na"):
            raise ValidationError("basis must be full, partial or na")
        session = self._session_factory()
        try:
            customer = self._customer_or_404(
                session, str(data.get("customer_id") or ""), business_id)
            if data.get("ticket_id"):
                ticket = session.get(CxTicket, data["ticket_id"])
                if ticket is None or ticket.business_id != business_id:
                    raise NotFoundError("ticket not found in business")
            if data.get("incident_id"):
                incident = session.get(CxIncident, data["incident_id"])
                if incident is None \
                        or incident.business_id != business_id:
                    raise NotFoundError("incident not found in business")
            row = CxResolution(
                business_id=business_id, customer_id=customer.id,
                ticket_id=data.get("ticket_id"),
                incident_id=data.get("incident_id"),
                problem_class=problem_class,
                root_cause_group=group,
                action_kind=action, status="recommended",
                basis=basis, revenue_id=data.get("revenue_id"),
                rationale=str(data["rationale"]),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = resolution_dict(row)
        finally:
            session.close()
        return result

    def _resolution_or_404(self, session, resolution_id: str):
        row = session.get(CxResolution, resolution_id or "")
        if row is None:
            raise NotFoundError("resolution not found")
        return row

    def approve_resolution(self, principal: Principal,
                           resolution_id: str, data: dict) -> dict:
        from .service import resolution_dict
        self._require_owner(principal, "experience.resolution.approve")
        session = self._session_factory()
        try:
            row = self._resolution_or_404(session, resolution_id)
            if row.status != "recommended":
                raise ValidationError(
                    f"resolution is {row.status}; only recommended "
                    "resolutions can be approved")
            business_id = row.business_id
            action_kind = row.action_kind
        finally:
            session.close()
        approval_id = self._owner_approval(
            principal,
            action="experience.resolution.approve",
            resource=resolution_id,
            parameters={"resolution_id": resolution_id,
                        "action_kind": action_kind},
            reason="owner approval of a service-recovery "
                   "recommendation (§11)",
            approval_id=(data or {}).get("approval_id"))
        session = self._session_factory()
        try:
            row = self._resolution_or_404(session, resolution_id)
            row.status = "approved"
            row.approval_id = approval_id
            session.commit()
            session.refresh(row)
            result = resolution_dict(row)
        finally:
            session.close()
        self._audit(principal, "experience.resolution_approved",
                    "experience", resolution_id, "allow",
                    "resolution recommendation approved by the owner",
                    {"business_id": business_id})
        return result

    def execute_resolution(self, principal: Principal,
                           resolution_id: str, data: dict) -> dict:
        """Financial actions execute ONLY through P-07: refunds
        via `create_refund` against the case's verified P-07
        revenue record (amount supplied by the owner here, capped
        by P-07), goodwill via a P-07 spending request that then
        follows P-07's own approval. P-18 stores only the ids
        P-07 returns."""
        from .service import resolution_dict
        self._require_owner(principal, "experience.resolution.execute")
        data = data or {}
        session = self._session_factory()
        try:
            row = self._resolution_or_404(session, resolution_id)
            if row.status != "approved":
                raise ValidationError(
                    f"resolution is {row.status}; only approved "
                    "resolutions execute")
            action = row.action_kind
            business_id = row.business_id
            rationale = row.rationale
            stored_revenue_id = row.revenue_id
        finally:
            session.close()
        refund_id = None
        spending_request_id = None
        note = "non-financial resolution carried out by the owner"
        if action == "refund_recommendation":
            revenue_id = str(data.get("revenue_id")
                             or stored_revenue_id or "")
            amount_minor = int(data.get("amount_minor") or 0)
            if not revenue_id or amount_minor <= 0:
                raise ValidationError(
                    "executing a refund needs the P-07 revenue_id "
                    "(on the case or supplied here) and a positive "
                    "amount_minor supplied by the owner; P-18 holds "
                    "no amounts of its own")
            currency = str(data.get("currency") or "INR")
            refund = self._financial.revenue.create_refund(
                principal, revenue_id,
                {"amount": Money(amount_minor, currency),
                 "refund_date": date.today().isoformat(),
                 "reason": rationale,
                 "source": "p18_resolution"})
            refund_id = refund["id"]
            note = ("refund executed as P-07 refund "
                    f"{refund_id} against verified revenue; P-18 "
                    "moved no money")
        elif action == "goodwill_recommendation":
            amount_minor = int(data.get("amount_minor") or 0)
            if amount_minor <= 0:
                raise ValidationError(
                    "a goodwill credit needs a positive amount_minor "
                    "supplied by the owner")
            currency = str(data.get("currency") or "INR")
            request = self._financial.budgets.request_spend(
                principal, business_id,
                {"amount": Money(amount_minor, currency),
                 "category": "customer_goodwill",
                 "purpose": f"P-18 goodwill resolution "
                            f"{resolution_id}: {rationale}"[:500],
                 "project_ref": f"p18-resolution:{resolution_id}",
                 "kind": "expense"})
            spending_request_id = request["id"]
            note = ("goodwill prepared as P-07 spending request "
                    f"{spending_request_id} (status "
                    f"{request.get('status')}); it completes only "
                    "through P-07's own approval workflow — P-18 "
                    "moved no money")
        session = self._session_factory()
        try:
            row = self._resolution_or_404(session, resolution_id)
            row.status = "executed"
            row.p07_refund_id = refund_id
            row.p07_spending_request_id = spending_request_id
            session.commit()
            session.refresh(row)
            result = resolution_dict(row)
        finally:
            session.close()
        result["execution_note"] = note
        self._audit(principal, "experience.resolution_executed",
                    "experience", resolution_id, "allow", note,
                    {"business_id": business_id,
                     "p07_refund_id": refund_id,
                     "p07_spending_request_id": spending_request_id})
        return result

    def verify_resolution(self, principal: Principal,
                          resolution_id: str, data: dict) -> dict:
        from .service import resolution_dict
        self._require_owner(principal, "experience.resolution.verify")
        data = data or {}
        session = self._session_factory()
        try:
            row = self._resolution_or_404(session, resolution_id)
            if row.status != "executed":
                raise ValidationError(
                    f"resolution is {row.status}; only executed "
                    "resolutions can be verified")
            row.outcome = str(data.get("outcome") or "")
            row.verified = bool(data.get("verified", True))
            row.status = "verified" if row.verified else "closed"
            business_id = row.business_id
            group = row.root_cause_group
            action = row.action_kind
            outcome = row.outcome
            session.commit()
            session.refresh(row)
            result = resolution_dict(row)
        finally:
            session.close()
        self._feed_memory(
            principal,
            title=f"Resolution pattern: {group or 'ungrouped'}",
            content=(f"A {group or 'ungrouped'} case was resolved "
                     f"via {action}. Recorded outcome: "
                     f"{outcome or 'not stated'}."),
            source_ref=f"p18:resolution:{resolution_id}",
            business_id=business_id)
        self._audit(principal, "experience.resolution_verified",
                    "experience", resolution_id, "allow",
                    "resolution outcome recorded; pattern fed to "
                    "P-09 memory", {"business_id": business_id})
        return result

    def list_resolutions(self, principal: Principal,
                         business_id: str) -> dict:
        from .service import resolution_dict
        self._require_reader(principal, "experience.resolution.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            rows = session.execute(
                select(CxResolution).where(
                    CxResolution.business_id == business_id)
                .order_by(CxResolution.created_at)).scalars().all()
            return {"items": [resolution_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()

    # ---------------------------------------------------- success tasks (§12)
    def create_success_task(self, principal: Principal,
                            business_id: str, data: dict) -> dict:
        from .service import success_task_dict
        self._require_owner(principal, "experience.success_task.create")
        self._business_or_404(business_id)
        kind = str(data.get("kind") or "")
        if kind not in C.SUCCESS_TASK_KINDS:
            raise ValidationError(
                f"kind must be one of {C.SUCCESS_TASK_KINDS}")
        if not str(data.get("title") or "").strip():
            raise ValidationError("a success task needs a title")
        source = str(data.get("source") or "owner")
        if source not in C.SUCCESS_TASK_SOURCES:
            raise ValidationError(
                f"source must be one of {C.SUCCESS_TASK_SOURCES}")
        session = self._session_factory()
        try:
            customer = self._customer_or_404(
                session, str(data.get("customer_id") or ""), business_id)
            row = CxSuccessTask(
                business_id=business_id, customer_id=customer.id,
                kind=kind, title=str(data["title"]),
                due_at=data.get("due_at"), source=source,
                related_ref=data.get("related_ref"),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            task_id = row.id
            result = success_task_dict(row)
        finally:
            session.close()
        if data.get("via_workflow"):
            workflow = self._operations.create_workflow(principal, {
                "business_id": business_id,
                "name": f"P-18 success task: {result['title']}"[:300],
                "objective": "Scheduled customer-success follow-up",
                "origin": "p18_experience",
                "idempotency_key": f"p18-success-task:{task_id}",
                "definition": {"steps": [{
                    "step_key": "follow_up",
                    "name": "Complete the success follow-up",
                    "kind": "task_handler",
                    "action_class": "business.read",
                    "substrate": {
                        "handler": "core.echo_check",
                        "payload": {"message": "success follow-up "
                                               "due",
                                    "task_id": task_id}},
                    "acceptance_criteria": {"task_status": "completed"},
                }]},
            })
            session = self._session_factory()
            try:
                row = session.get(CxSuccessTask, task_id)
                if not row.related_ref:
                    row.related_ref = f"p12-workflow:{workflow['id']}"
                session.commit()
            finally:
                session.close()
            result["workflow_id"] = workflow["id"]
        return result

    def complete_success_task(self, principal: Principal,
                              task_id: str) -> dict:
        from .service import success_task_dict
        self._require_owner(principal, "experience.success_task.complete")
        session = self._session_factory()
        try:
            row = session.get(CxSuccessTask, task_id)
            if row is None:
                raise NotFoundError("success task not found")
            if row.status == "done":
                raise ValidationError("success task is already done")
            row.status = "done"
            session.commit()
            session.refresh(row)
            result = success_task_dict(row)
        finally:
            session.close()
        return result

    def list_success_tasks(self, principal: Principal,
                           business_id: str) -> dict:
        from .service import success_task_dict
        self._require_reader(principal, "experience.success_task.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            rows = session.execute(
                select(CxSuccessTask).where(
                    CxSuccessTask.business_id == business_id)
                .order_by(CxSuccessTask.created_at)).scalars().all()
            return {"items": [success_task_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()

    # ---------------------------------------------------- improvement insights (§19)
    def improvement_insights(self, principal: Principal,
                             business_id: str) -> dict:
        self._require_reader(principal, "experience.insights")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            resolutions = session.execute(
                select(CxResolution).where(
                    CxResolution.business_id == business_id)
            ).scalars().all()
            incidents = session.execute(
                select(CxIncident).where(
                    CxIncident.business_id == business_id)
            ).scalars().all()
            tickets = session.execute(
                select(CxTicket).where(
                    CxTicket.business_id == business_id)
            ).scalars().all()
        finally:
            session.close()
        insights: list[dict] = []

        def confidence(n: int) -> str:
            return "high" if n >= 5 else "medium" if n >= 3 else "low"

        by_group: dict[str, list] = {}
        for r in resolutions:
            if r.root_cause_group:
                by_group.setdefault(r.root_cause_group, []).append(r)
        for group, rows in sorted(
                by_group.items(), key=lambda kv: -len(kv[1])):
            if len(rows) >= 2:
                insights.append({
                    "pattern": f"recurring root cause: {group}",
                    "evidence_count": len(rows),
                    "confidence": confidence(len(rows)),
                    "recommended_improvement":
                        _IMPROVEMENT_MAP.get(group, ""),
                    "source": "recorded resolutions",
                    "causation_note": "grouping is a hypothesis from "
                                      "recorded cases; correlation "
                                      "is not proven causation"})
        by_kind: dict[str, int] = {}
        for i in incidents:
            by_kind[i.kind] = by_kind.get(i.kind, 0) + 1
        for kind, n in sorted(by_kind.items(), key=lambda kv: -kv[1]):
            if n >= 2:
                insights.append({
                    "pattern": f"repeated incident: {kind}",
                    "evidence_count": n,
                    "confidence": confidence(n),
                    "recommended_improvement":
                        "Add detection/prevention for this incident "
                        "kind at the stage where it recurs.",
                    "source": "recorded incidents"})
        by_category: dict[str, list] = {}
        for t in tickets:
            by_category.setdefault(t.category, []).append(t)
        for category, rows in by_category.items():
            reopened = sum(1 for t in rows if t.reopened_count > 0)
            if len(rows) >= 3 and reopened:
                insights.append({
                    "pattern": f"{category} cases reopen after "
                               "resolution",
                    "evidence_count": reopened,
                    "confidence": confidence(len(rows)),
                    "recommended_improvement":
                        "Review the resolution checklist for this "
                        "category; cases are closing before the "
                        "problem is actually fixed.",
                    "source": "recorded tickets"})
        return {"business_id": business_id, "items": insights,
                "count": len(insights),
                "note": "insights are computed from recorded cases "
                        "with evidence counts; nothing here is "
                        "generated opinion"}

    # ---------------------------------------------------- customer 360 + overviews (§17)
    def customer_detail(self, principal: Principal, business_id: str,
                        customer_id: str) -> dict:
        self._require_reader(principal, "experience.customer.detail")
        self._business_or_404(business_id)
        from ..growth.service import customer_dict
        from .service import (
            fulfillment_dict, health_dict, onboarding_dict, ticket_dict,
        )
        session = self._session_factory()
        try:
            customer = self._customer_or_404(
                session, customer_id, business_id)
            result_customer = customer_dict(customer)
            purchases = self._customer_purchases(customer)
            obs = session.execute(
                select(CxOnboarding).where(
                    CxOnboarding.customer_id == customer_id)
            ).scalars().all()
            fulfils = session.execute(
                select(CxFulfillment).where(
                    CxFulfillment.customer_id == customer_id)
            ).scalars().all()
            tickets = session.execute(
                select(CxTicket).where(
                    CxTicket.customer_id == customer_id)
            ).scalars().all()
            health_row = session.execute(
                select(CxHealthSnapshot).where(
                    CxHealthSnapshot.customer_id == customer_id)
                .order_by(CxHealthSnapshot.created_at.desc())
            ).scalars().first()
            feedback = session.execute(
                select(CxFeedback).where(
                    CxFeedback.customer_id == customer_id)
            ).scalars().all()
        finally:
            session.close()
        csat_scores = [f.score for f in feedback
                       if f.kind == "csat" and f.score is not None]
        return {
            "customer": result_customer,
            "customer_source": "p17_crm_customers — the only "
                               "customer store; P-18 references it",
            "purchases": purchases,
            "purchase_count": len(purchases),
            "purchase_note": "read live from P-07 by the customer's "
                             "p07_customer_ref; never copied into "
                             "P-18",
            "onboardings": [onboarding_dict(o) for o in obs],
            "fulfillments": [fulfillment_dict(f) for f in fulfils],
            "tickets": [ticket_dict(t) for t in tickets],
            "open_tickets": sum(1 for t in tickets
                                if t.status in _OPEN_TICKET_STATUSES),
            "csat": csat_score(csat_scores),
            "health": (health_dict(health_row) if health_row else
                       {"classification": "insufficient_data",
                        "status": "INSUFFICIENT_DATA"}),
        }

    def business_overview(self, principal: Principal,
                          business_id: str) -> dict:
        self._require_reader(principal, "experience.overview")
        business = self._business_or_404(business_id)
        session = self._session_factory()
        try:
            def count(model, **filters):
                query = select(model).where(
                    model.business_id == business_id)
                for key, value in filters.items():
                    query = query.where(getattr(model, key) == value)
                return len(session.execute(query).scalars().all())

            from ..database.models.experience import CxCommunication
            counts = {
                "onboardings_open": sum(
                    count(CxOnboarding, status=s) for s in
                    ("not_started", "in_progress", "stalled")),
                "fulfillments_open": sum(
                    count(CxFulfillment, status=s) for s in
                    ("received", "preparing", "in_progress",
                     "shipped")),
                "tickets_open": sum(
                    count(CxTicket, status=s)
                    for s in _OPEN_TICKET_STATUSES),
                "incidents_open": count(CxIncident, status="open")
                + count(CxIncident, status="acknowledged"),
                "communications_queued": count(
                    CxCommunication, status="queued"),
                "resolutions_recommended": count(
                    CxResolution, status="recommended"),
            }
        finally:
            session.close()
        return {"business_id": business_id,
                "business_name": business.get("name"),
                "counts": counts,
                "metrics": self.experience_metrics(principal,
                                                   business_id),
                "health": self.health_overview(principal, business_id),
                "knowledge": self.kb_health(principal, business_id),
                "sla": self.sla_compliance(principal, business_id)}

    def portfolio_overview(self, principal: Principal) -> dict:
        """Cross-business view: owner/system only (P-13 posture —
        portfolio aggregates are never agent-visible)."""
        if principal.type not in (
                PrincipalType.OWNER, PrincipalType.SYSTEM):
            raise PermissionDeniedError(
                "cross-business experience aggregates are "
                "owner/system only")
        businesses = []
        for business in self._all_businesses():
            overview = self.business_overview(principal, business["id"])
            businesses.append({
                "business_id": business["id"],
                "business_name": business.get("name"),
                "counts": overview["counts"],
                "health_distribution":
                    overview["health"]["distribution"],
                "csat": overview["metrics"]["csat"],
            })
        return {"businesses": businesses,
                "note": "aggregates are computed live per business; "
                        "no customer data crosses businesses"}
