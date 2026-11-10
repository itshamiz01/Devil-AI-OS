"""Double-entry ledger (§5). Posting is a single database
transaction: an unbalanced or partially-written entry can never
persist (Scenario 12). Posted entries are immutable — the only
corrections are reversal and adjustment entries. Duplicate postings
are prevented by the unique idempotency key (Scenario 11)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy.exc import IntegrityError

from ..core.exceptions import (
    InvalidStateTransitionError, NotFoundError, PermissionDeniedError,
    ValidationError,
)
from ..permissions.models import PrincipalType
from ..database.models.financial import (
    FinancialAccount, FinancialPeriod, JournalEntry, JournalLine,
)
from ..database.repositories.financial import (
    AccountRepository, JournalRepository, PeriodRepository,
)
from ..events.events import EventType
from . import constants as C
from .money import CurrencyRegistry


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}"


class LedgerService:
    def __init__(self, session_factory, registry: CurrencyRegistry, audit):
        self._session_factory = session_factory
        self._registry = registry
        self._audit = audit  # callable(principal, action, target_type, target_id, decision, reason, details)
        # P-14 Stage B (DEF-I3): financial event publisher, assigned
        # by the FinancialService facade. Signature:
        # publish(event_type, payload). ``None`` → off.
        self.publish_event = None

    def _publish_financial(self, event_type, payload: dict) -> None:
        """Best-effort financial event publish (DEF-I3): publishing
        never changes the ledger result."""
        if self.publish_event is None:
            return
        try:
            self.publish_event(event_type, payload)
        except Exception as exc:  # publishing must not break the ledger
            import logging
            logging.getLogger("autonomus.financial").warning(
                "financial event publish failed: %s", exc)

    def assert_known_currency(self, currency: str) -> None:
        """§14/§23: amounts in unconfigured currencies are refused —
        precision rules for an unknown currency cannot be known."""
        if not self._registry.is_known(currency):
            raise ValidationError(
                f"currency {currency!r} is not configured in the "
                "financial settings; refusing the amount")

    # ------------------------------------------------------------- chart
    def seed_chart(self, session, business_id: str, currency: str, actor: str) -> int:
        repo = AccountRepository(session)
        existing = {a.code for a in repo.for_business(business_id)
                    if a.currency == currency}
        created = 0
        for code, name, account_type, subtype in C.DEFAULT_CHART:
            if code in existing:
                continue
            session.add(FinancialAccount(
                business_id=business_id, code=code, name=name,
                account_type=account_type, subtype=subtype,
                currency=currency, is_system=True, created_by=actor))
            created += 1
        session.commit()
        return created

    def list_accounts(self, business_id: str) -> list[dict]:
        session = self._session_factory()
        try:
            return [account_dict(a) for a in AccountRepository(session).for_business(business_id)]
        finally:
            session.close()

    def add_account(self, principal, business_id: str, data: dict) -> dict:
        session = self._session_factory()
        try:
            repo = AccountRepository(session)
            if repo.by_code(business_id, data["code"],
                            data["currency"]) is not None:
                raise ValidationError(f"account code {data['code']} already exists")
            row = FinancialAccount(
                business_id=business_id, code=data["code"], name=data["name"],
                account_type=data["account_type"],
                subtype=data.get("subtype", ""), currency=data["currency"],
                is_system=False, created_by=_actor(principal))
            repo.add(row)
            session.expunge(row)
            return account_dict(row)
        finally:
            session.close()

    # ------------------------------------------------------------ periods
    def ensure_period(self, session, business_id: str, date_str: str) -> FinancialPeriod:
        day = dt.date.fromisoformat(date_str)
        label = f"{day.year:04d}-{day.month:02d}"
        repo = PeriodRepository(session)
        period = repo.for_label(business_id, label)
        if period is None:
            start = day.replace(day=1)
            end = (start + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
            period = FinancialPeriod(
                business_id=business_id, period_type="month", label=label,
                start_date=start.isoformat(), end_date=end.isoformat(),
                status="open")
            session.add(period)
            session.flush()
        return period

    # ------------------------------------------------------------ posting
    def post_entry(self, principal, business_id: str, *, lines: list[dict],
                   entry_date: str, description: str = "",
                   reference: str | None = None, source_type: str = "manual",
                   source_id: str | None = None, kind: str = "standard",
                   reversal_of_id: str | None = None,
                   idempotency_key: str | None = None,
                   is_internal_transfer: bool = False,
                   counterpart_business_id: str | None = None,
                   approval_id: str | None = None,
                   reason: str | None = None) -> dict:
        """Post a balanced journal entry atomically. ``lines`` items:
        {account_id, debit_minor, credit_minor, currency, memo?}."""
        session = self._session_factory()
        try:
            repo = JournalRepository(session)
            if idempotency_key:
                existing = repo.by_idempotency_key(idempotency_key)
                if existing is not None:
                    return self._entry_dict(session, existing, duplicate=True)
            self._validate_lines(session, business_id, lines)
            period = self.ensure_period(session, business_id, entry_date)
            if period.status != "open":
                raise InvalidStateTransitionError(
                    f"accounting period {period.label} is closed")
            entry = JournalEntry(
                business_id=business_id, period_id=period.id,
                entry_date=entry_date, description=description,
                reference=reference, source_type=source_type,
                source_id=source_id, kind=kind, reversal_of_id=reversal_of_id,
                idempotency_key=idempotency_key,
                is_internal_transfer=is_internal_transfer,
                counterpart_business_id=counterpart_business_id,
                approval_id=approval_id, reason=reason,
                posted_by=_actor(principal))
            session.add(entry)
            session.flush()
            for line in lines:
                session.add(JournalLine(
                    entry_id=entry.id, account_id=line["account_id"],
                    debit_minor=int(line.get("debit_minor", 0)),
                    credit_minor=int(line.get("credit_minor", 0)),
                    currency=line["currency"], memo=line.get("memo")))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                if idempotency_key:
                    existing = repo.by_idempotency_key(idempotency_key)
                    if existing is not None:
                        return self._entry_dict(session, existing, duplicate=True)
                raise
            session.refresh(entry)
            result = self._entry_dict(session, entry)
            self._audit(principal, "financial.journal_posted", "journal_entry",
                        entry.id, "allow", None,
                        {"business_id": business_id, "source_type": source_type,
                         "kind": kind})
            # P-07 financial event (P-14 Stage B, DEF-I3): the journal
            # posting is persisted as a critical event.
            self._publish_financial(EventType.FINANCIAL_JOURNAL_POSTED, {
                "entry_id": entry.id, "business_id": business_id,
                "kind": kind, "source_type": source_type,
                "entry_date": entry_date})
            return result
        finally:
            session.close()

    def _validate_lines(self, session, business_id: str, lines: list[dict]) -> None:
        if not lines or len(lines) < 2:
            raise ValidationError("a journal entry needs at least two lines")
        accounts = AccountRepository(session)
        total_debit = 0
        total_credit = 0
        currencies = set()
        for line in lines:
            debit = line.get("debit_minor", 0)
            credit = line.get("credit_minor", 0)
            for value in (debit, credit):
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValidationError(
                        "journal line amounts must be integer minor units")
                if value < 0:
                    raise ValidationError("journal line amounts cannot be negative")
            if (debit > 0) == (credit > 0):
                raise ValidationError(
                    "each journal line must be a debit XOR a credit")
            account = accounts.get(line.get("account_id", ""))
            if account is None:
                raise NotFoundError(f"account {line.get('account_id')} not found")
            if account.business_id != business_id:
                raise ValidationError(
                    "journal line account belongs to a different business")
            if not account.is_active:
                raise ValidationError(f"account {account.code} is inactive")
            if line["currency"].upper() != account.currency:
                raise ValidationError(
                    f"line currency {line['currency']} does not match account "
                    f"{account.code} currency {account.currency}")
            currencies.add(line["currency"].upper())
            total_debit += debit
            total_credit += credit
        if len(currencies) != 1:
            raise ValidationError("a journal entry is single-currency (§14)")
        if total_debit == 0 or total_debit != total_credit:
            raise ValidationError(
                f"journal entry is unbalanced: debits {total_debit} != "
                f"credits {total_credit} (minor units)")

    def post_simple(self, principal, business_id: str, *, debit_code: str,
                    credit_code: str, amount_minor: int, currency: str,
                    entry_date: str, description: str = "",
                    reference: str | None = None, source_type: str = "manual",
                    source_id: str | None = None, kind: str = "standard",
                    idempotency_key: str | None = None,
                    is_internal_transfer: bool = False,
                    counterpart_business_id: str | None = None,
                    approval_id: str | None = None,
                    reason: str | None = None) -> dict:
        session = self._session_factory()
        try:
            accounts = AccountRepository(session)
            debit_account = accounts.by_code(business_id, debit_code,
                                             currency)
            credit_account = accounts.by_code(business_id, credit_code,
                                              currency)
            if debit_account is None or credit_account is None:
                # §14: a foreign-currency posting provisions the
                # system template accounts in that currency on first
                # use — the chart is per (business, currency), codes
                # come only from the §5.2 template, never invented.
                template = {code: (name, account_type, subtype)
                            for code, name, account_type, subtype
                            in C.DEFAULT_CHART}
                for code, missing in (
                        (debit_code, debit_account is None),
                        (credit_code, credit_account is None)):
                    if not missing:
                        continue
                    if code not in template:
                        raise NotFoundError(
                            f"account code {code} is not in the chart "
                            "template")
                    name, account_type, subtype = template[code]
                    session.add(FinancialAccount(
                        business_id=business_id, code=code, name=name,
                        account_type=account_type, subtype=subtype,
                        currency=currency, is_system=True,
                        created_by=_actor(principal)))
                session.commit()
                debit_account = accounts.by_code(business_id, debit_code,
                                                 currency)
                credit_account = accounts.by_code(business_id, credit_code,
                                                  currency)
            debit_id, credit_id = debit_account.id, credit_account.id
        finally:
            session.close()
        return self.post_entry(
            principal, business_id,
            lines=[
                {"account_id": debit_id, "debit_minor": amount_minor,
                 "credit_minor": 0, "currency": currency},
                {"account_id": credit_id, "debit_minor": 0,
                 "credit_minor": amount_minor, "currency": currency},
            ],
            entry_date=entry_date, description=description,
            reference=reference, source_type=source_type, source_id=source_id,
            kind=kind, idempotency_key=idempotency_key,
            is_internal_transfer=is_internal_transfer,
            counterpart_business_id=counterpart_business_id,
            approval_id=approval_id, reason=reason)

    # ----------------------------------------------------------- reversal
    def reverse_entry(self, principal, entry_id: str, *, reason: str) -> dict:
        # §5.3/§26.3: reversing posted history is owner-only, enforced
        # here as well as at the route layer (defense in depth).
        if principal.type != PrincipalType.OWNER:
            raise PermissionDeniedError(
                "reversing a posted journal entry is owner-only (§5.3)")
        if not reason or not reason.strip():
            raise ValidationError("a reversal requires a documented reason (§5.3)")
        session = self._session_factory()
        try:
            repo = JournalRepository(session)
            original = repo.get(entry_id)
            if original is None:
                raise NotFoundError(f"journal entry {entry_id} not found")
            if original.kind == "reversal":
                raise InvalidStateTransitionError("a reversal cannot be reversed")
            if repo.reversal_of(entry_id) is not None:
                raise InvalidStateTransitionError(
                    "entry already reversed; a second reversal would double-correct")
            lines = repo.lines(entry_id)
            swapped = [
                {"account_id": line.account_id,
                 "debit_minor": line.credit_minor,
                 "credit_minor": line.debit_minor,
                 "currency": line.currency,
                 "memo": f"reversal of {entry_id}"}
                for line in lines
            ]
            business_id = original.business_id
            entry_date = dt.date.today().isoformat()
            description = f"Reversal: {original.description}"
        finally:
            session.close()
        return self.post_entry(
            principal, business_id, lines=swapped, entry_date=entry_date,
            description=description, source_type="reversal",
            source_id=entry_id, kind="reversal", reversal_of_id=entry_id,
            idempotency_key=f"reversal:{entry_id}", reason=reason)

    # ------------------------------------------------------------- reads
    def get_entry(self, entry_id: str) -> dict:
        session = self._session_factory()
        try:
            entry = JournalRepository(session).get(entry_id)
            if entry is None:
                raise NotFoundError(f"journal entry {entry_id} not found")
            return self._entry_dict(session, entry)
        finally:
            session.close()

    def list_entries(self, business_id: str, limit: int = 50,
                     offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            repo = JournalRepository(session)
            rows, total = repo.list(limit=limit, offset=offset,
                                    business_id=business_id)
            return [self._entry_dict(session, row) for row in rows], total
        finally:
            session.close()

    def _entry_dict(self, session, entry: JournalEntry,
                    duplicate: bool = False) -> dict:
        repo = JournalRepository(session)
        lines = repo.lines(entry.id)
        return {
            "id": entry.id, "business_id": entry.business_id,
            "period_id": entry.period_id, "entry_date": entry.entry_date,
            "description": entry.description, "reference": entry.reference,
            "source_type": entry.source_type, "source_id": entry.source_id,
            "kind": entry.kind, "reversal_of_id": entry.reversal_of_id,
            "is_reversed": repo.reversal_of(entry.id) is not None,
            "idempotency_key": entry.idempotency_key,
            "is_internal_transfer": entry.is_internal_transfer,
            "counterpart_business_id": entry.counterpart_business_id,
            "approval_id": entry.approval_id, "reason": entry.reason,
            "posted_by": entry.posted_by,
            "total_debit_minor": sum(l.debit_minor for l in lines),
            "total_credit_minor": sum(l.credit_minor for l in lines),
            "currency": lines[0].currency if lines else None,
            "duplicate": duplicate,
            "lines": [
                {"id": l.id, "account_id": l.account_id,
                 "debit_minor": l.debit_minor, "credit_minor": l.credit_minor,
                 "currency": l.currency, "memo": l.memo} for l in lines],
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }

    # ----------------------------------------------------------- balances
    def account_balances(self, business_id: str) -> list[dict]:
        session = self._session_factory()
        try:
            accounts = AccountRepository(session).for_business(business_id)
            lines = JournalRepository(session).all_lines_for_business(business_id)
            totals: dict[str, dict[str, int]] = {}
            for line in lines:
                bucket = totals.setdefault(line.account_id,
                                           {"debit": 0, "credit": 0})
                bucket["debit"] += line.debit_minor
                bucket["credit"] += line.credit_minor
            result = []
            for account in accounts:
                bucket = totals.get(account.id, {"debit": 0, "credit": 0})
                if account.account_type in ("asset", "expense"):
                    balance = bucket["debit"] - bucket["credit"]
                else:
                    balance = bucket["credit"] - bucket["debit"]
                result.append({
                    **account_dict(account),
                    "total_debit_minor": bucket["debit"],
                    "total_credit_minor": bucket["credit"],
                    "balance_minor": balance,
                })
            return result
        finally:
            session.close()

    def account_balance(self, business_id: str, code: str) -> int:
        for row in self.account_balances(business_id):
            if row["code"] == code:
                return row["balance_minor"]
        raise NotFoundError(f"account {code} not found for business")

    # ---------------------------------------------------------- integrity
    def verify_integrity(self, business_id: str) -> dict:
        """Recompute everything from lines: any out-of-band tampering
        with a posted entry (changed amounts, cross-business lines)
        is detected and reported, never silently absorbed."""
        session = self._session_factory()
        try:
            repo = JournalRepository(session)
            entries = repo.for_business(business_id, limit=100000)
            problems: list[dict] = []
            accounts = {a.id: a for a in
                        AccountRepository(session).for_business(business_id)}
            for entry in entries:
                lines = repo.lines(entry.id)
                debit = sum(l.debit_minor for l in lines)
                credit = sum(l.credit_minor for l in lines)
                if debit != credit or debit == 0:
                    problems.append({
                        "entry_id": entry.id, "problem": "unbalanced",
                        "debit_minor": debit, "credit_minor": credit})
                currencies = {l.currency for l in lines}
                if len(currencies) > 1:
                    problems.append({"entry_id": entry.id,
                                     "problem": "multi_currency_lines"})
                for line in lines:
                    account = accounts.get(line.account_id)
                    if account is None:
                        problems.append({
                            "entry_id": entry.id, "problem": "line_account_foreign",
                            "line_id": line.id})
                    if line.debit_minor < 0 or line.credit_minor < 0:
                        problems.append({"entry_id": entry.id,
                                         "problem": "negative_line",
                                         "line_id": line.id})
            return {"business_id": business_id, "ok": not problems,
                    "entries_checked": len(entries), "problems": problems}
        finally:
            session.close()


def account_dict(account: FinancialAccount) -> dict:
    return {
        "id": account.id, "business_id": account.business_id,
        "code": account.code, "name": account.name,
        "account_type": account.account_type, "subtype": account.subtype,
        "currency": account.currency, "is_system": account.is_system,
        "is_active": account.is_active, "created_by": account.created_by,
    }
