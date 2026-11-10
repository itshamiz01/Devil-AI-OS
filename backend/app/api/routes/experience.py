"""P-18 Customer Experience, Service Delivery & Customer Success
Engine API.

Route map under /api/v1/experience:
- status / settings / integrations / agent-roles
- lifecycle templates (§3), onboarding (§3/§4), fulfilment (§5)
- evaluation pass (incidents, SLA breaches, stalls — §18) and
  incident handling (§13 of the plan: delivery incidents)
- SLA policies + compliance (§7), tickets + messages (§7),
  escalation into P-12 workflows
- knowledge base (§13) and the grounded support assistant (§6)
- communications (§10: queue + honestly blocked dispatch),
  proactive candidates (§11), feedback (§12)
- resolutions (§8) with approval and P-07 execution, quality
  reviews (§15), success tasks, improvement insights (§19)
- metrics (§16), customer health (§9), customer 360, per-business
  and portfolio overviews (§17)

Permissions mirror the house pattern: read = read_business_data,
write = modify_business_data, govern = approve_actions. The
service additionally enforces owner-only writes and reads, and
the cross-business isolation rule — routes never widen service
rules. Nothing here moves money: refunds and goodwill exist
only as P-07 records created through P-07's own paths, and
customers are P-17 records referenced by id.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict

from ...core.application import Application
from ...experience.service import ExperienceService
from ...permissions.models import Permission, Principal
from ..dependencies import (
    correlation_id, get_application, require_permission,
)
from ..schemas.common import ok

router = APIRouter(tags=["experience"])

READ = require_permission(Permission.READ_BUSINESS_DATA)
WRITE = require_permission(Permission.MODIFY_BUSINESS_DATA)
GOVERN = require_permission(Permission.APPROVE_ACTIONS)


def _svc(application: Application) -> ExperienceService:
    return application.experience


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SettingsIn(_In):
    autonomy_level: int | None = None
    communications_stopped: bool | None = None
    onboarding_stall_hours: int | None = None
    unassigned_work_hours: int | None = None
    comm_frequency_limit_per_30d: int | None = None
    feedback_request_interval_days: int | None = None
    health_weights: dict | None = None


class TemplateIn(_In):
    business_id: str | None = None
    name: str | None = None
    business_model: str | None = None
    stages: list | None = None
    is_default: bool = False
    is_fixture: bool = False


class OnboardingIn(_In):
    customer_id: str
    business_model: str | None = None
    template_id: str | None = None
    is_fixture: bool = False


class OnboardingStepIn(_In):
    step_key: str
    status: str | None = None


class OnboardingUpdateIn(_In):
    status: str | None = None
    assistance_needed: bool | None = None


class StatusIn(_In):
    status: str


class FulfillmentIn(_In):
    customer_id: str | None = None
    kind: str | None = None
    title: str | None = None
    status: str | None = None
    status_source: str | None = None
    revenue_id: str | None = None
    order_ref: str | None = None
    tracking_ref: str | None = None
    due_at: str | None = None
    assigned_to: str | None = None
    milestones: list | None = None
    is_fixture: bool = False


class FulfillmentTransitionIn(_In):
    status: str | None = None
    status_source: str | None = None
    tracking_ref: str | None = None
    delivered_at: str | None = None
    assigned_to: str | None = None


class AcceptanceIn(_In):
    acceptance: str


class MilestoneIn(_In):
    milestone: str
    status: str | None = None


class SlaPolicyIn(_In):
    category: str | None = None
    first_response_minutes: int | None = None
    resolution_minutes: int | None = None


class TicketIn(_In):
    customer_id: str | None = None
    category: str | None = None
    subject: str | None = None
    description: str | None = None
    priority_factors: dict | None = None
    assigned_to: str | None = None
    related_ref: str | None = None
    is_fixture: bool = False


class AssignIn(_In):
    assigned_to: str


class MessageIn(_In):
    author_kind: str | None = None
    body: str | None = None
    internal: bool = False


class ReasonIn(_In):
    reason: str | None = None


class ArticleIn(_In):
    title: str | None = None
    content: str | None = None
    category: str | None = None
    source: str | None = None
    is_fixture: bool = False


class ReviewIn(_In):
    review_status: str


class AskIn(_In):
    question: str
    customer_id: str | None = None
    ticket_id: str | None = None
    category: str | None = None
    is_fixture: bool = False


class CommunicationIn(_In):
    customer_id: str
    kind: str | None = None
    channel: str | None = None
    body: str | None = None
    related_ref: str | None = None
    approval_id: str | None = None
    is_fixture: bool = False


class FeedbackIn(_In):
    customer_id: str | None = None
    kind: str | None = None
    score: int | None = None
    comment: str | None = None
    source: str | None = None
    related_ref: str | None = None
    is_fixture: bool = False


class HealthIn(_In):
    declared_signals: list | None = None


class QualityIn(_In):
    ticket_id: str | None = None
    dimensions: dict | None = None
    method: str | None = None
    notes: str | None = None


class ResolutionIn(_In):
    customer_id: str | None = None
    ticket_id: str | None = None
    incident_id: str | None = None
    problem_class: str | None = None
    root_cause_group: str | None = None
    action_kind: str | None = None
    basis: str | None = None
    revenue_id: str | None = None
    rationale: str | None = None
    is_fixture: bool = False


class ApprovalIn(_In):
    approval_id: str | None = None
    approval_action: str | None = None
    approval_target: str | None = None


class ExecuteIn(_In):
    revenue_id: str | None = None
    amount_minor: int | None = None
    currency: str | None = None


class VerifyIn(_In):
    outcome: str | None = None
    verified: bool = True


class SuccessTaskIn(_In):
    customer_id: str | None = None
    kind: str | None = None
    title: str | None = None
    due_at: str | None = None
    source: str | None = None
    related_ref: str | None = None
    via_workflow: bool = False
    is_fixture: bool = False


# ---------------------------------------------------------------- status
@router.get("/experience/status")
def status(request: Request,
           application: Application = Depends(get_application),
           principal: Principal = Depends(READ)):
    return ok(_svc(application).engine_status(principal),
              correlation_id(request))


@router.get("/experience/settings")
def get_settings(request: Request,
                 application: Application = Depends(get_application),
                 principal: Principal = Depends(READ)):
    return ok(_svc(application).get_settings(), correlation_id(request))


@router.post("/experience/settings")
def update_settings(body: SettingsIn, request: Request,
                    application: Application = Depends(get_application),
                    principal: Principal = Depends(GOVERN)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return ok(_svc(application).update_settings(principal, data),
              correlation_id(request))


@router.get("/experience/integrations")
def integrations(request: Request,
                 application: Application = Depends(get_application),
                 principal: Principal = Depends(READ)):
    return ok(_svc(application).integrations(principal),
              correlation_id(request))


@router.get("/experience/agent-roles")
def agent_roles(request: Request,
                application: Application = Depends(get_application),
                principal: Principal = Depends(READ)):
    return ok(_svc(application).agent_roles(principal),
              correlation_id(request))


@router.get("/experience/overview")
def portfolio_overview(request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(READ)):
    return ok(_svc(application).portfolio_overview(principal),
              correlation_id(request))


# ---------------------------------------------------------------- templates & onboarding
@router.post("/experience/businesses/{business_id}/templates")
def create_template(business_id: str, body: TemplateIn, request: Request,
                    application: Application = Depends(get_application),
                    principal: Principal = Depends(WRITE)):
    return ok(_svc(application).create_template(
        principal, business_id, body.model_dump()),
        correlation_id(request))


@router.get("/experience/businesses/{business_id}/templates")
def list_templates(business_id: str, request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(READ)):
    return ok(_svc(application).list_templates(principal, business_id),
              correlation_id(request))


@router.post("/experience/businesses/{business_id}/onboardings")
def start_onboarding(business_id: str, body: OnboardingIn,
                     request: Request,
                     application: Application = Depends(get_application),
                     principal: Principal = Depends(WRITE)):
    return ok(_svc(application).start_onboarding(
        principal, business_id, body.model_dump()),
        correlation_id(request))


@router.get("/experience/businesses/{business_id}/onboardings")
def list_onboardings(business_id: str, request: Request,
                     status: str | None = Query(default=None),
                     application: Application = Depends(get_application),
                     principal: Principal = Depends(READ)):
    return ok(_svc(application).list_onboardings(
        principal, business_id, status=status),
        correlation_id(request))


@router.get("/experience/businesses/{business_id}/onboarding-dashboard")
def onboarding_dashboard(business_id: str, request: Request,
                         application: Application =
                         Depends(get_application),
                         principal: Principal = Depends(READ)):
    return ok(_svc(application).onboarding_dashboard(
        principal, business_id), correlation_id(request))


@router.post("/experience/onboardings/{onboarding_id}/steps")
def update_step(onboarding_id: str, body: OnboardingStepIn,
                request: Request,
                application: Application = Depends(get_application),
                principal: Principal = Depends(WRITE)):
    return ok(_svc(application).update_onboarding_step(
        principal, onboarding_id, body.step_key,
        body.status or "completed"),
        correlation_id(request))


@router.post("/experience/onboardings/{onboarding_id}/status")
def onboarding_status(onboarding_id: str, body: StatusIn, request: Request,
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(WRITE)):
    return ok(_svc(application).update_onboarding(
        principal, onboarding_id, {"status": body.status}),
        correlation_id(request))


@router.post("/experience/onboardings/{onboarding_id}/assistance")
def onboarding_assistance(onboarding_id: str, body: ReasonIn,
                          request: Request,
                          application: Application =
                          Depends(get_application),
                          principal: Principal = Depends(WRITE)):
    return ok(_svc(application).update_onboarding(
        principal, onboarding_id, {"assistance_needed": True}),
        correlation_id(request))


# ---------------------------------------------------------------- fulfilment
@router.post("/experience/businesses/{business_id}/fulfillments")
def create_fulfillment(business_id: str, body: FulfillmentIn,
                       request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(WRITE)):
    return ok(_svc(application).create_fulfillment(
        principal, business_id, body.model_dump()),
        correlation_id(request))


@router.get("/experience/businesses/{business_id}/fulfillments")
def list_fulfillments(business_id: str, request: Request,
                      status: str | None = Query(default=None),
                      customer_id: str | None = Query(default=None),
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(READ)):
    return ok(_svc(application).list_fulfillments(
        principal, business_id, status=status, customer_id=customer_id),
        correlation_id(request))


@router.post("/experience/fulfillments/{fulfillment_id}/transition")
def fulfillment_transition(fulfillment_id: str,
                           body: FulfillmentTransitionIn,
                           request: Request,
                           application: Application =
                           Depends(get_application),
                           principal: Principal = Depends(WRITE)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return ok(_svc(application).transition_fulfillment(
        principal, fulfillment_id, data),
        correlation_id(request))


@router.post("/experience/fulfillments/{fulfillment_id}/milestones")
def fulfillment_milestone(fulfillment_id: str, body: MilestoneIn,
                          request: Request,
                          application: Application =
                          Depends(get_application),
                          principal: Principal = Depends(WRITE)):
    return ok(_svc(application).update_milestone(
        principal, fulfillment_id, body.milestone,
        body.status or "completed"),
        correlation_id(request))


@router.post("/experience/fulfillments/{fulfillment_id}/acceptance")
def fulfillment_acceptance(fulfillment_id: str, body: AcceptanceIn,
                           request: Request,
                           application: Application =
                           Depends(get_application),
                           principal: Principal = Depends(WRITE)):
    return ok(_svc(application).set_acceptance(
        principal, fulfillment_id, body.acceptance),
        correlation_id(request))


# ---------------------------------------------------------------- evaluation & incidents
@router.post("/experience/businesses/{business_id}/evaluate")
def evaluate(business_id: str, request: Request,
             application: Application = Depends(get_application),
             principal: Principal = Depends(GOVERN)):
    return ok(_svc(application).evaluate(principal, business_id),
              correlation_id(request))


@router.post("/experience/evaluate")
def evaluate_all(request: Request,
                 application: Application = Depends(get_application),
                 principal: Principal = Depends(GOVERN)):
    return ok(_svc(application).evaluate(principal),
              correlation_id(request))


@router.get("/experience/businesses/{business_id}/incidents")
def list_incidents(business_id: str, request: Request,
                   status: str | None = Query(default=None),
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(READ)):
    return ok(_svc(application).list_incidents(
        principal, business_id, status=status), correlation_id(request))


@router.post("/experience/incidents/{incident_id}/transition")
def incident_transition(incident_id: str, body: StatusIn, request: Request,
                        application: Application =
                        Depends(get_application),
                        principal: Principal = Depends(WRITE)):
    return ok(_svc(application).transition_incident(
        principal, incident_id, body.status), correlation_id(request))


# ---------------------------------------------------------------- SLA & tickets
@router.post("/experience/businesses/{business_id}/sla-policies")
def upsert_sla(business_id: str, body: SlaPolicyIn, request: Request,
               application: Application = Depends(get_application),
               principal: Principal = Depends(GOVERN)):
    return ok(_svc(application).upsert_sla_policy(
        principal, business_id, body.model_dump()),
        correlation_id(request))


@router.get("/experience/businesses/{business_id}/sla-policies")
def list_sla(business_id: str, request: Request,
             application: Application = Depends(get_application),
             principal: Principal = Depends(READ)):
    return ok(_svc(application).list_sla_policies(principal, business_id),
              correlation_id(request))


@router.get("/experience/businesses/{business_id}/sla-compliance")
def sla_compliance(business_id: str, request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(READ)):
    return ok(_svc(application).sla_compliance(principal, business_id),
              correlation_id(request))


@router.post("/experience/businesses/{business_id}/tickets")
def create_ticket(business_id: str, body: TicketIn, request: Request,
                  application: Application = Depends(get_application),
                  principal: Principal = Depends(WRITE)):
    return ok(_svc(application).create_ticket(
        principal, business_id, body.model_dump()),
        correlation_id(request))


@router.get("/experience/businesses/{business_id}/tickets")
def list_tickets(business_id: str, request: Request,
                 status: str | None = Query(default=None),
                 category: str | None = Query(default=None),
                 customer_id: str | None = Query(default=None),
                 application: Application = Depends(get_application),
                 principal: Principal = Depends(READ)):
    return ok(_svc(application).list_tickets(
        principal, business_id, status=status, category=category,
        customer_id=customer_id), correlation_id(request))


@router.get("/experience/tickets/{ticket_id}")
def get_ticket(ticket_id: str, request: Request,
               application: Application = Depends(get_application),
               principal: Principal = Depends(READ)):
    return ok(_svc(application).get_ticket(principal, ticket_id),
              correlation_id(request))


@router.post("/experience/tickets/{ticket_id}/transition")
def ticket_transition(ticket_id: str, body: StatusIn, request: Request,
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(WRITE)):
    return ok(_svc(application).transition_ticket(
        principal, ticket_id, body.status), correlation_id(request))


@router.post("/experience/tickets/{ticket_id}/assign")
def ticket_assign(ticket_id: str, body: AssignIn, request: Request,
                  application: Application = Depends(get_application),
                  principal: Principal = Depends(WRITE)):
    return ok(_svc(application).assign_ticket(
        principal, ticket_id, body.assigned_to), correlation_id(request))


@router.post("/experience/tickets/{ticket_id}/messages")
def ticket_message(ticket_id: str, body: MessageIn, request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(WRITE)):
    return ok(_svc(application).add_ticket_message(
        principal, ticket_id, body.model_dump()), correlation_id(request))


@router.post("/experience/tickets/{ticket_id}/escalate")
def ticket_escalate(ticket_id: str, body: ReasonIn, request: Request,
                    application: Application = Depends(get_application),
                    principal: Principal = Depends(GOVERN)):
    return ok(_svc(application).escalate_ticket(
        principal, ticket_id, body.model_dump()), correlation_id(request))


# ---------------------------------------------------------------- knowledge & assistant
@router.post("/experience/businesses/{business_id}/articles")
def create_article(business_id: str, body: ArticleIn, request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(WRITE)):
    return ok(_svc(application).create_article(
        principal, business_id, body.model_dump()),
        correlation_id(request))


@router.get("/experience/businesses/{business_id}/articles")
def list_articles(business_id: str, request: Request,
                  approval_status: str | None = Query(default=None),
                  category: str | None = Query(default=None),
                  application: Application = Depends(get_application),
                  principal: Principal = Depends(READ)):
    return ok(_svc(application).list_articles(
        principal, business_id, approval_status=approval_status,
        category=category), correlation_id(request))


@router.get("/experience/businesses/{business_id}/kb-health")
def kb_health(business_id: str, request: Request,
              application: Application = Depends(get_application),
              principal: Principal = Depends(READ)):
    return ok(_svc(application).kb_health(principal, business_id),
              correlation_id(request))


@router.post("/experience/articles/{article_id}")
def update_article(article_id: str, body: ArticleIn, request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(WRITE)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return ok(_svc(application).update_article(principal, article_id,
                                               data),
              correlation_id(request))


@router.post("/experience/articles/{article_id}/approve")
def approve_article(article_id: str, request: Request,
                    application: Application = Depends(get_application),
                    principal: Principal = Depends(GOVERN)):
    return ok(_svc(application).approve_article(principal, article_id),
              correlation_id(request))


@router.post("/experience/articles/{article_id}/retire")
def retire_article(article_id: str, request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(WRITE)):
    return ok(_svc(application).retire_article(principal, article_id),
              correlation_id(request))


@router.post("/experience/articles/{article_id}/review")
def review_article(article_id: str, body: ReviewIn, request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(WRITE)):
    return ok(_svc(application).set_article_review(
        principal, article_id, body.review_status),
        correlation_id(request))


@router.post("/experience/businesses/{business_id}/support/ask")
def ask_support(business_id: str, body: AskIn, request: Request,
                application: Application = Depends(get_application),
                principal: Principal = Depends(WRITE)):
    return ok(_svc(application).ask_support(
        principal, business_id, body.model_dump()),
        correlation_id(request))


@router.get("/experience/businesses/{business_id}/support/answers")
def list_answers(business_id: str, request: Request,
                 application: Application = Depends(get_application),
                 principal: Principal = Depends(READ)):
    return ok(_svc(application).list_answers(principal, business_id),
              correlation_id(request))


# ---------------------------------------------------------------- communications & feedback
@router.post("/experience/businesses/{business_id}/communications")
def queue_communication(business_id: str, body: CommunicationIn,
                        request: Request,
                        application: Application =
                        Depends(get_application),
                        principal: Principal = Depends(WRITE)):
    return ok(_svc(application).queue_communication(
        principal, business_id, body.model_dump()),
        correlation_id(request))


@router.get("/experience/businesses/{business_id}/communications")
def list_communications(business_id: str, request: Request,
                        customer_id: str | None = Query(default=None),
                        application: Application =
                        Depends(get_application),
                        principal: Principal = Depends(READ)):
    return ok(_svc(application).list_communications(
        principal, business_id, customer_id=customer_id),
        correlation_id(request))


@router.post("/experience/communications/{communication_id}/dispatch")
def dispatch_communication(communication_id: str, request: Request,
                           application: Application =
                           Depends(get_application),
                           principal: Principal = Depends(WRITE)):
    return ok(_svc(application).attempt_dispatch(
        principal, communication_id), correlation_id(request))


@router.get("/experience/businesses/{business_id}/proactive")
def proactive(business_id: str, request: Request,
              application: Application = Depends(get_application),
              principal: Principal = Depends(READ)):
    return ok(_svc(application).proactive_candidates(
        principal, business_id), correlation_id(request))


@router.post("/experience/businesses/{business_id}/feedback")
def record_feedback(business_id: str, body: FeedbackIn, request: Request,
                    application: Application = Depends(get_application),
                    principal: Principal = Depends(WRITE)):
    return ok(_svc(application).record_feedback(
        principal, business_id, body.model_dump()),
        correlation_id(request))


@router.get("/experience/businesses/{business_id}/feedback")
def list_feedback(business_id: str, request: Request,
                  customer_id: str | None = Query(default=None),
                  kind: str | None = Query(default=None),
                  application: Application = Depends(get_application),
                  principal: Principal = Depends(READ)):
    return ok(_svc(application).list_feedback(
        principal, business_id, customer_id=customer_id, kind=kind),
        correlation_id(request))


# ---------------------------------------------------------------- resolutions, quality, tasks
@router.post("/experience/businesses/{business_id}/resolutions")
def create_resolution(business_id: str, body: ResolutionIn,
                      request: Request,
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(WRITE)):
    return ok(_svc(application).create_resolution(
        principal, business_id, body.model_dump()),
        correlation_id(request))


@router.get("/experience/businesses/{business_id}/resolutions")
def list_resolutions(business_id: str, request: Request,
                     application: Application = Depends(get_application),
                     principal: Principal = Depends(READ)):
    return ok(_svc(application).list_resolutions(principal, business_id),
              correlation_id(request))


@router.post("/experience/resolutions/{resolution_id}/approve")
def approve_resolution(resolution_id: str, body: ApprovalIn,
                       request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(GOVERN)):
    return ok(_svc(application).approve_resolution(
        principal, resolution_id, body.model_dump()),
        correlation_id(request))


@router.post("/experience/resolutions/{resolution_id}/execute")
def execute_resolution(resolution_id: str, body: ExecuteIn,
                       request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(GOVERN)):
    return ok(_svc(application).execute_resolution(
        principal, resolution_id, body.model_dump()),
        correlation_id(request))


@router.post("/experience/resolutions/{resolution_id}/verify")
def verify_resolution(resolution_id: str, body: VerifyIn, request: Request,
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(WRITE)):
    return ok(_svc(application).verify_resolution(
        principal, resolution_id, body.model_dump()),
        correlation_id(request))


@router.post("/experience/businesses/{business_id}/quality-reviews")
def create_quality(business_id: str, body: QualityIn, request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(WRITE)):
    return ok(_svc(application).create_quality_review(
        principal, business_id, body.model_dump()),
        correlation_id(request))


@router.get("/experience/businesses/{business_id}/quality-reviews")
def list_quality(business_id: str, request: Request,
                 application: Application = Depends(get_application),
                 principal: Principal = Depends(READ)):
    return ok(_svc(application).list_quality_reviews(
        principal, business_id), correlation_id(request))


@router.get("/experience/businesses/{business_id}/quality-summary")
def quality_summary(business_id: str, request: Request,
                    application: Application = Depends(get_application),
                    principal: Principal = Depends(READ)):
    return ok(_svc(application).quality_summary(principal, business_id),
              correlation_id(request))


@router.post("/experience/businesses/{business_id}/success-tasks")
def create_success_task(business_id: str, body: SuccessTaskIn,
                        request: Request,
                        application: Application =
                        Depends(get_application),
                        principal: Principal = Depends(WRITE)):
    return ok(_svc(application).create_success_task(
        principal, business_id, body.model_dump()),
        correlation_id(request))


@router.get("/experience/businesses/{business_id}/success-tasks")
def list_success_tasks(business_id: str, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(READ)):
    return ok(_svc(application).list_success_tasks(
        principal, business_id), correlation_id(request))


@router.post("/experience/success-tasks/{task_id}/complete")
def complete_success_task(task_id: str, request: Request,
                          application: Application =
                          Depends(get_application),
                          principal: Principal = Depends(WRITE)):
    return ok(_svc(application).complete_success_task(principal, task_id),
              correlation_id(request))


# ---------------------------------------------------------------- metrics, health, customers
@router.get("/experience/businesses/{business_id}/metrics")
def metrics(business_id: str, request: Request,
            application: Application = Depends(get_application),
            principal: Principal = Depends(READ)):
    return ok(_svc(application).experience_metrics(principal, business_id),
              correlation_id(request))


@router.get("/experience/businesses/{business_id}/insights")
def insights(business_id: str, request: Request,
             application: Application = Depends(get_application),
             principal: Principal = Depends(READ)):
    return ok(_svc(application).improvement_insights(
        principal, business_id), correlation_id(request))


@router.get("/experience/businesses/{business_id}/overview")
def business_overview(business_id: str, request: Request,
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(READ)):
    return ok(_svc(application).business_overview(principal, business_id),
              correlation_id(request))


@router.post("/experience/businesses/{business_id}/customers/"
             "{customer_id}/health")
def compute_health(business_id: str, customer_id: str, body: HealthIn,
                   request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(WRITE)):
    return ok(_svc(application).compute_health(
        principal, business_id, customer_id, body.model_dump()),
        correlation_id(request))


@router.get("/experience/businesses/{business_id}/customers/"
            "{customer_id}/health")
def latest_health(business_id: str, customer_id: str, request: Request,
                  application: Application = Depends(get_application),
                  principal: Principal = Depends(READ)):
    return ok(_svc(application).latest_health(
        principal, business_id, customer_id), correlation_id(request))


@router.get("/experience/businesses/{business_id}/health")
def health_overview(business_id: str, request: Request,
                    application: Application = Depends(get_application),
                    principal: Principal = Depends(READ)):
    return ok(_svc(application).health_overview(principal, business_id),
              correlation_id(request))


@router.get("/experience/businesses/{business_id}/customers/"
            "{customer_id}")
def customer_detail(business_id: str, customer_id: str, request: Request,
                    application: Application = Depends(get_application),
                    principal: Principal = Depends(READ)):
    return ok(_svc(application).customer_detail(
        principal, business_id, customer_id), correlation_id(request))
