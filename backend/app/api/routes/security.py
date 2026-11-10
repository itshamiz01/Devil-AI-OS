"""P-10 security routes (/api/v1/security/...).

Every route is authenticated and permission-guarded through P-01;
the service layer re-checks owner-only operations itself (§6.5:
the backend is the authority, never the caller). No route returns a
secret value — the data model has none to return. Login itself is
NOT duplicated here: it remains P-01's ``POST /api/v1/auth/login``
(§26.1: do not implement an endpoint whose secure equivalent
already exists); logout/session management, which P-01 lacked,
lives here.
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Query, Request

from ...core.application import Application
from ...core.exceptions import ValidationError
from ...permissions.models import Permission, Principal, PrincipalType
from ..dependencies import (
    correlation_id, get_application, get_principal, require_permission,
)
from ..schemas.common import ok, page
from ..schemas.security import (
    AlertStatusIn, BackupRestoreIn, CapabilityIssueIn, ClassificationIn,
    CommandGuardIn,
    ContentScreenIn, DeviceEnrolIn, DeviceRelabelIn, DownloadGuardIn,
    EgressCheckIn, EmergencyModeIn,
    EscalationRequestIn, FilesystemGuardIn, FinancialAuthorizeIn,
    FinancialSuspensionIn, HandoffValidateIn, IncidentIn, IncidentUpdateIn,
    OutboundScreenIn, PermissionCheckIn, PolicyRollbackIn, PolicyUpdateIn,
    RecoveryCodeVerifyIn, RecoveryCodesGenerateIn,
    RedirectChainIn, RestrictionIn, SecretAccessCheckIn, SecretRegisterIn,
    TotpVerifyIn,
)

router = APIRouter(tags=["security"])

READ = require_permission("read_system_data")
CONFIG = require_permission("modify_system_config")


def _described(body) -> Principal:
    try:
        return Principal(PrincipalType(body.principal_type), body.principal_id)
    except (ValueError, AttributeError) as exc:
        raise ValidationError(f"invalid principal: {exc}") from exc


def _svc(application: Application):
    return application.security


# --------------------------------------------------------------- status
@router.get("/security/status")
async def security_status(request: Request,
                          application: Application = Depends(get_application),
                          _: Principal = Depends(READ)):
    return ok(_svc(application).monitor.status(), correlation_id(request))


# --------------------------------------------------------------- policies
@router.get("/security/policies")
async def get_policies(request: Request,
                       application: Application = Depends(get_application),
                       _: Principal = Depends(READ)):
    svc = _svc(application)
    versions, total = svc.list_policy_versions(limit=1)
    return ok({"settings": svc.get_settings(),
               "latest_version": versions[0]["version"] if versions else None,
               "version_count": total}, correlation_id(request))


@router.put("/security/policies")
async def update_policies(body: PolicyUpdateIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(CONFIG)):
    settings = _svc(application).update_settings(principal, body.patch, body.reason)
    return ok({"settings": settings}, correlation_id(request))


@router.post("/security/policies/validate")
async def validate_policies(body: PolicyUpdateIn, request: Request,
                            application: Application = Depends(get_application),
                            _: Principal = Depends(READ)):
    from ...security import policy as policy_module
    svc = _svc(application)
    try:
        _merged, changed = policy_module.validate_settings_patch(
            body.patch, svc.get_settings())
        return ok({"valid": True, "changed_keys": changed}, correlation_id(request))
    except ValueError as exc:
        return ok({"valid": False, "error": str(exc)}, correlation_id(request))


@router.get("/security/policies/versions")
async def policy_versions(request: Request, limit: int = Query(default=50, ge=1, le=200),
                          offset: int = Query(default=0, ge=0),
                          application: Application = Depends(get_application),
                          _: Principal = Depends(READ)):
    rows, total = _svc(application).list_policy_versions(limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/security/policies/rollback")
async def rollback_policy(body: PolicyRollbackIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(CONFIG)):
    settings = _svc(application).rollback_policy(principal, body.version, body.reason)
    return ok({"settings": settings}, correlation_id(request))


# ------------------------------------------------------------- identities
@router.get("/security/identities")
async def identities(request: Request,
                     application: Application = Depends(get_application),
                     _: Principal = Depends(READ)):
    return ok(_svc(application).list_identities(), correlation_id(request))


@router.get("/security/agents/{agent_id}/permissions")
async def agent_permissions(agent_id: str, request: Request,
                            application: Application = Depends(get_application),
                            _: Principal = Depends(READ)):
    return ok(_svc(application).agent_permissions(agent_id), correlation_id(request))


# ------------------------------------------------------ broker + capabilities
@router.post("/security/permissions/check")
async def permission_check(body: PermissionCheckIn, request: Request,
                           application: Application = Depends(get_application),
                           _: Principal = Depends(READ)):
    decision = _svc(application).broker.authorize(
        _described(body), permission=body.permission, action=body.action,
        resource=body.resource, business_ref=body.business_ref,
        task_id=body.task_id, parameters=body.parameters,
        approval_id=body.approval_id, capability_id=body.capability_id,
        correlation_id=correlation_id(request))
    return ok(decision, correlation_id(request))


@router.post("/security/permissions/request", status_code=201)
async def permission_request(body: EscalationRequestIn, request: Request,
                             application: Application = Depends(get_application),
                             _: Principal = Depends(READ)):
    result = _svc(application).broker.request_escalation(
        _described(body), permission=body.permission, action=body.action,
        resource=body.resource, reason=body.reason, parameters=body.parameters)
    return ok(result, correlation_id(request))


@router.post("/security/capabilities", status_code=201)
async def issue_capability(body: CapabilityIssueIn, request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(get_principal)):
    try:
        holder = Principal(PrincipalType(body.holder_type), body.holder_id)
    except ValueError as exc:
        raise ValidationError(f"invalid holder principal: {exc}") from exc
    result = _svc(application).broker.issue_capability(
        principal, holder, permission=body.permission, resource=body.resource,
        business_ref=body.business_ref, task_id=body.task_id,
        ttl_minutes=body.ttl_minutes, reason=body.reason)
    return ok(result, correlation_id(request))


@router.get("/security/capabilities")
async def list_capabilities(request: Request, holder_id: str | None = None,
                            status: str | None = None,
                            limit: int = Query(default=50, ge=1, le=200),
                            offset: int = Query(default=0, ge=0),
                            application: Application = Depends(get_application),
                            _: Principal = Depends(READ)):
    rows, total = _svc(application).broker.list_capabilities(
        holder_id=holder_id, status=status, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/security/capabilities/{capability_id}/revoke")
async def revoke_capability(capability_id: str, request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(get_principal)):
    result = _svc(application).broker.revoke_capability(principal, capability_id)
    return ok(result, correlation_id(request))


@router.get("/security/broker/decisions")
async def broker_decisions(request: Request, principal_id: str | None = None,
                           allowed: bool | None = None,
                           limit: int = Query(default=50, ge=1, le=200),
                           offset: int = Query(default=0, ge=0),
                           application: Application = Depends(get_application),
                           _: Principal = Depends(READ)):
    rows, total = _svc(application).broker.list_decisions(
        principal_id=principal_id, allowed=allowed, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


# ----------------------------------------------------------------- secrets
@router.get("/security/secrets/access-events")
async def secret_access_events(request: Request, secret_name: str | None = None,
                               limit: int = Query(default=50, ge=1, le=200),
                               offset: int = Query(default=0, ge=0),
                               application: Application = Depends(get_application),
                               _: Principal = Depends(READ)):
    rows, total = _svc(application).secrets.list_access_events(
        secret_name=secret_name, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/security/secrets/backends")
async def secret_backends(request: Request,
                          application: Application = Depends(get_application),
                          _: Principal = Depends(READ)):
    svc = _svc(application)
    return ok({"backends": svc.secrets.backend_status(),
               "totp_configured": svc.totp.configured}, correlation_id(request))


@router.get("/security/secrets")
async def list_secrets(request: Request, status: str | None = None,
                       limit: int = Query(default=50, ge=1, le=200),
                       offset: int = Query(default=0, ge=0),
                       application: Application = Depends(get_application),
                       _: Principal = Depends(CONFIG)):
    rows, total = _svc(application).secrets.list_secrets(
        status=status, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/security/secrets", status_code=201)
async def register_secret(body: SecretRegisterIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(CONFIG)):
    result = _svc(application).secrets.register(principal, body.model_dump())
    return ok(result, correlation_id(request))


@router.post("/security/secrets/{name}/rotate")
async def rotate_secret(name: str, request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(CONFIG)):
    return ok(_svc(application).secrets.rotate(principal, name),
              correlation_id(request))


@router.post("/security/secrets/{name}/revoke")
async def revoke_secret(name: str, request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(CONFIG)):
    return ok(_svc(application).secrets.revoke(principal, name),
              correlation_id(request))


@router.post("/security/secrets/{name}/access-check")
async def secret_access_check(name: str, body: SecretAccessCheckIn, request: Request,
                              application: Application = Depends(get_application),
                              _: Principal = Depends(READ)):
    result = _svc(application).secrets.check_access(
        _described(body), name, body.purpose)
    return ok(result, correlation_id(request))


# ------------------------------------------------------------------ guards
@router.post("/security/guards/filesystem")
async def filesystem_guard(body: FilesystemGuardIn, request: Request,
                           application: Application = Depends(get_application),
                           _: Principal = Depends(READ)):
    result = _svc(application).filesystem_guard.evaluate(
        _described(body), operation=body.operation, raw_path=body.path)
    return ok(result, correlation_id(request))


@router.post("/security/guards/command")
async def command_guard(body: CommandGuardIn, request: Request,
                        application: Application = Depends(get_application),
                        _: Principal = Depends(READ)):
    result = _svc(application).command_guard.evaluate(
        _described(body), argv=body.argv, working_dir=body.working_dir)
    return ok(result, correlation_id(request))


@router.post("/security/guards/download")
async def download_guard(body: DownloadGuardIn, request: Request,
                         application: Application = Depends(get_application),
                         _: Principal = Depends(READ)):
    result = _svc(application).download_guard.evaluate(
        filename=body.filename, size_bytes=body.size_bytes,
        content_type=body.content_type)
    return ok(result, correlation_id(request))


# ----------------------------------------------------------------- network
@router.post("/security/network/egress")
async def egress_check(body: EgressCheckIn, request: Request,
                       application: Application = Depends(get_application),
                       _: Principal = Depends(READ)):
    return ok(_svc(application).egress.validate_url(body.url),
              correlation_id(request))


@router.post("/security/network/redirects")
async def redirect_check(body: RedirectChainIn, request: Request,
                         application: Application = Depends(get_application),
                         _: Principal = Depends(READ)):
    return ok(_svc(application).egress.validate_redirect_chain(body.urls),
              correlation_id(request))


# -------------------------------------------------------------- ai security
@router.post("/security/content/screen")
async def screen_content(body: ContentScreenIn, request: Request,
                         application: Application = Depends(get_application),
                         _: Principal = Depends(READ)):
    from ...security.ai_security import screen_content as _screen
    return ok(_screen(body.text, source=body.source), correlation_id(request))


@router.post("/security/content/screen-outbound")
async def screen_outbound(body: OutboundScreenIn, request: Request,
                          application: Application = Depends(get_application),
                          _: Principal = Depends(READ)):
    from ...security.ai_security import screen_outbound as _screen_out
    return ok(_screen_out(body.text), correlation_id(request))


@router.post("/security/handoffs/validate")
async def validate_handoff(body: HandoffValidateIn, request: Request,
                           application: Application = Depends(get_application),
                           _: Principal = Depends(READ)):
    from ...security.ai_security import validate_handoff as _validate
    return ok(_validate(body.envelope), correlation_id(request))


# ---------------------------------------------------------------- financial
@router.post("/security/financial/authorize")
async def financial_authorize(body: FinancialAuthorizeIn, request: Request,
                              application: Application = Depends(get_application),
                              _: Principal = Depends(READ)):
    result = _svc(application).financial_guard.authorize(
        _described(body), action=body.action, business_id=body.business_id,
        amount_minor=body.amount_minor, currency=body.currency,
        recipient=body.recipient, approval_id=body.approval_id)
    return ok(result, correlation_id(request))


# ---------------------------------------------------------------- emergency
@router.post("/security/emergency/mode")
async def set_mode(body: EmergencyModeIn, request: Request,
                   application: Application = Depends(get_application),
                   principal: Principal = Depends(CONFIG)):
    result = _svc(application).emergency.set_mode(principal, body.mode, body.reason)
    return ok(result, correlation_id(request))


@router.post("/security/emergency/financial-suspension")
async def set_financial_suspension(body: FinancialSuspensionIn, request: Request,
                                   application: Application = Depends(get_application),
                                   principal: Principal = Depends(CONFIG)):
    result = _svc(application).emergency.set_financial_suspension(
        principal, body.suspended, body.reason)
    return ok(result, correlation_id(request))


@router.get("/security/emergency/events")
async def emergency_events(request: Request,
                           limit: int = Query(default=50, ge=1, le=200),
                           offset: int = Query(default=0, ge=0),
                           application: Application = Depends(get_application),
                           _: Principal = Depends(READ)):
    rows, total = _svc(application).emergency.list_events(limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


# -------------------------------------------------------------------- audit
@router.get("/security/audit")
async def audit_events(request: Request, actor_id: str | None = None,
                       action_prefix: str | None = None, decision: str | None = None,
                       limit: int = Query(default=50, ge=1, le=200),
                       offset: int = Query(default=0, ge=0),
                       application: Application = Depends(get_application),
                       _: Principal = Depends(READ)):
    rows, total = _svc(application).monitor.list_events(
        actor_id=actor_id, action_prefix=action_prefix, decision=decision,
        limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/security/audit/seal")
async def seal_audit(request: Request,
                     application: Application = Depends(get_application),
                     _: Principal = Depends(CONFIG)):
    return ok(_svc(application).chain.seal_new_events(), correlation_id(request))


@router.get("/security/audit/verify")
async def verify_audit(request: Request,
                       application: Application = Depends(get_application),
                       _: Principal = Depends(READ)):
    return ok(_svc(application).chain.verify(), correlation_id(request))


# ------------------------------------------------------------------- alerts
@router.get("/security/alerts")
async def list_alerts(request: Request, status: str | None = None,
                      limit: int = Query(default=50, ge=1, le=200),
                      offset: int = Query(default=0, ge=0),
                      application: Application = Depends(get_application),
                      _: Principal = Depends(READ)):
    rows, total = _svc(application).monitor.list_alerts(
        status=status, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/security/alerts/evaluate")
async def evaluate_alerts(request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(CONFIG)):
    created = _svc(application).monitor.evaluate_alerts(principal)
    return ok({"created": created}, correlation_id(request))


@router.post("/security/alerts/{alert_id}/status")
async def set_alert_status(alert_id: str, body: AlertStatusIn, request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(CONFIG)):
    result = _svc(application).monitor.set_alert_status(principal, alert_id, body.status)
    return ok(result, correlation_id(request))


# ---------------------------------------------------------------- incidents
@router.get("/security/incidents")
async def list_incidents(request: Request, status: str | None = None,
                         limit: int = Query(default=50, ge=1, le=200),
                         offset: int = Query(default=0, ge=0),
                         application: Application = Depends(get_application),
                         _: Principal = Depends(READ)):
    rows, total = _svc(application).list_incidents(
        status=status, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/security/incidents", status_code=201)
async def create_incident(body: IncidentIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(CONFIG)):
    result = _svc(application).create_incident(principal, body.model_dump())
    return ok(result, correlation_id(request))


@router.patch("/security/incidents/{incident_id}")
async def update_incident(incident_id: str, body: IncidentUpdateIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(CONFIG)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    result = _svc(application).update_incident(principal, incident_id, patch)
    return ok(result, correlation_id(request))


# ------------------------------------------------------------------ backups
@router.get("/security/backups")
async def list_backups(request: Request,
                       limit: int = Query(default=50, ge=1, le=200),
                       offset: int = Query(default=0, ge=0),
                       application: Application = Depends(get_application),
                       _: Principal = Depends(READ)):
    rows, total = _svc(application).backup.list_backups(limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/security/backups", status_code=201)
async def create_backup(request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(CONFIG)):
    result = _svc(application).backup.create_backup(principal)
    return ok(result, correlation_id(request))


@router.post("/security/backups/{backup_id}/verify")
async def verify_backup(backup_id: str, request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(CONFIG)):
    result = _svc(application).backup.verify_backup(principal, backup_id)
    return ok(result, correlation_id(request))


@router.post("/security/backups/{backup_id}/restore-preview")
async def restore_preview(backup_id: str, body: BackupRestoreIn,
                          request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(CONFIG)):
    """P-14 Stage B (DEF-A4): guarded restore preview — verifies the
    backup, checks the hash-bound approval read-only, snapshots the
    current database, and returns the manual execution plan. Never
    overwrites the live database."""
    result = _svc(application).restore_preview(
        principal, backup_id, body.approval_id)
    return ok(result, correlation_id(request))


# ------------------------------------------------------------------ threats
@router.get("/security/threats")
async def list_threats(request: Request,
                       limit: int = Query(default=100, ge=1, le=200),
                       offset: int = Query(default=0, ge=0),
                       application: Application = Depends(get_application),
                       _: Principal = Depends(READ)):
    rows, total = _svc(application).list_threats(limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


# -------------------------------------------------------------- restrictions
@router.get("/security/restrictions")
async def list_restrictions(request: Request, status: str | None = None,
                            limit: int = Query(default=50, ge=1, le=200),
                            offset: int = Query(default=0, ge=0),
                            application: Application = Depends(get_application),
                            _: Principal = Depends(READ)):
    rows, total = _svc(application).list_restrictions(
        status=status, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/security/restrictions", status_code=201)
async def impose_restriction(body: RestrictionIn, request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(CONFIG)):
    result = _svc(application).impose_restriction(
        principal, body.agent_id, body.restriction, body.reason)
    return ok(result, correlation_id(request))


@router.post("/security/restrictions/{restriction_id}/release")
async def release_restriction(restriction_id: str, request: Request,
                              application: Application = Depends(get_application),
                              principal: Principal = Depends(CONFIG)):
    result = _svc(application).release_restriction(principal, restriction_id)
    return ok(result, correlation_id(request))


# ------------------------------------------------------------ classifications
@router.get("/security/classifications")
async def list_classifications(request: Request,
                               limit: int = Query(default=50, ge=1, le=200),
                               offset: int = Query(default=0, ge=0),
                               application: Application = Depends(get_application),
                               _: Principal = Depends(READ)):
    rows, total = _svc(application).list_classifications(limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/security/classifications", status_code=201)
async def register_classification(body: ClassificationIn, request: Request,
                                  application: Application = Depends(get_application),
                                  principal: Principal = Depends(CONFIG)):
    result = _svc(application).register_classification(principal, body.model_dump())
    return ok(result, correlation_id(request))


# ------------------------------------------------------------ browser access
@router.get("/security/browser-sessions/{session_id}/access")
async def browser_session_access(session_id: str, request: Request,
                                 principal_type: str | None = None,
                                 principal_id: str | None = None,
                                 application: Application = Depends(get_application),
                                 caller: Principal = Depends(READ)):
    subject = caller
    if principal_type and principal_id:
        try:
            subject = Principal(PrincipalType(principal_type), principal_id)
        except ValueError as exc:
            raise ValidationError(f"invalid principal: {exc}") from exc
    result = _svc(application).check_browser_session_access(subject, session_id)
    return ok(result, correlation_id(request))


# --------------------------------------------------------------------- auth
@router.get("/security/auth/sessions")
async def list_sessions(request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(CONFIG)):
    return ok(_svc(application).sessions.list_sessions(principal),
              correlation_id(request))


@router.post("/security/auth/sessions/{session_id}/revoke")
async def revoke_session(session_id: str, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(CONFIG)):
    result = _svc(application).sessions.revoke_session(principal, session_id)
    return ok(result, correlation_id(request))


@router.post("/security/auth/logout")
async def logout(request: Request,
                 application: Application = Depends(get_application),
                 principal: Principal = Depends(get_principal)):
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    if not token:
        return ok({"revoked": False}, correlation_id(request))
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    revoked = _svc(application).sessions.revoke_by_token_hash(principal, token_hash)
    return ok({"revoked": revoked}, correlation_id(request))


@router.post("/security/auth/totp/verify")
async def totp_verify(body: TotpVerifyIn, request: Request,
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(get_principal)):
    svc = _svc(application)
    return ok({"configured": svc.totp.configured,
               "verified": svc.totp.verify(body.code)}, correlation_id(request))


# ------------------------------------------- devices (Expansion F-01)
# Identity & Device Security: the device registry and MFA recovery
# codes, extending P-10 in place. Route guards use the Permission
# ENUM (§4.2 inheritance contract point 2) and the service layer
# re-checks owner-only operations itself, exactly like the session
# surface above. The device secret appears in exactly the enrol /
# rotate responses; recovery codes in exactly the generate
# response. No other route can return either.
DEVICE_READ = require_permission(Permission.READ_SYSTEM_DATA.value)
DEVICE_WRITE = require_permission(Permission.MODIFY_SYSTEM_CONFIG.value)


@router.post("/security/devices", status_code=201)
async def enrol_device(body: DeviceEnrolIn, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(DEVICE_WRITE)):
    result = _svc(application).devices.enrol(principal, body.model_dump())
    return ok(result, correlation_id(request))


@router.get("/security/devices")
async def list_devices(request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(DEVICE_READ)):
    return ok(_svc(application).devices.list_devices(principal),
              correlation_id(request))


@router.get("/security/devices/{device_id}")
async def get_device(device_id: str, request: Request,
                     application: Application = Depends(get_application),
                     principal: Principal = Depends(DEVICE_READ)):
    return ok(_svc(application).devices.get_device(principal, device_id),
              correlation_id(request))


@router.patch("/security/devices/{device_id}")
async def relabel_device(device_id: str, body: DeviceRelabelIn, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(DEVICE_WRITE)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    result = _svc(application).devices.relabel(principal, device_id, patch)
    return ok(result, correlation_id(request))


@router.post("/security/devices/{device_id}/trust")
async def trust_device(device_id: str, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(DEVICE_WRITE)):
    result = _svc(application).devices.set_trust(principal, device_id, True)
    return ok(result, correlation_id(request))


@router.post("/security/devices/{device_id}/untrust")
async def untrust_device(device_id: str, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(DEVICE_WRITE)):
    result = _svc(application).devices.set_trust(principal, device_id, False)
    return ok(result, correlation_id(request))


@router.post("/security/devices/{device_id}/revoke")
async def revoke_device(device_id: str, request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(DEVICE_WRITE)):
    result = _svc(application).devices.revoke(principal, device_id)
    return ok(result, correlation_id(request))


@router.post("/security/devices/{device_id}/rotate-secret")
async def rotate_device_secret(device_id: str, request: Request,
                               application: Application = Depends(get_application),
                               principal: Principal = Depends(DEVICE_WRITE)):
    result = _svc(application).devices.rotate_secret(principal, device_id)
    return ok(result, correlation_id(request))


# ------------------------------------- recovery codes (Expansion F-01)
@router.post("/security/auth/recovery-codes/generate", status_code=201)
async def generate_recovery_codes(body: RecoveryCodesGenerateIn, request: Request,
                                  application: Application = Depends(get_application),
                                  principal: Principal = Depends(DEVICE_WRITE)):
    result = _svc(application).recovery_codes.generate(principal, body.count)
    return ok(result, correlation_id(request))


@router.get("/security/auth/recovery-codes")
async def recovery_codes_status(request: Request,
                                application: Application = Depends(get_application),
                                principal: Principal = Depends(DEVICE_READ)):
    return ok(_svc(application).recovery_codes.status(principal),
              correlation_id(request))


@router.post("/security/auth/recovery-codes/verify")
async def verify_recovery_code(body: RecoveryCodeVerifyIn, request: Request,
                               application: Application = Depends(get_application),
                               principal: Principal = Depends(get_principal)):
    result = _svc(application).recovery_codes.verify(principal, body.code)
    return ok(result, correlation_id(request))
