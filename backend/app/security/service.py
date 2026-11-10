"""SecurityService — the P-10 facade.

Owns the owner-governed security policy lifecycle (``security.
settings`` in system_config: seeded, versioned on every change,
rollback as a new version — §23) and wires the P-10 sub-services
over the P-01 substrate. Constructed last in ``Application.startup``
(after P-09), because the financial guard reads P-07 and the
restriction overlay reads P-04's agent registry.

Article 0 boundary, stated structurally: this facade's only
governance write is its OWN settings key, through the owner-only
versioned path below. It never calls ``ApprovalService.decide``
(approvals are consumed read-only via ``verify_binding``), never
writes P-07, and reads nothing from P-09 memory — a structural test
greps this package for those surfaces.
"""
from __future__ import annotations

import json

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.base import utcnow
from ..database.models.business import Business
from ..database.models.core import AuditEvent
from ..database.models.security import (
    SecurityDataClassification, SecurityIncident, SecurityAgentRestriction,
)
from ..database.repositories.core import AuditRepository, ConfigRepository
from ..database.repositories.security import (
    DataClassificationRepository, IncidentRepository,
    AgentRestrictionRepository, PolicyVersionRepository, ThreatRepository,
)
from ..database.models.security import SecurityPolicyVersion, SecurityThreat
from ..permissions.models import Principal, PrincipalType
from ..events.events import Event, EventType
from . import constants as C
from . import policy as P
from .audit_chain import AuditChainService
from .backup import BackupService
from .broker import PermissionBroker
from .devices import DeviceService, RecoveryCodeService
from .emergency import EmergencyService
from .financial_guard import FinancialGuard
from .guards import CommandGuard, DownloadGuard, FilesystemGuard
from .identity import LoginGuard, SessionService, TotpVerifier
from .monitoring import SecurityMonitor
from .network import EgressValidator
from .secrets import SecretService


class SecurityService:
    def __init__(self, session_factory, *, permissions, approvals,
                 app_settings, financial=None, bus=None):
        self._session_factory = session_factory
        self._permissions = permissions
        self._approvals = approvals
        self._app_settings = app_settings
        self._financial = financial
        # P-14 Stage B (DEF-I1): optional event bus; incidents publish
        # SECURITY_INCIDENT_DETECTED when a bus is wired.
        self._bus = bus

        self.chain = AuditChainService(session_factory)
        self.sessions = SessionService(session_factory, self._audit)
        # Expansion Feature 1 (Identity & Device Security): the
        # device registry + MFA recovery codes, extending this
        # facade — same audit callback, same P-01 substrate.
        self.devices = DeviceService(session_factory, self._audit)
        self.recovery_codes = RecoveryCodeService(session_factory, self._audit)
        self.login_guard = LoginGuard(session_factory, self.get_settings)
        self.broker = PermissionBroker(session_factory, permissions, approvals,
                                       self.get_settings, self._audit)
        self.secrets = SecretService(session_factory, permissions,
                                     self.get_settings, self._audit)
        self.totp = TotpVerifier(
            lambda: self.secrets.resolve_reference("env:AUTONOMUS_TOTP_SECRET"))
        self.emergency = EmergencyService(
            session_factory, self.get_settings,
            lambda pr, patch, reason: self._apply_settings(
                pr, patch, reason, via_emergency=True),
            self._audit)
        self.monitor = SecurityMonitor(session_factory, self.get_settings, self.chain)
        self.backup = BackupService(
            session_factory, app_settings.effective_database_url,
            app_settings.data_dir, self._audit)
        self.filesystem_guard = FilesystemGuard(
            self.get_settings, self.classification_level, self._audit)
        self.command_guard = CommandGuard(self.get_settings, self._audit)
        self.download_guard = DownloadGuard(self.get_settings)
        self.egress = EgressValidator(self.get_settings)
        self.financial_guard = FinancialGuard(
            session_factory, permissions, approvals, self.get_settings,
            self._financial_settings, self._audit)

    # ------------------------------------------------------------ settings
    def seed_settings(self) -> None:
        session = self._session_factory()
        try:
            repo = ConfigRepository(session)
            if repo.get(C.SETTINGS_KEY) is None:
                repo.set(C.SETTINGS_KEY, json.dumps(C.DEFAULT_SETTINGS),
                         "security settings (owner-governed; mode, capability "
                         "TTLs, login throttling, alert thresholds, command "
                         "allowlist, protected roots, egress policy)")
                PolicyVersionRepository(session).add(SecurityPolicyVersion(
                    version=1, previous_settings={},
                    new_settings=dict(C.DEFAULT_SETTINGS), changed_keys=[],
                    actor="system:bootstrap", reason="initial seed"))
        finally:
            session.close()

    def get_settings(self) -> dict:
        session = self._session_factory()
        try:
            row = ConfigRepository(session).get(C.SETTINGS_KEY)
            stored = json.loads(row.value) if row and row.value else {}
        finally:
            session.close()
        return {**C.DEFAULT_SETTINGS, **stored}

    def update_settings(self, principal: Principal, patch: dict,
                        reason: str | None = None) -> dict:
        """Owner-only policy write (§23.2). Mode and financial
        suspension are refused here — they move only through the
        emergency endpoints, so every mode transition also produces
        an emergency event (§20)."""
        if isinstance(patch, dict) and (
                "mode" in patch or "financial_suspension" in patch):
            self._deny_policy_update(principal, patch,
                                     "mode and financial_suspension change only "
                                     "through the emergency controls")
            raise ValidationError(
                "security mode and financial suspension change only through "
                "the emergency endpoints (POST /security/emergency/...)")
        return self._apply_settings(principal, patch, reason, via_emergency=False)

    def _apply_settings(self, principal: Principal, patch: dict,
                        reason: str | None, *, via_emergency: bool) -> dict:
        if not P.is_owner(principal):
            self._deny_policy_update(principal, patch,
                                     "security policy is owner-governed (Article 0)")
            raise PermissionDeniedError(
                "security policy changes are owner-only; agents cannot "
                "modify approval policies or their own permissions (§8.4/§23.2)",
                details={"error_category": "POLICY_OWNER_ONLY"})
        current = self.get_settings()
        merged, changed = P.validate_settings_patch(patch, current)
        session = self._session_factory()
        try:
            ConfigRepository(session).set(
                C.SETTINGS_KEY, json.dumps(merged),
                f"updated by {P.actor(principal)}")
            repo = PolicyVersionRepository(session)
            latest = repo.latest()
            version = (latest.version + 1) if latest else 1
            repo.add(SecurityPolicyVersion(
                version=version, previous_settings=current,
                new_settings=merged, changed_keys=changed,
                actor=P.actor(principal), reason=reason))
        finally:
            session.close()
        self._audit(principal, "security.policy_update", "system_config",
                    C.SETTINGS_KEY, "allow",
                    reason or "security policy updated",
                    {"changed_keys": changed, "version": version,
                     "via_emergency": via_emergency})
        return merged

    def _deny_policy_update(self, principal, patch, why: str) -> None:
        self._audit(principal, "security.policy_update", "system_config",
                    C.SETTINGS_KEY, "deny", why,
                    {"attempted_keys": sorted(patch) if isinstance(patch, dict) else []})

    def list_policy_versions(self, *, limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = PolicyVersionRepository(session).list(
                limit=limit, offset=offset)
            return [{
                "version": r.version, "changed_keys": r.changed_keys,
                "actor": r.actor, "reason": r.reason,
                "approval_id": r.approval_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            } for r in rows], total
        finally:
            session.close()

    def rollback_policy(self, principal: Principal, version: int,
                        reason: str | None = None) -> dict:
        """§23.4: restore a recorded version's settings as a NEW
        version (history is never rewritten). Mandatory protections
        are code, not settings, so no rollback can disable them."""
        if not P.is_owner(principal):
            self._deny_policy_update(principal, {}, "rollback is owner-only")
            raise PermissionDeniedError("policy rollback is owner-only (§23.4)")
        session = self._session_factory()
        try:
            target = PolicyVersionRepository(session).get_by_version(version)
            if target is None:
                raise NotFoundError(f"policy version {version} not found")
            target_settings = dict(target.new_settings)
        finally:
            session.close()
        current = self.get_settings()
        changed = [k for k in target_settings
                   if current.get(k) != target_settings[k]]
        return self._apply_settings(
            principal, {k: target_settings[k] for k in changed},
            reason or f"rollback to policy version {version}",
            via_emergency=True)

    def _financial_settings(self) -> dict:
        if self._financial is None:
            return {}
        return self._financial.get_settings()

    # ------------------------------------------------------- threat register
    def seed_threat_register(self) -> int:
        session = self._session_factory()
        try:
            repo = ThreatRepository(session)
            seeded = 0
            for entry in C.THREAT_REGISTER_SEED:
                if repo.get_by_code(entry["code"]) is None:
                    repo.add(SecurityThreat(**entry))
                    seeded += 1
            return seeded
        finally:
            session.close()

    def list_threats(self, *, limit: int = 100, offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = ThreatRepository(session).list(limit=limit, offset=offset)
            return [{
                "code": r.code, "title": r.title, "description": r.description,
                "entry_point": r.entry_point, "affected_assets": r.affected_assets,
                "likelihood": r.likelihood, "impact": r.impact,
                "risk_level": r.risk_level,
                "preventive_controls": r.preventive_controls,
                "detection_controls": r.detection_controls,
                "recovery_procedure": r.recovery_procedure,
                "verification_test": r.verification_test, "status": r.status,
            } for r in rows], total
        finally:
            session.close()

    # ------------------------------------------------------- classifications
    def register_classification(self, principal: Principal, data: dict) -> dict:
        if not P.is_owner(principal):
            raise PermissionDeniedError(
                "data classification is owner-governed (§17.1)")
        level = int(data.get("classification", 0))
        if level not in C.CLASSIFICATION_LEVELS:
            raise ValidationError("classification must be a level 1–5 (§4.2)")
        resource_ref = (data.get("resource_ref") or "").strip()
        if not resource_ref:
            raise ValidationError("resource_ref is required")
        # P-14 Stage B (DEF-D4): when a business_ref is supplied it must
        # reference an existing business — canonical IDs only.
        business_ref = data.get("business_ref")
        if business_ref:
            session_check = self._session_factory()
            try:
                if session_check.get(Business, business_ref) is None:
                    raise ValidationError(
                        f"business_ref {business_ref} does not reference an "
                        "existing business (P-14 DEF-D4)")
            finally:
                session_check.close()
        session = self._session_factory()
        try:
            repo = DataClassificationRepository(session)
            row = repo.get_by_resource(resource_ref)
            if row is None:
                row = repo.add(SecurityDataClassification(
                    resource_ref=resource_ref, classification=level,
                    business_ref=data.get("business_ref"),
                    owner_principal=P.actor(principal),
                    retention_days=data.get("retention_days"),
                    notes=data.get("notes")))
            else:
                row.classification = level
                row.business_ref = data.get("business_ref", row.business_ref)
                row.retention_days = data.get("retention_days", row.retention_days)
                row.notes = data.get("notes", row.notes)
                row = repo.save(row)
            result = {"resource_ref": row.resource_ref,
                      "classification": row.classification,
                      "classification_name": C.CLASSIFICATION_LEVELS[row.classification],
                      "business_ref": row.business_ref,
                      "retention_days": row.retention_days}
        finally:
            session.close()
        self._audit(principal, "security.classification_registered",
                    "resource", resource_ref, "allow",
                    f"classification level {level}", {})
        return result

    def classification_level(self, resource_ref: str) -> int | None:
        session = self._session_factory()
        try:
            row = DataClassificationRepository(session).get_by_resource(resource_ref)
            return row.classification if row else None
        finally:
            session.close()

    def list_classifications(self, *, limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = DataClassificationRepository(session).list(
                limit=limit, offset=offset)
            return [{
                "resource_ref": r.resource_ref, "classification": r.classification,
                "classification_name": C.CLASSIFICATION_LEVELS[r.classification],
                "business_ref": r.business_ref,
                "retention_days": r.retention_days, "notes": r.notes,
            } for r in rows], total
        finally:
            session.close()

    # ---------------------------------------------------------- restrictions
    def impose_restriction(self, principal: Principal, agent_id: str,
                           restriction: str = "suspended",
                           reason: str | None = None) -> dict:
        if not P.is_owner(principal):
            raise PermissionDeniedError(
                "agent restrictions are owner-only (§15.4)")
        if restriction not in ("suspended", "read_only"):
            raise ValidationError("restriction must be 'suspended' or 'read_only'")
        session = self._session_factory()
        try:
            repo = AgentRestrictionRepository(session)
            if repo.active_for(agent_id) is not None:
                raise ValidationError(
                    f"agent '{agent_id}' already has an active restriction; "
                    f"release it before imposing another")
            row = repo.add(SecurityAgentRestriction(
                agent_id=agent_id, restriction=restriction, reason=reason,
                status="active", imposed_by=P.actor(principal)))
            result = self._restriction_dict(row)
        finally:
            session.close()
        self._audit(principal, "security.agent_restricted", "agent", agent_id,
                    "allow", reason or f"restriction '{restriction}' imposed", {})
        return result

    def release_restriction(self, principal: Principal, restriction_id: str) -> dict:
        if not P.is_owner(principal):
            raise PermissionDeniedError("restriction release is owner-only (§15.4)")
        session = self._session_factory()
        try:
            repo = AgentRestrictionRepository(session)
            row = repo.get(restriction_id)
            if row is None:
                raise NotFoundError(f"restriction {restriction_id} not found")
            row.status = "released"
            row.released_by = P.actor(principal)
            result = self._restriction_dict(repo.save(row))
        finally:
            session.close()
        self._audit(principal, "security.agent_restriction_released", "agent",
                    result["agent_id"], "allow", "restriction released", {})
        return result

    def list_restrictions(self, *, status: str | None = None,
                          limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = AgentRestrictionRepository(session).list(
                status=status, limit=limit, offset=offset)
            return [self._restriction_dict(r) for r in rows], total
        finally:
            session.close()

    @staticmethod
    def _restriction_dict(row: SecurityAgentRestriction) -> dict:
        return {"id": row.id, "agent_id": row.agent_id,
                "restriction": row.restriction, "reason": row.reason,
                "status": row.status, "imposed_by": row.imposed_by,
                "released_by": row.released_by,
                "created_at": row.created_at.isoformat() if row.created_at else None}

    # -------------------------------------------------------------- incidents
    def create_incident(self, principal: Principal, data: dict) -> dict:
        if not P.is_owner(principal):
            raise PermissionDeniedError("incident records are owner-managed")
        session = self._session_factory()
        try:
            row = IncidentRepository(session).add(SecurityIncident(
                title=data.get("title", ""), category=data.get("category", "general"),
                severity=data.get("severity", "medium"),
                description=data.get("description", ""),
                related_ref=data.get("related_ref"),
                created_by=P.actor(principal)))
            result = self._incident_dict(row)
        finally:
            session.close()
        self._audit(principal, "security.incident_created", "incident",
                    result["id"], "allow", data.get("title", ""), {})
        # P-14 Stage B (DEF-I1): incidents are first-class bus events,
        # persisted via the critical set like other security signals.
        if self._bus is not None:
            self._bus.publish_sync_safe(Event(
                event_type=EventType.SECURITY_INCIDENT_DETECTED,
                source="security.service",
                payload={"incident_id": result["id"],
                         "title": result["title"],
                         "category": result["category"],
                         "incident_severity": result["severity"],
                         "related_ref": result["related_ref"]},
                severity=result["severity"], actor=P.actor(principal)))
        return result

    def update_incident(self, principal: Principal, incident_id: str,
                        patch: dict) -> dict:
        if not P.is_owner(principal):
            raise PermissionDeniedError("incident records are owner-managed")
        session = self._session_factory()
        try:
            repo = IncidentRepository(session)
            row = repo.get(incident_id)
            if row is None:
                raise NotFoundError(f"incident {incident_id} not found")
            if "status" in patch:
                if patch["status"] not in ("open", "investigating", "contained",
                                            "resolved", "closed"):
                    raise ValidationError(f"unknown incident status '{patch['status']}'")
                row.status = patch["status"]
            if "resolution" in patch:
                row.resolution = patch["resolution"]
            if "severity" in patch:
                row.severity = patch["severity"]
            result = self._incident_dict(repo.save(row))
        finally:
            session.close()
        self._audit(principal, "security.incident_updated", "incident",
                    incident_id, "allow", str(sorted(patch)), {})
        return result

    def list_incidents(self, *, status: str | None = None,
                       limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = IncidentRepository(session).list(
                status=status, limit=limit, offset=offset)
            return [self._incident_dict(r) for r in rows], total
        finally:
            session.close()

    @staticmethod
    def _incident_dict(row: SecurityIncident) -> dict:
        return {"id": row.id, "title": row.title, "category": row.category,
                "severity": row.severity, "description": row.description,
                "status": row.status, "related_ref": row.related_ref,
                "created_by": row.created_by, "resolution": row.resolution,
                "created_at": row.created_at.isoformat() if row.created_at else None}

    # ------------------------------------------------- identities (§5/§6/§24.2)
    def list_identities(self) -> dict:
        """The identity registry as a view over P-01: principal types
        (resolved by P-01 auth) + registered agents. No second
        identity store exists (§2 rule 4)."""
        from ..database.models.core import Agent as AgentRow
        from sqlalchemy import select
        session = self._session_factory()
        try:
            agents = list(session.scalars(
                select(AgentRow).order_by(AgentRow.id).limit(500)))
        finally:
            session.close()
        return {
            "principal_types": [t.value for t in PrincipalType],
            "note": ("human and service identities are resolved by P-01 "
                     "authentication; agents are P-01 registrations governed "
                     "by the P-04 factory"),
            "agents": [{
                "agent_id": a.id, "name": a.name, "role": a.role,
                "business_ref": a.business_ref, "status": a.status,
                "created_by": (f"{a.created_by_type}:{a.created_by_id}"
                               if a.created_by_type else None),
            } for a in agents],
        }

    def agent_permissions(self, agent_id: str) -> dict:
        """Role defaults + explicit DB rules for one agent (§24.2
        view over the P-01 engine's data — the engine stays the
        authority; this only displays its inputs)."""
        from ..database.repositories.core import PermissionRepository
        from ..permissions.policies import ROLE_DEFAULTS
        session = self._session_factory()
        try:
            rules = PermissionRepository(session).rules_for("agent", agent_id)
        finally:
            session.close()
        return {
            "agent_id": agent_id,
            "role_defaults": sorted(ROLE_DEFAULTS.get("agent", set())),
            "explicit_rules": [{
                "permission": r.permission, "effect": r.effect,
                "resource": r.resource,
                "scope": "agent" if r.principal_id else "role",
            } for r in rules],
        }

    # ------------------------------------------- browser sessions (§12, Sc.17)
    def check_browser_session_access(self, principal: Principal,
                                     session_id: str) -> dict:
        """May this principal use this P-05 browser session?
        Sessions bind to an agent; cross-business use is denied by
        resolving both agents' registered business scope (the same
        resolution P-07–P-09 use)."""
        from ..database.models.core import Agent as AgentRow
        from ..database.models.execution import BrowserSession
        session = self._session_factory()
        try:
            row = session.get(BrowserSession, session_id)
            if row is None:
                raise NotFoundError(f"browser session {session_id} not found")
            info = {"session_id": row.id, "agent_id": row.agent_id,
                    "status": row.status,
                    "allowed_domains": row.allowed_domains,
                    "permission_profile": row.permission_profile}
            owner_business = None
            owner_row = session.get(AgentRow, row.agent_id)
            if owner_row is not None:
                owner_business = owner_row.business_ref
            caller_business = None
            if principal.type is PrincipalType.AGENT:
                caller_row = session.get(AgentRow, principal.id)
                if caller_row is not None:
                    caller_business = caller_row.business_ref
        finally:
            session.close()
        if row.status != "active":
            return {**info, "allowed": False,
                    "reason": f"browser session is '{row.status}', not active"}
        if expires := row.expires_at:
            if expires.tzinfo is None:
                import datetime as dt
                expires = expires.replace(tzinfo=dt.timezone.utc)
            if expires <= utcnow():
                return {**info, "allowed": False, "reason": "browser session expired"}
        if P.is_owner(principal):
            return {**info, "allowed": True, "reason": "owner access"}
        if principal.type is not PrincipalType.AGENT:
            return {**info, "allowed": False,
                    "reason": "browser sessions are agent-bound; this principal type may not use them"}
        if principal.id == row.agent_id:
            return {**info, "allowed": True,
                    "reason": "the session belongs to this agent"}
        if caller_business is not None and caller_business == owner_business:
            return {**info, "allowed": True,
                    "reason": "same registered business scope as the session owner"}
        return {**info, "allowed": False,
                "reason": ("browser session belongs to another agent/business; "
                           "cross-business session access denied (§12.1)")}

    # ------------------------------------------- backup restore (DEF-A4)
    def restore_preview(self, principal: Principal, backup_id: str,
                        approval_id: str) -> dict:
        """P-14 Stage B (DEF-A4): a GUARDED restore preview.

        The application never overwrites a live database (the backup
        module's stated design; restore stays the manual owner
        procedure in the incident-response playbook). This method
        performs every guard the future execution step needs and
        returns the concrete plan WITHOUT executing it:

        - owner-only;
        - the backup must exist and verify (hash + inventory +
          integrity, via the existing verify path);
        - an approved, hash-bound P-01 approval for the restore must
          exist — consumed READ-ONLY through verify_binding, exactly
          like every other P-10 approval consumer (this facade never
          decides approvals);
        - a fresh pre-restore snapshot of the current database is
          taken first, so the manual step always has a rollback copy.

        ``executed`` is always False here; the owner performs the
        file swap with the app stopped (playbook §5) and re-verifies.
        """
        if not P.is_owner(principal):
            raise PermissionDeniedError("restore preview is owner-only (§20.4)")
        from ..permissions.approvals import parameters_hash
        verification = self.backup.verify_backup(principal, backup_id)
        if verification["status"] != "verified":
            raise ValidationError(
                f"backup {backup_id} does not verify "
                f"({verification['detail']}); restore preview refused")
        approval = self._approvals.get(approval_id)
        bound = self._approvals.verify_binding(
            approval, "security.restore_backup", "backup",
            {"backup_id": backup_id})
        if not bound:
            raise ValidationError(
                "approval is not an approved, hash-bound approval for "
                "restoring this backup (P-14 DEF-A4 guard)")
        snapshot = self.backup.create_backup(principal)
        plan = {
            "backup_id": backup_id,
            "backup_location": verification["location"],
            "backup_sha256": verification["sha256"],
            "approval_id": approval_id,
            "approval_parameters_hash": parameters_hash(
                "security.restore_backup", "backup", {"backup_id": backup_id}),
            "pre_restore_snapshot_id": snapshot["id"],
            "pre_restore_snapshot_location": snapshot["location"],
            "executed": False,
            "manual_steps": [
                "Stop the application.",
                "Copy the pre-restore snapshot file aside as the rollback copy.",
                "Copy the backup file over the live database file.",
                "Start the application.",
                "Verify: GET /security/status and POST /security/audit/verify, "
                "then record the restore in an incident record.",
            ],
            "note": ("Preview only — the application does not overwrite a "
                     "live database; the file swap is the owner's manual "
                     "step (INCIDENT_RESPONSE_PLAYBOOK §5)."),
        }
        self._audit(principal, "security.backup_restore_previewed", "backup",
                    backup_id, "allow",
                    "guarded restore preview issued (not executed)",
                    {"approval_id": approval_id,
                     "snapshot_id": snapshot["id"]})
        return plan

    # ---------------------------------------------------------------- audit
    def _audit(self, principal, action: str, target_type: str, target_id,
               decision: str, reason: str | None = None,
               details: dict | None = None) -> None:
        session = self._session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value if principal else "system",
                actor_id=principal.id if principal else "security-engine",
                action=action, target_type=target_type, target_id=target_id,
                decision=decision, reason=reason, details=details or {},
                created_at=utcnow()))
        finally:
            session.close()
