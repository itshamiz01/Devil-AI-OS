"""Secrets management (§9): a metadata registry plus brokered use.

Two rules shape everything here:

1. **Values are never stored by P-10.** The registry holds names,
   broker references (``env:NAME`` / ``windows-vault:NAME``),
   purpose, classification and lifecycle metadata. Resolution goes
   through P-05's existing credential broker (§13.3 there) at the
   moment of use.
2. **Agents request an operation, not the secret (§9.4).**
   :meth:`SecretBroker.execute_with_secret` resolves the value and
   hands it only to the caller-supplied operation callback. No API
   response, audit event, access event or log line produced by this
   module contains a value — access events record name, actor,
   purpose and outcome only.

Windows storage (§9.2): the Windows Credential Manager / DPAPI
backend is an interface with an availability probe. On this Linux
staging host it is unavailable, and its status is reported as
REQUIRES OWNER CONFIGURATION — it is never claimed to have been
exercised. The working backend is the environment broker (the same
one P-05 uses).
"""
from __future__ import annotations

import sys

from ..core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from ..database.models.base import utcnow
from ..database.models.security import SecuritySecretAccessEvent, SecuritySecretMetadata
from ..database.repositories.security import (
    SecretAccessEventRepository, SecretMetadataRepository,
)
from ..execution.credentials import EnvCredentialBroker, is_credential_ref
from ..permissions.engine import PermissionEngine
from ..permissions.models import Principal
from . import constants as C
from . import policy as P

WINDOWS_REF_PREFIX = "windows-vault:"


class SecretBackendUnavailable(Exception):
    """Raised when a backend cannot resolve on this host."""


class EnvSecretBackend:
    name = "env"

    def __init__(self):
        self._broker = EnvCredentialBroker()

    @property
    def available(self) -> bool:
        return True

    def resolve(self, reference: str) -> str | None:
        return self._broker.resolve(reference)


class WindowsVaultBackend:
    """Windows Credential Manager / DPAPI backend (§9.2).

    Available only on Windows with the platform credential APIs
    present. Staging runs on Linux: unavailable by construction,
    status REQUIRES OWNER CONFIGURATION."""

    name = "windows-vault"

    @property
    def available(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import win32cred  # noqa: F401  (pywin32, Windows only)
        except Exception:
            return False
        return True

    @property
    def unavailable_reason(self) -> str:
        if sys.platform != "win32":
            return ("not a Windows host (staging runs on Linux); "
                    "REQUIRES OWNER CONFIGURATION on the Windows machine")
        return "pywin32 credential APIs not available; REQUIRES OWNER CONFIGURATION"

    def resolve(self, reference: str) -> str | None:
        raise SecretBackendUnavailable(
            f"windows vault backend unavailable: {self.unavailable_reason}")


def metadata_to_dict(row: SecuritySecretMetadata) -> dict:
    # Deliberately no value field exists on the row at all.
    return {
        "id": row.id, "name": row.name, "backend": row.backend,
        "reference_hint": row.reference.split(":", 1)[0] + ":***",
        "purpose": row.purpose, "classification": row.classification,
        "classification_name": C.CLASSIFICATION_LEVELS.get(row.classification),
        "status": row.status,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "last_rotated_at": row.last_rotated_at.isoformat() if row.last_rotated_at else None,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def access_event_to_dict(row: SecuritySecretAccessEvent) -> dict:
    return {
        "id": row.id, "secret_name": row.secret_name, "actor": row.actor,
        "purpose": row.purpose, "outcome": row.outcome, "detail": row.detail,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class SecretService:
    def __init__(self, session_factory, permissions: PermissionEngine,
                 get_settings, audit, *, backends: dict | None = None):
        self._session_factory = session_factory
        self._permissions = permissions
        self._get_settings = get_settings
        self._audit = audit
        self._backends = backends or {
            "env": EnvSecretBackend(),
            "windows-vault": WindowsVaultBackend(),
        }

    # --------------------------------------------------------- registry
    def register(self, principal: Principal, data: dict) -> dict:
        if not P.is_owner(principal):
            raise PermissionDeniedError(
                "secret registration is owner-only (§9.5)",
                details={"error_category": "SECRET_OWNER_ONLY"})
        name = (data.get("name") or "").strip()
        reference = (data.get("reference") or "").strip()
        if not name:
            raise ValidationError("secret name is required")
        if is_credential_ref(reference):
            backend = "env"
        elif reference.startswith(WINDOWS_REF_PREFIX) and len(reference) > len(WINDOWS_REF_PREFIX):
            backend = "windows-vault"
        else:
            raise ValidationError(
                "secret reference must be of the form 'env:NAME' or "
                "'windows-vault:NAME' — references, never values")
        classification = int(data.get("classification", 4))
        if classification not in C.CLASSIFICATION_LEVELS:
            raise ValidationError("classification must be a level 1–5 (§4.2)")
        session = self._session_factory()
        try:
            repo = SecretMetadataRepository(session)
            if repo.get_by_name(name) is not None:
                raise ValidationError(f"a secret named '{name}' is already registered")
            row = repo.add(SecuritySecretMetadata(
                name=name, reference=reference, backend=backend,
                purpose=data.get("purpose"), classification=classification,
                status="active", expires_at=data.get("expires_at"),
                created_by=P.actor(principal)))
            result = metadata_to_dict(row)
        finally:
            session.close()
        self._audit(principal, "security.secret_registered", "secret", name,
                    "allow", "secret metadata registered (no value stored)",
                    {"backend": backend, "classification": classification})
        return result

    def list_secrets(self, *, status: str | None = None, limit: int = 50,
                     offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            rows, total = SecretMetadataRepository(session).list(
                status=status, limit=limit, offset=offset)
            return [metadata_to_dict(r) for r in rows], total
        finally:
            session.close()

    def rotate(self, principal: Principal, name: str) -> dict:
        """Record a rotation (§9.5). The VALUE change itself happens
        where the secret lives (environment / vault) by the owner;
        the registry records that it happened and when."""
        row = self._lifecycle_change(
            principal, name, "security.secret_rotated",
            lambda r: setattr(r, "last_rotated_at", utcnow())
            or setattr(r, "status", "active"))
        return row

    def revoke(self, principal: Principal, name: str) -> dict:
        return self._lifecycle_change(
            principal, name, "security.secret_revoked",
            lambda r: setattr(r, "status", "revoked"))

    def _lifecycle_change(self, principal, name, audit_action, mutate) -> dict:
        if not P.is_owner(principal):
            raise PermissionDeniedError(
                "secret lifecycle changes are owner-only (§9.5)",
                details={"error_category": "SECRET_OWNER_ONLY"})
        session = self._session_factory()
        try:
            repo = SecretMetadataRepository(session)
            row = repo.get_by_name(name)
            if row is None:
                raise NotFoundError(f"secret '{name}' is not registered")
            mutate(row)
            result = metadata_to_dict(repo.save(row))
        finally:
            session.close()
        self._audit(principal, audit_action, "secret", name, "allow",
                    "secret lifecycle change (metadata only)", {})
        return result

    # ------------------------------------------------------------ broker
    def check_access(self, principal: Principal, name: str,
                     purpose: str | None = None) -> dict:
        """Decision-only brokered-access check (§9.4): would this
        principal be allowed to use this secret? The value is NOT
        resolved — this is the only secret operation the HTTP API
        exposes, so no response can ever carry a value."""
        allowed, outcome, detail = self._access_decision(principal, name)
        self._record_event(principal, name, purpose, outcome, detail)
        return {"secret_name": name, "allowed": allowed, "outcome": outcome,
                "detail": detail}

    def execute_with_secret(self, principal: Principal, name: str,
                            purpose: str | None, operation):
        """Resolve the secret and hand the value ONLY to ``operation``
        (§9.4). Returns the operation's own result. Service-level
        API for trusted in-process callers; never exposed over HTTP.
        """
        allowed, outcome, detail = self._access_decision(principal, name)
        if not allowed:
            self._record_event(principal, name, purpose, outcome, detail)
            raise PermissionDeniedError(detail,
                                        details={"error_category": "SECRET_ACCESS_DENIED"})
        session = self._session_factory()
        try:
            row = SecretMetadataRepository(session).get_by_name(name)
            reference, backend_name = row.reference, row.backend
        finally:
            session.close()
        backend = self._backends[backend_name]
        try:
            value = backend.resolve(reference)
        except SecretBackendUnavailable as exc:
            self._record_event(principal, name, purpose, "unavailable", str(exc))
            raise PermissionDeniedError(
                "secret backend unavailable; failing closed (deny)",
                details={"error_category": "SECRET_BACKEND_UNAVAILABLE"}) from exc
        if value is None:
            self._record_event(principal, name, purpose, "unavailable",
                               "reference did not resolve to a value")
            raise PermissionDeniedError(
                "secret reference did not resolve; failing closed (deny)",
                details={"error_category": "SECRET_UNRESOLVED"})
        self._record_event(principal, name, purpose, "granted",
                           "value resolved into a brokered operation")
        return operation(value)

    def _access_decision(self, principal: Principal, name: str) -> tuple[bool, str, str]:
        session = self._session_factory()
        try:
            row = SecretMetadataRepository(session).get_by_name(name)
        finally:
            session.close()
        if row is None:
            return False, "not_found", f"secret '{name}' is not registered"
        if row.status != "active":
            return False, "denied", f"secret '{name}' is '{row.status}'"
        try:
            mode = self._get_settings().get("mode", C.MODE_SAFE)
        except Exception:
            mode = C.MODE_SAFE
        ok, why = P.mode_allows(mode, principal, C.RISK_CRITICAL)
        if not ok:
            return False, "denied", f"secret access blocked by security mode: {why}"
        decision = self._permissions.check(principal, "access_sensitive_data")
        if not decision.allowed:
            return False, "denied", (
                f"principal lacks 'access_sensitive_data' ({decision.reason}); "
                f"secrets are used through brokered operations, never handed out")
        return True, "granted", "brokered access permitted"

    def _record_event(self, principal, name, purpose, outcome, detail) -> None:
        session = self._session_factory()
        try:
            SecretAccessEventRepository(session).add(SecuritySecretAccessEvent(
                secret_name=name, actor=P.actor(principal), purpose=purpose,
                outcome=outcome, detail=detail))
        finally:
            session.close()
        self._audit(principal, "security.secret_access", "secret", name,
                    "allow" if outcome == "granted" else "deny", detail, {})

    def list_access_events(self, *, secret_name: str | None = None,
                           limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            rows, total = SecretAccessEventRepository(session).list(
                secret_name=secret_name, limit=limit, offset=offset)
            return [access_event_to_dict(r) for r in rows], total
        finally:
            session.close()

    # ------------------------------------------------------------- misc
    def resolve_reference(self, reference: str) -> str | None:
        """Internal resolution for trusted facade wiring (e.g. the
        TOTP secret supplier). Not exposed over HTTP."""
        if is_credential_ref(reference):
            return self._backends["env"].resolve(reference)
        if reference.startswith(WINDOWS_REF_PREFIX):
            return self._backends["windows-vault"].resolve(reference)
        return None

    def backend_status(self) -> list[dict]:
        status = []
        for name, backend in self._backends.items():
            entry = {"backend": name, "available": backend.available}
            if not backend.available:
                entry["status"] = "REQUIRES OWNER CONFIGURATION"
                entry["reason"] = getattr(backend, "unavailable_reason",
                                          "backend unavailable on this host")
            else:
                entry["status"] = "available"
            status.append(entry)
        return status
