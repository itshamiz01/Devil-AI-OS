"""Coordination mixin (§13): cross-business workflows.

P-13 coordinates scope and participation; P-12 executes. A
portfolio workflow is a coordination record linking one P-12
workflow per participating business — each created inside that
business's own scope, so participation creates NO unrestricted
access between participants (§21 Scenario 9).

Every participating business explicitly authorizes what it
contributes (authorization starts PENDING — never assumed), and
contributions come from a closed shareable set: customer records,
credentials and financial detail can never be a contribution.
Participation status is derived from the linked P-12 workflow at
read time; execution truth stays in P-12.
"""
from __future__ import annotations

from ..core.exceptions import (
    InvalidStateTransitionError, NotFoundError, ValidationError,
)
from ..database.models.portfolio import (
    PortfolioWorkflow, PortfolioWorkflowParticipation,
)
from ..database.repositories.portfolio import (
    ParticipationRepository, PortfolioWorkflowRepository,
)
from ..permissions.models import Principal
from . import constants as C
from .constants import actor_of

OPS_STATUS_MAP = {"COMPLETED": "COMPLETED", "FAILED": "FAILED",
                  "CANCELLED": "FAILED"}


def participation_dict(row: PortfolioWorkflowParticipation,
                       ops_status: str | None = None) -> dict:
    contributes = row.contributes or {}
    if ops_status in OPS_STATUS_MAP:
        status = OPS_STATUS_MAP[ops_status]
    elif row.sub_workflow_id:
        status = "LINKED"
    elif row.authorization_status == "AUTHORIZED":
        status = "AUTHORIZED"
    else:
        status = "PENDING"
    return {
        "id": row.id, "workflow_id": row.portfolio_workflow_id,
        "business_id": row.business_id, "role": row.role,
        "contribution_category": contributes.get("category"),
        "contribution_description": contributes.get("description", ""),
        "contributes": contributes,
        "authorization_status": row.authorization_status,
        "operations_workflow_id": row.sub_workflow_id,
        "sub_workflow_id": row.sub_workflow_id,
        "status": status,
    }


def workflow_dict(row: PortfolioWorkflow, participations: list) -> dict:
    return {
        "id": row.id, "portfolio_id": row.portfolio_id,
        "name": row.name, "objective": row.objective,
        "status": row.status, "created_by": row.created_by,
        "participations": participations,
        "execution_authority": "P-12 (each participation is a P-12 "
                               "workflow inside its own business "
                               "scope)",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class CoordinationMixin:
    def create_portfolio_workflow(self, principal: Principal,
                                  portfolio_id: str, data: dict) -> dict:
        self._require_owner(principal, "portfolio.workflow_create")
        self._portfolio_or_404(portfolio_id)
        participations = list(data.get("participations") or [])
        if len(participations) < 2:
            raise ValidationError(
                "a portfolio workflow coordinates at least two "
                "businesses (§13)")
        member_ids = set(self._member_business_ids(portfolio_id))
        seen = set()
        for part in participations:
            business_id = part.get("business_id")
            category = str(part.get("contribution_category")
                           or (part.get("contributes") or {}).get(
                               "category") or "")
            if business_id not in member_ids:
                raise ValidationError(
                    f"business {business_id} is not a member of this "
                    "portfolio; only members participate")
            if business_id in seen:
                raise ValidationError(
                    f"business {business_id} appears twice")
            seen.add(business_id)
            if category in C.NEVER_GRANTABLE or category in (
                    "customer_records", "credentials", "financial_detail"):
                raise ValidationError(
                    f"contribution category {category!r} can never be "
                    "shared into a cross-business workflow (§13/§20)")
            if category not in C.SHAREABLE_CONTRIBUTIONS:
                raise ValidationError(
                    f"unknown contribution category {category!r}; "
                    f"shareable: {sorted(C.SHAREABLE_CONTRIBUTIONS)}")
        session = self._session_factory()
        try:
            workflow = PortfolioWorkflowRepository(session).add(
                PortfolioWorkflow(
                    portfolio_id=portfolio_id,
                    name=str(data.get("name") or "")[:300],
                    objective=str(data.get("objective") or ""),
                    success_criteria=dict(
                        data.get("success_criteria") or {}),
                    created_by=actor_of(principal)))
            parts = []
            for part in participations:
                category = str(part.get("contribution_category")
                               or (part.get("contributes") or {}).get(
                                   "category") or "")
                row = ParticipationRepository(session).add(
                    PortfolioWorkflowParticipation(
                        portfolio_workflow_id=workflow.id,
                        business_id=part["business_id"],
                        role=str(part.get("role") or "contributor"),
                        contributes={
                            "category": category,
                            "description": str(
                                part.get("contribution_description")
                                or "")},
                        authorization_status="PENDING",
                        deliverables=list(part.get("deliverables") or []),
                        asset_ownership=dict(
                            part.get("asset_ownership") or {})))
                parts.append(participation_dict(row))
            workflow_id = workflow.id
        finally:
            session.close()
        self._audit(principal, "portfolio.workflow_created",
                    "portfolio_workflow", workflow_id, "allow",
                    "portfolio workflow drafted; no access created "
                    "between participants",
                    {"businesses": sorted(seen)})
        session = self._session_factory()
        try:
            workflow = PortfolioWorkflowRepository(session).get(
                workflow_id)
            return workflow_dict(workflow, parts)
        finally:
            session.close()

    def authorize_participation(self, principal: Principal,
                                workflow_id: str,
                                business_id: str) -> dict:
        """A business's explicit authorization of its own
        contribution — recorded per business, audited per business."""
        self._require_owner(principal, "portfolio.workflow_authorize")
        session = self._session_factory()
        try:
            repo = ParticipationRepository(session)
            rows = repo.for_workflow(workflow_id)
            target = next((r for r in rows
                           if r.business_id == business_id), None)
            if target is None:
                raise NotFoundError(
                    "this business does not participate in the workflow")
            if target.authorization_status == "AUTHORIZED":
                raise InvalidStateTransitionError(
                    "participation already authorized")
            target.authorization_status = "AUTHORIZED"
            repo.save(target)
            result = participation_dict(target)
            category = (target.contributes or {}).get("category")
        finally:
            session.close()
        self._audit(principal, "portfolio.workflow_participation_authorized",
                    "business", business_id, "allow",
                    "business authorized its portfolio-workflow "
                    "contribution",
                    {"workflow_id": workflow_id,
                     "contribution": category})
        return result

    def start_portfolio_workflow(self, principal: Principal,
                                 workflow_id: str) -> dict:
        """Start: every participation must be AUTHORIZED. Each
        business's contribution becomes a P-12 workflow in that
        business's own scope. Completion of a workflow never marks a
        business profitable or operational (§4 honesty rule)."""
        self._require_owner(principal, "portfolio.workflow_start")
        session = self._session_factory()
        try:
            repo = PortfolioWorkflowRepository(session)
            workflow = repo.get(workflow_id)
            if workflow is None:
                raise NotFoundError(f"portfolio workflow {workflow_id} "
                                    "not found")
            if workflow.status != "DRAFT":
                raise InvalidStateTransitionError(
                    f"workflow is {workflow.status}; only DRAFT starts")
            parts = ParticipationRepository(session).for_workflow(
                workflow_id)
            pending = [p.business_id for p in parts
                       if p.authorization_status != "AUTHORIZED"]
            if pending:
                raise ValidationError(
                    "every participating business must explicitly "
                    f"authorize its contribution first; pending: "
                    f"{pending}")
            workflow_snapshot = {
                "name": workflow.name, "objective": workflow.objective}
            part_data = [{
                "id": p.id, "business_id": p.business_id,
                "category": (p.contributes or {}).get("category"),
                "description": (p.contributes or {}).get(
                    "description", "")} for p in parts]
        finally:
            session.close()
        # Create the P-12 sub-workflows (outside the P-13 session).
        created_ids: dict[str, str] = {}
        for part in part_data:
            created = self._operations.create_workflow(principal, {
                "business_id": part["business_id"],
                "name": f"Portfolio contribution: "
                        f"{workflow_snapshot['name']}",
                "objective": workflow_snapshot["objective"],
                "origin": "portfolio_coordination",
                "definition": {"steps": [{
                    "step_key": "contribution",
                    "name": f"Contribute {part['category']}",
                    "kind": "task_handler",
                    "action_class": "business.read",
                    "substrate": {
                        "handler": "core.echo_check",
                        "payload": {
                            "message": "portfolio contribution "
                                       "executed in own scope",
                            "category": part["category"],
                            "description": part["description"]}},
                    "acceptance_criteria": {"task_status": "completed"},
                }]},
            })
            created_ids[part["id"]] = created["id"]
        session = self._session_factory()
        try:
            repo = PortfolioWorkflowRepository(session)
            workflow = repo.get(workflow_id)
            parts = ParticipationRepository(session).for_workflow(
                workflow_id)
            parts_out = []
            for part in parts:
                part.sub_workflow_id = created_ids[part.id]
                ParticipationRepository(session).save(part)
                parts_out.append(participation_dict(part))
            workflow.status = "ACTIVE"
            repo.save(workflow)
            result = workflow_dict(workflow, parts_out)
        finally:
            session.close()
        self._audit(principal, "portfolio.workflow_started",
                    "portfolio_workflow", workflow_id, "allow",
                    "portfolio workflow started via P-12 sub-workflows",
                    {"participations": len(parts_out)})
        return result

    def refresh_portfolio_workflow(self, principal: Principal,
                                   workflow_id: str) -> dict:
        """Sync participation statuses from P-12 (the execution
        authority) and roll the coordination status up."""
        self._require_portfolio_reader(principal, "portfolio.workflow")
        session = self._session_factory()
        try:
            repo = PortfolioWorkflowRepository(session)
            workflow = repo.get(workflow_id)
            if workflow is None:
                raise NotFoundError(f"portfolio workflow {workflow_id} "
                                    "not found")
            parts = ParticipationRepository(session).for_workflow(
                workflow_id)
            parts_data = []
            for part in parts:
                ops_status = None
                if part.sub_workflow_id:
                    view = self._operations.get_workflow(
                        principal, part.sub_workflow_id)
                    ops_status = view.get("status")
                parts_data.append(participation_dict(part, ops_status))
            if parts_data and all(p["status"] == "COMPLETED"
                                  for p in parts_data):
                workflow.status = "COMPLETED"
            elif any(p["status"] == "FAILED" for p in parts_data):
                workflow.status = "FAILED"
            repo.save(workflow)
            result = workflow_dict(workflow, parts_data)
        finally:
            session.close()
        return result

    def list_portfolio_workflows(self, principal: Principal,
                                 portfolio_id: str) -> dict:
        self._require_portfolio_reader(principal, "portfolio.workflows")
        session = self._session_factory()
        try:
            rows, _t = PortfolioWorkflowRepository(session).list(
                limit=200, portfolio_id=portfolio_id)
            items = []
            for row in rows:
                parts = ParticipationRepository(session).for_workflow(
                    row.id)
                items.append(workflow_dict(
                    row, [participation_dict(p) for p in parts]))
        finally:
            session.close()
        return {"items": items, "total": len(items)}
