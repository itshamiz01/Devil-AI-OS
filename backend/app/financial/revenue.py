"""Revenue intelligence (§6). The §3.1 truth hierarchy is enforced
here: a record counts as *collected* only when it is settled AND
verified from an authorised source (§6.4/§7.3). An agent's report, a
browser redirect, a frontend message or an order creation can never
verify a payment — verification happens only through the verified
paths (signature-verified provider events, reconciliation against an
authoritative statement, or owner attestation with evidence)."""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from ..core.exceptions import InvalidStateTransitionError, NotFoundError, ValidationError
from ..database.models.financial import (
    Dispute, Invoice, Order, Refund, RevenueRecord, Subscription,
)
from ..database.repositories.financial import (
    DisputeRepository, InvoiceRepository, OrderRepository,
    RefundRepository, RevenueRepository, SubscriptionRepository,
)
from ..events.events import EventType
from . import constants as C
from .ledger import LedgerService
from .money import Money, require_positive


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}"


def classification_for(status: str, verification: str, current: str) -> str:
    if status in C.CLASSIFICATION_BY_STATUS:
        bucket = C.CLASSIFICATION_BY_STATUS[status]
        if bucket == "collected" and verification != "verified":
            return "booked"  # settled-but-unverified is NOT collected (§3.1)
        return bucket
    return current  # side states keep the bucket the money was in


def revenue_dict(row: RevenueRecord) -> dict:
    return {
        "id": row.id, "business_id": row.business_id,
        "category": row.category, "classification": row.classification,
        "lifecycle_status": row.lifecycle_status,
        "verification_status": row.verification_status,
        "amount_minor": row.amount_minor, "currency": row.currency,
        "transaction_date": row.transaction_date, "source": row.source,
        "external_ref": row.external_ref, "invoice_id": row.invoice_id,
        "order_id": row.order_id, "subscription_id": row.subscription_id,
        "customer_ref": row.customer_ref, "channel": row.channel,
        "product_ref": row.product_ref, "evidence": row.evidence,
        "creation_method": row.creation_method,
        "is_internal_transfer": row.is_internal_transfer,
        "journal_entry_id": row.journal_entry_id,
        "description": row.description, "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class RevenueService:
    def __init__(self, session_factory, ledger: LedgerService, audit):
        self._session_factory = session_factory
        self._ledger = ledger
        self._audit = audit
        # P-14 Stage B (DEF-I6): P-09 outcome-ingestion callable,
        # assigned by the FinancialService facade (which receives it
        # late from the Application assembly). Signature:
        # ingest(principal, candidate) -> dict. ``None`` → off.
        self.outcome_feed = None
        # P-14 Stage B (DEF-I3): financial event publisher, assigned
        # by the facade. Signature: publish(event_type, payload).
        self.publish_event = None

    def _publish_financial(self, event_type, payload: dict) -> None:
        """Best-effort financial event publish (DEF-I3): publishing
        never changes the financial result."""
        if self.publish_event is None:
            return
        try:
            self.publish_event(event_type, payload)
        except Exception as exc:  # publishing must not break finance
            import logging
            logging.getLogger("autonomus.financial").warning(
                "financial event publish failed: %s", exc)

    def _feed_outcome(self, principal, candidate: dict) -> None:
        """Best-effort P-09 outcome feed (DEF-I6): ingestion never
        changes the financial result; failures are logged only."""
        if self.outcome_feed is None:
            return
        try:
            self.outcome_feed(principal, candidate)
        except Exception as exc:  # feeding must not break finance
            import logging
            logging.getLogger("autonomus.financial").warning(
                "outcome feed to P-09 failed: %s", exc)

    # ------------------------------------------------------------ records
    def create_revenue(self, principal, business_id: str, data: dict, *,
                       verified: bool = False) -> dict:
        """``verified=True`` is an INTERNAL-only path (verified webhook /
        reconciliation). API callers can never set it."""
        status = data.get("initial_status", "EXPECTED")
        if status not in C.REVENUE_LIFECYCLE and status not in C.REVENUE_SIDE_STATES:
            raise ValidationError(f"unknown revenue lifecycle status {status!r}")
        if data["category"] not in C.REVENUE_CATEGORIES:
            raise ValidationError(f"unknown revenue category {data['category']!r}")
        amount: Money = require_positive(data["amount"])
        self._ledger.assert_known_currency(amount.currency)
        verification = "verified" if verified else "unverified"
        if verified and data["source"] not in C.VERIFIED_SOURCES:
            raise ValidationError(
                f"source {data['source']!r} cannot verify a payment (§7.3)")
        if data.get("external_ref"):
            # §5.3/§20: an external transaction id is unique per
            # business — a second record with the same reference is a
            # duplicate posting and is refused, never merged.
            session = self._session_factory()
            try:
                existing = RevenueRepository(session).for_business(
                    business_id, limit=100000)
                if any(r.external_ref == data["external_ref"]
                       for r in existing):
                    raise ValidationError(
                        "a revenue record with this external_ref already "
                        "exists for this business (duplicate posting "
                        "protection, §5.3)")
            finally:
                session.close()
        session = self._session_factory()
        try:
            row = RevenueRecord(
                business_id=business_id, category=data["category"],
                classification=classification_for(
                    status, verification, "projected"),
                lifecycle_status=status, verification_status=verification,
                amount_minor=amount.minor, currency=amount.currency,
                transaction_date=data["transaction_date"], source=data["source"],
                external_ref=data.get("external_ref"),
                invoice_id=data.get("invoice_id"), order_id=data.get("order_id"),
                subscription_id=data.get("subscription_id"),
                customer_ref=data.get("customer_ref"),
                channel=data.get("channel"), product_ref=data.get("product_ref"),
                evidence=data.get("evidence") or {},
                creation_method=data.get("creation_method", "manual"),
                is_internal_transfer=bool(data.get("is_internal_transfer", False)),
                description=data.get("description", ""),
                created_by=_actor(principal))
            RevenueRepository(session).add(row)
            session.expunge(row)
        finally:
            session.close()
        result = revenue_dict(row)
        if verified and status in ("PAYMENT_SETTLED", "VERIFIED"):
            self._post_collection(principal, row)
            result = self.get_revenue(row.id)
        return result

    def get_revenue(self, revenue_id: str) -> dict:
        session = self._session_factory()
        try:
            row = RevenueRepository(session).get(revenue_id)
            if row is None:
                raise NotFoundError(f"revenue record {revenue_id} not found")
            session.expunge(row)
            return revenue_dict(row)
        finally:
            session.close()

    def _get_row(self, session, revenue_id: str) -> RevenueRecord:
        row = RevenueRepository(session).get(revenue_id)
        if row is None:
            raise NotFoundError(f"revenue record {revenue_id} not found")
        return row

    def transition(self, principal, revenue_id: str, target: str) -> dict:
        session = self._session_factory()
        try:
            row = self._get_row(session, revenue_id)
            allowed = C.REVENUE_TRANSITIONS.get(row.lifecycle_status, set())
            if target not in allowed:
                raise InvalidStateTransitionError(
                    f"revenue cannot move {row.lifecycle_status} -> {target}",
                    details={"allowed": sorted(allowed)})
            if target == "VERIFIED" and row.verification_status != "verified":
                raise InvalidStateTransitionError(
                    "cannot mark VERIFIED: no verified evidence exists for "
                    "this record (§7.3)")
            row.lifecycle_status = target
            row.classification = classification_for(
                target, row.verification_status, row.classification)
            RevenueRepository(session).save(row)
            business_id, verification = row.business_id, row.verification_status
            session.expunge(row)
        finally:
            session.close()
        if target in ("PAYMENT_SETTLED", "VERIFIED") and verification == "verified":
            self._post_collection(principal, row)
        return self.get_revenue(revenue_id)

    def verify_revenue(self, principal, revenue_id: str, *, source: str,
                       evidence: dict) -> dict:
        """The only manual verification path: source must be an
        authorised §6.4 source and evidence must be present. Owner
        attestation additionally requires an approval (enforced by the
        caller/facade policy)."""
        if source not in C.VERIFIED_SOURCES:
            raise ValidationError(
                f"source {source!r} is not an authorised verification "
                "source (§6.4/§7.3)")
        if not evidence:
            raise ValidationError("verification requires evidence (§3.2)")
        session = self._session_factory()
        try:
            row = self._get_row(session, revenue_id)
            session.expunge(row)
        finally:
            session.close()
        # Post the collection FIRST: if posting fails, the record
        # must not be left verified-but-unposted (§3 truth rules).
        if row.lifecycle_status in ("PAYMENT_SETTLED", "VERIFIED",
                                    "RECOGNIZED"):
            self._post_collection(principal, row)
        session = self._session_factory()
        try:
            row = self._get_row(session, revenue_id)
            row.verification_status = "verified"
            row.source = source
            merged = dict(row.evidence or {})
            merged["verification"] = evidence
            row.evidence = merged
            if row.lifecycle_status == "PAYMENT_SETTLED":
                row.lifecycle_status = "VERIFIED"
            row.classification = classification_for(
                row.lifecycle_status, "verified", row.classification)
            RevenueRepository(session).save(row)
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "financial.revenue_verified", "revenue_record",
                    revenue_id, "allow", None, {"source": source})
        # P-07 financial event (P-14 Stage B, DEF-I3): verification is
        # the financial-truth moment; published so the event is
        # persisted with the critical set.
        self._publish_financial(EventType.FINANCIAL_REVENUE_VERIFIED, {
            "revenue_id": revenue_id, "business_id": row.business_id,
            "amount_minor": row.amount_minor, "currency": row.currency,
            "source": source})
        # P-14 Stage B (DEF-I6): verified revenue feeds P-09 outcome
        # memory (best-effort).
        self._feed_outcome(principal, {
            "title": (f"Revenue verified for business {row.business_id}: "
                      f"{row.amount_minor} minor units {row.currency}"),
            "content": (
                f"Revenue record {revenue_id} for business "
                f"{row.business_id} was verified via source {source}. "
                f"The collected revenue amount is {row.amount_minor} "
                f"minor units in {row.currency}; the journal collection "
                f"entry was posted and the revenue is now verified "
                f"financial truth for the business."),
            "source_type": "financial",
            "source_ref": revenue_id,
            "business_id": row.business_id,
            "layer": "episodic",
            "category": "financial_outcome",
            "truth_class": "observed",
        })
        return self.get_revenue(revenue_id)

    def _post_collection(self, principal, row: RevenueRecord) -> None:
        """Post the collection journal once: Dr processor / Cr income,
        or Dr processor / Cr receivable when an invoice entry exists."""
        session = self._session_factory()
        try:
            fresh = self._get_row(session, row.id)
            if fresh.journal_entry_id is not None:
                return
            invoiced = fresh.invoice_id is not None
            business_id, amount = fresh.business_id, fresh.amount_minor
            currency, category = fresh.currency, fresh.category
            revenue_id = fresh.id
        finally:
            session.close()
        credit_code = (C.ACCOUNT_RECEIVABLE if invoiced
                       else C.REVENUE_CATEGORY_ACCOUNT[category])
        entry = self._ledger.post_simple(
            principal, business_id, debit_code=C.ACCOUNT_PROCESSOR,
            credit_code=credit_code, amount_minor=amount, currency=currency,
            entry_date=row.transaction_date,
            description=f"Verified collected revenue {revenue_id}",
            source_type="revenue", source_id=revenue_id,
            idempotency_key=f"revenue:{revenue_id}:collect")
        session = self._session_factory()
        try:
            fresh = self._get_row(session, revenue_id)
            fresh.journal_entry_id = entry["id"]
            RevenueRepository(session).save(fresh)
        finally:
            session.close()

    # ------------------------------------------------------------ invoices
    def create_invoice(self, principal, business_id: str, data: dict) -> dict:
        amount: Money = data["amount"]
        session = self._session_factory()
        try:
            row = Invoice(
                business_id=business_id, number=data["number"],
                revenue_record_id=data.get("revenue_record_id"),
                customer_ref=data.get("customer_ref"),
                amount_minor=amount.minor, currency=amount.currency,
                status="issued", issued_date=data["issued_date"],
                due_date=data.get("due_date"), created_by=_actor(principal))
            InvoiceRepository(session).add(row)
            session.expunge(row)
            invoice = invoice_dict(row)
            revenue_id = data.get("revenue_record_id")
        finally:
            session.close()
        if revenue_id:
            # Dr Accounts Receivable / Cr Income; the linked record is
            # now invoiced (an invoice is not proof of payment, §3.1).
            session = self._session_factory()
            try:
                record = self._get_row(session, revenue_id)
                record.invoice_id = invoice["id"]
                if record.lifecycle_status in ("EXPECTED", "ORDER_CREATED"):
                    record.classification = "invoiced"
                RevenueRepository(session).save(record)
                category = record.category
            finally:
                session.close()
            self._ledger.post_simple(
                principal, business_id, debit_code=C.ACCOUNT_RECEIVABLE,
                credit_code=C.REVENUE_CATEGORY_ACCOUNT[category],
                amount_minor=amount.minor, currency=amount.currency,
                entry_date=data["issued_date"],
                description=f"Invoice {data['number']} issued",
                source_type="invoice", source_id=invoice["id"],
                idempotency_key=f"invoice:{invoice['id']}:issue")
        return invoice

    def create_order(self, principal, business_id: str, data: dict) -> dict:
        amount: Money = data["amount"]
        session = self._session_factory()
        try:
            row = Order(
                business_id=business_id, external_ref=data.get("external_ref"),
                customer_ref=data.get("customer_ref"),
                amount_minor=amount.minor, currency=amount.currency,
                status="created", channel=data.get("channel"),
                order_date=data["order_date"], created_by=_actor(principal))
            OrderRepository(session).add(row)
            session.expunge(row)
            return order_dict(row)
        finally:
            session.close()

    # --------------------------------------------------------- subscriptions
    def create_subscription(self, principal, business_id: str, data: dict) -> dict:
        amount: Money = data["amount"]
        if data.get("interval", "monthly") not in ("monthly", "annual"):
            raise ValidationError("subscription interval must be monthly or annual")
        session = self._session_factory()
        try:
            row = Subscription(
                business_id=business_id, customer_ref=data.get("customer_ref"),
                plan_ref=data["plan_ref"], amount_minor=amount.minor,
                currency=amount.currency,
                interval=data.get("interval", "monthly"),
                status=data.get("status", "active"),
                started_date=data["started_date"],
                current_period_end=data.get("current_period_end"),
                created_by=_actor(principal))
            SubscriptionRepository(session).add(row)
            session.expunge(row)
            return subscription_dict(row)
        finally:
            session.close()

    def set_subscription_status(self, principal, subscription_id: str,
                                status: str) -> dict:
        if status not in ("trial", "active", "cancelled", "failed_renewal",
                          "expired"):
            raise ValidationError(f"unknown subscription status {status!r}")
        session = self._session_factory()
        try:
            repo = SubscriptionRepository(session)
            row = repo.get(subscription_id)
            if row is None:
                raise NotFoundError(f"subscription {subscription_id} not found")
            row.status = status
            repo.save(row)
            session.expunge(row)
            return subscription_dict(row)
        finally:
            session.close()

    @staticmethod
    def monthly_normalised_minor(subscription: Subscription) -> int:
        """MRR methodology (§6.3): a monthly plan contributes its
        amount; an annual plan contributes amount/12 (Decimal,
        half-even to the minor unit) — never the full annual amount,
        so annual plans are never double-counted."""
        if subscription.interval == "monthly":
            return subscription.amount_minor
        divided = (Decimal(subscription.amount_minor) / Decimal(12)).quantize(
            Decimal(1), rounding=ROUND_HALF_EVEN)
        return int(divided)

    # -------------------------------------------------------------- refunds
    def create_refund(self, principal, revenue_id: str, data: dict) -> dict:
        amount: Money = require_positive(data["amount"])
        session = self._session_factory()
        try:
            record = self._get_row(session, revenue_id)
            if record.verification_status != "verified" or \
                    record.classification not in ("collected", "recognized"):
                raise InvalidStateTransitionError(
                    "only verified collected revenue can be refunded")
            existing = RefundRepository(session).for_revenue(revenue_id)
            already = sum(r.amount_minor for r in existing)
            if already + amount.minor > record.amount_minor:
                raise ValidationError(
                    "refund exceeds the original payment amount")
            row = Refund(
                revenue_record_id=revenue_id, business_id=record.business_id,
                amount_minor=amount.minor, currency=amount.currency,
                reason=data.get("reason"), source=data.get("source", "manual"),
                external_ref=data.get("external_ref"),
                refund_date=data["refund_date"], created_by=_actor(principal))
            RefundRepository(session).add(row)
            session.expunge(row)
            refund = refund_dict(row)
            business_id = record.business_id
            category = record.category
            new_status = ("REFUNDED" if already + amount.minor == record.amount_minor
                          else "PARTIALLY_REFUNDED")
            record.lifecycle_status = new_status
            RevenueRepository(session).save(record)
        finally:
            session.close()
        entry = self._ledger.post_simple(
            principal, business_id,
            debit_code=C.REVENUE_CATEGORY_ACCOUNT[category],
            credit_code=C.ACCOUNT_PROCESSOR, amount_minor=amount.minor,
            currency=amount.currency, entry_date=data["refund_date"],
            description=f"Refund {refund['id']} for revenue {revenue_id}",
            source_type="refund", source_id=refund["id"],
            idempotency_key=f"refund:{refund['id']}")
        session = self._session_factory()
        try:
            repo = RefundRepository(session)
            stored = repo.get(refund["id"])
            stored.journal_entry_id = entry["id"]
            repo.save(stored)
        finally:
            session.close()
        self._audit(principal, "financial.refund_recorded", "refund",
                    refund["id"], "allow", None,
                    {"revenue_record_id": revenue_id})
        return {**refund, "journal_entry_id": entry["id"]}

    # ------------------------------------------------------------- disputes
    def create_dispute(self, principal, revenue_id: str, data: dict) -> dict:
        amount: Money = require_positive(data["amount"])
        session = self._session_factory()
        try:
            record = self._get_row(session, revenue_id)
            row = Dispute(
                revenue_record_id=revenue_id, business_id=record.business_id,
                amount_minor=amount.minor, currency=amount.currency,
                reason=data.get("reason"), kind=data.get("kind", "dispute"),
                status="opened", external_ref=data.get("external_ref"),
                opened_date=data["opened_date"], created_by=_actor(principal))
            DisputeRepository(session).add(row)
            session.expunge(row)
            dispute = dispute_dict(row)
            if record.lifecycle_status in ("PAYMENT_SETTLED", "VERIFIED",
                                           "RECOGNIZED", "PARTIALLY_REFUNDED"):
                record.lifecycle_status = ("CHARGEBACK" if row.kind == "chargeback"
                                           else "DISPUTED")
                RevenueRepository(session).save(record)
            business_id, category = record.business_id, record.category
            is_chargeback = row.kind == "chargeback"
        finally:
            session.close()
        if is_chargeback:
            entry = self._ledger.post_simple(
                principal, business_id,
                debit_code=C.REVENUE_CATEGORY_ACCOUNT[category],
                credit_code=C.ACCOUNT_PROCESSOR, amount_minor=amount.minor,
                currency=amount.currency, entry_date=data["opened_date"],
                description=f"Chargeback {dispute['id']} for revenue {revenue_id}",
                source_type="dispute", source_id=dispute["id"],
                idempotency_key=f"dispute:{dispute['id']}")
            dispute["journal_entry_id"] = entry["id"]
        return dispute

    # -------------------------------------------------------------- metrics
    def list_revenue(self, business_id: str, limit: int = 50,
                     offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            rows, total = RevenueRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [revenue_dict(r) for r in rows], total
        finally:
            session.close()

    def metrics(self, business_id: str, currency: str) -> dict:
        """Deterministic revenue metrics for one currency. Records in
        other currencies are counted separately and never summed in
        (§14). Net collected = verified collected + recognized −
        refunds − lost chargebacks."""
        session = self._session_factory()
        try:
            records = RevenueRepository(session).for_business(business_id)
            refunds = RefundRepository(session).for_business(business_id)
            disputes = DisputeRepository(session).for_business(business_id)
            invoices, _ = InvoiceRepository(session).list(
                limit=1000, business_id=business_id)
            subscriptions = SubscriptionRepository(session).active_for(business_id)
        finally:
            session.close()
        same = [r for r in records if r.currency == currency
                and not r.is_internal_transfer]
        buckets = {name: 0 for name in
                   ("projected", "booked", "invoiced", "collected", "recognized")}
        collected_count = 0
        collected_gross = 0
        for record in same:
            if record.lifecycle_status in ("CANCELLED", "FAILED", "REVERSED"):
                continue
            buckets[record.classification] = \
                buckets.get(record.classification, 0) + record.amount_minor
            if record.classification in ("collected", "recognized") \
                    and record.verification_status == "verified":
                collected_gross += record.amount_minor
                collected_count += 1
        refunds_total = sum(r.amount_minor for r in refunds
                            if r.currency == currency)
        chargebacks_total = sum(
            d.amount_minor for d in disputes
            if d.currency == currency and d.kind == "chargeback")
        disputed_open = sum(
            d.amount_minor for d in disputes
            if d.currency == currency and d.status == "opened")
        invoiced_total = sum(i.amount_minor for i in invoices
                             if i.currency == currency
                             and i.status != "cancelled")
        outstanding = sum(
            i.amount_minor for i in invoices
            if i.currency == currency
            and i.status in ("issued", "partially_paid", "overdue"))
        mrr = sum(self.monthly_normalised_minor(s) for s in subscriptions
                  if s.currency == currency)
        by_channel: dict[str, int] = {}
        by_product: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for record in same:
            if record.classification in ("collected", "recognized") \
                    and record.verification_status == "verified":
                by_channel[record.channel or "unspecified"] = \
                    by_channel.get(record.channel or "unspecified", 0) + record.amount_minor
                by_product[record.product_ref or "unspecified"] = \
                    by_product.get(record.product_ref or "unspecified", 0) + record.amount_minor
                by_category[record.category] = \
                    by_category.get(record.category, 0) + record.amount_minor
        return {
            "business_id": business_id, "currency": currency,
            "projected_minor": buckets["projected"],
            "booked_minor": buckets["booked"],
            "invoiced_minor": invoiced_total,
            "collected_gross_minor": collected_gross,
            "recognized_minor": buckets["recognized"],
            "refunds_minor": refunds_total,
            "chargebacks_minor": chargebacks_total,
            "disputed_open_minor": disputed_open,
            "net_collected_minor": collected_gross - refunds_total - chargebacks_total,
            "outstanding_receivables_minor": outstanding,
            "mrr_minor": mrr, "arr_minor": mrr * 12,
            "mrr_methodology": (
                "MRR = sum over ACTIVE subscription contracts of the "
                "monthly-normalised amount (monthly plan: its amount; "
                "annual plan: amount/12, half-even). Contracts are not "
                "cash: collected revenue is counted only from verified "
                "revenue records."),
            "average_order_value_minor": (
                collected_gross // collected_count if collected_count else None),
            "collected_count": collected_count,
            "by_channel_minor": by_channel, "by_product_minor": by_product,
            "by_category_minor": by_category,
            "other_currencies": sorted(
                {r.currency for r in records if r.currency != currency}),
        }


def invoice_dict(row: Invoice) -> dict:
    return {"id": row.id, "business_id": row.business_id, "number": row.number,
            "revenue_record_id": row.revenue_record_id,
            "customer_ref": row.customer_ref, "amount_minor": row.amount_minor,
            "currency": row.currency, "status": row.status,
            "issued_date": row.issued_date, "due_date": row.due_date,
            "created_by": row.created_by}


def order_dict(row: Order) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "external_ref": row.external_ref, "customer_ref": row.customer_ref,
            "amount_minor": row.amount_minor, "currency": row.currency,
            "status": row.status, "channel": row.channel,
            "order_date": row.order_date, "created_by": row.created_by}


def subscription_dict(row: Subscription) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "customer_ref": row.customer_ref, "plan_ref": row.plan_ref,
            "amount_minor": row.amount_minor, "currency": row.currency,
            "interval": row.interval, "status": row.status,
            "started_date": row.started_date,
            "current_period_end": row.current_period_end,
            "monthly_normalised_minor": RevenueService.monthly_normalised_minor(row),
            "created_by": row.created_by}


def refund_dict(row: Refund) -> dict:
    return {"id": row.id, "revenue_record_id": row.revenue_record_id,
            "business_id": row.business_id, "amount_minor": row.amount_minor,
            "currency": row.currency, "reason": row.reason,
            "source": row.source, "external_ref": row.external_ref,
            "refund_date": row.refund_date,
            "journal_entry_id": row.journal_entry_id,
            "created_by": row.created_by}


def dispute_dict(row: Dispute) -> dict:
    return {"id": row.id, "revenue_record_id": row.revenue_record_id,
            "business_id": row.business_id, "amount_minor": row.amount_minor,
            "currency": row.currency, "reason": row.reason, "kind": row.kind,
            "status": row.status, "external_ref": row.external_ref,
            "opened_date": row.opened_date,
            "journal_entry_id": row.journal_entry_id,
            "created_by": row.created_by}
