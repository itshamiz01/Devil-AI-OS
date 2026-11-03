from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from ..database.connection import Database
from ..database.models import utcnow
from ..database.repositories import AuditRepo, CredentialRepo, PrincipalRepo, SessionRepo
from .config import Settings
from .exceptions import UnauthorizedError, QueueFullError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class LoginRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window = window_seconds
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self.hits[key]
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise QueueFullError("Too many login attempts")
        q.append(now)


class AuthService:
    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        self.limiter = LoginRateLimiter(settings.login_rate_limit)

    async def login(self, username: str, password: str, client_key: str) -> tuple[str, datetime]:
        self.limiter.check(client_key)
        async with self.db.session_factory() as session:
            principal = await PrincipalRepo(session).by_name(username)
            cred = await CredentialRepo(session).get(principal.id) if principal else None
            if not principal or not principal.active or principal.kind != "owner" or not cred or not verify_password(cred.password_hash, password):
                await AuditRepo(session).record("auth.login", "denied", principal_id=principal.id if principal else None, action="login")
                await session.commit()
                raise UnauthorizedError("Invalid credentials")
            token = secrets.token_urlsafe(32)
            expires = utcnow() + timedelta(minutes=self.settings.session_ttl_minutes)
            await SessionRepo(session).create(token_hash(token), principal.id, expires)
            await AuditRepo(session).record("auth.login", "allowed", principal_id=principal.id, action="login")
            await session.commit()
            return token, expires

    async def authenticate(self, token: str):
        async with self.db.session_factory() as session:
            auth_session = await SessionRepo(session).valid(token_hash(token))
            if not auth_session:
                raise UnauthorizedError("Invalid or expired session")
            principal = await PrincipalRepo(session).get(auth_session.principal_id)
            if not principal or not principal.active:
                raise UnauthorizedError("Principal inactive")
            return principal

    async def logout(self, token: str) -> None:
        async with self.db.session_factory() as session:
            await SessionRepo(session).revoke(token_hash(token))
            await session.commit()

    async def bootstrap_owner(self, username: str, password: str) -> str:
        from ..permissions.engine import PermissionEngine
        if len(password) < 12:
            raise ValueError("Owner password must be at least 12 characters")
        async with self.db.session_factory() as session:
            repo = PrincipalRepo(session)
            principal = await repo.by_name(username)
            if principal and principal.kind != "owner":
                raise ValueError("Principal name already used by non-owner")
            if not principal:
                principal = await repo.create("owner", username)
            await CredentialRepo(session).set_hash(principal.id, hash_password(password))
            await session.commit()
            principal_id = principal.id
        await PermissionEngine(self.db).grant_owner_permissions(principal_id)
        return principal_id
