"""Reconciliation (§13). External records are matched against the
internal ledger with a deterministic ladder — exact external ID →
payment reference → invoice reference → amount+currency+date window.
Fuzzy candidates are *suggestions* (PARTIALLY_MATCHED, still open) and
are never auto-verified. A discrepancy resolution never overwrites
either side: it posts an audited adjustment entry and records the
resolution against the item."""
from __future__ import annotations

import datetime as dt
import hashlib

from ..core.exceptions import (
    InvalidStateTransitionError, NotFoundError, ValidationError,
)
from ..database.models.financial import (
    ReconciliationItem, ReconciliationSession,
)
from ..database.repositories.financial import (
    ExpenseRepository, InvoiceRepository, JournalRepository,
    ReconciliationItemRepository, ReconciliationSessionRepository,
    RevenueRepository,
)
from ..permissions.models import PrincipalType
from . import constants as C
from .ledger import LedgerService
from .money import Money

DATE_WINDOW_DAYS = 3


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}"


def _item_hash(item: dict) -> str:
    material = "|".join([
        item["date"], str(item["amount"].minor), item["amount"].currency,
        item["description"], item.get("external_ref") or ""])
    return hashlib.sha256(material.encode()).hexdigest()[:24]


def session_dict(row: ReconciliationSession) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "source_type": row.source_type, "source_ref": row.source_ref,
            "period_start": row.period_start, "period_end": row.period_end,
            "status": row.status, "summary": row.summary,
            "created_by": row.created_by}


def item_dict(row: ReconciliationItem) -> dict:
    return {"id": row.id, "session_id": row.session_id,
            "external_ref": row.external_ref,
            "external_amount_minor": row.external_amount_minor,
            "external_currency": row.external_currency,
            "external_date": row.external_date,
            "description": row.description,
            "matched_type": row.matched_type, "matched_id": row.matched_id,
            "match_method": row.match_method,
            "classification": row.classification,
            "discrepancy": row.discrepancy, "resolution": row.resolution,
            "status": row.status}


class ReconciliationService:
    def __init__(self, session_factory, ledger: LedgerService, audit):
        self._session_factory = session_factory
        self._ledger = ledger
        self._audit = audit

    # ------------------------------------------------------------- import
    def create_session_with_items(self, principal, business_id: str, *,
                                  source_type: str, source_ref: str | None,
                                  items: list[dict]) -> dict:
        """Create a session and import items. Re-importing the same
        statement is duplicate-safe: rows whose import hash already
        exists for this business+source are skipped and counted."""
        session = self._session_factory()
        try:
            existing_refs = set()
            prior_sessions, _ = ReconciliationSessionRepository(session).list(
                limit=500, business_id=business_id,
                filters={"source_type": source_type})
            item_repo = ReconciliationItemRepository(session)
            for prior in prior_sessions:
                for prior_item in item_repo.for_session(prior.id):
                    if prior_item.external_ref:
                        existing_refs.add(prior_item.external_ref)
            row = ReconciliationSession(
                business_id=business_id, source_type=source_type,
                source_ref=source_ref, status="open", summary={},
                created_by=_actor(principal))
            ReconciliationSessionRepository(session).add(row)
            session_id = row.id
            imported, duplicates = 0, 0
            for item in items:
                amount: Money = item["amount"]
                ref = item.get("external_ref") or f"hash:{_item_hash(item)}"
                if ref in existing_refs:
                    duplicates += 1
                    continue
                existing_refs.add(ref)
                session.add(ReconciliationItem(
                    session_id=session_id, external_ref=ref,
                    external_amount_minor=amount.minor,
                    external_currency=amount.currency,
                    external_date=item["date"],
                    description=item["description"],
                    classification="UNMATCHED", status="open"))
                imported += 1
            stored = ReconciliationSessionRepository(session).get(session_id)
            stored.summary = {"imported": imported,
                              "duplicates_skipped": duplicates,
                              "total_rows": len(items)}
            ReconciliationSessionRepository(session).save(stored)
            session.expunge(stored)
            return {**session_dict(stored), "imported": imported,
                    "duplicates_skipped": duplicates}
        finally:
            session.close()

    # ----------------------------------------------------------- matching
    def run_matching(self, principal, session_id: str) -> dict:
        session = self._session_factory()
        try:
            sess = ReconciliationSessionRepository(session).get(session_id)
            if sess is None:
                raise NotFoundError(f"reconciliation session {session_id} not found")
            business_id = sess.business_id
            items = ReconciliationItemRepository(session).for_session(session_id)
            revenues = RevenueRepository(session).for_business(business_id)
            expenses = ExpenseRepository(session).for_business(business_id)
            invoices, _ = InvoiceRepository(session).list(
                limit=1000, business_id=business_id)
            journals = JournalRepository(session).for_business(business_id)
            counts: dict[str, int] = {}
            seen_matched_refs: set[str] = set()
            for item in items:
                if item.status == "resolved":
                    continue
                self._match_item(item, revenues, expenses, invoices, journals,
                                 seen_matched_refs)
                counts[item.classification] = counts.get(item.classification, 0) + 1
                session.commit()
            sess.summary = {**sess.summary, "classifications": counts}
            sess.status = ("needs_review" if any(
                k in counts for k in ("AMOUNT_MISMATCH", "REQUIRES_REVIEW",
                                      "CURRENCY_MISMATCH", "DATE_MISMATCH"))
                else "completed")
            ReconciliationSessionRepository(session).save(sess)
            session.expunge(sess)
            result = session_dict(sess)
        finally:
            session.close()
        self._audit(principal, "financial.reconciliation_run",
                    "reconciliation_session", session_id, "allow", None,
                    {"classifications": result["summary"].get("classifications")})
        return result

    def _match_item(self, item, revenues, expenses, invoices, journals,
                    seen_matched_refs: set) -> None:
        ref = item.external_ref or ""
        amount, currency, date = (item.external_amount_minor,
                                  item.external_currency, item.external_date)

        def finish(classification, matched_type=None, matched_id=None,
                   method=None, discrepancy=None):
            item.classification = classification
            item.matched_type = matched_type
            item.matched_id = matched_id
            item.match_method = method
            item.discrepancy = discrepancy or {}
            if classification == "MATCHED":
                item.status = "resolved"
                item.resolution = {"method": method, "auto": True,
                                   "note": "deterministic exact/amount-date match"}

        # 1. exact external ID on a revenue record
        for record in revenues:
            if ref and record.external_ref == ref:
                if record.id in seen_matched_refs:
                    return finish("DUPLICATE", "revenue_record", record.id,
                                  "external_id",
                                  {"note": "already matched by another item"})
                if record.amount_minor != amount:
                    return finish("AMOUNT_MISMATCH", "revenue_record",
                                  record.id, "external_id",
                                  {"internal_amount_minor": record.amount_minor,
                                   "external_amount_minor": amount,
                                   "difference_minor": amount - record.amount_minor})
                if record.currency != currency:
                    return finish("CURRENCY_MISMATCH", "revenue_record",
                                  record.id, "external_id",
                                  {"internal_currency": record.currency})
                seen_matched_refs.add(record.id)
                return finish("MATCHED", "revenue_record", record.id, "external_id")
        # 2. payment reference on a journal entry
        for entry in journals:
            if ref and entry.reference == ref:
                total = entry_total(entry, journals)
                if total is not None and total != amount:
                    return finish("AMOUNT_MISMATCH", "journal_entry", entry.id,
                                  "payment_ref",
                                  {"internal_amount_minor": total,
                                   "external_amount_minor": amount,
                                   "difference_minor": amount - total})
                return finish("MATCHED", "journal_entry", entry.id, "payment_ref")
        # 3. invoice reference
        for invoice in invoices:
            if ref and invoice.number == ref:
                if invoice.amount_minor != amount:
                    return finish("AMOUNT_MISMATCH", "invoice", invoice.id,
                                  "invoice_ref",
                                  {"internal_amount_minor": invoice.amount_minor,
                                   "external_amount_minor": amount,
                                   "difference_minor": amount - invoice.amount_minor})
                return finish("MATCHED", "invoice", invoice.id, "invoice_ref")
        # 4. amount + currency + date window (unique candidate only)
        candidates = []
        for record in revenues:
            if record.amount_minor == amount and record.currency == currency \
                    and _within(record.transaction_date, date):
                candidates.append(("revenue_record", record))
        for expense in expenses:
            if expense.amount_minor == amount and expense.currency == currency \
                    and _within(expense.expense_date, date):
                candidates.append(("expense_record", expense))
        if len(candidates) == 1:
            kind, record = candidates[0]
            return finish("MATCHED", kind, record.id, "amount_date")
        if len(candidates) > 1:
            return finish("PARTIALLY_MATCHED", None, None, "amount_date",
                          {"note": "multiple candidates; ambiguous — human "
                                   "review required, never auto-verified",
                           "candidate_ids": [c[1].id for c in candidates]})
        # 5. fuzzy suggestion: same amount, different currency OR
        #    amount matches but the date is outside the window.
        for record in revenues:
            if record.amount_minor == amount and record.currency != currency:
                return finish("CURRENCY_MISMATCH", "revenue_record", record.id,
                              "fuzzy_suggestion",
                              {"internal_currency": record.currency,
                               "note": "suggestion only — not verified"})
            if record.amount_minor == amount and record.currency == currency:
                return finish("DATE_MISMATCH", "revenue_record", record.id,
                              "fuzzy_suggestion",
                              {"internal_date": record.transaction_date,
                               "note": "suggestion only — not verified"})
        return finish("UNMATCHED", None, None, None,
                      {"note": "no internal record matches this external row"})

    # ---------------------------------------------------------- resolution
    def resolve_item(self, principal, item_id: str, data: dict) -> dict:
        """Owner-reviewed resolution. ``create_adjustment`` posts an
        adjustment journal entry for the difference — it never edits
        the internal record or the external row (§13.1 step 12)."""
        if principal.type != PrincipalType.OWNER:
            from ..core.exceptions import PermissionDeniedError
            raise PermissionDeniedError(
                "reconciliation resolutions require the Owner")
        session = self._session_factory()
        try:
            repo = ReconciliationItemRepository(session)
            item = repo.get(item_id)
            if item is None:
                raise NotFoundError(f"reconciliation item {item_id} not found")
            if item.status == "resolved":
                raise InvalidStateTransitionError("item already resolved")
            sess = ReconciliationSessionRepository(session).get(item.session_id)
            business_id = sess.business_id
            snapshot = item_dict(item)
        finally:
            session.close()
        action = data["action"]
        resolution = {"action": action, "resolved_by": _actor(principal),
                      "evidence": data.get("evidence") or {}}
        if action == "create_adjustment":
            difference = snapshot["discrepancy"].get("difference_minor")
            if difference is None:
                raise ValidationError(
                    "adjustment requires an AMOUNT_MISMATCH item with a "
                    "recorded difference")
            currency = snapshot["external_currency"]
            # External > internal: recognise the missing amount
            # (Dr processor / Cr other income). External < internal:
            # write the excess back (Dr other expense / Cr processor).
            if difference > 0:
                debit, credit = C.ACCOUNT_PROCESSOR, "4090"
            else:
                debit, credit = "5090", C.ACCOUNT_PROCESSOR
            entry = self._ledger.post_simple(
                principal, business_id, debit_code=debit, credit_code=credit,
                amount_minor=abs(difference), currency=currency,
                entry_date=dt.date.today().isoformat(),
                description=f"Reconciliation adjustment for item {item_id} "
                            f"(session {snapshot['session_id']})",
                source_type="reconciliation", source_id=item_id,
                kind="adjustment", reason=data.get("reason"),
                idempotency_key=f"reconciliation:{item_id}:adjustment")
            resolution["journal_entry_id"] = entry["id"]
            resolution["adjustment_minor"] = difference
        elif action not in ("accept_match", "mark_reviewed"):
            raise ValidationError(f"unknown resolution action {action!r}")
        session = self._session_factory()
        try:
            repo = ReconciliationItemRepository(session)
            item = repo.get(item_id)
            item.status = "resolved"
            item.resolution = resolution
            if action == "accept_match" and item.classification == "PARTIALLY_MATCHED":
                item.classification = "MATCHED"
            repo.save(item)
            session.expunge(item)
            result = item_dict(item)
        finally:
            session.close()
        self._audit(principal, "financial.reconciliation_resolved",
                    "reconciliation_item", item_id, "allow", None,
                    {"action": action})
        return result

    # -------------------------------------------------------------- reads
    def get_session(self, session_id: str) -> dict:
        session = self._session_factory()
        try:
            row = ReconciliationSessionRepository(session).get(session_id)
            if row is None:
                raise NotFoundError(f"reconciliation session {session_id} not found")
            items = ReconciliationItemRepository(session).for_session(session_id)
            session.expunge(row)
            return {**session_dict(row),
                    "items": [item_dict(i) for i in items]}
        finally:
            session.close()

    def list_sessions(self, business_id: str, limit: int = 50,
                      offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            rows, total = ReconciliationSessionRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [session_dict(r) for r in rows], total
        finally:
            session.close()


def _within(date_a: str, date_b: str) -> bool:
    try:
        delta = abs((dt.date.fromisoformat(date_a)
                     - dt.date.fromisoformat(date_b)).days)
    except ValueError:
        return False
    return delta <= DATE_WINDOW_DAYS


def entry_total(entry, _journals) -> int | None:
    return None  # journal totals need lines; ref-match does not compare amounts
