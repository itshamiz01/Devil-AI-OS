"""P-13 PortfolioService: the Multi-business Coordination Engine.

A coordination and intelligence layer over P-01–P-12. It owns only
portfolio state (see models/portfolio.py). Every authority stays
where it already lives:

* business identity + lifecycle — P-06 (referenced, never copied;
  the §4 portfolio stage is a derived label, never stored);
* money — P-07 (portfolio finance is an analytical layer over
  ``FinancialService``; internal allocations are P-13 management
  accounting that P-07 never reads; P-13 never transfers funds);
* survival/scaling readings + allocation proposals — P-08;
* execution — P-12 (portfolio workflows link P-12 sub-workflows);
* memory — P-09 (only ORGANIZATION_SHARED records are shareable);
* approvals/permissions/audit — P-01/P-10 (decisions here are
  governed status fields on P-13 rows; every mutation writes a
  P-01 audit event; sensitive writes are owner-only).

Isolation posture (§20): portfolio-level aggregates are
owner/system-only. Agent-facing surfaces are exactly two checked
functions (agent access, service access) that fail closed and audit
denials. Credentials are never a grantable category, anywhere.

The service is composed of mixins (registry, relationships,
intelligence, shared services, resources, access, coordination,
finance, planning), one per prompt area, sharing the helpers here.
"""
from __future__ import annotations

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.base import utcnow
from ..database.models.core import AuditEvent
from ..database.repositories.core import AuditRepository
from ..database.repositories.portfolio import PortfolioRepository
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from .constants import actor_of
from .access import AccessMixin
from .coordination import CoordinationMixin
from .finance import FinanceMixin
from .intelligence import IntelligenceMixin
from .planning import PlanningMixin
from .registry import RegistryMixin
from .relationships import RelationshipsMixin
from .resources import ResourcesMixin
from .shared_services import SharedServicesMixin


class PortfolioService(RegistryMixin, RelationshipsMixin,
                       IntelligenceMixin, SharedServicesMixin,
                       ResourcesMixin, AccessMixin, CoordinationMixin,
                       FinanceMixin, PlanningMixin):
    def __init__(self, session_factory, *, bus=None, business=None,
                 financial=None, survival=None, operations=None,
                 memory=None, agents=None, discovery=None):
        self._session_factory = session_factory
        self._bus = bus
        self._business = business          # P-06 BusinessCreationService
        self._financial = financial        # P-07 FinancialService
        self._survival = survival          # P-08 SurvivalService
        self._operations = operations      # P-12 OperationsService
        self._memory = memory              # P-09 MemoryService
        self._agents = agents              # P-04 AgentFactoryService
        self._discovery = discovery        # P-03 OpportunityService

    # ------------------------------------------------------- settings
    def seed_settings(self) -> None:
        import json

        from ..database.repositories.core import ConfigRepository
        session = self._session_factory()
        try:
            repo = ConfigRepository(session)
            if repo.get(C.SETTINGS_KEY) is None:
                repo.set(C.SETTINGS_KEY, json.dumps(C.DEFAULT_SETTINGS),
                         "P-13 portfolio coordination settings; "
                         "owner-editable governance (concentration "
                         "threshold, share cap, capacities)")
        finally:
            session.close()

    def get_settings(self) -> dict:
        import json

        from ..database.repositories.core import ConfigRepository
        session = self._session_factory()
        try:
            row = ConfigRepository(session).get(C.SETTINGS_KEY)
            stored = json.loads(row.value) if row and row.value else {}
        finally:
            session.close()
        merged = dict(C.DEFAULT_SETTINGS)
        merged.update(stored)
        merged["capacities"] = {
            **C.DEFAULT_SETTINGS["capacities"],
            **(stored.get("capacities") or {})}
        return merged

    def update_settings(self, principal: Principal, patch: dict) -> dict:
        import json

        from ..database.repositories.core import ConfigRepository
        self._require_owner(principal, "portfolio.settings.update")
        current = self.get_settings()
        for key in ("concentration_threshold_bps",
                    "business_share_cap_bps"):
            if key in patch:
                value = int(patch[key])
                if not 1 <= value <= 10000:
                    raise ValidationError(
                        f"{key} must be within 1..10000 bps")
                current[key] = value
        if "capacities" in patch:
            for kind, units in dict(patch["capacities"]).items():
                if kind not in C.RESOURCE_KINDS:
                    raise ValidationError(f"unknown resource kind: {kind}")
                if int(units) < 0:
                    raise ValidationError("capacity units must be >= 0")
                current["capacities"][kind] = int(units)
        session = self._session_factory()
        try:
            ConfigRepository(session).set(
                C.SETTINGS_KEY, json.dumps(current),
                "P-13 portfolio coordination settings; owner-editable")
        finally:
            session.close()
        self._audit(principal, "portfolio.settings_updated", "portfolio",
                    None, "allow", "owner updated portfolio settings",
                    {"keys": sorted(patch.keys())})
        return current

    # ------------------------------------------------------------ audit
    def _audit(self, principal, action, target_type, target_id, decision,
               reason=None, details=None) -> None:
        session = self._session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value if principal else "system",
                actor_id=principal.id if principal else "portfolio-engine",
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
                f"{action} is restricted to the owner: portfolio-level "
                "decisions change cross-business structure and remain "
                "owner authority (§20/§25 rule 20)")

    def _require_portfolio_reader(self, principal: Principal,
                                  action: str) -> None:
        """Portfolio aggregates are owner/system-only: an agent's view
        of the portfolio is exactly what its scoped grants say (§20),
        never the whole ecosystem by default."""
        if principal.type not in (PrincipalType.OWNER,
                                  PrincipalType.SYSTEM):
            self._audit(principal, "portfolio.isolation_violation",
                        "portfolio", None, "deny",
                        f"{action}: portfolio aggregates are not "
                        "visible to this principal",
                        {"principal": actor_of(principal)})
            raise PermissionDeniedError(
                "portfolio-level information is restricted to the "
                "owner; agents receive only explicitly scoped grants")

    def _assert_business_read(self, principal: Principal,
                              business_id: str) -> None:
        """Mirror of P-07's per-business isolation: owner/system
        unrestricted; an agent only its registered home business;
        everyone else denied (audited)."""
        if principal.type in (PrincipalType.OWNER,
                              PrincipalType.SYSTEM):
            return
        if principal.type == PrincipalType.AGENT:
            session = self._session_factory()
            try:
                from ..database.models.core import Agent as AgentRow
                row = session.get(AgentRow, principal.id)
                if row is not None and row.business_ref == business_id:
                    return
            finally:
                session.close()
        self._audit(principal, "portfolio.isolation_violation", "business",
                    business_id, "deny",
                    "principal has no access to this business",
                    {"principal": actor_of(principal)})
        raise PermissionDeniedError(
            "business data is not accessible to this principal "
            "(business-level isolation, §20)")

    # --------------------------------------------------------- lookups
    def _portfolio_or_404(self, portfolio_id: str):
        session = self._session_factory()
        try:
            row = PortfolioRepository(session).get(portfolio_id)
            if row is None:
                raise NotFoundError(f"portfolio {portfolio_id} not found")
            session.expunge(row)
            return row
        finally:
            session.close()

    def _business_or_404(self, business_id: str) -> dict:
        """The P-06 record, read through P-06's own service."""
        return self._business.get_business(business_id)

    def _member_business_ids(self, portfolio_id: str) -> list[str]:
        from ..database.repositories.portfolio import MembershipRepository
        session = self._session_factory()
        try:
            rows = MembershipRepository(session).for_portfolio(
                portfolio_id, active_only=True)
            return [r.business_id for r in rows]
        finally:
            session.close()

    def engine_status(self) -> dict:
        session = self._session_factory()
        try:
            _, portfolios = PortfolioRepository(session).list(limit=1)
        finally:
            session.close()
        return {
            "engine": "P-13 Multi-business Coordination Engine",
            "portfolios": portfolios,
            "financial_authority": "P-07 (portfolio finance is an "
                                   "analytical layer; P-13 never "
                                   "transfers funds)",
            "lifecycle_authority": "P-06 state machine + P-08 overlay "
                                   "(portfolio stage is a derived label)",
            "execution_authority": "P-12 (portfolio workflows link "
                                   "P-12 sub-workflows)",
        }
