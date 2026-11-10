"""Identity-layer extensions (§5): session visibility/revocation,
login throttling, and MFA verification.

These EXTEND P-01's ``AuthService`` — the one authentication system.
Sessions remain P-01 ``app_sessions`` rows; this module adds the
listing/revocation surface P-01 lacked (§5.4) and a throttling guard
that ``AuthService.login`` consults through an optional hook (when
the hook is absent, P-01 behaviour is unchanged).

MFA (§5.3): a stdlib RFC 6238 TOTP verifier — implemented and
vector-tested, but enrolment needs an owner-set secret delivered
through the credential broker (``env:AUTONOMUS_TOTP_SECRET``), so
live MFA is REQUIRES OWNER CONFIGURATION. Recovery codes were NOT
IMPLEMENTED in P-10; Expansion Feature 1 implements them in
``app/security/devices.py`` (``RecoveryCodeService``), wired into
the same facade.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time

from ..core.exceptions import NotFoundError, PermissionDeniedError
from ..database.models.base import utcnow
from ..database.models.core import AppSession
from ..database.repositories.core import SessionRepository
from ..database.repositories.security import LoginAttemptRepository
from ..database.models.security import SecurityLoginAttempt
from ..permissions.models import Principal
from . import policy as P

import datetime as dt


def session_to_dict(row: AppSession) -> dict:
    return {
        "id": row.id, "principal": f"{row.principal_type}:{row.principal_id}",
        # Expansion Feature 1: the bound device, when the login
        # presented a device credential (NULL = unbound session).
        "device_id": row.device_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "revoked": row.revoked,
    }


class SessionService:
    """Owner-facing session management over P-01 sessions (§5.4)."""

    def __init__(self, session_factory, audit):
        self._session_factory = session_factory
        self._audit = audit

    def list_sessions(self, principal: Principal) -> list[dict]:
        if not P.is_owner(principal):
            raise PermissionDeniedError("session visibility is owner-only")
        session = self._session_factory()
        try:
            from sqlalchemy import select
            rows = list(session.scalars(
                select(AppSession).order_by(AppSession.created_at.desc()).limit(200)))
            return [session_to_dict(r) for r in rows]
        finally:
            session.close()

    def revoke_session(self, principal: Principal, session_id: str) -> dict:
        if not P.is_owner(principal):
            raise PermissionDeniedError("session revocation is owner-only")
        session = self._session_factory()
        try:
            row = session.get(AppSession, session_id)
            if row is None:
                raise NotFoundError(f"session {session_id} not found")
            row.revoked = True
            SessionRepository(session).save(row)
            result = session_to_dict(row)
        finally:
            session.close()
        self._audit(principal, "security.session_revoked", "session", session_id,
                    "allow", "owner revoked a session", {})
        return result

    def revoke_by_token_hash(self, principal: Principal, token_hash: str) -> bool:
        """Logout: revoke the session matching the caller's own
        presented token (identified by its hash — the raw token is
        never stored). Any authenticated principal may end its own
        session."""
        session = self._session_factory()
        try:
            row = SessionRepository(session).get_by_token_hash(token_hash)
            if row is None:
                return False
            if f"{row.principal_type}:{row.principal_id}" != P.actor(principal):
                raise PermissionDeniedError("a principal may only end its own session")
            row.revoked = True
            SessionRepository(session).save(row)
            session_id = row.id
        finally:
            session.close()
        self._audit(principal, "security.session_revoked", "session", session_id,
                    "allow", "logout: own session revoked", {})
        return True


class LoginGuard:
    """Brute-force throttling for owner login (§5.2).

    Consulted by ``AuthService.login`` when wired: before a password
    is checked, recent failures for the username inside the window
    are counted; at the configured maximum the attempt is refused
    (and recorded as throttled). Every outcome is recorded in
    ``security_login_attempts`` — username and success flag only.
    """

    def __init__(self, session_factory, get_settings):
        self._session_factory = session_factory
        self._get_settings = get_settings

    def is_throttled(self, username: str) -> bool:
        settings = self._get_settings()
        window = dt.timedelta(minutes=int(settings["login_window_minutes"]))
        session = self._session_factory()
        try:
            failures = LoginAttemptRepository(session).recent_failures(
                username, utcnow() - window)
        finally:
            session.close()
        return failures >= int(settings["login_max_failures"])

    def record(self, username: str, success: bool, *, throttled: bool = False) -> None:
        session = self._session_factory()
        try:
            LoginAttemptRepository(session).add(SecurityLoginAttempt(
                username=username, success=success, throttled=throttled))
        finally:
            session.close()

    # AuthService hook protocol: returns True to let the attempt
    # proceed to password verification, False to refuse it now.
    def before_login(self, username: str) -> bool:
        throttled = self.is_throttled(username)
        if throttled:
            self.record(username, False, throttled=True)
        return not throttled

    def after_login(self, username: str, success: bool) -> None:
        self.record(username, success)


# ------------------------------------------------------------------- MFA
def totp_code(secret_b32: str, *, for_time: float | None = None,
              digits: int = 6, period: int = 30) -> str:
    """RFC 6238 TOTP over HMAC-SHA-1 (the interoperable default).
    Stdlib only — no new dependency (§22.1)."""
    key = base64.b32decode(secret_b32.strip().upper())
    counter = int((for_time if for_time is not None else time.time()) // period)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10 ** digits)).zfill(digits)


class TotpVerifier:
    """Verifies TOTP codes against a broker-resolved secret.

    The secret itself is never stored by P-10: the facade resolves
    it per verification through the credential broker
    (``env:AUTONOMUS_TOTP_SECRET``). Without that owner-set secret,
    ``configured`` is False and verification fails closed.
    """

    def __init__(self, secret_supplier):
        self._secret_supplier = secret_supplier  # () -> str | None

    @property
    def configured(self) -> bool:
        return bool(self._secret_supplier())

    def verify(self, code: str, *, at_time: float | None = None) -> bool:
        secret = self._secret_supplier()
        if not secret or not code:
            return False
        now = at_time if at_time is not None else time.time()
        # ±1 step window for clock skew, constant-time comparison.
        return any(
            hmac.compare_digest(totp_code(secret, for_time=now + delta * 30), code.strip())
            for delta in (-1, 0, 1))
