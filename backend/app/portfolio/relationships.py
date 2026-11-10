"""Relationships mixin (§7): the governed business relationship
graph.

A relationship describes how two P-06 businesses interact within a
portfolio. Creating one grants nothing: the access scope on an
ACTIVE relationship is a declaration the access layer may consult,
and data still flows only through explicitly scoped grants and the
P-09 scope rules. Relationships pass through governed states
(PROPOSED → UNDER_REVIEW → APPROVED → ACTIVE →
SUSPENDED/TERMINATED/EXPIRED); only the owner moves them.
"""
from __future__ import annotations

from ..core.exceptions import (
    InvalidStateTransitionError, NotFoundError, ValidationError,
)
from ..database.models.portfolio import BusinessRelationship
from ..database.repositories.portfolio import RelationshipRepository
from ..permissions.models import Principal
from . import constants as C
from .constants import actor_of


def relationship_dict(row: BusinessRelationship) -> dict:
    return {
        "id": row.id, "portfolio_id": row.portfolio_id,
        "source_business_id": row.source_business_id,
        "target_business_id": row.target_business_id,
        "relationship_type": row.relationship_type,
        "status": row.status,
        # The API name for the model's access_scope declaration.
        "sharing_policy": row.access_scope,
        "access_scope": row.access_scope,
        "shared_responsibilities": [],
        "description": row.description,
        "notes": row.description,
        "risk_classification": row.risk_classification,
        "created_by": row.created_by,
        "approved_by": row.decided_by,
        "decided_by": row.decided_by,
        "expires_at": row.ends_on,
        "ends_on": row.ends_on,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class RelationshipsMixin:
    def create_relationship(self, principal: Principal, data: dict) -> dict:
        self._require_owner(principal, "portfolio.relationship_create")
        portfolio_id = data.get("portfolio_id")
        if not portfolio_id:
            raise ValidationError(
                "portfolio_id is required: relationships are recorded "
                "within a portfolio's governance context")
        self._portfolio_or_404(portfolio_id)
        source = data.get("source_business_id")
        target = data.get("target_business_id")
        if not source or not target:
            raise ValidationError(
                "source_business_id and target_business_id are required")
        if source == target:
            raise ValidationError(
                "a business cannot have a relationship with itself")
        rtype = str(data.get("relationship_type") or "")
        if rtype not in C.RELATIONSHIP_TYPES:
            raise ValidationError(f"unknown relationship type: {rtype}")
        policy = str(data.get("sharing_policy")
                     or data.get("access_scope") or "NONE")
        if policy not in C.SHARING_POLICIES:
            raise ValidationError(f"unknown sharing policy: {policy}")
        self._business_or_404(source)
        self._business_or_404(target)
        session = self._session_factory()
        try:
            row = RelationshipRepository(session).add(BusinessRelationship(
                portfolio_id=portfolio_id,
                source_business_id=source, target_business_id=target,
                relationship_type=rtype, access_scope=policy,
                description=str(data.get("notes")
                                or data.get("description") or ""),
                risk_classification=str(
                    data.get("risk_classification") or "low"),
                ends_on=data.get("expires_at") or data.get("ends_on"),
                created_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.relationship_created",
                    "business_relationship", row.id, "allow",
                    "relationship proposed (grants no access)",
                    {"source": source, "target": target, "type": rtype})
        return relationship_dict(row)

    def transition_relationship(self, principal: Principal,
                                relationship_id: str, status: str) -> dict:
        self._require_owner(principal, "portfolio.relationship_transition")
        if status not in C.RELATIONSHIP_STATUSES:
            raise ValidationError(f"unknown relationship status: {status}")
        session = self._session_factory()
        try:
            repo = RelationshipRepository(session)
            row = repo.get(relationship_id)
            if row is None:
                raise NotFoundError(
                    f"relationship {relationship_id} not found")
            allowed = C.RELATIONSHIP_TRANSITIONS.get(row.status, set())
            if status not in allowed:
                raise InvalidStateTransitionError(
                    f"relationship cannot move {row.status} -> {status} "
                    f"(allowed: {sorted(allowed)})")
            row.status = status
            if status == "APPROVED":
                row.decided_by = actor_of(principal)
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.relationship_transition",
                    "business_relationship", relationship_id, "allow",
                    f"relationship -> {status}", {})
        return relationship_dict(row)

    def list_relationships(self, principal: Principal, *,
                           portfolio_id: str | None = None,
                           business_id: str | None = None,
                           status: str | None = None) -> dict:
        self._require_portfolio_reader(principal, "portfolio.relationships")
        session = self._session_factory()
        try:
            repo = RelationshipRepository(session)
            if business_id and portfolio_id:
                rows = repo.for_business(portfolio_id, business_id)
            else:
                rows, _total = repo.list(
                    limit=200, portfolio_id=portfolio_id, status=status)
                if business_id:
                    rows = [r for r in rows
                            if business_id in (r.source_business_id,
                                               r.target_business_id)]
            items = [relationship_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": len(items)}

    def _active_relationship(self, portfolio_id: str, a: str, b: str,
                             rtype: str | None = None) -> bool:
        """Internal: is there an ACTIVE relationship between the two
        businesses (either direction)? Supporting evidence for
        detectors — never access itself."""
        session = self._session_factory()
        try:
            rows, _ = RelationshipRepository(session).list(
                limit=200, portfolio_id=portfolio_id, status="ACTIVE")
            for row in rows:
                pair = {row.source_business_id, row.target_business_id}
                if pair == {a, b} and (
                        rtype is None or row.relationship_type == rtype):
                    return True
            return False
        finally:
            session.close()
