"""P-11 Command Center aggregation service.

READ-ONLY over the authoritative records of P-01–P-10, with exactly two
exceptions, both dashboard-owned (§25): principal preferences and
notification read/dismiss state. Every figure here is produced by the
engine that owns it or counted directly from its tables:

* money comes ONLY from P-07 ``FinancialService.consolidated()`` (verbatim);
* approvals come from P-01 ``ApprovalService``;
* security posture comes from P-10's monitor status;
* system health comes from P-01's ``SystemMonitor``.

Nothing is recomputed with different definitions, nothing is invented, and
unavailable sources surface as explicit ``unavailable`` states — never as
zeros dressed up as measurements.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, or_, select

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models import (
    Agent,
    AgentCreationRequest,
    Approval,
    AuditEvent,
    Business,
    BusinessDecision,
    BusinessHealthSnapshot,
    DashboardNotificationState,
    DashboardPreference,
    EventDeadLetter,
    ExecutionRequest,
    FinancialAlert,
    LearningRecord,
    MemoryContradiction,
    MemoryRecord,
    Opportunity,
    SecurityAlert,
    SecurityIncident,
    SpendingRequest,
    SystemEvent,
    Task,
)
from ..database.models.base import utcnow
from ..permissions.models import Principal

SEVERITY_ORDER = {"critical": 0, "high": 1, "error": 2, "medium": 3,
                  "warning": 4, "low": 5, "info": 6}

# Notification categories that must never be silently dismissed (§5.4):
# critical security and financial alerts stay visible until handled at
# their source (alert acknowledged / approval decided), not hidden here.
NON_DISMISSIBLE_KINDS = {"security_alert", "financial_alert"}

DEFAULT_PREFERENCES = {
    "sidebar_collapsed": False,
    "default_view": "overview",
    "timezone": "UTC",
    "currency": "INR",
    "density": "comfortable",
    "reduce_motion": False,
}


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def _counts(session, model, column) -> dict[str, int]:
    rows = session.execute(
        select(column, func.count()).group_by(column)).all()
    return {str(k): int(v) for k, v in rows}


class DashboardService:
    def __init__(self, application):
        self.app = application

    # ------------------------------------------------------------ internals
    def _session(self):
        return self.app.session_factory()

    def _measured(self) -> str:
        return utcnow().isoformat()

    # ------------------------------------------------------------- overview
    def overview(self, currency: str = "INR") -> dict:
        app = self.app
        measured = self._measured()
        lifecycle = app.lifecycle.state.value
        monitor_status = app.monitor.status(lifecycle)
        security = app.security.monitor.status()
        sec_mode = security.get("mode", "normal")
        session = self._session()
        try:
            business_counts = _counts(session, Business, Business.status)
            agent_counts = _counts(session, Agent, Agent.status)
            opp_counts = _counts(session, Opportunity, Opportunity.status)
            task_counts = _counts(session, Task, Task.status)
            pending_approvals = session.scalar(
                select(func.count()).select_from(Approval)
                .where(Approval.status == "pending")) or 0
            open_sec_alerts = session.scalar(
                select(func.count()).select_from(SecurityAlert)
                .where(SecurityAlert.status == "open")) or 0
            critical_alerts = session.scalar(
                select(func.count()).select_from(SecurityAlert).where(
                    SecurityAlert.status == "open",
                    SecurityAlert.severity == "critical")) or 0
        finally:
            session.close()

        fin = app.financial.consolidated(currency)
        totals = fin["totals"]

        if sec_mode not in ("normal",):
            operating_state = sec_mode  # e.g. safe_mode / emergency (P-10 truth)
        elif lifecycle != "ready":
            operating_state = lifecycle
        elif monitor_status.get("threshold_violations"):
            operating_state = "operational_with_warnings"
        else:
            operating_state = "operational"

        def metric(key, label, value, source, note=None, period="current",
                   unit=None, state="ok"):
            return {"key": key, "label": label, "value": value, "unit": unit,
                    "period": period, "source": source, "note": note,
                    "state": state, "measured_at": measured}

        active_business_states = {"OPERATIONAL", "LAUNCHED", "ACTIVE"}
        active_agent_states = {"active", "running", "busy"}
        running_task_states = {"running", "in_progress"}
        validated_opp_states = {"VALIDATED", "validated"}
        kpis = [
            metric("active_businesses", "Active businesses",
                   sum(v for k, v in business_counts.items()
                       if k in active_business_states),
                   "P-06 business registry (businesses by status)",
                   note=f"of {sum(business_counts.values())} total businesses"),
            metric("validated_opportunities", "Validated opportunities",
                   sum(v for k, v in opp_counts.items()
                       if k in validated_opp_states),
                   "P-03 opportunity registry",
                   note=f"of {sum(opp_counts.values())} discovered"),
            metric("active_agents", "Active agents",
                   sum(v for k, v in agent_counts.items()
                       if k.lower() in active_agent_states),
                   "P-04 agent factory (agents by status)",
                   note=f"of {sum(agent_counts.values())} registered"),
            metric("running_tasks", "Running tasks",
                   sum(v for k, v in task_counts.items()
                       if k.lower() in running_task_states),
                   "P-01 task manager",
                   note=f"queue depth {monitor_status.get('queue', {}).get('depth', 0)}"),
            metric("collected_revenue", "Collected revenue",
                   totals["net_collected_minor"],
                   "P-07 consolidated (verified collected only)",
                   note="net collected, minor units; forecasts excluded",
                   unit=currency),
            metric("actual_expenses", "Actual expenses", totals["expenses_minor"],
                   "P-07 consolidated (paid expenses only)",
                   note="minor units", unit=currency),
            metric("net_profit", "Net profit / loss", totals["net_profit_minor"],
                   "P-07 consolidated (collected − paid expenses)",
                   note="actuals only — never projected profit", unit=currency),
            metric("available_cash", "Available cash", None,
                   "P-07 per-business available-cash endpoints",
                   note="portfolio available cash is not consolidated by P-07; "
                        "see Finance view per business",
                   state="unavailable"),
        ]
        return {
            "operating_state": operating_state,
            "lifecycle_state": lifecycle,
            "mode": app.settings.mode,
            "security_mode": sec_mode,
            "financial_suspension": security.get("financial_suspension", False),
            "database_healthy": monitor_status.get("database_healthy"),
            "threshold_violations": monitor_status.get("threshold_violations", []),
            "queue": monitor_status.get("queue", {}),
            "counts": {
                "businesses_total": sum(business_counts.values()),
                "businesses_by_status": business_counts,
                "agents_total": sum(agent_counts.values()),
                "agents_by_status": agent_counts,
                "opportunities_total": sum(opp_counts.values()),
                "opportunities_by_status": opp_counts,
                "tasks_by_status": task_counts,
                "pending_approvals": int(pending_approvals),
                "open_security_alerts": int(open_sec_alerts),
                "critical_alerts": int(critical_alerts),
            },
            "kpis": kpis,
            "finance": {"currency": currency, "totals": totals,
                        "businesses": fin["businesses"],
                        "internal_transfers_excluded":
                            fin["internal_transfers_excluded"],
                        "note": fin["note"], "source": "P-07 consolidated"},
            "measured_at": measured,
        }

    # -------------------------------------------------------- system health
    async def system_health(self) -> dict:
        app = self.app
        measured = self._measured()
        lifecycle = app.lifecycle.state.value
        db_ok = app.monitor.database_healthy()
        violations = app.monitor.threshold_violations()
        # Provider truth from the same call as GET /models/status (P-02).
        try:
            models = await app.intelligence.models_status()
        except Exception:
            models = None
        security = app.security.monitor.status()
        session = self._session()
        try:
            memory_indexed = session.scalar(
                select(func.count()).select_from(MemoryRecord)) or 0
            exec_running = session.scalar(
                select(func.count()).select_from(ExecutionRequest)
                .where(ExecutionRequest.status == "RUNNING")) or 0
            # P-14 Stage B (DEF-I4): dead-letter depth is part of the
            # §14 monitoring surface — failed event deliveries are
            # visible, not silent.
            dead_letters = session.scalar(
                select(func.count()).select_from(EventDeadLetter)) or 0
            browser_active = None
        finally:
            session.close()

        def check(key, label, state, detail, source):
            return {"key": key, "label": label, "state": state,
                    "detail": detail, "source": source, "measured_at": measured}

        providers = (models or {}).get("providers", {}) if models else {}
        ollama = providers.get("ollama", {})
        cloud = providers.get("cloud", {})
        checks = [
            check("backend", "Backend", "ok" if lifecycle == "ready" else "degraded",
                  f"lifecycle state: {lifecycle}", "P-01 lifecycle manager"),
            check("database", "Database", "ok" if db_ok else "down",
                  "connectivity check passed" if db_ok else "connectivity check FAILED",
                  "P-01 system monitor"),
            check("ai_provider", "AI providers",
                  "ok" if (ollama.get("available") or cloud.get("available"))
                  else "unavailable",
                  f"ollama: {ollama.get('detail', 'not probed')}; "
                  f"cloud: {cloud.get('detail', 'not probed')}",
                  "P-02 model router (deterministic planner remains available)"),
            check("task_queue", "Task queue",
                  "degraded" if violations else "ok",
                  f"depth {app.monitor.status(lifecycle).get('queue', {}).get('depth', 0)}"
                  + (f"; threshold violations: {len(violations)}" if violations else ""),
                  "P-01 task manager"),
            check("memory_store", "Memory system", "ok",
                  f"{memory_indexed} memory records (SQLite vector adapter, "
                  "local-hash-v1 — P-09)", "P-09 memory engine"),
            check("browser_automation", "Browser automation", "unavailable",
                  "P-05 browser adapter is partial (read path); no live browser "
                  "session telemetry exists", "P-05 execution engine"),
            check("gpu", "GPU", "unavailable",
                  "no GPU telemetry source exists in the backend, and none is "
                  "invented; the target machine's Quadro K1100M is below "
                  "Ollama's minimum compute capability, so inference is "
                  "CPU-only (P-04 hardware verdict)", "not measured"),
            check("security", "Security subsystem",
                  "ok" if security.get("mode") == "normal" else "degraded",
                  f"mode {security.get('mode')}; financial suspension "
                  f"{security.get('financial_suspension')}", "P-10 security monitor"),
            check("execution", "Execution engine", "ok",
                  f"{exec_running} execution requests currently RUNNING",
                  "P-05 execution requests"),
            check("workers", "Background workers", "ok" if lifecycle == "ready"
                  else "degraded",
                  "in-process task manager workers (no separate worker fleet "
                  "is configured)", "P-01 task manager"),
        ]
        # P-14 Stage B (DEF-A3): complete the §14 monitoring surface.
        # Resource utilization comes from the same P-01 monitor the
        # Operations view uses; per-module health is derived
        # mechanically from the checks above — each check names its
        # owning module in its source, and a module's state is the
        # worst state among its own checks (derived, never invented).
        resources = app.monitor.resources()
        _rank = {"ok": 0, "unavailable": 1, "degraded": 2, "down": 3}
        _modules: dict[str, dict] = {}
        for c in checks:
            token = next((t for t in c["source"].replace("(", " ").split()
                          if t.startswith("P-") and t[2:].rstrip(")").isdigit()),
                         "platform")
            entry = _modules.setdefault(
                token, {"module": token, "state": "ok", "checks": []})
            entry["checks"].append(c["key"])
            if _rank.get(c["state"], 0) > _rank.get(entry["state"], 0):
                entry["state"] = c["state"]
        return {"checks": checks, "measured_at": measured,
                "resources": {
                    "cpu_percent": resources.get("cpu_percent"),
                    "memory_percent": resources.get("memory_percent"),
                    "disk_percent": resources.get("disk_percent"),
                    "threshold_violations": violations,
                    "source": "P-01 system monitor"},
                "modules": [_modules[k] for k in sorted(_modules)],
                "event_dead_letters": int(dead_letters),
                "overall": "down" if any(c["state"] == "down" for c in checks)
                else ("degraded" if any(c["state"] in ("degraded", "unavailable")
                                        for c in checks) else "ok")}

    # ------------------------------------------------------------- activity
    def activity(self, limit: int = 50) -> dict:
        session = self._session()
        try:
            rows = session.execute(
                select(SystemEvent).order_by(SystemEvent.created_at.desc())
                .limit(limit)).scalars().all()
            items = [{
                "event_id": e.event_id, "event_type": e.event_type,
                "source": e.source, "severity": e.severity,
                "task_id": e.task_id, "payload": e.payload,
                "created_at": _iso(e.created_at),
                "link": (f"#/execution" if e.task_id else None),
            } for e in rows]
            total = session.scalar(select(func.count()).select_from(SystemEvent)) or 0
        finally:
            session.close()
        return {"items": items, "total": int(total), "measured_at": self._measured(),
                "note": "persisted critical events only (P-01 event persistence); "
                        "the full audit trail lives under Security → Audit"}

    # ------------------------------------------------------------ attention
    def attention(self) -> dict:
        app = self.app
        session = self._session()
        items: list[dict] = []
        try:
            for a in session.execute(
                    select(Approval).where(Approval.status == "pending")
                    .order_by(Approval.created_at.asc()).limit(50)).scalars():
                items.append({
                    "kind": "approval", "severity": a.risk_classification,
                    "title": f"Approval pending: {a.action}",
                    "detail": a.reason or f"requested by "
                              f"{a.requesting_principal_type}:{a.requesting_principal_id}",
                    "ref_id": a.id, "link": "#/approvals",
                    "created_at": _iso(a.created_at)})
            failed_cutoff = utcnow() - dt.timedelta(hours=24)
            for t in session.execute(
                    select(Task).where(Task.status == "failed",
                                       Task.updated_at >= failed_cutoff)
                    .order_by(Task.updated_at.desc()).limit(50)).scalars():
                items.append({
                    "kind": "failed_task",
                    "severity": "high" if t.essential else "medium",
                    "title": f"Task failed: {t.name}",
                    "detail": (t.error or {}).get("message", "see task detail")
                    if isinstance(t.error, dict) else "see task detail",
                    "ref_id": t.id, "link": "#/execution",
                    "created_at": _iso(t.updated_at)})
            for snap in session.execute(
                    select(BusinessHealthSnapshot)
                    .order_by(BusinessHealthSnapshot.created_at.desc())
                    .limit(200)).scalars():
                if snap.classification in ("AT_RISK", "CRITICAL", "FAILING"):
                    items.append({
                        "kind": "survival_warning",
                        "severity": "critical" if snap.classification == "CRITICAL"
                        else "high",
                        "title": f"Business survival: {snap.classification}",
                        "detail": snap.explanation or snap.overlay_state,
                        "ref_id": snap.business_id, "link": "#/survival",
                        "created_at": _iso(snap.created_at)})
            for fa in session.execute(
                    select(FinancialAlert).where(FinancialAlert.status == "open")
                    .order_by(FinancialAlert.created_at.desc())
                    .limit(50)).scalars():
                items.append({
                    "kind": "financial_alert", "severity": fa.severity,
                    "title": fa.title, "detail": fa.recommended_action,
                    "ref_id": fa.id, "link": "#/finance",
                    "created_at": _iso(fa.created_at)})
            for sa in session.execute(
                    select(SecurityAlert).where(SecurityAlert.status == "open")
                    .order_by(SecurityAlert.created_at.desc())
                    .limit(50)).scalars():
                items.append({
                    "kind": "security_alert", "severity": sa.severity,
                    "title": f"Security alert: {sa.subject}",
                    "detail": sa.detail, "ref_id": sa.id, "link": "#/security",
                    "created_at": _iso(sa.created_at)})
            for inc in session.execute(
                    select(SecurityIncident).where(
                        SecurityIncident.status.in_(("open", "investigating")))
                    .order_by(SecurityIncident.created_at.desc())
                    .limit(50)).scalars():
                items.append({
                    "kind": "security_incident", "severity": inc.severity,
                    "title": f"Incident: {inc.title}",
                    "detail": inc.description, "ref_id": inc.id,
                    "link": "#/security", "created_at": _iso(inc.created_at)})
        finally:
            session.close()
        items.sort(key=lambda i: (SEVERITY_ORDER.get(i["severity"], 6),
                                  i["created_at"] or ""))
        return {"items": items, "total": len(items),
                "measured_at": self._measured()}

    # ------------------------------------------------------- module summary
    def agents_summary(self) -> dict:
        session = self._session()
        try:
            by_status = _counts(session, Agent, Agent.status)
            total = sum(by_status.values())
            requests = _counts(session, AgentCreationRequest,
                               AgentCreationRequest.decision)
        finally:
            session.close()
        return {"total": total, "by_status": by_status,
                "creation_requests_by_status": requests,
                "source": "P-04 agent factory tables", "measured_at": self._measured()}

    def businesses_summary(self) -> dict:
        session = self._session()
        try:
            by_status = _counts(session, Business, Business.status)
            rows = session.execute(
                select(Business).order_by(Business.created_at.desc())
                .limit(200)).scalars().all()
            businesses = [{
                "id": b.id, "name": b.name, "category": b.category,
                "status": b.status, "risk_classification": b.risk_classification,
                "is_fixture": b.is_fixture, "deployment_state": b.deployment_state,
                "public_availability": b.public_availability,
                "created_at": _iso(b.created_at)} for b in rows]
        finally:
            session.close()
        return {"total": sum(by_status.values()), "by_status": by_status,
                "businesses": businesses, "source": "P-06 business registry",
                "measured_at": self._measured(),
                "note": "financial values per business live in the Finance view "
                        "(P-07 authoritative records only)"}

    def opportunities_summary(self) -> dict:
        session = self._session()
        try:
            by_status = _counts(session, Opportunity, Opportunity.status)
        finally:
            session.close()
        return {"total": sum(by_status.values()), "by_status": by_status,
                "source": "P-03 opportunity registry",
                "measured_at": self._measured()}

    def execution_summary(self) -> dict:
        session = self._session()
        try:
            requests = _counts(session, ExecutionRequest, ExecutionRequest.status)
            tasks = _counts(session, Task, Task.status)
        finally:
            session.close()
        return {"requests_by_status": requests, "tasks_by_status": tasks,
                "source": "P-05 execution + P-01 task tables",
                "measured_at": self._measured()}

    def finance_summary(self, currency: str = "INR") -> dict:
        fin = self.app.financial.consolidated(currency)
        session = self._session()
        try:
            open_alerts = session.scalar(
                select(func.count()).select_from(FinancialAlert)
                .where(FinancialAlert.status == "open")) or 0
            spending = _counts(session, SpendingRequest, SpendingRequest.status)
        finally:
            session.close()
        return {**fin, "open_alerts": int(open_alerts),
                "spending_requests_by_status": spending,
                "source": "P-07 consolidated (verbatim)",
                "measured_at": self._measured()}

    def security_summary(self) -> dict:
        status = self.app.security.monitor.status()
        session = self._session()
        try:
            incidents = _counts(session, SecurityIncident, SecurityIncident.status)
            alerts = _counts(session, SecurityAlert, SecurityAlert.status)
        finally:
            session.close()
        return {**status, "incidents_by_status": incidents,
                "alerts_by_status": alerts,
                "source": "P-10 security monitor + tables",
                "measured_at": self._measured()}

    def approvals_summary(self) -> dict:
        _, core_total = self.app.approvals.list("pending", 1, 0)
        session = self._session()
        try:
            # AgentCreationRequest has no status column: a request is
            # pending until `decision` is set (P-04); approval_status
            # tracks any linked core approval.
            by_approval_status = _counts(
                session, AgentCreationRequest,
                AgentCreationRequest.approval_status)
            creation_pending = session.scalar(
                select(func.count()).select_from(AgentCreationRequest)
                .where(AgentCreationRequest.decision.is_(None))) or 0
            spending = _counts(session, SpendingRequest, SpendingRequest.status)
            fin_alerts = session.scalar(
                select(func.count()).select_from(FinancialAlert)
                .where(FinancialAlert.status == "open")) or 0
        finally:
            session.close()
        pending_markers = ("pending", "PENDING", "PENDING_APPROVAL",
                           "AWAITING_APPROVAL", "awaiting_approval")
        return {
            "core_pending": core_total,
            "agent_creation_by_approval_status": by_approval_status,
            "agent_creation_pending": int(creation_pending),
            "spending_requests_by_status": spending,
            "spending_pending": sum(
                v for k, v in spending.items() if k in pending_markers),
            "financial_open_alerts": int(fin_alerts),
            "source": "P-01 approvals + P-04 creation requests + P-07 spending "
                      "requests (counts only; decisions happen on the owning "
                      "endpoints)", "measured_at": self._measured()}

    # ---------------------------------------------------------- notifications
    def _derive_notifications(self, session) -> list[dict]:
        notes: list[dict] = []
        for a in session.execute(
                select(Approval).where(Approval.status == "pending")
                .order_by(Approval.created_at.desc()).limit(50)).scalars():
            notes.append({
                "id": f"approval:{a.id}", "kind": "approval",
                "severity": a.risk_classification,
                "title": f"Approval requested: {a.action}",
                "detail": a.reason or "", "link": "#/approvals",
                "dismissible": True, "created_at": _iso(a.created_at)})
        for sa in session.execute(
                select(SecurityAlert).where(SecurityAlert.status == "open")
                .order_by(SecurityAlert.created_at.desc()).limit(50)).scalars():
            notes.append({
                "id": f"security_alert:{sa.id}", "kind": "security_alert",
                "severity": sa.severity, "title": f"Security: {sa.subject}",
                "detail": sa.detail, "link": "#/security",
                "dismissible": sa.severity not in ("critical",),
                "created_at": _iso(sa.created_at)})
        for fa in session.execute(
                select(FinancialAlert).where(FinancialAlert.status == "open")
                .order_by(FinancialAlert.created_at.desc()).limit(50)).scalars():
            notes.append({
                "id": f"financial_alert:{fa.id}", "kind": "financial_alert",
                "severity": fa.severity, "title": fa.title,
                "detail": fa.recommended_action, "link": "#/finance",
                "dismissible": fa.severity not in ("critical",),
                "created_at": _iso(fa.created_at)})
        for t in session.execute(
                select(Task).where(Task.status == "failed")
                .order_by(Task.updated_at.desc()).limit(50)).scalars():
            notes.append({
                "id": f"task_failed:{t.id}", "kind": "task_failure",
                "severity": "high" if t.essential else "medium",
                "title": f"Task failed: {t.name}", "detail": "",
                "link": "#/execution", "dismissible": True,
                "created_at": _iso(t.updated_at)})
        for e in session.execute(
                select(SystemEvent).where(
                    SystemEvent.severity.in_(("warning", "error", "critical")))
                .order_by(SystemEvent.created_at.desc()).limit(50)).scalars():
            notes.append({
                "id": f"event:{e.event_id}", "kind": "system_event",
                "severity": e.severity, "title": f"{e.event_type}",
                "detail": f"source: {e.source}", "link": "#/operations",
                "dismissible": e.severity != "critical",
                "created_at": _iso(e.created_at)})
        notes.sort(key=lambda n: (SEVERITY_ORDER.get(n["severity"], 6),
                                  -(dt.datetime.fromisoformat(n["created_at"])
                                    .timestamp() if n["created_at"] else 0)))
        return notes

    def notifications(self, principal: Principal) -> dict:
        key = f"{principal.type.value}:{principal.id}"
        session = self._session()
        try:
            derived = self._derive_notifications(session)
            states = {s.notification_id: s for s in session.execute(
                select(DashboardNotificationState).where(
                    DashboardNotificationState.principal_key == key)).scalars()}
            items = []
            unread = 0
            for n in derived:
                st = states.get(n["id"])
                if st and st.is_dismissed:
                    continue
                is_read = bool(st and st.is_read)
                if not is_read:
                    unread += 1
                items.append({**n, "is_read": is_read})
            return {"items": items, "unread": unread, "total": len(items),
                    "measured_at": self._measured(),
                    "note": "derived live from approvals, alerts, failed tasks "
                            "and persisted events; only your read/dismiss "
                            "state is stored"}
        finally:
            session.close()

    def _notification_or_404(self, session, notification_id: str) -> dict:
        for n in self._derive_notifications(session):
            if n["id"] == notification_id:
                return n
        raise NotFoundError(f"notification {notification_id} not found "
                            "(it may already be resolved at its source)")

    def _state_for(self, session, principal: Principal,
                   notification_id: str) -> DashboardNotificationState:
        key = f"{principal.type.value}:{principal.id}"
        row = session.execute(
            select(DashboardNotificationState).where(
                DashboardNotificationState.principal_key == key,
                DashboardNotificationState.notification_id == notification_id)
        ).scalar_one_or_none()
        if row is None:
            row = DashboardNotificationState(
                principal_key=key, notification_id=notification_id)
            session.add(row)
        return row

    def mark_notification_read(self, principal: Principal,
                               notification_id: str) -> dict:
        session = self._session()
        try:
            self._notification_or_404(session, notification_id)
            row = self._state_for(session, principal, notification_id)
            row.mark_read()
            session.commit()
            return {"notification_id": notification_id, "is_read": True}
        finally:
            session.close()

    def dismiss_notification(self, principal: Principal,
                             notification_id: str) -> dict:
        session = self._session()
        try:
            note = self._notification_or_404(session, notification_id)
            if note["kind"] in NON_DISMISSIBLE_KINDS and \
                    note["severity"] == "critical":
                raise ValidationError(
                    "critical security/financial alerts cannot be dismissed "
                    "from the notification centre; handle them at their "
                    "source (Security / Finance) so the underlying condition "
                    "is resolved, per §5.4")
            if not note["dismissible"]:
                raise ValidationError(
                    "this notification cannot be dismissed; resolve it at "
                    "its source")
            row = self._state_for(session, principal, notification_id)
            row.mark_dismissed()
            row.mark_read()
            session.commit()
            return {"notification_id": notification_id, "is_dismissed": True}
        finally:
            session.close()

    # ---------------------------------------------------------------- search
    def search(self, query: str, per_type: int = 8) -> dict:
        q = query.strip()
        if len(q) < 2:
            raise ValidationError("search query must be at least 2 characters")
        like = f"%{q}%"
        session = self._session()
        try:
            def hits(model, fields, kind, label_of, link_of, extra=None):
                conds = [getattr(model, f).ilike(like) for f in fields]
                if extra is not None:
                    conds.append(extra)
                rows = session.execute(
                    select(model).where(or_(*conds))
                    .order_by(model.created_at.desc()).limit(per_type)).scalars()
                return [{"kind": kind, "id": r.id, "label": label_of(r),
                         "detail": "", "link": link_of(r)} for r in rows]

            results = {
                "businesses": hits(Business, ["name", "category"], "business",
                                   lambda b: b.name,
                                   lambda b: f"#/businesses/{b.id}"),
                "agents": hits(Agent, ["name", "role"], "agent",
                               lambda a: a.name, lambda a: f"#/agents/{a.id}"),
                "opportunities": hits(Opportunity, ["name", "category"],
                                      "opportunity", lambda o: o.name,
                                      lambda o: f"#/opportunities/{o.id}"),
                "tasks": hits(Task, ["name", "description"], "task",
                              lambda t: t.name, lambda t: "#/execution"),
                "memory": hits(MemoryRecord, ["title", "subject"], "memory",
                               lambda m: m.title, lambda m: "#/memory"),
                "security_events": hits(
                    AuditEvent, ["action", "target_id"], "security_event",
                    lambda e: e.action, lambda e: "#/security"),
            }
            total = sum(len(v) for v in results.values())
            return {"query": q, "results": results, "total": total,
                    "measured_at": self._measured(),
                    "note": "scoped by backend authorization; sensitive "
                            "operations are never executed from search (§20.1)"}
        finally:
            session.close()

    # ------------------------------------------------------------ preferences
    def get_preferences(self, principal: Principal) -> dict:
        key = f"{principal.type.value}:{principal.id}"
        session = self._session()
        try:
            row = session.execute(
                select(DashboardPreference).where(
                    DashboardPreference.principal_key == key)).scalar_one_or_none()
            prefs = dict(DEFAULT_PREFERENCES)
            if row is not None:
                prefs.update(row.preferences or {})
            return {"principal": key, "preferences": prefs,
                    "is_default": row is None}
        finally:
            session.close()

    def put_preferences(self, principal: Principal, patch: dict) -> dict:
        allowed = set(DEFAULT_PREFERENCES)
        unknown = set(patch) - allowed
        if unknown:
            raise ValidationError(
                f"unknown dashboard preference keys: {sorted(unknown)}; "
                f"allowed: {sorted(allowed)}")
        key = f"{principal.type.value}:{principal.id}"
        session = self._session()
        try:
            row = session.execute(
                select(DashboardPreference).where(
                    DashboardPreference.principal_key == key)).scalar_one_or_none()
            merged = dict(DEFAULT_PREFERENCES)
            if row is not None:
                merged.update(row.preferences or {})
            merged.update(patch)
            if row is None:
                row = DashboardPreference(principal_key=key, preferences=merged)
                session.add(row)
            else:
                row.preferences = merged
            session.commit()
            return {"principal": key, "preferences": merged, "is_default": False}
        finally:
            session.close()

    # -------------------------------------------------- survival (read view)
    def survival_overview(self) -> dict:
        session = self._session()
        try:
            decisions = _counts(session, BusinessDecision, BusinessDecision.status)
            latest: dict[str, BusinessHealthSnapshot] = {}
            for snap in session.execute(
                    select(BusinessHealthSnapshot).order_by(
                        BusinessHealthSnapshot.created_at.desc())).scalars():
                latest.setdefault(snap.business_id, snap)
            snapshots = [{
                "business_id": s.business_id, "classification": s.classification,
                "score_bps": s.score_bps, "overlay_state": s.overlay_state,
                "confidence": s.confidence, "explanation": s.explanation,
                "created_at": _iso(s.created_at)} for s in latest.values()]
            learning = session.scalar(
                select(func.count()).select_from(LearningRecord)) or 0
            contradictions = session.scalar(
                select(func.count()).select_from(MemoryContradiction)) or 0
        finally:
            session.close()
        return {"decisions_by_status": decisions,
                "latest_health_by_business": snapshots,
                "learning_records": int(learning),
                "memory_contradictions": int(contradictions),
                "source": "P-08 survival tables (latest snapshot per business)",
                "measured_at": self._measured(),
                "note": "recommendations are displayed, never executed from "
                        "the dashboard (§12.4): decisions follow P-08 policy "
                        "and owner approval"}
