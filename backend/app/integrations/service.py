"""IntegrationService — the Universal Integration Framework facade
(Expansion Feature 2).

Composed on the Application after P-18, consuming only existing
authorities:

- **Credentials: P-10.** A registry row stores a secret NAME; the
  value is resolved by ``SecretService.execute_with_secret`` at the
  moment of invocation and exists only inside that callback (§9.4).
  The framework never stores, logs or returns a value.
- **Authorization: P-10's PermissionBroker** over the P-01 engine,
  for every invocation — mode gates, restrictions, business scope,
  risk gates (capability at Level 2, owner-decided hash-bound
  approval at Level 3) apply unchanged. Risk classification comes
  from the capability's declared action, which registration
  required to already exist in P-10's ``ACTION_RISK``.
- **Audit: the P-01 ``audit_events`` trail**, via the shared
  repository — no parallel log.
- **Money: none.** The framework is plumbing; it holds no money
  column, moves no money, and P-07 is untouched.

Honesty contract: a connector without a registered adapter cannot
be enabled and can never be invoked; a connector whose credential
cannot be resolved fails as ``requires_owner_configuration``; an
adapter failure is recorded as ``error``. Nothing here fabricates
a success.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time

from ..core.exceptions import (
    AutonomusError, NotFoundError, PermissionDeniedError, ValidationError,
)
from ..core.version import APP_VERSION
from ..database.models.base import utcnow
from ..database.models.integrations import (
    IntegrationConnector, IntegrationInvocation,
)
from ..database.repositories.core import AuditRepository
from ..database.models.core import AuditEvent
from ..database.repositories.integrations import (
    ConnectorRepository, InvocationRepository,
)
from ..database.repositories.security import SecretMetadataRepository
from ..permissions.models import Principal
from ..security import policy as security_policy
from . import constants as C
from .interfaces.base import ConnectorAdapter, ConnectorContext, ConnectorDescriptor
from .registry import ADAPTER_FACTORIES, builtin_descriptors
from .validation import validate_descriptor, validate_payload

INVOKE_TIMEOUT_SECONDS = 10.0


class IntegrationError(AutonomusError):
    status_code = 502
    code = "integration_error"


def _actor(principal: Principal | None) -> str:
    return security_policy.actor(principal) if principal else "system:integrations"


def connector_to_dict(row: IntegrationConnector, state: str) -> dict:
    descriptor = row.descriptor or {}
    return {
        "key": row.key, "name": row.name, "provider": row.provider,
        "version": row.version, "kind": row.kind,
        "description": row.description, "source": row.source,
        "adapter": row.adapter_key,
        "has_adapter": row.adapter_key is not None,
        "requires_credential": row.requires_credential,
        "credential_configured": row.credential_secret_name is not None,
        "credential_secret_name": row.credential_secret_name,
        "required_permissions": descriptor.get("required_permissions", []),
        "capabilities": descriptor.get("capabilities", []),
        "settings": row.settings or {},
        "lifecycle_status": row.lifecycle_status,
        "state": state,
        "health_detail": row.health_detail,
        "last_health_at": row.last_health_at.isoformat() if row.last_health_at else None,
        "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
        "last_invoked_at": row.last_invoked_at.isoformat() if row.last_invoked_at else None,
        "last_error": row.last_error,
        "error_count": row.error_count,
        "registered_by": row.registered_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def invocation_to_dict(row: IntegrationInvocation) -> dict:
    return {
        "id": row.id, "connector_key": row.connector_key,
        "capability": row.capability,
        "principal": f"{row.principal_type}:{row.principal_id}",
        "idempotency_key": row.idempotency_key,
        "broker_decision_id": row.broker_decision_id,
        "outcome": row.outcome, "result": row.result,
        "error_detail": row.error_detail,
        "duration_ms": row.duration_ms,
        "correlation_id": row.correlation_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class IntegrationService:
    def __init__(self, application):
        self._app = application
        self._session_factory = application.session_factory
        self._adapters: dict[str, ConnectorAdapter] = {}
        for adapter_key, factory in ADAPTER_FACTORIES.items():
            self._adapters[adapter_key] = factory()

    # ------------------------------------------------------------ seeding
    def seed_connectors(self) -> int:
        """Idempotently register the built-in catalogue (reference
        connector + the P-07/P-17/P-18 surfaces). Existing rows keep
        their lifecycle, settings and credential attachment; only
        the declared descriptor snapshot is refreshed."""
        seeded = 0
        session = self._session_factory()
        try:
            repo = ConnectorRepository(session)
            for descriptor, source, adapter_key in builtin_descriptors():
                row = repo.get_by_key(descriptor.key)
                if row is None:
                    row = repo.add(IntegrationConnector(
                        key=descriptor.key, name=descriptor.name,
                        provider=descriptor.provider, version=descriptor.version,
                        kind=descriptor.kind, description=descriptor.description,
                        source=source, descriptor=descriptor.to_dict(),
                        adapter_key=adapter_key,
                        requires_credential=descriptor.requires_credential,
                        lifecycle_status=(
                            C.LIFECYCLE_ENABLED if adapter_key == "local_echo"
                            else C.LIFECYCLE_REGISTERED),
                        health_state=C.STATE_NOT_CONFIGURED,
                        registered_by="system:bootstrap"))
                    seeded += 1
                else:
                    row.name = descriptor.name
                    row.provider = descriptor.provider
                    row.version = descriptor.version
                    row.kind = descriptor.kind
                    row.description = descriptor.description
                    row.descriptor = descriptor.to_dict()
                    row.adapter_key = adapter_key
                    row.requires_credential = descriptor.requires_credential
                    repo.save(row)
                row.health_state = self._reported_state(row)
                repo.save(row)
        finally:
            session.close()
        return seeded

    # --------------------------------------------------------- state math
    def _secret_active(self, name: str | None) -> bool:
        """Metadata-only check: is this P-10 registry entry present
        and active? No value is resolved for a state computation."""
        if not name:
            return False
        session = self._session_factory()
        try:
            row = SecretMetadataRepository(session).get_by_name(name)
            return row is not None and row.status == "active"
        finally:
            session.close()

    def _reported_state(self, row: IntegrationConnector) -> str:
        if row.adapter_key is None:
            return C.STATE_REQUIRES_OWNER_CONFIGURATION
        if row.requires_credential and not self._secret_active(row.credential_secret_name):
            return C.STATE_REQUIRES_OWNER_CONFIGURATION
        if row.lifecycle_status != C.LIFECYCLE_ENABLED:
            return C.STATE_NOT_CONFIGURED
        if row.health_state == C.STATE_ERROR:
            return C.STATE_ERROR
        return C.STATE_CONFIGURED

    def _get_row(self, key: str) -> IntegrationConnector:
        session = self._session_factory()
        try:
            row = ConnectorRepository(session).get_by_key(key)
            if row is None:
                raise NotFoundError(f"connector '{key}' is not registered")
            session.expunge(row)
            return row
        finally:
            session.close()

    def _save(self, row: IntegrationConnector) -> IntegrationConnector:
        session = self._session_factory()
        try:
            repo = ConnectorRepository(session)
            stored = repo.get_by_key(row.key)
            for column in IntegrationConnector.__table__.columns:
                if column.key not in ("id", "created_at"):
                    setattr(stored, column.key, getattr(row, column.key))
            saved = repo.save(stored)
            session.expunge(saved)
            return saved
        finally:
            session.close()

    # ------------------------------------------------------------- queries
    def list_connectors(self, *, lifecycle_status=None, state=None,
                        source=None, limit=100, offset=0):
        session = self._session_factory()
        try:
            rows, total = ConnectorRepository(session).list(
                lifecycle_status=lifecycle_status, source=source,
                limit=limit, offset=offset)
            result = []
            for row in rows:
                reported = self._reported_state(row)
                if state is not None and reported != state:
                    continue
                result.append(connector_to_dict(row, reported))
            return result, total
        finally:
            session.close()

    def get_connector(self, key: str) -> dict:
        row = self._get_row(key)
        return connector_to_dict(row, self._reported_state(row))

    def framework_status(self) -> dict:
        rows, _total = self.list_connectors(limit=1000)
        by_state: dict[str, int] = {}
        by_lifecycle: dict[str, int] = {}
        for row in rows:
            by_state[row["state"]] = by_state.get(row["state"], 0) + 1
            by_lifecycle[row["lifecycle_status"]] = \
                by_lifecycle.get(row["lifecycle_status"], 0) + 1
        return {
            "framework": "universal-integration-framework",
            "api_version": APP_VERSION,
            "state_vocabulary": list(C.STATES),
            "lifecycle_vocabulary": list(C.LIFECYCLES),
            "connector_count": len(rows),
            "with_adapter": sum(1 for r in rows if r["has_adapter"]),
            "by_state": by_state, "by_lifecycle": by_lifecycle,
            "credential_authority": "P-10 (metadata registry + brokered use)",
            "authorization_authority": "P-10 PermissionBroker over P-01 engine",
            "note": ("a connector is invocable only when it has a "
                     "registered adapter, is enabled, and any required "
                     "credential resolves through P-10; everything else "
                     "fails honestly in the framework vocabulary"),
        }

    # ----------------------------------------------------------- lifecycle
    def register_connector(self, principal: Principal, data: dict) -> dict:
        if not security_policy.is_owner(principal):
            raise PermissionDeniedError(
                "connector registration is owner-only (framework "
                "configuration is system configuration)")
        descriptor = ConnectorDescriptor.from_dict(data)
        validate_descriptor(descriptor)
        session = self._session_factory()
        try:
            repo = ConnectorRepository(session)
            if repo.get_by_key(descriptor.key) is not None:
                raise ValidationError(
                    f"a connector named '{descriptor.key}' is already registered")
            row = repo.add(IntegrationConnector(
                key=descriptor.key, name=descriptor.name,
                provider=descriptor.provider, version=descriptor.version,
                kind=descriptor.kind, description=descriptor.description,
                source="owner", descriptor=descriptor.to_dict(),
                adapter_key=None,
                requires_credential=descriptor.requires_credential,
                lifecycle_status=C.LIFECYCLE_REGISTERED,
                health_state=C.STATE_REQUIRES_OWNER_CONFIGURATION,
                registered_by=_actor(principal)))
            result = connector_to_dict(row, self._reported_state(row))
        finally:
            session.close()
        self._audit(principal, "integration.connector_registered", "connector",
                    descriptor.key, "allow",
                    "connector registered (declaration only; no adapter)",
                    {"kind": descriptor.kind})
        return result

    def configure_connector(self, principal: Principal, key: str,
                            data: dict) -> dict:
        if not security_policy.is_owner(principal):
            raise PermissionDeniedError("connector configuration is owner-only")
        row = self._get_row(key)
        secret_name = data.get("credential_secret_name", row.credential_secret_name)
        if secret_name is not None:
            if not isinstance(secret_name, str) or not secret_name.strip():
                raise ValidationError("credential_secret_name must be a "
                                      "non-empty P-10 secret registry name")
            secret_name = secret_name.strip()
            session = self._session_factory()
            try:
                known = SecretMetadataRepository(session).get_by_name(secret_name)
            finally:
                session.close()
            if known is None:
                raise ValidationError(
                    f"secret '{secret_name}' is not registered in the P-10 "
                    f"secrets registry; register the reference there first "
                    f"(the framework stores names, never values)")
            row.credential_secret_name = secret_name
        if "clear_credential" in data and data["clear_credential"]:
            row.credential_secret_name = None
        if "settings" in data and data["settings"] is not None:
            if not isinstance(data["settings"], dict):
                raise ValidationError("settings must be an object of "
                                      "non-secret configuration")
            row.settings = data["settings"]
        if row.lifecycle_status == C.LIFECYCLE_REGISTERED:
            row.lifecycle_status = C.LIFECYCLE_CONFIGURED
        row.health_state = self._reported_state(row)
        row = self._save(row)
        self._audit(principal, "integration.connector_configured", "connector",
                    key, "allow", "connector configuration updated",
                    {"credential_attached": row.credential_secret_name is not None})
        return connector_to_dict(row, self._reported_state(row))

    def set_enabled(self, principal: Principal, key: str, enabled: bool) -> dict:
        if not security_policy.is_owner(principal):
            raise PermissionDeniedError("connector enable/disable is owner-only")
        row = self._get_row(key)
        if enabled:
            if row.adapter_key is None:
                raise ValidationError(
                    f"connector '{key}' has no implemented adapter; "
                    f"enabling it would claim a connector that does not "
                    f"exist. It remains requires_owner_configuration "
                    f"until a real connector is implemented and tested.")
            row.lifecycle_status = C.LIFECYCLE_ENABLED
            action = "integration.connector_enabled"
        else:
            row.lifecycle_status = C.LIFECYCLE_DISABLED
            action = "integration.connector_disabled"
        row.health_state = self._reported_state(row)
        row = self._save(row)
        self._audit(principal, action, "connector", key, "allow",
                    f"connector {'enabled' if enabled else 'disabled'}", {})
        return connector_to_dict(row, self._reported_state(row))

    def attach_adapter(self, principal: Principal | None,
                       adapter: ConnectorAdapter) -> dict:
        """Attach a live adapter instance and its registry row
        (the developer flow behind ``registry.ADAPTER_FACTORIES``,
        and the test harness's entry point). The descriptor is
        validated like any registration; the row is created or
        refreshed with ``adapter_key`` set, so the connector
        becomes invocable once enabled. Existing lifecycle is
        preserved on re-attach."""
        descriptor = adapter.descriptor
        validate_descriptor(descriptor)
        self._adapters[descriptor.key] = adapter
        session = self._session_factory()
        try:
            repo = ConnectorRepository(session)
            row = repo.get_by_key(descriptor.key)
            if row is None:
                row = repo.add(IntegrationConnector(
                    key=descriptor.key, name=descriptor.name,
                    provider=descriptor.provider, version=descriptor.version,
                    kind=descriptor.kind, description=descriptor.description,
                    source="framework", descriptor=descriptor.to_dict(),
                    adapter_key=descriptor.key,
                    requires_credential=descriptor.requires_credential,
                    lifecycle_status=C.LIFECYCLE_REGISTERED,
                    health_state=C.STATE_NOT_CONFIGURED,
                    registered_by=_actor(principal)))
            else:
                row.name = descriptor.name
                row.provider = descriptor.provider
                row.version = descriptor.version
                row.kind = descriptor.kind
                row.description = descriptor.description
                row.descriptor = descriptor.to_dict()
                row.adapter_key = descriptor.key
                row.requires_credential = descriptor.requires_credential
                row = repo.save(row)
            result = connector_to_dict(row, self._reported_state(row))
        finally:
            session.close()
        return result

    # -------------------------------------------------------------- health
    async def health_check(self, principal: Principal, key: str) -> dict:
        row = self._get_row(key)
        adapter = self._adapters.get(row.adapter_key) if row.adapter_key else None
        if adapter is None:
            row.health_state = C.STATE_REQUIRES_OWNER_CONFIGURATION
            row.health_detail = ("no adapter is implemented for this "
                                 "connector; health cannot be checked")
            row.last_health_at = utcnow()
            row = self._save(row)
            return connector_to_dict(row, row.health_state)
        try:
            health = await asyncio.wait_for(adapter.health(), timeout=5.0)
            available, detail = health.available, health.detail
        except Exception as exc:  # adapter failure is data, not a crash
            available, detail = False, f"health check failed: {type(exc).__name__}: {exc}"
        row.last_health_at = utcnow()
        row.health_detail = detail
        if available:
            if row.health_state == C.STATE_ERROR:
                row.health_state = C.STATE_NOT_CONFIGURED  # clear standing error
            row.health_state = self._reported_state(row)
        else:
            row.health_state = C.STATE_ERROR
            row.last_error = f"health check: {detail}"
            row.error_count += 1
        row = self._save(row)
        self._audit(principal, "integration.health_checked", "connector", key,
                    "allow" if available else "deny",
                    detail, {"available": available})
        return connector_to_dict(row, self._reported_state(row))

    # -------------------------------------------------------------- invoke
    async def invoke(self, principal: Principal, key: str, capability_name: str,
                     payload: dict | None = None, *,
                     approval_id: str | None = None,
                     capability_id: str | None = None,
                     idempotency_key: str | None = None,
                     correlation_id: str | None = None,
                     timeout_seconds: float = INVOKE_TIMEOUT_SECONDS) -> dict:
        payload = payload or {}
        row = self._get_row(key)
        descriptor = ConnectorDescriptor.from_dict(row.descriptor or {})
        capability = descriptor.capability(capability_name)

        def record(outcome, *, result=None, error=None, duration_ms=None,
                   broker_decision_id=None):
            return self._record_invocation(
                row.key, capability_name, principal, outcome, result=result,
                error=error, duration_ms=duration_ms,
                broker_decision_id=broker_decision_id,
                idempotency_key=idempotency_key, correlation_id=correlation_id)

        if capability is None:
            record(C.OUTCOME_INVALID_REQUEST,
                   error=f"capability '{capability_name}' is not declared "
                         f"on connector '{key}'")
            raise ValidationError(
                f"capability '{capability_name}' is not declared on "
                f"connector '{key}' (capability contract enforcement)")

        # Idempotent replay: a recorded success is returned, never
        # re-executed (duplicate-request protection, pack §7).
        if idempotency_key:
            session = self._session_factory()
            try:
                prior = InvocationRepository(session).find_idempotent(
                    key, capability_name, idempotency_key)
                prior_result = prior.result if prior is not None else None
                prior_id = prior.id if prior is not None else None
            finally:
                session.close()
            if prior is not None:
                record(C.OUTCOME_DUPLICATE,
                       result={"replayed_invocation_id": prior_id})
                return {"connector": key, "capability": capability_name,
                        "outcome": C.OUTCOME_DUPLICATE,
                        "result": prior_result,
                        "invocation_id": prior_id, "replayed": True}

        # Readiness gate — honest failure, never a fabricated success.
        state = self._reported_state(row)
        if row.adapter_key is None or row.lifecycle_status != C.LIFECYCLE_ENABLED:
            outcome = (C.OUTCOME_REQUIRES_OWNER_CONFIGURATION
                       if state == C.STATE_REQUIRES_OWNER_CONFIGURATION
                       else C.OUTCOME_NOT_CONFIGURED)
            detail = (f"connector '{key}' is not invocable: lifecycle="
                      f"{row.lifecycle_status}, state={state}")
            record(outcome, error=detail)
            raise IntegrationError(detail, details={"state": state,
                                                    "outcome": outcome})
        if state == C.STATE_REQUIRES_OWNER_CONFIGURATION:
            detail = (f"connector '{key}' requires a credential that is "
                      f"not registered/active in P-10")
            record(C.OUTCOME_REQUIRES_OWNER_CONFIGURATION, error=detail)
            raise IntegrationError(detail, details={"state": state,
                                                    "outcome": C.OUTCOME_REQUIRES_OWNER_CONFIGURATION})

        errors = validate_payload(capability.input_schema, payload)
        if errors:
            record(C.OUTCOME_INVALID_REQUEST, error="; ".join(errors))
            raise ValidationError(
                "payload does not match the capability's declared input "
                "schema: " + "; ".join(errors))

        if capability.rate_limit_per_minute is not None:
            from datetime import timedelta
            session = self._session_factory()
            try:
                recent = InvocationRepository(session).count_since(
                    key, capability_name, utcnow() - timedelta(seconds=60))
            finally:
                session.close()
            if recent >= capability.rate_limit_per_minute:
                detail = (f"rate limit for '{key}.{capability_name}' "
                          f"({capability.rate_limit_per_minute}/minute) reached")
                record(C.OUTCOME_RATE_LIMITED, error=detail)
                raise IntegrationError(detail, details={
                    "outcome": C.OUTCOME_RATE_LIMITED})

        # Governed execution: the P-10 broker decides (P-01 engine,
        # mode/restriction/scope gates, risk gates). Parameters bind
        # connector + capability + the payload hash, so a Level-3
        # approval covers this exact call and no other.
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        decision = self._app.security.broker.authorize(
            principal, permission=capability.permission,
            action=capability.risk_action, resource=f"integration:{key}",
            parameters={"connector": key, "capability": capability_name,
                        "payload_sha256": payload_hash},
            approval_id=approval_id, capability_id=capability_id,
            correlation_id=correlation_id)
        if not decision["allowed"]:
            record(C.OUTCOME_DENIED, error=decision["reason"],
                   broker_decision_id=decision.get("decision_id"))
            raise PermissionDeniedError(
                f"integration invocation denied by the P-10 broker: "
                f"{decision['reason']}",
                details={"broker_decision_id": decision.get("decision_id"),
                         "risk_level": decision.get("risk_level")})

        adapter = self._adapters[row.adapter_key]
        context = ConnectorContext(
            connector_key=key, capability=capability_name,
            principal=_actor(principal), correlation_id=correlation_id,
            settings=dict(row.settings or {}))
        started = time.monotonic()
        try:
            if descriptor.requires_credential:
                result = await asyncio.to_thread(
                    self._invoke_with_credential_sync,
                    principal, row.credential_secret_name, adapter,
                    capability_name, payload, context, timeout_seconds)
            else:
                result = await asyncio.wait_for(
                    adapter.invoke(capability_name, payload, context),
                    timeout=timeout_seconds)
        except PermissionDeniedError as exc:
            category = (exc.details or {}).get("error_category", "")
            duration_ms = int((time.monotonic() - started) * 1000)
            if category in ("SECRET_UNRESOLVED", "SECRET_BACKEND_UNAVAILABLE"):
                record(C.OUTCOME_REQUIRES_OWNER_CONFIGURATION, error=exc.message,
                       duration_ms=duration_ms,
                       broker_decision_id=decision.get("decision_id"))
                self._mark_error(row, f"credential: {exc.message}")
                raise IntegrationError(
                    f"connector '{key}' credential could not be resolved "
                    f"through P-10: {exc.message}",
                    details={"outcome": C.OUTCOME_REQUIRES_OWNER_CONFIGURATION}) from exc
            record(C.OUTCOME_DENIED, error=exc.message, duration_ms=duration_ms,
                   broker_decision_id=decision.get("decision_id"))
            raise
        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            if isinstance(exc, asyncio.TimeoutError):
                detail = f"adapter invocation timed out after {timeout_seconds}s"
                outcome = C.OUTCOME_ERROR
            else:
                detail = f"{type(exc).__name__}: {exc}"
                outcome = C.OUTCOME_ERROR
            record(outcome, error=detail, duration_ms=duration_ms,
                   broker_decision_id=decision.get("decision_id"))
            self._mark_error(row, detail)
            raise IntegrationError(
                f"connector '{key}' capability '{capability_name}' failed: "
                f"{detail}", details={"outcome": outcome}) from exc

        duration_ms = int((time.monotonic() - started) * 1000)
        invocation = record(C.OUTCOME_SUCCESS, result=result,
                            duration_ms=duration_ms,
                            broker_decision_id=decision.get("decision_id"))
        row.last_invoked_at = utcnow()
        if capability.is_sync:
            row.last_sync_at = utcnow()
        if row.health_state == C.STATE_ERROR:
            row.health_state = C.STATE_NOT_CONFIGURED
        row.health_state = self._reported_state(row)
        self._save(row)
        self._audit(principal, "integration.invoked", "connector", key,
                    "allow", f"capability '{capability_name}' succeeded",
                    {"capability": capability_name, "outcome": C.OUTCOME_SUCCESS,
                     "duration_ms": duration_ms})
        return {"connector": key, "capability": capability_name,
                "outcome": C.OUTCOME_SUCCESS, "result": result,
                "invocation_id": invocation["id"], "replayed": False,
                "duration_ms": duration_ms,
                "broker_decision_id": decision.get("decision_id")}

    def _invoke_with_credential_sync(self, principal, secret_name, adapter,
                                     capability_name, payload, context,
                                     timeout_seconds):
        """Run one credentialled invocation inside P-10's brokered
        secret operation (§9.4): P-10 resolves the value and hands
        it only to this callback; the adapter coroutine runs in
        this worker thread. The value never leaves the callback."""
        def operation(value: str):
            context.credential_value = value
            try:
                return asyncio.run(asyncio.wait_for(
                    adapter.invoke(capability_name, payload, context),
                    timeout=timeout_seconds))
            finally:
                context.credential_value = None
        return self._app.security.secrets.execute_with_secret(
            principal, secret_name,
            f"integration invocation ({context.connector_key}.{capability_name})",
            operation)

    def _mark_error(self, row: IntegrationConnector, detail: str) -> None:
        row.health_state = C.STATE_ERROR
        row.last_error = detail
        row.error_count += 1
        self._save(row)

    # ------------------------------------------------------------- webhook
    def verify_webhook(self, principal: Principal, key: str, body: bytes,
                       headers: dict) -> dict:
        """Brokered webhook signature verification (service-level;
        deliberately NO new public route — inbound routing stays
        with the owning engine, e.g. P-07's payments webhook)."""
        row = self._get_row(key)
        adapter = self._adapters.get(row.adapter_key) if row.adapter_key else None
        if adapter is None:
            raise ValidationError(
                f"connector '{key}' has no adapter; webhook verification "
                f"is not available")
        if not row.requires_credential or not row.credential_secret_name:
            raise ValidationError(
                f"connector '{key}' has no credential configured for "
                f"webhook verification")

        def operation(value: str):
            return adapter.verify_webhook_signature(value, body, headers)

        try:
            verified = self._app.security.secrets.execute_with_secret(
                principal, row.credential_secret_name,
                f"integration webhook verification ({key})", operation)
        except NotImplementedError as exc:
            raise ValidationError(
                f"connector '{key}' does not verify webhook signatures") from exc
        self._audit(principal, "integration.webhook_verified", "connector",
                    key, "allow" if verified else "deny",
                    "webhook signature verification", {"verified": bool(verified)})
        return {"connector": key, "verified": bool(verified)}

    # ------------------------------------------------------------ history
    def list_invocations(self, *, connector_key=None, outcome=None,
                         limit=50, offset=0):
        session = self._session_factory()
        try:
            rows, total = InvocationRepository(session).list(
                connector_key=connector_key, outcome=outcome,
                limit=limit, offset=offset)
            return [invocation_to_dict(r) for r in rows], total
        finally:
            session.close()

    def _record_invocation(self, connector_key, capability, principal, outcome,
                           *, result=None, error=None, duration_ms=None,
                           broker_decision_id=None, idempotency_key=None,
                           correlation_id=None) -> dict:
        session = self._session_factory()
        try:
            row = InvocationRepository(session).add(IntegrationInvocation(
                connector_key=connector_key, capability=capability,
                principal_type=principal.type.value, principal_id=principal.id,
                idempotency_key=idempotency_key,
                broker_decision_id=broker_decision_id, outcome=outcome,
                result=result, error_detail=error, duration_ms=duration_ms,
                correlation_id=correlation_id))
            return invocation_to_dict(row)
        finally:
            session.close()

    # ---------------------------------------------------------------- audit
    def _audit(self, principal, action: str, target_type: str, target_id,
               decision: str, reason: str | None = None,
               details: dict | None = None) -> None:
        session = self._session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value if principal else "system",
                actor_id=principal.id if principal else "integration-framework",
                action=action, target_type=target_type, target_id=target_id,
                decision=decision, reason=reason, details=details or {},
                created_at=utcnow()))
        finally:
            session.close()
