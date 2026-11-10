"""Security monitoring and alerting (§19.4/§19.5).

The status aggregation here is the DATA behind the §24 Security
Command Center — the views themselves are P-11 (no frontend exists
in staging). Everything is read over existing stores: P-01 sessions,
agents, approvals and audit events, plus P-10's own tables.

Alerts are deterministic rules over the audit trail (never a
model): repeated denials per actor, repeated failed logins, and
non-owner policy-change attempts (recorded by the facade as denied
``security.policy_update`` audit events). Rules deduplicate against
open alerts so routine noise does not page the owner (§19.5).
"""
from __future__ import annotations

import datetime as dt

from ..database.models.base import utcnow
from ..database.models.core import Agent as AgentRow, AppSession, Approval
from ..database.models.security import SecurityAlert
from ..database.repositories.core import AuditRepository  # noqa: F401  (re-export convenience)
from ..database.repositories.security import (
    AlertRepository, BackupRecordRepository, LoginAttemptRepository,
    SecurityAuditQuery,
)
from ..permissions.models import Principal
from . import policy as P

ACTIVE_AGENT_STATES = {"initializing", "active", "idle", "busy", "degraded"}


def alert_to_dict(row: SecurityAlert) -> dict:
    return {
        "id": row.id, "rule": row.rule, "severity": row.severity,
        "subject": row.subject, "detail": row.detail, "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class SecurityMonitor:
    def __init__(self, session_factory, get_settings, chain_service):
        self._session_factory = session_factory
        self._get_settings = get_settings
        self._chain = chain_service

    # ------------------------------------------------------------- status
    def status(self) -> dict:
        """The §19.4/§24.1 overview as data (frontend is P-11)."""
        settings = self._get_settings()
        session = self._session_factory()
        try:
            from sqlalchemy import func, select
            now = utcnow()
            active_sessions = session.scalar(
                select(func.count()).select_from(AppSession).where(
                    AppSession.revoked == False,  # noqa: E712
                    AppSession.expires_at > now)) or 0
            active_agents = session.scalar(
                select(func.count()).select_from(AgentRow).where(
                    AgentRow.status.in_(ACTIVE_AGENT_STATES))) or 0
            pending_approvals = session.scalar(
                select(func.count()).select_from(Approval).where(
                    Approval.status == "pending")) or 0
            open_alerts = AlertRepository(session).count_open()
            latest_backup = BackupRecordRepository(session).latest()
            recent, _ = SecurityAuditQuery(session).list_events(
                action_prefix="security.", limit=10)
            recent_events = [{
                "action": e.action, "actor": f"{e.actor_type}:{e.actor_id}",
                "decision": e.decision, "reason": e.reason,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            } for e in recent]
        finally:
            session.close()
        return {
            "mode": settings.get("mode"),
            "financial_suspension": bool(settings.get("financial_suspension")),
            "active_sessions": active_sessions,
            "active_agents": active_agents,
            "pending_approvals": pending_approvals,
            "open_alerts": open_alerts,
            "recent_security_events": recent_events,
            "latest_backup": ({
                "id": latest_backup.id, "status": latest_backup.status,
                "created_at": latest_backup.created_at.isoformat()
                if latest_backup.created_at else None,
            } if latest_backup else None),
            "audit_chain": self._chain.verify(),
        }

    def list_events(self, *, actor_id: str | None = None,
                    action_prefix: str | None = None,
                    decision: str | None = None, limit: int = 50,
                    offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            rows, total = SecurityAuditQuery(session).list_events(
                actor_id=actor_id, action_prefix=action_prefix,
                decision=decision, limit=limit, offset=offset)
            return [{
                "id": e.id, "actor": f"{e.actor_type}:{e.actor_id}",
                "action": e.action, "target_type": e.target_type,
                "target_id": e.target_id, "decision": e.decision,
                "reason": e.reason, "correlation_id": e.correlation_id,
                "details": e.details or {},
                "created_at": e.created_at.isoformat() if e.created_at else None,
            } for e in rows], total
        finally:
            session.close()

    # ------------------------------------------------------------- alerts
    def evaluate_alerts(self, principal: Principal | None = None) -> list[dict]:
        """Run the deterministic alert rules once; returns the alerts
        created by this evaluation (already-open duplicates are not
        re-created)."""
        settings = self._get_settings()
        threshold = int(settings["alert_denial_threshold"])
        window = dt.timedelta(minutes=int(settings["alert_window_minutes"]))
        since = utcnow() - window
        created: list[dict] = []
        session = self._session_factory()
        try:
            repo = AlertRepository(session)
            query = SecurityAuditQuery(session)

            def raise_alert(rule: str, severity: str, subject: str,
                            detail: str, dedupe_key: str) -> None:
                if repo.open_by_dedupe(dedupe_key) is not None:
                    return
                row = repo.add(SecurityAlert(
                    rule=rule, severity=severity, subject=subject,
                    detail=detail, status="open", dedupe_key=dedupe_key))
                created.append(alert_to_dict(row))

            for actor_type, actor_id, count in query.denial_counts_by_actor(since):
                if count >= threshold:
                    raise_alert(
                        "repeated_denials", "warning",
                        f"{actor_type}:{actor_id}",
                        f"{count} denied authorization checks in the last "
                        f"{settings['alert_window_minutes']} minutes",
                        f"repeated_denials:{actor_type}:{actor_id}")
            policy_denials, _ = query.list_events(
                action_prefix="security.policy_update", decision="deny",
                limit=200)
            # Audit rows read back from SQLite carry naive datetimes;
            # normalise to aware UTC before comparing (the P-01
            # _expire_if_needed precedent).
            recent_policy = [
                e for e in policy_denials
                if e.created_at and (
                    e.created_at if e.created_at.tzinfo is not None
                    else e.created_at.replace(tzinfo=dt.timezone.utc)) >= since]
            for event in recent_policy:
                raise_alert(
                    "policy_change_attempt", "critical",
                    f"{event.actor_type}:{event.actor_id}",
                    "a non-owner attempted to change security policy "
                    "(denied and recorded)",
                    f"policy_change_attempt:{event.id}")
            from sqlalchemy import func, select
            from ..database.models.security import SecurityLoginAttempt
            failed = session.execute(
                select(SecurityLoginAttempt.username, func.count())
                .where(SecurityLoginAttempt.success == False,  # noqa: E712
                       SecurityLoginAttempt.created_at >= since)
                .group_by(SecurityLoginAttempt.username)).all()
            for username, count in failed:
                if count >= int(settings["login_max_failures"]):
                    raise_alert(
                        "repeated_failed_logins", "critical", username,
                        f"{count} failed login attempts in the last "
                        f"{settings['alert_window_minutes']} minutes",
                        f"repeated_failed_logins:{username}")
        finally:
            session.close()
        return created

    def list_alerts(self, *, status: str | None = None, limit: int = 50,
                    offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            rows, total = AlertRepository(session).list(
                status=status, limit=limit, offset=offset)
            return [alert_to_dict(r) for r in rows], total
        finally:
            session.close()

    def set_alert_status(self, principal: Principal, alert_id: str,
                         status: str) -> dict:
        if not P.is_owner(principal):
            from ..core.exceptions import PermissionDeniedError
            raise PermissionDeniedError("alert management is owner-only")
        if status not in ("acknowledged", "closed", "open"):
            from ..core.exceptions import ValidationError
            raise ValidationError(f"unknown alert status '{status}'")
        session = self._session_factory()
        try:
            repo = AlertRepository(session)
            row = repo.get(alert_id)
            if row is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError(f"alert {alert_id} not found")
            row.status = status
            return alert_to_dict(repo.save(row))
        finally:
            session.close()
