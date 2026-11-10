"""Authentication scheme (P-01 §13) — ONE coherent scheme, three credential
sources, all producing a :class:`~app.permissions.models.Principal`:

1. **Owner password login** (primary): ``POST /api/v1/auth/login`` with the
   owner username/password. The password comes only from
   ``AUTONOMUS_ADMIN_PASSWORD`` (env/secret storage, never committed); at
   first startup it is hashed with scrypt and only the hash is kept in
   ``system_config``. Login returns a random session token; only its
   SHA-256 hash is stored in ``app_sessions`` with an expiry.
2. **Service token**: ``AUTONOMUS_SERVICE_TOKEN`` presented as a Bearer
   token maps to the limited Service principal (read + submit only).
3. **Local-dev token**: when NO admin password is configured, the API runs
   in documented local-dev mode: ``AUTONOMUS_DEV_TOKEN`` as a Bearer token
   maps to the Owner principal. If neither a password nor any token is
   configured, protected endpoints reject every request (locked mode).

There is NO hardcoded default credential. Plaintext passwords are never
stored or logged; session tokens are stored only as hashes.

**Device binding (Expansion Feature 1)**: a password login may
additionally present a registered device's credential
(``device_id`` + ``device_secret``). When wired by
``Application.startup``, the optional ``device_hook`` (P-10's
``DeviceService`` — the same late-attachment pattern as
``login_guard``) verifies the device is trusted and, on success,
the new session row carries ``device_id``. Presenting device
fields and failing verification refuses the whole login; a bound
session is refused at resolution while its device is not trusted.
With no hook wired, presenting device fields fails closed and
ordinary password login is unchanged.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from ..database.models.base import as_utc, utcnow
from ..database.models.core import AppSession
from ..database.repositories.core import ConfigRepository, SessionRepository
from ..permissions.models import Principal, PrincipalType

ADMIN_HASH_KEY = "auth.admin_password_hash"
ADMIN_USER_KEY = "auth.admin_username"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, session_factory, settings):
        self._session_factory = session_factory
        self.settings = settings

    # ------------------------------------------------------------- seeding
    def seed_admin_from_settings(self) -> None:
        """At startup: if a password is configured and no hash exists yet,
        store its scrypt hash. Idempotent; never overwrites an existing hash
        (password rotation is an owner action, not a silent env override)."""
        session = self._session_factory()
        try:
            repo = ConfigRepository(session)
            repo.set(ADMIN_USER_KEY, self.settings.admin_username,
                     "Owner admin username")
            if self.settings.admin_password and repo.get(ADMIN_HASH_KEY) is None:
                repo.set(ADMIN_HASH_KEY, hash_password(self.settings.admin_password),
                         "scrypt hash of the owner admin password (hash only, never plaintext)")
        finally:
            session.close()

    @property
    def auth_mode(self) -> str:
        session = self._session_factory()
        try:
            has_hash = ConfigRepository(session).get(ADMIN_HASH_KEY) is not None
        finally:
            session.close()
        if has_hash:
            return "password"
        if self.settings.dev_token:
            return "local-dev-token"
        return "locked"

    # --------------------------------------------------------------- login
    def login(self, username: str, password: str,
              device_id: str | None = None,
              device_secret: str | None = None) -> str | None:
        # P-10 login guard hook (§5.2 throttling): when a guard is
        # wired (Application startup), attempts are throttled and
        # recorded. Guard failure fails closed — authentication
        # state uncertain means NOT authenticated (§20.3). With no
        # guard wired, P-01 behaviour is unchanged.
        guard = getattr(self, "login_guard", None)
        if guard is not None:
            try:
                if not guard.before_login(username):
                    return None
            except Exception:
                return None
        token = None
        if self._device_gate(device_id, device_secret):
            token = self._login_verified(username, password,
                                         device_id=device_id)
        if token is not None and device_id:
            # Best-effort bookkeeping (last-seen + audit), exactly
            # like the guard's after_login: it must never break a
            # completed login.
            hook = getattr(self, "device_hook", None)
            if hook is not None:
                try:
                    hook.note_device_login(device_id)
                except Exception:
                    pass
        if guard is not None:
            try:
                guard.after_login(username, token is not None)
            except Exception:
                pass  # recording must never break a completed login check
        return token

    def _device_gate(self, device_id: str | None,
                     device_secret: str | None) -> bool:
        """Expansion Feature 1: whether this login may proceed to
        password verification. No device fields presented -> the
        legacy unbound login proceeds. Any device field presented
        makes verification mandatory: both fields, a wired hook,
        and the hook's verdict that the device is trusted with a
        matching credential. Anything else fails closed."""
        if device_id is None and device_secret is None:
            return True
        if not device_id or not device_secret:
            return False
        hook = getattr(self, "device_hook", None)
        if hook is None:
            return False
        try:
            return bool(hook.verify_device_credential(device_id, device_secret))
        except Exception:
            return False

    def _login_verified(self, username: str, password: str,
                        device_id: str | None = None) -> str | None:
        session = self._session_factory()
        try:
            repo = ConfigRepository(session)
            user_row = repo.get(ADMIN_USER_KEY)
            hash_row = repo.get(ADMIN_HASH_KEY)
            if user_row is None or hash_row is None or hash_row.value is None:
                return None
            if username != (user_row.value or self.settings.admin_username):
                return None
            if not verify_password(password, hash_row.value):
                return None
            token = secrets.token_urlsafe(32)
            expires = utcnow().timestamp() + self.settings.session_expiry_hours * 3600
            import datetime as dt
            SessionRepository(session).add(AppSession(
                token_hash=_token_hash(token), principal_type=PrincipalType.OWNER.value,
                principal_id=username, device_id=device_id,
                expires_at=dt.datetime.fromtimestamp(expires, dt.timezone.utc)))
            return token
        finally:
            session.close()

    # --------------------------------------------------------- resolution
    def resolve_bearer(self, token: str | None) -> Principal | None:
        if not token:
            return None
        # Service token (limited principal)
        if self.settings.service_token and hmac.compare_digest(token, self.settings.service_token):
            return Principal(PrincipalType.SERVICE, "service-api", "Service API")
        # Local-dev token. P-14 Stage B (DEF-S1 hardening): honoured
        # ONLY when no admin password hash exists — once a password is
        # configured the dev token stops working, matching auth_mode()'s
        # contract above (previously it was silently accepted in
        # password mode too).
        if self.settings.dev_token and hmac.compare_digest(token, self.settings.dev_token):
            session = self._session_factory()
            try:
                password_configured = ConfigRepository(session).get(
                    ADMIN_HASH_KEY) is not None
            finally:
                session.close()
            if not password_configured:
                return Principal(PrincipalType.OWNER, self.settings.admin_username,
                                 "Owner (dev token)")
        # Session token from password login
        session = self._session_factory()
        try:
            row = SessionRepository(session).get_by_token_hash(_token_hash(token))
            if row is None or row.revoked:
                return None
            # P-14 Stage B (DEF-D2): standardised naive→aware shim.
            if as_utc(row.expires_at) <= utcnow():
                return None
            # Expansion Feature 1: a device-bound session is valid
            # only while its device is trusted. Untrust/revoke also
            # sweep (revoke) bound sessions, so this check is the
            # structural backstop; it fails closed when the device
            # state cannot be established. With no hook wired the
            # row's revoked flag stands alone (P-01 behaviour).
            if row.device_id:
                hook = getattr(self, "device_hook", None)
                if hook is not None:
                    try:
                        if not hook.session_device_trusted(row.device_id):
                            return None
                    except Exception:
                        return None
            return Principal(PrincipalType(row.principal_type), row.principal_id, row.principal_id)
        finally:
            session.close()
