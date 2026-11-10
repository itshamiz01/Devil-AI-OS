"""Payment provider framework (§7). Provider-independent adapters;
the ledger never depends on a provider. The webhook pipeline is:
signature verification → timestamp/replay window → idempotency →
processing. A payment is classified collected ONLY through this
verified path (§7.3).

Honesty register (§29 Stage 5): only the deterministic FakeProvider
is exercised end-to-end. The Stripe adapter is interface + event
mapping, status ``interface_only`` / REQUIRES OWNER CONFIGURATION —
it has never been tested against Stripe's real interface and no real
keys or account data exist here. Webhook secrets are read from the
environment variable NAMED on the provider row; values are never
stored in the database, logged, or returned by any API (§23.1).
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import time

from sqlalchemy.exc import IntegrityError

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.financial import PaymentEvent, PaymentProvider
from ..database.repositories.financial import (
    PaymentEventRepository, PayoutRepository, ProviderRepository,
    RevenueRepository,
)
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from .money import Money, parse_amount
from .revenue import RevenueService


def _system(provider_name: str) -> Principal:
    return Principal(PrincipalType.SYSTEM, f"webhook:{provider_name}")


def payload_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# ------------------------------------------------------------------ adapters
class FakeProviderAdapter:
    """Deterministic in-repo test double implementing the full §7.1
    interface. Signature: HMAC-SHA256(secret, "<timestamp>.<body>")."""

    key = "fake"
    capabilities = {"payment_events": True, "verification": True,
                    "settlements": True, "refunds": True, "disputes": True,
                    "balances": False, "payouts": True, "health": True}

    def health(self) -> dict:
        return {"status": "ok", "adapter": self.key,
                "note": "deterministic test double — not a real provider"}

    def sign(self, secret: str, body: bytes, timestamp: int) -> str:
        message = f"{timestamp}.".encode() + body
        return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()

    def verify(self, secret: str, body: bytes, headers: dict) -> bool:
        signature = headers.get("x-fake-signature", "")
        timestamp = headers.get("x-fake-timestamp", "")
        if not signature or not timestamp:
            return False
        expected = self.sign(secret, body, int(timestamp)) \
            if timestamp.isdigit() else ""
        return hmac.compare_digest(expected, signature)

    def timestamp(self, headers: dict) -> int | None:
        raw = headers.get("x-fake-timestamp", "")
        return int(raw) if raw.isdigit() else None

    def parse(self, payload: dict) -> dict:
        return {
            "external_event_id": payload["event_id"],
            "event_type": payload["type"].replace(".", "_"),
            "external_ref": payload.get("payment_ref"),
            "business_id": payload.get("business_id"),
            "amount_minor": payload.get("amount_minor"),
            "currency": (payload.get("currency") or "").upper() or None,
            "occurred_date": payload.get("occurred_date"),
            "customer_ref": payload.get("customer_ref"),
            "raw": payload,
        }


class StripeAdapter:
    """Interface + Stripe-shaped event mapping ONLY. Status is
    ``interface_only``: never tested against Stripe's real interface
    in this environment (§29 Stage 5) — REQUIRES OWNER CONFIGURATION
    before any live use."""

    key = "stripe"
    capabilities = {"payment_events": True, "verification": True,
                    "settlements": True, "refunds": True, "disputes": True,
                    "balances": True, "payouts": True, "health": True}
    _TYPE_MAP = {
        "payment_intent.succeeded": "payment_settled",
        "charge.succeeded": "payment_settled",
        "payment_intent.payment_failed": "payment_failed",
        "charge.refunded": "refund_issued",
        "charge.dispute.created": "dispute_opened",
        "payout.paid": "payout_paid",
    }

    def health(self) -> dict:
        return {"status": "interface_only", "adapter": self.key,
                "note": "not configured; not tested against Stripe's real "
                        "interface (§29 Stage 5)"}

    def verify(self, secret: str, body: bytes, headers: dict) -> bool:
        # Stripe scheme: header "t=<ts>,v1=<hmac(secret, '<ts>.<body>')>".
        header = headers.get("stripe-signature", "")
        parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
        timestamp, signature = parts.get("t", ""), parts.get("v1", "")
        if not timestamp.isdigit() or not signature:
            return False
        message = f"{timestamp}.".encode() + body
        expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def timestamp(self, headers: dict) -> int | None:
        header = headers.get("stripe-signature", "")
        parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
        raw = parts.get("t", "")
        return int(raw) if raw.isdigit() else None

    def parse(self, payload: dict) -> dict:
        obj = (payload.get("data") or {}).get("object") or {}
        metadata = obj.get("metadata") or {}
        amount = obj.get("amount_received", obj.get("amount"))
        return {
            "external_event_id": payload["id"],
            "event_type": self._TYPE_MAP.get(payload.get("type", ""), "unknown"),
            "external_ref": obj.get("id"),
            "business_id": metadata.get("business_id"),
            "amount_minor": amount,  # Stripe amounts are already minor units
            "currency": (obj.get("currency") or "").upper() or None,
            "occurred_date": metadata.get("occurred_date"),
            "customer_ref": metadata.get("customer_ref"),
            "raw": payload,
        }


class CsvImportAdapter:
    """Offline bank/provider statement imports (§7.4)."""

    key = "csv_import"
    capabilities = {"payment_events": False, "verification": False,
                    "settlements": True, "refunds": False, "disputes": False,
                    "balances": True, "payouts": False, "health": True}

    def health(self) -> dict:
        return {"status": "ok", "adapter": self.key,
                "note": "offline CSV statement import"}


ADAPTERS = {"fake": FakeProviderAdapter(), "stripe": StripeAdapter(),
            "csv_import": CsvImportAdapter()}


def fake_webhook_headers(secret: str, body: bytes,
                         timestamp: int | None = None) -> dict:
    """Signing helper for tests/smoke (the FakeProvider's scheme)."""
    ts = int(time.time()) if timestamp is None else timestamp
    signature = ADAPTERS["fake"].sign(secret, body, ts)
    return {"x-fake-signature": signature, "x-fake-timestamp": str(ts)}


# ------------------------------------------------------------------- service
class PaymentsService:
    def __init__(self, session_factory, registry, revenue: RevenueService,
                 audit, settings_getter):
        self._session_factory = session_factory
        self._registry = registry
        self._revenue = revenue
        self._audit = audit
        self._settings = settings_getter

    # ------------------------------------------------------------ registry
    def seed_providers(self, actor: str = "system") -> None:
        session = self._session_factory()
        try:
            repo = ProviderRepository(session)
            seeds = [
                ("fake-provider", "fake", "active_fake", None),
                ("stripe", "stripe", "interface_only", "AUTONOMUS_STRIPE_WEBHOOK_SECRET"),
                ("csv-import", "csv_import", "configured", None),
            ]
            for name, key, status, secret_env in seeds:
                if repo.by_name(name) is None:
                    repo.add(PaymentProvider(
                        name=name, adapter_key=key, status=status,
                        webhook_secret_env=secret_env,
                        capabilities=ADAPTERS[key].capabilities,
                        config={}, created_by=actor))
        finally:
            session.close()

    def list_providers(self) -> list[dict]:
        session = self._session_factory()
        try:
            rows, _ = ProviderRepository(session).list(limit=100)
            return [provider_dict(r) for r in rows]
        finally:
            session.close()

    def get_provider(self, name: str) -> PaymentProvider:
        session = self._session_factory()
        try:
            row = ProviderRepository(session).by_name(name)
            if row is None:
                raise NotFoundError(f"payment provider {name!r} not found")
            session.expunge(row)
            return row
        finally:
            session.close()

    def provider_health(self, name: str) -> dict:
        provider = self.get_provider(name)
        adapter = ADAPTERS[provider.adapter_key]
        return {"provider": provider.name, "status": provider.status,
                **adapter.health()}

    # ------------------------------------------------------------- webhook
    def process_webhook(self, provider_name: str, raw_body: bytes,
                        headers: dict) -> dict:
        provider = self.get_provider(provider_name)
        principal = _system(provider_name)
        if provider.status in ("interface_only", "disabled"):
            self._audit(principal, "financial.webhook_rejected_unconfigured",
                        "payment_provider", provider.id, "deny",
                        f"provider status is {provider.status}; webhooks are "
                        "not processed until the owner configures the provider",
                        {})
            raise ValidationError(
                f"provider {provider_name!r} is {provider.status} — webhook "
                "processing requires owner configuration (§29 Stage 5)")
        adapter = ADAPTERS[provider.adapter_key]
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValidationError("webhook body is not valid JSON")
        secret_env = provider.webhook_secret_env
        secret = os.environ.get(secret_env) if secret_env else None
        if provider.adapter_key == "fake" and not secret:
            secret = "fake-provider-test-secret"  # test double only
        if not secret:
            raise ValidationError(
                "webhook secret is not available in the environment; "
                "the event cannot be verified and is rejected (§7.2)")
        if not adapter.verify(secret, raw_body, headers):
            event = self._record_event(provider, payload, adapter,
                                       signature_valid=False,
                                       status="rejected_forged", raw_body=raw_body)
            self._audit(principal, "financial.webhook_forged", "payment_event",
                        event["id"], "deny",
                        "signature verification failed; event recorded, "
                        "nothing posted", {})
            return {"accepted": False, "status": "rejected_forged",
                    "payment_event_id": event["id"]}
        window = int(self._settings().get("webhook_replay_window_seconds", 300))
        timestamp = adapter.timestamp(headers)
        if timestamp is None or abs(int(time.time()) - timestamp) > window:
            event = self._record_event(provider, payload, adapter,
                                       signature_valid=True,
                                       status="rejected_replay", raw_body=raw_body)
            self._audit(principal, "financial.webhook_replay", "payment_event",
                        event["id"], "deny",
                        "timestamp outside the replay window", {})
            return {"accepted": False, "status": "rejected_replay",
                    "payment_event_id": event["id"]}
        parsed = adapter.parse(payload)
        existing = self._find_event(provider.id, parsed["external_event_id"])
        if existing is not None:
            return {"accepted": True, "status": "duplicate",
                    "payment_event_id": existing["id"],
                    "revenue_record_id": existing["revenue_record_id"],
                    "note": "duplicate delivery safely acknowledged; "
                            "no second posting (§7.2)"}
        event = self._record_event(provider, payload, adapter,
                                   signature_valid=True, status="verified",
                                   raw_body=raw_body)
        if event.get("duplicate"):
            return {"accepted": True, "status": "duplicate",
                    "payment_event_id": event["id"],
                    "note": "concurrent duplicate suppressed by the unique "
                            "constraint (Scenario 11)"}
        return self._process_verified(principal, provider, event, parsed)

    def _find_event(self, provider_id: str, external_event_id: str) -> dict | None:
        session = self._session_factory()
        try:
            row = PaymentEventRepository(session).by_external(
                provider_id, external_event_id)
            if row is None:
                return None
            session.expunge(row)
            return event_dict(row)
        finally:
            session.close()

    def _record_event(self, provider: PaymentProvider, payload: dict, adapter,
                      *, signature_valid: bool, status: str,
                      raw_body: bytes) -> dict:
        try:
            parsed = adapter.parse(payload)
        except Exception:
            parsed = {"external_event_id": payload.get("event_id")
                      or payload.get("id") or "unparseable",
                      "event_type": "unparseable", "external_ref": None,
                      "business_id": None, "amount_minor": None,
                      "currency": None}
        session = self._session_factory()
        try:
            row = PaymentEvent(
                provider_id=provider.id,
                external_event_id=str(parsed["external_event_id"]),
                event_type=parsed["event_type"],
                business_id=parsed.get("business_id"),
                external_ref=parsed.get("external_ref"),
                amount_minor=parsed.get("amount_minor"),
                currency=parsed.get("currency"), payload=payload,
                payload_hash=payload_hash(raw_body),
                signature_valid=signature_valid, status=status,
                provenance={"adapter": provider.adapter_key,
                            "provider_status": provider.status})
            try:
                PaymentEventRepository(session).add(row)
            except IntegrityError:
                session.rollback()
                existing = PaymentEventRepository(session).by_external(
                    provider.id, str(parsed["external_event_id"]))
                if existing is not None:
                    session.expunge(existing)
                    return {**event_dict(existing), "duplicate": True}
                raise
            session.expunge(row)
            return event_dict(row)
        finally:
            session.close()

    def _process_verified(self, principal, provider: PaymentProvider,
                          event: dict, parsed: dict) -> dict:
        event_type = parsed["event_type"]
        session = self._session_factory()
        try:
            repo = PaymentEventRepository(session)
            row = repo.get(event["id"])
            if event_type == "payment_settled":
                outcome = self._settle(principal, parsed)
                row.status = "processed"
                row.revenue_record_id = outcome.get("revenue_record_id")
                row.journal_entry_id = outcome.get("journal_entry_id")
            elif event_type == "refund_issued":
                outcome = self._refund(principal, parsed)
                row.status = "processed"
                row.revenue_record_id = outcome.get("revenue_record_id")
            elif event_type == "dispute_opened":
                outcome = self._dispute(principal, parsed)
                row.status = "processed"
                row.revenue_record_id = outcome.get("revenue_record_id")
            elif event_type == "payout_paid":
                outcome = self._payout(principal, provider, parsed)
                row.status = "processed"
            elif event_type == "payment_failed":
                outcome = {"note": "failed payment recorded; no revenue created"}
                row.status = "processed"
            else:
                outcome = {"note": f"unknown event type {event_type!r}"}
                row.status = "dead_letter"
            repo.save(row)
            event_id = row.id
        finally:
            session.close()
        self._audit(principal, "financial.webhook_processed", "payment_event",
                    event_id, "allow", None,
                    {"event_type": event_type, **outcome})
        return {"accepted": True, "status": "processed",
                "payment_event_id": event_id, **outcome}

    def _find_revenue_by_ref(self, business_id: str | None,
                             external_ref: str | None) -> dict | None:
        if not external_ref:
            return None
        session = self._session_factory()
        try:
            rows = RevenueRepository(session).for_business(business_id) \
                if business_id else []
            for row in rows:
                if row.external_ref == external_ref:
                    session.expunge(row)
                    from .revenue import revenue_dict
                    return revenue_dict(row)
            return None
        finally:
            session.close()

    def _settle(self, principal, parsed: dict) -> dict:
        business_id = parsed.get("business_id")
        if not business_id:
            raise ValidationError("settled payment event carries no business_id")
        existing = self._find_revenue_by_ref(business_id, parsed.get("external_ref"))
        amount = Money(int(parsed["amount_minor"]), parsed["currency"])
        if existing is not None:
            if existing["verification_status"] != "verified":
                self._revenue.verify_revenue(
                    principal, existing["id"], source="verified_payment_event",
                    evidence={"provider_event": parsed["external_event_id"],
                              "external_ref": parsed.get("external_ref")})
            if existing["lifecycle_status"] not in ("VERIFIED", "RECOGNIZED",
                                                    "PAYMENT_SETTLED"):
                try:
                    self._revenue.transition(principal, existing["id"],
                                             "PAYMENT_SETTLED")
                except Exception:
                    pass
            record = self._revenue.get_revenue(existing["id"])
            if record["lifecycle_status"] == "PAYMENT_SETTLED":
                record = self._revenue.transition(principal, record["id"], "VERIFIED")
            return {"revenue_record_id": record["id"],
                    "journal_entry_id": record.get("journal_entry_id"),
                    "matched_existing": True}
        record = self._revenue.create_revenue(
            principal, business_id,
            {"category": "product_sale", "amount": amount,
             "transaction_date": parsed.get("occurred_date")
             or time.strftime("%Y-%m-%d"),
             "source": "verified_payment_event",
             "external_ref": parsed.get("external_ref"),
             "customer_ref": parsed.get("customer_ref"),
             "initial_status": "PAYMENT_SETTLED",
             "creation_method": "verified_webhook",
             "evidence": {"provider_event": parsed["external_event_id"]}},
            verified=True)
        return {"revenue_record_id": record["id"],
                "journal_entry_id": record.get("journal_entry_id"),
                "matched_existing": False}

    def _refund(self, principal, parsed: dict) -> dict:
        existing = self._find_revenue_by_ref(parsed.get("business_id"),
                                             parsed.get("external_ref"))
        if existing is None:
            return {"note": "refund references an unknown payment; recorded "
                            "for review, nothing posted"}
        refund = self._revenue.create_refund(
            principal, existing["id"],
            {"amount": Money(int(parsed["amount_minor"]), parsed["currency"]),
             "refund_date": parsed.get("occurred_date") or time.strftime("%Y-%m-%d"),
             "source": "verified_payment_event",
             "external_ref": parsed.get("external_ref"),
             "reason": "provider refund event"})
        return {"revenue_record_id": existing["id"], "refund_id": refund["id"]}

    def _dispute(self, principal, parsed: dict) -> dict:
        existing = self._find_revenue_by_ref(parsed.get("business_id"),
                                             parsed.get("external_ref"))
        if existing is None:
            return {"note": "dispute references an unknown payment; recorded "
                            "for review, nothing posted"}
        dispute = self._revenue.create_dispute(
            principal, existing["id"],
            {"amount": Money(int(parsed["amount_minor"]), parsed["currency"]),
             "opened_date": parsed.get("occurred_date") or time.strftime("%Y-%m-%d"),
             "kind": "dispute", "external_ref": parsed.get("external_ref"),
             "reason": "provider dispute event"})
        return {"revenue_record_id": existing["id"], "dispute_id": dispute["id"]}

    def _payout(self, principal, provider: PaymentProvider, parsed: dict) -> dict:
        session = self._session_factory()
        try:
            row_repo = PayoutRepository(session)
            from ..database.models.financial import ProviderPayout
            row = ProviderPayout(
                provider_id=provider.id, business_id=parsed.get("business_id"),
                external_ref=parsed.get("external_ref") or parsed["external_event_id"],
                amount_minor=int(parsed["amount_minor"]),
                currency=parsed["currency"], status="paid",
                received_date=parsed.get("occurred_date"),
                created_by=f"system:webhook:{provider.name}")
            try:
                row_repo.add(row)
            except IntegrityError:
                session.rollback()
                return {"note": "duplicate payout safely ignored"}
            return {"payout_id": row.id}
        finally:
            session.close()

    # --------------------------------------------------------- CSV import
    def import_statement(self, principal, business_id: str, *, csv_text: str,
                         source_type: str = "bank_statement",
                         source_ref: str | None = None) -> dict:
        """Parse a statement CSV (columns: date, description, amount,
        currency, external_ref?). Amounts are decimal strings. Rows
        are returned as normalised items for reconciliation; duplicate
        rows are detected by the reconciliation layer's dedupe."""
        reader = csv.DictReader(io.StringIO(csv_text))
        required = {"date", "description", "amount", "currency"}
        if reader.fieldnames is None or not required.issubset(
                {f.strip().lower() for f in reader.fieldnames}):
            raise ValidationError(
                f"statement CSV must have columns {sorted(required)}")
        items = []
        for raw in reader:
            row = {k.strip().lower(): (v or "").strip() for k, v in raw.items()}
            amount = parse_amount(row["amount"], row["currency"].upper(),
                                  self._registry, field="statement amount")
            items.append({
                "external_ref": row.get("external_ref") or None,
                "amount": amount, "date": row["date"],
                "description": row["description"],
            })
        return {"business_id": business_id, "source_type": source_type,
                "source_ref": source_ref, "items": items,
                "row_count": len(items)}


def provider_dict(row: PaymentProvider) -> dict:
    return {
        "id": row.id, "name": row.name, "adapter_key": row.adapter_key,
        "status": row.status,
        "webhook_secret_env": row.webhook_secret_env,
        "secret_value_exposed": False,
        "capabilities": row.capabilities, "config": row.config,
        "created_by": row.created_by,
    }


def event_dict(row: PaymentEvent) -> dict:
    return {
        "id": row.id, "provider_id": row.provider_id,
        "external_event_id": row.external_event_id,
        "event_type": row.event_type, "business_id": row.business_id,
        "external_ref": row.external_ref, "amount_minor": row.amount_minor,
        "currency": row.currency, "payload_hash": row.payload_hash,
        "signature_valid": row.signature_valid, "status": row.status,
        "journal_entry_id": row.journal_entry_id,
        "revenue_record_id": row.revenue_record_id,
        "provenance": row.provenance,
    }
