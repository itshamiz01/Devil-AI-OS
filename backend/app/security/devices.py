"""Identity & Device Security (Expansion Feature 1).

Extends P-10 — the one security authority — with the two identity
capabilities the Gate 2 readiness review found missing: a device
registry with session binding, and MFA recovery codes (the
standing P-10 limitation "recovery codes NOT IMPLEMENTED").

Nothing here is a parallel system:

- devices and recovery codes are governed by the same
  ``SecurityService`` facade that owns P-10; every event is
  written to the P-01 ``audit_events`` trail through the facade's
  audit callback (actions ``security.device_*`` /
  ``security.recovery_*``) — no parallel log exists;
- sessions remain P-01 ``app_sessions`` rows; binding is one
  additive nullable column (``device_id``) plus enforcement in
  ``DeviceService`` and in the P-01 resolution path;
- the device hook into ``AuthService`` follows the exact
  ``login_guard`` precedent: an optional, late-attached object
  (``Application.startup`` wires it after P-10 is built). With no
  hook wired, P-01 login behaviour is unchanged — except that
  *presenting* device credentials with no hook wired fails closed.

Secrets discipline: a device secret is a 256-bit random credential
shown exactly once at enrolment/rotation; only its SHA-256 hash
is stored (the P-01 session-token pattern). Recovery codes are
lower-entropy secrets, so they are stored only as scrypt hashes
(P-01's ``hash_password``) and shown exactly once at generation.
Neither value is ever logged, audited or returned again.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from sqlalchemy import select

from ..core.auth import hash_password, verify_password
from ..core.exceptions import (
    InvalidStateTransitionError, NotFoundError, PermissionDeniedError,
    ValidationError,
)
from ..database.models.base import new_uuid, utcnow
from ..database.models.core import AppSession
from ..database.models.security import SecurityDevice, SecurityRecoveryCode
from ..database.repositories.security import (
    DeviceRepository, RecoveryCodeRepository,
)
from ..permissions.models import Principal, PrincipalType
from . import policy as P

# ------------------------------------------------------------ devices
TRUST_UNTRUSTED = "untrusted"
TRUST_TRUSTED = "trusted"
TRUST_REVOKED = "revoked"


def _device_secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def device_to_dict(row: SecurityDevice) -> dict:
    """The device as the API returns it. ``secret_hash`` is never
    included: outputs structurally cannot contain credential
    material, exactly like the P-10 secret registry's dicts."""
    return {
        "id": row.id,
        "principal": f"{row.principal_type}:{row.principal_id}",
        "label": row.label,
        "platform": row.platform,
        "device_name": row.device_name,
        "trust_status": row.trust_status,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "revoked_by": row.revoked_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class DeviceService:
    """The device registry: enrolment, trust, revocation, secret
    rotation, and the ``AuthService`` device-hook protocol."""

    def __init__(self, session_factory, audit):
        self._session_factory = session_factory
        self._audit = audit

    # ------------------------------------------------------- owner ops
    def enrol(self, principal: Principal, data: dict) -> dict:
        """Register a new device for the owner identity. The device
        starts UNTRUSTED — trust is a separate explicit owner act —
        and its credential is returned in this response only."""
        self._require_owner(principal, "device enrolment")
        label = (data.get("label") or "").strip()
        if not label:
            raise ValidationError("a device label is required")
        secret = secrets.token_urlsafe(32)
        session = self._session_factory()
        try:
            row = DeviceRepository(session).add(SecurityDevice(
                principal_type=principal.type.value,
                principal_id=principal.id,
                label=label,
                platform=(data.get("platform") or None),
                device_name=(data.get("device_name") or None),
                secret_hash=_device_secret_hash(secret),
                trust_status=TRUST_UNTRUSTED))
            result = device_to_dict(row)
        finally:
            session.close()
        result["device_secret"] = secret
        result["secret_shown_once"] = True
        self._audit(principal, "security.device_enrolled", "device",
                    result["id"], "allow",
                    "device enrolled (untrusted until the owner trusts it)",
                    {"label": label, "trust_status": TRUST_UNTRUSTED})
        return result

    def list_devices(self, principal: Principal) -> list[dict]:
        self._require_owner(principal, "device visibility")
        session = self._session_factory()
        try:
            rows = DeviceRepository(session).list_for(
                principal.type.value, principal.id)
            return [device_to_dict(r) for r in rows]
        finally:
            session.close()

    def get_device(self, principal: Principal, device_id: str) -> dict:
        self._require_owner(principal, "device visibility")
        session = self._session_factory()
        try:
            row = self._owned_device(session, principal, device_id)
            return device_to_dict(row)
        finally:
            session.close()

    def relabel(self, principal: Principal, device_id: str, data: dict) -> dict:
        self._require_owner(principal, "device changes")
        session = self._session_factory()
        try:
            row = self._owned_device(session, principal, device_id)
            if row.trust_status == TRUST_REVOKED:
                raise InvalidStateTransitionError(
                    "a revoked device is terminal and cannot be changed")
            changed = []
            if data.get("label") is not None:
                label = str(data["label"]).strip()
                if not label:
                    raise ValidationError("a device label must not be empty")
                row.label = label
                changed.append("label")
            if "platform" in data:
                row.platform = data["platform"] or None
                changed.append("platform")
            if "device_name" in data:
                row.device_name = data["device_name"] or None
                changed.append("device_name")
            result = device_to_dict(DeviceRepository(session).save(row))
        finally:
            session.close()
        self._audit(principal, "security.device_relabelled", "device",
                    device_id, "allow", "device metadata updated",
                    {"changed": changed})
        return result

    def set_trust(self, principal: Principal, device_id: str,
                  trusted: bool) -> dict:
        """The owner's trust decision. Untrusting sweeps (revokes)
        every session bound to the device: a device that is no
        longer trusted must not hold live sessions."""
        self._require_owner(principal, "device trust changes")
        session = self._session_factory()
        try:
            row = self._owned_device(session, principal, device_id)
            if row.trust_status == TRUST_REVOKED:
                raise InvalidStateTransitionError(
                    "a revoked device is terminal; enrol a new device instead")
            target = TRUST_TRUSTED if trusted else TRUST_UNTRUSTED
            if row.trust_status == target:
                raise InvalidStateTransitionError(
                    f"device is already {target}")
            row.trust_status = target
            swept = 0
            if not trusted:
                swept = self._sweep_sessions(session, device_id)
            result = device_to_dict(DeviceRepository(session).save(row))
        finally:
            session.close()
        self._audit(principal,
                    "security.device_trusted" if trusted
                    else "security.device_untrusted",
                    "device", device_id, "allow",
                    f"device marked {target} by the owner",
                    {"sessions_revoked": swept})
        return result

    def revoke(self, principal: Principal, device_id: str) -> dict:
        """Terminal revocation: the credential dies and every bound
        session is revoked with it."""
        self._require_owner(principal, "device revocation")
        session = self._session_factory()
        try:
            row = self._owned_device(session, principal, device_id)
            if row.trust_status == TRUST_REVOKED:
                raise InvalidStateTransitionError("device is already revoked")
            row.trust_status = TRUST_REVOKED
            row.revoked_at = utcnow()
            row.revoked_by = P.actor(principal)
            swept = self._sweep_sessions(session, device_id)
            result = device_to_dict(DeviceRepository(session).save(row))
        finally:
            session.close()
        self._audit(principal, "security.device_revoked", "device",
                    device_id, "allow", "device revoked by the owner",
                    {"sessions_revoked": swept})
        return result

    def rotate_secret(self, principal: Principal, device_id: str) -> dict:
        """Credential rotation: a fresh device secret (returned in
        this response only); the old secret stops working at once
        and every bound session is revoked, so a leaked credential
        cannot survive rotation."""
        self._require_owner(principal, "device credential rotation")
        session = self._session_factory()
        try:
            row = self._owned_device(session, principal, device_id)
            if row.trust_status == TRUST_REVOKED:
                raise InvalidStateTransitionError(
                    "a revoked device is terminal and cannot be rotated")
            secret = secrets.token_urlsafe(32)
            row.secret_hash = _device_secret_hash(secret)
            swept = self._sweep_sessions(session, device_id)
            result = device_to_dict(DeviceRepository(session).save(row))
        finally:
            session.close()
        result["device_secret"] = secret
        result["secret_shown_once"] = True
        self._audit(principal, "security.device_secret_rotated", "device",
                    device_id, "allow",
                    "device credential rotated by the owner",
                    {"sessions_revoked": swept})
        return result

    # ------------------------------------------- AuthService hook protocol
    # Consulted by AuthService.login / resolve_bearer when wired
    # (the login_guard pattern). These methods never raise into the
    # auth path: a refusal is a boolean, and AuthService fails
    # closed on any exception.

    def verify_device_credential(self, device_id: str,
                                 device_secret: str) -> bool:
        """May a login bind a session to this device? Only a
        TRUSTED device with a matching credential. Every refusal is
        audited with a reason category — never the secret."""
        session = self._session_factory()
        try:
            row = session.get(SecurityDevice, device_id)
            if row is None:
                category = "unknown_device"
            elif row.trust_status == TRUST_REVOKED:
                category = "device_revoked"
            elif row.trust_status != TRUST_TRUSTED:
                category = "device_not_trusted"
            elif not hmac.compare_digest(
                    _device_secret_hash(device_secret), row.secret_hash):
                category = "bad_secret"
            else:
                return True
        finally:
            session.close()
        self._audit(None, "security.device_credential_refused", "device",
                    device_id, "deny",
                    f"device credential refused at login: {category}",
                    {"reason": category})
        return False

    def note_device_login(self, device_id: str) -> None:
        """Record a successful device-bound login: last-seen moves
        and the login itself enters the audit trail under the
        device's registered identity."""
        session = self._session_factory()
        try:
            row = session.get(SecurityDevice, device_id)
            if row is None:
                return
            row.last_seen_at = utcnow()
            DeviceRepository(session).save(row)
            identity = Principal(
                PrincipalType(row.principal_type), row.principal_id)
            label = row.label
        finally:
            session.close()
        self._audit(identity, "security.device_login", "device",
                    device_id, "allow",
                    "session bound to device at login", {"label": label})

    def session_device_trusted(self, device_id: str) -> bool:
        """Resolution-time check used by ``AuthService``: a bound
        session is valid only while its device is trusted."""
        session = self._session_factory()
        try:
            row = session.get(SecurityDevice, device_id)
            return row is not None and row.trust_status == TRUST_TRUSTED
        finally:
            session.close()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _require_owner(principal: Principal, what: str) -> None:
        if not P.is_owner(principal):
            raise PermissionDeniedError(
                f"{what} is owner-only (the device registry belongs to "
                f"the owner identity)")

    @staticmethod
    def _owned_device(session, principal: Principal,
                      device_id: str) -> SecurityDevice:
        """Fetch a device owned by this principal. A device that
        belongs to another identity is indistinguishable from
        missing (the P-18 cross-store pattern)."""
        row = session.get(SecurityDevice, device_id)
        if row is None or row.principal_type != principal.type.value \
                or row.principal_id != principal.id:
            raise NotFoundError(f"device {device_id} not found")
        return row

    @staticmethod
    def _sweep_sessions(session, device_id: str) -> int:
        """Revoke every live session bound to the device, in the
        caller's transaction (the repository save that follows
        commits the sweep together with the device change)."""
        rows = list(session.scalars(
            select(AppSession).where(
                AppSession.device_id == device_id,
                AppSession.revoked == False)))  # noqa: E712
        for row in rows:
            row.revoked = True
        return len(rows)


# --------------------------------------------------------- recovery codes
# Unambiguous alphabet (no 0/O, 1/I/L confusables): 31 symbols;
# 12 characters in 4-4-4 groups carry ~59 bits per code.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_COUNT_DEFAULT = 10
CODE_COUNT_MIN = 1
CODE_COUNT_MAX = 20


def _new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(12))
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"


def _normalize_code(code: str) -> str:
    return "".join(ch for ch in (code or "") if ch.isalnum()).upper()


class RecoveryCodeService:
    """MFA recovery codes for the owner identity — the governed
    fallback primitive beside P-10's TOTP verifier. Generation is
    the only moment plaintext codes exist outside the owner's
    hands; verification consumes a code exactly once."""

    def __init__(self, session_factory, audit):
        self._session_factory = session_factory
        self._audit = audit

    def generate(self, principal: Principal,
                 count: int = CODE_COUNT_DEFAULT) -> dict:
        """Mint a fresh batch. Every still-unused code from earlier
        batches is invalidated first, so exactly one live batch
        exists per owner identity."""
        self._require_owner(principal)
        if not isinstance(count, int) or isinstance(count, bool) \
                or not CODE_COUNT_MIN <= count <= CODE_COUNT_MAX:
            raise ValidationError(
                f"count must be between {CODE_COUNT_MIN} and {CODE_COUNT_MAX}")
        batch_id = new_uuid()
        session = self._session_factory()
        try:
            repo = RecoveryCodeRepository(session)
            invalidated = 0
            for row in repo.unused_for(principal.type.value, principal.id):
                row.status = "invalidated"
                repo.save(row)
                invalidated += 1
            codes: list[str] = []
            for _ in range(count):
                code = _new_code()
                repo.add(SecurityRecoveryCode(
                    principal_type=principal.type.value,
                    principal_id=principal.id,
                    batch_id=batch_id,
                    code_hash=hash_password(_normalize_code(code)),
                    status="unused"))
                codes.append(code)
        finally:
            session.close()
        self._audit(principal, "security.recovery_codes_generated",
                    "recovery_codes", batch_id, "allow",
                    f"recovery code batch generated ({count} codes)",
                    {"batch_id": batch_id, "count": count,
                     "invalidated_previous": invalidated})
        return {
            "batch_id": batch_id,
            "codes": codes,
            "count": count,
            "invalidated_previous": invalidated,
            "shown_once": True,
            "note": ("These codes are shown exactly once. Only hashes "
                     "are stored; they cannot be retrieved again."),
        }

    def status(self, principal: Principal) -> dict:
        """Counts only — a code's plaintext is never retrievable."""
        self._require_owner(principal)
        session = self._session_factory()
        try:
            rows = RecoveryCodeRepository(session).list_for(
                principal.type.value, principal.id)
        finally:
            session.close()
        unused = [r for r in rows if r.status == "unused"]
        return {
            "configured": bool(rows),
            "total_generated": len(rows),
            "unused": len(unused),
            "used": sum(1 for r in rows if r.status == "used"),
            "invalidated": sum(1 for r in rows if r.status == "invalidated"),
            "batches": len({r.batch_id for r in rows}),
            "current_batch_id": unused[0].batch_id if unused else None,
            "last_generated_at": (
                max((r.created_at for r in rows)).isoformat()
                if rows else None),
        }

    def verify(self, principal: Principal, code: str) -> dict:
        """Consume one recovery code. Success marks the code used
        (single-use: it can never verify again); failure changes
        nothing but the audit trail. Both outcomes are audited."""
        self._require_owner(principal)
        normalized = _normalize_code(code)
        matched_id = None
        if normalized:
            session = self._session_factory()
            try:
                repo = RecoveryCodeRepository(session)
                for row in repo.unused_for(principal.type.value, principal.id):
                    if verify_password(normalized, row.code_hash):
                        row.status = "used"
                        row.used_at = utcnow()
                        repo.save(row)
                        matched_id = row.id
                        break
            finally:
                session.close()
        if matched_id is not None:
            self._audit(principal, "security.recovery_code_used",
                        "recovery_code", matched_id, "allow",
                        "recovery code consumed (single-use)", {})
            return {"verified": True}
        self._audit(principal, "security.recovery_code_refused",
                    "recovery_code", None, "deny",
                    "recovery code did not match any unused code", {})
        return {"verified": False}

    @staticmethod
    def _require_owner(principal: Principal) -> None:
        if not P.is_owner(principal):
            raise PermissionDeniedError(
                "recovery codes belong to the owner identity and are "
                "owner-only")
