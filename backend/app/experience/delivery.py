"""P-18 delivery: lifecycle templates (§3), onboarding (§4),
fulfillment (§5) and the deterministic evaluation pass that turns
delivery problems into actionable incidents (§5/§7/§11).

The evaluation pass is computed from recorded timestamps on
demand — the P-15 pattern. P-18 creates no scheduler and no loop;
P-12 owns recurring workflows and consumes these findings.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.base import as_utc, utcnow
from ..database.models.experience import (
    CxFulfillment, CxIncident, CxLifecycleTemplate, CxOnboarding,
    CxTicket,
)
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from .scoring import parse_time


class DeliveryMixin:
    # ---------------------------------------------------- templates (§3)
    def create_template(self, principal: Principal, business_id: str,
                        data: dict) -> dict:
        from .service import template_dict
        self._require_owner(principal, "experience.template.create")
        self._business_or_404(business_id)
        model = str(data.get("business_model") or "")
        if model not in C.BUSINESS_MODELS:
            raise ValidationError(
                f"business_model must be one of {C.BUSINESS_MODELS}")
        stages = data.get("stages")
        if not isinstance(stages, list) or not stages:
            raise ValidationError(
                "a lifecycle template needs at least one stage")
        seen = set()
        for stage in stages:
            if not isinstance(stage, dict) or not stage.get("key") \
                    or not stage.get("label"):
                raise ValidationError(
                    "every stage needs a key and a label")
            if stage["key"] in seen:
                raise ValidationError(
                    f"duplicate stage key: {stage['key']}")
            seen.add(stage["key"])
        session = self._session_factory()
        try:
            if data.get("is_default"):
                for other in session.execute(
                        select(CxLifecycleTemplate).where(
                            CxLifecycleTemplate.business_id == business_id,
                            CxLifecycleTemplate.business_model == model,
                            CxLifecycleTemplate.is_default.is_(True))
                ).scalars().all():
                    other.is_default = False
            row = CxLifecycleTemplate(
                business_id=business_id, business_model=model,
                name=str(data.get("name") or f"{model} lifecycle"),
                stages=stages,
                is_default=bool(data.get("is_default", False)),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = template_dict(row)
        finally:
            session.close()
        self._audit(principal, "experience.template_created",
                    "experience", result["id"], "allow",
                    "lifecycle template created",
                    {"business_id": business_id, "business_model": model})
        return result

    def list_templates(self, principal: Principal, business_id: str) -> dict:
        from .service import template_dict
        self._require_reader(principal, "experience.template.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            rows = session.execute(
                select(CxLifecycleTemplate).where(
                    CxLifecycleTemplate.business_id == business_id)
                .order_by(CxLifecycleTemplate.created_at)).scalars().all()
            items = [template_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "count": len(items),
                "system_defaults": {
                    model: C.DEFAULT_LIFECYCLES[model]
                    for model in C.BUSINESS_MODELS},
                "note": "business templates override the labelled "
                        "system defaults per business model"}

    def _resolve_template(self, session, business_id: str,
                          template_id: str | None,
                          business_model: str | None):
        """Returns (stages, template_id, source). A business's own
        template wins; otherwise the labelled system default for
        the business model is used — never silently."""
        if template_id:
            template = session.get(CxLifecycleTemplate, template_id)
            if template is None:
                raise NotFoundError("lifecycle template not found")
            if template.business_id != business_id:
                raise ValidationError(
                    "template belongs to a different business "
                    "(isolation, §15)")
            return template.stages or [], template.id, "business_template"
        if business_model:
            template = session.execute(
                select(CxLifecycleTemplate).where(
                    CxLifecycleTemplate.business_id == business_id,
                    CxLifecycleTemplate.business_model == business_model,
                    CxLifecycleTemplate.is_default.is_(True))
            ).scalar_one_or_none()
            if template is not None:
                return (template.stages or [], template.id,
                        "business_template")
            return (C.DEFAULT_LIFECYCLES[business_model], None,
                    "system_default")
        return C.DEFAULT_LIFECYCLES["other"], None, "system_default"

    # ---------------------------------------------------- onboarding (§4)
    def start_onboarding(self, principal: Principal, business_id: str,
                         data: dict) -> dict:
        from .service import onboarding_dict
        self._require_owner(principal, "experience.onboarding.start")
        self._business_or_404(business_id)
        model = data.get("business_model")
        if model is not None and model not in C.BUSINESS_MODELS:
            raise ValidationError(
                f"business_model must be one of {C.BUSINESS_MODELS}")
        session = self._session_factory()
        try:
            customer = self._customer_or_404(
                session, data.get("customer_id") or "", business_id)
            existing = session.execute(
                select(CxOnboarding).where(
                    CxOnboarding.business_id == business_id,
                    CxOnboarding.customer_id == customer.id,
                    CxOnboarding.status.in_(
                        ("not_started", "in_progress", "stalled")))
            ).scalar_one_or_none()
            if existing is not None:
                return {**onboarding_dict(existing),
                        "already_existed": True}
            stages, template_id, source = self._resolve_template(
                session, business_id, data.get("template_id"), model)
            steps = [{"key": s["key"], "label": s["label"],
                      "kind": s["kind"], "status": "pending",
                      "completed_at": None}
                     for s in stages
                     if s["kind"] in ("purchase", "onboarding",
                                      "verification")]
            row = CxOnboarding(
                business_id=business_id, customer_id=customer.id,
                template_id=template_id, template_source=source,
                steps=steps, status="not_started",
                is_fixture=bool(data.get("is_fixture", False)),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = {**onboarding_dict(row), "already_existed": False}
        finally:
            session.close()
        self._audit(principal, "experience.onboarding_started",
                    "experience", result["id"], "allow",
                    "onboarding workflow created",
                    {"business_id": business_id,
                     "customer_id": result["customer_id"]})
        return result

    def update_onboarding_step(self, principal: Principal,
                               onboarding_id: str, step_key: str,
                               status: str) -> dict:
        from .service import onboarding_dict
        self._require_owner(principal, "experience.onboarding.step")
        if status not in ("pending", "completed", "skipped"):
            raise ValidationError(
                "step status must be pending, completed or skipped")
        session = self._session_factory()
        try:
            row = session.get(CxOnboarding, onboarding_id)
            if row is None:
                raise NotFoundError("onboarding not found")
            if row.status in ("completed", "failed"):
                raise ValidationError(
                    f"onboarding is {row.status}; its steps are final")
            steps = [dict(s) for s in (row.steps or [])]
            target = next((s for s in steps if s["key"] == step_key),
                          None)
            if target is None:
                raise NotFoundError(f"step {step_key} not found")
            target["status"] = status
            target["completed_at"] = (
                utcnow().isoformat() if status == "completed" else None)
            row.steps = steps
            if any(s["status"] == "completed" for s in steps) \
                    and row.started_at is None:
                row.started_at = utcnow().isoformat()
            if steps and all(s["status"] in ("completed", "skipped")
                             for s in steps):
                row.status = "completed"
                row.completed_at = utcnow().isoformat()
                row.assistance_needed = False
            elif any(s["status"] == "completed" for s in steps):
                row.status = "in_progress"
            session.commit()
            session.refresh(row)
            result = onboarding_dict(row)
        finally:
            session.close()
        self._audit(principal, "experience.onboarding_step",
                    "experience", onboarding_id, "allow",
                    f"step {step_key} -> {status}", {})
        return result

    def update_onboarding(self, principal: Principal, onboarding_id: str,
                          data: dict) -> dict:
        from .service import onboarding_dict
        self._require_owner(principal, "experience.onboarding.update")
        session = self._session_factory()
        try:
            row = session.get(CxOnboarding, onboarding_id)
            if row is None:
                raise NotFoundError("onboarding not found")
            if "assistance_needed" in data:
                row.assistance_needed = bool(data["assistance_needed"])
            if "status" in data:
                target = str(data["status"])
                if target not in C.ONBOARDING_STATUSES:
                    raise ValidationError(
                        f"status must be one of {C.ONBOARDING_STATUSES}")
                if target == "failed" and row.status == "completed":
                    raise ValidationError(
                        "a completed onboarding cannot fail")
                row.status = target
            session.commit()
            session.refresh(row)
            result = onboarding_dict(row)
        finally:
            session.close()
        return result

    def list_onboardings(self, principal: Principal, business_id: str,
                         *, status: str | None = None) -> dict:
        from .service import onboarding_dict
        self._require_reader(principal, "experience.onboarding.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            query = select(CxOnboarding).where(
                CxOnboarding.business_id == business_id)
            if status:
                query = query.where(CxOnboarding.status == status)
            rows = session.execute(
                query.order_by(CxOnboarding.created_at)).scalars().all()
            return {"items": [onboarding_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()

    def onboarding_dashboard(self, principal: Principal,
                             business_id: str) -> dict:
        self._require_reader(principal, "experience.onboarding.dashboard")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            rows = session.execute(
                select(CxOnboarding).where(
                    CxOnboarding.business_id == business_id)
            ).scalars().all()
        finally:
            session.close()
        by_status = {s: 0 for s in C.ONBOARDING_STATUSES}
        durations = []
        assistance = []
        for row in rows:
            by_status[row.status] = by_status.get(row.status, 0) + 1
            if row.assistance_needed and row.status not in (
                    "completed", "failed"):
                assistance.append(row.id)
            started, done = parse_time(row.started_at), \
                parse_time(row.completed_at)
            if started and done:
                durations.append((done - started).total_seconds() / 3600)
        finished = by_status.get("completed", 0) + by_status.get("failed", 0)
        return {
            "business_id": business_id,
            "total": len(rows), "by_status": by_status,
            "new_customers": by_status.get("not_started", 0),
            "in_progress": by_status.get("in_progress", 0),
            "completed": by_status.get("completed", 0),
            "incomplete": (by_status.get("not_started", 0)
                           + by_status.get("in_progress", 0)
                           + by_status.get("stalled", 0)),
            "delayed": by_status.get("stalled", 0),
            "requiring_assistance": assistance,
            "average_completion_hours": (
                round(sum(durations) / len(durations), 2)
                if durations else None),
            "success_rate_percent": (
                round(by_status.get("completed", 0) / finished * 100, 1)
                if finished else None),
            "note": "averages are computed only from onboardings "
                    "with both a start and a completion timestamp",
        }

    # ---------------------------------------------------- fulfillment (§5)
    def create_fulfillment(self, principal: Principal, business_id: str,
                           data: dict) -> dict:
        from .service import fulfillment_dict
        self._require_owner(principal, "experience.fulfillment.create")
        self._business_or_404(business_id)
        kind = str(data.get("kind") or "")
        if kind not in C.FULFILLMENT_KINDS:
            raise ValidationError(
                f"kind must be one of {C.FULFILLMENT_KINDS}")
        status = str(data.get("status") or "received")
        if status not in C.FULFILLMENT_STATUS_FLOWS[kind]:
            raise ValidationError(
                f"status {status} is not part of the {kind} "
                f"fulfillment flow {C.FULFILLMENT_STATUS_FLOWS[kind]}")
        source = str(data.get("status_source") or "manual")
        if source not in C.FULFILLMENT_STATUS_SOURCES:
            raise ValidationError(
                f"status_source must be one of "
                f"{C.FULFILLMENT_STATUS_SOURCES}")
        session = self._session_factory()
        try:
            customer = self._customer_or_404(
                session, data.get("customer_id") or "", business_id)
            revenue_id = data.get("revenue_id")
            if revenue_id:
                known, _ = self._financial.revenue.list_revenue(
                    business_id, limit=1000)
                if revenue_id not in {r["id"] for r in known}:
                    raise ValidationError(
                        "revenue_id does not reference a P-07 revenue "
                        "record of this business")
            milestones = []
            for m in data.get("milestones") or []:
                if not isinstance(m, dict) or not m.get("key"):
                    raise ValidationError(
                        "every milestone needs a key")
                milestones.append({
                    "key": str(m["key"]),
                    "label": str(m.get("label") or m["key"]),
                    "status": str(m.get("status") or "pending"),
                    "completed_at": m.get("completed_at")})
            row = CxFulfillment(
                business_id=business_id, customer_id=customer.id,
                kind=kind, title=str(data.get("title") or "Fulfillment"),
                status=status, status_source=source,
                revenue_id=revenue_id,
                order_ref=data.get("order_ref"),
                tracking_ref=data.get("tracking_ref"),
                due_at=data.get("due_at"),
                assigned_to=data.get("assigned_to"),
                milestones=milestones,
                is_fixture=bool(data.get("is_fixture", False)),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = fulfillment_dict(row)
        finally:
            session.close()
        self._audit(principal, "experience.fulfillment_created",
                    "experience", result["id"], "allow",
                    f"{kind} fulfillment recorded",
                    {"business_id": business_id})
        return result

    def transition_fulfillment(self, principal: Principal,
                               fulfillment_id: str, data: dict) -> dict:
        from .service import fulfillment_dict
        self._require_owner(principal, "experience.fulfillment.transition")
        session = self._session_factory()
        try:
            row = session.get(CxFulfillment, fulfillment_id)
            if row is None:
                raise NotFoundError("fulfillment not found")
            target = str(data.get("status") or "")
            if target not in C.FULFILLMENT_STATUS_FLOWS[row.kind]:
                raise ValidationError(
                    f"status {target} is not part of the {row.kind} "
                    f"fulfillment flow")
            if "status_source" in data:
                if data["status_source"] not in \
                        C.FULFILLMENT_STATUS_SOURCES:
                    raise ValidationError("unknown status_source")
                row.status_source = str(data["status_source"])
            row.status = target
            if data.get("tracking_ref"):
                row.tracking_ref = str(data["tracking_ref"])
            if target in ("delivered", "completed"):
                row.delivered_at = data.get("delivered_at") \
                    or utcnow().isoformat()
            if data.get("assigned_to"):
                row.assigned_to = str(data["assigned_to"])
            session.commit()
            session.refresh(row)
            result = fulfillment_dict(row)
        finally:
            session.close()
        self._audit(principal, "experience.fulfillment_transition",
                    "experience", fulfillment_id, "allow",
                    f"fulfillment -> {result['status']} "
                    f"(source: {result['status_source']})", {})
        return result

    def update_milestone(self, principal: Principal, fulfillment_id: str,
                         key: str, status: str) -> dict:
        from .service import fulfillment_dict
        self._require_owner(principal, "experience.fulfillment.milestone")
        if status not in ("pending", "in_progress", "completed"):
            raise ValidationError(
                "milestone status must be pending, in_progress or "
                "completed")
        session = self._session_factory()
        try:
            row = session.get(CxFulfillment, fulfillment_id)
            if row is None:
                raise NotFoundError("fulfillment not found")
            milestones = [dict(m) for m in (row.milestones or [])]
            target = next((m for m in milestones if m["key"] == key),
                          None)
            if target is None:
                raise NotFoundError(f"milestone {key} not found")
            target["status"] = status
            target["completed_at"] = (
                utcnow().isoformat() if status == "completed" else None)
            row.milestones = milestones
            if milestones and all(m["status"] == "completed"
                                  for m in milestones) \
                    and row.status == "in_progress":
                row.status = "completed"
                row.delivered_at = row.delivered_at \
                    or utcnow().isoformat()
            session.commit()
            session.refresh(row)
            result = fulfillment_dict(row)
        finally:
            session.close()
        return result

    def set_acceptance(self, principal: Principal, fulfillment_id: str,
                       acceptance: str) -> dict:
        from .service import fulfillment_dict
        self._require_owner(principal, "experience.fulfillment.acceptance")
        if acceptance not in C.ACCEPTANCE_STATES:
            raise ValidationError(
                f"acceptance must be one of {C.ACCEPTANCE_STATES}")
        session = self._session_factory()
        try:
            row = session.get(CxFulfillment, fulfillment_id)
            if row is None:
                raise NotFoundError("fulfillment not found")
            if row.status not in ("delivered", "completed"):
                raise ValidationError(
                    "customer acceptance applies once delivery is "
                    "recorded")
            row.acceptance = acceptance
            session.commit()
            session.refresh(row)
            result = fulfillment_dict(row)
        finally:
            session.close()
        return result

    def list_fulfillments(self, principal: Principal, business_id: str,
                          *, status: str | None = None,
                          customer_id: str | None = None) -> dict:
        from .service import fulfillment_dict
        self._require_reader(principal, "experience.fulfillment.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            query = select(CxFulfillment).where(
                CxFulfillment.business_id == business_id)
            if status:
                query = query.where(CxFulfillment.status == status)
            if customer_id:
                query = query.where(
                    CxFulfillment.customer_id == customer_id)
            rows = session.execute(
                query.order_by(CxFulfillment.created_at)).scalars().all()
            return {"items": [fulfillment_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()

    # ---------------------------------------------------- evaluation (§5/§7)
    def _open_incident(self, session, *, business_id: str, kind: str,
                       related_kind: str, related_id: str | None,
                       customer_id: str | None, severity: str,
                       detail: str, actor: str) -> CxIncident | None:
        existing = session.execute(
            select(CxIncident).where(
                CxIncident.business_id == business_id,
                CxIncident.kind == kind,
                CxIncident.related_id == related_id,
                CxIncident.status.in_(("open", "acknowledged")))
        ).scalar_one_or_none()
        if existing is not None:
            return None
        row = CxIncident(
            business_id=business_id, kind=kind, severity=severity,
            status="open", related_kind=related_kind,
            related_id=related_id, customer_id=customer_id,
            detail=detail, detected_by="evaluation",
            created_by=actor)
        session.add(row)
        session.flush()
        return row

    def evaluate(self, principal: Principal,
                 business_id: str | None = None) -> dict:
        """Deterministic detection pass over recorded state:
        stalled onboarding, delayed / failed / unassigned /
        incompletely-delivered fulfillment, SLA breaches and
        repeated fulfillment failure. Idempotent — one open
        incident per (kind, record). Owner or system only."""
        if principal.type not in (PrincipalType.OWNER,
                                  PrincipalType.SYSTEM):
            raise PermissionDeniedError(
                "the experience evaluation pass is owner/system only")
        from .service import incident_dict
        from .support import policy_for
        settings = self.get_settings()
        if not settings["auto_evaluation_enabled"]:
            return {"created": [], "count": 0,
                    "note": "evaluation is disabled by the owner "
                            "(auto_evaluation_enabled = false)"}
        now = utcnow()
        created: list[dict] = []
        session = self._session_factory()
        try:
            businesses = [business_id] if business_id else [
                b["id"] for b in self._all_businesses()]
            for bid in businesses:
                stall_cutoff = now - dt.timedelta(
                    hours=int(settings["onboarding_stall_hours"]))
                for ob in session.execute(
                        select(CxOnboarding).where(
                            CxOnboarding.business_id == bid,
                            CxOnboarding.status.in_(
                                ("not_started", "in_progress")))
                ).scalars().all():
                    if as_utc(ob.created_at) and \
                            as_utc(ob.created_at) < stall_cutoff:
                        if ob.status != "stalled":
                            ob.status = "stalled"
                            ob.assistance_needed = True
                        incident = self._open_incident(
                            session, business_id=bid,
                            kind="onboarding_stalled",
                            related_kind="onboarding", related_id=ob.id,
                            customer_id=ob.customer_id, severity="medium",
                            detail="onboarding has not completed "
                                   f"within {settings['onboarding_stall_hours']}h",
                            actor=C.actor_of(principal))
                        if incident:
                            created.append(incident_dict(incident))
                unassigned_cutoff = now - dt.timedelta(
                    hours=int(settings["unassigned_work_hours"]))
                failed_by_customer: dict[str, int] = {}
                for f in session.execute(
                        select(CxFulfillment).where(
                            CxFulfillment.business_id == bid)
                ).scalars().all():
                    due = parse_time(f.due_at)
                    if due and due < now and f.status not in (
                            "delivered", "completed", "failed",
                            "returned"):
                        incident = self._open_incident(
                            session, business_id=bid,
                            kind="delayed_fulfillment",
                            related_kind="fulfillment", related_id=f.id,
                            customer_id=f.customer_id, severity="high",
                            detail=f"fulfillment due {f.due_at} is "
                                   f"still {f.status}",
                            actor=C.actor_of(principal))
                        if incident:
                            created.append(incident_dict(incident))
                    if f.status == "failed":
                        failed_by_customer[f.customer_id] = \
                            failed_by_customer.get(f.customer_id, 0) + 1
                        incident = self._open_incident(
                            session, business_id=bid,
                            kind="failed_provisioning"
                            if f.kind in ("digital", "service")
                            else "delayed_fulfillment",
                            related_kind="fulfillment", related_id=f.id,
                            customer_id=f.customer_id, severity="high",
                            detail=f"{f.kind} fulfillment recorded "
                                   "failed", actor=C.actor_of(principal))
                        if incident:
                            created.append(incident_dict(incident))
                    if f.assigned_to is None and f.status in (
                            "received", "preparing", "in_progress") \
                            and as_utc(f.created_at) \
                            and as_utc(f.created_at) < unassigned_cutoff:
                        incident = self._open_incident(
                            session, business_id=bid,
                            kind="unassigned_work",
                            related_kind="fulfillment", related_id=f.id,
                            customer_id=f.customer_id, severity="medium",
                            detail="fulfillment has no assignee after "
                                   f"{settings['unassigned_work_hours']}h",
                            actor=C.actor_of(principal))
                        if incident:
                            created.append(incident_dict(incident))
                    if f.status in ("delivered", "completed") and any(
                            m.get("status") != "completed"
                            for m in (f.milestones or [])):
                        incident = self._open_incident(
                            session, business_id=bid,
                            kind="missing_deliverable",
                            related_kind="fulfillment", related_id=f.id,
                            customer_id=f.customer_id, severity="medium",
                            detail="fulfillment marked delivered with "
                                   "incomplete milestones",
                            actor=C.actor_of(principal))
                        if incident:
                            created.append(incident_dict(incident))
                for customer_id, failures in failed_by_customer.items():
                    if failures >= 2:
                        incident = self._open_incident(
                            session, business_id=bid,
                            kind="repeated_failure",
                            related_kind="customer",
                            related_id=customer_id,
                            customer_id=customer_id, severity="high",
                            detail=f"{failures} failed fulfillments "
                                   "recorded for this customer",
                            actor=C.actor_of(principal))
                        if incident:
                            created.append(incident_dict(incident))
                for t in session.execute(
                        select(CxTicket).where(
                            CxTicket.business_id == bid,
                            CxTicket.status.notin_(
                                ("resolved", "closed")))
                ).scalars().all():
                    policy = policy_for(session, bid, t.category)
                    if not policy:
                        continue
                    from .scoring import sla_state
                    state = sla_state(
                        policy, created_at=t.created_at,
                        first_response_at=t.first_response_at,
                        resolved_at=t.resolved_at, now=now)
                    if state["status"] == "breached":
                        incident = self._open_incident(
                            session, business_id=bid, kind="sla_breach",
                            related_kind="ticket", related_id=t.id,
                            customer_id=t.customer_id, severity="high",
                            detail="ticket breached the business's "
                                   "configured SLA policy",
                            actor=C.actor_of(principal))
                        if incident:
                            created.append(incident_dict(incident))
            session.commit()
        finally:
            session.close()
        self._audit(principal, "experience.evaluation_run", "experience",
                    None, "allow",
                    f"evaluation created {len(created)} incident(s)",
                    {"business_id": business_id})
        return {"created": created, "count": len(created),
                "evaluated_at": now.isoformat()}

    # ---------------------------------------------------- incidents
    def list_incidents(self, principal: Principal, business_id: str,
                       *, status: str | None = None) -> dict:
        from .service import incident_dict
        self._require_reader(principal, "experience.incident.list")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            query = select(CxIncident).where(
                CxIncident.business_id == business_id)
            if status:
                query = query.where(CxIncident.status == status)
            rows = session.execute(
                query.order_by(CxIncident.created_at)).scalars().all()
            return {"items": [incident_dict(r) for r in rows],
                    "count": len(rows)}
        finally:
            session.close()

    def transition_incident(self, principal: Principal, incident_id: str,
                            status: str) -> dict:
        from .service import incident_dict
        self._require_owner(principal, "experience.incident.transition")
        if status not in ("acknowledged", "resolved"):
            raise ValidationError(
                "incident status must be acknowledged or resolved")
        session = self._session_factory()
        try:
            row = session.get(CxIncident, incident_id)
            if row is None:
                raise NotFoundError("incident not found")
            if row.status == "resolved":
                raise ValidationError("incident is already resolved")
            row.status = status
            if status == "resolved":
                row.resolved_at = utcnow().isoformat()
            session.commit()
            session.refresh(row)
            result = incident_dict(row)
        finally:
            session.close()
        self._audit(principal, "experience.incident_transition",
                    "experience", incident_id, "allow",
                    f"incident -> {status}", {})
        return result
