"""SQLAlchemy models for the P-18 Customer Experience, Service
Delivery & Customer Success Engine tables.

One additive migration creates these tables; no P-01..P-17 table is
altered. P-18 is the post-purchase service layer over P-06
(businesses), P-07 (money), P-09 (memory), P-12 (workflows) and
P-17 (customers), so its tables hold only state no earlier phase
owns: lifecycle templates, onboardings, fulfillments, support
tickets and their messages, knowledge articles, grounded support
answers, operational communications, feedback, customer health
snapshots, service incidents, resolution/recovery cases, SLA
policies, quality reviews and customer success tasks.

Discipline carried from P-07/P-13/P-16/P-17:

* **Customers are P-17's.** Every customer-scoped row references
  ``crm_customers.id``; P-18 creates no customer store, no copy
  path exists, and a customer of business A is never visible to
  business B (parent/child business match is enforced in-service).
* **No money columns at all.** Refund and goodwill recommendations
  store references and basis only; amounts are supplied by the
  owner at execution time and pass straight into P-07
  (``create_refund`` / ``request_spend``), which stores the money
  fact. A named test asserts no P-18 column is a money column.
* **No execution state.** Approvals are P-01 records (only the id
  is referenced), escalations are P-12 workflows (only the id is
  referenced), and no communication is ever recorded as sent —
  no transport is configured.
* **Scores are labelled evidence, never truth.** Feedback rows
  carry their source (recorded | owner_declared) and fixture flag;
  health snapshots persist their factors and evidence; quality
  reviews persist their method.
* Cross-engine references are plain indexed ids, so the migration
  cycle never entangles P-18 with earlier tables' lifecycles.
"""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class CxLifecycleTemplate(Base, TimestampMixin):
    """One §3 configurable lifecycle template of one business.
    ``stages`` is an ordered list of {key, label, kind} where kind
    is purchase|onboarding|verification|preparation|fulfillment|
    delivery|notification|assistance|satisfaction|success."""

    __tablename__ = "cx_lifecycle_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    business_model: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    stages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CxOnboarding(Base, TimestampMixin):
    """One §4 onboarding workflow for one P-17 customer. ``steps``
    mirrors the template's onboarding-relevant stages as
    {key, label, status, completed_at}; status is the workflow
    state (not_started|in_progress|completed|stalled|failed)."""

    __tablename__ = "cx_onboardings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    template_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    template_source: Mapped[str] = mapped_column(
        String(24), nullable=False, default="business_template")
    # template_source: business_template|system_default
    steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="not_started", index=True)
    assistance_needed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CxFulfillment(Base, TimestampMixin):
    """One §5 fulfillment record (physical | digital | service).
    Status claims carry ``status_source`` (manual | owner_declared |
    integration): unverified stays labelled unverified, and no
    shipment or delivery fact is ever fabricated."""

    __tablename__ = "cx_fulfillments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="received", index=True)
    # status: received|preparing|in_progress|shipped|delivered|
    # completed|failed|returned
    status_source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    revenue_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    order_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tracking_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    due_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    delivered_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    milestones: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # milestones (service kind): {key, label, status, completed_at}
    assigned_to: Mapped[str | None] = mapped_column(String(120), nullable=True)
    acceptance: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # acceptance: pending|accepted|rejected
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CxSlaPolicy(Base, TimestampMixin):
    """One §7 SLA policy of one business, owner-configured only.
    There are no seeded defaults anywhere in P-18: a business with
    no policy reports ``not_configured`` and its compliance metrics
    are NOT_AVAILABLE. ``category`` may be a ticket category or
    ``*`` for the business-wide policy."""

    __tablename__ = "cx_sla_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="*", index=True)
    first_response_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="owner_configured")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CxTicket(Base, TimestampMixin):
    """One §7 support case. Priority is computed from declared
    factors (``priority_factors``) by the deterministic scoring in
    ``experience/scoring.py`` — the breakdown is stored so the
    level is always explainable. SLA fields are computed against
    the business's configured policy at read/evaluation time."""

    __tablename__ = "cx_tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="medium", index=True)
    priority_factors: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="new", index=True)
    # status: new|classified|assigned|in_progress|
    # waiting_for_customer|escalated|resolved|closed
    assigned_to: Mapped[str | None] = mapped_column(String(120), nullable=True)
    related_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    first_response_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resolved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    closed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reopened_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    escalation_workflow_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CxTicketMessage(Base, TimestampMixin):
    """One message on a support case (§7 conversation history).
    ``internal`` notes are never customer-facing copy."""

    __tablename__ = "cx_ticket_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    ticket_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    author_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # author_kind: customer|owner|agent|system
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CxKnowledgeArticle(Base, TimestampMixin):
    """One §13 knowledge article of one business. Only
    ``approval_status == approved`` articles may ground a support
    answer; version increments on every content edit and edits of
    an approved article return it to draft (policy-sensitive
    content is never silently republished)."""

    __tablename__ = "cx_knowledge_articles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="general", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    approval_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    # approval_status: draft|approved|retired
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="current")
    # review_status: current|stale
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CxSupportAnswer(Base, TimestampMixin):
    """One §6 grounded support answer. The answer text is composed
    extractively from approved articles; ``article_refs`` pins the
    exact article ids + versions used, and ``confidence_class``
    is one of verified | partially_verified |
    insufficient_information | human_review_required."""

    __tablename__ = "cx_support_answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    ticket_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    answer_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    article_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence_class: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CxCommunication(Base, TimestampMixin):
    """One §8 operational/service communication. No transport is
    configured, so a record can only ever be ``queued`` or
    ``dispatch_blocked`` — never sent or delivered. Consent,
    suppression, opt-out, dedupe and frequency checks run before
    queueing; sensitive kinds require a P-01 approval."""

    __tablename__ = "cx_communications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(24), nullable=False, default="email")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    dedupe_key: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    related_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dispatch_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CxFeedback(Base, TimestampMixin):
    """One §10 feedback record. ``score`` is the customer's own
    recorded score (CSAT 1–5, NPS 0–10, effort 1–5) or None for
    comment-only kinds. ``source`` is recorded | owner_declared —
    AI-estimated sentiment does not exist in P-18."""

    __tablename__ = "cx_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    # kind: csat|nps|effort|product|service|support|delivery|
    # complaint|feature_request
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="recorded")
    related_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CxHealthSnapshot(Base, TimestampMixin):
    """One §12 customer health classification, computed from
    recorded P-18/P-07 signals only. It is a service-health
    classification with persisted factors and evidence — never a
    churn prediction and never presented as a customer decision."""

    __tablename__ = "cx_health_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    classification: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    # classification: healthy|stable|needs_attention|at_risk|
    # critical|insufficient_data
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    factors: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    recommended_action: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CxIncident(Base, TimestampMixin):
    """One §5/§7/§11 actionable service incident, raised by the
    deterministic evaluation pass or recorded manually. Detection
    is idempotent: one open incident per (kind, related record)."""

    __tablename__ = "cx_incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # kind: delayed_fulfillment|failed_provisioning|
    # missing_deliverable|unassigned_work|sla_breach|
    # onboarding_stalled|repeated_failure
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    # status: open|acknowledged|resolved
    related_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    related_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    detected_by: Mapped[str] = mapped_column(String(24), nullable=False, default="evaluation")
    resolved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CxResolution(Base, TimestampMixin):
    """One §11 resolution / service-recovery case. Financial
    actions are recommendations until the owner approves and P-07
    executes: for a refund the case references the P-07 revenue
    record and stores only the refund id P-07 returns; for
    goodwill it stores only the P-07 spending-request id. No
    amount is ever stored here (DECISION D2)."""

    __tablename__ = "cx_resolutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    ticket_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    incident_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    problem_class: Mapped[str] = mapped_column(String(40), nullable=False, default="general")
    root_cause_group: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # root_cause_group: product|service|process|fulfillment_
    # provider|technical|communication|human_error|policy_
    # ambiguity — a grouping hypothesis, never proven causation
    action_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # action_kind: replacement|redelivery|technical_assistance|
    # service_correction|account_restoration|human_escalation|
    # refund_recommendation|goodwill_recommendation
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="recommended", index=True)
    # status: recommended|approved|executed|rejected|verified|closed
    basis: Mapped[str] = mapped_column(String(16), nullable=False, default="na")
    # basis (refunds): full|partial|na
    revenue_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    p07_refund_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    p07_spending_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outcome: Mapped[str] = mapped_column(Text, nullable=False, default="")
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CxQualityReview(Base, TimestampMixin):
    """One §9 QA sampling review of a support case. Dimension
    scores are an internal reviewer's recorded assessment under
    the documented method in P18_TEST_PLAN.md / the quality doc —
    never an AI-generated satisfaction claim."""

    __tablename__ = "cx_quality_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    ticket_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    dimensions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # dimensions: accuracy|completeness|clarity|relevance|
    # resolution_effectiveness|professionalism|consistency|
    # customer_effort|timeliness|policy_compliance -> 0..5
    method: Mapped[str] = mapped_column(String(200), nullable=False, default="manual_sample_review")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class CxSuccessTask(Base, TimestampMixin):
    """One §12 proactive customer-success task (internal work,
    created by recommendation or by the owner). Customer-facing
    follow-through still goes through the governed communication
    path; this record never contacts anyone."""

    __tablename__ = "cx_success_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # kind: onboarding_assistance|product_education|troubleshoot|
    # service_review|human_support|configuration_guidance
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    # status: open|done|cancelled
    due_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="owner")
    # source: owner|health_evaluation|incident|ticket
    related_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
