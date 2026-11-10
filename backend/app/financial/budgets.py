"""Budget & capital control (§9). This module *authorises the
recording of obligations* — it never executes a payment (§23.2).

Available cash (§9.4) is one deterministic formula with named,
non-overlapping components (no double-counting):

    available = cash balances (latest per account, from authoritative
                sources)
              − protected reserves (active designations)
              − committed (authorised-but-unrecorded spending
                requests + committed expenses)
              − obligations (accounts-payable ledger balance)

Approval levels (§9.5): Level 0 read-only (never a spend), Level 1
pre-authorised inside an owner-approved budget + configured limits,
Level 2 owner approval (hash-bound P-01 approval, drift-checked),
Level 3 structurally blocked — no approval path exists in P-07.
"""
from __future__ import annotations

from decimal import Decimal

from ..core.exceptions import (
    InvalidStateTransitionError, NotFoundError, PermissionDeniedError,
    ValidationError,
)
from ..database.models.financial import (
    Budget, ExpenseRecord, FinancialReserve, SpendingRequest,
)
from ..database.repositories.financial import (
    BudgetRepository, CashBalanceRepository, ExpenseRepository,
    ReserveRepository, SpendingRequestRepository,
)
from ..permissions.models import PrincipalType
from . import constants as C
from .ledger import LedgerService
from .money import Money, parse_amount, require_positive


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}"


AUTHORISED_STATUSES = {"authorised_level1", "authorised_owner"}


def budget_dict(row: Budget) -> dict:
    return {
        "id": row.id, "scope_type": row.scope_type, "scope_ref": row.scope_ref,
        "business_id": row.business_id, "parent_budget_id": row.parent_budget_id,
        "name": row.name, "owner_id": row.owner_id,
        "period_start": row.period_start, "period_end": row.period_end,
        "approved_minor": row.approved_minor, "currency": row.currency,
        "approval_requirement": row.approval_requirement,
        "review_date": row.review_date, "status": row.status,
        "created_by": row.created_by,
    }


def request_dict(row: SpendingRequest) -> dict:
    return {
        "id": row.id, "business_id": row.business_id,
        "budget_id": row.budget_id, "requester": f"{row.requester_type}:{row.requester_id}",
        "amount_minor": row.amount_minor, "currency": row.currency,
        "category": row.category, "purpose": row.purpose, "kind": row.kind,
        "required_level": row.required_level, "status": row.status,
        "approval_id": row.approval_id, "decision_reason": row.decision_reason,
        "decided_by": row.decided_by, "expense_record_id": row.expense_record_id,
        "agent_id": row.agent_id, "task_id": row.task_id,
        "project_ref": row.project_ref, "experiment_ref": row.experiment_ref,
        "execution_note": "P-07 authorises recording an obligation only; "
                          "no payment or transfer is executed (§23.2)",
    }


def reserve_dict(row: FinancialReserve) -> dict:
    return {
        "id": row.id, "business_id": row.business_id,
        "reserve_type": row.reserve_type, "balance_minor": row.balance_minor,
        "target_minor": row.target_minor, "currency": row.currency,
        "status": row.status, "created_by": row.created_by,
        "spendable": False,
    }


class BudgetService:
    def __init__(self, session_factory, registry, ledger: LedgerService,
                 audit, approvals, settings_getter):
        self._session_factory = session_factory
        self._registry = registry
        self._ledger = ledger
        self._audit = audit
        self._approvals = approvals
        self._settings = settings_getter

    @staticmethod
    def _require_owner(principal, action: str) -> None:
        if principal.type != PrincipalType.OWNER:
            raise PermissionDeniedError(
                f"{action} is financial governance: only the Owner may do it")

    # ------------------------------------------------------------ budgets
    def create_budget(self, principal, data: dict) -> dict:
        self._require_owner(principal, "create budget")
        if data["scope_type"] not in C.BUDGET_SCOPES:
            raise ValidationError(f"unknown budget scope {data['scope_type']!r}")
        amount: Money = require_positive(data["amount"])
        session = self._session_factory()
        try:
            row = Budget(
                scope_type=data["scope_type"], scope_ref=data.get("scope_ref"),
                business_id=data.get("business_id"),
                parent_budget_id=data.get("parent_budget_id"),
                name=data["name"], owner_id=_actor(principal),
                period_start=data["period_start"], period_end=data["period_end"],
                approved_minor=amount.minor, currency=amount.currency,
                approval_requirement=data.get("approval_requirement", "level_2"),
                review_date=data.get("review_date"), status="active",
                created_by=_actor(principal))
            BudgetRepository(session).add(row)
            session.expunge(row)
            return budget_dict(row)
        finally:
            session.close()

    def get_budget(self, budget_id: str) -> Budget:
        session = self._session_factory()
        try:
            row = BudgetRepository(session).get(budget_id)
            if row is None:
                raise NotFoundError(f"budget {budget_id} not found")
            session.expunge(row)
            return row
        finally:
            session.close()

    def list_budgets(self, business_id: str | None = None, limit: int = 50,
                     offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            rows, total = BudgetRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [budget_dict(r) for r in rows], total
        finally:
            session.close()

    def _budget_flows(self, session, budget_id: str, currency: str) -> tuple[int, int]:
        expenses = session.query(ExpenseRecord).filter(
            ExpenseRecord.budget_id == budget_id,
            ExpenseRecord.currency == currency).all()
        spent = sum(e.amount_minor for e in expenses
                    if e.payment_status == "paid")
        committed_expenses = sum(e.amount_minor for e in expenses
                                 if e.payment_status == "committed")
        requests = session.query(SpendingRequest).filter(
            SpendingRequest.budget_id == budget_id,
            SpendingRequest.currency == currency).all()
        committed_requests = sum(
            r.amount_minor for r in requests
            if r.status in AUTHORISED_STATUSES and r.expense_record_id is None)
        return spent, committed_expenses + committed_requests

    def budget_utilisation(self, budget_id: str) -> dict:
        budget = self.get_budget(budget_id)
        session = self._session_factory()
        try:
            spent, committed = self._budget_flows(
                session, budget_id, budget.currency)
        finally:
            session.close()
        remaining = budget.approved_minor - spent - committed
        ratio = (Decimal(spent + committed) / Decimal(budget.approved_minor)
                 if budget.approved_minor else Decimal(0))
        return {
            **budget_dict(budget), "spent_minor": spent,
            "committed_minor": committed, "remaining_minor": remaining,
            "utilisation_ratio": str(ratio.quantize(Decimal("0.0001"))),
            "over_budget": remaining < 0,
        }

    # ------------------------------------------------------------ reserves
    def create_reserve(self, principal, data: dict) -> dict:
        self._require_owner(principal, "create reserve")
        if data["reserve_type"] not in C.RESERVE_TYPES:
            raise ValidationError(f"unknown reserve type {data['reserve_type']!r}")
        amount: Money = require_positive(data["amount"])
        target = data.get("target")
        session = self._session_factory()
        try:
            row = FinancialReserve(
                business_id=data.get("business_id"),
                reserve_type=data["reserve_type"], balance_minor=amount.minor,
                target_minor=target.minor if isinstance(target, Money) else None,
                currency=amount.currency, status="active",
                created_by=_actor(principal))
            ReserveRepository(session).add(row)
            session.expunge(row)
            return reserve_dict(row)
        finally:
            session.close()

    def set_reserve_balance(self, principal, reserve_id: str,
                            amount: Money, *, reason: str) -> dict:
        """Changing a protected reserve is a Level-3-adjacent governance
        act: owner-only, reason required, fully audited (§9.5)."""
        self._require_owner(principal, "change protected reserve")
        if not reason:
            raise ValidationError("changing a reserve requires a reason")
        session = self._session_factory()
        try:
            repo = ReserveRepository(session)
            row = repo.get(reserve_id)
            if row is None:
                raise NotFoundError(f"reserve {reserve_id} not found")
            old = row.balance_minor
            row.balance_minor = amount.minor
            repo.save(row)
            session.expunge(row)
            result = reserve_dict(row)
        finally:
            session.close()
        self._audit(principal, "financial.reserve_changed", "financial_reserve",
                    reserve_id, "allow", reason,
                    {"old_minor": old, "new_minor": amount.minor})
        return result

    def list_reserves(self, business_id: str | None) -> list[dict]:
        session = self._session_factory()
        try:
            rows = ReserveRepository(session).for_business(business_id)
            return [reserve_dict(r) for r in rows]
        finally:
            session.close()

    # ------------------------------------------------------- available cash
    def record_cash_balance(self, principal, business_id: str, data: dict) -> dict:
        amount: Money = require_positive(data["amount"])
        session = self._session_factory()
        try:
            from ..database.models.financial import CashBalance
            row = CashBalance(
                business_id=business_id, account_ref=data["account_ref"],
                balance_minor=amount.minor, currency=amount.currency,
                source=data["source"],
                verification_status=data.get("verification_status", "reported"),
                created_by=_actor(principal))
            CashBalanceRepository(session).add(row)
            session.expunge(row)
            return {"id": row.id, "business_id": business_id,
                    "account_ref": row.account_ref,
                    "balance_minor": row.balance_minor,
                    "currency": row.currency, "source": row.source,
                    "verification_status": row.verification_status,
                    "created_by": row.created_by}
        finally:
            session.close()

    def available_cash(self, business_id: str, currency: str) -> dict:
        """The §9.4 formula. Each component names its source so the
        figure can be re-derived by hand; components never overlap."""
        session = self._session_factory()
        try:
            cash_rows = [r for r in CashBalanceRepository(session)
                         .latest_for(business_id) if r.currency == currency]
            cash = sum(r.balance_minor for r in cash_rows)
            verified_cash = sum(r.balance_minor for r in cash_rows
                                if r.verification_status == "verified")
            reserves = sum(r.balance_minor for r in ReserveRepository(session)
                           .for_business(business_id)
                           if r.currency == currency)
            requests = session.query(SpendingRequest).filter(
                SpendingRequest.business_id == business_id,
                SpendingRequest.currency == currency).all()
            committed_requests = sum(
                r.amount_minor for r in requests
                if r.status in AUTHORISED_STATUSES
                and r.expense_record_id is None)
            expenses = ExpenseRepository(session).for_business(business_id)
            committed_expenses = sum(
                e.amount_minor for e in expenses
                if e.currency == currency and e.payment_status == "committed")
        finally:
            session.close()
        try:
            obligations = self._ledger.account_balance(
                business_id, C.ACCOUNT_PAYABLE)
        except NotFoundError:
            obligations = 0
        committed = committed_requests + committed_expenses
        available = cash - reserves - committed - obligations
        return {
            "business_id": business_id, "currency": currency,
            "cash_balance_minor": cash,
            "verified_cash_minor": verified_cash,
            "protected_reserves_minor": reserves,
            "committed_minor": committed,
            "obligations_minor": obligations,
            "available_cash_minor": available,
            "formula": "available = cash − protected reserves − committed "
                       "− obligations (accounts-payable ledger balance); "
                       "components are disjoint by construction (§9.4)",
        }

    # ---------------------------------------------------- spend authorising
    def _limits(self, currency: str) -> dict | None:
        settings = self._settings()
        raw = (settings.get("spending_limits") or {}).get(currency)
        if raw is None:
            return None
        return {key: parse_amount(value, currency, self._registry, field=key).minor
                for key, value in raw.items()}

    def request_spend(self, principal, business_id: str, data: dict) -> dict:
        """Decide a spending authorisation. Returns the persisted
        SpendingRequest with its decision. Level 3 never authorises."""
        if principal.type == PrincipalType.EXTERNAL:
            raise PermissionDeniedError(
                "external principals cannot request spending authorisations")
        amount: Money = require_positive(data["amount"])
        kind = data.get("kind", "expense")
        session = self._session_factory()
        try:
            row = SpendingRequest(
                business_id=business_id, budget_id=data.get("budget_id"),
                requester_type=principal.type.value, requester_id=principal.id,
                amount_minor=amount.minor, currency=amount.currency,
                category=data["category"], purpose=data.get("purpose", ""),
                kind=kind, required_level=2, status="held_for_owner",
                agent_id=data.get("agent_id"), task_id=data.get("task_id"),
                project_ref=data.get("project_ref"),
                experiment_ref=data.get("experiment_ref"))
            repo = SpendingRequestRepository(session)
            repo.add(row)
            request_id = row.id
        finally:
            session.close()

        reasons: list[str] = []
        if kind in C.LEVEL3_KINDS:
            status, level = "blocked_level3", 3
            reasons.append(
                f"kind {kind!r} is Level 3 (§9.5): transfers, investments, "
                "reserve/policy changes are structurally blocked in P-07 — "
                "no approval path exists and no execution mechanism is "
                "part of this phase (§23.2)")
            self._audit(principal, "financial.level3_blocked", "spending_request",
                        request_id, "deny", reasons[-1],
                        {"business_id": business_id, "kind": kind,
                         "amount_minor": amount.minor})
        else:
            level = 2 if kind in C.LEVEL2_KINDS else 1
            if kind in C.LEVEL2_KINDS:
                reasons.append(f"kind {kind!r} requires owner approval (§9.5 Level 2)")
            budget = None
            if data.get("budget_id"):
                try:
                    budget = self.get_budget(data["budget_id"])
                except NotFoundError:
                    budget = None
                    level = 2
                    reasons.append("budget not found; failing safe to owner approval")
            if budget is not None:
                if budget.business_id not in (None, business_id):
                    level = 2
                    reasons.append("budget belongs to a different business")
                if budget.status != "active":
                    level = 2
                    reasons.append(f"budget status is {budget.status}")
                utilisation = self.budget_utilisation(budget.id)
                if amount.minor > utilisation["remaining_minor"]:
                    level = 2
                    reasons.append(
                        "amount exceeds the budget's remaining amount "
                        f"({utilisation['remaining_minor']} minor)")
                if budget.scope_type == "experiment":
                    limits = self._limits(amount.currency)
                    if limits and amount.minor > limits["max_experiment_loss"]:
                        level = 2
                        reasons.append("amount exceeds the configured "
                                       "maximum experiment loss")
                if budget.approval_requirement == "level_2":
                    level = 2
                    reasons.append("budget requires owner approval for spends")
            else:
                level = 2
                reasons.append("no budget covers this spend; owner approval "
                               "required (fail-safe)")
            limits = self._limits(amount.currency)
            if limits is None:
                level = 2
                reasons.append(f"no spending limits configured for "
                               f"{amount.currency}; failing safe to Level 2")
            elif amount.minor > limits["max_single_transaction"]:
                level = 2
                reasons.append("amount exceeds the configured maximum "
                               "single transaction")
            available = self.available_cash(business_id, amount.currency)
            if amount.minor > available["available_cash_minor"]:
                level = 2
                reasons.append("amount exceeds available cash "
                               f"({available['available_cash_minor']} minor "
                               "after reserves/commitments/obligations)")
            status = "authorised_level1" if level == 1 else "held_for_owner"
            if level == 1:
                reasons.append("within an active owner-approved budget and "
                               "all configured limits (Level 1 pre-authorised)")
        session = self._session_factory()
        try:
            repo = SpendingRequestRepository(session)
            row = repo.get(request_id)
            row.status = status
            row.required_level = level
            row.decision_reason = "; ".join(reasons)
            row.decided_by = "system:budget_engine" if status != "blocked_level3" \
                else "system:level3_block"
            repo.save(row)
            session.expunge(row)
            result = request_dict(row)
        finally:
            session.close()
        self._audit(principal, "financial.spend_decided", "spending_request",
                    request_id, "allow" if status == "authorised_level1" else "deny",
                    "; ".join(reasons),
                    {"business_id": business_id, "status": status,
                     "required_level": level})
        return result

    def approve_spend(self, principal, request_id: str, approval_id: str) -> dict:
        """Owner approval of a held spend, bound by a hash-checked
        P-01 approval (drift fails closed, P-01 §9.4 pattern)."""
        self._require_owner(principal, "approve spend")
        session = self._session_factory()
        try:
            repo = SpendingRequestRepository(session)
            row = repo.get(request_id)
            if row is None:
                raise NotFoundError(f"spending request {request_id} not found")
            if row.status != "held_for_owner":
                raise InvalidStateTransitionError(
                    f"spending request is {row.status}, not held_for_owner")
            business_id, amount_minor, currency = \
                row.business_id, row.amount_minor, row.currency
        finally:
            session.close()
        approval = self._approvals.get(approval_id)
        parameters = {"spending_request_id": request_id,
                      "amount_minor": amount_minor, "currency": currency}
        if not self._approvals.verify_binding(
                approval, "financial.spend_approve", business_id, parameters):
            self._audit(principal, "financial.spend_approval_drift",
                        "spending_request", request_id, "deny",
                        "approval does not bind this exact spend", {})
            raise InvalidStateTransitionError(
                "approval does not bind this exact spending request "
                "(action/parameters drift); a new approval is required")
        session = self._session_factory()
        try:
            repo = SpendingRequestRepository(session)
            row = repo.get(request_id)
            row.status = "authorised_owner"
            row.approval_id = approval_id
            row.decided_by = _actor(principal)
            row.decision_reason = (row.decision_reason or "") + \
                " | owner approved via hash-bound P-01 approval"
            repo.save(row)
            session.expunge(row)
            result = request_dict(row)
        finally:
            session.close()
        self._audit(principal, "financial.spend_approved", "spending_request",
                    request_id, "allow", None, {"approval_id": approval_id})
        return result

    def reject_spend(self, principal, request_id: str, *, reason: str) -> dict:
        self._require_owner(principal, "reject spend")
        session = self._session_factory()
        try:
            repo = SpendingRequestRepository(session)
            row = repo.get(request_id)
            if row is None:
                raise NotFoundError(f"spending request {request_id} not found")
            if row.status not in ("held_for_owner",):
                raise InvalidStateTransitionError(
                    f"spending request is {row.status}; only held requests "
                    "can be rejected")
            row.status = "rejected"
            row.decision_reason = reason
            row.decided_by = _actor(principal)
            repo.save(row)
            session.expunge(row)
            return request_dict(row)
        finally:
            session.close()

    def mark_recorded(self, principal, request_id: str, expense_id: str) -> dict:
        session = self._session_factory()
        try:
            repo = SpendingRequestRepository(session)
            row = repo.get(request_id)
            if row is None:
                raise NotFoundError(f"spending request {request_id} not found")
            if row.status not in AUTHORISED_STATUSES:
                raise InvalidStateTransitionError(
                    f"spending request is {row.status}; only authorised "
                    "requests can be recorded as expenses")
            row.status = "recorded"
            row.expense_record_id = expense_id
            repo.save(row)
            session.expunge(row)
            return request_dict(row)
        finally:
            session.close()

    def get_request(self, request_id: str) -> dict:
        session = self._session_factory()
        try:
            row = SpendingRequestRepository(session).get(request_id)
            if row is None:
                raise NotFoundError(f"spending request {request_id} not found")
            session.expunge(row)
            return request_dict(row)
        finally:
            session.close()

    def list_requests(self, business_id: str, limit: int = 50,
                      offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            rows, total = SpendingRequestRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [request_dict(r) for r in rows], total
        finally:
            session.close()
