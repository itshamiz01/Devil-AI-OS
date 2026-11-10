"""P-18 ExperienceService: the Customer Experience, Service
Delivery & Customer Success Engine.

A post-purchase service layer over P-01–P-17. It owns only
experience state (see models/experience.py). Every authority
stays where it already lives:

* customers — P-17 (``crm_customers`` is the one customer store;
  P-18 references it and creates no copy);
* purchase facts — P-07 (read live by the customer's
  ``p07_customer_ref``; P-18 stores no purchase facts);
* money — P-07 (refunds execute only through
  ``RevenueService.create_refund``; goodwill only through a P-07
  spending request; P-18 tables carry no money column and its
  write flows provably leave P-07's consolidated output
  byte-equal);
* workflows — P-12 (escalations and follow-ups are P-12
  workflows in DRAFT, created on the P-13 precedent; P-18 builds
  no scheduler — its SLA/delay evaluation is a deterministic
  on-demand pass in the P-15 pattern);
* approvals — P-01 hash-bound approvals (P-18 stores only ids);
* agents — P-04 (the §14 roles are seeded P-04 templates; no
  role can send a message or execute a financial action);
* memory — P-09 (verified service findings fed best-effort;
  memory is data, never authority — Article 0);
* governance — P-10 (P-18 adds no authority; writes are
  owner-gated in-service on the P-13/P-16/P-17 pattern, reads
  are owner/system-only because customer data is restricted).

No support channel is connected. The engine records, coordinates
and measures; it does not send messages, book shipments or
provision accounts through any external system, and it says so
in every surface where that matters.
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
from ..database.models.experience import (
    CxCommunication, CxFeedback, CxFulfillment, CxHealthSnapshot,
    CxIncident, CxKnowledgeArticle, CxLifecycleTemplate,
    CxOnboarding, CxQualityReview, CxResolution, CxSlaPolicy,
    CxSuccessTask, CxSupportAnswer, CxTicket, CxTicketMessage,
)
from ..database.models.growth import CrmCustomer, LeadSuppression
from ..database.repositories.core import AuditRepository, ConfigRepository
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from .delivery import DeliveryMixin
from .engage import EngageMixin
from .insight import InsightMixin
from .support import SupportMixin

SYSTEM_PRINCIPAL = Principal(PrincipalType.SYSTEM, "p18-experience")

_log = get_logger("experience.service")


def _iso(value) -> str | None:
    value = as_utc(value) if isinstance(value, dt.datetime) else value
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.isoformat()
    return str(value)


def _actor(principal) -> str:
    return C.actor_of(principal)


# ------------------------------------------------------------ dicts
def template_dict(row: CxLifecycleTemplate) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "business_model": row.business_model, "name": row.name,
            "stages": row.stages or [], "is_default": row.is_default,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def onboarding_dict(row: CxOnboarding) -> dict:
    steps = row.steps or []
    done = sum(1 for s in steps if s.get("status") == "completed")
    return {"id": row.id, "business_id": row.business_id,
            "customer_id": row.customer_id,
            "template_id": row.template_id,
            "template_source": row.template_source,
            "steps": steps, "status": row.status,
            "steps_completed": done, "steps_total": len(steps),
            "progress_percent": (round(done / len(steps) * 100, 1)
                                 if steps else 0.0),
            "assistance_needed": row.assistance_needed,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "is_fixture": row.is_fixture,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def fulfillment_dict(row: CxFulfillment) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "customer_id": row.customer_id, "kind": row.kind,
            "title": row.title, "status": row.status,
            "status_source": row.status_source,
            "revenue_id": row.revenue_id, "order_ref": row.order_ref,
            "tracking_ref": row.tracking_ref, "due_at": row.due_at,
            "delivered_at": row.delivered_at,
            "milestones": row.milestones or [],
            "assigned_to": row.assigned_to,
            "acceptance": row.acceptance,
            "is_fixture": row.is_fixture,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def sla_policy_dict(row: CxSlaPolicy) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "category": row.category,
            "first_response_minutes": row.first_response_minutes,
            "resolution_minutes": row.resolution_minutes,
            "source": row.source, "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def ticket_dict(row: CxTicket) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "customer_id": row.customer_id, "category": row.category,
            "subject": row.subject, "description": row.description,
            "priority": row.priority,
            "priority_factors": row.priority_factors or {},
            "status": row.status, "assigned_to": row.assigned_to,
            "related_ref": row.related_ref,
            "first_response_at": row.first_response_at,
            "resolved_at": row.resolved_at,
            "closed_at": row.closed_at,
            "reopened_count": row.reopened_count,
            "escalation_level": row.escalation_level,
            "escalation_workflow_id": row.escalation_workflow_id,
            "is_fixture": row.is_fixture,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def ticket_message_dict(row: CxTicketMessage) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "ticket_id": row.ticket_id,
            "author_kind": row.author_kind, "body": row.body,
            "internal": row.internal, "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def article_dict(row: CxKnowledgeArticle) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "title": row.title, "content": row.content,
            "category": row.category, "version": row.version,
            "source": row.source,
            "approval_status": row.approval_status,
            "review_status": row.review_status,
            "approved_by": row.approved_by,
            "is_fixture": row.is_fixture,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def answer_dict(row: CxSupportAnswer) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "customer_id": row.customer_id, "ticket_id": row.ticket_id,
            "question": row.question, "answer_text": row.answer_text,
            "article_refs": row.article_refs or [],
            "confidence_class": row.confidence_class,
            "escalated": row.escalated,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def communication_dict(row: CxCommunication) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "customer_id": row.customer_id, "kind": row.kind,
            "channel": row.channel, "body": row.body,
            "status": row.status, "dedupe_key": row.dedupe_key,
            "requires_approval": row.requires_approval,
            "approval_id": row.approval_id,
            "related_ref": row.related_ref,
            "dispatch_note": row.dispatch_note,
            "sent": False,
            "is_fixture": row.is_fixture,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def feedback_dict(row: CxFeedback) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "customer_id": row.customer_id, "kind": row.kind,
            "score": row.score, "comment": row.comment,
            "source": row.source, "related_ref": row.related_ref,
            "is_fixture": row.is_fixture,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def health_dict(row: CxHealthSnapshot) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "customer_id": row.customer_id,
            "classification": row.classification, "score": row.score,
            "factors": row.factors or {}, "evidence": row.evidence or {},
            "confidence": row.confidence,
            "recommended_action": row.recommended_action,
            "basis": "recorded service signals only; a service-health "
                     "classification, not a churn prediction",
            "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def incident_dict(row: CxIncident) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "kind": row.kind, "severity": row.severity,
            "status": row.status, "related_kind": row.related_kind,
            "related_id": row.related_id,
            "customer_id": row.customer_id, "detail": row.detail,
            "detected_by": row.detected_by,
            "resolved_at": row.resolved_at,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def resolution_dict(row: CxResolution) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "customer_id": row.customer_id, "ticket_id": row.ticket_id,
            "incident_id": row.incident_id,
            "problem_class": row.problem_class,
            "root_cause_group": row.root_cause_group,
            "root_cause_basis": "grouping hypothesis from recorded "
                                "cases; correlation is not proven "
                                "causation",
            "action_kind": row.action_kind, "status": row.status,
            "basis": row.basis, "revenue_id": row.revenue_id,
            "p07_refund_id": row.p07_refund_id,
            "p07_spending_request_id": row.p07_spending_request_id,
            "approval_id": row.approval_id, "rationale": row.rationale,
            "outcome": row.outcome, "verified": row.verified,
            "financial_authority": "P-07",
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def quality_review_dict(row: CxQualityReview) -> dict:
    from .scoring import quality_score
    return {"id": row.id, "business_id": row.business_id,
            "ticket_id": row.ticket_id,
            "dimensions": row.dimensions or {},
            "aggregate": quality_score(row.dimensions or {}),
            "method": row.method, "notes": row.notes,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def success_task_dict(row: CxSuccessTask) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "customer_id": row.customer_id, "kind": row.kind,
            "title": row.title, "status": row.status,
            "due_at": row.due_at, "source": row.source,
            "related_ref": row.related_ref,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


class ExperienceService(DeliveryMixin, SupportMixin, EngageMixin,
                        InsightMixin):
    """Composed of mixins, one per prompt area, sharing the helpers
    here (the P-13/P-16/P-17 service shape). Constructed over the
    assembled Application."""

    def __init__(self, application):
        self._app = application
        self._session_factory = application.session_factory
        self._business = application.business        # P-06
        self._financial = application.financial      # P-07
        self._memory = application.memory            # P-09
        self._operations = application.operations    # P-12
        self._portfolio = application.portfolio      # P-13
        self._approvals = application.approvals      # P-01
        self._bus = application.bus

    # ------------------------------------------------------- settings
    def seed_settings(self) -> None:
        session = self._session_factory()
        try:
            repo = ConfigRepository(session)
            if repo.get(C.SETTINGS_KEY) is None:
                repo.set(C.SETTINGS_KEY, json.dumps(C.DEFAULT_SETTINGS),
                         "P-18 experience settings; owner-editable "
                         "governance (autonomy level, communication "
                         "stop, evaluation thresholds, health weights)")
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
        merged["health_weights"] = {
            **C.DEFAULT_SETTINGS["health_weights"],
            **(stored.get("health_weights") or {})}
        return merged

    def update_settings(self, principal: Principal, patch: dict) -> dict:
        self._require_owner(principal, "experience.settings.update")
        current = self.get_settings()
        for key in ("communications_stopped", "auto_evaluation_enabled"):
            if key in patch:
                current[key] = bool(patch[key])
        if "autonomy_level" in patch:
            level = int(patch["autonomy_level"])
            if level not in C.AUTONOMY_LEVELS:
                raise ValidationError("autonomy_level must be 0..3 (§18)")
            current["autonomy_level"] = level
        for key, lo, hi in (("onboarding_stall_hours", 1, 24 * 365),
                            ("unassigned_work_hours", 1, 24 * 365),
                            ("comm_frequency_limit_per_30d", 0, 100),
                            ("feedback_request_interval_days", 0, 365)):
            if key in patch:
                value = int(patch[key])
                if not lo <= value <= hi:
                    raise ValidationError(f"{key} must be within {lo}..{hi}")
                current[key] = value
        if "health_weights" in patch:
            for factor, weight in dict(patch["health_weights"]).items():
                if factor not in C.DEFAULT_SETTINGS["health_weights"]:
                    raise ValidationError(f"unknown health weight: {factor}")
                if float(weight) < 0:
                    raise ValidationError("health weights must be >= 0")
                current["health_weights"][factor] = weight
        session = self._session_factory()
        try:
            ConfigRepository(session).set(
                C.SETTINGS_KEY, json.dumps(current),
                "P-18 experience settings; owner-editable")
        finally:
            session.close()
        self._audit(principal, "experience.settings_updated",
                    "experience", None, "allow",
                    "owner updated P-18 experience settings",
                    {"keys": sorted(patch.keys())})
        return current

    # ------------------------------------------------------------ audit
    def _audit(self, principal, action, target_type, target_id, decision,
               reason=None, details=None) -> None:
        session = self._session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value if principal else "system",
                actor_id=principal.id if principal else "experience-engine",
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
                f"{action} is restricted to the owner: customer "
                "service decisions change customer relationships and "
                "can commit the business, and remain owner authority "
                "(§18/§21)")

    def _require_reader(self, principal: Principal, action: str) -> None:
        """Customer data is owner/system-only (the P-13/P-16/P-17
        posture): an agent never receives customer records by
        default."""
        if principal.type not in (PrincipalType.OWNER,
                                  PrincipalType.SYSTEM):
            self._audit(principal, "experience.isolation_violation",
                        "experience", None, "deny",
                        f"{action}: experience data is not visible to "
                        "this principal",
                        {"principal": _actor(principal)})
            raise PermissionDeniedError(
                "customer and service information is restricted to "
                "the owner; agents receive only explicitly scoped "
                "grants")

    def _owner_approval(self, principal: Principal, *, action: str,
                        resource: str | None, parameters: dict,
                        reason: str, approval_id: str | None = None,
                        ) -> str:
        """The P-08/P-16/P-17 approval pattern: a supplied approval
        must be a hash-bound, owner-decided P-01 approval for
        exactly these parameters; an owner caller without one gets
        a created + decided approval (the owner's call *is* the
        decision, bound and audited); anyone else is refused."""
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
                self._audit(principal, f"{action}.approve", "experience",
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
            "this experience decision requires owner approval; an "
            "agent cannot approve its own proposals (§18)")

    # ---------------------------------------------------------- helpers
    def _business_or_404(self, business_id: str) -> dict:
        try:
            return self._business.get_business(business_id)
        except Exception:
            raise NotFoundError(f"business {business_id} not found")

    def _all_businesses(self) -> list[dict]:
        rows, _total = self._business.list_businesses(limit=500)
        return rows

    def _customer_or_404(self, session, customer_id: str,
                         business_id: str | None = None) -> CrmCustomer:
        """Load a P-17 customer; when a business scope is given the
        customer must belong to it — a customer of another business
        is indistinguishable from a missing one (isolation, §15)."""
        customer = session.get(CrmCustomer, customer_id or "")
        if customer is None:
            raise NotFoundError(f"customer {customer_id} not found")
        if business_id is not None and customer.business_id != business_id:
            raise NotFoundError(
                f"customer {customer_id} not found in business "
                f"{business_id}")
        return customer

    def _feed_memory(self, principal, *, title: str, content: str,
                     source_ref: str, business_id: str | None = None,
                     outcome_status: str = "verified") -> None:
        """Best-effort P-09 feed of verified service findings only
        (the P-14 I6 posture). A feed failure never changes the
        experience result."""
        if self._memory is None:
            return
        try:
            self._memory.ingestion.ingest(principal, {
                "title": title, "content": content,
                "source_type": "agent_output", "source_ref": source_ref,
                "business_id": business_id,
                "verification_status": outcome_status})
        except Exception as exc:  # feeding must not break the engine
            _log.warning("P-18 finding feed to P-09 failed: %s", exc)

    def _customer_purchases(self, customer: CrmCustomer) -> list[dict]:
        """Purchase facts read live from P-07 by the customer's
        ref (§16 contract). Refunded rows are P-07 facts too and
        are labelled by their lifecycle status, never hidden."""
        if not customer.p07_customer_ref:
            return []
        rows, _total = self._financial.revenue.list_revenue(
            customer.business_id, limit=500)
        return [r for r in rows
                if r.get("customer_ref") == customer.p07_customer_ref]

    # ------------------------------------------------------------ status
    def engine_status(self, principal: Principal) -> dict:
        self._require_reader(principal, "experience.status")
        settings = self.get_settings()
        session = self._session_factory()
        try:
            counts = {
                "onboardings": len(session.execute(
                    select(CxOnboarding.id)).all()),
                "fulfillments": len(session.execute(
                    select(CxFulfillment.id)).all()),
                "open_tickets": len(session.execute(
                    select(CxTicket.id).where(
                        CxTicket.status.notin_(
                            ("resolved", "closed")))).all()),
                "open_incidents": len(session.execute(
                    select(CxIncident.id).where(
                        CxIncident.status == "open")).all()),
                "knowledge_articles": len(session.execute(
                    select(CxKnowledgeArticle.id)).all()),
                "queued_communications": len(session.execute(
                    select(CxCommunication.id).where(
                        CxCommunication.status == "queued")).all()),
            }
        finally:
            session.close()
        return {
            "engine": C.ENGINE_NAME,
            "autonomy_level": settings["autonomy_level"],
            "communications_stopped": settings["communications_stopped"],
            "counts": counts,
            "customer_authority": "P-17 (crm_customers)",
            "financial_authority": "P-07",
            "workflow_authority": "P-12",
            "execution_capability": "none — records, coordinates and "
                                    "measures service delivery; sends "
                                    "nothing, ships nothing, moves no "
                                    "money",
            "classification": "READY FOR CONTROLLED PILOT",
        }

    def integrations(self, principal: Principal) -> dict:
        self._require_reader(principal, "experience.integrations")
        return {"items": C.INTEGRATIONS, "count": len(C.INTEGRATIONS),
                "note": "no support channel, logistics, delivery or "
                        "transport integration is connected; every "
                        "surface reports its honest state"}

    # ------------------------------------------------------ agent roles
    def seed_agent_templates(self) -> dict:
        """Seed the ten §14 roles as P-04 agent templates through
        the existing factory (idempotent by name). Roles receive
        only existing catalogue capabilities; no role gets an
        external-send or financial capability because customer
        sends do not exist and refunds stay with the owner + P-07.
        Validation failures are reported, never hidden."""
        factory = self._app.agents
        settings = factory.settings_values()
        from ..agents.constants import DEFAULT_RESOURCE_BUDGET
        session = self._session_factory()
        try:
            from ..database.repositories.agents import TemplateRepository
            existing = {t.name for t in
                        TemplateRepository(session).list(limit=500)[0]}
        finally:
            session.close()
        seeded, skipped, invalid = [], [], []
        for role in C.AGENT_ROLES:
            if role["name"] in existing:
                skipped.append(role["name"])
                continue
            config = {
                "role": role["role"], "agent_type": role["agent_type"],
                "mission": role["mission"],
                "system_instruction": role["instruction"],
                "primary_responsibility": role["responsibility"],
                "secondary_responsibilities": [],
                "input_schema": {"required_fields": ["objective"]},
                "output_schema": {"required_fields": role["outputs"]},
                "allowed_capabilities": list(role["capabilities"]),
                "restricted_capabilities": [],
                "tool_requirements": {"handlers": list(C._HANDLERS)},
                "model_requirements": {"task_class": "general",
                                       "profile_name": None},
                "memory_requirements": {
                    "scopes": ["agent_configuration_history",
                               "previous_task_references"]},
                "resource_budget": dict(DEFAULT_RESOURCE_BUDGET),
                "timeout_seconds": 120,
                "retry_policy": {"max_retries": 1},
                "quality_criteria": {"output_schema_valid": True,
                                     "evidence_required_for_claims": True},
                "evaluation_rules": {
                    "min_output_fields": len(role["outputs"])},
                "approval_requirements": {"creation": "level_0"},
                "security_classification": "internal",
            }
            template = factory.templates.create(
                SYSTEM_PRINCIPAL, name=role["name"], category="experience",
                description=role["mission"], configuration=config,
                settings=settings)
            version = factory.templates.get_version(template.id, 1)
            if version.validation_status == "valid":
                factory.templates.publish(
                    SYSTEM_PRINCIPAL, template.id, version=1)
                seeded.append(role["name"])
            else:
                invalid.append({"name": role["name"],
                                "errors": version.validation_errors})
        return {"seeded": seeded, "already_present": skipped,
                "invalid": invalid}

    def agent_roles(self, principal: Principal) -> dict:
        self._require_reader(principal, "experience.agents")
        factory = self._app.agents
        session = self._session_factory()
        try:
            from ..database.repositories.agents import TemplateRepository
            rows, _ = TemplateRepository(session).list(limit=500)
            by_name = {t.name: t for t in rows}
        finally:
            session.close()
        items = []
        for role in C.AGENT_ROLES:
            template = by_name.get(role["name"])
            items.append({
                "name": role["name"], "role": role["role"],
                "capabilities": role["capabilities"],
                "permission_summary": role["responsibility"],
                "template_status": (template.status if template
                                    else "not_seeded"),
                "external_send_capability": "none — no P-18 role "
                "receives an external communication capability",
                "financial_capability": "none — refunds and "
                "compensation remain owner-executed through P-07"})
        return {"items": items, "count": len(items),
                "note": "roles are P-04 Agent Factory templates "
                        "(seeded by P-18); P-18 builds no separate "
                        "agent orchestration (§14)"}
