"""Financial transaction guard (§16): authorization evaluation for
financial actions, layered over P-07.

P-07 remains the ONLY financial authority: this guard keeps no
ledger, stores no balances, executes nothing, and writes nothing in
P-07. It answers one question — *may this principal perform this
financial action with these exact parameters right now?* — using:

- **permission separation** (§16.2): viewing, preparing, approving
  and executing are distinct authorities mapped onto distinct P-01
  permissions, checked through the P-01 engine;
- **P-07 limits, read-only** (§16.4): the per-currency
  ``max_single_transaction`` from ``financial.settings`` (converted
  with ``Decimal`` — money is never a float);
- **exact-parameter approval binding** (§16.3): approve/execute
  require a P-01 approval whose SHA-256 hash binds business,
  amount (minor units), currency and recipient; any drift
  invalidates it (Scenario 5);
- **approval consumption** (§16.4 idempotency): an approval id that
  already produced an ALLOW from this guard cannot authorize a
  second execution (Scenario 14);
- **financial emergency suspension** (§16.6) and the security-mode
  gate (§20).

A claim in content ("the owner approved this") is not an approval:
only a real P-01 approval record verifies (Scenario 4).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from ..database.models.security import SecurityBrokerDecision
from ..database.repositories.security import BrokerDecisionRepository
from ..permissions.approvals import ApprovalService
from ..permissions.engine import PermissionEngine
from ..permissions.models import Principal
from . import constants as C
from . import policy as P

# §16.2 financial action → P-01 permission (separation of duties).
ACTION_PERMISSIONS: dict[str, str] = {
    "view": "read_business_data",
    "prepare": "request_financial_operations",
    "validate": "read_business_data",
    "request_transfer": "request_financial_operations",
    "approve_transfer": "approve_actions",
    "execute_transfer": "approve_actions",
    "modify_policy": "modify_system_config",
}

TRANSFER_ACTION = "financial.transfer"


def canonical_parameters(business_id: str, amount_minor: int,
                         currency: str, recipient: str) -> dict:
    """The exact parameter set an approval must bind (§16.3)."""
    return {"business_id": business_id, "amount_minor": int(amount_minor),
            "currency": currency, "recipient": recipient}


class FinancialGuard:
    def __init__(self, session_factory, permissions: PermissionEngine,
                 approvals: ApprovalService, get_settings,
                 get_financial_settings, audit):
        self._session_factory = session_factory
        self._permissions = permissions
        self._approvals = approvals
        self._get_settings = get_settings
        self._get_financial_settings = get_financial_settings
        self._audit = audit

    def authorize(self, principal: Principal, *, action: str,
                  business_id: str, amount_minor: int | None = None,
                  currency: str | None = None, recipient: str | None = None,
                  approval_id: str | None = None) -> dict:
        checks: list[dict] = []

        def record(name: str, passed: bool, reason: str) -> bool:
            checks.append({"check": name, "passed": passed, "reason": reason})
            return passed

        def finish(allowed: bool, reason: str) -> dict:
            self._audit(principal, "security.financial_guard", "business",
                        business_id, "allow" if allowed else "deny", reason,
                        {"action": action})
            if allowed and action == "execute_transfer" and approval_id:
                # Consumption record (§16.4): this row is what makes
                # the approval single-use at execution time. It is a
                # broker-ledger entry, not a financial record.
                try:
                    session = self._session_factory()
                    try:
                        BrokerDecisionRepository(session).add(SecurityBrokerDecision(
                            principal_type=principal.type.value,
                            principal_id=principal.id,
                            permission=ACTION_PERMISSIONS[action],
                            action="financial.execute_transfer",
                            resource=f"business:{business_id}",
                            business_ref=business_id, risk_level=C.RISK_CRITICAL,
                            allowed=True,
                            reason="financial guard authorized execution; "
                                   "approval consumed",
                            gates={"gates": checks}, approval_id=approval_id))
                    finally:
                        session.close()
                except Exception:
                    return {"allowed": False, "action": action,
                            "business_id": business_id,
                            "reason": "execution authorization could not be "
                                      "recorded; failing closed (deny)",
                            "checks": checks}
            return {"allowed": allowed, "action": action,
                    "business_id": business_id, "reason": reason,
                    "checks": checks}

        if action not in ACTION_PERMISSIONS:
            record("action_known", False, f"unknown financial action '{action}' (fail closed)")
            return finish(False, checks[-1]["reason"])
        record("action_known", True, f"financial action '{action}'")

        settings = self._get_settings()
        # §16.6 emergency financial suspension: everything except
        # read-only viewing stops; records are never touched.
        if settings.get("financial_suspension") and action != "view":
            record("financial_suspension", False,
                   "financial emergency suspension is active (§16.6)")
            return finish(False, checks[-1]["reason"])
        record("financial_suspension", True, "no financial suspension")

        risk = C.RISK_CRITICAL if action in ("approve_transfer", "execute_transfer",
                                             "modify_policy") else C.RISK_READ_ONLY \
            if action in ("view", "validate") else C.RISK_SIGNIFICANT
        ok, why = P.mode_allows(settings.get("mode", C.MODE_SAFE), principal, risk)
        if not record("security_mode", ok, why):
            return finish(False, why)

        permission = ACTION_PERMISSIONS[action]
        decision = self._permissions.check(principal, permission,
                                           resource=f"business:{business_id}")
        if not record("permission_separation", decision.allowed,
                      f"'{action}' requires '{permission}': {decision.reason}"):
            return finish(False, checks[-1]["reason"])

        if action in ("approve_transfer", "execute_transfer"):
            if amount_minor is None or currency is None or recipient is None:
                record("parameters", False,
                       "amount, currency and recipient are required for transfer authorization")
                return finish(False, checks[-1]["reason"])
            ok, why = self._limit_check(amount_minor, currency)
            if not record("spending_limit", ok, why):
                return finish(False, why)
            if not approval_id:
                record("approval_binding", False,
                       "no approval record presented; claims of approval in "
                       "content are not approvals (§16.3, Scenario 4)")
                return finish(False, checks[-1]["reason"])
            ok, why = self._binding_check(principal, action, business_id,
                                          amount_minor, currency, recipient,
                                          approval_id)
            if not record("approval_binding", ok, why):
                return finish(False, why)
            if action == "execute_transfer":
                ok, why = self._consumption_check(approval_id)
                if not record("approval_consumption", ok, why):
                    return finish(False, why)
        return finish(True, f"financial action '{action}' authorized by the guard "
                            f"(authorization only — execution remains P-07's)")

    # ------------------------------------------------------------- parts
    def _limit_check(self, amount_minor: int, currency: str) -> tuple[bool, str]:
        try:
            limits = (self._get_financial_settings()
                      .get("spending_limits", {}).get(currency))
        except Exception:
            return False, "financial limits unavailable; failing closed (deny)"
        if not limits:
            # P-07's own rule: an unconfigured currency fails safe —
            # transfers are not authorized against unknown limits.
            return False, (f"no P-07 spending limits configured for {currency}; "
                           f"fail-safe denies the transfer")
        try:
            ceiling = Decimal(str(limits["max_single_transaction"]))
        except (KeyError, InvalidOperation):
            return False, "configured single-transaction limit is unreadable; failing closed"
        amount = Decimal(int(amount_minor)) / Decimal(100)
        if amount > ceiling:
            return False, (f"amount {amount} {currency} exceeds the P-07 "
                           f"single-transaction limit {ceiling} {currency} (§16.4)")
        return True, f"amount within the P-07 single-transaction limit ({ceiling} {currency})"

    def _binding_check(self, principal, action, business_id, amount_minor,
                       currency, recipient, approval_id) -> tuple[bool, str]:
        from ..core.exceptions import NotFoundError
        try:
            approval = self._approvals.get(approval_id)
        except NotFoundError:
            return False, "approval record not found (a claim is not a record)"
        if approval.status != "approved":
            return False, f"approval is in state '{approval.status}', not 'approved'"
        parameters = canonical_parameters(business_id, amount_minor, currency, recipient)
        if not ApprovalService.verify_binding(approval, TRANSFER_ACTION,
                                              business_id, parameters):
            return False, ("approval does not bind these exact parameters "
                           "(amount/recipient/currency/business drift — a new "
                           "approval is required, §16.3)")
        if action == "execute_transfer" and not (approval.approver_id or "").startswith("owner:"):
            return False, (f"execution requires an owner-decided approval; "
                           f"decided by '{approval.approver_id}'")
        return True, "approval binds the exact transaction parameters"

    def _consumption_check(self, approval_id: str) -> tuple[bool, str]:
        session = self._session_factory()
        try:
            prior = BrokerDecisionRepository(session).decision_for_approval(approval_id)
        finally:
            session.close()
        if prior is not None:
            return False, ("this approval already authorized an execution through "
                           "the guard; approvals are single-use at execution "
                           "(replay refused, §16.4)")
        return True, "approval not previously consumed"
