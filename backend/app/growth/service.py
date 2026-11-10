"""P-17 GrowthService: the Customer Acquisition, Marketing &
Revenue Growth Engine.

A commercial growth layer over P-01–P-16. It owns only growth
state (see models/growth.py). Every authority stays where it
already lives:

* business identity + lifecycle — P-06 (referenced, never copied);
* money — P-07 (spend exists only as P-07 expense / spending
  records; attributed revenue is read live from P-07 revenue
  metrics by channel tag; P-17 stores no ledger data and its write
  flows provably leave P-07's consolidated output byte-equal);
* experiments — P-08 (growth experiment designs hand off; P-08
  binds the real P-07 budget and enforces the stop-loss);
* economy strategy + the owner's profitability gate — P-16 (the
  gate is consumed live from ``EconomyService.engine_status``;
  expansion approvals in P-17 respect it with the same per-item
  owner override, never a global off-switch);
* portfolio coordination — P-13 (read for context; customer data
  and finances stay per-business);
* approvals — P-01 hash-bound approvals (P-17 stores only ids);
* agents — P-04 (the §12 roles are seeded P-04 templates; P-17
  builds no orchestration);
* memory — P-09 (verified outcomes fed best-effort; memory is
  data, never authority — Article 0);
* governance — P-10 (P-17 adds no authority; writes are
  owner-gated in-service on the P-13/P-16 pattern, and its
  pause/stop/freeze flags compose with P-10 modes).

External marketing platforms: none are connected. The engine
prepares, governs and measures; it does not post, send, or spend
through any platform, and it says so in every surface where that
matters.
"""
from __future__ import annotations

import datetime as dt
import json
import re


from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..core.logging import get_logger
from ..database.models.base import as_utc, utcnow
from ..database.models.core import AuditEvent
from ..database.models.growth import (
    BrandProfile, ChannelEvaluation, CommunicationMessage,
    CommunicationTemplate, ContentItem, CrmCustomer, CustomerPersona,
    FunnelEvent, GrowthExperiment, GrowthInteraction, GrowthLead,
    IdealCustomerProfile, LeadSuppression, MarketingCampaign,
    MarketingStrategy, Partnership, SalesOpportunity, SeoRecord,
)
from ..database.repositories.core import AuditRepository, ConfigRepository
from ..financial import constants as FC
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from .analytics import AnalyticsMixin
from .campaigns import CampaignsMixin
from .engagement import EngagementMixin
from .intelligence import IntelligenceMixin
from .pipeline import PipelineMixin

SYSTEM_PRINCIPAL = Principal(PrincipalType.SYSTEM, "p17-growth")

_log = get_logger("growth.service")


def _iso(value: dt.datetime | None) -> str | None:
    value = as_utc(value)
    return value.isoformat() if value else None


def _actor(principal) -> str:
    return C.actor_of(principal)


def dedupe_key_for(contact: dict) -> str:
    """Normalized contact identity for per-business deduplication:
    email first (case-insensitive), then phone digits, then a
    name+company slug. Deterministic and documented — the same
    person imported twice for one business collides on purpose."""
    email = str(contact.get("email") or "").strip().lower()
    if email:
        return f"email:{email}"
    phone = re.sub(r"\D", "", str(contact.get("phone") or ""))
    if phone:
        return f"phone:{phone}"
    name = re.sub(r"[^a-z0-9]+", "-", str(
        contact.get("name") or "").strip().lower()).strip("-")
    company = re.sub(r"[^a-z0-9]+", "-", str(
        contact.get("company") or "").strip().lower()).strip("-")
    return f"name:{name}|{company}"


def slug_for(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug[:40] or "campaign"


# ------------------------------------------------------------ dicts
def brand_profile_dict(row: BrandProfile) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "brand_name": row.brand_name, "identity": row.identity,
            "tone_of_voice": row.tone_of_voice, "colors": row.colors or [],
            "typography": row.typography, "logo_refs": row.logo_refs or [],
            "messaging_guidelines": row.messaging_guidelines,
            "prohibited_claims": row.prohibited_claims or [],
            "product_information": row.product_information,
            "assets": row.assets or [], "updated_by": row.updated_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def persona_dict(row: CustomerPersona) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "segment": row.segment, "needs": row.needs or [],
            "problems": row.problems or [],
            "motivations": row.motivations or [],
            "budget_sensitivity": row.budget_sensitivity,
            "product_category": row.product_category,
            "objections": row.objections or [],
            "discovery_channels": row.discovery_channels or [],
            "buying_journey": row.buying_journey,
            "demographics": row.demographics or {},
            "evidence": row.evidence or [],
            "is_fixture": row.is_fixture, "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def icp_dict(row: IdealCustomerProfile) -> dict:
    return {"id": row.id, "business_id": row.business_id, "kind": row.kind,
            "segment": row.segment, "criteria": row.criteria or {},
            "factor_scores": row.factor_scores or {},
            "priority_score": row.priority_score,
            "priority_label": "prioritisation estimate, not a demand "
                              "measurement",
            "rationale": row.rationale, "is_fixture": row.is_fixture,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def channel_dict(row: ChannelEvaluation) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "channel_key": row.channel_key, "category": row.category,
            "label": C.CHANNELS.get(row.channel_key, ("", row.channel_key))[1],
            "evaluation": row.evaluation or {},
            "evaluation_label": "declared estimates",
            "factor_scores": row.factor_scores or {},
            "expected_value_score": row.expected_value_score,
            "status": row.status, "notes": row.notes,
            "integration_state": "not_configured",
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def strategy_dict(row: MarketingStrategy) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "title": row.title, "approach": row.approach, "kind": row.kind,
            "sections": row.sections or {}, "status": row.status,
            "approval_id": row.approval_id,
            "gate_override": row.gate_override,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def campaign_dict(row: MarketingCampaign) -> dict:
    return {"id": row.id, "business_id": row.business_id, "name": row.name,
            "code": row.code,
            "attribution_channel": f"{C.ATTRIBUTION_CHANNEL_PREFIX}{row.code}",
            "project_ref": f"{C.CAMPAIGN_PROJECT_REF_PREFIX}{row.id}",
            "objective": row.objective, "purpose": row.purpose,
            "strategy_id": row.strategy_id,
            "channel_evaluation_id": row.channel_evaluation_id,
            "channel_key": row.channel_key,
            "target_audience": row.target_audience or {},
            "start_date": row.start_date, "end_date": row.end_date,
            "budget_ceiling_minor": row.budget_ceiling_minor,
            "budget_ceiling_label": "approved ceiling (proposal data), "
                                    "not spend",
            "currency": row.currency,
            "expected_results": row.expected_results or {},
            "expected_results_label": "ESTIMATE — declared expectations, "
                                      "not results",
            "creative_asset_refs": row.creative_asset_refs or [],
            "landing_page": row.landing_page,
            "conversion_event": row.conversion_event, "status": row.status,
            "approval_id": row.approval_id, "gate_override": row.gate_override,
            "auto_pause_rules": row.auto_pause_rules,
            "spend_request_ids": row.spend_request_ids or [],
            "paused_reason": row.paused_reason, "is_fixture": row.is_fixture,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def content_dict(row: ContentItem) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "campaign_id": row.campaign_id, "kind": row.kind,
            "title": row.title, "brief": row.brief or {}, "body": row.body,
            "status": row.status, "review": row.review or {},
            "scheduled_at": row.scheduled_at, "release_ref": row.release_ref,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def lead_dict(row: GrowthLead) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "contact": row.contact or {}, "dedupe_key": row.dedupe_key,
            "source_kind": row.source_kind,
            "source_channel": row.source_channel,
            "campaign_id": row.campaign_id,
            "consent_status": row.consent_status,
            "lawful_basis": row.lawful_basis, "segment": row.segment,
            "interest": row.interest, "score": row.score,
            "score_factors": row.score_factors or {},
            "score_band": row.score_band, "stage": row.stage,
            "assigned_to": row.assigned_to,
            "converted_customer_id": row.converted_customer_id,
            "is_fixture": row.is_fixture, "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def suppression_dict(row: LeadSuppression) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "dedupe_key": row.dedupe_key, "reason": row.reason,
            "source": row.source, "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def sales_opportunity_dict(row: SalesOpportunity) -> dict:
    weighted = None
    if row.estimated_value_minor is not None:
        weighted = int(row.estimated_value_minor * row.probability / 100)
    return {"id": row.id, "business_id": row.business_id,
            "lead_id": row.lead_id, "customer_id": row.customer_id,
            "product": row.product,
            "estimated_value_minor": row.estimated_value_minor,
            "estimated_value_label": "ESTIMATE — pipeline value is not "
                                     "revenue; realized revenue exists "
                                     "only in P-07",
            "weighted_value_minor": weighted,
            "currency": row.currency, "stage": row.stage,
            "probability": row.probability,
            "expected_close_date": row.expected_close_date,
            "assigned_to": row.assigned_to, "next_action": row.next_action,
            "lost_reason": row.lost_reason, "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def customer_dict(row: CrmCustomer) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "display_name": row.display_name, "contact": row.contact or {},
            "dedupe_key": row.dedupe_key,
            "p07_customer_ref": row.p07_customer_ref,
            "segment": row.segment, "lifecycle_stage": row.lifecycle_stage,
            "consent_status": row.consent_status,
            "preferences": row.preferences or {},
            "acquisition_campaign_id": row.acquisition_campaign_id,
            "acquisition_channel": row.acquisition_channel,
            "source_lead_id": row.source_lead_id,
            "health_score": row.health_score,
            "health_factors": row.health_factors or {},
            "health_computed_at": row.health_computed_at,
            "is_fixture": row.is_fixture, "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def interaction_dict(row: GrowthInteraction) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "subject_kind": row.subject_kind, "subject_id": row.subject_id,
            "kind": row.kind, "summary": row.summary,
            "outcome": row.outcome, "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def funnel_event_dict(row: FunnelEvent) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "campaign_id": row.campaign_id, "stage": row.stage,
            "count": row.count, "period_start": row.period_start,
            "period_end": row.period_end, "source": row.source,
            "source_label": "DECLARED — owner/imported count, not "
                            "system-measured",
            "is_fixture": row.is_fixture, "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def experiment_dict(row: GrowthExperiment) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "campaign_id": row.campaign_id, "title": row.title,
            "hypothesis": row.hypothesis,
            "control_description": row.control_description,
            "test_description": row.test_description,
            "primary_metric": row.primary_metric,
            "minimum_evaluation": row.minimum_evaluation or {},
            "duration_days": row.duration_days,
            "budget_ceiling_minor": row.budget_ceiling_minor,
            "budget_ceiling_label": "pre-declared ceiling; execution "
                                    "binds a P-07 budget in P-08",
            "max_acceptable_loss_minor": row.max_acceptable_loss_minor,
            "status": row.status, "approval_id": row.approval_id,
            "p08_experiment_id": row.p08_experiment_id,
            "observations": row.observations or {},
            "observations_label": "DECLARED observations recorded by "
                                  "the owner, not platform-measured",
            "result": row.result, "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def seo_dict(row: SeoRecord) -> dict:
    return {"id": row.id, "business_id": row.business_id, "kind": row.kind,
            "title": row.title, "data": row.data or {},
            "source": row.source,
            "source_label": "declared/imported record — the system has "
                            "no crawler and no search feed",
            "period_start": row.period_start, "period_end": row.period_end,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def template_dict(row: CommunicationTemplate) -> dict:
    return {"id": row.id, "business_id": row.business_id, "kind": row.kind,
            "name": row.name, "subject": row.subject, "body": row.body,
            "status": row.status, "approval_id": row.approval_id,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def message_dict(row: CommunicationMessage) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "template_id": row.template_id,
            "recipient_kind": row.recipient_kind,
            "recipient_id": row.recipient_id, "channel": row.channel,
            "status": row.status, "refusal_reason": row.refusal_reason,
            "dispatch_note": row.dispatch_note,
            "delivery_label": "no transport is configured; no message "
                              "is ever recorded as sent or delivered",
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def partnership_dict(row: Partnership) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "partner_name": row.partner_name, "kind": row.kind,
            "stage": row.stage, "evaluation": row.evaluation or {},
            "contact_proposal": row.contact_proposal,
            "approval_id": row.approval_id,
            "referral_code": row.referral_code,
            "referral_channel": (f"{C.PARTNER_CHANNEL_PREFIX}{row.referral_code}"
                                 if row.referral_code else None),
            "agreement_label": "internal record only — the system "
                               "never enters a binding agreement",
            "notes": row.notes, "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


class GrowthService(IntelligenceMixin, CampaignsMixin, PipelineMixin,
                    EngagementMixin, AnalyticsMixin):
    """Composed of mixins, one per prompt area, sharing the helpers
    here (the P-13/P-16 service shape). Constructed over the
    assembled Application (the P-15/P-16 precedent)."""

    def __init__(self, application):
        self._app = application
        self._session_factory = application.session_factory
        self._business = application.business        # P-06
        self._financial = application.financial      # P-07
        self._survival = application.survival        # P-08
        self._memory = application.memory            # P-09
        self._portfolio = application.portfolio      # P-13
        self._economy = application.economy          # P-16
        self._approvals = application.approvals      # P-01
        self._bus = application.bus

    # ------------------------------------------------------- settings
    def seed_settings(self) -> None:
        session = self._session_factory()
        try:
            repo = ConfigRepository(session)
            if repo.get(C.SETTINGS_KEY) is None:
                repo.set(C.SETTINGS_KEY, json.dumps(C.DEFAULT_SETTINGS),
                         "P-17 growth settings; owner-editable governance "
                         "(autonomy level, pause/stop/freeze flags, "
                         "scoring weights, frequency limits)")
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
        for nested in ("lead_score_weights", "icp_weights",
                       "channel_weights"):
            merged[nested] = {**C.DEFAULT_SETTINGS[nested],
                              **(stored.get(nested) or {})}
        return merged

    def update_settings(self, principal: Principal, patch: dict) -> dict:
        self._require_owner(principal, "growth.settings.update")
        current = self.get_settings()
        for key in ("all_campaigns_paused", "communications_stopped",
                    "outreach_suspended", "marketing_spend_frozen"):
            if key in patch:
                current[key] = bool(patch[key])
        if "autonomy_level" in patch:
            level = int(patch["autonomy_level"])
            if level not in C.AUTONOMY_LEVELS:
                raise ValidationError("autonomy_level must be 1..4 (§24)")
            current["autonomy_level"] = level
        if "comm_frequency_limit_per_30d" in patch:
            value = int(patch["comm_frequency_limit_per_30d"])
            if not 0 <= value <= 50:
                raise ValidationError(
                    "comm_frequency_limit_per_30d must be within 0..50")
            current["comm_frequency_limit_per_30d"] = value
        for key, valid in (("lead_score_weights", C.LEAD_SCORE_FACTORS),
                           ("icp_weights", C.ICP_FACTOR_KEYS),
                           ("channel_weights", C.CHANNEL_FACTOR_KEYS)):
            if key in patch:
                for factor, weight in dict(patch[key]).items():
                    if factor not in valid:
                        raise ValidationError(f"unknown {key} entry: {factor}")
                    if float(weight) < 0:
                        raise ValidationError("weights must be >= 0")
                    current[key][factor] = weight
        if "cac_expense_categories" in patch:
            cats = list(patch["cac_expense_categories"])
            unknown = [c for c in cats if c not in FC.EXPENSE_CATEGORIES]
            if unknown:
                raise ValidationError(
                    f"unknown P-07 expense categories: {unknown}")
            current["cac_expense_categories"] = cats
        session = self._session_factory()
        try:
            ConfigRepository(session).set(
                C.SETTINGS_KEY, json.dumps(current),
                "P-17 growth settings; owner-editable")
        finally:
            session.close()
        self._audit(principal, "growth.settings_updated", "growth",
                    None, "allow", "owner updated P-17 growth settings",
                    {"keys": sorted(patch.keys())})
        return current

    # ------------------------------------------------------------ audit
    def _audit(self, principal, action, target_type, target_id, decision,
               reason=None, details=None) -> None:
        session = self._session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value if principal else "system",
                actor_id=principal.id if principal else "growth-engine",
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
                f"{action} is restricted to the owner: commercial "
                "growth decisions change customer relationships and "
                "spend commitments and remain owner authority (§24)")

    def _require_reader(self, principal: Principal, action: str) -> None:
        """Growth aggregates and customer data are owner/system-only
        (the P-13/P-16 posture): an agent never receives customer
        data or portfolio growth figures by default."""
        if principal.type not in (PrincipalType.OWNER,
                                  PrincipalType.SYSTEM):
            self._audit(principal, "growth.isolation_violation",
                        "growth", None, "deny",
                        f"{action}: growth data is not visible to "
                        "this principal",
                        {"principal": _actor(principal)})
            raise PermissionDeniedError(
                "customer and growth information is restricted to "
                "the owner; agents receive only explicitly scoped "
                "grants")

    # ---------------------------------------------------------- helpers
    def _business_or_404(self, business_id: str) -> dict:
        try:
            return self._business.get_business(business_id)
        except Exception:
            raise NotFoundError(f"business {business_id} not found")

    def _all_businesses(self) -> list[dict]:
        rows, _total = self._business.list_businesses(limit=500)
        return rows

    def _profile(self, business_id: str) -> dict | None:
        try:
            return self._financial.get_profile(business_id)
        except Exception:
            return None

    def _indicators(self, business_id: str) -> dict | None:
        """P-07's stable read contract; None when the business has
        no financial profile (never fabricated)."""
        try:
            return self._financial.p08_indicators(business_id)
        except Exception:
            return None

    def _revenue_metrics(self, business_id: str) -> dict | None:
        profile = self._profile(business_id)
        if profile is None:
            return None
        return self._financial.revenue.metrics(
            business_id, profile["base_currency"])

    def _gate(self) -> dict:
        """The owner's P-16 profitability gate, consumed live."""
        return self._economy.engine_status(
            SYSTEM_PRINCIPAL)["profitability_gate"]

    def _owner_approval(self, principal: Principal, *, action: str,
                        resource: str | None, parameters: dict,
                        reason: str, approval_id: str | None = None,
                        ) -> str:
        """The P-08/P-16 approval pattern: a supplied approval must
        be a hash-bound, owner-decided P-01 approval for exactly
        these parameters; an owner caller without one gets a created
        + decided approval (the owner's call *is* the decision,
        bound and audited); anyone else is refused."""
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
                self._audit(principal, f"{action}.approve", "growth",
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
            "this growth decision requires owner approval; an agent "
            "cannot approve its own proposals (§24)")

    def _check_gate(self, principal: Principal, *, what: str,
                    gate_override_reason: str | None) -> dict | None:
        """Profitability-gate enforcement for expansion approvals.
        Returns the recorded override dict when the owner overrode a
        closed gate; raises when the gate is closed and no override
        reason was supplied. A no-op (None) when the gate is open."""
        gate = self._gate()
        if gate["state"] == "open":
            return None
        if gate_override_reason and gate_override_reason.strip():
            if principal.type != PrincipalType.OWNER:
                raise PermissionDeniedError(
                    "only the owner can override the profitability gate")
            return {"by": _actor(principal),
                    "reason": gate_override_reason.strip(),
                    "at": utcnow().isoformat(),
                    "gate_reason": gate["reason"]}
        raise ValidationError(
            f"the owner's profitability gate is CLOSED ({gate['reason']}); "
            f"{what} cannot be approved until the portfolio is "
            "verifiably profitable, or the owner records a per-item "
            "override with a reason (P-16: profitability before "
            "expansion; there is no global off-switch)")

    def _feed_memory(self, principal, *, title: str, content: str,
                     source_ref: str, business_id: str | None = None,
                     outcome_status: str = "verified") -> None:
        """Best-effort P-09 feed of verified outcomes only (the
        P-14 I6 / P-16 posture). A feed failure never changes the
        growth result."""
        if self._memory is None:
            return
        try:
            self._memory.ingestion.ingest(principal, {
                "title": title, "content": content,
                "source_type": "agent_output", "source_ref": source_ref,
                "business_id": business_id,
                "verification_status": outcome_status})
        except Exception as exc:  # feeding must not break the engine
            _log.warning("P-17 outcome feed to P-09 failed: %s", exc)

    # ------------------------------------------------------ P-07 spend
    def _campaign_spend(self, business_id: str, campaign_id: str) -> dict:
        """Actual + committed spend for one campaign, read from
        P-07 expense records tagged with the campaign project_ref.
        P-17 stores no spend of its own (§21)."""
        project_ref = f"{C.CAMPAIGN_PROJECT_REF_PREFIX}{campaign_id}"
        expenses, _total = self._financial.expenses.list_expenses(
            business_id, limit=1000)
        paid = 0
        committed = 0
        count = 0
        for row in expenses:
            if row.get("project_ref") != project_ref:
                continue
            if row.get("kind") not in FC.P_AND_L_EXPENSE_KINDS:
                continue
            if row.get("payment_status") == "paid":
                paid += int(row.get("amount_minor") or 0)
                count += 1
            elif row.get("payment_status") == "committed":
                committed += int(row.get("amount_minor") or 0)
        return {"actual_spend_minor": paid,
                "committed_spend_minor": committed,
                "expense_records": count,
                "source": "P-07 expense records (paid P&L kinds) with "
                          f"project_ref {project_ref}"}

    def _eligible_spend(self, business_id: str, *,
                        campaign_id: str | None = None) -> int:
        """Eligible acquisition spend for CAC (§17/§27): P-07 paid
        P&L expenses in the configured marketing categories,
        optionally scoped to one campaign's project_ref."""
        categories = set(self.get_settings()["cac_expense_categories"])
        expenses, _total = self._financial.expenses.list_expenses(
            business_id, limit=1000)
        total = 0
        for row in expenses:
            if row.get("category") not in categories:
                continue
            if row.get("kind") not in FC.P_AND_L_EXPENSE_KINDS:
                continue
            if row.get("payment_status") != "paid":
                continue
            if campaign_id is not None and row.get(
                    "project_ref") != (f"{C.CAMPAIGN_PROJECT_REF_PREFIX}"
                                       f"{campaign_id}"):
                continue
            total += int(row.get("amount_minor") or 0)
        return total

    # ------------------------------------------------------ agents (§12)
    def seed_agent_templates(self) -> dict:
        """Seed the 17 §12 marketing roles as P-04 agent templates
        through the existing factory (idempotent by name). Roles
        receive only existing catalogue capabilities; the outreach
        role gets no external-send capability because none exists.
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
                SYSTEM_PRINCIPAL, name=role["name"], category="growth",
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
        self._require_reader(principal, "growth.agents")
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
                "external_send_capability": "none — no external-send "
                "capability exists in the P-04 catalogue"})
        return {"items": items, "count": len(items),
                "note": "roles are P-04 Agent Factory templates "
                        "(seeded by P-17); P-17 builds no separate "
                        "agent orchestration (§12)"}

    # ---------------------------------------------------------- status
    def engine_status(self, principal: Principal) -> dict:
        self._require_reader(principal, "growth.status")
        settings = self.get_settings()
        session = self._session_factory()
        try:
            counts = {
                "campaigns": session.query(MarketingCampaign).count(),
                "leads": session.query(GrowthLead).count(),
                "customers": session.query(CrmCustomer).count(),
                "content_items": session.query(ContentItem).count(),
                "partnerships": session.query(Partnership).count(),
            }
        finally:
            session.close()
        return {
            "engine": C.ENGINE_NAME,
            "autonomy_level": settings["autonomy_level"],
            "all_campaigns_paused": settings["all_campaigns_paused"],
            "communications_stopped": settings["communications_stopped"],
            "outreach_suspended": settings["outreach_suspended"],
            "marketing_spend_frozen": settings["marketing_spend_frozen"],
            "profitability_gate": self._gate(),
            "financial_authority": "P-07",
            "business_authority": "P-06",
            "experiment_authority": "P-08",
            "economy_authority": "P-16 (profitability gate consumed live)",
            "execution_capability": "none — research, preparation, "
                                    "governed approvals and measurement "
                                    "only; no platform is connected, no "
                                    "message is sent, no spend executes "
                                    "outside P-07",
            "counts": counts,
            "generated_at": utcnow().isoformat(),
        }

    def integrations(self, principal: Principal) -> dict:
        self._require_reader(principal, "growth.integrations")
        return {"items": [{**item, "state": "not_configured",
                           "state_label": "REQUIRES OWNER CONFIGURATION"}
                          for item in C.INTEGRATIONS],
                "note": "no external marketing platform, transport or "
                        "data feed is connected; the engine never "
                        "simulates one"}
