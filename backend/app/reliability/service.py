"""ReliabilityService — the P-15 read/write surface over the
existing engines.

Constructed over the assembled ``Application`` (the DashboardService
precedent): P-15 owns no queue, scheduler, breaker, backup or
ledger. It samples the P-01 monitor, evaluates reliability
conditions into the incident register, computes the §13 readiness
score from live evidence, runs the §11 benchmark suite, and
delegates every control to the owning engine (P-10 backups and
emergency controls, P-12 breakers, P-07 ledger reads).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import time

from sqlalchemy import func, select, text

from ..core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from ..core.logging import get_logger
from ..database.models.base import as_utc, utcnow
from ..database.models.core import EventDeadLetter, Task
from ..database.models.operations import OperationsDeadLetter
from ..database.models.reliability import (
    BenchmarkRun, PerformanceSample, ReadinessSnapshot, ReliabilityIncident,
)
from ..permissions.models import Principal, PrincipalType
from . import benchmarks as bench
from . import constants as C
from . import readiness as readiness_engine

SYSTEM_PRINCIPAL = Principal(PrincipalType.SYSTEM, "p15-reliability")


def _iso(value: dt.datetime | None) -> str | None:
    value = as_utc(value)
    return value.isoformat() if value else None


def sample_to_dict(row: PerformanceSample) -> dict:
    return {"id": row.id, "sampled_at": _iso(row.sampled_at),
            "source": row.source,
            "cpu_percent": row.cpu_percent,
            "memory_percent": row.memory_percent,
            "disk_percent": row.disk_percent,
            "queue_depth": row.queue_depth,
            "queue_running": row.queue_running,
            "db_latency_ms": row.db_latency_ms,
            "database_healthy": row.database_healthy,
            "metrics": row.metrics or {}}


def incident_to_dict(row: ReliabilityIncident) -> dict:
    return {"id": row.id, "severity": row.severity,
            "component": row.component, "kind": row.kind,
            "title": row.title, "detail": row.detail,
            "status": row.status,
            "detected_at": _iso(row.detected_at),
            "acknowledged_at": _iso(row.acknowledged_at),
            "resolved_at": _iso(row.resolved_at),
            "root_cause": row.root_cause, "response": row.response,
            "recovery_actions": row.recovery_actions or [],
            "preventive": row.preventive, "evidence": row.evidence or {}}


def snapshot_to_dict(row: ReadinessSnapshot) -> dict:
    return {"id": row.id, "computed_at": _iso(row.computed_at),
            "overall_score": row.overall_score, "band": row.band,
            "classification": row.classification,
            "critical_gate_ok": row.critical_gate_ok,
            "categories": row.categories or {},
            "failed_checks": row.failed_checks or [],
            "blockers": row.blockers or [],
            "recommendations": row.recommendations or [],
            "evidence_summary": _evidence_summary(row.evidence or {})}


def _evidence_summary(ev: dict) -> dict:
    """A compact, UI-safe view of the evidence a score rests on."""
    return {
        "database_healthy": (ev.get("database") or {}).get("healthy"),
        "database_integrity_ok": (ev.get("database") or {}).get("integrity_ok"),
        "audit_chain_ok": (ev.get("audit_chain") or {}).get("ok"),
        "open_incidents": (ev.get("incidents") or {}).get("open_by_severity"),
        "backups": ev.get("backups"),
        "samples_count": (ev.get("samples") or {}).get("count"),
        "migration": ev.get("migration"),
    }


def benchmark_to_dict(row: BenchmarkRun) -> dict:
    return {"id": row.id, "kind": row.kind, "status": row.status,
            "started_at": _iso(row.started_at),
            "finished_at": _iso(row.finished_at),
            "results": row.results or {}, "notes": row.notes or []}


class ReliabilityService:
    def __init__(self, application):
        self._app = application
        self._log = get_logger("reliability.service")
        self._stop = asyncio.Event()

    # ------------------------------------------------------------ settings
    def seed_settings(self) -> None:
        from ..database.repositories.core import ConfigRepository
        session = self._app.session_factory()
        try:
            repo = ConfigRepository(session)
            if repo.get(C.SETTINGS_KEY) is None:
                repo.set(C.SETTINGS_KEY, json.dumps(C.DEFAULT_SETTINGS),
                         "P-15 reliability settings; owner-editable "
                         "(sampler cadence, backup policy window, "
                         "stuck-task threshold, benchmark tolerance)")
        finally:
            session.close()

    def get_settings(self) -> dict:
        from ..database.repositories.core import ConfigRepository
        session = self._app.session_factory()
        try:
            row = ConfigRepository(session).get(C.SETTINGS_KEY)
            stored = json.loads(row.value) if row and row.value else {}
        finally:
            session.close()
        merged = dict(C.DEFAULT_SETTINGS)
        merged.update(stored)
        return merged

    def update_settings(self, principal: Principal, patch: dict) -> dict:
        self._require_owner(principal, "reliability.settings.update")
        current = self.get_settings()
        ranges = {"sample_interval_seconds": (5, 3600),
                  "backup_max_age_hours": (1, 8760),
                  "stuck_task_minutes": (1, 10080)}
        for key, (lo, hi) in ranges.items():
            if key in patch:
                value = int(patch[key])
                if not lo <= value <= hi:
                    raise ValidationError(f"{key} must be within {lo}..{hi}")
                current[key] = value
        if "benchmark_tolerance_multiplier" in patch:
            value = float(patch["benchmark_tolerance_multiplier"])
            if not 1.0 <= value <= 10.0:
                raise ValidationError(
                    "benchmark_tolerance_multiplier must be within 1.0..10.0")
            current["benchmark_tolerance_multiplier"] = value
        from ..database.repositories.core import ConfigRepository
        session = self._app.session_factory()
        try:
            ConfigRepository(session).set(
                C.SETTINGS_KEY, json.dumps(current),
                "P-15 reliability settings; owner-editable")
        finally:
            session.close()
        self._audit(principal, "reliability.settings_updated", "reliability",
                    None, "owner updated P-15 reliability settings")
        return current

    # ------------------------------------------------------------ sampling
    def _db_latency_ms(self) -> float | None:
        try:
            start = time.perf_counter()
            with self._app.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return round((time.perf_counter() - start) * 1000.0, 2)
        except Exception:
            return None

    def _db_integrity(self) -> tuple[bool | None, str]:
        url = self._app.settings.effective_database_url
        if not url.startswith("sqlite"):
            return None, f"integrity check implemented for SQLite only; backend is {url.split(':', 1)[0]}"
        try:
            with self._app.engine.connect() as conn:
                rows = conn.execute(text("PRAGMA integrity_check")).fetchall()
            values = [str(r[0]).lower() for r in rows]
            ok = values == ["ok"]
            return ok, f"PRAGMA integrity_check -> {values}"
        except Exception as exc:
            return False, f"integrity check raised: {exc}"

    def record_sample(self, source: str = "manual") -> dict:
        app = self._app
        resources = app.monitor.resources()
        queue = None
        if app.monitor.queue_stats is not None:
            try:
                queue = app.monitor.queue_stats.snapshot()
            except Exception:
                queue = None
        violations = app.monitor.threshold_violations(resources)
        row = PerformanceSample(
            source=source,
            cpu_percent=resources.get("cpu_percent"),
            memory_percent=resources.get("memory_percent"),
            disk_percent=resources.get("disk_percent"),
            queue_depth=(queue or {}).get("depth"),
            queue_running=(queue or {}).get("running"),
            db_latency_ms=self._db_latency_ms(),
            database_healthy=app.monitor.database_healthy(),
            metrics={"resources": resources, "queue": queue,
                     "threshold_violations": violations,
                     "lifecycle_state": app.lifecycle.state.value})
        session = app.session_factory()
        try:
            session.add(row)
            session.commit()
            session.refresh(row)
            return sample_to_dict(row)
        finally:
            session.close()

    def list_samples(self, *, limit: int = 60) -> list[dict]:
        session = self._app.session_factory()
        try:
            rows = session.execute(
                select(PerformanceSample)
                .order_by(PerformanceSample.sampled_at.desc())
                .limit(limit)).scalars().all()
            return [sample_to_dict(r) for r in reversed(rows)]
        finally:
            session.close()

    async def run_sampler(self) -> None:
        """The long-duration harness (§11.5): sample + evaluate on
        cadence for as long as the process runs. Started by the
        application outside the test environment, beside the P-12
        operations loop; it feeds no queue and controls nothing."""
        while not self._stop.is_set():
            try:
                self.record_sample(source="sampler")
                self.evaluate_incidents()
            except Exception:
                self._log.exception("reliability sampler iteration failed")
            interval = self.get_settings()["sample_interval_seconds"]
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def stop_sampler(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------ incidents
    def _open_incident(self, session, component: str, kind: str):
        return session.execute(
            select(ReliabilityIncident)
            .where(ReliabilityIncident.component == component,
                   ReliabilityIncident.kind == kind,
                   ReliabilityIncident.status.in_({"open", "acknowledged"}))
            .limit(1)).scalars().first()

    def _raise(self, session, *, severity: str, component: str, kind: str,
               title: str, detail: str, evidence: dict, auto: bool) -> dict | None:
        if self._open_incident(session, component, kind) is not None:
            return None
        row = ReliabilityIncident(
            severity=severity, component=component, kind=kind, title=title,
            detail=detail,
            evidence={**evidence, "auto_detected": auto})
        session.add(row)
        session.flush()
        return incident_to_dict(row)

    def evaluate_incidents(self) -> dict:
        """Scan live conditions and open/auto-resolve incidents.

        Detection only — recovery actions stay with the owning
        engines and the owner (§4.5: self-healing never overrides
        P-10, never touches money, data or permissions)."""
        app = self._app
        settings = self.get_settings()
        opened: list[dict] = []
        resolved: list[str] = []
        session = app.session_factory()
        try:
            # Database down = P0 (critical gate condition).
            db_ok = app.monitor.database_healthy()
            raised = None
            if not db_ok:
                raised = self._raise(
                    session, severity="P0", component="database",
                    kind="connectivity_failure",
                    title="Database connectivity check failed",
                    detail="The P-01 monitor's connectivity check failed; "
                           "critical operations must fail safely.",
                    evidence={}, auto=True)
            if raised:
                opened.append(raised)
            resolved += self._auto_resolve(
                session, "database", "connectivity_failure", db_ok,
                "connectivity check passed again")

            # Resource thresholds = P2.
            violations = app.monitor.threshold_violations()
            raised = None
            if violations:
                raised = self._raise(
                    session, severity="P2", component="resources",
                    kind="threshold_violation",
                    title="Resource threshold exceeded",
                    detail=f"violations: {violations}",
                    evidence={"violations": violations}, auto=True)
            if raised:
                opened.append(raised)
            resolved += self._auto_resolve(
                session, "resources", "threshold_violation", not violations,
                "resources back under thresholds")

            # Open circuit breakers = P1.
            safety = app.operations.safety_status(SYSTEM_PRINCIPAL)
            open_breakers = [b for b in safety.get("circuit_breakers", [])
                             if b.get("state") == "open"]
            raised = None
            if open_breakers:
                raised = self._raise(
                    session, severity="P1", component="operations",
                    kind="circuit_breaker_open",
                    title="Circuit breaker open",
                    detail=f"open breakers: {[b.get('target') for b in open_breakers]}",
                    evidence={"breakers": open_breakers}, auto=True)
            if raised:
                opened.append(raised)
            resolved += self._auto_resolve(
                session, "operations", "circuit_breaker_open",
                not open_breakers, "no circuit breaker open")

            # Dead letters = P2 (operations) / P3 (events, cumulative).
            ops_open = safety.get("open_dead_letters", 0)
            if ops_open:
                raised = self._raise(
                    session, severity="P2", component="operations",
                    kind="dead_letters_open",
                    title="Operations dead letters open",
                    detail=f"{ops_open} operations dead letter(s) awaiting review",
                    evidence={"open": ops_open}, auto=True)
                if raised:
                    opened.append(raised)
            resolved += self._auto_resolve(
                session, "operations", "dead_letters_open", not ops_open,
                "operations dead-letter queue drained")
            event_total = session.scalar(
                select(func.count()).select_from(EventDeadLetter)) or 0
            if event_total:
                raised = self._raise(
                    session, severity="P3", component="events",
                    kind="dead_letters_present",
                    title="Event dead letters recorded",
                    detail=f"{event_total} failed/dropped event deliveries "
                           "on record (durable, P-14 DEF-I4)",
                    evidence={"total": int(event_total)}, auto=True)
                if raised:
                    opened.append(raised)

            # Backup posture = P3.
            backups = self._backup_state(settings)
            if backups["count"] == 0:
                raised = self._raise(
                    session, severity="P3", component="backup",
                    kind="no_backups",
                    title="No backups recorded",
                    detail="The P-10 backup service holds no backups; "
                           "data protection is unproven.",
                    evidence={}, auto=True)
                if raised:
                    opened.append(raised)
            resolved += self._auto_resolve(
                session, "backup", "no_backups", backups["count"] > 0,
                "a backup now exists")
            if backups["count"] > 0 and backups["stale"]:
                raised = self._raise(
                    session, severity="P3", component="backup",
                    kind="backup_stale",
                    title="Latest backup is stale",
                    detail=f"newest backup is older than the policy window "
                           f"of {settings['backup_max_age_hours']}h",
                    evidence={"latest": backups["latest"]}, auto=True)
                if raised:
                    opened.append(raised)
            resolved += self._auto_resolve(
                session, "backup", "backup_stale",
                backups["count"] > 0 and not backups["stale"],
                "a fresh backup now exists")
            session.commit()
        finally:
            session.close()
        active = self.incident_summary()["open_total"]
        return {"opened": opened, "auto_resolved": resolved, "active": active}

    def _auto_resolve(self, session, component: str, kind: str,
                      condition_clear: bool, note: str) -> list[str]:
        if not condition_clear:
            return []
        row = self._open_incident(session, component, kind)
        if row is None or not (row.evidence or {}).get("auto_detected"):
            return []
        row.status = "resolved"
        row.resolved_at = utcnow()
        row.response = f"auto-resolved by the P-15 evaluator: {note}"
        row.recovery_actions = [*(row.recovery_actions or []),
                                {"action": "auto_resolve", "note": note,
                                 "at": _iso(utcnow())}]
        session.flush()
        return [row.id]

    def create_incident(self, principal: Principal, data: dict) -> dict:
        self._require_owner(principal, "reliability.incidents.create")
        severity = str(data.get("severity", "")).upper()
        if severity not in C.SEVERITIES:
            raise ValidationError(f"severity must be one of {C.SEVERITIES}")
        component = str(data.get("component") or "").strip()
        kind = str(data.get("kind") or "").strip()
        title = str(data.get("title") or "").strip()
        if not component or not kind or not title:
            raise ValidationError("component, kind and title are required")
        session = self._app.session_factory()
        try:
            row = ReliabilityIncident(
                severity=severity, component=component, kind=kind,
                title=title, detail=str(data.get("detail") or ""),
                evidence={"auto_detected": False,
                          "created_by": f"{principal.type.value}:{principal.id}"})
            session.add(row)
            session.commit()
            session.refresh(row)
            result = incident_to_dict(row)
        finally:
            session.close()
        self._audit(principal, "reliability.incident_created", "reliability",
                    result["id"], f"manual incident {severity} {component}/{kind}")
        return result

    def list_incidents(self, *, status: str | None = None,
                       severity: str | None = None, limit: int = 50,
                       offset: int = 0) -> tuple[list[dict], int]:
        session = self._app.session_factory()
        try:
            query = select(ReliabilityIncident)
            count_query = select(func.count()).select_from(ReliabilityIncident)
            if status:
                query = query.where(ReliabilityIncident.status == status)
                count_query = count_query.where(ReliabilityIncident.status == status)
            if severity:
                query = query.where(ReliabilityIncident.severity == severity)
                count_query = count_query.where(ReliabilityIncident.severity == severity)
            total = session.scalar(count_query) or 0
            rows = session.execute(
                query.order_by(ReliabilityIncident.detected_at.desc())
                .limit(limit).offset(offset)).scalars().all()
            return [incident_to_dict(r) for r in rows], int(total)
        finally:
            session.close()

    def incident_summary(self) -> dict:
        session = self._app.session_factory()
        try:
            rows = session.execute(select(ReliabilityIncident)).scalars().all()
        finally:
            session.close()
        open_by = {sev: 0 for sev in C.SEVERITIES}
        open_total = resolved = acknowledged = 0
        for row in rows:
            if row.status in ("open", "acknowledged"):
                open_by[row.severity] = open_by.get(row.severity, 0) + 1
                open_total += 1
                if row.status == "acknowledged":
                    acknowledged += 1
            elif row.status == "resolved":
                resolved += 1
        denom = resolved + open_total
        return {"open_by_severity": open_by, "open_total": open_total,
                "acknowledged": acknowledged, "resolved": resolved,
                "total": len(rows),
                "recovery_rate": round(resolved / denom, 3) if denom else None}

    def acknowledge_incident(self, principal: Principal, incident_id: str) -> dict:
        self._require_owner(principal, "reliability.incidents.acknowledge")
        return self._transition_incident(
            principal, incident_id, "acknowledged", {})

    def resolve_incident(self, principal: Principal, incident_id: str,
                         resolution: dict) -> dict:
        self._require_owner(principal, "reliability.incidents.resolve")
        return self._transition_incident(
            principal, incident_id, "resolved", resolution)

    def _transition_incident(self, principal: Principal, incident_id: str,
                             target: str, resolution: dict) -> dict:
        session = self._app.session_factory()
        try:
            row = session.get(ReliabilityIncident, incident_id)
            if row is None:
                raise NotFoundError(f"incident {incident_id} not found")
            if row.status == "resolved":
                raise ValidationError("incident is already resolved")
            row.status = target
            now = utcnow()
            if target == "acknowledged":
                row.acknowledged_at = now
            else:
                row.resolved_at = now
                row.root_cause = resolution.get("root_cause") or row.root_cause
                row.response = resolution.get("response") or row.response
                if resolution.get("recovery_actions"):
                    row.recovery_actions = resolution["recovery_actions"]
                row.preventive = resolution.get("preventive") or row.preventive
            session.commit()
            session.refresh(row)
            result = incident_to_dict(row)
        finally:
            session.close()
        self._audit(principal, f"reliability.incident_{target}", "reliability",
                    incident_id, f"incident {target} by owner")
        return result

    # ------------------------------------------------------------ evidence
    def _backup_state(self, settings: dict | None = None) -> dict:
        settings = settings or self.get_settings()
        try:
            rows, total = self._app.security.backup.list_backups(limit=1)
        except Exception:
            return {"count": 0, "latest": None, "latest_verified": None,
                    "stale": False, "readable": False}
        latest = rows[0] if rows else None
        latest_verified = None
        stale = False
        if latest is not None:
            latest_verified = bool(latest.get("verified_at")) or \
                latest.get("status") == "verified"
            created = latest.get("created_at")
            if created:
                created_at = dt.datetime.fromisoformat(created)
                age_hours = (utcnow() - as_utc(created_at)).total_seconds() / 3600
                stale = age_hours > settings["backup_max_age_hours"]
        return {"count": int(total), "latest": latest,
                "latest_verified": latest_verified, "stale": stale,
                "readable": True}

    def _migration_state(self) -> dict:
        from pathlib import Path

        db_revision = None
        head = None
        try:
            with self._app.engine.connect() as conn:
                db_revision = conn.execute(
                    text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:
            db_revision = None
        try:
            from alembic.config import Config
            from alembic.script import ScriptDirectory
            backend_dir = Path(__file__).resolve().parents[2]
            config = Config(str(backend_dir / "alembic.ini"))
            head = ScriptDirectory.from_config(config).get_current_head()
        except Exception:
            head = None
        return {"database_revision": db_revision, "head": head,
                "is_head": (db_revision is not None and head is not None
                            and db_revision == head)}

    async def collect_evidence(self) -> dict:
        from ..dashboard.service import DashboardService
        app = self._app
        settings = self.get_settings()
        dashboard = DashboardService(app)
        health = await dashboard.system_health()
        resources = app.monitor.resources()
        violations = app.monitor.threshold_violations(resources)
        queue = None
        if app.monitor.queue_stats is not None:
            try:
                queue = app.monitor.queue_stats.snapshot()
            except Exception:
                queue = None
        safety = app.operations.safety_status(SYSTEM_PRINCIPAL)
        integrity_ok, integrity_detail = self._db_integrity()
        chain = {}
        try:
            result = app.security.chain.verify()
            chain = {"ok": bool(result.get("ok")),
                     "detail": f"checked {result.get('checked', '?')} sealed "
                               f"entries; unsealed tail: "
                               f"{result.get('unsealed_events', 0)}"}
        except Exception as exc:
            chain = {"ok": False, "detail": f"verification raised: {exc}"}
        try:
            _, open_alerts = app.security.monitor.list_alerts(
                status="open", limit=1)
        except Exception:
            open_alerts = None
        session = app.session_factory()
        try:
            sample_count = session.scalar(
                select(func.count()).select_from(PerformanceSample)) or 0
            latest_sample = session.execute(
                select(PerformanceSample)
                .order_by(PerformanceSample.sampled_at.desc()).limit(1)
            ).scalars().first()
            event_dead = session.scalar(
                select(func.count()).select_from(EventDeadLetter)) or 0
        finally:
            session.close()
        bench_state = self._benchmark_state(settings)
        financial = self.financial_reliability()
        self_checks = self._self_checks(integrity_ok, queue)
        return {
            "resources": {**resources, "threshold_violations": violations},
            "database": {"healthy": app.monitor.database_healthy(),
                         "integrity_ok": integrity_ok,
                         "integrity_detail": integrity_detail,
                         "latency_ms": self._db_latency_ms()},
            "components": health.get("checks", []),
            "queue": queue or {},
            "incidents": self.incident_summary(),
            "breakers": safety.get("circuit_breakers", []),
            "dead_letters": {
                "operations_open": safety.get("open_dead_letters", 0),
                "event_total": int(event_dead)},
            "backups": self._backup_state(settings),
            "audit_chain": chain,
            "financial": financial,
            "security": {
                "mode": app.security.emergency.current_mode(),
                "financial_suspended":
                    app.security.emergency.financial_suspended(),
                "open_alerts": open_alerts,
                "controls_wired": True},
            "samples": {"count": int(sample_count),
                        "latest_at": _iso(latest_sample.sampled_at)
                        if latest_sample else None},
            "benchmarks": bench_state,
            "self_checks": self_checks,
            "recovery": {
                "mechanism_present": True,
                "tasks_recovered_at_startup":
                    len(getattr(app, "recovered_task_ids", []) or []),
                "workflows_recovered_at_startup":
                    getattr(app, "recovered_workflow_count", 0),
                "execution_interrupted_at_startup":
                    len((getattr(app, "execution_recovery", {}) or {})
                        .get("interrupted_requests", []))},
            "migration": self._migration_state(),
            "logging_configured": bool(app.settings.effective_log_file),
        }

    def _self_checks(self, integrity_ok, queue) -> list[dict]:
        checks = []
        checks.append({"key": "database_integrity",
                       "ok": integrity_ok is True,
                       "detail": "PRAGMA integrity_check result consumed "
                                 "by the readiness evidence"})
        checks.append({"key": "queue_snapshot_readable",
                       "ok": queue is not None,
                       "detail": "P-01 queue snapshot readable"})
        try:
            res = self._app.monitor.resources()
            checks.append({"key": "monitor_resources_readable",
                           "ok": "cpu_percent" in res,
                           "detail": "P-01 monitor resources readable"})
        except Exception as exc:
            checks.append({"key": "monitor_resources_readable", "ok": False,
                           "detail": f"raised: {exc}"})
        session = self._app.session_factory()
        try:
            session.scalar(select(func.count()).select_from(EventDeadLetter))
            checks.append({"key": "dead_letter_table_readable", "ok": True,
                           "detail": "event dead-letter table readable"})
        except Exception as exc:
            checks.append({"key": "dead_letter_table_readable", "ok": False,
                           "detail": f"raised: {exc}"})
        finally:
            session.close()
        checks.append({"key": "backup_service_readable",
                       "ok": self._backup_state()["readable"],
                       "detail": "P-10 backup service list readable"})
        migration = self._migration_state()
        checks.append({"key": "migration_head_known",
                       "ok": migration["head"] is not None,
                       "detail": f"alembic head: {migration['head']}"})
        return checks

    def _benchmark_state(self, settings: dict) -> dict:
        session = self._app.session_factory()
        try:
            row = session.execute(
                select(BenchmarkRun)
                .where(BenchmarkRun.status == "completed")
                .order_by(BenchmarkRun.started_at.desc()).limit(1)
            ).scalars().first()
            latest = benchmark_to_dict(row) if row else None
        finally:
            session.close()
        if latest is None:
            return {"latest": None, "within_tolerance": None,
                    "tolerance_detail": "no completed benchmark run"}
        timings = (latest.get("results") or {}).get("timings_ms_median_of_3") or {}
        multiplier = settings["benchmark_tolerance_multiplier"]
        compared, breaches = [], []
        for key, baseline in C.P14_BASELINE_MS.items():
            if key in timings:
                compared.append(key)
                if timings[key] > baseline * multiplier:
                    breaches.append(
                        f"{key} {timings[key]}ms > {multiplier}x P-14 "
                        f"baseline {baseline}ms")
        if not compared:
            return {"latest": latest, "within_tolerance": None,
                    "tolerance_detail": "no comparable timings in the "
                                        "latest run"}
        return {"latest": latest, "within_tolerance": not breaches,
                "tolerance_detail": ("all compared medians within "
                                     f"{multiplier}x of the P-14 baseline"
                                     if not breaches else "; ".join(breaches))}

    # ------------------------------------------------------------ readiness
    async def compute_readiness(self, *, persist: bool = True) -> dict:
        evidence = await self.collect_evidence()
        scored = readiness_engine.score_readiness(evidence)
        result = {**scored, "evidence": evidence,
                  "computed_at": _iso(utcnow()), "id": None}
        if persist:
            row = ReadinessSnapshot(
                overall_score=scored["overall_score"], band=scored["band"],
                classification=scored["classification"],
                critical_gate_ok=scored["critical_gate_ok"],
                categories=scored["categories"],
                failed_checks=scored["failed_checks"],
                blockers=scored["blockers"],
                recommendations=scored["recommendations"],
                evidence=evidence)
            session = self._app.session_factory()
            try:
                session.add(row)
                session.commit()
                session.refresh(row)
                result["id"] = row.id
                result["computed_at"] = _iso(row.computed_at)
            finally:
                session.close()
        return result

    def latest_readiness(self) -> dict | None:
        session = self._app.session_factory()
        try:
            row = session.execute(
                select(ReadinessSnapshot)
                .order_by(ReadinessSnapshot.computed_at.desc()).limit(1)
            ).scalars().first()
            return snapshot_to_dict(row) if row else None
        finally:
            session.close()

    def readiness_history(self, *, limit: int = 20) -> list[dict]:
        session = self._app.session_factory()
        try:
            rows = session.execute(
                select(ReadinessSnapshot)
                .order_by(ReadinessSnapshot.computed_at.desc())
                .limit(limit)).scalars().all()
            return [snapshot_to_dict(r) for r in rows]
        finally:
            session.close()

    # ------------------------------------------------------------ benchmarks
    async def run_benchmark(self, principal: Principal,
                            kind: str = "baseline") -> dict:
        self._require_owner(principal, "reliability.benchmarks.run")
        row = BenchmarkRun(kind=kind, status="running")
        session = self._app.session_factory()
        try:
            session.add(row)
            session.commit()
            session.refresh(row)
            run_id = row.id
        finally:
            session.close()
        try:
            results = await bench.run_suite(self._app)
            status = "completed"
        except Exception as exc:
            results = {"error": f"{type(exc).__name__}: {exc}"}
            status = "failed"
        session = self._app.session_factory()
        try:
            row = session.get(BenchmarkRun, run_id)
            row.results = results
            row.notes = results.get("notes", [])
            row.status = status
            row.finished_at = utcnow()
            session.commit()
            session.refresh(row)
            result = benchmark_to_dict(row)
        finally:
            session.close()
        self._audit(principal, "reliability.benchmark_run", "reliability",
                    run_id, f"benchmark run {status}")
        return result

    def list_benchmarks(self, *, limit: int = 20) -> list[dict]:
        session = self._app.session_factory()
        try:
            rows = session.execute(
                select(BenchmarkRun)
                .order_by(BenchmarkRun.started_at.desc())
                .limit(limit)).scalars().all()
            return [benchmark_to_dict(r) for r in rows]
        finally:
            session.close()

    def create_backup(self, principal: Principal) -> dict:
        """Delegate to the P-10 backup service and verify the result.
        P-15 owns no backup machinery (§6.2 reuse)."""
        self._require_owner(principal, "reliability.backups.create")
        created = self._app.security.backup.create_backup(principal)
        verified = self._app.security.backup.verify_backup(
            principal, created["id"])
        self._audit(principal, "reliability.backup_created", "reliability",
                    created["id"], "backup created via P-10 service and verified")
        return {"created": created, "verification": verified}

    # ------------------------------------------------------------ financial
    def financial_reliability(self) -> dict:
        """§9 read-model over P-07. There is no trading in the
        platform: broker/order/position items are NOT APPLICABLE and
        are reported as such — never invented."""
        app = self._app
        per_business = []
        try:
            rows, _total = app.business.list_businesses(limit=50)
        except Exception:
            rows = []
        for row in rows:
            business_id = row.get("id")
            try:
                result = app.financial.ledger.verify_integrity(business_id)
                ok = result.get("ok", result.get("balanced"))
                per_business.append({"business_id": business_id,
                                     "integrity_ok": bool(ok),
                                     "detail": result})
            except Exception as exc:
                per_business.append({"business_id": business_id,
                                     "integrity_ok": False,
                                     "detail": f"raised: {exc}"})
        return {
            "businesses_checked": len(per_business),
            "integrity_ok": (all(b["integrity_ok"] for b in per_business)
                             if per_business else None),
            "per_business": per_business,
            "financial_suspended": app.security.emergency.financial_suspended(),
            "security_mode": app.security.emergency.current_mode(),
            "duplicate_protection": "P-07 ledger idempotency + P-01 "
                                    "approval consumption (unchanged by P-15)",
            "trading": "NOT APPLICABLE — no trading integration exists "
                       "in the platform; nothing is monitored or invented",
        }

    # ------------------------------------------------------------ stability
    def stability_report(self) -> dict:
        """§11.5 long-duration status from REAL samples only. A
        window is COMPLETE only when recorded samples actually span
        it; otherwise INCOMPLETE — never back-filled or projected."""
        settings = self.get_settings()
        session = self._app.session_factory()
        try:
            rows = session.execute(
                select(PerformanceSample)
                .order_by(PerformanceSample.sampled_at.asc())).scalars().all()
            stuck_cutoff = utcnow() - dt.timedelta(
                minutes=settings["stuck_task_minutes"])
            stuck = session.execute(
                select(Task).where(Task.status == "running",
                                   Task.started_at.is_not(None),
                                   Task.started_at < stuck_cutoff)
                .limit(10)).scalars().all()
        finally:
            session.close()
        windows = []
        for hours in settings["long_duration_targets_hours"]:
            if rows:
                span_hours = (as_utc(rows[-1].sampled_at)
                              - as_utc(rows[0].sampled_at)).total_seconds() / 3600
            else:
                span_hours = 0.0
            in_window = [r for r in rows
                         if (utcnow() - as_utc(r.sampled_at)).total_seconds()
                         <= hours * 3600]
            growth = None
            mem = [r.memory_percent for r in in_window
                   if r.memory_percent is not None]
            if len(mem) >= 10:
                decile = max(1, len(mem) // 10)
                growth = round(
                    sum(mem[-decile:]) / decile - sum(mem[:decile]) / decile, 2)
            complete = span_hours >= hours * 0.95 and len(in_window) > 0
            windows.append({
                "target_hours": hours,
                "status": "COMPLETE" if complete else "INCOMPLETE",
                "sample_span_hours": round(span_hours, 3),
                "samples_in_window": len(in_window),
                "memory_percent_growth_first_vs_last_decile": growth,
                "note": "real recorded coverage only; the window "
                        "completes when the sampler has genuinely run "
                        "for its duration"})
        return {"windows": windows,
                "total_samples": len(rows),
                "stuck_tasks": [{"id": t.id, "name": t.name,
                                 "started_at": _iso(t.started_at)}
                                for t in stuck],
                "stuck_threshold_minutes": settings["stuck_task_minutes"]}

    # ------------------------------------------------------------ overview
    async def overview(self) -> dict:
        from ..dashboard.service import DashboardService
        app = self._app
        dashboard = DashboardService(app)
        health = await dashboard.system_health()
        samples = self.list_samples(limit=60)
        safety = app.operations.safety_status(SYSTEM_PRINCIPAL)
        settings = self.get_settings()
        queue = (app.monitor.queue_stats.snapshot()
                 if app.monitor.queue_stats is not None else None)
        depth = (queue or {}).get("depth", 0)
        capacity = (queue or {}).get("capacity", 0) or 1
        ratio = depth / capacity
        backpressure = ("high" if ratio >= 0.9 else
                        "elevated" if ratio >= 0.6 else "none")
        providers = app.intelligence.cached_models_status()
        return {
            "generated_at": _iso(utcnow()),
            "health": health,
            "history": samples,
            "ai": providers or {"probed": False,
                                "detail": "no provider probe has run yet "
                                          "in this process"},
            "agents": dashboard.agents_summary(),
            "businesses": dashboard.businesses_summary(),
            "queue": {"snapshot": queue,
                      "operations_dead_letters_open":
                          safety.get("open_dead_letters", 0)},
            "reliability": {
                "incidents": self.incident_summary(),
                "circuit_breakers": safety.get("circuit_breakers", []),
                "recent_incidents": self.list_incidents(limit=5)[0]},
            "data_protection": {
                "backups": self._backup_state(settings),
                "database": {"healthy": app.monitor.database_healthy(),
                             "latency_ms": self._db_latency_ms()},
                "migration": self._migration_state()},
            "readiness": self.latest_readiness(),
            "financial": self.financial_reliability(),
            "controls": {
                "security_mode": app.security.emergency.current_mode(),
                "financial_suspended":
                    app.security.emergency.financial_suspended(),
                "source": "P-10 emergency service (P-15 delegates; it "
                          "owns no parallel control)"},
            "resources": {
                "priority_classes": C.PRIORITY_CLASSES,
                "admission_block_reason": app.monitor.admission_block_reason(),
                "backpressure": backpressure,
                "queue_capacity": capacity,
                "max_concurrency": app.settings.max_concurrency,
                "note": "admission control is the P-01 monitor guard + "
                        "P-01 queue capacity; P-15 reports and classifies "
                        "— it is not a second scheduler"},
            "stability": self.stability_report(),
        }

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _require_owner(principal: Principal, action: str) -> None:
        if principal.type != PrincipalType.OWNER:
            raise PermissionDeniedError(
                f"{action} is restricted to the owner: reliability "
                "controls change the production posture and remain "
                "owner authority under P-10 governance")

    def _audit(self, principal, action, target_type, target_id, reason) -> None:
        from ..database.models.core import AuditEvent
        from ..database.repositories.core import AuditRepository
        session = self._app.session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value if principal else "system",
                actor_id=principal.id if principal else "p15-reliability",
                action=action, target_type=target_type,
                target_id=target_id, decision="allow", reason=reason,
                correlation_id=None, details={},
                created_at=utcnow()))
        finally:
            session.close()
