"""Repository layer for P-10 security tables. All SQL for the
security package lives here or in the services built on these
repositories; API routes never build queries directly.

Append-only by convention: broker decisions, policy versions, secret
access events, emergency events, audit-chain seals and login
attempts expose no update or delete. Capabilities, alerts,
incidents, restrictions, backups and secret metadata transition
status only through their services, which audit every transition.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.core import AuditEvent
from ..models.security import (
    SecurityAgentRestriction, SecurityAlert, SecurityAuditChain,
    SecurityBackupRecord, SecurityBrokerDecision, SecurityCapability,
    SecurityDataClassification, SecurityDevice, SecurityEmergencyEvent,
    SecurityIncident, SecurityLoginAttempt, SecurityPolicyVersion,
    SecurityRecoveryCode, SecuritySecretAccessEvent, SecuritySecretMetadata,
    SecurityThreat,
)


class _Repo:
    model = None

    def __init__(self, session: Session):
        self.session = session

    def add(self, row):
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def save(self, row):
        self.session.commit()
        self.session.refresh(row)
        return row

    def get(self, row_id: str):
        return self.session.get(self.model, row_id)


class CapabilityRepository(_Repo):
    model = SecurityCapability

    def list(self, *, holder_id: str | None = None, status: str | None = None,
             limit: int = 50, offset: int = 0) -> tuple[list, int]:
        stmt = select(SecurityCapability)
        count = select(func.count()).select_from(SecurityCapability)
        if holder_id is not None:
            stmt = stmt.where(SecurityCapability.holder_id == holder_id)
            count = count.where(SecurityCapability.holder_id == holder_id)
        if status is not None:
            stmt = stmt.where(SecurityCapability.status == status)
            count = count.where(SecurityCapability.status == status)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(SecurityCapability.created_at.desc())
            .limit(limit).offset(offset)))
        return rows, total


class BrokerDecisionRepository(_Repo):
    model = SecurityBrokerDecision

    def list(self, *, principal_id: str | None = None, allowed: bool | None = None,
             limit: int = 50, offset: int = 0) -> tuple[list, int]:
        stmt = select(SecurityBrokerDecision)
        count = select(func.count()).select_from(SecurityBrokerDecision)
        if principal_id is not None:
            stmt = stmt.where(SecurityBrokerDecision.principal_id == principal_id)
            count = count.where(SecurityBrokerDecision.principal_id == principal_id)
        if allowed is not None:
            stmt = stmt.where(SecurityBrokerDecision.allowed == allowed)
            count = count.where(SecurityBrokerDecision.allowed == allowed)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(SecurityBrokerDecision.created_at.desc())
            .limit(limit).offset(offset)))
        return rows, total

    def decision_for_approval(self, approval_id: str, *, allowed_only: bool = True):
        stmt = select(SecurityBrokerDecision).where(
            SecurityBrokerDecision.approval_id == approval_id)
        if allowed_only:
            stmt = stmt.where(SecurityBrokerDecision.allowed == True)  # noqa: E712
        return self.session.scalars(stmt).first()


class PolicyVersionRepository(_Repo):
    model = SecurityPolicyVersion

    def latest(self) -> SecurityPolicyVersion | None:
        return self.session.scalars(
            select(SecurityPolicyVersion)
            .order_by(SecurityPolicyVersion.version.desc())).first()

    def get_by_version(self, version: int) -> SecurityPolicyVersion | None:
        return self.session.scalars(
            select(SecurityPolicyVersion)
            .where(SecurityPolicyVersion.version == version)).first()

    def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list, int]:
        total = self.session.scalar(
            select(func.count()).select_from(SecurityPolicyVersion)) or 0
        rows = list(self.session.scalars(
            select(SecurityPolicyVersion)
            .order_by(SecurityPolicyVersion.version.desc())
            .limit(limit).offset(offset)))
        return rows, total


class SecretMetadataRepository(_Repo):
    model = SecuritySecretMetadata

    def get_by_name(self, name: str) -> SecuritySecretMetadata | None:
        return self.session.scalars(
            select(SecuritySecretMetadata)
            .where(SecuritySecretMetadata.name == name)).first()

    def list(self, *, status: str | None = None, limit: int = 50,
             offset: int = 0) -> tuple[list, int]:
        stmt = select(SecuritySecretMetadata)
        count = select(func.count()).select_from(SecuritySecretMetadata)
        if status is not None:
            stmt = stmt.where(SecuritySecretMetadata.status == status)
            count = count.where(SecuritySecretMetadata.status == status)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(SecuritySecretMetadata.name).limit(limit).offset(offset)))
        return rows, total


class SecretAccessEventRepository(_Repo):
    model = SecuritySecretAccessEvent

    def list(self, *, secret_name: str | None = None, limit: int = 50,
             offset: int = 0) -> tuple[list, int]:
        stmt = select(SecuritySecretAccessEvent)
        count = select(func.count()).select_from(SecuritySecretAccessEvent)
        if secret_name is not None:
            stmt = stmt.where(SecuritySecretAccessEvent.secret_name == secret_name)
            count = count.where(SecuritySecretAccessEvent.secret_name == secret_name)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(SecuritySecretAccessEvent.created_at.desc())
            .limit(limit).offset(offset)))
        return rows, total


class EmergencyEventRepository(_Repo):
    model = SecurityEmergencyEvent

    def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list, int]:
        total = self.session.scalar(
            select(func.count()).select_from(SecurityEmergencyEvent)) or 0
        rows = list(self.session.scalars(
            select(SecurityEmergencyEvent)
            .order_by(SecurityEmergencyEvent.created_at.desc())
            .limit(limit).offset(offset)))
        return rows, total


class AlertRepository(_Repo):
    model = SecurityAlert

    def open_by_dedupe(self, dedupe_key: str) -> SecurityAlert | None:
        return self.session.scalars(
            select(SecurityAlert).where(
                SecurityAlert.dedupe_key == dedupe_key,
                SecurityAlert.status == "open")).first()

    def list(self, *, status: str | None = None, limit: int = 50,
             offset: int = 0) -> tuple[list, int]:
        stmt = select(SecurityAlert)
        count = select(func.count()).select_from(SecurityAlert)
        if status is not None:
            stmt = stmt.where(SecurityAlert.status == status)
            count = count.where(SecurityAlert.status == status)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(SecurityAlert.created_at.desc())
            .limit(limit).offset(offset)))
        return rows, total

    def count_open(self) -> int:
        return self.session.scalar(
            select(func.count()).select_from(SecurityAlert)
            .where(SecurityAlert.status == "open")) or 0


class IncidentRepository(_Repo):
    model = SecurityIncident

    def list(self, *, status: str | None = None, limit: int = 50,
             offset: int = 0) -> tuple[list, int]:
        stmt = select(SecurityIncident)
        count = select(func.count()).select_from(SecurityIncident)
        if status is not None:
            stmt = stmt.where(SecurityIncident.status == status)
            count = count.where(SecurityIncident.status == status)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(SecurityIncident.created_at.desc())
            .limit(limit).offset(offset)))
        return rows, total


class BackupRecordRepository(_Repo):
    model = SecurityBackupRecord

    def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list, int]:
        total = self.session.scalar(
            select(func.count()).select_from(SecurityBackupRecord)) or 0
        rows = list(self.session.scalars(
            select(SecurityBackupRecord)
            .order_by(SecurityBackupRecord.created_at.desc())
            .limit(limit).offset(offset)))
        return rows, total

    def latest(self) -> SecurityBackupRecord | None:
        return self.session.scalars(
            select(SecurityBackupRecord)
            .order_by(SecurityBackupRecord.created_at.desc())).first()


class ThreatRepository(_Repo):
    model = SecurityThreat

    def get_by_code(self, code: str) -> SecurityThreat | None:
        return self.session.scalars(
            select(SecurityThreat).where(SecurityThreat.code == code)).first()

    def list(self, *, limit: int = 100, offset: int = 0) -> tuple[list, int]:
        total = self.session.scalar(
            select(func.count()).select_from(SecurityThreat)) or 0
        rows = list(self.session.scalars(
            select(SecurityThreat).order_by(SecurityThreat.code)
            .limit(limit).offset(offset)))
        return rows, total


class AuditChainRepository(_Repo):
    model = SecurityAuditChain

    def last(self) -> SecurityAuditChain | None:
        return self.session.scalars(
            select(SecurityAuditChain)
            .order_by(SecurityAuditChain.seq.desc())).first()

    def count(self) -> int:
        return self.session.scalar(
            select(func.count()).select_from(SecurityAuditChain)) or 0

    def all_ordered(self) -> list:
        return list(self.session.scalars(
            select(SecurityAuditChain).order_by(SecurityAuditChain.seq)))

    def sealed_event_ids(self) -> set[str]:
        return set(self.session.scalars(
            select(SecurityAuditChain.audit_event_id)))


class LoginAttemptRepository(_Repo):
    model = SecurityLoginAttempt

    def recent_failures(self, username: str, since: dt.datetime) -> int:
        return self.session.scalar(
            select(func.count()).select_from(SecurityLoginAttempt).where(
                SecurityLoginAttempt.username == username,
                SecurityLoginAttempt.success == False,  # noqa: E712
                SecurityLoginAttempt.created_at >= since)) or 0


class AgentRestrictionRepository(_Repo):
    model = SecurityAgentRestriction

    def active_for(self, agent_id: str) -> SecurityAgentRestriction | None:
        return self.session.scalars(
            select(SecurityAgentRestriction).where(
                SecurityAgentRestriction.agent_id == agent_id,
                SecurityAgentRestriction.status == "active")).first()

    def list(self, *, status: str | None = None, limit: int = 50,
             offset: int = 0) -> tuple[list, int]:
        stmt = select(SecurityAgentRestriction)
        count = select(func.count()).select_from(SecurityAgentRestriction)
        if status is not None:
            stmt = stmt.where(SecurityAgentRestriction.status == status)
            count = count.where(SecurityAgentRestriction.status == status)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(SecurityAgentRestriction.created_at.desc())
            .limit(limit).offset(offset)))
        return rows, total


class DataClassificationRepository(_Repo):
    model = SecurityDataClassification

    def get_by_resource(self, resource_ref: str) -> SecurityDataClassification | None:
        return self.session.scalars(
            select(SecurityDataClassification)
            .where(SecurityDataClassification.resource_ref == resource_ref)).first()

    def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list, int]:
        total = self.session.scalar(
            select(func.count()).select_from(SecurityDataClassification)) or 0
        rows = list(self.session.scalars(
            select(SecurityDataClassification)
            .order_by(SecurityDataClassification.resource_ref)
            .limit(limit).offset(offset)))
        return rows, total


class DeviceRepository(_Repo):
    """Expansion Feature 1: the device registry store."""

    model = SecurityDevice

    def list_for(self, principal_type: str, principal_id: str) -> list:
        return list(self.session.scalars(
            select(SecurityDevice).where(
                SecurityDevice.principal_type == principal_type,
                SecurityDevice.principal_id == principal_id)
            .order_by(SecurityDevice.created_at)))

    def count_for(self, principal_type: str, principal_id: str, *,
                  trust_status: str | None = None) -> int:
        stmt = select(func.count()).select_from(SecurityDevice).where(
            SecurityDevice.principal_type == principal_type,
            SecurityDevice.principal_id == principal_id)
        if trust_status is not None:
            stmt = stmt.where(SecurityDevice.trust_status == trust_status)
        return self.session.scalar(stmt) or 0


class RecoveryCodeRepository(_Repo):
    """Expansion Feature 1: MFA recovery-code store. Hash-only rows;
    no method here returns or reconstructs a plaintext code."""

    model = SecurityRecoveryCode

    def list_for(self, principal_type: str, principal_id: str) -> list:
        return list(self.session.scalars(
            select(SecurityRecoveryCode).where(
                SecurityRecoveryCode.principal_type == principal_type,
                SecurityRecoveryCode.principal_id == principal_id)
            .order_by(SecurityRecoveryCode.created_at)))

    def unused_for(self, principal_type: str, principal_id: str) -> list:
        return list(self.session.scalars(
            select(SecurityRecoveryCode).where(
                SecurityRecoveryCode.principal_type == principal_type,
                SecurityRecoveryCode.principal_id == principal_id,
                SecurityRecoveryCode.status == "unused")
            .order_by(SecurityRecoveryCode.created_at)))


class SecurityAuditQuery:
    """Read-only queries over the P-01 ``audit_events`` table for the
    security views (§19). No writes: the audit trail's only writer
    remains the existing repositories/services."""

    def __init__(self, session: Session):
        self.session = session

    def list_events(self, *, actor_id: str | None = None,
                    action_prefix: str | None = None,
                    decision: str | None = None, limit: int = 50,
                    offset: int = 0) -> tuple[list, int]:
        stmt = select(AuditEvent)
        count = select(func.count()).select_from(AuditEvent)
        if actor_id is not None:
            stmt = stmt.where(AuditEvent.actor_id == actor_id)
            count = count.where(AuditEvent.actor_id == actor_id)
        if action_prefix is not None:
            stmt = stmt.where(AuditEvent.action.like(f"{action_prefix}%"))
            count = count.where(AuditEvent.action.like(f"{action_prefix}%"))
        if decision is not None:
            stmt = stmt.where(AuditEvent.decision == decision)
            count = count.where(AuditEvent.decision == decision)
        total = self.session.scalar(count) or 0
        rows = list(self.session.scalars(
            stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id)
            .limit(limit).offset(offset)))
        return rows, total

    def count_denials_since(self, since: dt.datetime,
                            actor_id: str | None = None) -> int:
        stmt = select(func.count()).select_from(AuditEvent).where(
            AuditEvent.decision == "deny", AuditEvent.created_at >= since)
        if actor_id is not None:
            stmt = stmt.where(AuditEvent.actor_id == actor_id)
        return self.session.scalar(stmt) or 0

    def denial_counts_by_actor(self, since: dt.datetime) -> list[tuple[str, str, int]]:
        rows = self.session.execute(
            select(AuditEvent.actor_type, AuditEvent.actor_id, func.count())
            .where(AuditEvent.decision == "deny", AuditEvent.created_at >= since)
            .group_by(AuditEvent.actor_type, AuditEvent.actor_id)).all()
        return [(t, i, c) for (t, i, c) in rows]

    def all_ordered(self) -> list:
        """Every audit event in chain order (created_at, id) — the
        canonical order the hash chain seals and verifies."""
        return list(self.session.scalars(
            select(AuditEvent).order_by(AuditEvent.created_at, AuditEvent.id)))
