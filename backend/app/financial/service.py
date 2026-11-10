"""FinancialService — the P-07 facade.

Wires the deterministic sub-services (ledger, revenue, expenses,
budgets, payments, reconciliation, analytics, forecasting, reports,
analyst) over the P-01 substrate: approvals are P-01 approvals, the
audit trail is the P-01 append-only log, governance settings live in
owner-governed ``system_config``. There is NO transaction-execution
method on this service or anywhere in the package (§23.2).
"""
from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import select

from ..core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from ..database.models.base import utcnow
from ..database.models.business import Business
from ..database.models.core import Agent as AgentRow
from ..database.models.core import AuditEvent
from ..database.models.financial import (
    ExchangeRate, FinancialProfile, TaxRecord, TaskCostRecord,
)
from ..database.repositories.core import AuditRepository, ConfigRepository
from ..database.repositories.financial import (
    ExchangeRateRepository, TaxRepository, TaskCostRepository,
)
from ..events.bus import EventBus
from ..events.events import Event, EventType
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from .analyst import FinancialAnalyst
from .analytics import AnalyticsService
from .budgets import BudgetService
from .expenses import ExpenseService
from .forecasting import ForecastingService
from .ledger import LedgerService
from .money import CurrencyRegistry, Money, convert, parse_amount
from .payments import PaymentsService
from .reconciliation import ReconciliationService
from .reports import ReportService
from .revenue import RevenueService

MODEL_BY_CATEGORY = {
    "digital_products": "digital_products", "software": "saas",
    "services": "services", "content": "content",
    "education": "digital_products", "distribution": "digital_products",
    "b2b": "services",
}


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}"


def profile_dict(row: FinancialProfile) -> dict:
    return {
        "id": row.id, "business_id": row.business_id,
        "base_currency": row.base_currency,
        "reporting_currency": row.reporting_currency,
        "reporting_period": row.reporting_period,
        "business_model": row.business_model, "status": row.status,
        "is_fixture": row.is_fixture, "source": row.source,
        "estimates": row.estimates, "created_by": row.created_by,
        "note": "estimates ingested from P-06 are labelled estimates "
                "forever; they are never actuals (§25 P-03 contract)",
    }


class FinancialService:
    def __init__(self, session_factory, *, settings, permissions, approvals,
                 bus: EventBus, business=None):
        self._session_factory = session_factory
        self._core_settings = settings
        self._permissions = permissions
        self._approvals = approvals
        self._bus = bus
        self._business = business
        self.registry = CurrencyRegistry()
        self.ledger = LedgerService(session_factory, self.registry, self._audit)
        self.revenue = RevenueService(session_factory, self.ledger, self._audit)
        self.expenses = ExpenseService(session_factory, self.ledger, self._audit)
        self.budgets = BudgetService(
            session_factory, self.registry, self.ledger, self._audit,
            approvals, self.get_settings)
        self.payments = PaymentsService(
            session_factory, self.registry, self.revenue, self._audit,
            self.get_settings)
        self.reconciliation = ReconciliationService(
            session_factory, self.ledger, self._audit)
        self.analytics = AnalyticsService(
            session_factory, self.ledger, self.revenue, self.expenses,
            self.budgets, self._audit, self.get_settings)
        self.forecasting = ForecastingService(
            session_factory, self.budgets, self._audit)
        self.reports = ReportService(
            session_factory, self.ledger, self.revenue, self.budgets,
            self.analytics)
        self.analyst = FinancialAnalyst(
            self.revenue, self.expenses, self.budgets, self.analytics)
        # P-14 Stage B (DEF-I3): wire the financial event publisher
        # into the sub-services that own the event moments. Uses the
        # facade's own sync-safe publish helper; best-effort only.
        self.ledger.publish_event = self._publish_financial_sync
        self.revenue.publish_event = self._publish_financial_sync
        # P-14 Stage B (DEF-I6): the facade's outcome ingestor,
        # late-attached by the Application assembly (P-09 is built
        # after P-07); the revenue service reads it through the
        # closure so late attachment works without rewiring.
        self.outcome_ingestor = None
        self.revenue.outcome_feed = self._feed_outcome_late

    def _publish_financial_sync(self, event_type, payload: dict) -> None:
        """Sync-safe publish through the facade's bus (DEF-I3)."""
        if self._bus is None:
            return
        self._bus.publish_sync_safe(Event(
            event_type=event_type, source="financial", payload=payload))

    def _feed_outcome_late(self, principal, candidate: dict) -> None:
        if self.outcome_ingestor is not None:
            self.outcome_ingestor(principal, candidate)

    # ------------------------------------------------------------- audit
    def _audit(self, principal, action, target_type, target_id, decision,
               reason=None, details=None) -> None:
        session = self._session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value if principal else "system",
                actor_id=principal.id if principal else "financial-engine",
                action=action, target_type=target_type, target_id=target_id,
                decision=decision, reason=reason,
                details=details or {}, created_at=utcnow()))
        finally:
            session.close()

    async def _publish(self, event_type, payload, severity="info"):
        if self._bus is not None:
            await self._bus.publish(Event(
                event_type=event_type, source=C.SOURCE, payload=payload,
                severity=severity))

    @staticmethod
    def _require_owner(principal: Principal, action: str) -> None:
        if principal.type != PrincipalType.OWNER:
            raise PermissionDeniedError(
                f"{action} is financial governance: only the Owner "
                "principal may do it", details={"action": action})

    # ---------------------------------------------------------- settings
    def seed_settings(self) -> None:
        session = self._session_factory()
        try:
            repo = ConfigRepository(session)
            if repo.get(C.SETTINGS_KEY) is None:
                repo.set(C.SETTINGS_KEY, json.dumps(C.DEFAULT_SETTINGS),
                         "P-07 financial settings; owner-governed limits "
                         "and thresholds (§9/§12/§16)")
            if repo.get(C.CURRENCIES_KEY) is None:
                repo.set(C.CURRENCIES_KEY, json.dumps(C.DEFAULT_CURRENCIES),
                         "P-07 currency registry: code -> minor-unit "
                         "exponent (§5.1/§14)")
            self._load_currencies(session)
        finally:
            session.close()

    def _load_currencies(self, session) -> None:
        row = ConfigRepository(session).get(C.CURRENCIES_KEY)
        if row and row.value:
            overrides = json.loads(row.value)
            for code, exponent in overrides.items():
                self.registry._exponents[str(code).upper()] = int(exponent)

    def get_settings(self) -> dict:
        session = self._session_factory()
        try:
            row = ConfigRepository(session).get(C.SETTINGS_KEY)
            if row and row.value:
                return json.loads(row.value)
            return dict(C.DEFAULT_SETTINGS)
        finally:
            session.close()

    def update_settings(self, principal: Principal, patch: dict) -> dict:
        """Owner-only. Agents can never modify financial limits —
        the system does not rewrite its own rules (Article 0, §3.3)."""
        self._require_owner(principal, "update financial settings")
        session = self._session_factory()
        try:
            repo = ConfigRepository(session)
            current = self.get_settings()
            merged = {**current, **patch}
            repo.set(C.SETTINGS_KEY, json.dumps(merged),
                     "P-07 financial settings; owner-governed")
        finally:
            session.close()
        self._audit(principal, "financial.settings_update", "system_config",
                    C.SETTINGS_KEY, "allow", None, {"keys": sorted(patch)})
        return merged

    def get_currencies(self) -> dict:
        return {"currencies": {code: self.registry.exponent(code)
                               for code in self.registry.codes()},
                "source": "system_config financial.currencies "
                          "(owner-governed, seeded from ISO 4217)"}

    # --------------------------------------------------- business access
    def assert_business_access(self, principal: Principal,
                               business_id: str) -> None:
        """Per-business isolation (§23): owner/system unrestricted;
        an agent only reaches the business it is registered to;
        everyone else is denied. Denials are audited."""
        if principal.type in (PrincipalType.OWNER, PrincipalType.SYSTEM):
            return
        if principal.type == PrincipalType.AGENT:
            session = self._session_factory()
            try:
                agent = session.get(AgentRow, principal.id)
                if agent is not None and agent.business_ref == business_id:
                    return
            finally:
                session.close()
        self._audit(principal, "financial.isolation_violation", "business",
                    business_id, "deny",
                    "principal has no financial access to this business",
                    {"principal": _actor(principal)})
        raise PermissionDeniedError(
            "financial data for this business is not accessible to this "
            "principal (§23 business-level permissions)")

    # ------------------------------------------------------------ profile
    def _get_business_row(self, business_id: str) -> Business:
        session = self._session_factory()
        try:
            row = session.get(Business, business_id)
            if row is None:
                raise NotFoundError(f"business {business_id} not found")
            session.expunge(row)
            return row
        finally:
            session.close()

    def get_profile(self, business_id: str) -> dict | None:
        session = self._session_factory()
        try:
            from ..database.repositories.financial import ProfileRepository
            row = ProfileRepository(session).for_business(business_id)
            if row is None:
                return None
            session.expunge(row)
            return profile_dict(row)
        finally:
            session.close()

    async def ensure_profile(self, principal: Principal, business_id: str,
                             *, business_model: str | None = None) -> dict:
        """Create the financial profile for a P-06 business (idempotent),
        ingesting the P-06 bridge payload as labelled estimates and
        seeding the chart of accounts (§18/§25)."""
        existing = self.get_profile(business_id)
        if existing is not None:
            return existing
        business = self._get_business_row(business_id)
        payload: dict = {}
        if self._business is not None:
            try:
                payload = self._business.financial_inputs(business_id)
            except NotFoundError:
                payload = {}
        currency = payload.get("currency", "INR")
        if not self.registry.is_known(currency):
            currency = "INR"
        estimates = self._convert_payload_estimates(payload, currency)
        model = business_model or MODEL_BY_CATEGORY.get(
            business.category, "digital_products")
        session = self._session_factory()
        try:
            from ..database.repositories.financial import ProfileRepository
            row = FinancialProfile(
                business_id=business_id, base_currency=currency,
                reporting_currency=currency, reporting_period="monthly",
                business_model=model, status="active",
                is_fixture=bool(business.is_fixture),
                source="p06_bridge" if payload else "manual",
                p06_payload=payload, estimates=estimates,
                created_by=_actor(principal))
            ProfileRepository(session).add(row)
            session.expunge(row)
            profile = profile_dict(row)
        finally:
            session.close()
        session = self._session_factory()
        try:
            self.ledger.seed_chart(session, business_id, currency,
                                   _actor(principal))
        finally:
            session.close()
        self._audit(principal, "financial.profile_created", "business",
                    business_id, "allow", None,
                    {"currency": currency, "business_model": model})
        await self._publish(EventType.FINANCIAL_PROFILE_CREATED,
                            {"business_id": business_id})
        return profile

    def _convert_payload_estimates(self, payload: dict, currency: str) -> dict:
        """P-06 speaks float estimates inside JSON. They are converted
        ONCE, here, via Decimal(str(x)) into integer minor units and
        stay labelled 'estimate' — the float never enters arithmetic."""
        if not payload:
            return {"classification": "estimate", "source": "none",
                    "startup_total_minor": 0, "recurring_monthly_minor": 0,
                    "currency": currency, "items": []}

        def convert_items(values, kind):
            items = []
            for value in values or []:
                amount = value.get("amount")
                if amount is None and value.get("range"):
                    amount = (Decimal(str(value["range"]["low"]))
                              + Decimal(str(value["range"]["high"]))) / 2
                money = parse_amount(str(amount), currency, self.registry,
                                     field=f"{kind} estimate")
                items.append({"kind": kind, "amount_minor": money.minor,
                              "source": value.get("source"),
                              "classification": "estimate",
                              "confidence": value.get("confidence"),
                              "assumptions": value.get("assumptions") or []})
            return items

        startup = convert_items(payload.get("startup_costs"), "startup_cost")
        recurring = convert_items(payload.get("recurring_costs"),
                                  "recurring_cost")
        pricing = payload.get("pricing")
        pricing_minor = None
        if pricing and pricing.get("amount") is not None:
            pricing_minor = parse_amount(
                str(pricing["amount"]), currency, self.registry,
                field="pricing estimate").minor
        return {
            "classification": "estimate", "source": "p06_bridge",
            "currency": currency,
            "startup_total_minor": sum(i["amount_minor"] for i in startup),
            "recurring_monthly_minor": sum(i["amount_minor"] for i in recurring),
            "pricing_minor": pricing_minor,
            "items": startup + recurring,
        }

    def list_business_ids(self) -> list[str]:
        session = self._session_factory()
        try:
            return list(session.scalars(select(Business.id)).all())
        finally:
            session.close()

    # ------------------------------------------------------ opening cash
    def record_opening_balance(self, principal: Principal, business_id: str,
                               data: dict) -> dict:
        """Opening cash: a cash-balance record AND the opening journal
        (Dr Cash / Cr Owner Contributions), so the ledger and the
        available-cash formula agree from day one."""
        amount: Money = data["amount"]
        balance = self.budgets.record_cash_balance(
            principal, business_id,
            {"amount": amount, "account_ref": data.get("account_ref", "cash:primary"),
             "source": data.get("source", "owner_recorded_opening_balance"),
             "verification_status": data.get("verification_status", "reported")})
        entry = self.ledger.post_simple(
            principal, business_id, debit_code=C.ACCOUNT_CASH,
            credit_code=C.ACCOUNT_OWNER_CONTRIBUTIONS,
            amount_minor=amount.minor, currency=amount.currency,
            entry_date=data["entry_date"],
            description="Opening balance (owner recorded)",
            source_type="opening", source_id=balance["id"], kind="opening",
            idempotency_key=f"opening:{business_id}:{balance['id']}")
        return {"cash_balance": balance, "journal_entry_id": entry["id"]}

    # -------------------------------------------------- internal transfers
    def record_internal_transfer(self, principal: Principal,
                                 from_business_id: str, to_business_id: str,
                                 data: dict) -> dict:
        """§18: corresponding entries in BOTH businesses (source:
        Dr other-current-assets / Cr cash; destination: Dr cash /
        Cr other-liabilities), flagged is_internal_transfer. No
        revenue or expense record is created, and consolidated
        reporting excludes these entries — a transfer is not income."""
        if from_business_id == to_business_id:
            raise ValidationError("an internal transfer needs two businesses")
        amount: Money = data["amount"]
        reference = data["reference"]
        date = data["entry_date"]
        out_entry = self.ledger.post_simple(
            principal, from_business_id, debit_code="1200",
            credit_code=C.ACCOUNT_CASH, amount_minor=amount.minor,
            currency=amount.currency, entry_date=date,
            description=f"Internal transfer to {to_business_id} ({reference})",
            source_type="internal_transfer", source_id=reference,
            idempotency_key=f"transfer:{reference}:out",
            is_internal_transfer=True, counterpart_business_id=to_business_id)
        in_entry = self.ledger.post_simple(
            principal, to_business_id, debit_code=C.ACCOUNT_CASH,
            credit_code="2300", amount_minor=amount.minor,
            currency=amount.currency, entry_date=date,
            description=f"Internal transfer from {from_business_id} ({reference})",
            source_type="internal_transfer", source_id=reference,
            idempotency_key=f"transfer:{reference}:in",
            is_internal_transfer=True, counterpart_business_id=from_business_id)
        self._audit(principal, "financial.internal_transfer", "business",
                    from_business_id, "allow", None,
                    {"to_business_id": to_business_id,
                     "amount_minor": amount.minor, "reference": reference})
        return {"reference": reference,
                "out_entry_id": out_entry["id"], "in_entry_id": in_entry["id"],
                "counted_as_revenue": False}

    def consolidated(self, currency: str) -> dict:
        """Consolidated portfolio view (§18): sums ONLY same-currency
        verified figures per business; internal transfers never enter
        revenue. Cross-currency totals are reported per currency —
        never summed without a documented rate (§14)."""
        per_business = []
        totals = {"net_collected_minor": 0, "expenses_minor": 0,
                  "net_profit_minor": 0}
        for business_id in self.list_business_ids():
            profile = self.get_profile(business_id)
            if profile is None or profile["base_currency"] != currency:
                continue
            metrics = self.revenue.metrics(business_id, currency)
            totals_exp = self.expenses.totals(business_id, currency)
            profit = metrics["net_collected_minor"] \
                - totals_exp["pl_expense_paid_minor"]
            per_business.append({
                "business_id": business_id,
                "net_collected_minor": metrics["net_collected_minor"],
                "expenses_minor": totals_exp["pl_expense_paid_minor"],
                "net_profit_minor": profit,
                "is_fixture": profile["is_fixture"]})
            totals["net_collected_minor"] += metrics["net_collected_minor"]
            totals["expenses_minor"] += totals_exp["pl_expense_paid_minor"]
            totals["net_profit_minor"] += profit
        return {
            "currency": currency, "businesses": per_business,
            "totals": totals,
            "internal_transfers_excluded": True,
            "note": "only businesses whose base currency is "
                    f"{currency} are consolidated here; other currencies "
                    "are never summed without a documented exchange rate (§14)",
        }

    # ------------------------------------------------------------------ FX
    def add_exchange_rate(self, principal: Principal, data: dict) -> dict:
        self._require_owner(principal, "record exchange rate")
        if data["source"] not in C.FX_RATE_SOURCES:
            raise ValidationError(
                f"exchange-rate source must be one of {sorted(C.FX_RATE_SOURCES)} "
                "(§14: documented sources or owner-entered manual rates only)")
        rate = Decimal(str(data["rate"]))
        if rate <= 0:
            raise ValidationError("exchange rate must be positive")
        self.registry.exponent(data["from_currency"])
        self.registry.exponent(data["to_currency"])
        session = self._session_factory()
        try:
            row = ExchangeRate(
                from_currency=data["from_currency"].upper(),
                to_currency=data["to_currency"].upper(), rate=str(rate),
                source=data["source"], created_by=_actor(principal))
            ExchangeRateRepository(session).add(row)
            session.expunge(row)
            return {"id": row.id, "from_currency": row.from_currency,
                    "to_currency": row.to_currency, "rate": row.rate,
                    "source": row.source, "created_by": row.created_by,
                    "recorded_at": row.created_at.isoformat()
                    if row.created_at else None}
        finally:
            session.close()

    def convert_amount(self, amount: Money, to_currency: str) -> dict:
        """Convert with the latest recorded rate. Missing rate →
        status 'pending' with the original preserved — a rate is
        never invented (§14, Scenario 7)."""
        if amount.currency == to_currency.upper():
            return {"status": "converted", "original_minor": amount.minor,
                    "original_currency": amount.currency,
                    "converted_minor": amount.minor, "currency": to_currency,
                    "rate": "1", "source": "identity"}
        session = self._session_factory()
        try:
            repo = ExchangeRateRepository(session)
            direct = repo.latest(amount.currency, to_currency.upper())
            inverse = None if direct else repo.latest(to_currency.upper(),
                                                      amount.currency)
        finally:
            session.close()
        if direct is not None:
            converted = convert(amount, to_currency, Decimal(direct.rate),
                                self.registry)
            return {"status": "converted", "original_minor": amount.minor,
                    "original_currency": amount.currency,
                    "converted_minor": converted.minor,
                    "currency": to_currency.upper(), "rate": direct.rate,
                    "source": direct.source, "rate_id": direct.id,
                    "rate_recorded_at": direct.created_at.isoformat()
                    if direct.created_at else None}
        if inverse is not None:
            rate = Decimal(1) / Decimal(inverse.rate)
            converted = convert(amount, to_currency, rate, self.registry)
            return {"status": "converted", "original_minor": amount.minor,
                    "original_currency": amount.currency,
                    "converted_minor": converted.minor,
                    "currency": to_currency.upper(), "rate": str(rate),
                    "source": f"inverse of recorded {inverse.source} rate",
                    "rate_id": inverse.id}
        return {"status": "pending",
                "original_minor": amount.minor,
                "original_currency": amount.currency,
                "converted_minor": None, "currency": to_currency.upper(),
                "rate": None,
                "note": "no documented exchange rate recorded; conversion "
                        "is pending and the original currency is "
                        "preserved (§14)"}

    # ------------------------------------------------------------------ tax
    def create_tax_record(self, principal: Principal, business_id: str,
                          data: dict) -> dict:
        self._require_owner(principal, "create tax record")

        def minor(key):
            value = data.get(key)
            if value is None:
                return 0
            return parse_amount(str(value), data["currency"], self.registry,
                                field=key).minor

        session = self._session_factory()
        try:
            row = TaxRecord(
                business_id=business_id, jurisdiction=data["jurisdiction"],
                category=data["category"], period_label=data["period_label"],
                estimated_liability_minor=minor("estimated_liability"),
                collected_minor=minor("collected"), payable_minor=minor("payable"),
                paid_minor=minor("paid"), currency=data["currency"],
                due_date=data.get("due_date"), rate=data.get("rate") or {},
                status="open", professional_review_required=True,
                notes=data.get("notes", ""), created_by=_actor(principal))
            TaxRepository(session).add(row)
            session.expunge(row)
            return tax_dict(row)
        finally:
            session.close()

    def list_tax_records(self, business_id: str) -> list[dict]:
        session = self._session_factory()
        try:
            rows, _ = TaxRepository(session).list(limit=200,
                                                  business_id=business_id)
            return [tax_dict(r) for r in rows]
        finally:
            session.close()

    # ------------------------------------------------------------ task costs
    def record_task_cost(self, principal: Principal, data: dict) -> dict:
        """§19 cost declaration for an agent task / execution. Local
        inference (cost_kind=free_local) records a monetary cost of
        exactly 0 unless the owner configured an electricity estimate
        — a cost is never invented for free local software (§19.1)."""
        currency = data["currency"]
        estimated = parse_amount(str(data.get("estimated", "0")), currency,
                                 self.registry, field="estimated")
        limit = parse_amount(str(data.get("approved_limit", "0")), currency,
                             self.registry, field="approved_limit")
        actual = None
        if data.get("actual") is not None:
            actual = parse_amount(str(data["actual"]), currency,
                                  self.registry, field="actual")
        cost_kind = data.get("cost_kind", "direct_monetary")
        notes = data.get("notes", "")
        if cost_kind == "free_local":
            settings = self.get_settings()
            if settings.get("electricity_cost_per_hour") is None:
                if actual is not None and actual.minor != 0:
                    raise ValidationError(
                        "free local inference has no monetary cost unless "
                        "the owner configures an electricity estimate "
                        "(§19.1); refusing to invent one")
                actual = Money(0, currency)
                notes = (notes + " | direct monetary cost 0: local "
                         "inference is free software; no electricity "
                         "estimate configured by the owner").strip(" |")
            else:
                cost_kind = "estimated_electricity"
        session = self._session_factory()
        try:
            row = TaskCostRecord(
                business_id=data["business_id"],
                project_ref=data.get("project_ref"),
                agent_id=data.get("agent_id"), task_id=data.get("task_id"),
                execution_request_id=data.get("execution_request_id"),
                category=data["category"], estimated_minor=estimated.minor,
                approved_limit_minor=limit.minor,
                actual_minor=actual.minor if actual else None,
                currency=currency, cost_kind=cost_kind,
                approval_requirement=data.get("approval_requirement", "level_2"),
                status="recorded" if actual is not None else "estimated",
                notes=notes, created_by=_actor(principal))
            TaskCostRepository(session).add(row)
            session.expunge(row)
            result = task_cost_dict(row)
        finally:
            session.close()
        if actual is not None and actual.minor > limit.minor:
            self._audit(principal, "financial.task_cost_over_limit",
                        "task_cost_record", result["id"], "deny",
                        "actual cost exceeded the approved limit",
                        {"actual_minor": actual.minor,
                         "approved_limit_minor": limit.minor})
            result["over_limit"] = True
        return result

    def list_task_costs(self, business_id: str) -> list[dict]:
        session = self._session_factory()
        try:
            rows, _ = TaskCostRepository(session).list(
                limit=200, business_id=business_id)
            return [task_cost_dict(r) for r in rows]
        finally:
            session.close()

    # ------------------------------------------- P-03 assumption comparison
    def assumption_comparison(self, business_id: str) -> dict:
        """P-03/P-06 assumptions vs P-07 actuals (§25): the original
        estimates are read, never rewritten; variance is reported."""
        profile = self.get_profile(business_id)
        if profile is None:
            raise NotFoundError("no financial profile for this business")
        currency = profile["base_currency"]
        estimates = profile["estimates"]
        totals = self.expenses.totals(business_id, currency)
        metrics = self.revenue.metrics(business_id, currency)
        actual_months = max(1, len({
            e["expense_date"][:7] for e in
            self.expenses.list_expenses(business_id, limit=1000)[0]})) \
            if totals["total_paid_minor"] else 0
        actual_monthly_burn = (totals["pl_expense_paid_minor"] // actual_months
                               if actual_months else 0)
        return {
            "business_id": business_id, "currency": currency,
            "assumptions": {
                "startup_total_minor": estimates.get("startup_total_minor"),
                "recurring_monthly_minor": estimates.get(
                    "recurring_monthly_minor"),
                "pricing_minor": estimates.get("pricing_minor"),
                "classification": "estimate (P-03/P-06 origin, unchanged)",
            },
            "actuals": {
                "total_expenses_paid_minor": totals["pl_expense_paid_minor"],
                "average_monthly_burn_minor": actual_monthly_burn,
                "verified_net_collected_minor": metrics["net_collected_minor"],
            },
            "variance": {
                "startup_vs_total_expenses_minor":
                    totals["pl_expense_paid_minor"]
                    - (estimates.get("startup_total_minor") or 0),
                "recurring_assumption_vs_actual_burn_minor":
                    actual_monthly_burn
                    - (estimates.get("recurring_monthly_minor") or 0),
            },
            "note": "assumption quality is evaluated from actuals; the "
                    "original estimates are never edited (§25)",
        }

    # ------------------------------------------------------- P-08 interface
    def p08_indicators(self, business_id: str) -> dict:
        """The stable read-only P-08 contract (§25). P-08 must consume
        these figures rather than computing its own."""
        profile = self.get_profile(business_id)
        if profile is None:
            raise NotFoundError("no financial profile for this business")
        currency = profile["base_currency"]
        metrics = self.revenue.metrics(business_id, currency)
        totals = self.expenses.totals(business_id, currency)
        profit = self.analytics.profitability(
            business_id, currency, profile["business_model"])
        available = self.budgets.available_cash(business_id, currency)
        runway = self.analytics.runway(business_id, currency)
        health = self.analytics.health(business_id, currency)
        budgets, _ = self.budgets.list_budgets(business_id=business_id,
                                               limit=200)
        max_utilisation = None
        for budget in budgets:
            utilisation = self.budgets.budget_utilisation(budget["id"])
            ratio = Decimal(utilisation["utilisation_ratio"])
            if max_utilisation is None or ratio > max_utilisation:
                max_utilisation = ratio
        recon = self.reports.reconciliation_report(business_id)
        return {
            "business_id": business_id, "currency": currency,
            "verified_collected_revenue_minor": metrics["net_collected_minor"],
            "actual_expenses_minor": totals["pl_expense_paid_minor"],
            "profitability": {
                "status": profit["status"],
                "net_profit_minor": profit["net_profit_minor"],
                "is_loss": profit["is_loss"]},
            "cash_flow": {
                "available_cash_minor": available["available_cash_minor"],
                "cash_balance_minor": available["cash_balance_minor"]},
            "available_capital_minor": available["available_cash_minor"],
            "runway_months": runway.get("runway_months"),
            "runway_status": runway["status"],
            "financial_risk": health["status"],
            "budget_utilisation_max_ratio": (str(max_utilisation)
                                             if max_utilisation is not None
                                             else None),
            "reconciliation_status": {
                "unresolved_items": recon["unresolved_count"],
                "sessions": len(recon["sessions"])},
            "generated_at": utcnow().isoformat(),
            "contract": "P-08 read-only indicators v1 (§25) — P-08 must "
                        "not compute competing financial figures",
        }

    # ------------------------------------------------------------- summary
    def business_summary(self, business_id: str) -> dict:
        profile = self.get_profile(business_id)
        if profile is None:
            raise NotFoundError("no financial profile for this business; "
                                "create it first")
        currency = profile["base_currency"]
        return {
            "profile": profile,
            "revenue": self.revenue.metrics(business_id, currency),
            "expenses": self.expenses.totals(business_id, currency),
            "available_cash": self.budgets.available_cash(business_id, currency),
            "profitability": self.analytics.profitability(
                business_id, currency, profile["business_model"]),
            "health": self.analytics.health(business_id, currency),
            "runway": self.analytics.runway(business_id, currency),
        }

    def engine_status(self) -> dict:
        session = self._session_factory()
        try:
            from ..database.repositories.financial import ProfileRepository
            _, profiles = ProfileRepository(session).list(limit=1)
        finally:
            session.close()
        return {
            "engine": "P-07 Financial Intelligence Engine",
            "profiles": profiles,
            "providers": self.payments.list_providers(),
            "execution_capability": "none — accounting, verification and "
                                    "governance only (§23.2)",
            "currencies": self.get_currencies(),
        }


def tax_dict(row: TaxRecord) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "jurisdiction": row.jurisdiction, "category": row.category,
            "period_label": row.period_label,
            "estimated_liability_minor": row.estimated_liability_minor,
            "collected_minor": row.collected_minor,
            "payable_minor": row.payable_minor, "paid_minor": row.paid_minor,
            "currency": row.currency, "due_date": row.due_date,
            "rate": row.rate, "status": row.status,
            "professional_review_required": row.professional_review_required,
            "notice": "tracking estimate only — not tax advice and not a "
                      "compliance certification (§15)",
            "notes": row.notes, "created_by": row.created_by}


def task_cost_dict(row: TaskCostRecord) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "project_ref": row.project_ref, "agent_id": row.agent_id,
            "task_id": row.task_id,
            "execution_request_id": row.execution_request_id,
            "category": row.category, "estimated_minor": row.estimated_minor,
            "approved_limit_minor": row.approved_limit_minor,
            "actual_minor": row.actual_minor, "currency": row.currency,
            "cost_kind": row.cost_kind,
            "approval_requirement": row.approval_requirement,
            "status": row.status, "notes": row.notes,
            "created_by": row.created_by}
