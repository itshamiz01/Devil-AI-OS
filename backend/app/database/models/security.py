"""SQLAlchemy models for the P-10 Security and Governance tables.

One additive migration creates these tables; no P-01..P-09 table is
altered. P-10 deliberately reuses the P-01 substrate instead of
duplicating it (P-10 prompt §2 rule 4, §25 read with the audit in
``docs/audits/P10_PRE_IMPLEMENTATION_AUDIT.md``):

- identities, sessions, roles and permission rules stay in P-01
  (``agents``, ``app_sessions``, ``permissions``) — there is no
  ``security_users`` / ``security_sessions`` / ``security_roles``
  table here;
- approvals stay in the P-01 ``approvals`` table — there is no
  ``security_approval_requests`` table here;
- the audit trail stays in the append-only P-01 ``audit_events``
  table — ``security_audit_chain`` only seals it with hashes;
- financial records stay in P-07 — **no table in this module has a
  money/amount column**: the financial guard records authorization
  decisions and the approval ids it consumed, never amounts as
  financial truth (amounts appear only inside broker/guard decision
  *context* JSON for binding verification, clearly labelled as
  request context, never as a ledger figure);
- secret VALUES are never stored: ``security_secret_metadata``
  holds names, backend references of the form ``env:NAME`` /
  ``windows-vault:NAME`` and lifecycle metadata only.

Append-only by convention: broker decisions, policy versions,
secret access events, emergency events, audit-chain seals, login
attempts and threat-register history expose no update/delete in
their repositories (status transitions on capabilities, alerts,
incidents, restrictions and secret metadata are the governed
exceptions, each recorded as a new audit event).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class SecurityCapability(TimestampMixin, Base):
    """A task-scoped capability token (§7.2). Narrower than a P-01
    permission grant: it binds one holder to one permission on one
    resource (optionally one business / one task), expires, and is
    revocable. Owner-only permissions can never be issued as
    capabilities to agents (delegation rules live in the broker)."""

    __tablename__ = "security_capabilities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    holder_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    holder_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(100), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(300), nullable=True)
    business_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issued_by: Mapped[str] = mapped_column(String(232), nullable=False)  # type:id
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(232), nullable=True)


class SecurityBrokerDecision(TimestampMixin, Base):
    """One Permission Broker authorization decision (§7.1). This is a
    domain ledger of broker requests (tool, operation, target, risk,
    gates evaluated); the cross-system audit trail remains the P-01
    ``audit_events`` table, which also receives a
    ``security.broker_decision`` entry per row here."""

    __tablename__ = "security_broker_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    principal_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    principal_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(300), nullable=True)
    business_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk_level: Mapped[int] = mapped_column(Integer, nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    gates: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    capability_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SecurityPolicyVersion(TimestampMixin, Base):
    """One versioned change to the owner-governed security policy
    (``system_config`` key ``security.settings``, §23.3). Stores the
    full previous and new settings documents so rollback is a
    restore of a recorded version, never a reconstruction."""

    __tablename__ = "security_policy_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    previous_settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    new_settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    changed_keys: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    actor: Mapped[str] = mapped_column(String(232), nullable=False)  # type:id
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SecuritySecretMetadata(TimestampMixin, Base):
    """Secret registry entry (§9): metadata ONLY. ``reference`` is a
    broker reference (``env:NAME`` or ``windows-vault:NAME``), never
    a value. Classification follows §4.2 levels 1–5."""

    __tablename__ = "security_secret_metadata"
    __table_args__ = (
        UniqueConstraint("name", name="uq_security_secret_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    reference: Mapped[str] = mapped_column(String(300), nullable=False)
    backend: Mapped[str] = mapped_column(String(40), nullable=False)  # env | windows-vault
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True, nullable=False)
    # active | rotation_due | revoked | expired
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_rotated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(232), nullable=False)


class SecuritySecretAccessEvent(TimestampMixin, Base):
    """Value-free secret access event (§9.5). Records WHO asked for
    WHICH named secret for WHAT purpose and the outcome — never the
    reference target beyond the backend type, never any value."""

    __tablename__ = "security_secret_access_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    secret_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(232), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(300), nullable=True)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    # granted | denied | unavailable | not_found
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class SecurityEmergencyEvent(TimestampMixin, Base):
    """One security-mode transition (§20). The current mode itself
    lives in owner-governed ``security.settings``; this table is the
    append-only history of who changed it and why."""

    __tablename__ = "security_emergency_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    from_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    to_mode: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    financial_suspension: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    actor: Mapped[str] = mapped_column(String(232), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class SecurityAlert(TimestampMixin, Base):
    """A deterministic monitoring alert (§19.5). Generated by rules
    over the audit trail — never by a model."""

    __tablename__ = "security_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    rule: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(24), default="warning", nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True, nullable=False)
    # open | acknowledged | closed
    dedupe_key: Mapped[str] = mapped_column(String(300), nullable=False, index=True)


class SecurityIncident(TimestampMixin, Base):
    """An incident record (§19/§30 playbook). Owner-managed."""

    __tablename__ = "security_incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(24), default="medium", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), default="open", index=True, nullable=False)
    # open | investigating | contained | resolved | closed
    related_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_by: Mapped[str] = mapped_column(String(232), nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)


class SecurityBackupRecord(TimestampMixin, Base):
    """A backup manifest + verification record (§20.4). The manifest
    hashes the backup artifact; verification re-opens the artifact
    and re-checks it — a backup that was never verified is reported
    as such, never as a recovery guarantee."""

    __tablename__ = "security_backup_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    kind: Mapped[str] = mapped_column(String(40), default="database", nullable=False)
    location: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    table_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="created", index=True, nullable=False)
    # created | verified | verify_failed | requires_owner_configuration
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(232), nullable=False)
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SecurityThreat(TimestampMixin, Base):
    """One living threat-register entry (§4.3, STRIDE-informed)."""

    __tablename__ = "security_threat_register"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(24), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    entry_point: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    affected_assets: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    likelihood: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    impact: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), default="medium", nullable=False, index=True)
    preventive_controls: Mapped[str] = mapped_column(Text, nullable=False, default="")
    detection_controls: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recovery_procedure: Mapped[str] = mapped_column(Text, nullable=False, default="")
    verification_test: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), default="mitigated", nullable=False)
    # mitigated | partially_mitigated | accepted_risk | open


class SecurityAuditChain(TimestampMixin, Base):
    """One hash-chain seal over a P-01 ``audit_events`` row (§19.3).

    ``entry_hash = sha256(previous_hash + canonical(event fields))``.
    The chain makes later modification or deletion of sealed audit
    rows DETECTABLE. It is tamper-evidence, not tamper-proofing —
    an attacker with raw database write access could rewrite the
    chain too; protected storage remains an owner concern (the
    prompt's own §19.3 caveat)."""

    __tablename__ = "security_audit_chain"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    audit_event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class SecurityLoginAttempt(TimestampMixin, Base):
    """One login attempt outcome (§5.2 throttling evidence). Stores
    the username and success flag only — never the password, never
    a token."""

    __tablename__ = "security_login_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    username: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    throttled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SecurityAgentRestriction(TimestampMixin, Base):
    """A security-layer restriction overlay for one agent (§15.4).
    The P-04 factory owns the agent lifecycle; this overlay is what
    the P-10 broker consults at authorization time. An active row
    denies the agent at the broker regardless of grants, without
    editing factory state."""

    __tablename__ = "security_agent_restrictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    restriction: Mapped[str] = mapped_column(String(40), default="suspended", nullable=False)
    # suspended | read_only
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True, nullable=False)
    # active | released
    imposed_by: Mapped[str] = mapped_column(String(232), nullable=False)
    released_by: Mapped[str | None] = mapped_column(String(232), nullable=True)


class SecurityDataClassification(TimestampMixin, Base):
    """Classification registry entry for a protected resource
    (§17.1/§4.2): levels 1 (public) … 5 (critical)."""

    __tablename__ = "security_data_classifications"
    __table_args__ = (
        UniqueConstraint("resource_ref", name="uq_security_classification_resource"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    resource_ref: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    classification: Mapped[int] = mapped_column(Integer, nullable=False)
    business_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    owner_principal: Mapped[str] = mapped_column(String(232), nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class SecurityDevice(TimestampMixin, Base):
    """One registered device (Expansion Feature 1: Identity &
    Device Security).

    Device identity is a server-issued credential, NOT a hardware
    claim: at enrolment the server generates a random device
    secret, returns it exactly once, and stores only its SHA-256
    hash here — the same pattern P-01 uses for session tokens.
    ``label`` / ``platform`` / ``device_name`` are owner-supplied
    descriptive metadata, explicitly self-declared and never used
    as identity evidence (the expansion pack forbids relying on
    easily spoofed hardware identifiers).

    Trust lifecycle: ``untrusted`` (at enrolment) -> ``trusted``
    (explicit owner action) -> ``revoked`` (terminal). Only a
    trusted device may bind a session (``app_sessions.device_id``);
    untrust, revocation and secret rotation revoke every bound
    session. No column in this table holds a money value or a
    secret value — ``secret_hash`` is a one-way hash.
    """

    __tablename__ = "security_devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    principal_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    principal_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    device_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    trust_status: Mapped[str] = mapped_column(
        String(24), default="untrusted", index=True, nullable=False)
    # untrusted | trusted | revoked
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(232), nullable=True)


class SecurityRecoveryCode(TimestampMixin, Base):
    """One MFA recovery code (Expansion Feature 1, closing the
    P-10 gap "recovery codes NOT IMPLEMENTED").

    Codes are generated in batches for the owner identity, shown
    exactly once at generation, and stored ONLY as scrypt hashes
    (P-01's ``hash_password`` — a slow hash, because a recovery
    code carries less entropy than a session token). A code is
    single-use; regenerating a batch flips every still-unused
    code of earlier batches to ``invalidated`` (rows are kept so
    the audit story survives). No plaintext code exists anywhere
    in the database.
    """

    __tablename__ = "security_recovery_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    principal_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    principal_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="unused", index=True, nullable=False)
    # unused | used | invalidated
    used_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
