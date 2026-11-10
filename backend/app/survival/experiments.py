"""§9 Experiment management and stop-loss protection.

An experiment is a controlled investment, pre-declared BEFORE it
starts: hypothesis, problem, target customer, expected outcome,
success and failure metrics, minimum evidence, maximum duration,
approved budget, maximum acceptable loss, evaluation schedule and
owner approval status (§9.2) — the Constitution's pre-declaration
rule. The budget is a real P-07 budget, so spend runs through P-07's
machinery; stop-loss (§9.4) is mechanical, checked against P-07
budget utilisation readings: budget exhausted OR loss cap reached OR
time limit OR compliance/security risk OR hypothesis invalidated →
the experiment is STOPPED and further spend authorisation through
P-08 is refused, while P-07's own budget checks refuse overspend
independently. Sunk cost is never an input (§3.1): the stop-loss
evaluation reads only caps and current readings, never "amount
already spent justifies continuing".

Failed experiments are preserved permanently as learning records —
this module exposes no delete path (§9.5/§32 rule 18).
"""
from __future__ import annotations

from datetime import date, timedelta

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.survival import (
    BusinessExperiment, ExperimentEvaluation,
)
from ..database.repositories.survival import (
    ExperimentEvaluationRepository, ExperimentRepository,
)
from ..permissions.models import PrincipalType
from . import constants as C

REQUIRED_FIELDS = [
    "hypothesis", "problem", "target_customer", "expected_outcome",
    "success_metric", "failure_metric", "minimum_evidence",
    "max_duration_days", "approved_budget_minor",
    "max_acceptable_loss_minor", "evaluation_schedule",
]


def experiment_dict(row: BusinessExperiment) -> dict:
    return {
        "id": row.id, "business_id": row.business_id, "name": row.name,
        "status": row.status, "hypothesis": row.hypothesis,
        "problem": row.problem, "target_customer": row.target_customer,
        "expected_outcome": row.expected_outcome,
        "success_metric": row.success_metric,
        "failure_metric": row.failure_metric,
        "minimum_evidence": row.minimum_evidence,
        "max_duration_days": row.max_duration_days,
        "budget_id": row.budget_id,
        "approved_budget_minor": row.approved_budget_minor,
        "max_acceptable_loss_minor": row.max_acceptable_loss_minor,
        "currency": row.currency,
        "operational_requirements": row.operational_requirements,
        "required_agents": row.required_agents,
        "data_sources": row.data_sources,
        "evaluation_schedule": row.evaluation_schedule,
        "declaration_id": row.declaration_id,
        "approval_id": row.approval_id,
        "owner_approved": row.owner_approved,
        "started_on": row.started_on, "stop_reason": row.stop_reason,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
    }


def evaluation_dict(row: ExperimentEvaluation) -> dict:
    return {
        "id": row.id, "experiment_id": row.experiment_id,
        "business_id": row.business_id,
        "classification": row.classification,
        "actual_outcome": row.actual_outcome,
        "observed_metric_value": row.observed_metric_value,
        "actuals": row.actuals, "actuals_source": row.actuals_source,
        "unexpected_findings": row.unexpected_findings,
        "lessons": row.lessons,
        "recommended_next_step": row.recommended_next_step,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
    }


class ExperimentService:
    def __init__(self, session_factory, financial, business, approvals,
                 audit, pause_checker):
        self._session_factory = session_factory
        self._financial = financial
        self._business = business
        self._approvals = approvals
        self._audit = audit
        self._pause_active = pause_checker

    # ------------------------------------------------------------- create
    def create_experiment(self, principal, business_id: str,
                          data: dict) -> dict:
        self._business.get_business(business_id)
        missing = [f for f in REQUIRED_FIELDS
                   if data.get(f) in (None, "", [])]
        if missing:
            raise ValidationError(
                "experiment pre-declaration is incomplete (§9.2); "
                f"missing: {missing}. Nothing runs on a partial "
                "declaration.")
        if int(data["approved_budget_minor"]) <= 0:
            raise ValidationError("approved budget must be positive")
        if int(data["max_acceptable_loss_minor"]) < 0 or \
                int(data["max_acceptable_loss_minor"]) > \
                int(data["approved_budget_minor"]):
            raise ValidationError(
                "maximum acceptable loss must be between 0 and the "
                "approved budget")
        if int(data["max_duration_days"]) <= 0:
            raise ValidationError("maximum duration must be positive")
        currency = data.get("currency") or "INR"
        # Reconcile with the business's P-06 pre-declaration (lock 3):
        # link it, never duplicate it.
        declaration = self._business.approved_declaration(business_id)
        session = self._session_factory()
        try:
            row = ExperimentRepository(session).add(BusinessExperiment(
                business_id=business_id,
                name=data.get("name") or "experiment",
                status="DESIGNED",
                hypothesis=data["hypothesis"], problem=data["problem"],
                target_customer=data["target_customer"],
                expected_outcome=data["expected_outcome"],
                success_metric=data["success_metric"],
                failure_metric=data["failure_metric"],
                minimum_evidence=data["minimum_evidence"],
                max_duration_days=int(data["max_duration_days"]),
                approved_budget_minor=int(data["approved_budget_minor"]),
                max_acceptable_loss_minor=int(
                    data["max_acceptable_loss_minor"]),
                currency=currency,
                operational_requirements=data.get(
                    "operational_requirements") or "",
                required_agents=data.get("required_agents") or [],
                data_sources=data.get("data_sources") or [],
                evaluation_schedule=data["evaluation_schedule"],
                declaration_id=data.get("declaration_id")
                or (declaration.id if declaration else None),
                owner_approved=False,
                created_by=_actor(principal)))
            experiment_id = row.id
        finally:
            session.close()
        self._audit(principal, "survival.experiment_created", "experiment",
                    experiment_id, "allow",
                    "pre-declaration recorded (§9.2)")
        return self.get_experiment(experiment_id)

    def get_experiment(self, experiment_id: str) -> dict:
        session = self._session_factory()
        try:
            row = ExperimentRepository(session).get(experiment_id)
            if row is None:
                raise NotFoundError(
                    f"experiment {experiment_id} not found")
            return experiment_dict(row)
        finally:
            session.close()

    def list_experiments(self, *, business_id: str | None = None,
                         status: str | None = None, limit: int = 50,
                         offset: int = 0):
        session = self._session_factory()
        try:
            filters = {"status": status} if status else None
            rows, total = ExperimentRepository(session).list(
                limit=limit, offset=offset, business_id=business_id,
                filters=filters)
            return [experiment_dict(r) for r in rows], total
        finally:
            session.close()

    # ------------------------------------------------------------ approve
    def approve_experiment(self, principal, experiment_id: str,
                           data: dict) -> dict:
        """Owner approval, hash-bound through P-01 (action
        survival.experiment). Creates the linked P-07 experiment
        budget — the budget is the enforcement surface for stop-loss."""
        experiment = self.get_experiment(experiment_id)
        if experiment["status"] not in ("DESIGNED", "PROPOSED"):
            raise ValidationError(
                f"experiment in status {experiment['status']} cannot "
                "be approved")
        approval_id = data.get("approval_id")
        if approval_id:
            ok = self._verify_approval(experiment, approval_id)
            if not ok:
                self._audit(principal, "survival.experiment_approve",
                            "experiment", experiment_id, "deny",
                            "approval binding invalid or not owner-decided")
                raise PermissionDeniedError(
                    "experiment approval must be a hash-bound P-01 "
                    "approval decided by the owner")
        elif principal.type == PrincipalType.OWNER:
            approval = self._approvals.create(
                principal, action=C.APPROVAL_ACTION_EXPERIMENT,
                resource=experiment["business_id"],
                risk_classification="high",
                reason="P-08 experiment approval (§9.2)",
                requested_permissions=["modify_business_data"],
                parameters={"experiment_id": experiment_id,
                            "business_id": experiment["business_id"],
                            "approved_budget_minor":
                                experiment["approved_budget_minor"]})
            self._approvals.decide(approval.id, principal, True)
            approval_id = approval.id
        else:
            raise PermissionDeniedError(
                "experiments require owner approval before they run "
                "(§9.2); an agent cannot approve its own experiment")
        from ..financial.money import Money
        budget = self._financial.budgets.create_budget(principal, {
            "scope_type": "experiment", "scope_ref": experiment_id,
            "business_id": experiment["business_id"],
            "name": f"experiment:{experiment['name']}",
            "amount": Money(experiment["approved_budget_minor"],
                            experiment["currency"]),
            "period_start": date.today().isoformat(),
            "period_end": (date.today() + timedelta(
                days=experiment["max_duration_days"])).isoformat(),
            "approval_requirement": "level_2",
        })
        session = self._session_factory()
        try:
            repo = ExperimentRepository(session)
            row = repo.get(experiment_id)
            row.status = "APPROVED"
            row.owner_approved = True
            row.approval_id = approval_id
            row.budget_id = budget["id"]
            repo.save(row)
        finally:
            session.close()
        self._audit(principal, "survival.experiment_approved",
                    "experiment", experiment_id, "allow",
                    f"P-07 budget {budget['id']} created as the "
                    "stop-loss enforcement surface")
        return self.get_experiment(experiment_id)

    def _verify_approval(self, experiment: dict, approval_id: str) -> bool:
        try:
            approval = self._approvals.get(approval_id)
        except Exception:
            return False
        params = {"experiment_id": experiment["id"],
                  "business_id": experiment["business_id"],
                  "approved_budget_minor":
                      experiment["approved_budget_minor"]}
        if not self._approvals.verify_binding(
                approval, C.APPROVAL_ACTION_EXPERIMENT,
                experiment["business_id"], params):
            return False
        return approval.status == "approved" and bool(
            approval.approver_id
            and approval.approver_id.startswith("owner:"))

    # -------------------------------------------------------------- start
    def start_experiment(self, principal, experiment_id: str) -> dict:
        experiment = self.get_experiment(experiment_id)
        if not experiment["owner_approved"]:
            raise PermissionDeniedError(
                "an unapproved experiment cannot start (§9.2)")
        if experiment["status"] != "APPROVED":
            raise ValidationError(
                f"experiment in status {experiment['status']} cannot "
                "start")
        if self._pause_active(experiment["business_id"]):
            raise PermissionDeniedError(
                "emergency pause is active for this business (§25.2)")
        session = self._session_factory()
        try:
            repo = ExperimentRepository(session)
            row = repo.get(experiment_id)
            row.status = "RUNNING"
            row.started_on = date.today().isoformat()
            repo.save(row)
        finally:
            session.close()
        self._audit(principal, "survival.experiment_started",
                    "experiment", experiment_id, "allow", "RUNNING")
        return self.get_experiment(experiment_id)

    # ----------------------------------------------------------- stop-loss
    def check_stop_loss(self, principal, experiment_id: str) -> dict:
        """Mechanical stop-loss evaluation (§9.4). Inputs are caps
        from the pre-declaration and current P-07 budget readings —
        never sunk-cost reasoning. Tripping a condition stops the
        experiment and blocks further P-08 spend authorisation."""
        experiment = self.get_experiment(experiment_id)
        if experiment["status"] not in ("RUNNING", "OBSERVING",
                                        "APPROVED"):
            return {"experiment_id": experiment_id,
                    "status": experiment["status"],
                    "stop_loss_tripped": False,
                    "note": "experiment is not running"}
        utilisation = None
        spent = 0
        if experiment["budget_id"]:
            utilisation = self._financial.budgets.budget_utilisation(
                experiment["budget_id"])
            spent = utilisation["spent_minor"] + \
                utilisation["committed_minor"]
        reasons: list[str] = []
        if utilisation is not None and \
                spent >= experiment["approved_budget_minor"]:
            reasons.append("budget_exhausted")
        # Loss reading: experiment-budget spend is the maximum-loss
        # exposure (§9.4); the cap compares the same P-07 reading.
        if utilisation is not None and \
                spent >= experiment["max_acceptable_loss_minor"] > 0:
            reasons.append("max_loss_reached")
        if experiment["started_on"]:
            deadline = date.fromisoformat(experiment["started_on"]) \
                + timedelta(days=experiment["max_duration_days"])
            if date.today() > deadline:
                reasons.append("time_limit")
        tripped = bool(reasons)
        if tripped and experiment["status"] in ("RUNNING", "OBSERVING",
                                                "APPROVED"):
            session = self._session_factory()
            try:
                repo = ExperimentRepository(session)
                row = repo.get(experiment_id)
                row.status = "STOPPED"
                row.stop_reason = ", ".join(reasons)
                repo.save(row)
            finally:
                session.close()
            self._audit(principal, "survival.experiment_stop_loss",
                        "experiment", experiment_id, "allow",
                        f"stop-loss tripped: {reasons}")
        return {"experiment_id": experiment_id,
                "status": "STOPPED" if tripped else experiment["status"],
                "stop_loss_tripped": tripped, "reasons": reasons,
                "budget_utilisation": utilisation,
                "note": "further spend is refused: the experiment is "
                        "STOPPED in P-08 and the linked P-07 budget's "
                        "own checks refuse overspend (§9.4)"}

    def authorise_spend(self, principal, experiment_id: str,
                        amount_minor: int) -> dict:
        """The P-08 gate in front of experiment spend: a stopped,
        unapproved or budget-exceeding spend is refused here, before
        P-07's request_spend applies its own checks."""
        experiment = self.get_experiment(experiment_id)
        if experiment["status"] in ("STOPPED", "FAILED", "SUCCESSFUL",
                                    "INCONCLUSIVE", "ARCHIVED"):
            self._audit(principal, "survival.experiment_spend",
                        "experiment", experiment_id, "deny",
                        f"experiment is {experiment['status']}; spend "
                        "is blocked (§9.4)")
            raise PermissionDeniedError(
                f"experiment is {experiment['status']}; further spend "
                "is blocked. A new experiment requires a new "
                "justification and authorisation (§26.4 S4)")
        if experiment["status"] not in ("RUNNING", "OBSERVING"):
            raise PermissionDeniedError(
                "experiment is not running; spend is not authorised")
        check = self.check_stop_loss(principal, experiment_id)
        if check["stop_loss_tripped"]:
            raise PermissionDeniedError(
                f"stop-loss tripped ({check['reasons']}); spend blocked")
        utilisation = self._financial.budgets.budget_utilisation(
            experiment["budget_id"])
        remaining = utilisation["remaining_minor"]
        if amount_minor > remaining:
            raise PermissionDeniedError(
                "spend exceeds the experiment budget's remaining "
                "amount (P-07 reading); blocked (§9.4)")
        return {"experiment_id": experiment_id, "authorised": True,
                "amount_minor": amount_minor,
                "budget_remaining_minor": remaining,
                "note": "authorisation is a gate decision; the spend "
                        "itself runs through P-07 request_spend"}

    def stop_experiment(self, principal, experiment_id: str,
                        reason: str = "manual") -> dict:
        if reason not in C.STOP_REASONS:
            raise ValidationError(
                f"unknown stop reason {reason!r}; supported: "
                f"{C.STOP_REASONS}")
        session = self._session_factory()
        try:
            repo = ExperimentRepository(session)
            row = repo.get(experiment_id)
            if row is None:
                raise NotFoundError(
                    f"experiment {experiment_id} not found")
            if row.status in ("SUCCESSFUL", "FAILED", "INCONCLUSIVE",
                              "ARCHIVED"):
                raise ValidationError(
                    f"experiment already concluded ({row.status})")
            row.status = "STOPPED"
            row.stop_reason = reason
            repo.save(row)
        finally:
            session.close()
        self._audit(principal, "survival.experiment_stopped",
                    "experiment", experiment_id, "allow", reason)
        return self.get_experiment(experiment_id)

    # ----------------------------------------------------------- evaluate
    def evaluate_experiment(self, principal, experiment_id: str,
                            data: dict) -> dict:
        """§9.5 evaluation. The classification follows the recorded
        evidence: success/failure metrics were declared up front; the
        observed value is compared against them. A VALIDATED result
        additionally requires P-07 evidence (budget consumed within
        cap and, where the metric is financial, verified readings) —
        an agent's say-so never validates an experiment."""
        experiment = self.get_experiment(experiment_id)
        classification = str(data.get("classification") or "").upper()
        if classification not in C.EVALUATION_CLASSES:
            raise ValidationError(
                f"unknown evaluation classification {classification!r}")
        utilisation = None
        if experiment["budget_id"]:
            utilisation = self._financial.budgets.budget_utilisation(
                experiment["budget_id"])
        if classification == "VALIDATED":
            if utilisation is not None and (
                    utilisation["spent_minor"]
                    + utilisation["committed_minor"]
                    > experiment["approved_budget_minor"]):
                raise ValidationError(
                    "cannot classify VALIDATED: spend exceeded the "
                    "approved budget (P-07 reading)")
            if not data.get("observed_metric_value"):
                raise ValidationError(
                    "VALIDATED requires the observed success-metric "
                    "value as evidence (§9.5)")
        session = self._session_factory()
        try:
            row = ExperimentEvaluationRepository(session).add(
                ExperimentEvaluation(
                    experiment_id=experiment_id,
                    business_id=experiment["business_id"],
                    classification=classification,
                    actual_outcome=data.get("actual_outcome") or "",
                    observed_metric_value=data.get(
                        "observed_metric_value"),
                    actuals={"budget_utilisation": utilisation},
                    unexpected_findings=data.get(
                        "unexpected_findings") or "",
                    lessons=data.get("lessons") or "",
                    recommended_next_step=data.get(
                        "recommended_next_step") or "",
                    created_by=_actor(principal)))
            result = evaluation_dict(row)
            repo = ExperimentRepository(session)
            exp_row = repo.get(experiment_id)
            exp_row.status = {
                "VALIDATED": "SUCCESSFUL",
                "PARTIALLY_VALIDATED": "SUCCESSFUL",
                "INCONCLUSIVE": "INCONCLUSIVE",
                "INVALIDATED": "FAILED",
                "FAILED": "FAILED",
            }[classification]
            repo.save(exp_row)
        finally:
            session.close()
        self._audit(principal, "survival.experiment_evaluated",
                    "experiment", experiment_id, "allow",
                    f"classified {classification}; preserved as a "
                    "learning record (§9.5)")
        return result

    def list_evaluations(self, experiment_id: str) -> list[dict]:
        session = self._session_factory()
        try:
            rows = ExperimentEvaluationRepository(
                session).for_experiment(experiment_id)
            return [evaluation_dict(r) for r in rows]
        finally:
            session.close()


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}" if principal else "system"
